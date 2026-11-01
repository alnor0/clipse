"""The sound under the mouse while you move through a clip (Settings ->
Preview -> Play the sound while moving through a clip).

Like scrubbing in an editor: every time the position changes, a short
piece of the sound from just there is played - about a tenth of a
second, faded in and out so it doesn't click. Move slowly and you hear
the clip in little steps; fast, and it's a blur of what's passing by.
That's what it's for: finding the word, the hit, the beat.

The clip's sound is read into memory once, in the background (mono, a
low sample rate - plenty for this), so any spot can be played at once.
"""
import threading
import time
from array import array

from .audio_preview import sound_device

RATE = 22050            # mono 16-bit: 2.6 MB a minute
MAX_SECONDS = 20 * 60   # beyond this a clip is silent while scrubbing
GRAIN = 0.11            # seconds of sound per step
FADE = 0.012            # ...faded in and out over this
MIN_GAP = 0.045         # steps closer together than this replace each other rather than queue up


class ScrubSound:
    def __init__(self, volume=lambda: 1.0):
        self.volume = volume      # () -> 0-1
        self.path = None
        self._samples = None      # array('h') once read
        self._generation = 0
        self._lock = threading.Lock()
        self._pending = None      # the piece to play next (the latest wins)
        self._device = None
        self._last = 0.0

    # -- reading the clip --
    def load(self, path, muted=()):
        """Starts reading `path`'s sound (nothing happens if it's the one in memory) - without the sound tracks
        switched off in the preview (`muted`, places 0 ...: a song's stems)."""
        muted = frozenset(muted or ())
        if not path or (path, muted) == (self.path, getattr(self, "_muted", frozenset())):
            return
        self.path, self._muted = path, muted
        self._samples = None
        self._generation += 1
        threading.Thread(target=self._read, args=(path, self._generation, muted), daemon=True).start()

    def _read(self, path, generation, muted=()):
        try:
            import av
            samples = array("h")
            from .audio_mix import decode_all
            with av.open(path) as container:
                if not container.streams.audio:
                    return
                # every sound track at once (a song's stems, a mic and the desktop)
                for chunk in decode_all(container, layout="mono", rate=RATE, muted=muted,
                                        stop=lambda: generation != self._generation or len(samples) >= RATE * MAX_SECONDS):
                    samples.frombytes(chunk)
                if generation != self._generation:
                    return  # another clip was asked for meanwhile
                del samples[RATE * MAX_SECONDS:]
            if generation == self._generation:
                self._samples = samples
        except Exception as e:
            print(f"[scrub sound] couldn't read {path}: {e}")

    # -- playing --
    def at(self, seconds):
        """The position moved to `seconds`: play the bit of sound there."""
        samples = self._samples
        if samples is None:
            return
        now = time.monotonic()
        start = max(0, int(seconds * RATE))
        piece = samples[start:start + int(GRAIN * RATE)]
        if len(piece) < 64:
            return
        gain = max(0.0, min(1.0, float(self.volume())))
        fade = min(int(FADE * RATE), len(piece) // 2)
        n = len(piece)
        for i in range(fade):
            k = gain * i / fade
            piece[i] = int(piece[i] * k)
            piece[n - 1 - i] = int(piece[n - 1 - i] * k)
        if gain < 0.999:
            for i in range(fade, n - fade):
                piece[i] = int(piece[i] * gain)
        with self._lock:
            self._pending = piece
            self._last = now
        if self._device is None:
            self._open()

    def _generator(self):
        playing, at = None, 0
        frames = yield b""
        while True:
            with self._lock:
                if self._pending is not None:  # a newer spot: straight to it
                    playing, at, self._pending = self._pending, 0, None
            out = array("h")
            if playing is not None:
                out = playing[at:at + frames]
                at += len(out)
                if at >= len(playing):
                    playing = None
            if len(out) < frames:
                out.extend(array("h", bytes(2 * (frames - len(out)))))
            frames = yield out

    def _open(self):
        try:
            import miniaudio
            gen = self._generator()
            next(gen)
            device = sound_device(sample_rate=RATE, nchannels=1)
            device.start(gen)
            self._device = device
        except Exception as e:
            print(f"[scrub sound] no sound device: {e}")
            self._device = False  # don't try again for this clip

    def quiet(self):
        """Scrubbing ended: let go of the sound device (the clip stays in memory)."""
        device, self._device = self._device, None
        with self._lock:
            self._pending = None
        if device:
            try:
                device.close()
            except Exception:
                pass

    def forget(self):
        """Another clip (or none): drop what was read."""
        self.quiet()
        self._generation += 1
        self.path, self._samples = None, None
