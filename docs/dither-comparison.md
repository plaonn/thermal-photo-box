# Dithering comparison (on-screen reference)

These images show what each dithering method does to the same photo after the preprocessing used in the [XP-80T experiment](experiments-xp80t.md). They are **screen previews, not scans of printed receipts**. On paper, dot gain and printer density change the result considerably. In the XP-80T tests the preview that looked best did not always print best. The ranking in the experiment log comes from physical prints of a different (private) portrait.

## Sample image

[`sample/astronaut.png`](sample/astronaut.png): astronaut Eileen Collins, from the NASA Great Images collection (<https://flic.kr/p/r9qvLn>). Released into the public domain with no known copyright restrictions. It was taken from the [scikit-image](https://github.com/scikit-image/scikit-image) sample data. Using it does not imply endorsement by NASA or by the person shown.

The source is 512 px wide and is upscaled to the 576-dot print width before preprocessing.

## Detail view

The crop below is 160×160 dots, enlarged 3× with nearest-neighbour scaling so individual dots stay visible. At normal size, the browser's downscaling blurs dither patterns and makes them hard to compare.

![Enlarged crops of each dithering method](images/astronaut/detail.png)

## Full-width results (576 dots)

View each file at 100% zoom. Each one is the exact 1-bit bitmap that would be sent to the printer.

The two right-hand columns come from different sources:

- **This sample (screen preview):** what the previews above show on the NASA sample. Written when this page was created.
- **XP-80T experiment log:** the original observations on a private portrait, copied from [experiments-xp80t.md](experiments-xp80t.md#compared-algorithms). They mix screen previews and physical prints, as recorded there.

| Method | File | This sample (screen preview) | XP-80T experiment log |
| --- | --- | --- | --- |
| Grayscale (input) | [00-grayscale.png](images/astronaut/00-grayscale.png) | After resize, gamma 0.70, contrast 0.90, blur 0.35 px | Same preprocessing |
| Floyd–Steinberg (Pillow) | [floyd.png](images/astronaut/floyd.png) | Fine detail, with directional worm patterns | Detail preserved; conspicuous texture/diagonal patterns on paper |
| Serpentine Floyd–Steinberg | [serpentine.png](images/astronaut/serpentine.png) | Alternating scan direction changes the texture | Different but still noticeable texture |
| Jarvis–Judice–Ninke | [jjn.png](images/astronaut/jjn.png) | Wider error spread, smoother tones | **Best-looking physical print in these comparisons** |
| Atkinson | [atkinson.png](images/astronaut/atkinson.png) | Spreads only 6/8 of the error, so highlights wash out and contrast goes up | Paler, lost some dark detail |
| Bayer 8×8 | [bayer.png](images/astronaut/bayer.png) | Regular cross-hatch grid | Regular grid was conspicuous |
| FFT high-pass threshold mask | [blue.png](images/astronaut/blue.png) | Rough blue-noise approximation; noisy | Poor photographic preview; not a faithful optimized blue-noise algorithm |
| Ostromoukhov | not rendered | — | Softer/less defined when actually printed |
| Zhou–Fang | not rendered | — | Promising PNG preview, but JJN preferred on paper |

Ostromoukhov and Zhou–Fang need an external implementation, so this page has no images for them. See below.

## Simulated print (uncalibrated)

On paper a thermal dot is not a square pixel. It is a roughly round or elliptical spot, usually larger than the dot pitch, and neighbouring spots merge (dot gain). `thermal-photo-box simulate` renders a 1-bit image with that model:

- Each printed dot becomes an anti-aliased ellipse. Its horizontal radius is `--radius` dot pitches, and it is `--aspect` times taller in the paper-feed direction.
- Overlapping dots merge, the edges are softened slightly, and the paper and black are grey levels (245 and 35) rather than pure white and black.
- Defaults: radius 0.75, aspect 1.15. **These are guesses, not measurements from the XP-80T.** Heat build-up when the same element fires repeatedly is not modelled.

The same crops as above, rendered with the default model:

![Simulated print of each dithering method](images/astronaut/detail-simulated.png)

```bash
thermal-photo-box simulate docs/images/astronaut/jjn.png --scale 8 --radius 0.75 --aspect 1.15
```

### Does the model reproduce the XP-80T ranking?

`experiments/simulate_sweep.py` simulates each bitmap for a range of dot radii and compares it with the grayscale target. Both are viewed through a 1.5-dot Gaussian low-pass, as a crude stand-in for viewing distance. It reports two numbers:

- **bias:** mean simulated minus target, in grey levels. Negative means darker.
- **structure:** spread of the remaining difference. Lower is closer to the target.

The NASA sample gave these results. Ostromoukhov and Zhou–Fang were rendered with a temporary clone of the external implementation; the PNGs are not stored here.

| radius | Floyd–Steinberg | Serpentine FS | JJN | Atkinson | Bayer 8×8 | FFT mask | Ostromoukhov | Zhou–Fang |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0.50 | +11.9 / **8.2** | +11.8 / 8.4 | +12.1 / 8.8 | +14.7 / 5.3 | +11.4 / 9.1 | +12.0 / 13.5 | +11.9 / 9.1 | +10.2 / 10.0 |
| 0.60 | −14.6 / 7.4 | −14.8 / 7.7 | −12.2 / 7.5 | −7.3 / 12.6 | −16.6 / 9.9 | −11.9 / 14.0 | −13.9 / **7.0** | −16.0 / 7.5 |
| 0.71 | −37.4 / 15.7 | −37.8 / 16.0 | −32.0 / **13.5** | −24.0 / 18.0 | −40.9 / 19.2 | −30.7 / 18.4 | −36.0 / 14.4 | −38.4 / 14.5 |
| 0.80 | −54.7 / 22.5 | −55.1 / 22.8 | −47.1 / **19.2** | −37.1 / 23.3 | −58.7 / 25.9 | −45.1 / 23.0 | −53.0 / 21.0 | −55.8 / 21.3 |
| 0.90 | −69.9 / 29.4 | −70.2 / 29.5 | −60.7 / **24.9** | −49.7 / 28.6 | −73.0 / 31.6 | −58.2 / 27.9 | −67.9 / 27.8 | −71.6 / 28.8 |
| 1.00 | −85.0 / 37.9 | −84.8 / 37.7 | −74.8 / **32.0** | −62.9 / 35.1 | −85.2 / 38.2 | −70.8 / 33.4 | −83.0 / 36.1 | −86.9 / 37.6 |

Each cell is bias / structure. The lowest structure error per row is in bold, ignoring Atkinson in the 0.50 row (see below).

Reading:

- With little or no dot gain (radius ≤ 0.6), Floyd–Steinberg, Ostromoukhov and Zhou–Fang are as good as or better than JJN. This matches the screen previews, where these methods looked promising.
- Once dots overlap (radius ≥ 0.71), JJN has the lowest structure error, and it darkens less than Floyd–Steinberg, Ostromoukhov and Zhou–Fang. Its coarser, connected patterns expose less dot edge to spread. This matches the XP-80T paper result, where JJN was preferred over all three.
- Every method prints much darker than the target once dots overlap. The gamma 0.70 brightening in the preprocessing can be read as a manual compensation for this.
- Atkinson darkens least because it discards a quarter of the error. Its structure error is not the lowest, and at radius 0.50 it is low only because it leaves highlights blank. That is consistent with the log's "paler, lost some dark detail".

Limits: one sample image, an uncalibrated radius, and a crude metric. Bias and structure are not independent, because darkening compresses contrast. The agreement is a sign that the model points the right way, not a validation. The next step would be to calibrate radius and aspect against a printed test chart.

## Reproduce

```bash
pip install -e .
python experiments/compare_dither.py docs/sample/astronaut.png \
  --output docs/images/astronaut --detail 180 60 160 --simulate
cd docs/images/astronaut && python ../../../experiments/simulate_sweep.py 00-grayscale.png \
  floyd.png serpentine.png jjn.png atkinson.png bayer.png blue.png
```

To print the same set on a connected XP-80T, add `--print`. Add `--density N` only if you accept that the experimental density command may change persistent printer settings (see the README caution).

`experiments/compare_structure_aware.py` compares JJN with Ostromoukhov and Zhou–Fang through a local clone of [dalpil/structure-aware-dithering](https://github.com/dalpil/structure-aware-dithering), which is not vendored here:

```bash
python experiments/compare_structure_aware.py --repo /path/to/structure-aware-dithering \
  --input docs/images/astronaut --output output/structure-aware
```
