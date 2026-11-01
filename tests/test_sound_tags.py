"""A sound's energy and tags in the picker (tag_strip.py) and Mark the beats (beats.py) - against the fake Resolve.
python3 tests/test_sound_tags.py"""
import os
import subprocess
import sys
import tempfile

import _setup
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from clipse import beats, file_tags as ft, sound_analysis as sa

w, s, F = _setup.picker()
fails = 0


def check(what, ok):
    global fails
    print(("ok   " if ok else "FAIL ") + what)
    fails += not ok


def press(widget, key, text="", mods=Qt.NoModifier):
    QKeyHandled = QKeyEvent(QEvent.KeyPress, key, mods, text)
    _setup.app.sendEvent(widget, QKeyHandled)
    _setup.pump(0.02)


def settle():
    for _ in range(100):
        _setup.pump(0.02)
        if w.tag_keeper._writes.empty():
            break
    _setup.pump(0.1)


folder = tempfile.mkdtemp(prefix="clipse_sound_tags_")
paths = {}
for name, tags in (("calm.wav", ["bed", "e1"]), ("mid.wav", ["bed", "e2"]), ("hard.flac", ["opener", "e3"]),
                   ("plain.mp3", []), ("other.m4a", [])):
    path = os.path.join(folder, name)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=330:duration=1", path], check=True)
    if tags:
        ft.write(path, tags)
    paths[name] = path

rows = [r for r in w.model.clip_rows if r.category == "audio"][:5]
check("the stand-in has five sounds to tag", len(rows) == 5)
for row, (name, path) in zip(rows, paths.items()):
    row.name, row.file, row.music, row.file_tags, row.energy = name, path, True, [], 0
w._apply_analysis(w.model.clip_rows)
for _ in range(50):
    _setup.pump(0.02)
    if rows[0].file_tags:
        break
by = {row.name: row for row in rows}

print("-- reading --")
check("tags read from the files", by["calm.wav"].file_tags == ["bed", "e1"] and by["hard.flac"].file_tags == ["opener", "e3"])
check("energy from the tag", by["calm.wav"].energy == 1 and by["hard.flac"].energy == 3)
check("none: no bars", by["plain.mp3"].energy == 0)


def found(text):
    w.search_edit.setText(text)
    _setup.pump(0.05)
    return [w.model.rows[i].name for i in w.model.visible]


print("-- searching --")
check("a tag finds the sounds", set(found("bed")[:2]) == {"calm.wav", "mid.wav"})
check("e2 finds only that energy", found("e2") == ["mid.wav"])
check("with a word: bed e1", found("bed e1") == ["calm.wav"])
check("under a prefix too", found("a: e3") == ["hard.flac"])

print("-- the guess, only when asked for --")
from clipse.clip_model import shown_energy  # noqa: E402
from clipse.picker_window import SoundAnalyser, _set_energy  # noqa: E402
plain = by["plain.mp3"]
check("off as it ships", s.listen["guess_energy"] is False)
SoundAnalyser.apply(plain, {"energy": 0.8, "bpm": 120})
check("off: no bars, whatever the analysis says", shown_energy(plain, s) == (0, False))
check("...and e3 doesn't find it", "plain.mp3" not in found("e3"))
s.listen["guess_energy"] = True
check("on: the guess shows, as a guess", shown_energy(plain, s) == (3, True))
w.search_edit.setText("")
check("...and e3 finds it", "plain.mp3" in found("e3"))
check("your own tag still wins", shown_energy(by["mid.wav"], s) == (2, False))
SoundAnalyser.apply(plain, {"energy": 0.1, "bpm": 120})
check("calm is one", shown_energy(plain, s) == (1, True))
plain.analysis = None
plain.bpm = None
_set_energy(plain)
check("not analysed: nothing to guess from", shown_energy(plain, s) == (0, False))
s.listen["guess_energy"] = False

print("-- setting energy --")


def highlight(name):
    w.search_edit.setText("")
    found(name)
    w._select_row(0)
    _setup.pump(0.02)
    return w._tag_row()


row = highlight("plain.mp3")
check("the highlighted sound", row is not None and row.name == "plain.mp3")
press(w.search_edit, Qt.Key_2, "", Qt.AltModifier)
settle()
check("Alt+2: on the row at once and in the file", row.energy == 2 and ft.read(row.file) == ["e2"])
press(w.search_edit, Qt.Key_3, "", Qt.AltModifier)
settle()
check("Alt+3 replaces it", ft.read(row.file) == ["e3"])
press(w.search_edit, Qt.Key_3, "", Qt.AltModifier)
settle()
check("the same again takes it away", ft.read(row.file) == [] and row.energy == 0)

print("-- the strip --")
press(w.search_edit, Qt.Key_T, "", Qt.AltModifier)
_setup.pump(0.05)
check("Alt+T opens it, the keyboard in its field", w.tag_strip.isVisible() and w.focusWidget() is w.tag_strip.field)
field = w.tag_strip.field
check("nothing typed: only the top row", w.tag_strip.suggested() == [])
field.setText("e")
_setup.pump(0.02)
check("typing offers the tags on other sounds, never an energy", {"bed", "opener"} <= set(w.tag_strip.suggested())
      and not any(ft.ENERGY.fullmatch(t) for t in w.tag_strip.suggested()))
field.clear()
press(field, Qt.Key_1, "1")
settle()
check("1 with nothing typed: energy", ft.read(row.file) == ["e1"] and w.tag_strip.energy == 1)
field.setText("be")
_setup.pump(0.02)
check("typing narrows them", w.tag_strip.suggested() == ["bed"])
press(field, Qt.Key_Tab)
settle()
check("Tab takes the first", ft.read(row.file) == ["e1", "bed"] and field.text() == "")
field.setText("Brand New, BED")
press(field, Qt.Key_Return)
settle()
check("Enter adds what's typed, commas between, none twice", ft.read(row.file) == ["e1", "bed", "Brand New"])
check("the row has them", "Brand New" in row.file_tags)
check("...and they're found", "plain.mp3" in found("brand"))
highlight("plain.mp3")
press(field, Qt.Key_Backspace)
settle()
check("Backspace takes the last off", ft.read(row.file) == ["e1", "bed"])
field.setText("x")
press(field, Qt.Key_Escape)
check("Esc clears what's typed first", field.text() == "" and w.tag_strip.isVisible())
other = highlight("mid.wav")
_setup.pump(0.02)
check("it follows the list", other is not row and w.tag_strip.energy == 2 and "bed" in w.tag_strip.tags)
press(field, Qt.Key_Down)
_setup.pump(0.02)
press(field, Qt.Key_Up)
check("the arrows go on through the list", w.tag_strip.isVisible())
highlight("other.m4a")
check("a kind it can't tag says so", w.tag_strip.why_not and not field.isEnabled())
press(w.search_edit, Qt.Key_2, "", Qt.AltModifier)
settle()
check("...and the key changes nothing", ft.read(paths["other.m4a"]) == [])
highlight("mid.wav")
press(field, Qt.Key_Escape)
check("Esc closes it, the picker stays", not w.tag_strip.isVisible() and w.isVisible())

print("-- a file that won't take it --")
path = paths["calm.wav"]
row = highlight("calm.wav")
with open(path, "r+b") as f:
    f.seek(4)
    f.write(b"\xff\xff\xff\x7f")
    f.seek(16)
    f.write(b"\xff\xff\xff\x7f")
press(w.search_edit, Qt.Key_3, "", Qt.AltModifier)
settle()
_setup.pump(0.2)
check("the row goes back when the file refuses", row.energy != 3)

print("-- on the row's own menu, and in Actions --")
check("right-click has Tags", [c[0] for c in w._row_menu_choices(by["mid.wav"])] == ["Tags"])
labels = [a[1] for a in w._all_actions()]
check("Tags, Mark the beats and Mark the bars are actions", {"Tags", "Mark the beats", "Mark the bars"} <= set(labels))
check("each has a key to set", s.keybinds.get("act_mark_beats") == "" and s.keybinds.get("tag_clip") == "Alt+T")

print("-- what counts as music --")
from clipse.resolve_client import is_music  # noqa: E402
check("a minute with no word against it: music, beat or no beat", is_music("Johnny - Amy Rowe.mov", "", "", 278.6) is True)
check("under 30 s: a sound effect", is_music("thing.wav", "", "", 20) is False)
check("in between: the beat check decides", is_music("thing.wav", "", "", 45) is None)
check("the name wins over the length", is_music("long whoosh.wav", "", "", 200) is False
      and is_music("2026-10-30_keysounds_03.wav", "", "", 99) is False)
check("a higher setting still counts", is_music("thing.wav", "", "", 90, 120) is False)
long_song = os.path.join(folder, "no_beat.wav")
subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "anoisesrc=d=70:a=0.2", long_song], check=True)
hit = sa.analyse(long_song, False)
check("analysed as an effect: no tempo asked", "bpm" not in hit and "energy" not in hit)
check("...not complete now it's music", not sa.complete(hit, True) and sa.complete(hit, False))
hit = sa.analyse(long_song, True)
check("...so it's analysed again as music", "bpm" in hit)
check("...once", sa.complete(sa.cached(long_song), True))

print("-- the beats' places --")
frames = beats.beat_frames(120, 0.0, 0, 1, 100, 160, 0.0, 60)
check("120 BPM at 60 fps: every 30 frames, from the clip's start", [f for f, _n in frames] == [100, 130])
frames = beats.beat_frames(120, 0.25, 0, 1, 100, 200, 0.0, 60)
check("the first beat a quarter second in", [f for f, _n in frames] == [115, 145, 175])
frames = beats.beat_frames(120, 0.0, 0, 1, 100, 160, 10.1, 60)
check("a clip that starts 10.1 s into the song: the next beat", frames[0][0] == 100 + round(0.4 * 60))
frames = beats.beat_frames(120, 0.0, 1, 4, 100, 400, 0.0, 60)
check("bars from the beat they start on, numbered", frames == [(130, 1), (250, 2), (370, 3)])
frames = beats.beat_frames(120, 0.0, 0, 4, 100, 400, 4.0, 60)
check("a bar's number is its place in the song", frames[0] == (100, 3))
check("no tempo, nothing", beats.beat_frames(None, 0, 0, 1, 0, 100, 0, 60) == [])
check("a tempo too quick for the frames never marks a frame twice",
      len({f for f, _n in beats.beat_frames(600, 0, 0, 1, 0, 100, 0, 5)}) == len(beats.beat_frames(600, 0, 0, 1, 0, 100, 0, 5)))

print("-- which beat a bar starts on --")
import numpy as np  # noqa: E402
rate, bpm = 44100, 120.0
length = int(rate * 40)
music = np.zeros(length, dtype=np.float32)
t = np.arange(length) / rate
beat = 60 / bpm
for n in range(int(40 / beat)):
    at = int((n * beat) * rate)
    size = int(rate * 0.12)
    env = np.exp(-np.arange(size) / (rate * 0.03))
    level = 1.0 if n % 4 == 1 else 0.25  # (the kick leans on the second beat here)
    music[at:at + size] += (level * env * np.sin(2 * np.pi * 60 * np.arange(size) / rate))[:len(music[at:at + size])]
    root = [220.0, 261.6, 196.0, 174.6][((n - 1) // 4) % 4]  # (and the chord changes there)
    held = min(int(beat * rate), length - at)
    music[at:at + held] += 0.2 * np.sin(2 * np.pi * root * t[:held])
song = os.path.join(folder, "bars.wav")
pcm = (np.clip(music, -1, 1) * 32767).astype(np.int16)
with subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "s16le", "-ar", str(rate), "-ac", "1", "-i", "-", song],
                      stdin=subprocess.PIPE) as encoder:
    encoder.stdin.write(pcm.tobytes())
got = sa.bar_start(song, bpm, 0.0)
check("a bar starts where the kick and the harmony lean", got == 1)

print("-- marking --")


class Pool:
    def __init__(self, name, kind, file, media_id="m1"):
        self.name, self.kind, self.file, self.id = name, kind, file, media_id

    def GetName(self):
        return self.name

    def GetMediaId(self):
        return self.id

    def GetClipProperty(self, key=None):
        return {"Type": self.kind, "File Path": self.file}[key]


class Item:
    def __init__(self, pool, start, end, left=0):
        self.pool, self.start, self.end, self.left = pool, start, end, left

    def GetMediaPoolItem(self):
        return self.pool

    def GetStart(self):
        return self.start

    def GetEnd(self):
        return self.end

    def GetLeftOffset(self):
        return self.left


class Timeline:
    def __init__(self, items, selected=(), here=0):
        self.items, self.selected, self.here, self.marks, self.refused = items, list(selected), here, {}, set()

    def GetSetting(self, _name):
        return "60"

    def GetStartFrame(self):
        return 1000

    def GetCurrentTimecode(self):
        from clipse.timeline_tools import frames_tc
        return frames_tc(1000 + self.here, 60, False)

    def GetSelectedClips(self):
        return self.selected

    def GetTrackCount(self, _kind):
        return 1

    def GetItemListInTrack(self, _kind, _track):
        return self.items

    def GetMarkers(self):
        return dict(self.marks)

    def AddMarker(self, frame, colour, name, note, length, data):
        if frame in self.marks or frame in self.refused:
            return False
        self.marks[frame] = {"color": colour, "name": name, "note": note, "duration": length, "customData": data}
        return True

    def DeleteMarkerAtFrame(self, frame):
        return self.marks.pop(frame, None) is not None


class Folder:
    def __init__(self, clips):
        self.clips = clips

    def GetClipList(self):
        return self.clips

    def GetSubFolderList(self):
        return []


class MediaPool:
    def __init__(self, clips):
        self.root = Folder(clips)

    def GetRootFolder(self):
        return self.root


song_pool, other_pool = Pool("bars.wav", "Audio", song), Pool("mid.wav", "Audio", paths["mid.wav"], "m2")
clip = Item(song_pool, 1000 + 600, 1000 + 1200, left=300)
timeline = Timeline([Item(other_pool, 1000, 1000 + 100), clip], selected=[clip])
worked, _said = beats.mark(timeline, run="1")
expected = [f for f, _n in beats.beat_frames(*sa.beats(song), 0, 1, 600, 1200, 5.0, 60)]
check("a selected clip's beats, where it is, from where in the song it starts",
      worked and sorted(timeline.marks) == expected and expected[0] == 600)
check("marked as Clipse's own", timeline.marks[600] == {"color": beats.COLOUR, "name": "Beat", "note": "", "duration": 1,
                                                        "customData": "clipse_beats:1"})
beats.mark(timeline, bars=True, run="2")
check("the bars take the place of the beats over that clip", all(m["name"].startswith("Bar") for m in timeline.marks.values())
      and len(timeline.marks) < len(expected))
timeline.marks[10] = {"color": "Blue", "name": "Mine", "customData": ""}
check("Undo takes back that run alone, your own marker stays", beats.clear(timeline, "2") > 0 and list(timeline.marks) == [10])
timeline.marks.clear()
timeline.selected = []
timeline.here = 900
worked, _said = beats.mark(timeline, song=song, run="3")
check("nothing selected: the highlighted song on the timeline", worked and len(timeline.marks) == len(expected))
timeline.marks.clear()
worked, _said = beats.mark(timeline, run="4")
check("no song highlighted: the sound under the playhead", worked and min(timeline.marks) >= 600)
timeline.here = 50000
worked, said = beats.mark(Timeline([clip], here=50000), run="5")
check("nothing to go by: it says so", not worked and "Select" in said)
wrapped = Pool("bars", "Compound", "", "c1")
timeline = Timeline([Item(wrapped, 1000, 1000 + 600, left=120)], selected=[])
timeline.selected = list(timeline.items)
check("a compound clip of unknown song: asks", beats.mark(timeline, run="6") == (False, "Highlight the song in the picker first"))
worked, _said = beats.mark(timeline, run="7", media_pool=MediaPool([song_pool]))
check("named after a sound in the Media Pool: that one", worked and timeline.marks
      and sorted(timeline.marks) == [f for f, _n in beats.beat_frames(*sa.beats(song), 0, 1, 0, 600, 2.0, 60)])
timeline.marks.clear()
strange = Pool("my mix", "Compound", "", "c2")
timeline = Timeline([Item(strange, 1000, 1000 + 600)])
timeline.selected = list(timeline.items)
worked, _said = beats.mark(timeline, song=song, run="8")
check("named otherwise: the highlighted song", worked and timeline.marks)
beats.remember_compound("c3", song, 3.0)
timeline = Timeline([Item(Pool("x", "Compound", "", "c3"), 1000, 1000 + 600, left=60)])
timeline.selected = list(timeline.items)
worked, _said = beats.mark(timeline, run="9")
check("one Clipse wrapped: remembered, where in the song it starts", worked
      and sorted(timeline.marks) == [f for f, _n in beats.beat_frames(*sa.beats(song), 0, 1, 0, 600, 4.0, 60)])
from clipse import resolve_commands as commands  # noqa: E402
lines = commands._marker_lines(timeline, 60.0, 1000, False)
check("Copy timeline counts them, doesn't list them", len(lines) == 1 and "beat markers" in lines[0])

print("all good" if not fails else f"{fails} FAILED")
sys.exit(1 if fails else 0)
