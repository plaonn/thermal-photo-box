# XP-80T experiment log (2026-11-01)

These are observations from one user's hardware and sample portrait, not universal printer benchmarks.

## Hardware and connection

- Model: Xprinter XP-80T, direct thermal, 203 dpi, 80 mm roll.
- Printable width used: **576 dots** (approx. 72 mm).
- USB vendor/product: **1FC9:2016**, macOS USB descriptor: **USB Printer Port**.
- Firmware reported on the factory test receipt: **7.010PR6G**.
- macOS recognized the device under `system_profiler SPUSBHostDataType`, not necessarily `SPUSBDataType`.
- On macOS, direct USB printing with `python-escpos` worked, avoiding fixed-page print-driver scaling.

## Density control

- `GS | n` / `1D 7C nn` with values 0, 4, 8 showed **no visible difference** in this device's raster prints.
- Alternative experimental command: `1F 1B 1F 13 14 nn` with `nn` in 1–8.
- Visually distinct printed results at levels 1 versus 8; intermediate levels 3, 4 and 6 were compared.
- Level 1 appeared unchanged after a printer power cycle, suggesting the setting persists; the exact persistence mechanism was not independently established.
- Level **4** was selected as a starting point for photographic testing (personal preference on the tested image). Level 6 looked comparatively dark; level 3 comparatively pale.
- **Caution:** The second command may alter persistent device settings. Its status outside the tested XP-80T firmware is unknown. Reversal in the tests was performed by selecting another level, e.g. 4; factory default was not verified.

## Preprocessing used

- Resize proportionally to 576 pixels wide.
- Convert to grayscale.
- Gamma exponent **0.70** (brightens midtones).
- Contrast multiplier **0.90**.
- Gaussian blur radius **0.35 px**.
- Dither to 1-bit PNG; send the bitmap unchanged using ESC/POS raster image output.

## Compared algorithms

| Method | Observation on the tested portrait |
| --- | --- |
| Floyd–Steinberg (Pillow) | Detail preserved; conspicuous texture/diagonal patterns on paper |
| Serpentine Floyd–Steinberg | Different but still noticeable texture |
| Atkinson | Paler, lost some dark detail |
| Bayer 8×8 | Regular grid was conspicuous |
| FFT high-pass threshold-mask approximation | Poor photographic preview; **not** a faithful optimized blue-noise algorithm |
| Jarvis–Judice–Ninke (JJN) | Best-looking physical print in these comparisons |
| Ostromoukhov (third-party implementation) | Softer/less defined when actually printed |
| Zhou–Fang (third-party implementation) | Promising PNG preview, but JJN preferred on paper |

The two last methods were tested using the third-party `dalpil/structure-aware-dithering` project. The original implementation is **not vendored** here. Check its license and methodology before reuse.

## Limits / next steps

- The visual ranking is specific to the image, paper and printer used.
- No repeatable objective image-quality metric or calibrated thermal-dot model was measured.
- Future experiments may compare JJN with local contrast (e.g., low-strength CLAHE) and multiple test images.
- Do not publish the private portrait, printer serial number or photographs of people without permission.

## References

- [Xprinter XP-80T product/support](https://www.xprintertech.com/pos/xp-80t)
- [Structure-aware dithering project](https://github.com/dalpil/structure-aware-dithering)
