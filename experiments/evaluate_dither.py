#!/usr/bin/env python3
"""Evaluate dithered bitmaps against the unadjusted original via print simulation.

For each bitmap the print is simulated, filtered by the S-CIELAB luminance
contrast-sensitivity function for the viewing distance and compared in CIE L*
with the original, which is resized and converted to grey with no gamma,
contrast or blur adjustment and mapped into the printable L* range.

Columns (see thermal_photo_box.evaluate):
  bias         mean dL*; negative = darker than the original
  tone         local tone error (smooth part of dL*)
  texture      visible graininess (fine part of dL*, RMS)
  directional  0..1; how aligned the texture is in flat regions (worms, lines).
               Isotropic noise scores about 0.13.
  periodic     share of flat-region texture power in the top 0.1% of
               frequencies (grids). Isotropic noise scores about 0.01.
"""
import argparse
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from thermal_photo_box.cli import WIDTH, preprocess
from thermal_photo_box.evaluate import evaluate
from thermal_photo_box.simulate import DEFAULT_RADIUS, DotModel


def artifact_sheet(items, columns=2):
    """Grid of artifact maps (darker = stronger aligned texture), one shared scale."""
    peak = max(float(np.percentile(m, 99.5)) for _, m in items) or 1.0
    font = ImageFont.load_default(size=24)
    h, w = items[0][1].shape
    label_h, pad = 34, 12
    rows = (len(items) + columns - 1) // columns
    sheet = Image.new("L", (columns * (w + pad) + pad, rows * (h + label_h + pad) + pad), 255)
    draw = ImageDraw.Draw(sheet)
    for i, (name, amap) in enumerate(items):
        x = pad + (i % columns) * (w + pad)
        y = pad + (i // columns) * (h + label_h + pad)
        img = (255 * (1 - np.clip(amap / peak, 0, 1))).astype(np.uint8)
        draw.text((x, y), name, fill=0, font=font)
        sheet.paste(Image.fromarray(img), (x, y + label_h))
        draw.rectangle((x - 1, y + label_h - 1, x + w, y + label_h + h), outline=160)
    return sheet


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0],
                                     formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    parser.add_argument("original", type=Path, help="Original source image (not the preprocessed grey)")
    parser.add_argument("bitmaps", type=Path, nargs="+", help="1-bit PNGs to evaluate")
    parser.add_argument("--model", choices=["heat", "overlap"], default="heat")
    parser.add_argument("--radii", type=float, nargs="+", help="Isolated-dot radii (default: model default)")
    parser.add_argument("--distance", type=float, default=30.0, help="Viewing distance in cm")
    parser.add_argument("--artifacts", type=Path, help="Write an artifact-map sheet (first radius) to this PNG")
    args = parser.parse_args()

    reference = preprocess(args.original, WIDTH, 1.0, 1.0, 0.0)
    bitmaps = []
    for path in args.bitmaps:
        with Image.open(path) as src:
            bitmaps.append((path.stem, src.convert("1")))

    radii = args.radii or [DEFAULT_RADIUS[args.model]]
    for n, radius in enumerate(radii):
        model = DotModel(radius=radius, kind=args.model)
        print(f"\n{args.model} model, radius {radius:.2f}, viewing distance {args.distance:g} cm")
        print(f"{'method':<14}{'bias':>8}{'tone':>8}{'texture':>9}{'directional':>13}{'periodic':>10}")
        maps = []
        for name, bitmap in bitmaps:
            e = evaluate(bitmap, reference, model, distance_cm=args.distance)
            print(f"{name:<14}{e.bias:>+8.1f}{e.tone:>8.1f}{e.texture:>9.2f}{e.directional:>13.2f}{e.periodic:>10.3f}")
            maps.append((name, e.artifact_map))
        if n == 0 and args.artifacts:
            args.artifacts.parent.mkdir(parents=True, exist_ok=True)
            artifact_sheet(maps).save(args.artifacts, optimize=True)
            print(f"Saved {args.artifacts}")


if __name__ == "__main__":
    main()
