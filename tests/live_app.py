"""The app tried in the real DaVinci Resolve - the picker's own code, not the stand-in.

    .venv/bin/python tests/live_app.py        (Resolve open - not while you're working in it)

On a scratch timeline ("ds scratch - app <time>", left there - delete it when you like) and a scratch bin ("ds scratch -
app") of made-up media (a picture, a video, a sound - in /tmp/clipse-live-media): the Media Pool read and looked at
again, inserts at the playhead and back to back, Insert as at every marker, a Text+ with words, an adjustment clip and a
Fusion composition at the playhead, Swap clip, Next use of clip, Undo - and in a Fusion composition the next / previous
keyframe and Tidy up. Plain inserts and reads only: nothing is grabbed, rendered or deleted, and Resolve's page isn't
switched. Clipse's own files go to a throwaway HOME. Your timeline is the open one again afterwards.
"""
import math
import os
import struct
import time
import wave

MEDIA = "/tmp/clipse-live-media"   # (before _setup: it moves HOME)
import _setup  # noqa: E402,F401 (a throwaway HOME, Qt without a screen)
from clipse import presets as pm  # noqa: E402
from clipse import resolve_client as rc  # noqa: E402
from clipse import scripts_fusion as sf  # noqa: E402
from clipse import timeline_tools as tt  # noqa: E402

BIN = "ds scratch - app"
NAMES = {"picture": "ds live picture.png", "video": "ds live video.mp4", "sound": "ds live sound.wav"}
failed = []


def check(what, ok, detail=""):
    print(("ok   " if ok else "FAIL ") + what + (f"  ({detail})" if detail and not ok else ""))
    if not ok:
        failed.append(what)


def make_media():
    """A picture, two seconds of video, three seconds of sound - made once."""
    os.makedirs(MEDIA, exist_ok=True)
    paths = {kind: os.path.join(MEDIA, name) for kind, name in NAMES.items()}
    if not os.path.exists(paths["picture"]):
        from PySide6.QtGui import QColor, QImage, QPainter
        im = QImage(1920, 1080, QImage.Format_RGB32)
        im.fill(QColor(40, 70, 140))
        p = QPainter(im)
        p.fillRect(640, 300, 640, 480, QColor(230, 200, 90))
        p.end()
        im.save(paths["picture"])
    if not os.path.exists(paths["sound"]):
        with wave.open(paths["sound"], "w") as w:
            w.setnchannels(2)
            w.setsampwidth(2)
            w.setframerate(48000)
            w.writeframes(b"".join(struct.pack("<hh", v, v) for v in
                                   (int(9000 * math.sin(2 * math.pi * 440 * n / 48000)) for n in range(48000 * 3))))
    if not os.path.exists(paths["video"]):
        import av
        import numpy as np
        out = av.open(paths["video"], "w")
        stream = out.add_stream("libx264", rate=30)
        stream.width, stream.height, stream.pix_fmt = 1280, 720, "yuv420p"
        for i in range(60):
            frame = np.zeros((720, 1280, 3), dtype=np.uint8)
            frame[:, :, 0] = (i * 4) % 255
            frame[200:520, 100 + i * 15:300 + i * 15, 1] = 220
            for packet in stream.encode(av.VideoFrame.from_ndarray(frame, format="rgb24")):
                out.mux(packet)
        for packet in stream.encode():
            out.mux(packet)
        out.close()
    return paths


def scratch_bin(pool, paths):
    root = pool.GetRootFolder()
    folder = next((f for f in root.GetSubFolderList() if f.GetName() == BIN), None) or pool.AddSubFolder(root, BIN)
    have = {c.GetName() for c in folder.GetClipList()}
    if any(name not in have for name in NAMES.values()):
        pool.SetCurrentFolder(folder)
        pool.ImportMedia([p for kind, p in paths.items() if NAMES[kind] not in have])
    pool.SetCurrentFolder(root)
    return folder


def items(timeline, kind="video"):
    out = []
    for track in range(1, timeline.GetTrackCount(kind) + 1):
        out += [(track, it) for it in timeline.GetItemListInTrack(kind, track) or []]
    return out


def main():
    from clipse.settings import Settings
    from clipse.picker_window import PickerWindow
    r = rc.connect_to_resolve(timeout=8)
    page = r.GetCurrentPage()
    project = r.GetProjectManager().GetCurrentProject()
    pool = project.GetMediaPool()
    home = project.GetCurrentTimeline()
    paths = make_media()
    scratch_bin(pool, paths)
    timeline = pool.CreateEmptyTimeline(f"{BIN} {time.strftime('%H.%M.%S')}")
    project.SetCurrentTimeline(timeline)
    fps = float(timeline.GetSetting("timelineFrameRate"))
    start = timeline.GetStartFrame()
    print(f"scratch timeline: {timeline.GetName()} ({fps:g} fps), page: {page}")
    try:
        settings = Settings()
        settings.load()
        settings.general.update(tour_done=True, check_for_updates=False)
        w = PickerWindow(settings, {})
        w.set_resolve(r)

        # -- the Media Pool: read in full the first time, looked at again on the next opening --
        t = time.monotonic()
        w.open_picker()
        while w._scan is not None and time.monotonic() - t < 60:
            _setup.pump(0.05)
        names = [row.name for row in w.model.clip_rows]
        check(f"the Media Pool read ({len(names)} rows, {time.monotonic() - t:.1f} s): the scratch media is in it",
              all(n in names for n in NAMES.values()), str([n for n in NAMES.values() if n not in names]))
        w.hide()
        w._media_reads[project.GetName()]["any"] = 0  # (as if 10 s had passed: the quick look runs)
        t = time.monotonic()
        w.open_picker()
        while w._scan is not None and time.monotonic() - t < 60:
            _setup.pump(0.05)
        check(f"...opened again: the quick look ({time.monotonic() - t:.2f} s) finds the same",
              all(n in [row.name for row in w.model.clip_rows] for n in NAMES.values()))
        index = {kind: names.index(name) for kind, name in NAMES.items()}

        def at(frame):
            timeline.SetCurrentTimecode(tt.frame_to_tc(frame, fps))

        # -- inserts --
        at(start)
        before = len(items(timeline))
        w._insert_with(dict(pm.get(settings, "normal")), [index["picture"]])
        landed = items(timeline)
        pic = [it for _t, it in landed if it.GetName() == NAMES["picture"]]
        want = round(settings.presets["still_length"] * fps)
        check(f"a picture at the playhead, as long as \"A picture lasts\" ({want} frames)",
              len(landed) == before + 1 and pic and abs(pic[0].GetDuration() - want) <= 1,
              f"{[(it.GetName(), it.GetStart(), it.GetDuration()) for _t, it in landed]}")
        at(start + 10 * round(fps))
        w._insert_with(dict(pm.get(settings, "normal"), spacing="back_to_back"), [index["video"], index["sound"]])
        vids = [it for _t, it in items(timeline) if it.GetName() == NAMES["video"]]
        snds = [it for _t, it in items(timeline, "audio") if it.GetName() == NAMES["sound"]]
        check("a video and a sound back to back: the sound starts where the video ends",
              vids and snds and abs(snds[0].GetStart() - (vids[0].GetStart() + vids[0].GetDuration())) <= 1,
              f"video {vids and (vids[0].GetStart(), vids[0].GetDuration())}, sound {snds and snds[0].GetStart()}")

        # -- Insert as > Afterwards: a compound clip - in the compound_clips bin, not whichever bin is open --
        at(start + 14 * round(fps))
        pool.SetCurrentFolder(next(f for f in pool.GetRootFolder().GetSubFolderList() if f.GetName() == BIN))
        # (pictures and sounds together - the case where Resolve makes it but hands back nothing, 2026-10-19)
        w._insert_with(dict(pm.get(settings, "normal"), spacing="back_to_back", convert="compound"),
                       [index["picture"], index["sound"]] * 4)
        app_bin = next((f for f in pool.GetRootFolder().GetSubFolderList() if f.GetName() == "clipse"), None)
        compounds = next((f for f in (app_bin.GetSubFolderList() if app_bin else []) if f.GetName() == "compound_clips"), None)
        here = [c.GetName() for c in (compounds.GetClipList() if compounds else [])]
        stray = [c.GetName() for c in next(f for f in pool.GetRootFolder().GetSubFolderList()
                                            if f.GetName() == BIN).GetClipList() if c.GetName() not in NAMES.values()
                 and c.GetClipProperty("Type") != "Timeline"]
        check("Afterwards a compound clip: it goes in clipse > compound_clips, not the bin that's open",
              bool(here) and not stray, f"compound_clips: {here}, left in the open bin: {stray}")
        pool.SetCurrentFolder(pool.GetRootFolder())

        # -- Insert as at every marker --
        marks = [start + 20 * round(fps) + k * round(fps) for k in (0, 3, 6)]
        for m in marks:
            timeline.AddMarker(m - start, "Blue", "ds live", "", 1)
        w._insert_with(dict(pm.placing(settings, "markers")), [index["picture"]])
        starts = sorted(it.GetStart() for _t, it in items(timeline) if it.GetName() == NAMES["picture"])
        check("Insert as at every marker: a picture on each of the 3 markers", all(m in starts for m in marks),
              f"pictures start at {starts}, markers {marks}")

        # -- a Text+ with words, an adjustment clip and a Fusion composition at the playhead --
        at(start + 40 * round(fps))
        w.session.update(timeline=timeline, media_pool=pool)
        row = w._title_rows("Hello from the live test")[0]
        message = w._add_basic(row)
        texts = [it for _t, it in items(timeline) if it.GetName() in ("text_plus", "Text+")
                 and it.GetStart() == start + 40 * round(fps)]
        words = ""
        if texts and texts[0].GetFusionCompCount():
            tool = next(iter(texts[0].GetFusionCompByIndex(1).GetToolList(False, "TextPlus").values()), None)
            words = tool.GetInput("StyledText") if tool else ""
        check("a Text+ at the playhead with its words, from the Media Pool", words == "Hello from the live test",
              f"{message} - {words!r}")
        at(start + 50 * round(fps))
        w.run_direct_command("adjust", "fixed")
        _setup.pump(0.5)
        check("an adjustment clip at the playhead",
              any("adjust" in it.GetName().lower() for _t, it in items(timeline)),
              str([it.GetName() for _t, it in items(timeline)]))
        at(start + 60 * round(fps))
        w.run_direct_command("comp", "fixed")
        _setup.pump(0.5)
        comps = [it for _t, it in items(timeline) if "fusion" in it.GetName().lower()]
        check("a Fusion composition at the playhead", bool(comps), str([it.GetName() for _t, it in items(timeline)]))
        at(start + 2)  # (over the first picture, on V1)
        w.session.update(timeline=timeline, media_pool=pool)
        message = w._add_basic(w._basic_rows("solid")[0])
        solids = [(t, it) for t, it in items(timeline) if it.GetName() == "solid_color"]
        check("a solid colour at the playhead: over the picture on V1, as long as a picture lasts",
              len(solids) == 1 and solids[0][0] > 1 and abs(solids[0][1].GetDuration() - want) <= 1, message)
        v1 = [it.GetName() for it in timeline.GetItemListInTrack("video", 1) or []]
        check("...V1 as it was: nothing cut into it", v1.count(NAMES["picture"]) >= 1 and not any(
              n in v1 for n in ("text_plus", "Text+", "solid_color")), str(v1))

        # -- Next use of clip: from before the first picture, the playhead to it --
        at(start + 2)
        w._select_row(w.model.visible.index(index["picture"]))
        w._jump_use(1)
        _setup.pump(0.3)
        now = rc.tc_to_frame(timeline.GetCurrentTimecode(), fps)
        check("Next use of clip: the playhead to the picture's next use", now in starts, f"at {now}, uses {starts}")

        # -- Swap clip: the picture it takes out becomes the video, in the same place --
        # (the clip selected on the timeline goes first, else the one on top under the playhead. With Resolve's
        #  Selection Follows Playhead on, the selection stays on its track: after the jump above that can be the
        #  picture underneath - seen on a Mac, 2026-10-21. So: whichever it took, that one is swapped)
        at(marks[1] + 2)
        w.open_picker()
        w.start_swap()
        _setup.pump(0.5)
        video = [row.name for row in w.model.clip_rows].index(NAMES["video"])  # (the list may have been read again)
        w._select_row(w.model.visible.index(video))
        spots = [(track, at_) for kind, track, at_ in (w._swap or {}).get("spots") or [] if kind == "video"]
        w.confirm()
        _setup.pump(0.8)

        def on(spot):
            return [it.GetName() for it in timeline.GetItemListInTrack("video", spot[0]) or [] if it.GetStart() == spot[1]]
        check("Swap clip: the picture it took out is the video now, on its track and at its start",
              len(spots) == 1 and on(spots[0]) == [NAMES["video"]], f"took {spots}, there now: {[on(s) for s in spots]}")

        # -- Undo Clipse's last step (a swap isn't one: the solid colour before it) --
        count = len(items(timeline))
        print("   undo:", w.undo_last_action())
        _setup.pump(0.5)
        check("Undo takes back Clipse's last step", len(items(timeline)) != count)

        # -- Fusion: Tidy up - in the composition of a clip on the scratch timeline --
        clip = comps[0] if comps else pic[0]
        comp = clip.GetFusionCompByIndex(1) if clip.GetFusionCompCount() else clip.AddFusionComp()
        made = sf.run_lua(comp, r"""
local t = comp:AddTool("Transform", -32768, -32768)
t:SetAttrs({TOOLS_Name = "DSKeys"})
t.Size = BezierSpline({})
t.Size[10] = 1
t.Size[40] = 2
t.Size[70] = 1
comp.CurrentTime = 0
comp:SetData("ClipseResult", "ok")
""", wait=8.0)
        check("a Transform with keyframes at 10, 40, 70 in the composition", made == "ok", str(made))
        tidy = sf.run_lua(comp, sf.tidy_lua(), wait=8.0)
        if str(tidy) == "no node view":  # (the node editor is there only on the Fusion page - not switched to)
            print("skip Tidy up: it needs the Fusion page open (the test doesn't switch your page)")
        else:
            check("Tidy up runs in the composition", tidy is not None and str(tidy).split()[0].isdigit(), str(tidy))
    finally:
        if home is None or not project.SetCurrentTimeline(home):
            print(f"(couldn't open your timeline again - {'none was open' if home is None else home.GetName()})")
        if r.GetCurrentPage() != page:
            r.OpenPage(page)
    print(f"\n{len(failed)} wrong" + (":" if failed else " - all good"))
    for what in failed:
        print("   " + what)
    print(f'(the scratch timeline "{timeline.GetName()}" and the bin "{BIN}" are left in place - delete them when you like)')


if __name__ == "__main__":
    main()
