"""Listen to a sound before inserting it.

Plays the clip's own file straight from disk with miniaudio (a small
library with ready-made builds for Windows, macOS and Linux - no system
audio libraries to install). Resolve's scripting API can't play audio
itself. WAV, MP3, FLAC and OGG files can be played; other formats are
skipped with a message.

miniaudio is optional: where it isn't installed (unusual platforms,
Python 3.9), previewing simply says it isn't available.
"""
import os

PLAYABLE = (".wav", ".mp3", ".flac", ".ogg")


def _with_volume(source, preview):
    """Passes the decoded audio through, scaled by the current volume
    (read for every chunk, so changing the volume works while playing)."""
    from array import array
    frames = yield b""
    while True:
        try:
            chunk = source.send(frames)
        except StopIteration:
            preview._finished = True
            return
        gain = preview.gain
        if gain < 0.999:
            chunk = array("h", [int(sample * gain) for sample in chunk])
        frames = yield chunk



# How much sound the device holds before it's heard. miniaudio's own 200 ms was heard as the sound
# coming late - behind the picture, the progress line and the click (2026-10-14). Small enough
# not to be noticed, big enough not to crackle while the app is busy.
SOUND_BUFFER_MS = 50


def sound_device(**kwargs):
    """A miniaudio playback device for the app's sounds - with the small buffer above."""
    import miniaudio
    return miniaudio.PlaybackDevice(buffersize_msec=SOUND_BUFFER_MS, app_name="Clipse", **kwargs)


class AudioPreview:
    def __init__(self):
        self._device = None
        self._finished = False
        self.current_path = None
        self.volume = 70  # percent

    @property
    def gain(self):
        """Volume as a multiplier. Squared, so the slider feels even to the ear."""
        v = max(0, min(100, self.volume)) / 100
        return v * v

    @staticmethod
    def available():
        try:
            import miniaudio  # noqa: F401
            return True
        except Exception:
            return False

    @property
    def playing(self):
        return self._device is not None and not self._finished

    def play(self, path):
        """Starts playing `path` from the beginning (stopping anything already
        playing). Returns None on success, or a message saying why it can't."""
        self.stop()
        if not path or not os.path.isfile(path):
            return "Can't preview: the clip's file wasn't found on disk."
        if not path.lower().endswith(PLAYABLE):
            return f"Can't preview {os.path.splitext(path)[1] or 'this'} files (WAV, MP3, FLAC and OGG work)."
        try:
            import miniaudio
        except Exception:
            return "Audio preview isn't available on this computer (the miniaudio library is missing)."
        try:
            stream = _with_volume(miniaudio.stream_file(path), self)
            next(stream)
            device = sound_device()
            self._finished = False
            device.start(stream)
        except Exception as e:
            return f"Couldn't play the file: {e}"
        self._device = device
        self.current_path = path
        return None

    def stop(self):
        if self._device is not None:
            try:
                self._device.close()
            except Exception:
                pass
        self._device = None
        self._finished = False
        self.current_path = None
