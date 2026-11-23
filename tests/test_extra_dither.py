import sys
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "experiments"))
import extra_dither as ed  # noqa: E402


def ink(img):
    return float((np.asarray(img.convert("L")) == 0).mean())


class ExtraDitherTest(unittest.TestCase):
    def test_kernels_sum(self):
        for kernel in (ed.STUCKI, ed.BURKES, ed.SIERRA, ed.SIERRA2, ed.SIERRA_LITE, ed.SHIAU_FAN, ed.FS_KERNEL):
            self.assertAlmostEqual(sum(w for _, _, w in kernel), 1.0)
            self.assertTrue(all(dy > 0 or dx > 0 for dx, dy, _ in kernel))  # causal
        self.assertAlmostEqual(sum(w for _, _, w in ed.ATKINSON_KERNEL), 0.75)

    def test_void_and_cluster_is_permutation(self):
        mask = ed.void_and_cluster()
        self.assertEqual(sorted(mask.ravel().tolist()), list(range(mask.size)))

    def test_flat_grey_tone(self):
        grey = Image.new("L", (96, 96), 96)  # 62% ink
        target = 1 - 96 / 255
        for name, method in ed.EXTRA_METHODS.items():
            if name.startswith("atkinson"):
                continue  # Atkinson deliberately loses part of the error
            with self.subTest(name=name):
                self.assertAlmostEqual(ink(method(grey)), target, delta=0.03)


if __name__ == "__main__":
    unittest.main()
