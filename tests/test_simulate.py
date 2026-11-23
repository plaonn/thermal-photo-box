import unittest

import numpy as np
from PIL import Image

from thermal_photo_box.simulate import DotModel, simulate


class SimulateTest(unittest.TestCase):
    def test_blank_and_solid(self):
        model = DotModel(kind="overlap", radius=0.75)
        white = np.asarray(simulate(Image.new("1", (6, 6), 1), 4, model))
        black = np.asarray(simulate(Image.new("1", (6, 6), 0), 4, model))
        self.assertEqual(white.shape, (24, 24))
        self.assertTrue((white == model.paper).all())
        self.assertTrue((black == model.ink).all())

    def test_single_dot_area_matches_ellipse(self):
        model = DotModel(radius=0.75, aspect=1.2, blur=0, kind="overlap")
        img = Image.new("1", (5, 5), 1)
        img.putpixel((2, 2), 0)
        scale = 16
        grey = np.asarray(simulate(img, scale, model), dtype=np.float32)
        coverage = (model.paper - grey) / (model.paper - model.ink)
        expected = np.pi * 0.75 * 0.75 * 1.2 * scale * scale
        self.assertAlmostEqual(coverage.sum() / expected, 1.0, delta=0.02)

    def test_dot_is_taller_than_wide_with_aspect(self):
        model = DotModel(radius=0.6, aspect=1.5, blur=0, kind="overlap")
        img = Image.new("1", (5, 5), 1)
        img.putpixel((2, 2), 0)
        dark = np.asarray(simulate(img, 16, model)) < 128
        rows = np.where(dark.any(axis=1))[0]
        cols = np.where(dark.any(axis=0))[0]
        self.assertGreater(np.ptp(rows), np.ptp(cols))

    def test_heat_isolated_dot_radius(self):
        model = DotModel(radius=0.6, aspect=1.0)
        img = Image.new("1", (9, 9), 1)
        img.putpixel((4, 4), 0)
        scale = 16
        grey = np.asarray(simulate(img, scale, model), dtype=np.float32)
        half = (grey < (model.paper + model.ink) / 2).sum()
        self.assertAlmostEqual(half / (np.pi * 0.6 * 0.6 * scale * scale), 1.0, delta=0.08)

    def test_heat_fills_gaps_between_neighbours(self):
        # Two dots one pitch apart: the boundary between them is darker than
        # the same position next to a single dot (summed heat tails).
        model = DotModel()
        scale = 16
        single = Image.new("1", (9, 9), 1)
        single.putpixel((4, 4), 0)
        pair = single.copy()
        pair.putpixel((5, 4), 0)
        y, x = 4 * scale + scale // 2, 5 * scale
        a = np.asarray(simulate(single, scale, model), dtype=np.float32)[y, x]
        b = np.asarray(simulate(pair, scale, model), dtype=np.float32)[y, x]
        self.assertLess(b, a - 50)

    def test_heat_blank_and_solid(self):
        model = DotModel()
        white = np.asarray(simulate(Image.new("1", (8, 8), 1), 4, model))
        black = np.asarray(simulate(Image.new("1", (8, 8), 0), 4, model))
        self.assertTrue((white == model.paper).all())
        # Image edges receive heat from one side only; check the interior.
        self.assertLessEqual(np.abs(black[8:-8, 8:-8].astype(int) - model.ink).max(), 1)


if __name__ == "__main__":
    unittest.main()
