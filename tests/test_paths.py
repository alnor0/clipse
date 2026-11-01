"""Where the files go (clipse/paths.py): each system's own folders, ~/.clipse moved over once, files written whole.
Run: python3 tests/test_paths.py"""
import json
import os
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
home = tempfile.mkdtemp()
os.environ["HOME"] = os.environ["USERPROFILE"] = home  # (Windows' ~ is USERPROFILE)
for name in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME", "APPDATA", "LOCALAPPDATA"):
    os.environ.pop(name, None)
sys.path.insert(0, str(ROOT))

failed = []


def check(what, ok):
    print(("ok   " if ok else "FAIL ") + what)
    if not ok:
        failed.append(what)


# ~/.clipse as 1.0.0 left it
old = os.path.join(home, ".clipse")
for name, text in {"settings.json": '{"general": {}}', "favorites.json": '["a"]', "recent.json": "{}",
                   "history.json": "[]", "service.log": "log", "daemon.pid": "1", "heartbeat": "",
                   "cache/My_Project.json": "{}", "cache/fusion_tools.json": "[]",
                   "templates/Mine.json": "{}", "frame-grabs/grab.png": "png", "app/bin/python": ""}.items():
    path = os.path.join(old, name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    pathlib.Path(path).write_text(text)
from clipse import paths  # noqa: E402

os.makedirs(paths.CONFIG_DIR)  # (a favourites file already in the new place - ~/.config/clipse, Windows' AppData ...)
pathlib.Path(paths.config("favorites.json")).write_text('["newer"]')

if sys.platform.startswith("linux"):
    check("Linux: the XDG folders", (paths.CONFIG_DIR, paths.DATA_DIR, paths.CACHE_DIR, paths.LOG_DIR) == (
        f"{home}/.config/clipse", f"{home}/.local/share/clipse", f"{home}/.cache/clipse", f"{home}/.local/state/clipse"))
paths.move_old()
paths.move_old()  # (twice: nothing more happens)
check("settings, templates -> the settings folder",
      os.path.isfile(paths.config("settings.json")) and os.path.isfile(paths.config("templates", "Mine.json")))
check("a file already in the new place is left as it is",
      json.load(open(paths.config("favorites.json"))) == ["newer"])
check("recent, history -> data; logs and the PID -> logs",
      os.path.isfile(paths.data("recent.json")) and os.path.isfile(paths.data("history.json"))
      and os.path.isfile(paths.log("service.log")) and os.path.isfile(paths.log("daemon.pid")))
check("a project's Media Pool list -> cache/projects, Fusion's node list -> cache",
      os.path.isfile(paths.cache("projects", "My_Project.json")) and os.path.isfile(paths.cache("fusion_tools.json")))
check("frame grabs and the testing install stay in ~/.clipse (projects link to the grabs)",
      os.path.isfile(os.path.join(old, "frame-grabs", "grab.png")) and os.path.isdir(os.path.join(old, "app")))
check("what nothing reads any more goes", not os.path.exists(os.path.join(old, "heartbeat")))
check("ones of the old place nobody takes stay (the favourites that were older)",
      os.path.isfile(os.path.join(old, "favorites.json")))

# written whole or not at all
target = paths.data("thing.json")
paths.write_json(target, {"a": 1})


class Boom:
    pass


try:
    paths.write_json(target, {"a": Boom()})  # (fails half-way through)
except TypeError:
    pass
check("a save that fails half-way leaves the file as it was", json.load(open(target)) == {"a": 1})
_beside = set(os.listdir(paths.DATA_DIR)) - ({"settings.json", "favorites.json", "templates"} if paths.DATA_DIR == paths.CONFIG_DIR else set())  # (one folder on Windows)
check("and leaves nothing beside it", sorted(_beside) == ["history.json", "recent.json", "thing.json"])

pathlib.Path(target).write_text('{"a": 1, "cut sho')
check("a broken file reads as the default", paths.read_json(target, "default") == "default")
check("... and is kept aside, not written over",
      not os.path.exists(target) and os.path.isfile(paths.data("thing.broken.json")))

# settings: a broken file is never replaced by the defaults
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from clipse import settings as settings_module  # noqa: E402
pathlib.Path(paths.SETTINGS_FILE).write_text('{"general": {"empty_ord')
s = settings_module.Settings()
s.load()
check("settings that can't be read are kept as settings.broken.json",
      os.path.isfile(paths.config("settings.broken.json")))
s.save()
check("saved settings say their layout", json.load(open(paths.SETTINGS_FILE)).get("format") == settings_module.FORMAT)

# Resolve's step scripts read the settings from where they are now
from clipse import resolve_shortcuts as rs  # noqa: E402
lua = rs.launcher_text(b"STEP:forward", [])
check("the step script reads settings.json from its new place",
      paths.SETTINGS_FILE in lua and ".clipse" not in lua)

print("\nall good" if not failed else f"\n{len(failed)} failed")
sys.exit(1 if failed else 0)
