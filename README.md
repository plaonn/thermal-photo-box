# thermal-photo-box

Photo printing experiments for **80 mm ESC/POS thermal receipt printers**, initially tested on **Xprinter XP-80T** (USB `1fc9:2016`, 203 dpi).

This repository preserves empirical findings and a small, runnable Python prototype. It is **not** a calibrated image-quality benchmark or a universal printer driver.

## Quick start (macOS)

Connect the XP-80T over USB and power it on. On Apple Silicon macOS, `system_profiler SPUSBHostDataType` showed the device as **USB Printer Port**; a `/dev/cu.usb*` node is not required.

```bash
brew install libusb
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

Generate **preview files only** from your own JPEG/PNG (no printer access):

```bash
thermal-photo-box render ~/Pictures/test.jpg --method jjn --output output
```

This creates `output/grayscale.png` and `output/jjn.png`. The rendering defaults match the experiment: width 576 px, gamma 0.70, contrast 0.90, Gaussian blur 0.35 px.

Print an existing **1-bit, 576-pixel-wide** image without re-dithering:

```bash
thermal-photo-box print output/jjn.png --density 4 --cut
```

Set density independently:

```bash
thermal-photo-box density 4
```

**Hardware caution:** The experimental `1F 1B 1F 13 14 nn` density command had an observable effect on the tested XP-80T and appeared to survive restart. It **may modify persistent device settings**. Do not assume support on other devices or firmware. The factory default was not established. Omitting `--density` during print avoids issuing a density command.

## Findings

On the tested portrait and paper, **Jarvis–Judice–Ninke (JJN)** with density **4** was preferred over Floyd–Steinberg, serpentine Floyd–Steinberg, Ostromoukhov and Zhou–Fang. This is a subjective, image-specific physical-print observation; the more promising preview did not always produce the better printed result.

See [XP-80T experiment log](docs/experiments-xp80t.md) for the device parameters, density commands, settings, alternatives tested and limitations.

## Project scope

- Image preprocessing and binary raster generation
- ESC/POS printing of precomputed image rasters
- Empirical printer-density experiments and reproducible comparisons
- Additional printer models and processing algorithms may be added later; they are not claimed as supported now

External reference implementations (e.g. [dalpil/structure-aware-dithering](https://github.com/dalpil/structure-aware-dithering)) are **not** included. Private test portraits, USB serial numbers and photos of identifiable people are not included.

## License

MIT, for the code and text in this repository. Third-party libraries and external reference implementations have their own licenses.
