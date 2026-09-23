"""Ablate burst carrier phase tracking on BPSK and QPSK chirps."""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rf.generate_iq_fixture import PAYLOAD
from rf.generate_psk_fixture import synthesize_bpsk, synthesize_qpsk
from rf.waveform_selector import select_waveform


def main() -> None:
    records = []
    for index, (modulation, generator) in enumerate((
        ("BPSK", synthesize_bpsk), ("QPSK", synthesize_qpsk)
    )):
        for noise_index, noise in enumerate((0.02, 0.04)):
            for end_index, end_offset in enumerate((250, 275, 300, 350)):
                seed = 20261800 + index * 100 + noise_index * 10 + end_index
                samples, truth = generator(
                    noise_std=noise,
                    rolloff=0.35,
                    carrier_offset=250,
                    carrier_end_offset=end_offset,
                    carrier_phase=0.8,
                    seed=seed,
                )
                outcomes = []
                for tracking in (False, True):
                    result = select_waveform(
                        samples, truth["sampleRate"],
                        (truth["symbolRate"],), (modulation.lower(),),
                        use_gardner=False, use_equalizer=False,
                        use_carrier_tracking=tracking,
                    )
                    payload = (
                        bytes.fromhex(result["chosenPayloadHex"])
                        if result["chosenPayloadHex"] else b""
                    )
                    candidate = next((
                        item for item in result["candidates"]
                        if item["status"] == "decoded"
                    ), None)
                    outcomes.append({
                        "exact": payload[:len(PAYLOAD)] == PAYLOAD,
                        "validFrames": result["validProtocolFrames"],
                        "chosenModulation": result["chosenModulation"],
                        "carrierTracking": (
                            candidate["demodulation"]["carrierTracking"]
                            if candidate else None
                        ),
                    })
                fixed, tracked = outcomes
                records.append({
                    "transmitModulation": modulation,
                    "noiseStd": noise,
                    "seed": seed,
                    "startCarrierOffsetHz": 250,
                    "endCarrierOffsetHz": end_offset,
                    "fixedExactPayload": fixed["exact"],
                    "trackedExactPayload": tracked["exact"],
                    "fixedValidProtocolFrames": fixed["validFrames"],
                    "trackedValidProtocolFrames": tracked["validFrames"],
                    "chosenModulation": tracked["chosenModulation"],
                    "selectedCarrierTracking": tracked["carrierTracking"],
                })
    report = {
        "schema": "psk-carrier-drift-ablation-v1",
        "cases": len(records),
        "fixedExactPayloads": sum(item["fixedExactPayload"] for item in records),
        "trackedExactPayloads": sum(item["trackedExactPayload"] for item in records),
        "improvedCases": sum(
            not item["fixedExactPayload"] and item["trackedExactPayload"]
            for item in records
        ),
        "regressions": sum(
            item["fixedExactPayload"] and not item["trackedExactPayload"]
            for item in records
        ),
        "wrongModulation": sum(
            item["chosenModulation"] != item["transmitModulation"]
            for item in records
        ),
        "falseValidProtocolFrames": sum(
            item["trackedValidProtocolFrames"] > 0
            and not item["trackedExactPayload"] for item in records
        ),
        "records": records,
        "boundary": (
            "Deterministic linearly varying carrier frequency on short synthetic "
            "RRC PSK bursts. Quadratic burst phase fitting assumes smooth drift; "
            "phase steps, faster wander and real oscillators remain untested."
        ),
    }
    output = ROOT / "reports" / "carrier_drift_ablation.json"
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    keys = ("cases", "fixedExactPayloads", "trackedExactPayloads",
            "improvedCases", "regressions", "wrongModulation",
            "falseValidProtocolFrames")
    print(output)
    print(json.dumps({key: report[key] for key in keys}))
    if (report["trackedExactPayloads"] != report["cases"]
            or report["regressions"] or report["wrongModulation"]
            or report["falseValidProtocolFrames"]):
        raise SystemExit("carrier drift evaluation failed")


if __name__ == "__main__":
    main()
