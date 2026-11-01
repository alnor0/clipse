"""Clipse's Fusion-page tools tried in the real Fusion - Tidy up, a node from the picker (after the selected one, or only
placed), Copy node name, Node off / on, Before - After, Pull out - on a scratch timeline's own composition, never yours.

    .venv/bin/python tests/live_fusion.py        (Resolve open on the Fusion page - not while you work in it)

The Fusion page shows a new composition only when it's opened, so it goes to the Edit page and back once; it stops
before touching anything if the composition open isn't the scratch one. Uses "ds live picture.png" (tests/live_app.py
makes it). The scratch timeline is left in place."""
import sys
import time

import _setup  # noqa: E402,F401
from clipse import fusion_animate as fa  # noqa: E402
from clipse import fusion_expressions as fx  # noqa: E402
from clipse import resolve_client as rc  # noqa: E402
from clipse import scripts_fusion as sf  # noqa: E402
from clipse import timeline_tools as tt  # noqa: E402

failed = []


def check(what, ok, detail=""):
    print(("ok   " if ok else "FAIL ") + what + (f"  ({detail})" if detail and not ok else ""))
    if not ok:
        failed.append(what)


def lua(comp, body):
    return sf.run_lua(comp, "local flow = comp.CurrentFrame and comp.CurrentFrame.FlowView\n" + body, wait=8.0)


STATE = r"""
local out = {}
for _, t in pairs(comp:GetToolList(false)) do
  local a = t:GetAttrs()
  local p = flow and flow:GetPosTable(t)
  if p and p[1] then
    local i = t:FindMainInput(1)
    local src = i and i:GetConnectedOutput()
    local from = src and src:GetTool():GetAttrs().TOOLS_Name or "-"
    out[#out + 1] = string.format("%s %s %.2f %.2f %s %s", a.TOOLS_Name, a.TOOLS_RegID, p[1], p[2], from,
                                  a.TOOLB_PassThrough and "off" or "on")
  end
end
comp:SetData("ClipseResult", table.concat(out, "\n"))
"""


def state(comp):
    nodes = {}
    for line in str(lua(comp, STATE) or "").splitlines():
        name, kind, x, y, src, on = line.split(" ")
        nodes[name] = dict(kind=kind, x=float(x), y=float(y), src=src, on=on == "on")
    return nodes


def select(comp, name=None):
    lua(comp, ("flow:Select()\n" if True else "") + (
        f'local t = comp:FindTool("{name}"); flow:Select(t, true); comp:SetActiveTool(t)\n' if name else
        "comp:SetActiveTool(nil)\n") + 'comp:SetData("ClipseResult", "ok")')


def main():
    r = rc.connect_to_resolve(timeout=8)
    if r.GetCurrentPage() != "fusion":
        sys.exit("The Fusion page isn't open - nothing done.")
    project = r.GetProjectManager().GetCurrentProject()
    pool = project.GetMediaPool()
    home = project.GetCurrentTimeline()
    fusion = r.Fusion()

    def walk(folder):
        yield from folder.GetClipList() or []
        for sub in folder.GetSubFolderList() or []:
            yield from walk(sub)
    picture = next(c for c in walk(pool.GetRootFolder()) if c.GetName() == "ds live picture.png")
    timeline = pool.CreateEmptyTimeline(f"ds scratch - fusion {time.strftime('%H.%M.%S')}")
    try:
        project.SetCurrentTimeline(timeline)
        fps = float(timeline.GetSetting("timelineFrameRate"))
        rc.append_clip(pool, picture, {"mediaPoolItem": picture, "trackIndex": 1, "mediaType": 1}, 0, 240, still=True)
        item = timeline.GetItemListInTrack("video", 1)[0]
        if not item.GetFusionCompCount():
            item.AddFusionComp()
        timeline.SetCurrentTimecode(tt.frame_to_tc(item.GetStart() + 5, fps))
        time.sleep(1.0)
        mine = item.GetFusionCompByIndex(1)
        lua(mine, 'local n = comp:AddTool("Note", -32768, -32768); n:SetAttrs({TOOLS_Name = "DSScratchMark"})\n'
                  'comp:SetData("ClipseResult", "ok")')
        r.OpenPage("edit")  # (the Fusion page picks up the clip under the playhead only when it's opened)
        time.sleep(1.0)
        r.OpenPage("fusion")
        open_comp = None
        for _ in range(20):  # (the Fusion page follows the playhead onto the scratch clip's composition)
            open_comp = fusion.GetCurrentComp()
            if open_comp is not None and "DSScratchMark" in (state(open_comp) or {}):
                break
            time.sleep(0.25)
        else:
            sys.exit("The Fusion page isn't showing the scratch composition - stopped before touching anything.")
        print(f"scratch: {timeline.GetName()}, its composition is the one open on the Fusion page")

        # a messy chain: MediaIn1 -> DSTransform -> DSBlur -> DSMerge (DSBack on top) -> MediaOut1, scattered about
        made = lua(open_comp, r"""
local m = comp:FindToolByID("MediaIn") ; local o = comp:FindToolByID("MediaOut")
local tr = comp:AddTool("Transform", -32768, -32768); tr:SetAttrs({TOOLS_Name = "DSTransform"})
local bl = comp:AddTool("Blur", -32768, -32768); bl:SetAttrs({TOOLS_Name = "DSBlur"})
local bg = comp:AddTool("Background", -32768, -32768); bg:SetAttrs({TOOLS_Name = "DSBack"})
local mg = comp:AddTool("Merge", -32768, -32768); mg:SetAttrs({TOOLS_Name = "DSMerge"})
tr.Input = m.Output; bl.Input = tr.Output; mg.Background = bl.Output; mg.Foreground = bg.Output; o.Input = mg.Output
local spots = {{m, 9, 2}, {tr, -3, 7}, {bl, 6, -4}, {bg, 1, 1}, {mg, -6, -2}, {o, 2, 9}}
for _, s in ipairs(spots) do flow:SetPos(s[1], s[2], s[3]) end
comp:SetData("ClipseResult", "ok")""")
        check("a messy chain of six nodes in the scratch composition", made == "ok", str(made))

        # -- Tidy up (and the view centred) --
        said = sf.tidy_nodes(r, fit=True)
        n = state(open_comp)
        chain = ["MediaIn1", "DSTransform", "DSBlur", "DSMerge", "MediaOut1"]
        xs = [n[k]["x"] for k in chain if k in n]
        spots = [(v["x"], v["y"]) for k, v in n.items() if v["kind"] != "Note"]
        check(f"Tidy up: {said}", said.startswith("Tidied up"), said)
        check("...the chain runs left to right on one row", len(xs) == 5 and xs == sorted(xs)
              and len({n[k]["y"] for k in chain}) == 1, str({k: (n[k]["x"], n[k]["y"]) for k in chain if k in n}))
        check("...what joins it (the Background) sits above the Merge, no two nodes on one spot",
              n["DSBack"]["y"] < n["DSMerge"]["y"] and abs(n["DSBack"]["x"] - n["DSMerge"]["x"]) < 1.01
              and len(set(spots)) == len(spots), str(n.get("DSBack")))
        check("...wired as before", n["DSBlur"]["src"] == "DSTransform" and n["DSMerge"]["src"] == "DSBlur"
              and n["MediaOut1"]["src"] == "DSMerge")
        again = sf.tidy_nodes(r)
        check("...tidied again, nothing moves", state(open_comp) == n, again)

        # -- a node from the picker: after the selected one, or only placed when nothing is selected --
        select(open_comp, "DSTransform")
        ok, said = sf.insert_tool(r, "ColorCorrector", "Color Corrector", timeline=timeline)
        n = state(open_comp)
        cc = next((k for k, v in n.items() if v["kind"] == "ColorCorrector"), None)
        check(f"a node with DSTransform selected goes in after it: {said}",
              ok and cc and n[cc]["src"] == "DSTransform" and n["DSBlur"]["src"] == cc, said)
        select(open_comp)
        ok, said = sf.insert_tool(r, "BrightnessContrast", "Brightness Contrast", timeline=timeline)
        n2 = state(open_comp)
        bc = next((k for k, v in n2.items() if v["kind"] == "BrightnessContrast"), None)
        lowest = max(v["y"] for k, v in n.items() if v["kind"] != "Note")
        wired = [k for k, v in n2.items() if v["src"] == bc]
        check(f"nothing selected: only placed, under the others, wired to nothing: {said}",
              ok and bc and n2[bc]["src"] == "-" and not wired and n2[bc]["y"] > lowest
              and all(n2[k]["src"] == n[k]["src"] for k in n), f"{n2.get(bc)}, feeds {wired}")

        # -- Copy node name (the name it would copy) --
        select(open_comp, "DSBlur")
        time.sleep(0.3)
        name, problem = fx.selected_node_name(r)
        check("Copy node name: the selected node's name", name == "DSBlur", f"{name!r} {problem!r}")

        # -- Node off / on --
        ok, said = fa.toggle_nodes(r)
        off = not state(open_comp)["DSBlur"]["on"]
        ok2, said2 = fa.toggle_nodes(r)
        check(f"Node off / on: off, then on again ({said} / {said2})",
              ok and off and ok2 and state(open_comp)["DSBlur"]["on"])

        # -- Before / after --
        lua(open_comp, 'comp:FindTool("DSTransform"):SetAttrs({TOOLB_PassThrough = true}); comp:SetData("ClipseResult", "ok")')
        ok, said = fa.before_after(r)
        n = state(open_comp)
        effects = [k for k, v in n.items() if v["kind"] not in ("MediaIn", "MediaOut", "Note")]
        ends_on = n["MediaIn1"]["on"] and n["MediaOut1"]["on"]
        check(f"Before / after: every effect off, the ends left alone ({said})",
              ok and ends_on and not any(n[k]["on"] for k in effects))
        ok, said = fa.before_after(r)
        n = state(open_comp)
        check(f"...again: back on - but the one switched off by hand stays off ({said})",
              ok and not n["DSTransform"]["on"] and all(n[k]["on"] for k in effects if k != "DSTransform"))

        # -- Pull out --
        select(open_comp, "DSBlur")
        said = sf.pull_out_nodes(r)
        n = state(open_comp)
        check(f"Pull out: the Blur out of the chain, the chain still joined ({said})",
              said.startswith("Pulled 1") and n["DSBlur"]["src"] == "-" and n["DSMerge"]["src"] == cc,
              str({k: n[k]["src"] for k in ("DSBlur", "DSMerge")}))
    finally:
        project.SetCurrentTimeline(home)
        r.OpenPage("edit")
        time.sleep(1.0)
        r.OpenPage("fusion")
        print(f"(back on {project.GetCurrentTimeline().GetName()}; the scratch timeline \"{timeline.GetName()}\" "
              "is left in place)")
    print(f"\n{len(failed)} wrong" + (":" if failed else " - all good"))
    for what in failed:
        print("   " + what)


if __name__ == "__main__":
    main()
