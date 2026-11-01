"""Where Clipse keeps its files: each system's own places, as its other apps do.

             settings (yours)                       data (yours)            cache (made again)          logs
  Linux      ~/.config/clipse                       ~/.local/share/clipse   ~/.cache/clipse             ~/.local/state/clipse
  Mac        ~/Library/Application Support/Clipse   (the same)              ~/Library/Caches/Clipse     ~/Library/Logs/Clipse
  Windows    %APPDATA%\\Clipse                       (the same)              %LOCALAPPDATA%\\Clipse\\Cache  %LOCALAPPDATA%\\Clipse\\Logs

Linux follows the XDG folders (XDG_CONFIG_HOME ... when they're set), as Vicinae does. Settings are what you chose
(settings.json, favourites, project templates); data is what the app keeps for you (history, what it
learned); the cache can be thrown away and is made again; logs and the service's small marks (its PID ...) are in
logs. Files are written whole or not at all (`write_json`): a crash in the middle of a save leaves the old file.

Until 1.0.x everything was in ~/.clipse; `move_old` takes it over once. Frame grabs made there stay (projects link
to them), and so does ~/.clipse/app on a computer the testing zip's installers set up (a program, not settings).
Stdlib only: the client uses it too.
"""
import json
import os
import shutil
import sys
import tempfile

NAME = "clipse"
TITLE = "Clipse"  # (Mac and Windows folders are named as the app is)


def _home():
    return os.path.expanduser("~")


def _xdg(variable, fallback):
    value = os.environ.get(variable, "")
    return value if os.path.isabs(value) else os.path.join(_home(), fallback)


def _windows(variable, fallback):
    return os.environ.get(variable) or os.path.join(_home(), "AppData", fallback)


if sys.platform == "darwin":
    _support = os.path.join(_home(), "Library", "Application Support", TITLE)
    CONFIG_DIR = DATA_DIR = _support
    CACHE_DIR = os.path.join(_home(), "Library", "Caches", TITLE)
    LOG_DIR = os.path.join(_home(), "Library", "Logs", TITLE)
elif sys.platform == "win32":
    CONFIG_DIR = DATA_DIR = os.path.join(_windows("APPDATA", "Roaming"), TITLE)
    _local = os.path.join(_windows("LOCALAPPDATA", "Local"), TITLE)
    CACHE_DIR = os.path.join(_local, "Cache")
    LOG_DIR = os.path.join(_local, "Logs")
else:
    CONFIG_DIR = os.path.join(_xdg("XDG_CONFIG_HOME", ".config"), NAME)
    DATA_DIR = os.path.join(_xdg("XDG_DATA_HOME", os.path.join(".local", "share")), NAME)
    CACHE_DIR = os.path.join(_xdg("XDG_CACHE_HOME", ".cache"), NAME)
    LOG_DIR = os.path.join(_xdg("XDG_STATE_HOME", os.path.join(".local", "state")), NAME)


def config(*parts):
    return os.path.join(CONFIG_DIR, *parts)


def data(*parts):
    return os.path.join(DATA_DIR, *parts)


def cache(*parts):
    return os.path.join(CACHE_DIR, *parts)


def log(*parts):
    return os.path.join(LOG_DIR, *parts)


SETTINGS_FILE = config("settings.json")


# -- writing safely --
def write_text(path, text):
    """The whole file or none of it: written beside it, flushed to the disk, then swapped in. A crash, a full disk
    or the power going in the middle leaves the file as it was - written straight over, it was left empty or cut
    short, read as no file, and the next save put the defaults in its place."""
    folder = os.path.dirname(path)
    os.makedirs(folder, exist_ok=True)
    handle, tmp = tempfile.mkstemp(prefix="." + os.path.basename(path) + ".", suffix=".tmp", dir=folder)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        for attempt in range(20):
            try:
                os.replace(tmp, path)
                break
            except PermissionError:  # (Windows: someone has it open for a moment - Resolve's step script reading it)
                if sys.platform != "win32" or attempt == 19:
                    raise
                import time
                time.sleep(0.05)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def write_json(path, value, **dump_args):
    write_text(path, json.dumps(value, **dump_args))


def read_json(path, default=None):
    """What the file holds, or `default` when there's none. A file that can't be read as JSON is kept aside
    (name.broken.json) rather than written over with the defaults - it can still be looked at."""
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default
    except (ValueError, UnicodeDecodeError):
        root, ext = os.path.splitext(path)
        try:
            os.replace(path, root + ".broken" + ext)
            print(f"[paths] {os.path.basename(path)} couldn't be read - kept as {os.path.basename(root)}.broken{ext}",
                  flush=True)
        except OSError:
            pass
        return default
    except OSError:
        return default


# -- from ~/.clipse (until 1.0.x) --
OLD_DIR = os.path.join(_home(), ".clipse")
_OLD = {  # name there -> where it goes
    "settings.json": config, "favorites.json": config, "templates": config, "test_updates": config,
    "history.json": data, "picks.json": data, "recent.json": data,
    "search_history.json": data, "insert_frequency.json": data, "stats.json": data,
    "sound_analysis.json": cache, "subtitles": cache, "library.drb": cache,
    "update_check.json": cache,
    "service.log": log, "service.previous.log": log, "watcher.log": log, "update.log": log,
    "daemon.pid": log, "crashed": log, "install_note": log,
}
_GONE = ("heartbeat", "starting", "insert_log.json", "extended_options.json")  # (nothing reads them any more)


def move_old():
    """Takes ~/.clipse's files to their places, once (every part of the app calls it as it starts: whichever comes
    first). A file already in the new place is left as it is. Safe when two start at the same moment."""
    if not os.path.isdir(OLD_DIR):
        return
    moves = [(os.path.join(OLD_DIR, name), where(name)) for name, where in _OLD.items()]
    old_cache = os.path.join(OLD_DIR, "cache")
    try:  # (the Media Pool's, one a project, and Fusion's node list)
        moves += [(os.path.join(old_cache, name),
                   cache(name) if name == "fusion_tools.json" else cache("projects", name))
                  for name in os.listdir(old_cache)]
    except OSError:
        pass
    for source, target in moves:
        if not os.path.exists(source) or os.path.exists(target):
            continue
        try:
            os.makedirs(os.path.dirname(target.rstrip(os.sep)) or ".", exist_ok=True)
            os.replace(source, target)
        except OSError:
            try:
                shutil.move(source, target)  # (another drive)
            except (OSError, shutil.Error):
                pass
    for name in _GONE:
        try:
            os.remove(os.path.join(OLD_DIR, name))
        except OSError:
            pass
    for folder in (old_cache, OLD_DIR):
        try:
            os.rmdir(folder)  # (only when nothing is left - frame grabs and the testing install stay)
        except OSError:
            pass
