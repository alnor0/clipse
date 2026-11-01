"""Usage statistics (no page shows them since Settings > Statistics went, 2026-10-14): what you use, how often,
and roughly how much time that saved. Kept on this computer only
(stats.json, paths.data) - nothing is sent anywhere.

Time saved is an estimate: for each thing Clipse does, about how
long doing it by hand in Resolve takes (finding a clip in the Media Pool
and dragging it in, grabbing a still on the Color page and importing it,
building a macro in the Macro Editor ...). The numbers are listed in
ESTIMATES so the total can be checked - and Settings says it's an estimate.
"""
import json
import os
import threading
import time
from . import paths

STATS_FILE = paths.data("stats.json")
DAYS_KEPT = 120

# what each thing is called, and about how many seconds it saves over doing it by hand
ESTIMATES = {
    "insert": ("Clips inserted", 6),
    "grab": ("Frames grabbed", 15),
    "adjust": ("Adjustment clips", 10),
    "comp": ("Fusion compositions placed", 10),
    "jump": ("Jumps to a clip's next use", 6),
    "title": ("Titles added", 12),
    "node": ("Fusion nodes and macros added", 5),
    "tidy": ("Node editors tidied", 30),
    "pullout": ("Nodes pulled out", 8),
    "macro": ("Macros made", 120),
    "template": ("Project templates used", 180),
    "undo": ("Undos", 0),
    "open": ("Times the picker was opened", 0),
}

_lock = threading.Lock()
_data = None


def _load():
    global _data
    if _data is None:
        _data = paths.read_json(STATS_FILE, {})
        if not isinstance(_data, dict):
            _data = {}
        _data.setdefault("since", time.strftime("%Y-%m-%d"))
        _data.setdefault("counts", {})
        _data.setdefault("days", {})
    return _data


def _save():
    try:
        paths.write_json(STATS_FILE, _data)
    except OSError:
        pass


def record(kind, n=1):
    """Counts `n` of `kind` (a key of ESTIMATES) for today."""
    if n <= 0:
        return
    with _lock:
        data = _load()
        data["counts"][kind] = data["counts"].get(kind, 0) + n
        if kind != "open":
            today = time.strftime("%Y-%m-%d")
            data["days"][today] = data["days"].get(today, 0) + n
            if len(data["days"]) > DAYS_KEPT:
                for day in sorted(data["days"])[:-DAYS_KEPT]:
                    del data["days"][day]
        _save()


def summary():
    """{"since", "counts", "days", "saved_seconds", "actions"} for the Statistics page."""
    with _lock:
        data = json.loads(json.dumps(_load()))
    counts = data["counts"]
    saved = sum(ESTIMATES.get(k, ("", 0))[1] * v for k, v in counts.items())
    actions = sorted(((ESTIMATES[k][0], v) for k, v in counts.items() if k in ESTIMATES and v),
                     key=lambda kv: -kv[1])
    return {"since": data["since"], "counts": counts, "days": data["days"], "saved_seconds": saved,
            "actions": actions}


def reset():
    global _data
    with _lock:
        _data = {"since": time.strftime("%Y-%m-%d"), "counts": {}, "days": {}}
        _save()


def format_duration(seconds):
    minutes = int(round(seconds / 60))
    if minutes < 1:
        return "under a minute"
    hours, minutes = divmod(minutes, 60)
    if not hours:
        return f"{minutes} min"
    return f"{hours} h {minutes} min" if minutes else f"{hours} h"
