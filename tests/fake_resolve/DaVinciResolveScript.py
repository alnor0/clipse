"""A stand-in for DaVinci Resolve's scripting module, for tests without Resolve.
Set FAKE_CLIPS / FAKE_DELAY to size it; it logs what it was asked to do to $HOME/log.txt.
It mimics known Resolve quirks: stills keep their own length (150 frames) whatever is asked;
a clip's sound goes on the audio track with the same number as the track it's put on (and the
next ones, when its sound is several tracks) - audio tracks are never added for it, and with
one of them taken or missing nothing lands at all, though the answer is still "done"."""
import os
HOME = os.environ["HOME"]
LOG = os.path.join(HOME, "log.txt")
PAGE = os.environ.get("FAKE_PAGE", "edit")
def log(m):
    open(LOG, "a").write(m + "\n")
MEDIA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "media")
A = MEDIA + "/"  # optional test media (previews only)
ADDED = {}  # clip name -> its "Date Added" as Resolve writes it (a test sets some)
SECS = {"Upbeat Corporate.wav": 60, "untitled_01.wav": 45, "rain ambience.wav": 45, "recording_02.wav": 40, "whoosh.wav": 2}
FILES = {**{k: A + k for k in SECS}, "whoosh.wav": A + "whoosh.wav", "av.mp4": A + "av.mp4",
         "SFX_034.wav": A + "beep.wav"}
TAGS = {"SFX_034.wav": ("whoosh, dark", "Teal"), "whoosh.wav": ("", "Pink"), "av.mp4": ("", "Blue")}
# sound that is more than one track: clip name -> the kind of each track
SOUND = {"screen rec.mp4": ["mono", "mono"], "two mics.wav": ["mono", "mono"]}
class MPI:
    def __init__(s, n, mid, t): s.n, s.mid, s.t = n, mid, t
    def sound(s): return SOUND.get(s.n, ["stereo"] if s.t == "Audio" else [])
    def GetAudioMapping(s):
        import json
        return json.dumps({"track_mapping": {str(n + 1): {"type": kind} for n, kind in enumerate(s.sound())}})
    def GetName(s): return s.n
    def SetName(s, n): log(f"RENAME {s.n} -> {n}"); s.n = n; return True
    # (a Media Pool clip's colour: what TAGS gives it until one is set; generators and Fusion clips never keep one)
    def GetClipColor(s): return getattr(s, "colour", TAGS.get(s.n, ("", ""))[1])
    def SetClipColor(s, c):
        log(f"POOLCOLOUR {s.n} {c}")
        if s.t not in ("Generator", "Fusion Title", "Fusion Composition"): s.colour = c
        return True
    def ClearClipColor(s): log(f"POOLCOLOUR {s.n} none"); s.colour = ""; return True
    def GetMediaId(s): return s.mid
    # in / out marks on the clip itself - the one thing that gives a still a length (measured in 21.1.1)
    def GetMarkInOut(s): return {"video": dict(getattr(s, "marks", {}))}
    def SetMarkInOut(s, a, b, kind="all"):
        if os.environ.get("FAKE_OLD_RESOLVE"): raise AttributeError("SetMarkInOut")
        s.marks = {"in": a, "out": b}; return True
    def ClearMarkInOut(s, kind="all"): s.marks = {}; return True
    def GetClipProperty(s, k=None):
        import time as _t; _t.sleep(float(os.environ.get("FAKE_DELAY", "0.002")))
        kw, col = TAGS.get(s.n, ("", ""))
        fr = str(SECS.get(s.n, 6) * 30)
        if s.t == "Still":
            fr = "1"
        d = {"Type": s.t, "FPS": "30", "Frames": fr, "File Path": FILES.get(s.n, ""), "Keyword": kw,
             "Comments": "", "Clip Color": col, "Resolution": "4032x3024" if s.t == "Still" else "1920x1080",
             "Date Added": ADDED.get(s.n, "Mon Oct 19 2026 10:00:00")}
        return d if k is None else d.get(k)
class Folder:
    def __init__(s, name, clips, subs=()): s.name, s.c, s.subs = name, clips, list(subs)
    def GetName(s): return s.name
    def GetClipList(s): return s.c
    def GetSubFolderList(s): return s.subs
class TextTool:
    def SetInput(s, k, v): log(f"SETINPUT {k}={v}")
class TitleComp:
    def GetToolList(s, sel, kind=None): return {1: TextTool()}
class TitleItem:
    def GetFusionCompByIndex(s, i): return TitleComp()
class Item:
    def __init__(s, n, a, b, mpi=None): s.n, s.a, s.b, s.mpi, s.linked = n, a, b, mpi, []
    def GetLinkedItems(s): return list(s.linked)
    def GetUniqueId(s): return f"item-{id(s)}"
    def GetMediaPoolItem(s): return s.mpi
    def GetSourceStartTime(s): return getattr(s, "src", (0.0, (s.b - s.a) / 30))[0]  # which part of the clip, in seconds
    def GetSourceEndTime(s): return getattr(s, "src", (0.0, (s.b - s.a) / 30))[1]
    def GetTrackTypeAndIndex(s):
        for k, lst in TRACKS.items():
            if s in lst: return list(k)
        return None
    def GetName(s): return s.n
    def GetStart(s): return s.a
    def GetEnd(s): return s.b
    def SetProperty(s, k, v): log(f"PROP {s.n} {k}={v}"); return True
    def SetClipColor(s, c): log(f"COLOUR {s.n} {c}"); s.colour = c; return True
    def ClearClipColor(s): log(f"COLOUR {s.n} none"); s.colour = ""; return True
    def GetClipColor(s): return getattr(s, "colour", "")
    def GetFusionCompCount(s): return getattr(s, "comps", 0)
TRACKS = {}
NAMES = {}
OFF = set()  # tracks switched off
SETTINGS = {"timelineResolutionWidth": "1920", "timelineResolutionHeight": "1080", "timelineFrameRate": "25",
            "colorScienceMode": "davinciYRGB", "perfCacheClipsLocation": "/tmp/cache"}
USED = []
UNDER_PLAYHEAD = [None]
ADDED_MARKERS = {}
RENDER = {"jobs": [], "running": False, "preset": None, "dir": "/tmp", "name": "out", "storage": [HOME]}
MARKS = {"video": {}, "audio": {}}  # the timeline's in / out marks - what a render job covers
class TL:
    def __init__(s, name="Timeline 1", uid="TL", end=108000): s.name, s.uid, s.end = name, uid, end
    def GetStartFrame(s): return 108000 - 108000
    def GetEndFrame(s): return s.end
    def GetTrackCount(s, t): return max([i for (k, i) in TRACKS if k == t] or [0])
    def GetItemListInTrack(s, t, i): return TRACKS.get((t, i), [])
    def GetSetting(s, k): return {"timelineResolutionWidth": "1920", "timelineResolutionHeight": "1080"}.get(k, "30")
    def GetCurrentTimecode(s): return "00:00:01:00"
    def SetCurrentTimecode(s, tc): return True
    def AddTrack(s, t, sub=None):
        top = s.GetTrackCount(t) + 1
        at = sub.get("index", top) if isinstance(sub, dict) else top
        at = at if 1 <= at <= top else top
        for k in range(top, at, -1):  # the tracks from there on move up one
            TRACKS[(t, k)] = TRACKS.get((t, k - 1), [])
            OFF.discard((t, k)); OFF.add((t, k)) if (t, k - 1) in OFF else None
            if (t, k - 1) in NAMES: NAMES[(t, k)] = NAMES.pop((t, k - 1))
        TRACKS[(t, at)] = []
        OFF.add((t, at)) if t == "subtitle" else OFF.discard((t, at))  # a new subtitle track comes switched off
        return True
    def SetTrackEnable(s, t, i, on): OFF.discard((t, i)) if on else OFF.add((t, i)); return True
    def GetIsTrackEnabled(s, t, i): return (t, i) not in OFF
    def SetClipsLinked(s, items, on):  # as in Resolve: an item taken into a new link leaves its old one
        for it in items:
            for other in it.linked: other.linked = [x for x in other.linked if x is not it]
            it.linked = [x for x in items if x is not it] if on else []
        log(f"LINK {len(items)}"); return True
    def GetTrackName(s, t, i): return NAMES.get((t, i), f"{t[0].upper()}{i}")
    def SetTrackName(s, t, i, n): NAMES[(t, i)] = n; log(f"TRACKNAME {t}{i}={n}"); return True
    def GetName(s): return s.name
    def GetUniqueId(s): return s.uid
    def GetCurrentVideoItem(s): return UNDER_PLAYHEAD[0]
    def CreateSubtitlesFromAudio(s, settings=None):  # comes straight back; Resolve works on
        log("SUBTITLES " + " ".join(f"{k}={v}" for k, v in sorted((settings or {}).items()))); return True
    def GetMarkInOut(s): return {k: dict(v) for k, v in MARKS.items()}
    def SetMarkInOut(s, a, b, kind="all"):
        for k in (("video", "audio") if kind == "all" else (kind,)): MARKS[k] = {"in": a, "out": b}
        return True
    def ClearMarkInOut(s, kind="all"):
        for k in (("video", "audio") if kind == "all" else (kind,)): MARKS[k] = {}
        return True
    def AddMarker(s, frame, color, name, note, duration, data=""):
        if frame in ADDED_MARKERS: return False
        ADDED_MARKERS[frame] = color; log(f"MARKER {frame} {color}"); return True
    def DuplicateTimeline(s, name=None):
        t = TL(name or s.name + " copy", s.uid + "c", s.end); TIMELINES.append(t); log(f"DUPLICATE {s.name}"); return t
    def GetMarkers(s): return {30: {"color": "Blue"}, 90.0: {"color": "Red"}, 150: {}}
    def CreateCompoundClip(s, items, info=None):
        where = None
        for k, lst in sorted(TRACKS.items()):
            for it in list(lst):
                if it in items:
                    lst.remove(it)
                    where = where or k
        a = min(i.a for i in items); b = max(i.b for i in items)
        mpi = MPI((info or {}).get("name", "Compound"), "cmp", "Compound")
        new = Item(mpi.GetName(), a, b, mpi)
        new.track = where
        TRACKS[where].append(new)
        log(f"COMPOUND {[i.n for i in items]} -> {mpi.GetName()} {a}-{b}")
        return new
    def DeleteClips(s, items, ripple=False):
        for k, lst in TRACKS.items():
            TRACKS[k] = [i for i in lst if i not in items]
        log(f"DELETE {[i.GetName() for i in items]}")
        return True
    def DeleteTrack(s, t, i):  # the tracks above move down one, as in Resolve
        top = s.GetTrackCount(t)
        for k in range(i, top):
            TRACKS[(t, k)] = TRACKS.get((t, k + 1), [])
            OFF.discard((t, k)); OFF.add((t, k)) if (t, k + 1) in OFF else None  # on / off goes with the track
            if (t, k + 1) in NAMES: NAMES[(t, k)] = NAMES.pop((t, k + 1))
            else: NAMES.pop((t, k), None)
        TRACKS.pop((t, top), None); NAMES.pop((t, top), None); OFF.discard((t, top)); log(f"DELTRACK {t}{i}"); return True
    def GrabStill(s):
        if PAGE_NOW[0] != "color" and os.environ.get("GRAB_NEEDS_COLOR"):
            return None
        log("GRAB"); return Still()
    def InsertFusionTitleIntoTimeline(s, n):
        log(f"TITLE {n}")
        return TitleItem()
MUSIC = Folder("Music", [MPI("Upbeat Corporate.wav", "m1", "Audio")] + [MPI(f"B-roll {i:03d}.mp4", f"b{i}", "Video") for i in range(int(os.environ.get("FAKE_CLIPS", "800")))])
ROOT = Folder("Master", [MPI("photo_1.jpg", "p1", "Still"), MPI("photo_2.jpg", "p2", "Still"), MPI("photo_3.jpg", "p3", "Still"),
                         MPI("whoosh.wav", "w1", "Audio"), MPI("av.mp4", "a1", "Video"), MPI("SFX_034.wav", "s1", "Audio"),
                         MPI("screen rec.mp4", "sr1", "Video + Audio"), MPI("two mics.wav", "tm1", "Audio"),
                         MPI("untitled_01.wav", "u1", "Audio"), MPI("rain ambience.wav", "r1", "Audio"),
                         MPI("recording_02.wav", "c1", "Audio")], [MUSIC])
PAGE_NOW = [PAGE]
class Still: pass
class Album:
    def ExportStills(s, stills, folder, prefix, fmt):
        import struct, zlib
        open(os.path.join(folder, prefix + "_1.1.1." + fmt), "wb").write(b"png")
        open(os.path.join(folder, prefix + "_1.1.1.drx"), "w").write("drx")
        log(f"EXPORT {prefix} {fmt}"); return True
    def DeleteStills(s, stills): log("DELSTILL"); return True
class Gallery:
    def GetCurrentStillAlbum(s): return Album()
def _all_bins(folder=None):
    folder = folder or ROOT
    return [folder] + [b for sub in folder.subs for b in _all_bins(sub)]
COPY_ON_MOVE = [0]  # batches MoveClips copies instead of moving
class Pool:
    def GetCurrentFolder(s): return ROOT
    def CreateEmptyTimeline(s, name):
        t = TL(name, "N" + str(len(TIMELINES))); TIMELINES.append(t); log(f"NEWTIMELINE {name}"); return t
    def AddSubFolder(s, parent, name):
        f = Folder(name, []); parent.subs.append(f); log(f"ADDBIN {name}"); return f
    def ImportMedia(s, paths):
        items = [MPI(os.path.basename(p), "g" + str(len(paths)), "Subtitle" if p.endswith(".srt") else "Still") for p in paths]
        for item, p in zip(items, paths): item.path = p
        log(f"IMPORT {[os.path.basename(p) for p in paths]}"); return items
    def GetRootFolder(s): return ROOT
    def ImportFolderFromFile(s, path, source=""):  # a .drb: the bin saved in it, with its clips
        if not os.path.exists(path) or os.environ.get("FAKE_OLD_RESOLVE"): return False
        if "composition" in os.path.basename(path):  # (each bin file holds the bin it was saved from)
            ROOT.subs.append(Folder("davinci-search composition", [MPI("Fusion Composition", "fc0", "Fusion Composition")]))
        elif "library" in os.path.basename(path):  # library.py's: one title or generator, made from its name
            import re, uuid, zipfile
            with zipfile.ZipFile(path) as z:
                xml = next(z.read(n).decode() for n in z.namelist() if "000_" in n)
            raw = bytes.fromhex(re.search(r"<Sm2MpGenerator.*?<FieldsBlob>([0-9a-f]+)<", xml, re.S).group(1))[9:]
            name = raw[4:4 + raw[3]].decode()
            kind = re.search(r"<Name>(Fusion Title|Fusion Generator)</Name>", xml)
            ROOT.subs.append(Folder("clipse_import", [MPI(name, "lib" + uuid.uuid4().hex[:8], kind.group(1) if kind else "Generator")]))
        else:
            ROOT.subs.append(Folder("davinci-search", [MPI("Adjustment Clip", "adj1", "Generator")]))
        log(f"IMPORTBIN {os.path.basename(path)}"); return True
    def GetSelectedClips(s): return []
    def MoveClips(s, clips, folder):
        if COPY_ON_MOVE[0] and len(clips) > 1:  # (as Resolve once did for Organise, 2026-10-30: copies in the bin,
            COPY_ON_MOVE[0] -= 1                 # the clips left where they were - each copy a new clip)
            for c in clips:
                copy = MPI(c.n, c.mid + "-copy", c.t)
                folder.c.append(copy)
            log(f"COPY {[c.GetName() for c in clips]} -> {folder.GetName()}"); return True
        for f in _all_bins():
            f.c[:] = [c for c in f.c if c not in clips]
        folder.c.extend(clips); log(f"MOVE {[c.GetName() for c in clips]} -> {folder.GetName()}"); return True
    def DeleteClips(s, clips):
        for f in _all_bins():
            f.c[:] = [c for c in f.c if c not in clips]
        log(f"POOLDELETE {[c.GetName() for c in clips]}"); return True
    def MoveFolders(s, folders, target):
        for f in _all_bins():
            f.subs[:] = [b for b in f.subs if b not in folders]
        target.subs.extend(folders); log(f"MOVEBIN {[f.GetName() for f in folders]} -> {target.GetName()}"); return True
    def DeleteFolders(s, folders):
        for f in _all_bins():
            f.subs[:] = [b for b in f.subs if b not in folders]
        log(f"DELBIN {[f.GetName() for f in folders]}"); return True
    def SetCurrentFolder(s, f): return True
    def SetSelectedClip(s, c): return True
    def AppendToTimeline(s, infos):
        for i in infos:
            if not isinstance(i, dict):  # a clip on its own: at the start, the whole of it
                i = {"mediaPoolItem": i, "trackIndex": 1, "recordFrame": CURRENT[0].GetStartFrame(), "startFrame": 0, "endFrame": 100}
            kind = "audio" if i.get("mediaType") == 2 else "video"
            mpi = i["mediaPoolItem"]
            if mpi.t == "Subtitle":
                # An .srt, as Resolve 21 does it - whatever track and frame are asked for: onto the lowest
                # subtitle track that's switched on (none: nowhere), starting after what's on subtitle track 1.
                import re
                on = sorted(k[1] for k in TRACKS if k[0] == "subtitle" and k not in OFF)
                if not on:
                    continue
                first = max([it.b for it in TRACKS.get(("subtitle", 1), [])] or [CURRENT[0].GetStartFrame()])
                def frame(stamp):
                    h, m, sec = stamp.replace(",", ".").split(":")
                    return first + round((int(h) * 3600 + int(m) * 60 + float(sec)) * 30)
                for block in open(mpi.path, encoding="utf-8").read().strip().split("\n\n"):
                    rows = block.split("\n")
                    a, b = re.findall(r"\d+:\d+:\d+,\d+", rows[1])
                    TRACKS[("subtitle", on[0])].append(Item("\n".join(rows[2:]), frame(a), frame(b), mpi))
                log(f"APPENDSUBTITLES {on[0]}"); continue
            if mpi.t == "Still":  # Resolve: its own still length whatever is asked - unless the clip is marked
                marks = getattr(mpi, "marks", {})
                length = marks["out"] - marks["in"] + 1 if marks else 150
                i = dict(i, startFrame=i.get("startFrame", 0), endFrame=i.get("endFrame", 0))
            else:
                length = i["endFrame"] - i["startFrame"]
            a, b, at = i["recordFrame"], i["recordFrame"] + length, i["trackIndex"]
            def there(n): return ("audio", n) in TRACKS
            def taken(n): return any(a < it.b and it.a < b for it in TRACKS.get(("audio", n), []))
            sound = [] if i.get("mediaType") == 1 else mpi.sound()
            log(f"APPEND {i['mediaPoolItem'].GetName()} start={i['startFrame']} end={i['endFrame']}")
            if kind == "audio":
                if taken(at):
                    continue  # says "done", lands nowhere
                for n in range(max(1, len(sound))):  # ...and the tracks that aren't there are left out
                    if n == 0 or (there(at + n) and not taken(at + n)):
                        TRACKS.setdefault(("audio", at + n), []).append(Item(mpi.GetName(), a, b, mpi))
                continue
            if any(not there(at + n) or taken(at + n) for n in range(len(sound))):
                continue  # no free audio track for its sound: nothing lands
            if any(a < it.b and it.a < b for it in TRACKS.get(("video", at), [])):
                continue  # the spot is taken: nothing lands (as Resolve)
            picture = Item(mpi.GetName(), a, b, mpi)
            TRACKS.setdefault(("video", at), []).append(picture)
            for n in range(len(sound)):
                own = Item(mpi.GetName(), a, b, mpi)
                TRACKS[("audio", at + n)].append(own)
                picture.linked.append(own); own.linked.append(picture)  # Resolve links them itself
        return [object()]
TIMELINES = [TL("Timeline 1", "TL", 1717), TL("Shorts cut", "T2", 1800), TL("Main edit v3", "T3", 30 * 754)]
CURRENT = [TIMELINES[0]]
class Project:
    def GetCurrentTimeline(s): return CURRENT[0]
    def GetTimelineCount(s): return len(TIMELINES)
    def GetTimelineByIndex(s, i): return TIMELINES[i - 1]
    def SetCurrentTimeline(s, t): CURRENT[0] = t; return True
    def GetRenderPresetList(s): return ["H.265 Master", "YouTube - 1080p", "YouTube - 2160p"]
    def LoadRenderPreset(s, name): RENDER["preset"] = name; return name in s.GetRenderPresetList()
    def SetRenderSettings(s, d):
        RENDER["dir"] = d.get("TargetDir", RENDER["dir"]); RENDER["name"] = d.get("CustomName", RENDER["name"]); return True
    def AddRenderJob(s):
        if not RENDER["dir"]: return ""
        if RENDER["storage"] is not None and not any(RENDER["dir"].startswith(v) for v in RENDER["storage"]):
            log("MESSAGE Render Path Inaccessible"); return ""  # Resolve on Linux: only inside the media storage
        job = {"JobId": f"job{RENDER.setdefault('made', 0)}", "TargetDir": RENDER["dir"], "OutputFilename": RENDER["name"] + ".mp4",
               "MarkIn": MARKS["video"].get("in", 0), "MarkOut": MARKS["video"].get("out", CURRENT[0].end - 1)}
        RENDER["made"] += 1; RENDER["jobs"].append(job); return job["JobId"]
    def DeleteRenderJob(s, job): RENDER["jobs"][:] = [j for j in RENDER["jobs"] if j["JobId"] != job]; return True
    def GetRenderJobList(s): return list(RENDER["jobs"])
    def StartRendering(s, *jobs): RENDER["running"] = True; log(f"RENDER {RENDER['preset']} {jobs}"); return True
    def StopRendering(s): RENDER["running"] = False
    def IsRenderingInProgress(s): return RENDER["running"]
    def GetMediaPool(s): return Pool()
    def GetName(s): return "P"
    def GetGallery(s): return Gallery()
    def GetSetting(s, k=None): return dict(SETTINGS) if not k else SETTINGS.get(k)
    def SetSetting(s, k, v):
        if k == "timelineFrameRate": return False
        SETTINGS[k] = v; log(f"SET {k}={v}"); return True
class PM:
    def GetCurrentProject(s): return Project()
    def SaveProject(s): log("SAVE"); return True
class Comp:
    data = {}
    def SetData(s, k, v): Comp.data[k] = v
    def GetData(s, k): return Comp.data.get(k)
    def Execute(s, lua):
        log("EXECUTE " + lua.splitlines()[1][:120])
        if "GetRegList" in lua:
            Comp.data["ClipseTools"] = "\n".join(f"{i}\t{i} Tool\tTools\\Cat{i % 3}" for i in range(12))
        else:
            Comp.data["ClipseResult"] = "connected after MediaIn1"
            log("LUA " + " | ".join(l for l in lua.splitlines()[1:3]))
    def GetToolList(s, sel=False): return {}
class Fusion:
    def GetCurrentComp(s): return Comp()
    def RunScript(s, path): log(f"RUNSCRIPT {path}"); return None
class Storage:
    def GetMountedVolumeList(s): return list(RENDER["storage"] or [])
class Resolve:
    # the names Resolve gives the subtitle choices (README: Auto Caption Settings)
    SUBTITLE_LANGUAGE, SUBTITLE_CAPTION_PRESET, SUBTITLE_CHARS_PER_LINE = "language", "preset", "chars"
    SUBTITLE_LINE_BREAK, SUBTITLE_GAP = "lines", "gap"
    AUTO_CAPTION_AUTO, AUTO_CAPTION_DANISH, AUTO_CAPTION_ENGLISH = "auto", "da", "en"
    AUTO_CAPTION_SUBTITLE_DEFAULT, AUTO_CAPTION_TELETEXT, AUTO_CAPTION_NETFLIX = "normal", "teletext", "netflix"
    AUTO_CAPTION_LINE_SINGLE, AUTO_CAPTION_LINE_DOUBLE = "one", "two"
    def GetProjectManager(s): return PM()
    def GetMediaStorage(s): return Storage()
    def GetCurrentPage(s): return PAGE_NOW[0]
    def OpenPage(s, p): PAGE_NOW[0] = p; log(f"PAGE {p}"); return True
    def Fusion(s): return Fusion()
    def GetProductName(s): return "DaVinci Resolve Studio"
    def GetVersionString(s): return "20.2.0"
    def GetLayoutPresetList(s): return list(LAYOUTS)
    def LoadLayoutPreset(s, name): log(f"LAYOUT {name}"); return name in LAYOUTS
    def SaveLayoutPreset(s, name):
        if name in LAYOUTS: return False
        LAYOUTS.append(name); log(f"SAVELAYOUT {name}"); return True
    def UpdateLayoutPreset(s, name): log(f"UPDATELAYOUT {name}"); return name in LAYOUTS
LAYOUTS = ["Editing", "Colour big viewer"]
def scriptapp(name):
    return Resolve()
