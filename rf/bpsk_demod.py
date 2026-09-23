"""Minimal burst BPSK demodulator with carrier and timing recovery evidence."""
from __future__ import annotations

import math
from typing import Any, Callable

import numpy as np

from rf.denoise import suppress_edge_stationary_tone, suppress_impulses
from rf.pulse_shaping import root_raised_cosine, sample_symbols
from rf.signal_quality import detect_bursts
from rf.timing_recovery import gardner_recover


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
    clock_offsets_ppm: tuple[float, ...] = (
        -10_000, -5_000, -2_000, -1_000, -500,
        0, 500, 1_000, 2_000, 5_000, 10_000,
    ),
    use_gardner: bool = True,
    payload_score: Callable[[bytes], float] | None = None,
) -> dict[str, Any]:
    if any(1 + offset * 1e-6 <= 0 for offset in clock_offsets_ppm):
        raise ValueError("clock offset candidates must keep a positive symbol period")
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
    fft_size = 1 << int(np.ceil(np.log2(squared.size * 16)))
    squared_spectrum = np.fft.fft(squared * np.hanning(squared.size), fft_size)
    squared_frequencies = np.fft.fftfreq(fft_size, 1 / sample_rate)
    carrier_offset = float(
        squared_frequencies[int(np.argmax(np.abs(squared_spectrum)))] / 2
    )
    time_axis = np.arange(segment.size) / sample_rate
    corrected = segment * np.exp(-2j * np.pi * carrier_offset * time_axis)
    carrier_phase = float(np.angle(np.mean(corrected * corrected)) / 2)
    corrected *= np.exp(-1j * carrier_phase)

    preamble_bits = np.unpackbits(np.frombuffer(preamble, dtype=np.uint8), bitorder="big")
    receive_branches = [("integrate-dump", corrected, True)]
    matched = np.convolve(
        corrected,
        root_raised_cosine(samples_per_symbol, 0.35),
        mode="same",
    )
    receive_branches.append(("rrc-0.35", matched, False))
    candidates = []

    def consider(
        means: np.ndarray,
        receive_filter: str,
        clock_offset_ppm: float,
        timing: int,
        timing_report: dict[str, Any],
    ) -> None:
        for inverted in (False, True):
            bits = (
                means.real < 0 if inverted else means.real > 0
            ).astype(np.uint8)
            for position in range(bits.size - preamble_bits.size + 1):
                errors = int(np.count_nonzero(
                    bits[position:position + preamble_bits.size] != preamble_bits
                ))
                if errors <= 2:
                    mean_axis = np.mean(np.abs(means.real))
                    constellation_error = np.sqrt(
                        np.mean(means.imag ** 2) +
                        np.var(np.abs(means.real))
                    )
                    confidence = float(
                        mean_axis / (constellation_error + 1e-9)
                    )
                    candidates.append((
                        errors,
                        -confidence,
                        receive_filter,
                        clock_offset_ppm,
                        timing,
                        inverted,
                        position,
                        bits,
                        timing_report,
                    ))
                    break

    for receive_filter, branch, integrate in receive_branches:
        drift_candidates = (0.0,) if integrate else clock_offsets_ppm
        for clock_offset_ppm in drift_candidates:
            effective_period = samples_per_symbol / (1 + clock_offset_ppm * 1e-6)
            for timing in range(samples_per_symbol):
                usable = branch[timing:]
                if integrate:
                    usable = usable[:usable.size - usable.size % samples_per_symbol]
                    if usable.size < preamble_bits.size * samples_per_symbol:
                        continue
                    means = usable.reshape(-1, samples_per_symbol).mean(axis=1)
                else:
                    means = sample_symbols(branch, timing, effective_period)
                    if means.size < preamble_bits.size:
                        continue
                consider(
                    means,
                    receive_filter,
                    clock_offset_ppm,
                    timing,
                    {
                        "method": "fixed" if integrate else "clock-grid",
                        "samplesPerSymbol": float(effective_period),
                    },
                )
    if use_gardner:
        acquisition_offsets = (
            clock_offsets_ppm[0], 0.0, clock_offsets_ppm[-1]
        ) if clock_offsets_ppm else (0.0,)
        for acquisition_offset in dict.fromkeys(acquisition_offsets):
            initial_period = samples_per_symbol / (
                1 + acquisition_offset * 1e-6
            )
            for timing in range(samples_per_symbol):
                means, gardner_report = gardner_recover(
                    matched,
                    samples_per_symbol,
                    timing,
                    initial_samples_per_symbol=initial_period,
                )
                if means.size < preamble_bits.size:
                    continue
                consider(
                    means,
                    "rrc-0.35",
                    gardner_report["estimatedClockOffsetPpm"],
                    timing,
                    {
                        "method": "gardner",
                        "acquisitionClockOffsetPpm": acquisition_offset,
                        **gardner_report,
                    },
                )
    if not candidates:
        raise ValueError("preamble not found after BPSK demodulation")
    def selection_key(item: tuple) -> tuple:
        payload_bits = item[7][item[6] + preamble_bits.size:]
        payload = _bits_to_bytes(payload_bits)
        validation_score = float(payload_score(payload)) if payload_score else 0.0
        return (-validation_score, item[0], item[1], item[6])

    errors, negative_confidence, receive_filter, clock_offset_ppm, timing, inverted, position, bits, timing_report = min(
        candidates,
        key=selection_key,
    )
    payload_bits = bits[position + preamble_bits.size:]
    payload = _bits_to_bytes(payload_bits)
    validation_score = float(payload_score(payload)) if payload_score else 0.0
    return {
        "schema": "bpsk-demod-report-v1",
        "payload": payload,
        "payloadHex": payload.hex(" ").upper(),
        "symbolRate": float(symbol_rate),
        "samplesPerSymbol": samples_per_symbol,
        "carrierOffsetHz": carrier_offset,
        "carrierPhaseRadians": carrier_phase,
        "timingOffset": timing,
        "receiveFilter": receive_filter,
        "sampleClockOffsetPpm": clock_offset_ppm,
        "timingRecovery": timing_report,
        "bitPolarityInverted": inverted,
        "preambleBitErrors": errors,
        "decisionConfidence": -negative_confidence,
        "payloadValidationScore": validation_score,
        "burst": {"startSample": start, "endSample": end},
        "dcOffset": {"i": dc.real, "q": dc.imag},
        "impulseSuppression": impulse_report,
        "toneSuppression": tone_report,
        "boundary": "Current BPSK baseline assumes a burst and a known preamble; clock-grid and Gardner branches are validated only on synthetic captures.",
    }
