#!/usr/bin/env python3
"""How a plain square-pixel preview of a 1-bit image differs from the simulated print.

A 1-bit image shown on screen draws each dot as a filled square. On paper,
dots are round, spread, and merge with their neighbours. This script compares,
for a few methods:

- "screen (sRGB averaging)": the bitmap scaled down by an image viewer, which
  averages grey values without linearising them (most viewers and browsers);
- "square dots": each dot fills its cell exactly, mixed in linear light
  (the "square" dot model), i.e. a correct downscale of the bitmap;
- the heat print model at two radii.

It prints the apparent lightness of flat grey levels under each rendering,
evaluates the square model on all samples, and writes per-sample sheets
(one row per method) to --output.

Example:
    python experiments/square_preview.py --output docs/images/square --csv docs/square.csv
"""
import argparse
import csv
import sys
from pathlib import Path

import numpy as np
from PIL import Image

from thermal_photo_box.cli import WIDTH, preprocess
from thermal_photo_box.evaluate import evaluate, lstar
from thermal_photo_box.simulate import DotModel, simulate_reflectance, srgb_to_linear

sys.path.insert(0, str(Path(__file__).resolve().parent))
from benchmark import (DETAIL, DETAIL_SIZE, METRICS, ROOT, SAMPLES, fetch, grouped_sheet,  # noqa: E402
                       outlined_original, print_thumbnail)
from compare_dither import LABELS, METHODS, detail_crop  # noqa: E402
from extra_dither import EXTRA_METHODS  # noqa: E402

SHOWN = ("jjn", "atkinson", "floyd", "bayer", "clustered")
SHEET_SAMPLES = ("patches", "rocket", "sally-ride")
RADII = (0.55, 0.65)
SQUARE = DotModel(kind="square")


def srgb_average(bitmap, size, model=SQUARE):
    """The bitmap in paper/ink grey levels, downscaled by averaging sRGB values (no linearisation)."""
    grey = bitmap.convert("L").point(lambda v: model.paper if v else model.ink)
    return grey.resize(size, Image.Resampling.BOX)


def flat_grey_table(levels=(16, 48, 96, 128, 160, 208, 240)):
    """Apparent L* of flat grey levels dithered with JJN, under each rendering."""
    paper, ink = (float(lstar(srgb_to_linear(v / 255))) for v in (SQUARE.paper, SQUARE.ink))
    rows = []
    for g in levels:
        bitmap = METHODS["jjn"](Image.new("L", (128, 128), g))
        target = ink + float(lstar(srgb_to_linear(g / 255))) / 100 * (paper - ink)
        viewer = np.asarray(srgb_average(bitmap, (1, 1)), dtype=np.float64)[0, 0]
        cells = [float(lstar(srgb_to_linear(viewer / 255)))]
        for model in (SQUARE, *(DotModel(radius=r) for r in RADII)):
            y = simulate_reflectance(bitmap, 4, model)[32:-32, 32:-32]
            cells.append(float(lstar(y.mean())))
        rows.append((g, target, *cells))
    return rows


def sheet(sample, reference, bitmaps, detail):
    columns = (["square"] if detail else ["srgb", "square"]) + [str(r) for r in RADII]
    names = {"srgb": "screen (sRGB averaging)", "square": "square dots",
             **{str(r): f"heat, radius {r}" for r in RADII}}
    groups = [(LABELS[m], [f"{m}@{c}" for c in columns]) for m in bitmaps]
    labels = {f"{m}@{c}": names[c] for m in bitmaps for c in columns}
    box = (*DETAIL[sample], DETAIL_SIZE)
    original = detail_crop(reference, box, 3) if detail else outlined_original(sample, reference)
    tiles = {}
    for m, bitmap in bitmaps.items():
        for c in columns:
            if c == "srgb":
                tiles[f"{m}@{c}"] = srgb_average(bitmap, original.size)
                continue
            model = SQUARE if c == "square" else DotModel(radius=float(c))
            tiles[f"{m}@{c}"] = detail_crop(bitmap, box, 3, model) if detail else print_thumbnail(bitmap, model)
    return grouped_sheet((f"{sample} (original)", original), tiles, font_size=24 if detail else 22,
                         groups=groups, labels=labels)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0],
                                     formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    parser.add_argument("--samples", nargs="+", choices=SAMPLES, default=list(SAMPLES))
    parser.add_argument("--distance", type=float, default=30.0, help="Viewing distance in cm")
    parser.add_argument("--cache", type=Path, default=ROOT / "output/samples")
    parser.add_argument("--output", type=Path, help="Write sheets for a few samples to this directory")
    parser.add_argument("--csv", type=Path, help="Write the square-model evaluation to this CSV file")
    args = parser.parse_args()

    print("Apparent L* of flat grey levels dithered with JJN")
    print(f"{'grey':>5}{'target':>8}{'sRGB avg':>10}{'square':>8}" + "".join(f"{'heat ' + str(r):>11}" for r in RADII))
    for g, *cells in flat_grey_table():
        print(f"{g:>5}" + "".join(f"{c:>{w}.1f}" for c, w in zip(cells, (8, 10, 8, 11, 11))))

    methods = {**METHODS, **EXTRA_METHODS}
    rows = []
    for sample in args.samples:
        path = fetch(sample, args.cache)
        print(f"Evaluating {sample}...", flush=True)
        gray = preprocess(path, WIDTH, 0.70, 0.90, 0.35)
        reference = preprocess(path, WIDTH, 1.0, 1.0, 0.0)
        bitmaps = {name: methods[name](gray) for name in SHOWN}
        if args.output and sample in SHEET_SAMPLES:
            args.output.mkdir(parents=True, exist_ok=True)
            for detail, suffix in ((False, "full"), (True, "detail")):
                sheet(sample, reference, bitmaps, detail).save(
                    args.output / f"{sample}-{suffix}.jpg", quality=80, optimize=True)
        for name, bitmap in bitmaps.items():
            e = evaluate(bitmap, reference, SQUARE, distance_cm=args.distance)
            rows.append({"sample": sample, "method": name, **{m: getattr(e, m) for m in METRICS}})

    if args.csv:
        args.csv.parent.mkdir(parents=True, exist_ok=True)
        with args.csv.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]))
            writer.writeheader()
            for row in rows:
                writer.writerow({k: (round(v, 4) if isinstance(v, float) else v) for k, v in row.items()})

    print(f"\nSquare model, mean over {len(args.samples)} samples")
    print(f"{'method':<12}" + "".join(f"{m:>13}" for m in METRICS))
    for name in SHOWN:
        at = [r for r in rows if r["method"] == name]
        print(f"{name:<12}" + "".join(f"{np.mean([r[m] for r in at]):>13.3f}" for m in METRICS))


if __name__ == "__main__":
    main()
