"""Minimal SigMF reader/writer for reproducible offline IQ experiments."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

import numpy as np


@dataclass(frozen=True)
class SigMFCapture:
    samples: np.ndarray
    metadata: dict[str, Any]
    sample_rate: float
    center_frequency: float | None
    datatype: str
    hardware: str | None


_DTYPES = {
    "cf32_le": (np.dtype("<f4"), 1.0),
    "cf32_be": (np.dtype(">f4"), 1.0),
    "ci16_le": (np.dtype("<i2"), 32768.0),
    "ci16_be": (np.dtype(">i2"), 32768.0),
}


def _paths(path: str | Path) -> tuple[Path, Path]:
    source = Path(path)
    if source.name.endswith(".sigmf-meta"):
        base = source.with_name(source.name.removesuffix(".sigmf-meta"))
    elif source.name.endswith(".sigmf-data"):
        base = source.with_name(source.name.removesuffix(".sigmf-data"))
    else:
        base = source
    return base.with_name(base.name + ".sigmf-meta"), base.with_name(base.name + ".sigmf-data")


def load(path: str | Path) -> SigMFCapture:
    meta_path, data_path = _paths(path)
    metadata = json.loads(meta_path.read_text(encoding="utf-8"))
    global_meta = metadata.get("global", {})
    datatype = global_meta.get("core:datatype")
    if datatype not in _DTYPES:
        raise ValueError(f"unsupported SigMF datatype: {datatype!r}")
    sample_rate = float(global_meta.get("core:sample_rate", 0))
    if not np.isfinite(sample_rate) or sample_rate <= 0:
        raise ValueError("SigMF core:sample_rate must be positive")
    scalar_dtype, scale = _DTYPES[datatype]
    scalars = np.fromfile(data_path, dtype=scalar_dtype)
    if scalars.size % 2:
        raise ValueError("IQ data must contain interleaved I/Q scalar pairs")
    values = scalars.astype(np.float32) / scale
    samples = (values[0::2] + 1j * values[1::2]).astype(np.complex64)
    captures = metadata.get("captures") or [{}]
    frequency = captures[0].get("core:frequency")
    return SigMFCapture(
        samples=samples,
        metadata=metadata,
        sample_rate=sample_rate,
        center_frequency=float(frequency) if frequency is not None else None,
        datatype=datatype,
        hardware=global_meta.get("core:hw"),
    )


def write_cf32(path: str | Path, samples: np.ndarray, sample_rate: float, *, center_frequency: float | None = None, hardware: str | None = None, description: str | None = None) -> tuple[Path, Path]:
    if not np.isfinite(sample_rate) or sample_rate <= 0:
        raise ValueError("sample_rate must be positive")
    iq = np.asarray(samples, dtype=np.complex64).reshape(-1)
    meta_path, data_path = _paths(path)
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    interleaved = np.empty(iq.size * 2, dtype="<f4")
    interleaved[0::2], interleaved[1::2] = iq.real, iq.imag
    interleaved.tofile(data_path)
    global_meta: dict[str, Any] = {
        "core:datatype": "cf32_le",
        "core:sample_rate": float(sample_rate),
        "core:version": "1.2.5",
        "core:recorder": "uav-protocol-evidence-demo",
    }
    if hardware:
        global_meta["core:hw"] = hardware
    if description:
        global_meta["core:description"] = description
    capture: dict[str, Any] = {"core:sample_start": 0}
    if center_frequency is not None:
        capture["core:frequency"] = float(center_frequency)
    metadata = {"global": global_meta, "captures": [capture], "annotations": []}
    meta_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return meta_path, data_path
