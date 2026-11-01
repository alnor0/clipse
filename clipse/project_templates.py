"""Project templates: the setup you start every video with, in one step.

A template remembers
  - where loose clips go and which colours clips get ("organise" - Organise
    project, organise.py; made from its bins when it doesn't say),
  - the bin structure of the Media Pool (01_footage / a-roll, 02_audio /
    music ...),
  - the project settings (resolution, frame rate, colour management,
    audio, ...),
  - the tracks of the current timeline: how many, and their names
    (V1 A-roll, A4 Music ...).

`tpl:` in the picker lists them: Enter applies one to the project that's
open (it only ever ADDS - missing bins and tracks are created, nothing is
deleted or moved). Type a name after `tpl:` and the first row saves the
open project as a template with that name.

Resolve's own preferences (Preferences window) aren't part of a project
and scripts can't change them, so they're not in templates. Saved
templates live in the settings folder's templates/ (paths.config) as small .json files.
"""
import json
import os
import re
import time
from . import paths

TEMPLATES_DIR = paths.config("templates")

# Bins are named numbered, lowercase, with underscores - 03_graphics, screen_recordings (2026-10-17)
# settings that belong to this computer or this one project, never to a template
_SKIP = ("path", "folder", "directory", "dir", "cache", "name", "date", "user", "collaborat", "database")


def _youtube_bins():
    return [
        ["01_footage", ["a-roll", "b-roll", "screen_recordings"]],
        ["02_audio", ["music", "sfx", "voiceover"]],
        ["03_graphics", ["stills", "titles", "logos", "fusion"]],
        ["04_timelines", []],
    ]


BUILTIN = {
    "YouTube video": {
        "about": "4K \u00b7 A/B-roll, music & SFX",
        "bins": _youtube_bins(),
        "settings": {"timelineResolutionWidth": "3840", "timelineResolutionHeight": "2160"},
        "tracks": {"video": ["A-roll", "B-roll", "Graphics", "Titles"],
                   "audio": ["Voice", "SFX", "SFX 2", "Music"]},
    },
    "Tutorial / screen recording": {
        "about": "4K \u00b7 screen, camera, voiceover",
        "bins": [
            ["01_screen_recordings", []],
            ["02_camera", []],
            ["03_audio", ["voiceover", "music", "sfx"]],
            ["04_graphics", ["keycaps", "callouts", "titles", "stills"]],
            ["05_timelines", []],
        ],
        "settings": {"timelineResolutionWidth": "3840", "timelineResolutionHeight": "2160"},
        "tracks": {"video": ["Screen", "Camera", "Callouts", "Titles"],
                   "audio": ["Voiceover", "Screen audio", "SFX", "Music"]},
    },
    "Shorts / vertical": {
        "about": "1080 \u00d7 1920 vertical",
        "bins": [["01_footage", []], ["02_audio", ["music", "sfx", "voice"]], ["03_graphics", []]],
        "settings": {"timelineResolutionWidth": "1080", "timelineResolutionHeight": "1920"},
        "tracks": {"video": ["Footage", "B-roll", "Captions"], "audio": ["Voice", "SFX", "Music"]},
    },
    "Minimal": {
        "about": "four bins only",
        "bins": [["01_footage", []], ["02_audio", []], ["03_graphics", []], ["04_timelines", []]],
        "settings": {},
        "tracks": {},
    },
}


def _file(name):
    safe = re.sub(r"[^\w\- ]+", "_", name).strip() or "template"
    return os.path.join(TEMPLATES_DIR, f"{safe}.json")


def saved_templates():
    """{name: template} of the templates you saved."""
    out = {}
    try:
        files = sorted(os.listdir(TEMPLATES_DIR))
    except OSError:
        return out
    for f in files:
        if not f.endswith(".json"):
            continue
        try:
            with open(os.path.join(TEMPLATES_DIR, f), encoding="utf-8") as fh:
                data = json.load(fh)
            out[data.get("name") or f[:-5]] = data
        except (OSError, ValueError):
            continue
    return out


def all_templates():
    """[(name, template, built_in)] - yours first, then the built-in ones."""
    mine = saved_templates()
    return [(n, t, False) for n, t in mine.items()] + [(n, t, True) for n, t in BUILTIN.items() if n not in mine]


def all_templates_by_name():
    return {name: template for name, template, _built_in in all_templates()}


def describe(template):
    if template.get("about"):
        return template["about"]
    s = template.get("settings") or {}
    parts = []
    if s.get("timelineResolutionWidth"):
        parts.append(f"{s['timelineResolutionWidth']} x {s.get('timelineResolutionHeight', '?')}")
    if s.get("timelineFrameRate"):
        parts.append(f"{s['timelineFrameRate']} fps")
    count = _count_bins(template.get("bins") or [])
    if count:
        parts.append(f"{count} bins")
    tracks = template.get("tracks") or {}
    n = sum(len(v) for v in tracks.values())
    if n:
        parts.append(f"{n} tracks")
    return ", ".join(parts) or "empty"


def _entries(tree):
    """[(name, sub-tree)] - a bin is "Name" or ["Name", [sub-bins]]."""
    return [(e, []) if isinstance(e, str) else (e[0], e[1] if len(e) > 1 else []) for e in tree or []]


def _count_bins(tree):
    return sum(1 + _count_bins(sub) for _name, sub in _entries(tree))


def delete(name):
    try:
        os.remove(_file(name))
        return True
    except OSError:
        return False


# -- saving --
def _bin_tree(folder, depth=0):
    if depth > 6:
        return []
    return [[sub.GetName(), _bin_tree(sub, depth + 1)] for sub in (folder.GetSubFolderList() or [])]


def save_current(resolve, name):
    """Saves the open project's bins, settings and timeline tracks as a template."""
    name = name.strip()
    if not name:
        return "Type a name for the template after tpl:"
    project = resolve.GetProjectManager().GetCurrentProject()
    if project is None:
        return "No project open."
    bins = _bin_tree(project.GetMediaPool().GetRootFolder())
    settings = {}
    everything = {}
    for args in ((), ("",)):  # all settings at once (the call differs between Resolve versions)
        try:
            everything = project.GetSetting(*args) or {}
        except Exception:
            continue
        if isinstance(everything, dict) and everything:
            break
    if isinstance(everything, dict):
        for key, value in everything.items():
            if not any(word in key.lower() for word in _SKIP):
                settings[key] = str(value)
    tracks = {}
    timeline = project.GetCurrentTimeline()
    if timeline is not None:
        for kind in ("video", "audio", "subtitle"):
            try:
                count = timeline.GetTrackCount(kind)
                tracks[kind] = [timeline.GetTrackName(kind, i) or "" for i in range(1, count + 1)]
            except Exception:
                continue
    data = {"name": name, "saved": int(time.time()), "from_project": project.GetName(),
            "bins": bins, "settings": settings, "tracks": tracks}
    existed = os.path.exists(_file(name))
    kept = (saved_templates().get(name) or {}).get("organise") if existed else None
    if kept:  # (updated from a project: where clips go and their colours stay as they were - organise.py)
        data["organise"] = kept
    paths.write_json(_file(name), data, indent=1)
    return (f"{'Updated' if existed else 'Saved'} the template \"{name}\": {_count_bins(bins)} bins, "
            f"{len(settings)} settings, {sum(len(v) for v in tracks.values())} tracks.")


# -- applying --
def _add_bins(media_pool, parent, tree, counter):
    existing = {f.GetName(): f for f in (parent.GetSubFolderList() or [])}
    for name, sub in _entries(tree):
        folder = existing.get(name)
        if folder is None:
            folder = media_pool.AddSubFolder(parent, name)
            if folder is None:
                continue
            counter[0] += 1
        _add_bins(media_pool, folder, sub, counter)


def apply(resolve, template, name=""):
    """Applies a template to the open project - only adds, never removes.
    Returns a message saying what changed (and what Resolve refused)."""
    project = resolve.GetProjectManager().GetCurrentProject()
    if project is None:
        return "No project open."
    media_pool = project.GetMediaPool()
    current = media_pool.GetCurrentFolder()
    added = [0]
    _add_bins(media_pool, media_pool.GetRootFolder(), template.get("bins") or [], added)
    if current is not None:
        media_pool.SetCurrentFolder(current)

    changed, refused = 0, []
    for key, value in (template.get("settings") or {}).items():
        try:
            if str(project.GetSetting(key)) == str(value):
                continue
            if project.SetSetting(key, str(value)):
                changed += 1
            else:
                refused.append(key)
        except Exception:
            refused.append(key)

    named = 0
    tracks = template.get("tracks") or {}
    timeline = project.GetCurrentTimeline()
    if timeline is None and any(tracks.values()):
        timeline = media_pool.CreateEmptyTimeline("Timeline 1")
    if timeline is not None:
        for kind, names in tracks.items():
            try:
                while timeline.GetTrackCount(kind) < len(names):
                    if not (timeline.AddTrack(kind, "stereo") if kind == "audio" else timeline.AddTrack(kind)):
                        break
                for i, track_name in enumerate(names, start=1):
                    if track_name and i <= timeline.GetTrackCount(kind) and timeline.GetTrackName(kind, i) != track_name:
                        if timeline.SetTrackName(kind, i, track_name):
                            named += 1
            except Exception:
                continue

    parts = [f"{added[0]} bins added" if added[0] else "", f"{changed} settings changed" if changed else "",
             f"{named} tracks named" if named else ""]
    message = f"Applied \"{name}\": " + (", ".join(p for p in parts if p) or "everything was already in place") + "."
    if refused:
        hint = " (the frame rate can't change once a timeline has clips)" if any("FrameRate" in k for k in refused) else ""
        message += f" Resolve kept its own value for {len(refused)} setting{'s' if len(refused) != 1 else ''}{hint}."
    return message
