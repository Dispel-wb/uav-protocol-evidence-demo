"""List SoapySDR devices or record one finite capture to SigMF."""
import argparse
import json

from rf.soapy_source import SoapySource
from rf.stream_capture import CaptureConfig, capture_to_sigmf


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--args", default="")
    parser.add_argument("--frequency", type=float)
    parser.add_argument("--sample-rate", type=float)
    parser.add_argument("--duration", type=float, default=1)
    parser.add_argument("--gain", type=float)
    parser.add_argument("--bandwidth", type=float)
    parser.add_argument("--output", default="captures/live")
    options = parser.parse_args()
    if options.list:
        print(json.dumps(SoapySource.enumerate(options.args), ensure_ascii=False, indent=2))
        return
    if options.frequency is None or options.sample_rate is None:
        parser.error("--frequency and --sample-rate are required for capture")
    source = SoapySource(options.args)
    config = CaptureConfig(center_frequency=options.frequency, sample_rate=options.sample_rate, duration_seconds=options.duration, gain=options.gain, bandwidth=options.bandwidth)
    meta, data, report = capture_to_sigmf(source, config, options.output)
    print(meta)
    print(data)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
