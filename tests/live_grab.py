"""Grab Frame tried in the real Resolve, through the picker's own grab_frame: twice in a row on the Edit page (the case
that crashed Resolve 21.1.1 on Linux, 2026-10-20), then once from the Fusion page; then 30 s of asking Resolve, and
its log looked through for a crash. Pages switch while it runs.

    .venv/bin/python tests/live_grab.py        (Resolve open - not while you work in it)

Uses "ds live video.mp4" (tests/live_app.py makes it); the grabs go to /tmp/clipse-live-media/grabs. The scratch
timeline is left in place."""
import os
import sys
import time

import _setup  # noqa: E402,F401
from clipse import resolve_client as rc  # noqa: E402
from clipse import stills  # noqa: E402
from clipse import timeline_tools as tt  # noqa: E402

GRABS = "/tmp/clipse-live-media/grabs"
failed = []


def check(what, ok, detail=""):
    print(("ok   " if ok else "FAIL ") + what + (f"  ({detail})" if detail and not ok else ""))
    if not ok:
        failed.append(what)


def resolve_log():
    path = os.path.expanduser("~/Library/Application Support/Blackmagic Design/DaVinci Resolve/logs/ResolveDebug.txt")
    try:
        return os.path.getsize(path), path
    except OSError:
        return 0, path


def main():
    from clipse.settings import Settings
    from clipse.picker_window import PickerWindow
    r = rc.connect_to_resolve(timeout=8)
    page = r.GetCurrentPage()
    project = r.GetProjectManager().GetCurrentProject()
    pool = project.GetMediaPool()
    home = project.GetCurrentTimeline()

    def walk(folder):
        yield from folder.GetClipList() or []
        for sub in folder.GetSubFolderList() or []:
            yield from walk(sub)
    video = next(c for c in walk(pool.GetRootFolder()) if c.GetName() == "ds live video.mp4")
    log_size, log_path = resolve_log()
    timeline = pool.CreateEmptyTimeline(f"ds scratch - grab {time.strftime('%H.%M.%S')}")
    try:
        project.SetCurrentTimeline(timeline)
        fps = float(timeline.GetSetting("timelineFrameRate"))
        rc.append_clip(pool, video, {"mediaPoolItem": video, "trackIndex": 1, "mediaType": 1}, 0, 119)
        item = timeline.GetItemListInTrack("video", 1)[0]
        settings = Settings()
        settings.load()
        settings.general.update(tour_done=True, check_for_updates=False)
        settings.files["grabs_folder"] = GRABS
        w = PickerWindow(settings, {})
        w.set_resolve(r)
        r.OpenPage("edit")
        time.sleep(1.0)
        folder = os.path.join(GRABS, stills.project_folder_name(project.GetName()))

        old = set(os.listdir(folder)) if os.path.isdir(folder) else set()
        said = []
        for k, at in enumerate((60, 90)):  # (1 s and 1.5 s into the video, at 60 fps)
            timeline.SetCurrentTimecode(tt.frame_to_tc(item.GetStart() + at, fps))
            time.sleep(0.3)
            said.append(w.grab_frame())  # (straight after each other - no pause between them)
        print("   " + "\n   ".join(str(s) for s in said))
        import re
        pngs = sorted(f for f in set(os.listdir(folder)) - old if f.endswith(".png"))
        check("two grabs in a row on the Edit page: two PNGs, each named after the video and where in it",
              len(pngs) == 2 and all(re.fullmatch(r"ds_live_video_0m01s(_\d+)?\.png", p) for p in pngs), str(pngs))
        check("...back on the Edit page afterwards", r.GetCurrentPage() == "edit", r.GetCurrentPage())
        grabs_bin = stills.app_bin(pool, stills.GRABS_BIN)
        in_bin = [c.GetName() for c in (grabs_bin.GetClipList() if grabs_bin else [])]
        check("...both in clipse > frame_grabs", sum(n.startswith("ds_live_video_") for n in in_bin) >= 2, str(in_bin))
        on = [it.GetName() for n in range(1, timeline.GetTrackCount("video") + 1)
              for it in timeline.GetItemListInTrack("video", n) or [] if it.GetName().startswith("ds_live_video_")]
        check("...both on the timeline", len(on) >= 2, str(on))

        r.OpenPage("fusion")
        time.sleep(1.5)
        timeline.SetCurrentTimecode(tt.frame_to_tc(item.GetStart() + 30, fps))
        time.sleep(0.3)
        said = w.grab_frame()
        print("   " + str(said))
        check("from the Fusion page: grabbed, and back on the Fusion page", str(said).startswith("Grabbed")
              and r.GetCurrentPage() == "fusion", f"{said} - on {r.GetCurrentPage()}")

        print("   waiting 30 s - the crashes came 15-25 s after a grab ...")
        alive = True
        for _ in range(30):
            time.sleep(1)
            try:
                alive = bool(r.GetVersionString()) and project.GetCurrentTimeline() is not None
            except Exception:
                alive = False
            if not alive:
                break
        check("Resolve still answers 30 s later", alive)
        size, _ = resolve_log()
        new = ""
        if size > log_size:
            with open(log_path, errors="replace") as f:
                f.seek(log_size)
                new = f.read()
        bad = [line for line in new.splitlines() if any(w_ in line for w_ in ("out_of_range", "Assertion", "terminate"))]
        check("...and its log has no crash in it", not bad, "\n".join(bad[:5]))
    finally:
        try:
            project.SetCurrentTimeline(home)
            if r.GetCurrentPage() != page:
                r.OpenPage(page)
            print(f"(back on {project.GetCurrentTimeline().GetName()}, {r.GetCurrentPage()} page; "
                  f"\"{timeline.GetName()}\" left in place)")
        except Exception as e:
            print(f"(couldn't go back: {e})")
    print(f"\n{len(failed)} wrong" + (":" if failed else " - all good"))
    for what in failed:
        print("   " + what)


if __name__ == "__main__":
    main()
