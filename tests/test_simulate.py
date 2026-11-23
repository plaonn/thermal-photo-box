import unittest

import numpy as np
from PIL import Image

from thermal_photo_box.simulate import DotModel, simulate


class SimulateTest(unittest.TestCase):
    def test_blank_and_solid(self):
        model = DotModel()
        white = np.asarray(simulate(Image.new("1", (6, 6), 1), 4, model))
        black = np.asarray(simulate(Image.new("1", (6, 6), 0), 4, model))
        self.assertEqual(white.shape, (24, 24))
        self.assertTrue((white == model.paper).all())
        self.assertTrue((black == model.ink).all())

    def test_single_dot_area_matches_ellipse(self):
        model = DotModel(radius=0.75, aspect=1.2, blur=0)
        img = Image.new("1", (5, 5), 1)
        img.putpixel((2, 2), 0)
        scale = 16
        grey = np.asarray(simulate(img, scale, model), dtype=np.float32)
        coverage = (model.paper - grey) / (model.paper - model.ink)
        expected = np.pi * 0.75 * 0.75 * 1.2 * scale * scale
        self.assertAlmostEqual(coverage.sum() / expected, 1.0, delta=0.02)

    def test_dot_is_taller_than_wide_with_aspect(self):
        model = DotModel(radius=0.6, aspect=1.5, blur=0)
        img = Image.new("1", (5, 5), 1)
        img.putpixel((2, 2), 0)
        dark = np.asarray(simulate(img, 16, model)) < 128
        rows = np.where(dark.any(axis=1))[0]
        cols = np.where(dark.any(axis=0))[0]
        self.assertGreater(np.ptp(rows), np.ptp(cols))


if __name__ == "__main__":
    unittest.main()
