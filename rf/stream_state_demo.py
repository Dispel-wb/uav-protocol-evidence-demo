"""Run the complete synthetic RF-to-protocol-state trajectory."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from rf.state_fixture import synthesize_trajectory
from rf.stream_capture import ArraySource, CaptureConfig
from rf.streaming_pipeline import run_streaming


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    samples, truth = synthesize_trajectory()
    config = CaptureConfig(
        center_frequency=433_920_000,
        sample_rate=truth["sampleRate"],
        duration_seconds=samples.size / truth["sampleRate"],
        chunk_samples=710,
        ring_samples=truth["windowSamples"],
    )
    report = run_streaming(
        ArraySource(samples, truth["sampleRate"]),
        config,
        [800, 1_200, 2_400],
        analysis_window_samples=truth["windowSamples"],
        hop_samples=truth["windowSamples"],
        queue_capacity=2,
    )
    report["truth"] = truth
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    state = report["analysis"]["protocolState"]
    summary = {
        "windows": report["analysis"]["analyzedWindows"],
        "validWindows": report["analysis"]["validProtocolWindows"],
        "finalState": state["finalState"],
        "links": len(state["links"]),
        "violations": len(state["violations"]),
    }
    print(output)
    print(json.dumps(summary))
    if state["finalState"] != truth["expectedFinalState"]:
        raise SystemExit("RF trajectory did not reach the expected protocol state")
    if state["violations"]:
        raise SystemExit("RF trajectory produced unexpected state violations")


if __name__ == "__main__":
    main()
