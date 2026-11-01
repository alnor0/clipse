"""Settings and presets as a file: to move to another computer (Mac <->
Linux <-> Windows), keep a backup, or share your Insert as presets.

Two kinds of file, both plain JSON:
  settings  your setup (Settings > About > Your setup): everything in Settings - except what belongs to one computer
            (where windows sit, folders, your own scripts), which the computer it's loaded on keeps as it has it -
            and, since 2026-10-19 ("is one .json really the only thing worth saving?"), your favourites, your
            project templates and what it has learned (what you pick for what you type, what you insert most).
            Loaded, those are added to what's there; nothing of yours goes. Not in it: history (it's of this
            computer's projects), caches, logs, the key (it's for this computer).
  presets   your own Insert as presets and your changes to the built-in
            ones. Importing adds them; nothing you have is removed.
"""
import copy
import json
import sys

from . import __version__

MARK = "clipse"
# namespace -> keys that are about this computer, not about how you like the app
MACHINE_KEYS = {
    "display": ("window_width", "window_height", "preview_geometry", "picker_pos"),
    "general": ("tour_done", "app_set_up"),
}
MACHINE_NAMESPACES = ("folders", "files")  # paths on this computer


class NotOurs(Exception):
    """The file isn't one of ours (or not the kind that was asked for)."""


def _write(path, kind, body):
    data = {"app": MARK, "kind": kind, "version": __version__, "system": sys.platform, **body}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def _read(path, kind):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as e:
        raise NotOurs(f"Couldn't read the file ({e})")
    if not isinstance(data, dict) or data.get("app") != MARK:
        raise NotOurs("This isn't a Clipse file.")
    if data.get("kind") != kind:
        other = "presets" if data.get("kind") == "presets" else "settings"
        raise NotOurs(f"This file holds {other} - use Import {other} for it.")
    return data


def kind_of(path):
    """"settings" or "presets" - what a Clipse file holds (NotOurs when it isn't one)."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as e:
        raise NotOurs(f"Couldn't read the file ({e})")
    if not isinstance(data, dict) or data.get("app") != MARK or data.get("kind") not in ("settings", "presets"):
        raise NotOurs("This isn't a Clipse file.")
    return data["kind"]


def export_settings(settings, path):
    body = copy.deepcopy(settings.as_dict())
    for namespace, keys in MACHINE_KEYS.items():
        for key in keys:
            body.get(namespace, {}).pop(key, None)
    for namespace in MACHINE_NAMESPACES:
        body.pop(namespace, None)
    from . import picks, project_templates, resolve_client as rc
    _write(path, "settings", {"settings": body, "favourites": sorted(rc.load_favorites()),
                              "templates": list(project_templates.saved_templates().values()),
                              "picks": _json_file(picks.FILE), "inserted": rc.load_insert_frequency()})


def _json_file(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _add_yours(data):
    """A setup file's favourites, templates and what it learned, added to what's here (nothing here goes). Returns
    what came in, for the line saying so."""
    import os
    from . import picks, project_templates, resolve_client as rc
    came = []
    favourites = [f for f in data.get("favourites") or [] if isinstance(f, str)]
    if favourites:
        mine = rc.load_favorites()
        new = set(favourites) - mine
        if new:
            rc.save_favorites(mine | new)
            came.append(f"{len(new)} favourite{'s' if len(new) != 1 else ''}")
    templates = [t for t in data.get("templates") or [] if isinstance(t, dict) and t.get("name")]
    have = set(project_templates.saved_templates())
    added = 0
    for template in templates:
        if template["name"] in have:
            continue  # (yours by that name stays)
        try:
            os.makedirs(project_templates.TEMPLATES_DIR, exist_ok=True)
            with open(project_templates._file(template["name"]), "w", encoding="utf-8") as f:
                json.dump(template, f, indent=1)
            added += 1
        except OSError:
            pass
    if added:
        came.append(f"{added} project template{'s' if added != 1 else ''}")
    learned = False
    incoming = data.get("picks")
    if isinstance(incoming, dict) and incoming:
        mine = _json_file(picks.FILE)
        for query, keys in incoming.items():
            if not isinstance(keys, dict):
                continue
            here = mine.setdefault(query, {})
            for key, value in keys.items():
                if isinstance(value, list) and len(value) == 2:
                    old = here.get(key)
                    here[key] = [max(value[0], old[0]), max(value[1], old[1])] if old else value
        _write_json(picks.FILE, mine)
        picks._data = None  # (read again when next asked)
        learned = True
    inserted = data.get("inserted")
    if isinstance(inserted, dict) and inserted:
        mine = rc.load_insert_frequency()
        for name, count in inserted.items():
            if isinstance(count, int):
                mine[name] = max(count, mine.get(name, 0))
        _write_json(rc.INSERT_FREQUENCY_FILE, mine)
        learned = True
    if learned:
        came.append("what it learned")
    return came


def _write_json(path, value):
    import os
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(value, f)
    except OSError:
        pass


def import_settings(settings, path):
    """Everything in Settings becomes what the file says; what belongs to
    this computer stays. Returns a line saying what happened."""
    data = _read(path, "settings")
    incoming = data.get("settings")
    if not isinstance(incoming, dict):
        raise NotOurs("There are no settings in this file.")
    mine = copy.deepcopy(settings.as_dict())
    merged = {name: value for name, value in incoming.items() if isinstance(value, dict)}
    for namespace in MACHINE_NAMESPACES:
        merged[namespace] = mine.get(namespace, {})
    for namespace, keys in MACHINE_KEYS.items():
        for key in keys:
            if key in mine.get(namespace, {}):
                merged.setdefault(namespace, {})[key] = mine[namespace][key]
    # back to the defaults, then the file on top - in place, since the app
    # holds on to these dictionaries
    for name, default in vars(type(settings)()).items():
        current = getattr(settings, name, None)
        if isinstance(current, dict) and isinstance(default, dict):
            current.clear()
            current.update(default)
        else:
            setattr(settings, name, default)
    settings.apply(merged)
    settings.save()
    came = _add_yours(data)
    where = {"darwin": "a Mac", "win32": "Windows"}.get(str(data.get("system")), "Linux")
    also = f", with {', '.join(came[:-1]) + (' and ' if len(came) > 1 else '') + came[-1]}" if came else ""
    return f"The setup from {where} (version {data.get('version', '?')}) is in use now{also}."


def export_presets(settings, path):
    """Returns how many presets went into the file."""
    own = [copy.deepcopy(p) for p in settings.presets.get("user", [])]
    edits = copy.deepcopy(settings.presets.get("edits", {}))
    _write(path, "presets", {"presets": own, "edits": edits})
    return len(own) + len(edits)


def import_presets(settings, path):
    """Adds the file's presets to yours: one with a name you already have
    comes in as "Name 2". Changes to built-in presets are taken over only
    where you haven't changed that preset yourself. Returns a line."""
    from . import presets
    data = _read(path, "presets")
    added = changed = 0
    taken = {p["name"] for p in presets.all_presets(settings)}
    for preset in data.get("presets") or []:
        if not isinstance(preset, dict) or not str(preset.get("name", "")).strip():
            continue
        clean = presets._clean(preset)
        base, n = clean["name"], 2
        while clean["name"] in taken:
            clean["name"], n = f"{base} {n}", n + 1
        taken.add(clean["name"])
        clean["id"] = presets._new_id() + f"{added:02x}"
        settings.presets["user"].append(clean)
        added += 1
    edits = data.get("edits") if isinstance(data.get("edits"), dict) else {}
    for pid, diff in edits.items():
        if pid in presets.BUILTIN_IDS and isinstance(diff, dict) and not settings.presets["edits"].get(pid):
            base = next(b for b in presets.BUILTINS if b["id"] == pid)
            presets.save(settings, {**base, **diff, "id": pid})
            changed += 1
    settings.save()
    if not added and not changed:
        return "There was nothing new in that file."
    parts = ([f"{added} preset{'s' if added != 1 else ''} added"] if added else []) + \
            ([f"{changed} built-in preset{'s' if changed != 1 else ''} changed"] if changed else [])
    return " and ".join(parts) + " - they're in Insert as."
