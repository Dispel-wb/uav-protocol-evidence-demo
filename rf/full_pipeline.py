"""Join a finite sample source to quality analysis, candidate demodulation and protocol evidence."""
from __future__ import annotations

import time
from typing import Iterable

from rf.candidate_selector import select
from rf.signal_quality import analyze
from rf.stream_capture import CaptureConfig, SampleSource, capture


def run(source: SampleSource, config: CaptureConfig, symbol_rates: Iterable[float]) -> dict:
    started = time.perf_counter()
    samples, capture_report = capture(source, config)
    quality = analyze(samples, config.sample_rate)
    selection = select(samples, config.sample_rate, symbol_rates)
    elapsed_ms = (time.perf_counter() - started) * 1000
    return {
        "schema": "rf-to-protocol-pipeline-v1",
        "capture": capture_report,
        "quality": quality,
        "selection": selection,
        "processingMilliseconds": elapsed_ms,
        "complete": capture_report["complete"] and selection["validProtocolFrames"] > 0,
        "boundary": "当前实现对有限采样窗口完成端到端处理；实时流式DSP和硬件持续运行仍需验证。",
    }
