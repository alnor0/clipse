"""A file's sound tracks by name, and which of them you hear (2026-10-31).

A song's stems in one file (DRUMS, BASS, INSTRUMENTS, MELODY) are sound tracks
with names. The preview has a switch for each; the parts switched off are
silent there and go onto the timeline switched off. What's switched off is kept
for that file only - a file not set yet has every part on (the owner: "The
settings only change for the specific track").

Kept in stems.json (paths.data), on this computer only.
"""

import os
import threading

from . import paths

FILE = paths.data("stems.json")
MAX_FILES = 2000

_lock = threading.Lock()
_data = None
_names = {}  # path -> its parts' names (read once)


def _load():
    global _data
    if _data is None:
        loaded = paths.read_json(FILE, {})
        loaded = loaded if isinstance(loaded, dict) else {}
        _data = {"files": dict(loaded.get("files") or {})}
    return _data


def _key(name):
    return str(name or "").strip().lower()


def part_names(path):
    """The names of the file's sound tracks, in order ([] for one track or none). A track without a name of its
    own is "Track 2" ..."""
    if not path:
        return []
    with _lock:
        if path in _names:
            return _names[path]
    names = []
    try:
        import av
        with av.open(path) as container:
            tracks = list(container.streams.audio)
            if len(tracks) > 1:
                for n, stream in enumerate(tracks, 1):
                    tags = stream.metadata or {}
                    name = tags.get("name") or tags.get("title") or ""
                    if not name:
                        handler = tags.get("handler_name") or ""
                        name = handler if handler and handler.lower() not in ("soundhandler", "sound handler") else ""
                    names.append(_nice(name) or f"Track {n}")
    except Exception:
        names = []
    with _lock:
        _names[path] = names
        while len(_names) > 500:
            _names.pop(next(iter(_names)))
    return names


def _nice(name):
    """DRUMS -> Drums; a name in mixed case stays as it is."""
    name = " ".join(str(name).replace("_", " ").split())
    return name.capitalize() if name.isupper() or name.islower() else name


def muted(path, names=None):
    """Which parts (their places, 0 ...) of the file are switched off."""
    names = part_names(path) if names is None else names
    if not names:
        return set()
    with _lock:
        data = _load()
        off = {_key(n) for n in data["files"].get(os.path.abspath(path)) or []}
    return {i for i, name in enumerate(names) if _key(name) in off}


def set_muted(path, names, off):
    """`off` (places) switched off for this file."""
    off_names = [names[i] for i in sorted(off) if 0 <= i < len(names)]
    with _lock:
        data = _load()
        files = data["files"]
        key = os.path.abspath(path)
        files.pop(key, None)
        if off_names:  # (all on is how a file starts: nothing to keep)
            files[key] = off_names
        while len(files) > MAX_FILES:
            files.pop(next(iter(files)))
        paths.write_json(FILE, data)
