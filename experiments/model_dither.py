"""Error-diffusion variants motivated by the print simulation (experimental).

Terminology: "ink" or "dark" means the area of thermal paper that has developed
(turned dark); there is no ink or ribbon in a direct thermal printer.

- Model-based error diffusion (after Pappas & Neuhoff): the error is computed
  against the predicted print, not against a perfect black square. Firing a dot
  darkens the paper by an amount that depends on the dots already printed around
  it (heat from neighbours adds up). That amount comes from a table of the heat
  model, indexed by the seven already-decided neighbours. Because each increment
  is computed given every earlier decision, the increments add up to the
  predicted total darkness. Input is the target in linear light, like the
  evaluation target, so this method needs no gamma preprocessing.
- Paired shadow holes: in dark areas, a white (undeveloped) dot is extended to
  the dot below it, so holes are two dots tall and survive heat spread.
- Partial error loss: JJN that diffuses only 7/8 of the error, a mild form of
  Atkinson's solid highlights and shadows.
- Adaptive threshold noise: strong blue-noise threshold modulation in flat
  areas, weaker at edges and in detailed areas.

All take a greyscale PIL image and return a 1-bit image, black = printed dot.
`model_jjn` expects the reference (no gamma or contrast adjustment); the others
expect the standard preprocessed input.
"""
from functools import lru_cache

import numpy as np

from thermal_photo_box.cli import JJN_KERNEL
from thermal_photo_box.evaluate import lstar, lstar_to_y
from thermal_photo_box.simulate import DotModel, gaussian_blur, simulate_reflectance, srgb_to_linear
from extra_dither import _to_image, blue_noise_threshold, diffuse

# Already-decided neighbours in raster order, as (dx, dy).
CAUSAL = ((-2, -1), (-1, -1), (0, -1), (1, -1), (2, -1), (-2, 0), (-1, 0))
DESIGN_RADIUS = 0.65


def _coverage(dots, model, scale=4):
    """Developed area of a small patch, in dot cells, under the heat model."""
    paper = float(srgb_to_linear(model.paper / 255))
    ink = float(srgb_to_linear(model.ink / 255))
    y = simulate_reflectance(_to_image(dots), scale, model)
    return float(((paper - y) / (paper - ink)).sum()) / scale ** 2


@lru_cache(maxsize=None)
def increment_table(radius=DESIGN_RADIUS):
    """Extra developed area (in dot cells) from firing a dot, per causal neighbourhood."""
    model = DotModel(radius=radius)
    table = np.zeros(1 << len(CAUSAL))
    for config in range(len(table)):
        dots = np.zeros((11, 11), dtype=bool)
        for bit, (dx, dy) in enumerate(CAUSAL):
            if config >> bit & 1:
                dots[5 + dy, 5 + dx] = True
        before = _coverage(dots, model)
        dots[5, 5] = True
        table[config] = _coverage(dots, model) - before
    return table


def target_coverage(reference, model=DotModel()):
    """Developed-area fraction whose L* matches the reference, as in the evaluation."""
    paper = float(srgb_to_linear(model.paper / 255))
    ink = float(srgb_to_linear(model.ink / 255))
    l_paper, l_ink = float(lstar(paper)), float(lstar(ink))
    l_ref = lstar(srgb_to_linear(np.asarray(reference, dtype=np.float64) / 255))
    y = lstar_to_y(l_ink + l_ref / 100 * (l_paper - l_ink))
    return np.clip((paper - y) / (paper - ink), 0.0, 1.0)


def model_jjn(reference, radius=DESIGN_RADIUS, noise=0.0, kernel=JJN_KERNEL, serpentine=False, penalty=0.0):
    """Model-based JJN. `noise` is the threshold-noise amplitude in grey levels (as in jjn-tm64).

    Undecided neighbours are taken as white, so the increments add up exactly to
    the predicted darkness. This favours dots next to existing ones (they add
    less darkness, so they pass the threshold more easily), which forms lines in
    dark tones. Sharing each interaction between the two dots instead (half
    each, undecided neighbours weighted by the local darkness) was tried and
    printed 15 L* too dark: heat development is a threshold effect, so the
    interactions are not pairwise.

    Two counter-measures against the lines:
    - `serpentine`: odd rows are processed right to left (the causal
      neighbourhood and the kernel are mirrored; the heat model is symmetric).
    - `penalty`: the threshold is raised by `penalty` times the darkness a dot
      saves by being next to existing dots. At 0.5 the threshold is the same
      as for an isolated dot, so the decision no longer prefers neighbours; the
      error is still measured against the predicted print, so tone is kept.
    """
    table = increment_table(radius)
    alone = table[0]
    src = target_coverage(reference).copy()
    h, w = src.shape
    jitter = blue_noise_threshold((h, w), noise) / 255 if noise else np.zeros((h, w))
    dots = np.zeros((h + 1, w + 4), dtype=bool)  # one blank row above, two blank columns each side
    for y in range(h):
        row = src[y]
        reverse = serpentine and y % 2 == 1
        s = -1 if reverse else 1
        for x in (range(w - 1, -1, -1) if reverse else range(w)):
            config = 0
            for bit, (dx, dy) in enumerate(CAUSAL):
                if dots[y + 1 + dy, x + 2 + s * dx]:
                    config |= 1 << bit
            inc = table[config]
            v = row[x]
            fire = v > inc / 2 + penalty * (alone - inc) - jitter[y, x]
            dots[y + 1, x + 2] = fire
            err = v - (inc if fire else 0.0)
            for dx, dy, weight in kernel:
                nx, ny = x + s * dx, y + dy
                if 0 <= nx < w and ny < h:
                    src[ny, nx] += err * weight
    return _to_image(dots[1:, 2:-2])


def paired_holes(gray, dark=96, noise=64, kernel=JJN_KERNEL):
    """JJN with threshold noise; in areas darker than `dark`, white dots are two dots tall."""
    src = np.asarray(gray, dtype=np.float64).copy()
    level = np.asarray(gray, dtype=np.float64)
    h, w = src.shape
    jitter = blue_noise_threshold((h, w), noise) if noise else np.zeros((h, w))
    dots = np.zeros((h, w), dtype=bool)
    forced = np.zeros((h, w), dtype=bool)
    for y in range(h):
        row = src[y]
        for x in range(w):
            v = row[x]
            ink = False if forced[y, x] else v < 128.0 + jitter[y, x]
            dots[y, x] = ink
            if not ink and not forced[y, x] and level[y, x] < dark and y + 1 < h:
                forced[y + 1, x] = True
            err = v - (0.0 if ink else 255.0)
            for dx, dy, weight in kernel:
                nx, ny = x + dx, y + dy
                if 0 <= nx < w and ny < h:
                    src[ny, nx] += err * weight
    return _to_image(dots)


def partial_loss(gray, kept=7 / 8, noise=64):
    """JJN with threshold noise that diffuses only `kept` of the error."""
    kernel = tuple((dx, dy, wt * kept) for dx, dy, wt in JJN_KERNEL)
    noise_map = blue_noise_threshold(np.asarray(gray).shape, noise) if noise else None
    return diffuse(gray, kernel, noise_map)


def adaptive_noise(gray, noise=64, floor=0.25, scale=8.0):
    """JJN with threshold noise that is full strength in flat areas and `floor` of it at edges."""
    g = np.asarray(gray, dtype=np.float64)
    gy, gx = np.gradient(gaussian_blur(g, 1.0))
    edges = gaussian_blur(np.hypot(gx, gy), 1.5)
    weight = floor + (1 - floor) * np.exp(-edges / scale)
    return diffuse(gray, JJN_KERNEL, blue_noise_threshold(g.shape, noise) * weight)


# name: (function, input) where input is "gray" (standard preprocessing) or "reference"
IMPROVED = {
    "jjn-model": (model_jjn, "reference"),
    "jjn-model-tm64": (lambda r: model_jjn(r, noise=64), "reference"),
    "jjn-model-serp": (lambda r: model_jjn(r, serpentine=True), "reference"),
    "jjn-model-serp-tm64": (lambda r: model_jjn(r, noise=64, serpentine=True), "reference"),
    "jjn-model-pen": (lambda r: model_jjn(r, serpentine=True, penalty=0.5), "reference"),
    "jjn-model-pen-tm64": (lambda r: model_jjn(r, noise=64, serpentine=True, penalty=0.5), "reference"),
    "jjn-tm64-pairs": (paired_holes, "gray"),
    "jjn-tm64-loss": (partial_loss, "gray"),
    "jjn-tm64-adaptive": (adaptive_noise, "gray"),
}

IMPROVED_LABELS = {
    "jjn-model": "JJN, model-based",
    "jjn-model-tm64": "JJN, model-based + noise 64",
    "jjn-model-serp": "JJN, model-based, serpentine",
    "jjn-model-serp-tm64": "JJN, model-based, serpentine + noise 64",
    "jjn-model-pen": "JJN, model-based, serpentine + chain penalty",
    "jjn-model-pen-tm64": "JJN, model-based, serpentine + chain penalty + noise 64",
    "jjn-tm64-pairs": "JJN + noise 64, paired shadow holes",
    "jjn-tm64-loss": "JJN + noise 64, 7/8 error",
    "jjn-tm64-adaptive": "JJN + adaptive noise",
}
