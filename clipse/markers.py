"""Markers over a stretch of the edit (2026-10-30, the owner: "a range marker ... the length of the clips that i
select ... to mark where i want broll and explanation for things that you can use for context"). His keys, set in
Resolve: C - Resolve's own Add Marker; Shift+C - Stretch Marker to Clips (fit); Alt+C - Edit Marker (the note window,
marker_note.py). Copy timeline lists every marker with its start, end, name and note.

Resolve can't move or lengthen a marker from a script: it's taken away and an identical one put back (colour, name,
note, its own data). Two markers can't share a frame - AddMarker says no, and the old one is put back."""
import re

from .timeline_tools import tc_frames

# what a marker is for: its name, and its colour in Resolve - soft, natural ones (2026-10-30, the owner: "more natural
# and soothing colors"; they were Purple, Yellow, Mint). Blue is Resolve's own, a marker not yet told.
KINDS = [("B-roll", "Sky"), ("Explain", "Sand"), ("Note", "Mint")]
HIDDEN_FILE = "hidden_markers.json"  # (data folder: {timeline: {frame: marker}} while they're hidden)
DEFAULT_COLOUR = "Blue"
UNNAMED = "Marker"  # (Resolve won't take a marker without a name)


def _timing(timeline):
    fps = float(timeline.GetSetting("timelineFrameRate") or 24) or 24
    return fps, int(timeline.GetStartFrame() or 0)


def playhead(timeline):
    """The playhead in frames from the timeline's start (as markers count)."""
    fps, start = _timing(timeline)
    return tc_frames(str(timeline.GetCurrentTimecode() or "00:00:00:00"), fps) - start


def span(timeline):
    """(first, end) in frames from the timeline's start: the clips selected on the timeline, from the start of the
    first to the end of the last - or, none selected, the clip under the playhead. None when there's neither."""
    _fps, start = _timing(timeline)
    try:
        items = list(timeline.GetSelectedClips() or [])
    except Exception:
        items = []
    if not items:
        item = timeline.GetCurrentVideoItem()
        items = [item] if item is not None else []
    if not items:
        return None
    return min(int(i.GetStart()) for i in items) - start, max(int(i.GetEnd()) for i in items) - start


def markers(timeline):
    """{frame: info} with whole-number frames."""
    return {int(float(f)): dict(info or {}) for f, info in (timeline.GetMarkers() or {}).items()}


def _length(info):
    return max(1, int(float(info.get("duration") or 1)))


def at(timeline, frame):
    """(frame, info) of the marker over `frame` - one that starts there, or a range marker it lies in - or None."""
    hits = [(f, info) for f, info in markers(timeline).items() if f <= frame < f + _length(info)]
    return max(hits, key=lambda hit: hit[0]) if hits else None  # (the latest to start: the one you just placed)


def _put(timeline, frame, info, length):
    # (a name is a must: 21.1.1 says no to a marker without one - "" fails, " " lands; found 2026-10-30, Shift+C's
    #  every new marker failed as "Another marker starts there")
    return bool(timeline.AddMarker(frame, info.get("color") or DEFAULT_COLOUR, info.get("name") or UNNAMED,
                                   info.get("note") or "", length, info.get("customData") or ""))


def _replace(timeline, old, info, frame, length):
    """The marker at `old` taken away and put at `frame`, `length` long, with `info` - put back as it was when
    Resolve says no."""
    before = markers(timeline).get(old)
    if before is not None:
        timeline.DeleteMarkerAtFrame(old)
    if _put(timeline, frame, info, length):
        return True
    if before is not None:
        _put(timeline, old, before, _length(before))
    return False


def _empty(info):
    """A marker just placed (C): nothing in it yet - no name but Resolve's own ("Marker 1") - one frame long."""
    return _unnamed(info) and not str(info.get("note") or "").strip() and _length(info) <= 1


def _unnamed(info):
    return bool(re.fullmatch(r"(marker( \d+)?)?", str(info.get("name") or "").strip().lower()))


def fit(timeline):
    """Shift+C: the marker at the playhead - else one inside the selection - made as long as the selected clips (or
    the clip under the playhead); with none there, a new one over them. When the clips already have a marker at
    their start, that one is fitted and an empty one just placed with C goes (it said "Another marker starts there").
    (worked, what to say when it didn't, the marker's frame, whether it's new) - the note window opens on it."""
    where = span(timeline)
    if where is None:
        return False, "Select clips, or put the playhead over one", None, False
    first, end = where
    hit = at(timeline, playhead(timeline))
    if hit is None:
        inside = [(f, info) for f, info in markers(timeline).items() if first <= f < end]
        here = playhead(timeline)
        hit = min(inside, key=lambda m: abs(m[0] - here)) if inside else None
    there = markers(timeline).get(first)
    if hit is not None and hit[0] != first and there is not None:  # (the clips have theirs already)
        if not _empty(hit[1]):
            return False, "These clips have a marker already", None, False
        timeline.DeleteMarkerAtFrame(hit[0])
        hit = (first, there)
    created = hit is None or _empty(hit[1])  # (one with no words yet: Esc in the window takes it away again)
    if hit is None:
        done = _put(timeline, first, {}, end - first)
    else:
        done = _replace(timeline, hit[0], hit[1], first, end - first)
    return (True, "", first, created) if done else (False, "Another marker starts there", None, False)


def add(timeline, frame, kind, words):
    """C's Enter: a new marker at `frame` - `kind` its name and colour, `words` its note. Placed only now, with words
    (2026-10-30, the owner: "Not giving an explanation doesnt allow placing a marker")."""
    return _put(timeline, frame, {"name": kind, "note": words.strip(), "color": dict(KINDS).get(kind)}, 1)


def _timeline_key(timeline):
    try:
        return str(timeline.GetUniqueId() or "") or str(timeline.GetName())
    except Exception:
        return str(timeline.GetName())


def hidden(timeline):
    """{frame: marker} of this timeline's markers hidden by Hide - Show Markers ({} when none are)."""
    from .paths import data, read_json
    return {int(f): m for f, m in ((read_json(data(HIDDEN_FILE), {}) or {}).get(_timeline_key(timeline)) or {}).items()}


def toggle(timeline):
    """Hide - Show Markers (2026-10-30, the owner: "how to hide/show markers" - nothing in Resolve's scripting shows or
    hides them): the open timeline's markers taken off and kept exactly in the data folder, or put back. A marker
    added meanwhile where a hidden one was keeps its place (that one stays kept). (what to say)."""
    from .paths import data, read_json, write_json
    every = read_json(data(HIDDEN_FILE), {}) or {}
    key = _timeline_key(timeline)
    kept = {int(f): m for f, m in (every.get(key) or {}).items()}
    if kept:
        left = {f: m for f, m in kept.items() if not _put(timeline, f, m, _length(m))}
        if left:
            every[key] = left
        else:
            every.pop(key, None)
        write_json(data(HIDDEN_FILE), every)
        back = len(kept) - len(left)
        return f"{back} marker{'s' if back != 1 else ''} back" + (f", {len(left)} kept (others are there)" if left else "")
    now = markers(timeline)
    if not now:
        return "No markers on this timeline"
    every[key] = {str(f): m for f, m in now.items()}
    write_json(data(HIDDEN_FILE), every)  # (kept before any goes)
    for f in now:
        timeline.DeleteMarkerAtFrame(f)
    return f"{len(now)} marker{'s' if len(now) != 1 else ''} hidden"


def kind_of(info):
    """The kind (KINDS' name) a marker is, by its name - "" for one that isn't one of them."""
    names = {name.lower(): name for name, _c in KINDS}
    return names.get(str(info.get("name") or "").strip().lower(), "")


def describe(timeline, frame, kind, note):
    """Alt+C, the note window's Enter: the marker at `frame` becomes `kind` (its name and colour) with `note`."""
    info = markers(timeline).get(frame)
    if info is None:
        return False, "The marker isn't there any more"
    colour = dict(KINDS).get(kind, info.get("color") or DEFAULT_COLOUR)
    new = dict(info, name=kind or info.get("name") or "", note=note.strip(), color=colour)
    if _replace(timeline, frame, new, frame, _length(info)):
        return True, ""
    return False, "Resolve didn't take the change"
