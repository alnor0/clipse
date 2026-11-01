"""Grab Frame: the frame under the playhead as a still in your project.

Resolve's own scripting does all of it - no screenshots of the screen and
no fake keypresses:
  1. Timeline.GrabStill() makes a gallery still of the current frame
     (Resolve only allows that on the Color page in some versions - then we
     switch there for a moment and come back);
  2. the still is exported as a PNG and removed from the gallery again -
     into a folder of the project's own name in Pictures/Clipse, or in the
     folder on Settings > Scripts (2026-10-19:
     it went into the app's hidden folder unless asked, where nobody backed
     it up and a project moved to another computer lost its grabs);
  3. the PNG is imported into the "frame_grabs" bin (in the "clipse" bin) and, if
     "Put it on the timeline" is on, placed at the playhead on the first free track.
"""
import os
import re
import time

CLIPSE_BIN = "clipse"  # one bin at the top of the Media Pool for everything the app makes or brings
GRABS_BIN = "frame_grabs"
VOICE_BIN = "voiceovers"  # every voiceover take (voiceover.py)
# every compound or Fusion clip the app makes (Insert as > Afterwards, End together) - Resolve puts a new one in
# whatever bin is open in the Media Pool, so they ended up among your footage (2026-10-19)
COMPOUND_BIN = "compound_clips"
GROUPED_BIN = COMPOUND_BIN  # (the End together ones had a bin of their own, grouped_stills)
# what these bins were called before - one that's there is moved over, so nothing ends up split over two
OLD_BIN_NAMES = {CLIPSE_BIN: "Clipse", GRABS_BIN: "Frame grabs", COMPOUND_BIN: "grouped_stills"}


def _named(folder, name):
    return next((f for f in folder.GetSubFolderList() or [] if f.GetName() == name), None)


def _move_over(media_pool, old, target):
    """Everything in the bin `old` into `target`, and `old` removed once empty (a script can't rename a bin)."""
    try:
        clips = list(old.GetClipList() or [])
        if clips and not media_pool.MoveClips(clips, target):
            return  # (they stay where they are; new ones go in the new bin)
        subs = list(old.GetSubFolderList() or [])
        if subs:
            media_pool.MoveFolders(subs, target)
        if not (old.GetClipList() or []) and not (old.GetSubFolderList() or []):
            media_pool.DeleteFolders([old])
        print(f"[bins] \"{old.GetName()}\" moved into \"{target.GetName()}\" ({len(clips)} clips)")
    except Exception as e:
        print(f"[bins] couldn't move \"{old.GetName()}\" into \"{target.GetName()}\": {e}")


def app_bin(media_pool, name=CLIPSE_BIN):
    """The bin Clipse keeps things in: "clipse" at the top of the Media Pool, and GRABS_BIN, COMPOUND_BIN
    inside it (2026-10-20: "shouldn't they go in the clipse folder") - made if they aren't there, named
    like_this. What earlier versions made is moved in: a "Clipse" bin's clips, frame_grabs and compound_clips
    at the top as they are, one with an older name ("Frame grabs") clip by clip. If any of that doesn't work the old bin
    is simply used on. None if no bin could be made. (Making a bin takes you into it: the caller puts the
    current bin back.)"""
    root = media_pool.GetRootFolder()
    home = _named(root, CLIPSE_BIN)
    old_home = _named(root, OLD_BIN_NAMES[CLIPSE_BIN])
    if home is None:
        home = media_pool.AddSubFolder(root, CLIPSE_BIN)
        if home is None:
            return old_home
    if old_home is not None:
        _move_over(media_pool, old_home, home)
    at_top = [f for f in (_named(root, n) for n in (GRABS_BIN, COMPOUND_BIN)) if f is not None]
    if at_top:  # (where they were made until 2026-10-20 - all moved in at once)
        try:
            media_pool.MoveFolders(at_top, home)
        except Exception as e:
            print(f"[bins] couldn't move {[f.GetName() for f in at_top]} into \"{CLIPSE_BIN}\": {e}")
    if name == CLIPSE_BIN:
        return home
    target = _named(home, name) or _named(root, name)
    if target is not None:
        return target
    target = media_pool.AddSubFolder(home, name)
    old = _named(root, OLD_BIN_NAMES.get(name))
    if old is None or target is None:
        return target or old
    _move_over(media_pool, old, target)
    return target


def default_grabs_folder():
    return os.path.join(os.path.expanduser("~"), "Pictures", "Clipse")


def project_folder_name(name):
    """A project's name as a folder's: what no system allows in one swapped for _ (2026-10-19: a folder for each
    project - grabs don't mix, and a project moved knows its folder)."""
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", str(name or "")).strip(" .")
    return name or "Untitled project"


def grabs_folder(settings):
    """Where the PNG goes - and stays: a Media Pool clip is only a link to its file. (Grabs made before 2026-10-19
    are in ~/.clipse/frame-grabs, left there: projects link to them.)"""
    chosen = (settings.files.get("grabs_folder") or "").strip()
    return os.path.expanduser(chosen) if chosen else default_grabs_folder()


def like_this(text):
    """A name as a file's, like_this - lower case, words joined by _ (2026-10-20: "this goes for every file and
    bin name")."""
    return re.sub(r"\W+", "_", str(text or "").lower()).strip("_")


def _clock(seconds):
    """3.4 -> 0m03s, 3725 -> 1h02m05s."""
    m, s = divmod(int(max(0.0, seconds)), 60)
    h, m = divmod(m, 60)
    return f"{h}h{m:02d}m{s:02d}s" if h else f"{m}m{s:02d}s"


def _is_grab(item, grabs):
    """A clip on the timeline that's one of the grabs (its file in the grabs folder)."""
    try:
        path = item.GetMediaPoolItem().GetClipProperty("File Path") or ""
    except Exception:
        return False
    return bool(grabs and path) and os.path.abspath(path).startswith(os.path.abspath(grabs) + os.sep)


def _lies_over(item):
    """An adjustment clip or a Fusion composition: laid over the footage, not where the picture comes from."""
    try:
        return item.GetMediaPoolItem().GetClipProperty("Type") in ("Generator", "Fusion Composition")
    except Exception:
        return False


def _under_grabs(timeline, item, playhead, grabs):
    """The clip under the playhead below the grabs on top of it (a grab lands on the timeline over its clip, and the
    next grab there would be named after it - "drone_0m03s_0m01s", seen 2026-10-21) - else None."""
    try:
        track = item.GetTrackTypeAndIndex()[1]
    except Exception:
        return None
    for below in range(track - 1, 0, -1):
        for other in timeline.GetItemListInTrack("video", below) or []:
            if other.GetStart() <= playhead < other.GetEnd() and not _is_grab(other, grabs) and not _lies_over(other):
                return other
    return None


def grab_name(timeline, grabs=None):
    """What a grab is called: the clip the frame is from and where in that clip - drone_mountains_0m03s (2026-10-20:
    "<timeline> 00-00-01-10" - "there doesn't look like there is anything logical about it"). Nothing under the
    playhead to name it by (a title, a gap): the timeline's name and where on it. An earlier grab on top (its file in
    `grabs`, the grabs folder) is looked through."""
    from .resolve_client import tc_to_frame
    try:
        fps = float(timeline.GetSetting("timelineFrameRate")) or 24.0
        playhead = tc_to_frame(str(timeline.GetCurrentTimecode()), fps)
    except (TypeError, ValueError):
        return like_this(timeline.GetName()) or "frame"
    try:
        item = timeline.GetCurrentVideoItem()
    except Exception:
        item = None
    if item is not None and _is_grab(item, grabs):
        item = _under_grabs(timeline, item, playhead, grabs)
    elif item is not None and _lies_over(item):  # (an adjustment clip over the footage: the footage's name - it was
        item = _under_grabs(timeline, item, playhead, grabs) or item  # "adjustment_clip_1h00m01s", Windows 2026-10-22)
    name = os.path.splitext(item.GetName() or "")[0] if item is not None else ""
    if name:
        try:  # Resolve 19+: where the clip starts in its recording, in seconds
            into = float(item.GetSourceStartTime() or 0)
        except Exception:
            into = float(item.GetLeftOffset() or 0) / fps
        seconds = into + (playhead - item.GetStart()) / fps
    else:
        name = timeline.GetName()
        seconds = (playhead - timeline.GetStartFrame()) / fps
    return f"{like_this(name) or 'frame'}_{_clock(seconds)}"


def _grab(resolve, timeline):
    """A GalleryStill of the current frame, plus the page to go back to."""
    page = None
    try:
        page = resolve.GetCurrentPage()
    except Exception:
        pass
    try:
        still = timeline.GrabStill()
    except Exception:
        still = None
    if still or page == "color":
        return still, None
    # not allowed on this page: grab it on the Color page, then come back
    resolve.OpenPage("color")
    for _ in range(10):
        time.sleep(0.15)
        try:
            still = timeline.GrabStill()
        except Exception:
            still = None
        if still:
            break
    return still, page


def _back_on(resolve, page, seconds=3.0):
    """Waits until Resolve is on `page` again, and a moment more - True once it is. GrabStill on the Edit page goes
    to the Color page by itself; anything asked of Resolve before it's back can bring it down (2026-10-20, 21.1.1:
    the still put on the timeline right after the second grab in a row, Resolve still on its way back -
    std::out_of_range, Resolve gone)."""
    if not page:
        return True
    until = time.monotonic() + seconds
    while True:
        try:
            if resolve.GetCurrentPage() == page:
                break
        except Exception:
            return False
        if time.monotonic() >= until:
            return False
        time.sleep(0.05)
    time.sleep(0.3)
    return True


def _settle(resolve, page, opened):
    """Resolve back on `page` after a grab. 21.1.1 comes back from the Color page by itself (~0.35 s); 21.0.4 stays
    there (2026-10-21, a Mac: the still was put on the timeline from the Color page and Resolve went down with
    std::out_of_range) - so when it doesn't come back by itself it's taken back. `opened`: Clipse went to the Color
    page itself, and takes it back at once. True once it's there."""
    if not page:
        return True
    if not opened and _back_on(resolve, page, seconds=1.5):
        return True
    try:
        resolve.OpenPage(page)
    except Exception:
        return False
    return _back_on(resolve, page)


def save_frame(resolve, settings, return_to_page=True):
    """Saves the frame under the playhead as a PNG. Returns (path, message, back): path is None if it didn't work;
    back is False when Resolve couldn't be brought back from the Color page - nothing more may be asked of it then
    (no import, no insert). return_to_page=False: Resolve may be left on the Edit page - come_back."""
    project = resolve.GetProjectManager().GetCurrentProject()
    timeline = project.GetCurrentTimeline() if project else None
    if timeline is None:
        return None, "No timeline open.", True
    folder = os.path.join(grabs_folder(settings), project_folder_name(project.GetName()))
    try:
        os.makedirs(folder, exist_ok=True)
    except OSError as e:
        return None, f"Couldn't create {folder}: {e}", True
    try:
        started_on = resolve.GetCurrentPage()
    except Exception:
        started_on = None
    still, back_to = _grab(resolve, timeline)
    path, message = None, ""
    try:
        path, message = _export(project, timeline, still, folder, settings)
    finally:
        settle = back_to or started_on
        if settle == "fusion" and not return_to_page:
            settle = "edit"  # (the grab is placed from the Edit page - where Resolve comes back to by itself)
        back = _settle(resolve, settle, opened=bool(back_to))  # (nothing else is asked of Resolve until it's back)
        if back and return_to_page:
            come_back(resolve, started_on)
    if not back:
        print(f"[grab] Resolve didn't come back to the {settle} page")
    return path, message, back


def _export(project, timeline, still, folder, settings):
    """The grabbed still as a PNG in `folder`, named after what it shows; the still out of the gallery again."""
    if not still:
        return None, "Resolve didn't grab the frame (is there a clip under the playhead?)."
    album = project.GetGallery().GetCurrentStillAlbum()
    if album is None:
        return None, "Couldn't reach the gallery to export the frame."
    name = grab_name(timeline, grabs_folder(settings))
    before = set(os.listdir(folder))
    ok = album.ExportStills([still], folder, name, "png")
    new = sorted(set(os.listdir(folder)) - before)
    try:
        album.DeleteStills([still])  # it was only needed for the export
    except Exception:
        pass
    pngs = [f for f in new if f.lower().endswith(".png")]
    for extra in new:  # the grade file Resolve writes next to it
        if extra.lower().endswith(".drx"):
            try:
                os.remove(os.path.join(folder, extra))
            except OSError:
                pass
    if not ok or not pngs:
        return None, "Resolve couldn't export the frame."
    path = os.path.join(folder, pngs[0])
    tidy = os.path.join(folder, f"{name}.png")  # Resolve adds its own label to the name
    n = 2
    while os.path.exists(tidy) and os.path.abspath(tidy) != os.path.abspath(path):
        tidy = os.path.join(folder, f"{name}_{n}.png")
        n += 1
    try:
        os.replace(path, tidy)
        path = tidy
    except OSError:
        pass
    return path, f"Saved the frame as {os.path.basename(path)}"


def come_back(resolve, page):
    """Back to `page` after a grab that left Resolve on another one: from the Fusion page Resolve grabs on the Color
    page by itself and comes back to the Edit page (2026-10-21). After the grab is on the timeline - on the Fusion
    page a script can't read the playhead (GetCurrentTimecode is None there, 21.1.1)."""
    try:
        if page and resolve.GetCurrentPage() != page:
            resolve.OpenPage(page)
            _back_on(resolve, page, seconds=6.0)  # (the Fusion page takes a while to open)
    except Exception:
        pass


def import_grab(media_pool, path, bin_name=GRABS_BIN):
    """Imports the PNG into the "frame_grabs" bin (or `bin_name` - a voiceover's take into "voiceovers"), made if
    needed, without changing which bin you're looking at. Returns (MediaPoolItem, bin)."""
    root = media_pool.GetRootFolder()
    current = media_pool.GetCurrentFolder()
    target = app_bin(media_pool, bin_name) or root
    media_pool.SetCurrentFolder(target)
    try:
        items = media_pool.ImportMedia([path]) or []
    finally:
        if current is not None:
            media_pool.SetCurrentFolder(current)
    return (items[0] if items else None), target
