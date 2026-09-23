"""Ablate PSK timing-drift search against a fixed symbol clock."""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rf.generate_iq_fixture import PAYLOAD
from rf.generate_psk_fixture import synthesize_bpsk, synthesize_qpsk
from rf.waveform_selector import select_waveform


def exact_payload(result: dict) -> bool:
    payload = (
        bytes.fromhex(result["chosenPayloadHex"])
        if result["chosenPayloadHex"] else b""
    )
    return payload[:len(PAYLOAD)] == PAYLOAD


def main() -> None:
    records = []
    generators = (("BPSK", synthesize_bpsk), ("QPSK", synthesize_qpsk))
    offsets = (-10_000, -5_000, 0, 5_000, 10_000)
    for modulation_index, (modulation, generator) in enumerate(generators):
        for offset_index, offset_ppm in enumerate(offsets):
            samples, truth = generator(
                noise_std=0.04,
                carrier_offset=250,
                carrier_phase=0.8,
                rolloff=0.35,
                sample_clock_offset_ppm=offset_ppm,
                seed=20261500 + modulation_index * 100 + offset_index,
            )
            fixed = select_waveform(
                samples,
                truth["sampleRate"],
                (truth["symbolRate"],),
                ("bpsk", "qpsk"),
                clock_offsets_ppm=(0,),
                use_gardner=False,
            )
            adaptive = select_waveform(
                samples,
                truth["sampleRate"],
                (truth["symbolRate"],),
                ("bpsk", "qpsk"),
                use_gardner=False,
            )
            selected = next((
                item for item in adaptive["candidates"]
                if item["status"] == "decoded"
                and item["modulation"] == adaptive["chosenModulation"]
            ), None)
            records.append({
                "transmitModulation": modulation,
                "injectedClockOffsetPpm": offset_ppm,
                "fixedClockExactPayload": exact_payload(fixed),
                "adaptiveExactPayload": exact_payload(adaptive),
                "chosenModulation": adaptive["chosenModulation"],
                "selectedClockOffsetPpm": (
                    selected.get("demodulation", {}).get("sampleClockOffsetPpm")
                    if selected else None
                ),
                "validProtocolFrames": adaptive["validProtocolFrames"],
            })
    fixed_exact = sum(item["fixedClockExactPayload"] for item in records)
    adaptive_exact = sum(item["adaptiveExactPayload"] for item in records)
    wrong_modulation = sum(
        item["chosenModulation"] != item["transmitModulation"] for item in records
    )
    false_valid = sum(
        item["validProtocolFrames"] > 0 and not item["adaptiveExactPayload"]
        for item in records
    )
    report = {
        "schema": "psk-clock-drift-ablation-v1",
        "cases": len(records),
        "fixedClockExactPayloads": fixed_exact,
        "adaptiveExactPayloads": adaptive_exact,
        "improvedCases": sum(
            not item["fixedClockExactPayload"] and item["adaptiveExactPayload"]
            for item in records
        ),
        "regressions": sum(
            item["fixedClockExactPayload"] and not item["adaptiveExactPayload"]
            for item in records
        ),
        "wrongModulation": wrong_modulation,
        "falseValidProtocolFrames": false_valid,
        "records": records,
        "boundary": (
            "Short deterministic rolloff-0.35 RRC bursts with an intentionally wide "
            "clock-stress range up to one percent. Candidate-grid recovery is not a "
            "continuous timing loop and does not establish real oscillator tolerance."
        ),
    }
    output = ROOT / "reports" / "psk_clock_drift_ablation.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(output)
    summary = {key: report[key] for key in (
        "cases", "fixedClockExactPayloads", "adaptiveExactPayloads",
        "improvedCases", "regressions", "wrongModulation",
        "falseValidProtocolFrames",
    )}
    print(json.dumps(summary))
    if adaptive_exact != len(records) or report["regressions"] or wrong_modulation or false_valid:
        raise SystemExit("PSK clock-drift evaluation failed")


if __name__ == "__main__":
    main()
