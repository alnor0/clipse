"""Tempo (BPM) of music - used by sound_analysis.py.

Takes the first 90 seconds (one channel, 11025 Hz), finds where the sound
gets suddenly louder (onsets: drum hits, chord changes) and looks for the
steadiest repeat between them. Typical tempos (around 120) are gently
preferred, and the kick drum decides between half and double speed (hats
between kicks are off-beats), so a song isn't reported at half or double
its speed.
"""
import math
from operator import mul

RATE = 11025
HOP = 128                     # samples per analysis step (~12 ms)
SECONDS = 90
MIN_BPM, MAX_BPM = 60, 200


def _beat_strengths(onset, lag):
    """How strong the hits are on the beat vs halfway between beats, for a
    beat every `lag` steps (at the phase where the beats are strongest)."""
    m = len(onset)

    def strength(phase):
        total, count, pos = 0.0, 0, float(phase)
        while pos < m - 1:
            i = int(pos)
            total += max(onset[i], onset[i + 1], onset[i - 1] if i else 0.0)
            count += 1
            pos += lag
        return total / count if count else 0.0
    best = max(range(int(lag)), key=strength)  # lag may be fractional: no drift
    return strength(best), strength(best + lag / 2.0)


def _onsets(samples):
    """Where the sound gets suddenly louder, step by step: over the whole
    range, and in the lows only (kick drums - the beat itself, without the
    hi-hats in between). The lows come from averaging blocks of samples, a
    cheap low-pass. Loudness is compared on a log scale relative to the
    clip's own level, so quiet ticks don't count as much as real hits."""
    n = len(samples) // HOP
    block = 32
    full, low = [], []
    for i in range(n):
        seg = samples[i * HOP:(i + 1) * HOP]
        full.append(sum(map(mul, seg, seg)) / HOP)
        means = [sum(seg[j:j + block]) / block for j in range(0, HOP, block)]
        low.append(sum(v * v for v in means) / len(means))

    def rise(e):
        ref = 0.05 * (sum(e) / len(e)) or 1.0
        e = [math.log1p(v / ref) for v in e]
        return [max(0.0, e[i] - e[i - 1]) for i in range(1, len(e))]
    return rise(full), rise(low)


def _normalised(values):
    mean = sum(values) / len(values)
    spread = math.sqrt(sum((v - mean) ** 2 for v in values) / len(values)) or 1.0
    return [(v - mean) / spread for v in values]


def tempo(samples, rate=RATE):
    """BPM of the samples (16-bit mono), or None if there's no clear beat."""
    if len(samples) // HOP < 400:
        return None
    full, low = _onsets(samples)
    if sum(full) / len(full) < 0.01:
        return None  # hardly any change in loudness: a pad, a drone - no beat
    onset = [a + b for a, b in zip(_normalised(full), _normalised(low))]
    fps = rate / HOP
    lags = range(max(1, int(60 * fps / MAX_BPM)), int(60 * fps / MIN_BPM) * 2 + 2)
    m = len(onset)
    scores = {lag: sum(map(mul, onset[:m - lag], onset[lag:])) / (m - lag) for lag in lags}

    def bpm_of(lag):
        return 60 * fps / lag
    # prefer typical tempos: a gentle bell around 120 BPM (on a log scale)
    best_lag, best = None, -1e18
    for lag, score in scores.items():
        if not MIN_BPM <= bpm_of(lag) <= MAX_BPM:
            continue
        weight = math.exp(-0.5 * (math.log2(bpm_of(lag) / 120.0) / 0.9) ** 2)
        if score * weight > best:
            best_lag, best = lag, score * weight
    if best_lag is None or scores[best_lag] <= 0:
        return None
    # no clear beat (ambience, speech, noise): the repeat is weak compared to the signal itself
    power = sum(o * o for o in onset) / m
    if power <= 0 or scores[best_lag] / power < 0.12:
        return None
    def sharp(lag):  # between neighbouring lags, for the exact tempo
        a, b, c = scores.get(lag - 1), scores[lag], scores.get(lag + 1)
        if a is not None and c is not None and (a - 2 * b + c) != 0:
            return lag + max(-0.5, min(0.5, 0.5 * (a - c) / (a - 2 * b + c)))
        return float(lag)
    # octave check, by the kick drum: twice as slow if every other hit is
    # clearly weaker in the lows (those were hi-hats between the kicks)...
    double = best_lag * 2
    if double in scores and bpm_of(double) >= MIN_BPM and scores[double] >= 0.3 * scores[best_lag]:
        on, off = _beat_strengths(low, 2 * sharp(best_lag))
        if off < 0.5 * on:
            best_lag = double
    # ...or twice as fast if the hits halfway between beats are as strong
    half = best_lag / 2.0
    lo, hi = int(math.floor(half)), int(math.ceil(half))
    if lo in scores and hi in scores and bpm_of(half) <= MAX_BPM:
        if max(scores[lo], scores[hi]) >= 0.5 * scores[best_lag]:
            on, off = _beat_strengths(low, sharp(best_lag))
            if off >= 0.7 * on:
                best_lag = lo if scores[lo] >= scores[hi] else hi
    # the exact tempo: a few beats further on, the same rounding error is
    # spread over several beats (4 beats = 4x as precise)
    lag = sharp(best_lag)

    def score(k):
        if k not in scores:
            scores[k] = sum(map(mul, onset[:m - k], onset[k:])) / (m - k) if 0 < k < m // 2 else -1e18
        return scores[k]
    for beats in (4, 3, 2):
        target = int(round(beats * lag))
        a, b, c = score(target - 1), score(target), score(target + 1)
        if b >= a and b >= c and b > 0:
            lag = sharp(target) / beats
            break
    return round(_fit(onset, fps, bpm_of(lag)), 1)


def _fit(onset, fps, guess, reach=1.5, step=0.05):
    """The tempo to a twentieth of a BPM: of the tempos near `guess`, the one whose beat grid - at its best
    phase - lands hardest on the hits across the whole stretch. A few tenths off is half a beat of drift by
    the end of a song (measured 2026-10-15: one song 105.7 for 106.0, another 76.8 for 77.0 - on beat
    markers, visibly late); held against every beat at once, the grid can't be off by that."""
    try:
        import numpy as np
    except ImportError:
        return guess
    env = np.asarray(onset, dtype=np.float64)
    env = env - env.mean()
    best, best_score = guess, -1e18
    for bpm in np.arange(guess - reach, guess + reach + step / 2, step):
        period = 60.0 * fps / bpm
        beats = np.arange(int((len(env) - 1) / period)) * period
        if len(beats) < 8:
            return guess
        phases = np.linspace(0.0, period, 24, endpoint=False)
        positions = (beats[None, :] + phases[:, None]).astype(int)
        positions = np.minimum(positions, len(env) - 1)
        score = env[positions].mean(axis=1).max()
        if score > best_score:
            best, best_score = float(bpm), score
    return best
