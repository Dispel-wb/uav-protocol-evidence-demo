"""Create an explicit readiness report for real SoapySDR capture."""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import platform
import sys

from rf.soapy_source import SoapySource


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--args", default="")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    bindings = importlib.util.find_spec("SoapySDR") is not None
    devices = []
    enumeration_error = None
    if bindings:
        try:
            devices = SoapySource.enumerate(args.args)
        except RuntimeError as error:
            enumeration_error = str(error)
    blockers = []
    if not bindings:
        blockers.append("SoapySDR Python bindings are not installed")
    if bindings and enumeration_error:
        blockers.append(enumeration_error)
    if bindings and not enumeration_error and not devices:
        blockers.append("No SoapySDR-compatible receive device was enumerated")
    report = {
        "schema": "sdr-hardware-readiness-v1",
        "platform": platform.platform(),
        "python": sys.version.split()[0],
        "soapyBindingsInstalled": bindings,
        "deviceArguments": args.args,
        "devices": devices,
        "enumerationError": enumeration_error,
        "readyForCapture": bindings and bool(devices) and not enumeration_error,
        "blockers": blockers,
        "nextEvidence": [
            "enumerated device identity and driver",
            "finite SigMF capture with hardware timestamps",
            "continuous run with timeout, overflow and latency statistics",
        ],
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(output)
    print(json.dumps({
        "readyForCapture": report["readyForCapture"],
        "deviceCount": len(devices),
        "blockers": blockers,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
