"""XP-80T thermal photo printing prototype.

Tested empirically by the project owner with USB ID 1fc9:2016.
Hardware-dependent functionality is not automatically tested.
"""
import argparse
from pathlib import Path

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter, ImageOps

WIDTH = 576
VID = 0x1FC9
PID = 0x2016

JJN_KERNEL = (
    (1, 0, 7 / 48), (2, 0, 5 / 48),
    (-2, 1, 3 / 48), (-1, 1, 5 / 48), (0, 1, 7 / 48),
    (1, 1, 5 / 48), (2, 1, 3 / 48),
    (-2, 2, 1 / 48), (-1, 2, 3 / 48), (0, 2, 5 / 48),
    (1, 2, 3 / 48), (2, 2, 1 / 48),
)


def preprocess(path: Path, width: int, gamma: float, contrast: float, blur: float) -> Image.Image:
    with Image.open(path) as src:
        rgb = ImageOps.exif_transpose(src).convert("RGB")
    height = max(1, round(rgb.height * width / rgb.width))
    gray = ImageOps.grayscale(rgb.resize((width, height), Image.Resampling.LANCZOS))
    # Exponent below 1 brightens midtones.
    lut = [round(255 * (i / 255) ** gamma) for i in range(256)]
    gray = gray.point(lut)
    gray = ImageEnhance.Contrast(gray).enhance(contrast)
    if blur > 0:
        gray = gray.filter(ImageFilter.GaussianBlur(blur))
    return gray


def error_diffusion(gray: Image.Image, kernel, serpentine: bool = False) -> Image.Image:
    src = np.asarray(gray, dtype=np.float32).copy()
    h, w = src.shape
    output = np.empty((h, w), dtype=np.uint8)
    for y in range(h):
        reverse = serpentine and y % 2 == 1
        indices = range(w - 1, -1, -1) if reverse else range(w)
        direction = -1 if reverse else 1
        for x in indices:
            old = src[y, x]
            new = 255 if old >= 128 else 0
            output[y, x] = new
            err = old - new
            for dx, dy, weight in kernel:
                nx, ny = x + direction * dx, y + dy
                if 0 <= nx < w and 0 <= ny < h:
                    src[ny, nx] += err * weight
    return Image.fromarray(output).convert("1", dither=Image.Dither.NONE)


def dither(gray: Image.Image, method: str) -> Image.Image:
    if method == "jjn":
        return error_diffusion(gray, JJN_KERNEL)
    if method == "floyd":
        return gray.convert("1", dither=Image.Dither.FLOYDSTEINBERG)
    raise ValueError("Unsupported dither method: " + method)


def open_printer():
    from escpos.printer import Usb
    return Usb(VID, PID)


def set_density(printer, level: int):
    """Experimental Xprinter-compatible persistent setting; XP-80T verified locally."""
    if not 1 <= level <= 8:
        raise ValueError("density must be 1..8")
    printer._raw(bytes.fromhex("1F 1B 1F 13 14") + bytes([level]))


def main():
    parser = argparse.ArgumentParser(description="Thermal photo printing prototype")
    commands = parser.add_subparsers(dest="command", required=True)

    render = commands.add_parser("render", help="Generate grayscale and 1-bit preview PNGs")
    render.add_argument("image", type=Path)
    render.add_argument("--output", type=Path, default=Path("output"))
    render.add_argument("--method", choices=["jjn", "floyd"], default="jjn")
    render.add_argument("--width", type=int, default=WIDTH)
    render.add_argument("--gamma", type=float, default=0.70)
    render.add_argument("--contrast", type=float, default=0.90)
    render.add_argument("--blur", type=float, default=0.35)

    send = commands.add_parser("print", help="Send existing 1-bit PNG without redithering")
    send.add_argument("image", type=Path)
    send.add_argument("--density", type=int, choices=range(1, 9), default=None)
    send.add_argument("--cut", action="store_true")

    density = commands.add_parser("density", help="Set persistent printer density (experimental)")
    density.add_argument("level", type=int, choices=range(1, 9))

    args = parser.parse_args()
    if args.command == "render":
        if args.width <= 0 or args.gamma <= 0 or args.contrast <= 0 or args.blur < 0:
            parser.error("width, gamma, contrast must be positive; blur cannot be negative")
        args.output.mkdir(parents=True, exist_ok=True)
        gray = preprocess(args.image, args.width, args.gamma, args.contrast, args.blur)
        gray_path = args.output / "grayscale.png"
        result_path = args.output / (args.method + ".png")
        gray.save(gray_path)
        dither(gray, args.method).save(result_path)
        print(f"Saved {gray_path} and {result_path}; no printing performed")
        return

    if args.command == "print":
        with Image.open(args.image) as src:
            if src.mode != "1":
                parser.error("Expected a 1-bit PNG (mode=1); render first")
            if src.width != WIDTH:
                parser.error(f"XP-80T requires {WIDTH}px wide input")
            bitmap = src.copy()

    printer = open_printer()
    try:
        if args.command == "density":
            set_density(printer, args.level)
            print(f"Transmitted density {args.level}; confirm by actual print")
        else:
            if args.density is not None:
                set_density(printer, args.density)
            printer.image(bitmap, impl="bitImageRaster")
            printer.text("\n\n")
            if args.cut:
                printer.cut()
            print("Image data transmitted; check actual print")
    finally:
        printer.close()


if __name__ == "__main__":
    main()
