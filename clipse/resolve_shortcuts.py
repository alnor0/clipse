"""Shortcuts inside DaVinci Resolve itself.

Writes one tiny launcher script per action into Resolve's Scripts/Utility
folder. Resolve lists Utility scripts under Workspace -> Scripts on EVERY
page (Edit scripts only show on the Edit page, which is why the shortcuts
didn't work on the Fusion page), and Keyboard Customization can bind a key
to each one — no AutoHotkey / Hammerspoon / window-manager
config needed, the same on Windows, macOS and Linux.

Each launcher (Lua: Resolve always has it - Python only where it's installed) sends its message straight to the
background service (the fast path - no client process involved). If the service isn't running, it starts the client
instead, which starts the service and then delivers the command (see client.auto_start_and_send).

Run via:  clipse --install-resolve-shortcuts
          clipse --uninstall-resolve-shortcuts
"""
import os
import re

from .scripts_fusion import default_scripts_folder

LAUNCHER_PREFIX = "Clipse "  # then the script's number and name: "Clipse 01 - Swap Clip" (or "Clipse - Open")
OLD_PREFIXES = ("davinci-search - ", "DaVinci Clipse - ")  # (the names before, 2026-10-18: those are taken out)
_OURS = re.compile(r"Clipse (\d\d - |- )")  # (ours: numbered, or as they were named until 2026-10-19 - those go)

# (menu name, message sent to the service or None, client arguments) - each with its number in MENU_NUMBERS.
# Resolve keeps a key by the script's PLACE in its Scripts menu, not its name (configs/keyboard.preset.xml:
# workspace_sub1_menu1, _menu2 ...), and sorts the menu by name: a script added, taken out or renamed in the middle
# moved every key after it onto the wrong script (2026-10-19). So the extra ones are numbered - "Clipse 01 - Swap
# Clip" - after the three that aren't: Open (the one to use), Quit and Restart, which sort first ("-" before a
# digit). A number, once given, never changes or comes free again: a new script takes the next one and sorts last,
# and nobody's keys move. Never another one without a number. Taking one out would still move every one after it:
# a script that's no longer wanted stays in the menu - unless it's last (17 Next Keyframe and 18 Previous Keyframe
# went, 2026-10-21: Resolve's own keys do the same). The names are what you search for in Keyboard Customization.
ACTIONS = [
    ("Open", b"TRIGGER", []),  # (it was "Search": the one to use, 2026-10-19)
    ("Swap Clip", b"SWAP:clip", ["swap", "clip"]),
    ("Undo Last Action", b"UNDO:last", ["undo", "last"]),
    ("Grab Frame", b"GRAB:frame", ["grab", "frame"]),
    ("Next Use of Clip", b"JUMP:next", ["jump", "next"]),
    ("Previous Use of Clip", b"JUMP:previous", ["jump", "previous"]),
    ("Adjustment Clip Over Clip", b"ADJ:match", ["adjust", "match"]),
    ("Adjustment Clip Over Footage", b"ADJ:match-skip-adj", ["adjust", "match-skip-adj"]),
    ("Adjustment Clip at Playhead", b"ADJ:fixed", ["adjust", "fixed"]),
    ("Fusion Composition Over Clip", b"COMP:match", ["comp", "match"]),
    ("Fusion Composition Over Footage", b"COMP:match-skip-adj", ["comp", "match-skip-adj"]),
    ("Fusion Composition at Playhead", b"COMP:fixed", ["comp", "fixed"]),
    ("Tidy Fusion Nodes", b"FUSION:tidy", ["fusion", "tidy"]),
    ("Pull Out Fusion Node", b"FUSION:pullout", ["fusion", "pullout"]),
    ("Copy Node Name", b"FUSION:copyname", ["fusion", "copyname"]),
    ("Fusion Node Off - On", b"FUSION:nodeonoff", ["fusion", "nodeonoff"]),
    ("Fusion Before - After", b"FUSION:beforeafter", ["fusion", "beforeafter"]),
    ("Step Back", b"STEP:back", ["step", "back"]),
    ("Step Forward", b"STEP:forward", ["step", "forward"]),
    ("Record Voiceover", b"VOICE:record", ["voice", "record"]),  # (2026-10-27)
    ("Organise Project", b"ORGANISE:project", ["organise", "project"]),  # (2026-10-30)
    ("Stretch Marker to Clips", b"MARKER:fit", ["marker", "fit"]),  # (2026-10-30: his Shift+C - markers.py)
    ("Add Marker", b"MARKER:add", ["marker", "add"]),  # (his C: a marker, and its note window at once)
    ("Hide - Show Markers", b"MARKER:toggle", ["marker", "toggle"]),
    ("Quit", None, ["--stop"]),  # (until it's wanted again: a key here, or Resolve opened again)
    ("Restart", None, ["--restart", "--refresh"]),  # (the picker opens again once it's up)
]
UNNUMBERED = ("Open", "Quit", "Restart")  # first in the menu, in this (alphabetical) order
MENU_NUMBERS = {  # never change one; a new script gets the next number (21 ... - RETIRED_NUMBERS aren't given again)
    "Swap Clip": 1, "Undo Last Action": 2, "Grab Frame": 3, "Next Use of Clip": 4, "Previous Use of Clip": 5,
    "Adjustment Clip Over Clip": 6, "Adjustment Clip Over Footage": 7, "Adjustment Clip at Playhead": 8,
    "Fusion Composition Over Clip": 9, "Fusion Composition Over Footage": 10, "Fusion Composition at Playhead": 11,
    "Tidy Fusion Nodes": 12, "Pull Out Fusion Node": 13, "Copy Node Name": 14, "Fusion Node Off - On": 15,
    "Fusion Before - After": 16, "Step Back": 19, "Step Forward": 20,  # (swapped 2026-10-21 - back first, as everywhere)
    "Record Voiceover": 21, "Organise Project": 22, "Stretch Marker to Clips": 23,
    "Add Marker": 25, "Hide - Show Markers": 26,
}
RETIRED_NUMBERS = {17: "Next Keyframe", 18: "Previous Keyframe"}  # (taken out 2026-10-21 - never given again)
# A script taken out of the MIDDLE of the menu keeps its place with a stand-in (2026-10-21, the owner: "Ok do that"):
# the file stays, so every script after it keeps its place - and its key; pressed, it says it's gone. {number: name}.
# (17 and 18 have none: they went from the end, before a release - nobody had a key on them.)
STAND_INS = {24: "Edit Marker"}  # (2026-10-30, the owner: "Remove this one" - C opens a marker already there)


def menu_name(name):
    """The script's name in Resolve's menu and Keyboard Customization: "Clipse - Open", "Clipse 01 - Swap Clip"."""
    if name in UNNUMBERED:
        return f"{LAUNCHER_PREFIX}- {name}"
    return f"{LAUNCHER_PREFIX}{MENU_NUMBERS[name]:02d} - {name}"


def is_ours(file_name):
    """One of the app's own scripts in Resolve's menu (by its file name), or one under a name it had before."""
    return bool(_OURS.match(file_name)) or file_name.startswith(OLD_PREFIXES)


LAUNCHER_MARK = "-- Clipse launcher"  # (the first line of every one: a .lua named "Clipse - ..." without it isn't ours)

# Lua, not Python (2026-10-21): Resolve runs a .py from its Scripts menu only where Python is installed for everyone -
# a user's Mac or Windows usually has none, and every "Clipse - ..." in the menu did nothing there. Lua is Resolve's
# own (LuaJIT, with its ffi): the message goes to the service through the system's own socket calls, as the .py did.
_TEMPLATE = """\
-- Clipse launcher - created by `clipse --install-resolve-shortcuts`.
-- Give it a key in DaVinci Resolve -> Keyboard Customization (search "Clipse").
local MESSAGE = __MESSAGE__
local COMMAND = __COMMAND__  -- used when the background service isn't running yet
local PORT = 51823

local ffi = require("ffi")
local windows = ffi.os == "Windows"

local function declare(text)  -- (Resolve may run this again in the same Lua: declared once is enough)
  pcall(ffi.cdef, text)
end

local function address()  -- 127.0.0.1:PORT as the system wants it (macOS's starts with its length)
  local hi, lo = math.floor(PORT / 256), PORT % 256
  local first = ffi.os == "OSX" and {16, 2} or {2, 0}
  return ffi.new("uint8_t[16]", {first[1], first[2], hi, lo, 127, 0, 0, 1}), 16
end

local function send(message)  -- true when the service has it
  local addr, size = address()
  if windows then
    declare[[
      int WSAStartup(uint16_t version, void *data);
      uintptr_t socket(int af, int type, int protocol);
      int connect(uintptr_t s, const void *name, int size);
      int send(uintptr_t s, const char *data, int size, int flags);
      int closesocket(uintptr_t s);
      int AllowSetForegroundWindow(uint32_t pid);
    ]]
    -- Resolve is the active app, so it may hand focus on to the picker - without this, Windows keeps typing in Resolve
    pcall(function() ffi.C.AllowSetForegroundWindow(0xFFFFFFFF) end)
    local ws = ffi.load("ws2_32")
    ws.WSAStartup(0x0202, ffi.new("uint8_t[1024]"))
    local s = ws.socket(2, 1, 6)
    if s == ffi.cast("uintptr_t", -1) then return false end
    local ok = ws.connect(s, addr, size) == 0 and ws.send(s, message, #message, 0) == #message
    ws.closesocket(s)
    return ok
  end
  declare[[
    int socket(int domain, int type, int protocol);
    int connect(int fd, const void *addr, unsigned int size);
    long send(int fd, const void *data, unsigned long size, int flags);
    int setsockopt(int fd, int level, int name, const void *value, unsigned int size);
    int close(int fd);
  ]]
  local fd = ffi.C.socket(2, 1, 0)
  if fd < 0 then return false end
  -- a service that goes away mid-send mustn't take Resolve with it (SIGPIPE): no signal for this socket
  local flags = 0
  if ffi.os == "OSX" then
    ffi.C.setsockopt(fd, 0xffff, 0x1022, ffi.new("int[1]", 1), 4)  -- SOL_SOCKET, SO_NOSIGPIPE
  else
    flags = 0x4000  -- MSG_NOSIGNAL
  end
  local ok = ffi.C.connect(fd, addr, size) == 0 and tonumber(ffi.C.send(fd, message, #message, flags)) == #message
  ffi.C.close(fd)
  return ok
end

local function start()  -- the client: it starts the service, then delivers the command
  if windows then
    declare[[
      typedef struct { uint32_t cb; void *a, *b, *c; uint32_t d[8]; uint16_t e, f; void *g, *h, *i, *j; } ClipseStartup;
      typedef struct { void *process, *thread; uint32_t pid, tid; } ClipseProcess;
      int MultiByteToWideChar(unsigned int page, uint32_t flags, const char *text, int size, uint16_t *wide, int count);
      int CreateProcessW(const uint16_t *app, uint16_t *line, void *pa, void *ta, int inherit, uint32_t flags,
                         void *env, const uint16_t *cwd, ClipseStartup *si, ClipseProcess *pi);
      int CloseHandle(void *handle);
    ]]
    local parts = {}
    for i, arg in ipairs(COMMAND) do parts[i] = '"' .. arg .. '"' end
    local line = table.concat(parts, " ")
    local n = ffi.C.MultiByteToWideChar(65001, 0, line, -1, nil, 0)
    local wide = ffi.new("uint16_t[?]", n)
    ffi.C.MultiByteToWideChar(65001, 0, line, -1, wide, n)
    local si, pi = ffi.new("ClipseStartup"), ffi.new("ClipseProcess")
    si.cb = ffi.sizeof(si)
    if ffi.C.CreateProcessW(nil, wide, nil, nil, 0, 0x00000008, nil, nil, si, pi) ~= 0 then  -- DETACHED_PROCESS: no console
      ffi.C.CloseHandle(pi.process)
      ffi.C.CloseHandle(pi.thread)
    end
    return
  end
  local parts = {}
  for i, arg in ipairs(COMMAND) do parts[i] = "'" .. (arg:gsub("'", "'\\\\''")) .. "'" end
  os.execute(table.concat(parts, " ") .. " >/dev/null 2>&1 &")
end

__HERE__
local sent = false
if MESSAGE then
  local ok, answer = pcall(send, MESSAGE)
  sent = ok and answer
end
if not sent and #COMMAND > 0 then
  start()
end
"""


def _lua_string(text):
    """`text` as a Lua string literal that needs no escaping (a long bracket of a level it doesn't contain)."""
    level = 0
    while f"]{'=' * level}]" in text:
        level += 1
    return f"[{'=' * level}[{text}]{'=' * level}]"


# Step Forward / Step Back move the playhead themselves, inside Resolve (2026-10-21: through the service, pressed
# quickly, "not that fast and a little laggy"): no message, no Python, Resolve's own calls. How far: Settings >
# Scripts' Step back / Step forward, read from settings.json at every press (5 until it's changed). Only when it can't (no
# timeline ...) does the message go to the service, which says why on screen.
_STEP_HERE = r"""
local function step_frames()  -- this direction's own (Settings > Scripts: Step back / Step forward)
  local f = io.open(SETTINGS, "r")
  if not f then return 5 end
  local text = f:read("*a")
  f:close()
  local key = STEP > 0 and "step_forward_frames" or "step_back_frames"
  local n = tonumber(text:match('"' .. key .. '"%s*:%s*(%d+)'))
  return (n and n > 0) and n or 5
end

local function drop_of(fps)  -- 29.97 / 59.94 drop-frame: 2 / 4 frame numbers skipped a minute
  return math.floor(fps + 0.5) == 60 and 4 or 2
end

local function frames_of(tc, fps)
  local h, m, s, sep, f = tc:match("(%d+):(%d+):(%d+)([:;])(%d+)")
  if not h then return nil end
  h, m, s, f = tonumber(h), tonumber(m), tonumber(s), tonumber(f)
  local n = (h * 3600 + m * 60 + s) * math.floor(fps + 0.5) + f
  if sep == ";" then
    local minutes = h * 60 + m
    n = n - drop_of(fps) * (minutes - math.floor(minutes / 10))
  end
  return n, sep == ";"
end

local function tc_of(n, fps, drop)
  local nominal = math.floor(fps + 0.5)
  if n < 0 then n = 0 end
  if drop then
    local d = drop_of(fps)
    local per_ten, per_minute = nominal * 600 - d * 9, nominal * 60 - d
    local tens, rest = math.floor(n / per_ten), n % per_ten
    n = n + d * 9 * tens + (rest > d and d * math.floor((rest - d) / per_minute) or 0)
  end
  local f, secs = n % nominal, math.floor(n / nominal)
  return string.format("%02d:%02d:%02d%s%02d", math.floor(secs / 3600), math.floor(secs / 60) % 60, secs % 60,
                       drop and ";" or ":", f)
end

local function stepped()
  local r = resolve or (Resolve and Resolve())
  if not r then return false end
  local by = STEP * step_frames()
  if r:GetCurrentPage() == "fusion" then  -- the composition's own time
    local c = (fu or fusion or r:Fusion()):GetCurrentComp()
    if not c then return false end
    local a = c:GetAttrs()
    local t = c.CurrentTime + by
    if a.COMPN_GlobalStart and t < a.COMPN_GlobalStart then t = a.COMPN_GlobalStart end
    if a.COMPN_GlobalEnd and t > a.COMPN_GlobalEnd then t = a.COMPN_GlobalEnd end
    c.CurrentTime = t
    return true
  end
  local project = r:GetProjectManager():GetCurrentProject()
  local tl = project and project:GetCurrentTimeline()
  local tc = tl and tl:GetCurrentTimecode()
  if not tc or tc == "" then return false end
  local fps = tonumber(tl:GetSetting("timelineFrameRate")) or 24
  local now, drop = frames_of(tc, fps)
  if not now then return false end
  if tl:SetCurrentTimecode(tc_of(now + by, fps, drop)) then return true end
  -- past the start or the end: as far as it goes (asked only then - every question waits on Resolve's picture)
  local to = math.max(tl:GetStartFrame(), math.min(now + by, tl:GetEndFrame() - 1))
  return to == now or tl:SetCurrentTimecode(tc_of(to, fps, drop)) and true or false
end

local ok, done = pcall(stepped)
if ok and done then return end
"""


def launcher_text(message, args):
    """The .lua launcher for one action: `message` to the service (bytes, or None: only the client), else `args`
    (None: nothing - a stand-in, only said by a running service)."""
    command = "{" + ", ".join(_lua_string(a) for a in (_client_command(args) if args is not None else [])) + "}"
    here = ""
    if message in (b"STEP:forward", b"STEP:back"):
        from . import paths
        here = (f"local STEP = {1 if message == b'STEP:forward' else -1}\n"
                f"local SETTINGS = {_lua_string(paths.SETTINGS_FILE)}" + _STEP_HERE)
    return _TEMPLATE.replace("__MESSAGE__", _lua_string(message.decode()) if message else "nil") \
                    .replace("__COMMAND__", command).replace("__HERE__", here)


# Clipse's scripts are in a folder of their own there - a submenu in Resolve's Workspace > Scripts. Resolve keeps a
# key by the script's place in its menu, and a loose script of someone else's sorting before Clipse's moved every key
# one down (seen 2026-10-21); a submenu has places of its own ("workspace_sub1_sub001_menu1") that loose scripts don't
# move - but submenus are numbered by their place among the folders, so a folder sorting before it moved it (tried
# in 21.1.1 the same day: Aaa, and a folder per script - deleting one moved the next). Resolve sorts them: a space,
# "!", digits, "_", letters, "~" - so the folder starts with "!": first, always (the owner's choice: "put something
# like ! before").
MENU_FOLDER = "!Clipse"
OLD_MENU_FOLDERS = ("Clipse",)  # (where they were for an hour, 2026-10-21 - taken out)


def clipse_scripts_folder():
    return os.path.join(utility_scripts_folder(), MENU_FOLDER)


def utility_scripts_folder():
    """Scripts/Utility — available on every Resolve page. Same base folder
    as default_scripts_folder() (Scripts/Edit), just the sibling folder."""
    return os.path.join(os.path.dirname(default_scripts_folder()), "Utility")


def _client_command(args):
    # sys.executable is the Python of this install (or the compiled program), so
    # the launcher keeps working no matter what's on Resolve's PATH.
    from .launch import command  # (compiled: the program itself with --client - launch.py)
    return command("client", *args, windowless=True)  # (Windows, from Python: pythonw - no console window)


def _marked(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.readline().startswith(LAUNCHER_MARK)
    except (OSError, UnicodeDecodeError):
        return False


def _existing_launchers(folder):
    """The app's own launchers there: the .lua ones (marked as ours) and the .py ones from before."""
    if not os.path.isdir(folder):
        return []
    return [os.path.join(folder, f) for f in os.listdir(folder)
            if is_ours(f) and (f.endswith(".py") or (f.endswith(".lua") and _marked(os.path.join(folder, f))))]


def install(folder=None):
    folder = folder or clipse_scripts_folder()
    os.makedirs(folder, exist_ok=True)
    # Resolve's Scripts menu - and the keys bound in Keyboard Customization -
    # should see as little change as possible on an update: launchers that
    # are already right are left alone (not deleted and written again), and
    # only launchers for actions that no longer exist are removed.
    wanted = {}
    for name, message, args in ACTIONS:  # (the same names as the .py ones before: the menu keeps its order, and keys)
        wanted[os.path.join(folder, f"{menu_name(name)}.lua")] = launcher_text(message, args)
    for number, name in STAND_INS.items():
        wanted[os.path.join(folder, f"{LAUNCHER_PREFIX}{number:02d} - {name}.lua")] = \
            launcher_text(f"RETIRED:{name}".encode(), None)
    for path in _existing_launchers(folder) + _old_launchers(folder):
        if path not in wanted:
            os.remove(path)  # a .py one from before, a retired action, one loose in Utility or in the folder before
            #                  (2026-10-21), or one an older version put in Scripts/Edit
    _drop_old_folders(folder)
    written = []
    for path, text in wanted.items():
        try:
            with open(path, encoding="utf-8") as f:
                if f.read() == text:
                    written.append(path)
                    continue
        except OSError:
            pass
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        written.append(path)
    return folder, written


def _old_launchers(folder):
    """Ours where they were before: loose in Utility, in an older folder, in Scripts/Edit."""
    utility = os.path.dirname(folder)
    return _existing_launchers(utility) + [p for old in OLD_MENU_FOLDERS for p in
                                           _existing_launchers(os.path.join(utility, old))] \
        + _existing_launchers(default_scripts_folder())


def _drop_old_folders(folder):
    for old in OLD_MENU_FOLDERS:
        try:
            os.rmdir(os.path.join(os.path.dirname(folder), old))  # (only when nothing else is left in it)
        except OSError:
            pass


def uninstall(folder=None):
    folder = folder or clipse_scripts_folder()
    removed = _existing_launchers(folder) + _old_launchers(folder)
    for path in removed:
        os.remove(path)
    for gone in [folder] + [os.path.join(os.path.dirname(folder), old) for old in OLD_MENU_FOLDERS]:
        try:
            os.rmdir(gone)  # (only when nothing else is left in it)
        except OSError:
            pass
    return folder, removed


# -- your own scripts in Resolve's menu --
# A script from one of your folders that isn't already in Resolve's
# Scripts folder gets a small launcher in Scripts/Utility, so it shows in
# Workspace > Scripts on every page and Keyboard Customization can give it
# a key. The launcher runs your script inside Resolve, the way Resolve
# runs any menu script (resolve / fusion / bmd are there for it).
_USER_TEMPLATE = {
    ".py": """\
# Clipse: runs one of your scripts from Resolve's Scripts menu - added with a right-click on it in the picker.
# Delete this file (or right-click it there again) to take it out of the menu. Your script itself isn't touched.
import runpy
runpy.run_path({path!r}, init_globals=dict(globals(), __name__="__main__"))
""",
    ".lua": """\
-- Clipse: runs one of your scripts from Resolve's Scripts menu - added with a right-click on it in the picker.
-- Delete this file (or right-click it there again) to take it out of the menu. Your script itself isn't touched.
dofile([==[{path}]==])
"""}
USER_MARK = "Clipse: runs one of your scripts"  # (in the first line of every launcher of ours)
OLD_MARKS = ("davinci-search: runs one of your scripts", "DaVinci Clipse: runs one of your scripts")  # (launchers made before the new name)


def resolve_script_folders():
    """Resolve's own script folders (yours, everyone's on the computer, Reactor's) - a script in these is in its
    Scripts menu already."""
    from .scripts_fusion import system_scripts_folders
    return [os.path.dirname(default_scripts_folder())] + system_scripts_folders()


def in_resolve_menu(path):
    real = os.path.realpath(path)
    return any(real.startswith(os.path.realpath(base) + os.sep) for base in resolve_script_folders())


def _ours(launcher):
    try:
        with open(launcher, encoding="utf-8") as f:
            first = f.readline()
        return any(m in first for m in (USER_MARK,) + OLD_MARKS)
    except OSError:
        return False


def user_launcher_path(script_path):
    name, ext = os.path.splitext(os.path.basename(script_path))
    return os.path.join(utility_scripts_folder(), f"{name}{ext}")


def menu_place(script_path):
    """Where `script_path` stands with Resolve's Scripts menu: "there" (it's in one of Resolve's script folders),
    "added" (a launcher of ours runs it from there), or "" (not in the menu)."""
    if in_resolve_menu(script_path):
        return "there"
    launcher = user_launcher_path(script_path)
    return "added" if os.path.exists(launcher) and _ours(launcher) else ""


def add_user_launcher(script_path):
    """Puts your script in Resolve's Workspace > Scripts menu. Returns (ok, message, launcher path)."""
    ext = os.path.splitext(script_path)[1].lower()
    if ext not in _USER_TEMPLATE:
        return False, "Only Python and Lua scripts can go in Resolve's menu", None
    target = user_launcher_path(script_path)
    if os.path.exists(target) and not _ours(target):
        return False, f"Resolve's menu already has a script called {os.path.basename(target)}", None
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, "w", encoding="utf-8") as f:
        f.write(_USER_TEMPLATE[ext].format(path=os.path.abspath(script_path)))
    return True, "Added to Resolve's Scripts menu \u203a Utility", target


def user_launcher_targets():
    """The scripts of yours that launchers of ours run from Resolve's menu (added with a right-click in the picker,
    or on Settings > Scripts) - wherever they are."""
    import ast
    import re
    folder, out = utility_scripts_folder(), []
    if not os.path.isdir(folder):
        return out
    for name in sorted(os.listdir(folder)):
        launcher = os.path.join(folder, name)
        if not _ours(launcher):
            continue
        try:
            with open(launcher, encoding="utf-8") as f:
                text = f.read()
        except OSError:
            continue
        hit = re.search(r"run_path\(('[^\n]*?'|\"[^\n]*?\"), init_globals", text) or re.search(r"dofile\(\[==\[(.*?)\]==\]\)", text)
        if hit is None:
            continue
        path = ast.literal_eval(hit.group(1)) if hit.re.pattern.startswith("run_path") else hit.group(1)
        if os.path.exists(path):
            out.append(path)
    return out


def remove_user_launcher(launcher_path):
    if not _ours(launcher_path):
        return False
    try:
        os.remove(launcher_path)
        return True
    except OSError:
        return False


def put_back_missing(folder=None):
    """When the service starts: any of its scripts missing from Resolve's menu are put back, quietly (deleted by
    hand, a Resolve reinstall ...), and any whose contents changed in an update are written again (install writes
    only those - a script rewritten keeps its place in the menu, so its key stays). Returns the names put back."""
    folder = folder or clipse_scripts_folder()
    there = {os.path.basename(p) for p in _existing_launchers(folder)}
    missing = [name for name, _m, _a in ACTIONS if f"{menu_name(name)}.lua" not in there]
    install(folder)  # (under an old name, or retired - Rescan and Search, 2026-10-19 - they go)
    return missing
