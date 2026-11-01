"""Organise project (Actions > Project, Clipse 22 - Organise Project): the project's template's bins are added, the
clips lying loose in the Media Pool go into them, and clips get a colour by what they are - in the Media Pool and on
every timeline. The second half of a project template: the template makes the bins, this fills and marks them
(2026-10-30, the owner: "a system in all my projects, where i color things depending on use").

Which template: the one whose bins the project has most of (yours before the built-in ones) - nothing to pick.
What a template says (its "organise", made from its bins when it has none - `rules`):
    places   {"kinds": {kind: bin}, "folders": {folder on disk: bin}}   where a loose clip goes - a folder can
             start with ~ and be a pattern ("~/library/generated/*_broll_*"); the most particular one wins
             "split": [folder]   those folders' files go in a bin named after the folder each is in, inside the
             rule's bin - sfx/_collections/whoosh/fast_whip.wav: 04_audio/sfx/whoosh (2026-10-30: "i normally have
             this structure. Can i keep that"); one straight in the rule's folder goes in its bin
    colours  {"kinds": {kind: colour}, "bins": {bin: colour}}           the colour a clip gets
Kinds: video, music, sfx (a sound: music or a sound effect as Clipse tells them apart everywhere -
resolve_client.is_music), still, fusion, compound, adjustment, generator, timeline. A bin is its path, "02_b-roll/screen".

What no rule claims stays in Master for you to put away (2026-10-30: "The stuff that doesnt have a ruel just
stays in master") - footage goes only by a folder rule. Only the unusual things get a colour - footage, sound, adjustment clips and compositions keep Resolve's own (the same day: "just the out of the
ordinary ones get special colors"). It only adds: a clip already in a bin stays there, nothing is un-coloured, and a
colour you gave a clip by hand (one the template doesn't use) is kept.

A program of its own (launch.command("organise")), like playhead.py: Resolve takes about a second for each colour
it changes on a clip (measured 2026-10-30, 21.1.1: 1000 ms a timeline clip, up to 4 s a Media Pool clip - reading
is under a millisecond), and its library holds Python's lock meanwhile - in the service the picker would stand still
for minutes. When it's done it tells the service what it did (SAY:, a toast)."""
import fnmatch
import os
import re
import sys
import time

RETRY_AFTER = (1, 2, 4, 8, 15)  # seconds: a clip Resolve copied instead of moving is tried again after each
KINDS = ("video", "music", "sfx", "still", "fusion", "compound", "adjustment", "generator", "timeline")
# a kind's own colour beats its bin's (a Fusion composition in b-roll is still yellow); a still's doesn't
STRONG = ("fusion", "compound", "adjustment")
# Media Pool clips Resolve says yes to a colour for, and never keeps it (their timeline clips do keep it)
UNCOLOURABLE = ("Generator", "Fusion Title", "Fusion Composition", "Fusion Generator")

# made from a template's bins when it says nothing: (kind, the bin names it goes in, best first)
_PLACE_WORDS = [("still", ("images", "stills", "photos", "pictures", "graphics")),
                ("sfx", ("sfx", "sound_effects", "effects", "sounds")), ("music", ("music", "songs")),
                ("fusion", ("fusion", "compositions")), ("compound", ("compound_clips", "compound", "fusion")),
                ("adjustment", ("fusion",)), ("timeline", ("timelines",))]
# (adjustment clips and Fusion compositions keep Resolve's own - 2026-10-30, the owner: "Just keep the original color
#  of adjustment clips ... and the same for fusion comps"; they were Tan and Yellow until then)
_KIND_COLOURS = {"still": "Navy", "compound": "Teal"}
_KIND_COLOURS_BEFORE = ("Yellow", "Tan")
_BIN_WORDS = [(("b-roll", "b_roll", "broll"), "Orange"), (("overlays",), "Pink")]
# Organise's own colours, whatever a template says now: a clip in one of them was coloured by Organise, not by hand
OWN_COLOURS = set(_KIND_COLOURS.values()) | set(_KIND_COLOURS_BEFORE) | {colour for _words, colour in _BIN_WORDS}


def kind_of(clip):
    """A Media Pool clip's kind (KINDS), or "" for one that has none here (subtitles, multicam ...)."""
    t = (clip.GetClipProperty("Type") or "").strip()
    if t == "Generator":
        return "adjustment" if "adjust" in (clip.GetName() or "").lower() else "generator"
    if t == "Audio":  # (2026-10-30: "The organise doesnt organize my sounds") - by the name, the folders it's in on
        from .resolve_client import _seconds, is_music  # disk and its keywords, then its length (long, nothing said:
        props = clip.GetClipProperty() or {}             # music) - a sound's Frames is empty, its Duration a timecode
        folders = " ".join(str(props.get("File Path") or "").replace("\\", "/").split("/")[:-1][-3:])
        return "sfx" if is_music(clip.GetName() or "", folders, props.get("Keyword") or "", _seconds(props)) is False \
            else "music"
    return {"Video": "video", "Video + Audio": "video", "Still": "still", "Compound": "compound",
            "Timeline": "timeline"}.get(t, "fusion" if t.startswith("Fusion") else "")


def bin_paths(tree, parent=""):
    """Every bin of a template's (or a project's) tree, as paths - "02_b-roll", "02_b-roll/screen"."""
    from .project_templates import _entries
    out = []
    for name, sub in _entries(tree):
        path = f"{parent}/{name}" if parent else name
        out += [path] + bin_paths(sub, path)
    return out


def rules(template):
    """The template's places and colours: its own "organise", over what its bins suggest."""
    paths = bin_paths(template.get("bins") or [])
    last = {p: re.sub(r"^\d+[_\- ]*", "", p.rsplit("/", 1)[-1].lower()) for p in paths}  # ("05_fusion": fusion)
    kinds = {}
    for kind, words in _PLACE_WORDS:
        found = next((p for word in words for p in paths if last[p] == word), None)
        if found:
            kinds[kind] = found
    bins = {p: colour for p in paths for words, colour in _BIN_WORDS if last[p] in words}
    own = template.get("organise") or {}
    places = {"kinds": {**kinds, **(own.get("places") or {}).get("kinds", {})},
              "folders": dict((own.get("places") or {}).get("folders", {})),
              "split": list((own.get("places") or {}).get("split", []))}
    colours = {"kinds": {**_KIND_COLOURS, **(own.get("colours") or {}).get("kinds", {})},
               "bins": {**bins, **(own.get("colours") or {}).get("bins", {})},
               "was": list((own.get("colours") or {}).get("was", []))}  # (colours it gave before, changed since)
    return {"places": places, "colours": colours}


def editable(template):
    """A template's "organise" written out in full (what `rules` makes of it), for Settings > Organise to change."""
    the = rules(template)
    return {"places": {"kinds": dict(the["places"]["kinds"]), "folders": dict(the["places"]["folders"]),
                       "split": list(the["places"]["split"])},
            "colours": {"kinds": dict(the["colours"]["kinds"]), "bins": dict(the["colours"]["bins"]),
                        "was": list(the["colours"]["was"])}}


def _moved(path, old, new):
    """`path` with the bin `old` (and what's inside it) now at `new` - None (new None) when it's gone."""
    if path == old or path.startswith(old + "/"):
        return None if new is None else new + path[len(old):]
    return path


def bin_moved(own, old, new=None):
    """Every rule of `own` (editable's) that names the bin `old` or one inside it follows it to `new`; with new None
    the bin was taken away: a kind going there stays in Master, its folders' rules and colours go."""
    kinds = own["places"]["kinds"]
    for kind, path in list(kinds.items()):
        kinds[kind] = _moved(path, old, new) or "" if path else path
    own["places"]["folders"] = {folder: _moved(path, old, new) for folder, path in own["places"]["folders"].items()
                                if _moved(path, old, new) is not None}
    own["places"]["split"] = [f for f in own["places"].get("split", []) if f in own["places"]["folders"]]
    own["colours"]["bins"] = {_moved(path, old, new): colour for path, colour in own["colours"]["bins"].items()
                              if _moved(path, old, new) is not None}
    return own


def _project_bins(root):
    """{bin path: folder} of the open project."""
    found = {}

    def walk(folder, path):
        for sub in folder.GetSubFolderList() or []:
            here = f"{path}/{sub.GetName()}" if path else sub.GetName()
            found[here] = sub
            walk(sub, here)
    walk(root, "")
    return found


def best_template(project):
    """(name, template) whose bins the project has most of - or (None, None) when it has none of any."""
    from . import project_templates as pt
    have = set(_project_bins(project.GetMediaPool().GetRootFolder()))
    best, most = (None, None), 0
    for name, template, _built_in in pt.all_templates():  # (yours first: a tie goes to yours)
        n = len(have & set(bin_paths(template.get("bins") or [])))
        if n > most:
            best, most = (name, template), n
    return best


def colour_for(kind, bin_path, colours):
    """The colour a clip of `kind` in `bin_path` gets, or "" - leave it as Resolve has it."""
    if kind in STRONG and colours["kinds"].get(kind):
        return colours["kinds"][kind]
    for path, colour in sorted(colours["bins"].items(), key=lambda kv: -len(kv[0])):  # (the closest bin first)
        if colour and (bin_path == path or bin_path.startswith(path + "/")):  # ("": none of its own)
            return colour
    return colours["kinds"].get(kind, "")


def place_for(kind, file_path, places):
    """The bin a loose clip goes in, or "" - it stays where it is."""
    file_path = (file_path or "").replace("\\", "/")
    for rule, path in sorted(places["folders"].items(), key=lambda kv: -len(kv[0])):  # (the deepest folder first)
        folder = os.path.expanduser(rule).replace("\\", "/").rstrip("/")
        if not folder:
            continue
        if any(c in folder for c in "*?["):  # a pattern - "~/library/generated/*_broll_*" (2026-10-30: his overlays
            if fnmatch.fnmatch(file_path, folder):  # and b-roll come out in one folder, told apart by name)
                return _split(path, file_path, folder, rule in places.get("split", ()))
        elif file_path.startswith(folder + "/"):
            return _split(path, file_path, folder, rule in places.get("split", ()))
    return places["kinds"].get(kind, "")


def _split(path, file_path, folder, split):
    """`path`, or with split the bin of the folder the file is in inside it - when that folder is below the rule's
    (a pattern's: below where its first wildcard starts)."""
    if not split or not path:
        return path
    base = folder[:min([folder.index(c) for c in "*?[" if c in folder] or [len(folder)])]
    base = base.rstrip("/") if base.endswith("/") or base == folder else os.path.dirname(base)
    parent = os.path.dirname(file_path)
    if parent.startswith(base + "/"):
        return f"{path}/{os.path.basename(parent)}"
    return path


def _bin(media_pool, root, bins, path):
    """The bin at `path` - made (with any bins on the way) if it isn't there."""
    if path in bins:
        return bins[path]
    parent_path, _sep, name = path.rpartition("/")
    parent = _bin(media_pool, root, bins, parent_path) if parent_path else root
    folder = media_pool.AddSubFolder(parent, name) if parent is not None else None
    if folder is not None:
        bins[path] = folder
    return folder


def _move(media_pool, source, clips, folder):
    """MoveClips, checked: (how many moved, the clips that stayed where they were).

    Twice (2026-10-30, 21.1.1, the owner's runs ~20 s after importing by hand) Resolve answered yes and made a new clip
    of each in the bin - a new id, the moment as its Date Added - and left them in Master: duplicates. The second time
    8 of 31 pictures, again even one at a time; minutes later the same 8 moved at once (with the bin open or not) -
    Resolve still busy with what was just imported, it seems. organise() tries those again a little later (RETRY_AFTER).
    So what's in the bin is looked at afterwards: a clip that wasn't there before and isn't one of ours is a copy
    Resolve just made of one of ours (the same file) - nothing uses it yet, and it goes; ours are tried one at a time
    (one at a time always moved), and one that's copied even then stays in Master."""
    ours = {c.GetMediaId(): c for c in clips}

    def once(batch):
        before = {c.GetMediaId() for c in folder.GetClipList() or []}
        if not media_pool.MoveClips(batch, folder):
            return [], batch
        here = folder.GetClipList() or []
        ids = {c.GetMediaId() for c in here}
        stayed = [c for c in batch if c.GetMediaId() not in ids]
        files = {c.GetClipProperty("File Path") for c in stayed}
        copies = [c for c in here if c.GetMediaId() not in before and c.GetMediaId() not in ours
                  and c.GetClipProperty("File Path") in files]
        if copies:
            print(f"[organise] Resolve copied {len(copies)} into {folder.GetName()} instead of moving them "
                  f"(open bin: {getattr(media_pool.GetCurrentFolder(), 'GetName', lambda: '?')()}, "
                  f"{len(media_pool.GetSelectedClips() or {})} selected) - the copies taken away", flush=True)
            media_pool.DeleteClips(copies)
        return [c for c in batch if c not in stayed], stayed

    moved, stayed = once(clips)
    stuck = []
    if stayed and len(clips) > 1:
        for clip in stayed:
            done, left = once([clip])
            moved += done
            stuck += left
    else:
        stuck = stayed
    return len(moved), stuck


GIVEN_FILE = "organise_given.json"  # (in the data folder: {project: {clip: the colour Organise gave it}})


def _key(thing):
    """A clip's own id, for what Organise gave it: a Media Pool clip's media id, a timeline clip's unique id."""
    try:  # (Resolve's objects answer hasattr with yes for anything; a call they don't have is None)
        if callable(getattr(thing, "GetMediaId", None)):
            return "m:" + thing.GetMediaId()
        return "t:" + thing.GetUniqueId()
    except Exception:
        return None


def _set_colour(thing, colour, palette, dry=False, given=None, every=False):
    """True when it changed. Kept: the colour it has, or one given by hand - neither in `palette` nor the one Organise
    gave this very clip last time (`given`, by _key: so a colour changed in a template, by hand in its file too,
    still reaches the clips that had the old one - 2026-10-30: "It didnt work again")."""
    current = thing.GetClipColor() or ""
    key = _key(thing) if given is not None else None
    ours = current in palette or (key is not None and given.get(key) == current)
    if every and not colour:  # (Recolour all clips: one the template gives no colour loses the one Organise gave it)
        if not current or not ours:
            return False
        if not dry and thing.ClearClipColor():
            given.pop(key, None) if key is not None else None
            return True
        return dry
    if every:  # (...and every other gets the template's, one coloured by hand too)
        ours = True
    if not colour or current == colour or (current and not ours):
        if colour and current == colour and key is not None and not dry:
            given[key] = colour  # (already right: still Organise's)
        return False
    if dry:
        return True
    done = bool(thing.SetClipColor(colour))
    if done and key is not None:
        given[key] = colour
    return done


def organise(resolve, dry=False, changes=None, colours=False, only=None):
    """Does it all to the open project; returns (worked, message). dry: only works out what it would do (and lists
    it in `changes`) - for trying it on a real project. colours: Recolour all clips (Settings > Organise, 2026-10-30:
    "a button inside organise that refreshes the colors of all clips") - nothing sorted, every clip the template's
    colour, one given by hand too; one the template gives none loses the colour Organise gave it. only: just these
    clips coloured (_key's: "m:<media id>", "t:<timeline clip id>") and nothing sorted - what Clipse has just made
    (a grabbed frame, an adjustment clip or composition placed - the same day: "if i take a grab frame action, then
    would that also not get a color?")."""
    note = changes.append if changes is not None else (lambda _line: None)
    from . import project_templates as pt
    project = resolve.GetProjectManager().GetCurrentProject() if resolve is not None else None
    if project is None:
        return False, "No project open"
    name, template = best_template(project)
    if template is None:
        return False, "Set the project up from a template first (tpl:)"
    the = rules(template)
    from .paths import data, read_json, write_json
    every_given = read_json(data(GIVEN_FILE), {}) or {}
    project_key = (getattr(project, "GetUniqueId", lambda: "")() or "") + ":" + (project.GetName() or "")
    given = every_given.setdefault(project_key, {})
    # (what counts as Organise's colour, not one given by hand: what the template gives now, what it gave before a
    #  change in Settings > Organise and Organise's own - 2026-10-30, b-roll changed to Olive stayed Orange: "Why
    #  does organise not update the colors")
    palette = set(the["colours"]["kinds"].values()) | set(the["colours"]["bins"].values()) \
        | set(the["colours"]["was"]) | OWN_COLOURS
    media_pool = project.GetMediaPool()
    root = media_pool.GetRootFolder()
    current = media_pool.GetCurrentFolder()
    added = [0]
    if colours or only is not None:
        pass
    elif dry:
        missing = [p for p in bin_paths(template.get("bins") or []) if p not in _project_bins(root)]
        added[0] = len(missing)
        for path in missing:
            note(f"bin  {path}")
    else:
        pt._add_bins(media_pool, root, template.get("bins") or [], added)
    bins = _project_bins(root)

    moved = 0
    loose = {}  # bin path -> its clips
    going = {}  # (dry) a loose clip's id -> the bin it would go in
    for clip in [] if colours or only is not None else root.GetClipList() or []:
        path = place_for(kind_of(clip), clip.GetClipProperty("File Path"), the["places"])
        if path:
            loose.setdefault(path, []).append(clip)
            going[clip.GetMediaId()] = path
            note(f"move {clip.GetName()} -> {path}")
    copied = []  # (clips Resolve wouldn't move)
    for path, clips in loose.items():
        if dry:
            moved += len(clips)
            continue
        folder = _bin(media_pool, root, bins, path)
        if folder is not None:
            done, stuck = _move(media_pool, root, clips, folder)
            moved += done
            copied += [(clip, folder) for clip in stuck]
    for wait in RETRY_AFTER:  # (just imported, Resolve copies some again and again - minutes later they move)
        if not copied:
            break
        time.sleep(wait)
        left = []
        for clip, folder in copied:
            done, stuck = _move(media_pool, root, [clip], folder)
            moved += done
            left += [(clip, folder)] if stuck else []
        copied = left
    if current is not None:
        media_pool.SetCurrentFolder(current)

    coloured = 0
    by_clip = {}  # a Media Pool clip's id -> its colour, for its timeline clips

    def walk(folder, path):
        nonlocal coloured
        for clip in folder.GetClipList() or []:
            kind = kind_of(clip)
            if kind == "timeline":
                continue
            colour = colour_for(kind, going.get(clip.GetMediaId(), path) if dry else path, the["colours"])
            by_clip[clip.GetMediaId()] = colour
            if only is not None and _key(clip) not in only:
                continue
            if clip.GetClipProperty("Type") not in UNCOLOURABLE and _set_colour(clip, colour, palette, dry, given,
                                                                                colours):
                coloured += 1
                note(f"colour {path or '(Master)'} / {clip.GetName()} -> {colour}")
        for sub in folder.GetSubFolderList() or []:
            walk(sub, f"{path}/{sub.GetName()}" if path else sub.GetName())
    walk(root, "")

    timelines = [project.GetTimelineByIndex(n) for n in range(1, (project.GetTimelineCount() or 0) + 1)] \
        if only is None else [project.GetCurrentTimeline()]
    for timeline in [t for t in timelines if t is not None]:
        for track in range(1, (timeline.GetTrackCount("video") or 0) + 1):
            for item in timeline.GetItemListInTrack("video", track) or []:
                clip = item.GetMediaPoolItem()
                if only is not None and _key(item) not in only and (clip is None or _key(clip) not in only):
                    continue
                if clip is not None:
                    colour = by_clip.get(clip.GetMediaId(), "")
                elif "adjust" in (item.GetName() or "").lower():
                    colour = the["colours"]["kinds"].get("adjustment", "")
                elif item.GetFusionCompCount():  # (a Fusion composition, title or generator from the Effects)
                    colour = the["colours"]["kinds"].get("fusion", "")
                else:
                    colour = ""
                if _set_colour(item, colour, palette, dry, given, colours):
                    coloured += 1
                    note(f"colour {timeline.GetName()} V{track} / {item.GetName()} -> {colour}")

    if not dry:
        write_json(data(GIVEN_FILE), every_given)
    done = [f"{added[0]} bin{'s' if added[0] != 1 else ''} added" if added[0] else "",
            f"{moved} clip{'s' if moved != 1 else ''} sorted" if moved else "",
            f"{coloured} coloured" if coloured else "",
            f"{len(copied)} Resolve wouldn't move" if copied else ""]
    if colours:
        return True, f"Recoloured with \u201c{name}\u201d: " + (f"{coloured} changed" if coloured else "all in order")
    return True, (f"{'Would organise' if dry else 'Organised'} with \u201c{name}\u201d: "
                  + (", ".join(d for d in done if d) or "all in order"))


def _bin_of(root, clip):
    """The bin path a Media Pool clip is in ("" for Master), or None when it isn't found."""
    mid = clip.GetMediaId()

    def walk(folder, path):
        if any(c.GetMediaId() == mid for c in folder.GetClipList() or []):
            return path
        for sub in folder.GetSubFolderList() or []:
            found = walk(sub, f"{path}/{sub.GetName()}" if path else sub.GetName())
            if found is not None:
                return found
        return None
    return walk(root, "")


def colour_now(resolve, things):
    """What Clipse has just made (a grabbed frame, an adjustment clip or composition placed, a title) its colour by
    the project's template, here and now - right after Resolve put it down, so it never shows plain first (2026-10-30,
    the owner: Alt+A's adjustment clip turning Tan 0.1 s later "look glitchy" - a program of its own took that long to
    start). One colour is ~1 ms; Resolve only makes the call wait until it has drawn the clip. Quiet: no template,
    no colour."""
    project = resolve.GetProjectManager().GetCurrentProject() if resolve is not None else None
    if project is None or not things:
        return
    _name, template = best_template(project)
    if template is None:
        return
    the = rules(template)
    palette = set(the["colours"]["kinds"].values()) | set(the["colours"]["bins"].values()) \
        | set(the["colours"]["was"]) | OWN_COLOURS
    from .paths import data, read_json, write_json
    every_given = read_json(data(GIVEN_FILE), {}) or {}
    given = every_given.setdefault((getattr(project, "GetUniqueId", lambda: "")() or "") + ":" + (project.GetName() or ""), {})
    root = project.GetMediaPool().GetRootFolder()
    for thing in things:
        if thing is None:
            continue
        clip = thing if callable(getattr(thing, "GetMediaId", None)) else thing.GetMediaPoolItem()
        if clip is not None:
            if clip.GetClipProperty("Type") in UNCOLOURABLE and clip is thing:
                continue
            colour = colour_for(kind_of(clip), _bin_of(root, clip) or "", the["colours"])
        elif "adjust" in (thing.GetName() or "").lower():
            colour = the["colours"]["kinds"].get("adjustment", "")
        elif thing.GetFusionCompCount():
            colour = the["colours"]["kinds"].get("fusion", "")
        else:
            continue
        _set_colour(thing, colour, palette, given=given)
    write_json(data(GIVEN_FILE), every_given)


def start(colours=False):
    """Runs it as a program of its own (main), its output in the logs folder's organise.log - from the picker, Resolve's
    menu and Settings > Organise's Recolour all clips (colours). In the background: with Resolve behind, it takes a
    second for each colour."""
    import subprocess
    from .launch import command
    from .paths import log as log_file
    args = ["--colours"] if colours else []
    with open(log_file("organise.log"), "w") as log:
        subprocess.Popen(command("organise", *args, windowless=True),
                         stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT)


def main():
    """The program (launch.command("organise")): organises the open project, then says how it went."""
    from . import resolve_client as rc
    from .client import send
    resolve = rc.connect_to_resolve(timeout=10)
    if resolve is None:
        worked, message = False, "Resolve didn't answer"
    else:
        try:
            only = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--only=")), None)
            worked, message = organise(resolve, colours="--colours" in sys.argv,
                                       only=set(filter(None, only.split(","))) if only is not None else None)
        except Exception as e:
            worked, message = False, f"Organise stopped: {e}"
    print(f"[organise] {message}", flush=True)
    if any(a.startswith("--only=") for a in sys.argv):
        sys.exit(0)  # (a grab or a clip placed says its own words; nothing more on screen)
    try:
        send(b"SAY:" + message.encode("utf-8"))
    except OSError:
        pass
    sys.exit(0 if worked else 1)


if __name__ == "__main__":
    main()
