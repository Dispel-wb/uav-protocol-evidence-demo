"""Demodulate the fixed 2-FSK baseline and emit bytes plus an evidence report."""
import argparse
import json
from pathlib import Path

import numpy as np

from rf.fsk_demod import demodulate
from rf.sigmf_io import load


def bit_errors(observed: bytes, expected: bytes) -> int:
    width = min(len(observed), len(expected))
    differences = sum(int(value).bit_count() for value in np.bitwise_xor(np.frombuffer(observed[:width], dtype=np.uint8), np.frombuffer(expected[:width], dtype=np.uint8)))
    return differences + abs(len(observed) - len(expected)) * 8


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("capture")
    parser.add_argument("--symbol-rate", type=float, required=True)
    parser.add_argument("--truth")
    parser.add_argument("--output", required=True)
    parser.add_argument("--hex-output", required=True)
    args = parser.parse_args()
    capture = load(args.capture)
    report = demodulate(capture.samples, capture.sample_rate, args.symbol_rate)
    payload = report.pop("payload")
    if args.truth:
        truth = json.loads(Path(args.truth).read_text(encoding="utf-8"))
        expected = bytes.fromhex(truth["payloadHex"])
        recovered = payload[:len(expected)]
        errors = bit_errors(recovered, expected)
        report["verification"] = {"expectedBytes": len(expected), "recoveredBytes": len(recovered), "bitErrors": errors, "ber": errors / (len(expected) * 8), "exactPrefix": recovered == expected}
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    Path(args.hex_output).write_text(payload.hex(" ").upper(), encoding="ascii")
    print(args.output)
    print(args.hex_output)


if __name__ == "__main__":
    main()
