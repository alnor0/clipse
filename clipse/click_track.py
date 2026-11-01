"""A click where each clip starts - to hear a rhythm before it's on the timeline
(Insert as -> the gap curve -> Play).

The whole run is made up front: silence with a short, dry hit at every start
(a crack of noise over a short punch - see _hit), the first one a little
brighter, so the ear knows where it begins. Mono 16-bit, played through the
same sound device the picker listens with (miniaudio)."""
import math
import time
from array import array

from .audio_preview import sound_device

RATE = 22050
TICK = 0.03     # seconds a hit lasts - short and dry
TAIL = 0.35     # ...and of quiet after the last one, so it isn't cut off


def _hit(gain, bright=False, seed=7):
    """One hit: a burst of noise with a short punch under it, both gone within a few hundredths of
    a second - mostly the strike itself, almost nothing that keeps sounding after it. (Tried before
    this: a pure sine tick - "too much UI-like"; a struck block with a falling low body - "too much
    echo"; a click's edge over a low thud - "still slightly too much thud, and make it less light";
    a knock in the middle of the range - "less echo and more like a hit": a tone that rings, however
    briefly, is heard as an echo. So no steady tone here at all. A version halfway to a concrete impact
    - darker, with a low body of noise 110 ms long - was tried and taken back, 2026-10-15.)
    bright: the first one of a run, a little higher, so the ear knows where it begins."""
    import random
    rng = random.Random(seed)
    n = int(TICK * RATE)
    smooth, punch_from, punch_to = (0.55, 360.0, 170.0) if bright else (0.42, 300.0, 140.0)
    out, fast, slow, phase = [], 0.0, 0.0, 0.0
    for i in range(n):
        t = i / RATE
        white = rng.uniform(-1.0, 1.0)
        fast += smooth * (white - fast)       # noise without its hiss ...
        slow += 0.06 * (fast - slow)          # ... and without its rumble: the crack of a strike
        crack = (fast - slow) * math.exp(-330.0 * t) * 2.2
        pitch = punch_to + (punch_from - punch_to) * math.exp(-t / 0.004)   # falls, as a struck thing does
        phase += 2 * math.pi * pitch / RATE
        punch = math.sin(phase) * math.exp(-240.0 * t) * 0.42
        fade = min(1.0, (n - i) / (n * 0.3))  # the last third runs out to nothing
        out.append(int(32767 * gain * max(-1.0, min(1.0, (crack + punch) * fade))))
    return out


def _tick(pitch, gain):  # (kept for anything still asking by pitch: the first of a run is the higher one)
    return _hit(gain, bright=pitch > 1500.0)


def samples(times, gain=1.0):
    """array('h'): a tick at each of `times` (seconds from the start)."""
    times = sorted(max(0.0, float(t)) for t in times)
    if not times:
        return array("h")
    out = array("h", bytes(2 * int((times[-1] + TICK + TAIL) * RATE)))
    gain = max(0.0, min(1.0, gain)) * 0.8
    first, rest = _hit(gain, bright=True), _hit(gain)
    for n, t in enumerate(times):
        at = int(t * RATE)
        for i, value in enumerate(first if n == 0 else rest):
            if at + i < len(out):  # ticks closer together than one lasts add up
                out[at + i] = max(-32767, min(32767, out[at + i] + value))
    return out


def available():
    try:
        import miniaudio  # noqa: F401
        return True
    except Exception:
        return False


class ClickTrack:
    def __init__(self, volume=lambda: 1.0):
        self.volume = volume   # () -> 0-1
        self._device = None
        self._started = 0.0
        self.length = 0.0      # seconds the run lasts

    @property
    def playing(self):
        return self._device is not None and self.position() < self.length

    def position(self):
        """Seconds since it started."""
        return time.monotonic() - self._started

    def play(self, times):
        """Plays a tick at each of `times`. None when it does, else why it can't."""
        self.stop()
        data = samples(times, self.volume())
        if not len(data):
            return "Nothing to play - there are no gaps yet."
        try:
            import miniaudio
        except Exception:
            return "No sound here: the miniaudio library is missing."

        def run():
            at = 0
            frames = yield b""
            while True:
                out = data[at:at + frames]
                at += len(out)
                if len(out) < frames:
                    out.extend(array("h", bytes(2 * (frames - len(out)))))
                frames = yield out
        try:
            gen = run()
            next(gen)
            device = sound_device(sample_rate=RATE, nchannels=1)
            device.start(gen)
        except Exception as e:
            return f"No sound device: {e}"
        self._device, self._started, self.length = device, time.monotonic(), len(data) / RATE
        return None

    def stop(self):
        device, self._device = self._device, None
        if device:
            try:
                device.close()
            except Exception:
                pass
