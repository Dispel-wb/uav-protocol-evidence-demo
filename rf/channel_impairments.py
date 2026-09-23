"""Deterministic channel impairments used for regression and ablation."""
from __future__ import annotations

import numpy as np


def add_impulsive_noise(
    samples: np.ndarray,
    start: int,
    end: int,
    *,
    fraction: float = 0.01,
    amplitude: float = 3.0,
    seed: int = 20261400,
) -> tuple[np.ndarray, dict]:
    if not 0 < fraction < 1 or amplitude <= 0:
        raise ValueError("impulse fraction and amplitude must be positive")
    iq = np.asarray(samples, dtype=np.complex64).reshape(-1).copy()
    if not 0 <= start < end <= iq.size:
        raise ValueError("invalid impairment bounds")
    count = max(1, round((end - start) * fraction))
    rng = np.random.default_rng(seed)
    indices = np.sort(rng.choice(np.arange(start, end), size=count, replace=False))
    phases = rng.uniform(-np.pi, np.pi, count)
    iq[indices] += (amplitude * np.exp(1j * phases)).astype(np.complex64)
    return iq, {
        "schema": "impulsive-noise-v1",
        "fraction": fraction,
        "amplitude": amplitude,
        "count": count,
        "seed": seed,
        "indices": indices.tolist(),
    }
