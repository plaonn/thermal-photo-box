import unittest

import numpy as np
from PIL import Image

from thermal_photo_box.evaluate import csf_filter, evaluate, lstar, lstar_to_y
from thermal_photo_box.simulate import DotModel


def bitmap_from(array):
    return Image.fromarray(np.where(array, 0, 255).astype(np.uint8)).convert("1", dither=Image.Dither.NONE)


class EvaluateTest(unittest.TestCase):
    def test_lstar_roundtrip(self):
        y = np.linspace(0.001, 1, 50)
        np.testing.assert_allclose(lstar_to_y(lstar(y)), y, rtol=1e-9)

    def test_csf_keeps_uniform_level(self):
        np.testing.assert_allclose(csf_filter(np.full((64, 64), 0.4), 42.0), 0.4, atol=1e-9)

    def test_stripes_are_directional_and_noise_is_not(self):
        size = 160
        rng = np.random.default_rng(0)
        reference = Image.new("L", (size, size), 128)
        model = DotModel(radius=0.5)
        y, x = np.mgrid[:size, :size]
        stripes = ((x + y) // 2) % 4 == 0  # diagonal lines, 25% coverage
        noise = rng.random((size, size)) < 0.25
        e_stripes = evaluate(bitmap_from(stripes), reference, model, scale=2)
        e_noise = evaluate(bitmap_from(noise), reference, model, scale=2)
        self.assertGreater(e_stripes.directional, e_noise.directional + 0.3)
        self.assertGreater(e_stripes.periodic, 10 * e_noise.periodic)

    def test_size_mismatch_is_rejected(self):
        with self.assertRaises(ValueError):
            evaluate(Image.new("1", (10, 10)), Image.new("L", (12, 10)))


if __name__ == "__main__":
    unittest.main()
