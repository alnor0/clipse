"""A sound's tags inside the file (clipse/file_tags.py): all four kinds, and the sound never changes.
Run: python3 tests/test_file_tags.py (needs ffmpeg to make its sounds)."""
import hashlib
import os
import shutil
import struct
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
tmp_home = tempfile.mkdtemp(prefix="clipse_tags_")
os.environ["XDG_CACHE_HOME"] = os.path.join(tmp_home, "cache")
os.environ["XDG_CONFIG_HOME"] = os.path.join(tmp_home, "config")
os.environ["XDG_DATA_HOME"] = os.path.join(tmp_home, "data")
os.environ["XDG_STATE_HOME"] = os.path.join(tmp_home, "state")
from clipse import file_tags as ft  # noqa: E402

failures = 0


def check(what, ok):
    global failures
    print(("  ok    " if ok else "  FAIL  ") + what)
    failures += 0 if ok else 1


def make(name, *args):
    path = os.path.join(tmp_home, name)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=330:duration=2", *args, path],
                   check=True)
    return path


def sound_of(path):
    """What ffmpeg decodes: the sound itself, however the tags are kept."""
    out = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-map", "0:a", "-f", "s16le", "-"],
                         check=True, capture_output=True).stdout
    return hashlib.sha256(out).hexdigest()


files = {"wav": make("a.wav"), "mp3": make("a.mp3", "-id3v2_version", "4"), "flac": make("a.flac"),
         "mov": make("a.mov", "-c:a", "pcm_s16le")}
files["mp3 2.3"] = make("b.mp3", "-id3v2_version", "3", "-metadata", "title=Kept")
files["mp3 none"] = make("c.mp3", "-id3v2_version", "0", "-write_id3v1", "1", "-metadata", "title=Old")

for kind, path in files.items():
    print(kind)
    before = sound_of(path)
    mtime = os.stat(path).st_mtime_ns
    check("no tags to begin with", ft.read(path) == [])
    ft.write(path, ["bed", "e1", "two words"])
    check("reads back", ft.read(path) == ["bed", "e1", "two words"])
    check("the sound didn't change", sound_of(path) == before)
    check("the modified time stayed", os.stat(path).st_mtime_ns == mtime)
    stamp = ft._stamp(path)
    ft.write(path, ft.with_energy(ft.read(path), 3))
    check("energy replaced", ft.read(path) == ["bed", "two words", "e3"] and ft.energy_of(ft.read(path)) == 3)
    check("a change is seen, even at the same size and time", ft._stamp(path) != stamp)
    check("known at once", ft.known(path) == ["bed", "two words", "e3"])
    ft.write(path, ["bed", "two words", "e3"])
    ft.write(path, [])
    check("all taken away", ft.read(path) == [])
    check("the sound still didn't change", sound_of(path) == before)
    ft.write(path, ["æøå", "e2"])
    check("other letters", ft.read(path) == ["æøå", "e2"])
    check("nothing left beside it", not [f for f in os.listdir(tmp_home) if f.endswith(".tmp")])

print("the rest of the file's tags")
title = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format_tags=title", "-of", "csv=p=0", files["mp3 2.3"]],
                       capture_output=True, text=True).stdout.strip()
check("an MP3's title stays", title == "Kept")

print("through a link")
link = os.path.join(tmp_home, "link.mov")
os.symlink(files["mov"], link)
ft.write(link, ["opener"])
check("the real file changes, the link stays one", os.path.islink(link) and ft.read(files["mov"]) == ["opener"])

print("what's refused")
odd = os.path.join(tmp_home, "odd.wav")
shutil.copy(files["wav"], odd)
with open(odd, "r+b") as f:  # a chunk that runs past the end
    f.seek(36)
    f.write(b"data" + struct.pack("<I", 0x7FFFFFF0))
kept = open(odd, "rb").read()
try:
    ft.write(odd, ["x"])
    check("a damaged WAV is refused", False)
except ValueError:
    check("a damaged WAV is refused", open(odd, "rb").read() == kept)
middle = os.path.join(tmp_home, "fast.mov")
subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", files["mov"], "-c", "copy", "-movflags", "faststart", middle], check=True)
kept = open(middle, "rb").read()
try:
    ft.write(middle, ["x"])
    check("a .mov with its index first is refused", False)
except ValueError:
    check("a .mov with its index first is refused", open(middle, "rb").read() == kept)
check("no kind Clipse can't tag", not ft.can_tag("a.m4a") and ft.can_tag("A.WAV"))
try:
    ft.write(os.path.join(tmp_home, "x.m4a"), ["x"])
    check("an .m4a is refused", False)
except ValueError:
    check("an .m4a is refused", True)

print("energy")
check("one energy", ft.with_energy(["e1", "bed"], 2) == ["bed", "e2"] and ft.with_energy(["e1", "bed"], 0) == ["bed"])
check("reads either case", ft.energy_of(["bed", "E2"]) == 2 and ft.energy_of(["bed", "e12"]) == 0)

print("what's known")
path = files["wav"]
ft.write(path, ["known"])
os.utime(path, ns=(1, os.stat(path).st_mtime_ns))
check("fresh reads what changed", ft.fresh(path) == ["known"])
ft.save()
ft._state["known"] = None
check("kept for the next start", ft.known(path) == ["known"])

print("after tagging")
marker = os.path.join(tmp_home, "ran")
ft.after_tagging([path])  # no such file: nothing
hook = ft.paths.config("after_tagging")
os.makedirs(os.path.dirname(hook), exist_ok=True)
with open(hook, "w") as f:
    f.write(f'#!/bin/sh\nprintf "%s" "$1" > "{marker}"\n')
os.chmod(hook, 0o755)
ft.after_tagging([path])
import time  # noqa: E402
for _ in range(50):
    if os.path.exists(marker):
        break
    time.sleep(0.02)
check("a program of your own runs", os.path.exists(marker) and open(marker).read() == path)

shutil.rmtree(tmp_home, ignore_errors=True)
print("all good" if not failures else f"{failures} FAILED")
sys.exit(1 if failures else 0)
