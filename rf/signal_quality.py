"""Deterministic signal detection and quality evidence for complex IQ samples."""
from __future__ import annotations

import math
from typing import Any

import numpy as np


def remove_dc(samples: np.ndarray) -> tuple[np.ndarray, complex]:
    iq = np.asarray(samples, dtype=np.complex64).reshape(-1)
    offset = complex(np.mean(iq)) if iq.size else 0j
    return (iq - offset).astype(np.complex64), offset


def _runs(mask: np.ndarray, minimum: int) -> list[tuple[int, int]]:
    padded = np.pad(mask.astype(np.int8), (1, 1))
    edges = np.diff(padded)
    starts, ends = np.flatnonzero(edges == 1), np.flatnonzero(edges == -1)
    return [(int(start), int(end)) for start, end in zip(starts, ends) if end - start >= minimum]


def detect_bursts(samples: np.ndarray, *, window: int = 64, threshold_db: float = 6.0, minimum: int = 128, padding: int = 32) -> tuple[list[tuple[int, int]], float, float]:
    iq = np.asarray(samples, dtype=np.complex64).reshape(-1)
    if iq.size < window:
        raise ValueError("capture is shorter than the detector window")
    power = np.abs(iq) ** 2
    smoothed = np.convolve(power, np.ones(window, dtype=np.float32) / window, mode="same")
    noise_power = float(np.quantile(smoothed, 0.2))
    threshold = max(noise_power * 10 ** (threshold_db / 10), np.finfo(np.float32).tiny)
    raw = _runs(smoothed > threshold, minimum)
    bursts: list[tuple[int, int]] = []
    for start, end in raw:
        start, end = max(0, start - padding), min(iq.size, end + padding)
        if bursts and start <= bursts[-1][1]:
            bursts[-1] = (bursts[-1][0], end)
        else:
            bursts.append((start, end))
    return bursts, noise_power, threshold


def spectral_evidence(samples: np.ndarray, sample_rate: float) -> dict[str, float]:
    iq = np.asarray(samples, dtype=np.complex64).reshape(-1)
    if not iq.size:
        return {"peakOffsetHz": 0.0, "occupiedBandwidthHz": 0.0}
    window = np.hanning(iq.size).astype(np.float32)
    spectrum = np.fft.fftshift(np.fft.fft(iq * window))
    power = np.abs(spectrum) ** 2
    frequencies = np.fft.fftshift(np.fft.fftfreq(iq.size, d=1 / sample_rate))
    peak = float(frequencies[int(np.argmax(power))])
    cumulative = np.cumsum(power)
    total = float(cumulative[-1])
    if total <= 0:
        bandwidth = 0.0
    else:
        low = int(np.searchsorted(cumulative, total * 0.005))
        high = int(np.searchsorted(cumulative, total * 0.995))
        bandwidth = float(max(0, frequencies[min(high, iq.size - 1)] - frequencies[min(low, iq.size - 1)]))
    return {"peakOffsetHz": peak, "occupiedBandwidthHz": bandwidth}


def analyze(samples: np.ndarray, sample_rate: float) -> dict[str, Any]:
    iq = np.asarray(samples, dtype=np.complex64).reshape(-1)
    if not iq.size:
        raise ValueError("IQ capture is empty")
    cleaned, dc = remove_dc(iq)
    bursts, noise_power, threshold = detect_bursts(cleaned)
    active = np.zeros(cleaned.size, dtype=bool)
    for start, end in bursts:
        active[start:end] = True
    signal_power = float(np.mean(np.abs(cleaned[active]) ** 2)) if np.any(active) else 0.0
    outside = np.abs(cleaned[~active]) ** 2
    measured_noise = float(np.mean(outside)) if outside.size else noise_power
    excess = max(signal_power - measured_noise, np.finfo(np.float32).tiny)
    snr_db = 10 * math.log10(excess / measured_noise) if signal_power > measured_noise and measured_noise > 0 else None
    spectral_source = cleaned[active] if np.any(active) else cleaned
    spectrum = spectral_evidence(spectral_source, sample_rate)
    return {
        "schema": "iq-quality-report-v1",
        "sampleRate": float(sample_rate),
        "samples": int(cleaned.size),
        "durationSeconds": float(cleaned.size / sample_rate),
        "dcOffset": {"i": dc.real, "q": dc.imag, "magnitude": abs(dc)},
        "rms": float(np.sqrt(np.mean(np.abs(cleaned) ** 2))),
        "noisePower": measured_noise,
        "detectorThresholdPower": threshold,
        "estimatedSnrDb": float(snr_db) if snr_db is not None else None,
        "bursts": [{"startSample": start, "endSample": end, "startSeconds": start / sample_rate, "endSeconds": end / sample_rate} for start, end in bursts],
        **spectrum,
        "boundary": "SNR为无参考估计；正式结论需使用已知序列、误码率或校准信号复核。",
    }
