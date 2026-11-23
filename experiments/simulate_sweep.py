#!/usr/bin/env python3
"""Score dithered bitmaps under the dot-overlap model for a range of dot radii.

For each bitmap and radius: simulate the print, average each dot cell back to
one value, low-pass both it and the target grayscale with a Gaussian (a crude
model of viewing distance) and compare. The target is the grayscale input
mapped into the paper..ink range. Two numbers are reported per cell:

- bias: mean(simulated - target); negative means the print comes out darker.
  Dot gain shows up here, and a global tone curve can partly compensate it.
- structure: standard deviation of the difference, i.e. the error left after
  removing the global bias. Lower is closer to the target.

This is a sanity check of the model, not a perceptual quality metric.
"""
import argparse
from pathlib import Path

import numpy as np
from PIL import Image

from thermal_photo_box.simulate import DotModel, simulate


def cell_average(image, scale):
    a = np.asarray(image, dtype=np.float32)
    h, w = a.shape[0] // scale, a.shape[1] // scale
    return a[:h * scale, :w * scale].reshape(h, scale, w, scale).mean(axis=(1, 3))


def lowpass(a, sigma):
    """Separable Gaussian blur with edge padding."""
    r = int(np.ceil(3 * sigma))
    k = np.exp(-0.5 * (np.arange(-r, r + 1) / sigma) ** 2)
    k /= k.sum()
    p = np.pad(a, r, mode="edge")
    p = np.apply_along_axis(lambda v: np.convolve(v, k, mode="valid"), 0, p)
    return np.apply_along_axis(lambda v: np.convolve(v, k, mode="valid"), 1, p)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("gray", type=Path, help="Grayscale target (00-grayscale.png)")
    parser.add_argument("bitmaps", type=Path, nargs="+", help="1-bit PNGs to score")
    parser.add_argument("--radii", type=float, nargs="+", default=[0.4, 0.5, 0.55, 0.6, 0.7])
    parser.add_argument("--model", choices=["heat", "overlap"], default="heat")
    parser.add_argument("--threshold", type=float, default=DotModel.threshold)
    parser.add_argument("--aspect", type=float, default=DotModel.aspect)
    parser.add_argument("--sigma", type=float, default=1.5, help="Viewing low-pass sigma in dots")
    parser.add_argument("--scale", type=int, default=4)
    args = parser.parse_args()

    base = DotModel()
    with Image.open(args.gray) as g:
        target = np.asarray(g.convert("L"), dtype=np.float32)
    target = base.ink + target / 255.0 * (base.paper - base.ink)
    target_lp = lowpass(target, args.sigma)

    bitmaps = []
    for path in args.bitmaps:
        with Image.open(path) as src:
            bitmaps.append((path.stem, src.convert("1")))

    print(f"{args.model} model; bias / structure after a {args.sigma}-dot low-pass (grey levels)")
    print("radius  " + "  ".join(f"{name:>14}" for name, _ in bitmaps))
    for radius in args.radii:
        model = DotModel(radius=radius, aspect=args.aspect, paper=base.paper, ink=base.ink, blur=base.blur,
                         kind=args.model, threshold=args.threshold)
        cells = []
        for _, bitmap in bitmaps:
            sim = lowpass(cell_average(simulate(bitmap, args.scale, model), args.scale), args.sigma)
            err = sim - target_lp
            cells.append(f"{err.mean():+6.1f} / {err.std():4.1f}")
        print(f"{radius:6.2f}  " + "  ".join(f"{c:>14}" for c in cells))


if __name__ == "__main__":
    main()
