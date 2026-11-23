"""Blue-noise threshold mask (Ulichney's void-and-cluster), for threshold modulation of error diffusion.

Varying the error-diffusion threshold by a blue-noise mask (Knox & Eschbach)
keeps the error from settling into regular cycles, which otherwise show as
lines, lattices and worms. See docs/candidates.md.
"""
from functools import lru_cache

import numpy as np


@lru_cache(maxsize=None)
def void_and_cluster(size=64, sigma=1.5, seed=1):
    """Ulichney's void-and-cluster threshold mask, ranks 0..size*size-1."""
    rng = np.random.default_rng(seed)
    n = size * size
    d = np.minimum(np.arange(size), size - np.arange(size))
    kernel = np.exp(-(d[:, None] ** 2 + d[None, :] ** 2) / (2 * sigma ** 2))

    def energy_of(pattern):
        return np.real(np.fft.ifft2(np.fft.fft2(pattern) * np.fft.fft2(kernel)))

    def shifted(i):
        y, x = divmod(i, size)
        return np.roll(np.roll(kernel, y, axis=0), x, axis=1)

    # Initial binary pattern: 10% random minority pixels, relaxed by moving the
    # tightest cluster into the largest void until stable.
    pattern = np.zeros((size, size))
    pattern.flat[rng.choice(n, n // 10, replace=False)] = 1
    energy = energy_of(pattern)
    while True:
        cluster = int(np.argmax(np.where(pattern == 1, energy, -np.inf)))
        pattern.flat[cluster] = 0
        energy -= shifted(cluster)
        void = int(np.argmin(np.where(pattern == 0, energy, np.inf)))
        if void == cluster:
            pattern.flat[cluster] = 1
            energy += shifted(cluster)
            break
        pattern.flat[void] = 1
        energy += shifted(void)
    initial = pattern.copy()
    ones = int(initial.sum())
    rank = np.zeros(n, dtype=np.int64)

    # Phase 1: remove tightest clusters, ranks ones-1 .. 0.
    pattern, energy = initial.copy(), energy_of(initial)
    for r in range(ones - 1, -1, -1):
        i = int(np.argmax(np.where(pattern == 1, energy, -np.inf)))
        pattern.flat[i] = 0
        energy -= shifted(i)
        rank[i] = r
    # Phase 2 and 3: fill largest voids, ranks ones .. n-1.
    pattern, energy = initial.copy(), energy_of(initial)
    for r in range(ones, n):
        i = int(np.argmin(np.where(pattern == 0, energy, np.inf)))
        pattern.flat[i] = 1
        energy += shifted(i)
        rank[i] = r
    return rank.reshape(size, size)


def _tile(mask, shape):
    s = mask.shape[0]
    return np.tile(mask, ((shape[0] + s - 1) // s, (shape[1] + s - 1) // s))[:shape[0], :shape[1]]


def blue_noise_threshold(shape, amplitude):
    """Blue-noise threshold perturbation in -amplitude/2 .. +amplitude/2."""
    mask = void_and_cluster()
    return (_tile(mask, shape) + 0.5) / mask.size * amplitude - amplitude / 2
