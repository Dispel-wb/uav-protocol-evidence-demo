"""Evaluate shaped BPSK/QPSK through the common waveform selector."""
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
    generators = (("BPSK", synthesize_bpsk), ("QPSK", synthesize_qpsk))
    for modulation_index, (modulation, generator) in enumerate(generators):
        for noise_index, noise in enumerate((0.02, 0.04, 0.08)):
            for offset_index, offset in enumerate((-300, 0, 300)):
                samples, truth = generator(
                    noise_std=noise,
                    carrier_offset=offset,
                    carrier_phase=0.8,
                    rolloff=0.35,
                    seed=20261400 + modulation_index * 100 + noise_index * 10 + offset_index,
                )
                result = select_waveform(
                    samples,
                    truth["sampleRate"],
                    (800, truth["symbolRate"], 2400),
                    ("fsk", "bpsk", "qpsk"),
                    use_gardner=False,
                    use_equalizer=False,
                )
                payload = (
                    bytes.fromhex(result["chosenPayloadHex"])
                    if result["chosenPayloadHex"] else b""
                )
                chosen = next((
                    item for item in result["candidates"]
                    if item["status"] == "decoded"
                    and item["modulation"] == result["chosenModulation"]
                    and item["symbolRate"] == result["chosenSymbolRate"]
                ), None)
                records.append({
                    "transmitModulation": modulation,
                    "pulseShape": truth["pulseShape"],
                    "rolloff": truth["rolloff"],
                    "noiseStd": noise,
                    "carrierOffsetHz": offset,
                    "chosenModulation": result["chosenModulation"],
                    "chosenSymbolRate": result["chosenSymbolRate"],
                    "receiveFilter": (
                        chosen.get("demodulation", {}).get("receiveFilter")
                        if chosen else None
                    ),
                    "validProtocolFrames": result["validProtocolFrames"],
                    "exactPayload": payload[:len(PAYLOAD)] == PAYLOAD,
                })
    exact = sum(item["exactPayload"] for item in records)
    wrong_modulation = sum(
        item["chosenModulation"] != item["transmitModulation"] for item in records
    )
    false_valid = sum(
        item["validProtocolFrames"] > 0 and not item["exactPayload"]
        for item in records
    )
    receive_filter_selections = {
        receive_filter: sum(
            item["receiveFilter"] == receive_filter for item in records
        )
        for receive_filter in ("integrate-dump", "rrc-0.35")
    }
    report = {
        "schema": "rrc-psk-evaluation-v1",
        "cases": len(records),
        "exactPayloads": exact,
        "wrongModulation": wrong_modulation,
        "falseValidProtocolFrames": false_valid,
        "receiveFilterSelections": receive_filter_selections,
        "records": records,
        "boundary": (
            "Deterministic rolloff-0.35 RRC BPSK/QPSK generated and received by "
            "the same implementation; this does not represent timing-clock drift, "
            "multipath, nonlinear amplifiers or real transmitters."
        ),
    }
    output = ROOT / "reports" / "rrc_psk_evaluation.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(output)
    summary = {key: report[key] for key in (
        "cases", "exactPayloads", "wrongModulation", "falseValidProtocolFrames"
    )}
    print(json.dumps(summary))
    if exact != len(records) or wrong_modulation or false_valid:
        raise SystemExit("RRC PSK evaluation failed")


if __name__ == "__main__":
    main()
