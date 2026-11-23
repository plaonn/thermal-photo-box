"""Compare a simulated print with the original image, and detect dither artifacts.

Pipeline:

1. Simulate the print and average each dot cell in linear reflectance.
2. Build the target from the *unadjusted* original greyscale, mapped into the
   printable L* range between ink and paper (gamut mapping).
3. Filter both with the S-CIELAB luminance contrast-sensitivity filter for a
   given viewing distance, then convert to CIE L*. The difference dL* contains
   only what is visible at that distance.
4. Split dL* into a smooth *tone* part and the remaining *texture* part.
5. Inside flat regions of the original, measure whether the texture is
   *directional* (worms, diagonal lines) and *periodic* (grids). Neither
   exists in the original, so both indicate artifacts introduced by dithering.

The numbers are only as good as the print simulation, whose parameters are
uncalibrated.
"""
from dataclasses import dataclass

import numpy as np
from PIL import Image

from .simulate import DotModel, gaussian_blur, simulate_reflectance, srgb_to_linear

# S-CIELAB luminance filter (Zhang & Wandell, 1997): weight and spread (degrees)
# of each term w * exp(-(x^2 + y^2) / s^2).
SCIELAB_LUMINANCE = ((0.921, 0.0283), (0.105, 0.133), (-0.108, 4.336))


# Orientation coherence of isotropic noise with the 3-dot window: mean about
# 0.13-0.17, 95th percentile about 0.35. The artifact map only shows coherence
# above that percentile, so random grain stays blank.
NOISE_COHERENCE_P95 = 0.35


def dots_per_degree(distance_cm: float, dpi: float) -> float:
    return distance_cm / 2.54 * np.tan(np.radians(1.0)) * dpi


def lstar(y):
    y = np.clip(np.asarray(y, dtype=np.float64), 0.0, None)
    f = np.where(y > 216 / 24389, np.cbrt(y), (24389 / 27 * y + 16) / 116)
    return 116 * f - 16


def lstar_to_y(L):
    f = (np.asarray(L, dtype=np.float64) + 16) / 116
    return np.where(f > 6 / 29, f ** 3, 3 * (6 / 29) ** 2 * (f - 4 / 29))


def csf_filter(y: np.ndarray, dpd: float) -> np.ndarray:
    """Apply the S-CIELAB luminance filter by FFT, with reflected padding."""
    h, w = y.shape
    p = np.pad(y, ((h - 1, h - 1), (w - 1, w - 1)), mode="reflect")
    fy = np.fft.fftfreq(p.shape[0])[:, None]
    fx = np.fft.rfftfreq(p.shape[1])[None, :]
    f2 = fx * fx + fy * fy  # cycles per dot, squared
    response = np.zeros_like(f2)
    for weight, spread in SCIELAB_LUMINANCE:
        sigma = spread * dpd / np.sqrt(2)  # in dots
        response += weight * np.exp(-2 * np.pi ** 2 * sigma ** 2 * f2)
    response /= sum(weight for weight, _ in SCIELAB_LUMINANCE)
    out = np.fft.irfft2(np.fft.rfft2(p) * response, s=p.shape)
    return out[h - 1:2 * h - 1, w - 1:2 * w - 1]


def cell_average(a: np.ndarray, scale: int) -> np.ndarray:
    h, w = a.shape[0] // scale, a.shape[1] // scale
    return a[:h * scale, :w * scale].reshape(h, scale, w, scale).mean(axis=(1, 3))


@dataclass
class Evaluation:
    bias: float  # mean dL*; negative = darker than target
    tone: float  # std of the smooth part of dL* (local tone error)
    texture: float  # RMS of the fine part of dL* (visible graininess)
    directional: float  # energy-weighted orientation coherence of texture in flat regions, 0..1
    periodic: float  # share of flat-region texture power in the strongest 0.1% of frequencies
    delta: np.ndarray  # dL* map
    artifact_map: np.ndarray  # texture amplitude where coherence exceeds what random grain reaches


def evaluate(bitmap: Image.Image, reference: Image.Image, model: DotModel = DotModel(),
             distance_cm: float = 30.0, dpi: float = 203.0, scale: int = 4) -> Evaluation:
    """Evaluate a 1-bit bitmap against the unadjusted greyscale reference of the same size."""
    if bitmap.size != reference.size:
        raise ValueError(f"size mismatch: bitmap {bitmap.size}, reference {reference.size}")
    dpd = dots_per_degree(distance_cm, dpi)

    sim = cell_average(simulate_reflectance(bitmap, scale, model), scale)
    l_paper = lstar(srgb_to_linear(model.paper / 255))
    l_ink = lstar(srgb_to_linear(model.ink / 255))
    l_ref = lstar(srgb_to_linear(np.asarray(reference.convert("L"), dtype=np.float64) / 255))
    target = lstar_to_y(l_ink + l_ref / 100 * (l_paper - l_ink))

    delta = lstar(csf_filter(sim, dpd)) - lstar(csf_filter(target, dpd))
    tone = gaussian_blur(delta, 0.25 * dpd)
    texture = delta - tone

    # Flat regions of the original: small smoothed gradient.
    gy, gx = np.gradient(gaussian_blur(l_ref, 1.0))
    edges = gaussian_blur(np.hypot(gx, gy), 2.0)
    flat = (edges < 1.0).astype(np.float64)

    gy, gx = np.gradient(texture)
    window = 3.0
    jxx = gaussian_blur(gx * gx, window)
    jyy = gaussian_blur(gy * gy, window)
    jxy = gaussian_blur(gx * gy, window)
    coherence = np.sqrt((jxx - jyy) ** 2 + 4 * jxy ** 2) / (jxx + jyy + 1e-12)
    energy = gaussian_blur(texture * texture, window)
    weight = energy * flat
    directional = float((coherence * weight).sum() / max(weight.sum(), 1e-12))

    hann = np.outer(np.hanning(texture.shape[0]), np.hanning(texture.shape[1]))
    power = np.abs(np.fft.rfft2(texture * flat * hann)) ** 2
    power[0, 0] = 0
    ranked = np.sort(power.ravel())[::-1]
    top = max(1, int(round(ranked.size * 0.001)))
    periodic = float(ranked[:top].sum() / max(ranked.sum(), 1e-12))

    return Evaluation(
        bias=float(delta.mean()),
        tone=float(tone.std()),
        texture=float(np.sqrt((texture ** 2).mean())),
        directional=directional,
        periodic=periodic,
        delta=delta,
        artifact_map=np.clip((coherence - NOISE_COHERENCE_P95) / (1 - NOISE_COHERENCE_P95), 0, None)
        * np.sqrt(energy) * flat,
    )
