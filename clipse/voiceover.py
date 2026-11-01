"""Voiceover: Clipse records your microphone itself and puts the take on the timeline (2026-10-27: Resolve's own
couldn't find the mic on Linux - it asks the sound card, which PipeWire already holds, and a mic PipeWire makes
(a mono input split off an interface) isn't a sound card at all - "and maybe I want a little more options").

Through miniaudio, as the preview's sound: on Linux it records through PipeWire / PulseAudio, so it sees the
microphones the system lists. No Qt here - the pill on screen and the take's steps are voiceover_pill.py.

It can start when you speak (speech_started: the room's level is learnt as it listens), and the playhead moves
along while it records - from a program of its own, playhead.py. (Start with playback - Clipse watching for Space in
Resolve - was tried first, the same day, and didn't start for him: it went.)
"""
import os
import re
import threading
import time

RATE = 48000                 # what video uses
MAX_SECONDS = 30 * 60        # a take stops by itself after this (48 kHz floats: ~350 MB)
PERIOD_MS, PERIODS = 40, 8   # a chunk every 40 ms (the meter), 320 ms held while the app is busy (a Resolve call)
DEFAULT_FOLDER = os.path.join(os.path.expanduser("~"), "Music", "Clipse")
MONITOR = "Monitor of "      # PulseAudio's name for what an output plays - not a microphone
LEAD_SECONDS = 0.3           # starting when you speak: kept from before you were heard (the first sound of a word)
SPEECH_DB, OVER_ROOM_DB = -42.0, 15.0  # ...heard: louder than this, and than the room by this much


def available():
    try:
        import miniaudio  # noqa: F401
        import numpy  # noqa: F401
        return True
    except Exception:
        return False


def microphones():
    """The names of the inputs the system lists, in its order - without what an output plays."""
    try:
        import miniaudio
        return [d["name"] for d in miniaudio.Devices().get_captures() if not d["name"].startswith(MONITOR)]
    except Exception as e:
        print(f"[voiceover] couldn't list the microphones: {e}")
        return []


class Recorder:
    """The microphone, from start() to stop(): its sound kept as float chunks, with when each one came (so a
    moment on the clock is a place in the take - index_at). `level` is the loudest of the last chunk, 0-1."""

    def __init__(self, mic=""):
        self.mic = mic            # a name from microphones(); "" (or one that's gone): the system's own
        self.level = 0.0
        self._chunks = []         # numpy float32 arrays
        self._dropped = 0         # samples forgotten from the front (forget_before)
        self._count = 0           # samples since start, dropped ones too
        self._t0 = None           # when sample 0 was heard, on time.monotonic()'s clock
        self._lock = threading.Lock()
        self._device = None
        self._devices = None      # (kept alive: the device id belongs to it)

    def start(self):
        """None when it records, else why not."""
        import miniaudio
        device_id = None
        if self.mic:
            try:
                self._devices = miniaudio.Devices()
                device_id = next((d["id"] for d in self._devices.get_captures() if d["name"] == self.mic), None)
            except Exception:
                device_id = None
            if device_id is None:
                print(f"[voiceover] '{self.mic}' isn't there - the system's own microphone instead")
        try:
            self._device = miniaudio.CaptureDevice(miniaudio.SampleFormat.FLOAT32, 1, RATE, PERIOD_MS, device_id,
                                                   PERIODS, app_name="Clipse")
            listen = self._listen()
            next(listen)
            self._device.start(listen)
        except Exception as e:
            self._device = None
            return f"Couldn't open the microphone: {e}"
        return None

    def _listen(self):
        import numpy as np
        data = yield  # (primed with next(): each chunk the device hands over lands here)
        while True:
            now = time.monotonic()
            chunk = np.frombuffer(data, dtype=np.float32).copy()
            with self._lock:
                self._chunks.append(chunk)
                self._count += len(chunk)
                # The chunk's last sample was heard about now; the earliest such guess is the least late one.
                first = now - self._count / RATE
                self._t0 = first if self._t0 is None else min(self._t0, first)
            self.level = float(np.abs(chunk).max()) if len(chunk) else 0.0
            data = yield

    def loudness(self, seconds=0.1):
        """The last `seconds` of sound, in dBFS (its RMS) - -120 for none."""
        import numpy as np
        want = int(seconds * RATE)
        with self._lock:
            recent, have = [], 0
            for chunk in reversed(self._chunks):
                recent.append(chunk)
                have += len(chunk)
                if have >= want:
                    break
        if not recent:
            return -120.0
        sound = np.concatenate(recent[::-1])[-want:]
        return float(10 * np.log10(max(float(np.mean(np.square(sound, dtype=np.float64))), 1e-12)))

    @property
    def seconds(self):
        return self._count / RATE

    def index_at(self, moment):
        """The sample heard at `moment` (time.monotonic())."""
        return 0 if self._t0 is None else int(round((moment - self._t0) * RATE))

    def forget_before(self, moment):
        """Drops what came before `moment` - waiting for playback, only the last few seconds are needed."""
        keep_from = self.index_at(moment)
        with self._lock:
            while self._chunks and self._dropped + len(self._chunks[0]) < keep_from:
                self._dropped += len(self._chunks.pop(0))

    def cut(self, start=None, end=None):
        """The sound from sample `start` to `end` (None: from the first kept / to the last) as one float32 array -
        while it goes on recording."""
        import numpy as np
        with self._lock:
            sound = np.concatenate(self._chunks) if self._chunks else np.zeros(0, np.float32)
            dropped = self._dropped
        a = 0 if start is None else max(0, start - dropped)
        b = len(sound) if end is None else max(a, min(len(sound), end - dropped))
        return sound[a:b]

    def stop(self):
        if self._device is not None:
            try:
                self._device.close()
            except Exception:
                pass
            self._device = None
        with self._lock:
            self._chunks = []


def speech_started(level_db, room_db):
    """Is a voice heard: the last moment's level (Recorder.loudness) against the room's (the quietest so far)?"""
    return level_db > max(SPEECH_DB, room_db + OVER_ROOM_DB)


def kept_spans(start, end, pauses):
    """The (from, to) moments of a take from `start` to `end` without its pauses - [(paused, resumed or None)]."""
    spans, at = [], start
    for paused, resumed in pauses:
        if paused > at:
            spans.append((at, min(paused, end)))
        at = end if resumed is None else max(at, resumed)
    if at < end:
        spans.append((at, end))
    return [(a, b) for a, b in spans if b > a]


def trim_silence(sound, rate=RATE, margin=0.15):
    """(first, end) of `sound` with the quiet at its start and end left out - `margin` seconds kept around the
    voice. Judged in 100 ms steps (a click or a breath of the room isn't a word): quiet is 22 dB under the take's
    loudest step, and at least 12 dB over the room (its quietest tenth). The whole when nothing stands out.
    (2026-10-27: a fixed -55 dBFS kept a second of his room, which peaks at -53 between words.)"""
    import numpy as np
    window = rate // 50  # 20 ms
    count = len(sound) // window
    if count < 5:
        return 0, len(sound)
    power = np.mean(np.square(sound[:count * window].reshape(count, window), dtype=np.float64), axis=1)
    steps = np.convolve(power, np.ones(5) / 5, mode="same")  # each 20 ms with the 100 ms around it
    db = 10 * np.log10(np.maximum(steps, 1e-12))
    room = float(np.percentile(10 * np.log10(np.maximum(power, 1e-12)), 10))
    threshold = max(room + 12.0, float(db.max()) - 22.0)
    loud = np.flatnonzero(db > threshold)
    if not len(loud) or float(db.max()) < room + 12.0:
        return 0, len(sound)
    keep = int(margin * rate)
    return max(0, loud[0] * window - keep), min(len(sound), (loud[-1] + 1) * window + keep)


def write_wav(path, sound, rate=RATE):
    """`sound` (floats, -1 to 1) as a 24-bit mono WAV."""
    import wave
    import numpy as np
    whole = np.round(np.clip(sound, -1.0, 1.0) * 8388607).astype("<i4")
    data = whole.view(np.uint8).reshape(-1, 4)[:, :3].tobytes()  # (the low three bytes of each)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with wave.open(path, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(3)
        out.setframerate(rate)
        out.writeframes(data)


def folder(settings, project_name):
    """Where the takes go - and stay (a Media Pool clip is only a link to its file): Music/Clipse, or the
    folder on Settings > Scripts, then a folder of the project's name, as frame grabs."""
    from .stills import project_folder_name
    chosen = (settings.files.get("voice_folder") or "").strip()
    return os.path.join(os.path.expanduser(chosen) if chosen else DEFAULT_FOLDER, project_folder_name(project_name))


def next_name(where):
    """voiceover_01.wav, then _02 ...: the next number not in `where` yet (every take is kept)."""
    taken = set()
    try:
        for name in os.listdir(where):
            found = re.fullmatch(r"voiceover_(\d+)\.wav", name)
            if found:
                taken.add(int(found.group(1)))
    except OSError:
        pass
    n = max(taken, default=0) + 1
    return f"voiceover_{n:02d}.wav"
