#!/usr/bin/env python3
"""Write a synthetic chart of uniform grey patches (576 dots wide).

Uniform areas are where dithering artifacts (worms, diagonal lines, grids) are
most visible, because the original has no structure there.
"""
import argparse
from pathlib import Path

import numpy as np
from PIL import Image

# sRGB grey levels, light to dark, two rows of five patches.
LEVELS = (242, 217, 191, 166, 140, 115, 89, 64, 38, 13)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output", type=Path, default=Path("docs/sample/patches.png"))
    parser.add_argument("--width", type=int, default=576)
    parser.add_argument("--patch-height", type=int, default=160)
    args = parser.parse_args()

    cols = 5
    edges = np.linspace(0, args.width, cols + 1).round().astype(int)
    chart = np.zeros((2 * args.patch_height, args.width), dtype=np.uint8)
    for i, level in enumerate(LEVELS):
        r, c = divmod(i, cols)
        chart[r * args.patch_height:(r + 1) * args.patch_height, edges[c]:edges[c + 1]] = level
    args.output.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(chart).save(args.output, optimize=True)
    print(f"Saved {args.output}")


if __name__ == "__main__":
    main()
