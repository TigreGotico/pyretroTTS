"""Measure the fundamental frequency of rendered PCM.

Used to pick SAM's pitch knob, whose eight-bit arithmetic is not monotonic:
some knob values render an octave away from where the arithmetic says they
should. Measuring is cheaper than modelling that.

Plain autocorrelation reports octave errors. A strong second harmonic makes the
peak at half the period win; the peak at twice the period is nearly as strong as
the true one. Both engines here have loud harmonics, so both trip it.

`fundamental` uses the cumulative mean normalized difference function from YIN
(de Cheveigné and Kawahara, 2002), which is the standard fix: the normalization
suppresses the zero-lag trough, and taking the first dip below an absolute
threshold picks the period rather than one of its multiples.
"""
import struct

SAMPLE_RATE = 22050

#: YIN's absolute threshold. A dip below this is accepted as the period.
_THRESHOLD = 0.15


def fundamental(pcm: bytes, sample_rate: int = SAMPLE_RATE,
                low_hz: int = 60, high_hz: int = 600) -> float:
    """The fundamental of the middle half of `pcm`, in Hz. 0.0 for silence."""
    samples = struct.unpack(f"<{len(pcm) // 2}h", pcm)
    samples = samples[len(samples) // 4: 3 * len(samples) // 4]
    if not any(samples):
        return 0.0

    max_lag = min(sample_rate // low_hz, len(samples) // 2)
    min_lag = sample_rate // high_hz
    if max_lag <= min_lag:
        return 0.0

    # difference function
    window = len(samples) - max_lag
    difference = [0.0] * (max_lag + 1)
    for lag in range(1, max_lag + 1):
        total = 0.0
        for i in range(0, window, 2):
            delta = samples[i] - samples[i + lag]
            total += delta * delta
        difference[lag] = total

    # cumulative mean normalization
    normalized = [1.0] * (max_lag + 1)
    running = 0.0
    for lag in range(1, max_lag + 1):
        running += difference[lag]
        normalized[lag] = difference[lag] * lag / running if running else 1.0

    for lag in range(min_lag, max_lag):
        if normalized[lag] < _THRESHOLD and normalized[lag] <= normalized[lag + 1]:
            return sample_rate / lag

    best = min(range(min_lag, max_lag), key=lambda lag: normalized[lag])
    return sample_rate / best
