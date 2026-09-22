"""Evaluate conservative 2-FSK versus GFSK shape recognition."""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rf.candidate_selector import select
from rf.generate_iq_fixture import synthesize


def main() -> None:
    noise_levels = [0.02, 0.04, 0.08, 0.12]
    offsets = [-4_000, -2_000, 0, 2_000, 4_000]
    records = []
    for expected, gaussian_bt in (("2-FSK", None), ("GFSK", 0.5)):
        for noise in noise_levels:
            for index, offset in enumerate(offsets):
                samples, truth = synthesize(
                    gaussian_bt=gaussian_bt,
                    noise_std=noise,
                    carrier_offset=offset,
                    seed=20261100 + index + round(noise * 1000),
                )
                selection = select(samples, truth["sampleRate"], [truth["symbolRate"]])
                observed = selection["chosenModulation"]
                records.append({
                    "expected": expected,
                    "observed": observed,
                    "noiseStd": noise,
                    "carrierOffsetHz": offset,
                    "validProtocolFrames": selection["validProtocolFrames"],
                    "correct": observed == expected,
                    "rejected": observed is None,
                })
    wrong = sum(
        item["observed"] is not None and not item["correct"]
        for item in records
    )
    report = {
        "schema": "fsk-shape-evaluation-v1",
        "cases": len(records),
        "correct": sum(item["correct"] for item in records),
        "rejected": sum(item["rejected"] for item in records),
        "wrong": wrong,
        "validProtocolCases": sum(item["validProtocolFrames"] > 0 for item in records),
        "records": records,
        "boundary": "All cases are deterministic synthetic 2-FSK or BT=0.5 GFSK. This does not establish recognition performance for real radios or other pulse shapes.",
    }
    output = ROOT / "reports" / "fsk_shape_evaluation.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(output)
    print(json.dumps({key: report[key] for key in (
        "cases", "correct", "rejected", "wrong", "validProtocolCases"
    )}))
    if wrong or report["validProtocolCases"] != len(records):
        raise SystemExit("modulation shape evaluation failed")


if __name__ == "__main__":
    main()
