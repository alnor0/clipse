"""Moves Resolve's playhead along with a voiceover while it records (voiceover_pill.VoiceoverTake) - a small program
of its own, started for the take (launch.command("playhead")) and told what to do one line at a time on its input:

    move <wall clock> <frame> <fps> <drop>   at that moment (time.time()) the playhead is at frame - and goes on
    hold                                      stops it where it is
    goto <frame> <fps> <drop>                 stops it, and puts it at frame
    quit                                      (or the input closing) ends it

Why a program of its own: right after the playhead moves, Resolve makes a script's next call wait until it has
drawn that frame - a second while Resolve is in the background (measured 2026-10-27, 21.1.1, ten moves: 998 ms each)
- and Resolve's library holds Python's lock meanwhile, so every thread waits (another thread ticked once in those
998 ms). In the service the microphone and the pill would stand still; here only this waits, and catches up to the
frame for now when Resolve answers - it never falls behind, it skips. How long each move took is written to
playhead.log in the logs folder when it ends (2026-10-27: "laggy" - his footage is AV1 1440p60 with a whole picture
once a second, so every move has Resolve decode up to 59 frames to show one; optimized media or proxies fix that)."""
import sys
import threading
import time


def main():
    from . import resolve_client as rc
    from .timeline_tools import frames_tc
    resolve = rc.connect_to_resolve(timeout=10)
    if resolve is None:
        print("[playhead] Resolve didn't answer", flush=True)
        return
    project = resolve.GetProjectManager().GetCurrentProject()
    timeline = project.GetCurrentTimeline() if project else None
    if timeline is None:
        return
    plan = {"moving": None, "goto": None, "over": False}  # moving: (wall clock, frame, fps, drop)
    lock = threading.Lock()

    def listen():
        for line in sys.stdin:
            words = line.split()
            with lock:
                if words[:1] == ["move"] and len(words) == 5:
                    plan["moving"] = (float(words[1]), int(words[2]), float(words[3]), words[4] == "1")
                elif words[:1] == ["hold"]:
                    plan["moving"] = None
                elif words[:1] == ["goto"] and len(words) == 4:
                    plan["moving"] = None
                    plan["goto"] = (int(words[1]), float(words[2]), words[3] == "1")
                elif words[:1] == ["quit"]:
                    break
        with lock:
            plan["over"] = True

    threading.Thread(target=listen, daemon=True).start()
    shown, took, began = None, [], time.monotonic()

    def set_to(frame, fps, drop):
        before = time.monotonic()
        timeline.SetCurrentTimecode(frames_tc(frame, fps, drop))
        took.append(time.monotonic() - before)
    while True:
        with lock:
            moving, goto, over, plan["goto"] = plan["moving"], plan["goto"], plan["over"], None
        if goto is not None:  # (first, even when it's over: a "goto" right before "quit" still goes there)
            frame, fps, drop = goto
            set_to(frame, fps, drop)
            shown = frame
        if over:
            _write_down(took, time.monotonic() - began)
            return
        if goto is None and moving is not None:
            since, start, fps, drop = moving
            frame = start + int(max(0.0, time.time() - since) * fps)  # (the frame for now: late, it skips ahead)
            if frame != shown:
                set_to(frame, fps, drop)
                shown = frame
            time.sleep(max(0.002, 0.5 / fps))
            continue
        time.sleep(0.01)


def _write_down(took, seconds):
    """playhead.log: how many moves in how long, and how long Resolve took over one."""
    from . import paths
    if not took:
        return
    ms = sorted(t * 1000 for t in took)
    line = (f"{time.strftime('%H:%M:%S')}  {len(ms)} moves in {seconds:.1f} s ({len(ms) / max(seconds, 0.001):.1f} a "
            f"second) - a move took {ms[len(ms) // 2]:.0f} ms (middle), {ms[-1]:.0f} ms (longest)\n")
    try:
        with open(paths.log("playhead.log"), "a") as f:
            f.write(line)
    except OSError:
        pass


if __name__ == "__main__":
    main()
