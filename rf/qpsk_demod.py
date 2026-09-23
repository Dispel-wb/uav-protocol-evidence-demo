"""Minimal burst QPSK demodulator with fourth-power carrier recovery."""
from __future__ import annotations

import math
from typing import Any

import numpy as np

from rf.signal_quality import detect_bursts


def _symbols_to_bits(symbols: np.ndarray) -> np.ndarray:
    bits = np.empty(symbols.size * 2, dtype=np.uint8)
    positive_i = symbols.real >= 0
    positive_q = symbols.imag >= 0
    bits[0::2] = ~positive_q
    bits[1::2] = ~positive_i
    return bits


def _bits_to_bytes(bits: np.ndarray) -> bytes:
    usable = bits[:bits.size - bits.size % 8]
    return np.packbits(usable, bitorder="big").tobytes()


def demodulate_qpsk(
    samples: np.ndarray,
    sample_rate: float,
    symbol_rate: float,
    *,
    preamble: bytes = bytes.fromhex("55 55 55 55 D3 91"),
) -> dict[str, Any]:
    iq = np.asarray(samples, dtype=np.complex64).reshape(-1)
    bursts, _, _ = detect_bursts(iq)
    if not bursts:
        raise ValueError("no burst detected")
    start, end = max(bursts, key=lambda item: item[1] - item[0])
    outside = np.concatenate((iq[:start], iq[end:]))
    dc = complex(np.mean(outside)) if outside.size else 0j
    segment = (iq[start:end] - dc).astype(np.complex64)
    samples_per_symbol = int(round(sample_rate / symbol_rate))
    if not math.isclose(
        samples_per_symbol,
        sample_rate / symbol_rate,
        rel_tol=0,
        abs_tol=1e-6,
    ):
        raise ValueError("this baseline requires an integer number of samples per symbol")
    preamble_bits = np.unpackbits(np.frombuffer(preamble, dtype=np.uint8), bitorder="big")
    minimum_samples = math.ceil(preamble_bits.size / 2) * samples_per_symbol
    if segment.size < minimum_samples:
        raise ValueError("burst is too short for the QPSK preamble")

    fourth = segment ** 4
    fourth_phase = np.unwrap(np.angle(fourth))
    phase_slope = np.polyfit(np.arange(fourth.size), fourth_phase, 1)[0]
    carrier_offset = float(phase_slope * sample_rate / (8 * np.pi))
    time_axis = np.arange(segment.size) / sample_rate
    corrected = segment * np.exp(-2j * np.pi * carrier_offset * time_axis)
    carrier_phase = float(np.angle(-np.mean(corrected ** 4)) / 4)
    corrected *= np.exp(-1j * carrier_phase)

    candidates = []
    for timing in range(samples_per_symbol):
        usable = corrected[timing:]
        usable = usable[:usable.size - usable.size % samples_per_symbol]
        if usable.size < minimum_samples:
            continue
        means = usable.reshape(-1, samples_per_symbol).mean(axis=1)
        for quadrant in range(4):
            rotated = means * np.exp(-1j * quadrant * np.pi / 2)
            bits = _symbols_to_bits(rotated)
            for position in range(bits.size - preamble_bits.size + 1):
                errors = int(np.count_nonzero(
                    bits[position:position + preamble_bits.size] != preamble_bits
                ))
                if errors <= 2:
                    axis_margin = np.minimum(np.abs(rotated.real), np.abs(rotated.imag))
                    confidence = float(
                        np.mean(axis_margin) / (np.std(np.abs(rotated)) + 1e-9)
                    )
                    candidates.append((
                        errors,
                        -confidence,
                        timing,
                        quadrant,
                        position,
                        bits,
                    ))
                    break
    if not candidates:
        raise ValueError("preamble not found after QPSK demodulation")
    errors, negative_confidence, timing, quadrant, position, bits = min(
        candidates,
        key=lambda item: (item[0], item[1], item[4]),
    )
    payload_bits = bits[position + preamble_bits.size:]
    payload = _bits_to_bytes(payload_bits)
    return {
        "schema": "qpsk-demod-report-v1",
        "payload": payload,
        "payloadHex": payload.hex(" ").upper(),
        "symbolRate": float(symbol_rate),
        "samplesPerSymbol": samples_per_symbol,
        "carrierOffsetHz": carrier_offset,
        "carrierPhaseRadians": carrier_phase,
        "timingOffset": timing,
        "quadrantRotation": quadrant,
        "preambleBitErrors": errors,
        "decisionConfidence": -negative_confidence,
        "burst": {"startSample": start, "endSample": end},
        "dcOffset": {"i": dc.real, "q": dc.imag},
        "boundary": "Current QPSK baseline assumes rectangular pulse shaping, integer samples per symbol and a known preamble.",
    }
