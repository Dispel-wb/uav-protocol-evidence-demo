"""Small, evidence-producing denoisers shared by waveform demodulators."""
from __future__ import annotations

import numpy as np


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
