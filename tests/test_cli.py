import sys
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from thermal_photo_box.cli import dither

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "experiments"))
from extra_dither import EXTRA_METHODS  # noqa: E402


def ink(img):
    return float((np.asarray(img.convert("L")) == 0).mean())


class DitherTest(unittest.TestCase):
    def setUp(self):
        ramp = np.tile(np.linspace(0, 255, 96), (48, 1)).astype(np.uint8)
        self.gray = Image.fromarray(ramp)

    def test_jjn_noise_matches_experiment(self):
        cli = np.asarray(dither(self.gray, "jjn-noise"))
        experiment = np.asarray(EXTRA_METHODS["jjn-tm64"](self.gray))
        self.assertGreater((cli == experiment).mean(), 0.99)

    def test_jjn_noise_keeps_tone(self):
        for level in (32, 128, 224):
            flat = Image.new("L", (64, 64), level)
            self.assertAlmostEqual(ink(dither(flat, "jjn-noise")), 1 - level / 255, delta=0.03)

    def test_jjn_noise_is_one_bit_and_deterministic(self):
        a, b = dither(self.gray, "jjn-noise"), dither(self.gray, "jjn-noise")
        self.assertEqual(a.mode, "1")
        self.assertTrue((np.asarray(a) == np.asarray(b)).all())


if __name__ == "__main__":
    unittest.main()
