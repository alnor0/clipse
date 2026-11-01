"""Every sound track of a file heard together.

A file can hold several sound tracks (a song's stems, a recording's mic and
desktop sound); Resolve plays them all at once. Each track is decoded and
resampled by itself, lined up by its own time, and added together - what
comes out is 16-bit at the rate and layout asked for.
"""


def _numpy():
    try:
        import numpy
        return numpy
    except Exception:  # without numpy only the first track is heard
        return None

# How far one track may run ahead of another before the one behind counts as
# silent there (a track that has stopped, or gives nothing): the rest isn't held up.
WAIT_LIMIT = 1.0  # seconds


def audio_streams(container):
    """The file's sound tracks - all of them where they can be mixed, else the first."""
    streams = list(container.streams.audio)
    return streams if _numpy() is not None else streams[:1]


class Mix:
    """Frames of any of `streams` in, the tracks added together out (bytes of int16)."""

    def __init__(self, streams, layout="stereo", rate=48000, start=0.0, muted=()):
        import av
        self._muted = {s.index for n, s in enumerate(streams) if n in set(muted or ())}  # (by place: 0 ...) silent
        self.rate = rate
        self.channels = 1 if layout == "mono" else 2
        self.start = float(start or 0.0)  # the first sample handed out is this moment of the file
        self.made = 0                     # samples (per channel) handed out so far
        self._resamplers = {s.index: av.AudioResampler(format="s16", layout=layout, rate=rate) for s in streams}
        self._waiting = {s.index: [] for s in streams}   # resampled, not yet mixed
        self._skip = {}                                  # per track: samples to drop before `start` (< 0: silence first)
        self._ended = set()

    @property
    def seconds(self):
        """The moment of the file the sound handed out so far reaches."""
        return self.start + self.made / self.rate

    def push(self, frame, stream):
        """A decoded frame of `stream`; answers what can be mixed now (maybe b"")."""
        key = stream.index
        resampler = self._resamplers.get(key)
        if resampler is None:
            return b""
        if key not in self._skip:
            t = float(frame.time) if frame.time is not None else self.start
            self._skip[key] = int(round((self.start - t) * self.rate))
        for f in resampler.resample(frame):
            self._take(key, bytes(f.planes[0])[: f.samples * 2 * self.channels])
        return self._mix()

    def finish(self):
        """The file has ended: the rest of every track."""
        for key, resampler in self._resamplers.items():
            if key in self._ended:
                continue
            try:
                for f in resampler.resample(None):
                    self._take(key, bytes(f.planes[0])[: f.samples * 2 * self.channels])
            except Exception:
                pass
            self._ended.add(key)
        return self._mix(final=True)

    def _take(self, key, data):
        if not data or key in self._ended:
            return
        skip = self._skip.get(key, 0)
        if skip < 0:  # this track starts after `start`: silence until it does
            data = bytes(-skip * 2 * self.channels) + data
            self._skip[key] = 0
        elif skip > 0:  # before `start`: dropped
            n = len(data) // (2 * self.channels)
            drop = min(n, skip)
            self._skip[key] = skip - drop
            data = data[drop * 2 * self.channels:]
            if not data:
                return
        self._waiting[key].append(data)

    def _mix(self, final=False):
        keys = list(self._waiting)
        if len(keys) == 1 and not self._muted:  # one track: as it comes
            out = b"".join(self._waiting[keys[0]])
            self._waiting[keys[0]] = []
            self.made += len(out) // (2 * self.channels)
            return out
        width = 2 * self.channels
        have = {k: sum(len(c) for c in self._waiting[k]) // width for k in keys}
        if final:
            n = max(have.values())
        else:
            live = [have[k] for k in keys if k not in self._ended]
            n = min(live) if live else max(have.values())
            if n == 0 and max(have.values()) > WAIT_LIMIT * self.rate:
                # a track gives nothing while another is a second ahead: it's left out from here
                self._ended.update(k for k in keys if have[k] == 0)
                live = [have[k] for k in keys if k not in self._ended]
                n = min(live) if live else 0
        if n <= 0:
            return b""
        np = _numpy()
        total = np.zeros(n * self.channels, dtype=np.int32)
        for k in keys:
            data = b"".join(self._waiting[k])
            use = min(len(data) // width, n)
            if use and k not in self._muted:
                total[: use * self.channels] += np.frombuffer(data[: use * width], dtype=np.int16)
            rest = data[use * width:]
            self._waiting[k] = [rest] if rest else []
        self.made += n
        return np.clip(total, -32768, 32767).astype(np.int16).tobytes()


def decode_all(container, layout="mono", rate=48000, stop=None, each=None, muted=()):
    """Every sound track of an open file mixed, chunk by chunk (bytes of int16).
    `each(frame, stream)` sees every decoded frame; `stop()` true ends it early."""
    streams = audio_streams(container)
    if not streams:
        return
    start = (container.start_time or 0) / 1_000_000 if container.start_time else 0.0
    mix = Mix(streams, layout=layout, rate=rate, start=start, muted=muted)
    for packet in container.demux(*streams):
        for frame in packet.decode():
            if each is not None:
                each(frame, packet.stream)
            out = mix.push(frame, packet.stream)
            if out:
                yield out
            if stop is not None and stop():
                return
    out = mix.finish()
    if out:
        yield out


def decode_tracks(container, layout="mono", rate=8000, stop=None, each=None):
    """Every sound track of an open file by itself, lined up from the same moment: [numpy int16 array, ...] as long
    as the longest - or None (no numpy, no sound, or `stop()` came true). For redrawing a song's waveform with some
    of its parts switched off without reading the file again."""
    np = _numpy()
    streams = list(container.streams.audio)
    if np is None or not streams:
        return None
    start = (container.start_time or 0) / 1_000_000 if container.start_time else 0.0
    mixes = {s.index: Mix([s], layout=layout, rate=rate, start=start) for s in streams}
    parts = {s.index: [] for s in streams}
    for packet in container.demux(*streams):
        for frame in packet.decode():
            if each is not None:
                each(frame, packet.stream)
            out = mixes[packet.stream.index].push(frame, packet.stream)
            if out:
                parts[packet.stream.index].append(out)
        if stop is not None and stop():
            return None
    for key, mix in mixes.items():
        out = mix.finish()
        if out:
            parts[key].append(out)
    arrays = [np.frombuffer(b"".join(parts[s.index]), dtype=np.int16) for s in streams]
    longest = max(len(a) for a in arrays)
    return [np.pad(a, (0, longest - len(a))) if len(a) < longest else a for a in arrays]
