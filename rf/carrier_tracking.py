"""Data-independent carrier phase tracking for short PSK bursts."""
from __future__ import annotations

from typing import Any

import numpy as np


def track_carrier_phase(
    samples: np.ndarray,
    sample_rate: float,
    samples_per_symbol: int,
    order: int,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Fit a quadratic residual phase to smoothed Mth-power PSK samples.

    The Mth power removes ideal PSK data phase. The fit tracks a linearly
    changing oscillator frequency within one detected burst. A separate
    untracked receive branch remains available to protocol validation.
    """
    source = np.asarray(samples, dtype=np.complex64).reshape(-1)
    if order not in (2, 4) or sample_rate <= 0 or samples_per_symbol < 2:
        raise ValueError("invalid carrier tracking parameters")
    window = 2 * samples_per_symbol
    if source.size < 8 * window:
        raise ValueError("burst is too short for carrier tracking")

    raised = source.astype(np.complex128) ** order
    smoothed = np.convolve(raised, np.ones(window) / window, mode="same")
    indices = np.arange(
        window, source.size - window, max(1, samples_per_symbol // 2)
    )
    times = indices / sample_rate
    observations = smoothed[indices]
    phases = np.unwrap(np.angle(observations))
    weights = np.abs(observations)
    if not np.all(np.isfinite(weights)) or float(np.max(weights)) <= 1e-12:
        raise ValueError("carrier phase evidence is too weak")
    coefficients = np.polyfit(times, phases, 2, w=weights)
    fitted = np.polyval(coefficients, times)
    circular_residual = np.angle(np.exp(1j * (phases - fitted)))
    weighted_error = float(np.average(
        circular_residual**2, weights=weights
    ))
    all_times = np.arange(source.size) / sample_rate
    # Keep the coarse carrier phase and its PSK quadrant. Only cancel drift.
    residual_drift = coefficients[0] * all_times**2 + coefficients[1] * all_times
    correction = np.exp(-1j * residual_drift / order)
    corrected = (source * correction).astype(np.complex64)
    report = {
        "method": "mth-power-quadratic",
        "order": order,
        "phaseFitResidualRadiansRms": float(np.sqrt(weighted_error)),
        "startResidualFrequencyHz": float(
            coefficients[1] / (2 * np.pi * order)
        ),
        "endResidualFrequencyHz": float(
            (2 * coefficients[0] * all_times[-1] + coefficients[1])
            / (2 * np.pi * order)
        ),
        "observations": int(indices.size),
    }
    return corrected, report
