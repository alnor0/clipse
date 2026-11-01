"""Stretch Marker to Clips and Edit Marker (markers.py) against a small stand-in timeline. python3 tests/test_markers.py"""
import _setup  # noqa: F401  (the throwaway HOME)
from clipse import markers

fails = 0


def check(what, ok):
    global fails
    print(("ok   " if ok else "FAIL ") + what)
    fails += not ok


class Item:
    def __init__(self, a, b): self.a, self.b = a, b
    def GetStart(self): return self.a
    def GetEnd(self): return self.b


class Timeline:
    """Markers by frame from the start (Resolve's way), clips by absolute frame; it starts at 01:00:00:00, 30 fps."""
    START = 108000

    def __init__(self):
        self.marks, self.selected, self.under, self.tc = {}, [], None, "01:00:00:00"
    def GetSetting(self, k): return "30" if k == "timelineFrameRate" else ""
    def GetStartFrame(self): return self.START
    def GetCurrentTimecode(self): return self.tc
    def GetSelectedClips(self): return list(self.selected)
    def GetCurrentVideoItem(self): return self.under
    def GetMarkers(self): return {float(f): dict(i) for f, i in self.marks.items()}
    def DeleteMarkerAtFrame(self, f): return self.marks.pop(int(f), None) is not None
    def AddMarker(self, f, color, name, note, duration, data=""):
        if int(f) in self.marks or not name: return False  # (as 21.1.1: no marker without a name)
        self.marks[int(f)] = {"color": color, "name": name, "note": note, "duration": duration, "customData": data}
        return True


t = Timeline()
check("nothing selected, nothing under the playhead: it says so", markers.fit(t)[:2] == (False, "Select clips, or put the playhead over one"))

# C put a marker at the playhead (0:02 = frame 60); two clips from 0:01 to 0:07 are selected
t.tc = "01:00:02:00"
t.marks[60] = {"color": "Blue", "name": "Marker 1", "note": "keep", "duration": 1, "customData": "x"}
t.selected = [Item(t.START + 30, t.START + 120), Item(t.START + 120, t.START + 210)]
worked, _said, frame, created = markers.fit(t)
check("the marker at the playhead is stretched over the selected clips",
      worked and list(t.marks) == [30] and t.marks[30]["duration"] == 180)
check("...keeping its colour, note and data", t.marks[30]["color"] == "Blue" and t.marks[30]["note"] == "keep"
      and t.marks[30]["customData"] == "x")

# again with the playhead inside the range: the same marker, fitted to the clip under the playhead
t.selected, t.under, t.tc = [], Item(t.START + 90, t.START + 150), "01:00:03:00"
markers.fit(t)
check("nothing selected: the clip under the playhead", list(t.marks) == [90] and t.marks[90]["duration"] == 60)

# no marker anywhere near: a new one over the clips
t.marks, t.tc = {}, "01:00:20:00"
t.selected = [Item(t.START + 300, t.START + 360)]
markers.fit(t)
check("no marker there: a new one over the clips, named (Resolve needs one)", t.marks.get(300, {}).get("duration") == 60
      and t.marks[300]["name"] == "Marker")

# a marker inside the selection, the playhead elsewhere: that one is fitted
t.marks = {320: {"color": "Red", "name": "x", "note": "", "duration": 1}}
t.selected = [Item(t.START + 300, t.START + 400)]
markers.fit(t)
check("one inside the selection is the one fitted", list(t.marks) == [300] and t.marks[300]["color"] == "Red")

# C again where the clips have a marker already (2026-10-30, "another marker starts here"): theirs is fitted, the
# empty new one goes
t.marks = {300: {"color": "Cream", "name": "b-roll", "note": "x", "duration": 50}, 350: {"color": "Blue", "name": "Marker 3", "duration": 1}}
t.tc = "01:00:11:20"  # (frame 350: the one just placed - Resolve named it)
t.selected = [Item(t.START + 300, t.START + 400)]
worked, said, frame, created = markers.fit(t)
check("the clips' own marker is fitted, the empty one just placed goes", worked and list(t.marks) == [300]
      and t.marks[300]["duration"] == 100 and t.marks[300]["note"] == "x")
t.marks = {300: {"color": "Cream", "duration": 50}, 350: {"color": "Red", "name": "mine", "duration": 1}}
worked, said, frame, created = markers.fit(t)
check("...one with words in it is never taken away: it says so", not worked and set(t.marks) == {300, 350}
      and "already" in said)


# Edit Marker: kind and words
t.marks = {90: {"color": "Blue", "name": "", "note": "", "duration": 60, "customData": "d"}}
t.tc = "01:00:04:00"
hit = markers.at(t, markers.playhead(t))
check("the marker at the playhead is found inside its range", hit is not None and hit[0] == 90)
worked, _ = markers.describe(t, 90, "B-roll", "  show the media pool  ")
check("Edit Marker: its kind's name and colour, the words, same place and length",
      worked and t.marks[90] == {"color": "Sky", "name": "B-roll", "note": "show the media pool", "duration": 60,
                                 "customData": "d"})
check("...read back as that kind", markers.kind_of(t.marks[90]) == "B-roll")
markers.describe(t, 90, "Explain", "")
check("changed to Explain: sand, words cleared", t.marks[90]["color"] == "Sand" and t.marks[90]["note"] == "")

# C's Enter: only now a marker, with its kind and words
t.marks = {}
check("C, Enter: the marker with its kind, colour and words", markers.add(t, 300, "Explain", " why this ")
      and t.marks[300] == {"color": "Sand", "name": "Explain", "note": "why this", "duration": 1, "customData": ""})

# Shift+C says which marker the window opens on, and whether it's new (Esc takes a new one away)
t.marks, t.tc, t.under = {}, "01:00:20:00", None
t.selected = [Item(t.START + 600, t.START + 660)]
worked, _said, frame, created = markers.fit(t)
check("Shift+C, no marker there: a new one, said so (for Esc)", worked and frame == 600 and created)
t.marks[600]["note"] = "words"
worked, _said, frame, created = markers.fit(t)
check("...again, it has words now: not new", worked and frame == 600 and not created)

# Hide - Show Markers: all off and kept, then back exactly
t.marks = {30: {"color": "Sky", "name": "B-roll", "note": "a", "duration": 60, "customData": ""},
           200: {"color": "Blue", "name": "Marker", "note": "", "duration": 1, "customData": ""}}
before = {f: dict(m) for f, m in t.marks.items()}
t.GetUniqueId = lambda: "tl-1"
said = markers.toggle(t)
check("hide: every marker off the timeline, kept", t.marks == {} and said == "2 markers hidden"
      and set(markers.hidden(t)) == {30, 200})
t.marks[200] = {"color": "Red", "name": "new", "note": "", "duration": 1, "customData": ""}  # (one added meanwhile)
said = markers.toggle(t)
check("show: back exactly; one added meanwhile in a kept one's place keeps it", t.marks[30] == before[30]
      and t.marks[200]["name"] == "new" and said.startswith("1 marker back") and set(markers.hidden(t)) == {200})
del t.marks[200]
said = markers.toggle(t)
check("...again: the last kept one back too", t.marks[200] == before[200] and markers.hidden(t) == {})
t.marks = {}
check("no markers: says so", markers.toggle(t) == "No markers on this timeline")

# the window
from clipse.settings import Settings
from clipse.marker_note import MarkerNote
s = Settings()
s.load()
w = MarkerNote(s)
got = []
w.done.connect(lambda kind, words: got.append((kind, words)))
w.ask("0:03.0 to 0:05.0", "Explain", "zoom in")
check("the window opens with the marker's kind and words", w.tiles.chosen == 1 and w.words.text() == "zoom in")
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
QTest.keyClick(w.words, Qt.Key_Tab)
QTest.keyClick(w.words, Qt.Key_Return)
check("Tab: the next kind; Enter: done with it", got == [("Note", "zoom in")] and not w.isVisible())
w.ask("0:03.0", "", "")
QTest.keyClick(w.words, Qt.Key_Return)
check("Enter with no words: placed all the same (words are optional)", got[-1] == ("B-roll", "") and not w.isVisible())
cancelled = []
w.cancelled.connect(lambda: cancelled.append(1))
w.ask("0:03.0", "", "")
QTest.keyClick(w.words, Qt.Key_Escape)
check("Esc: closed, nothing given", cancelled == [1] and len(got) == 2 and not w.isVisible())

print(f"\n{'all good' if not fails else f'{fails} failed'}")
raise SystemExit(1 if fails else 0)
