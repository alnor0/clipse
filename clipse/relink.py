"""Relink missing clips (Actions > Project, 2026-11-01: "cant i just have a relink command to do this for me?"): every
clip in the open project whose file isn't where Resolve thinks, pointed at the file again.

Resolve remembers the path a clip came in by. Dragged in through a shortcut (a folder of links, one per tag, say), it
goes offline when that shortcut goes - and the real file is still there, near where the shortcut was. So: from the
path Resolve has, up to the nearest folders that exist, the first with a file of that name. A shortcut found on the way
counts as the file it leads to, so the clip ends up on the real file and no longer hangs on the shortcut. Several
different files of that name: it's left alone and said - the wrong sound in an edit is worse than a missing one. Never
looks in the home folder as a whole, or above it."""
import os

LEVELS_UP = 3      # folders that exist, going up from the path Resolve has
MAX_FILES = 200000  # (a folder this big isn't one library)


def _too_wide(folder):
    home = os.path.expanduser("~")
    folder = os.path.abspath(folder)
    return folder == home or home.startswith(folder + os.sep) or os.path.dirname(folder) == folder


def _matches(folder, name):
    """The real files `name` leads to below `folder`."""
    found, seen = set(), 0
    for root, _dirs, files in os.walk(folder):
        seen += len(files)
        if seen > MAX_FILES:
            break
        if name in files:
            real = os.path.realpath(os.path.join(root, name))
            if os.path.isfile(real):
                found.add(real)
    return found


def find_real(path):
    """(the file for this missing path, or None, and whether several were found)."""
    name, folder, tried = os.path.basename(path), os.path.dirname(path), 0
    while folder and tried < LEVELS_UP and not _too_wide(folder):
        if os.path.isdir(folder):
            tried += 1
            found = _matches(folder, name)
            if len(found) == 1:
                return found.pop(), False
            if found:
                return None, True
        parent = os.path.dirname(folder)
        if parent == folder:
            break
        folder = parent
    return None, False


def _missing_clips(folder, out):
    for clip in folder.GetClipList() or []:
        path = str(clip.GetClipProperty("File Path") or "")
        # (a picture sequence's path has its frames in brackets, and isn't one file to look for)
        if path and "[" not in os.path.basename(path) and not os.path.exists(path):
            out.append((clip, path))
    for inner in folder.GetSubFolderList() or []:
        _missing_clips(inner, out)
    return out


def _clips(count):
    return f"{count} clip{'s' if count != 1 else ''}"


def relink_missing(resolve):
    """(worked, what to say)."""
    project = resolve.GetProjectManager().GetCurrentProject()
    media_pool = project.GetMediaPool() if project else None
    if media_pool is None:
        return False, "Open a project first"
    missing = _missing_clips(media_pool.GetRootFolder(), [])
    if not missing:
        return False, "No clips are missing"
    into, lost, several = {}, [], []
    for clip, path in missing:
        real, many = find_real(path)
        if real:
            into.setdefault(os.path.dirname(real), []).append((clip, real))
        else:
            (several if many else lost).append(clip)
    done = 0
    for folder, clips in into.items():
        media_pool.RelinkClips([clip for clip, _real in clips], folder)
        for clip, real in clips:  # (its answer isn't what counts: where the clip points now is)
            now = str(clip.GetClipProperty("File Path") or "")
            if now and os.path.exists(now) and os.path.realpath(now) == real:
                done += 1
            else:
                lost.append(clip)
    said = [f"Relinked {_clips(done)}"] if done else []
    if several:
        said.append(f"{_clips(len(several))} with more than one match: {several[0].GetName()}")
    if lost:
        said.append(f"couldn't find {_clips(len(lost))}: {lost[0].GetName()}")
    message = ", ".join(said)
    print(f"[relink] {message}: {[c.GetName() for c in several + lost]}")
    return bool(done), message[0].upper() + message[1:]
