"""Minimal evidence-producing 2-FSK preprocessing and demodulation chain."""
from __future__ import annotations

import math
from typing import Any

import numpy as np

from rf.denoise import suppress_impulses
from rf.signal_quality import detect_bursts, remove_dc


def estimate_tones(samples: np.ndarray, sample_rate: float, *, minimum_separation_hz: float = 1_000) -> tuple[float, float]:
    iq = np.asarray(samples, dtype=np.complex64).reshape(-1)
    spectrum = np.abs(np.fft.fftshift(np.fft.fft(iq * np.hanning(iq.size)))) ** 2
    frequencies = np.fft.fftshift(np.fft.fftfreq(iq.size, 1 / sample_rate))
    order = np.argsort(spectrum)[::-1]
    first = int(order[0])
    second = next((int(index) for index in order[1:] if abs(frequencies[index] - frequencies[first]) >= minimum_separation_hz), None)
    if second is None:
        raise ValueError("unable to resolve two FSK tones")
    low, high = sorted((float(frequencies[first]), float(frequencies[second])))
    return low, high


def frequency_shift(samples: np.ndarray, sample_rate: float, offset_hz: float) -> np.ndarray:
    iq = np.asarray(samples, dtype=np.complex64).reshape(-1)
    phase = -2j * np.pi * offset_hz * np.arange(iq.size) / sample_rate
    return (iq * np.exp(phase)).astype(np.complex64)


def lowpass(samples: np.ndarray, sample_rate: float, cutoff_hz: float, taps: int = 129) -> np.ndarray:
    if not 0 < cutoff_hz < sample_rate / 2:
        raise ValueError("cutoff_hz must be between zero and Nyquist")
    if taps < 3 or taps % 2 == 0:
        raise ValueError("taps must be an odd integer >= 3")
    positions = np.arange(taps) - (taps - 1) / 2
    normalized = cutoff_hz / sample_rate
    kernel = 2 * normalized * np.sinc(2 * normalized * positions) * np.hamming(taps)
    kernel /= np.sum(kernel)
    return np.convolve(np.asarray(samples, dtype=np.complex64), kernel.astype(np.float32), mode="same").astype(np.complex64)


def normalize_rms(samples: np.ndarray, target: float = 0.5) -> tuple[np.ndarray, float]:
    iq = np.asarray(samples, dtype=np.complex64).reshape(-1)
    rms = float(np.sqrt(np.mean(np.abs(iq) ** 2))) if iq.size else 0.0
    gain = target / rms if rms > 0 else 1.0
    return (iq * gain).astype(np.complex64), gain


def preprocess(
    samples: np.ndarray,
    sample_rate: float,
    symbol_rate: float,
    *,
    suppress_impulsive: bool = True,
) -> dict[str, Any]:
    cleaned, dc = remove_dc(samples)
    bursts, _, _ = detect_bursts(cleaned)
    if not bursts:
        raise ValueError("no burst detected")
    start, end = max(bursts, key=lambda item: item[1] - item[0])
    impulse_report = {"suppressedSamples": 0, "applied": False, "reason": "disabled"}
    if suppress_impulsive:
        cleaned, impulse_report = suppress_impulses(cleaned, start, end)
    low, high = estimate_tones(cleaned[start:end], sample_rate, minimum_separation_hz=max(symbol_rate * 0.75, 200))
    if (high - low) / 2 < symbol_rate:
        segment = cleaned[start:end]
        instantaneous = np.angle(segment[1:] * np.conj(segment[:-1])) * sample_rate / (2 * np.pi)
        smoothing = max(3, round(sample_rate / symbol_rate / 6))
        smoothed = np.convolve(
            instantaneous,
            np.ones(smoothing, dtype=np.float32) / smoothing,
            mode="valid",
        )
        low, high = map(float, np.quantile(smoothed, [0.1, 0.9]))
    carrier_offset = (low + high) / 2
    deviation = (high - low) / 2
    corrected = frequency_shift(cleaned, sample_rate, carrier_offset)
    cutoff = min(sample_rate * 0.45, deviation + symbol_rate * 1.25)
    filtered = lowpass(corrected, sample_rate, cutoff)
    active_rms = float(np.sqrt(np.mean(np.abs(filtered[start:end]) ** 2)))
    gain = 0.5 / active_rms if active_rms > 0 else 1.0
    normalized = (filtered * gain).astype(np.complex64)
    return {"samples": normalized, "burst": (start, end), "dcOffset": dc, "toneLowHz": low, "toneHighHz": high, "carrierOffsetHz": carrier_offset, "deviationHz": deviation, "filterCutoffHz": cutoff, "gain": gain, "impulseSuppression": impulse_report}


def _bits_to_bytes(bits: np.ndarray) -> bytes:
    usable = bits[: bits.size - bits.size % 8]
    return np.packbits(usable.astype(np.uint8), bitorder="big").tobytes()


def demodulate(samples: np.ndarray, sample_rate: float, symbol_rate: float, *, preamble: bytes = bytes.fromhex("55 55 55 55 D3 91"), suppress_impulsive: bool = True) -> dict[str, Any]:
    processed = preprocess(samples, sample_rate, symbol_rate, suppress_impulsive=suppress_impulsive)
    start, end = processed["burst"]
    segment = processed["samples"][start:end]
    instantaneous = np.angle(segment[1:] * np.conj(segment[:-1])) * sample_rate / (2 * np.pi)
    samples_per_symbol = int(round(sample_rate / symbol_rate))
    if not math.isclose(samples_per_symbol, sample_rate / symbol_rate, rel_tol=0, abs_tol=1e-6):
        raise ValueError("this baseline requires an integer number of samples per symbol")
    preamble_bits = np.unpackbits(np.frombuffer(preamble, dtype=np.uint8), bitorder="big")
    candidates = []
    for timing in range(samples_per_symbol):
        usable = instantaneous[timing:]
        usable = usable[: usable.size - usable.size % samples_per_symbol]
        if usable.size < preamble_bits.size * samples_per_symbol:
            continue
        means = usable.reshape(-1, samples_per_symbol).mean(axis=1)
        for inverted in (False, True):
            bits = (means < 0 if inverted else means > 0).astype(np.uint8)
            for position in range(0, bits.size - preamble_bits.size + 1):
                errors = int(np.count_nonzero(bits[position:position + preamble_bits.size] != preamble_bits))
                if errors <= 2:
                    confidence = float(np.mean(np.abs(means)) / (np.std(means - np.sign(means) * np.mean(np.abs(means))) + 1e-9))
                    candidates.append((errors, -confidence, timing, inverted, position, bits, means))
                    break
    if not candidates:
        raise ValueError("preamble not found after 2-FSK demodulation")
    errors, negative_confidence, timing, inverted, position, bits, means = min(candidates, key=lambda item: (item[0], item[1], item[4]))
    payload_bits = bits[position + preamble_bits.size:]
    payload = _bits_to_bytes(payload_bits)
    return {
        "schema": "fsk-demod-report-v1",
        "payload": payload,
        "payloadHex": payload.hex(" ").upper(),
        "symbolRate": float(symbol_rate),
        "samplesPerSymbol": samples_per_symbol,
        "timingOffset": timing,
        "bitPolarityInverted": inverted,
        "preambleBitErrors": errors,
        "decisionConfidence": -negative_confidence,
        "burst": {"startSample": start, "endSample": end},
        "preprocess": {
            key: (float(value.real) if isinstance(value, complex) else float(value))
            for key, value in processed.items()
            if key not in {"samples", "burst", "dcOffset", "impulseSuppression"}
        },
        "impulseSuppression": processed["impulseSuppression"],
        "dcOffset": {"i": processed["dcOffset"].real, "q": processed["dcOffset"].imag},
        "boundary": "当前基线仅适用于已知符号率的2-FSK；同步字命中和协议CRC仍需共同验证。",
    }
