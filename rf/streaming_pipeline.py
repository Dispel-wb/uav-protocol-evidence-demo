"""Bounded streaming pipeline with isolated capture and analysis stages."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from queue import Full, Queue
from threading import Event, Lock, Thread
import time
from typing import Iterable

import numpy as np

from rf.candidate_selector import select
from rf.protocol_feedback import mavlink_evidence, update_mavlink_continuity
from rf.protocol_state import ProtocolStateTracker
from rf.ring_buffer import ComplexRingBuffer
from rf.stream_capture import CaptureConfig, SampleSource, StreamChunk


@dataclass(frozen=True)
class QueuedChunk:
    chunk: StreamChunk
    end_sample: int
    queued_ns: int


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    return float(np.percentile(np.asarray(values), percentile))


def run_streaming(
    source: SampleSource,
    config: CaptureConfig,
    symbol_rates: Iterable[float],
    *,
    analysis_window_samples: int,
    hop_samples: int | None = None,
    queue_capacity: int = 8,
) -> dict:
    """Process a finite-duration source through a continuous chunk pipeline."""
    if analysis_window_samples <= 0 or queue_capacity <= 0:
        raise ValueError("analysis window and queue capacity must be positive")
    hop = hop_samples or analysis_window_samples
    if hop <= 0 or hop > analysis_window_samples:
        raise ValueError("hop must be positive and no larger than the analysis window")
    rates = tuple(symbol_rates)
    if not rates:
        raise ValueError("at least one symbol-rate candidate is required")

    target = int(round(config.sample_rate * config.duration_seconds))
    queue: Queue[QueuedChunk | None] = Queue(maxsize=queue_capacity)
    counters = {
        "receivedSamples": 0,
        "timeouts": 0,
        "overflows": 0,
        "emptyReads": 0,
        "timestampJumps": 0,
        "queueBackpressureEvents": 0,
    }
    counter_lock = Lock()
    stop_requested = Event()
    reader_error: list[BaseException] = []

    def enqueue(item: QueuedChunk | None) -> bool:
        while not stop_requested.is_set():
            try:
                queue.put(item, timeout=0.05)
                return True
            except Full:
                with counter_lock:
                    counters["queueBackpressureEvents"] += 1
        return False

    def read_source() -> None:
        last_end_timestamp = None
        consecutive_timeouts = consecutive_empty = 0
        try:
            source.configure(config)
            source.start()
            while counters["receivedSamples"] < target:
                remaining = target - counters["receivedSamples"]
                chunk = source.read(min(config.chunk_samples, remaining))
                if chunk.timeout:
                    counters["timeouts"] += 1
                    consecutive_timeouts += 1
                    if consecutive_timeouts >= 3:
                        break
                    continue
                consecutive_timeouts = 0
                values = np.asarray(chunk.samples, dtype=np.complex64).reshape(-1)
                if not values.size:
                    counters["emptyReads"] += 1
                    consecutive_empty += 1
                    if consecutive_empty >= 3:
                        break
                    continue
                consecutive_empty = 0
                if chunk.overflow:
                    counters["overflows"] += 1
                if chunk.timestamp_ns is not None:
                    tolerance = round(1.5e9 / config.sample_rate)
                    if last_end_timestamp is not None:
                        if abs(chunk.timestamp_ns - last_end_timestamp) > tolerance:
                            counters["timestampJumps"] += 1
                    last_end_timestamp = chunk.timestamp_ns + round(
                        values.size * 1e9 / config.sample_rate
                    )
                counters["receivedSamples"] += values.size
                queued = QueuedChunk(
                    chunk,
                    counters["receivedSamples"],
                    time.perf_counter_ns(),
                )
                if not enqueue(queued):
                    break
        except BaseException as error:
            reader_error.append(error)
        finally:
            try:
                source.stop()
            except BaseException as error:
                reader_error.append(error)
            if not stop_requested.is_set():
                enqueue(None)

    started_ns = time.perf_counter_ns()
    reader = Thread(target=read_source, name="iq-capture", daemon=True)
    reader.start()
    ring = ComplexRingBuffer(analysis_window_samples)
    samples_since_analysis = 0
    window_reports = []
    decision_latencies = []
    last_sequences: dict[tuple[int, int], int] = {}
    continuity_totals = {"missingFrames": 0, "duplicates": 0, "outOfOrder": 0}
    state_tracker = ProtocolStateTracker()
    analysis_error = None
    try:
        while True:
            queued = queue.get()
            if queued is None:
                break
            values = np.asarray(queued.chunk.samples, dtype=np.complex64).reshape(-1)
            ring.write(values)
            samples_since_analysis += values.size
            if ring.size < analysis_window_samples or samples_since_analysis < hop:
                continue
            samples_since_analysis %= hop
            analysis_started_ns = time.perf_counter_ns()
            selection = select(
                ring.latest(analysis_window_samples),
                config.sample_rate,
                rates,
            )
            chosen_hex = selection["chosenPayloadHex"]
            evidence = (
                mavlink_evidence(bytes.fromhex(chosen_hex))
                if chosen_hex else {"frames": []}
            )
            continuity = update_mavlink_continuity(evidence, last_sequences)
            state_delta = state_tracker.update(evidence["frames"], len(window_reports))
            for key in continuity_totals:
                continuity_totals[key] += continuity[key]
            finished_ns = time.perf_counter_ns()
            decision_ms = (finished_ns - queued.queued_ns) / 1e6
            decision_latencies.append(decision_ms)
            window_reports.append({
                "startSample": queued.end_sample - analysis_window_samples,
                "endSample": queued.end_sample,
                "processingMilliseconds": (finished_ns - analysis_started_ns) / 1e6,
                "ingestToDecisionMilliseconds": decision_ms,
                "chosenSymbolRate": selection["chosenSymbolRate"],
                "validProtocolFrames": selection["validProtocolFrames"],
                "chosenPayloadHex": chosen_hex,
                "protocolContinuity": continuity,
                "protocolState": state_delta,
            })
    except BaseException as error:
        analysis_error = error
        stop_requested.set()
    finally:
        reader.join(timeout=5)
    if reader.is_alive():
        raise RuntimeError("capture stage did not stop")
    if analysis_error is not None:
        raise RuntimeError("analysis stage failed") from analysis_error
    if reader_error:
        raise RuntimeError("capture stage failed") from reader_error[0]

    elapsed_ms = (time.perf_counter_ns() - started_ns) / 1e6
    valid_windows = sum(item["validProtocolFrames"] > 0 for item in window_reports)
    state_evidence = state_tracker.finalize()
    return {
        "schema": "streaming-rf-pipeline-v1",
        "hardware": source.hardware,
        "config": asdict(config),
        "analysisWindowSamples": analysis_window_samples,
        "hopSamples": hop,
        "queueCapacity": queue_capacity,
        "capture": {
            **counters,
            "targetSamples": target,
            "complete": counters["receivedSamples"] == target,
        },
        "analysis": {
            "analyzedWindows": len(window_reports),
            "validProtocolWindows": valid_windows,
            "latencyMilliseconds": {
                "p50": _percentile(decision_latencies, 50),
                "p95": _percentile(decision_latencies, 95),
                "max": max(decision_latencies, default=None),
            },
            "protocolContinuity": continuity_totals,
            "protocolState": state_evidence,
            "windows": window_reports,
        },
        "elapsedMilliseconds": elapsed_ms,
        "complete": counters["receivedSamples"] == target and valid_windows > 0,
        "boundary": "采样与分析已使用有界队列隔离；结果来自有限时长回放，尚未证明真实硬件持续运行性能。",
    }
