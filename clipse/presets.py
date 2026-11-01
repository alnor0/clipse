"""Insert presets: how clips land on the timeline when you press Enter.

A preset answers four questions - where (the playhead, every marker,
every cut), how several clips are spaced (stacked, back to back, spaced
out along a curve), what each clip is (its length, picture and/or sound,
its size and place in the frame) and what happens after (wrap into a
compound or Fusion clip, a clip colour).

The built-in presets can be changed in Insert as for the insert at hand: the
change is never saved, and after the insert they're as they ship again (`used`).
Save as mine keeps it as a preset of your own ("My normal", `own_copy`).
Insert as is for the one insert - a preset of yours is used once, and the next
insert is plain Normal again. Nothing is lost by that:
your presets stay under Yours, the insert is in History, and picking it there
sets Insert as up the way it was (`restore`).

Shortcuts: Ctrl+Enter inserts one clip after another (back_to_back), Alt+M
is At every marker, Alt+C On every cut - as they ship."""
import copy
import re
import math
import random
import time

# every field a preset has, with the value that means "leave it alone"
FIELDS = {
    "name": "",
    "where": "playhead",      # "playhead" | "markers" | "cuts"
    "align": "start",         # markers/cuts: the clip "start"s there, is "centre"d on it, "end"s there, or has
                              # its "loudest" moment there
    "align_pictures": "start",  # markers/cuts: the same for pictures and videos (`align` is the sounds'); a
                              # picture with no sound to go by and "loudest": its start
    "shift": 0.0,             # markers/cuts: seconds the clip is moved from there (+ later)
    "clip_shifts": {},        # markers/cuts: a clip's own extra seconds, by its name, on top of `shift`
    "run_out": "repeat",      # markers/cuts, more markers than clips: "repeat" (start over) | "once" (the rest
                              # get none) | "sounds_repeat" / "pictures_repeat" (only those start over)
    "overlap": "stack",       # markers/cuts, clips that would overlap: "stack" (the next one on the track above) |
                              # "cut_first" (the first stops where the next starts) | "cut_next" (the next starts
                              # where the first ends, its own beginning cut off) | "back_to_back" (the next waits)
    "order": "turns",         # markers/cuts, several clips: "turns" (one after another) | "random"
    "pair": "both",           # markers/cuts, pictures and sounds staged: "both" (one of each on every marker) |
                              # "turns" (they take turns with each other, one clip per marker)
    "repeat": "once",         # playhead, back to back or spaced out, more of one kind than the other: "once" |
                              # "match" (the fewer start over until every sound has a picture - 1 picture and
                              # 10 sounds: the picture goes in with every sound, `repeated`)
    "pictures_count": 0,      # Repeat (playhead, one after another): this many pictures in all, starting over (0:
    "sounds_count": 0,        # Match - as many as the other kind) ... and sounds. 1 picture and 2 sounds, 20 and
                              # 20: twenty of each, a picture with every sound (2026-10-16: "the most
                              # versatile and simple options")
    "marker_colours": [],     # markers: only the ones of these colours ("Blue", "Red" ...); none = every marker
    "cut_tracks": ["V1"],     # cuts: the tracks whose cuts count ("V1", "V2", "A1" ...) - every one where a clip on
                              # one of them begins after another (2026-10-17: "v1 v2 v3 a1 a2 a3?")
    "cut_edges": "between",   # cuts: "between" (where one clip begins after another) | "starts" (every clip's start,
                              # the first too) | "ends" (every clip's end, the last too) | "both"
    "spacing": "together",    # several clips: "together" (stacked) | "back_to_back" | "interval"
    "gap": 12,                # interval: frames from one clip's start to the next - the first gap
    "gap_end": 12,            # ... and the last; the curve goes from one to the other
    "curve": [0.333, 0.333, 0.667, 0.667],  # cubic-bezier (x1, y1, x2, y2) from the first gap to the last
    "curve_strength": 1.0,    # the curve applied to itself this many times (1.5: halfway to twice) - eases harder
    "vary": 0,                # interval: each gap a random +- this many frames
    "ends": "own",            # pictures / videos: "own" (each its own length) | "together" (all end at once,
                              # where the last one ends) | "audio" (all end where the sounds end)
    "ends_audio": "own",      # ...and sounds, by themselves: "own" | "together" | "pictures" (all end where the
                              # pictures end - 2026-10-16, the twin of the pictures' "audio") | "first" (all end where
                              # the FIRST one ends)
    "gaps": "",               # interval: exact gaps instead ("17, 13, 9, 8, 4"), the last one repeats
    "length": 0.0,            # seconds each video or picture lasts (0: the whole clip; a picture: "A picture lasts")
    "length_audio": 0.0,      # seconds each sound lasts (0: the whole sound)
    "media": "both",          # "both" | "video" (just the picture) | "audio" (just the sound)
    "scale": 100.0,           # % - of what size_by measures against
    "size_by": "fit",         # "fit" (100 %: the whole picture, as Resolve fits it) | "width" (as wide as the frame) |
                              # "height" (as tall) | "fill" (covering it, no bars) - 2026-10-17
    "scale_vary": 0.0,        # +- % at random
    "x": 0.0,                 # % of the frame's width, + is right
    "y": 0.0,                 # % of the frame's height, + is up
    "scatter": 0.0,           # % of the frame - each clip lands somewhere random within this
    "scatter_random": 50.0,   # % - how loosely they're scattered: 0 a tidy grid, 100 anywhere near their spot
    "rotation": 0.0,          # degrees
    "rotation_vary": 0.0,     # +- degrees at random
    "opacity": 100.0,         # %
    "inside": True,           # keep every picture wholly inside the frame (size and turn counted)
    "apart": False,           # scattered pictures never touch: moved apart, all made smaller where there's no room
    "margin": 0.0,            # % of the frame kept free at the edges; below 0: that far over the edge is fine
    "convert": "none",        # afterwards: "none" | "compound" | "fusion"
    "colour": "",             # afterwards: a Resolve clip colour, or "" to leave it
}

ALIGNS = ("start", "centre", "end", "loudest")
OVERLAPS = ("stack", "cut_first", "cut_next", "back_to_back")
RUN_OUTS = ("repeat", "once", "sounds_repeat", "pictures_repeat")
SHIFT_MAX = 10.0  # seconds a clip can be moved off its marker, either way
COUNT_MAX = 999   # Repeat: at most this many pictures (or sounds)

CURVES = {  # name -> cubic-bezier, for the curve tiles
    "linear": [0.333, 0.333, 0.667, 0.667],
    "ease_in": [0.55, 0.0, 1.0, 0.45],
    "ease_out": [0.0, 0.55, 0.45, 1.0],
    "ease_in_out": [0.6, 0.0, 0.4, 1.0],
}
CURVE_LABELS = {"linear": "Even", "ease_in": "Ease in", "ease_out": "Ease out", "ease_in_out": "Ease in & out",
                "custom": "Your curve"}

# Resolve's marker colours, in the order its menu has them
MARKER_HEX = {"Blue": "#3f8fe8", "Cyan": "#35c4dc", "Green": "#3fb65f", "Yellow": "#e2c84a", "Red": "#e0504a",
              "Pink": "#f08ab0", "Purple": "#9258d6", "Fuchsia": "#cf46bd", "Rose": "#e89aa6",
              "Lavender": "#a6a2ea", "Sky": "#8cc6f0", "Mint": "#86dcbc", "Lemon": "#e6e283", "Sand": "#d6bd8c",
              "Cocoa": "#8c6a52", "Cream": "#efe6cc"}

CLIP_COLOURS = ["Apricot", "Yellow", "Lime", "Olive", "Green", "Teal", "Navy", "Blue", "Purple", "Violet",
                "Pink", "Tan", "Beige", "Brown", "Chocolate", "Orange"]
COLOUR_HEX = {"Orange": "#e8892c", "Apricot": "#f0a36b", "Yellow": "#e2c34d", "Lime": "#9fc94a",
              "Olive": "#5f9845", "Green": "#3fa66b", "Teal": "#2fa3a3", "Navy": "#3a5aa0", "Blue": "#4b8fe0",
              "Purple": "#8a5ad6", "Violet": "#c157c9", "Pink": "#e06c9f", "Tan": "#c6a27e", "Beige": "#d9c7a7",
              "Brown": "#9a6a3e", "Chocolate": "#7a4a2a"}


def _p(pid, name, **fields):
    preset = copy.deepcopy(FIELDS)
    preset.update(fields)
    preset["id"], preset["name"], preset["builtin"] = pid, name, True
    return preset


# Only the plain ways clips go on the timeline are built in. Anything else you set up
# yourself in Insert as (and Duplicate keeps it as one of your own).
GROUPS = [("yours", "")]  # Normal first, then yours - one row, no heading (there's nothing to tell apart)
BUILTINS = [
    _p("normal", "Normal", group="yours"),
]
# Built in once (the first three until 1.41.1, the looks until 1.42): name, and what it was
RETIRED = {
    # (Back to back was Normal with one setting changed - 2026-10-14: "that is just stacked, with one
    # setting changed?". Ctrl+Enter still inserts back to back: back_to_back())
    "back_to_back": ("Back to back", dict(spacing="back_to_back")),
    # (At every marker and On every cut were Normal with Where changed - the same three choices twice, above the
    # editor and in it: "normal, every marker, and every cut are there twice". Alt+M / Alt+C: placing())
    "markers": ("At every marker", dict(where="markers", align="start", align_pictures="start")),
    "cuts": ("On every cut", dict(where="cuts", align="centre", align_pictures="centre")),
    "slow_down": ("Slow down", dict(spacing="interval", gap=3, gap_end=24, curve=list(CURVES["ease_in"]))),
    "compound": ("As a compound clip", dict(convert="compound")),
    "fusion": ("As a Fusion clip", dict(convert="fusion")),
    "spaced": ("Stagger", dict(spacing="interval", gap=8, gap_end=8)),
    "speed_up": ("Speed up", dict(spacing="interval", gap=24, gap_end=3, curve=list(CURVES["ease_out"]))),
    "scattered": ("Photo pile", dict(spacing="interval", gap=6, gap_end=6, scale=42.0, scale_vary=18.0, scatter=100.0,
                                     rotation_vary=7.0, margin=-4.0)),
    "build_up": ("Build up", dict(spacing="interval", gap=10, gap_end=10, ends="together")),
    "slideshow": ("Slideshow", dict(spacing="back_to_back", length=3.0)),
    "quick_cuts": ("Quick cuts", dict(spacing="back_to_back", length=0.5)),
    "collage": ("Collage", dict(scale=34.0, scale_vary=6.0, scatter=100.0, margin=3.0)),
    "pip": ("Picture in picture", dict(scale=32.0, x=100.0, y=-100.0, margin=4.0)),
    "logo": ("Corner logo", dict(scale=14.0, x=100.0, y=100.0, margin=4.0, opacity=85.0)),
    "overlay": ("Overlay", dict(media="video", opacity=50.0)),
}
BUILTIN_IDS = [b["id"] for b in BUILTINS]
# what the fixed shortcuts use
def placing(settings, where):
    """Alt+M / Alt+C: what Insert as is set up to do, at every marker (or cut). Set up for the playhead, it's
    a plain one there: at markers each clip starts on its marker, at cuts it's centred on the cut."""
    base = active(settings)
    if base["where"] != where:
        base = dict(base, where=where, **({"align": "centre", "align_pictures": "centre"} if where == "cuts"
                                         else {"align": "start", "align_pictures": "start"}))
    preset = _clean(base)
    preset["id"] = active(settings)["id"] if active(settings)["where"] == where else "normal"
    preset["name"] = active(settings)["name"] if active(settings)["where"] == where else (
        "At every marker" if where == "markers" else "On every cut")
    return preset


def back_to_back(settings):
    """Ctrl+Enter: what Insert as is set up to do, one clip after another (at the playhead; set up for
    markers or cuts, it's a plain insert one after another)."""
    base = active(settings)
    if base["where"] != "playhead":
        base = _clean(FIELDS)
    preset = _clean(dict(base, spacing="back_to_back"))
    preset["id"], preset["name"] = "back_to_back", "Back to back"
    return preset

DEFAULTS = {"user": [], "edits": {}, "active": "normal", "keep": False, "migrated": False, "seeds": {},
            "still_length": 5.0}  # seconds a picture lasts when a preset's Length is "Whole clip"


# -- the list --
def _clean(preset):
    out = copy.deepcopy(FIELDS)
    for key, value in (preset or {}).items():
        if key not in FIELDS:
            continue
        default = FIELDS[key]
        number = isinstance(value, (int, float)) and not isinstance(value, bool)
        if (isinstance(default, (int, float)) and number) or isinstance(value, type(default)):
            out[key] = value
    for key in ("gap", "gap_end", "vary"):
        out[key] = int(out[key])
    for key in ("pictures_count", "sounds_count"):
        out[key] = max(0, min(COUNT_MAX, int(out[key])))
    out["curve_strength"] = max(1.0, min(4.0, float(out["curve_strength"])))
    for key in ("length", "length_audio", "scatter_random", "scale", "scale_vary", "x", "y", "scatter", "rotation", "rotation_vary", "opacity", "margin"):
        out[key] = float(out[key])
    out["marker_colours"] = [c for c in MARKER_HEX if c in out["marker_colours"]]
    out["cut_tracks"] = track_order(t for t in out["cut_tracks"] if _TRACK.fullmatch(str(t))) or ["V1"]
    out["shift"] = max(-SHIFT_MAX, min(SHIFT_MAX, float(out["shift"])))
    if "align_pictures" not in (preset or {}):  # (saved when one "On the marker" was for every clip)
        out["align_pictures"] = out["align"] if out["align"] != "loudest" else "start"
    for key, allowed in (("align", ALIGNS), ("align_pictures", ALIGNS), ("overlap", OVERLAPS),
                         ("order", ("turns", "random")), ("pair", ("both", "turns")), ("run_out", RUN_OUTS),
                         ("repeat", ("once", "match")), ("cut_edges", CUT_EDGES), ("size_by", SIZE_BY)):
        if out[key] not in allowed:
            out[key] = FIELDS[key]
    out["clip_shifts"] = {str(name): max(-SHIFT_MAX, min(SHIFT_MAX, float(sec)))
                          for name, sec in out["clip_shifts"].items()
                          if isinstance(sec, (int, float)) and not isinstance(sec, bool) and sec}
    if not (isinstance(out["curve"], list) and len(out["curve"]) == 4):
        out["curve"] = list(FIELDS["curve"])
    return out


def _with_sound_length(saved):
    """Until 1.42 one Length was for pictures and sounds alike: a preset saved then keeps cutting its sounds."""
    if "length" in saved and "length_audio" not in saved:
        saved = {**saved, "length_audio": saved["length"]}
    if "ends" in saved and "ends_audio" not in saved:  # ...and one Ends, likewise
        saved = {**saved, "ends_audio": saved["ends"]}
    return saved


def all_presets(settings):
    """The built-ins (with your edits), then your own."""
    store = settings.presets
    out = []
    for builtin in BUILTINS:
        preset = _clean({**builtin, **_with_sound_length(store["edits"].get(builtin["id"], {}))})
        preset["id"], preset["builtin"], preset["group"] = builtin["id"], True, builtin["group"]
        preset["edited"] = bool(store["edits"].get(builtin["id"]))
        out.append(preset)
    for own in store["user"]:
        preset = _clean(_with_sound_length(own))
        preset["id"], preset["builtin"], preset["edited"] = own.get("id") or _new_id(), False, False
        preset["group"] = "yours"
        out.append(preset)
    return out


def get(settings, pid):
    for preset in all_presets(settings):
        if preset["id"] == pid:
            return preset
    return None


def active(settings):
    return get(settings, settings.presets.get("active")) or get(settings, "normal")


def set_active(settings, pid):
    settings.presets["active"] = pid


def _new_id():
    return f"own_{int(time.time() * 1000):x}{random.randint(0, 255):02x}"


def save(settings, preset):
    """Stores `preset` - a built-in keeps only what differs from how it ships."""
    clean = _clean(preset)
    pid = preset["id"]
    if pid in BUILTIN_IDS:
        base = next(b for b in BUILTINS if b["id"] == pid)
        diff = {k: v for k, v in clean.items() if k in FIELDS and v != base.get(k)}
        # (said outright beside its twin - or _with_sound_length would take it for a preset saved before
        # sounds had their own, and copy the pictures' over it)
        for key, twin in (("length", "length_audio"), ("ends", "ends_audio")):
            if key in diff:
                diff[twin] = clean[twin]
        if diff:
            settings.presets["edits"][pid] = diff
        else:
            settings.presets["edits"].pop(pid, None)
        return
    clean["id"] = pid
    users = settings.presets["user"]
    for i, own in enumerate(users):
        if own.get("id") == pid:
            users[i] = clean
            return
    users.append(clean)


def copy_name(settings, preset):
    """What a copy of `preset` is called: "My normal" of a built-in one, "Name 2" of one of yours."""
    taken = {p["name"] for p in all_presets(settings)}
    base = preset["name"] if not preset.get("builtin") else f"My {preset['name'][0].lower()}{preset['name'][1:]}"
    name, n = base, 2
    while name in taken:
        name, n = f"{base} {n}", n + 1
    return name


def duplicate(settings, preset):
    copy_of = _clean(preset)
    copy_of["id"] = _new_id()
    copy_of["name"] = copy_name(settings, preset)
    save(settings, copy_of)
    return get(settings, copy_of["id"])


def own_copy(settings, preset):
    """`preset` - a built-in one that's just been changed in Insert as - as one of your own: the
    built-in stays as it ships, the change lives in a copy under Yours ("My normal"), which is
    the one in use. Returns the copy's (id, name)."""
    copy_of = _clean(preset)
    copy_of["id"] = _new_id()
    taken = {p["name"] for p in all_presets(settings)}
    base = f"My {preset['name'][0].lower()}{preset['name'][1:]}"
    name, n = base, 2
    while name in taken:
        name, n = f"{base} {n}", n + 1
    copy_of["name"] = name
    settings.presets["user"].append(copy_of)
    settings.presets["active"] = copy_of["id"]
    seeds = settings.presets.setdefault("seeds", {})
    if preset.get("id") in seeds:  # the same pictures in the same places as the frame was showing
        seeds[copy_of["id"]] = seeds[preset["id"]]
    return copy_of["id"], name


def edits_to_own(settings):
    """Built-in presets used to be edited in place. What was changed that way becomes a preset of
    your own, once, and the built-in goes back to how it ships."""
    store = settings.presets
    for builtin in BUILTINS:
        edits = store["edits"].pop(builtin["id"], None)
        if not edits:
            continue
        changed = _clean({**builtin, **_with_sound_length(edits)})
        changed["name"], changed["id"] = builtin["name"], builtin["id"]
        in_use = store.get("active")
        pid, _name = own_copy(settings, changed)
        store["active"] = pid if in_use == builtin["id"] else in_use  # (what was in use stays in use)


def delete(settings, pid):
    if pid in BUILTIN_IDS:
        settings.presets["edits"].pop(pid, None)  # a built-in goes back to how it ships
    else:
        settings.presets["user"] = [p for p in settings.presets["user"] if p.get("id") != pid]
    if settings.presets.get("active") == pid and pid not in BUILTIN_IDS:
        settings.presets["active"] = "normal"


def plain(preset):
    """Is this the plain insert - Normal as it ships, nothing set?"""
    clean = _clean(preset)
    return all(clean[key] == FIELDS[key] for key in FIELDS if key != "name")


def used(settings, preset):
    """An insert was made with `preset`: Insert as is for the one insert, so the next one is plain
    again - Normal in use, and Normal back to how it ships if it was what had been set up. (What
    was set up isn't lost: the insert is in History, and picking it there puts it back - restore.)
    The built-ins go back to how they ship (a change to one is for the insert at hand - Save as mine
    keeps it); your own presets stay as they are. presets "keep" switches this off."""
    store = settings.presets
    if store.get("keep"):
        return False
    changed = store.get("active") != "normal" or bool(store["edits"])
    store["active"] = "normal"
    store["edits"].clear()  # every built-in back to how it ships
    return changed


def restore(settings, preset):
    """History: the Insert as settings an insert was made with are the ones in use again - one of
    your own presets (if it's still there, unchanged) by name, anything else as a preset of your
    own called "From history". Returns what to call it."""
    clean = _clean(_with_sound_length(preset or {}))
    for own in all_presets(settings):
        if own["id"] == (preset or {}).get("id") and own["id"] != "normal" \
                and all(own[key] == clean[key] for key in FIELDS if key != "name"):
            settings.presets["active"] = own["id"]
            return own["name"]
    if plain(clean):
        settings.presets["active"] = "normal"
        return ""
    # ...as a preset of your own called "From history" (the one before it is written over)
    users = settings.presets["user"]
    kept = next((own for own in users if own.get("name") == "From history"), None)
    clean["name"] = "From history"
    clean["id"] = kept["id"] if kept else _new_id()
    if kept:
        users[users.index(kept)] = clean
    else:
        users.append(clean)
    settings.presets["active"] = clean["id"]
    return summary(clean)


def tidy(settings):
    """There used to be more built-in presets. One you had changed isn't lost: it
    becomes one of your own, under its old name."""
    store = settings.presets
    for pid, (name, was) in RETIRED.items():
        edits = store["edits"].pop(pid, None)
        if edits:
            own = _clean({**FIELDS, **was, **edits, "name": name})
            own["id"] = _new_id()
            store["user"].append(own)
            if store.get("active") == pid:
                store["active"] = own["id"]
        if store.get("active") == pid:
            store["active"] = "normal"
        (store.get("seeds") or {}).pop(pid, None)


def migrate(settings):
    """Insert Options from before presets (1.36 and older) -> presets: a
    stagger you had set up becomes one of your own, and "At markers and
    cuts" moves into the two presets that use it."""
    store = settings.presets
    tidy(settings)
    edits_to_own(settings)
    if store.get("migrated"):
        return
    store["migrated"] = True
    adv = getattr(settings, "advanced", {}) or {}
    align = (getattr(settings, "timeline_tools", {}) or {}).get("place_align", "start")
    if align != "start":
        for pid in ("markers", "cuts"):
            store["edits"].setdefault(pid, {})["align"] = align
    mine = {}
    curve = adv.get("stagger_video_curve", "linear")
    if curve == "custom" and str(adv.get("stagger_video_custom_gaps", "")).strip():
        mine.update(spacing="interval", gaps=str(adv["stagger_video_custom_gaps"]).strip(),
                    gap=12, gap_end=12)
    elif adv.get("stagger_video_offset_frames", 0):
        start = int(adv["stagger_video_offset_frames"])
        if curve == "ease_out":
            mine.update(spacing="interval", gap=start, gap_end=int(adv.get("stagger_video_floor", 2)),
                        curve=list(CURVES["ease_out"]))
        else:
            mine.update(spacing="interval", gap=start, gap_end=start)
    if adv.get("audio_custom_length_enabled"):
        mine["length"] = round(int(adv.get("audio_custom_length_frames", 180)) / 30.0, 2)
    if adv.get("video_track_scale_percent", 100) != 100:
        mine["scale"] = float(adv["video_track_scale_percent"])
    if adv.get("convert_to_clip_type") in ("compound", "fusion"):
        mine["convert"] = adv["convert_to_clip_type"]
    if mine:
        preset = _clean({**FIELDS, **mine})
        preset["id"], preset["name"] = _new_id(), "My stagger" if "gap" in mine or "gaps" in mine else "My insert"
        store["user"].append(preset)


# -- timing --
def _bezier(t, a, b):
    """One coordinate of a cubic bezier from 0 to 1 with handles a and b."""
    u = 1 - t
    return 3 * u * u * t * a + 3 * u * t * t * b + t ** 3


def ease(curve, x):
    """y of the curve at x (both 0-1) - like CSS cubic-bezier()."""
    x1, y1, x2, y2 = curve
    x = min(1.0, max(0.0, x))
    lo, hi = 0.0, 1.0
    for _ in range(40):  # x(t) only ever grows: bisect for the t that gives x
        mid = (lo + hi) / 2
        if _bezier(mid, x1, x2) < x:
            lo = mid
        else:
            hi = mid
    return _bezier((lo + hi) / 2, y1, y2)


def eased(preset, x):
    """The preset's curve at x - applied to itself `curve_strength` times,
    which is what makes an ease in or out really drastic."""
    strength = max(1.0, float(preset.get("curve_strength", 1.0)))
    for _ in range(int(strength)):
        x = ease(preset["curve"], x)
    part = strength - int(strength)
    return x + (ease(preset["curve"], x) - x) * part if part > 1e-6 else x


def exact_gaps(preset):
    try:
        return [max(0, int(round(float(v)))) for v in str(preset.get("gaps", "")).replace(";", ",").split(",")
                if v.strip()]
    except ValueError:
        return []


def gaps(preset, count, rng=None):
    """The count-1 gaps (frames, start to start) between `count` clips."""
    needed = max(0, count - 1)
    listed = exact_gaps(preset)
    if listed:
        out = (listed + [listed[-1]] * needed)[:needed]
    else:
        out = []
        for k in range(needed):
            t = k / (needed - 1) if needed > 1 else 0.0
            out.append(preset["gap"] + (preset["gap_end"] - preset["gap"]) * eased(preset, t))
    vary = int(preset.get("vary", 0))
    if vary and rng is not None:
        out = [g + rng.uniform(-vary, vary) for g in out]
    return [max(0, int(round(g))) for g in out]


def offsets(preset, count, rng=None):
    out = [0]
    for g in gaps(preset, count, rng):
        out.append(out[-1] + g)
    return out[:count] if count else []


SIZE_BY = ("fit", "width", "height", "fill")


def has_picture_changes(preset):
    return any(preset[k] != FIELDS[k] for k in ("scale", "size_by", "scale_vary", "x", "y", "scatter", "rotation",
                                                "rotation_vary", "opacity"))


def size_zoom(size_by, base_w, base_h, fw, fh):
    """The zoom at which a picture fitted to base_w x base_h (zoom 1) is 100 % by `size_by`: as wide as the frame,
    as tall, covering it - or as it is (fit)."""
    wide, tall = fw / max(1e-6, base_w), fh / max(1e-6, base_h)
    return {"width": wide, "height": tall, "fill": max(wide, tall)}.get(size_by, 1.0)


def _fitted(aspect, fw, fh, mode="fit", pixels=None):
    """How big a picture of this shape is in the frame at zoom 1, by the
    project's Image Scaling -> Mismatched resolution files:
    fit (scale entire image to fit - Resolve's default), fill (scale full
    frame with crop), stretch, or native (center crop with no resizing)."""
    if mode == "stretch":
        return fw, fh
    if mode == "native" and pixels:
        return float(pixels[0]), float(pixels[1])
    wider = aspect >= fw / fh
    if mode == "fill":
        return (fh * aspect, fh) if wider else (fw, fw / aspect)
    return (fw, fw / aspect) if wider else (fh * aspect, fh)


def _rotated_box(w, h, degrees):
    a = math.radians(degrees)
    c, s = abs(math.cos(a)), abs(math.sin(a))
    return w * c + h * s, w * s + h * c


def layout(preset, count, frame_w, frame_h, aspects=None, seed=0, mode="fit"):
    """Where each of `count` pictures goes: [{zoom, pan, tilt, angle}] -
    zoom 1 = as Resolve scales it to the frame, pan/tilt = how far its
    middle is from the frame's, in timeline pixels (+ is right/up).
    props_for() turns that into Resolve's own Pan/Tilt numbers.

    - The same seed gives the same layout - the editor's preview shows
      exactly what the next insert does.
    - "Keep inside the frame": each picture's size and turn are taken into
      account, and it's placed (or made a little smaller) so all of it shows.
    - Scatter spreads them over all the room there is, edges and corners
      included (_spots) - so a pile of pictures fills the frame."""
    rng = random.Random(seed)
    inside = preset.get("inside", True)
    margin = max(-45.0, float(preset.get("margin", 0.0))) / 100.0  # below 0: that far over the edge is fine
    fw, fh = float(frame_w), float(frame_h)
    # a hair of room on top of the margin, so rounding never puts an edge a pixel outside
    room_w, room_h = fw * (1 - 2 * margin) - 4, fh * (1 - 2 * margin) - 4
    spread = preset["scatter"] / 100.0
    out, reach = [], []  # reach: where each picture's middle may be - (lo_x, hi_x, lo_y, hi_y)
    for i in range(count):
        given = aspects[i] if aspects and i < len(aspects) else None
        pixels = given if isinstance(given, tuple) else None
        aspect = (pixels[0] / pixels[1]) if pixels else (given or 16 / 9)
        base_w, base_h = _fitted(aspect, fw, fh, mode, pixels)
        size_by = preset.get("size_by", "fit")
        zoom = max(0.01, size_zoom(size_by, base_w, base_h, fw, fh)
                   * preset["scale"] * (1 + rng.uniform(-1, 1) * preset["scale_vary"] / 100.0) / 100.0)
        angle = preset["rotation"] + rng.uniform(-1, 1) * preset["rotation_vary"]
        bw, bh = _rotated_box(base_w * zoom, base_h * zoom, angle)
        # (as wide / as tall as the frame, or filling it, is meant to reach its edges: never shrunk back inside)
        if inside and size_by == "fit" and (bw > room_w or bh > room_h):
            shrink = min(room_w / bw, room_h / bh)
            zoom, bw, bh = zoom * shrink, bw * shrink, bh * shrink
        cx, cy = preset["x"] / 100.0 * fw, preset["y"] / 100.0 * fh
        lo_x, hi_x = cx - spread * fw, cx + spread * fw
        lo_y, hi_y = cy - spread * fh, cy + spread * fh
        if inside:  # where its middle can be with all of it in the frame
            lim_x, lim_y = max(0.0, (room_w - bw) / 2), max(0.0, (room_h - bh) / 2)
            lo_x, hi_x = _overlap(lo_x, hi_x, -lim_x, lim_x)
            lo_y, hi_y = _overlap(lo_y, hi_y, -lim_y, lim_y)
        reach.append((lo_x, hi_x, lo_y, hi_y))
        out.append({"zoom": zoom, "pan": 0.0, "tilt": 0.0, "angle": angle, "aspect": aspect,
                    "size": (base_w, base_h), "frame": (fw, fh), "box": (bw, bh)})
    loose = max(0.0, min(100.0, float(preset.get("scatter_random", 50.0)))) / 100.0
    spots = _spots(count, reach, rng, loose) if spread > 0 and count > 1 else [(rng.random(), rng.random()) for _ in out]
    for place, (lo_x, hi_x, lo_y, hi_y), (fx, fy) in zip(out, reach, spots):
        place["pan"], place["tilt"] = lo_x + (hi_x - lo_x) * fx, lo_y + (hi_y - lo_y) * fy
    if preset.get("apart") and spread > 0 and count > 1:
        _apart(out, preset, fw, fh, room_w, room_h, spread, inside)
    return out


def _apart(out, preset, fw, fh, room_w, room_h, spread, inside):
    """Not touching: scattered pictures are pushed apart until none touch - a little room (1 % of the frame)
    between any two, their turned outlines counted - each within where it may go. Where there's no room for
    all of them at their size, they're all made a little smaller and tried again."""
    gap = 0.01 * fw
    cx, cy = preset["x"] / 100.0 * fw, preset["y"] / 100.0 * fh
    for _attempt in range(5):
        limits = []
        for p in out:
            bw, bh = p["box"]
            lo_x, hi_x, lo_y, hi_y = cx - spread * fw, cx + spread * fw, cy - spread * fh, cy + spread * fh
            if inside:
                lim_x, lim_y = max(0.0, (room_w - bw) / 2), max(0.0, (room_h - bh) / 2)
                lo_x, hi_x = _overlap(lo_x, hi_x, -lim_x, lim_x)
                lo_y, hi_y = _overlap(lo_y, hi_y, -lim_y, lim_y)
            limits.append((lo_x, hi_x, lo_y, hi_y))
            p["pan"], p["tilt"] = min(hi_x, max(lo_x, p["pan"])), min(hi_y, max(lo_y, p["tilt"]))
        for _round in range(40):
            touching = False
            for i in range(len(out)):
                a = out[i]
                for j in range(i + 1, len(out)):
                    b = out[j]
                    dx, dy = b["pan"] - a["pan"], b["tilt"] - a["tilt"]
                    need_x = (a["box"][0] + b["box"][0]) / 2 + gap - abs(dx)
                    need_y = (a["box"][1] + b["box"][1]) / 2 + gap - abs(dy)
                    if need_x <= 0 or need_y <= 0:
                        continue
                    touching = True
                    if need_x / fw < need_y / fh:  # (apart the shorter way)
                        push = (need_x / 2 + 0.5) * (1 if dx >= 0 else -1)
                        a["pan"], b["pan"] = a["pan"] - push, b["pan"] + push
                    else:
                        push = (need_y / 2 + 0.5) * (1 if dy >= 0 else -1)
                        a["tilt"], b["tilt"] = a["tilt"] - push, b["tilt"] + push
                    for n in (i, j):
                        lo_x, hi_x, lo_y, hi_y = limits[n]
                        out[n]["pan"] = min(hi_x, max(lo_x, out[n]["pan"]))
                        out[n]["tilt"] = min(hi_y, max(lo_y, out[n]["tilt"]))
            if not touching:
                return
        for p in out:  # no room for them all at this size: all a little smaller, and again
            p["zoom"] *= 0.92
            p["box"] = (p["box"][0] * 0.92, p["box"][1] * 0.92)
    # still touching: each its own cell of an even grid over the room they have - made small enough for it,
    # placed anywhere inside it (Randomness: how far from its middle). Can't touch, however many there are.
    loose = max(0.0, min(100.0, float(preset.get("scatter_random", 50.0)))) / 100.0
    area_w = min(room_w if inside else fw, 2 * spread * fw + max(p["box"][0] for p in out))
    area_h = min(room_h if inside else fh, 2 * spread * fh + max(p["box"][1] for p in out))
    cols = max(1, int(math.ceil(math.sqrt(len(out) * area_w / max(1.0, area_h)))))
    rows = max(1, int(math.ceil(len(out) / cols)))
    cell_w, cell_h = area_w / cols, area_h / rows
    rng = random.Random(len(out) * 7919 + int(spread * 1000))
    cells = rng.sample(range(cols * rows), len(out))
    for p, cell in zip(out, cells):
        fit = min(1.0, (cell_w - gap) / max(1.0, p["box"][0]), (cell_h - gap) / max(1.0, p["box"][1]))
        p["zoom"], p["box"] = p["zoom"] * fit, (p["box"][0] * fit, p["box"][1] * fit)
        slack_x, slack_y = max(0.0, cell_w - gap - p["box"][0]) / 2, max(0.0, cell_h - gap - p["box"][1]) / 2
        p["pan"] = cx + (cell % cols + 0.5) * cell_w - area_w / 2 + rng.uniform(-1, 1) * slack_x * loose
        p["tilt"] = cy + (cell // cols + 0.5) * cell_h - area_h / 2 + rng.uniform(-1, 1) * slack_y * loose


def _spots(count, reach, rng, loose=0.5):
    """Where `count` scattered pictures go, each as (0-1, 0-1) of its own reach: spread over all of it.

    A grid as wide and high as the reach is, its outer rows and columns ON the edges - so the pictures
    there touch the frame's edges and corners - and the others moved about a little inside theirs, so
    it doesn't look ruled. (Random spots, even picking the emptiest of a dozen, left the corners bare
    nearly every time and a fifth of the frame uncovered: "I can't get the images to fill the frame".)
    With fewer pictures than cells, the cells furthest from each other are the ones used - the corners
    first. Which picture gets which cell is drawn by lot: the order they go on stays mixed.
    loose (0-1, Insert as > Randomness): how far a picture may stray from its cell - 0 a ruled grid,
    0.5 as described, towards 1 the outer ones leave the edges too and it turns into a loose pile."""
    wide = max(0.0, sum(hi_x - lo_x for lo_x, hi_x, _a, _b in reach) / count)
    high = max(0.0, sum(hi_y - lo_y for _a, _b, lo_y, hi_y in reach) / count)
    # never more columns than pictures: pictures as tall as the frame leave a reach of a rounding error
    # (7e-15 px) up and down, and the grid for that was 70 million columns - 20 GB, the app killed (2026-10-15)
    ratio = wide / high if high > 1e-6 else (math.inf if wide > 1e-6 else 1.0)
    cols = max(1, min(count, int(round(math.sqrt(count * ratio))) if ratio != math.inf else count))
    rows = max(1, int(math.ceil(count / cols)))
    while cols * rows < count:
        cols += 1
    cells = [(c / (cols - 1) if cols > 1 else 0.5, r / (rows - 1) if rows > 1 else 0.5)
             for r in range(rows) for c in range(cols)]
    corners = [n for n, (x, y) in enumerate(cells) if x in (0.0, 1.0) and y in (0.0, 1.0)]
    chosen = [rng.choice(corners or list(range(len(cells))))]
    far = [math.inf] * len(cells)   # each cell's distance to the nearest one taken
    while len(chosen) < count:
        last = cells[chosen[-1]]
        far[chosen[-1]] = -1.0
        for n, (x, y) in enumerate(cells):
            if far[n] >= 0:
                far[n] = min(far[n], math.hypot((x - last[0]) * wide, (y - last[1]) * high))
        best = max(far)
        chosen.append(rng.choice([n for n, d in enumerate(far) if d >= best - 1e-9]))
    rng.shuffle(chosen)
    spots = []
    for n in chosen:
        x, y = cells[n]
        stray, inward = 0.7 * loose, max(0.0, loose - 0.5) * 1.2   # in cells
        if cols == 1:      # one column: anywhere across
            x = rng.random() if loose > 0 else 0.5
        elif 0.0 < x < 1.0:
            x = min(1.0, max(0.0, x + rng.uniform(-stray, stray) / (cols - 1)))
        elif inward:       # (a cell on an edge stays on it, until it's let loose)
            x = abs(x - rng.uniform(0.0, inward) / (cols - 1))
        if rows == 1:
            y = rng.random() if loose > 0 else 0.5
        elif 0.0 < y < 1.0:
            y = min(1.0, max(0.0, y + rng.uniform(-stray, stray) / (rows - 1)))
        elif inward:
            y = abs(y - rng.uniform(0.0, inward) / (rows - 1))
        spots.append((x, y))
    return spots


def _overlap(lo, hi, lo2, hi2):
    """The part of [lo, hi] inside [lo2, hi2] - or the nearest point of it if they don't meet."""
    a, b = max(lo, lo2), min(hi, hi2)
    if a <= b:
        return a, b
    point = lo2 if hi < lo2 else hi2
    return point, point


PAN_REACH = 1.0  # measured in 21.1.1 on a 1920 x 1080 timeline (2026-10-14), by the viewer's own ruler:
# a 1000 x 977 logo at zoom 0.3 and 0.5, Pan 300 / 400 / -500 moved it 0.58 x as far (its width at zoom 1 is
# 0.58 of the frame's), Tilt 200 moved it 200. It used to be 2.0: every scattered picture landed half as far
# out as planned, the lot bunched in the middle ("this is how it looks for me when I insert it").


def resolve_pan(place):
    """(Pan, Tilt) that put a picture's middle place["pan"], place["tilt"]
    timeline pixels from the frame's.

    Resolve's Pan isn't in timeline pixels: a Pan of p moves the picture
    p * (its width at zoom 1 / the frame's width) pixels, whatever
    its Zoom or Rotation - so a narrow picture moves less than a wide one for
    the same number. Tilt is the same with heights."""
    (base_w, base_h), (fw, fh) = place["size"], place["frame"]
    return (place["pan"] * fw / (PAN_REACH * base_w) if base_w else 0.0,
            place["tilt"] * fh / (PAN_REACH * base_h) if base_h else 0.0)


def props_for(preset, place):
    """Resolve's Inspector values for one placed picture - only the ones that change."""
    props = {}
    if abs(place["zoom"] - 1.0) > 1e-6:
        props["ZoomX"] = props["ZoomY"] = round(place["zoom"], 4)
    pan, tilt = resolve_pan(place)
    if abs(pan) > 0.01:
        props["Pan"] = round(pan, 2)
    if abs(tilt) > 0.01:
        props["Tilt"] = round(tilt, 2)
    if abs(place["angle"]) > 0.01:
        props["RotationAngle"] = round(place["angle"], 2)
    if preset["opacity"] < 100:
        props["Opacity"] = round(max(0.0, preset["opacity"]), 1)
    return props


def seed_for(settings, pid):
    """The layout the preview shows for this preset - and the next insert uses."""
    seeds = settings.presets.setdefault("seeds", {})
    if pid not in seeds:
        seeds[pid] = random.randint(1, 10 ** 9)
    return seeds[pid]


def reshuffle(settings, pid):
    seeds = dict(settings.presets.get("seeds") or {})
    seeds[pid] = random.randint(1, 10 ** 9)
    settings.presets["seeds"] = seeds
    return seeds[pid]


_TRACK = re.compile(r"[VA][1-9][0-9]?")


def track_order(tracks):
    """V1, V2 ..., then A1, A2 ... - each once."""
    return sorted(set(tracks), key=lambda t: (t[0] != "V", int(t[1:])))


CUT_EDGES = ("between", "starts", "ends", "both")


def track_edges(spans, edges="between"):
    """Where on a track's clips [(start, end)] an insert goes: where one begins after another ("between"), every
    start, every end, or both."""
    spans = sorted(spans)
    starts, ends = {a for a, _b in spans}, {b for _a, b in spans}
    if edges == "starts":
        return starts
    if edges == "ends":
        return ends
    if edges == "both":
        return starts | ends
    return {a for a, _b in spans[1:]}


def cut_frames(by_track, tracks, edges="between"):
    """Every cut on the `tracks` named ("V1", "A2" ...): {track: [(start, end) of its clips]} -> the frames,
    sorted, each once. (A track handed over as plain frames is its cuts already.)"""
    out = set()
    for track in tracks or ["V1"]:
        spans = (by_track or {}).get(track, [])
        out |= set(spans) if spans and not isinstance(spans[0], (tuple, list)) else track_edges(spans, edges)
    return sorted(out)


def summary(preset):
    """One line on what the preset does."""
    parts = []
    if preset["where"] == "markers":
        only = [c.lower() for c in preset.get("marker_colours") or []]
        parts.append("at every " + (", ".join(only[:-1]) + " and " + only[-1] if len(only) > 1 else only[0])
                     + " marker" if only else "at every marker")
    elif preset["where"] == "cuts":
        tracks = preset.get("cut_tracks") or ["V1"]
        what = {"starts": "clip start", "ends": "clip end", "both": "clip start and end"}.get(
            preset.get("cut_edges"), "cut")
        parts.append(f"at every {what} on " + (", ".join(tracks[:-1]) + " and " + tracks[-1] if len(tracks) > 1
                                           else tracks[0]))
    if preset["where"] != "playhead":
        parts += [part for part in (
            {"centre": "pictures centred on it", "end": "pictures end on it",
             "loudest": "videos loudest on it"}.get(preset["align_pictures"]),
            {"centre": "sounds centred on it", "end": "sounds end on it",
             "loudest": "sounds loudest on it"}.get(preset["align"]),
            "moved " + shift_words(preset["shift"]) if preset["shift"] else None,
            "some moved by hand" if preset["clip_shifts"] else None,
            "one clip per marker" if preset["pair"] == "turns" else None,
            "in random order" if preset["order"] == "random" else None,
            {"once": "each clip once", "sounds_repeat": "pictures once, sounds repeat",
             "pictures_repeat": "pictures repeat, sounds once"}.get(preset["run_out"]),
            {"cut_first": "an overlap cuts the first", "cut_next": "an overlap cuts the next",
             "back_to_back": "overlaps wait their turn"}.get(preset["overlap"])) if part]
    spacing = preset["spacing"]
    if preset["where"] == "playhead":
        if spacing == "back_to_back":
            parts.append("one after another")
        elif spacing == "interval":
            listed = exact_gaps(preset)
            if listed:
                parts.append("gaps " + ", ".join(str(g) for g in listed[:6]) + (" ..." if len(listed) > 6 else ""))
            elif preset["gap"] == preset["gap_end"]:
                parts.append(f"{preset['gap']} frames apart")
            else:
                parts.append(f"{preset['gap']} → {preset['gap_end']} frames apart")
        else:
            parts.append("at the playhead")
        if spacing in REPEATS and preset.get("repeat") == "match":
            numbers = [f"{int(preset[k])} {what}" for k, what in (("pictures_count", "pictures"),
                                                                  ("sounds_count", "sounds")) if int(preset.get(k, 0))]
            parts.append(", ".join(numbers) if numbers else "repeated to match")
    can_end = preset["where"] == "playhead" and preset["spacing"] != "back_to_back"
    together = can_end and preset.get("ends") == "together"
    together_s = can_end and preset.get("ends_audio") == "together"
    if can_end and preset.get("ends_audio") == "first":
        parts.append("sounds end with the first one" + (f", {preset['length_audio']:g} s long" if preset["length_audio"] else ""))
    if can_end and preset.get("ends") == "audio":
        parts.append("pictures end with the sounds")
    if can_end and preset.get("ends_audio") == "pictures":
        parts.append("sounds end with the pictures")
    for on, seconds, what in ((together, preset["length"], "pictures"), (together_s, preset["length_audio"], "sounds")):
        if on:
            parts.append(f"{what} end together" + (f", {seconds:g} s after the last starts" if seconds else ""))
        elif seconds:
            parts.append(f"{what} {seconds:g} s")
    if preset["media"] == "video":
        parts.append("picture only")
    elif preset["media"] == "audio":
        parts.append("sound only")
    by, scale = preset.get("size_by", "fit"), preset["scale"]
    measured = by != "fit"
    if measured:  # "as wide as the frame", "50 % of the frame's width", "filling the frame at 80 %"
        parts.append({"width": "as wide as the frame", "height": "as tall as the frame", "fill": "filling the frame"}[by]
                     if scale == 100 else f"filling the frame at {scale:g} %" if by == "fill"
                     else f"{scale:g} % of the frame's {by}")
    if scale != 100 and not measured or preset["scale_vary"]:
        parts.append((f"{preset['scale']:g} % size" if not measured else "size")
                     + (f" ±{preset['scale_vary']:g}" if preset["scale_vary"] else ""))
    if preset["scatter"]:
        parts.append("scattered" + (", not touching" if preset.get("apart") else ""))
    elif preset["x"] or preset["y"]:
        parts.append("moved")
    if preset["rotation"] or preset["rotation_vary"]:
        parts.append("tilted")
    if preset["opacity"] < 100:
        parts.append(f"{preset['opacity']:g} % opacity")
    if preset["convert"] == "compound":
        parts.append("wrapped in a compound clip")
    elif preset["convert"] == "fusion":
        parts.append("wrapped in a Fusion clip")
    if preset["colour"]:
        parts.append(f"coloured {preset['colour']}")
    text = " \u00b7 ".join(parts)
    return text[:1].upper() + text[1:]


# what's changed on a preset, as the chips under its name in Insert as - settings that go together are one
CHANGE_GROUPS = [
    ("where",), ("marker_colours",), ("cut_tracks",), ("cut_edges",), ("pair",), ("order",), ("run_out",), ("align_pictures",), ("align",),
    ("shift", "clip_shifts"), ("overlap",),
    ("spacing", "gap", "gap_end", "gaps", "curve", "curve_strength", "vary"), ("repeat",), ("pictures_count",), ("sounds_count",),
    ("ends",), ("ends_audio",), ("length",), ("length_audio",), ("media",),
    ("size_by",), ("scale", "scale_vary"), ("x", "y"), ("scatter", "scatter_random"), ("rotation", "rotation_vary"),
    ("opacity",), ("inside", "margin"), ("apart",), ("convert",), ("colour",),
]
_CHANGE_WORDS = {"marker_colours": "every marker", "scatter_random": "randomness", "inside": "over the edge",
                 "margin": "margin", "curve": "the curve", "gaps": "exact gaps", "vary": "gaps vary",
                 "length": "length", "length_audio": "sound length", "spacing": "spacing", "x": "moved",
                 "clip_shifts": "moved one by one", "where": "where", "repeat": "repeated to match",
                 "apart": "not touching"}


def base_of(preset):
    """What a preset is set up from: a built-in one as it ships - one of yours, Normal."""
    pid = preset.get("id")
    built = next((b for b in BUILTINS if b["id"] == pid), None)
    return _clean(built if built is not None else FIELDS)


def changes(preset, base=None):
    """[(words, keys)]: each change from `base` (base_of) in a few words - "blue markers", "30 % size" -
    with the settings it's made of, to take it back by itself."""
    base = base or base_of(preset)
    preset = _clean(preset)
    plain_parts = set(summary(base).split(" \u00b7 "))
    out = []
    for keys in CHANGE_GROUPS:
        if all(preset[k] == base[k] for k in keys):
            continue
        if keys == ("inside", "margin"):  # (the summary doesn't say these)
            words = "may go over the edge" if not preset["inside"] else \
                (f"{-preset['margin']:g} % over the edge" if preset['margin'] < 0 else f"{preset['margin']:g} % margin")
            out.append((words, keys))
            continue
        if keys == ("repeat",) and (preset["pictures_count"] or preset["sounds_count"]):
            out.append(("repeated", keys))  # (the numbers say the rest)
            continue
        if keys == ("where",) and preset["where"] == "cuts":  # (which tracks is a chip of its own)
            out.append(("at every cut", keys))
            continue
        if keys == ("cut_tracks",):
            out.append(("cuts on " + ", ".join(preset["cut_tracks"]), keys))
            continue
        if keys == ("cut_edges",):
            out.append(({"starts": "every clip's start", "ends": "every clip's end",
                         "both": "every start and end"}.get(preset["cut_edges"], "where clips meet"), keys))
            continue
        if keys in (("pictures_count",), ("sounds_count",)):  # (plain, whatever else is set)
            out.append((f"{preset[keys[0]]} {'pictures' if keys[0] == 'pictures_count' else 'sounds'}", keys))
            continue
        alone = dict(base, **{k: preset[k] for k in keys})
        new = [part for part in summary(alone).split(" \u00b7 ") if part not in plain_parts]
        words = ", ".join(new).lower() if new else \
            next((_CHANGE_WORDS[k] for k in keys if k in _CHANGE_WORDS and preset[k] != base[k]), keys[0].replace("_", " "))
        out.append((words[:1].lower() + words[1:], keys))
    return out


def shift_words(seconds, fps=None):
    """"0.25 s later" / "6 frames earlier" - how far a clip is moved off its marker."""
    if not seconds:
        return "right on it"
    way = "later" if seconds > 0 else "earlier"
    if fps and abs(seconds) * fps < 30:
        frames = int(round(abs(seconds) * fps))
        return f"{frames} frame{'s' if frames != 1 else ''} {way}"
    return f"{abs(seconds):g} s {way}"


def anchor(align, length, loudest=None):
    """How far into a clip `length` frames long the point that goes on the marker is: its start, middle,
    end - or its loudest moment (`loudest`, frames from where it starts; a clip with no sound to go by:
    its start)."""
    if align == "centre":
        return length // 2
    if align == "end":
        return length
    if align == "loudest" and loudest is not None:
        return max(0, min(length, int(loudest)))
    return 0


def marker_plan(preset, events, clips, fps, rng=None):
    """Where each clip goes at markers or cuts - worked out before anything is put down, so overlaps can
    be settled first.

    events: the marker (or cut) frames. clips: [{"length": frames, "loudest": frames or None,
    "sound": True for a sound, "name": for its own shift}] - the staged clips, each with its length on
    the timeline. More markers than clips: every clip once, then `run_out` says which start over.
    Returns [{"event", "clip" (index into clips), "start", "length", "head"}], in timeline order:
    head = frames cut off the clip's own beginning (Cut the next). A clip with nothing left is left out.

    Overlaps are settled among clips of a kind (pictures with pictures, sounds with sounds): a sound
    under a picture is no overlap."""
    rng = rng or random.Random()
    shift = int(round(float(preset.get("shift", 0.0)) * fps))
    own = preset.get("clip_shifts") or {}
    # who takes turns: all the clips together - or, pictures and sounds both on every marker, each kind
    # among itself
    pictures = [i for i, clip in enumerate(clips) if not clip.get("sound")]
    sounds = [i for i, clip in enumerate(clips) if clip.get("sound")]
    groups = [pictures, sounds] if preset.get("pair", "both") == "both" and pictures and sounds \
        else [list(range(len(clips)))]
    run_out = preset.get("run_out", "repeat")

    def again(i):  # once every clip has had its marker: does this one start over?
        sound = bool(clips[i].get("sound"))
        return run_out == "repeat" or (run_out == "sounds_repeat" and sound) or (run_out == "pictures_repeat" and not sound)

    random_order = preset.get("order") == "random"
    first_round = [rng.sample(members, len(members)) if random_order else list(members) for members in groups]
    out, last = [], [None] * len(groups)
    for n, frame in enumerate(sorted(events)):
        for g, members in enumerate(groups):
            if not members:
                continue
            if n < len(members):  # every clip once first (at random: in a shuffled order)
                which = first_round[g][n]
            else:
                left = [i for i in members if again(i)]
                if not left:
                    continue
                if random_order and len(left) > 1:
                    which = rng.choice([i for i in left if i != last[g]])  # (never the same one twice running)
                else:
                    which = left[(n - len(members)) % len(left)]
            last[g] = which
            clip = clips[which]
            length = max(1, int(clip["length"]))
            align = preset.get("align", "start") if clip.get("sound") else preset.get("align_pictures", "start")
            start = frame - anchor(align, length, clip.get("loudest")) + shift \
                + int(round(float(own.get(clip.get("name", ""), 0.0)) * fps))
            out.append({"event": frame, "clip": which, "start": start, "length": length, "head": 0})
    rule = preset.get("overlap", "stack")
    if rule == "stack":
        return out
    kept = []
    for sound in (False, True):
        group = sorted((e for e in out if bool(clips[e["clip"]].get("sound")) == sound), key=lambda e: e["start"])
        if rule == "cut_first":
            for e, after in zip(group, group[1:] + [None]):
                if after is not None and after["start"] < e["start"] + e["length"]:
                    e["length"] = after["start"] - e["start"]
                if e["length"] > 0:
                    kept.append(e)
        else:
            end = None
            for e in group:
                if end is not None and e["start"] < end:
                    if rule == "back_to_back":
                        e["start"] = end
                    else:  # cut_next: what's under the one before goes
                        cut = end - e["start"]
                        e["start"], e["head"], e["length"] = end, e["head"] + cut, e["length"] - cut
                if e["length"] > 0:
                    kept.append(e)
                    end = e["start"] + e["length"]
    return sorted(kept, key=lambda e: (e["start"], e["event"]))


def clip_length(preset, kind, frames, fps, still_frames):
    """How many timeline frames a clip of `kind`, `frames` long, lands with this preset's Length / Sound
    length (a picture: as long as it's asked to be; with no Length, what a picture lasts)."""
    if kind == "audio":
        asked = int(round(preset.get("length_audio", 0.0) * fps)) if preset.get("length_audio") else 0
        return min(asked, frames) if asked else frames
    asked = int(round(preset["length"] * fps)) if preset["length"] else 0
    if kind == "still":
        return asked or still_frames
    return min(asked, frames) if asked else frames


REPEATS = ("back_to_back", "interval")  # where Repeat to match does something


def counts(preset, n_pictures, n_sounds):
    """Repeat: (pictures, sounds) - how many of each go in, in all, both starting over until there are that many.
    Match (0) is as many as the other kind's number - and with both on Match, as many as the kind there's more of
    (1 picture and 10 sounds: ten of each). None with Each once, or anywhere but at the playhead one after another."""
    if preset.get("where") != "playhead" or preset.get("spacing") not in REPEATS or preset.get("repeat") != "match":
        return None
    want_p = max(0, min(COUNT_MAX, int(preset.get("pictures_count", 0) or 0)))
    want_s = max(0, min(COUNT_MAX, int(preset.get("sounds_count", 0) or 0)))
    if not n_pictures:
        return 0, (want_s or n_sounds)
    if not n_sounds:
        return (want_p or n_pictures), 0
    both = max(n_pictures, n_sounds)
    return (want_p or want_s or both), (want_s or want_p or both)


def repeated(preset, sounds):
    """Pictures and sounds that go in together: Repeat (1 picture and 10 sounds, the picture goes in with every
    sound - 3 and 10: 1 2 3 1 2 3 ...; 1 picture and 2 sounds, 20 of each: twenty pairs). Where one kind has more
    than the other, the rest go in alone. sounds: for each staged clip, True for a sound. Returns
    [(picture, sound)] - indices, None for one that's alone - in the order they go in; None when nothing goes
    in pairs (not at the playhead one after another, Each once, only one kind, or nothing to repeat)."""
    pictures = [i for i, sound in enumerate(sounds) if not sound]
    heard = [i for i, sound in enumerate(sounds) if sound]
    wanted = counts(preset, len(pictures), len(heard))
    if wanted is None or not pictures or not heard:
        return None
    many_p, many_s = wanted
    if many_p == len(pictures) == many_s == len(heard):
        return None  # (as many of each, and that's what's staged: nothing to repeat)
    return [(pictures[k % len(pictures)] if k < many_p else None, heard[k % len(heard)] if k < many_s else None)
            for k in range(max(many_p, many_s))]


def up_to(preset, clips, sounds):
    """Repeat with only one kind staged: that kind again, one after another, until there are as many as asked
    (fewer than staged: the first ones). Returns the clips to put in (the same list when nothing repeats)."""
    if not clips or (True in sounds and False in sounds):
        return list(clips)
    wanted = counts(preset, sounds.count(False), sounds.count(True))
    if wanted is None:
        return list(clips)
    many = wanted[1] if sounds[0] else wanted[0]
    return [clips[k % len(clips)] for k in range(many)]


def pairs_lead(pairs, sounds):
    """Who sets a pair's length: the kind there's more of in all; as many of each, the kind more of was staged
    (3 pictures and a sound, matched: each as long as its picture); and that the same too, the sound (1 picture and
    1 sound, 5 of each: each as long as its sound). sounds: the staged clips, True for a sound. True: the sound."""
    heard, seen = sum(s is not None for _p, s in pairs), sum(p is not None for p, _s in pairs)
    if heard != seen:
        return heard > seen
    return sum(sounds) >= len(sounds) - sum(sounds)


def pair_lengths(lead, partner, partner_still):
    """Repeat to match, back to back: each pair lasts as long as its clip of the kind there's more of (`lead`
    frames); the other one fills it - a picture exactly, a video or sound as far as it goes (`partner`)."""
    return lead if partner_still else min(partner, lead)


SHOWN_EVENTS = 400  # Insert as draws your markers or cuts as far apart as they are - up to this many


def timeline_plan(preset, clips, fps=30.0, still_frames=150, seed=1, loudest=None, events=None):
    """What an insert with `preset` puts on the timeline, worked out the way
    the picker does it - for the preview in Insert as.

    clips: [(kind, frames, label)] - kind "video", "still" or "audio";
    events: the timeline's marker (or cut) frames, to draw those - else three as an example;
    frames: the clip's own length (stills: Resolve's still length - what one gets with no Length set).
    Returns {"items": [{kind, label, start, end, own_end, track, early, target}],
             "ends": {"pictures": frame the pictures end together at, "sounds": ...} (what ends together),
             "end": frame they end together at (or None), "group": (start, end) of the stills'
             compound clip (or None), "events": marker / cut frames, "need_still": frames a
             still would need to reach the end (0 if fine)}."""
    rng = random.Random(seed)
    real, items, events = list(events or []), [], []
    if preset["where"] == "playhead":  # How many: they start over until there are that many (pairs: `repeated`)
        clips = up_to(preset, clips, [c[0] == "audio" for c in clips])
    where, spacing = preset["where"], preset["spacing"] if len(clips) > 1 else "together"
    # pictures (videos, stills) and sounds each end by themselves or together - a setting for each
    can_end = where == "playhead" and spacing != "back_to_back"
    n_pictures, n_sounds = sum(c[0] != "audio" for c in clips), sum(c[0] == "audio" for c in clips)
    with_sounds = can_end and preset.get("ends") == "audio" and n_pictures > 0 and n_sounds > 0
    # (with no sound in the insert, "with the sounds" has nothing to follow: the pictures end together)
    together = with_sounds or (can_end and preset.get("ends") in ("together", "audio") and n_pictures > 1)
    sounds_first = can_end and preset.get("ends_audio") == "first" and n_sounds > 1
    with_pictures = can_end and preset.get("ends_audio") == "pictures" and n_pictures > 0 and n_sounds > 0
    together_s = sounds_first or with_pictures or (can_end and preset.get("ends_audio") == "together" and n_sounds > 1)
    length_frames = int(round(preset["length"] * fps)) if preset["length"] else 0
    sound_frames = int(round(preset.get("length_audio", 0.0) * fps)) if preset.get("length_audio") else 0

    def own(kind, frames):
        if (together_s if kind == "audio" else together):
            return frames if kind != "still" else still_frames
        return clip_length(preset, kind, frames, fps, still_frames)

    if where in ("markers", "cuts"):
        if real:  # yours, as far apart as they are on the timeline - the first one a second in
            first = sorted(real)[0] - int(fps)
            events = [int(e) - first for e in sorted(real)[:SHOWN_EVENTS]]
        else:  # an example
            events = [int(fps * t) for t in (1.0, 3.0, 5.0)]
        staged = [{"length": own(kind, frames), "sound": kind == "audio", "name": _label,
                   "loudest": (loudest[n] if loudest and n < len(loudest) else None)}
                  for n, (kind, frames, _label) in enumerate(clips)]
        for e in marker_plan(preset, events, staged, fps, random.Random(seed)):
            kind, frames, label = clips[e["clip"]]
            items.append({"kind": kind, "label": label, "start": e["start"], "end": e["start"] + e["length"],
                          "head": e["head"], "whole": staged[e["clip"]]["length"], "frames": frames})
    else:
        pairs = repeated(dict(preset, spacing=spacing), [c[0] == "audio" for c in clips])
        if pairs and spacing == "interval":  # (each kind follows the curve by itself: picture n with sound n)
            clips = [clips[i] for pair in pairs for i in pair if i is not None]
        if pairs and spacing == "back_to_back":
            by_sound = pairs_lead(pairs, [c[0] == "audio" for c in clips])
            cursor = 0
            for p_index, s_index in pairs:
                first, second = (s_index, p_index) if by_sound else (p_index, s_index)
                if first is None:  # (the other kind has run out: this one by itself)
                    first, second = second, None
                lead = clips[first]
                length = own(*lead[:2])
                partner = clips[second] if second is not None else None
                for (kind, frames, label), leads in ((lead, True),) + (((partner, False),) if partner else ()):
                    lasts = length if leads else pair_lengths(length, own(kind, frames), kind == "still")
                    items.append({"kind": kind, "label": label, "start": cursor, "end": cursor + lasts,
                                  "frames": frames})
                cursor += length
        elif spacing == "interval":
            pictures = [c for c in clips if c[0] != "audio"]
            sounds = [c for c in clips if c[0] == "audio"]
            at = {"p": offsets(preset, len(pictures), rng), "s": offsets(preset, len(sounds), rng)}
            count = {"p": 0, "s": 0}
            for kind, frames, label in clips:
                k = "s" if kind == "audio" else "p"
                start = at[k][count[k]]
                count[k] += 1
                items.append({"kind": kind, "label": label, "start": start, "end": start + own(kind, frames)})
        else:
            cursor = 0
            for kind, frames, label in clips:
                start = cursor
                end = start + own(kind, frames)
                items.append({"kind": kind, "label": label, "start": start, "end": end})
                if spacing == "back_to_back":
                    cursor = end
    for n, it in enumerate(items):
        it["own_end"] = it["end"]
        it["early"] = False
        it["over"] = False
        it.setdefault("frames", clips[n % len(clips)][1])  # (markers / cuts say which clip it is)
    ends = {}  # "pictures" / "sounds" -> the frame they end together at
    # (the kind the other ends with goes first; each with the other: both where the last one ends)
    groups = [("sounds", together_s, sound_frames), ("pictures", together, length_frames)]
    if with_pictures and not with_sounds:
        groups.reverse()
    both_follow = with_pictures and with_sounds
    last_of_all = max((i["end"] for i in items), default=0)
    for what, on, asked in groups:
        members = [i for i in items if (i["kind"] == "audio") == (what == "sounds")]
        if not on or not members:
            continue
        if both_follow:
            end = last_of_all
        elif what == "pictures" and with_sounds:  # where the sound that ends last ends
            end = max(i["end"] for i in items if i["kind"] == "audio")
        elif what == "sounds" and with_pictures:  # where the picture that ends last ends
            end = max(i["end"] for i in items if i["kind"] != "audio")
        else:
            # the one the others follow: the last to start - or, sounds ending with the first, the first
            lead = min(members, key=lambda i: (i["start"], -i["end"])) if what == "sounds" and sounds_first \
                else max(members, key=lambda i: (i["start"], i["end"]))
            end = lead["start"] + (min(asked, lead["frames"]) if lead["kind"] != "still" else asked) if asked else lead["end"]
        ends[what] = end
        for it in members:
            it["target"] = end
            if it["kind"] == "still":  # a still takes any length: cut or stretched to the end point
                it["end"] = max(it["start"] + 1, end)
            else:
                it["end"] = it["start"] + max(1, min(end - it["start"], it["frames"]))
                it["early"] = it["end"] < end
    group = None
    if ends and preset["convert"] != "none":
        group = (min(i["start"] for i in items), max(i["end"] for i in items))
    # tracks, the way Resolve stacks them: above anything it overlaps
    for kind_group in (("video", "still"), ("audio",)):
        placed = []
        for it in items:
            if it["kind"] not in kind_group:
                continue
            track = 1 + max((p["track"] for p in placed if p["start"] < it["own_end"] and it["start"] < p["own_end"]),
                            default=0)
            it["track"] = track
            placed.append(it)
    return {"items": items, "ends": ends, "end": max(ends.values()) if ends else None, "group": group,
            "events": events, "need_still": 0}
