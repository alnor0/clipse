"""Relink missing clips (clipse/relink.py). python3 tests/test_relink.py"""
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from clipse import relink  # noqa: E402

fails = 0


def check(what, ok):
    global fails
    print(("ok   " if ok else "FAIL ") + what)
    fails += not ok


top = tempfile.mkdtemp(prefix="clipse_relink_")
library = os.path.join(top, "work", "library", "music")
os.makedirs(os.path.join(library, "_collections", "bed"))
os.makedirs(os.path.join(library, "stems"))


def make(path, words="sound"):
    with open(path, "w") as f:
        f.write(words)
    return path


song = make(os.path.join(library, "Song.mov"))
deep = make(os.path.join(library, "stems", "Deep.wav"))
twin_a = make(os.path.join(library, "Twin.wav"), "a")
os.makedirs(os.path.join(library, "other"))
twin_b = make(os.path.join(library, "other", "Twin.wav"), "b")
linked = make(os.path.join(library, "Linked.mov"))
os.symlink(linked, os.path.join(library, "_collections", "bed", "Linked.mov"))
gone_role = os.path.join(library, "_collections", "gone")

print("-- finding the file --")
check("in the folder above the shortcut", relink.find_real(os.path.join(gone_role, "Song.mov")) == (song, False))
check("in a folder below that", relink.find_real(os.path.join(gone_role, "Deep.wav")) == (deep, False))
check("a shortcut on the way counts as its file", relink.find_real(os.path.join(gone_role, "Linked.mov")) == (linked, False))
check("two different files of that name: none, and it says so", relink.find_real(os.path.join(gone_role, "Twin.wav")) == (None, True))
check("nowhere: none", relink.find_real(os.path.join(gone_role, "Nope.wav")) == (None, False))
home = os.path.expanduser("~")
check("never the whole home folder", relink._too_wide(home) and relink._too_wide(os.path.dirname(home))
      and relink._too_wide("/") and not relink._too_wide(os.path.join(home, "Music")))
check("not found under a folder gone with no library left", relink.find_real("/no/such/place/Song.mov") == (None, False))


class Clip:
    def __init__(self, name, path):
        self.name, self.path = name, path

    def GetName(self):
        return self.name

    def GetClipProperty(self, key):
        return {"File Path": self.path}[key]


class Folder:
    def __init__(self, clips, inner=()):
        self.clips, self.inner = clips, list(inner)

    def GetClipList(self):
        return self.clips

    def GetSubFolderList(self):
        return self.inner


class Pool:
    def __init__(self, root, refuse=False):
        self.root, self.refuse, self.calls = root, refuse, []

    def GetRootFolder(self):
        return self.root

    def RelinkClips(self, clips, folder):
        self.calls.append((len(clips), folder))
        if self.refuse:
            return False
        for clip in clips:
            clip.path = os.path.join(folder, clip.name)
        return True


class Project:
    def __init__(self, pool):
        self.pool = pool

    def GetMediaPool(self):
        return self.pool


class Resolve:
    def __init__(self, pool):
        self.pool = pool

    def GetProjectManager(self):
        return self

    def GetCurrentProject(self):
        return Project(self.pool) if self.pool else None


print("-- in a project --")
fine = Clip("Linked.mov", os.path.join(library, "_collections", "bed", "Linked.mov"))
title = Clip("Text+", "")
frames = Clip("shot.[0001-0100].exr", "/gone/shot.[0001-0100].exr")
a, b = Clip("Song.mov", os.path.join(gone_role, "Song.mov")), Clip("Deep.wav", os.path.join(gone_role, "Deep.wav"))
again = Clip("Song.mov", os.path.join(gone_role, "Song.mov"))
pool = Pool(Folder([a, fine, title, frames], [Folder([b, again])]))
check("relinks them", relink.relink_missing(Resolve(pool)) == (True, "Relinked 3 clips"))
check("each to its real file", a.path == song and again.path == song and b.path == deep)
check("a folder at a time", sorted(pool.calls) == sorted([(2, library), (1, os.path.join(library, "stems"))]))
check("what works is left alone, a title and a picture sequence too", fine.path.endswith("bed/Linked.mov") and
      title.path == "" and frames.path.startswith("/gone"))
check("again: none are missing", relink.relink_missing(Resolve(pool)) == (False, "No clips are missing"))
one = Clip("Song.mov", os.path.join(gone_role, "Song.mov"))
check("one is one clip", relink.relink_missing(Resolve(Pool(Folder([one])))) == (True, "Relinked 1 clip"))

twin, nope, ok = (Clip("Twin.wav", os.path.join(gone_role, "Twin.wav")), Clip("Nope.wav", os.path.join(gone_role, "Nope.wav")),
                  Clip("Song.mov", os.path.join(gone_role, "Song.mov")))
worked, said = relink.relink_missing(Resolve(Pool(Folder([twin, nope, ok]))))
check("says what it couldn't", worked and said == "Relinked 1 clip, 1 clip with more than one match: Twin.wav, couldn't find 1 clip: Nope.wav")
check("...and those stay as they were", twin.path.endswith("gone/Twin.wav") and nope.path.endswith("gone/Nope.wav"))
stuck = Clip("Song.mov", os.path.join(gone_role, "Song.mov"))
worked, said = relink.relink_missing(Resolve(Pool(Folder([stuck]), refuse=True)))
check("Resolve refusing isn't called done", not worked and said == "Couldn't find 1 clip: Song.mov")
check("no project: says so", relink.relink_missing(Resolve(None)) == (False, "Open a project first"))

shutil.rmtree(top, ignore_errors=True)
print("\nall good" if not fails else f"\n{fails} FAILED")
sys.exit(1 if fails else 0)
