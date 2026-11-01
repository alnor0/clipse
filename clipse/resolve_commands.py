"""Things Resolve can be told to do from the picker's action list (>):
go to a page, render with a preset, a new timeline, another track, a
marker, a colour for the clip under the playhead ...

Every command takes Resolve and returns (worked, message). The message
is shown in the picker when it didn't work - or when there's nothing to
see in Resolve itself (Save project). Only the scripting API is used.
"""
import os
import re
import sys

PAGES = [("media", "Media"), ("cut", "Cut"), ("edit", "Edit"), ("fusion", "Fusion"), ("color", "Color"),
         ("fairlight", "Fairlight"), ("deliver", "Deliver")]

# Resolve's own clip colours, in the order its menu has them
CLIP_COLORS = ["Orange", "Apricot", "Yellow", "Lime", "Olive", "Green", "Teal", "Navy", "Blue", "Purple",
               "Violet", "Pink", "Tan", "Beige", "Brown", "Chocolate"]
CLIP_COLOR_HEX = {
    "Orange": "#eb6e01", "Apricot": "#ffa833", "Yellow": "#d4ad1f", "Lime": "#9fc615", "Olive": "#5e9921",
    "Green": "#448f65", "Teal": "#00987f", "Navy": "#15627b", "Blue": "#4376a1", "Purple": "#996ca4",
    "Violet": "#d0568d", "Pink": "#e98cb5", "Tan": "#b9af97", "Beige": "#c4a07c", "Brown": "#996601",
    "Chocolate": "#8c5a3f",
}


def _project(resolve):
    manager = resolve.GetProjectManager() if resolve is not None else None
    return manager.GetCurrentProject() if manager is not None else None


def _timeline(resolve):
    project = _project(resolve)
    return project.GetCurrentTimeline() if project is not None else None


def _call(obj, name, *args):
    """obj.name(*args) - None when this Resolve doesn't have it (an older version)."""
    method = getattr(obj, name, None)
    return method(*args) if callable(method) else None


def open_page(resolve, page):
    name = dict(PAGES).get(page, page)
    if resolve is None or not resolve.OpenPage(page):
        return False, f"Couldn't open the {name} page"
    return True, f"{name} page"


def render_presets(resolve):
    project = _project(resolve)
    try:
        return [str(name) for name in (project.GetRenderPresetList() or [])] if project is not None else []
    except Exception as e:
        print(f"[commands] couldn't read the render presets: {e}")
        return []


def _put_marks_back(timeline, marks):
    """The timeline's in / out marks as they were before a render borrowed them."""
    try:
        timeline.ClearMarkInOut()
        for kind in ("video", "audio"):
            mark = (marks or {}).get(kind) or {}
            if "in" in mark and "out" in mark:
                timeline.SetMarkInOut(int(mark["in"]), int(mark["out"]), kind)
    except Exception as e:
        print(f"[commands] couldn't put the in / out marks back: {e}")


def render(resolve, preset, just_clip=False):
    """Adds the current timeline to the render queue with `preset` and
    starts it. Never writes over a file that's already there: the job
    is left in the queue for you to look at instead.

    Resolve renders what's between the timeline's in and out marks (all
    of it when nothing is marked). just_clip: only the clip under the
    playhead - the marks go around it while the job is made (the job keeps
    its range) and are put back as they were."""
    project = _project(resolve)
    timeline = project.GetCurrentTimeline() if project is not None else None
    if timeline is None:
        return False, "Open a timeline first"
    if project.IsRenderingInProgress():
        return False, "Resolve is rendering already"
    title, marks = timeline.GetName(), None
    if just_clip:
        item = _call(timeline, "GetCurrentVideoItem")
        if item is None:
            return False, "The playhead isn't over a clip"
        first, last = int(item.GetStart()), int(item.GetEnd()) - 1
        title = f"{title} - {os.path.splitext(str(item.GetName() or 'clip'))[0]}"
    if not project.LoadRenderPreset(preset):
        return False, f"Couldn't load the render preset {preset}"
    if just_clip:
        marks = _call(timeline, "GetMarkInOut") or {}
        if not _call(timeline, "SetMarkInOut", first, last):
            return False, "This Resolve can't render a part of the timeline from a script (it needs 19.1 or newer)"
    try:
        job = project.AddRenderJob()  # with the place and name chosen on the Deliver page, if any
        details = next((j for j in (project.GetRenderJobList() or []) if j.get("JobId") == job), {}) if job else {}
        folder = str(details.get("TargetDir") or "")
        if not job or (just_clip and folder):
            # nowhere to save yet, or somewhere Resolve won't write: a Renders folder of our own.
            # A clip on its own: next to the timeline's renders, under a name of its own.
            usual_name = os.path.splitext(str(details.get("OutputFilename") or ""))[0]
            if job:
                project.DeleteRenderJob(job)
            else:
                folder, problem = _render_folder(resolve)
                if not folder:
                    return False, problem
            project.SetRenderSettings({"TargetDir": folder, "CustomName": _free_name(folder, title)})
            job = project.AddRenderJob()
            if just_clip and usual_name:  # the next render of the whole timeline keeps its usual name
                project.SetRenderSettings({"CustomName": usual_name})
            if not job:
                return False, f"Resolve wouldn't add the render job for {folder} - try once from the Deliver page"
    finally:
        if just_clip:
            _put_marks_back(timeline, marks)
    details = next((j for j in (project.GetRenderJobList() or []) if j.get("JobId") == job), {})
    folder, name = str(details.get("TargetDir") or ""), str(details.get("OutputFilename") or "")
    if folder and name and os.path.exists(os.path.join(folder, name)):
        return False, f"{name} is already in {folder} - the job is in the render queue, not started"
    if not project.StartRendering(job):
        return False, "The job is in the render queue, but Resolve didn't start it"
    what = name or ("the clip" if just_clip else "the timeline")
    return True, f"Rendering {what} with {preset}" + (f" to {folder}" if folder else "")


def _render_folder(resolve):
    """(a folder Resolve will render into, or None and why not). On Linux
    Resolve only renders into its media storage (Preferences > Media
    Storage) - anywhere else it answers "Render Path Inaccessible" - so
    that's where the folder goes; elsewhere it's the Movies / Videos folder."""
    places = []
    try:
        places = [str(v) for v in (resolve.GetMediaStorage().GetMountedVolumeList() or [])]
    except Exception as e:
        print(f"[commands] couldn't read the media storage: {e}")
    home = os.path.expanduser("~")
    if not sys.platform.startswith("linux"):
        places = [os.path.join(home, "Movies" if sys.platform == "darwin" else "Videos")] + places
    for place in places:
        folder = os.path.join(place, "Renders")
        try:
            os.makedirs(folder, exist_ok=True)
        except OSError:
            continue
        if os.access(folder, os.W_OK):
            return folder, ""
    return None, ("Resolve has nowhere to render to - add a folder in Preferences \u203a Media Storage"
                  if sys.platform.startswith("linux") else "Choose where to save on the Deliver page first")


def _free_name(folder, name):
    """`name`, or "name 2", "name 3" ... - whichever no file in `folder` has yet."""
    name = "".join(c for c in name if c not in '\\/:*?"<>|').strip() or "Timeline"
    taken = {os.path.splitext(f)[0].lower() for f in os.listdir(folder)}
    free, n = name, 2
    while free.lower() in taken:
        free, n = f"{name} {n}", n + 1
    return free


# Subtitles from speech: the choices Resolve offers a script (its Create Subtitles from Audio
# window has the same ones). (what's saved in Settings, what Settings shows)
SUBTITLE_LANGUAGES = [
    ("auto", "Work it out from the speech"), ("danish", "Danish"), ("dutch", "Dutch"), ("english", "English"),
    ("french", "French"), ("german", "German"), ("italian", "Italian"), ("japanese", "Japanese"), ("korean", "Korean"),
    ("mandarin_simplified", "Mandarin (simplified)"), ("mandarin_traditional", "Mandarin (traditional)"),
    ("norwegian", "Norwegian"), ("portuguese", "Portuguese"), ("russian", "Russian"), ("spanish", "Spanish"),
    ("swedish", "Swedish"),
]
SUBTITLE_LINES = [("single", "One line at a time"), ("double", "Two lines")]
SUBTITLE_PRESETS = [("default", "Normal"), ("teletext", "Teletext"), ("netflix", "Netflix")]


def _subtitle_settings(resolve, options):
    """`options` (the app's settings) as the table Resolve wants. Only what
    this Resolve has a name for goes in - the rest is left to it."""
    options = options or {}

    def named(name):
        try:
            return getattr(resolve, name, None)
        except Exception:
            return None

    wanted = [
        ("SUBTITLE_LANGUAGE", named("AUTO_CAPTION_" + str(options.get("subtitle_language", "auto")).upper())),
        ("SUBTITLE_CAPTION_PRESET", named({"teletext": "AUTO_CAPTION_TELETEXT", "netflix": "AUTO_CAPTION_NETFLIX"}.get(
            options.get("subtitle_preset"), "AUTO_CAPTION_SUBTITLE_DEFAULT"))),
        ("SUBTITLE_LINE_BREAK", named("AUTO_CAPTION_LINE_DOUBLE" if options.get("subtitle_lines") == "double"
                                      else "AUTO_CAPTION_LINE_SINGLE")),
    ]
    try:
        wanted.append(("SUBTITLE_CHARS_PER_LINE", max(1, min(60, int(options.get("subtitle_chars", 42))))))
        wanted.append(("SUBTITLE_GAP", max(0, min(10, int(options.get("subtitle_gap", 0))))))
    except (TypeError, ValueError):
        pass
    settings = {}
    for key_name, value in wanted:
        key = named(key_name)
        if key is not None and value is not None:
            settings[key] = value
    return settings


def subtitles_from_speech(resolve, options=None):
    """Resolve listens to the timeline and writes subtitles on a subtitle
    track (Timeline > Create Subtitles from Audio). How they're split -
    language, longest line, one or two lines, the gap between them - comes
    from Settings > Timeline > Subtitles. How they LOOK (font, size, colour,
    place) is the subtitle track's own style in Resolve's Inspector: no
    script can set that. The call comes straight back and Resolve carries
    on in the background - seen in 21.1.1."""
    timeline = _timeline(resolve)
    if timeline is None:
        return False, "Open a timeline first"
    settings = _subtitle_settings(resolve, options)
    started = _call(timeline, "CreateSubtitlesFromAudio", settings) if settings else \
        _call(timeline, "CreateSubtitlesFromAudio")
    if not started:
        return False, "Resolve wouldn't start - subtitles from speech need Resolve Studio 18.5 or newer"
    return True, "Resolve is writing subtitles from the speech - they show on a subtitle track when it's done"


def stop_rendering(resolve):
    project = _project(resolve)
    if project is None or not project.IsRenderingInProgress():
        return False, "Nothing is rendering"
    project.StopRendering()
    return True, "Stopped rendering"


def new_timeline(resolve):
    project = _project(resolve)
    if project is None:
        return False, "No project open in Resolve"
    taken = set()
    for i in range(1, int(project.GetTimelineCount() or 0) + 1):
        timeline = project.GetTimelineByIndex(i)
        if timeline is not None:
            taken.add(timeline.GetName())
    n = len(taken) + 1
    while f"Timeline {n}" in taken:
        n += 1
    timeline = project.GetMediaPool().CreateEmptyTimeline(f"Timeline {n}")
    if not timeline:
        return False, "Resolve didn't make the timeline"
    project.SetCurrentTimeline(timeline)
    return True, f"Timeline {n}"


def duplicate_timeline(resolve):
    project, timeline = _project(resolve), _timeline(resolve)
    if timeline is None:
        return False, "Open a timeline first"
    copy = _call(timeline, "DuplicateTimeline")
    if not copy:
        return False, "This Resolve can't duplicate a timeline from a script"
    project.SetCurrentTimeline(copy)
    return True, f"{copy.GetName()}"


def add_track(resolve, kind):
    timeline = _timeline(resolve)
    if timeline is None:
        return False, "Open a timeline first"
    added = _call(timeline, "AddTrack", kind, "stereo") if kind == "audio" else _call(timeline, "AddTrack", kind)
    if not added:
        return False, f"Resolve didn't add the {kind} track"
    return True, f"{kind.capitalize()} track {timeline.GetTrackCount(kind)}"


def remove_empty_tracks(resolve):
    """Every video and audio track with nothing on it goes (never the last one of a kind)."""
    from .resolve_client import clean_empty_tracks
    timeline = _timeline(resolve)
    if timeline is None:
        return False, "Open a timeline first"
    before = timeline.GetTrackCount("video") + timeline.GetTrackCount("audio")
    clean_empty_tracks(timeline)
    gone = before - (timeline.GetTrackCount("video") + timeline.GetTrackCount("audio"))
    if not gone:
        return False, "No empty tracks on this timeline"
    return True, f"Removed {gone} empty track{'s' if gone != 1 else ''}"


# what a track can be named after (see name_tracks)
_KINDS = ("Pictures", "Video", "Titles", "Adjustment", "Fusion", "Compound clips", "Timelines", "Generators",
          "Music", "Sound effects", "Video sound", "Sound")
_DEFAULT_NAME = re.compile(r"^(video|audio|v|a) ?\d+$", re.IGNORECASE)  # as Resolve names a new track


def _kind_of(item, track_type, sound_kind):
    """What one clip on the timeline is, in a word or two."""
    try:
        pool_item = item.GetMediaPoolItem()
    except Exception:
        pool_item = None
    name = str(item.GetName() or "")
    if pool_item is None:  # made on the timeline: a title, an adjustment clip, a generator ...
        low = name.lower()
        if "adjustment" in low:
            return "Adjustment"
        if "text" in low or "title" in low or "subtitle" in low:
            return "Titles"
        if "fusion" in low:
            return "Fusion"
        return "Generators" if track_type == "video" else "Sound"
    kind = str(pool_item.GetClipProperty("Type") or "")
    if track_type == "audio":
        if "Video" in kind:
            return "Video sound"
        return {True: "Music", False: "Sound effects"}.get(sound_kind(name) if sound_kind else None, "Sound")
    if kind == "Still":
        return "Pictures"
    if "Compound" in kind:
        return "Compound clips"
    if "Timeline" in kind:
        return "Timelines"
    if "Fusion" in kind:
        return "Fusion"
    return "Video"


def _track_name(kinds):
    """The name for a track holding clips of these kinds: what most of it
    is, or its two main kinds when it's a mix."""
    counts = {}
    for kind in kinds:
        counts[kind] = counts.get(kind, 0) + 1
    ranked = sorted(counts, key=lambda k: -counts[k])
    if len(ranked) == 1 or counts[ranked[0]] >= 0.7 * len(kinds):
        return ranked[0]
    return f"{ranked[0]} + {ranked[1].lower()}"


def name_tracks(resolve, sound_kind=None):
    """Names each track after what's on it (Pictures, Video, Music, Sound
    effects ...). Only tracks still called "Video 3" / "Audio 2", or named
    by this before - a name you gave a track is yours. sound_kind: clip
    name -> True (music) / False (a sound effect) / None (not known)."""
    timeline = _timeline(resolve)
    if timeline is None:
        return False, "Open a timeline first"
    ours = {k.lower() for k in _KINDS}
    named = 0
    for track_type in ("video", "audio"):
        for index in range(1, int(timeline.GetTrackCount(track_type) or 0) + 1):
            current = str(timeline.GetTrackName(track_type, index) or "")
            mine = all(part.strip().lower() in ours for part in current.split("+")) if current else True
            if current and not _DEFAULT_NAME.match(current) and not mine:
                continue
            items = (timeline.GetItemListInTrack(track_type, index) or [])[:60]  # plenty to tell
            if not items:
                continue
            name = _track_name([_kind_of(item, track_type, sound_kind) for item in items])
            if name != current and timeline.SetTrackName(track_type, index, name):
                named += 1
    if not named:
        return False, "Nothing to name - every track has its name already"
    return True, f"Named {named} track{'s' if named != 1 else ''}"


def _playhead_frame(timeline):
    """The playhead as a frame number counted from the start of the timeline."""
    from .resolve_client import tc_to_frame
    fps = int(round(float(timeline.GetSetting("timelineFrameRate") or 24)))
    return tc_to_frame(timeline.GetCurrentTimecode(), fps) - int(timeline.GetStartFrame() or 0)


def add_marker(resolve, color="Blue"):
    timeline = _timeline(resolve)
    if timeline is None:
        return False, "Open a timeline first"
    try:
        frame = _playhead_frame(timeline)
    except (ValueError, AttributeError, TypeError):
        return False, "Couldn't read where the playhead is"
    if not timeline.AddMarker(frame, color, "Marker", "", 1):  # (21.1.1 says no to one without a name - markers.py)
        return False, "There's a marker at the playhead already"
    return True, "Marker added"


def _when(seconds):
    """Seconds -> "1:04.5" (or "1:02:04.5"): what a person, or a chat assistant, reads easily."""
    tenths = int(round(seconds * 10))
    minutes, tenths = divmod(tenths, 600)
    hours, minutes = divmod(minutes, 60)
    clock = f"{minutes:02d}:{tenths // 10:02d}.{tenths % 10}" if hours else f"{minutes}:{tenths // 10:02d}.{tenths % 10}"
    return f"{hours}:{clock}" if hours else clock


def _timing(timeline):
    """(fps, first frame, drop-frame?) of a timeline."""
    fps = float(timeline.GetSetting("timelineFrameRate") or 24) or 24
    start = int(timeline.GetStartFrame() or 0)
    drop = ";" in str(timeline.GetCurrentTimecode() or "")  # (drop-frame: Resolve writes a ";" before the frames)
    return fps, start, drop


def _marker_lines(timeline, fps, start, drop):
    from .timeline_tools import frames_tc
    lines = []
    markers = timeline.GetMarkers() or {}
    try:  # (hidden by Hide - Show Markers: still yours, still listed - markers.py)
        from .markers import hidden
        kept = {f: dict(m, hidden=True) for f, m in hidden(timeline).items() if float(f) not in {float(k) for k in markers}}
    except Exception:
        kept = {}
    markers = {**markers, **kept}
    from .beats import is_ours
    beats = sum(is_ours(info) for info in markers.values())
    if beats:  # (hundreds of them say nothing to whoever reads this)
        lines.append(f"- {beats} beat markers left out")
    for frame in sorted(markers, key=float):
        info = markers[frame] or {}
        if is_ours(info):
            continue
        at = int(float(frame))
        duration = int(float(info.get("duration") or 1))
        when = _when(at / fps)
        if duration > 1:
            when += f" to {_when((at + duration) / fps)}"
        words = [str(info.get(k) or "").strip() for k in ("name", "note")]
        words = [w for w in words if w]
        colour = str(info.get("color") or "")
        lines.append(f"- {when}  [{frames_tc(start + at, fps, drop)}]  {colour or 'Marker'}"
                     + (": " + " - ".join(words) if words else "") + ("  (hidden)" if info.get("hidden") else ""))
    return lines


def _speech_track(timeline):
    """The subtitle track that holds what's said: the highest one that's on and has subtitles - or, when every one is
    off, the highest that has any (subtitles made from speech only to read them are kept switched off, 2026-10-28)."""
    from .subtitles import _track_to_tidy
    count = int(timeline.GetTrackCount("subtitle") or 0)
    if not count:
        return None
    on = _track_to_tidy(timeline)
    if on:
        return on
    for index in range(count, 0, -1):
        if timeline.GetItemListInTrack("subtitle", index):
            return index
    return None


def _said_lines(timeline, fps, start):
    from .subtitles import read_track
    track = _speech_track(timeline)
    if not track:
        return []
    return [f"- {_when((a - start) / fps)} to {_when((b - start) / fps)}  {text}"
            for a, b, text in read_track(timeline, track) if text.strip()]


def markers_text(timeline):
    """The open timeline's markers as plain text - to paste into a chat assistant (ChatGPT ...) so it knows what
    happens when (2026-10-23: "so it knows when to trigger animation or visuals"). Each marker: when (from the
    timeline's start, and its timecode), how long, its colour, name and note. What's said, when the timeline has
    subtitles. None when there are no markers."""
    if not (timeline.GetMarkers() or {}):
        return None
    fps, start, drop = _timing(timeline)
    length = (int(timeline.GetEndFrame() or start) - start) / fps
    name = str(timeline.GetName() or "Timeline")
    lines = [f"Timeline: {name} ({_when(length)} long, {fps:g} fps)",
             "Times are minutes:seconds from the start of the timeline, then the timecode.", "", "Markers:"]
    lines += _marker_lines(timeline, fps, start, drop)
    said = _said_lines(timeline, fps, start)
    if said:
        lines += ["", "What's said:"] + said
    return "\n".join(lines) + "\n"


def _clip_source(item):
    """(file name, where in it the clip starts - "0:03.2" or "") for a clip from the Media Pool; ("", "") for
    titles, generators, Fusion compositions."""
    try:
        mpi = item.GetMediaPoolItem()
    except Exception:
        mpi = None
    if mpi is None:
        return "", ""
    try:
        name = str(mpi.GetClipProperty("File Name") or "")
    except Exception:
        name = ""
    try:
        clip_fps = float(mpi.GetClipProperty("FPS") or 0) or None
    except Exception:
        clip_fps = None
    try:
        offset = int(item.GetLeftOffset() or 0)
    except Exception:
        offset = 0
    try:
        kind = str(mpi.GetClipProperty("Type") or "")
        frames = int(float(mpi.GetClipProperty("Frames") or 0))
    except Exception:
        kind, frames = "", 0
    # (Resolve gives some clips an offset counted from their source timecode - an hour off - and stills have none)
    sane = offset > 0 and clip_fps and "still" not in kind.lower() and (not frames or offset < frames)
    return name, (_when(offset / clip_fps) if sane else "")


def _on(item):
    try:
        return bool(item.GetClipEnabled())
    except Exception:
        return True


def _item_line(it, fps, start, drop):
    from .timeline_tools import frames_tc
    a, b = int(it.GetStart()), int(it.GetEnd())
    file, from_ = _clip_source(it)
    clip = str(it.GetName() or "Clip")
    where = ", ".join(x for x in ((file if file and file != clip else ""), (f"from {from_}" if from_ else "")) if x)
    return (f"- {_when((a - start) / fps)} to {_when((b - start) / fps)}  [{frames_tc(a, fps, drop)}]  {clip}"
            + (f"  ({where})" if where else "") + ("" if _on(it) else "  (switched off)"))


def timeline_text(timeline, heading=True):
    """Everything on a timeline as plain text with times - to paste into a chat assistant so it can follow the edit
    (2026-10-28: "so you can accurately depict my timeline and understand what is going on"): every clip on every
    track (when, its name, the file and where in it), the markers, and what's said when there are subtitles."""
    from .timeline_tools import frames_tc
    fps, start, drop = _timing(timeline)
    end = int(timeline.GetEndFrame() or start)
    name = str(timeline.GetName() or "Timeline")
    size = "x".join(str(timeline.GetSetting(k) or "") for k in ("timelineResolutionWidth", "timelineResolutionHeight"))
    lines = [f"Timeline: {name} ({_when((end - start) / fps)} long, {fps:g} fps, {size})"]
    if heading:
        lines.append("Times are minutes:seconds from the start of the timeline, then the timecode.")
    video_cuts = {}
    for kind, label in (("video", "Video"), ("audio", "Audio")):
        for index in range(1, int(timeline.GetTrackCount(kind) or 0) + 1):
            items = timeline.GetItemListInTrack(kind, index) or []
            cuts = [(int(it.GetStart()), int(it.GetEnd()), str(it.GetName() or "")) for it in items]
            if kind == "video":
                video_cuts[index] = set(cuts)
            else:  # linked sound usually has the picture's cuts: name the video track, list only the differences
                same = max(video_cuts.items(), key=lambda kv: len(kv[1] & set(cuts)), default=(None, set()))
                if same[0] is not None and items and len(same[1] & set(cuts)) >= 0.8 * len(cuts):
                    items = [it for it, c in zip(items, cuts) if c not in same[1] or not _on(it)]
                    try:
                        track_name = str(timeline.GetTrackName(kind, index) or "")
                    except Exception:
                        track_name = ""
                    title = f"{label} {index}" + (f" ({track_name})" if track_name and track_name != f"{label} {index}" else "")
                    lines += ["", f"{title}: the same cuts as Video {same[0]}" + (", except:" if items else "")]
                    for it in items:
                        lines.append(_item_line(it, fps, start, drop))
                    continue
            try:
                track_name = str(timeline.GetTrackName(kind, index) or "")
            except Exception:
                track_name = ""
            title = f"{label} {index}" + (f" ({track_name})" if track_name and track_name != f"{label[0]}{index}" else "")
            lines += ["", f"{title}:" if items else f"{title}: empty"]
            for it in items:
                lines.append(_item_line(it, fps, start, drop))
    markers = _marker_lines(timeline, fps, start, drop)
    if markers:
        lines += ["", "Markers:"] + markers
    said = _said_lines(timeline, fps, start)
    lines += ["", "What's said:"] + said if said else \
        ["", "What's said: no subtitles on this timeline (Resolve: Timeline \u203a Create Subtitles from Audio)"]
    return "\n".join(lines) + "\n"


def transcript_text(timeline):
    """Only what's said on the timeline, with times - from its subtitles. None when there are none."""
    fps, start, _drop = _timing(timeline)
    said = _said_lines(timeline, fps, start)
    if not said:
        return None
    name = str(timeline.GetName() or "Timeline")
    end = int(timeline.GetEndFrame() or start)
    return "\n".join([f"Transcript: {name} ({_when((end - start) / fps)} long)",
                      "Times are minutes:seconds from the start of the timeline.", ""] + said) + "\n"


def _media_pool_lines(project, per_bin=30):
    """The Media Pool as bins with their clips (name, kind, length) - a long bin shows its first clips and how many
    more there are, so the paste stays readable."""
    try:
        root = project.GetMediaPool().GetRootFolder()
    except Exception:
        return []
    lines = []

    def walk(folder, path):
        try:
            clips = list(folder.GetClipList() or [])
        except Exception:
            clips = []
        if clips:
            kinds = {}
            for c in clips:
                try:
                    k = str(c.GetClipProperty("Type") or "Clip")
                except Exception:
                    k = "Clip"
                kinds[k] = kinds.get(k, 0) + 1
            summary = ", ".join(f"{n} {k.lower()}" for k, n in sorted(kinds.items(), key=lambda kv: -kv[1]))
            lines.append(f"- {path} ({len(clips)}: {summary})")
            for c in clips[:per_bin]:
                try:
                    length = str(c.GetClipProperty("Duration") or "")
                except Exception:
                    length = ""
                lines.append(f"    {c.GetName()}" + (f"  [{length}]" if length and length != "00:00:00:00" else ""))
            if len(clips) > per_bin:
                lines.append(f"    ... and {len(clips) - per_bin} more")
        try:
            subs = list(folder.GetSubFolderList() or [])
        except Exception:
            subs = []
        for sub in subs:
            walk(sub, f"{path} / {sub.GetName()}")

    walk(root, str(root.GetName() or "Master"))
    return lines


def project_text(project):
    """Everything about the project as plain text with times, to paste into a chat assistant so it knows the whole
    project at any moment (2026-10-28: "I basically want you to know everything about my project, at specific
    times"): its settings, the Media Pool, and every timeline - the open one first - with its clips, markers and
    what's said."""
    count = int(project.GetTimelineCount() or 0)
    current = project.GetCurrentTimeline()
    timelines = [t for t in (project.GetTimelineByIndex(i) for i in range(1, count + 1))
                 if t is not None and not str(t.GetName() or "").startswith("clipse_scratch")]   # (Clipse's own helper)
    count = len(timelines)
    cur_id = current.GetUniqueId() if current is not None else None
    timelines.sort(key=lambda t: t.GetUniqueId() != cur_id)          # the open one first
    def setting(k):
        try:
            return str(project.GetSetting(k) or "")
        except Exception:
            return ""
    size = "x".join(x for x in (setting("timelineResolutionWidth"), setting("timelineResolutionHeight")) if x)
    fps = setting("timelineFrameRate")
    parts = [f"Project: {project.GetName()}",
             "  " + ", ".join(x for x in (f"{fps} fps" if fps else "", size,
                                         f"{count} timeline{'s' if count != 1 else ''}") if x),
             f"  Open timeline: {current.GetName()}" if current is not None else "  No timeline open",
             "Times are minutes:seconds from the start of each timeline, then the timecode."]
    pool = _media_pool_lines(project)
    if pool:
        parts += ["", "Media Pool:"] + pool
    for tl in timelines:
        parts += ["", "=" * 60, timeline_text(tl, heading=False).rstrip()
                  + ("\n(this is the open timeline)" if tl.GetUniqueId() == cur_id else "")]
    return "\n".join(parts) + "\n"


def timelines_text(project):
    """Every timeline in the project, one after another."""
    count = int(project.GetTimelineCount() or 0)
    parts = [f"Project: {project.GetName()} ({count} timeline{'s' if count != 1 else ''})",
             "Times are minutes:seconds from the start of each timeline, then the timecode."]
    for i in range(1, count + 1):
        tl = project.GetTimelineByIndex(i)
        if tl is not None:
            parts += ["", "=" * 60, timeline_text(tl, heading=False).rstrip()]
    return "\n".join(parts) + "\n"


def save_project(resolve):
    manager = resolve.GetProjectManager() if resolve is not None else None
    if manager is None or not manager.SaveProject():
        return False, "Resolve didn't save the project"
    return True, "Project saved"


def color_clip(resolve, color):
    """A clip colour (or None: none) for the clip under the playhead - the
    one on the highest video track there, like Resolve's viewer shows."""
    timeline = _timeline(resolve)
    item = timeline.GetCurrentVideoItem() if timeline is not None else None
    if item is None:
        return False, "No clip under the playhead"
    worked = item.SetClipColor(color) if color else item.ClearClipColor()
    if not worked:
        return False, "Resolve didn't change the clip's colour"
    return True, f"{item.GetName()}: {color or 'no colour'}"
