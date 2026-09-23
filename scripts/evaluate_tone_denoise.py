"""Ablate edge-stationary tone cancellation across supported waveforms."""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rf.bpsk_demod import demodulate_bpsk
from rf.channel_impairments import add_tone_interference
from rf.denoise import suppress_edge_stationary_tone
from rf.fsk_demod import demodulate as demodulate_fsk
from rf.generate_iq_fixture import synthesize
from rf.generate_psk_fixture import synthesize_bpsk, synthesize_qpsk
from rf.protocol_feedback import mavlink_evidence
from rf.qpsk_demod import demodulate_qpsk


def valid(demodulator, samples, truth, enabled: bool) -> tuple[int, dict]:
    try:
        result = demodulator(
            samples,
            truth["sampleRate"],
            truth["symbolRate"],
            suppress_tone=enabled,
        )
        evidence = mavlink_evidence(result["payload"])
        return evidence["validFrames"], result.get("toneSuppression", {})
    except (ValueError, ArithmeticError):
        return 0, {}


def main() -> None:
    cases = (
        ("2-FSK", lambda seed: synthesize(seed=seed), demodulate_fsk),
        ("GFSK", lambda seed: synthesize(seed=seed, gaussian_bt=0.5), demodulate_fsk),
        ("BPSK", lambda seed: synthesize_bpsk(seed=seed), demodulate_bpsk),
        ("QPSK", lambda seed: synthesize_qpsk(seed=seed), demodulate_qpsk),
    )
    frequencies = [7_000, 9_000, 11_000]
    records = []
    for modulation, generator, demodulator in cases:
        for index, frequency in enumerate(frequencies):
            samples, truth = generator(300 + index)
            _, clean_suppression = suppress_edge_stationary_tone(
                samples,
                truth["sampleRate"],
            )
            impaired, impairment = add_tone_interference(
                samples,
                truth["sampleRate"],
                frequency_offset=frequency,
                amplitude=0.15,
                phase=0.3 + index,
            )
            raw_valid, _ = valid(demodulator, impaired, truth, False)
            cleaned_valid, suppression = valid(demodulator, impaired, truth, True)
            records.append({
                "modulation": modulation,
                "frequencyOffsetHz": frequency,
                "amplitude": impairment["amplitude"],
                "rawValidFrames": raw_valid,
                "cleanedValidFrames": cleaned_valid,
                "suppressionApplied": suppression.get("applied", False),
                "estimatedFrequencyHz": suppression.get("frequencyOffsetHz"),
                "coherenceDb": suppression.get("coherenceDb"),
                "cleanSignalSuppressionApplied": clean_suppression["applied"],
            })
    report = {
        "schema": "tone-denoise-ablation-v1",
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
        "falseAppliedCleanCases": sum(
            item["cleanSignalSuppressionApplied"] for item in records
        ),
        "records": records,
        "boundary": "Synthetic tone present in both capture edges; cancellation must be rejected when edge-stationarity is not established.",
    }
    output = ROOT / "reports" / "tone_denoise_ablation.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(output)
    keys = (
        "cases", "rawRecovered", "cleanedRecovered", "improvedCases",
        "regressedCases", "falseAppliedCleanCases",
    )
    print(json.dumps({key: report[key] for key in keys}))
    if (
        report["cleanedRecovered"] != len(records)
        or report["regressedCases"]
        or report["falseAppliedCleanCases"]
    ):
        raise SystemExit("tone denoise ablation failed")


if __name__ == "__main__":
    main()
