#!/usr/bin/env python3
"""Apparent lightness of 50% dot coverage in different arrangements, under the heat print model.

Shows that dot gain turns arrangement into tone: the same number of dots prints
lighter or darker depending on how they touch. Also a direct probe for the real
dot radius: print these patterns and compare.

Example:
    python experiments/arrangement.py
"""
import numpy as np
from PIL import Image

from thermal_photo_box.evaluate import lstar
from thermal_photo_box.simulate import DotModel, simulate_reflectance

SIZE = 64
RADII = (0.45, 0.55, 0.65, 0.75)


def patterns(n=SIZE):
    y, x = np.mgrid[:n, :n]
    return {"checkerboard": (x + y) % 2 == 0, "vertical lines": x % 2 == 0,
            "horizontal lines": y % 2 == 0, "2x2 clusters": (x // 2 + y // 2) % 2 == 0}


def main():
    pats = patterns()
    print(f"{'radius':>6}" + "".join(f"{k:>18}" for k in pats))
    for r in RADII:
        cells = []
        for dots in pats.values():
            image = Image.fromarray(np.where(dots, 0, 255).astype(np.uint8)).convert("1")
            y = simulate_reflectance(image, 4, DotModel(radius=r))[32:-32, 32:-32]
            cells.append(float(lstar(y.mean())))
        print(f"{r:>6}" + "".join(f"{c:>18.1f}" for c in cells))


if __name__ == "__main__":
    main()
