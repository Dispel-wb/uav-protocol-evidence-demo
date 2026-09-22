"""Try a small set of 2-FSK symbol-rate candidates and retain all evidence."""
from __future__ import annotations

from typing import Any, Iterable

import numpy as np

from rf.fsk_demod import demodulate
from rf.protocol_feedback import mavlink_evidence


def select(samples: np.ndarray, sample_rate: float, symbol_rates: Iterable[float]) -> dict[str, Any]:
    candidates = []
    for symbol_rate in symbol_rates:
        try:
            report = demodulate(samples, sample_rate, float(symbol_rate))
            payload = report.pop("payload")
            protocol = mavlink_evidence(payload)
            score = protocol["validFrames"] * 1_000 - report["preambleBitErrors"] * 100 + min(report["decisionConfidence"], 99)
            candidates.append({"symbolRate": float(symbol_rate), "status": "decoded", "score": score, "payloadHex": payload.hex(" ").upper(), "protocolEvidence": protocol, "demodulation": report})
        except (ValueError, ArithmeticError) as error:
            candidates.append({"symbolRate": float(symbol_rate), "status": "rejected", "score": None, "reason": str(error)})
    decoded = [candidate for candidate in candidates if candidate["status"] == "decoded"]
    decoded.sort(key=lambda candidate: (candidate["protocolEvidence"]["validFrames"], candidate["score"]), reverse=True)
    chosen = decoded[0] if decoded else None
    return {
        "schema": "demod-candidate-selection-v1",
        "chosenSymbolRate": chosen["symbolRate"] if chosen else None,
        "chosenPayloadHex": chosen["payloadHex"] if chosen else None,
        "validProtocolFrames": chosen["protocolEvidence"]["validFrames"] if chosen else 0,
        "candidates": candidates,
        "boundary": "候选集合当前仅改变2-FSK符号率；未覆盖其他调制方式。所有失败候选均保留原因。",
    }
