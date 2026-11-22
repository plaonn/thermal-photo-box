#!/usr/bin/env python3
"""Compare JJN with Ostromoukhov and Zhou-Fang from an external implementation.

Requires a local clone of https://github.com/dalpil/structure-aware-dithering
(not vendored here; check its license before reuse) and `uv`. Inputs are the
00-grayscale.png and jjn.png written by compare_dither.py.
"""
import argparse
import shutil
import subprocess
from pathlib import Path

from PIL import Image

from thermal_photo_box.cli import WIDTH, open_printer, set_density

METHODS = ("jjn", "ostromoukhov", "zhoufang")


def run_external(repo, source, destination, method):
    subprocess.run(["uv", "run", "dither", str(source), str(destination), method], cwd=repo, check=True)


def load_binary(path):
    with Image.open(path) as source:
        gray = source.convert("L")
    if gray.width != WIDTH:
        raise ValueError(f"{path}: expected {WIDTH}px, got {gray.width}px")
    if not set(gray.getdata()).issubset({0, 255}):
        raise ValueError(f"{path}: not a binary image")
    return gray.convert("1", dither=Image.Dither.NONE)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", type=Path, required=True, help="Local structure-aware-dithering clone")
    parser.add_argument("--input", type=Path, default=Path("output/dither-comparison"),
                        help="Directory containing 00-grayscale.png and jjn.png")
    parser.add_argument("--output", type=Path, default=Path("output/structure-aware"))
    parser.add_argument("--methods", nargs="+", choices=METHODS, default=list(METHODS))
    parser.add_argument("--print", dest="do_print", action="store_true", help="Print results over USB")
    parser.add_argument("--density", type=int, choices=range(1, 9), help="Send the persistent density command first")
    args = parser.parse_args()

    repo = args.repo.expanduser().resolve()
    gray_path = (args.input / "00-grayscale.png").resolve()
    jjn_path = (args.input / "jjn.png").resolve()
    output = args.output.expanduser().resolve()
    if not repo.is_dir():
        parser.error(f"Repository not found: {repo}")
    if not gray_path.is_file():
        parser.error(f"Grayscale input not found: {gray_path}; run compare_dither.py first")
    output.mkdir(parents=True, exist_ok=True)

    results = []
    for method in args.methods:
        path = output / f"{method}.png"
        if method == "jjn":
            if not jjn_path.is_file():
                parser.error(f"JJN file not found: {jjn_path}")
            shutil.copyfile(jjn_path, path)
        else:
            print(f"Processing {method}...", flush=True)
            run_external(repo, gray_path, path, method)
        results.append((method, load_binary(path)))
        print(f"  Saved: {path}")

    if not args.do_print:
        print("Files generated; no printing performed. Add --print to print.")
        return

    printer = open_printer()
    try:
        if args.density is not None:
            set_density(printer, args.density)
        for method, image in results:
            print(f"Printing {method}...", flush=True)
            printer.text(f"\n--- {method.upper()} ---\n")
            printer.image(image, impl="bitImageRaster")
            printer.text("\n\n")
        printer.cut()
        print("Image data transmitted; check actual prints")
    finally:
        printer.close()


if __name__ == "__main__":
    main()
