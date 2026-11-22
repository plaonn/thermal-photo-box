#!/usr/bin/env python3
"""Render (and optionally print) a dithering comparison for 576-dot printers.

Reproduces the XP-80T comparison in docs/experiments-xp80t.md:
Floyd-Steinberg, serpentine Floyd-Steinberg, Jarvis-Judice-Ninke, Atkinson,
Bayer 8x8 and an FFT high-pass threshold-mask approximation of blue noise.

Preprocessing is shared with the `thermal-photo-box render` command.
Printing is opt-in (--print); a density command is sent only with --density.
"""
import argparse
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from thermal_photo_box.cli import JJN_KERNEL, WIDTH, error_diffusion, open_printer, preprocess, set_density

FS_KERNEL = ((1, 0, 7 / 16), (-1, 1, 3 / 16), (0, 1, 5 / 16), (1, 1, 1 / 16))


def floyd(gray):
    return gray.convert("1", dither=Image.Dither.FLOYDSTEINBERG)


def serpentine(gray):
    return error_diffusion(gray, FS_KERNEL, serpentine=True)


def jjn(gray):
    return error_diffusion(gray, JJN_KERNEL)


def atkinson(gray):
    src = np.asarray(gray, dtype=np.float32)
    h, w = src.shape
    buf = np.pad(src, ((0, 2), (1, 2)), mode="edge")
    out = np.empty((h, w), dtype=np.uint8)
    for y in range(h):
        for x in range(w):
            v = buf[y, x + 1]
            q = 255.0 if v >= 128 else 0.0
            out[y, x] = int(q)
            err = (v - q) / 8.0  # distributes 6/8 of the error
            buf[y, x + 2] += err
            buf[y, x + 3] += err
            buf[y + 1, x] += err
            buf[y + 1, x + 1] += err
            buf[y + 1, x + 2] += err
            buf[y + 2, x + 1] += err
    return Image.fromarray(out).convert("1", dither=Image.Dither.NONE)


def bayer(gray):
    m = np.array([[0]], dtype=np.int32)
    for _ in range(3):
        m = np.block([[4 * m, 4 * m + 2], [4 * m + 3, 4 * m + 1]])
    src = np.asarray(gray, dtype=np.uint8)
    h, w = src.shape
    threshold = np.tile((m + 0.5) * (255.0 / 64), ((h + 7) // 8, (w + 7) // 8))[:h, :w]
    return Image.fromarray(np.where(src < threshold, 0, 255).astype(np.uint8)).convert("1", dither=Image.Dither.NONE)


def blue_noise_mask(size=128, seed=42):
    """High-pass-shaped random threshold mask; not an optimized void-and-cluster mask."""
    rng = np.random.default_rng(seed)
    noise = rng.standard_normal((size, size))
    fy = np.fft.fftfreq(size)[:, None]
    fx = np.fft.fftfreq(size)[None, :]
    radius = np.sqrt(fx * fx + fy * fy)
    weight = (radius / (radius + 0.12)) ** 1.5
    weight[0, 0] = 0
    filtered = np.fft.ifft2(np.fft.fft2(noise) * weight).real
    order = np.argsort(filtered.ravel())
    ranks = np.empty(size * size, dtype=np.float64)
    ranks[order] = np.arange(size * size)
    return (ranks.reshape(size, size) + 0.5) * 255.0 / (size * size)


def blue(gray):
    src = np.asarray(gray, dtype=np.uint8)
    h, w = src.shape
    mask = blue_noise_mask()
    s = mask.shape[0]
    threshold = np.tile(mask, ((h + s - 1) // s, (w + s - 1) // s))[:h, :w]
    return Image.fromarray(np.where(src < threshold, 0, 255).astype(np.uint8)).convert("1", dither=Image.Dither.NONE)


METHODS = {
    "floyd": floyd,
    "serpentine": serpentine,
    "jjn": jjn,
    "atkinson": atkinson,
    "bayer": bayer,
    "blue": blue,
}


def detail_sheet(images, box, scale, columns=3):
    """Nearest-neighbour enlarged crops so individual dots stay visible on screen."""
    left, top, size = box
    label_h, pad = 16, 8
    cell = size * scale
    rows = (len(images) + columns - 1) // columns
    sheet = Image.new("L", (columns * (cell + pad) + pad, rows * (cell + label_h + pad) + pad), 255)
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()
    for i, (name, image) in enumerate(images):
        crop = image.convert("L").crop((left, top, left + size, top + size))
        crop = crop.resize((cell, cell), Image.Resampling.NEAREST)
        x = pad + (i % columns) * (cell + pad)
        y = pad + (i // columns) * (cell + label_h + pad)
        draw.text((x, y), name, fill=0, font=font)
        sheet.paste(crop, (x, y + label_h))
    return sheet


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("image", type=Path, help="Source photo")
    parser.add_argument("--methods", nargs="+", choices=METHODS, default=list(METHODS))
    parser.add_argument("--output", type=Path, default=Path("output/dither-comparison"))
    parser.add_argument(
        "--detail", type=int, nargs=3, metavar=("LEFT", "TOP", "SIZE"),
        help="Also write detail.png with enlarged square crops at this position (576-px coordinates)",
    )
    parser.add_argument("--detail-scale", type=int, default=3)
    parser.add_argument("--print", dest="do_print", action="store_true", help="Print results over USB")
    parser.add_argument("--density", type=int, choices=range(1, 9), help="Send the persistent density command first")
    args = parser.parse_args()

    args.output.mkdir(parents=True, exist_ok=True)
    gray = preprocess(args.image, WIDTH, 0.70, 0.90, 0.35)
    gray.save(args.output / "00-grayscale.png")

    results = []
    for name in args.methods:
        print(f"Processing {name}...", flush=True)
        image = METHODS[name](gray)
        path = args.output / f"{name}.png"
        image.save(path, optimize=True)
        results.append((name, image))
        print(f"  Saved: {path}")

    if args.detail:
        path = args.output / "detail.png"
        detail_sheet([("grayscale", gray)] + results, args.detail, args.detail_scale).save(path, optimize=True)
        print(f"  Saved: {path}")

    if not args.do_print:
        print("Previews saved; no printing performed. Add --print to print.")
        return

    printer = open_printer()
    try:
        if args.density is not None:
            set_density(printer, args.density)
        for name, image in results:
            print(f"Printing {name}...", flush=True)
            printer.text(f"\n--- {name.upper()} ---\n")
            printer.image(image, impl="bitImageRaster")
            printer.text("\n\n")
        printer.cut()
        print("Image data transmitted; check actual prints")
    finally:
        printer.close()


if __name__ == "__main__":
    main()
