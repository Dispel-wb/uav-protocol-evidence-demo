"""Minimal burst QPSK demodulator with fourth-power carrier recovery."""
from __future__ import annotations

import math
from typing import Any, Callable

import numpy as np

from rf.denoise import suppress_edge_stationary_tone, suppress_impulses
from rf.carrier_tracking import track_carrier_phase
from rf.equalization import train_linear_equalizer
from rf.pulse_shaping import root_raised_cosine, sample_symbols
from rf.signal_quality import detect_bursts
from rf.timing_recovery import gardner_recover


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
    suppress_impulsive: bool = True,
    suppress_tone: bool = True,
    clock_offsets_ppm: tuple[float, ...] = (
        -10_000, -5_000, -2_000, -1_000, -500,
        0, 500, 1_000, 2_000, 5_000, 10_000,
    ),
    use_gardner: bool = True,
    payload_score: Callable[[bytes], float] | None = None,
    use_equalizer: bool = True,
    use_carrier_tracking: bool = True,
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
    preamble_bits = np.unpackbits(np.frombuffer(preamble, dtype=np.uint8), bitorder="big")
    preamble_pairs = preamble_bits.reshape(-1, 2)
    preamble_symbols = (
        np.where(preamble_pairs[:, 1] > 0, -1.0, 1.0)
        + 1j * np.where(preamble_pairs[:, 0] > 0, -1.0, 1.0)
    ).astype(np.complex64) / np.sqrt(2)
    minimum_samples = math.ceil(preamble_bits.size / 2) * samples_per_symbol
    if segment.size < minimum_samples:
        raise ValueError("burst is too short for the QPSK preamble")

    fourth = segment ** 4
    fft_size = 1 << int(np.ceil(np.log2(fourth.size * 16)))
    fourth_spectrum = np.fft.fft(fourth * np.hanning(fourth.size), fft_size)
    fourth_frequencies = np.fft.fftfreq(fft_size, 1 / sample_rate)
    carrier_offset = float(
        fourth_frequencies[int(np.argmax(np.abs(fourth_spectrum)))] / 4
    )
    time_axis = np.arange(segment.size) / sample_rate
    corrected = segment * np.exp(-2j * np.pi * carrier_offset * time_axis)
    carrier_phase = float(np.angle(-np.mean(corrected ** 4)) / 4)
    corrected *= np.exp(-1j * carrier_phase)

    receive_branches = [("integrate-dump", corrected, True, {"method": "fixed"})]
    matched = np.convolve(
        corrected,
        root_raised_cosine(samples_per_symbol, 0.35),
        mode="same",
    )
    receive_branches.append(("rrc-0.35", matched, False, {"method": "fixed"}))
    if use_carrier_tracking:
        tracked, carrier_tracking_report = track_carrier_phase(
            corrected, sample_rate, samples_per_symbol, 4
        )
        receive_branches.extend((
            ("integrate-dump", tracked, True, carrier_tracking_report),
            ("rrc-0.35", np.convolve(
                tracked, root_raised_cosine(samples_per_symbol, 0.35), mode="same"
            ), False, carrier_tracking_report),
        ))
    candidates = []

    def consider(
        means: np.ndarray,
        receive_filter: str,
        clock_offset_ppm: float,
        timing: int,
        timing_report: dict[str, Any],
        carrier_tracking_report: dict[str, Any],
    ) -> None:
        for quadrant in range(4):
            rotated = means * np.exp(-1j * quadrant * np.pi / 2)
            bits = _symbols_to_bits(rotated)
            for position in range(bits.size - preamble_bits.size + 1):
                errors = int(np.count_nonzero(
                    bits[position:position + preamble_bits.size] != preamble_bits
                ))
                if errors <= 2:
                    axis_margin = np.minimum(
                        np.abs(rotated.real), np.abs(rotated.imag)
                    )
                    confidence = float(
                        np.mean(axis_margin) /
                        (np.std(np.abs(rotated)) + 1e-9)
                    )
                    candidates.append((
                        errors,
                        -confidence,
                        receive_filter,
                        clock_offset_ppm,
                        timing,
                        quadrant,
                        position,
                        bits,
                        timing_report,
                        None,
                        carrier_tracking_report,
                    ))
                    if use_equalizer and position % 2 == 0:
                        equalized, equalizer_report = train_linear_equalizer(
                            rotated,
                            preamble_symbols,
                            position // 2,
                        )
                        equalized_bits = _symbols_to_bits(equalized)
                        equalized_errors = int(np.count_nonzero(
                            equalized_bits[
                                position:position + preamble_bits.size
                            ] != preamble_bits
                        ))
                        if equalized_errors <= 2:
                            axis_margin = np.minimum(
                                np.abs(equalized.real), np.abs(equalized.imag)
                            )
                            equalized_confidence = float(
                                np.mean(axis_margin) /
                                (np.std(np.abs(equalized)) + 1e-9)
                            )
                            candidates.append((
                                equalized_errors,
                                -equalized_confidence,
                                receive_filter,
                                clock_offset_ppm,
                                timing,
                                quadrant,
                                position,
                                equalized_bits,
                                timing_report,
                                equalizer_report,
                                carrier_tracking_report,
                            ))
                    break

    for receive_filter, branch, integrate, carrier_tracking_report in receive_branches:
        drift_candidates = (0.0,) if integrate else clock_offsets_ppm
        for clock_offset_ppm in drift_candidates:
            effective_period = samples_per_symbol / (1 + clock_offset_ppm * 1e-6)
            for timing in range(samples_per_symbol):
                usable = branch[timing:]
                if integrate:
                    usable = usable[:usable.size - usable.size % samples_per_symbol]
                    if usable.size < minimum_samples:
                        continue
                    means = usable.reshape(-1, samples_per_symbol).mean(axis=1)
                else:
                    means = sample_symbols(branch, timing, effective_period)
                    if means.size * 2 < preamble_bits.size:
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
                    carrier_tracking_report,
                )
    if use_gardner:
        for receive_filter, branch, integrate, carrier_tracking_report in receive_branches:
            if integrate:
                continue
            acquisition_offsets = (
                clock_offsets_ppm[0], 0.0, clock_offsets_ppm[-1]
            ) if clock_offsets_ppm else (0.0,)
            for acquisition_offset in dict.fromkeys(acquisition_offsets):
                initial_period = samples_per_symbol / (
                    1 + acquisition_offset * 1e-6
                )
                for timing in range(samples_per_symbol):
                    means, gardner_report = gardner_recover(
                        branch, samples_per_symbol, timing,
                        initial_samples_per_symbol=initial_period,
                    )
                    if means.size * 2 < preamble_bits.size:
                        continue
                    consider(
                        means, receive_filter,
                        gardner_report["estimatedClockOffsetPpm"], timing,
                        {"method": "gardner",
                         "acquisitionClockOffsetPpm": acquisition_offset,
                         **gardner_report},
                        carrier_tracking_report,
                    )
    if not candidates:
        raise ValueError("preamble not found after QPSK demodulation")
    def selection_key(item: tuple) -> tuple:
        payload_bits = item[7][item[6] + preamble_bits.size:]
        payload = _bits_to_bytes(payload_bits)
        validation_score = float(payload_score(payload)) if payload_score else 0.0
        return (-validation_score, item[0], item[1], item[6])

    errors, negative_confidence, receive_filter, clock_offset_ppm, timing, quadrant, position, bits, timing_report, equalizer_report, carrier_tracking_report = min(
        candidates,
        key=selection_key,
    )
    payload_bits = bits[position + preamble_bits.size:]
    payload = _bits_to_bytes(payload_bits)
    validation_score = float(payload_score(payload)) if payload_score else 0.0
    return {
        "schema": "qpsk-demod-report-v1",
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
        "carrierTracking": carrier_tracking_report,
        "equalization": (
            equalizer_report
            if equalizer_report is not None
            else {"applied": False, "method": "none"}
        ),
        "quadrantRotation": quadrant,
        "preambleBitErrors": errors,
        "decisionConfidence": -negative_confidence,
        "payloadValidationScore": validation_score,
        "burst": {"startSample": start, "endSample": end},
        "dcOffset": {"i": dc.real, "q": dc.imag},
        "impulseSuppression": impulse_report,
        "toneSuppression": tone_report,
        "boundary": "Current QPSK baseline assumes a burst and a known preamble; clock-grid and Gardner branches are validated only on synthetic captures.",
    }
