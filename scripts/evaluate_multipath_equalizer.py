"""Ablate training-sequence equalization on deterministic QPSK echoes."""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rf.generate_iq_fixture import PAYLOAD
from rf.generate_psk_fixture import synthesize_qpsk
from rf.waveform_selector import select_waveform


def exact_payload(result: dict) -> bool:
    payload = (
        bytes.fromhex(result["chosenPayloadHex"])
        if result["chosenPayloadHex"] else b""
    )
    return payload[:len(PAYLOAD)] == PAYLOAD


def chosen_demodulation(result: dict) -> dict:
    candidate = next((
        item for item in result["candidates"]
        if item["status"] == "decoded"
        and item["modulation"] == result["chosenModulation"]
    ), None)
    return candidate.get("demodulation", {}) if candidate else {}


def main() -> None:
    echoes = (
        (15, -0.7 + 0j),
        (25, -0.6 + 0j),
        (35, -0.5 + 0j),
        (40, -0.5 + 0j),
        (50, 0 + 0.8j),
    )
    records = []
    for noise_index, noise in enumerate((0.03, 0.05)):
        for echo_index, (delay, gain) in enumerate(echoes):
            seed = 20261700 + noise_index * 10 + echo_index
            samples, truth = synthesize_qpsk(
                noise_std=noise,
                carrier_offset=250,
                carrier_phase=0.8,
                rolloff=0.35,
                multipath_paths=((0, 1 + 0j), (delay, gain)),
                seed=seed,
            )
            raw = select_waveform(
                samples,
                truth["sampleRate"],
                (truth["symbolRate"],),
                ("qpsk",),
                use_gardner=False,
                use_equalizer=False,
            )
            equalized = select_waveform(
                samples,
                truth["sampleRate"],
                (truth["symbolRate"],),
                ("qpsk",),
                use_gardner=False,
                use_equalizer=True,
            )
            demodulation = chosen_demodulation(equalized)
            equalizer = demodulation.get("equalization", {})
            records.append({
                "noiseStd": noise,
                "seed": seed,
                "echoDelaySamples": delay,
                "echoGain": {"i": gain.real, "q": gain.imag},
                "rawExactPayload": exact_payload(raw),
                "rawValidProtocolFrames": raw["validProtocolFrames"],
                "equalizedExactPayload": exact_payload(equalized),
                "equalizedValidProtocolFrames": equalized["validProtocolFrames"],
                "equalizerMethod": equalizer.get("method"),
                "trainingMseBefore": equalizer.get("trainingMseBefore"),
                "trainingMseAfter": equalizer.get("trainingMseAfter"),
            })
    raw_exact = sum(item["rawExactPayload"] for item in records)
    equalized_exact = sum(item["equalizedExactPayload"] for item in records)
    regressions = sum(
        item["rawExactPayload"] and not item["equalizedExactPayload"]
        for item in records
    )
    false_valid = sum(
        item["equalizedValidProtocolFrames"] > 0
        and not item["equalizedExactPayload"]
        for item in records
    )
    report = {
        "schema": "qpsk-multipath-equalizer-ablation-v1",
        "cases": len(records),
        "rawExactPayloads": raw_exact,
        "equalizedExactPayloads": equalized_exact,
        "improvedCases": sum(
            not item["rawExactPayload"] and item["equalizedExactPayload"]
            for item in records
        ),
        "regressions": regressions,
        "falseValidProtocolFrames": false_valid,
        "records": records,
        "boundary": (
            "Deterministic two-path rolloff-0.35 RRC QPSK only. The seven-tap "
            "equalizer is trained by a known preamble and selected with protocol CRC; "
            "time-varying fading and channels without a known sequence remain untested."
        ),
    }
    output = ROOT / "reports" / "multipath_equalizer_ablation.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(output)
    summary = {key: report[key] for key in (
        "cases", "rawExactPayloads", "equalizedExactPayloads",
        "improvedCases", "regressions", "falseValidProtocolFrames",
    )}
    print(json.dumps(summary))
    if equalized_exact != len(records) or regressions or false_valid:
        raise SystemExit("multipath equalizer evaluation failed")


if __name__ == "__main__":
    main()
