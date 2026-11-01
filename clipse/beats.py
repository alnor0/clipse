"""Mark the beats / Mark the bars (2026-11-01: "Clipse already finds the beat, so it could place markers on every beat
or bar of a song. Yes please"): a marker on every beat, or every 4 beats, of a song on the timeline - for the length of
the clip, where the song is at that point of it. At every marker (Insert as) then cuts to them.

Which song: the clip selected on the timeline; else the song highlighted in the picker, where it's on the timeline
nearest the playhead; else the sound under the playhead. A compound clip has no file a script can see: Clipse remembers
what it wrapped itself (remember_compound), or goes by its name; for one named otherwise, the song highlighted in the
picker is taken.

A program of its own (launch.command("beats"), compiled --beats), as organise.py: measured 2026-11-01 in 21.1.1, a marker
takes 4 ms with Resolve in front and 1 s with it behind, Python's lock held. The picker closes first, so Resolve is in
front; if it isn't, the service isn't held up. A failure says so through the service (SAY:); the markers landing is the
answer otherwise. Each run's markers carry its number in their custom data, so Undo takes back that run's only."""
import math
import os
import sys

from . import paths

DATA = "clipse_beats"
COLOUR = "Cream"
BEATS_IN_A_BAR = 4
COMPOUNDS_FILE = paths.data("compound_sounds.json")
MAX_COMPOUNDS = 500


def is_ours(info):
    return str((info or {}).get("customData") or "").startswith(DATA)


def beat_frames(bpm, beat0, bar0, every, first, end, in_file, fps):
    """[(frame, count from 1)] of every `every`-th beat over a clip at frames first-end, whose first frame shows the
    file `in_file` seconds in. A bar's number is its place in the song, whatever part of it the clip shows."""
    if not bpm or bpm <= 0 or end <= first:
        return []
    step = 60.0 / bpm * every
    base = (beat0 + bar0 * 60.0 / bpm) % step
    count = max(0, math.ceil((in_file - base) / step - 1e-9))
    last, out = None, []
    while True:
        seconds = base + count * step
        frame = first + round((seconds - in_file) * fps)
        if frame >= end:
            return out
        if frame >= first and frame != last:
            out.append((frame, count + 1))
            last = frame
        count += 1


# -- compound clips ----------------------------------------------------------
def remember_compound(media_id, file, in_file):
    """A compound clip Clipse wrapped a song in: which file, and how far into it the compound's first frame is."""
    if not media_id or not file:
        return
    known = paths.read_json(COMPOUNDS_FILE, {})
    known = known if isinstance(known, dict) else {}
    known.pop(media_id, None)
    known[media_id] = {"file": file, "in_file": round(float(in_file), 3)}
    while len(known) > MAX_COMPOUNDS:
        del known[next(iter(known))]
    paths.write_json(COMPOUNDS_FILE, known)


def _compound(media_id):
    known = paths.read_json(COMPOUNDS_FILE, {})
    hit = known.get(media_id) if isinstance(known, dict) else None
    return hit if isinstance(hit, dict) and hit.get("file") else None


# -- which clip --------------------------------------------------------------
def _pool_item(item):
    try:
        return item.GetMediaPoolItem()
    except Exception:
        return None


def _file_of(item):
    pool = _pool_item(item)
    try:
        return str(pool.GetClipProperty("File Path") or "") if pool is not None else ""
    except Exception:
        return ""


def _sound_items(timeline):
    for track in range(1, int(timeline.GetTrackCount("audio") or 0) + 1):
        yield from timeline.GetItemListInTrack("audio", track) or []


def _same_file(a, b):
    return bool(a and b) and os.path.realpath(a) == os.path.realpath(b)


def _named_after(pool, media_pool):
    """The file a compound clip is named after: Clipse names one like_this after its song (and did before it remembered
    them) - sweet_nina_leimoti is Sweet Nina - Leimoti.mov."""
    from .stills import like_this
    wanted = str(pool.GetName() or "")

    def look(folder):
        for clip in folder.GetClipList() or []:
            file = str(clip.GetClipProperty("File Path") or "")
            if file and clip.GetClipProperty("Type") == "Audio" \
                    and like_this(os.path.splitext(str(clip.GetName() or ""))[0]) == wanted:
                return file
        for inner in folder.GetSubFolderList() or []:
            found = look(inner)
            if found:
                return found
        return ""
    return look(media_pool.GetRootFolder()) if media_pool is not None else ""


def _whats_in(item, song, fps, media_pool=None):
    """(file, how far into it the clip's first frame is, in seconds) - None when it can't be known."""
    left = float(item.GetLeftOffset() or 0) / fps
    file = _file_of(item)
    if file:
        return file, left
    pool = _pool_item(item)
    remembered = _compound(pool.GetMediaId()) if pool is not None else None
    if remembered:
        return remembered["file"], float(remembered.get("in_file") or 0) + left
    named = _named_after(pool, media_pool) if pool is not None else ""
    if named:
        return named, left
    return (song, left) if song else None


def choose(timeline, song, fps, media_pool=None):
    """(the clip on the timeline, its file, seconds into the file), or (None, what to say)."""
    try:
        chosen = timeline.GetSelectedClips() or []
        chosen = list(chosen.values()) if isinstance(chosen, dict) else list(chosen)
    except Exception:
        chosen = []
    for item in chosen:
        found = _whats_in(item, song, fps, media_pool)
        if found:
            return item, *found
    if chosen:
        return None, "Highlight the song in the picker first"
    from .markers import playhead
    start = int(timeline.GetStartFrame() or 0)
    here = playhead(timeline) + start
    items = list(_sound_items(timeline))
    if song:
        uses = [item for item in items if _same_file(_file_of(item), song)]
        if uses:
            item = min(uses, key=lambda i: 0 if int(i.GetStart()) <= here < int(i.GetEnd())
                       else min(abs(int(i.GetStart()) - here), abs(int(i.GetEnd()) - here)))
            return item, song, float(item.GetLeftOffset() or 0) / fps
    under = sorted((item for item in items if int(item.GetStart()) <= here < int(item.GetEnd())),
                   key=lambda i: int(i.GetStart()) - int(i.GetEnd()))
    for item in under:
        found = _whats_in(item, song, fps, media_pool)
        if found:
            return item, *found
    return None, "Select the song on the timeline first" if not under else "Highlight the song in the picker first"


# -- marking -----------------------------------------------------------------
def mark(timeline, song="", bars=False, run="", media_pool=None):
    """(worked, what to say). Markers of an earlier run over the same clip are replaced."""
    from . import markers as mk
    from . import sound_analysis as sa
    fps = float(timeline.GetSetting("timelineFrameRate") or 24) or 24
    start = int(timeline.GetStartFrame() or 0)
    picked = choose(timeline, song, fps, media_pool)
    if picked[0] is None:
        return False, picked[1]
    item, file, in_file = picked
    grid = sa.beats(file)
    name = os.path.splitext(os.path.basename(file))[0]
    if grid is None:
        return False, f"No steady beat in {name}"
    bpm, beat0 = grid
    bar0 = sa.bar_start(file, bpm, beat0) if bars else 0
    first, end = int(item.GetStart()) - start, int(item.GetEnd()) - start
    frames = beat_frames(bpm, beat0, bar0, BEATS_IN_A_BAR if bars else 1, first, end, in_file, fps)
    if not frames:
        return False, f"No beat falls inside {name} here"
    for frame, info in mk.markers(timeline).items():
        if first <= frame < end and is_ours(info):
            timeline.DeleteMarkerAtFrame(frame)
    data = f"{DATA}:{run}" if run else DATA
    print(f"[beats] {name}: {bpm} BPM, {len(frames)} from frame {frames[0][0]}", flush=True)
    placed = sum(bool(timeline.AddMarker(frame, COLOUR, f"Bar {count}" if bars else "Beat", "", 1, data))
                 for frame, count in frames)  # (where a marker of yours sits already, Resolve says no: yours stays)
    if not placed:
        return False, "Resolve didn't take the markers"
    print(f"[beats] placed {placed} of {len(frames)}", flush=True)
    return True, f"{placed} markers"


def clear(timeline, run):
    """Undo: the markers of that run taken away."""
    from . import markers as mk
    data = f"{DATA}:{run}"
    gone = 0
    for frame, info in mk.markers(timeline).items():
        if str((info or {}).get("customData") or "") == data:
            gone += bool(timeline.DeleteMarkerAtFrame(frame))
    return gone


def start(bars=False, song="", run="", undo=False):
    """Runs it as a program of its own; its output goes to the logs folder's beats.log. Returns the process."""
    import subprocess
    from .launch import command
    args = [f"--run={run}"] + (["--undo"] if undo else []) + (["--bars"] if bars else []) + ([f"--song={song}"] if song else [])
    with open(paths.log("beats.log"), "a") as log:
        return subprocess.Popen(command("beats", *args, windowless=True),
                                stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT)


def _argument(name):
    return next((a.split("=", 1)[1] for a in sys.argv if a.startswith(f"--{name}=")), "")


def main():
    from . import resolve_client as rc
    from .client import send
    resolve = rc.connect_to_resolve(timeout=10)
    worked, message = False, "Resolve didn't answer"
    if resolve is not None:
        try:
            project = resolve.GetProjectManager().GetCurrentProject()
            timeline = project.GetCurrentTimeline() if project else None
            if timeline is None:
                message = "Open a timeline first"
            elif "--undo" in sys.argv:
                worked, message = True, f"{clear(timeline, _argument('run'))} markers taken back"
            else:
                worked, message = mark(timeline, _argument("song"), "--bars" in sys.argv, _argument("run"),
                                       project.GetMediaPool())
        except Exception as e:
            import traceback
            traceback.print_exc()
            message = f"Marking the beats stopped: {e}"
    print(f"[beats] {message}", flush=True)
    if not worked:
        try:
            send(b"SAY:" + message.encode("utf-8"))
        except Exception:
            pass


if __name__ == "__main__":
    main()
