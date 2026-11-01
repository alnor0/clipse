"""Subtitles split where a phrase ends ("Tidy the subtitles").

Resolve writes subtitles from the speech, but cuts them when a line is
full: "...for DaVinci Resolve, because I" / "was tired of clicking...".
This reads those subtitles off the timeline, splits the same words again
where a phrase ends - after a comma or a full stop, before "because" /
"and" / "that", never leaving "the" or "to" hanging - and puts the result
on a subtitle track of its own. The ones Resolve wrote stay on their
track, switched off.

Resolve only says when each subtitle starts and ends, not each word. So a
word's time is worked out from where it sits in its subtitle (by length);
a subtitle that starts mid-way through an old one starts at about, not
exactly, the right moment.

What works from a script (tried in 21.1.1): an .srt file imports into the
Media Pool as a "Subtitle" clip and AppendToTimeline puts its subtitles
on the timeline - where, see tidy_subtitles. Subtitles read back with
GetStart / GetEnd / GetName. An .srt's times count from the timeline's
start, whatever timecode that is."""
import os
import re
import time

from . import stills
from . import paths

FOLDER = paths.cache("subtitles")
PAUSE_SECONDS = 0.6       # a gap this long between two subtitles is a pause: nothing is joined across it
SHORTEST_SECONDS = 0.7    # a subtitle shown for less than this can't be read

_AFTER = ",;:–—-"   # a line may well end after one of these
# ...or just before one of these (and, but, because, that ... in the languages Resolve listens for)
_BEFORE = set("""
and but or because so that which when if while then who where as than although though unless until since
og men eller fordi så at som når hvis mens da der hvor end selvom indtil siden
och för att eftersom medan där när
und aber oder weil dass wenn während dann wo als obwohl bis
et mais ou parce que quand si pendant alors qui où comme
y pero o porque que cuando si mientras entonces quien donde como
en maar of omdat dat wanneer als terwijl dan wie waar
e ma perché che quando se mentre poi chi dove come
""".split())
# all right before these (in, on, with ...)
_SOFT = set("""
in on at to with for from of by about into over under after before through without between
i på til med for fra af om over under efter før ved gennem uden mellem
mit für von zu bei nach vor durch ohne zwischen auf aus
avec pour de à dans sur sous après avant par sans entre
con para de a en sobre bajo después antes por sin entre
met voor van naar bij na door zonder tussen op uit
""".split())
# never end a line on one of these (the, a, my, to, very ...)
_GLUE = set("""
the a an my your his her its our their this that these those to of very no not
en et den det de min mit din dit sin sit vores jeres at meget ikke ingen
der die das ein eine mein dein sein ihr unser sehr nicht kein
le la les un une des mon ton son notre votre leur très ne pas
el la los las un una mi tu su nuestro muy no
de het een mijn jouw zijn haar onze zeer niet geen
il lo gli una mio tuo suo nostro molto non
""".split())


def _bare(word):
    return word.lower().strip(".,;:!?\"'()[]–—-")


def split_by_sense(words, limit, last_may_be_short=True, breaks=()):
    """`words` cut into runs of at most `limit` characters, where a phrase
    ends rather than where the line is full. `breaks`: places (a count of
    words) where a cut is wanted anyway - a pause in the speech. The runs
    as (first word, one past the last word)."""
    n = len(words)
    if n == 0:
        return []
    lengths = [len(w) for w in words]
    wanted = set(breaks)

    def cost(i, j):
        size = sum(lengths[i:j]) + (j - i - 1)
        if size > limit and j - i > 1:
            return None  # too long (one endless word has to go somewhere)
        spare = max(0, limit - size)
        c = spare * spare / limit * (0.15 if (j == n and last_may_be_short) else 1.0)  # fill the line
        if j < n:
            end, following = words[j - 1], _bare(words[j])
            if j in wanted:
                c -= 80                       # a pause: cut here
            elif end[-1:] in ".!?…":
                c -= 40                       # the sentence ends
            elif end[-1:] in _AFTER:
                c -= 25
            elif following in _BEFORE:
                c -= 18
            elif following in _SOFT:
                c -= 8
            if _bare(end) in _GLUE and j not in wanted:
                c += 60                       # "...the" / "...to" left hanging
            if j - i == 1 and end[-1:] not in ".!?":
                c += 30                       # a word on its own
            elif size < limit * 0.45 and end[-1:] not in ".!?" and j not in wanted:
                c += 14                       # too little to be worth a subtitle of its own
        if any(i < b < j for b in wanted):
            c += 200                          # never across a pause
        return c

    best = [None] * (n + 1)
    best[0] = (0.0, None)
    for j in range(1, n + 1):
        for i in range(max(0, j - 40), j):
            if best[i] is None:
                continue
            c = cost(i, j)
            if c is not None and (best[j] is None or best[i][0] + c < best[j][0]):
                best[j] = (best[i][0] + c, i)
    runs, j = [], n
    while j > 0:
        i = best[j][1] if best[j] is not None else j - 1
        runs.append((i, j))
        j = i
    return runs[::-1]


def tidy(subtitles, limit=42, fps=24.0, lines="single"):
    """[(start frame, end frame, text)] as Resolve wrote them -> the same
    words split where the phrases end. lines="double": two lines to a
    subtitle, each of at most `limit` characters."""
    subtitles = sorted((int(s), int(e), " ".join(str(t).split())) for s, e, t in subtitles if str(t).strip())
    words, starts, ends, breaks = [], [], [], []
    pause = PAUSE_SECONDS * fps
    previous_end = None
    for start, end, text in subtitles:
        parts = text.split()
        if previous_end is not None and start - previous_end >= pause:
            breaks.append(len(words))  # the speaker stopped here
        total = sum(len(p) + 1 for p in parts)
        at = float(start)
        for part in parts:  # a word's share of the subtitle's time goes by its length
            share = (len(part) + 1) / total * (end - start)
            words.append(part)
            starts.append(at)
            ends.append(at + share)
            at += share
        previous_end = end
    runs = [(i, j, None) for i, j in split_by_sense(words, limit, breaks=breaks)]
    if lines == "double":  # two lines that belong together make one subtitle: no pause, no full stop between them
        pairs, k = [], 0
        while k < len(runs):
            i, j, _ = runs[k]
            if k + 1 < len(runs) and j not in breaks and words[j - 1][-1:] not in ".!?\u2026":
                pairs.append((i, runs[k + 1][1], j))
                k += 2
            else:
                pairs.append((i, j, None))
                k += 1
        runs = pairs
    out = []
    for i, j, line_break in runs:
        text = " ".join(words[i:j]) if line_break is None else \
            " ".join(words[i:line_break]) + "\n" + " ".join(words[line_break:j])
        out.append([int(round(starts[i])), int(round(ends[j - 1])), text])
    shortest = int(round(SHORTEST_SECONDS * fps))
    for k, sub in enumerate(out):  # no gaps inside a sentence, nothing too short to read, nothing overlapping
        following = out[k + 1][0] if k + 1 < len(out) else None
        if following is not None and 0 <= following - sub[1] < pause:
            sub[1] = following
        if sub[1] - sub[0] < shortest:
            sub[1] = sub[0] + shortest if following is None else min(max(sub[1], sub[0] + shortest), max(following, sub[1]))
        sub[1] = max(sub[1], sub[0] + 1)
    return [tuple(sub) for sub in out]


def _stamp(seconds):
    ms = int(round(max(0.0, seconds) * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def srt_text(subtitles, fps, first_frame=0):
    """The subtitles as the text of an .srt file; times count from `first_frame`."""
    blocks = []
    for n, (start, end, text) in enumerate(subtitles, 1):
        blocks.append(f"{n}\n{_stamp((start - first_frame) / fps)} --> {_stamp((end - first_frame) / fps)}\n{text}\n")
    return "\n".join(blocks)


# -- in Resolve --
def read_track(timeline, index):
    return [(int(it.GetStart()), int(it.GetEnd()), str(it.GetName() or ""))
            for it in timeline.GetItemListInTrack("subtitle", index) or []]


def _track_to_tidy(timeline):
    """The subtitle track to work on: the highest one that's switched on and has subtitles."""
    for index in range(timeline.GetTrackCount("subtitle"), 0, -1):
        try:
            on = timeline.GetIsTrackEnabled("subtitle", index)
        except Exception:
            on = True
        if on and timeline.GetItemListInTrack("subtitle", index):
            return index
    return None


def _own_bin(media_pool):
    return stills.app_bin(media_pool)


def tidy_subtitles(resolve, options=None):
    """The subtitles of the open timeline, split where the phrases end, on
    a new subtitle track; the old track is switched off, not removed.
    (worked, message)"""
    options = options or {}
    try:
        project = resolve.GetProjectManager().GetCurrentProject()
        timeline = project.GetCurrentTimeline() if project is not None else None
    except Exception:
        timeline = None
    if timeline is None:
        return False, "Open a timeline first"
    old_track = _track_to_tidy(timeline)
    if old_track is None:
        return False, "No subtitles on this timeline yet - run Subtitles from speech first"
    before = read_track(timeline, old_track)
    try:
        fps = float(timeline.GetSetting("timelineFrameRate"))
    except (TypeError, ValueError):
        fps = 24.0
    try:
        limit = max(8, min(60, int(options.get("subtitle_chars", 42))))
    except (TypeError, ValueError):
        limit = 42
    after = tidy(before, limit, fps, options.get("subtitle_lines", "single"))
    if [t for _s, _e, t in after] == [t for _s, _e, t in sorted(before)]:
        return False, "These subtitles are already split where the phrases end"
    first_frame = int(timeline.GetStartFrame())
    os.makedirs(FOLDER, exist_ok=True)
    safe = re.sub(r"[^\w\- ]+", "_", str(timeline.GetName() or "timeline")).strip() or "timeline"
    path = os.path.join(FOLDER, f"{safe} {time.strftime('%Y-%m-%d %H.%M.%S')}.srt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(srt_text(after, fps, first_frame))
    media_pool = project.GetMediaPool()
    current = media_pool.GetCurrentFolder()
    try:
        media_pool.SetCurrentFolder(_own_bin(media_pool))
        imported = media_pool.ImportMedia([path]) or []
    finally:
        if current is not None:
            media_pool.SetCurrentFolder(current)
    if not imported:
        return False, "Resolve wouldn't take the subtitle file"
    # Where Resolve puts a subtitle file is its own business (tried many ways in 21.1.1): it
    # ignores the track and the frame it's asked for, puts the subtitles on a subtitle track
    # that's switched on, and counts their times from the end of what's on subtitle track 1.
    # With another track switched on it sometimes puts them nowhere at all. What worked every
    # time: one subtitle track switched on, empty, and nothing on track 1. So: a new empty track
    # in FIRST place (the others move up one), everything else switched off - then look where
    # they landed, and take it all back if that's not where they belong.
    count = timeline.GetTrackCount("subtitle")
    were_on = [index for index in range(1, count + 1) if timeline.GetIsTrackEnabled("subtitle", index)]
    if not timeline.AddTrack("subtitle", {"index": 1}):
        return False, "Resolve wouldn't add a subtitle track"
    old_track += 1
    others = range(2, count + 2)
    for index in others:
        timeline.SetTrackEnable("subtitle", index, False)
    timeline.SetTrackEnable("subtitle", 1, True)
    was_there = {index: sorted(read_track(timeline, index)) for index in others}

    def strays():
        """What's on the timeline now that wasn't before - on the new track or anyone else's."""
        found = list(timeline.GetItemListInTrack("subtitle", 1) or [])
        for index in others:
            left = list(was_there[index])
            for item in timeline.GetItemListInTrack("subtitle", index) or []:
                key = (int(item.GetStart()), int(item.GetEnd()), str(item.GetName() or ""))
                if key in left:
                    left.remove(key)
                else:
                    found.append(item)
        return found

    def in_place():
        there = read_track(timeline, 1)
        return len(there) == len(after) and abs(min(s for s, _e, _t in there) - after[0][0]) <= 1

    landed_right = False
    if timeline.GetIsTrackEnabled("subtitle", 1):  # (else they'd go onto one of YOUR tracks: don't even try)
        for clip_info in ([{"mediaPoolItem": imported[0], "trackIndex": 1, "recordFrame": first_frame}], [imported[0]]):
            media_pool.AppendToTimeline(clip_info)
            landed_right = in_place()
            if landed_right:
                break
            wrong = strays()
            there = read_track(timeline, 1)
            print(f"[subtitles] {len(there)} of {len(after)} subtitles on the new track"
                  + (f", the first at {min(s for s, _e, _t in there)} instead of {after[0][0]}" if there else "")
                  + f"; {len(wrong)} taken off again")
            if wrong:
                timeline.DeleteClips(wrong, False)
    if not landed_right:  # everything back as it was
        try:
            timeline.DeleteTrack("subtitle", 1)
            for index in range(1, count + 1):
                timeline.SetTrackEnable("subtitle", index, index in were_on)
        except Exception as e:
            print(f"[subtitles] couldn't put the tracks back as they were: {e}")
        return False, "Resolve didn't put the tidied subtitles where they belong - yours are as they were"
    landed = len(after)
    try:
        timeline.SetTrackName("subtitle", 1, "Tidied")
    except Exception as e:
        print(f"[subtitles] the new track keeps Resolve's name: {e}")
    return True, (f"Tidied: {len(before)} subtitles are now {landed}, on a new subtitle track - "
                  f"the old ones are still there (track {old_track}), switched off")
