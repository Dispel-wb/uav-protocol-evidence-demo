import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from rf.generate_iq_fixture import generate
from rf.fsk_demod import demodulate, preprocess
from rf.candidate_selector import select
from rf.protocol_feedback import mavlink_evidence
from rf.ring_buffer import ComplexRingBuffer
from rf.stream_capture import ArraySource, CaptureConfig, capture, capture_to_sigmf
from rf.full_pipeline import run as run_full_pipeline
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
            config = CaptureConfig(center_frequency=433_920_000, sample_rate=48_000, duration_seconds=capture.samples.size / 48_000, chunk_samples=1024, ring_samples=capture.samples.size)
            full = run_full_pipeline(ArraySource(capture.samples, 48_000), config, [800, 1_200, 2_400])
            self.assertTrue(full["complete"])
            self.assertEqual(full["selection"]["chosenSymbolRate"], 1_200)
            self.assertGreater(full["processingMilliseconds"], 0)

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

    def test_ring_and_replay_capture(self):
        ring = ComplexRingBuffer(4)
        ring.write(np.array([1, 2, 3], dtype=np.complex64))
        ring.write(np.array([4, 5, 6], dtype=np.complex64))
        np.testing.assert_array_equal(ring.latest(), np.array([3, 4, 5, 6], dtype=np.complex64))
        self.assertEqual(ring.overwritten, 2)

        samples = np.arange(16, dtype=np.float32).astype(np.complex64)
        config = CaptureConfig(center_frequency=100e6, sample_rate=8, duration_seconds=2, chunk_samples=5, ring_samples=16)
        source = ArraySource(samples, 8, start_timestamp_ns=1_000, overflow_chunks={1})
        captured, report = capture(source, config)
        np.testing.assert_array_equal(captured, samples)
        self.assertTrue(report["complete"])
        self.assertEqual(report["overflows"], 1)
        self.assertEqual(report["timeouts"], 0)
        with tempfile.TemporaryDirectory() as directory:
            meta, _, stored_report = capture_to_sigmf(ArraySource(samples, 8), config, Path(directory) / "replay")
            replayed = load(meta)
            np.testing.assert_array_equal(replayed.samples, samples)
            self.assertEqual(stored_report["receivedSamples"], 16)


if __name__ == "__main__":
    unittest.main()
