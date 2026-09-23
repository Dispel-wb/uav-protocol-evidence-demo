"""Minimal burst BPSK demodulator with carrier and timing recovery evidence."""
from __future__ import annotations

import math
from typing import Any

import numpy as np

from rf.denoise import suppress_edge_stationary_tone, suppress_impulses
from rf.signal_quality import detect_bursts


def _bits_to_bytes(bits: np.ndarray) -> bytes:
    usable = bits[:bits.size - bits.size % 8]
    return np.packbits(usable.astype(np.uint8), bitorder="big").tobytes()


def demodulate_bpsk(
    samples: np.ndarray,
    sample_rate: float,
    symbol_rate: float,
    *,
    preamble: bytes = bytes.fromhex("55 55 55 55 D3 91"),
    suppress_impulsive: bool = True,
    suppress_tone: bool = True,
) -> dict[str, Any]:
    iq = np.asarray(samples, dtype=np.complex64).reshape(-1)
    tone_report = {"applied": False, "reason": "disabled"}
    if suppress_tone:
        iq, tone_report = suppress_edge_stationary_tone(iq, sample_rate)
    bursts, _, _ = detect_bursts(iq)
    if not bursts:
        raise ValueError("no burst detected")
    start, end = max(bursts, key=lambda item: item[1] - item[0])
    outside = np.concatenate((iq[:start], iq[end:]))
    dc = complex(np.mean(outside)) if outside.size else 0j
    cleaned = (iq - dc).astype(np.complex64)
    impulse_report = {"suppressedSamples": 0, "applied": False, "reason": "disabled"}
    if suppress_impulsive:
        cleaned, impulse_report = suppress_impulses(cleaned, start, end)
    segment = cleaned[start:end]
    samples_per_symbol = int(round(sample_rate / symbol_rate))
    if not math.isclose(
        samples_per_symbol,
        sample_rate / symbol_rate,
        rel_tol=0,
        abs_tol=1e-6,
    ):
        raise ValueError("this baseline requires an integer number of samples per symbol")
    if segment.size < samples_per_symbol * len(preamble) * 8:
        raise ValueError("burst is too short for the BPSK preamble")

    squared = segment * segment
    squared_phase = np.unwrap(np.angle(squared))
    phase_slope = np.polyfit(np.arange(squared.size), squared_phase, 1)[0]
    carrier_offset = float(phase_slope * sample_rate / (4 * np.pi))
    time_axis = np.arange(segment.size) / sample_rate
    corrected = segment * np.exp(-2j * np.pi * carrier_offset * time_axis)
    carrier_phase = float(np.angle(np.mean(corrected * corrected)) / 2)
    corrected *= np.exp(-1j * carrier_phase)

    preamble_bits = np.unpackbits(np.frombuffer(preamble, dtype=np.uint8), bitorder="big")
    candidates = []
    for timing in range(samples_per_symbol):
        usable = corrected[timing:]
        usable = usable[:usable.size - usable.size % samples_per_symbol]
        if usable.size < preamble_bits.size * samples_per_symbol:
            continue
        means = usable.reshape(-1, samples_per_symbol).mean(axis=1)
        for inverted in (False, True):
            bits = (means.real < 0 if inverted else means.real > 0).astype(np.uint8)
            for position in range(bits.size - preamble_bits.size + 1):
                errors = int(np.count_nonzero(
                    bits[position:position + preamble_bits.size] != preamble_bits
                ))
                if errors <= 2:
                    confidence = float(
                        np.mean(np.abs(means.real)) /
                        (np.std(means.imag) + 1e-9)
                    )
                    candidates.append((
                        errors,
                        -confidence,
                        timing,
                        inverted,
                        position,
                        bits,
                    ))
                    break
    if not candidates:
        raise ValueError("preamble not found after BPSK demodulation")
    errors, negative_confidence, timing, inverted, position, bits = min(
        candidates,
        key=lambda item: (item[0], item[1], item[4]),
    )
    payload_bits = bits[position + preamble_bits.size:]
    payload = _bits_to_bytes(payload_bits)
    return {
        "schema": "bpsk-demod-report-v1",
        "payload": payload,
        "payloadHex": payload.hex(" ").upper(),
        "symbolRate": float(symbol_rate),
        "samplesPerSymbol": samples_per_symbol,
        "carrierOffsetHz": carrier_offset,
        "carrierPhaseRadians": carrier_phase,
        "timingOffset": timing,
        "bitPolarityInverted": inverted,
        "preambleBitErrors": errors,
        "decisionConfidence": -negative_confidence,
        "burst": {"startSample": start, "endSample": end},
        "dcOffset": {"i": dc.real, "q": dc.imag},
        "impulseSuppression": impulse_report,
        "toneSuppression": tone_report,
        "boundary": "Current BPSK baseline assumes a burst, integer samples per symbol and a known preamble; real oscillator drift and pulse shaping remain to be validated.",
    }
