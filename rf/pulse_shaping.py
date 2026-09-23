"""Root-raised-cosine taps shared by synthetic transmitters and receivers."""
from __future__ import annotations

import numpy as np


def root_raised_cosine(
    samples_per_symbol: int,
    rolloff: float = 0.35,
    span_symbols: int = 8,
) -> np.ndarray:
    if samples_per_symbol <= 0 or not 0 < rolloff <= 1 or span_symbols <= 0:
        raise ValueError("invalid root-raised-cosine parameters")
    if span_symbols % 2:
        raise ValueError("span_symbols must be even")
    positions = np.arange(
        -span_symbols * samples_per_symbol // 2,
        span_symbols * samples_per_symbol // 2 + 1,
    )
    time = positions / samples_per_symbol
    taps = np.empty(time.size, dtype=np.float64)
    for index, value in enumerate(time):
        if abs(value) < 1e-12:
            taps[index] = 1 + rolloff * (4 / np.pi - 1)
        elif abs(abs(4 * rolloff * value) - 1) < 1e-10:
            angle = np.pi / (4 * rolloff)
            taps[index] = rolloff / np.sqrt(2) * (
                (1 + 2 / np.pi) * np.sin(angle)
                + (1 - 2 / np.pi) * np.cos(angle)
            )
        else:
            numerator = (
                np.sin(np.pi * value * (1 - rolloff))
                + 4 * rolloff * value * np.cos(np.pi * value * (1 + rolloff))
            )
            denominator = np.pi * value * (1 - (4 * rolloff * value) ** 2)
            taps[index] = numerator / denominator
    taps /= np.sqrt(np.sum(taps * taps))
    return taps.astype(np.float32)


def shape_symbols(
    symbols: np.ndarray,
    samples_per_symbol: int,
    rolloff: float,
) -> np.ndarray:
    impulses = np.zeros(len(symbols) * samples_per_symbol, dtype=np.complex64)
    impulses[::samples_per_symbol] = symbols
    taps = root_raised_cosine(samples_per_symbol, rolloff)
    shaped = np.convolve(impulses, taps, mode="same")
    rms = float(np.sqrt(np.mean(np.abs(shaped) ** 2)))
    return (shaped / rms).astype(np.complex64)
