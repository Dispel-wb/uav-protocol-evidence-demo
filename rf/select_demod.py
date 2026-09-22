"""CLI for evidence-preserving 2-FSK candidate selection."""
import argparse
import json
from pathlib import Path

from rf.candidate_selector import select
from rf.sigmf_io import load


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("capture")
    parser.add_argument("--symbol-rates", nargs="+", type=float, required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    capture = load(args.capture)
    report = select(capture.samples, capture.sample_rate, args.symbol_rates)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
