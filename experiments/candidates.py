#!/usr/bin/env python3
"""Compare the print candidates (JJN, Atkinson, with and without threshold noise) across dot radii.

The radius of the heat print model is not calibrated, and the tone ranking of
the methods depends on it. This script renders each candidate at several radii
so you can see which differences hold whatever the real dot size is.

For each sample it writes two sheets, one row per method and one column per
radius: SAMPLE-full.jpg (whole image) and SAMPLE-detail.jpg (enlarged crop).
It also evaluates every candidate at every radius (see thermal_photo_box.evaluate)
and prints the means over the samples.

Samples are the same as in benchmark.py and are downloaded on first use.

Example:
    python experiments/candidates.py --output docs/images/candidates --csv docs/candidates.csv
"""
import argparse
import csv
import sys
from pathlib import Path

import numpy as np

from thermal_photo_box.cli import WIDTH, preprocess
from thermal_photo_box.evaluate import evaluate
from thermal_photo_box.simulate import DotModel

sys.path.insert(0, str(Path(__file__).resolve().parent))
from benchmark import (DETAIL, DETAIL_SIZE, METRICS, ROOT, SAMPLES, fetch, grouped_sheet,  # noqa: E402
                       outlined_original, print_thumbnail)
from compare_dither import LABELS, METHODS, detail_crop  # noqa: E402
from extra_dither import EXTRA_METHODS  # noqa: E402

CANDIDATES = ("jjn", "jjn-tm32", "jjn-tm64", "atkinson", "atkinson-tm32", "atkinson-tm64")
RADII = (0.45, 0.55, 0.65, 0.75)


def sheet(sample, reference, bitmaps, radii, detail):
    groups = [(LABELS[name], [f"{name}@{r}" for r in radii]) for name in bitmaps]
    labels = {f"{name}@{r}": f"radius {r}" for name in bitmaps for r in radii}
    tiles = {}
    box = (*DETAIL[sample], DETAIL_SIZE)
    for name, bitmap in bitmaps.items():
        for r in radii:
            model = DotModel(radius=r)
            tiles[f"{name}@{r}"] = detail_crop(bitmap, box, 3, model) if detail else print_thumbnail(bitmap, model)
    original = detail_crop(reference, box, 3) if detail else outlined_original(sample, reference)
    return grouped_sheet((f"{sample} (original)", original), tiles, font_size=24 if detail else 22,
                         groups=groups, labels=labels)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0],
                                     formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    parser.add_argument("--samples", nargs="+", choices=SAMPLES, default=list(SAMPLES))
    parser.add_argument("--radii", type=float, nargs="+", default=list(RADII))
    parser.add_argument("--distance", type=float, default=30.0, help="Viewing distance in cm")
    parser.add_argument("--cache", type=Path, default=ROOT / "output/samples")
    parser.add_argument("--output", type=Path, help="Write the sheets to this directory")
    parser.add_argument("--csv", type=Path, help="Write every result to this CSV file")
    args = parser.parse_args()

    methods = {**METHODS, **EXTRA_METHODS}
    rows = []
    for sample in args.samples:
        path = fetch(sample, args.cache)
        print(f"Evaluating {sample}...", flush=True)
        gray = preprocess(path, WIDTH, 0.70, 0.90, 0.35)
        reference = preprocess(path, WIDTH, 1.0, 1.0, 0.0)
        bitmaps = {name: methods[name](gray) for name in CANDIDATES}
        if args.output:
            args.output.mkdir(parents=True, exist_ok=True)
            for detail, suffix in ((False, "full"), (True, "detail")):
                sheet(sample, reference, bitmaps, args.radii, detail).save(
                    args.output / f"{sample}-{suffix}.jpg", quality=80, optimize=True)
        for radius in args.radii:
            for name, bitmap in bitmaps.items():
                e = evaluate(bitmap, reference, DotModel(radius=radius), distance_cm=args.distance)
                rows.append({"sample": sample, "radius": radius, "method": name,
                             **{m: getattr(e, m) for m in METRICS}})

    if args.csv:
        args.csv.parent.mkdir(parents=True, exist_ok=True)
        with args.csv.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]))
            writer.writeheader()
            for row in rows:
                writer.writerow({k: (round(v, 4) if isinstance(v, float) else v) for k, v in row.items()})

    print(f"\nMean over {len(args.samples)} samples (bias: mean, others: mean)")
    print(f"{'method':<16}{'radius':>7}" + "".join(f"{m:>13}" for m in METRICS))
    for name in CANDIDATES:
        for radius in args.radii:
            at = [r for r in rows if r["method"] == name and r["radius"] == radius]
            print(f"{name:<16}{radius:>7}" + "".join(f"{np.mean([r[m] for r in at]):>13.3f}" for m in METRICS))


if __name__ == "__main__":
    main()
