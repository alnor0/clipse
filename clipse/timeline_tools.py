"""Timeline tools — jump between a clip's timeline instances, and place
adjustment clips sized to what's under the playhead. Pure Resolve-API
logic, no Qt. Triggered by the client's direct commands
(`clipse jump next`, `... adjust match`, etc.), which you
bind to system-wide keys — see daemon.py / PickerWindow.run_direct_command.

Both run inside the already-connected daemon, so there's no Python
startup or Resolve-connection cost per keypress."""
import os
import time

from . import stills
from .resolve_client import tc_to_frame

ADJUSTMENT_MODES = ("match", "match-skip-adj", "fixed")
# A clip from the Media Pool laid over what's under the playhead - an adjustment clip, or an empty
# Fusion composition: (what it's called, the setting with its Media Pool name, ... with its length)
PLACED = {"adjust": ("Adjustment clip", "adj_clip_name", "adj_fixed_frames"),
          "comp": ("Fusion composition", "comp_clip_name", "comp_fixed_frames"),
          "library": ("", None, None)}  # (Text+ / Solid colour - library.py: its own name, a picture's length)
# Media Pool names like_this, as the app's bins (2026-10-20) - the app's own clips under the names before are renamed
DEFAULT_ADJ_CLIP_NAME = "adjustment_clip"  # (settings.TIMELINE_TOOLS_DEFAULTS["adj_clip_name"])
DEFAULT_COMP_CLIP_NAME = "fusion_composition"  # (settings.TIMELINE_TOOLS_DEFAULTS["comp_clip_name"])
OLD_CLIP_NAMES = {DEFAULT_ADJ_CLIP_NAME: "Adjustment Clip", DEFAULT_COMP_CLIP_NAME: "Fusion Composition"}
JUMP_DIRECTIONS = ("next", "previous")
STEP_DIRECTIONS = ("forward", "back")


def frame_to_tc(frame, fps):
    fps_int = round(fps)
    total_seconds, f = divmod(int(frame), fps_int)
    h, rem = divmod(total_seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}:{f:02d}"


def selected_media_pool_items(media_pool):
    """GetSelectedClips() returns a dict on some Resolve versions, a list
    on others."""
    selected = media_pool.GetSelectedClips() or []
    return list(selected.values()) if isinstance(selected, dict) else list(selected)


# ---------------------------------------------------------------
# Step the playhead a few frames (Step Forward / Step Back - 2026-10-21: "moves for example 5 frames forwards and
# backwards")
# ---------------------------------------------------------------

def _drop_per_minute(fps):
    return 4 if round(fps) == 60 else 2  # (29.97 and 59.94 drop-frame: 2 / 4 frame numbers skipped a minute)


def tc_frames(tc, fps):
    """A timecode as Resolve writes it ("01:00:00:00", drop-frame "01:00:00;02") -> frames since 00:00:00:00."""
    drop = ";" in tc
    h, m, s, f = (int(x) for x in tc.replace(";", ":").split(":"))
    frames = (h * 3600 + m * 60 + s) * round(fps) + f
    if drop:
        minutes = h * 60 + m
        frames -= _drop_per_minute(fps) * (minutes - minutes // 10)
    return frames


def frames_tc(frames, fps, drop=False):
    """Frames since 00:00:00:00 -> a timecode Resolve takes (drop-frame with a ";" before the frames)."""
    nominal, frames = round(fps), max(0, int(frames))
    if drop:
        d = _drop_per_minute(fps)
        per_ten = nominal * 600 - d * 9
        per_minute = nominal * 60 - d
        tens, rest = divmod(frames, per_ten)
        frames += d * 9 * tens + (d * ((rest - d) // per_minute) if rest > d else 0)
    total_seconds, f = divmod(frames, nominal)
    h, rem = divmod(total_seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}{';' if drop else ':'}{f:02d}"


# The Fusion page: the composition's own time (the timeline's playhead can't be set there - 21.1.1 scripting doc)
_STEP_LUA = r"""
local t = comp.CurrentTime + %d
local a = comp:GetAttrs()
local lo, hi = a.COMPN_GlobalStart or t, a.COMPN_GlobalEnd or t
if t < lo then t = lo end
if t > hi then t = hi end
comp.CurrentTime = t
comp:SetData("ClipseResult", tostring(t))
"""


def step_playhead(resolve, frames):
    """The playhead `frames` on (or back, negative) - on the timeline, or in the composition on the Fusion page.
    Kept between the timeline's start and end. (worked, message)"""
    try:
        page = resolve.GetCurrentPage()
    except Exception:
        page = None
    if page == "fusion":
        from .scripts_fusion import run_lua
        comp = resolve.Fusion().GetCurrentComp()
        if comp is None:
            return False, "No Fusion composition open"
        at = run_lua(comp, _STEP_LUA % int(frames))
        return (True, f"Frame {at}") if at is not None else (False, "Fusion didn't answer in time - try again")
    project = resolve.GetProjectManager().GetCurrentProject()
    timeline = project.GetCurrentTimeline() if project else None
    if timeline is None:
        return False, "No timeline open"
    tc = timeline.GetCurrentTimecode()
    if not tc:
        return False, "Step needs a timeline page"
    fps = float(timeline.GetSetting("timelineFrameRate") or 24)
    now = tc_frames(tc, fps)
    start, end = int(timeline.GetStartFrame()), int(timeline.GetEndFrame())
    to = min(max(now + int(frames), start), max(start, end))
    if to != now and not timeline.SetCurrentTimecode(frames_tc(to, fps, ";" in tc)):
        return False, "Resolve didn't move the playhead"
    return True, frames_tc(to, fps, ";" in tc)


# ---------------------------------------------------------------
# Jump to next/previous instance
# ---------------------------------------------------------------

def find_instance_starts(timeline, media_ids, names):
    """Sorted, de-duplicated start frames of every timeline item (video
    and audio) that uses one of media_ids or is named one of names.
    De-duplicated so a clip's linked video+audio counts as one stop."""
    starts = set()
    for track_type in ("video", "audio"):
        for track_index in range(1, timeline.GetTrackCount(track_type) + 1):
            for item in timeline.GetItemListInTrack(track_type, track_index) or []:
                if item.GetName() in names:  # cheap check first — skips the GetMediaPoolItem() call
                    starts.add(item.GetStart())
                    continue
                mp_item = item.GetMediaPoolItem()
                if mp_item is not None and mp_item.GetMediaId() in media_ids:
                    starts.add(item.GetStart())
    return sorted(starts)


# Where each clip is used on the timeline, remembered between presses so
# rapid next/previous presses don't rescan the whole timeline every time
# (the scan is the slow part: one Resolve API call per timeline item).
# Sliding window: every press within JUMP_CACHE_SECONDS of the previous
# one reuses the result, so a burst of presses scans exactly once; a
# pause longer than that rescans, picking up any timeline edits.
JUMP_CACHE_SECONDS = 2.0
_jump_cache = {"key": None, "starts": None, "fps": None, "last_used": 0.0}


def _timeline_key(timeline):
    try:
        return timeline.GetUniqueId()
    except Exception:
        return timeline.GetName()


def jump_steps(timeline, starts, steps, label, fps=None):
    """Moves the playhead `steps` instances forward (positive) or back
    (negative) from the playhead, wrapping around at either end — so a
    burst of 3 queued "next" presses is handled as one 3-step jump instead
    of three round-trips. Returns a status message."""
    if fps is None:
        fps = float(timeline.GetSetting("timelineFrameRate"))
    current = tc_to_frame(timeline.GetCurrentTimecode(), fps)
    n = len(starts)
    if steps > 0:
        first = next((i for i, s in enumerate(starts) if s > current), 0)
        target_index = (first + steps - 1) % n
    else:
        earlier = [i for i, s in enumerate(starts) if s < current]
        first = earlier[-1] if earlier else n - 1
        target_index = (first + steps + 1) % n
    timeline.SetCurrentTimecode(frame_to_tc(starts[target_index], fps))
    return f"{label}: {target_index + 1} of {n}"


def jump_to_instance(timeline, starts, direction, label):
    """Single-step convenience wrapper around jump_steps()."""
    return jump_steps(timeline, starts, 1 if direction == "next" else -1, label)


def jump_targets(timeline, media_pool):
    """The clips Next / Previous use of clip can go by, in order: the one selected on the timeline, the one
    selected in the Media Pool, the one under the playhead (Timeline.GetSelectedClips does tell a script -
    21.1.1). The first that's used on this timeline is the one - a Media Pool selection left from earlier,
    of a clip that isn't on it, doesn't stand in the way of the clip you're on."""
    out = []
    try:
        chosen = timeline.GetSelectedClips() or []
        chosen = list(chosen.values()) if isinstance(chosen, dict) else list(chosen)
    except Exception:
        chosen = []
    out += [item.GetMediaPoolItem() for item in chosen[:1] if item is not None]
    out += selected_media_pool_items(media_pool)[:1]
    try:
        under = timeline.GetCurrentVideoItem()
        out.append(under.GetMediaPoolItem() if under is not None else None)
    except Exception:
        pass
    return [item for item in out if item is not None]


def jump_selected_clip(timeline, media_pool, steps):
    """Client command: jumps `steps` instances (+ forward / - back) for the
    first clip of jump_targets that's on the timeline. Returns a status message."""
    if steps == 0:
        return None
    targets = jump_targets(timeline, media_pool)
    if not targets:
        return "Select a clip on the timeline or in the Media Pool first."
    now = time.monotonic()
    cache = _jump_cache
    fps = None
    for target in targets:
        media_id = target.GetMediaId()
        key = (_timeline_key(timeline), media_id)
        if cache["key"] == key and now - cache["last_used"] < JUMP_CACHE_SECONDS:
            starts, fps, name = cache["starts"], cache["fps"], cache["name"]
        else:
            name = target.GetName()
            starts = find_instance_starts(timeline, {media_id}, {name})
            fps = fps or float(timeline.GetSetting("timelineFrameRate"))
            cache.update(key=key, starts=starts, fps=fps, name=name)
        cache["last_used"] = now
        if starts:
            return jump_steps(timeline, starts, steps, name, fps=fps)
    return f"'{targets[0].GetName()}' isn't used on the timeline."


def invalidate_jump_cache():
    """Called after anything that changes the timeline (adjustment clip
    placement), so the next jump rescans."""
    _jump_cache["key"] = None


# ---------------------------------------------------------------
# Adjustment clip
# ---------------------------------------------------------------

def find_clip_by_name(folder, name):
    """First clip named `name` anywhere under `folder` (any bin depth)."""
    for item in folder.GetClipList():
        if item.GetName() == name:
            return item
    for sub in folder.GetSubFolderList():
        found = find_clip_by_name(sub, name)
        if found:
            return found
    return None


ADJUSTMENT_CLIP_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "adjustment_clip.drb")
# (the same for an empty Fusion composition - once there is such a file: see lookup_composition_clip)
COMPOSITION_CLIP_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "fusion_composition.drb")


def _clip_id(clip):
    try:
        return clip.GetUniqueId()
    except Exception:
        return clip.GetMediaId()


def _bring_clip(media_pool, path, wanted, what, name=""):
    """A clip into the Media Pool from one of the small bin files that come with the app (or library.py
    writes), kept in the app's own bin (stills.CLIPSE_BIN) and called `name`. The files are bins saved by Resolve 21
    with Folder.Export - which saves the bin that's OPEN in the Media Pool, not the one it's called
    on: with the root open it wrote the whole project into the file. The clip, or None when this
    Resolve won't take the file (an older one may not read it)."""
    root = media_pool.GetRootFolder()
    try:
        current = media_pool.GetCurrentFolder()

        def bins():
            return list(root.GetSubFolderList() or [])
        before = {_clip_id(c) for f in bins() for c in f.GetClipList() or []}
        media_pool.SetCurrentFolder(root)
        ok = media_pool.ImportFolderFromFile(path)
        clip = arrived_in = None
        if ok:
            for folder in bins():
                for candidate in folder.GetClipList() or []:
                    if clip is None and _clip_id(candidate) not in before and wanted(candidate):
                        clip, arrived_in = candidate, folder
        if clip is not None and arrived_in.GetName() != stills.CLIPSE_BIN:
            # one bin for what the app brings: the clip moves there, the bin it came in goes again - with anything
            # left in it (2026-10-20: a renamed copy was found left behind in it more than once, the clip moved
            # unrenamed - never seen happen again on its own; the clip is taken from the clipse bin)
            own = stills.app_bin(media_pool, stills.CLIPSE_BIN)
            there = {_clip_id(c) for c in (own.GetClipList() or [])} if own is not None else set()
            if own is not None and media_pool.MoveClips([clip], own):
                moved = [c for c in own.GetClipList() or [] if _clip_id(c) not in there]
                clip = moved[0] if moved else clip
                media_pool.DeleteFolders([arrived_in])
        if clip is not None and name and clip.GetName() != name:
            try:
                clip.SetName(name)
            except Exception:
                pass
        if current is not None:
            media_pool.SetCurrentFolder(current)
        return clip
    except Exception as e:
        print(f"[{what}] couldn't bring in the {what} clip: {e}")
    return None


def _own_clip(media_pool, name):
    """The app's own clip by the name it had before (OLD_CLIP_NAMES: "Adjustment Clip" ...), in the bin it brought
    it into - renamed `name`. Else one of yours by that old name anywhere, left as it is. Or None."""
    old = OLD_CLIP_NAMES.get(name)
    if not old:
        return None
    root = media_pool.GetRootFolder()
    for bin_name in (stills.CLIPSE_BIN, stills.OLD_BIN_NAMES[stills.CLIPSE_BIN]):
        folder = next((f for f in root.GetSubFolderList() or [] if f.GetName() == bin_name), None)
        clip = next((c for c in (folder.GetClipList() or [] if folder else []) if c.GetName() == old), None)
        if clip is not None:
            try:
                clip.SetName(name)
            except Exception:
                pass
            return clip
    return find_clip_by_name(root, old)


def bring_adjustment_clip(media_pool, name=DEFAULT_ADJ_CLIP_NAME):
    """A plain adjustment clip into the Media Pool, from the small bin file
    that comes with the app - so nobody has to make one by hand first.
    (Resolve's own "Adjustment Clip" generator is no use here: it always
    cuts into V1 at the playhead and pushes everything after it along -
    tried in 21.1.1.)"""
    return _bring_clip(media_pool, ADJUSTMENT_CLIP_FILE, lambda c: c.GetClipProperty("Type") == "Generator"
                       and "adjust" in str(c.GetName()).lower(), "adjustment", name)


def _is_composition(clip):
    """A Fusion composition - not a Fusion title or generator, which are "Fusion" too (library.py makes them)."""
    try:
        kind = str(clip.GetClipProperty("Type") or "").lower()
        return "fusion" in kind and "title" not in kind and "generator" not in kind
    except Exception:
        return False


def bring_composition_clip(media_pool, name=DEFAULT_COMP_CLIP_NAME):
    """An empty Fusion composition into the Media Pool, the same way. (Resolve can't make one from
    a script, nor import a .comp - ImportMedia answers with nothing, tried in 21.1.1: the file is a
    bin with one made by hand. Placed, it takes any length it's asked for.)"""
    if not os.path.exists(COMPOSITION_CLIP_FILE):
        return None
    return _bring_clip(media_pool, COMPOSITION_CLIP_FILE, _is_composition, "composition", name)


def lookup_adjustment_clip(settings, media_pool):
    """Returns (clip, None) or (None, error message). With the name left as
    it comes ("adjustment_clip") and no such clip in the project, the app
    brings its own in - nothing to set up."""
    clip_name = settings.timeline_tools["adj_clip_name"]
    clip = find_clip_by_name(media_pool.GetRootFolder(), clip_name)
    if clip is None and clip_name == DEFAULT_ADJ_CLIP_NAME:
        clip = _own_clip(media_pool, clip_name)
    if clip is None and clip_name == DEFAULT_ADJ_CLIP_NAME:
        clip = bring_adjustment_clip(media_pool, clip_name)
        if clip is not None:
            print(f"[adjustment] no adjustment clip in this project yet - added one in the \"{stills.CLIPSE_BIN}\" bin.")
    if clip is None:
        return None, (f"No clip named '{clip_name}' in the Media Pool — add an adjustment clip, "
                      f"or change the name in Settings -> Timeline -> Adjustment clip.")
    return clip, None


def _clip_positions(timeline, name):
    """(track, start, end) of every video item named `name` — used to spot
    exactly which item a placement created."""
    positions = set()
    for track_index in range(1, timeline.GetTrackCount("video") + 1):
        for item in timeline.GetItemListInTrack("video", track_index) or []:
            if item.GetName() == name:
                positions.add((track_index, item.GetStart(), item.GetEnd()))
    return positions


def _clip_fps(clip, fallback):
    """The Media Pool clip's own frame rate. AppendToTimeline's
    startFrame/endFrame are counted in the CLIP's frames, not the
    timeline's — a 24 fps adjustment clip on a 60 fps timeline asked for
    "501 frames" comes out 501 x 60/24 = 1252 timeline frames long."""
    try:
        value = float(clip.GetClipProperty("FPS"))
        return value if value > 0 else fallback
    except (TypeError, ValueError):
        return fallback


def place_over(settings, timeline, media_pool, clip, mode, kind="adjust", frames=None, landed_out=None, what=None):
    """Places `clip` (an adjustment clip, or with kind="comp" an empty Fusion composition) on the lowest video track that's free for its whole
    duration, above everything it would overlap.
    - match:          same start/length as the clip under the playhead
                      (topmost one), or the fixed length if none
    - match-skip-adj: same, but clips of this kind already there are ignored,
                      so it sizes to the real footage underneath
    - fixed:          fixed length starting at the playhead
    frames: that length (else the kind's own setting). landed_out: a list the new timeline item is added to.
    what: what it's called in the message (else the kind's name). Returns a status message."""
    tools = settings.timeline_tools
    kind_name, name_key, frames_key = PLACED[kind]
    what = what or kind_name
    clip_name = clip.GetName() or (tools[name_key] if name_key else what)
    fps = float(timeline.GetSetting("timelineFrameRate"))
    original_timecode = timeline.GetCurrentTimecode()
    playhead_frame = tc_to_frame(original_timecode, fps)
    track_count = timeline.GetTrackCount("video")

    underlying = None
    if mode != "fixed":
        for track_index in range(1, track_count + 1):
            for item in timeline.GetItemListInTrack("video", track_index) or []:
                if item.GetStart() <= playhead_frame < item.GetEnd():
                    if mode == "match-skip-adj" and item.GetName() == clip_name:
                        continue
                    underlying = item  # keeps overwriting, so the topmost track wins

    if underlying is not None:
        new_start, new_end = underlying.GetStart(), underlying.GetEnd()
    else:
        new_start = playhead_frame  # fixed mode, or nothing under the playhead to match
        new_end = playhead_frame + max(1, int(frames or tools[frames_key]))
    duration = new_end - new_start

    highest_occupied = 0
    for track_index in range(1, track_count + 1):
        items = timeline.GetItemListInTrack("video", track_index) or []
        if any(new_start < i.GetEnd() and i.GetStart() < new_end for i in items):
            highest_occupied = track_index
    target_track = highest_occupied + 1
    while timeline.GetTrackCount("video") < target_track:
        timeline.AddTrack("video")

    # Convert the wanted timeline length into the adjustment clip's own
    # frames (see _clip_fps). Exact when both frame rates match; otherwise
    # it can only be cut in steps of fps/clip_fps timeline frames, so the
    # nearest step is used and the result is reported below.
    clip_fps = _clip_fps(clip, fps)
    source_frames = max(1, round(duration * clip_fps / fps))

    invalidate_jump_cache()
    before = _clip_positions(timeline, clip_name)
    placed = media_pool.AppendToTimeline([{
        "mediaPoolItem": clip, "startFrame": 0, "endFrame": source_frames,
        "trackIndex": target_track, "recordFrame": new_start, "mediaType": 1,
    }])
    if not placed:
        return f"{what} placement failed - Resolve rejected the insert."
    if landed_out is not None:
        landed_out.extend(placed if isinstance(placed, list) else [])

    # Verify what Resolve actually did — AppendToTimeline can report success
    # while placing the clip somewhere else or shorter than asked (e.g. a
    # generator can't be longer than its own Media Pool length).
    try:  # the item Resolve hands back: a title or generator is named after its template ("Text+"), not the clip
        item = placed[0]
        landed = [(item.GetTrackTypeAndIndex()[1], item.GetStart(), item.GetEnd())]
    except Exception:
        landed = [p for p in _clip_positions(timeline, clip_name) if p not in before]
    if not landed:
        return (f"Resolve reported success but no new '{clip_name}' appeared on the timeline "
                f"(asked for V{target_track}, frames {new_start}-{new_end}).")
    track, start, end = landed[0]
    problems = []
    if (track, start) != (target_track, new_start):
        problems.append(f"landed on V{track} at frame {start} instead of V{target_track} at {new_start}")
    actual = end - start
    if actual != duration:
        if abs(clip_fps - fps) > 0.01:
            problems.append(
                f"is {actual} frames instead of {duration}: '{clip_name}' in your Media Pool is "
                f"{clip_fps:g} fps but this timeline is {fps:g} fps, so it can only be cut in steps of "
                f"{fps / clip_fps:g} frames. For a frame-exact match, right-click it in the Media Pool -> "
                f"Clip Attributes -> set its frame rate to {fps:g}")
        elif actual < duration:
            problems.append(f"is only {actual} frames instead of {duration} — your '{clip_name}' in the "
                            f"Media Pool is probably shorter than that; make it longer (e.g. 10 minutes) and retry")
        else:
            problems.append(f"is {actual} frames instead of the {duration} asked for")
    if problems:
        return f"{what} placed, but it " + "; ".join(problems) + "."
    if underlying is not None:
        return f"{what} on V{target_track}, matching '{underlying.GetName()}' ({duration} frames)."
    if mode == "fixed":
        return f"{what} on V{target_track}, {duration} frames from the playhead."
    return f"{what} on V{target_track}, {duration} frames - nothing under the playhead to match."


def place_adjustment_clip(settings, timeline, media_pool, clip, mode):
    return place_over(settings, timeline, media_pool, clip, mode, "adjust")


def placed_fine(message, kind="adjust", what=None):
    """Did place_over say it went as asked? (Anything else is worth showing.)"""
    return message.startswith(f"{what or PLACED[kind][0]} on V")


def _first_clip(folder, test, depth=0):
    for clip in folder.GetClipList() or []:
        if test(clip):
            return clip
    if depth < 12:
        for sub in folder.GetSubFolderList() or []:
            found = _first_clip(sub, test, depth + 1)
            if found is not None:
                return found
    return None


def lookup_composition_clip(settings, media_pool):
    """(clip, None) or (None, what to do). The empty Fusion composition the Fusion Composition
    scripts place: the Media Pool clip with the name in Settings > Scripts - or, with that name
    left as it comes, any Fusion composition in the Media Pool, and with none there the app's own
    is brought in (like the adjustment clip)."""
    name = settings.timeline_tools["comp_clip_name"]
    root = media_pool.GetRootFolder()
    clip = find_clip_by_name(root, name)
    if clip is None and name == DEFAULT_COMP_CLIP_NAME:
        clip = _own_clip(media_pool, name) or _first_clip(root, _is_composition)
        if clip is None:
            clip = bring_composition_clip(media_pool, name)
            if clip is not None:
                print(f"[composition] no Fusion composition in this project yet - added one in the \"{stills.CLIPSE_BIN}\" bin.")
    if clip is None:
        return None, (f"No Fusion composition named '{name}' in the Media Pool - make one once: right-click in "
                      f"the Media Pool, New Fusion Composition, and call it that.")
    return clip, None


def used_media_ids(timeline):
    """Media ids of every clip on the timeline's video and audio tracks."""
    ids = set()
    for kind in ("video", "audio"):
        for index in range(1, (timeline.GetTrackCount(kind) or 0) + 1):
            for item in timeline.GetItemListInTrack(kind, index) or []:
                try:
                    clip = item.GetMediaPoolItem()
                    if clip is not None:
                        ids.add(clip.GetMediaId())
                except Exception:
                    pass
    return ids


class UsedParts:
    """Which parts of each Media Pool clip are on the timeline already -
    for the marks under the preview's bar, so the same piece of B-roll
    isn't used twice. Read a little at a time (step), like the Media Pool,
    so a long timeline never makes the preview wait."""

    def __init__(self, timeline):
        self.timeline = timeline
        self.parts = {}    # media id -> {(start seconds, end seconds) in the clip}
        self.done = False
        try:
            self._fps = float(timeline.GetSetting("timelineFrameRate"))
        except (TypeError, ValueError):
            self._fps = 24.0
        self._tracks = [(kind, index) for kind in ("video", "audio")
                        for index in range(1, (timeline.GetTrackCount(kind) or 0) + 1)]
        self._items = []

    def _part(self, item):
        try:  # Resolve 19+: straight in seconds
            start, end = item.GetSourceStartTime(), item.GetSourceEndTime()
            if start is not None and end is not None:
                return float(start), float(end)
        except Exception:
            pass
        left = float(item.GetLeftOffset() or 0)  # older: how far into the clip it starts, in timeline frames
        return left / self._fps, (left + float(item.GetDuration() or 0)) / self._fps

    def step(self, seconds=0.006):
        """Reads on for about `seconds`. True when the whole timeline has been looked at."""
        until = time.monotonic() + seconds
        while not self.done:
            if not self._items:
                if not self._tracks:
                    self.done = True
                    break
                kind, index = self._tracks.pop(0)
                self._items = list(self.timeline.GetItemListInTrack(kind, index) or [])
                continue
            item = self._items.pop()
            try:
                clip = item.GetMediaPoolItem()
                if clip is not None:
                    start, end = self._part(item)
                    if end > start:
                        self.parts.setdefault(clip.GetMediaId(), set()).add((round(start, 3), round(end, 3)))
            except Exception:
                pass  # a title, a generator, a clip Resolve won't tell about
            if time.monotonic() >= until:
                break
        return self.done

    def of(self, media_ids):
        """(the used stretches of these clips joined up, in seconds: [(start, end)], how many times they're used)."""
        spans = sorted(span for media_id in media_ids for span in self.parts.get(media_id, ()))
        joined = []
        for start, end in spans:
            if joined and start <= joined[-1][1] + 0.02:
                joined[-1][1] = max(joined[-1][1], end)
            else:
                joined.append([start, end])
        return [tuple(span) for span in joined], len(spans)


def media_use_counts(timeline):
    """How many times each Media Pool clip is used on the timeline:
    {media id: count}. A video's own linked audio doesn't count twice
    (uses are counted per clip and start position)."""
    seen = set()
    for kind in ("video", "audio"):
        for index in range(1, (timeline.GetTrackCount(kind) or 0) + 1):
            for item in timeline.GetItemListInTrack(kind, index) or []:
                try:
                    clip = item.GetMediaPoolItem()
                    if clip is not None:
                        seen.add((clip.GetMediaId(), item.GetStart()))
                except Exception:
                    pass
    counts = {}
    for media_id, _start in seen:
        counts[media_id] = counts.get(media_id, 0) + 1
    return counts
