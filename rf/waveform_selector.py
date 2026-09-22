"""Select among supported modulation families using sync and protocol evidence."""
from __future__ import annotations

from typing import Any, Iterable

import numpy as np

from rf.bpsk_demod import demodulate_bpsk
from rf.candidate_selector import select as select_fsk
from rf.protocol_feedback import mavlink_evidence


def select_waveform(
    samples: np.ndarray,
    sample_rate: float,
    symbol_rates: Iterable[float],
    modulations: Iterable[str] = ("fsk",),
) -> dict[str, Any]:
    rates = tuple(float(rate) for rate in symbol_rates)
    families = tuple(dict.fromkeys(name.lower() for name in modulations))
    unsupported = set(families) - {"fsk", "bpsk"}
    if not rates:
        raise ValueError("at least one symbol-rate candidate is required")
    if not families or unsupported:
        raise ValueError(f"unsupported modulation candidates: {sorted(unsupported)}")

    candidates = []
    if "fsk" in families:
        fsk = select_fsk(samples, sample_rate, rates)
        for candidate in fsk["candidates"]:
            normalized = {**candidate, "demodulator": "FSK"}
            if candidate["status"] == "decoded":
                label = candidate["modulationEvidence"]["label"]
                normalized["modulation"] = label or "FSK-family-unknown"
            candidates.append(normalized)

    if "bpsk" in families:
        for rate in rates:
            try:
                report = demodulate_bpsk(samples, sample_rate, rate)
                payload = report.pop("payload")
                protocol = mavlink_evidence(payload)
                score = (
                    protocol["validFrames"] * 1_000
                    - report["preambleBitErrors"] * 100
                    + min(report["decisionConfidence"], 99)
                )
                candidates.append({
                    "demodulator": "BPSK",
                    "modulation": "BPSK",
                    "symbolRate": rate,
                    "status": "decoded",
                    "score": score,
                    "payloadHex": payload.hex(" ").upper(),
                    "protocolEvidence": protocol,
                    "demodulation": report,
                })
            except (ValueError, ArithmeticError) as error:
                candidates.append({
                    "demodulator": "BPSK",
                    "modulation": "BPSK",
                    "symbolRate": rate,
                    "status": "rejected",
                    "score": None,
                    "reason": str(error),
                })

    decoded = [item for item in candidates if item["status"] == "decoded"]
    decoded.sort(
        key=lambda item: (item["protocolEvidence"]["validFrames"], item["score"]),
        reverse=True,
    )
    chosen = decoded[0] if decoded else None
    return {
        "schema": "waveform-candidate-selection-v1",
        "chosenModulation": chosen["modulation"] if chosen else None,
        "chosenDemodulator": chosen["demodulator"] if chosen else None,
        "chosenSymbolRate": chosen["symbolRate"] if chosen else None,
        "chosenPayloadHex": chosen["payloadHex"] if chosen else None,
        "validProtocolFrames": chosen["protocolEvidence"]["validFrames"] if chosen else 0,
        "candidates": candidates,
        "boundary": "Selection covers FSK-family and BPSK burst baselines only; CRC-valid protocol evidence dominates confidence scores.",
    }
