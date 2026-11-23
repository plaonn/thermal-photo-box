"""Approximate on-paper appearance of a 1-bit thermal print.

Each black dot is drawn as an anti-aliased ellipse centred on its grid cell
(a circular/elliptical dot-overlap printer model). Overlapping dots merge.
Paper and ink are grey levels rather than pure white/black.

The default parameters are NOT calibrated against a real printer. They are
plausible starting values for a 203 dpi direct-thermal printer. Heat
accumulation (thermal history) is not modelled.
"""
from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageFilter


@dataclass(frozen=True)
class DotModel:
    radius: float = 0.75  # horizontal dot radius, in dot pitches
    aspect: float = 1.15  # vertical/horizontal radius ratio (paper feed is vertical)
    paper: int = 245  # grey level of unprinted paper
    ink: int = 35  # grey level of a fully covered area
    blur: float = 0.10  # edge softness, in dot pitches (Gaussian sigma)


def _coverage_tile(dx: int, dy: int, scale: int, model: DotModel, samples: int = 4) -> np.ndarray:
    """Fraction of each output sub-pixel in a cell covered by the dot at offset (dx, dy)."""
    rx = model.radius
    ry = model.radius * model.aspect
    # Sub-sample positions inside one cell, in dot units relative to the cell centre.
    n = scale * samples
    pos = (np.arange(n) + 0.5) / n - 0.5
    ys = (pos[:, None] - dy) / ry
    xs = (pos[None, :] - dx) / rx
    inside = (xs * xs + ys * ys) <= 1.0
    return inside.reshape(scale, samples, scale, samples).mean(axis=(1, 3)).astype(np.float32)


def simulate(bitmap: Image.Image, scale: int = 8, model: DotModel = DotModel()) -> Image.Image:
    """Render a 1-bit image (black = printed dot) as a greyscale image `scale` times larger."""
    if scale < 1:
        raise ValueError("scale must be >= 1")
    dots = (np.asarray(bitmap.convert("1"), dtype=bool) == 0).astype(np.float32)
    h, w = dots.shape
    reach_x = int(np.ceil(model.radius + 0.5))
    reach_y = int(np.ceil(model.radius * model.aspect + 0.5))
    padded = np.pad(dots, ((reach_y, reach_y), (reach_x, reach_x)))

    # Union of overlapping dots: 1 - prod(1 - coverage_i).
    clear = np.ones((h, scale, w, scale), dtype=np.float32)
    for dy in range(-reach_y, reach_y + 1):
        for dx in range(-reach_x, reach_x + 1):
            tile = _coverage_tile(dx, dy, scale, model)
            if not tile.any():
                continue
            # Neighbour at offset (dx, dy) from each cell.
            src = padded[reach_y + dy:reach_y + dy + h, reach_x + dx:reach_x + dx + w]
            clear *= 1.0 - src[:, None, :, None] * tile[None, :, None, :]
    coverage = 1.0 - clear.reshape(h * scale, w * scale)

    grey = model.paper - coverage * (model.paper - model.ink)
    image = Image.fromarray(np.clip(np.rint(grey), 0, 255).astype(np.uint8))
    if model.blur > 0:
        image = image.filter(ImageFilter.GaussianBlur(model.blur * scale))
    return image
