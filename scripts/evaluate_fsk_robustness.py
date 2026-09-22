"""Sweep deterministic noise and frequency offsets for the 2-FSK baseline."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rf.fsk_demod import demodulate
from rf.generate_iq_fixture import PAYLOAD, synthesize
from rf.protocol_feedback import mavlink_evidence


def main() -> None:
    offsets = [-4_000, -2_000, 0, 2_000, 4_000]
    noise_levels = [0.02, 0.04, 0.08, 0.12, 0.18]
    records = []
    for noise in noise_levels:
        for offset in offsets:
            seed = 20260923 + int(noise * 1000) + offset
            samples, truth = synthesize(
                noise_std=noise,
                carrier_offset=offset,
                seed=seed,
            )
            started = time.perf_counter()
            try:
                result = demodulate(samples, truth["sampleRate"], truth["symbolRate"])
                payload = result["payload"][:len(PAYLOAD)]
                evidence = mavlink_evidence(payload)
                exact = payload == PAYLOAD
                record = {
                    "noiseStd": noise,
                    "carrierOffsetHz": offset,
                    "status": "decoded",
                    "exactPayload": exact,
                    "validProtocolFrames": evidence["validFrames"],
                    "estimatedCarrierOffsetHz": result["preprocess"]["carrierOffsetHz"],
                    "preambleBitErrors": result["preambleBitErrors"],
                }
            except ValueError as error:
                record = {
                    "noiseStd": noise,
                    "carrierOffsetHz": offset,
                    "status": "rejected",
                    "exactPayload": False,
                    "validProtocolFrames": 0,
                    "reason": str(error),
                }
            record["processingMilliseconds"] = (time.perf_counter() - started) * 1000
            records.append(record)
    exact = sum(record["exactPayload"] for record in records)
    false_valid = sum(
        not record["exactPayload"] and record["validProtocolFrames"] > 0
        for record in records
    )
    report = {
        "schema": "fsk-robustness-sweep-v1",
        "cases": len(records),
        "exactCases": exact,
        "exactRate": exact / len(records),
        "falseValidProtocolFrames": false_valid,
        "noiseLevels": noise_levels,
        "carrierOffsetsHz": offsets,
        "records": records,
        "boundary": "全部为确定性合成信号；结果用于回归和寻找失败边界，不代表真实射频环境。",
    }
    output = ROOT / "reports" / "fsk_robustness.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(output)
    print(json.dumps({
        "cases": len(records),
        "exactCases": exact,
        "exactRate": report["exactRate"],
        "falseValidProtocolFrames": false_valid,
    }))
    if false_valid:
        raise SystemExit("failed payload was accepted as a valid protocol frame")


if __name__ == "__main__":
    main()
