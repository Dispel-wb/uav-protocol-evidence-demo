"""Operator-controlled SoapySDR capture and streaming protocol analysis."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import signal
from threading import Event

from rf.soapy_source import SoapySource
from rf.stream_capture import CaptureConfig
from rf.streaming_pipeline import run_streaming


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--args", default="", help="SoapySDR device arguments")
    parser.add_argument("--frequency", type=float, required=True)
    parser.add_argument("--sample-rate", type=float, required=True)
    parser.add_argument("--gain", type=float)
    parser.add_argument("--bandwidth", type=float)
    parser.add_argument("--channel", type=int, default=0)
    parser.add_argument("--chunk-samples", type=int, default=4096)
    parser.add_argument("--window-seconds", type=float, default=0.5)
    parser.add_argument("--hop-seconds", type=float, default=0.5)
    parser.add_argument("--queue-capacity", type=int, default=8)
    parser.add_argument("--symbol-rates", type=float, nargs="+", default=[1200])
    parser.add_argument("--modulations", nargs="+", default=["fsk"])
    parser.add_argument("--max-duration", type=float, default=3600)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    if args.window_seconds <= 0 or args.hop_seconds <= 0 or args.max_duration <= 0:
        raise SystemExit("window, hop and maximum duration must be positive")

    stop = Event()

    def request_stop(_signum, _frame) -> None:
        stop.set()

    previous_handlers = {
        name: signal.signal(name, request_stop)
        for name in (signal.SIGINT, signal.SIGTERM)
    }
    try:
        source = SoapySource(args.args)
        config = CaptureConfig(
            center_frequency=args.frequency,
            sample_rate=args.sample_rate,
            duration_seconds=args.max_duration,
            gain=args.gain,
            bandwidth=args.bandwidth,
            channel=args.channel,
            chunk_samples=args.chunk_samples,
            ring_samples=round(args.sample_rate * args.window_seconds),
        )
        report = run_streaming(
            source,
            config,
            args.symbol_rates,
            analysis_window_samples=round(args.sample_rate * args.window_seconds),
            hop_samples=round(args.sample_rate * args.hop_seconds),
            queue_capacity=args.queue_capacity,
            stop_event=stop,
            modulations=args.modulations,
        )
    finally:
        for name, handler in previous_handlers.items():
            signal.signal(name, handler)

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(output)
    print(json.dumps({
        "stopReason": report["capture"]["stopReason"],
        "receivedSamples": report["capture"]["receivedSamples"],
        "validProtocolWindows": report["analysis"]["validProtocolWindows"],
        "finalProtocolState": report["analysis"]["protocolState"]["finalState"],
    }))


if __name__ == "__main__":
    main()
