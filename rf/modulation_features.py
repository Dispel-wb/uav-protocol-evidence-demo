"""Interpretable frequency-transition features for FSK-family waveforms."""
from __future__ import annotations

import numpy as np

from rf.signal_quality import analyze, detect_bursts, remove_dc


def fsk_shape_features(
    samples: np.ndarray,
    sample_rate: float,
    symbol_rate: float,
) -> dict[str, float]:
    cleaned, _ = remove_dc(samples)
    bursts, _, _ = detect_bursts(cleaned)
    if not bursts:
        raise ValueError("no burst detected")
    start, end = max(bursts, key=lambda item: item[1] - item[0])
    segment = cleaned[start:end]
    frequency = np.angle(segment[1:] * np.conj(segment[:-1])) * sample_rate / (2 * np.pi)
    smoothing = max(3, round(sample_rate / symbol_rate / 6))
    kernel = np.ones(smoothing, dtype=np.float32) / smoothing
    smoothed = np.convolve(frequency, kernel, mode="valid")
    low, high = np.quantile(smoothed, [0.1, 0.9])
    center = (low + high) / 2
    deviation = (high - low) / 2
    if deviation <= 0:
        raise ValueError("unable to estimate FSK deviation")
    centered = smoothed - center
    normalized = np.abs(centered) / deviation
    return {
        "frequencyCenterHz": center,
        "frequencyDeviationHz": deviation,
        "smoothingSamples": smoothing,
        "intermediateFraction": float(np.mean(normalized < 0.72)),
        "nearToneFraction": float(np.mean(normalized > 0.82)),
    }


def classify_fsk_shape(
    samples: np.ndarray,
    sample_rate: float,
    symbol_rate: float,
) -> dict[str, float | str | None]:
    features = fsk_shape_features(samples, sample_rate, symbol_rate)
    snr_db = analyze(samples, sample_rate)["estimatedSnrDb"]
    fraction = features["intermediateFraction"]
    if snr_db is None or snr_db < 9.5:
        label, reason = None, "SNR is below the validated shape-classification range"
    elif fraction <= 0.12:
        label, reason = "2-FSK", "frequency samples cluster near two abrupt tone levels"
    elif fraction >= 0.18:
        label, reason = "GFSK", "frequency transitions contain a sustained intermediate region"
    else:
        label, reason = None, "transition shape falls inside the conservative rejection band"
    return {
        "schema": "fsk-shape-evidence-v1",
        "label": label,
        "reason": reason,
        "estimatedSnrDb": snr_db,
        **features,
        "boundary": "Thresholds are validated only on deterministic synthetic 2-FSK and BT=0.5 GFSK; low-SNR or out-of-family signals are rejected.",
    }
