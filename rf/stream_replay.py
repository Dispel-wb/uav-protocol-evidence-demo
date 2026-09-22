"""Run the streaming pipeline against a repeatable SigMF replay."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from rf.sigmf_io import load
from rf.stream_capture import ArraySource, CaptureConfig
from rf.streaming_pipeline import run_streaming


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input")
    parser.add_argument("--repeat", type=int, default=3)
    parser.add_argument("--symbol-rates", type=float, nargs="+", default=[800, 1200, 2400])
    parser.add_argument("--chunk-samples", type=int, default=1024)
    parser.add_argument("--queue-capacity", type=int, default=8)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    if args.repeat <= 0:
        raise SystemExit("repeat must be positive")

    recording = load(args.input)
    samples = np.tile(recording.samples, args.repeat)
    config = CaptureConfig(
        center_frequency=recording.center_frequency or 0,
        sample_rate=recording.sample_rate,
        duration_seconds=samples.size / recording.sample_rate,
        chunk_samples=args.chunk_samples,
        ring_samples=recording.samples.size,
    )
    report = run_streaming(
        ArraySource(samples, recording.sample_rate),
        config,
        args.symbol_rates,
        analysis_window_samples=recording.samples.size,
        hop_samples=recording.samples.size,
        queue_capacity=args.queue_capacity,
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(output)
    print(json.dumps({
        "windows": report["analysis"]["analyzedWindows"],
        "validWindows": report["analysis"]["validProtocolWindows"],
        "finalProtocolState": report["analysis"]["protocolState"]["finalState"],
        "latencyP95Ms": report["analysis"]["latencyMilliseconds"]["p95"],
    }))
    if not report["complete"]:
        raise SystemExit("streaming replay did not complete with protocol evidence")


if __name__ == "__main__":
    main()
