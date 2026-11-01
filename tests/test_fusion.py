"""The Lua that Clipse runs inside Fusion - inserting nodes, ready-made
animations, keyframe steps, expressions - run under LuaJIT against a stand-in
composition (fusion_mock.lua). It isn't Fusion: it shows the scripts run and
what they leave behind, not that Fusion agrees.   python3 tests/test_fusion.py"""
import os
import shutil
import subprocess
import tempfile

import _setup
from clipse import fusion_animate as fa
from clipse import fusion_expressions as fx
from clipse import scripts_fusion as sf

LUA = shutil.which("luajit") or shutil.which("lua5.1")
if LUA is None:
    print("skipped - no LuaJIT here to run Fusion's scripts with")
    raise SystemExit(0)
fails = 0


def check(what, ok):
    global fails
    print(("ok   " if ok else "FAIL ") + what)
    fails += not ok


class Recorder:
    """Takes the place of a composition on the Python side and keeps the script it's handed."""
    def __init__(self):
        self.scripts = []
    def Execute(self, lua): self.scripts.append(lua)
    def SetData(self, key, value): pass
    def GetData(self, key): return None
    def StartUndo(self, title): pass
    def EndUndo(self, keep): pass
    def GetAttrs(self): return {"COMPN_RenderStart": 0.0, "COMPN_RenderEnd": 119.0}
    def GetPrefs(self, key): return 60.0


def script(call):
    rec = Recorder()
    try:
        call(rec)
    except Exception:
        pass  # (the Python side has no answer to read; the script is what's wanted)
    return rec.scripts[-1]


def lua_string(text):
    return "[======[" + text + "]======]"


insert_transform = script(lambda c: sf.add_tool_after_selected(c, "Transform", "Add Transform"))
insert_text = script(lambda c: sf.add_tool_after_selected(c, "TextPlus", "Add Text+"))
insert_quiet = script(lambda c: sf.add_tool_after_selected(c, "Transform", "Animate", undo=False))
insert_fade = script(lambda c: sf.add_tool_after_selected(c, "BrightnessContrast", "Animate", undo=False))
insert_group = sf.macro_lua("/nowhere/dynamic_arrow.setting", "dynamic_arrow")
insert_out = script(lambda c: sf.add_tool_after_selected(c, "MediaOut", "Add MediaOut"))
slide = fa.animate_lua(*[fa.plan("slide_left", "in", 0, 119, 60.0)[i] for i in (1, 2, 3)])
fade = fa.animate_lua(*[fa.plan("fade", "out", 0, 119, 60.0)[i] for i in (1, 2, 3)])
smooth, reverse, remove = (script(lambda c, what=what: fa.change_existing(c, what)) for what in ("smooth", "reverse", "remove"))
select = script(lambda c: fa.select_node_comp(c, "Transform2"))
wiggle, timer, fade_in = fx.BY_KEY["wiggle_rotation"], fx.BY_KEY["timer"], fx.BY_KEY["fade_in"]
look_angle = script(lambda c: fx.look(c, wiggle))
look_fade = script(lambda c: fx.look(c, fade_in))
put_angle = script(lambda c: fx._put(c, "Angle", wiggle["code"], {}))
swing = fx.BY_KEY["swing"]
put_sliders = script(lambda c: fx._put(c, "Angle", fx.code(swing, {"degrees": 20}), {},
                                       [("SwingDegrees", "Swing: degrees", 20, 0, 60), ("SwingSlow", "Swing: how slow", 10, 2, 60)],
                                       fx.control_code(swing)))
on_off = script(lambda c: fa.toggle_nodes_comp(c))
before_after = script(lambda c: fa.before_after_comp(c))
put_timer = script(lambda c: fx._put(c, "StyledText", timer["code"], {}))
put_gain = script(lambda c: fx._put(c, "Gain", fade_in["code"], {"Alpha": 1}))
name_of = fx._NAME_LUA

program = f"""
dofile({lua_string(str(_setup.ROOT / "tests" / "fusion_mock.lua"))})
local function say(label, value) print(label .. "\\t" .. tostring(value)) end
local a = mock.add("MediaIn", 0, 0)
local b = mock.add("MediaOut", 5, 0)
mock.connect(a, b, "Input")
comp:SetActiveTool(a)
for i = 1, 5 do
    say("insert" .. i, mock.run({lua_string(insert_transform)}))
    say("row" .. i, mock.row())
end
say("chain", mock.chain())
say("text", mock.run({lua_string(insert_text)}))
say("row_text", mock.row())
say("chain_text", mock.chain())

comp:SetActiveTool(a)
say("slide_node", mock.run({lua_string(insert_quiet)}))
say("slide", mock.run({lua_string(slide)}))
local s = mock.tool("SlideLeftIn")
say("slide_keys", s and mock.keys(s, "Center", "X") or "no such node")
say("slide_row", mock.row())
say("fade_node", mock.run({lua_string(insert_fade)}))
say("fade", mock.run({lua_string(fade)}))
local f = mock.tool("FadeOut")
say("fade_keys", f and mock.keys(f, "Gain") or "no such node")
say("fade_alpha", f and mock.value(f, "Alpha") or "?")

comp:SetActiveTool(s)
say("smooth", mock.run({lua_string(smooth)}))
say("reverse", mock.run({lua_string(reverse)}))
say("reversed_keys", mock.keys(s, "Center", "X"))
say("remove", mock.run({lua_string(remove)}))
say("still_animated", mock.animated(s, "Center"))

comp:SetActiveTool(mock.tool("Transform1"))
say("look_has", mock.run({lua_string(look_angle)}))
say("put", mock.run({lua_string(put_angle)}))
say("expression", mock.expression(mock.tool("Transform1"), "Angle"))
say("look_fade_on_transform", mock.run({lua_string(look_fade)}))
comp:SetActiveTool(mock.tool("Merge1"))
say("look_fade_on_merge", mock.run({lua_string(look_fade)}))
comp:SetActiveTool(mock.tool("TextPlus1"))
say("put_timer", mock.run({lua_string(put_timer)}))
comp:SetActiveTool(f)
say("put_gain", mock.run({lua_string(put_gain)}))
comp:SetActiveTool(mock.tool("Transform3"))
say("put_sliders", mock.run({lua_string(put_sliders)}))
say("slider_code", mock.expression(mock.tool("Transform3"), "Angle"))
say("slider_value", mock.value(mock.tool("Transform3"), "SwingDegrees"))
say("off", mock.run({lua_string(on_off)}))
say("is_off", tostring(mock.tool("Transform3"):GetAttrs().TOOLB_PassThrough))
say("on", mock.run({lua_string(on_off)}))
mock.tool("Transform2"):SetAttrs({{TOOLB_PassThrough = true}})
say("before", mock.run({lua_string(before_after)}))
local all_off, ends_on = true, true
for _, t in ipairs(comp:GetToolList(false)) do
    local a = t:GetAttrs()
    local is_end = a.TOOLS_RegID == "MediaIn" or a.TOOLS_RegID == "MediaOut"
    if is_end and a.TOOLB_PassThrough then ends_on = false end
    if not is_end and not a.TOOLB_PassThrough then all_off = false end
end
say("before_state", tostring(all_off) .. " " .. tostring(ends_on))
say("after", mock.run({lua_string(before_after)}))
say("after_state", tostring(mock.tool("Transform1"):GetAttrs().TOOLB_PassThrough) .. " "
    .. tostring(mock.tool("Transform2"):GetAttrs().TOOLB_PassThrough))
mock.tool("Transform2"):SetAttrs({{TOOLB_PassThrough = false}})
comp:SetActiveTool(nil)
say("look_none", mock.run({lua_string(look_angle)}))
say("select", mock.run({lua_string(select)}))
say("selected", comp.ActiveTool and comp.ActiveTool:GetAttrs().TOOLS_Name)
mock.run({lua_string(name_of)})
say("name", comp:GetData("ClipseResult"))
comp:SetActiveTool(mock.tool("Merge1"))
say("chain_before_out", mock.chain())
say("out2", mock.run({lua_string(insert_out)}))
say("wires_out", mock.wires())
say("chain_after_out", mock.chain())
mock.pictures = {{ShowThumbnails = true, ForceSource = true, AspectTilePics = true}}
comp:SetActiveTool(mock.tool("Transform1"))
say("text_pictures", mock.run({lua_string(insert_text)}))
say("row_text_pictures", mock.row())
-- a macro that is a group (dynamic_arrow): Fusion lists the nodes inside it too, with no place in the view
bmd.readfile = function() return {{}} end
function comp:Paste(_)
    local group = mock.add("GroupOperator", 0, 0)
    mock.connect(mock.inside(group, "Background"), mock.inside(group, "Transform"), "Input")
end
comp:SetActiveTool(mock.tool("Transform1"))
say("group", mock.run({lua_string(insert_group)}))
say("group_wires", mock.wires())
say("group_chain", mock.chain())
-- nothing selected: the node is only placed - under the rest, wired to nothing
comp:SetActiveTool(nil)
local wires_before = mock.wires()
say("loose", mock.run({lua_string(insert_transform)}))
say("loose_wires_same", tostring(mock.wires() == wires_before))
local loose = comp.ActiveTool
local lp = loose and comp.CurrentFrame.FlowView:GetPosTable(loose)
local lowest, leftmost = -math.huge, math.huge
for _, t in ipairs(comp:GetToolList(false)) do
    local p = t ~= loose and comp.CurrentFrame.FlowView:GetPosTable(t)
    if p then lowest, leftmost = math.max(lowest, p[2]), math.min(leftmost, p[1]) end
end
say("loose_place", lp and (tostring(lp[1] == leftmost) .. " " .. tostring(lp[2] > lowest)) or "none")
"""
with tempfile.NamedTemporaryFile("w", suffix=".lua", delete=False) as f:
    f.write(program)
done = subprocess.run([LUA, f.name], capture_output=True, text=True, timeout=30)
os.unlink(f.name)
if done.returncode != 0:
    print(done.stderr.strip()[:600])
got = dict(line.split("\t", 1) for line in done.stdout.splitlines() if "\t" in line)

# -- inserting nodes --
check("the scripts run from start to finish", done.returncode == 0 and "name" in got)
check("a node goes in right after the selected one, wired in between",
      got.get("insert1") == "connected after MediaIn1" and got.get("row1") == "MediaIn1@0 Transform1@1 MediaOut1@5")
check("with room in the row nothing else moves - four nodes fit before MediaOut",
      got.get("row4") == "MediaIn1@0 Transform1@1 Transform2@2 Transform3@3 Transform4@4 MediaOut1@5")
check("with no room left, what follows moves over by one - no further",
      got.get("row5") == "MediaIn1@0 Transform1@1 Transform2@2 Transform3@3 Transform4@4 Transform5@5 MediaOut1@6")
check("...and the chain is still whole",
      got.get("chain") == "MediaOut1<Transform5<Transform4<Transform3<Transform2<Transform1<MediaIn1")
check("a title has no picture going in: it's layered on with a Merge, just above the row",
      got.get("text", "").startswith("layered over") and "TextPlus1@6,-1" in got.get("row_text", "")
      and "Merge1@6 MediaOut1@7" in got.get("row_text", "") and got.get("chain_text", "").startswith("MediaOut1<Merge1<Transform5"))

check("a macro that's a group is wired in as one node - never the nodes inside it",
      got.get("group", "").startswith("layered over Transform1") and "GroupOperator1>" in got.get("group_wires", "")
      and "Transform1>Transform" not in got.get("group_wires", "") and "MediaIn1" in got.get("group_chain", ""))
check("nothing selected: the node is only placed - wired to nothing, under the other nodes, left-aligned with them",
      got.get("loose", "").startswith("placed on its own") and got.get("loose_wires_same") == "true"
      and got.get("loose_place") == "true true")

# -- ready-made animations --
check("with pictures on the tiles (Resolve shows one on every source) a layered title goes two rows up, clear of its Merge",
      got.get("text_pictures", "").startswith("layered over") and "TextPlus2@" in got.get("row_text_pictures", "")
      and got.get("row_text_pictures", "").split("TextPlus2@")[1].split()[0].endswith(",-2"))
check("Animate in: Slide from the left - a Transform after the node, named, with its two keyframes",
      got.get("slide") == "ok" and got.get("slide_keys") == "0=-0.5 24=0.5" and "SlideLeftIn@1" in got.get("slide_row", ""))
check("Animate out: Fade - a Brightness Contrast on the alpha, keyed at the end",
      got.get("fade") == "ok" and got.get("fade_keys") == "95=1 119=0" and got.get("fade_alpha") == "1")

# -- keyframes that are there --
check("smooth / turn round / take off all run, and say how many settings they changed",
      got.get("smooth") == "1 1" and got.get("reverse") == "1 1" and got.get("reversed_keys") == "0=0.5 24=-0.5"
      and got.get("remove") == "1 1" and got.get("still_animated") == "false")

# -- expressions --
check("an expression knows the selected Transform is the right place, and goes on its Angle",
      got.get("look_has") == "has Transform1" and got.get("put") == "ok Transform1" and got.get("expression") == wiggle["code"])
check("a fade belongs on a Merge's Blend - a Transform isn't the place for it",
      got.get("look_fade_on_transform") == "other Transform1" and got.get("look_fade_on_merge") == "has Merge1")
check("text goes on a Text+, a fade on a new Brightness Contrast's Gain",
      got.get("put_timer") == "ok TextPlus1" and got.get("put_gain") == "ok FadeOut")
check("with nothing selected it says so, and which node comes before the end", got.get("look_none", "").startswith("none Merge1"))
check("an expression's numbers become sliders on the node, and the code reads them by name",
      got.get("put_sliders") == "sliders Transform3" and got.get("slider_code") == "SwingDegrees*sin(time/SwingSlow)"
      and got.get("slider_value") == "20")
check("Node off / on switches the selected node off, and back on",
      got.get("off") == "1 1 Transform3" and got.get("is_off") == "true" and got.get("on") == "1 0 Transform3")
check("Before / after: every effect off and the ends left on - then back on, all but the one that was off before",
      got.get("before", "").startswith("before ") and got.get("before_state") == "true true"
      and got.get("after", "").startswith("after ") and got.get("after_state") == "false true")
check("Find a node selects it; Copy node name reads the selected one",
      got.get("select") == "ok" and got.get("selected") == "Transform2" and got.get("name") == "Transform2")

# -- every expression in the library, as far as it can be checked without Fusion --
broken = []
for entry in fx.LIBRARY:
    code = entry["code"]
    test = ("local time, comp = 12, {RenderStart = 0, RenderEnd = 120, GetPrefs = function() return 30 end} "
            "local sin, cos, abs, floor, ceil, min, max = math.sin, math.cos, math.abs, math.floor, math.ceil, math.min, math.max "
            "local function iif(c, a, b) if c then return a else return b end end "
            "local function Point(x, y) return {x, y} end local function Text(s) return s end "
            "local pi = math.pi "
            "local Transform1 = {Center = setmetatable({X = 0.5, Y = 0.5}, {__index = function(t, k) return t end}), Size = 1} "
            f"local v = {code} io.write(type(v))")
    out = subprocess.run([LUA, "-e", test], capture_output=True, text=True, timeout=10)
    want = "string" if entry["target"] == "words" else "table" if entry["target"] == "position" else "number"
    if out.returncode != 0 or out.stdout != want:
        broken.append((entry["key"], (out.stderr or out.stdout).strip()[:90]))
parts = [fx.code_parts(e) for e in fx.LIBRARY]
check("what's yours to change in an expression's code is exactly its sliders' numbers and the node it reads",
      all(text == fx.code(e) and all(text[a:b] == (fx._number(fx.defaults(e)[f]) if f else fx.NAMES_A_NODE) for a, b, f in spans)
          and {f for _a, _b, f in spans if f} == {p["id"] for p in e["params"]} for e, (text, spans) in zip(fx.LIBRARY, parts))
      and [(fx.code(fx.BY_KEY["half_size"])[a:b], f) for a, b, f in fx.code_parts(fx.BY_KEY["half_size"])[1]]
      == [("Transform1", None), ("0.5", "share")])
check("...and the code is cut into lines never inside a number or a name",
      all("".join(text[a:b] for a, b in fx.code_lines(text, n)) == text
          and not any(a > 0 and (text[a - 1].isalnum() or text[a - 1] in "_.") and (text[a].isalnum() or text[a] in "_.")
                      for a, _b in fx.code_lines(text, n))
          for text, _s in parts for n in (24, 40)))
frames, last = (0, 1, 2, 13, 29, 30, 361, 1799, 1800, 22623), 30000
clocks = {"stopwatch": lambda f: fx._stopwatch(f / 30), "countdown_clock": lambda f: fx._stopwatch((last - f) / 30),
          "timer": lambda f: fx.value_at(fx.BY_KEY["timer"], f)}
runs = {}
for key, want in clocks.items():
    test = (f"local comp = {{RenderStart = 0, RenderEnd = {last}, GetPrefs = function() return 30 end}} "
            "local floor = math.floor local function Text(s) return s end "
            f"for _, time in ipairs({{{', '.join(map(str, frames))}}}) do io.write({fx.code(fx.BY_KEY[key])}, ' ') end")
    out = subprocess.run([LUA, "-e", test], capture_output=True, text=True, timeout=10)
    runs[key] = out.stdout.split() == [want(f) for f in frames]
check("the stopwatch: minutes, seconds and hundredths - in Fusion as the preview shows it",
      runs["stopwatch"] and fx._stopwatch(754.12) == "12:34.12" and fx._stopwatch(2 / 30) == "00:00.07")
check("the countdown clock: the same, counting down to 00:00.00 on the last frame",
      runs["countdown_clock"] and fx._stopwatch((last - last) / 30) == "00:00.00")
check("the running timer: minutes and seconds", runs["timer"])
check("the clocks' code is short enough to read: one way to write the time, no slider",
      all(len(fx.BY_KEY[k]["code"]) < 200 and not fx.BY_KEY[k]["params"] for k in clocks) and "timecode" not in fx.BY_KEY)
check(f"all {len(fx.LIBRARY)} expressions are sound Lua and give the kind of value their setting takes" +
      (f": {broken}" if broken else ""), not broken)
check("each says which setting it goes on, and has something to play in the preview",
      all(fx.where(e) and fx.goes_on(e) and fx.samples(e) for e in fx.LIBRARY))

# -- Tidy up nodes --
MOCK = lua_string(str(_setup.ROOT / "tests" / "fusion_mock.lua"))
SCENES = {
    # MediaOut not wired up yet (what the old tidy fell over: it only followed what reaches MediaOut)
    "no_out": """
local out = mock.add("MediaOut", 7.25, 2.009)
local a, b, c = mock.add("MediaIn", 3, 5), mock.add("MediaIn", 9, 1), mock.add("MediaIn", 2, 2)
local m1, m2 = mock.add("Merge", 4, 4), mock.add("Merge", 8, 8)
mock.connect(a, m1, "Background"); mock.connect(m2, m1, "Foreground")
mock.connect(b, m2, "Background"); mock.connect(c, m2, "Foreground")
""",
    "three_merges": """
local i = mock.add("MediaIn", 0, 0); local out = mock.add("MediaOut", 9, 3)
local prev = i
for k = 1, 3 do
    local m = mock.add("Merge", k * 2, k); local f = mock.add("MediaIn", k, 7 - k)
    mock.connect(prev, m, "Background"); mock.connect(f, m, "Foreground"); prev = m
end
mock.connect(prev, out, "Input")
""",
    "branches": """
local i = mock.add("MediaIn", 0, 0); local out = mock.add("MediaOut", 9, 3)
local m1, m2, m3 = mock.add("Merge", 1, 1), mock.add("Merge", 2, 2), mock.add("Merge", 3, 3)
mock.connect(i, m1, "Background"); mock.connect(m1, m2, "Background"); mock.connect(m2, m3, "Background"); mock.connect(m3, out, "Input")
local a1, a2 = mock.add("MediaIn", 5, 5), mock.add("Transform", 5, 6); mock.connect(a1, a2, "Input"); mock.connect(a2, m1, "Foreground")
local b1 = mock.add("TextPlus", 6, 6); mock.connect(b1, m2, "Foreground")
local c1, c2, c3 = mock.add("MediaIn", 7, 7), mock.add("Blur", 7, 8), mock.add("Transform", 7, 9)
mock.connect(c1, c2, "Input"); mock.connect(c2, c3, "Input"); mock.connect(c3, m3, "Foreground")
mock.connect(mock.add("Ellipse", 1, 9), m2, "EffectMask")
""",
    "shared": """
local i = mock.add("MediaIn", 0, 0); local out = mock.add("MediaOut", 9, 3)
local m = mock.add("Merge", 3, 3); local b = mock.add("Blur", 4, 4)
mock.connect(i, m, "Background"); mock.connect(i, b, "Input"); mock.connect(b, m, "Foreground"); mock.connect(m, out, "Input")
""",
    "the_rest": """
mock.lists_modifiers = true
local i = mock.add("MediaIn", 0, 0); local out = mock.add("MediaOut", 9, 3); local t = mock.add("Transform", 4, 4)
mock.connect(i, t, "Input"); mock.connect(t, out, "Input")
t.Center = XYPath({})
mock.add("Note", 20, 20); mock.add("Underlay", 21, 21)
mock.add("Background", 6, 9); mock.add("TextPlus", 2, 9)
local g = mock.add("GroupOperator", 12, 5); local inner = mock.add("Blur", 100, 100); local inner2 = mock.add("Transform", 101, 100)
mock.into(g, inner); mock.into(g, inner2); mock.connect(inner, inner2, "Input")
mock.connect(mock.add("MediaIn", 3, 12), inner, "Input")
local after = mock.add("Merge", 13, 13); mock.connect(inner2, after, "Foreground"); mock.connect(mock.add("Background", 1, 15), after, "Background")
""",
    # Resolve as it comes: every source shows a picture on its tile, which hangs over the row below
    "pictures": """
mock.pictures = {ShowThumbnails = true, ForceSource = true, AspectTilePics = true}
local i = mock.add("MediaIn", 0, 0); local out = mock.add("MediaOut", 9, 3)
local prev = i
for k = 1, 3 do
    local m = mock.add("Merge", k * 2, k); local f = mock.add("MediaIn", k, 7 - k)
    mock.connect(prev, m, "Background"); mock.connect(f, m, "Foreground"); prev = m
end
mock.connect(prev, out, "Input")
local tall = mock.add("Transform", 3, 9); mock.picture(tall, 1080, 1920)
local over = mock.add("Merge", 5, 9); mock.connect(prev, over, "Background"); mock.connect(tall, over, "Foreground")
""",
    # your pictures and a video into one line of Merges: a square logo's tile is taller than the video's
    "mixed_pictures": """
mock.pictures = {ShowThumbnails = true, ForceSource = true, AspectTilePics = true}
local i = mock.add("MediaIn", 0, 0); local out = mock.add("MediaOut", 9, 3)
local prev = i
for k = 1, 3 do
    local m = mock.add("Merge", k * 2, k); local f = mock.add("MediaIn", k, 7 - k)
    if k < 3 then mock.picture(f, 1000, 977) else mock.picture(f, 1920, 1080) end
    mock.connect(prev, m, "Background"); mock.connect(f, m, "Foreground"); prev = m
end
mock.connect(prev, out, "Input")
""",
    "many_layers": """
local i = mock.add("MediaIn", 0, 0); local out = mock.add("MediaOut", 9, 3); local mm = mock.add("MultiMerge", 4, 4)
mock.connect(i, mm, "Background"); mock.connect(mm, out, "Input")
mock.connect(mock.add("TextPlus", 1, 1), mm, "Layer10.Foreground")
mock.connect(mock.add("TextPlus", 1, 2), mm, "Layer2.Foreground")
mock.connect(mock.add("TextPlus", 1, 3), mm, "Layer1.Foreground")
""",
}
RANDOM = """
math.randomseed(SEED)
local made = {}
local kinds = {"MediaIn", "Background", "Transform", "Blur", "Merge", "Merge", "Ellipse", "MultiMerge"}
local slots = {Transform = {"Input", "EffectMask"}, Blur = {"Input", "EffectMask"}, Merge = {"Background", "Foreground", "EffectMask"},
               MediaIn = {"EffectMask"}, Background = {"EffectMask"}, Ellipse = {"EffectMask"},
               MultiMerge = {"Background", "Layer1.Foreground", "Layer2.Foreground", "Layer10.Foreground"}}
for i = 1, math.random(1, 28) do
    local kind = kinds[math.random(#kinds)]
    local t = mock.add(kind, math.random(0, 30), math.random(0, 30))
    for _, slot in ipairs(slots[kind]) do
        if #made > 0 and math.random() < (slot == "EffectMask" and 0.15 or 0.7) then mock.connect(made[math.random(#made)], t, slot) end
    end
    made[#made + 1] = t
end
if math.random() < 0.8 then
    local out = mock.add("MediaOut", math.random(0, 30) + 0.25, math.random(0, 30) + 0.009)
    if math.random() < 0.8 then mock.connect(made[math.random(#made)], out, "Input") end
end
"""
RANDOM_COMPS = 150
parts = [f"local MOCK = {MOCK}\nlocal TIDY = {{}}\n"
         + "".join(f"TIDY.{style} = {lua_string(sf.tidy_lua(style))}\n" for style in ("lines", "vertical")) + """
local function try(label, style)
    local before = mock.places()
    local first = mock.run(TIDY[style]); local after = mock.places()
    local second = mock.run(TIDY[style])
    print(table.concat({label, style, first, second, before, after, mock.places(), mock.wires()}, "\\t"))
end
"""]
for name, scene in SCENES.items():
    for style in ("lines", "vertical"):
        parts.append(f"dofile(MOCK)\ndo\n{scene}\nend\ntry({name!r}, {style!r})\n")
PICTURES = "mock.pictures = {ShowThumbnails = true, ForceSource = true, AspectTilePics = true}"
for label, first in (("random", ""), ("pictures_random", PICTURES)):
    parts.append(f"for seed = 1, {RANDOM_COMPS} do for _, style in ipairs({{'lines', 'vertical'}}) do\n"
                 f"dofile(MOCK)\n{first}\nSEED = seed\ndo\n{RANDOM}\nend\ntry('{label}' .. seed, style)\nend end\n")
with tempfile.NamedTemporaryFile("w", suffix=".lua", delete=False) as f:
    f.write("".join(parts))
done = subprocess.run([LUA, f.name], capture_output=True, text=True, timeout=60)
os.unlink(f.name)
if done.returncode != 0:
    print(done.stderr.strip()[:600])


def spots(text):
    return {name: tuple(float(n) for n in xy.split(",")) for name, xy in (item.split("@") for item in text.split())}


tidied, wrong = {}, []
for line in done.stdout.splitlines():
    label, style, first, second, before, after, again, wires = (line.split("\t") + [""] * 8)[:8]
    was, now = spots(before), spots(after)
    tidied[label, style] = now
    along, across = (1, 0) if style == "vertical" else (0, 1)
    why = []
    if not first.replace(" ", "").isdigit():
        why.append(f"it said {first!r}")
    if not second.endswith(" 0") or after != again:
        why.append("a second go moved things again")
    if len(set(now.values())) != len(now):
        why.append("two nodes on one spot")
    if "MediaOut1" in now and now["MediaOut1"] != was["MediaOut1"]:
        why.append("MediaOut moved")
    for wire in wires.split():
        src, to = wire.split(">")
        to, slot = to.split(".", 1)
        if src not in now or to not in now or max(abs(n) for n in now[to] + now[src]) > 90:  # (inside the group)
            continue
        main = slot in ("Input", "Background")
        if now[src][along] > now[to][along] or (main and now[src][along] == now[to][along]):
            why.append(f"{src} isn't before {to}")
        if main and now[src][across] == now[to][across] and any(
                spot[across] == now[src][across] and now[src][along] < spot[along] < now[to][along] for spot in now.values()):
            why.append(f"a node sits on the wire from {src} to {to}")
    if label.startswith("pictures"):  # sources show a 16:9 picture: one row more, downwards
        for name, (x, y) in now.items():
            if name.startswith(("MediaIn", "Background", "TextPlus")) and (x, y + 1) in now.values():
                why.append(f"a node is hidden behind {name}'s picture")
    if why:
        wrong.append((label, style, why[:3]))
check(f"Tidy up: {len(SCENES)} set-ups and {2 * RANDOM_COMPS} random ones (half with pictures on the tiles), both ways - "
      "nothing on top of anything or behind a picture, every node before what it feeds, no node on a wire along a row, "
      "MediaOut where it was, and a second go moves nothing"
      + (f": {wrong[:4]}" if wrong else ""), done.returncode == 0 and not wrong and len(tidied) == 2 * (len(SCENES) + 2 * RANDOM_COMPS))


# Centre the node view after tidying (Settings > Scripts): FrameAll, its zoom put back - only when it's asked for
fitted = {}
for fit in (True, False):
    program = (f"dofile({MOCK})\nlocal a = mock.add('MediaIn', 3, 9); local b = mock.add('MediaOut', 0, 0)\n"
               "mock.connect(a, b, 'Input')\n"
               f"mock.run({lua_string(sf.tidy_lua('lines', fit))})\nprint((mock.framed or 0) .. ' ' .. (mock.scale or 1))\n")
    with tempfile.NamedTemporaryFile("w", suffix=".lua", delete=False) as f:
        f.write(program)
    ran = subprocess.run([LUA, f.name], capture_output=True, text=True, timeout=20)
    os.unlink(f.name)
    fitted[fit] = ran.stdout.strip().splitlines()[-1] if ran.stdout.strip() else ran.stderr.strip()[:200]
check("Tidy up centres the node view, the zoom as it was, when that's switched on - and only then",
      fitted == {True: "1 1", False: "0 1"} or print(fitted))


def at(scene, name, style="lines"):
    return tidied.get((scene, style), {}).get(name, (None, None))


def step(scene, a, b):  # how far b is from a: (columns, rows)
    (ax, ay), (bx, by) = at(scene, a), at(scene, b)
    return (round(bx - ax, 3), round(by - ay, 3)) if None not in (ax, bx) else None


check("a comp whose MediaOut isn't wired up is sorted all the same: the line ends beside MediaOut, "
      "the Merge coming in from the side right above, its own foreground above that",
      step("no_out", "Merge1", "MediaOut1") == (1, 0) and step("no_out", "MediaIn1", "Merge1") == (1, 0)
      and step("no_out", "Merge1", "Merge2") == (0, -1) and step("no_out", "MediaIn2", "Merge2") == (1, 0)
      and step("no_out", "Merge2", "MediaIn3") == (0, -1))
check("three Merges in a row have their foregrounds side by side right above them - no staircase",
      all(step("three_merges", f"Merge{k}", f"MediaIn{k + 1}") == (0, -1) for k in (1, 2, 3))
      and step("three_merges", "MediaIn1", "MediaOut1") == (4, 0))
check("a longer branch takes the nearest row with room; a mask goes right below its node",
      step("branches", "Merge1", "Transform1") == (0, -1) and step("branches", "Transform1", "MediaIn2") == (-1, 0)
      and step("branches", "Merge2", "TextPlus1") == (0, -1) and step("branches", "Merge3", "Transform2") == (0, -2)
      and step("branches", "Transform2", "MediaIn3") == (-2, 0) and step("branches", "Merge2", "Ellipse1") == (0, 1))
check("a node that feeds two stays in the main line, left of both",
      step("shared", "MediaIn1", "Merge1") == (1, 0) and step("shared", "Merge1", "Blur1") == (0, -1))
check("notes, underlays and the inside of a group stay put; a group sits in its line like any node; "
      "what's connected to nothing goes in a row underneath",
      at("the_rest", "Note1") == (20, 20) and at("the_rest", "Underlay1") == (21, 21) and at("the_rest", "Blur1") == (100, 100)
      and at("the_rest", "Transform2") == (101, 100) and step("the_rest", "Merge1", "GroupOperator1") == (0, -1)
      and step("the_rest", "GroupOperator1", "MediaIn2") == (-1, 0)
      and at("the_rest", "Background1")[1] == at("the_rest", "TextPlus1")[1] > at("the_rest", "Merge1")[1])
check("square pictures and a 16:9 video coming into one line sit level with each other - the video isn't lower",
      len({at("mixed_pictures", f"MediaIn{k}")[1] for k in (2, 3, 4)}) == 1
      and step("mixed_pictures", "Merge1", "MediaIn2")[1] < -2)
check("a MediaOut from the picker: a second output, taking the picture from the selected node - the chain as it was",
      got.get("out2") == "connected after Merge1" and "Merge1>MediaOut2.Input" in got.get("wires_out", "")
      and got.get("chain_after_out") == got.get("chain_before_out"))
check("layers come in their own order: Layer1 nearest, then Layer2, then Layer10",
      [step("many_layers", "MultiMerge1", f"TextPlus{n}") for n in (3, 2, 1)] == [(0, -1), (0, -2), (0, -3)])
check("a tile with a picture hangs over the row below: a foreground goes two rows above its Merge, "
      "a portrait picture switched on for one tile five",
      all(step("pictures", f"Merge{k}", f"MediaIn{k + 1}") == (0, -2) for k in (1, 2, 3))
      and step("pictures", "Merge4", "Transform1") == (0, -5))
check("...and top to bottom the next node in the line waits below the picture",
      tuple(round(b - a, 3) for a, b in zip(at("pictures", "MediaIn1", "vertical"), at("pictures", "Merge1", "vertical"))) == (0, 2)
      and tuple(round(b - a, 3) for a, b in zip(at("pictures", "Merge1", "vertical"), at("pictures", "Merge2", "vertical"))) == (0, 1))
check("Top to bottom: the line runs down to MediaOut, what joins it sits beside it",
      step("three_merges", "MediaIn1", "MediaOut1") is not None
      and tuple(round(b - a, 3) for a, b in zip(at("three_merges", "MediaIn1", "vertical"), at("three_merges", "MediaOut1", "vertical"))) == (0, 4)
      and tuple(round(b - a, 3) for a, b in zip(at("three_merges", "Merge2", "vertical"), at("three_merges", "MediaIn3", "vertical"))) == (-1, 0))

print("\nall good" if not fails else f"\n{fails} FAILED")
raise SystemExit(1 if fails else 0)
