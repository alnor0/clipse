"""Listening to your sounds once, so the picker knows more than their names.

For every audio file (run from Settings -> General -> Music & sound
effects -> Analyse sounds; nothing happens behind your back):

  all sounds   a "sound fingerprint" - how the sound is spread over low to
               high, how noisy or tonal it is, how it starts and fades,
               how long it is. Sounds with close fingerprints sound alike
               (`similar`): the picker's "Sounds like this" (Ctrl+L, like:) - by sound, not by name.
  music        BPM (bpm.py), musical key, mood words (calm / steady /
               energetic, plus uplifting / warm / tense / dark /
               melancholic) and a clean loop: two points a whole number of
               bars apart that sound the same, so the part in between
               repeats seamlessly (Alt+L marks it in the preview).

A long clip whose name doesn't say what it is counts as music when it
has a steady beat. Results are kept in sound_analysis.json (paths.cache)
(per file, by size and date), so each file is analysed once.

Mood and key are estimates from the sound alone - good for narrowing a
search ("m: calm"), not a music theory exam.
"""
import json
import math
import os
import threading
from array import array
from . import paths

CACHE_FILE = paths.cache("sound_analysis.json")
VERSION = 4  # (4: tempos to a twentieth of a BPM - bpm._fit; what was measured before is measured again)
RATE = 11025
N_FFT = 1024
HOP = 256
MAX_SECONDS = 360           # music: the first 6 minutes are plenty
BANDS = 24
LOW_HZ, HIGH_HZ = 40.0, 5400.0

MAX_ENTRIES = 20000         # (each sound a line - a few MB at most; the last used kept)
_lock = threading.Lock()
_cache = None
_by_time = {}  # "path|modified" -> its key: a file whose size alone changed (a tag: file_tags.py) is the same sound


def available():
    """numpy and PyAV are installed (the installers add them; without them
    there's simply no analysis)."""
    from importlib.util import find_spec
    return find_spec("numpy") is not None and find_spec("av") is not None


# -- the cache --
def _load():
    global _cache
    if _cache is None:
        loaded = paths.read_json(CACHE_FILE, {})
        # what an older version measured is measured again, so it goes; past MAX_ENTRIES the ones not used longest
        kept = [(k, v) for k, v in loaded.items() if isinstance(v, dict) and v.get("v") == VERSION] \
            if isinstance(loaded, dict) else []
        _cache = dict(kept[-MAX_ENTRIES:])
        _by_time.update((k.rsplit("|", 2)[0] + "|" + k.rsplit("|", 1)[1], k) for k in _cache)
    return _cache


def _key(path):
    try:
        st = os.stat(path)
        return f"{path}|{st.st_size}|{int(st.st_mtime)}"
    except OSError:
        return None


def cached(path):
    """The analysis of this file (unchanged since), or None. Can be
    "partial" (only levels, from trimming silence on insert) - see
    complete()."""
    key = _key(path) if path else None
    if not key:
        return None
    with _lock:
        cache = _load()
        hit = cache.get(key)
        if hit is None:  # (tags keep the modified time, and change the size)
            hit = cache.get(_by_time.get(key.rsplit("|", 2)[0] + "|" + key.rsplit("|", 1)[1]))
    return hit if isinstance(hit, dict) and hit.get("v") == VERSION else None


def _asked_as_effect(hit, music):
    """It's music now, and was analysed as a sound effect: its tempo and energy were never asked for."""
    return music is True and "bpm" not in hit


def complete(hit, music=None):
    """Fully analysed - including what was added in 1.32 (where the sound
    starts and ends, the beat grid)."""
    return (bool(hit) and not hit.get("error") and not hit.get("partial") and "peak" in hit and "clips" in hit
            and not (hit.get("bpm") and "beat_bpm" not in hit) and not _asked_as_effect(hit, music))


def _store(path, result):
    key = _key(path)
    if not key:
        return
    with _lock:
        cache = _load()
        same = key.rsplit("|", 2)[0] + "|" + key.rsplit("|", 1)[1]
        cache.pop(_by_time.get(same), None)
        cache.pop(key, None)  # (last in the file: kept longest)
        cache[key] = result
        _by_time[same] = key
        while len(cache) > MAX_ENTRIES:
            del cache[next(iter(cache))]
        try:
            paths.write_json(CACHE_FILE, cache, separators=(",", ":"))
        except OSError:
            pass


# -- reading the file --
BLOCKS_PER_SECOND = 200   # 5 ms resolution for finding where the sound starts and ends


class _Levels:
    """Peak and a 5 ms envelope - for where a sound really starts and ends.
    Measured on the file's own samples (the analysis itself works on a
    smoothed 11 kHz copy)."""

    def __init__(self):
        self.peak = 0.0
        self.flat = 0  # samples sitting on the ceiling right after another one: flattened tops = clipping
        self.envelope = []
        self._rest = None
        self._block = None
        self.complete = True  # False when only the first part of the file was read

    @staticmethod
    def _samples(frame):
        import numpy as np
        a = frame.to_ndarray()
        name = frame.format.name.rstrip("p")
        if name == "u8":
            a = (a.astype(np.float32) - 128.0) / 128.0
        elif name == "s16":
            a = a.astype(np.float32) / 32768.0
        elif name == "s32":
            a = a.astype(np.float32) / 2147483648.0
        else:
            a = a.astype(np.float32)
        channels = len(frame.layout.channels) or 1
        if frame.format.is_planar:
            a = np.abs(a).max(axis=0)
        else:
            a = np.abs(a.reshape(-1, channels)).max(axis=1)
        return a

    def add(self, frame):
        import numpy as np
        a = self._samples(frame)
        if not len(a):
            return
        if self._block is None:
            self._block = max(1, int(frame.sample_rate or 48000) // BLOCKS_PER_SECOND)
        self.peak = max(self.peak, float(a.max()))
        top = a >= 0.999
        self.flat += int((top[1:] & top[:-1]).sum())
        if self._rest is not None:
            a = np.concatenate((self._rest, a))
        whole = len(a) // self._block * self._block
        if whole:
            self.envelope.extend(a[:whole].reshape(-1, self._block).max(axis=1).tolist())
        self._rest = a[whole:]

    def result(self):
        """{"peak": dBFS, "sound": [start s, end s or None]}."""
        import math
        env = self.envelope + ([float(self._rest.max())] if self._rest is not None and len(self._rest) else [])
        peak_db = round(20 * math.log10(self.peak), 1) if self.peak > 1e-6 else -120.0
        out = {"peak": peak_db, "clips": self.flat}
        if env and self.peak > 1e-6:
            # the loudest moment (seconds into the file): what At every marker can put on the marker
            out["loudest"] = round(max(range(len(env)), key=env.__getitem__) / BLOCKS_PER_SECOND, 3)
            # where it's audible: within 45 dB of the loudest moment (and above -65 dBFS)
            threshold = max(self.peak * 10 ** (-45 / 20), 10 ** (-65 / 20))
            loud = [i for i, v in enumerate(env) if v >= threshold]
            if loud:
                start = max(0, loud[0] - 3) / BLOCKS_PER_SECOND          # 15 ms of lead-in
                end = min(len(env), loud[-1] + 13) / BLOCKS_PER_SECOND    # 60 ms of tail
                out["sound"] = [round(start, 3), round(end, 3) if self.complete else None]
        return out


def _decode(path, seconds, levels=None):
    import av
    import numpy as np
    from .audio_mix import audio_streams, decode_all
    container = av.open(path)
    try:
        several = len(audio_streams(container)) > 1
        parts, total, limit = [], 0, int(RATE * seconds)
        cut = [False]

        def measure(frame, stream):  # one track: the levels from the file's own samples
            if levels is not None and not several:
                levels.add(frame)

        def enough():
            cut[0] = total >= limit
            return cut[0]

        # every sound track at once (a song's stems, a mic and the desktop)
        for out in decode_all(container, layout="mono", rate=RATE, stop=enough, each=measure):
            chunk = np.frombuffer(out, dtype=np.int16)
            if levels is not None and several:  # several: from what's heard, every track together
                frame = av.AudioFrame.from_ndarray(chunk.reshape(1, -1), format="s16", layout="mono")
                frame.sample_rate = RATE
                levels.add(frame)
            parts.append(chunk)
            total += len(chunk)
        if cut[0] and levels is not None:
            levels.complete = False
        return np.concatenate(parts)[:limit] if parts else np.zeros(0, dtype=np.int16)
    finally:
        container.close()


def _spectrogram(x):
    import numpy as np
    if len(x) < N_FFT:
        x = np.pad(x, (0, N_FFT - len(x)))
    frames = np.lib.stride_tricks.sliding_window_view(x, N_FFT)[::HOP]
    window = np.hanning(N_FFT).astype(np.float32)
    return (np.abs(np.fft.rfft(frames * window, axis=1)) ** 2).astype(np.float32)  # (frames, bins)


def _band_matrix():
    import numpy as np
    freqs = np.fft.rfftfreq(N_FFT, 1.0 / RATE)
    edges = np.geomspace(LOW_HZ, HIGH_HZ, BANDS + 1)
    m = np.zeros((BANDS, len(freqs)), dtype=np.float32)
    for b in range(BANDS):
        sel = (freqs >= edges[b]) & (freqs < edges[b + 1])
        if not sel.any():  # very narrow low band: nearest bin
            sel = np.abs(freqs - math.sqrt(edges[b] * edges[b + 1])) == np.abs(
                freqs - math.sqrt(edges[b] * edges[b + 1])).min()
        m[b, sel] = 1.0
    return m, freqs


# -- the fingerprint (all sounds) --
_MEL = {}


def _mel_matrix(n_mels=40):
    """Triangular mel filters (the way ears space pitch) from 40 Hz to 5.4 kHz."""
    import numpy as np
    if n_mels in _MEL:
        return _MEL[n_mels]
    freqs = np.fft.rfftfreq(N_FFT, 1.0 / RATE)

    def mel(f):
        return 2595 * np.log10(1 + f / 700.0)

    def hz(m):
        return 700 * (10 ** (m / 2595.0) - 1)
    points = hz(np.linspace(mel(LOW_HZ), mel(HIGH_HZ), n_mels + 2))
    m = np.zeros((n_mels, len(freqs)), dtype=np.float32)
    for i in range(n_mels):
        lo, mid, hi = points[i], points[i + 1], points[i + 2]
        up = (freqs - lo) / max(mid - lo, 1e-6)
        down = (hi - freqs) / max(hi - mid, 1e-6)
        m[i] = np.clip(np.minimum(up, down), 0, None)
    _MEL[n_mels] = m
    return m


def _dct(x, n):
    """DCT-II of the rows of x, first n coefficients (MFCCs from log-mel)."""
    import numpy as np
    k = x.shape[1]
    basis = np.cos(np.pi / k * (np.arange(k)[None, :] + 0.5) * np.arange(n)[:, None])
    return x @ basis.T


def _fingerprint(spec, x):
    """How the sound sounds, in four groups of numbers - independent of
    its name and its level:
      timbre    MFCCs: the "colour" of the sound (what makes a whoosh a whoosh)
      spectral  brightness, spread, noisiness, peaks vs valleys, buzz
      envelope  how it starts, swells, fades and how long it is - and
                whether it rises or falls in pitch over time (risers vs drops)
      motion    hits per second, punch, how tonal it is
    """
    import numpy as np
    freqs = np.fft.rfftfreq(N_FFT, 1.0 / RATE)
    power = spec.sum(axis=1) + 1e-12
    n = len(power)
    loud = power > power.max() * 1e-3
    if loud.sum() < 2:
        loud = np.ones_like(power, dtype=bool)
    s = spec[loud]

    # timbre
    mel_db = 10 * np.log10(s @ _mel_matrix().T + 1e-10)
    mfcc = _dct(mel_db, 14)[:, 1:]                     # without c0 (that's just loudness)
    timbre = list(mfcc.mean(axis=0) / 10) + list(mfcc.std(axis=0) / 10)

    # spectral
    total = s.sum(axis=1) + 1e-12
    centroid = (s * freqs).sum(axis=1) / total
    spread = np.sqrt((s * (freqs[None, :] - centroid[:, None]) ** 2).sum(axis=1) / total)
    cum = np.cumsum(s, axis=1)
    rolloff = freqs[np.minimum((cum < 0.85 * cum[:, -1:]).sum(axis=1), len(freqs) - 1)]
    flat = np.exp(np.log(s + 1e-12).mean(axis=1)) / (s.mean(axis=1) + 1e-12)
    octaves = [(80, 160), (160, 320), (320, 640), (640, 1280), (1280, 2560), (2560, 5400)]
    contrast = []
    for lo, hi in octaves:
        sel = (freqs >= lo) & (freqs < hi)
        band = 10 * np.log10(s[:, sel] + 1e-12)
        contrast.append(float((np.percentile(band, 90, axis=1) - np.percentile(band, 20, axis=1)).mean() / 10))
    signs = np.signbit(x[: RATE * 60])
    zcr = float(np.count_nonzero(signs[1:] != signs[:-1]) / max(1, len(signs) - 1))
    spectral = [
        float(np.log2(np.median(centroid) + 1)),
        float(np.log2(np.percentile(centroid, 90) + 1) - np.log2(np.percentile(centroid, 10) + 1)),
        float(np.log2(np.median(spread) + 1)), float(np.log2(np.median(rolloff) + 1)),
        float(flat.mean()), float(flat.std()), *contrast, float(np.sqrt(zcr) * 4),
    ]

    # envelope (over the whole sound)
    env = 10 * np.log10(power)
    env = np.clip(env - env.max(), -60, 0) / 60 + 1                # 1 = the peak, 0 = 60 dB down
    points = np.interp(np.linspace(0, n - 1, 12), np.arange(n), env)
    fps = RATE / HOP
    peak = int(np.argmax(env))
    after = np.nonzero(env[peak:] < 1 - 20 / 60)[0]
    decay = (after[0] if len(after) else n - peak) / fps
    secs = len(x) / RATE
    cen_all = (spec * freqs).sum(axis=1) / (spec.sum(axis=1) + 1e-12)
    quarters = [cen_all[i * n // 4:max(i * n // 4 + 1, (i + 1) * n // 4)] for i in range(4)]
    weights_q = [power[i * n // 4:max(i * n // 4 + 1, (i + 1) * n // 4)] for i in range(4)]
    cen_q = [float(np.average(c, weights=w)) if w.sum() > 0 else 0.0 for c, w in zip(quarters, weights_q)]
    mid = np.log2(np.median(centroid) + 1)
    envelope = list(points) + [
        float(np.log2(peak / fps + 0.01)), float(np.log2(decay + 0.01)),
        float((env > 1 - 10 / 60).mean()), float(math.log2(secs + 0.1)),
        *[float(np.log2(c + 1) - mid) for c in cen_q],              # rises / falls in pitch
    ]

    # motion
    mel_flux = np.maximum(0, np.diff(mel_db, axis=0)).sum(axis=1) if len(mel_db) > 1 else np.zeros(1)
    onsets = int((mel_flux > mel_flux.mean() + 2 * mel_flux.std()).sum()) if len(mel_flux) > 2 else 0
    chroma = _chroma(s)
    tonal = float(chroma.max(axis=1).mean())
    motion = [float(math.log2(onsets / max(secs, 0.1) + 1)), float((10 * np.log10(power)).std() / 10), tonal]

    r = lambda values: [round(float(v), 4) for v in values]  # noqa: E731
    return {"timbre": r(timbre), "spectral": r(spectral), "envelope": r(envelope), "motion": r(motion)}


# -- music: key, mood, loop --
_MAJOR = [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88]
_MINOR = [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17]
_NOTES = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]


def _chroma(spec):
    import numpy as np
    freqs = np.fft.rfftfreq(N_FFT, 1.0 / RATE)
    sel = (freqs >= 80) & (freqs <= 2000)
    pcs = (np.round(12 * np.log2(freqs[sel] / 440.0) + 69).astype(int)) % 12
    m = np.zeros((12, sel.sum()), dtype=np.float32)
    m[pcs, np.arange(sel.sum())] = 1.0
    c = spec[:, sel] @ m.T                                             # (frames, 12)
    return c / (c.sum(axis=1, keepdims=True) + 1e-12)


def _key_of(chroma, spec):
    import numpy as np
    weights = spec.sum(axis=1)
    profile = (chroma * weights[:, None]).sum(axis=0)
    if (profile >= 0.5 * profile.max()).sum() < 3:
        return (0.0, "", "")  # one or two notes dominate (a drum, a drone): no key to speak of
    best = (-2.0, "", "")
    for tonic in range(12):
        for mode, template in (("major", _MAJOR), ("minor", _MINOR)):
            r = float(np.corrcoef(profile, np.roll(template, tonic))[0, 1])
            if r > best[0]:
                best = (r, _NOTES[tonic], mode)
    return best  # (how sure, note, mode)


def _mood(bpm, fingerprint, mode, spec):
    import numpy as np
    freqs = np.fft.rfftfreq(N_FFT, 1.0 / RATE)
    centroid = float(np.median((spec * freqs).sum(axis=1) / (spec.sum(axis=1) + 1e-12)))
    onset_rate = 2 ** fingerprint["motion"][0] - 1
    punch = fingerprint["motion"][1] * 10

    def scale(v, lo, hi):
        return max(0.0, min(1.0, (v - lo) / (hi - lo)))
    energy = 0.35 * scale(onset_rate, 0.8, 5.0) + 0.3 * scale(bpm or 90, 70, 150) \
        + 0.2 * scale(centroid, 700, 2600) + 0.15 * scale(punch, 3, 12)
    level = "calm" if energy < 0.36 else "energetic" if energy > 0.62 else "steady"
    bright = centroid > 1300
    if mode == "major":
        tone = "uplifting" if bright else "warm"
    elif mode == "minor":
        tone = "melancholic" if level == "calm" else "tense" if bright else "dark"
    else:
        tone = ""
    return round(energy, 2), [w for w in (level, tone) if w]


def _beat_grid(spec, bpm):
    """Frame index of every beat: the phase where the onsets line up best."""
    import numpy as np
    flux = np.maximum(0, np.diff(np.log1p(spec[:, :120]), axis=0)).sum(axis=1)
    fps = RATE / HOP
    period = 60.0 * fps / bpm
    best_phase, best = 0.0, -1.0
    for phase in np.arange(0, period, 0.5):
        idx = np.arange(phase, len(flux) - 1, period).astype(int)
        score = flux[idx].mean() if len(idx) else 0
        if score > best:
            best_phase, best = phase, score
    return np.arange(best_phase, len(spec) - 1, period)


def _loop(spec, chroma, bpm):
    """(start s, end s, bars) of the cleanest whole-bar loop, or None."""
    import numpy as np
    beats = _beat_grid(spec, bpm)
    if len(beats) < 24:
        return None
    bands_m, _f = _band_matrix()
    bands = np.log10(spec @ bands_m.T + 1e-10)
    feats = np.hstack([chroma * 3, bands])
    edges = beats.astype(int)
    per_beat = np.array([feats[a:b].mean(axis=0) for a, b in zip(edges[:-1], edges[1:]) if b > a])
    per_beat = (per_beat - per_beat.mean(axis=0)) / (per_beat.std(axis=0) + 1e-6)
    norms = np.linalg.norm(per_beat, axis=1) + 1e-9
    unit = per_beat / norms[:, None]
    n_beats = len(unit)
    fps = RATE / HOP
    best = None
    for bars in (16, 8, 4, 2):
        span = bars * 4
        for bar in range(1, (n_beats - span - 4) // 4 + 1):
            a = bar * 4
            b = a + span
            if b + 4 > n_beats:
                break
            # the beats just before and after each point must match: then the cut is seamless
            sim = float((unit[a - 2:a + 4] * unit[b - 2:b + 4]).sum(axis=1).mean())
            if best is None or sim > best[0] + (0.04 if bars < best[3] else 0):
                if sim > 0.55:
                    best = (sim, a, b, bars)
        if best is not None and best[3] == bars and best[0] > 0.8:
            break  # a clean long loop: no need for shorter ones
    if best is None:
        return None
    _sim, a, b, bars = best
    delay = (N_FFT / 2 + 0.75 * HOP) / RATE  # see _beat0
    return [round(float(beats[a] / fps) + delay, 3), round(float(beats[b] / fps) + delay, 3), bars]


# -- the whole analysis --
def analyse(path, music, retry_errors=False):
    """Analyses one file (or returns the stored result). music: True =
    known music, False = a sound effect (fingerprint only), None = unsure
    (music if it has a steady beat). Returns the result dict ({"error":
    "..."} if the file couldn't be analysed), or None if the libraries
    aren't installed."""
    hit = cached(path)
    if hit is not None and (complete(hit, music) or (hit.get("error") and not retry_errors)):
        return hit
    if not available():
        return hit
    try:
        if hit is not None and not hit.get("error") and not hit.get("partial") and not _asked_as_effect(hit, music):
            result = _upgrade(path, hit)  # analysed by an older version: just add what's new
        else:
            result = _analyse(path, music)
    except Exception as e:  # one odd file never stops the rest
        import traceback
        print(f"[analyse] couldn't analyse {os.path.basename(path)}: {e}")
        traceback.print_exc()
        result = {"v": VERSION, "error": str(e) or e.__class__.__name__}
    _store(path, result)
    return result


def _beat0(spec, bpm):
    """Seconds to the first beat - with the tempo, the beat grid drawn over
    the waveform."""
    beats = _beat_grid(spec, bpm)
    if not len(beats):
        return 0.0
    # a beat shows up in the onset curve a little before it's heard: the
    # analysis window starts before its middle (measured on click tracks)
    delay = (N_FFT / 2 + 0.75 * HOP) / RATE
    return round((float(beats[0]) * HOP / RATE + delay) % (60.0 / bpm), 3)


def _beat_lines(spec, bpm):
    """(tempo, seconds to the first beat) for the beat lines over the
    waveform. The tempo found from the first part of a song is right to
    about a tenth of a beat a minute - close enough to show as a number,
    but lines drawn from it slide off the beat over a few minutes. So the
    tempo is tuned here against the whole song: the one within 1.2 %
    whose lines sit on the most onsets from start to end."""
    import numpy as np
    flux = np.maximum(0, np.diff(np.log1p(spec[:, :120]), axis=0)).sum(axis=1)
    if len(flux) < 8:
        return bpm, 0.0
    flux = np.maximum(flux, np.concatenate((flux[1:], flux[-1:])))  # a line a frame early still counts
    fps = RATE / HOP
    base = 60.0 * fps / bpm
    best = (-1.0, base, 0.0)
    plain = -1.0
    for period in base * (1.0 + np.linspace(-0.012, 0.012, 97)):
        for phase in np.arange(0, period, 0.5):
            idx = np.arange(phase, len(flux) - 1, period).astype(int)
            score = float(flux[idx].mean()) if len(idx) else 0.0
            if score > best[0]:
                best = (score, period, phase)
            if period == base and score > plain:
                plain = score
    score, period, phase = best
    if score < plain * 1.03:  # no clear winner: the tempo as found
        return bpm, _beat0(spec, bpm)
    delay = (N_FFT / 2 + 0.75 * HOP) / RATE  # see _beat0
    seconds = period / fps  # one beat
    return round(60.0 / seconds, 3), round((phase * HOP / RATE + delay) % seconds, 3)


def _upgrade(path, hit):
    import numpy as np
    levels = _Levels()
    raw = _decode(path, MAX_SECONDS if hit.get("bpm") else 120, levels)
    result = dict(hit)
    result.update(levels.result())
    result.pop("partial", None)
    if hit.get("bpm") and "beat_bpm" not in hit and len(raw) >= RATE * 8:
        result["beat_bpm"], result["beat0"] = _beat_lines(_spectrogram(raw.astype(np.float32) / 32768.0), hit["bpm"])
    return result


def levels_only(path, seconds=120):
    """Where the sound starts and ends - quick, for
    trimming silence on insert before the sound has been analysed. Kept
    (as a partial result) so the next insert doesn't read the file again."""
    hit = cached(path)
    if hit is not None and ("sound" in hit or "peak" in hit or hit.get("error")):
        return hit
    if not available():
        return None
    try:
        levels = _Levels()
        _decode(path, seconds, levels)
        result = levels.result()
    except Exception as e:
        print(f"[levels] couldn't read {os.path.basename(path)}: {e}")
        return None
    # kept with what's known already (an analysis from before 1.32), or as a
    # partial result that Analyse sounds completes later
    result = dict(hit, **result) if hit is not None else {"v": VERSION, "partial": True, **result}
    _store(path, result)
    return result


def loudest(path, seconds=120):
    """Seconds into the file where its sound is loudest, or None (no sound, or nothing can read it).
    Kept with the rest of what's known about the file; a file looked at before this was kept is read
    again once - just its levels, quickly."""
    hit = cached(path)
    if hit is not None and "loudest" in hit:
        return hit["loudest"]
    if hit is not None and hit.get("error") or not available():
        return None
    try:
        levels = _Levels()
        _decode(path, seconds, levels)
        result = levels.result()
    except Exception as e:
        print(f"[levels] couldn't read {os.path.basename(path)}: {e}")
        return None
    if hit is not None:  # (only what's new: a complete analysis stays complete)
        result = dict(hit, loudest=result.get("loudest"))
    else:
        result = {"v": VERSION, "partial": True, "loudest": None, **result}
    _store(path, result)
    return result.get("loudest")


def _analyse(path, music):
    import numpy as np
    from . import bpm as bpm_mod
    levels = _Levels()
    raw = _decode(path, MAX_SECONDS if music is not False else 120, levels)
    x = raw.astype(np.float32) / 32768.0
    result = {"v": VERSION, "secs": round(len(x) / RATE, 2), **levels.result()}
    if len(x) < RATE * 0.05:
        result["features"] = None  # too short to say anything about
        return result
    spec = _spectrogram(x)
    result["features"] = _fingerprint(spec, x)
    if music is not False and len(x) >= RATE * 8:
        tempo = bpm_mod.tempo(array("h", raw[: RATE * bpm_mod.SECONDS].tobytes()))  # same sample rate
        if music is None:
            result["music"] = bool(tempo)
        if music or tempo:
            result["bpm"] = tempo
            chroma = _chroma(spec)
            sure, note, mode = _key_of(chroma, spec)
            if sure > 0.7:
                result["key"] = f"{note} {mode}"
            result["energy"], result["mood"] = _mood(tempo, result["features"], mode if sure > 0.7 else "", spec)
            if tempo:
                result["loop"] = _loop(spec, chroma, tempo)
                result["beat_bpm"], result["beat0"] = _beat_lines(spec, tempo)
    return result


# how much each part of the fingerprint counts when comparing two sounds
GROUP_WEIGHTS = {"timbre": 0.36, "spectral": 0.22, "envelope": 0.27, "motion": 0.15}


def similar(target, others):
    """How alike `target`'s fingerprint is to each of `others` (dict
    key -> fingerprint): [(key, 0-100)], most alike first.

    Each group (timbre, spectral, envelope, motion) is compared on its
    own, with every number scaled by how much it varies across your
    library (so no single number dominates), and the groups are then
    weighted: what it sounds like counts most, then how it moves over
    time, then brightness and texture."""
    import numpy as np
    keys = [k for k, f in others.items() if isinstance(f, dict)]
    if not keys or not isinstance(target, dict):
        return []
    total = np.zeros(len(keys))
    weight_sum = 0.0
    for group, weight in GROUP_WEIGHTS.items():
        t = np.array(target.get(group) or [], dtype=np.float64)
        rows = [others[k].get(group) or [] for k in keys]
        if not len(t) or any(len(r) != len(t) for r in rows):
            continue
        m = np.array(rows, dtype=np.float64)
        both = np.vstack([m, t])
        mean, std = both.mean(axis=0), both.std(axis=0)
        std = np.where(std < 1e-6, 1.0, std)
        d = np.sqrt((((m - mean) / std - (t - mean) / std) ** 2).mean(axis=1))
        total += weight * d
        weight_sum += weight
    if weight_sum == 0:
        return []
    dist = total / weight_sum
    score = np.clip(100 * np.exp(-0.75 * dist ** 1.5), 0, 100)
    order = np.argsort(-score)
    return [(keys[i], int(round(score[i]))) for i in order]


def beats(path):
    """(tempo, seconds to the first beat) of this file for Mark the beats, analysing it if it hasn't been, as music
    whatever it was taken for. None when it has no steady beat."""
    hit = analyse(path, True, retry_errors=True)
    if not hit or hit.get("error") or not hit.get("bpm") or "beat0" not in hit:
        return None
    return float(hit.get("beat_bpm") or hit["bpm"]), float(hit["beat0"])


def bar_start(path, bpm, beat0, every=4):
    """Which beat a bar starts on, 0 to every - 1, counted from beat0: the one with the most going on across the song -
    the lows hitting and the harmony changing. A guess, kept with the analysis: music tends to lean on it."""
    hit = cached(path)
    if hit is not None and "bar0" in hit:
        return int(hit["bar0"])
    try:
        import numpy as np
        raw = _decode(path, MAX_SECONDS)
        spec = _spectrogram(raw.astype(np.float32) / 32768.0)
        frames_a_second = RATE / HOP
        low = np.maximum(0, np.diff(np.log1p(spec[:, 3:15]), axis=0)).sum(axis=1)
        chroma = _chroma(spec)
        period = 60.0 / bpm * frames_a_second
        width = max(1, int(period))
        scores_low, scores_change = np.zeros(every), np.zeros(every)
        beat, n = beat0 * frames_a_second, 0
        while beat + width < spec.shape[0] - 1:
            at = int(beat)
            scores_low[n % every] += low[max(0, at - 1):at + 3].max(initial=0)
            if at >= width:
                before, after = chroma[at - width:at].mean(axis=0), chroma[at:at + width].mean(axis=0)
                scale = float(np.linalg.norm(before) * np.linalg.norm(after)) or 1.0
                scores_change[n % every] += 1.0 - float(before @ after) / scale
            beat += period
            n += 1

        def share(scores):
            return scores / scores.sum() if scores.sum() > 0 else scores
        best = int(np.argmax(share(scores_low) + share(scores_change)))
    except Exception as e:
        print(f"[analyse] couldn't find the bars of {os.path.basename(path)}: {e}")
        return 0
    if hit is not None:
        _store(path, dict(hit, bar0=best))
    return best
