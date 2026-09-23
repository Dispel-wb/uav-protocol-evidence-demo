"""Ablate sparse impulse suppression across all supported waveform families."""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rf.bpsk_demod import demodulate_bpsk
from rf.channel_impairments import add_impulsive_noise
from rf.fsk_demod import demodulate as demodulate_fsk
from rf.generate_iq_fixture import synthesize
from rf.generate_psk_fixture import synthesize_bpsk, synthesize_qpsk
from rf.protocol_feedback import mavlink_evidence
from rf.qpsk_demod import demodulate_qpsk


def valid(demodulator, samples, truth, enabled: bool) -> tuple[int, int]:
    try:
        result = demodulator(
            samples,
            truth["sampleRate"],
            truth["symbolRate"],
            suppress_impulsive=enabled,
        )
        evidence = mavlink_evidence(result["payload"])
        report = result.get("impulseSuppression", {})
        return evidence["validFrames"], report.get("suppressedSamples", 0)
    except (ValueError, ArithmeticError):
        return 0, 0


def main() -> None:
    cases = (
        ("2-FSK", lambda seed: synthesize(seed=seed), demodulate_fsk),
        ("GFSK", lambda seed: synthesize(seed=seed, gaussian_bt=0.5), demodulate_fsk),
        ("BPSK", lambda seed: synthesize_bpsk(seed=seed), demodulate_bpsk),
        ("QPSK", lambda seed: synthesize_qpsk(seed=seed), demodulate_qpsk),
    )
    records = []
    for modulation, generator, demodulator in cases:
        for index in range(5):
            samples, truth = generator(100 + index)
            impaired, impairment = add_impulsive_noise(
                samples,
                truth["startSample"],
                truth["endSample"],
                fraction=0.01,
                amplitude=3.0,
                seed=200 + index,
            )
            raw_valid, _ = valid(demodulator, impaired, truth, False)
            cleaned_valid, suppressed = valid(demodulator, impaired, truth, True)
            records.append({
                "modulation": modulation,
                "seed": index,
                "impulseCount": impairment["count"],
                "rawValidFrames": raw_valid,
                "cleanedValidFrames": cleaned_valid,
                "suppressedSamples": suppressed,
            })
    report = {
        "schema": "impulse-denoise-ablation-v1",
        "cases": len(records),
        "rawRecovered": sum(item["rawValidFrames"] > 0 for item in records),
        "cleanedRecovered": sum(item["cleanedValidFrames"] > 0 for item in records),
        "improvedCases": sum(
            item["rawValidFrames"] == 0 and item["cleanedValidFrames"] > 0
            for item in records
        ),
        "regressedCases": sum(
            item["rawValidFrames"] > 0 and item["cleanedValidFrames"] == 0
            for item in records
        ),
        "records": records,
        "boundary": "Deterministic sparse high-amplitude impulses on synthetic bursts; this does not cover continuous interference or real ADC clipping.",
    }
    output = ROOT / "reports" / "impulse_denoise_ablation.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(output)
    keys = ("cases", "rawRecovered", "cleanedRecovered", "improvedCases", "regressedCases")
    print(json.dumps({key: report[key] for key in keys}))
    if report["cleanedRecovered"] != len(records) or report["regressedCases"]:
        raise SystemExit("impulse denoise ablation failed")


if __name__ == "__main__":
    main()
