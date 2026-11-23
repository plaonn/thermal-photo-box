"""Additional halftoning methods for comparison (experimental, pure NumPy/Python).

- Error-diffusion kernels: Stucki, Burkes, Sierra, Two-row Sierra, Sierra Lite,
  Shiau-Fan.
- Threshold modulation: JJN and Atkinson with a blue-noise threshold
  (Knox & Eschbach), which breaks the limit cycles that produce regular
  patterns at simple grey levels.
- Green-noise error diffusion (Levien's output-dependent feedback, with a
  blue-noise threshold): previously printed neighbours make a dot more likely.
  Meant to form small clusters; in raster order it mostly forms short streaks.
- JJN on 2x2 cells: a simple clustered alternative at half resolution.
- Void-and-cluster blue-noise mask (Ulichney 1993), ordered dither.
- Riemersma dithering: error diffusion along a Hilbert curve.
- Direct binary search (DBS): iterative toggles that minimise the
  S-CIELAB-filtered error, starting from JJN. Toggles only, no swaps.
- Clustered-dot screen at 45 degrees (newspaper-style halftone).

All functions take a greyscale PIL image (the preprocessed input) and return a
1-bit image, black = printed dot.
"""
import numpy as np
from PIL import Image

from thermal_photo_box.bluenoise import _tile, blue_noise_threshold, void_and_cluster  # noqa: F401
from thermal_photo_box.cli import JJN_KERNEL

FS_KERNEL = ((1, 0, 7 / 16), (-1, 1, 3 / 16), (0, 1, 5 / 16), (1, 1, 1 / 16))
ATKINSON_KERNEL = tuple((dx, dy, 1 / 8) for dx, dy in ((1, 0), (2, 0), (-1, 1), (0, 1), (1, 1), (0, 2)))


def _kernel(rows, origin, divisor):
    """Kernel from rows of weights; `origin` is the column of the current pixel in row 0."""
    return tuple((x - origin, y, w / divisor) for y, row in enumerate(rows) for x, w in enumerate(row) if w)


STUCKI = _kernel(((0, 0, 0, 8, 4), (2, 4, 8, 4, 2), (1, 2, 4, 2, 1)), 2, 42)
BURKES = _kernel(((0, 0, 0, 8, 4), (2, 4, 8, 4, 2)), 2, 32)
SIERRA = _kernel(((0, 0, 0, 5, 3), (2, 4, 5, 4, 2), (0, 2, 3, 2, 0)), 2, 32)
SIERRA2 = _kernel(((0, 0, 0, 4, 3), (1, 2, 3, 2, 1)), 2, 16)
SIERRA_LITE = _kernel(((0, 0, 2), (0, 1, 1)), 1, 4)
SHIAU_FAN = _kernel(((0, 0, 0, 0, 8), (1, 1, 2, 4, 0)), 3, 16)


def _to_image(dots):
    """Boolean array (True = printed dot) -> 1-bit image."""
    return Image.fromarray(np.where(dots, 0, 255).astype(np.uint8)).convert("1", dither=Image.Dither.NONE)


def diffuse(gray, kernel, threshold_noise=None, hysteresis=0.0):
    """Generic error diffusion in raster order.

    threshold_noise: array added to the threshold (same shape as the image).
    hysteresis: Levien's output-dependent feedback; the threshold is raised
    (dots become more likely) by `hysteresis` times 255 times the fraction of the
    left, upper-left, upper and upper-right neighbours that are dots,
    minus one half (so a half-dark neighbourhood leaves the threshold unchanged).
    """
    src = np.asarray(gray, dtype=np.float64).copy()
    h, w = src.shape
    dots = np.zeros((h, w), dtype=bool)
    noise = np.zeros((h, w)) if threshold_noise is None else threshold_noise
    for y in range(h):
        row = src[y]
        for x in range(w):
            v = row[x]
            t = 128.0 + noise[y, x]
            if hysteresis:
                # Already decided causal neighbours: left, upper-left, up, upper-right.
                dark = 0
                if x:
                    dark += dots[y, x - 1]
                if y:
                    dark += dots[y - 1, x] + (dots[y - 1, x - 1] if x else 0) + (dots[y - 1, x + 1] if x + 1 < w else 0)
                t += hysteresis * 255.0 * (dark / 4 - 0.5)
            ink = v < t
            dots[y, x] = ink
            err = v - (0.0 if ink else 255.0)
            for dx, dy, weight in kernel:
                nx, ny = x + dx, y + dy
                if 0 <= nx < w and ny < h:
                    src[ny, nx] += err * weight
    return _to_image(dots)


def void_cluster(gray):
    src = np.asarray(gray, dtype=np.float64)
    mask = void_and_cluster()
    threshold = (_tile(mask, src.shape) + 0.5) * 255.0 / mask.size
    return _to_image(src < threshold)


def _hilbert(order):
    """(x, y) of every point of a Hilbert curve covering 2**order squared."""
    n = 1 << order
    for d in range(n * n):
        x = y = 0
        t = d
        s = 1
        while s < n:
            rx = 1 & (t // 2)
            ry = 1 & (t ^ rx)
            if ry == 0:
                if rx == 1:
                    x, y = s - 1 - x, s - 1 - y
                x, y = y, x
            x += s * rx
            y += s * ry
            t //= 4
            s *= 2
        yield x, y


def riemersma(gray, history=16, ratio=1 / 16):
    """Error diffusion along a Hilbert curve with an exponentially decaying error history."""
    src = np.asarray(gray, dtype=np.float64)
    h, w = src.shape
    order = int(np.ceil(np.log2(max(h, w))))
    weights = ratio ** (np.arange(history)[::-1] / (history - 1))  # oldest .. newest
    weights /= weights.sum()
    errors = np.zeros(history)
    dots = np.zeros((h, w), dtype=bool)
    for x, y in _hilbert(order):
        if x >= w or y >= h:
            continue
        v = src[y, x] + float(errors @ weights)
        ink = v < 128
        dots[y, x] = ink
        errors[:-1] = errors[1:]
        errors[-1] = v - (0.0 if ink else 255.0)
    return _to_image(dots)


def _hvs_kernel(distance_cm=30.0, dpi=203.0):
    """Positive lobes of the S-CIELAB luminance filter, in dots (normalised)."""
    from thermal_photo_box.evaluate import SCIELAB_LUMINANCE, dots_per_degree

    dpd = dots_per_degree(distance_cm, dpi)
    lobes = [(wt, sp * dpd / np.sqrt(2)) for wt, sp in SCIELAB_LUMINANCE if wt > 0]
    r = int(np.ceil(3 * max(s for _, s in lobes)))
    yy, xx = np.mgrid[-r:r + 1, -r:r + 1]
    p = sum(wt / (2 * np.pi * s * s) * np.exp(-(xx ** 2 + yy ** 2) / (2 * s * s)) for wt, s in lobes)
    return p / p.sum()


def _convolve_same(a, k):
    """Linear 'same' convolution via FFT (zero padding)."""
    kh, kw = k.shape
    shape = (a.shape[0] + kh - 1, a.shape[1] + kw - 1)
    out = np.fft.irfft2(np.fft.rfft2(a, shape) * np.fft.rfft2(k, shape), shape)
    return out[kh // 2:kh // 2 + a.shape[0], kw // 2:kw // 2 + a.shape[1]]


def dbs(gray, passes=8, start=None):
    """Direct binary search with toggles only, minimising |p * (b - g)|^2.

    b is the dot pattern (1 = ink) and g the target ink fraction. The
    autocorrelation c_pp of the visual filter p gives the change in error for a
    toggle at m: dE = 2 a c_ep(m) + a^2 c_pp(0), with a = +1 or -1. Pixels farther
    apart than the support of c_pp do not interact, so all toggles on such a
    sub-grid are evaluated and applied at once.
    """
    g = 1.0 - np.asarray(gray, dtype=np.float64) / 255.0
    if start is None:
        start = diffuse(gray, JJN_KERNEL)
    b = (np.asarray(start.convert("L")) == 0).astype(np.float64)
    p = _hvs_kernel()
    cpp = _convolve_same(p, p[::-1, ::-1])
    keep = cpp >= cpp.max() * 1e-3
    ys, xs = np.nonzero(keep)
    cy, cx = np.array(cpp.shape) // 2
    r = int(max(abs(ys - cy).max(), abs(xs - cx).max()))
    cpp = cpp[cy - r:cy + r + 1, cx - r:cx + r + 1]
    c0 = cpp[r, r]
    step = 2 * r + 1
    cep = _convolve_same(b - g, cpp)
    h, w = g.shape
    for _ in range(passes):
        changed = 0
        for oy in range(step):
            for ox in range(step):
                sub = (slice(oy, None, step), slice(ox, None, step))
                a = 1.0 - 2.0 * b[sub]
                gain = 2.0 * a * cep[sub] + c0
                accept = gain < 0
                if not accept.any():
                    continue
                delta = np.zeros_like(b)
                delta[sub] = np.where(accept, a, 0.0)
                b += delta
                cep += _convolve_same(delta, cpp)
                changed += int(accept.sum())
        if changed == 0:
            break
    return _to_image(b > 0.5)


def jjn_2x2(gray):
    """JJN at half resolution, each decision printed as a 2x2 cluster of dots."""
    w, h = gray.size
    half = gray.resize(((w + 1) // 2, (h + 1) // 2), Image.Resampling.BOX)
    dots = np.asarray(diffuse(half, JJN_KERNEL).convert("L")) == 0
    return _to_image(dots.repeat(2, axis=0).repeat(2, axis=1)[:h, :w])


def clustered_dot(gray, period=6.0, angle=45.0):
    """Clustered-dot screen: round dots on a grid rotated by `angle`, `period` dots apart."""
    src = np.asarray(gray, dtype=np.float64)
    h, w = src.shape
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float64)
    t = np.radians(angle)
    u = (xx * np.cos(t) + yy * np.sin(t)) * 2 * np.pi / period
    v = (-xx * np.sin(t) + yy * np.cos(t)) * 2 * np.pi / period
    spot = (np.cos(u) + np.cos(v)) / 4 + 0.5  # 1 at dot centres
    # Equalise so that a uniform grey prints the matching dot fraction.
    order = np.argsort(spot.ravel())
    ranks = np.empty(spot.size)
    ranks[order] = np.arange(spot.size)
    threshold = (ranks.reshape(h, w) + 0.5) / spot.size * 255.0
    return _to_image(src < threshold)


EXTRA_METHODS = {
    "stucki": lambda g: diffuse(g, STUCKI),
    "burkes": lambda g: diffuse(g, BURKES),
    "sierra": lambda g: diffuse(g, SIERRA),
    "sierra2": lambda g: diffuse(g, SIERRA2),
    "sierra-lite": lambda g: diffuse(g, SIERRA_LITE),
    "shiau-fan": lambda g: diffuse(g, SHIAU_FAN),
    "jjn-tm32": lambda g: diffuse(g, JJN_KERNEL, blue_noise_threshold(np.asarray(g).shape, 32)),
    "jjn-tm64": lambda g: diffuse(g, JJN_KERNEL, blue_noise_threshold(np.asarray(g).shape, 64)),
    "atkinson-tm32": lambda g: diffuse(g, ATKINSON_KERNEL, blue_noise_threshold(np.asarray(g).shape, 32)),
    "atkinson-tm64": lambda g: diffuse(g, ATKINSON_KERNEL, blue_noise_threshold(np.asarray(g).shape, 64)),
    "green-0.6": lambda g: diffuse(g, FS_KERNEL, blue_noise_threshold(np.asarray(g).shape, 64), hysteresis=0.6),
    "jjn-2x2": jjn_2x2,
    "void-cluster": void_cluster,
    "riemersma": riemersma,
    "dbs": dbs,
    "clustered": clustered_dot,
}

EXTRA_LABELS = {
    "stucki": "Stucki",
    "burkes": "Burkes",
    "sierra": "Sierra",
    "sierra2": "Two-row Sierra",
    "sierra-lite": "Sierra Lite",
    "shiau-fan": "Shiau-Fan",
    "jjn-tm32": "JJN + noise 32",
    "jjn-tm64": "JJN + noise 64",
    "atkinson-tm32": "Atkinson + noise 32",
    "atkinson-tm64": "Atkinson + noise 64",
    "green-0.6": "Green noise 0.6",
    "jjn-2x2": "JJN on 2x2 cells",
    "void-cluster": "Void-and-cluster",
    "riemersma": "Riemersma",
    "dbs": "DBS",
    "clustered": "Clustered dot 45deg",
}
