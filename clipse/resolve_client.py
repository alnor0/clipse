"""Everything that talks to DaVinci Resolve's scripting API. No Qt import
here on purpose — this module doesn't know or care what GUI toolkit is
driving it, same as the socket/daemon plumbing didn't in the Tk version."""
import json
import os
import platform
import re
import sys
import time
from collections import defaultdict

from .settings import AUDIO_EXTENSIONS, STILL_IMAGE_EXTENSIONS, DEFAULT_DURATION_FRAMES
from .stills import CLIPSE_BIN
from . import paths

CACHE_DIR = paths.cache("projects")  # (one file a project - a project not opened in CACHE_DAYS goes: prune_caches)
CACHE_DAYS = 180
CACHE_TTL_SECONDS = 120  # older than this: shown at once, then quietly rescanned
CACHE_FORMAT_VERSION = 6 # bump when the cache file layout changes — older files are just rescanned
INSERT_FREQUENCY_FILE = paths.data("insert_frequency.json")
INSERT_FREQUENCY_MAX = 5000  # (names; past it the least inserted go)
RESOLVE_WAIT_RETRY_SECONDS = 3

RESOLVE_API_OVERRIDE = None
RESOLVE_LIB_OVERRIDE = None


def _default_resolve_paths():
    """(scripting folder, fusionscript library) for a standard install."""
    system = platform.system()
    if system == "Windows":
        return (os.path.expandvars(r"%PROGRAMDATA%\Blackmagic Design\DaVinci Resolve\Support\Developer\Scripting"),
                os.path.expandvars(r"%PROGRAMFILES%\Blackmagic Design\DaVinci Resolve\fusionscript.dll"))
    if system == "Darwin":
        return ("/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting",
                "/Applications/DaVinci Resolve/DaVinci Resolve.app/Contents/Libraries/Fusion/fusionscript.so")
    return ("/opt/resolve/Developer/Scripting", "/opt/resolve/libs/Fusion/fusionscript.so")


def _running_resolve_libs():
    """fusionscript next to the Resolve that's actually running — finds
    installs in non-standard places (another drive, a renamed folder)."""
    system = platform.system()
    found = []
    try:
        if system == "Windows":
            import subprocess
            out = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "(Get-Process Resolve -ErrorAction SilentlyContinue).Path"],
                capture_output=True, text=True, timeout=5,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
            for exe in out.splitlines():
                if exe.strip():
                    found.append(os.path.join(os.path.dirname(exe.strip()), "fusionscript.dll"))
        elif system == "Darwin":
            import subprocess
            out = subprocess.run(["ps", "-axo", "comm"], capture_output=True, text=True, timeout=5).stdout
            for exe in out.splitlines():
                if exe.endswith("/Contents/MacOS/Resolve"):
                    contents = os.path.dirname(os.path.dirname(exe))
                    found.append(os.path.join(contents, "Libraries", "Fusion", "fusionscript.so"))
        else:
            for pid in os.listdir("/proc"):
                if not pid.isdigit():
                    continue
                try:
                    exe = os.readlink(f"/proc/{pid}/exe")
                except OSError:
                    continue
                if os.path.basename(exe) == "resolve":
                    root = os.path.dirname(os.path.dirname(exe))  # .../bin/resolve -> ...
                    found.append(os.path.join(root, "libs", "Fusion", "fusionscript.so"))
    except Exception:
        pass
    return found


def _fusionscript_candidates():
    _api, default_lib = _default_resolve_paths()
    candidates = [RESOLVE_LIB_OVERRIDE, os.environ.get("RESOLVE_SCRIPT_LIB"), default_lib]
    if platform.system() == "Darwin":
        candidates += [
            "/Applications/DaVinci Resolve Studio.app/Contents/Libraries/Fusion/fusionscript.so",
            os.path.expanduser("~/Applications/DaVinci Resolve/DaVinci Resolve.app/Contents/Libraries/Fusion/fusionscript.so"),
        ]
    elif platform.system() == "Windows":
        candidates.append(r"C:\Program Files\Blackmagic Design\DaVinci Resolve\fusionscript.dll")
    return [c for c in candidates if c]


_script_module = None


def _load_fusionscript():
    """Loads Resolve's scripting library directly. (Resolve's own
    DaVinciResolveScript.py helper is only a fallback: in older Resolve
    versions it uses the `imp` module, which Python 3.12+ no longer has.)"""
    global _script_module
    if _script_module is not None:
        return _script_module
    import importlib.machinery
    import importlib.util
    tried = []
    for checked_running in (False, True):
        paths = _running_resolve_libs() if checked_running else _fusionscript_candidates()
        for path in paths:
            if path in tried:
                continue
            tried.append(path)
            if not os.path.isfile(path):
                continue
            try:
                loader = importlib.machinery.ExtensionFileLoader("fusionscript", path)
                spec = importlib.util.spec_from_file_location("fusionscript", path, loader=loader)
                module = importlib.util.module_from_spec(spec)
                loader.exec_module(module)
                _script_module = module
                return module
            except Exception as e:
                print(f"Couldn't load {path}: {e}")
    # Fallback: Resolve's helper module
    api_dir = RESOLVE_API_OVERRIDE or os.environ.get("RESOLVE_SCRIPT_API") or _default_resolve_paths()[0]
    sys.path.append(os.path.join(api_dir, "Modules"))
    try:
        import DaVinciResolveScript as dvr_script
        _script_module = dvr_script
        return dvr_script
    except Exception:
        raise SystemExit(
            "Couldn't find DaVinci Resolve's scripting library (fusionscript). Looked in:\n  "
            + "\n  ".join(tried)
            + "\nIs DaVinci Resolve Studio installed? If it's installed somewhere else, set the "
              "RESOLVE_SCRIPT_LIB environment variable to the full path of fusionscript.")


def connect_to_resolve(on_waiting=None, timeout=None, wait=None):
    """Blocking connect-and-retry — call this before the GUI event loop
    starts. `on_waiting` is called once, the first time a retry is needed,
    so the caller can print/log. With `timeout` (seconds), gives up and
    returns None if Resolve hasn't answered by then. `wait(seconds)` is
    called instead of sleeping between tries; False from it gives up too."""
    dvr_script = _load_fusionscript()

    deadline = None if timeout is None else time.monotonic() + timeout
    attempt = 0
    while True:
        try:
            r = dvr_script.scriptapp("Resolve")
            if r is not None and r.GetProjectManager() is not None:
                return r
        except Exception:
            pass
        if deadline is not None and time.monotonic() >= deadline:
            return None
        if attempt == 0 and on_waiting:
            on_waiting()
        attempt += 1
        pause = (RESOLVE_WAIT_RETRY_SECONDS if deadline is None
                 else max(0.1, min(1.0, deadline - time.monotonic())))
        if wait is None:
            time.sleep(pause)
        elif not wait(pause):
            return None


def tc_to_frame(tc, fps):
    tc = tc.replace(";", ":")
    h, m, s, f = [int(x) for x in tc.split(":")]
    return int(((h * 3600 + m * 60 + s) * fps) + f)


def collect_all(folder, results):
    for item in folder.GetClipList():
        clip_type = item.GetClipProperty("Type") or ""
        results.append((item.GetMediaId(), item.GetName(), folder.GetName(), clip_type))
    for sub in folder.GetSubFolderList():
        collect_all(sub, results)


_META_KEYS = ("Keyword", "Keywords", "Comments", "Description")


def _seconds(props):
    """A clip's length in seconds from its properties, or 0 if unknown."""
    try:
        fps = float(str(props.get("FPS") or 0).split()[0])
    except (ValueError, IndexError):
        fps = 0.0
    if fps <= 0:
        return 0.0
    frames = props.get("Frames")
    try:
        if frames not in (None, ""):
            return int(float(frames)) / fps
    except ValueError:
        pass
    duration = str(props.get("Duration") or "")
    if duration.count(":") + duration.count(";") == 3:
        try:
            return tc_to_frame(duration, round(fps)) / round(fps)
        except (ValueError, ZeroDivisionError):
            pass
    return 0.0


def _added(props):
    """When the clip came into the Media Pool, in seconds since 1970 - 0 when not known.
    Resolve writes it "Tue Oct 20 2026 13:36:41" (21.1.1)."""
    text = str(props.get("Date Added") or "").strip()
    if not text:
        return 0.0
    try:
        return time.mktime(time.strptime(text, "%a %b %d %Y %H:%M:%S"))
    except (ValueError, OverflowError):
        return 0.0


def _clip_info(item, state):
    """(type, tags, colour, seconds, file path, when it was added) of a Media Pool clip - all
    from one GetClipProperty() call (plus the metadata / clip colour
    calls only where this Resolve needs them, decided on the first clip)."""
    props = item.GetClipProperty()
    if not isinstance(props, dict) or not props:
        return item.GetClipProperty("Type") or "", "", "", 0.0, "", 0.0
    secs = round(_seconds(props), 2)
    file = str(props.get("File Path") or "")
    clip_type, tags, color = _clip_type_and_tags(item, state, props)
    return clip_type, tags, color, secs, file, _added(props)


def _clip_type_and_tags(item, state, props=None):
    """A clip's type, plus its keywords, comments, description and clip
    colour as one lower-case string for searching. All clip properties
    come back in one call; whether this Resolve also needs the metadata /
    clip colour calls is decided on the first clip (state)."""
    if props is None:
        props = item.GetClipProperty() if state.get("tags") else None
    if not isinstance(props, dict) or not props:
        return item.GetClipProperty("Type") or "", "", ""
    if not state.get("tags"):
        return props.get("Type") or "", "", ""
    if "need_meta" not in state:
        state["need_meta"] = not any(k in props for k in _META_KEYS)
        state["need_color"] = "Clip Color" not in props
    parts = [props.get(k) for k in _META_KEYS]
    if state["need_meta"]:
        metadata = item.GetMetadata() or {}
        if isinstance(metadata, dict):
            parts += [metadata.get(k) for k in _META_KEYS]
    color = str((item.GetClipColor() if state["need_color"] else props.get("Clip Color")) or "").strip()
    parts.append(color)
    tags = " ".join(str(p).strip() for p in parts if p and str(p).strip())
    return props.get("Type") or "", tags.lower(), color


def scan_media_pool(root_folder, with_tags=True):
    """One walk over the whole Media Pool, collecting every clip AND every
    bin at once. Each clip records the bin path it lives in, so bin
    counts and clip lookups can be answered later without walking the
    Media Pool again (every Resolve API call is a round-trip, so the
    number of calls is what makes a scan fast or slow).
    Returns (entries, bin_paths): entries are
    (media_id, name, folder_name, clip_type, path, tags, clip_color, seconds, file, added) tuples, path being
    a tuple of bin names below the root; bin_paths lists every bin's path."""
    scan = MediaPoolScan(root_folder, with_tags)
    while not scan.step(None):
        pass
    return scan.entries, scan.bin_paths


class MediaPoolScan:
    """The same walk as scan_media_pool(), done a slice at a time: step()
    works for at most `budget` seconds and returns True once finished.
    The picker runs it between keypresses, so a big Media Pool is read
    without the window ever freezing - the list fills in when it's done.

    With `known` (media id -> entry, from the last read) it's the quick look every open takes (2026-10-19): a clip
    already known, by the same name in the same bin, keeps what was read of it then - only new, renamed or moved
    ones are asked about in full. About a third of a full read (measured: 22 ms against 78 for 132 clips); what it
    can't see (a new clip colour, keywords) waits for the next full read."""

    def __init__(self, root_folder, with_tags=True, known=None):
        self.entries, self.bin_paths = [], []
        self._known = known or {}
        self.count = 0
        self.total = 0       # clips in the whole Media Pool - known once the bins are walked (cheap: one call per bin)
        self.done = False
        self._state = {"tags": with_tags}
        self._walk = self._clips(root_folder)

    def _clips(self, root):
        # first the bins (a call or two each) - then the total is known and
        # reading the clips themselves (the slow part) can show how far it is
        bins = []

        def walk(folder, folder_name, path):  # same order as always: a bin's clips, then its bins
            clips = list(folder.GetClipList() or [])
            bins.append((folder_name, path, clips))
            self.total += len(clips)
            yield
            for sub in folder.GetSubFolderList() or []:
                sub_name = sub.GetName()
                sub_path = path + (sub_name,)
                self.bin_paths.append(sub_path)
                yield from walk(sub, sub_name, sub_path)
        yield from walk(root, root.GetName(), ())
        for folder_name, path, clips in bins:
            for item in clips:
                before = self._known.get(item.GetMediaId()) if self._known else None
                if before is not None and before[2] == folder_name and before[4] == path and before[1] == item.GetName():
                    self.entries.append(before)
                    self.count += 1
                    yield
                    continue
                try:
                    clip_type, tags, color, secs, file, added = _clip_info(item, self._state)
                except Exception:
                    clip_type, tags, color, secs, file, added = item.GetClipProperty("Type") or "", "", "", 0.0, "", 0.0
                self.entries.append((item.GetMediaId(), item.GetName(), folder_name, clip_type, path, tags, color,
                                     secs, file, added))
                self.count += 1
                yield

    def step(self, budget=0.012):
        """Reads clips until `budget` seconds have passed (None: to the end)."""
        if self.done:
            return True
        deadline = None if budget is None else time.monotonic() + budget
        for _ in self._walk:
            if deadline is not None and time.monotonic() >= deadline:
                return False
        self.done = True
        return True


def find_by_media_id(folder, media_id):
    for item in folder.GetClipList():
        if item.GetMediaId() == media_id:
            return item, folder
    for sub in folder.GetSubFolderList():
        result = find_by_media_id(sub, media_id)
        if result:
            return result
    return None


def collect_bins(folder, path, results):
    for sub in folder.GetSubFolderList():
        sub_path = path + (sub.GetName(),)
        results.append(sub_path)
        collect_bins(sub, sub_path, results)


def find_folder_by_path(folder, path):
    if not path:
        return folder
    name, rest = path[0], path[1:]
    for sub in folder.GetSubFolderList():
        if sub.GetName() == name:
            return find_folder_by_path(sub, rest)
    return None


_COPY_SUFFIX = re.compile(r"(\s+copy(\s*\d+)?)+$", re.IGNORECASE)


def _base_name(name):
    """The clip name without the " copy" / " copy 2" Resolve adds to
    duplicated clips - so "logo.png copy" still counts as a .png."""
    return _COPY_SUFFIX.sub("", name or "")


def get_category(name, clip_type, settings):
    if clip_type == "Timeline":  # the Media Pool lists every timeline too: never a clip (it has its own rows)
        return "timeline"
    if clip_type == "Generator":
        return "adjustment"
    if clip_type == "Still":
        return "image"
    if clip_type == "Audio":
        return "audio"
    name = _base_name(name)
    if clip_type == "Compound":
        return "compound"
    if name.lower().endswith(AUDIO_EXTENSIONS):
        return "audio"
    if name.lower().endswith(STILL_IMAGE_EXTENSIONS):
        return "image"
    return "video"


def is_still_image(name, clip_type=None):
    return clip_type == "Still" or _base_name(name).lower().endswith(STILL_IMAGE_EXTENSIONS)


def collect_bin_clips(folder, settings, results):
    for item in folder.GetClipList():
        name = item.GetName()
        clip_type = item.GetClipProperty("Type") or ""
        category = get_category(name, clip_type, settings)
        if settings.category_enabled(category):
            results.append((item, folder, name, category))
    if settings.general["bin_insert_recursive"]:
        for sub in folder.GetSubFolderList():
            collect_bin_clips(sub, settings, results)


def count_bin_clips(folder, settings):
    """How many clips a bin would actually insert (respects the same
    category toggles and bin_insert_recursive setting as a real insert),
    used for the "(N)" count shown next to each bin row."""
    items = []
    collect_bin_clips(folder, settings, items)
    return len(items)


class RowData:
    """One row in the picker list. `path` is only used by the
    script/macro/comp row kinds (see scripts_fusion.py) — Media Pool clip
    rows don't need it, since they're resolved through the Media Pool
    itself instead. `info_segments`, if set, is a list of (text, color_key)
    tuples rendered in place of folder_list, letting parts of the info
    text be colored independently — used by project rows to color-code
    Created/Modified by age (color_key: None for plain, or 'recent'/
    'medium'/'old'). `favorited` is baked in at row-build time from the
    persisted favorites set, and updated in place whenever toggled."""
    __slots__ = ("icon", "category", "name", "folder_list", "path", "info_segments", "favorited", "tags", "color",
                 "music", "bpm", "file", "secs", "analysis", "extra_tags", "glyph", "source", "added", "file_tags",
                 "energy", "energy_guess")

    def __init__(self, icon, category, name, folder_list, path=None, info_segments=None, favorited=False,
                 tags="", color=""):
        self.music = False  # audio only: True = music, False = sound effect, None = not known yet
        self.bpm = None     # music: tempo found by bpm.py
        self.file = ""      # the clip's file on disk (audio rows), for the BPM check
        self.source = ""    # the file on disk of any kind of clip (the project check-up looks for it)
        self.secs = 0.0
        self.added = 0.0    # when the clip came into the Media Pool (seconds since 1970), 0 when not known
        self.analysis = None  # sound_analysis.py result (audio rows, once analysed)
        self.extra_tags = ""  # searchable words from the analysis: "128 bpm calm a minor"
        self.file_tags = []   # sounds: the tags inside the file (file_tags.py), searched too
        self.energy = 0       # sounds: 1-3, the file's own tag; 0 none
        self.energy_guess = 0  # music: 1-3 from the analysis, shown only with Settings' Guess energy on
        self.glyph = None     # action rows: which line icon (glyphs.py)
        self.color = color  # Resolve's clip colour name ("Teal"), or ""
        self.tags = tags  # keywords, comments, clip colour (lower case) - searched too
        self.icon = icon
        self.category = category
        self.name = name
        self.folder_list = folder_list
        self.path = path
        self.info_segments = info_segments
        self.favorited = favorited


_WORDS = re.compile(r"[a-z]+")
_MUSIC_WORDS = {"music", "musik", "song", "songs", "track", "tracks", "bgm", "beat", "beats", "soundtrack",
                "score", "instrumental", "lofi", "melody", "remix", "edm", "hiphop", "jazz", "piano",
                "orchestral", "acoustic", "stems", "stem"}  # (stems: a song in parts - 2026-11-01)
_SFX_WORDS = {"sfx", "fx", "sounds", "effect", "effects", "whoosh", "swoosh", "swish", "woosh",
              "hit", "hits", "impact", "impacts", "riser", "risers", "boom", "click", "clicks", "pop", "pops",
              "foley", "ambience", "ambiance", "atmos", "roomtone", "transition", "transitions", "glitch",
              "ding", "notification", "rumble", "braam", "stinger", "sweep", "vo", "voice",
              "voiceover", "narration", "dialogue", "interview", "keysounds", "recording"}
ALWAYS_MUSIC_SECONDS = 60  # (2026-11-01, a song with no steady beat, filed as a sound effect: "But johnny is music?")


def is_music(name, folders, tags, seconds, min_seconds=30):
    """Music or a sound effect? True = music, False = a sound effect (or a
    voice), None = can't tell: between min_seconds and a minute, so the
    background beat check decides (a steady beat = music). Longer than that,
    with nothing in the name against it, it's music, beat or no beat.
    The clip's own name counts first, then its bins and keywords - so a
    "whoosh" inside a "Music" bin is still a sound effect."""
    for text in (_base_name(name).lower(), (folders or "").lower(), (tags or "").lower()):
        words = set(_WORDS.findall(text))
        if words & _SFX_WORDS and not (words & {"music", "song", "soundtrack", "bgm"}):
            return False
        if words & _MUSIC_WORDS:
            return True
    if seconds and seconds < min_seconds:
        return False
    if seconds and seconds >= max(min_seconds, ALWAYS_MUSIC_SECONDS):
        return True
    return None


def cache_file_for(project_name):
    safe_name = re.sub(r'[^a-zA-Z0-9_-]', '_', project_name)
    return os.path.join(CACHE_DIR, f"{safe_name}.json")


def read_cache(project_name):
    """(entries, bin_paths, age in seconds) from the project's last scan,
    or (None, None, None) when there isn't a usable one."""
    cache_file = cache_file_for(project_name)
    try:
        stat = os.stat(cache_file)
        age = max(0.0, time.time() - stat.st_mtime)
        stamp = (cache_file, stat.st_mtime_ns, stat.st_size)
        if _read_before.get("stamp") == stamp:  # the same file as last time: no need to read it again
            return _read_before["entries"], _read_before["bins"], age
        with open(cache_file, encoding="utf-8") as f:
            cached = json.load(f)
        if not (isinstance(cached, dict) and cached.get("v") == CACHE_FORMAT_VERSION):
            return None, None, None  # old format - just rescan
        entries = [(e["id"], e["name"], e["folder"], e.get("type", ""), tuple(e.get("path", ())),
                    e.get("tags", ""), e.get("color", ""), e.get("secs", 0.0), e.get("file", ""), e.get("added", 0.0))
                   for e in cached["entries"]]
        bins = [tuple(p) for p in cached["bins"]]
        _read_before.update(stamp=stamp, entries=entries, bins=bins)
        return entries, bins, age
    except (OSError, ValueError, KeyError, TypeError):
        return None, None, None


# The last cache file read, and the rows last built from it: opening the
# picker again with nothing changed doesn't do either a second time.
# (Whoever gets these lists must not change them in place.)
_read_before = {}
_built_before = {}


def write_cache(project_name, entries, bin_paths):
    cache_file = cache_file_for(project_name)
    try:
        paths.write_json(cache_file, {
            "v": CACHE_FORMAT_VERSION,
            "entries": [{"id": i, "name": n, "folder": fo, "type": t, "path": list(pa), "tags": tg,
                         "color": co, "secs": se, "file": fi, "added": ad}
                        for i, n, fo, t, pa, tg, co, se, fi, ad in entries],
            "bins": [list(p) for p in bin_paths]})
    except OSError:
        pass


def prune_caches():
    """The Media Pool lists of projects not opened in CACHE_DAYS (the service's start): one a project ever opened
    piled up for good. A project opened again is read again, as the first time."""
    cutoff = time.time() - CACHE_DAYS * 86400
    try:
        old = [e.path for e in os.scandir(CACHE_DIR) if e.is_file() and e.stat().st_mtime < cutoff]
    except OSError:
        return
    for path in old:
        try:
            os.remove(path)
        except OSError:
            pass


def scan_with_tags(settings):
    return settings.general.get("search_metadata", True) or settings.general.get("show_clip_color", True)


def load_rows(settings, root_folder, project_name, media_pool, force_refresh=False, favorited_names=None):
    """Rows from the cache when it's recent, else from a full (blocking)
    scan. The picker itself uses read_cache() + MediaPoolScan instead, so
    it never waits for a scan."""
    entries = bin_paths = None
    if not force_refresh:
        entries, bin_paths, age = read_cache(project_name)
        if entries is not None and age >= CACHE_TTL_SECONDS:
            entries = None
    if entries is None:
        entries, bin_paths = scan_media_pool(root_folder, with_tags=scan_with_tags(settings))
        write_cache(project_name, entries, bin_paths)
    rows, filtered_group_list, id_paths = build_rows(settings, entries, bin_paths, media_pool, favorited_names)
    return rows, filtered_group_list, cache_file_for(project_name), id_paths


def _selected_row(settings, media_pool):
    """The "Selected Clips (3)" row - counted in Resolve right now, every time."""
    try:
        selected_count = len(media_pool.GetSelectedClips() or [])
        selected_label = f"Selected Clips ({selected_count})"
    except Exception:
        selected_label = "Selected Clips (unsupported)"
    return (RowData(settings.icons["selected"], "selected", selected_label, ""),
            (selected_label, [(None, "", "Selected")], "selected"))


def build_rows(settings, entries, bin_paths, media_pool, favorited_names=None):
    """The picker's rows from a scan (or the cache): (rows, filtered_group_list, id_paths).
    The same scan with the same settings and favourites gives the rows
    built for it last time (as new lists), so opening again is instant."""
    general = settings.general
    made_from = (id(entries), len(entries), id(bin_paths), len(bin_paths), tuple(sorted(settings.icons.items())),
                 tuple(settings.kind_built(k) for k in ("show_audio", "show_video", "show_adjustment_clips",
                                                        "show_compound_clips", "show_images", "show_bins")),
                 general["bin_insert_recursive"],
                 settings.listen.get("music_min_seconds", 30), frozenset(favorited_names or ()))
    if _built_before.get("made_from") != made_from:
        rows, groups, id_paths = _build_rows(settings, entries, bin_paths, favorited_names)
        # (entries and bin_paths are kept too: while they're alive, their id() can't be anyone else's)
        _built_before.update(made_from=made_from, rows=rows, groups=groups, id_paths=id_paths,
                             entries=entries, bins=bin_paths)
    rows, groups = list(_built_before["rows"]), list(_built_before["groups"])
    if settings.kind_built("show_selected_clips_option"):
        row, group = _selected_row(settings, media_pool)
        rows.append(row)
        groups.append(group)
    return rows, groups, _built_before["id_paths"]


def _build_rows(settings, entries, bin_paths, favorited_names=None):
    icons = settings.icons
    favorited_names = favorited_names or set()

    # media id -> bin path, so inserting a clip can go straight to its bin
    # instead of searching the whole Media Pool (see find_clip_for_row).
    id_paths = {e[0]: e[4] for e in entries}

    groups = defaultdict(list)
    group_tags = defaultdict(list)
    group_color = {}
    group_media = {}  # (name, category) -> (seconds, file) of its first clip
    group_added = {}  # (name, category) -> when the newest of its clips came into the Media Pool
    categorized = []  # (path, category) per clip — reused for bin counts below
    for media_id, name, folder, clip_type, path, tags, color, secs, file, added in entries:
        if tuple(path) == (CLIPSE_BIN,):  # the app's own clips (text_plus, adjustment_clip ...): Basics places them
            continue
        category = get_category(name, clip_type, settings)
        if color and (name, category) not in group_color:
            group_color[(name, category)] = color
        if (name, category) not in group_media or (file and not group_media[(name, category)][1]):
            group_media[(name, category)] = (secs or 0.0, file or "")
        groups[(name, category)].append((media_id, folder, clip_type))
        group_added[(name, category)] = max(added or 0.0, group_added.get((name, category), 0.0))
        if tags and tags not in group_tags[(name, category)]:
            group_tags[(name, category)].append(tags)
        categorized.append((path, category))

    filtered_group_list = []
    for (name, category), instances in groups.items():
        if settings.category_enabled(category):
            filtered_group_list.append((name, instances, category))

    rows = []
    music_secs = float(settings.listen.get("music_min_seconds", 30) or 30)
    for name, instances, category in filtered_group_list:
        folder_list = ", ".join(f for _, f, _ in instances)
        tags = " ".join(group_tags.get((name, category), ()))
        row = RowData(icons[category], category, name, folder_list, favorited=name in favorited_names,
                      tags=tags, color=group_color.get((name, category), ""))
        row.source = group_media.get((name, category), (0.0, ""))[1]
        row.added = group_added.get((name, category), 0.0)
        if category == "audio":
            secs, file = group_media.get((name, category), (0.0, ""))
            row.file = file
            row.secs = secs
            row.music = is_music(name, folder_list, tags, secs, music_secs)
        rows.append(row)

    if settings.kind_built("show_bins"):
        # Bin counts come from the scan above — no extra Resolve calls.
        recursive = settings.general["bin_insert_recursive"]
        enabled_paths = [path for path, category in categorized if settings.category_enabled(category)]
        for path in bin_paths:
            if tuple(path) == (CLIPSE_BIN,):  # (its frame_grabs and compound_clips are listed)
                continue
            bin_name = path[-1]
            parent_display = " / ".join(path[:-1])
            depth = len(path)
            if recursive:
                count = sum(1 for p in enabled_paths if p[:depth] == path)
            else:
                count = sum(1 for p in enabled_paths if p == path)
            rows.append(RowData(icons["bin"], "bin", f"{bin_name} ({count})", parent_display,
                                 favorited=bin_name in favorited_names))
            filtered_group_list.append((bin_name, [(path, parent_display, "Bin")], "bin"))

    return rows, filtered_group_list, id_paths


def load_insert_frequency():
    data = paths.read_json(INSERT_FREQUENCY_FILE, {})
    return data if isinstance(data, dict) else {}


def record_insert(settings, insert_frequency, name):
    if not settings.general["sort_by_insert_frequency"]:
        return
    insert_frequency[name] = insert_frequency.get(name, 0) + 1
    if len(insert_frequency) > INSERT_FREQUENCY_MAX:
        for least in sorted(insert_frequency, key=insert_frequency.get)[:len(insert_frequency) - INSERT_FREQUENCY_MAX]:
            if least != name:
                del insert_frequency[least]
    try:
        paths.write_json(INSERT_FREQUENCY_FILE, insert_frequency)
    except OSError:
        pass


RECENT_FILE = paths.data("recent.json")
RECENT_MAX = 60


def load_recent():
    """Recently inserted things, most recent first: clip names, or
    "macro:<path>" / "script:<path>" / ... for the other row kinds."""
    data = paths.read_json(RECENT_FILE, [])
    return [k for k in data if isinstance(k, str)] if isinstance(data, list) else []


def record_recent(key):
    if not key or key.startswith("Selected Clips"):
        return
    recent = [k for k in load_recent() if k != key]
    recent.insert(0, key)
    try:
        paths.write_json(RECENT_FILE, recent[:RECENT_MAX])
    except OSError:
        pass


SEARCH_HISTORY_FILE = paths.data("search_history.json")
SEARCH_HISTORY_MAX = 100


def load_search_history():
    """Searches you acted on (inserted, revealed, ran ...), newest first."""
    data = paths.read_json(SEARCH_HISTORY_FILE, [])
    return [k for k in data if isinstance(k, str) and k.strip()] if isinstance(data, list) else []


def record_search(text):
    text = (text or "").strip()
    if not text:
        return
    history = [k for k in load_search_history() if k != text]
    history.insert(0, text)
    try:
        paths.write_json(SEARCH_HISTORY_FILE, history[:SEARCH_HISTORY_MAX])
    except OSError:
        pass


FAVORITES_FILE = paths.config("favorites.json")


def load_favorites():
    """Set of favorited clip names, persisted across sessions (unlike
    staged clips, which are cleared after every insert)."""
    data = paths.read_json(FAVORITES_FILE, [])
    return {k for k in data if isinstance(k, str)} if isinstance(data, list) else set()


def save_favorites(favorited_names):
    try:
        paths.write_json(FAVORITES_FILE, sorted(favorited_names))
    except OSError:
        pass


def find_clip_for_row(session, idx):
    filtered_group_list = session["filtered_group_list"]
    root_folder = session["root_folder"]
    cache_file = session["cache_file"]

    name, instances, category = filtered_group_list[idx]
    target_id, folder_name, clip_type = instances[0]
    found = None
    # Fast path: go straight to the clip's own bin (a few API calls)
    # instead of searching the whole Media Pool clip by clip.
    path = (session.get("id_paths") or {}).get(target_id)
    if path is not None:
        folder = find_folder_by_path(root_folder, path)
        if folder is not None:
            for item in folder.GetClipList() or []:
                if item.GetMediaId() == target_id:
                    found = (item, folder)
                    break
    if found is None:  # clip was moved since the scan — fall back to a full search
        found = find_by_media_id(root_folder, target_id)
    if not found:
        print(f"'{name}' no longer found — cache may be stale, delete {cache_file} and retry.")
        return None, None, name
    chosen_item, chosen_folder = found
    return chosen_item, chosen_folder, name


def expand_selected_clips(session, settings, selection_order_ids):
    media_pool = session["media_pool"]
    root_folder = session["root_folder"]
    try:
        selected = media_pool.GetSelectedClips() or []
    except AttributeError:
        print("This DaVinci Resolve version's scripting API doesn't support "
              "GetSelectedClips() — Selected Clips can't be used.")
        return []
    selected_by_id = {item.GetMediaId(): item for item in selected}
    ordered_ids = [i for i in selection_order_ids if i in selected_by_id]
    seen = set(ordered_ids)
    ordered_ids += [i for i in selected_by_id if i not in seen]
    items = []
    for media_id in ordered_ids:
        item = selected_by_id[media_id]
        name = item.GetName()
        clip_type = item.GetClipProperty("Type") or ""
        found = find_by_media_id(root_folder, media_id)
        folder = found[1] if found else root_folder
        category = get_category(name, clip_type, settings)
        if category != "timeline":
            items.append((item, folder, name, category))
    return items


def expand_row_to_items(session, settings, idx, selection_order_ids):
    name, instances, category = session["filtered_group_list"][idx]
    if category == "bin":
        path = instances[0][0]
        bin_folder = find_folder_by_path(session["root_folder"], path)
        if bin_folder is None:
            print(f"Bin '{name}' no longer found — skipped.")
            return []
        items = []
        collect_bin_clips(bin_folder, settings, items)
        if not items:
            print(f"Bin '{name}' has no clips to insert.")
        return items
    if category == "selected":
        return expand_selected_clips(session, settings, selection_order_ids)
    chosen_item, chosen_folder, clip_name = find_clip_for_row(session, idx)
    if chosen_item is None:
        return []
    clip_type = chosen_item.GetClipProperty("Type") or ""
    resolved_category = get_category(clip_name, clip_type, settings)
    return [(chosen_item, chosen_folder, clip_name, resolved_category)]


def compute_clip_duration(settings, chosen_item, name, fps=None):
    """Native duration a clip would get if inserted normally. Prefers
    Resolve's Frames property, but that comes back empty for at least
    some audio-only media items — when it does, falls back to parsing
    the Duration property (a timecode string) using the clip's own FPS,
    printing exactly what was tried so a wrong guess here is diagnosable
    rather than silently wrong again. (A preset's fixed length is applied
    on top of this - see PickerWindow._clip_range.)
    A picture's is the one set in Insert as (presets "still_length"), in the timeline's frames."""

    if is_still_image(name, chosen_item.GetClipProperty("Type")):
        # A picture has no length of its own (Frames says 1): it lasts what Insert as says a picture
        # lasts - in the timeline's frames - and insert_clip_item gives it exactly that (append_clip).
        if fps:
            return max(1, int(round(float(settings.presets.get("still_length", 5.0)) * fps)))
        return DEFAULT_DURATION_FRAMES

    frames_prop = chosen_item.GetClipProperty("Frames")
    if frames_prop:
        try:
            return int(frames_prop)
        except (TypeError, ValueError):
            print(f"[duration] '{name}': Frames property was {frames_prop!r} — not a valid integer.")

    duration_prop = chosen_item.GetClipProperty("Duration")
    fps_prop = chosen_item.GetClipProperty("FPS")
    if duration_prop:
        try:
            clip_fps = float(fps_prop) if fps_prop else 24.0
            duration_str = str(duration_prop)
            if ":" in duration_str:
                # The Duration is written in the TIMELINE's frames, the answer wanted in the clip's own
                # (measured in 21.1.1: a sound with FPS 24 and Duration 00:00:01:17 lands 77 frames long
                # on a 60 fps timeline - and asked for frames 0-10 it lands 25 long).
                shown_at = fps or clip_fps
                frames = round(tc_to_frame(duration_str, shown_at) * clip_fps / shown_at)
            else:
                # Not timecode-shaped — try it as a plain seconds value.
                frames = round(float(duration_str) * clip_fps)
            if frames > 0:
                return frames
        except Exception as e:
            print(f"[duration] '{name}': couldn't parse Duration={duration_prop!r} (FPS={fps_prop!r}): {e}")

    print(f"[duration] '{name}': couldn't determine native length from any property — "
          f"using the {DEFAULT_DURATION_FRAMES}-frame default. Please report this so it can be fixed properly.")
    return DEFAULT_DURATION_FRAMES


def _loudest_in(item, fps, source_start=0):
    """Timeline frames from where a clip starts (`source_start`: its first frame used, in its own frames) to its
    loudest moment - or None (no sound to go by)."""
    from . import sound_analysis as sa
    try:
        seconds = sa.loudest(item.GetClipProperty("File Path") or "")
    except Exception:
        return None
    if seconds is None:
        return None
    rate = clip_rate(item, fps)
    return int(round((seconds * rate - source_start) * fps / rate))


def swap_plan(opts, old, new, fps, whole_new, new_still, still_frames):
    """Where a swapped-in clip goes and what of it (Swap clip's ⋯, `opts`: swap_length / swap_align /
    swap_same_part). old: {"start", "end", "prev_end", "next_start", "source_start" (its first frame, in its own
    frames), "rate" (its frame rate), "loudest" (timeline frames from its start, or None)}; new: {"rate",
    "loudest" (timeline frames from its own beginning, or None)}; whole_new: its length in its own frames (None: a
    picture). Returns (start, length) on the timeline and `first`, its first frame in its own frames."""
    length_rule, align = opts.get("swap_length", "old"), opts.get("swap_align", "start")
    start, end = old["start"], old["end"]
    rate = new["rate"] or fps
    first = 0
    if opts.get("swap_same_part") and not new_still and old.get("source_start"):
        first = int(round(old["source_start"] / (old.get("rate") or fps) * rate))  # the same moment, in seconds
        if whole_new and first >= whole_new:
            first = 0

    def room(from_frame):  # timeline frames of it from `from_frame` on (a picture: any length)
        return None if new_still else max(1, int(round((whole_new - from_frame) * fps / rate)))

    def frames(timeline_frames):  # timeline frames -> its own
        return int(round(timeline_frames * rate / fps))
    lined = align == "loudest" and old.get("loudest") is not None and new.get("loudest") is not None \
        and not opts.get("swap_same_part")
    if length_rule == "old":  # its place stays: which part of it fills that place
        at, length = start, end - start
        if lined:
            shift = new["loudest"] - old["loudest"]  # (+: that much of its beginning goes)
            if shift >= 0:
                first = frames(shift)
            else:
                at, length = start - shift, length + shift
        elif align == "end" and not new_still and not opts.get("swap_same_part"):
            first = max(0, whole_new - frames(length))
        reach = room(first)
        length = max(1, min(length, reach) if reach else length)
        return at, length, first
    length = room(first) or still_frames  # its own length
    at = start if align == "start" or (align == "loudest" and not lined) else \
        end - length if align == "end" else start + old["loudest"] - new["loudest"]
    if length_rule == "own_stop":  # between the clip before and the one after
        floor = old.get("prev_end")
        if floor is not None and at < floor:
            first += frames(floor - at)
            length -= floor - at
            at = floor
        if old.get("next_start") is not None and at + length > old["next_start"]:
            length = old["next_start"] - at
    return at, max(1, length), first


def swap_items(settings, timeline, media_pool, items, new, new_name, fps, look_of):
    """Swap clip: `new` (a Media Pool clip) in place of each of `items` (timeline clips), the way Swap clip's ⋯
    says (swap_plan: how long, where, which part of it; its size and place, the old one's grade). Its clip
    colour goes along. A picture with its sound goes with the sound it brings (its own is taken out); where
    there was no sound, none comes. A sound's place takes only a sound, a picture's only a picture. Run on over
    the next clip (swap_length "own_over"), it goes a track up where it would cover something.
    Returns (swapped, skipped)."""
    opts = settings.timeline_tools
    kind_new = str(new.GetClipProperty("Type") or "")
    new_still = is_still_image(new_name, kind_new)
    new_sound, new_picture = "Audio" in kind_new, kind_new != "Audio"
    whole = None if new_still else compute_clip_duration(settings, new, new_name, fps)
    still_frames = compute_clip_duration(settings, new, new_name, fps) if new_still else 0
    wants_loudest = opts.get("swap_align") == "loudest"
    new_info = {"rate": clip_rate(new, fps), "loudest": _loudest_in(new, fps) if wants_loudest else None}
    done_spots, swapped, skipped = set(), 0, 0
    # (pictures first: a picture's own sound goes with it and isn't swapped by itself afterwards)
    for item in sorted(items, key=lambda it: it.GetTrackTypeAndIndex()[0] != "video"):
        try:
            track_type, index = item.GetTrackTypeAndIndex()
            start, end = int(item.GetStart()), int(item.GetEnd())
        except Exception:
            continue
        if (track_type, index, start) in done_spots:
            continue
        if (track_type == "video" and not new_picture) or (track_type == "audio" and not new_sound):
            skipped += 1
            continue
        linked = [l for l in (item.GetLinkedItems() or []) if l is not None] if track_type == "video" else []
        had_sound = any(l.GetTrackTypeAndIndex()[0] == "audio" for l in linked)
        for l in linked:
            l_type, l_index = l.GetTrackTypeAndIndex()
            done_spots.add((l_type, l_index, int(l.GetStart())))
        others = [it for it in (timeline.GetItemListInTrack(track_type, index) or []) if it is not item]
        old_pool = item.GetMediaPoolItem()
        try:
            source_start = int(item.GetSourceStartFrame())
        except Exception:
            source_start = 0
        old_rate = clip_rate(old_pool, fps) if old_pool is not None else fps
        old = {"start": start, "end": end, "source_start": source_start, "rate": old_rate,
               "prev_end": max((int(it.GetEnd()) for it in others if int(it.GetEnd()) <= start), default=None),
               "next_start": min((int(it.GetStart()) for it in others if int(it.GetStart()) >= end), default=None),
               "loudest": _loudest_in(old_pool, fps, source_start) if wants_loudest and old_pool else None}
        at, length, first = swap_plan(opts, old, new_info, fps, whole, new_still, still_frames)
        look = look_of(item) if track_type == "video" and opts.get("swap_look", True) else {}
        colour = item.GetClipColor() if hasattr(item, "GetClipColor") else ""
        media_type = 2 if track_type == "audio" else None if (had_sound and new_sound) else 1
        graded = _grade_holder(timeline, media_pool, item, new, at, length, first, new_still, fps) \
            if track_type == "video" and opts.get("swap_grade") else None
        timeline.DeleteClips([item] + linked)
        track = index  # (run on over the next clip: a track up wherever it would cover something)
        while _busy(timeline, track_type, track, at, at + length) or \
                (media_type is None and _busy(timeline, "audio", track, at, at + length)):
            track += 1
        if track > timeline.GetTrackCount(track_type):
            timeline.AddTrack(track_type)
        info = {"mediaPoolItem": new, "trackIndex": track, "recordFrame": at}
        if media_type:
            info["mediaType"] = media_type
        append_clip(media_pool, new, info, first, max(1, int(round(length * new_info["rate"] / fps))), new_still)
        again = lookup_item(timeline, track_type, track, at)
        if again is None:
            skipped += 1
            _drop_grade_holder(timeline, graded)
            continue
        for key, value in look.items():
            again.SetProperty(key, value)
        if colour:
            again.SetClipColor(colour)
        if graded is not None:
            try:
                graded["item"].CopyGrades([again])
            except Exception as e:
                print(f"[swap] couldn't carry the grade over: {e}")
            _drop_grade_holder(timeline, graded)
        swapped += 1
    return swapped, skipped


def _grade_holder(timeline, media_pool, old, new, at, length, first, still, fps):
    """Keep the colour grade: Resolve copies a grade only between clips on the timeline (CopyGrades), and the
    old one goes before the new one comes - so a stand-in of the new clip goes on a track of its own on top,
    takes the old one's grade, and hands it on (_drop_grade_holder takes it away again)."""
    try:
        timeline.AddTrack("video")
        top = int(timeline.GetTrackCount("video"))
        append_clip(media_pool, new, {"mediaPoolItem": new, "trackIndex": top, "recordFrame": at, "mediaType": 1},
                    first, max(1, int(round(length * clip_rate(new, fps) / fps))), still)
        holder = lookup_item(timeline, "video", top, at)
        if holder is None or not old.CopyGrades([holder]):
            print("[swap] Resolve didn't copy the grade")
        return {"item": holder, "track": top} if holder is not None else None
    except Exception as e:
        print(f"[swap] couldn't keep the grade: {e}")
        return None


def _drop_grade_holder(timeline, graded):
    if graded is None:
        return
    try:
        timeline.DeleteClips([graded["item"]])
        if not (timeline.GetItemListInTrack("video", graded["track"]) or []):
            timeline.DeleteTrack("video", graded["track"])
    except Exception as e:
        print(f"[swap] couldn't take the grade's stand-in away: {e}")


def lookup_item(timeline, track_type, track_index, start_frame):
    """Fetches a fresh TimelineItem reference by track+start position.
    Always use this instead of holding onto an item object across a
    Resolve API call that might invalidate it — confirmed in practice
    that a rejected CreateCompoundClip call leaves the original item
    *objects* still existing in Python but with dead/unreadable state
    (GetName() returning None) even though nothing raised. Re-fetching
    fresh from the timeline avoids relying on those corrupted handles."""
    try:
        for it in timeline.GetItemListInTrack(track_type, track_index):
            if it.GetStart() == start_frame:
                return it
    except Exception:
        pass
    return None


_AUDIO_TRACK_KINDS = {"mono", "stereo", "5.1", "5.1film", "7.1", "7.1film"} | {f"adaptive{n}" for n in range(1, 25)}


def sound_tracks_of(item):
    """(how many audio tracks the clip's sound takes on a timeline, what kind
    they are) - (0, "") for a clip without sound.

    A clip's sound isn't always one track: two channels are often set up as
    two mono tracks (screen recordings, cameras with a separate mic). Resolve
    then wants a free audio track for each of them (see insert_clip_item)."""
    try:
        tracks = json.loads(item.GetAudioMapping() or "{}").get("track_mapping") or {}
        kinds = [str((tracks[k] or {}).get("type") or "").lower() for k in sorted(tracks, key=int)]
        if kinds:
            return len(kinds), kinds[0] if kinds[0] in _AUDIO_TRACK_KINDS else "stereo"
    except Exception:
        pass  # an older Resolve without GetAudioMapping, or a clip it has no answer for
    try:
        has_sound = "audio" in str(item.GetClipProperty("Type") or "").lower()
    except Exception:
        has_sound = False
    return (1, "stereo") if has_sound else (0, "")


def _busy(timeline, track_type, index, start, end):
    """Is there something on this track between start and end? (A track that isn't there is free.)"""
    if index > timeline.GetTrackCount(track_type):
        return False
    return any(start < i.GetEnd() and i.GetStart() < end for i in timeline.GetItemListInTrack(track_type, index) or [])


def _tracks_of(track_type, index, sound_tracks):
    """The tracks a clip on `track_type` `index` takes: its own, and the audio tracks its sound goes on."""
    if track_type == "audio":
        return [("audio", index + n) for n in range(max(1, sound_tracks))]
    return [("video", index)] + [("audio", index + n) for n in range(sound_tracks)]


def room_on(timeline, track_type, index, start, end, sound_tracks, besides=()):
    """Is there room for a clip from start to end on that track (and its sound's)? `besides`: the
    (track type, index, start) of clips not to count - the clip itself and its sound, about to be put back."""
    for kind, at in _tracks_of(track_type, index, sound_tracks):
        if at > timeline.GetTrackCount(kind):
            continue
        for other in timeline.GetItemListInTrack(kind, at) or []:
            if (kind, at, other.GetStart()) not in besides and start < other.GetEnd() and other.GetStart() < end:
                return False
    return True


def lowest_room(timeline, item, track_type, start, end):
    """The lowest track with room for `item` from start to end - its sound's audio tracks free too -
    made when it isn't there yet (an audio one of its sound's kind)."""
    sound_tracks, kind = sound_tracks_of(item)
    index = 1
    while not room_on(timeline, track_type, index, start, end, sound_tracks):
        index += 1
    for what, at in _tracks_of(track_type, index, sound_tracks):
        while timeline.GetTrackCount(what) < at:
            before = timeline.GetTrackCount(what)
            if what == "audio" and kind:
                timeline.AddTrack(what, kind)
            if timeline.GetTrackCount(what) == before:
                timeline.AddTrack(what)
            if timeline.GetTrackCount(what) == before:
                break
    return index


def clip_rate(item, fallback):
    """The clip's own frame rate (its FPS in the Media Pool). AppendToTimeline's startFrame / endFrame -
    and a clip's in / out marks - are counted in THESE frames, not the timeline's (measured in 21.1.1:
    a 24 fps sound asked for frames 0-10 comes out 25 frames long on a 60 fps timeline)."""
    try:
        value = float(item.GetClipProperty("FPS") or 0)
    except (TypeError, ValueError):
        value = 0
    return value if value > 0 else (fallback or 24.0)


def on_timeline(item, clip_frames, fps):
    """How many timeline frames `clip_frames` of the clip's own frames take."""
    rate = clip_rate(item, fps)
    return max(1, int(round(clip_frames * fps / rate))) if fps else clip_frames


def of_clip(item, timeline_frames, fps):
    """...and the other way: how many of the clip's own frames fill `timeline_frames`."""
    rate = clip_rate(item, fps)
    return max(1, int(round(timeline_frames * rate / fps))) if fps else timeline_frames


def append_clip(media_pool, item, info, first, length, still=False):
    """AppendToTimeline for one clip: `length` of its own frames from `first`.

    A still's length (measured in 21.1.1, five stills): startFrame / endFrame are ignored - it gets
    Resolve's Standard still duration - unless its frame rate isn't the timeline's. What every still
    does take is the Media Pool clip's own in / out marks: marked 0-47 it lands 48 of its frames long.
    So a still is marked, appended and given its marks back. (No marks to set - an older Resolve -
    and it's asked the old way: Resolve's own length then.) Returns Resolve's answer."""
    marks = None
    if still:
        try:
            before = item.GetMarkInOut() or {}
            if item.SetMarkInOut(0, max(0, int(length) - 1)):
                marks = before
        except Exception:
            marks = None
    if marks is None:
        info = dict(info, startFrame=first, endFrame=first + length)
    try:
        return media_pool.AppendToTimeline([info])
    finally:
        if marks is not None:
            try:
                item.ClearMarkInOut()
                for kind, mark in marks.items():  # exactly as they were
                    if isinstance(mark, dict) and "in" in mark and "out" in mark:
                        item.SetMarkInOut(mark["in"], mark["out"], kind)
            except Exception as e:
                print(f"[still] couldn't put the marks of '{item.GetName()}' back: {e}")


def insert_clip_item(settings, session, insert_frequency, chosen_item, chosen_folder, name, playhead_frame,
                      duration_override=None, skipped_tracks_out=None, source_range=None):
    """source_range: (first_frame, end_frame) of the clip to use - the in
    and out points marked in the preview - or None for the whole clip."""
    media_pool = session["media_pool"]
    timeline = session["timeline"]

    if settings.general["reveal_in_media_pool"]:
        media_pool.SetCurrentFolder(chosen_folder)
        media_pool.SetSelectedClip(chosen_item)

    try:
        fps = float(timeline.GetSetting("timelineFrameRate"))
    except (TypeError, ValueError):
        fps = None
    duration = duration_override if duration_override is not None else \
        compute_clip_duration(settings, chosen_item, name, fps)
    source_start = 0
    is_still = is_still_image(name, chosen_item.GetClipProperty("Type"))
    # A still is given its length (append_clip marks it): the one asked for, or what a picture lasts.
    sized_still = is_still
    if source_range is not None:
        source_start, source_end = source_range
        duration = max(1, source_end - source_start)
        reach = on_timeline(chosen_item, duration, fps) if fps else duration  # (asked in the clip's frames)
    else:
        if is_still:  # (compute_clip_duration gives a still's length in timeline frames)
            reach = duration
            duration = of_clip(chosen_item, duration, fps) if fps else duration
        else:         # (...and everything else's in the clip's own)
            reach = on_timeline(chosen_item, duration, fps) if fps else duration
    new_start = playhead_frame
    new_end = playhead_frame + reach

    is_audio_only = chosen_item.GetClipProperty("Type") == "Audio"
    # "Insert video only" / "Insert audio only" (Alt+V / Alt+A in the picker)
    media = session.get("insert_media")
    if media == "video" and is_audio_only:
        return (f"'{name}' is a sound - it has no picture to insert on its own", playhead_frame, None, True, None)
    if media == "audio" and not is_audio_only and is_still_image(name, chosen_item.GetClipProperty("Type")):
        return (f"'{name}' is a still - it has no sound", playhead_frame, None, False, None)
    just_audio = is_audio_only or media == "audio"
    track_type = "audio" if just_audio else "video"
    track_count = timeline.GetTrackCount(track_type)

    highest_occupied = 0
    for track_index in range(1, track_count + 1):
        if _busy(timeline, track_type, track_index, new_start, new_end):
            highest_occupied = track_index

    target_track = highest_occupied + 1

    # Where the sound goes (measured in Resolve 21, on a scratch timeline):
    #  - a clip put on track N gets its sound on audio track N - and N+1, N+2 ...
    #    when its sound is several tracks (sound_tracks_of);
    #  - Resolve never adds an audio track for it. If one of those tracks is
    #    taken at that spot, or isn't there at all, AppendToTimeline still says
    #    yes but nothing lands (a sound on its own lands with tracks missing).
    # So: choose a track whose audio tracks are free, and make the ones that
    # aren't there yet. Ten copies of a clip with two-track sound go on V1, V3,
    # V5 ... (A1+A2, A3+A4 ...); the video tracks passed over are removed again
    # after the batch (clean_skipped_tracks) if they're still empty.
    sound_tracks, sound_kind = (0, "") if media == "video" else sound_tracks_of(chosen_item)
    if just_audio:
        sound_tracks = max(1, sound_tracks)
    elif sound_tracks:
        while any(_busy(timeline, "audio", target_track + n, new_start, new_end) for n in range(sound_tracks)):
            target_track += 1

    def note_new(kind, index):  # a track made here: taken away again after the batch if nothing lands on it
        if skipped_tracks_out is not None:
            skipped_tracks_out.append((kind, index))

    def add_track(kind):
        """One more track at the top - an audio one of the kind the clip's sound is. True if it's there now."""
        before = timeline.GetTrackCount(kind)
        if kind == "audio" and sound_kind:
            timeline.AddTrack(kind, sound_kind)
        if timeline.GetTrackCount(kind) == before:
            timeline.AddTrack(kind)
        return timeline.GetTrackCount(kind) > before

    # The lookup below is still the judge of whether it landed; if it didn't,
    # the next track is tried instead of losing the clip.
    max_attempts = 20
    timeline_item = None
    location = None
    for attempt in range(max_attempts):
        attempt_track = target_track + attempt
        while timeline.GetTrackCount(track_type) < attempt_track:
            if not add_track(track_type):
                break
            if timeline.GetTrackCount(track_type) < attempt_track:
                note_new(track_type, timeline.GetTrackCount(track_type))  # one passed over on the way up
        while sound_tracks and timeline.GetTrackCount("audio") < attempt_track + sound_tracks - 1:
            if not add_track("audio"):
                break
            note_new("audio", timeline.GetTrackCount("audio"))

        clip_info = {"mediaPoolItem": chosen_item, "trackIndex": attempt_track, "recordFrame": playhead_frame}
        if just_audio:
            clip_info["mediaType"] = 2
        elif media == "video":
            clip_info["mediaType"] = 1
        # mediaType is otherwise deliberately omitted — setting it to 1
        # ("video") explicitly forces video-only insertion even for clips
        # that have their own linked audio, silently dropping the audio.
        # Leaving it unset inserts the full clip.

        inserted = append_clip(media_pool, chosen_item, clip_info, source_start, duration, sized_still)
        if inserted:
            # Don't trust the return value as a usable TimelineItem
            # directly — its shape isn't consistent across Resolve
            # versions, and (per above) it can also just be wrong about
            # whether anything landed at all. Verify by looking the item
            # up by track + start position instead.
            location = (track_type, attempt_track, playhead_frame)
            timeline_item = lookup_item(timeline, *location)

        if timeline_item is not None:
            target_track = attempt_track
            break

        note_new(track_type, attempt_track)
        if not just_audio and media != "video":
            sound_tracks = max(sound_tracks, 2)  # its sound needs more room than Resolve said: make sure of two tracks
        print(f"[stack] '{name}' onto {track_type} track {attempt_track} didn't actually land "
              f"(no free audio track for its sound there?) — trying track {attempt_track + 1}.")
    if timeline_item is None:
        return (f"Insert failed for '{name}' — tried {max_attempts} tracks, none of them worked",
                playhead_frame, None, is_audio_only, None)
    if timeline_item is not None:
        # Use the item's REAL resulting end position for cursor math
        # rather than trusting the duration we requested — confirmed for
        # stills that Resolve can silently use its own length regardless
        # of what we ask for, and there's evidence (gaps appearing in
        # sequential/Ctrl+Enter inserts) this can happen for other clip
        # types too. Reading back the true position fixes the gap
        # regardless of why the mismatch happens for any given clip.
        try:
            actual_end = timeline_item.GetEnd()
            if actual_end and actual_end != new_end:
                print(f"[length] '{name}': requested end {new_end} but actual end is {actual_end} "
                      f"— using the real value for cursor placement.")
                new_end = actual_end
        except Exception as e:
            print(f"[length] '{name}': couldn't read back actual end position: {e}")

        # Picture and sound linked: Resolve does that itself on a normal insert
        # (seen in 21). Only when it hasn't, link them here - and then only
        # with this clip's own sound, on the audio tracks it went to. (Linking
        # with every same-named sound at that spot took the sound away from
        # the copies put there before: ten copies, nine of them unlinked.)
        if not just_audio and media != "video" and settings.general.get("link_video_audio_on_insert", True):
            try:
                already = timeline_item.GetLinkedItems() or []
            except Exception:
                already = []
            if not already and sound_tracks:
                try:
                    own_sound = []
                    last = min(timeline.GetTrackCount("audio"), target_track + sound_tracks - 1)
                    for a_idx in range(target_track, last + 1):
                        for it in timeline.GetItemListInTrack("audio", a_idx) or []:
                            try:
                                if it.GetStart() == playhead_frame and it.GetName() == name:
                                    own_sound.append(it)
                            except Exception:
                                continue
                    if own_sound:
                        ok = timeline.SetClipsLinked([timeline_item] + own_sound, True)
                        print(f"[link] '{name}': linked the picture with its {len(own_sound)} sound item(s) -> {ok}")
                except Exception as e:
                    print(f"[link] '{name}': couldn't link picture and sound: {e}")

    record_insert(settings, insert_frequency, name)
    record_recent(name)
    from . import stats
    stats.record("insert")
    only = {"audio": " (just its sound)", "video": " (just the picture)"}.get(media, "") if not is_audio_only else ""
    return f"Inserted '{name}'{only} from [{chosen_folder.GetName()}] on {track_type[0].upper()}{target_track}", \
        new_end, timeline_item, just_audio, location


CLIP_TYPE_LABELS = {
    "none": "None", "compound": "Compound Clip", "fusion": "Fusion Clip",
    "vfx_connect": "VFX Connect Clip",
}


def convert_clips(timeline, timeline_items, clip_type, name=None):
    """Wraps the given TimelineItems into one Compound/Fusion/VFX Connect
    clip. Returns the new TimelineItem on success, or None. CreateCompoundClip
    and CreateFusionClip are documented Resolve scripting API methods.
    CreateVFXConnectClip is NOT in Resolve's published public scripting
    API as of this writing — VFX Connect is a newer feature and this call
    may simply not exist on your Resolve version. If it fails, that's
    expected until/unless Resolve exposes it; everything else in this
    function is on solid ground."""
    timeline_items = [t for t in timeline_items if t is not None]
    if clip_type == "none":
        return None
    if not timeline_items:
        print(f"[convert] no valid placed items to wrap into a {CLIP_TYPE_LABELS.get(clip_type, clip_type)} "
              f"— nothing to convert.")
        return None
    if name and clip_type == "compound":
        print(f"[convert] named '{name}'")
    print(f"[convert] calling Create{clip_type.capitalize()}Clip-equivalent with "
          f"{len(timeline_items)} item(s): {[getattr(i, 'GetName', lambda: i)() for i in timeline_items]}")
    try:
        if clip_type == "compound":
            result = timeline.CreateCompoundClip(timeline_items, {"name": name} if name else {})
        elif clip_type == "fusion":
            result = timeline.CreateFusionClip(timeline_items)
        elif clip_type == "vfx_connect":
            result = timeline.CreateVFXConnectClip(timeline_items)
        else:
            return None
        if not result:
            print(f"[convert] call completed but returned a falsy result ({result!r}) — Resolve likely "
                  f"rejected the conversion (e.g. the selected items aren't all a valid/contiguous "
                  f"combination for this operation).")
            return None
        print(f"[convert] success — new clip: '{getattr(result, 'GetName', lambda: result)()}'")
        return result
    except AttributeError as e:
        print(f"This Resolve version's scripting API doesn't expose clip conversion to '{clip_type}': {e}")
        return None
    except Exception as e:
        print(f"Couldn't create {CLIP_TYPE_LABELS.get(clip_type, clip_type)}: {e}")
        return None


def delete_original_clips(timeline, original_items, new_item):
    """CreateCompoundClip/CreateFusionClip do NOT remove the pre-conversion
    clips from their original tracks — they have to be deleted explicitly,
    or clean_empty_tracks will never find those tracks empty. Matched by
    name (not object identity) since that's what survives round-tripping
    through the scripting API reliably."""
    try:
        new_name = new_item.GetName()
    except Exception as e:
        new_name = None
        print(f"[convert] couldn't read the new clip's name: {e}")

    to_delete = []
    for item in original_items:
        if item is None:
            continue
        try:
            if item.GetName() == new_name:
                continue  # this is the new clip itself, not an original
        except Exception:
            pass
        to_delete.append(item)

    print(f"[convert] deleting {len(to_delete)} original clip(s) left behind after conversion "
          f"(new clip: '{new_name}')")
    if not to_delete:
        return
    try:
        ok = timeline.DeleteClips(to_delete, False)
        print(f"[convert] DeleteClips -> {ok}")
    except Exception as e:
        print(f"Couldn't remove original clips after conversion: {e}")


def clean_skipped_tracks(timeline, skipped_tracks):
    """Removes only the specific tracks a batch's retry mechanism skipped
    over (see insert_clip_item's skipped_tracks_out) and that are still
    empty once the whole batch is done — e.g. a video track passed over
    because an earlier clip's linked audio collided there. Deliberately
    narrower than clean_empty_tracks: never touches a pre-existing empty
    track that isn't ours to clean up. Never removes the last track of a
    type. Processes highest index first per type so a deletion never
    shifts the index of one still waiting to be checked."""
    if not skipped_tracks:
        return
    by_type = {}
    for track_type, index in skipped_tracks:
        by_type.setdefault(track_type, set()).add(index)
    for track_type, indices in by_type.items():
        for index in sorted(indices, reverse=True):
            if timeline.GetTrackCount(track_type) <= 1:
                continue
            try:
                items = timeline.GetItemListInTrack(track_type, index)
            except Exception:
                continue
            if items:
                continue  # something else landed here later in the batch — leave it alone
            try:
                ok = timeline.DeleteTrack(track_type, index)
                print(f"[stack] cleaned up empty {track_type} track {index} left over from a skipped collision -> {ok}")
            except Exception as e:
                print(f"[stack] couldn't clean up skipped {track_type} track {index}: {e}")


def clean_empty_tracks(timeline):
    """Removes every completely empty video/audio track (never the last one of a kind). Every track is read
    first and the empty ones then go one straight after another, from the top down (so removing one never
    shifts one still to go) - Resolve's scripting can only remove one track per call (DeleteTrack), so
    nothing else is asked of it in between: reading and deleting in turn made the tracks visibly go one by
    one. (Resolve's own Delete Empty Tracks does it in one step; a script can't call it.)"""
    empty = {}
    for track_type in ("video", "audio"):
        count = int(timeline.GetTrackCount(track_type))
        found = []
        for index in range(count, 0, -1):
            try:
                if not (timeline.GetItemListInTrack(track_type, index) or []):
                    found.append(index)
            except Exception as e:
                print(f"[cleanup] {track_type} {index}: couldn't read contents: {e}")
        empty[track_type] = found[:count - 1] if len(found) == count else found  # (one is always kept)
    for track_type, indices in empty.items():
        for index in indices:
            try:
                timeline.DeleteTrack(track_type, index)
            except Exception as e:
                print(f"Couldn't remove empty {track_type} track {index}: {e}")
    print(f"[cleanup] removed empty tracks: video {empty['video'] or '-'}, audio {empty['audio'] or '-'}")


def remove_inserted(timeline, locations, items, tracks_before, label):
    """Deletes what one Clipse action put on the timeline: the
    clips at `locations` (track type, track, start), their linked audio,
    and `items`; then the tracks it added, if they're empty again."""
    targets = list(items)
    for location in locations:
        item = lookup_item(timeline, *location)
        if item is None:
            continue
        targets.append(item)
        linked = []
        try:
            linked = list(item.GetLinkedItems() or [])
        except Exception:
            pass
        if not linked and location[0] == "video":  # find its own audio: same start, same name
            try:
                name = item.GetName()
                for index in range(1, timeline.GetTrackCount("audio") + 1):
                    for other in timeline.GetItemListInTrack("audio", index) or []:
                        if other.GetStart() == location[2] and other.GetName() == name:
                            linked.append(other)
            except Exception:
                pass
        targets.extend(linked)
    if not targets:
        return "Nothing to undo - the clips are already gone."
    try:
        ok = timeline.DeleteClips(targets, False)
    except Exception as e:
        return f"Couldn't undo: {e}"
    if tracks_before:  # remove tracks the action added, if they're empty now
        for track_type, before in zip(("video", "audio"), tracks_before):
            try:
                count = timeline.GetTrackCount(track_type)
                while count > max(1, before) and not timeline.GetItemListInTrack(track_type, count):
                    timeline.DeleteTrack(track_type, count)
                    count -= 1
            except Exception:
                pass
    return f"Undid {label}." if ok else f"Resolve didn't remove the clips from {label}."


def nudge_timeline_ui_refresh(timeline):
    """Best-effort attempt to get Resolve's timeline track-header panel to
    repaint after scripted DeleteTrack calls — it can visually go stale
    (ghost/duplicate track labels) even though the underlying track list
    is actually correct. Re-setting the current timecode to itself is a
    harmless no-op if this doesn't actually help; there's no documented
    scripting API for "force UI refresh". If this doesn't fix it for you,
    it's likely just a Resolve redraw quirk — clicking elsewhere in
    Resolve or switching pages (Edit -> Color -> Edit) usually clears it."""
    try:
        tc = timeline.GetCurrentTimecode()
        timeline.SetCurrentTimecode(tc)
    except Exception:
        pass
