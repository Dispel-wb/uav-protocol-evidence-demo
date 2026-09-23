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


def apply_sample_clock_offset(
    samples: np.ndarray,
    offset_ppm: float,
) -> np.ndarray:
    """Resample a fixture so its symbol clock drifts against nominal receiver time."""
    source = np.asarray(samples, dtype=np.complex64).reshape(-1)
    scale = 1 + offset_ppm * 1e-6
    if scale <= 0:
        raise ValueError("sample clock offset must keep a positive sampling scale")
    if source.size < 2 or offset_ppm == 0:
        return source.copy()
    output_size = int(np.floor((source.size - 1) / scale)) + 1
    positions = np.arange(output_size, dtype=np.float64) * scale
    source_positions = np.arange(source.size, dtype=np.float64)
    real = np.interp(positions, source_positions, source.real)
    imag = np.interp(positions, source_positions, source.imag)
    return (real + 1j * imag).astype(np.complex64)


def apply_sample_clock_drift(
    samples: np.ndarray,
    start_offset_ppm: float,
    end_offset_ppm: float,
) -> np.ndarray:
    """Resample using a clock offset that changes linearly through the burst."""
    source = np.asarray(samples, dtype=np.complex64).reshape(-1)
    if source.size < 2:
        return source.copy()
    if min(start_offset_ppm, end_offset_ppm) <= -1_000_000:
        raise ValueError("sample clock drift must keep a positive sampling scale")
    positions = []
    position = 0.0
    last = source.size - 1
    while position < last:
        positions.append(position)
        progress = position / last
        offset_ppm = start_offset_ppm + (
            end_offset_ppm - start_offset_ppm
        ) * progress
        position += 1 + offset_ppm * 1e-6
    positions = np.asarray(positions, dtype=np.float64)
    source_positions = np.arange(source.size, dtype=np.float64)
    real = np.interp(positions, source_positions, source.real)
    imag = np.interp(positions, source_positions, source.imag)
    return (real + 1j * imag).astype(np.complex64)


def sample_symbols(
    samples: np.ndarray,
    first_sample: float,
    samples_per_symbol: float,
) -> np.ndarray:
    """Linearly interpolate symbol centers at a possibly noninteger period."""
    source = np.asarray(samples).reshape(-1)
    if samples_per_symbol <= 0:
        raise ValueError("samples_per_symbol must be positive")
    positions = np.arange(
        first_sample,
        source.size - 1,
        samples_per_symbol,
        dtype=np.float64,
    )
    source_positions = np.arange(source.size, dtype=np.float64)
    real = np.interp(positions, source_positions, source.real)
    imag = np.interp(positions, source_positions, source.imag)
    return real + 1j * imag
