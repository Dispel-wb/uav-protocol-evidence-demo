"""Analyze a SigMF capture and write a JSON quality report."""
import argparse
import json
from pathlib import Path

from rf.sigmf_io import load
from rf.signal_quality import analyze


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("capture", help="SigMF base path, .sigmf-meta, or .sigmf-data")
    parser.add_argument("--output", help="JSON output path")
    args = parser.parse_args()
    capture = load(args.capture)
    report = analyze(capture.samples, capture.sample_rate)
    report["capture"] = {
        "datatype": capture.datatype,
        "centerFrequency": capture.center_frequency,
        "hardware": capture.hardware,
    }
    output = Path(args.output) if args.output else Path(args.capture).with_suffix(".quality.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
