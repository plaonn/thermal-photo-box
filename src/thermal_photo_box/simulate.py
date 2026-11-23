"""Approximate on-paper appearance of a 1-bit thermal print.

Two dot models are available:

- "heat" (default): each fired element deposits a Gaussian heat spot.
  Spots from neighbouring dots add up, and the paper darkens along a soft
  threshold (sigmoid) of the summed heat. Isolated dots therefore stay small,
  while the heat tails of adjacent dots fill the gaps between them. This
  stands in for lateral heat spread in the paper. Heat build-up in the print
  head over successive lines is NOT modelled.
- "overlap": each dot is a hard-edged anti-aliased ellipse; overlapping dots
  merge (a classic circular dot-overlap printer model).
- "square": no dot model. Each dot fills its square cell exactly, as a 1-bit
  image looks on screen. Useful as a baseline; `radius`, `aspect` and the
  other shape parameters are ignored.

In the heat and overlap models `radius` is the radius of an isolated dot in dot pitches, and
`aspect` stretches it in the paper-feed (vertical) direction. Paper and ink are
grey levels rather than pure white/black, mixed in linear reflectance.

The default parameters are NOT calibrated against a real printer. They are
plausible starting values for a 203 dpi direct-thermal printer.
"""
from dataclasses import dataclass

import numpy as np
from PIL import Image

MODELS = ("heat", "overlap", "square")


DEFAULT_RADIUS = {"heat": 0.55, "overlap": 0.75, "square": 0.5}


@dataclass(frozen=True)
class DotModel:
    radius: float = DEFAULT_RADIUS["heat"]  # isolated-dot radius, in dot pitches (horizontal)
    aspect: float = 1.15  # vertical/horizontal ratio (paper feed is vertical)
    paper: int = 245  # grey level of unprinted paper
    ink: int = 35  # grey level of a fully developed area
    blur: float = 0.10  # overlap model only: edge softness, dot pitches (Gaussian sigma)
    kind: str = "heat"  # "heat", "overlap" or "square"
    threshold: float = 0.4  # heat model: development threshold, relative to one spot's peak
    softness: float = 0.08  # heat model: width of the sigmoid around the threshold


def _subpixel_positions(scale: int, samples: int) -> np.ndarray:
    """Sample positions inside one cell, in dot units relative to the cell centre."""
    n = scale * samples
    return (np.arange(n) + 0.5) / n - 0.5


def _overlap_tile(dx: int, dy: int, scale: int, model: DotModel, samples: int = 4) -> np.ndarray:
    """Fraction of each output sub-pixel in a cell covered by the ellipse at offset (dx, dy)."""
    pos = _subpixel_positions(scale, samples)
    ys = (pos[:, None] - dy) / (model.radius * model.aspect)
    xs = (pos[None, :] - dx) / model.radius
    inside = (xs * xs + ys * ys) <= 1.0
    return inside.reshape(scale, samples, scale, samples).mean(axis=(1, 3)).astype(np.float32)


def _heat_sigma(model: DotModel) -> float:
    """Gaussian sigma whose `threshold` contour has the requested isolated-dot radius."""
    return model.radius / np.sqrt(-2.0 * np.log(model.threshold))


def _heat_tile(dx: int, dy: int, scale: int, model: DotModel) -> np.ndarray:
    """Heat at the centre of each output sub-pixel from a unit-peak spot at offset (dx, dy)."""
    pos = _subpixel_positions(scale, 1)
    sx = _heat_sigma(model)
    sy = sx * model.aspect
    gy = np.exp(-0.5 * ((pos - dy) / sy) ** 2)
    gx = np.exp(-0.5 * ((pos - dx) / sx) ** 2)
    return np.outer(gy, gx).astype(np.float32)


def _neighbourhood(bitmap: Image.Image, reach_x: int, reach_y: int):
    dots = (np.asarray(bitmap.convert("1"), dtype=bool) == 0).astype(np.float32)
    padded = np.pad(dots, ((reach_y, reach_y), (reach_x, reach_x)))
    return dots.shape, padded


def _coverage_overlap(bitmap, scale, model):
    reach_x = int(np.ceil(model.radius + 0.5))
    reach_y = int(np.ceil(model.radius * model.aspect + 0.5))
    (h, w), padded = _neighbourhood(bitmap, reach_x, reach_y)
    # Union of overlapping dots: 1 - prod(1 - coverage_i).
    clear = np.ones((h, scale, w, scale), dtype=np.float32)
    for dy in range(-reach_y, reach_y + 1):
        for dx in range(-reach_x, reach_x + 1):
            tile = _overlap_tile(dx, dy, scale, model)
            if not tile.any():
                continue
            src = padded[reach_y + dy:reach_y + dy + h, reach_x + dx:reach_x + dx + w]
            clear *= 1.0 - src[:, None, :, None] * tile[None, :, None, :]
    return 1.0 - clear.reshape(h * scale, w * scale)


def _coverage_heat(bitmap, scale, model):
    if not 0 < model.threshold < 1 or model.softness <= 0:
        raise ValueError("heat model needs 0 < threshold < 1 and softness > 0")
    sigma = _heat_sigma(model)
    # Spots are summed out to 3 sigma; the remaining tail is negligible.
    reach_x = int(np.ceil(3 * sigma + 0.5))
    reach_y = int(np.ceil(3 * sigma * model.aspect + 0.5))
    (h, w), padded = _neighbourhood(bitmap, reach_x, reach_y)
    heat = np.zeros((h, scale, w, scale), dtype=np.float32)
    for dy in range(-reach_y, reach_y + 1):
        for dx in range(-reach_x, reach_x + 1):
            tile = _heat_tile(dx, dy, scale, model)
            src = padded[reach_y + dy:reach_y + dy + h, reach_x + dx:reach_x + dx + w]
            heat += src[:, None, :, None] * tile[None, :, None, :]
    heat = heat.reshape(h * scale, w * scale)
    # Soft development threshold, rescaled so no heat -> 0 and saturation -> 1.
    def curve(x):
        return 1.0 / (1.0 + np.exp(-(x - model.threshold) / model.softness))
    lo, hi = curve(0.0), 1.0
    return np.clip((curve(heat) - lo) / (hi - lo), 0.0, 1.0)


def srgb_to_linear(v):
    """sRGB-encoded value in 0..1 -> linear reflectance."""
    v = np.asarray(v, dtype=np.float64)
    return np.where(v <= 0.04045, v / 12.92, ((v + 0.055) / 1.055) ** 2.4)


def linear_to_srgb(y):
    """Linear reflectance in 0..1 -> sRGB-encoded value."""
    y = np.clip(np.asarray(y, dtype=np.float64), 0.0, 1.0)
    return np.where(y <= 0.0031308, 12.92 * y, 1.055 * y ** (1 / 2.4) - 0.055)


def gaussian_blur(a: np.ndarray, sigma: float) -> np.ndarray:
    """Separable Gaussian blur of a float array, edges padded by reflection."""
    if sigma <= 0:
        return a
    r = max(1, int(np.ceil(3 * sigma)))
    k = np.exp(-0.5 * (np.arange(-r, r + 1) / sigma) ** 2)
    k /= k.sum()
    p = np.pad(a, r, mode="reflect" if min(a.shape) > r else "edge")
    p = np.apply_along_axis(lambda v: np.convolve(v, k, mode="valid"), 0, p)
    return np.apply_along_axis(lambda v: np.convolve(v, k, mode="valid"), 1, p)


def simulate_reflectance(bitmap: Image.Image, scale: int = 8, model: DotModel = DotModel()) -> np.ndarray:
    """Linear reflectance (0..1) of the simulated print, `scale` times larger than the bitmap.

    Paper and ink are mixed in linear reflectance (Murray-Davies), not in
    gamma-encoded grey values.
    """
    if scale < 1:
        raise ValueError("scale must be >= 1")
    if model.kind == "heat":
        coverage = _coverage_heat(bitmap, scale, model)
    elif model.kind == "overlap":
        coverage = _coverage_overlap(bitmap, scale, model)
        if model.blur > 0:
            coverage = gaussian_blur(coverage, model.blur * scale)
    elif model.kind == "square":
        ink = (np.asarray(bitmap.convert("L")) < 128).astype(np.float64)
        coverage = np.repeat(np.repeat(ink, scale, axis=0), scale, axis=1)
    else:
        raise ValueError(f"unknown dot model: {model.kind}")
    paper = float(srgb_to_linear(model.paper / 255))
    ink = float(srgb_to_linear(model.ink / 255))
    return paper - coverage * (paper - ink)


def simulate(bitmap: Image.Image, scale: int = 8, model: DotModel = DotModel()) -> Image.Image:
    """Render a 1-bit image (black = printed dot) as an sRGB greyscale image `scale` times larger."""
    y = simulate_reflectance(bitmap, scale, model)
    return Image.fromarray(np.rint(linear_to_srgb(y) * 255).astype(np.uint8))
