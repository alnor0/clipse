"""Support for the three additions on top of clip search:
  - running other DaVinci Resolve/Fusion scripts from the picker
  - inserting Fusion macros (.setting files) into the current comp
  - loading Fusion compositions into the current comp
  - switching to a different Resolve project

Confidence level differs per feature — noted on each function. Folder
locations for scripts/macros/comps are all user-configurable
(Settings.folders) since there's no single correct location — especially
true for Fusion compositions, which have no standard folder at all.
"""
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from . import paths


_asked = [0]


def run_lua(comp, lua, key="ClipseResult", wait=3.0):
    """Runs `lua` inside the composition and hands back what it left under
    `key` (None: nothing, or it stopped on an error - that's in the log).

    comp.Execute only *asks* Fusion: it comes straight back and the script
    runs a moment later (measured in Resolve 21.1: 0 to 5 ms for one line,
    longer for a long one). Reading the answer straight away got the answer
    of the script before, or none - "nothing is selected" with a node
    selected. So the answer is waited for: `key` holds a token until the
    script, or the lines added after it here, put something else there.
    (In Lua, SetData(key, nil) leaves what was there, so "nothing" is "".)"""
    _asked[0] += 1
    token = f"clipse asked {os.getpid()}.{_asked[0]}"
    comp.SetData(key, token)
    comp.Execute("local __ok, __err = pcall(function() " + lua
                 + f'\nend)\nif not __ok then comp:SetData("{key}", "{token} stopped: " .. tostring(__err))'
                 + f'\nelseif comp:GetData("{key}") == "{token}" then comp:SetData("{key}", "") end')
    until, pause = time.monotonic() + wait, 0.001
    while True:
        value = comp.GetData(key)
        if value != token:
            break
        if time.monotonic() > until:
            print(f"[fusion] no answer from Fusion after {wait:g} s - is it busy, or showing a message?")
            return None
        time.sleep(pause)
        pause = min(0.02, pause * 1.5)
    if isinstance(value, str) and value.startswith(token):
        print(f"[fusion] a script stopped: {value[len(token) + 10:]}")
        return None
    return None if value == "" else value


def default_scripts_folder():
    """Where Resolve's own Fusion -> Edit menu looks for scripts, per OS.
    Same logic client.py uses as its own fallback when __file__ isn't
    available (Resolve's Scripts menu runs scripts via exec(), which
    doesn't set __file__)."""
    system = platform.system()
    if system == "Windows":
        return os.path.expandvars(r"%APPDATA%\Blackmagic Design\DaVinci Resolve\Support\Fusion\Scripts\Edit")
    if system == "Darwin":
        return os.path.expanduser("~/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Edit")
    return os.path.expanduser("~/.local/share/DaVinciResolve/Fusion/Scripts/Edit")


def system_scripts_folders():
    """Resolve's script folders for everyone on the computer, and Reactor's (scripts installed from it) - always
    looked in for scripts:, besides the folders on Settings > Folders."""
    system = platform.system()
    if system == "Windows":
        base = os.path.expandvars(r"%PROGRAMDATA%\Blackmagic Design\DaVinci Resolve\Fusion")
    elif system == "Darwin":
        base = "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion"
    else:
        base = "/var/BlackmagicDesign/DaVinci Resolve/Fusion"
    return [os.path.join(base, "Scripts"), os.path.join(base, "Reactor", "Deploy", "Scripts")]


def default_macros_folder():
    """The folder Fusion actually scans for macros (.setting files) —
    the default folder the macro: search lists."""
    system = platform.system()
    if system == "Windows":
        return os.path.expandvars(r"%APPDATA%\Blackmagic Design\DaVinci Resolve\Support\Fusion\Macros")
    if system == "Darwin":
        return os.path.expanduser("~/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Macros")
    return os.path.expanduser("~/.local/share/DaVinciResolve/Fusion/Macros")


def _resolve_support_dir():
    """Resolve's per-user support folder (the parent of Fusion/)."""
    return os.path.dirname(os.path.dirname(os.path.dirname(default_scripts_folder())))


def useful_folders(settings_folders, max_folders=300, depth=3):
    """The folders the folder: search lists - [(path, name, section)],
    name being a readable trail like "Templates \u203a Edit \u203a Titles (12)"
    (with how many things are inside). Your scripts / macros / Fusion
    composition folders first, then Resolve's own Fusion folders, LUTs
    and Clipse's settings. Only folders that exist."""
    system = platform.system()
    fusion_dir = os.path.dirname(os.path.dirname(default_scripts_folder()))  # .../Fusion
    support = _resolve_support_dir()
    if system == "Windows":
        luts = [os.path.expandvars(r"%PROGRAMDATA%\Blackmagic Design\DaVinci Resolve\Support\LUT")]
    elif system == "Darwin":
        luts = ["/Library/Application Support/Blackmagic Design/DaVinci Resolve/LUT"]
    else:
        luts = [os.path.join(support, "LUT"), "/opt/resolve/LUT"]
    roots = []  # (folder, root label, section, walk inside?)
    for section, key in (("Your scripts", "scripts"), ("Your macros", "macros"),
                         ("Your Fusion compositions", "fusion_comps")):
        for folder in settings_folders.get(key, []):
            if folder:
                parent = os.path.basename(os.path.dirname(folder.rstrip("/\\")))
                base = os.path.basename(folder.rstrip("/\\")) or folder
                label = f"{parent} \u203a {base}" if base in ("Edit", "Utility", "Comp", "Color", "Deliver") else base
                roots.append((folder, label, section, True))
    roots += [
        (os.path.join(fusion_dir, "Templates"), "Templates", "Resolve: titles, transitions, effects", True),
        (os.path.join(fusion_dir, "Macros"), "Macros", "Resolve: Fusion macros", True),
        (os.path.join(fusion_dir, "Fuses"), "Fuses", "Resolve: Fusion plugins", True),
        (os.path.join(fusion_dir, "Scripts"), "Scripts", "Resolve: scripts", True),
        (fusion_dir, "Fusion", "Resolve", False),
    ] + [(p, "LUT", "Resolve: LUTs", True) for p in luts] + [
        (paths.CONFIG_DIR, "Clipse", "Clipse: settings, favourites, templates", False),
    ]

    def inside(path):
        try:
            return sum(1 for e in os.scandir(path) if not e.name.startswith("."))
        except OSError:
            return 0

    seen, out = set(), []

    def add(path, trail, section):
        key = os.path.normcase(os.path.abspath(path))
        if key in seen or not os.path.isdir(path) or len(out) >= max_folders:
            return False
        seen.add(key)
        out.append((path, f"{trail} ({inside(path)})", section))
        return True

    for folder, label, section, walk in roots:
        if not add(folder, label, section) or not walk:
            continue
        base_depth = folder.rstrip("/\\").count(os.sep)
        for root, dirs, _files in os.walk(folder):
            dirs[:] = sorted(d for d in dirs if not d.startswith("."))
            if root.rstrip("/\\").count(os.sep) - base_depth >= depth:
                dirs[:] = []
                continue
            for d in dirs:
                rel = os.path.relpath(os.path.join(root, d), folder)
                add(os.path.join(root, d), " \u203a ".join([label] + rel.split(os.sep)), section)
    return out


def _app_launcher(file_name):
    from .resolve_shortcuts import is_ours
    return is_ours(file_name)


def _is_menu_launcher(path):
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            first = f.readline()  # (a .py or a .lua one)
        from .resolve_shortcuts import USER_MARK, OLD_MARKS
        return any(m in first for m in (USER_MARK,) + OLD_MARKS)
    except OSError:
        return False


def scan_folders(folders, extensions):
    """Recursively finds files with any of `extensions` (lowercase, with
    dot, e.g. '.py') under each folder in `folders`. Returns a list of
    (path, filename, parent_folder_display) tuples. Silently skips
    folders that don't exist — a folder the user configured but hasn't
    created yet, or a stale path from an old settings.json, shouldn't
    break the whole scan."""
    results, seen = [], set()
    for folder in folders:
        if not folder or not os.path.isdir(folder):
            continue
        for root, _dirs, files in os.walk(folder):
            for fname in files:
                if os.path.join(root, fname) in seen:  # (a folder inside another one listed: once)
                    continue
                seen.add(os.path.join(root, fname))
                if _app_launcher(fname):
                    continue  # this app's own Resolve shortcut launchers — not user scripts
                if os.path.splitext(fname)[1].lower() in extensions:
                    full_path = os.path.join(root, fname)
                    if _is_menu_launcher(full_path):
                        continue  # a script of yours put in Resolve's menu - the script itself is listed
                    display_name = os.path.splitext(fname)[0]
                    parent = os.path.basename(root) or root
                    results.append((full_path, display_name, parent))
    return results


# -- Running a script — high confidence. This is exactly the same pattern
# this whole app already uses: a script that imports DaVinciResolveScript
# and connects to the already-running Resolve instance itself. A script
# only works launched this way if it bootstraps its own connection —
# one that instead relies on Resolve's built-in console auto-injecting
# `resolve`/`fu`/`comp` won't work run externally like this, but that's
# inherent to how that script was written, not fixable by a launcher. --
def run_script(path, resolve=None):
    """Runs one of your scripts the way Resolve's Workspace > Scripts menu does: inside Resolve (Fusion's
    RunScript), Lua or Python, with `resolve`, `fu` and `app` there for it (`comp` on the Fusion page) - tried
    in 21.1.1. Without Resolve to ask, a Python script runs as a program of its own (it then has to connect
    to Resolve itself)."""
    if resolve is not None:
        try:
            fusion = resolve.Fusion()
            if fusion is not None:
                fusion.RunScript(path)
                return f"Running script: {os.path.basename(path)}"
        except Exception as e:
            print(f"[scripts] Resolve didn't run '{os.path.basename(path)}' itself ({e}) - running it as a program")
    if not path.lower().endswith(".py"):
        return f"Couldn't run '{os.path.basename(path)}': Resolve didn't answer"
    from .launch import COMPILED
    python = (shutil.which("python3") or shutil.which("python")) if COMPILED else sys.executable  # (compiled: no
    if not python:                                                                              # Python of ours)
        return f"Couldn't run '{os.path.basename(path)}': Resolve didn't answer, and there's no Python to run it with"
    try:
        if os.name == "nt":
            flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
            subprocess.Popen([python, path], creationflags=flags,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            subprocess.Popen([python, path], start_new_session=True,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return f"Running script: {os.path.basename(path)}"
    except Exception as e:
        return f"Couldn't run '{os.path.basename(path)}': {e}"


# -- Loading a Fusion composition — LOW confidence, unverified. Resolve's
# public scripting API doesn't have a clearly documented "load this .comp
# file into the current Fusion page" call as of this writing. This uses
# the most plausible method (Composition.Paste with the file's content),
# but this is a guess, not a confirmed working call — test it and report
# back what happens/prints. --
def _find_target_comp(resolve, timeline):
    """Shared targeting logic for both comp loading and macro import: if
    already on the Fusion page, target whatever comp is open there;
    otherwise attach a fresh comp to the clip under the playhead and
    switch to the Fusion page. Returns (fusion, comp, error_message) —
    error_message is None on success."""
    try:
        current_page = resolve.GetCurrentPage()
    except Exception as e:
        current_page = None
        print(f"Couldn't read the current Resolve page: {e}")

    if current_page == "fusion":
        try:
            fusion = resolve.Fusion()
        except Exception as e:
            return None, None, f"Couldn't reach Fusion: {e}"
        if fusion is None:
            return None, None, "Couldn't reach Fusion."
        try:
            comp = fusion.GetCurrentComp()
        except Exception as e:
            return None, None, f"Couldn't get the current Fusion composition: {e}"
        if comp is None:
            return None, None, "No active Fusion composition on the Fusion page."
        return fusion, comp, None

    if timeline is None:
        return None, None, "No timeline available to find a target clip."
    try:
        clip = timeline.GetCurrentVideoItem()
    except Exception as e:
        return None, None, f"Couldn't get the clip under the playhead: {e}"
    if clip is None:
        return None, None, "No clip under the playhead to attach a Fusion composition to."

    try:
        comp = clip.AddFusionComp()
    except Exception as e:
        return None, None, f"Couldn't add a Fusion composition to the clip: {e}"
    if comp is None:
        return None, None, "Resolve didn't create a Fusion composition on this clip (AddFusionComp returned falsy)."

    try:
        resolve.OpenPage("fusion")
    except Exception as e:
        print(f"Couldn't switch to the Fusion page: {e}")

    try:
        fusion = resolve.Fusion()
    except Exception:
        fusion = None

    return fusion, comp, None


def _lua_long_string(text):
    """Quote text as a Lua long string ([==[ ... ]==]) — no escaping
    needed, so any file path (backslashes, quotes, spaces) passes through
    unchanged."""
    level = 0
    while f"]{'=' * level}]" in text:
        level += 1
    eq = "=" * level
    return f"[{eq}[{text}]{eq}]"


class _LuaVars(dict):
    """Values for _INSERT_MACRO_LUA - anything not given is Lua nil."""

    def __missing__(self, key):
        return "nil"


def media_in_settings(media_id, name, path, frames, trim=None):
    """A MediaIn node for a Media Pool clip, as a settings table (the same
    text Fusion puts on the clipboard when you copy a MediaIn). MediaIn is
    what Resolve itself uses for Media Pool clips - unlike a Loader it plays
    camera video (H.264/H.265 ...) and doesn't mistake numbers in a file
    name for an image sequence."""
    q = _lua_long_string
    frames = max(1, int(frames or 1))
    first, last = (int(trim[0]), int(trim[1]) - 1) if trim else (0, frames - 1)
    return (
        "{ Tools = { MediaIn1 = MediaIn { "
        "CustomData = { MediaProps = { MEDIA_NAME = %s, MEDIA_PATH = %s, MEDIA_NUM_FRAMES = %d, "
        "MEDIA_SRC_FRAME_RATE = 0 } }, "
        "Inputs = { "
        "MediaID = Input { Value = %s }, "
        "Layer = Input { Value = \"0\" }, "
        "ClipTimeStart = Input { Value = %d }, ClipTimeEnd = Input { Value = %d }, "
        "GlobalIn = Input { Value = 0 }, GlobalOut = Input { Value = %d } "
        "} } } }" % (q(name), q(path or ""), frames, q(media_id), first, last, last - first))


def _tool_count(comp):
    try:
        return len(comp.GetToolList(False) or {})
    except Exception:
        return None


# Runs inside Fusion (Lua), ahead of the scripts that place nodes: tile_rows(tool) is how many rows
# of the node view a tile hangs down over beyond its own - 0 for a plain tile.
# Measured in Resolve 21.1.1: a tile that shows a picture is as wide as any other, with the picture
# under its name, as tall as the picture's shape makes it - a 16:9 one covers the row below as well, so
# a Merge right under its foreground was hidden behind it. Out of the box Resolve shows a picture on
# every source (MediaIn, Background, Text+ ...): the node view's Force Source Tile Pictures.
_TILE_LUA = r"""
local tile_prefs
local function tile_rows(t)
    if tile_prefs == nil then
        local ok, p = pcall(function() return comp:GetPrefs("Comp.FlowView") end)
        tile_prefs = (ok and type(p) == "table") and p or {}
    end
    if tile_prefs.ShowThumbnails == false then return 0 end
    local a = t:GetAttrs() or {}
    local out = t:FindMainOutput(1)
    local kind = out and (out:GetAttrs() or {}).OUTS_DataType or nil
    local shows = (tile_prefs.ForceAll == true)
    if not shows and out and a.TOOLS_RegID ~= "GroupOperator" and a.TOOLS_RegID ~= "MacroOperator" then
        if kind == "Mask" then
            shows = (tile_prefs.ForceMask == true)
        elseif (kind == nil or kind == "Image") and t:FindMainInput(1) == nil then
            shows = (tile_prefs.ForceSource ~= false)   -- a source: nothing goes in, a picture comes out
        end
    end
    if not shows then   -- switched on for this one tile (it's kept with the node's place)
        local ok, saved = pcall(function() return t:SaveSettings() end)
        if ok and type(saved) == "table" and type(saved.Tools) == "table" then
            local own = saved.Tools[a.TOOLS_Name]
            local flags = type(own) == "table" and type(own.ViewInfo) == "table" and own.ViewInfo.Flags or nil
            if type(flags) == "table" then
                for k, v in pairs(flags) do
                    if v == true and tostring(k):find("Pic") then shows = true end
                end
            end
        end
    end
    if not shows then return 0 end
    local shape = 16 / 9
    if tile_prefs.AspectTilePics == false then
        shape = 4 / 3
    else
        local w = (tonumber(a.TOOLI_ImageWidth) or 0) * (tonumber(a.TOOLN_ImageAspectX) or 1)
        local h = (tonumber(a.TOOLI_ImageHeight) or 0) * (tonumber(a.TOOLN_ImageAspectY) or 1)
        if w > 0 and h > 0 then shape = w / h end
    end
    -- a tile is 2.49 rows wide; its name takes half a row, and the next tile needs a little air
    return math.max(1, math.min(6, math.ceil(0.55 + 2.49 / shape) - 1))
end
"""


# Runs inside Fusion (Lua). Pastes the macro and wires it into the node
# chain right after the selected node - the same as dropping a tool onto
# the connection between two nodes:
#     Before:  A ----------> B          After:  A --> [macro] --> B
# Which node is "A":  the active/selected node; if that's MediaOut (or has
# no output), the node feeding it. With nothing selected it isn't wired in at
# all: it's placed under the other nodes, where it covers nothing.
# A macro with no image input (a title, a generator) is layered on top
# with a Merge instead:  A -> Merge(background), macro -> Merge(foreground).
# The new node sits in the next column; nodes after the insert point only
# move right when there's no room for it, and only as far as needed.
_INSERT_MACRO_LUA = r"""
local PATH, TITLE, CONNECT, TOOL = %(path)s, %(title)s, %(connect)s, %(tool)s
local CLIP, TRIM_IN, TRIM_OUT = %(clip)s, %(trim_in)s, %(trim_out)s
local SETTINGS = %(settings)s  -- a settings table as text (a MediaIn for a Media Pool clip), else nil
local UNDO, SELECT = %(undo)s, %(select)s  -- SELECT: "first" (the new node), "result" (where a chain continues), "none"

local function attrs(t) return t:GetAttrs() end
local function name(t) return attrs(t).TOOLS_Name end
local function regid(t) return attrs(t).TOOLS_RegID end
local function in1(t) return t and t:FindMainInput(1) end
local function out1(t) return t and t:FindMainOutput(1) end
local function feeding(t)  -- the node connected into t's main input
    local i = in1(t)
    local o = i and i:GetConnectedOutput()
    return o and o:GetTool() or nil
end

local function run()
    local settings = nil
    if not TOOL then
        if SETTINGS then settings = bmd.readstring(SETTINGS) else settings = bmd.readfile(PATH) end
        if not settings then return "unreadable" end
    end

    -- 1. Where to insert
    local before, mediaout = {}, nil
    for _, t in pairs(comp:GetToolList(false)) do
        before[name(t)] = true
        if regid(t) == "MediaOut" and not mediaout then mediaout = t end
    end
    local target = comp.ActiveTool
    if not target then
        for _, t in pairs(comp:GetToolList(true)) do target = t; break end
    end
    local loose = (target == nil)  -- nothing selected: it's only placed, not wired in
    if target and (regid(target) == "MediaOut" or not out1(target)) then
        target = feeding(target)
    end
    local target_out = out1(target)
    local downstream = {}
    if target_out then
        for _, inp in pairs(target_out:GetConnectedInputs() or {}) do
            downstream[#downstream + 1] = inp
        end
    end

    -- 2. Paste the macro / add the node (unselected first, so Fusion
    --    doesn't wire it up by itself - that's done below)
    if TOOL then
        comp:SetActiveTool(nil)
        local added = comp:AddTool(TOOL, -32768, -32768)
        if not added then return "unknown tool" end
        if CLIP then  -- a Loader for a Media Pool clip's file
            added.Clip = CLIP
            if TRIM_IN then pcall(function() added.ClipTimeStart = TRIM_IN end) end
            if TRIM_OUT then pcall(function() added.ClipTimeEnd = TRIM_OUT end) end
        end
    else
        comp:Paste(settings)
    end
    -- (a group's own nodes come back too: they belong to the group, which is wired up as one node -
    --  wiring the inside of a group to the chain outside it hung Resolve, 2026-10-17)
    local new, is_new = {}, {}
    for _, t in pairs(comp:GetToolList(false)) do
        if not before[name(t)] then
            is_new[name(t)] = true
            if not attrs(t).TOOLH_GroupParent then new[#new + 1] = t end
        end
    end
    if #new == 0 then return "nothing pasted" end
    if loose then
        -- (2026-10-20: "when no nodes are selected, please just place the node somewhere. Dont connect it")
        -- under everything else, left-aligned with it - where it covers nothing
        local flow = comp.CurrentFrame and comp.CurrentFrame.FlowView
        if flow then
            local left, bottom, minx, miny = math.huge, -math.huge, math.huge, math.huge
            for _, t in pairs(comp:GetToolList(false)) do
                local p = not is_new[name(t)] and not attrs(t).TOOLH_GroupParent and flow:GetPosTable(t)
                if p and p[1] then
                    left = math.min(left, p[1])
                    bottom = math.max(bottom, p[2] + tile_rows(t))
                end
            end
            local spots = {}
            for _, t in ipairs(new) do
                local p = flow:GetPosTable(t)
                if p and p[1] then
                    spots[t] = p
                    minx, miny = math.min(minx, p[1]), math.min(miny, p[2])
                end
            end
            if left == math.huge then left, bottom = 0, -2 end
            for t, p in pairs(spots) do flow:SetPos(t, left + (p[1] - minx), bottom + 2 + (p[2] - miny)) end
        end
        -- (in a chain the next one goes after this)
        if SELECT ~= "none" then
            local last = new[1]
            for _, t in ipairs(new) do
                local o, feeds_new = out1(t), false
                for _, inp in pairs(o and o:GetConnectedInputs() or {}) do
                    if is_new[name(inp:GetTool())] then feeds_new = true end
                end
                if o and not feeds_new then last = t end
            end
            comp:SetActiveTool(SELECT == "first" and new[1] or last)
        end
        return "placed on its own (no node selected)"
    end
    if not CONNECT then return "not connected" end
    if not target_out then return "pasted (no node to connect it to)" end

    -- the macro's ends: where the image goes in, where it comes out
    local in_tool, out_tool
    for _, t in ipairs(new) do
        local src = feeding(t)
        if in1(t) and not in_tool and not (src and is_new[name(src)]) then in_tool = t end
        local o = out1(t)
        local feeds_new = false
        if o then
            for _, inp in pairs(o:GetConnectedInputs() or {}) do
                if is_new[name(inp:GetTool())] then feeds_new = true end
            end
            if not feeds_new then out_tool = t end
        end
    end
    if not out_tool then
        -- an end - a MediaOut, a Saver: it takes the picture from there, and what came after stays as it was
        local sink
        for _, t in ipairs(new) do if in1(t) and not feeding(t) then sink = t; break end end
        if not sink then return "pasted (the macro has no output to connect)" end
        in1(sink):ConnectTo(target_out)
        local flow = comp.CurrentFrame and comp.CurrentFrame.FlowView
        if flow then
            local tp = flow:GetPosTable(target)
            if tp and tp[1] then flow:SetPos(sink, tp[1] + 1, tp[2] + 1) end
        end
        if SELECT ~= "none" then comp:SetActiveTool(sink) end
        return "connected after " .. name(target)
    end

    -- 3. Connect
    local result_out, merge
    if in_tool then
        in1(in_tool):ConnectTo(target_out)
        result_out = out1(out_tool)
    else
        comp:SetActiveTool(nil)
        merge = comp:AddTool("Merge", -32768, -32768)
        merge.Background:ConnectTo(target_out)
        merge.Foreground:ConnectTo(out1(out_tool))
        result_out = out1(merge)
    end
    for _, inp in ipairs(downstream) do inp:ConnectTo(result_out) end

    -- 4. Make room and line it up (only when the node view is available)
    local flow = comp.CurrentFrame and comp.CurrentFrame.FlowView
    local tp = flow and flow:GetPosTable(target)
    local anchor = flow and flow:GetPosTable(in_tool or out_tool)
    if tp and tp[1] and anchor and anchor[1] then
        local tx, ty = tp[1], tp[2]
        local minx, maxx, ref_y = math.huge, -math.huge, nil
        for _, t in ipairs(new) do
            local p = flow:GetPosTable(t)
            if p and p[1] then
                if p[1] < minx then minx = p[1] end
                if p[1] > maxx then maxx = p[1] end
            end
        end
        -- The new node goes in the very next column. What comes after only
        -- moves when there's no room for it - and then just far enough.
        -- (It used to go up to three columns away and push everything along
        -- every time: a few inserts and the comp was spread right across.)
        local step = 1
        local width = (maxx - minx) + step
        local next_x = nil  -- the nearest node after the selected one, on its row
        for _, inp in ipairs(downstream) do
            local dp = flow:GetPosTable(inp:GetTool())
            if dp and dp[1] and math.abs(dp[2] - ty) < 0.5 and dp[1] > tx then
                if not next_x or dp[1] < next_x then next_x = dp[1] end
            end
        end
        local push = 0
        if next_x then push = math.max(0, (tx + width + 1) - next_x) end
        local moved, queue = {}, {}
        if push > 0 then
            for _, inp in ipairs(downstream) do queue[#queue + 1] = inp:GetTool() end
        end
        while #queue > 0 do
            local t = table.remove(queue, 1)
            if t and not moved[name(t)] and not is_new[name(t)] then
                moved[name(t)] = true
                local p = flow:GetPosTable(t)
                if p and p[1] then flow:SetPos(t, p[1] + push, p[2]) end
                local o = out1(t)
                if o then
                    for _, inp in pairs(o:GetConnectedInputs() or {}) do queue[#queue + 1] = inp:GetTool() end
                end
            end
        end
        local dy = 0
        if merge then  -- a layered node sits above its Merge - far enough up that its picture doesn't cover it
            for _, t in ipairs(new) do dy = math.min(dy, -1 - tile_rows(t)) end
        end
        for _, t in ipairs(new) do
            local p = flow:GetPosTable(t)
            if p and p[1] then flow:SetPos(t, tx + step + (p[1] - minx), ty + dy + (p[2] - anchor[2])) end
        end
        if merge then flow:SetPos(merge, tx + width, ty) end
    end
    if SELECT == "result" then
        comp:SetActiveTool(merge or out_tool)  -- the next one in a chain goes after this
    elseif SELECT == "first" then
        comp:SetActiveTool(new[1])  -- ready to adjust
    end
    if merge then return "layered over " .. name(target) .. " with a Merge" end
    return "connected after " .. name(target)
end

comp:Lock()
if UNDO then comp:StartUndo(TITLE) end
local ok, result = pcall(run)
if UNDO then comp:EndUndo(true) end
comp:Unlock()
comp:SetData("ClipseResult", ok and result or ("error: " .. tostring(result)))
"""


def macro_lua(macro_path, name, connect=True):
    """The Lua that pastes a macro file and wires it in (see _INSERT_MACRO_LUA)."""
    return _TILE_LUA + _INSERT_MACRO_LUA % _LuaVars({"path": _lua_long_string(os.path.abspath(macro_path)),
                               "title": _lua_long_string(f"Insert {name}"),
                               "connect": "true" if connect else "false", "tool": "nil",
                               "clip": "nil", "trim_in": "nil", "trim_out": "nil",
                               "undo": "true", "select": '"none"'})


def import_macro(resolve, macro_path, timeline=None, connect=True):
    """Inserts a macro (.setting file) into the Fusion composition, using
    the scripting API only - no simulated clicks or keys - and connects it
    into the node chain after the selected node (see _INSERT_MACRO_LUA).

    Fusion reads the file with its own loader (bmd.readfile), because the
    .setting format is a Lua table that only Fusion itself reads
    correctly, so the work runs inside Fusion via Composition.Execute.
    One undo step: Ctrl+Z removes the macro and restores the connections.
    connect=False just pastes it, unconnected (Ctrl+Enter in the picker).

    Target comp: the open one on the Fusion page; on other pages, a new
    comp on the clip under the playhead (then switches to Fusion).
    Returns (success, message)."""
    name = os.path.splitext(os.path.basename(macro_path))[0]
    if not os.path.isfile(macro_path):
        return False, f"Macro file not found: {macro_path}"
    fusion, comp, error = _find_target_comp(resolve, timeline)
    if error:
        return False, error

    before = _tool_count(comp)
    lua = macro_lua(macro_path, name, connect)
    try:
        result = run_lua(comp, lua, wait=10.0)
    except Exception as e:
        return False, f"Couldn't add {name}: {e}"

    if result == "unreadable":
        return False, f"Fusion couldn't read {name}"
    if result and str(result).startswith("error:"):
        # the paste itself may still have worked - report what Fusion said
        return False, f"Macro '{name}': {result}"
    after = _tool_count(comp)
    if not result and before is not None and after is not None and after <= before:
        return False, f"{name} didn't go in"
    return True, f"Added {name}" + (f" - {result}." if result else ".")


# -- Fusion nodes (n: in the picker) --
# Common nodes, used until Fusion's own list has been read once (it needs
# an open composition) - id, name, category.
COMMON_TOOLS = [
    ("Background", "Background", "Generator"), ("FastNoise", "Fast Noise", "Generator"),
    ("TextPlus", "Text+", "Generator"), ("Text3D", "Text 3D", "3D"),
    ("Blur", "Blur", "Blur"), ("DirectionalBlur", "Directional Blur", "Blur"), ("Defocus", "Defocus", "Blur"),
    ("Glow", "Glow", "Blur"), ("SoftGlow", "Soft Glow", "Effect"), ("Sharpen", "Sharpen", "Blur"),
    ("VariBlur", "Vari Blur", "Blur"),
    ("Transform", "Transform", "Transform"), ("Resize", "Resize", "Transform"), ("Crop", "Crop", "Transform"),
    ("Letterbox", "Letterbox", "Transform"), ("CameraShake", "Camera Shake", "Transform"),
    ("Merge", "Merge", "Composite"), ("Dissolve", "Dissolve", "Composite"),
    ("ChannelBoolean", "Channel Booleans", "Composite"), ("MatteControl", "Matte Control", "Matte"),
    ("DeltaKeyer", "Delta Keyer", "Matte"), ("UltraKeyer", "Ultra Keyer", "Matte"),
    ("LumaKeyer", "Luma Keyer", "Matte"),
    ("ColorCorrector", "Color Corrector", "Color"), ("ColorCurves", "Color Curves", "Color"),
    ("BrightnessContrast", "Brightness Contrast", "Color"), ("HueCurves", "Hue Curves", "Color"),
    ("RectangleMask", "Rectangle", "Mask"), ("EllipseMask", "Ellipse", "Mask"),
    ("PolylineMask", "Polygon", "Mask"), ("BSplineMask", "B-Spline", "Mask"),
    ("Tracker", "Tracker", "Tracking"), ("PlanarTracker", "Planar Tracker", "Tracking"),
    ("CornerPositioner", "Corner Positioner", "Warp"), ("GridWarp", "Grid Warp", "Warp"),
    ("Displace", "Displace", "Warp"), ("Paint", "Paint", "Paint"), ("FilmGrain", "Film Grain", "Effect"),
    ("Highlight", "Highlight", "Effect"), ("Shadow", "Shadow", "Effect"),
    ("Merge3D", "Merge 3D", "3D"), ("Renderer3D", "Renderer 3D", "3D"), ("Camera3D", "Camera 3D", "3D"),
    ("ImagePlane3D", "Image Plane 3D", "3D"), ("Shape3D", "Shape 3D", "3D"),
    ("pEmitter", "pEmitter", "Particles"), ("pRender", "pRender", "Particles"),
    ("MediaOut", "MediaOut", "I/O"), ("Saver", "Saver", "I/O"),
]
# What a node does, in a line - shown in the preview for n: rows
TOOL_DESCRIPTIONS = {
    "Background": "A solid colour or gradient - a base layer, or a colour to put things on.",
    "FastNoise": "Animated noise: smoke, clouds, textures, grain or a moving background.",
    "TextPlus": "Titles and text, with fonts, outlines, shadows and per-character animation.",
    "Text3D": "3D text with depth and bevels - goes into a Renderer 3D.",
    "Blur": "Softens the image evenly.",
    "DirectionalBlur": "Blur in one direction - motion streaks, zoom or spin blur.",
    "Defocus": "An out-of-focus lens blur, with bokeh.",
    "Glow": "Makes bright parts bleed light around them.",
    "SoftGlow": "A softer, dreamier glow on the brightest parts.",
    "Sharpen": "Brings out edges and detail.",
    "VariBlur": "Blur that changes across the image, driven by another image.",
    "Transform": "Move, scale and rotate the image - keyframe it for movement.",
    "Resize": "Changes the image's pixel size.",
    "Crop": "Cuts the image down to a part of it.",
    "Letterbox": "Fits the image into another frame size, with bars.",
    "CameraShake": "Adds handheld-style shake.",
    "Merge": "Puts one image (Foreground) on top of another (Background).",
    "Dissolve": "Blends between two images.",
    "ChannelBoolean": "Combines channels of two images - for mattes and colour tricks.",
    "MatteControl": "Combines, cleans up and copies mattes (alpha) between images.",
    "DeltaKeyer": "Green / blue screen keying.",
    "UltraKeyer": "Green / blue screen keying, the classic one.",
    "LumaKeyer": "Keys out by brightness - lose the black or the white.",
    "ColorCorrector": "Colour, saturation, gain / lift / gamma - by shadows, midtones and highlights.",
    "ColorCurves": "RGB curves.",
    "BrightnessContrast": "Quick brightness, contrast, gamma and saturation.",
    "HueCurves": "Change colours by hue - e.g. make just the blues greener.",
    "RectangleMask": "A rectangle to limit an effect to part of the image.",
    "EllipseMask": "An ellipse to limit an effect to part of the image (vignettes, spotlights).",
    "PolylineMask": "A shape you draw point by point, to limit an effect or cut something out.",
    "BSplineMask": "A smooth curved shape you draw, to limit an effect or cut something out.",
    "Tracker": "Follows points in the shot - to stick things to it or stabilise it.",
    "PlanarTracker": "Follows a flat surface (a screen, a sign) to put something onto it.",
    "CornerPositioner": "Pins an image's four corners anywhere - put a picture onto a screen.",
    "GridWarp": "Bends the image with a grid of points.",
    "Displace": "Pushes pixels around using another image - heat haze, ripples, glitches.",
    "Paint": "Paint and clone strokes onto the image.",
    "FilmGrain": "Realistic film grain.",
    "Highlight": "Star-like streaks on the brightest points.",
    "Shadow": "A drop shadow from the image's alpha.",
    "Merge3D": "Combines 3D objects, lights and cameras into one scene.",
    "Renderer3D": "Turns a 3D scene into a normal 2D image.",
    "Camera3D": "A camera for a 3D scene.",
    "ImagePlane3D": "A flat card in 3D space with an image on it.",
    "Shape3D": "Simple 3D shapes: cube, sphere, cylinder ...",
    "MediaOut": "Where the composition's picture goes out to the timeline - a second one is a second output.",
    "Saver": "Writes the picture at that point to a file.",
    "pEmitter": "Makes particles - sparks, dust, snow, confetti.",
    "pRender": "Renders particles to an image.",
}

TOOLS_CACHE_FILE = paths.cache("fusion_tools.json")

_LIST_TOOLS_LUA = r"""
local out = {}
for _, reg in pairs(fu:GetRegList(CT_Tool) or {}) do
    local a = reg:GetAttrs() or {}
    local id, name, cat = a.REGS_ID, a.REGS_Name, a.REGS_Category or ""
    if id and name and not a.REGB_Hidden and not cat:find("Hidden") then
        out[#out + 1] = id .. "\t" .. name .. "\t" .. cat
    end
end
comp:SetData("ClipseTools", table.concat(out, "\n"))
"""


def list_fusion_tools(resolve):
    """Every node Fusion offers (third-party Fuses and plugins too): read
    from Fusion when a composition is open, remembered on disk after
    that. Returns [(id, name, category)]."""
    comp = None
    try:
        if resolve.GetCurrentPage() == "fusion":
            fusion = resolve.Fusion()
            comp = fusion.GetCurrentComp() if fusion else None
    except Exception:
        comp = None
    if comp is not None:
        try:
            text = run_lua(comp, _LIST_TOOLS_LUA, key="ClipseTools", wait=1.5) or ""
            comp.SetData("ClipseTools", None)
            tools = []
            for line in str(text).splitlines():
                parts = line.split("\t")
                if len(parts) == 3:
                    category = parts[2].strip("\\").split("\\")[-1] or "Other"
                    tools.append((parts[0], parts[1], category))
            if len(tools) >= 10:
                tools.sort(key=lambda t: t[1].lower())
                try:
                    paths.write_json(TOOLS_CACHE_FILE, tools)
                except OSError:
                    pass
                return tools
        except Exception as e:
            print(f"[nodes] couldn't read Fusion's node list: {e}")
    try:
        with open(TOOLS_CACHE_FILE, encoding="utf-8") as f:
            tools = [tuple(t) for t in json.load(f) if len(t) == 3]
        if tools:
            if not any(t[0] == "MediaOut" for t in tools):  # (read before MediaOut was listed too)
                tools = sorted(tools + [("MediaOut", "MediaOut", "I/O")], key=lambda t: t[1].lower())
            return tools
    except (OSError, ValueError, TypeError):
        pass
    return sorted(COMMON_TOOLS, key=lambda t: t[1].lower())


def add_tool_after_selected(comp, tool_id, title, connect=True, undo=True):
    """One node of kind `tool_id` into `comp`, wired in after the selected
    node and left selected (see _INSERT_MACRO_LUA). What Fusion said about
    it: "connected after X", "unknown tool", "error: ...". undo=False when
    the caller has its own undo step around this."""
    lua = _TILE_LUA + _INSERT_MACRO_LUA % _LuaVars({"path": "nil", "title": _lua_long_string(title),
                                        "connect": "true" if connect else "false",
                                        "tool": _lua_long_string(tool_id), "clip": "nil", "trim_in": "nil",
                                        "trim_out": "nil", "undo": "true" if undo else "false", "select": '"first"'})
    return run_lua(comp, lua)


def insert_tool(resolve, tool_id, tool_name, timeline=None, connect=True):
    """Adds a Fusion node and wires it in after the selected node - like
    a macro (see _INSERT_MACRO_LUA): a node with an image input goes in
    between, one without (Text+, Background ...) is layered on with a
    Merge. One undo step. Returns (success, message)."""
    fusion, comp, error = _find_target_comp(resolve, timeline)
    if error:
        return False, error
    try:
        result = add_tool_after_selected(comp, tool_id, f"Add {tool_name}", connect=connect)
    except Exception as e:
        return False, f"Couldn't add {tool_name}: {e}"
    if result == "unknown tool":
        return False, f"Fusion has no {tool_id} node"
    if result and str(result).startswith("error:"):
        return False, f"{tool_name}: {result}"
    return True, f"Added {tool_name}" + (f" - {result}." if result else ".")


def _clip_values(path, name, trim, media_id, frames, use_loader=False):
    """Lua values that add a Media Pool clip: a MediaIn linked to the clip
    (like dragging it in from the Media Pool), or - as a fallback - a
    Loader reading its file."""
    if media_id and not use_loader:
        return {"settings": _lua_long_string(media_in_settings(media_id, name, path, frames, trim))}
    return {"tool": "[[Loader]]", "clip": _lua_long_string(os.path.abspath(path)),
            "trim_in": str(int(trim[0])) if trim else "nil",
            "trim_out": str(int(trim[1]) - 1) if trim else "nil"}


def _run_insert(comp, values):
    return str(run_lua(comp, _TILE_LUA + _INSERT_MACRO_LUA % _LuaVars(values), wait=10.0) or "")


_FAILED = ("unreadable", "unknown tool", "nothing pasted")


def add_clip_to_comp(resolve, path, name, timeline=None, connect=True, trim=None, media_id=None, frames=None):
    """Adds a Media Pool clip to the open Fusion composition as a MediaIn
    (a Loader if that doesn't work), layered over the selected node with a
    Merge (Ctrl+Enter: just added, not connected). trim: (first, end)
    frames from the preview's in/out marks, or None. Returns (success, message)."""
    if not media_id and (not path or not os.path.isfile(path)):
        return False, f"{name}: its file is gone"
    fusion, comp, error = _find_target_comp(resolve, timeline)
    if error:
        return False, error
    base = {"path": "nil", "title": _lua_long_string(f"Add {name}"),
            "connect": "true" if connect else "false", "undo": "true", "select": '"result"'}
    try:
        result = _run_insert(comp, {**base, **_clip_values(path, name, trim, media_id, frames)})
        if (result in _FAILED or result.startswith("error:")) and media_id and path and os.path.isfile(path):
            print(f"[fusion] MediaIn for '{name}' didn't work ({result}) - trying a Loader")
            result = _run_insert(comp, {**base, **_clip_values(path, name, trim, media_id, frames, use_loader=True)})
    except Exception as e:
        return False, f"Couldn't add {name}: {e}"
    if result in _FAILED or result.startswith("error:"):
        return False, f"'{name}': {result}"
    return True, f"Added {name}" + (f" - {result}." if result else ".")


def insert_chain(resolve, entries, timeline=None, connect=True):
    """Several nodes / macros / clips in one go, in the order staged: each
    goes after the one before, so they end up as one straight line in the
    node editor (clips and nodes without an image input are layered on
    with a Merge, in that line, with the layer just above it). One undo step.
    entries: [("tool", id, name) | ("macro", path, name) | ("clip", path, name, trim)].
    Returns a message."""
    fusion, comp, error = _find_target_comp(resolve, timeline)
    if error:
        return error
    added, problems = 0, []
    try:
        comp.StartUndo(f"Add {len(entries)} nodes")
    except Exception:
        pass
    try:
        for entry in entries:
            kind, ref, name = entry[0], entry[1], entry[2]
            values = {"path": "nil", "title": _lua_long_string(f"Add {name}"),
                      "connect": "true" if connect else "false", "tool": "nil", "clip": "nil",
                      "trim_in": "nil", "trim_out": "nil", "undo": "false", "select": '"result"'}
            if kind == "tool":
                values["tool"] = _lua_long_string(ref)
            elif kind == "macro":
                if not os.path.isfile(ref):
                    problems.append(f"{name}: file not found")
                    continue
                values["path"] = _lua_long_string(os.path.abspath(ref))
            elif kind == "clip":  # ("clip", path, name, trim, media_id, frames)
                trim, media_id, frames = (list(entry[3:6]) + [None, None, None])[:3]
                if not media_id and (not ref or not os.path.isfile(ref)):
                    problems.append(f"{name}: file not found")
                    continue
                values.update(_clip_values(ref, name, trim, media_id, frames))
            result = _run_insert(comp, values)
            if kind == "clip" and (result in _FAILED or result.startswith("error:")) and ref and os.path.isfile(ref):
                values.update(_clip_values(ref, name, trim, None, frames, use_loader=True))
                values["settings"] = "nil"
                result = _run_insert(comp, values)
            if result.startswith("error:") or result in _FAILED:
                problems.append(f"{name}: {result}")
            else:
                added += 1
    finally:
        try:
            comp.EndUndo(True)
        except Exception:
            pass
    message = f"Added {added} of {len(entries)} in a row"
    return message + (" - " + "; ".join(problems) if problems else ".")


# Runs inside Fusion (Lua): sorts the node editor into clean lines.
#  - Every line of nodes is followed back from where it ends - MediaOut, or any node whose
#    picture goes nowhere - so a comp whose MediaOut isn't wired up yet is sorted all the same.
#  - A line runs left to right on one row, through each node's main input. What comes in from
#    the side (a Merge's foreground) sits right above the node it joins, a mask right below,
#    and runs left from there, on the nearest row with room - three Merges in a row have their
#    three foregrounds side by side above them, not on a staircase.
#  - A node is always to the left of everything it feeds, also when it feeds several.
#  - Lines that end somewhere else go underneath, one after the other; nodes connected to
#    nothing go in a row under that. A MediaOut with nothing going in waits at the end of the
#    first line. Sticky notes, underlays and what's inside a group stay as they are.
#  - A tile that shows a picture is taller (tile_rows): nothing is put where it hangs over.
#  - MediaOut stays where it was, so the view doesn't jump. One undo step.
# The answer is "<nodes> <how many moved>".
_TIDY_LUA = r"""
local flow = comp.CurrentFrame and comp.CurrentFrame.FlowView
if not flow then comp:SetData("ClipseResult", "no node view"); return end
local VERTICAL = (STYLE == "vertical")
local LEFT_ALONE = {Note = true, Underlay = true}
local NODE, WIRE = 1, 2

-- 1. The nodes: everything with a place in the node view. What's inside a group counts as the group.
local info, names = {}, {}       -- name -> {tool, id, x, y}; the names in Fusion's order
local parent_of = {}             -- name -> name of the group it's in
local listed = {}
local function note(t)
    local a = t:GetAttrs() or {}
    local name = a.TOOLS_Name
    if not name or listed[name] then return name end
    listed[name] = {tool = t, id = a.TOOLS_RegID}
    local group = a.TOOLH_GroupParent
    if group then parent_of[name] = note(group) end
    return name
end
local all, keys = comp:GetToolList(false) or {}, {}
for k in pairs(all) do keys[#keys + 1] = k end
table.sort(keys, function(a, b) return (tonumber(a) or 0) < (tonumber(b) or 0) end)
local every = {}
for _, k in ipairs(keys) do every[#every + 1] = note(all[k]) end
local function top(name)         -- the node in the view that `name` belongs to
    local n = 0
    while name and parent_of[name] and n < 50 do name = parent_of[name]; n = n + 1 end
    return name
end
for name, entry in pairs(listed) do
    if not parent_of[name] and not LEFT_ALONE[entry.id or ""] then
        -- (a modifier - a spline, a path - has no place in the view)
        local found, p = pcall(function() return flow:GetPosTable(entry.tool) end)
        if found and type(p) == "table" and tonumber(p[1]) and tonumber(p[2]) then
            info[name] = {tool = entry.tool, id = entry.id, x = p[1], y = p[2], tall = tile_rows(entry.tool)}
            names[#names + 1] = name
        end
    end
end
table.sort(names)
if #names == 0 then comp:SetData("ClipseResult", "nothing to sort"); return end

-- 2. What feeds what. For each node: the one on its main input, and the ones coming in from the side.
local function in_order(id)      -- Layer2 before Layer10
    return (tostring(id or ""):gsub("%d+", function(d) return string.format("%09d", tonumber(d)) end))
end
local feeds = {}                 -- name -> list of {from, main, mask, key}
for _, name in ipairs(names) do feeds[name] = {} end
for _, name in ipairs(every) do
    local owner = top(name)
    if owner and info[owner] then
        local t = listed[name].tool
        local main = (name == owner) and t:FindMainInput(1) or nil
        local main_id = main and (main:GetAttrs() or {}).INPS_ID or nil
        for _, inp in pairs(t:GetInputList() or {}) do
            local out = inp:GetConnectedOutput()
            local from_tool = out and out:GetTool() or nil
            if from_tool then
                local from = top(note(from_tool))
                if from and from ~= owner and info[from] then
                    local a = inp:GetAttrs() or {}
                    local id = tostring(a.INPS_ID or "")
                    feeds[owner][#feeds[owner] + 1] = {
                        from = from, main = (main_id ~= nil and id == main_id),
                        mask = (a.INPS_DataType == "Mask") or (id:find("Mask") ~= nil), key = in_order(id)}
                end
            end
        end
    end
end
local main_of, sides, fed_by_any = {}, {}, {}
local used_by = {}               -- name -> list of {to, step}: step 1 through a main input, 0 from the side
for _, name in ipairs(names) do
    local list, seen, kept = feeds[name], {}, {}
    table.sort(list, function(a, b)
        if a.main ~= b.main then return a.main end
        if a.mask ~= b.mask then return b.mask end
        if a.key ~= b.key then return a.key < b.key end
        return a.from < b.from
    end)
    for _, f in ipairs(list) do          -- the same node into two inputs is one line
        if not seen[f.from] then seen[f.from] = true; kept[#kept + 1] = f end
    end
    -- nothing on the main input: the first thing coming in is the line it sits in
    if kept[1] and not kept[1].main then kept[1].main = true end
    sides[name] = {}
    for _, f in ipairs(kept) do
        if f.main then main_of[name] = f.from else sides[name][#sides[name] + 1] = f end
        used_by[f.from] = used_by[f.from] or {}
        -- (top to bottom, a tile with a picture hangs over the next places in its own line)
        table.insert(used_by[f.from], {to = name, step = f.main and (1 + (VERTICAL and info[f.from].tall or 0)) or 0})
        fed_by_any[name] = true
    end
end

-- 3. Columns: a node sits left of everything it feeds - one column before what it's the main input of.
local depth, working = {}, {}
local function depth_of(name)
    if depth[name] then return depth[name] end
    if working[name] then return 0 end
    working[name] = true
    local d = 0
    for _, use in ipairs(used_by[name] or {}) do d = math.max(d, depth_of(use.to) + use.step) end
    working[name] = nil
    depth[name] = d
    return d
end
for _, name in ipairs(names) do depth_of(name) end

-- 4. Rows. Along / across: left-right and up-down for lines, the other way round for top to bottom.
local function along(name) return VERTICAL and info[name].y or info[name].x end
local function across(name) return VERTICAL and info[name].x or info[name].y end
local ends, loose, waiting_out = {}, {}, nil
for _, name in ipairs(names) do
    if not used_by[name] then
        if fed_by_any[name] then ends[#ends + 1] = name
        elseif info[name].id == "MediaOut" and not waiting_out then waiting_out = name
        else loose[#loose + 1] = name end
    end
end
local function rank(name) local id = info[name].id; return id == "MediaOut" and 0 or (id == "Saver" and 1 or 2) end
table.sort(ends, function(a, b)
    if rank(a) ~= rank(b) then return rank(a) < rank(b) end
    if across(a) ~= across(b) then return across(a) < across(b) end
    if along(a) ~= along(b) then return along(a) < along(b) end
    return a < b
end)
table.sort(loose, function(a, b)
    if along(a) ~= along(b) then return along(a) < along(b) end
    if across(a) ~= across(b) then return across(a) < across(b) end
    return a < b
end)
if #ends == 0 and waiting_out then table.insert(loose, 1, waiting_out); waiting_out = nil end

local row, taken = {}, {}        -- name -> row; nodes already in a line
local grid                       -- "column row" -> NODE or WIRE, for the line being laid out
local low, high, block
local function cell(c, r) return c .. " " .. r end
local function line_from(name)   -- `name` and what feeds it through the main inputs, as far as it's free
    local list = {}
    while name and not taken[name] do
        taken[name] = true
        list[#list + 1] = name
        name = main_of[name]
    end
    return list
end
local function covers(name, r)  -- a node's own cell, and those its picture hangs over
    local c, list = -depth[name], {}
    for k = 0, info[name].tall do
        list[#list + 1] = VERTICAL and cell(c + k, r) or cell(c, r + k)
    end
    return list
end
local function has_room(list, r)
    local lo, hi = math.huge, -math.huge
    for _, name in ipairs(list) do
        local c = -depth[name]
        for _, at in ipairs(covers(name, r)) do if grid[at] then return false end end
        lo, hi = math.min(lo, c), math.max(hi, c)
    end
    for c = lo, hi do if grid[cell(c, r)] == NODE then return false end end
    return true
end
local function put(list, r)
    local lo, hi = math.huge, -math.huge
    for _, name in ipairs(list) do
        local c = -depth[name]
        row[name] = r
        block[#block + 1] = name
        lo, hi = math.min(lo, c), math.max(hi, c)
        low, high = math.min(low, r), math.max(high, r + (VERTICAL and 0 or info[name].tall))
    end
    for c = lo, hi do grid[cell(c, r)] = WIRE end       -- (the wire along the row; nodes next)
    for _, name in ipairs(list) do
        for _, at in ipairs(covers(name, r)) do grid[at] = NODE end
    end
end
local branch
branch = function(list, r, way)  -- what joins this line from the side, the leftmost first
    -- single nodes coming in (a picture, a video, a text) go on one row, level with each other: the row the
    -- one that needs it furthest out needs (a square picture's tile is taller than a 16:9 one's - the 16:9
    -- one sat lower than the others)
    local level = {}
    for i = #list, 1, -1 do
        for _, side in ipairs(sides[list[i]]) do
            local from = side.from
            if not taken[from] and (not main_of[from] or taken[main_of[from]]) then
                local go = way or (side.mask and 1 or -1)
                local r2 = r + go
                while not has_room({from}, r2) do r2 = r2 + go end
                if level[go] == nil or (r2 - level[go]) * go > 0 then level[go] = r2 end
            end
        end
    end
    for i = #list, 1, -1 do
        local name = list[i]
        for _, side in ipairs(sides[name]) do
            if not taken[side.from] then
                local go = way or (side.mask and 1 or -1)   -- on the main line: pictures above, masks below
                local single = not main_of[side.from] or taken[main_of[side.from]]
                local sub = line_from(side.from)
                local r2 = (single and level[go]) or (r + go)
                while not has_room(sub, r2) do r2 = r2 + go end
                put(sub, r2)
                local c = -depth[name]
                if -depth[side.from] == c then               -- keep its wire down to the node clear
                    for between = r + go, r2 - go, go do
                        if not grid[cell(c, between)] then grid[cell(c, between)] = WIRE end
                    end
                end
                branch(sub, r2, go)
            end
        end
    end
end

local next_row, least_col = 0, 0
for _, name in ipairs(ends) do   -- each line is laid out by itself, then goes under the one before
    grid, low, high, block = {}, 0, 0, {}
    local list = line_from(name)
    put(list, 0)
    branch(list, 0, nil)
    for _, placed in ipairs(block) do row[placed] = row[placed] + next_row - low end
    next_row = next_row + (high - low) + 2            -- an empty row in between
end
if waiting_out then row[waiting_out] = row[ends[1]]; depth[waiting_out] = -1 end
for _, name in ipairs(names) do
    if row[name] then least_col = math.min(least_col, -depth[name]) end
end
local col = {}
for _, name in ipairs(names) do if row[name] then col[name] = -depth[name] end end
local loose_at = least_col
for _, name in ipairs(loose) do
    row[name], col[name] = next_row, loose_at
    loose_at = loose_at + 1 + (VERTICAL and info[name].tall or 0)
end

-- 5. Move them. The anchor - MediaOut when there is one - stays exactly where it was.
local anchor = waiting_out or ends[1] or loose[1]
if not anchor then comp:SetData("ClipseResult", "nothing to sort"); return end
for _, name in ipairs(names) do
    if info[name].id == "MediaOut" and row[name] then anchor = name; break end
end
local function spot(name)
    if VERTICAL then return row[name], col[name] end
    return col[name], row[name]
end
local ax, ay = spot(anchor)
local moves = {}
for _, name in ipairs(names) do
    local x, y = spot(name)
    x, y = info[anchor].x + (x - ax), info[anchor].y + (y - ay)
    -- (Fusion hands a place back rounded, and snapped to its grid: under a pixel isn't a move)
    if math.abs(x - info[name].x) > 0.02 or math.abs(y - info[name].y) > 0.02 then
        moves[#moves + 1] = {info[name].tool, x, y}
    end
end
if #moves > 0 then  -- (nothing to move: no step of its own in Fusion's undo either)
    comp:Lock()
    comp:StartUndo("Tidy up nodes")
    local ok, problem = pcall(function()
        for _, m in ipairs(moves) do flow:SetPos(m[1], m[2], m[3]) end
    end)
    comp:EndUndo(true)
    comp:Unlock()
    if not ok then error(problem, 0) end
end
-- (the nodes in the middle of the node view, the zoom as it was: "just center, not zoom". The node
-- view has no "centre on" of its own - FrameAll centres and zooms, so its zoom is put back after it)
if FIT then pcall(function() local s = flow:GetScale(); flow:FrameAll(); if s then flow:SetScale(s) end end) end
comp:SetData("ClipseResult", #names .. " " .. #moves)
"""


TIDY_STYLES = {"lines": "Lines, left to right", "vertical": "Top to bottom"}


def tidy_lua(style="lines", fit=False):
    """The whole script Tidy up nodes runs in the composition. fit: then the nodes in the middle of the node view, its
    zoom left as it was (Settings > Scripts)."""
    return (f"local STYLE = {_lua_long_string(style if style in TIDY_STYLES else 'lines')}\n"
            f"local FIT = {'true' if fit else 'false'}\n" + _TILE_LUA + _TIDY_LUA)


def tidy_quietly(resolve, style="lines"):
    """Tidy up after an insert (Settings > Fusion): nothing said - how many nodes moved (0 if none, or if it
    couldn't)."""
    try:
        comp = resolve.Fusion().GetCurrentComp() if resolve.GetCurrentPage() == "fusion" else None
        if comp is None:
            return 0
        _count, _sep, moved = str(run_lua(comp, tidy_lua(style), wait=10.0) or "").partition(" ")
        return int(moved) if moved.isdigit() else 0
    except Exception as e:
        print(f"[tidy] after the insert: {e}")
        return 0


def tidy_nodes(resolve, style="lines", fit=False):
    """Sorts the open Fusion composition's node editor (see _TIDY_LUA).
    style: "lines" - each line of nodes left to right, what joins it right above (masks below);
    "vertical" - the same running top to bottom."""
    try:
        if resolve.GetCurrentPage() != "fusion":
            return "Tidy up needs the Fusion page"
        comp = resolve.Fusion().GetCurrentComp()
    except Exception as e:
        return f"Couldn't reach Fusion: {e}"
    if comp is None:
        return "No Fusion composition open."
    try:
        result = str(run_lua(comp, tidy_lua(style, fit), wait=10.0) or "")
    except Exception as e:
        return f"Couldn't tidy up: {e}"
    count, _, moved = result.partition(" ")
    if count.isdigit() and moved.isdigit():  # (moved or not: pressing it out of habit is fine, no lecture)
        return f"Tidied up {count} node{'s' if count != '1' else ''}."
    return f"Tidy up: {result or 'nothing happened'}"


# Pull the selected node(s) out of their chain: whatever fed a node now
# feeds what it fed, so the chain stays connected - and the node itself
# sits loose just below, unconnected, ready to be reused or deleted.
_PULL_OUT_LUA = r"""
local comp = comp or fusion:GetCurrentComp()
local tools = comp:GetToolList(true)
local flow = comp.CurrentFrame and comp.CurrentFrame.FlowView
local n = 0
comp:StartUndo("Pull out node")
for _, tool in pairs(tools) do
    local main_in = tool:FindMainInput(1)
    local main_out = tool:FindMainOutput(1)
    local source = main_in and main_in:GetConnectedOutput() or nil
    if main_out then
        for _, input in pairs(main_out:GetConnectedInputs() or {}) do
            input:ConnectTo(source)
        end
    end
    if main_in then main_in:ConnectTo(nil) end
    if flow then
        local p = flow:GetPosTable(tool)
        if p and p[1] then flow:SetPos(tool, p[1], p[2] + 1.5) end
    end
    n = n + 1
end
comp:EndUndo(true)
comp:SetData("ClipseResult", tostring(n))
"""


def pull_out_nodes(resolve):
    """Fusion page: takes the selected node(s) out of the chain, keeping
    the chain connected (see _PULL_OUT_LUA). One Fusion undo step."""
    try:
        if resolve.GetCurrentPage() != "fusion":
            return "Pull out needs the Fusion page"
        comp = resolve.Fusion().GetCurrentComp()
    except Exception as e:
        return f"Couldn't reach Fusion: {e}"
    if comp is None:
        return "No Fusion composition open."
    try:
        result = str(run_lua(comp, _PULL_OUT_LUA) or "")
    except Exception as e:
        return f"Couldn't pull the node out: {e}"
    if result == "0":
        return "Select a node in Fusion first."
    if result.isdigit():
        return f"Pulled {result} node{'s' if result != '1' else ''} out of the chain."
    return f"Pull out: {result or 'nothing happened'}"


def load_comp(resolve, comp_path, timeline=None, try_load_comp_first=True):
    """Imports a saved .comp file onto the clip under the playhead via
    TimelineItem.ImportFusionComp(path) — documented in DaVinci Resolve's
    own official Scripting API reference: "Imports a Fusion composition
    from given file path by creating and adding a new composition for
    the item." This replaced two earlier guesses (Fusion.LoadComp,
    Comp.Paste) that both turned out wrong. try_load_comp_first is kept
    as a parameter for backward compatibility but no longer used.

    A clip can have several Fusion compositions attached to it — import
    alone doesn't tell Fusion to actually DISPLAY the new one, which is
    likely why it looked like nothing happened even on a successful
    import. LoadFusionCompByName explicitly activates it afterward, found
    by diffing the clip's composition name list before and after."""
    if timeline is None:
        return "No timeline available to find a target clip."
    try:
        clip = timeline.GetCurrentVideoItem()
    except Exception as e:
        return f"Couldn't get the clip under the playhead: {e}"
    if clip is None:
        return "No clip under the playhead to import a Fusion composition onto."

    try:
        names_before = set(clip.GetFusionCompNameList() or [])
    except Exception:
        names_before = set()

    try:
        new_comp = clip.ImportFusionComp(comp_path)
    except Exception as e:
        return f"ImportFusionComp('{comp_path}') failed: {e}"
    if new_comp is None:
        return (f"ImportFusionComp('{os.path.basename(comp_path)}') returned nothing — "
                f"the file may not be a valid Fusion composition, or the clip already has "
                f"one with a conflicting name.")

    activated_msg = ""
    try:
        # Resolve names an imported comp after its source file — try
        # that directly first, since it also correctly handles
        # re-importing a file whose name already existed on the clip
        # (which the old before/after diff approach missed entirely).
        expected_name = os.path.splitext(os.path.basename(comp_path))[0]
        activated = clip.LoadFusionCompByName(expected_name)
        print(f"[fusion] activating '{expected_name}' (from filename) -> {activated}")
        if activated:
            activated_msg = f" and activated it ('{expected_name}')"
        else:
            # Fallback: maybe Resolve named it something else — check
            # for a name that's new since the import.
            names_after = set(clip.GetFusionCompNameList() or [])
            new_names = names_after - names_before
            if new_names:
                new_name = next(iter(new_names))
                activated = clip.LoadFusionCompByName(new_name)
                print(f"[fusion] activating '{new_name}' (new since import) -> {activated}")
                activated_msg = f" and activated it ('{new_name}')" if activated else \
                    f" but couldn't activate it ('{new_name}' -> LoadFusionCompByName returned falsy)"
            else:
                activated_msg = f" but couldn't activate it (tried '{expected_name}', no new comp names found)"
    except Exception as e:
        print(f"[fusion] couldn't activate the newly-imported comp: {e}")

    try:
        resolve.OpenPage("fusion")
    except Exception as e:
        print(f"Couldn't switch to the Fusion page: {e}")

    return f"Imported '{os.path.basename(comp_path)}' via TimelineItem.ImportFusionComp(){activated_msg}."


# -- Switching projects — high confidence, documented API
# (ProjectManager.GetProjectListInCurrentFolder / LoadProject). Only
# lists projects in the project manager's CURRENT folder — a project
# filed in a different folder in your project library won't show up. --
def list_other_projects(project_manager, current_project_name):
    try:
        names = project_manager.GetProjectListInCurrentFolder() or []
    except Exception:
        return []
    return [n for n in names if n != current_project_name]


def format_relative_time(unix_timestamp):
    """'3d ago' / '5h ago' / '12m ago' / 'now' — largest non-zero unit,
    per request. Pure function, no Resolve dependency."""
    if unix_timestamp is None:
        return None
    delta = max(0, time.time() - unix_timestamp)
    days = int(delta // 86400)
    if days >= 1:
        return f"{days}d ago"
    hours = int(delta // 3600)
    if hours >= 1:
        return f"{hours}h ago"
    minutes = int(delta // 60)
    if minutes >= 1:
        return f"{minutes}m ago"
    return "now"


def age_color_category(unix_timestamp, medium_days=7, old_days=30):
    """'recent' (0 to medium_days), 'medium' (up to old_days), or 'old'
    (beyond that) — used to color-code the Created/Modified values by
    age. Both thresholds are user-adjustable (Settings -> Appearance)."""
    if unix_timestamp is None:
        return None
    days = max(0, time.time() - unix_timestamp) / 86400
    if days <= medium_days:
        return "recent"
    if days <= old_days:
        return "medium"
    return "old"


def get_project_timestamps(project_manager, project_name):
    """Best-effort (created_ts, modified_ts) for one project, or
    (None, None) if unavailable. Confirmed working for "Disk" database
    projects stored as directory bundles (the common case): "created" is
    the oldest file's mtime found inside the bundle, "modified" is the
    newest — Linux has no true file-creation time via stat(), and a
    directory's own mtime often doesn't change when files inside it are
    edited (only when entries are added/removed), so scanning the actual
    files is the closest available proxy for either value. Prints exactly
    what it tried so this stays diagnosable rather than silently wrong."""
    try:
        db_info = project_manager.GetCurrentDatabase() or {}
    except Exception as e:
        print(f"[project] couldn't read database info: {e}")
        return None, None

    db_type = db_info.get("DbType")
    print(f"[project] database info: {db_info}")
    if db_type != "Disk":
        print(f"[project] DbType is '{db_type}', not 'Disk' — no filesystem fallback "
              f"is possible for '{project_name}'; timestamps unavailable.")
        return None, None

    search_roots = [
        os.path.expanduser("~/.local/share/DaVinciResolve"),
        os.path.expanduser("~/Library/Application Support/Blackmagic Design/DaVinci Resolve"),
        os.path.expandvars(r"%APPDATA%\Blackmagic Design\DaVinci Resolve"),
    ]
    matches = []
    for root in search_roots:
        if not os.path.isdir(root):
            continue
        for dirpath, dirs, files in os.walk(root):
            for dname in dirs:
                if dname.lower() == project_name.lower():
                    matches.append(os.path.join(dirpath, dname))
            for fname in files:
                stem = os.path.splitext(fname)[0]
                if stem.lower() == project_name.lower():
                    matches.append(os.path.join(dirpath, fname))
    print(f"[project] filesystem search for '{project_name}' found: {matches or '(nothing)'}")
    if not matches:
        return None, None

    path = matches[0]
    try:
        if os.path.isdir(path):
            # A directory's own mtime often doesn't change when files
            # *inside* it are edited (only when entries are added/removed),
            # which is why created/modified were coming out identical —
            # scan the actual files instead. Linux has no true
            # "creation time" via stat(), so the oldest file's timestamp
            # is used as the closest available proxy for "created", and
            # the newest file's timestamp for "modified".
            timestamps = []
            for dirpath, _dirs, files in os.walk(path):
                for fname in files:
                    try:
                        timestamps.append(os.stat(os.path.join(dirpath, fname)).st_mtime)
                    except OSError:
                        continue
            if not timestamps:
                stat = os.stat(path)
                return stat.st_mtime, stat.st_mtime
            return min(timestamps), max(timestamps)
        else:
            stat = os.stat(path)
            created = getattr(stat, "st_birthtime", stat.st_ctime)
            return created, stat.st_mtime
    except Exception as e:
        print(f"[project] couldn't stat '{path}': {e}")
        return None, None


def switch_project(project_manager, name):
    try:
        ok = project_manager.LoadProject(name)
        if not ok:
            return f"Resolve couldn't switch to project '{name}' (LoadProject returned falsy)."
        return f"Switched to project '{name}'."
    except Exception as e:
        return f"Couldn't switch to project '{name}': {e}"


# -- Attempting to auto-start playback in Resolve's Source Viewer —
# LOW CONFIDENCE. Resolve's scripting API has no documented call for
# "start playback" on the Source Viewer at all, unlike SetSelectedClip
# (which reliably loads the clip into the viewer, paused at frame 0).
# This is a workaround, not a real API call: simulate a spacebar
# keypress (Resolve's default Play/Pause shortcut) via an OS-level input
# tool. Fragile by nature — depends on Resolve's window actually having
# focus, and on a working key-simulation tool being installed:
#   Linux (Wayland, e.g. Sway): ydotool — needs its daemon + permissions
#     set up separately; this does NOT configure that for you.
#   Linux (X11/XWayland fallback): xdotool
#   macOS: osascript keystroke, requires Accessibility permission
# Off by default (Settings -> General -> "Try to auto-start playback").
def attempt_playback(resolve):
    system = platform.system()
    try:
        if system == "Darwin":
            script = 'tell application "DaVinci Resolve" to activate\ntell application "System Events" to keystroke " "'
            result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=3)
            if result.returncode == 0:
                print("[preview] sent Space to Resolve via osascript (requires Accessibility permission).")
                return True
            print(f"[preview] osascript failed: {result.stderr.strip()}")
            return False

        if system == "Windows":
            print("[preview] auto-play isn't implemented for Windows yet — "
                  "no reliable built-in key-simulation tool to use without adding a new dependency.")
            return False

        import shutil
        if shutil.which("ydotool"):
            result = subprocess.run(["ydotool", "key", "space"], capture_output=True, text=True, timeout=3)
            if result.returncode == 0:
                print("[preview] sent Space via ydotool.")
                return True
            print(f"[preview] ydotool failed (is its daemon running with the right permissions?): "
                  f"{result.stderr.strip()}")
        if shutil.which("xdotool"):
            result = subprocess.run(["xdotool", "key", "space"], capture_output=True, text=True, timeout=3)
            if result.returncode == 0:
                print("[preview] sent Space via xdotool.")
                return True
            print(f"[preview] xdotool failed: {result.stderr.strip()}")

        print("[preview] no working key-simulation tool found (tried ydotool, xdotool) — "
              "auto-play skipped. The clip is still loaded in the Source Viewer, just not playing.")
        return False
    except Exception as e:
        print(f"[preview] auto-play attempt failed: {e}")
        return False


# -- Opening the scripts folder in the OS file manager — trivial, safe. --
def open_folder(path):
    try:
        os.makedirs(path, exist_ok=True)
        system = platform.system()
        if system == "Windows":
            os.startfile(path)
        elif system == "Darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
        return True
    except Exception as e:
        print(f"Couldn't open folder '{path}': {e}")
        return False


def open_terminal(path):
    """Opens a terminal emulator with its working directory set to `path`.
    Uses subprocess's own cwd= parameter rather than each terminal's own
    (wildly inconsistent) CLI flag for it — most terminal emulators start
    their shell in the process's own working directory when launched
    plainly, so this works across terminals without needing to special-
    case each one's argument syntax. $TERMINAL is tried first if set,
    then a list of common Linux terminal emulators."""
    try:
        os.makedirs(path, exist_ok=True)
    except Exception:
        pass
    system = platform.system()
    try:
        if system == "Darwin":
            subprocess.Popen(["open", "-a", "Terminal", path])
            return True
        if system == "Windows":
            subprocess.Popen(["cmd.exe"], cwd=path, creationflags=subprocess.CREATE_NEW_CONSOLE)
            return True

        import shutil
        candidates = []
        env_term = os.environ.get("TERMINAL")
        if env_term:
            candidates.append(env_term)
        candidates += ["ghostty", "kitty", "alacritty", "wezterm", "gnome-terminal",
                        "konsole", "xfce4-terminal", "foot", "xterm"]
        for name in candidates:
            exe = shutil.which(name)
            if exe:
                subprocess.Popen([exe], cwd=path)
                print(f"Opened a terminal ({name}) at {path}")
                return True
        print(f"Couldn't find a terminal emulator to open (tried: {', '.join(c for c in candidates if c)}). "
              f"Set the TERMINAL environment variable to your terminal's command, or open one manually at: {path}")
        return False
    except Exception as e:
        print(f"Couldn't open a terminal at '{path}': {e}")
        return False
