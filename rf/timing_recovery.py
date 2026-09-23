"""Fractional interpolation and Gardner symbol timing recovery."""
from __future__ import annotations

from typing import Any

import numpy as np


def _interpolate(samples: np.ndarray, position: float) -> complex:
    left = int(np.floor(position))
    fraction = position - left
    if left < 0 or left + 1 >= samples.size:
        return 0j
    return complex(
        samples[left] * (1 - fraction) + samples[left + 1] * fraction
    )


def gardner_recover(
    samples: np.ndarray,
    nominal_samples_per_symbol: float,
    initial_phase: float,
    *,
    initial_samples_per_symbol: float | None = None,
    phase_gain: float = 0.5,
    rate_gain: float = 0.03,
    maximum_rate_error: float = 0.03,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Recover symbol centers with a bounded second-order Gardner loop."""
    source = np.asarray(samples, dtype=np.complex64).reshape(-1)
    if nominal_samples_per_symbol <= 0:
        raise ValueError("nominal samples per symbol must be positive")
    if not 0 <= initial_phase < nominal_samples_per_symbol:
        raise ValueError("initial phase must be within one symbol")
    if phase_gain < 0 or rate_gain < 0 or not 0 < maximum_rate_error < 1:
        raise ValueError("invalid Gardner loop parameters")

    minimum_period = nominal_samples_per_symbol * (1 - maximum_rate_error)
    maximum_period = nominal_samples_per_symbol * (1 + maximum_rate_error)
    period = float(
        nominal_samples_per_symbol
        if initial_samples_per_symbol is None
        else initial_samples_per_symbol
    )
    if not minimum_period <= period <= maximum_period:
        raise ValueError("initial symbol period exceeds the Gardner loop bound")
    position = float(initial_phase)
    previous_symbol = None
    previous_position = None
    symbols = []
    errors = []
    periods = []

    while position < source.size - 1:
        symbol = _interpolate(source, position)
        symbols.append(symbol)
        if previous_symbol is None:
            next_position = position + period
        else:
            midpoint = _interpolate(
                source, (previous_position + position) / 2
            )
            normalization = (
                abs(previous_symbol) ** 2 + abs(symbol) ** 2
                + 2 * abs(midpoint) ** 2 + 1e-9
            )
            error = float(
                np.real((symbol - previous_symbol) * np.conj(midpoint))
                / normalization
            )
            period = float(np.clip(
                period + rate_gain * error,
                minimum_period,
                maximum_period,
            ))
            next_position = position + period + phase_gain * error
            errors.append(error)
        periods.append(period)
        previous_symbol = symbol
        previous_position = position
        position = next_position

    steady_periods = periods[max(1, len(periods) // 2):]
    mean_period = float(np.mean(steady_periods)) if steady_periods else period
    estimated_offset_ppm = (
        nominal_samples_per_symbol / mean_period - 1
    ) * 1e6
    report = {
        "symbols": len(symbols),
        "initialPhase": float(initial_phase),
        "initialSamplesPerSymbol": float(
            nominal_samples_per_symbol
            if initial_samples_per_symbol is None
            else initial_samples_per_symbol
        ),
        "meanSamplesPerSymbol": mean_period,
        "finalSamplesPerSymbol": float(period),
        "estimatedClockOffsetPpm": float(estimated_offset_ppm),
        "meanAbsoluteTimingError": (
            float(np.mean(np.abs(errors))) if errors else 0.0
        ),
        "phaseGain": phase_gain,
        "rateGain": rate_gain,
        "maximumRateError": maximum_rate_error,
    }
    return np.asarray(symbols, dtype=np.complex64), report
