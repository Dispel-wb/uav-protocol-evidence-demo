"""Sweep deterministic QPSK noise and carrier offsets through waveform selection."""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rf.generate_iq_fixture import PAYLOAD
from rf.generate_psk_fixture import synthesize_qpsk
from rf.waveform_selector import select_waveform


def main() -> None:
    noise_levels = [0.02, 0.04, 0.08, 0.12]
    offsets = [-400, -200, 0, 200, 400]
    records = []
    for noise_index, noise in enumerate(noise_levels):
        for offset_index, offset in enumerate(offsets):
            samples, truth = synthesize_qpsk(
                noise_std=noise,
                carrier_offset=offset,
                carrier_phase=0.8,
                seed=20261300 + noise_index * 10 + offset_index,
            )
            result = select_waveform(
                samples,
                truth["sampleRate"],
                [800, truth["symbolRate"], 2400],
                ["fsk", "bpsk", "qpsk"],
            )
            payload = (
                bytes.fromhex(result["chosenPayloadHex"])
                if result["chosenPayloadHex"] else b""
            )
            records.append({
                "noiseStd": noise,
                "carrierOffsetHz": offset,
                "chosenModulation": result["chosenModulation"],
                "chosenSymbolRate": result["chosenSymbolRate"],
                "validProtocolFrames": result["validProtocolFrames"],
                "exactPayload": payload[:len(PAYLOAD)] == PAYLOAD,
            })
    required = [item for item in records if item["noiseStd"] <= 0.04]
    wrong_modulation = sum(
        item["chosenModulation"] not in (None, "QPSK")
        for item in records
    )
    false_valid = sum(
        item["validProtocolFrames"] > 0 and not item["exactPayload"]
        for item in records
    )
    report = {
        "schema": "qpsk-robustness-v1",
        "cases": len(records),
        "requiredRangeCases": len(required),
        "requiredRangeExact": sum(item["exactPayload"] for item in required),
        "allExact": sum(item["exactPayload"] for item in records),
        "wrongModulation": wrong_modulation,
        "falseValidProtocolFrames": false_valid,
        "records": records,
        "boundary": "Deterministic rectangular-pulse QPSK only; this does not represent shaped pulses, timing drift, multipath or real oscillators.",
    }
    output = ROOT / "reports" / "qpsk_robustness.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(output)
    keys = (
        "cases", "requiredRangeCases", "requiredRangeExact", "allExact",
        "wrongModulation", "falseValidProtocolFrames",
    )
    print(json.dumps({key: report[key] for key in keys}))
    if report["requiredRangeExact"] != len(required) or wrong_modulation or false_valid:
        raise SystemExit("QPSK robustness evaluation failed")


if __name__ == "__main__":
    main()
