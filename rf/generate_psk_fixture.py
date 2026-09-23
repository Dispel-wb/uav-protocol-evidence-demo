"""Deterministic noisy BPSK IQ fixture for regression."""
from __future__ import annotations

import numpy as np

from rf.generate_iq_fixture import PAYLOAD, PREAMBLE
from rf.pulse_shaping import shape_symbols


def synthesize_bpsk(
    *,
    payload: bytes = PAYLOAD,
    noise_std: float = 0.04,
    carrier_offset: float = 150,
    carrier_phase: float = 0.7,
    amplitude: float = 0.4,
    sample_rate: float = 48_000,
    symbol_rate: float = 1_200,
    seed: int = 20261200,
    rolloff: float | None = None,
) -> tuple[np.ndarray, dict]:
    samples_per_symbol = int(round(sample_rate / symbol_rate))
    if samples_per_symbol <= 0 or not np.isclose(
        samples_per_symbol,
        sample_rate / symbol_rate,
    ):
        raise ValueError("synthetic fixture requires integer samples per symbol")
    framed = PREAMBLE + payload
    bits = np.unpackbits(np.frombuffer(framed, dtype=np.uint8), bitorder="big")
    symbols = np.where(bits > 0, 1.0, -1.0)
    baseband = (
        shape_symbols(symbols.astype(np.complex64), samples_per_symbol, rolloff)
        if rolloff is not None else np.repeat(symbols, samples_per_symbol)
    )
    start = 1_600
    end = start + baseband.size
    total = end + 1_600
    rng = np.random.default_rng(seed)
    noise = rng.normal(0, noise_std, total) + 1j * rng.normal(0, noise_std, total)
    samples = noise.astype(np.complex64)
    samples += np.complex64(0.02 + 0.01j)
    time_axis = np.arange(baseband.size) / sample_rate
    carrier = np.exp(1j * (2 * np.pi * carrier_offset * time_axis + carrier_phase))
    samples[start:end] += (amplitude * baseband * carrier).astype(np.complex64)
    truth = {
        "schema": "synthetic-bpsk-truth-v1",
        "sampleRate": sample_rate,
        "symbolRate": symbol_rate,
        "samplesPerSymbol": samples_per_symbol,
        "carrierOffsetHz": carrier_offset,
        "carrierPhaseRadians": carrier_phase,
        "noiseStd": noise_std,
        "amplitude": amplitude,
        "startSample": start,
        "endSample": end,
        "preambleHex": PREAMBLE.hex(" ").upper(),
        "payloadHex": payload.hex(" ").upper(),
        "modulation": "BPSK",
        "pulseShape": "RRC" if rolloff is not None else "rectangular",
        "rolloff": rolloff,
    }
    return samples, truth


def synthesize_qpsk(
    *,
    payload: bytes = PAYLOAD,
    noise_std: float = 0.04,
    carrier_offset: float = 120,
    carrier_phase: float = 0.5,
    amplitude: float = 0.4,
    sample_rate: float = 48_000,
    symbol_rate: float = 1_200,
    seed: int = 20261300,
    rolloff: float | None = None,
) -> tuple[np.ndarray, dict]:
    samples_per_symbol = int(round(sample_rate / symbol_rate))
    if samples_per_symbol <= 0 or not np.isclose(
        samples_per_symbol,
        sample_rate / symbol_rate,
    ):
        raise ValueError("synthetic fixture requires integer samples per symbol")
    framed = PREAMBLE + payload
    bits = np.unpackbits(np.frombuffer(framed, dtype=np.uint8), bitorder="big")
    pairs = bits.reshape(-1, 2)
    i_axis = np.where(pairs[:, 1] > 0, -1.0, 1.0)
    q_axis = np.where(pairs[:, 0] > 0, -1.0, 1.0)
    symbols = (i_axis + 1j * q_axis) / np.sqrt(2)
    baseband = (
        shape_symbols(symbols.astype(np.complex64), samples_per_symbol, rolloff)
        if rolloff is not None else np.repeat(symbols, samples_per_symbol)
    )
    start = 1_600
    end = start + baseband.size
    total = end + 1_600
    rng = np.random.default_rng(seed)
    noise = rng.normal(0, noise_std, total) + 1j * rng.normal(0, noise_std, total)
    samples = noise.astype(np.complex64)
    samples += np.complex64(0.02 + 0.01j)
    time_axis = np.arange(baseband.size) / sample_rate
    carrier = np.exp(1j * (2 * np.pi * carrier_offset * time_axis + carrier_phase))
    samples[start:end] += (amplitude * baseband * carrier).astype(np.complex64)
    truth = {
        "schema": "synthetic-qpsk-truth-v1",
        "sampleRate": sample_rate,
        "symbolRate": symbol_rate,
        "samplesPerSymbol": samples_per_symbol,
        "carrierOffsetHz": carrier_offset,
        "carrierPhaseRadians": carrier_phase,
        "noiseStd": noise_std,
        "amplitude": amplitude,
        "startSample": start,
        "endSample": end,
        "preambleHex": PREAMBLE.hex(" ").upper(),
        "payloadHex": payload.hex(" ").upper(),
        "modulation": "QPSK",
        "pulseShape": "RRC" if rolloff is not None else "rectangular",
        "rolloff": rolloff,
    }
    return samples, truth
