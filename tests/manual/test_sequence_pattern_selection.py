# -*- coding: utf-8 -*-
"""Tests covering configurable image sequence pattern detection."""
import os
import shutil
import tempfile
import unittest

from src.ingestion_core import SequenceDetector


class SequenceDetectorPatternTests(unittest.TestCase):
    """Validate pattern-aware sequence detection logic."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix='stax_seq_pattern_')

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def _make_files(self, filenames):
        paths = []
        for filename in filenames:
            path = os.path.join(self.temp_dir, filename)
            with open(path, 'w'):
                pass
            paths.append(path)
        return paths

    def test_pattern_selection_respects_separator(self):
        dot_files = ['plate.1001.exr', 'plate.1002.exr']
        underscore_files = ['plate_1001.exr', 'plate_1002.exr']
        all_files = dot_files + underscore_files
        paths = self._make_files(all_files)

        dot_sequence = SequenceDetector.detect_sequence(
            paths[0], pattern_key='.####.ext', auto_detect=True
        )
        self.assertIsNotNone(dot_sequence)
        if dot_sequence:
            self.assertEqual(dot_sequence['frame_count'], len(dot_files))

        underscore_sequence = SequenceDetector.detect_sequence(
            os.path.join(self.temp_dir, underscore_files[0]),
            pattern_key='.####.ext',
            auto_detect=True
        )
        self.assertIsNone(underscore_sequence)

    def test_variable_digit_lengths_detected(self):
        paths = self._make_files(['image.1.exr', 'image.10.exr', 'image.003.exr'])
        sequence = SequenceDetector.detect_sequence(paths[0], pattern_key='.####.ext', auto_detect=True)
        self.assertIsNotNone(sequence)
        if sequence:
            self.assertEqual(sequence['frame_range'], '1-10')
            self.assertEqual(os.path.basename(sequence['files'][0]), 'image.1.exr')
            self.assertEqual(os.path.basename(sequence['files'][-1]), 'image.10.exr')


if __name__ == '__main__':
    unittest.main()
