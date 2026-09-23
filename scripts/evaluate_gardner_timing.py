"""Compare a clock grid with Gardner tracking on variable-drift QPSK."""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rf.generate_iq_fixture import PAYLOAD
from rf.generate_psk_fixture import synthesize_qpsk
from rf.waveform_selector import select_waveform


def payload_bytes(result: dict) -> bytes:
    return (
        bytes.fromhex(result["chosenPayloadHex"])
        if result["chosenPayloadHex"] else b""
    )


def timing_method(result: dict) -> str | None:
    candidate = next((
        item for item in result["candidates"]
        if item["status"] == "decoded"
        and item["modulation"] == result["chosenModulation"]
    ), None)
    return (
        candidate.get("demodulation", {}).get("timingRecovery", {}).get("method")
        if candidate else None
    )


def main() -> None:
    expected = PAYLOAD * 4
    records = []
    for noise_index, noise in enumerate((0.02, 0.04, 0.06, 0.08)):
        for seed_index in range(2):
            seed = 20261600 + noise_index * 10 + seed_index
            samples, truth = synthesize_qpsk(
                payload=expected,
                guard_samples=40_000,
                noise_std=noise,
                carrier_offset=250,
                carrier_phase=0.8,
                rolloff=0.35,
                sample_clock_offset_ppm=-10_000,
                sample_clock_end_offset_ppm=10_000,
                seed=seed,
            )
            grid = select_waveform(
                samples,
                truth["sampleRate"],
                (truth["symbolRate"],),
                ("qpsk",),
                use_gardner=False,
            )
            tracked = select_waveform(
                samples,
                truth["sampleRate"],
                (truth["symbolRate"],),
                ("qpsk",),
                use_gardner=True,
            )
            records.append({
                "noiseStd": noise,
                "seed": seed,
                "startClockOffsetPpm": truth["sampleClockOffsetPpm"],
                "endClockOffsetPpm": truth["sampleClockEndOffsetPpm"],
                "gridCompletePayload": payload_bytes(grid)[:len(expected)] == expected,
                "gridValidProtocolFrames": grid["validProtocolFrames"],
                "trackedCompletePayload": payload_bytes(tracked)[:len(expected)] == expected,
                "trackedValidProtocolFrames": tracked["validProtocolFrames"],
                "selectedTimingMethod": timing_method(tracked),
            })
    grid_complete = sum(item["gridCompletePayload"] for item in records)
    tracked_complete = sum(item["trackedCompletePayload"] for item in records)
    regressions = sum(
        item["gridCompletePayload"] and not item["trackedCompletePayload"]
        for item in records
    )
    report = {
        "schema": "gardner-variable-clock-evaluation-v1",
        "cases": len(records),
        "gridCompletePayloads": grid_complete,
        "gardnerCompletePayloads": tracked_complete,
        "improvedCases": sum(
            not item["gridCompletePayload"] and item["trackedCompletePayload"]
            for item in records
        ),
        "regressions": regressions,
        "allGardnerUsed": all(
            item["selectedTimingMethod"] == "gardner" for item in records
        ),
        "records": records,
        "boundary": (
            "Deterministic four-frame RRC QPSK captures with clock offset ramping "
            "from -10000 to +10000 ppm. This validates software timing-loop behavior "
            "on synthetic data, not real oscillator or multipath performance."
        ),
    }
    output = ROOT / "reports" / "gardner_timing_evaluation.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(output)
    summary = {key: report[key] for key in (
        "cases", "gridCompletePayloads", "gardnerCompletePayloads",
        "improvedCases", "regressions", "allGardnerUsed",
    )}
    print(json.dumps(summary))
    if tracked_complete != len(records) or regressions or not report["allGardnerUsed"]:
        raise SystemExit("Gardner timing evaluation failed")


if __name__ == "__main__":
    main()
