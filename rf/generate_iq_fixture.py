"""Generate a deterministic noisy 2-FSK burst as a SigMF fixture."""
from pathlib import Path
import numpy as np

from rf.sigmf_io import write_cf32


def generate(path: str | Path) -> tuple[Path, Path]:
    sample_rate, symbol_rate, samples_per_symbol = 48_000.0, 1_200.0, 40
    preamble = bytes.fromhex("55 55 55 55 D3 91")
    payload = bytes.fromhex("FD 09 00 00 00 01 01 00 00 00 00 00 00 00 02 03 00 04 03 4A D7")
    framed = preamble + payload
    bits = np.unpackbits(np.frombuffer(framed, dtype=np.uint8), bitorder="big")
    start, burst_samples = 1_600, bits.size * samples_per_symbol
    end, total = start + burst_samples, start + burst_samples + 1_600
    rng = np.random.default_rng(20260923)
    samples = (rng.normal(0, 0.04, total) + 1j * rng.normal(0, 0.04, total)).astype(np.complex64)
    samples += np.complex64(0.02 + 0.01j)
    carrier_offset, deviation = 1_200.0, 3_000.0
    frequencies = np.repeat(np.where(bits > 0, carrier_offset + deviation, carrier_offset - deviation), samples_per_symbol)
    phase = 2 * np.pi * np.cumsum(frequencies) / sample_rate
    samples[start:end] += (0.4 * np.exp(1j * phase)).astype(np.complex64)
    paths = write_cf32(path, samples, sample_rate, center_frequency=433_920_000, hardware="synthetic-fixture", description="Deterministic noisy 2-FSK MAVLink frame for offline regression only")
    truth_path = Path(path).with_name(Path(path).name + "_truth.json")
    truth_path.write_text(__import__("json").dumps({"schema": "synthetic-fsk-truth-v1", "sampleRate": sample_rate, "symbolRate": symbol_rate, "samplesPerSymbol": samples_per_symbol, "carrierOffsetHz": carrier_offset, "deviationHz": deviation, "startSample": start, "endSample": end, "preambleHex": preamble.hex(" ").upper(), "payloadHex": payload.hex(" ").upper()}, indent=2), encoding="utf-8")
    return paths


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    for item in generate(root / "samples" / "iq" / "fsk_demo"):
        print(item)
