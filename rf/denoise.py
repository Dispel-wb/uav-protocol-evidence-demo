"""Small, evidence-producing denoisers shared by waveform demodulators."""
from __future__ import annotations

import numpy as np


def suppress_edge_stationary_tone(
    samples: np.ndarray,
    sample_rate: float,
    *,
    edge_fraction: float = 0.1,
    minimum_coherence_db: float = 5.0,
) -> tuple[np.ndarray, dict]:
    """Estimate a tone present in both capture edges and subtract it globally."""
    iq = np.asarray(samples, dtype=np.complex64).reshape(-1)
    edge = max(128, round(iq.size * edge_fraction))
    if edge * 2 >= iq.size:
        raise ValueError("capture is too short for edge-stationary tone suppression")
    first = iq[:edge] - np.mean(iq[:edge])
    transform_size = 1 << max(12, (edge * 8 - 1).bit_length())
    spectrum = np.fft.fft(first, transform_size)
    frequencies = np.fft.fftfreq(transform_size, 1 / sample_rate)
    eligible = np.abs(frequencies) >= max(50.0, sample_rate / transform_size * 2)
    peak_index = int(np.argmax(np.where(eligible, np.abs(spectrum), 0)))
    coarse = float(frequencies[peak_index])

    indices = np.concatenate((np.arange(edge), np.arange(iq.size - edge, iq.size)))
    values = iq[indices] - np.mean(iq[indices])
    resolution = sample_rate / edge
    candidates = np.linspace(coarse - resolution, coarse + resolution, 81)
    projections = np.array([
        abs(np.mean(values * np.exp(-2j * np.pi * frequency * indices / sample_rate)))
        for frequency in candidates
    ])
    frequency = float(candidates[int(np.argmax(projections))])
    reference = np.exp(2j * np.pi * frequency * indices / sample_rate)
    amplitude = complex(np.mean(values * np.conj(reference)))
    residual = values - amplitude * reference
    residual_power = float(np.mean(np.abs(residual) ** 2))
    tone_power = abs(amplitude) ** 2
    coherence_db = float(10 * np.log10(tone_power / max(residual_power, 1e-20)))
    if coherence_db < minimum_coherence_db:
        return iq.copy(), {
            "applied": False,
            "frequencyOffsetHz": frequency,
            "amplitude": abs(amplitude),
            "coherenceDb": coherence_db,
            "reason": "edge tone is below the coherence threshold",
        }
    all_indices = np.arange(iq.size)
    tone = amplitude * np.exp(2j * np.pi * frequency * all_indices / sample_rate)
    return (iq - tone).astype(np.complex64), {
        "applied": True,
        "frequencyOffsetHz": frequency,
        "amplitude": abs(amplitude),
        "coherenceDb": coherence_db,
        "reason": "coherent tone present in both capture edges",
    }


def suppress_impulses(
    samples: np.ndarray,
    start: int,
    end: int,
    *,
    threshold_mad: float = 8.0,
    maximum_fraction: float = 0.05,
) -> tuple[np.ndarray, dict]:
    """Replace sparse magnitude outliers inside one burst by interpolation."""
    iq = np.asarray(samples, dtype=np.complex64).reshape(-1)
    if not 0 <= start < end <= iq.size:
        raise ValueError("invalid burst bounds for impulse suppression")
    segment = iq[start:end]
    magnitude = np.abs(segment)
    median = float(np.median(magnitude))
    mad = float(np.median(np.abs(magnitude - median)))
    robust_scale = max(1.4826 * mad, median * 0.02, np.finfo(np.float32).eps)
    threshold = median + threshold_mad * robust_scale
    mask = magnitude > threshold
    count = int(np.count_nonzero(mask))
    if count == 0 or count / segment.size > maximum_fraction:
        return iq.copy(), {
            "suppressedSamples": 0,
            "candidateSamples": count,
            "thresholdMagnitude": threshold,
            "applied": False,
            "reason": "no sparse impulses" if count == 0 else "candidate fraction exceeds safety limit",
        }
    good = np.flatnonzero(~mask)
    bad = np.flatnonzero(mask)
    if good.size < 2:
        return iq.copy(), {
            "suppressedSamples": 0,
            "candidateSamples": count,
            "thresholdMagnitude": threshold,
            "applied": False,
            "reason": "insufficient clean neighbors",
        }
    repaired = segment.copy()
    repaired.real[bad] = np.interp(bad, good, segment.real[good])
    repaired.imag[bad] = np.interp(bad, good, segment.imag[good])
    output = iq.copy()
    output[start:end] = repaired
    return output, {
        "suppressedSamples": count,
        "candidateSamples": count,
        "thresholdMagnitude": threshold,
        "applied": True,
        "reason": "sparse magnitude outliers interpolated",
    }
