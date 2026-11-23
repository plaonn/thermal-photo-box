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

On paper a thermal dot is not a square pixel. `thermal-photo-box simulate` renders a 1-bit image at higher resolution with one of two dot models:

- **`heat` (default):** each fired element deposits a Gaussian heat spot on the paper. Spots from neighbouring dots **add up**, and the paper darkens along a soft threshold of the summed heat. An isolated dot therefore stays small, while the heat tails of adjacent dots fill the gaps between them. This stands in for heat spreading sideways in the paper. Defaults: isolated-dot radius 0.55, threshold 0.4, softness 0.08.
- **`overlap`:** each dot is a hard-edged ellipse and overlapping dots merge (the classic circular dot-overlap model). Default radius 0.75.

In both models the dot is `--aspect` (default 1.15) times taller in the paper-feed direction. Paper and black are grey levels (245 and 35) rather than pure white and black. **All parameters are guesses, not measurements from the XP-80T.** Heat build-up in the print head over successive lines is not modelled.

How the two models treat regular patterns (fraction of area darkened):

| Pattern | heat (r 0.55) | overlap (r 0.75) |
| --- | --- | --- |
| 25%: isolated dots on a 2-dot grid | 0.30 | 0.51 |
| 50%: checkerboard | 0.80 | 0.92 |

The heat model keeps isolated dots near their nominal size but darkens clustered areas strongly. The overlap model enlarges every dot equally.

The same crops as above, rendered with the heat model:

![Simulated print of each dithering method, heat model](images/astronaut/detail-simulated.png)

The overlap model is in [detail-simulated-overlap.png](images/astronaut/detail-simulated-overlap.png).

```bash
thermal-photo-box simulate docs/images/astronaut/jjn.png --scale 8            # heat model
thermal-photo-box simulate docs/images/astronaut/jjn.png --model overlap
```

### Evaluating the simulated prints

`experiments/evaluate_dither.py` compares each simulated print with the **unadjusted original**: the source resized and converted to grey, with no gamma, contrast or blur adjustment. The question is how close the whole pipeline gets to the photo, including the preprocessing that is meant to compensate for print darkening. The steps (code in `src/thermal_photo_box/evaluate.py`):

1. Simulate the print and average each dot cell in **linear reflectance**. Paper and ink are mixed as light, not as encoded grey values.
2. Map the original's lightness into the printable range between ink and paper.
3. Filter both images with the [S-CIELAB](https://doi.org/10.1889/1.1985127) luminance contrast-sensitivity filter for a 30 cm viewing distance at 203 dpi (about 42 dots per degree), then convert to CIE L\*. The difference ΔL\* contains only what the eye can resolve at that distance.
4. Split ΔL\* into a smooth **tone** part (Gaussian, σ = 0.25°) and the remaining **texture** part.
5. In **flat regions of the original** only, measure two kinds of structure that the photo does not contain and that dithering therefore introduced:
   - **directional:** energy-weighted orientation coherence of the texture (structure tensor, 3-dot window), from 0 to 1. Worms and diagonal lines score high. Isotropic grain scores about 0.13–0.17.
   - **periodic:** share of the texture's power in the strongest 0.1% of spatial frequencies. Grids score high. Isotropic grain scores about 0.01.

| Column | Meaning |
| --- | --- |
| bias | mean ΔL\*; negative = darker than the original |
| tone | local tone error (std of the smooth part, ΔL\*) |
| texture | visible graininess (RMS of the fine part, ΔL\*) |
| directional | aligned artifacts in flat areas (0–1) |
| periodic | regular artifacts in flat areas (0–1) |

In addition to the photo, a synthetic [chart of ten uniform grey patches](sample/patches.png) is used. Artifacts show up most clearly on uniform areas.

#### Results (heat model; each cell is radius 0.55 / 0.65)

NASA sample:

| Method | bias | tone | texture | directional | periodic |
| --- | --- | --- | --- | --- | --- |
| Floyd–Steinberg | +9.9 / −3.0 | 3.1 / 4.8 | 4.7 / 6.1 | 0.27 / 0.31 | 0.078 / 0.092 |
| Serpentine FS | +9.8 / −3.3 | 3.1 / 4.8 | 4.8 / 6.5 | 0.15 / 0.33 | 0.080 / 0.087 |
| JJN | +11.4 / +0.7 | 4.6 / **2.2** | 6.2 / 6.3 | 0.22 / 0.31 | 0.103 / **0.027** |
| Atkinson | +11.2 / +2.5 | 5.1 / 5.4 | 5.0 / 6.0 | 0.29 / 0.30 | 0.147 / 0.057 |
| Bayer 8×8 | +8.5 / −6.0 | 2.4 / 7.0 | 5.4 / 9.0 | 0.05 / 0.21 | 0.213 / 0.179 |
| FFT mask | +11.3 / +0.9 | 4.5 / 1.7 | 9.8 / 10.7 | 0.19 / 0.22 | 0.048 / 0.045 |
| Ostromoukhov | +10.6 / −2.0 | 3.8 / 3.4 | 5.4 / 6.1 | 0.24 / 0.38 | 0.080 / 0.046 |
| Zhou–Fang | +10.2 / −2.5 | 3.9 / 3.1 | 5.6 / 5.9 | 0.19 / 0.21 | 0.075 / 0.039 |

Grey-patch chart:

| Method | bias | tone | texture | directional | periodic |
| --- | --- | --- | --- | --- | --- |
| Floyd–Steinberg | +10.7 / −5.7 | 4.5 / 8.9 | 3.5 / 5.7 | 0.27 / 0.35 | 0.048 / 0.175 |
| Serpentine FS | +10.7 / −5.7 | 4.5 / 8.7 | 3.7 / 5.9 | 0.25 / 0.35 | 0.051 / 0.126 |
| JJN | +12.7 / −0.3 | 6.1 / **3.5** | 4.9 / 6.4 | 0.34 / 0.23 | 0.071 / **0.035** |
| Atkinson | +12.4 / +0.7 | 5.3 / 8.2 | 4.6 / 5.2 | 0.28 / 0.25 | 0.040 / 0.103 |
| Bayer 8×8 | +9.1 / −9.7 | 4.0 / 13.4 | 4.2 / 5.9 | 0.03 / 0.12 | 0.569 / 0.545 |
| FFT mask | +12.8 / +0.9 | 6.4 / 2.4 | 9.6 / 11.5 | 0.20 / 0.21 | 0.056 / 0.060 |
| Ostromoukhov | +11.9 / −3.1 | 5.7 / 5.3 | 4.4 / 6.2 | 0.35 / 0.41 | 0.066 / 0.061 |
| Zhou–Fang | +11.3 / −3.7 | 6.0 / 4.4 | 4.6 / 6.1 | 0.19 / 0.20 | 0.056 / 0.044 |

Ostromoukhov and Zhou–Fang were rendered with a temporary clone of the external implementation; their bitmaps are not stored here. The FFT mask has low tone error only because its coarse noise averages out; its texture is by far the worst.

#### Artifact maps

These maps show where the texture is more strongly aligned than random grain ever gets (coherence above the 95th percentile for noise, weighted by texture strength), in flat areas only. Darker means a stronger aligned artifact. Grids such as Bayer are not aligned in one direction, so they appear in the `periodic` column instead of on these maps. Heat model, radius 0.55, same scale for all panels:

![Artifact maps on the grey-patch chart](images/patches/artifacts.png)

Maps for other images are not stored. Generate them with `--artifacts` in `evaluate_dither.py` or `benchmark.py` (see [Reproduce](#reproduce)).

On the patch chart, the maps pick out patterns that are visible in the simulated prints:

- Floyd–Steinberg and serpentine FS: checkerboard regions broken by horizontal stripes at mid grey.
- Atkinson: diagonal lines in the light patches.
- JJN: meandering "worms" spread across most tones.

Random grain (FFT mask) mostly stays blank.

#### Reading

- **Tone decides the radius question.** At radius 0.55 every method prints about 10 L\* lighter than the original. At 0.65 the bias is close to zero. The gamma 0.70 and contrast 0.90 preprocessing was tuned by eye on real prints. If that tuning aimed at faithful tone, the XP-80T at density 4 behaves more like radius 0.65 than the default 0.55. This is an inference from a past preference, not a measurement.
- **At radius 0.65, JJN fits the paper result.** It has the lowest tone error among the error-diffusion methods and the lowest periodic score on both samples. Floyd–Steinberg and serpentine FS gain periodic and directional artifacts on the patch chart as dots spread (periodic 0.05 → 0.18). This matches the log's "conspicuous texture/diagonal patterns on paper".
- **JJN is not artifact-free.** Its worms raise the directional score at 0.55. Zhou–Fang has the lowest directional score of all error-diffusion methods at every radius, consistent with its structure-aware design. Against JJN it loses mainly on tone (darker by 3–4 L\* at 0.65). That gap is within the uncertainty of the uncalibrated model.
- **Ostromoukhov** has the highest directional score at 0.65 on both samples. The log only says "softer/less defined"; the simulation suggests aligned structure as one possible cause.
- **Graininess** is lowest for Floyd–Steinberg at small radii and roughly equal for all error-diffusion methods at 0.65. It does not explain the paper ranking.

#### Across more samples

`experiments/benchmark.py` repeats the evaluation on nine images. Two of them, the NASA sample and the patch chart, are stored here. A face crop of the NASA sample is cut from the stored file. The other six are downloaded on demand, pinned by SHA-256, and not stored in this repository.

| Sample | Content | Source and licence |
| --- | --- | --- |
| astronaut | portrait, detailed background | NASA, public domain |
| astronaut-face | face crop of the same photo, upscaled 3.2×, so smooth and soft | NASA, public domain |
| sally-ride | portrait, smooth backdrop | NASA, public domain ([Commons](https://commons.wikimedia.org/wiki/File:Sally_Ride_(1984).jpg)) |
| earthrise | dark scene, large black area | NASA / Bill Anders, public domain ([Commons](https://commons.wikimedia.org/wiki/File:NASA_Earthrise_AS08-14-2383_Apollo_8_1968-12-24.jpg)) |
| rocket | dark sky gradient | SpaceX, public domain (scikit-image) |
| coffee | wood grain, white cup, dark saucer | Rachel Michetti, CC0 (scikit-image) |
| chelsea | fur texture | Stefan van der Walt, CC0 (scikit-image) |
| camera | grass texture, plain sky | Lav Varshney, CC0 (scikit-image) |
| patches | ten uniform grey patches | synthetic |

##### Gallery

Each sheet shows one 128×128-dot crop: the unadjusted original on top, then every method as a simulated print. The heat model uses the default radius 0.55, and the crop is enlarged 3×. The red boxes in the overview mark the crops:

![Sample overview with crop positions](images/gallery/overview.jpg)

| | | |
| --- | --- | --- |
| [astronaut](images/gallery/astronaut.jpg) | [astronaut-face](images/gallery/astronaut-face.jpg) | [sally-ride](images/gallery/sally-ride.jpg) |
| [earthrise](images/gallery/earthrise.jpg) | [rocket](images/gallery/rocket.jpg) | [coffee](images/gallery/coffee.jpg) |
| [chelsea](images/gallery/chelsea.jpg) | [camera](images/gallery/camera.jpg) | [patches](images/gallery/patches.jpg) |

The dark sky of the rocket sample shows the artifacts most clearly:

![Simulated prints of the rocket sample](images/gallery/rocket.jpg)

- Floyd–Steinberg, serpentine FS and Ostromoukhov: vertical and horizontal stripes.
- Atkinson: diagonal lines.
- JJN: worms.
- Zhou–Fang: the most even texture.

##### Numbers

All numbers are in [benchmark.csv](benchmark.csv). Zhou–Fang uses random noise, so its numbers change slightly between runs (in the second decimal place). Mean over the nine samples, heat model, radius 0.55 / 0.65:

| Method | bias | tone | texture | directional | periodic |
| --- | --- | --- | --- | --- | --- |
| Floyd–Steinberg | +10.1 / −5.0 | 2.7 / 5.5 | 3.9 / 5.7 | 0.25 / 0.33 | 0.056 / 0.130 |
| Serpentine FS | +10.0 / −5.2 | 2.7 / 5.5 | 4.1 / 5.9 | 0.21 / 0.33 | 0.051 / 0.114 |
| JJN | +12.2 / −0.3 | 3.9 / 2.7 | 5.4 / 6.1 | 0.27 / 0.26 | 0.060 / 0.061 |
| Atkinson | +11.4 / +0.6 | 4.2 / 5.6 | 4.5 / 5.2 | 0.31 / 0.30 | 0.112 / 0.112 |
| Bayer 8×8 | +8.3 / −8.7 | 2.4 / 8.4 | 4.7 / 7.3 | 0.06 / 0.18 | 0.356 / 0.279 |
| FFT mask | +12.2 / +0.7 | 4.1 / 1.8 | 9.6 / 10.9 | 0.19 / 0.21 | 0.055 / 0.053 |
| Ostromoukhov | +11.2 / −3.1 | 3.5 / 3.7 | 4.7 / 5.8 | 0.28 / 0.35 | 0.049 / 0.078 |
| Zhou–Fang | +10.8 / −3.6 | 3.5 / 3.3 | 4.9 / 5.7 | 0.17 / 0.20 | 0.048 / 0.072 |

How consistent the rankings are across the nine images:

- **The best method depends on the radius.** At 0.55, Floyd–Steinberg or serpentine FS has the lowest tone error among the error-diffusion methods on eight of nine images; on the rocket, Zhou–Fang does. At 0.65, the order reverses: JJN and Zhou–Fang have lower tone error than Floyd–Steinberg on all nine images, and FS prints darker than the original on all nine. The model cannot pick a winner until the radius is measured on paper.
- **At 0.65, JJN is the most tone-neutral error-diffusion method.** Its bias stays within −4.6 to +2.2 L\*. Floyd–Steinberg ranges from −13.0 to −0.6.
- **Zhou–Fang is the least directional error-diffusion method** on all nine images at 0.65 and on seven of nine at 0.55.
- **Ostromoukhov** has the highest mean directional score at 0.65 and is the most directional method on five of the nine images.
- **FFT mask** has the lowest tone error and the highest texture on every image at 0.65: coarse grain that averages out.
- **Bayer** has the highest periodic score on all nine images at 0.55 and on eight at 0.65. It is the least directional at 0.55, because a grid has no single direction.

Limits: nine images, uncalibrated parameters, and an approximate vision model. S-CIELAB is a standard model, but the directional and periodic measures are this project's own heuristics. They are checked against synthetic stripes and noise (`tests/test_evaluate.py`) and by eye against the maps, not against viewer ratings.

## Reproduce

```bash
pip install -e .
python experiments/compare_dither.py docs/sample/astronaut.png \
  --output docs/images/astronaut --detail 180 60 160 --simulate
python experiments/make_test_chart.py      # docs/sample/patches.png
python experiments/compare_dither.py docs/sample/patches.png --output docs/images/patches
D=docs/images/patches
python experiments/evaluate_dither.py docs/sample/patches.png \
  $D/floyd.png $D/serpentine.png $D/jjn.png $D/atkinson.png $D/bayer.png $D/blue.png \
  --radii 0.55 0.65 --artifacts $D/artifacts.png      # add --model overlap for the other model

# All nine samples, including Ostromoukhov and Zhou-Fang (about 3 minutes):
git clone --depth 1 https://github.com/dalpil/structure-aware-dithering /tmp/sad
python experiments/benchmark.py --external /tmp/sad --csv docs/benchmark.csv \
  --gallery docs/images/gallery \
  --artifacts output/benchmark-artifacts      # artifact maps for every sample, not committed
```

To print the same set on a connected XP-80T, add `--print`. Add `--density N` only if you accept that the experimental density command may change persistent printer settings (see the README caution).

`experiments/compare_structure_aware.py` compares JJN with Ostromoukhov and Zhou–Fang through a local clone of [dalpil/structure-aware-dithering](https://github.com/dalpil/structure-aware-dithering), which is not vendored here:

```bash
python experiments/compare_structure_aware.py --repo /path/to/structure-aware-dithering \
  --input docs/images/astronaut --output output/structure-aware
```
