#!/usr/bin/env python3
"""Evaluate all dithering methods on a set of sample images.

Sample images are downloaded on first use into a local cache (default
output/samples, ignored by Git) and checked against pinned SHA-256 hashes.
Only the two local samples (NASA astronaut, grey-patch chart) are stored in the
repository. Every sample is public domain or CC0.

For each sample, each method dithers the image after the standard
preprocessing. Each bitmap is evaluated with the heat print model against the
unadjusted original (see thermal_photo_box.evaluate). The script prints:

- per radius, the mean of each metric over the samples, with the range;
- per radius and metric, the method order on each sample, so you can see whether
  a ranking holds across images or depends on one of them.

Ostromoukhov and Zhou-Fang need a local clone of
https://github.com/dalpil/structure-aware-dithering (pass --external REPO).

Example:
    python experiments/benchmark.py --radii 0.55 0.65 --csv docs/benchmark.csv
"""
import argparse
import csv
import hashlib
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from thermal_photo_box.cli import WIDTH, preprocess
from thermal_photo_box.evaluate import evaluate
from thermal_photo_box.simulate import DEFAULT_RADIUS, DotModel

sys.path.insert(0, str(Path(__file__).resolve().parent))
from compare_dither import METHODS, detail_sheet  # noqa: E402
from evaluate_dither import artifact_sheet  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SKIMAGE = "https://raw.githubusercontent.com/scikit-image/scikit-image/ae5a9eba9b0c092214aec7026455d985b4b594c1/src/_skimage2/data/"
COMMONS = "https://upload.wikimedia.org/wikipedia/commons/"

# name: (local path or URL, SHA-256 or None for local files, content, source and licence)
SAMPLES = {
    "astronaut": (ROOT / "docs/sample/astronaut.png", None,
                  "portrait, detailed background", "NASA, public domain (via scikit-image)"),
    "sally-ride": (COMMONS + "0/0c/Sally_Ride_%281984%29.jpg",
                   "ea25b741c25978a84efbd5c0c333c61e59486768178799c7f32b05d07e851cef",
                   "portrait, smooth backdrop", "NASA, public domain (Wikimedia Commons)"),
    "earthrise": (COMMONS + "d/d1/NASA_Earthrise_AS08-14-2383_Apollo_8_1968-12-24.jpg",
                  "765b9ea3bc93cc381b43130712aed92d2bf90f74ea3b4161c8f485bb225fc022",
                  "dark scene, large black area", "NASA / Bill Anders, public domain (Wikimedia Commons)"),
    "rocket": (SKIMAGE + "rocket.jpg",
               "c2dd0de7c538df8d111e479619b129464d0269d0ae5fd18ca91d33a7fdfea95c",
               "sky gradient, smoke", "SpaceX, public domain (via scikit-image)"),
    "coffee": (SKIMAGE + "coffee.png",
               "cc02f8ca188b167c775a7101b5d767d1e71792cf762c33d6fa15a4599b5a8de7",
               "wood grain, white cup, dark saucer", "Rachel Michetti, CC0 (via scikit-image)"),
    "chelsea": (SKIMAGE + "chelsea.png",
                "596aa1e7cb875eb79f437e310381d26b338a81c2da23439704a73c4651e8c4bb",
                "fur texture", "Stefan van der Walt, CC0 (via scikit-image)"),
    "camera": (SKIMAGE + "camera.png",
               "b0793d2adda0fa6ae899c03989482bff9a42d3d5690fc7e3648f2795d730c23a",
               "grass texture, plain sky", "Lav Varshney, CC0 (via scikit-image)"),
    "patches": (ROOT / "docs/sample/patches.png", None,
                "ten uniform grey patches", "synthetic (experiments/make_test_chart.py)"),
}
# Crops of a source image, in source pixels (left, top, right, bottom).
CROPS = {}
# Gallery crop per sample, in 576-dot coordinates (left, top); all crops are DETAIL_SIZE square.
DETAIL = {"astronaut": (190, 50), "sally-ride": (200, 180),
          "earthrise": (262, 236), "rocket": (190, 220), "coffee": (330, 40), "chelsea": (150, 90),
          "camera": (400, 180), "patches": (165, 96)}
DETAIL_SIZE = 128
EXTERNAL = ("ostromoukhov", "zhoufang")
METRICS = ("bias", "tone", "texture", "directional", "periodic")
# Lower is better for every metric; bias is ranked by its absolute value.
FORMAT = {"bias": "{:+.1f}", "tone": "{:.1f}", "texture": "{:.1f}", "directional": "{:.2f}", "periodic": "{:.3f}"}


def fetch(name, cache):
    source, digest, _, _ = SAMPLES[name]
    if name in CROPS:
        path = cache / f"{name}.png"
        if not path.is_file():
            path.parent.mkdir(parents=True, exist_ok=True)
            with Image.open(source) as img:
                img.convert("RGB").crop(CROPS[name]).save(path)
        return path
    if isinstance(source, Path):
        return source
    path = cache / f"{name}{Path(source).suffix}"
    if not path.is_file():
        print(f"Downloading {name}...", flush=True)
        request = urllib.request.Request(source, headers={"User-Agent": "thermal-photo-box-benchmark/0.1"})
        with urllib.request.urlopen(request, timeout=60) as response:
            data = response.read()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != digest:
        raise SystemExit(f"{path}: SHA-256 mismatch ({actual}); delete it to download again")
    return path


def dither_all(gray, external):
    bitmaps = {name: method(gray) for name, method in METHODS.items()}
    if external:
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "gray.png"
            gray.save(src)
            for name in EXTERNAL:
                dst = Path(tmp) / f"{name}.png"
                subprocess.run(["uv", "run", "dither", str(src), str(dst), name], cwd=external,
                               check=True, capture_output=True)
                with Image.open(dst) as img:
                    bitmaps[name] = img.convert("L").point(lambda v: 255 if v >= 128 else 0).convert("1")
    return bitmaps


def overview(references, columns=3, thumb=288):
    """Thumbnails of every sample with its gallery crop outlined."""
    font = ImageFont.load_default(size=20)
    label_h, pad = 28, 10
    cells = []
    for name, ref in references:
        img = ref.convert("RGB")
        left, top = DETAIL[name]
        ImageDraw.Draw(img).rectangle((left, top, left + DETAIL_SIZE, top + DETAIL_SIZE), outline=(230, 30, 30), width=4)
        img.thumbnail((thumb, 10 * thumb))
        cells.append((name, img))
    rows = (len(cells) + columns - 1) // columns
    row_h = [max(img.height for _, img in cells[r * columns:(r + 1) * columns]) for r in range(rows)]
    sheet = Image.new("RGB", (columns * (thumb + pad) + pad, sum(row_h) + rows * (label_h + pad) + pad), "white")
    draw = ImageDraw.Draw(sheet)
    y = pad
    for r in range(rows):
        for c, (name, img) in enumerate(cells[r * columns:(r + 1) * columns]):
            x = pad + c * (thumb + pad)
            draw.text((x, y), name, fill=0, font=font)
            sheet.paste(img, (x, y + label_h))
        y += row_h[r] + label_h + pad
    return sheet


def score(metric, value):
    return abs(value) if metric == "bias" else value


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0],
                                     formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    parser.add_argument("--samples", nargs="+", choices=SAMPLES, default=list(SAMPLES))
    parser.add_argument("--radii", type=float, nargs="+", default=[0.55, 0.65])
    parser.add_argument("--distance", type=float, default=30.0, help="Viewing distance in cm")
    parser.add_argument("--external", type=Path, help="Local structure-aware-dithering clone")
    parser.add_argument("--cache", type=Path, default=ROOT / "output/samples")
    parser.add_argument("--csv", type=Path, help="Write every result to this CSV file")
    parser.add_argument("--artifacts", type=Path, help="Write artifact-map sheets (first radius) to this directory")
    parser.add_argument("--gallery", type=Path,
                        help="Write simulated-print crops of every method per sample, plus overview.jpg, to this directory")
    parser.add_argument("--gallery-radius", type=float, default=DEFAULT_RADIUS["heat"],
                        help="Heat-model radius for the gallery (default: model default)")
    args = parser.parse_args()

    rows = []
    references = []
    for sample in args.samples:
        path = fetch(sample, args.cache)
        print(f"Evaluating {sample}...", flush=True)
        gray = preprocess(path, WIDTH, 0.70, 0.90, 0.35)
        reference = preprocess(path, WIDTH, 1.0, 1.0, 0.0)
        bitmaps = dither_all(gray, args.external)
        references.append((sample, reference))
        if args.gallery:
            args.gallery.mkdir(parents=True, exist_ok=True)
            box = (*DETAIL[sample], DETAIL_SIZE)
            sheet = detail_sheet((f"{sample} (original)", reference), list(bitmaps.items()), box, 3,
                                 columns=4, model=DotModel(radius=args.gallery_radius))
            sheet.save(args.gallery / f"{sample}.jpg", quality=80, optimize=True)
        for n, radius in enumerate(args.radii):
            model = DotModel(radius=radius)
            maps = []
            for method, bitmap in bitmaps.items():
                e = evaluate(bitmap, reference, model, distance_cm=args.distance)
                rows.append({"sample": sample, "radius": radius, "method": method,
                             **{m: getattr(e, m) for m in METRICS}})
                maps.append((method, e.artifact_map))
            if n == 0 and args.artifacts:
                args.artifacts.mkdir(parents=True, exist_ok=True)
                artifact_sheet(maps).save(args.artifacts / f"{sample}.png", optimize=True)

    if args.gallery:
        overview(references).save(args.gallery / "overview.jpg", quality=80, optimize=True)

    if args.csv:
        args.csv.parent.mkdir(parents=True, exist_ok=True)
        with args.csv.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["sample", "radius", "method", *METRICS])
            writer.writeheader()
            for row in rows:
                writer.writerow({k: (round(v, 4) if isinstance(v, float) else v) for k, v in row.items()})
        print(f"Saved {args.csv}")

    methods = list(dict.fromkeys(r["method"] for r in rows))
    for radius in args.radii:
        at = [r for r in rows if r["radius"] == radius]
        print(f"\n## Radius {radius:.2f}: mean over {len(args.samples)} samples (min..max)\n")
        print("| Method | " + " | ".join(METRICS) + " |")
        print("| --- |" + " --- |" * len(METRICS))
        for method in methods:
            cells = []
            for m in METRICS:
                v = np.array([r[m] for r in at if r["method"] == method])
                fmt = FORMAT[m]
                cells.append(f"{fmt.format(v.mean())} ({fmt.format(v.min())}..{fmt.format(v.max())})")
            print(f"| {method} | " + " | ".join(cells) + " |")
        print(f"\n## Radius {radius:.2f}: method order per sample, best first (bias by |bias|)\n")
        for m in METRICS:
            print(f"{m}:")
            for sample in args.samples:
                ranked = sorted((r for r in at if r["sample"] == sample), key=lambda r: score(m, r[m]))
                print(f"  {sample:<15}" + " ".join(r["method"] for r in ranked))


if __name__ == "__main__":
    main()
