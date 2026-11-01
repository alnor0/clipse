"""Learns what you pick for what you type.

Type "wh", press Enter on whoosh_03 - next time "wh" (or "who", or
"whoosh") lists whoosh_03 first. Each pick is remembered under the text
that was typed; a search gets a boost from the picks made for the same
text, for longer text it's the start of, and for shorter text it starts
with. More picks count more, old ones less.

Kept in picks.json (paths.data), on this computer only.
"""
import json
import os
import time

from .fuzzy import fold
from . import paths

FILE = paths.data("picks.json")
MAX_QUERIES = 500
_data = None  # {typed text: {key: [times picked, day last picked]}}


def _today():
    return int(time.time() // 86400)


def _load():
    global _data
    if _data is None:
        loaded = paths.read_json(FILE, {})
        _data = {q: {k: v for k, v in keys.items() if isinstance(v, list) and len(v) == 2}
                 for q, keys in loaded.items() if isinstance(keys, dict)} if isinstance(loaded, dict) else {}
    return _data


def key_for(row):
    """What a row is remembered as: its kind and name (scripts, macros,
    projects ... by their file, since names repeat)."""
    what = row.name if row.category == "action" or not row.path else row.path
    return f"{row.category}|{what}"


def record(query, row):
    query = " ".join(fold(query).split())
    if not query or len(query) > 40 or row is None:
        return
    data = _load()
    entry = data.setdefault(query, {})
    count = entry.get(key_for(row), [0, 0])[0]
    entry[key_for(row)] = [min(count + 1, 99), _today()]
    if len(data) > MAX_QUERIES:  # the texts not used for the longest go
        newest = lambda q: max(day for _n, day in data[q].values())
        for q in sorted(data, key=newest)[:len(data) - MAX_QUERIES]:
            del data[q]
    try:
        paths.write_json(FILE, data)
    except OSError:
        pass


def boosts(query):
    """{key: points to add to its search score} for what's typed now."""
    query = " ".join(fold(query).split())
    data = _load()
    if not query or not data:
        return {}
    today = _today()
    out = {}
    for typed, keys in data.items():
        if typed == query:
            near = 1.0
        elif typed.startswith(query):   # on the way to something typed before
            near = max(0.5, len(query) / len(typed))
        elif query.startswith(typed):   # typed further than before
            near = 0.8
        else:
            continue
        for key, (count, day) in keys.items():
            points = min(38.0, 10.0 + 8.0 * count) * near * (0.5 if today - day > 90 else 1.0)
            if points > out.get(key, 0.0):
                out[key] = points
    return out


def forget():
    global _data
    _data = {}
    try:
        os.remove(FILE)
    except OSError:
        pass
