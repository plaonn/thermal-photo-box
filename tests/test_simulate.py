import unittest

import numpy as np
from PIL import Image

from thermal_photo_box.simulate import DotModel, simulate, simulate_reflectance, srgb_to_linear


def coverage(img, scale, model):
    """Fraction of ink coverage per output pixel, from linear reflectance."""
    y = simulate_reflectance(img, scale, model)
    paper = float(srgb_to_linear(model.paper / 255))
    ink = float(srgb_to_linear(model.ink / 255))
    return (paper - y) / (paper - ink)


def single_dot(size=9):
    img = Image.new("1", (size, size), 1)
    img.putpixel((size // 2, size // 2), 0)
    return img


class OverlapModelTest(unittest.TestCase):
    def test_blank_and_solid(self):
        model = DotModel(kind="overlap", radius=0.75)
        white = np.asarray(simulate(Image.new("1", (6, 6), 1), 4, model))
        black = np.asarray(simulate(Image.new("1", (6, 6), 0), 4, model))
        self.assertEqual(white.shape, (24, 24))
        self.assertTrue((np.abs(white.astype(int) - model.paper) <= 1).all())
        self.assertTrue((np.abs(black.astype(int) - model.ink) <= 1).all())

    def test_single_dot_area_matches_ellipse(self):
        model = DotModel(radius=0.75, aspect=1.2, blur=0, kind="overlap")
        scale = 16
        c = coverage(single_dot(5), scale, model)
        expected = np.pi * 0.75 * 0.75 * 1.2 * scale * scale
        self.assertAlmostEqual(c.sum() / expected, 1.0, delta=0.02)

    def test_dot_is_taller_than_wide_with_aspect(self):
        model = DotModel(radius=0.6, aspect=1.5, blur=0, kind="overlap")
        dark = coverage(single_dot(5), 16, model) > 0.5
        rows = np.where(dark.any(axis=1))[0]
        cols = np.where(dark.any(axis=0))[0]
        self.assertGreater(np.ptp(rows), np.ptp(cols))


class HeatModelTest(unittest.TestCase):
    def test_isolated_dot_radius(self):
        model = DotModel(radius=0.6, aspect=1.0)
        scale = 16
        half = (coverage(single_dot(), scale, model) > 0.5).sum()
        self.assertAlmostEqual(half / (np.pi * 0.6 * 0.6 * scale * scale), 1.0, delta=0.08)

    def test_fills_gaps_between_neighbours(self):
        # Two dots one pitch apart: the boundary between them is darker than
        # the same position next to a single dot (summed heat tails).
        model = DotModel()
        scale = 16
        single = single_dot()
        pair = single.copy()
        pair.putpixel((5, 4), 0)
        y, x = 4 * scale + scale // 2, 5 * scale
        self.assertGreater(coverage(pair, scale, model)[y, x], coverage(single, scale, model)[y, x] + 0.3)

    def test_blank_and_solid(self):
        model = DotModel()
        white = coverage(Image.new("1", (8, 8), 1), 4, model)
        black = coverage(Image.new("1", (8, 8), 0), 4, model)
        self.assertTrue((np.abs(white) < 1e-6).all())
        # Image edges receive heat from one side only; check the interior.
        self.assertTrue((black[8:-8, 8:-8] > 0.99).all())



class SquareModelTest(unittest.TestCase):
    def test_each_dot_fills_its_cell(self):
        model = DotModel(kind="square")
        c = coverage(single_dot(3), 4, model)
        self.assertTrue(np.allclose(c[4:8, 4:8], 1.0))
        self.assertAlmostEqual(float(c.sum()), 16.0)


if __name__ == "__main__":
    unittest.main()
