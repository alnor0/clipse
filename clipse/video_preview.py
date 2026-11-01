"""The preview window next to the picker: watch a clip before inserting it.

Video is decoded with PyAV (ready-made builds of FFmpeg for Windows,
macOS and Linux, so practically every format Resolve uses plays) on a
background thread; frames are handed to the preview panel, and the sound
goes out through miniaudio at the listen volume.

Controls: play/pause, jump back/forward, loop or play once, autoplay.

Both libraries are optional: without them the panel says previewing
isn't available, and everything else works as before.
"""
import os
import threading
import time
from collections import deque

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QImage

from .audio_mix import Mix, audio_streams, decode_all, decode_tracks
from .audio_preview import SOUND_BUFFER_MS, sound_device

IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp", ".tif", ".tiff")
SAMPLE_RATE = 44100


def available():
    try:
        import av  # noqa: F401
        return True
    except Exception:
        return False


class _AudioQueue:
    """Decoded sound waiting to be played - filled by the decoder thread,
    drained by miniaudio's playback callback. Silent while paused."""

    def __init__(self, preview):
        self.chunks = deque()
        self.lock = threading.Lock()
        self.preview = preview  # for the volume
        self.paused = False

    def push(self, data):
        with self.lock:
            self.chunks.append(data)

    def clear(self):
        with self.lock:
            self.chunks.clear()

    def waiting(self):
        """True while there's sound the device hasn't taken yet."""
        with self.lock:
            return bool(self.chunks)

    def generator(self):
        from array import array
        frames = yield b""
        while True:
            need = frames * 4  # 16-bit stereo
            out = bytearray()
            if not self.paused:
                with self.lock:
                    while self.chunks and len(out) < need:
                        chunk = self.chunks.popleft()
                        take = need - len(out)
                        out += chunk[:take]
                        if len(chunk) > take:
                            self.chunks.appendleft(chunk[take:])
            out += bytes(need - len(out))  # silence when paused or the decoder is behind
            samples = array("h", bytes(out))
            gain = self.preview.gain
            if gain < 0.999:
                samples = array("h", [int(s * gain) for s in samples])
            frames = yield samples


class VideoPlayer(QObject):
    """Plays one file at a time. Emits frames sized to fit `max_size`."""
    frame = Signal(QImage, float, float, int)   # image, position (s), duration (s), generation
    state = Signal(bool, int)                   # playing?, generation
    message = Signal(str)
    waveform = Signal(object, int)              # list of peaks 0..1, generation
    clipping = Signal(object, int)              # per peak: does the sound clip there?, generation
    parts = Signal(object, object, int)         # a song's stems: their names, the ones switched off, generation

    def __init__(self, audio_preview, audio_only=False):
        super().__init__()
        self.audio_only = audio_only  # just the sound (Ctrl+Space with the preview closed)
        self.audio = audio_preview  # shares the listen volume
        self._thread = None
        self._has_picture = False
        self._stop = threading.Event()
        self._wake = threading.Event()  # interrupts waits when a control is used
        self._lock = threading.Lock()
        self._device = None
        self._queue = None
        self.max_size = (480, 270)
        self.current_path = None
        self.generation = 0  # bumped on every play/stop; frames from older runs are ignored
        self.loop = False
        self.paused = False
        self.position = 0.0
        self.duration = 0.0
        self.is_video = False
        self._seek_to = None
        self._restart = False
        # where each clip was left - going back to it carries on from there
        # (Settings -> Preview & listen -> Remember where each clip was)
        self.remember = True
        self.resume_points = {}
        # in/out marked in the preview: playback stays between them - and
        # loops there with Loop on (None: the whole clip)
        self.range = None       # (start s, end s or None)
        self.fps = 0.0          # the video's frame rate, for timecode
        self._parts_wave = None  # (path, each part's samples, where it clips, bins): a song's parts, to redraw quickly
        self.muted = set()      # a file's sound tracks (by place: 0 ...) left silent - a song's stems (stems.py)

    def _remember_place(self):
        path = self.current_path
        if not path or not self.is_video:
            return
        near_end = self.duration and self.position >= self.duration - 1.0
        if self.position < 1.0 or near_end:
            self.resume_points.pop(path, None)  # at the start or finished: start over next time
            return
        self.resume_points.pop(path, None)
        self.resume_points[path] = self.position
        while len(self.resume_points) > 300:
            self.resume_points.pop(next(iter(self.resume_points)))

    # -- controls (called from the GUI thread) --
    def play(self, path, autoplay=True):
        self.stop()
        self.current_path = path
        self.is_video = False
        self._has_picture = False
        if not path or not os.path.isfile(path):
            self.message.emit("The clip's file wasn't found on disk.")
            return
        if path.lower().endswith(IMAGE_EXTENSIONS):
            image = QImage(path)
            if image.isNull():
                self.message.emit("Can't show this image.")
            else:
                self.frame.emit(self._fit(image), 0.0, 0.0, self.generation)
            return
        if not available():
            self.message.emit("Video preview isn't available on this computer (PyAV is missing).")
            return
        self.is_video = True
        self.paused = not autoplay
        self.position, self.duration = 0.0, 0.0
        self._seek_to, self._restart = None, False
        resume = self.resume_points.get(path) if self.remember else None
        if self.range and (resume is None or not self._range_start() <= resume < (self._range_end() or 1e12)):
            resume = self._range_start() or None  # marked: start at the in
        if resume:
            self._seek_to = self.position = resume
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, args=(path, self._stop, self.generation), daemon=True)
        self._thread.start()

    def toggle_pause(self):
        if not self.is_video:
            return
        with self._lock:
            self.paused = not self.paused
            if not self.paused and self._ended():
                self._restart = True  # pressing play at the end starts over
        if self._queue is not None:
            self._queue.paused = self.paused
        self.state.emit(not self.paused, self.generation)
        self._wake.set()

    @property
    def running(self):
        """A clip is open in the player (playing, paused, or stopped at its end)."""
        return self._thread is not None and self._thread.is_alive()

    def seek_relative(self, seconds):
        self.seek_to(self.position + seconds)

    def restart(self):
        """From the start again (the marked in, if there is one), playing."""
        if not self.is_video:
            return
        with self._lock:
            self._restart = True
            self.paused = False
        if self._queue is not None:
            self._queue.paused = False
        self._wake.set()
        self.state.emit(True, self.generation)

    def seek_to(self, seconds):
        """Jumps to `seconds` from the start (stays paused if paused)."""
        if not self.is_video:
            return
        with self._lock:
            target = max(0.0, seconds)
            if self.duration:
                target = min(target, max(0.0, self.duration - 0.05))
            self._seek_to = target
        self._wake.set()

    def set_muted(self, off):
        """Parts of the sound switched off or on while it plays: heard at once (what's decoded ahead is
        decoded again), and the waveform drawn again of what's heard."""
        off = set(off)
        if off == self.muted:
            return
        self.muted = off
        if not self.is_video or not self.current_path:
            return
        with self._lock:
            if self._seek_to is None:
                self._seek_to = self.position
        self._wake.set()
        if self._thread is None or self.audio_only or self._has_picture:
            return
        parts = self._parts_wave
        if parts and parts[0] == self.current_path:  # read already: drawn again at once
            self.waveform.emit(self._parts_peaks(off), self.generation)
        else:
            threading.Thread(target=self._compute_waveform, args=(self.current_path, self._stop, self.generation),
                             daemon=True).start()

    def stop(self):
        self._remember_place()
        self.generation += 1
        self._stop.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
        self._thread = None
        self._close_audio()
        self.current_path = None
        self.is_video = False

    # -- internals --
    def _ended(self):
        end = self._range_end() or self.duration
        return bool(end) and self.position >= end - 0.15

    def _range_start(self):
        return self.range[0] if self.range else 0.0

    def _range_end(self):
        return self.range[1] if self.range and self.range[1] else None

    def _fit(self, image):
        w, h = self.max_size
        from PySide6.QtCore import Qt
        return image.scaled(w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation)

    def _open_audio(self, queue):
        try:
            import miniaudio
            gen = queue.generator()
            next(gen)
            device = sound_device(sample_rate=SAMPLE_RATE, nchannels=2)
            device.start(gen)
            self._device = device
        except Exception:
            self._device = None  # no sound - the picture still plays

    def _close_audio(self):
        if self._device is not None:
            try:
                self._device.close()
            except Exception:
                pass
        self._device = None
        self._queue = None

    def _lag(self):
        """Seconds from sound handed to the device to sound heard - what the picture and the progress
        line wait, so they keep step with it."""
        return SOUND_BUFFER_MS / 1000.0 if self._device is not None else 0.0

    def _nap(self, seconds):
        """Sleeps, but wakes up early when a control is used or on stop."""
        self._wake.wait(seconds)
        self._wake.clear()

    def _take_seek(self):
        with self._lock:
            target, self._seek_to = self._seek_to, None
            if target is None and self._restart:
                target = self._range_start()
            self._restart = False
        return target

    @property
    def playing(self):
        return self.is_video and not self.paused and self._thread is not None and self._thread.is_alive()

    def _compute_waveform(self, path, stop, generation, bins=480):
        """Peaks across the whole sound, for drawing its waveform. Decoded
        at a low sample rate on its own thread; skipped for very long files.
        Always answers (an empty list when there's no waveform), so the
        preview knows whether to wait for it."""
        peaks, clipped = [], []
        try:
            from . import stems
            parts = self._parts_wave
            if len(stems.part_names(path)) > 1 and not (parts and parts[0] == path):
                read = self._read_parts(path, stop, bins)  # (once per file: switching parts redraws from memory)
                if read is not None:
                    self._parts_wave = parts = (path, *read)
            if parts and parts[0] == path:
                peaks, clipped = self._parts_peaks(set(self.muted)), parts[2]
            else:
                peaks, clipped = self._waveform_peaks(path, stop, bins, set(self.muted))
        except Exception:
            peaks, clipped = [], []
        if not stop.is_set():
            self.clipping.emit(clipped if any(clipped) else [], generation)
            self.waveform.emit(peaks or [], generation)

    def _read_parts(self, path, stop, bins):
        """A song's parts, each by itself at the waveform's low rate - (their samples, where it clips, bins), or
        None. Clipping isn't looked for: a part rarely clips by itself, and looking took longer than the reading."""
        import av
        with av.open(path) as container:
            duration = float(container.duration / av.time_base) if container.duration else 0.0
            if duration > 30 * 60:
                return None
            tracks = decode_tracks(container, layout="mono", rate=8000 if duration < 120 else 2000, stop=stop.is_set)
        if not tracks or len(tracks[0]) < 2:
            return None
        bins = min(bins, len(tracks[0]))
        return tracks, [False] * bins, bins

    def _parts_peaks(self, muted):
        """The waveform of the parts that are on - at the whole song's scale, so what's left looks as much smaller
        as it is (scaled to its own loudest, the drums alone stood as tall as everything together)."""
        import numpy as np
        _path, tracks, _clipped, bins = self._parts_wave
        n = len(tracks[0])
        edges = (np.arange(bins) * n) // bins

        def tops(which):
            total = np.zeros(n, dtype=np.int32)
            for i in which:
                total += tracks[i]
            return np.maximum.reduceat(np.abs(total), edges)
        whole = float(tops(range(len(tracks))).max()) or 1.0
        heard = tops([i for i in range(len(tracks)) if i not in muted])
        return [float(v) / whole for v in heard]

    @staticmethod
    def _frame_clips(frame, np):
        """Where in this bit of sound (0-1 along it) it sits on the ceiling
        for two samples in a row - a flattened top, what clipping looks
        like. Looked at as it is in the file, before it's thinned out for
        the drawing."""
        a = frame.to_ndarray()
        if a.dtype.kind == "f":
            hit = (a >= 0.999) | (a <= -0.999)
        elif a.dtype.kind == "u":
            hit = (a >= 255) | (a <= 0)
        else:
            top = int(np.iinfo(a.dtype).max * 0.999)
            hit = (a >= top) | (a <= -top)
        step = 1 if frame.format.is_planar else max(1, len(frame.layout.channels))  # the next sample of the same channel
        flat = (hit[:, step:] & hit[:, :-step]).any(axis=0)
        return np.unique(np.nonzero(flat)[0] * 64 // max(1, flat.size)) / 64.0

    @staticmethod
    def _waveform_peaks(path, stop, bins, muted=()):
        import av
        from array import array
        try:
            import numpy as np  # only for finding clipping; the waveform works without
        except Exception:
            np = None
        container = av.open(path)
        clips_at = []  # how far into the sound (0-1) each clipping bit is
        try:
            duration = float(container.duration / av.time_base) if container.duration else 0.0
            if duration > 30 * 60:
                return [], []
            rate = 8000 if duration < 120 else 2000
            samples = array("h")

            def clipping(frame, stream):
                nonlocal np
                if np is not None and duration > 0 and frame.time is not None:
                    try:
                        long = frame.samples / float(frame.sample_rate)
                        clips_at.extend((frame.time + long * part) / duration
                                        for part in VideoPlayer._frame_clips(frame, np))
                    except Exception:
                        np = None  # a format it can't read: leave clipping out

            for chunk in decode_all(container, layout="mono", rate=rate, stop=stop.is_set, each=clipping, muted=muted):
                samples.frombytes(chunk)
            if stop.is_set():
                return [], []
        finally:
            container.close()
        n = len(samples)
        if n < 2:
            return [], []
        bins = min(bins, n)
        clipped = [False] * bins
        for at in clips_at:
            clipped[max(0, min(bins - 1, int(at * bins)))] = True
        peaks = []
        for i in range(bins):
            seg = samples[i * n // bins:(i + 1) * n // bins]
            peaks.append(max(max(seg), -min(seg)) if seg else 0)
        top = max(peaks) or 1
        return [p / top for p in peaks], clipped

    def _run_audio(self, container, audio, stop, generation):
        """A sound: no picture, so playback is paced by the audio itself
        (decoded a little ahead of what's playing), and the position is
        sent out for the progress bar."""
        import av
        self.duration = float(container.duration / av.time_base) if container.duration else 0.0
        if not self.duration and audio.duration and audio.time_base:
            self.duration = float(audio.duration * audio.time_base)
        tracks = audio_streams(container) or [audio]
        queue = _AudioQueue(self.audio)
        queue.paused = self.paused
        self._queue = queue
        self._open_audio(queue)
        empty = QImage()
        self.state.emit(not self.paused, generation)
        ahead = 0.4  # seconds decoded ahead of what's heard

        def jump_requested():
            return self._seek_to is not None or self._restart

        def report(pos):
            self.position = pos
            self.frame.emit(empty, pos, self.duration, generation)

        target = 0.0
        while not stop.is_set():
            container.seek(int(target * 1_000_000), backward=True)
            mix = Mix(tracks, layout="stereo", rate=SAMPLE_RATE, start=target, muted=self.muted)  # every track at once
            queue.clear()
            origin = None       # wall-clock time that corresponds to t = 0
            heard = target      # where playback is
            report(heard)
            jumped = False

            def wait_until(decoded_to):
                """Waits while more than `ahead` is queued; False on a jump/stop."""
                nonlocal origin, heard
                while not stop.is_set():
                    if jump_requested():
                        return False
                    if self.paused:
                        origin = None
                        self._nap(0.5)
                        continue
                    if origin is None:  # (heard a moment after it's handed over: the device's buffer)
                        origin = time.monotonic() - heard + self._lag()
                    heard = max(target, min(time.monotonic() - origin, decoded_to))
                    report(heard)
                    if decoded_to - heard < ahead:
                        return True
                    self._nap(0.05)
                return False

            end = target
            stop_at = self._range_end()
            past_out = False
            for packet in container.demux(*tracks):
                for frame in packet.decode():
                    t = float(frame.time or 0.0)
                    stop_at = self._range_end()  # read live: marking out while it plays counts
                    if stop_at is not None and t >= stop_at:
                        past_out = True  # the marked out: stop decoding, let what's queued play
                        end = max(end, stop_at)
                        break
                    if t + frame.samples / (frame.sample_rate or SAMPLE_RATE) < target:
                        continue  # before the jump point
                    out = mix.push(frame, packet.stream)
                    if out:
                        queue.push(out)
                    end = max(end, mix.seconds)
                    if not wait_until(end):
                        jumped = True
                        break
                if jumped or stop.is_set() or past_out:
                    break
            if stop.is_set():
                return
            if not jumped:
                if not past_out:
                    out = mix.finish()
                    if out:
                        queue.push(out)
                    end = max(end, mix.seconds)
                if not self.duration:
                    self.duration = end
                if stop_at is not None:
                    end = min(end, stop_at)
                # let the last of it play out
                while not stop.is_set() and not jump_requested():
                    if self.paused:
                        origin = None
                        self._nap(0.5)
                        continue
                    if origin is None:
                        origin = time.monotonic() - heard + self._lag()
                    heard = max(target, min(time.monotonic() - origin, end))
                    report(heard)
                    if heard >= end - 0.01:
                        break
                    self._nap(0.03)
                # ...and until the sound device has really taken all of it. The clock
                # above starts with the first sound decoded, the device a moment
                # later - so a very short sound (a click, a tick) was "over" before
                # any of it had been played, and longer ones lost their tail.
                patience = time.monotonic() + 3.0
                while (queue.waiting() and self._device is not None and not self.paused and not stop.is_set()
                       and not jump_requested() and time.monotonic() < patience):
                    self._nap(0.01)
                jumped = jump_requested()
                if stop.is_set():
                    return
            if jumped:
                target = self._take_seek()
                if target is None:
                    target = self.position
                continue
            report(end if stop_at is not None else self.duration)
            if self.loop:
                target = self._range_start()
                continue
            with self._lock:
                self.paused = True
                self.position = end if stop_at is not None else self.duration
            queue.paused = True
            self.state.emit(False, generation)
            while not stop.is_set() and self.paused and not jump_requested():
                self._nap(0.5)
            if stop.is_set():
                return
            target = self._take_seek()
            if target is None:
                target = self._range_start()
            queue.paused = self.paused

    def _run(self, path, stop, generation):
        import av
        try:
            container = av.open(path)
        except Exception as e:
            self.message.emit(f"Can't open the clip: {e}")
            return
        try:
            video = container.streams.video[0] if container.streams.video and not self.audio_only else None
            audio = container.streams.audio[0] if container.streams.audio else None
            from . import stems
            names = stems.part_names(path)  # several sound tracks: which of them are heard (kept per file)
            self.muted = stems.muted(path, names)
            self.parts.emit(names, sorted(self.muted), generation)
            if video is None:
                if audio is None:
                    self.message.emit("This clip has no sound." if self.audio_only else "Nothing to play in this file.")
                    return
                if not self.audio_only:
                    threading.Thread(target=self._compute_waveform, args=(path, stop, generation), daemon=True).start()
                self._run_audio(container, audio, stop, generation)
                return
            video.thread_type = "AUTO"
            self._has_picture = True
            self.duration = float(container.duration / av.time_base) if container.duration else 0.0
            queue = _AudioQueue(self.audio)
            queue.paused = self.paused
            self._queue = queue
            if audio is not None:
                self._open_audio(queue)
            try:
                self.fps = float(video.average_rate or video.guessed_rate or 0)
            except Exception:
                self.fps = 0.0
            sized = {"for": None, "out": (2, 2)}

            def out_size():
                """Frames as big as the preview shows them - worked out again
                when it grows or shrinks (the big view), not once per clip."""
                if sized["for"] != self.max_size:
                    w, h = self.max_size
                    vw, vh = video.codec_context.width or w, video.codec_context.height or h
                    scale = min(w / vw, h / vh)
                    sized["for"] = self.max_size
                    sized["out"] = (max(2, int(vw * scale) // 2 * 2), max(2, int(vh * scale) // 2 * 2))
                return sized["out"]
            tracks = (audio_streams(container) or [audio]) if audio is not None else []  # every sound track, mixed
            streams = [video] + tracks
            self.state.emit(not self.paused, generation)

            def show(frame, t):
                out_w, out_h = out_size()
                rgb = frame.reformat(width=out_w, height=out_h, format="rgb24")
                plane = rgb.planes[0]
                image = QImage(bytes(plane), out_w, out_h, plane.line_size, QImage.Format_RGB888).copy()
                self.position = t
                self.frame.emit(image, t, self.duration, generation)

            def jump_requested():
                return self._seek_to is not None or self._restart

            target = 0.0
            while not stop.is_set():
                # decode from `target` seconds
                container.seek(int(target * 1_000_000), backward=True)
                mix = Mix(tracks, layout="stereo", rate=SAMPLE_RATE, start=target, muted=self.muted) if tracks else None
                queue.clear()
                origin = None   # wall-clock time that corresponds to t = 0
                shown = False
                jumped = False
                stop_at = self._range_end()
                past_out = False
                for packet in container.demux(*streams):
                    if stop.is_set():
                        return
                    if jump_requested():
                        jumped = True
                        break
                    for frame in packet.decode():
                        t = float(frame.time or 0.0)
                        if packet.stream is not video:
                            out = mix.push(frame, packet.stream)  # (what's before the jump point is left out)
                            if out:
                                queue.push(out)
                            continue
                        if t < target - 0.001:
                            continue  # still decoding up to the jump point
                        stop_at = self._range_end()  # read live: marking out while it plays counts
                        if stop_at is not None and t >= stop_at and t > target + 0.001:
                            past_out = True  # the marked out
                            break
                        if self.paused:
                            # show where we are, then wait for play / jump / stop
                            if not shown:
                                show(frame, t)
                                shown = True
                            while self.paused and not stop.is_set() and not jump_requested():
                                self._nap(0.5)
                            origin = None
                            if stop.is_set():
                                return
                            if jump_requested():
                                jumped = True
                                break
                        if origin is None:  # (the picture waits for its sound: the device's buffer)
                            origin = time.monotonic() - t + self._lag()
                        delay = origin + t - time.monotonic()
                        if delay < -0.25:
                            continue  # running late - drop the frame
                        if delay > 0:
                            self._nap(delay)
                            if stop.is_set():
                                return
                            if jump_requested():
                                jumped = True
                                break
                            if self.paused:
                                origin = None
                                show(frame, t)
                                shown = True
                                continue
                        show(frame, t)
                        shown = True
                    if jumped or past_out:
                        break
                if stop.is_set():
                    return
                if jumped:
                    target = self._take_seek()
                    if target is None:
                        target = self.position
                    continue
                # reached the end (or the marked out): the last of the sound first (the
                # device runs a moment behind the picture), then loop, or stop on the last frame
                patience = time.monotonic() + 1.0
                while (queue.waiting() and self._device is not None and not self.paused and not stop.is_set()
                       and not jump_requested() and time.monotonic() < patience):
                    self._nap(0.01)
                if self.loop:
                    target = self._range_start()
                    continue
                with self._lock:
                    self.paused = True
                    if not past_out:
                        self.position = self.duration
                queue.paused = True
                self.state.emit(False, generation)
                while not stop.is_set() and self.paused and not jump_requested():
                    self._nap(0.5)
                if stop.is_set():
                    return
                target = self._take_seek()
                if target is None:
                    target = self._range_start()
                queue.paused = self.paused
        except Exception as e:
            if not stop.is_set():
                self.message.emit(f"Preview stopped: {e}")
        finally:
            container.close()


class Scrubber(QObject):
    """Frames for hover scrub - separate from playback, so moving the mouse
    across a video never moves where it's playing.

    Two background readers, each with its own copy of the file open:
    - a strip of small frames across the whole clip, read once (key frames
      only, coarse to fine, so the whole range is covered within moments);
      hovering shows the nearest one instantly;
    - the frame at exactly where the mouse is: the nearest key frame first,
      then the exact frame, dropped as soon as the mouse has moved on.
    """
    ready = Signal(QImage, float, int)   # image, seconds, generation

    def __init__(self):
        super().__init__()
        self.generation = 0
        self.path = None
        self.size = (0, 0)
        self.duration = 0.0
        self._strip = {}          # index -> the frame as JPEG bytes (full quality, a fraction of the memory)
        self._decoded = {}        # index -> QImage: the last few strip frames unpacked (sweeping back and forth)
        self._count = 0
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._want = None         # (seconds, generation) - the latest exact request
        self._wake = threading.Event()

    def start(self, path, duration_hint=0.0, size=(640, 360)):
        if path == self.path and size[0] <= self.size[0] + 8 and size[1] <= self.size[1] + 8:
            return  # already reading this clip, big enough
        self.stop()
        self.size = size
        if not path or path.lower().endswith(IMAGE_EXTENSIONS) or not available():
            return
        self.path = path
        self.duration = duration_hint
        self._stop = threading.Event()
        generation = self.generation
        threading.Thread(target=self._read_strip, args=(path, size, self._stop, generation),
                         name="clipse-scrub-strip", daemon=True).start()
        threading.Thread(target=self._read_exact, args=(path, size, self._stop, generation),
                         name="clipse-scrub", daemon=True).start()

    def stop(self):
        self.generation += 1
        self._stop.set()
        self._wake.set()
        with self._lock:
            self._strip = {}
            self._decoded = {}
            self._count = 0
            self._want = None
        self.path = None

    def nearest(self, seconds):
        """(image, its seconds) - the closest frame of the strip read so far - or None."""
        with self._lock:
            if not self._strip or not self._count or not self.duration:
                return None
            target = min(self._count - 1, max(0, int(seconds / self.duration * self._count)))
            for d in range(self._count):
                for i in (target - d, target + d):
                    if i in self._strip:
                        image = self._decoded.pop(i, None)
                        if image is None:
                            image = QImage.fromData(self._strip[i], "JPG")
                        self._decoded[i] = image  # newest last
                        while len(self._decoded) > 10:
                            self._decoded.pop(next(iter(self._decoded)))
                        return image, (i + 0.5) / self._count * self.duration
        return None

    def request(self, seconds):
        with self._lock:
            self._want = (seconds, self.generation)
        self._wake.set()

    # -- the readers --
    @staticmethod
    def _open(path):
        import av
        container = av.open(path)
        video = container.streams.video[0] if container.streams.video else None
        if video is None:
            container.close()
            return None, None
        video.thread_type = "AUTO"
        return container, video

    @staticmethod
    def _pack(image):
        from PySide6.QtCore import QBuffer, QByteArray, QIODevice
        data = QByteArray()
        buffer = QBuffer(data)
        buffer.open(QIODevice.WriteOnly)
        image.save(buffer, "JPG", 90)
        buffer.close()
        return bytes(data)

    @staticmethod
    def _image(frame, size):
        w, h = size
        vw, vh = frame.width or w, frame.height or h
        scale = min(w / vw, h / vh, 1.0)
        out_w, out_h = max(2, int(vw * scale) // 2 * 2), max(2, int(vh * scale) // 2 * 2)
        rgb = frame.reformat(width=out_w, height=out_h, format="rgb24")
        plane = rgb.planes[0]
        return QImage(bytes(plane), out_w, out_h, plane.line_size, QImage.Format_RGB888).copy()

    def _read_strip(self, path, size, stop, generation):
        import av
        try:
            container, video = self._open(path)
        except Exception:
            return
        if container is None:
            return
        try:
            duration = float(container.duration / av.time_base) if container.duration else 0.0
            if not duration and video.duration and video.time_base:
                duration = float(video.duration * video.time_base)
            if duration <= 0:
                return
            self.duration = duration
            count = int(max(24, min(96, duration * 4)))
            with self._lock:
                self._count = count
            video.codec_context.skip_frame = "NONKEY"  # key frames only: fast
            small = size  # as sharp as the preview shows it
            # coarse to fine: the ends and middle first, then the gaps between
            order, step = [], count
            seen = set()
            while step >= 1:
                for i in range(0, count, step):
                    if i not in seen:
                        seen.add(i)
                        order.append(i)
                step //= 2
            for i in order:
                if stop.is_set() or generation != self.generation:
                    return
                t = (i + 0.5) / count * duration
                try:
                    container.seek(int(t / video.time_base), stream=video, backward=True, any_frame=False)
                    for frame in container.decode(video):
                        packed = self._pack(self._image(frame, small))
                        with self._lock:
                            if generation == self.generation:
                                self._strip[i] = packed
                                self._decoded.pop(i, None)
                        break
                except Exception:
                    continue
            # Footage with key frames far apart (screen recordings, phones) gives
            # the same few pictures above - for clips up to a minute and a half,
            # read it through once more and put the real frame in every slot.
            if duration <= 90 and not stop.is_set():
                video.codec_context.skip_frame = "DEFAULT"
                container.seek(0, stream=video, backward=True)
                filled = set()
                for frame in container.decode(video):
                    if stop.is_set() or generation != self.generation:
                        return
                    t = float(frame.time or 0.0)
                    i = min(count - 1, int(t / duration * count))
                    if i in filled or abs(t - (i + 0.5) / count * duration) > duration / count / 2:
                        continue
                    filled.add(i)
                    packed = self._pack(self._image(frame, small))
                    with self._lock:
                        if generation == self.generation:
                            self._strip[i] = packed
                            self._decoded.pop(i, None)
        except Exception:
            pass
        finally:
            container.close()

    def _read_exact(self, path, size, stop, generation):
        try:
            container, video = self._open(path)
        except Exception:
            return
        if container is None:
            return
        try:
            while not stop.is_set():
                self._wake.wait(1.0)
                self._wake.clear()
                with self._lock:
                    want, self._want = self._want, None
                if want is None or want[1] != generation:
                    continue
                target = want[0]
                try:
                    container.seek(int(max(0.0, target) / video.time_base), stream=video, backward=True)
                except Exception:
                    continue
                first = True
                for frame in container.decode(video):
                    if stop.is_set() or self._want is not None:
                        break  # the mouse moved on - start over there
                    t = float(frame.time or 0.0)
                    if first or t >= target - 0.02:
                        self.ready.emit(self._image(frame, size), t, generation)
                    if t >= target - 0.02:
                        break
                    first = False
        except Exception:
            pass
        finally:
            container.close()
