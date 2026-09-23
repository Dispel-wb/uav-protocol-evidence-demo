"""Select among supported modulation families using sync and protocol evidence."""
from __future__ import annotations

from typing import Any, Iterable

import numpy as np

from rf.bpsk_demod import demodulate_bpsk
from rf.candidate_selector import select as select_fsk
from rf.protocol_feedback import mavlink_evidence
from rf.qpsk_demod import demodulate_qpsk


def select_waveform(
    samples: np.ndarray,
    sample_rate: float,
    symbol_rates: Iterable[float],
    modulations: Iterable[str] = ("fsk",),
    clock_offsets_ppm: Iterable[float] | None = None,
    use_gardner: bool = True,
    use_equalizer: bool = True,
) -> dict[str, Any]:
    rates = tuple(float(rate) for rate in symbol_rates)
    families = tuple(dict.fromkeys(name.lower() for name in modulations))
    clock_candidates = (
        None if clock_offsets_ppm is None
        else tuple(float(offset) for offset in clock_offsets_ppm)
    )
    timing_options = (
        {
            "use_gardner": use_gardner,
            "use_equalizer": use_equalizer,
        } if clock_candidates is None
        else {
            "clock_offsets_ppm": clock_candidates,
            "use_gardner": use_gardner,
            "use_equalizer": use_equalizer,
        }
    )
    timing_options["payload_score"] = lambda payload: mavlink_evidence(payload)[
        "validFrames"
    ]
    unsupported = set(families) - {"fsk", "bpsk", "qpsk"}
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
                report = demodulate_bpsk(
                    samples, sample_rate, rate, **timing_options
                )
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

    if "qpsk" in families:
        for rate in rates:
            try:
                report = demodulate_qpsk(
                    samples, sample_rate, rate, **timing_options
                )
                payload = report.pop("payload")
                protocol = mavlink_evidence(payload)
                score = (
                    protocol["validFrames"] * 1_000
                    - report["preambleBitErrors"] * 100
                    + min(report["decisionConfidence"], 99)
                )
                candidates.append({
                    "demodulator": "QPSK",
                    "modulation": "QPSK",
                    "symbolRate": rate,
                    "status": "decoded",
                    "score": score,
                    "payloadHex": payload.hex(" ").upper(),
                    "protocolEvidence": protocol,
                    "demodulation": report,
                })
            except (ValueError, ArithmeticError) as error:
                candidates.append({
                    "demodulator": "QPSK",
                    "modulation": "QPSK",
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
        "boundary": "Selection covers FSK-family, BPSK and QPSK burst baselines; CRC-valid protocol evidence is used both within PSK timing candidates and across demodulators.",
    }
