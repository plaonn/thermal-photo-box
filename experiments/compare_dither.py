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
from PIL import Image, ImageDraw, ImageFont, ImageOps

from thermal_photo_box.cli import JJN_KERNEL, WIDTH, error_diffusion, open_printer, preprocess, set_density
from thermal_photo_box.simulate import DEFAULT_RADIUS, DotModel, simulate

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


LABELS = {
    "grayscale": "Grayscale input",
    "floyd": "Floyd-Steinberg",
    "serpentine": "Serpentine Floyd-Steinberg",
    "jjn": "Jarvis-Judice-Ninke",
    "atkinson": "Atkinson",
    "bayer": "Bayer 8x8",
    "blue": "FFT threshold mask",
    "ostromoukhov": "Ostromoukhov",
    "zhoufang": "Zhou-Fang",
}


def detail_crop(image, box, scale, model=None):
    """Square crop `box` = (left, top, size), enlarged `scale` times.

    Bitmaps are rendered by the dot simulator when `model` is given; otherwise,
    and for greyscale images, the crop is enlarged with nearest-neighbour scaling.
    """
    left, top, size = box
    if model is not None and image.mode == "1":
        # Simulate with one dot of margin so edge dots see their neighbours.
        padded = ImageOps.expand(image, border=2, fill=1)  # white margin outside the image
        crop = padded.crop((left, top, left + size + 4, top + size + 4))
        return simulate(crop, scale, model).crop((2 * scale, 2 * scale, (size + 2) * scale, (size + 2) * scale))
    crop = image.convert("L").crop((left, top, left + size, top + size))
    return crop.resize((size * scale, size * scale), Image.Resampling.NEAREST)


def detail_sheet(source, images, box, scale, columns=3, model=None):
    """Source crop on the first row, then dithered crops in a grid.

    Crops are enlarged with nearest-neighbour scaling so individual dots stay visible.
    With `model`, each dithered crop is instead rendered by the dot simulator.
    """
    left, top, size = box
    cell = size * scale
    font = ImageFont.load_default(size=max(16, cell // 12))
    label_h = font.size + font.size // 2
    pad = font.size
    rows = 1 + (len(images) + columns - 1) // columns
    width = columns * (cell + pad) + pad
    sheet = Image.new("L", (width, rows * (cell + label_h + pad) + pad), 255)
    draw = ImageDraw.Draw(sheet)

    def place(name, image, x, y):
        sheet.paste(detail_crop(image, box, scale, model), (x, y + label_h))
        draw.text((x, y), LABELS.get(name, name), fill=0, font=font)

    place(source[0], source[1], (width - cell) // 2, pad)
    for i, (name, image) in enumerate(images):
        x = pad + (i % columns) * (cell + pad)
        y = pad + (1 + i // columns) * (cell + label_h + pad)
        place(name, image, x, y)
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
    parser.add_argument("--simulate", action="store_true",
                        help="With --detail, also write detail-simulated.png (heat model) and detail-simulated-overlap.png")
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
        detail_sheet(("grayscale", gray), results, args.detail, args.detail_scale).save(path, optimize=True)
        print(f"  Saved: {path}")

    if args.detail and args.simulate:
        for suffix, model in (("", DotModel()), ("-overlap", DotModel(radius=DEFAULT_RADIUS["overlap"], kind="overlap"))):
            path = args.output / f"detail-simulated{suffix}.png"
            detail_sheet(("grayscale", gray), results, args.detail, args.detail_scale, model=model).save(path, optimize=True)
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
