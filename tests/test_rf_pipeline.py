import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from rf.generate_iq_fixture import generate
from rf.fsk_demod import demodulate, preprocess
from rf.candidate_selector import select
from rf.protocol_feedback import mavlink_evidence
from rf.sigmf_io import load
from rf.signal_quality import analyze, remove_dc


class RFInputTests(unittest.TestCase):
    def test_sigmf_and_quality_pipeline(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory) / "fixture"
            meta_path, data_path = generate(base)
            self.assertTrue(meta_path.exists())
            self.assertTrue(data_path.exists())
            capture = load(meta_path)
            self.assertEqual(capture.datatype, "cf32_le")
            self.assertEqual(capture.sample_rate, 48_000)
            self.assertEqual(capture.center_frequency, 433_920_000)
            self.assertEqual(capture.samples.size, 11_840)
            report = analyze(capture.samples, capture.sample_rate)
            self.assertEqual(report["schema"], "iq-quality-report-v1")
            self.assertEqual(len(report["bursts"]), 1)
            burst = report["bursts"][0]
            self.assertLessEqual(abs(burst["startSample"] - 1_600), 100)
            self.assertLessEqual(abs(burst["endSample"] - 10_240), 100)
            self.assertGreater(report["estimatedSnrDb"], 12)
            self.assertTrue(abs(report["peakOffsetHz"] - 4_200) < 200 or abs(report["peakOffsetHz"] + 1_800) < 200)
            json.dumps(report)
            processed = preprocess(capture.samples, capture.sample_rate, 1_200)
            self.assertLess(abs(processed["carrierOffsetHz"] - 1_200), 150)
            demod = demodulate(capture.samples, capture.sample_rate, 1_200)
            expected = bytes.fromhex("FD 09 00 00 00 01 01 00 00 00 00 00 00 00 02 03 00 04 03 4A D7")
            self.assertEqual(demod["payload"][:len(expected)], expected)
            self.assertLessEqual(demod["preambleBitErrors"], 2)
            evidence = mavlink_evidence(demod["payload"])
            self.assertEqual(evidence["validFrames"], 1)
            selection = select(capture.samples, capture.sample_rate, [800, 1_000, 1_200, 2_400])
            self.assertEqual(selection["chosenSymbolRate"], 1_200)
            self.assertEqual(selection["validProtocolFrames"], 1)
            self.assertEqual(len(selection["candidates"]), 4)

    def test_dc_removal(self):
        samples = np.array([1 + 2j, 3 + 4j], dtype=np.complex64)
        cleaned, offset = remove_dc(samples)
        self.assertAlmostEqual(offset.real, 2)
        self.assertAlmostEqual(offset.imag, 3)
        self.assertAlmostEqual(abs(np.mean(cleaned)), 0)

    def test_ci16_reader(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory) / "ci16"
            Path(str(base) + ".sigmf-meta").write_text(json.dumps({"global": {"core:datatype": "ci16_le", "core:sample_rate": 1_000}, "captures": [{"core:sample_start": 0}]}), encoding="utf-8")
            np.array([32767, 0, 0, -32768], dtype="<i2").tofile(Path(str(base) + ".sigmf-data"))
            capture = load(base)
            self.assertEqual(capture.samples.size, 2)
            self.assertAlmostEqual(float(capture.samples[0].real), 32767 / 32768)
            self.assertAlmostEqual(float(capture.samples[1].imag), -1)


if __name__ == "__main__":
    unittest.main()
