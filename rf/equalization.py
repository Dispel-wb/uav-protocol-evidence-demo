"""Short training-sequence linear equalizer for symbol-rate PSK samples."""
from __future__ import annotations

from typing import Any

import numpy as np


def train_linear_equalizer(
    symbols: np.ndarray,
    training_symbols: np.ndarray,
    training_start: int,
    *,
    taps: int = 7,
    regularization: float = 1e-3,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Fit a centered complex FIR that maps received training symbols to known ones."""
    received = np.asarray(symbols, dtype=np.complex64).reshape(-1)
    expected = np.asarray(training_symbols, dtype=np.complex64).reshape(-1)
    if taps < 3 or taps % 2 == 0:
        raise ValueError("equalizer taps must be an odd integer of at least three")
    if regularization <= 0:
        raise ValueError("equalizer regularization must be positive")
    if training_start < 0 or training_start + expected.size > received.size:
        raise ValueError("training sequence lies outside received symbols")

    half = taps // 2
    padded = np.pad(received, (half, half))
    design = np.stack([
        padded[index:index + received.size]
        for index in range(taps)
    ], axis=1)
    training_design = design[training_start:training_start + expected.size]
    gram = training_design.conj().T @ training_design
    scale = float(np.trace(gram).real / taps) if taps else 1.0
    matrix = gram + regularization * max(scale, 1e-9) * np.eye(taps)
    target = training_design.conj().T @ expected
    coefficients = np.linalg.solve(matrix, target)
    equalized = design @ coefficients
    trained = equalized[training_start:training_start + expected.size]
    before = received[training_start:training_start + expected.size]
    before_scale = np.vdot(before, expected) / (np.vdot(before, before) + 1e-9)
    before_error = before * before_scale - expected
    after_error = trained - expected
    report = {
        "method": "training-fir",
        "taps": taps,
        "regularization": regularization,
        "trainingStartSymbol": training_start,
        "trainingSymbols": int(expected.size),
        "trainingMseBefore": float(np.mean(np.abs(before_error) ** 2)),
        "trainingMseAfter": float(np.mean(np.abs(after_error) ** 2)),
        "coefficients": [
            {"i": float(value.real), "q": float(value.imag)}
            for value in coefficients
        ],
    }
    return equalized.astype(np.complex64), report
