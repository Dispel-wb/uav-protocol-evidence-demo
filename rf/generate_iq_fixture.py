"""Generate a deterministic noisy 2-FSK burst as a SigMF fixture."""
from pathlib import Path
import numpy as np

from rf.sigmf_io import write_cf32


PREAMBLE = bytes.fromhex("55 55 55 55 D3 91")
PAYLOAD = bytes.fromhex("FD 09 00 00 00 01 01 00 00 00 00 00 00 00 02 03 00 04 03 4A D7")


def synthesize(
    *,
    noise_std: float = 0.04,
    carrier_offset: float = 1_200,
    deviation: float = 3_000,
    amplitude: float = 0.4,
    sample_rate: float = 48_000,
    symbol_rate: float = 1_200,
    seed: int = 20260923,
) -> tuple[np.ndarray, dict]:
    samples_per_symbol = int(round(sample_rate / symbol_rate))
    if samples_per_symbol <= 0 or not np.isclose(samples_per_symbol, sample_rate / symbol_rate):
        raise ValueError("synthetic fixture requires integer samples per symbol")
    framed = PREAMBLE + PAYLOAD
    bits = np.unpackbits(np.frombuffer(framed, dtype=np.uint8), bitorder="big")
    start, burst_samples = 1_600, bits.size * samples_per_symbol
    end, total = start + burst_samples, start + burst_samples + 1_600
    rng = np.random.default_rng(seed)
    noise = rng.normal(0, noise_std, total) + 1j * rng.normal(0, noise_std, total)
    samples = noise.astype(np.complex64)
    samples += np.complex64(0.02 + 0.01j)
    tones = np.where(bits > 0, carrier_offset + deviation, carrier_offset - deviation)
    frequencies = np.repeat(tones, samples_per_symbol)
    phase = 2 * np.pi * np.cumsum(frequencies) / sample_rate
    samples[start:end] += (amplitude * np.exp(1j * phase)).astype(np.complex64)
    truth = {
        "schema": "synthetic-fsk-truth-v1",
        "sampleRate": sample_rate,
        "symbolRate": symbol_rate,
        "samplesPerSymbol": samples_per_symbol,
        "carrierOffsetHz": carrier_offset,
        "deviationHz": deviation,
        "noiseStd": noise_std,
        "amplitude": amplitude,
        "startSample": start,
        "endSample": end,
        "preambleHex": PREAMBLE.hex(" ").upper(),
        "payloadHex": PAYLOAD.hex(" ").upper(),
    }
    return samples, truth


def generate(path: str | Path) -> tuple[Path, Path]:
    samples, truth = synthesize()
    paths = write_cf32(
        path,
        samples,
        truth["sampleRate"],
        center_frequency=433_920_000,
        hardware="synthetic-fixture",
        description="Deterministic noisy 2-FSK MAVLink frame for offline regression only",
    )
    truth_path = Path(path).with_name(Path(path).name + "_truth.json")
    truth_path.write_text(__import__("json").dumps(truth, indent=2), encoding="utf-8")
    return paths


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    for item in generate(root / "samples" / "iq" / "fsk_demo"):
        print(item)
