"""Device-independent IQ capture loop and deterministic array replay source."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol

import numpy as np

from rf.ring_buffer import ComplexRingBuffer
from rf.sigmf_io import write_cf32


@dataclass(frozen=True)
class CaptureConfig:
    center_frequency: float
    sample_rate: float
    duration_seconds: float
    gain: float | None = None
    bandwidth: float | None = None
    channel: int = 0
    chunk_samples: int = 4096
    ring_samples: int = 262_144


@dataclass(frozen=True)
class StreamChunk:
    samples: np.ndarray
    timestamp_ns: int | None = None
    overflow: bool = False
    timeout: bool = False


class SampleSource(Protocol):
    hardware: str
    def configure(self, config: CaptureConfig) -> None: ...
    def start(self) -> None: ...
    def read(self, count: int) -> StreamChunk: ...
    def stop(self) -> None: ...


class ArraySource:
    """Replay a fixed array using the same contract as a live SDR source."""
    hardware = "array-replay"

    def __init__(self, samples: np.ndarray, sample_rate: float, *, start_timestamp_ns: int = 0, overflow_chunks: set[int] | None = None):
        self.samples = np.asarray(samples, dtype=np.complex64).reshape(-1)
        self.sample_rate = float(sample_rate)
        self.start_timestamp_ns = int(start_timestamp_ns)
        self.overflow_chunks = overflow_chunks or set()
        self.position = 0
        self.chunk_index = 0

    def configure(self, config: CaptureConfig) -> None:
        if config.sample_rate != self.sample_rate:
            raise ValueError("replay sample rate does not match capture config")

    def start(self) -> None:
        self.position = 0
        self.chunk_index = 0

    def read(self, count: int) -> StreamChunk:
        if self.position >= self.samples.size:
            return StreamChunk(np.empty(0, dtype=np.complex64), timeout=True)
        end = min(self.samples.size, self.position + count)
        values = self.samples[self.position:end]
        timestamp = self.start_timestamp_ns + round(self.position * 1e9 / self.sample_rate)
        overflow = self.chunk_index in self.overflow_chunks
        self.position, self.chunk_index = end, self.chunk_index + 1
        return StreamChunk(values, timestamp_ns=timestamp, overflow=overflow)

    def stop(self) -> None:
        pass


def capture(source: SampleSource, config: CaptureConfig) -> tuple[np.ndarray, dict]:
    if config.sample_rate <= 0 or config.duration_seconds <= 0 or config.chunk_samples <= 0:
        raise ValueError("sample rate, duration and chunk size must be positive")
    target = int(round(config.sample_rate * config.duration_seconds))
    ring = ComplexRingBuffer(max(config.ring_samples, target))
    received = timeouts = overflows = timestamp_jumps = empty_reads = 0
    first_timestamp = last_end_timestamp = None
    source.configure(config)
    source.start()
    try:
        while received < target:
            chunk = source.read(min(config.chunk_samples, target - received))
            if chunk.timeout:
                timeouts += 1
                if timeouts >= 3:
                    break
                continue
            if chunk.overflow:
                overflows += 1
            values = np.asarray(chunk.samples, dtype=np.complex64).reshape(-1)
            if not values.size:
                empty_reads += 1
                if empty_reads >= 3:
                    break
                continue
            empty_reads = 0
            if chunk.timestamp_ns is not None:
                if first_timestamp is None:
                    first_timestamp = chunk.timestamp_ns
                if last_end_timestamp is not None and abs(chunk.timestamp_ns - last_end_timestamp) > round(1.5e9 / config.sample_rate):
                    timestamp_jumps += 1
                last_end_timestamp = chunk.timestamp_ns + round(values.size * 1e9 / config.sample_rate)
            ring.write(values)
            received += values.size
    finally:
        source.stop()
    samples = ring.latest(min(received, target))
    report = {
        "schema": "iq-capture-report-v1",
        "hardware": source.hardware,
        "config": asdict(config),
        "targetSamples": target,
        "receivedSamples": int(samples.size),
        "timeouts": timeouts,
        "overflows": overflows,
        "timestampJumps": timestamp_jumps,
        "emptyReads": empty_reads,
        "ringOverwrittenSamples": ring.overwritten,
        "firstTimestampNs": first_timestamp,
        "complete": samples.size == target,
    }
    return samples, report


def capture_to_sigmf(source: SampleSource, config: CaptureConfig, path: str | Path) -> tuple[Path, Path, dict]:
    samples, report = capture(source, config)
    meta_path, data_path = write_cf32(path, samples, config.sample_rate, center_frequency=config.center_frequency, hardware=source.hardware, description="Captured through device-independent stream interface")
    return meta_path, data_path, report
