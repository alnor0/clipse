"""Animation on the Fusion page without touching a keyframe.

"Animate in: Slide from the left" puts a node after the selected one and
gives it the keyframes - at the start of the clip, the right length, with
easing so it lands softly. "Animate out" is the same at the end. And for
keyframes that are already there: smooth them, turn them round, or take
them off again (the value stays as it is right now).

How it works: what to animate is worked out here (plain numbers, tested
without Resolve), then a short Lua script sets it in Fusion - one undo step.
Tried in Resolve 21.1.1."""

# Parked on 2026-10-13 on request ("shove it away for now"): the ready-made in / out moves
# and the "Keyframes: ..." changes are not offered anywhere while this is True. Everything is
# still here and still tested - set it to False to bring them back (> animate, the Animate tile).
PARKED = True

# Easing as the two handles of a curve between two keyframes, the way CSS
# writes it: (x1, y1, x2, y2), each a share of the way from the first
# keyframe to the second. "out" arrives softly, "in" leaves softly, "pop"
# goes a little too far and settles.
EASINGS = {
    "out": (0.16, 1.0, 0.3, 1.0),
    "in": (0.7, 0.0, 0.84, 0.0),
    "both": (0.45, 0.0, 0.55, 1.0),
    "pop": (0.34, 1.56, 0.64, 1.0),
    "wind_up": (0.36, 0.0, 0.66, -0.56),  # "pop" backwards: a small step back before it goes
}

# key: (name coming in, name going out, the node that does it, fixed settings on that node,
#       [(input, "X"/"Y" for a position else None, the value away, the value at rest, easing coming in)])
ANIMATIONS = {
    "fade": ("Fade", "Fade", "BrightnessContrast", {"Alpha": 1}, [("Gain", None, 0.0, 1.0, "both")]),
    "slide_left": ("Slide from the left", "Slide to the left", "Transform", {}, [("Center", "X", -0.5, 0.5, "out")]),
    "slide_right": ("Slide from the right", "Slide to the right", "Transform", {}, [("Center", "X", 1.5, 0.5, "out")]),
    "slide_up": ("Rise from below", "Sink down", "Transform", {}, [("Center", "Y", -0.5, 0.5, "out")]),
    "slide_down": ("Drop from above", "Fly up", "Transform", {}, [("Center", "Y", 1.5, 0.5, "out")]),
    "grow": ("Grow", "Shrink", "Transform", {}, [("Size", None, 0.0, 1.0, "out")]),
    "pop": ("Pop", "Pop", "Transform", {}, [("Size", None, 0.0, 1.0, "pop")]),
    "spin": ("Spin", "Spin", "Transform", {}, [("Angle", None, -180.0, 0.0, "out"), ("Size", None, 0.0, 1.0, "out")]),
}
DEFAULT_SECONDS = 0.4


def name_of(key, direction):
    return ANIMATIONS[key][0 if direction == "in" else 1]


def ease_keys(t0, v0, t1, v1, ease):
    """Two keyframes with the handles between them: {time: (value, left handle or None, right handle or None)}."""
    x1, y1, x2, y2 = EASINGS[ease]
    dt, dv = t1 - t0, v1 - v0
    return {t0: (v0, None, (t0 + x1 * dt, v0 + y1 * dv)),
            t1: (v1, (t0 + x2 * dt, v0 + y2 * dv), None)}


def frames_for(seconds, fps, first, last):
    """How many frames the animation takes: `seconds` of them, never more than half the clip."""
    return max(1, min(int(round(seconds * fps)), max(1, (last - first) // 2)))


def plan(key, direction, first, last, fps, seconds=DEFAULT_SECONDS):
    """What to set: (node kind, node name, fixed settings, [(input, axis, other axis' value, keyframes)])."""
    _in_name, _out_name, node, fixed, channels = ANIMATIONS[key]
    length = frames_for(seconds, fps, first, last)
    out = []
    for input_name, axis, away, rest, ease in channels:
        if direction == "in":
            keys = ease_keys(first, away, first + length, rest, ease)
        else:  # the same move backwards, at the end: leaving softly (a pop winds up first)
            leaving = {"out": "in", "pop": "wind_up"}.get(ease, ease)
            keys = ease_keys(last - length, rest, last, away, leaving)
        out.append((input_name, axis, 0.5 if axis else None, keys))
    label = key.title().replace("_", "") + direction.title()  # the node's name: "SlideLeftIn", "PopOut"
    return node, label, dict(fixed), out


# -- as Lua --
def _num(value):
    return repr(round(float(value), 6))


def _lua_keys(keys):
    parts = []
    for t in sorted(keys):
        value, left, right = keys[t]
        fields = [_num(value)]
        if left:
            fields.append(f"LH = {{{_num(left[0])}, {_num(left[1])}}}")
        if right:
            fields.append(f"RH = {{{_num(right[0])}, {_num(right[1])}}}")
        parts.append(f"[{_num(t)}] = {{{', '.join(fields)}}}")
    return "{" + ", ".join(parts) + "}"


def animate_lua(label, fixed, channels):
    """Names the active node and gives it the keyframes of `channels`."""
    lines = ["local function run()",
             "local tool = comp.ActiveTool",
             'if not tool then return "no node" end',
             f'tool:SetAttrs({{TOOLS_Name = "{label}", TOOLB_NameSet = true}})']
    for name, value in fixed.items():
        lines.append(f"tool.{name} = {_num(value)}")
    for input_name, axis, other, keys in channels:
        if axis:  # a position: one spline for X, one value for Y (or the other way round)
            still = "Y" if axis == "X" else "X"
            lines += [f"tool.{input_name} = XYPath({{}})",
                      f"local path = tool.{input_name}:GetConnectedOutput():GetTool()",
                      f"path.{axis} = BezierSpline({{}})",
                      f"path.{axis}:GetConnectedOutput():GetTool():SetKeyFrames({_lua_keys(keys)}, true)",
                      f"path.{still} = {_num(other)}"]
        else:
            lines += [f"tool.{input_name} = BezierSpline({{}})",
                      f"tool.{input_name}:GetConnectedOutput():GetTool():SetKeyFrames({_lua_keys(keys)}, true)"]
    lines += ['return "ok"', "end", "local ok, result = pcall(run)",
              'comp:SetData("ClipseResult", ok and result or ("error: " .. tostring(result)))']
    return "\n".join(lines)


# The splines of the selected nodes (a position's X and Y count too), then one of:
#   smooth  - every stretch between two keyframes eases in and out
#   reverse - the same keyframes, back to front
#   remove  - no animation any more; each value stays what it is on this frame
_SPLINES_LUA = r"""
local function splines_of(tool)
    local found = {}
    local function look(owner)
        for _, inp in pairs(owner:GetInputList() or {}) do
            local out = inp:GetConnectedOutput()
            local mod = out and out:GetTool() or nil
            if mod then
                local id = mod:GetAttrs().TOOLS_RegID
                if id == "BezierSpline" then
                    found[#found + 1] = {input = inp, spline = mod}
                elseif id == "XYPath" or id == "PolyPath" then
                    found[#found + 1] = {input = inp, path = mod}
                    look(mod)
                end
            end
        end
    end
    look(tool)
    return found
end
local function times_of(keys)
    local times = {}
    for t, _ in pairs(keys) do times[#times + 1] = t end
    table.sort(times)
    return times
end
"""

_EXISTING_LUA = r"""
local WHAT = %s
""" + _SPLINES_LUA + r"""
local tools = comp:GetToolList(true)
local changed, nodes = 0, 0
comp:Lock()
comp:StartUndo("Animation: " .. WHAT)
for _, tool in pairs(tools) do
    nodes = nodes + 1
    local found = splines_of(tool)
    if WHAT == "remove" then
        for _, f in ipairs(found) do
            if f.input:GetTool() == tool then  -- the node's own inputs; what hangs under a path goes with it
                local now = tool:GetInput(f.input.ID, comp.CurrentTime)
                f.input:ConnectTo(nil)
                tool:SetInput(f.input.ID, now)
                changed = changed + 1
            end
        end
    else
        for _, f in ipairs(found) do
            if f.spline then
                local keys = f.spline:GetKeyFrames()
                local times = times_of(keys)
                if #times >= 2 then
                    local new = {}
                    if WHAT == "smooth" then
                        for i, t in ipairs(times) do new[t] = {keys[t][1]} end
                        for i = 1, #times - 1 do
                            local a, b = times[i], times[i + 1]
                            local dt = b - a
                            new[a].RH = {a + dt * 0.45, keys[a][1]}
                            new[b].LH = {a + dt * 0.55, keys[b][1]}
                        end
                    else  -- reverse
                        local first, last = times[1], times[#times]
                        for _, t in ipairs(times) do
                            local k, at = keys[t], first + last - t
                            new[at] = {k[1]}
                            if k.RH then new[at].LH = {first + last - k.RH[1], k.RH[2]} end
                            if k.LH then new[at].RH = {first + last - k.LH[1], k.LH[2]} end
                        end
                    end
                    f.spline:SetKeyFrames(new, true)
                    changed = changed + 1
                end
            end
        end
    end
end
comp:EndUndo(true)
comp:Unlock()
comp:SetData("ClipseResult", tostring(nodes) .. " " .. tostring(changed))
"""


def clip_range(comp):
    """(first frame, last frame, frames per second) of the composition - where "in" starts and "out" ends."""
    attrs = comp.GetAttrs() or {}
    first = attrs.get("COMPN_RenderStart", attrs.get("COMPN_GlobalStart", 0))
    last = attrs.get("COMPN_RenderEnd", attrs.get("COMPN_GlobalEnd", first))
    try:
        fps = float(comp.GetPrefs("Comp.FrameFormat.Rate") or 0) or 24.0
    except Exception:
        fps = 24.0
    return int(first), int(last), fps


def animate_comp(comp, key, direction, seconds=DEFAULT_SECONDS, add_tool=None):
    """Adds the animation after the selected node of `comp`. (worked, message)."""
    from . import scripts_fusion
    add_tool = add_tool or scripts_fusion.add_tool_after_selected
    first, last, fps = clip_range(comp)
    if last - first < 2:
        return False, "This composition is too short to animate"
    node, label, fixed, channels = plan(key, direction, first, last, fps, seconds)
    title = f"Animate {direction}: {name_of(key, direction)}"
    comp.StartUndo(title)
    try:
        result = add_tool(comp, node, title, undo=False)
        if result == "unknown tool" or str(result or "").startswith("error:"):
            return False, f"{title}: Fusion couldn't add the {node} node ({result})"
        done = scripts_fusion.run_lua(comp, animate_lua(label, fixed, channels))
    finally:
        comp.EndUndo(True)
    if done != "ok":
        print(f"[animate] {title}: {done}")
        return False, f"{title}: the node is there, but Fusion didn't take the keyframes (Ctrl+Z takes it away)"
    length = frames_for(seconds, fps, first, last)
    where = "at the start" if direction == "in" else "at the end"
    return True, f"{title}: {length} frames {where}" + (f" - {result}" if result else "")


def change_existing(comp, what):
    """smooth / reverse / remove the keyframes of the selected nodes. (worked, message)."""
    from .scripts_fusion import run_lua
    nodes, _, changed = str(run_lua(comp, _EXISTING_LUA.replace("%s", f'"{what}"', 1)) or "0 0").partition(" ")
    if nodes == "0":
        return False, "Select the animated node in Fusion first"
    if changed in ("", "0"):
        return False, "The selected node has no keyframes"
    done = {"smooth": "Smoothed", "reverse": "Turned round", "remove": "Removed"}[what]
    return True, f"{done} {changed} animated setting{'s' if changed != '1' else ''}"


# Selects one node by name, so it's the one in the Inspector.
_SELECT_LUA = r"""
local tool = comp:FindTool(%s)
if tool then
    comp:SetActiveTool(tool)
    local flow = comp.CurrentFrame and comp.CurrentFrame.FlowView
    if flow then flow:Select() flow:Select(tool, true) end
end
comp:SetData("ClipseResult", tool and "ok" or "gone")
"""


# The selected nodes switched off (passed through, as Ctrl+P does in Fusion) - or back on.
_ON_OFF_LUA = r"""
local names, off = {}, 0
for _, tool in pairs(comp:GetToolList(true)) do
    local now = tool:GetAttrs().TOOLB_PassThrough and true or false
    tool:SetAttrs({TOOLB_PassThrough = not now})
    names[#names + 1] = tool:GetAttrs().TOOLS_Name
    if not now then off = off + 1 end
end
comp:SetData("ClipseResult", tostring(#names) .. " " .. tostring(off) .. " " .. table.concat(names, ", "))
"""


def toggle_nodes_comp(comp):
    from .scripts_fusion import run_lua
    comp.StartUndo("Node on / off")
    try:
        answer = run_lua(comp, _ON_OFF_LUA)
    finally:
        comp.EndUndo(True)
    count, off, names = (str(answer or "0 0 ").split(" ", 2) + ["", ""])[:3]
    if count in ("0", ""):
        return False, "Select a node in Fusion first"
    return True, f"{names}: " + ("off" if off == count else "on" if off == "0" else "switched over")


# Before / after: every effect off, so the viewer shows the clip as it came in - and the same key puts back the ones
# it switched off (kept in the composition under _BEFORE_KEY, so a node you'd switched off yourself stays off, and
# it still knows after a restart). The ends - MediaIn, Loader, MediaOut, Saver - and notes stay as they are, and
# so does what's inside a group (the group itself is switched).
_BEFORE_KEY = "ClipseBeforeAfter"
_BEFORE_AFTER_LUA = r"""
local KEY = "%s"
local KEEP = {MediaIn = true, Loader = true, MediaOut = true, Saver = true, Note = true, Underlay = true}
local kept = comp:GetData(KEY)
if kept and kept ~= "" then
    local n = 0
    for name in string.gmatch(kept, "[^\n]+") do
        local tool = comp:FindTool(name)
        if tool then tool:SetAttrs({TOOLB_PassThrough = false}); n = n + 1 end
    end
    comp:SetData(KEY, "")
    comp:SetData("ClipseResult", "after " .. n)
else
    local flow, names = comp.CurrentFrame and comp.CurrentFrame.FlowView, {}
    for _, tool in pairs(comp:GetToolList(false)) do
        local a = tool:GetAttrs()
        local placed = not flow or flow:GetPosTable(tool) ~= nil  -- (splines and paths have no place: not nodes)
        if placed and not KEEP[a.TOOLS_RegID] and not a.TOOLB_PassThrough and not a.TOOLH_GroupParent then
            tool:SetAttrs({TOOLB_PassThrough = true})
            names[#names + 1] = a.TOOLS_Name
        end
    end
    comp:SetData(KEY, table.concat(names, "\n"))
    comp:SetData("ClipseResult", "before " .. #names)
end
""" % _BEFORE_KEY


def before_after_comp(comp):
    """Before / after: (worked, message)."""
    from .scripts_fusion import run_lua
    comp.StartUndo("Before / after")
    try:
        answer = run_lua(comp, _BEFORE_AFTER_LUA)
    finally:
        comp.EndUndo(True)
    which, count = (str(answer or "").split(" ") + ["", ""])[:2]
    n = int(count) if count.isdigit() else 0
    if which == "before":
        return (True, f"Before - {n} node{'s' if n != 1 else ''} off") if n else \
            (False, "Nothing to switch off - no effects in this composition")
    if which == "after":
        return True, f"After - {n} node{'s' if n != 1 else ''} back on"
    return False, "Fusion didn't answer"


def nodes_in(comp):
    """[(name, kind)] of the nodes in `comp` - the ones you see in the node editor."""
    from .fusion_graph import _MODIFIERS
    out = []
    for tool in (comp.GetToolList(False) or {}).values():
        try:
            attrs = tool.GetAttrs() or {}
        except Exception:
            continue
        name, kind = str(attrs.get("TOOLS_Name") or ""), str(attrs.get("TOOLS_RegID") or "")
        if name and kind not in _MODIFIERS:
            out.append((name, kind))
    return out


def select_node_comp(comp, name):
    from .scripts_fusion import run_lua
    if run_lua(comp, _SELECT_LUA % ("[==[" + name + "]==]")) != "ok":
        return False, f"{name} isn't in this composition any more"
    return True, f"Selected {name}"


def _open_comp(resolve):
    try:
        if resolve.GetCurrentPage() != "fusion":
            return None, "Animating needs the Fusion page"
        comp = resolve.Fusion().GetCurrentComp()
    except Exception as e:
        return None, f"Couldn't reach Fusion: {e}"
    return (comp, "") if comp is not None else (None, "No Fusion composition open")


def animate(resolve, key, direction, seconds=DEFAULT_SECONDS):
    comp, problem = _open_comp(resolve)
    return animate_comp(comp, key, direction, seconds) if comp is not None else (False, problem)


def existing(resolve, what):
    comp, problem = _open_comp(resolve)
    return change_existing(comp, what) if comp is not None else (False, problem)


def nodes(resolve):
    """The open composition's nodes, or [] away from the Fusion page."""
    comp, _problem = _open_comp(resolve)
    try:
        return nodes_in(comp) if comp is not None else []
    except Exception as e:
        print(f"[fusion] couldn't list the nodes: {e}")
        return []


def select_node(resolve, name):
    comp, problem = _open_comp(resolve)
    if comp is None:
        return False, problem.replace("Animating needs", "Finding a node needs")
    return select_node_comp(comp, name)


def before_after(resolve):
    comp, problem = _open_comp(resolve)
    if comp is None:
        return False, problem.replace("Animating needs", "Before / after needs")
    return before_after_comp(comp)


def toggle_nodes(resolve):
    comp, problem = _open_comp(resolve)
    if comp is None:
        return False, problem.replace("Animating needs", "Switching a node off needs")
    return toggle_nodes_comp(comp)
