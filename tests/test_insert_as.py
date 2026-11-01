"""Insert as presets against the fake Resolve: where clips land, End together,
the picture layout staying inside the frame, markers.  python3 tests/test_insert_as.py"""
import os

import _setup
from clipse import presets as pm
from clipse import resolve_client as rc

w, s, F = _setup.picker()
names = [r.name for r in w.model.clip_rows]
fails = 0


def check(what, ok):
    global fails
    print(("ok   " if ok else "FAIL ") + what)
    fails += not ok


def run(pid, rows, **change):
    F.TRACKS.clear()
    open(F.LOG, "w").close()
    if pid in ("markers", "cuts"):  # (no presets of their own any more: Normal with Where set, as Alt+M / Alt+C)
        preset = dict(pm.placing(s, pid))
    else:
        preset = dict(pm.get(s, pid))
    preset.update(change)
    w._insert_with(preset, rows)
    return sorted((k[0][0] + str(k[1]), i.n, i.a, i.b) for k, lst in F.TRACKS.items() for i in lst)


broll = [names.index(f"B-roll 00{i}.mp4") for i in range(3)]
photos = [names.index(f"photo_{i}.jpg") for i in (1, 2, 3)]

placed = run("normal", broll, spacing="back_to_back")
check("back to back: each starts where the last ended", [p[2] for p in placed] == [30, 210, 390])
placed = run("normal", broll, spacing="interval", gap=12, gap_end=12)
check("spaced out: 12 frames apart", [p[2] for p in placed] == [30, 42, 54])
placed = run("normal", photos, spacing="interval", ends="together", gap=20, gap_end=20, length=1.0,
             convert="compound")
check("end together + wrap: one compound clip, cut at the end point, named after what went in", placed == [("v1", "photo_1_and_2_more", 30, 100)])
check("...and the compound clip goes in the compound_clips bin (in clipse), not whichever bin is open",
      any(f.GetName() == "compound_clips" and any(c.GetName() == "photo_1_and_2_more" for c in f.GetClipList())
          for top in F.ROOT.subs if top.GetName() == "clipse" for f in top.subs))
placed = run("normal", photos, spacing="interval", ends="together", gap=20, gap_end=20, length=1.0)
check("end together without wrap: the stills are cut to the end point themselves - a second after the last "
      "one starts - and there's no compound clip",
      [(p[2], p[3]) for p in placed] == [(30, 100), (50, 100), (70, 100)] and "COMPOUND" not in open(F.LOG).read())
# (2026-10-24: "the second video clip somehow removes the first") - videos marked shorter than they are fit
# one after another on V1; ending together lengthens the first into the second: it moves up a track
w._marks[""] = {"in": 0.0, "out": 2.0}  # (the fake B-roll has no file path: every one marked 0-2 s)
placed = run("normal", broll, spacing="interval", ends="together", gap=100, gap_end=100)
w._marks.clear()
overlap = any(a[0] == b[0] and a[2] < b[3] and b[2] < a[3] for a in placed for b in placed if a is not b)
check("end together never takes a clip away: one lengthened into the next on its track goes up a track",
      len(placed) == 3 and not overlap and sorted(p[3] for p in placed) == [210, 290, 290])
placed = run("normal", photos, spacing="interval", gap=20, gap_end=20, length=2.0)
check("Length gives every still that length (2 s), each on its own track where they overlap",
      [(p[0], p[2], p[3]) for p in placed] == [("v1", 30, 90), ("v2", 50, 110), ("v3", 70, 130)])
check("...by marking the Media Pool clip for the moment of the insert - its marks are as they were after",
      all(c.GetMarkInOut() == {"video": {}} for c in F.ROOT.c if c.GetName().startswith("photo_")))
s.presets["still_length"] = 3.0
placed = run("normal", photos[:1])
check("with no Length a picture lasts what Insert as says a picture lasts (3 s)", [(p[2], p[3]) for p in placed] == [(30, 120)])
s.presets["still_length"] = 5.0
os.environ["FAKE_OLD_RESOLVE"] = "1"
placed = run("normal", photos[:1], length=2.0)
check("a Resolve that can't mark a clip: the still comes in at Resolve's length, as before",
      [(p[2], p[3]) for p in placed] == [(30, 180)])
del os.environ["FAKE_OLD_RESOLVE"]


# -- Insert as is for the one insert; History puts it back --
def insert_now(rows):
    F.TRACKS.clear()
    w._insert_with(pm.active(s), rows)
    return sorted((i.a, i.b) for lst in F.TRACKS.values() for i in lst)


s.presets["edits"]["normal"] = {"spacing": "interval", "gap": 20, "gap_end": 20, "length": 1.0}
w.history.clear()
first = insert_now(photos)
check("Normal set up for an insert is used for that insert...", first == [(30, 60), (50, 80), (70, 100)])
check("...and is plain again straight after - nothing is repeated by itself",
      "normal" not in s.presets["edits"] and pm.plain(pm.active(s)) and insert_now(photos) == [(30, 180)] * 3)
check("History says how that insert was made", "20 frames apart" in w.history[0]["summary"] and w.history[1]["summary"] == "3 clips")
from clipse import history_dialog as hd
check("History is kept on disk - a restart of the service doesn't empty it",
      [e["summary"] for e in hd.load()][-2:] == [e["summary"] for e in w.history][-2:] and len(hd.load()) >= 2)
check("...per project: each keeps its last 50",
      len(hd.save([{"clip_names": {"a": 1}, "project": p, "summary": ""} for p in ("A", "B") for _ in range(60)])) == 100)
hd.save(w.history)
w.restore_history_entry(w.history[0])
check("picking it in History sets Insert as up the way it was, to see and to use",
      pm.active(s)["spacing"] == "interval" and pm.active(s)["length"] == 1.0 and insert_now(photos) == first
      and pm.plain(pm.active(s)))
mine = pm.duplicate(s, dict(pm.get(s, "normal"), spacing="interval", gap=10, gap_end=10))
pm.set_active(s, mine["id"])
insert_now(photos)
check("one of your own presets is used once too, and stays in the list",
      s.presets["active"] == "normal" and pm.get(s, mine["id"]) is not None)
w.restore_history_entry(w.history[-1])
check("...History brings it back by name", s.presets["active"] == mine["id"])
s.presets["keep"] = True
insert_now(photos)
check("...unless it's kept", s.presets["active"] == mine["id"])
s.presets["keep"] = False
pm.delete(s, mine["id"])
pm.set_active(s, "normal")
w.model.staged = {}  # (History staged the clips again)
w._update_staged_summary()

# -- the Fusion page has a History of its own: what went into a composition --
edits_before = len(hd.of_project(w.history, None, "edit"))
w._record_fusion_history([("node", "Transform", "Transform"), ("clip", names[photos[0]], "/x/a.jpg"),
                          ("macro", "Glow", "/m/Glow.setting")])
w._record_fusion_history([("expression", "Breathe", "breathe")])
fusion = hd.of_project(w.history, None, "fusion")
check("the Fusion page's History: what went into a composition, kept apart from the Edit page's inserts",
      [e["summary"] for e in fusion] == ["1 node \u00b7 1 clip \u00b7 1 macro", "Breathe"]
      and len(hd.of_project(w.history, None, "edit")) == edits_before)
w.restore_history_entry(fusion[0])
check("...picking one stages its nodes, macros and clips again, in the order they went in",
      [(e["category"], e["name"]) for e in w.model.chain] == [("node", "Transform"), ("macro", "Glow")]
      and list(w.model.staged) == [photos[0]]
      and w.model.chain[0]["seq"] < w._clip_seq[photos[0]] < w.model.chain[1]["seq"])
w.model.chain[:] = []
w.model.staged = {}
w._clip_seq = {}
w._update_staged_summary()
from clipse.history_dialog import HistoryDialog  # noqa: E402
_dialog = HistoryDialog(w.history, s, w, page="fusion")
check("...and the History window on the Fusion page lists only those", len(_dialog.shown()) == 2)
_dialog.deleteLater()

# -- pictures and sounds each end by themselves, or together --
sounds = [names.index(n) for n in ("Upbeat Corporate.wav", "untitled_01.wav", "rain ambience.wav")]
placed = run("normal", photos + sounds, spacing="interval", gap=20, gap_end=20, ends="together", ends_audio="own",
             length=1.0)
check("pictures ending together a second after the last starts, sounds left at their own lengths",
      [(p[2], p[3]) for p in placed if p[0][0] == "v"] == [(30, 100), (50, 100), (70, 100)]
      and len({p[3] for p in placed if p[0][0] == "a"}) == 3)
placed = run("normal", photos + sounds, spacing="interval", gap=20, gap_end=20, ends="own", ends_audio="together",
             length=1.0, length_audio=2.0)
check("...the other way round: each picture a second, the sounds ending together 2 s after the last one starts",
      [(p[2], p[3]) for p in placed if p[0][0] == "v"] == [(30, 60), (50, 80), (70, 100)]
      and [(p[2], p[3]) for p in placed if p[0][0] == "a"] == [(30, 130), (50, 130), (70, 130)])
placed = run("normal", photos + sounds, spacing="interval", gap=20, gap_end=20, ends="together", ends_audio="together",
             length=1.0, length_audio=2.0)
check("...and both, each at its own point",
      {p[3] for p in placed if p[0][0] == "v"} == {100} and {p[3] for p in placed if p[0][0] == "a"} == {130})
plan = pm.timeline_plan(dict(pm.get(s, "normal"), spacing="interval", gap=20, gap_end=20, ends="together",
                             ends_audio="together", length=1.0, length_audio=2.0),
                        [("still", 150, "a"), ("still", 150, "b"), ("audio", 900, "x"), ("audio", 900, "y")], 30.0, 150)
check("the drawing shows the same: the pictures' end and the sounds' end", plan["ends"] == {"pictures": 50, "sounds": 80})
placed = run("normal", photos + sounds, spacing="interval", gap=20, gap_end=20, ends="audio", ends_audio="together",
             length_audio=2.0)
check("pictures can end with the sounds: all of them where the last sound ends",
      {p[3] for p in placed if p[0][0] == "v"} == {130} == {p[3] for p in placed if p[0][0] == "a"})
placed = run("normal", photos[:1] + sounds[:1], ends="audio")
check("...one picture and one sound: the picture is as long as the sound",
      len({p[3] for p in placed}) == 1 and [p[3] for p in placed if p[0][0] == "v"] != [180])
placed = run("normal", photos, spacing="interval", gap=20, gap_end=20, ends="audio")
check("...with no sound in the insert there's nothing to follow: the pictures end together",
      [(p[2], p[3]) for p in placed] == [(30, 220), (50, 220), (70, 220)])
plan = pm.timeline_plan(dict(pm.get(s, "normal"), spacing="interval", gap=20, gap_end=20, ends="audio"),
                        [("still", 150, "a"), ("still", 150, "b"), ("audio", 90, "x"), ("audio", 60, "y")], 30.0, 150)
check("the drawing agrees: the pictures' end is the end of the sound that ends last", plan["ends"] == {"pictures": 90}
      and [i["end"] for i in plan["items"] if i["kind"] == "still"] == [90, 90])

# -- sounds can end with the pictures (2026-10-16: "like the picture ends with the sound") --
placed = run("normal", photos[:2] + sounds, spacing="interval", gap=20, gap_end=20, ends_audio="pictures", length=2.0)
seen_end = max(p[3] for p in placed if p[0][0] == "v")
check("sounds end with the pictures: every sound where the last picture ends",
      {p[3] for p in placed if p[0][0] == "a"} == {seen_end} and seen_end == 50 + 60)
placed = run("normal", photos[:1] + sounds[:1], ends_audio="pictures", length=1.0)
check("...one picture and one sound: the sound as long as the picture", {p[3] for p in placed} == {60})
plan = pm.timeline_plan(dict(pm.get(s, "normal"), spacing="interval", gap=20, gap_end=20, ends_audio="pictures",
                             length=3.0), [("still", 150, "a"), ("audio", 300, "x"), ("audio", 60, "y")], 30.0, 150)
check("...the drawing agrees - a sound shorter than that ends early, as far as it goes",
      [(i["kind"], i["end"]) for i in plan["items"]] == [("still", 90), ("audio", 90), ("audio", 80)]
      and plan["ends"].get("sounds") == 90)
plan = pm.timeline_plan(dict(pm.get(s, "normal"), spacing="interval", gap=20, gap_end=20, ends_audio="pictures",
                             ends="audio"), [("still", 150, "a"), ("audio", 300, "x")], 30.0, 150)
check("...each with the other: both where the last one ends", [i["end"] for i in plan["items"]] == [300, 300])
check("...and it says so", "sounds end with the pictures" in pm.summary(dict(pm.get(s, "normal"), ends_audio="pictures")))

placed = run("normal", sounds, spacing="interval", gap=20, gap_end=20, ends_audio="first", length_audio=2.0)
check("sounds can end with the first one: all where it ends, 2 s after it starts",
      [(p[2], p[3]) for p in placed] == [(30, 90), (50, 90), (70, 90)])
plan = pm.timeline_plan(dict(pm.get(s, "normal"), spacing="interval", gap=20, gap_end=20, ends_audio="first"),
                        [("audio", 90, "x"), ("audio", 200, "y"), ("audio", 200, "z")], 30.0, 150)
check("...as long as it is, when no length is given - the drawing agrees",
      plan["ends"] == {"sounds": 90} and [i["end"] for i in plan["items"]] == [90, 90, 90])

# -- the same numbers by dragging in the drawing --
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from clipse.insert_as_dialog import TimelinePreview as _Drawing
shown = dict(pm.get(s, "normal"), spacing="interval", gap=20, gap_end=20, ends="together")
drawing = _Drawing(s, shown, [("still", 150, "a"), ("still", 150, "b"), ("audio", 90, "x"), ("audio", 60, "y")], 30.0)
drawing.resize(700, drawing.minimumHeight())
dragged = []


def take(key, seconds, done):
    dragged.append((key, seconds, done))
    shown[key] = seconds
    drawing.refresh()


drawing.edited.connect(take)


def mouse(kind, pos):
    return QMouseEvent(kind, pos, pos, Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)


grips = {key: (last, rect) for key, last, rect in drawing.handles()}
check("the last picture and the last sound each have an end to drag", set(grips) == {"length", "length_audio"})
last, rect = grips["length"]
was_end = last["end"]
drawing.mousePressEvent(mouse(QEvent.MouseButtonPress, rect.center()))
drawing.mouseMoveEvent(mouse(QEvent.MouseMove, rect.center() + QPointF(-120, 0)))
drawing.mouseReleaseEvent(mouse(QEvent.MouseButtonRelease, rect.center() + QPointF(-120, 0)))
check("dragging the last picture's end to the left makes it shorter - and with End together, all of them end there",
      dragged[-1][0] == "length" and dragged[-1][2] is True and 0 < shown["length"] * 30 < was_end - last["start"]
      and len({i["end"] for i in drawing.plan["items"] if i["kind"] == "still"}) == 1)
last, rect = dict((k, (l, r)) for k, l, r in drawing.handles())["length_audio"]
drawing.mousePressEvent(mouse(QEvent.MouseButtonPress, rect.center()))
drawing.mouseMoveEvent(mouse(QEvent.MouseMove, rect.center() + QPointF(300, 0)))
drawing.mouseReleaseEvent(mouse(QEvent.MouseButtonRelease, rect.center() + QPointF(300, 0)))
check("a sound can't be dragged longer than it is", shown["length_audio"] == 2.0)
# it catches on things: here the end of the second sound (clip 4 in the drawing), from a few pixels off
last, rect = dict((k, (l, r)) for k, l, r in drawing.handles())["length"]
there = drawing.plan["items"][3]["end"]
drawing.mousePressEvent(mouse(QEvent.MouseButtonPress, rect.center()))
near = QPointF(drawing._x(there) + 4, rect.center().y())
drawing.mouseMoveEvent(mouse(QEvent.MouseMove, near))
caught = drawing._snap
drawing.mouseReleaseEvent(mouse(QEvent.MouseButtonRelease, near))
check("a dragged end catches on what's near it - the end of a sound - and says what",
      there % 15 and caught == (there, "end of 4") and round(shown["length"] * 30) == there - last["start"])
drawing.mousePressEvent(mouse(QEvent.MouseButtonPress, dict((k, r) for k, l, r in drawing.handles())["length"].center()))
free = QMouseEvent(QEvent.MouseMove, near, near, Qt.LeftButton, Qt.LeftButton, Qt.AltModifier)
drawing.mouseMoveEvent(free)
loose = drawing._snap
drawing.mouseReleaseEvent(mouse(QEvent.MouseButtonRelease, near))
check("...with Alt held it goes where the mouse is", loose is None and round(shown["length"] * 30) != there - last["start"])
drawing.mouseDoubleClickEvent(mouse(QEvent.MouseButtonDblClick, dict((k, r) for k, l, r in drawing.handles())["length"].center()))
check("a double-click on an end gives the clip its own length back", shown["length"] == 0.0)
shown["ends"] = "audio"
drawing.refresh()
check("pictures ending with the sounds have no end of their own to drag", [k for k, _l, _r in drawing.handles()] == ["length_audio"])
from clipse.insert_as_dialog import InsertAsDialog
dialog = InsertAsDialog(s, sample=[("still", 150, "a"), ("still", 150, "b"), ("audio", 90, "x")], fps=30.0, markers={})
dialog._pick("normal")
yours_before = len(s.presets["user"])
dialog._length_dragged("length", 1.5, True)
check("in Insert as a drag lands in the preset and in its number field",
      pm.get(s, "normal")["length"] == 1.5 and dialog._spins["length"].value() == 1.5)
check("a change to a built-in preset is the one in use - but it's never written down",
      dialog.preset["id"] == "normal" and pm.get(s, "normal")["edited"] and s.as_dict()["presets"]["edits"] == {}
      and len(s.presets["user"]) == yours_before)
check("...its buttons: Save as mine and Reset, no Duplicate",
      not dialog.keep_button.isHidden() and not dialog.reset_button.isHidden() and dialog.dup_button.isHidden())
pm.used(s, pm.get(s, "normal"))
check("...and after the insert every built-in is as it ships again", not s.presets["edits"] and pm.plain(pm.get(s, "normal")))
_bare = InsertAsDialog(s, sample=[("still", 150, "a")], fps=30.0, markers={},
                       events={"markers": {}, "cuts": [], "start": 0, "playhead": 0, "now": []})
_bare.preset.update(where="markers")
_bare._use_now(_bare.preset["id"])
_marker_words = _bare.cannot.text()
_bare.preset.update(where="cuts")
_bare._use_now(_bare.preset["id"])
check("Insert now at every marker / cut on a timeline with none: Insert as stays open and says why (the bar's message was missed)",
      not _bare.insert_now and _marker_words == "No markers on the timeline" and _bare.cannot.text() == "No cuts on V1 to put them at")
_bare.events["markers"] = {100: "Blue"}
_bare.preset.update(where="markers")
_bare._use_now(_bare.preset["id"])
check("...with a marker there it goes", _bare.insert_now)
pm.used(s, pm.get(s, "normal"))
dialog._pick("normal")
dialog._length_dragged("length", 2.0, True)
dialog._save_as_mine()
mine_now = dialog.preset["id"]
check("Save as mine: a preset of your own, as it was set up, in use - Normal back to how it ships",
      mine_now != "normal" and pm.get(s, mine_now)["name"] == "My normal" and pm.get(s, mine_now)["length"] == 2.0
      and pm.plain(pm.get(s, "normal")) and s.presets["active"] == mine_now and len(s.presets["user"]) == yours_before + 1
      and dialog.name_edit is not None and dialog.reset_button is None)
pm.delete(s, mine_now)
pm.set_active(s, "normal")
from clipse.settings import Settings as _Settings
old_way = _Settings()
old_way.apply({"presets": {"edits": {"normal": {"spacing": "interval", "gap": 9, "gap_end": 9}}, "active": "normal", "migrated": True}})
check("a built-in preset changed the old way (in place) becomes one of your own when the settings are read",
      not old_way.presets["edits"] and pm.plain(pm.get(old_way, "normal"))
      and [(u["name"], u["gap"]) for u in old_way.presets["user"]] == [("My normal", 9)]
      and old_way.presets["active"] == old_way.presets["user"][0]["id"])
# a number field drags from the number itself - also when the press has just given it the keyboard (Qt does
# that before the press arrives: a field that took "has the keyboard" for "is being typed in" never dragged)
from PySide6.QtTest import QTest
from PySide6.QtCore import QPoint
dialog._pick("normal")
turn = dialog._spins["rotation"]
edit = turn.lineEdit()
edit.setFocus()
QTest.mousePress(edit, Qt.LeftButton, Qt.NoModifier, QPoint(10, 5))
for x in range(13, 73, 3):
    QTest.mouseMove(edit, QPoint(x, 5))
QTest.mouseRelease(edit, Qt.LeftButton, Qt.NoModifier, QPoint(72, 5))
check("a number field drags from the number, keyboard on it or not", turn.value() > 0 and not turn._editing)
QTest.mouseClick(edit, Qt.LeftButton, Qt.NoModifier, QPoint(10, 5))
_setup.pump(0.05)
QTest.keyClicks(edit, "12")
QTest.keyClick(edit, Qt.Key_Return)
check("...and a plain click is for typing", turn.value() == 12.0)
QTest.mouseClick(edit, Qt.LeftButton, Qt.NoModifier, QPoint(10, 5))
_setup.pump(0.05)
QTest.keyClicks(edit, "20")
_setup.pump(0.05)  # typed - no Enter, and still in the field
before = turn.value()
QTest.mousePress(edit, Qt.LeftButton, Qt.NoModifier, QPoint(10, 5))
for x in range(13, 73, 3):
    QTest.mouseMove(edit, QPoint(x, 5))
QTest.mouseRelease(edit, Qt.LeftButton, Qt.NoModifier, QPoint(72, 5))
check("...and once it's been typed in, it drags again - from what was typed", before == 12.0 and turn.value() > 20.0
      and not turn._editing)
pm.used(s, pm.get(s, "normal"))
# a preset duplicated in the open dialog: the copy's editor has no Reset button - and nothing may reach for the old one
dialog._pick("normal")
dialog._duplicate()
copy_id = dialog.preset["id"]
try:
    dialog._length_dragged("length", 2.5, True)
    dialog._save(rebuild=True)
    went = pm.get(s, copy_id)["length"] == 2.5 and not dialog.preset.get("builtin")
except RuntimeError as e:
    went = False
    print(e)
check("after Duplicate the copy can be changed - no reaching for the built-in preset's Reset button, which is gone", went)
pm.delete(s, copy_id)
dialog._pick("normal")
from clipse.insert_as_dialog import CurveEditor
curve = CurveEditor(s, dict(pm.get(s, "normal"), spacing="interval", gap=24, gap_end=3), 20, 60.0)
curve.resize(700, 196)
check("the gap curve is drawn for the clips of the insert: 19 gaps for 20 clips, each with a bar to rest the mouse on",
      len(curve._gaps()) == 19 and curve._gaps()[0] == 24 and curve._gaps()[-1] == 3
      and curve._bar_at(QPointF(curve._plot().left() + 2, curve._plot().center().y())) == 0
      and curve._bar_at(QPointF(curve._plot().right() - 2, curve._plot().center().y())) == 18)
check("...with lines across at round numbers, and both numbers for a gap: frames and seconds",
      CurveEditor._step(30) == 10 and CurveEditor._step(7) == 2 and curve._words(24) == "24 f \u00b7 0.40 s")
curve.grab()  # (it paints)
# every pillar can be dragged: its gap is then set by hand
by_hand = dict(pm.get(s, "normal"), spacing="interval", gap=24, gap_end=4)
pillars = CurveEditor(s, by_hand, 6, 30.0)
pillars.resize(700, 196)
before = pillars._gaps()
plot = pillars._plot()
third = plot.left() + plot.width() / 5 * 2.5
pillars.mousePressEvent(mouse(QEvent.MouseButtonPress, QPointF(third, plot.bottom() - 3)))
pillars.mouseMoveEvent(mouse(QEvent.MouseMove, QPointF(third, pillars._y(17))))
pillars.mouseReleaseEvent(mouse(QEvent.MouseButtonRelease, QPointF(third, pillars._y(17))))
after = pm.exact_gaps(by_hand)
check("dragging a pillar of the gap curve sets that gap by hand - the others stay as the curve had them",
      after[2] == 17 and after[:2] + after[3:] == before[:2] + before[3:] and pillars._gaps() == after)
pillars.grab()
pillars.mousePressEvent(mouse(QEvent.MouseButtonPress, pillars._back.center()))
check("...and Back to the curve lets go of them", by_hand["gaps"] == "" and pillars._gaps() == before)
# -- scattered pictures fill the frame: edges and corners --
def reaches(places, w=1920.0, h=1080.0):
    """How many of the frame's four corners have a picture over them, and how far the pile reaches to each side."""
    boxes = [(p["pan"], p["tilt"], p["size"][0] * p["zoom"] / 2, p["size"][1] * p["zoom"] / 2) for p in places]
    corners = sum(any(abs(cx - x) <= bw and abs(cy - y) <= bh for x, y, bw, bh in boxes)
                  for cx, cy in ((-w / 2 + 70, -h / 2 + 70), (w / 2 - 70, -h / 2 + 70), (-w / 2 + 70, h / 2 - 70), (w / 2 - 70, h / 2 - 70)))
    return corners, min(x - bw for x, _y, bw, _bh in boxes), max(x + bw for x, _y, bw, _bh in boxes)


pile = dict(pm.FIELDS, scale=39.5, scatter=100.0, rotation_vary=5.0)
worst = min(reaches(pm.layout(pile, 20, 1920, 1080, None, seed))[0] for seed in range(40))
sides = [reaches(pm.layout(pile, 8, 1920, 1080, [1.0] * 8, seed)) for seed in range(40)]
check("twenty scattered pictures reach the frame's corners - at least three of the four, whatever the shuffle",
      worst >= 3)
check("...and eight square ones touch its left and right edge, corners covered",
      all(c == 4 and left < -940 and right > 940 for c, left, right in sides))

neat = pm.layout(dict(pile, scatter_random=0.0, rotation_vary=0.0), 12, 1920, 1080, None, 3)
loose = pm.layout(dict(pile, scatter_random=100.0, rotation_vary=0.0), 12, 1920, 1080, None, 3)
check("Randomness: at 0 % the scattered pictures stand in straight rows and columns, at 100 % they don't",
      len({round(p["tilt"]) for p in neat}) <= 3 and len({round(p["pan"]) for p in neat}) <= 5
      and len({round(p["tilt"]) for p in loose}) > 6)
his_gaps = dict(pm.FIELDS, spacing="interval", gaps="24, 14, 11, 9, 7, 6, 5, 4, 3, 6, 2, 2, 2, 1, 1, 1, 1")
check("gaps set by hand go on with their last number for the clips beyond the list (17 gaps, 25 clips)",
      pm.gaps(his_gaps, 25) == [24, 14, 11, 9, 7, 6, 5, 4, 3, 6, 2, 2, 2, 1, 1, 1, 1] + [1] * 7
      and pm.offsets(his_gaps, 25)[-1] == 99 + 7 and pm.gaps(his_gaps, 5) == [24, 14, 11, 9])

# -- Play: a click where each clip starts --
from clipse import click_track
ticks = click_track.samples([0.0, 0.5, 0.75], 1.0)


def loudest(a, b):
    return max(abs(v) for v in ticks[int(a * click_track.RATE):int(b * click_track.RATE)])


check("the click track has a hit at each start and quiet between them",
      len(ticks) == int((0.75 + click_track.TICK + click_track.TAIL) * click_track.RATE)
      and min(loudest(0.0, 0.05), loudest(0.5, 0.55), loudest(0.75, 0.8)) > 8000
      and loudest(0.06, 0.45) == 0 and loudest(0.56, 0.74) == 0)
hit = click_track._hit(1.0)
crossings = sum(1 for i in range(1, len(hit)) if (hit[i - 1] < 0) != (hit[i] < 0))
check("...a tap, not a beep and nothing ringing on: it starts hard and is gone within a twentieth of a second",
      max(abs(v) for v in hit[:120]) > 12000 and max(abs(v) for v in hit[-120:]) < 400 and len(hit) / click_track.RATE <= 0.05
      and click_track._hit(1.0, bright=True) != hit and crossings > 20)
heard = []
pillars.clicks.play = lambda times: heard.append(list(times)) or None
pillars.grab()
pillars.mousePressEvent(mouse(QEvent.MouseButtonPress, pillars._play.center()))
check("Play on the gap curve ticks where each clip starts (at 30 fps, the gaps in seconds added up)",
      heard and [round(v, 3) for v in heard[-1]] == [round(f / 30.0, 3) for f in pm.offsets(by_hand, 6)] and heard[-1][0] == 0.0)
pillars.mousePressEvent(mouse(QEvent.MouseButtonPress, QPointF(third, plot.bottom() - 3)))
pillars.mouseMoveEvent(mouse(QEvent.MouseMove, QPointF(third, pillars._y(9))))
pillars.mouseReleaseEvent(mouse(QEvent.MouseButtonRelease, QPointF(third, pillars._y(9))))
check("...and again by itself after a pillar is moved, with the new gap in it",
      len(heard) == 2 and round(heard[-1][3] - heard[-1][2], 3) == round(9 / 30.0, 3))
pillars.stop()
by_hand["gaps"] = ""
from clipse.insert_as_dialog import FramePad
square = pm.layout(dict(pm.FIELDS, scale=40.0, scatter=100.0), 12, 1920, 1080, [1.0] * 12, 5)
wide = pm.layout(dict(pm.FIELDS, scale=40.0, scatter=100.0), 12, 1920, 1080, None, 5)
check("a square picture has more room to the sides than a 16:9 one - the frame in Insert as is told the shapes",
      max(abs(p["pan"]) for p in square) > max(abs(p["pan"]) for p in wide) + 100
      and "shapes" in InsertAsDialog.__init__.__code__.co_varnames and hasattr(FramePad(s, by_hand, lambda: 5), "shapes"))
s.presets["edits"].pop("normal", None)
dialog.close()

s.presets["edits"]["normal"] = {"ends": "together"}
check("a preset saved when one Ends was for both keeps ending its sounds together too",
      pm.get(s, "normal")["ends_audio"] == "together")
s.presets["edits"].pop("normal")

whoosh = names.index("whoosh.wav")
placed = run("normal", [whoosh, photos[0]], length=2.0, length_audio=0.5)
check("sounds have a length of their own: the picture 2 s, the sound half a second",
      sorted((p[0][0], p[3] - p[2]) for p in placed) == [("a", 15), ("v", 60)])
whole = [p[3] - p[2] for p in run("normal", [whoosh])]
placed = run("normal", [whoosh, photos[0]], length=1.0)
check("...and with Sound length left at Whole sound it isn't cut", [p[3] - p[2] for p in placed if p[0][0] == "a"] == whole
      and whole != [30] and [p[3] - p[2] for p in placed if p[0][0] == "v"] == [30])
pm.save(s, dict(pm.get(s, "normal"), length=2.0, ends="together"))
check("a Length or Ends set now is for the pictures alone - saved and read back, the sounds' are untouched",
      pm.get(s, "normal")["length_audio"] == 0.0 and pm.get(s, "normal")["ends_audio"] == "own"
      and pm.get(s, "normal")["length"] == 2.0)
s.presets["edits"]["normal"] = {"length": 1.5}
check("a preset saved when one Length was for both keeps cutting its sounds",
      pm.get(s, "normal")["length_audio"] == 1.5 and pm._with_sound_length({"length_audio": 0.0, "length": 2.0})["length_audio"] == 0.0)
s.presets["edits"].pop("normal")
from clipse.insert_as_dialog import TimelinePreview
many = [("audio", 40, "hit")] * 20 + [("still", 150, "logo")] * 20
drawing = TimelinePreview(s, dict(pm.get(s, "normal"), spacing="interval", gap=12, gap_end=3), many, 30.0)
few = TimelinePreview(s, dict(pm.get(s, "normal"), spacing="interval", gap=12, gap_end=3), many[:4] + many[20:24], 30.0)
check("the drawing in Insert as shows all 40 clips, on thinner lanes - not a wall",
      len(drawing.plan["items"]) == 40 and drawing.lane < few.lane and drawing.minimumHeight() < 560)


class _Sound:  # a sound whose frame rate isn't the timeline's - as Resolve reports one
    def __init__(self, fps, duration): self.fps, self.duration = fps, duration
    def GetName(self): return "bells.wav"
    def GetClipProperty(self, key=None):
        return {"FPS": self.fps, "Frames": "", "Duration": self.duration, "Type": "Audio"}.get(key)


bells = _Sound(24.0, "00:00:01:17")
check("a length is asked for in the clip's own frames: 25 timeline frames of a 24 fps sound on a 60 fps "
      "timeline are 10 of its own, and back",
      rc.of_clip(bells, 25, 60.0) == 10 and rc.on_timeline(bells, 10, 60.0) == 25)
check("...and a sound's whole length is read the same way: 01:17 on a 60 fps timeline is 77 frames there, 31 of its own",
      rc.compute_clip_duration(s, bells, "bells.wav", 60.0) == 31)

real_markers = F.TL.GetMarkers
F.TL.GetMarkers = lambda self: {300: {"color": "Blue"}, 600: {}, 900: {}}  # far enough in for a clip to end there
marks = w._place_frames(F.CURRENT[0], "markers")
s.presets["still_length"] = 2.0
placed = run("markers", photos[:1], align_pictures="end")
check("at every marker, Ends there: each still ends on its marker", [p[3] for p in placed] == marks)
s.presets["still_length"] = 2.0
placed = run("markers", photos[:1], align_pictures="centre")
check("at every marker, Centred: each still's middle is on its marker",
      [(p[2] + p[3]) // 2 for p in placed] == marks)
placed = run("markers", broll[:1], align_pictures="end")
check("at every marker, Ends there: videos too", [p[3] for p in placed] == marks)
tl_fps = float(F.CURRENT[0].GetSetting("timelineFrameRate"))
placed = run("markers", broll[:1], shift=0.5)
check("at every marker, moved half a second later: each starts that far after its marker",
      [p[2] for p in placed] == [m + int(round(0.5 * tl_fps)) for m in marks])
placed = run("markers", broll[:1], align_pictures="centre", shift=-0.25)
check("...and Centred, a quarter second earlier", [(p[2] + p[3]) // 2 for p in placed] ==
      [m - int(round(0.25 * tl_fps)) for m in marks])
placed = run("markers", photos[:1] + sounds[1:2])
check("a picture and a sound staged: both land on every marker",
      sorted(p[2] for p in placed if p[0][0] == "v") == marks and sorted(p[2] for p in placed if p[0][0] == "a") == marks)
placed = run("markers", photos[:1] + sounds[1:2], pair="turns")
check("...or take turns, one per marker", [p[2] for p in sorted(placed, key=lambda p: p[2])] == marks)
F.TL.GetMarkers = lambda self: {300: {}, 400: {}, 900: {}}  # the first two closer together than a clip is long
long_one = run("markers", broll[:1])[0][3] - 300
check("(the B-roll is longer than the markers are apart)", long_one > 100)
placed = run("markers", broll[:1], overlap="stack")
check("overlapping, Stacked: whole clips, the second on the track above",
      [(p[0], p[2]) for p in placed] == [("v1", 300), ("v1", 900), ("v2", 400)])
placed = run("markers", broll[:1], overlap="cut_first")
check("overlapping, Cut the first: it stops where the next starts - all on one track",
      [(p[0], p[2], p[3]) for p in placed] == [("v1", 300, 400), ("v1", 400, 400 + long_one), ("v1", 900, 900 + long_one)])
placed = run("markers", broll[:1], overlap="cut_next")
check("overlapping, Cut the next: it starts where the first ends, and ends where it would have",
      [(p[0], p[2], p[3]) for p in placed] == [("v1", 300, 300 + long_one), ("v1", 300 + long_one, 400 + long_one),
                                               ("v1", 900, 900 + long_one)])
placed = run("markers", broll[:1], overlap="back_to_back")
check("overlapping, Back to back: the next waits for the first to end, whole",
      [(p[0], p[2], p[3]) for p in placed] == [("v1", 300, 300 + long_one), ("v1", 300 + long_one, 300 + 2 * long_one),
                                               ("v1", 900, 900 + long_one)])
F.TL.GetMarkers = real_markers

# the plan behind it, by itself
plan = pm.marker_plan(dict(pm.FIELDS, align="loudest"), [100, 200], [{"length": 60, "loudest": 12, "sound": True}], 30.0)
check("Loudest there: a clip's loudest moment lands on the marker", [e["start"] + 12 for e in plan] == [100, 200])
both_kinds = [{"length": 60, "loudest": None, "sound": False, "name": "logo"},
              {"length": 30, "loudest": 9, "sound": True, "name": "hit"}]
plan = pm.marker_plan(dict(pm.FIELDS, align="loudest", align_pictures="centre"), [100], both_kinds, 30.0)
check("pictures and sounds each have their own On the marker: the sound's loudest moment, the picture centred",
      sorted((e["clip"], e["start"]) for e in plan) == [(0, 70), (1, 91)])
check("...an old preset with one for both keeps it for its pictures (but not Loudest there)",
      pm._clean({"align": "end"})["align_pictures"] == "end" and pm._clean({"align": "loudest"})["align_pictures"] == "start")
plan = pm.marker_plan(dict(pm.FIELDS, shift=0.5, clip_shifts={"hit": -0.2}), [100], both_kinds, 30.0)
check("one clip moved by itself: on top of what they all move", sorted((e["clip"], e["start"]) for e in plan) == [(0, 115), (1, 109)])
three = [{"length": 5, "sound": False, "name": "a"}, {"length": 5, "sound": False, "name": "b"},
         {"length": 5, "sound": True, "name": "s"}]
marks6 = [0, 100, 200, 300, 400, 500]
def picked(**change):
    return [(e["event"], e["clip"]) for e in pm.marker_plan(dict(pm.FIELDS, **change), marks6, three, 30.0)]
check("more markers than clips, Start over: they go round again", [c for _m, c in picked() if c != 2] == [0, 1] * 3
      and [m for m, c in picked() if c == 2] == marks6)
check("...Each once: the markers after them get nothing", picked(run_out="once") == [(0, 0), (0, 2), (100, 1)])
check("...only the sounds start over: the pictures once each, the sound on every marker",
      sorted(picked(run_out="sounds_repeat")) == sorted([(0, 0), (100, 1)] + [(m, 2) for m in marks6]))
check("...only the pictures start over", sorted(picked(run_out="pictures_repeat"))
      == sorted([(0, 2)] + [(m, (0, 1)[n % 2]) for n, m in enumerate(marks6)]))
check("...and one clip per marker, Each once: every clip once, in turn",
      picked(run_out="once", pair="turns") == [(0, 0), (100, 1), (200, 2)])
plan = pm.marker_plan(dict(pm.FIELDS, align="loudest"), [100], [{"length": 60, "loudest": None}], 30.0)
check("...a clip with no sound to go by starts there", plan[0]["start"] == 100)
plan = pm.marker_plan(dict(pm.FIELDS, overlap="cut_first", pair="turns"), [100, 110],
                      [{"length": 60, "sound": False}, {"length": 60, "sound": True}], 30.0)
check("a sound under a picture is no overlap: neither is cut", [e["length"] for e in plan] == [60, 60])
mixed = [{"length": 20, "sound": False}, {"length": 20, "sound": True}, {"length": 20, "sound": True}]
plan = pm.marker_plan(dict(pm.FIELDS), [100, 200, 300], mixed, 30.0)
check("pictures and sounds Both on each: every marker gets the picture and a sound, the sounds taking turns",
      [(e["event"], e["clip"]) for e in plan] == [(100, 0), (100, 1), (200, 0), (200, 2), (300, 0), (300, 1)])
plan = pm.marker_plan(dict(pm.FIELDS, pair="turns"), [100, 200, 300], mixed, 30.0)
check("...Take turns: one clip per marker, whichever is next", [e["clip"] for e in plan] == [0, 1, 2])
plan = pm.marker_plan(dict(pm.FIELDS, overlap="cut_next"), [100, 110, 400], [{"length": 200}, {"length": 50}], 30.0)
check("Cut the next: a clip covered all the way is left out", [e["event"] for e in plan] == [100, 400])
import random as _random
plan = pm.marker_plan(dict(pm.FIELDS, order="random"), list(range(0, 2400, 100)), [{"length": 10}] * 3, 30.0,
                      _random.Random(4))
picks = [e["clip"] for e in plan]
check("At random: every clip gets used, never the same one twice running",
      set(picks) == {0, 1, 2} and all(a != b for a, b in zip(picks, picks[1:])) and picks != [0, 1, 2] * 8)
drawn = pm.timeline_plan(dict(pm.FIELDS, where="markers", overlap="cut_next"), [("video", 120, "a")], 30.0)
check("the drawing in Insert as knows what's cut off at the front", any(i["head"] for i in drawn["items"])
      and all(i["track"] == 1 for i in drawn["items"]))
drawn = pm.timeline_plan(dict(pm.FIELDS, where="markers"), [("audio", 20, "a"), ("still", 150, "b")], 30.0,
                         events=[3000, 3060, 3900])
check("the drawing in Insert as is of your markers, as far apart as they are - a picture and a sound on each",
      drawn["events"] == [30, 90, 930] and len(drawn["items"]) == 6)
check("the summary says where it sits and what happens to overlaps",
      pm.summary(dict(pm.FIELDS, where="markers", align="loudest", shift=0.5, overlap="cut_first"))
      == "At every marker \u00b7 sounds loudest on it \u00b7 moved 0.5 s later \u00b7 an overlap cuts the first")

bad = 0
p = dict(pm.FIELDS, scale=60.0, scale_vary=30.0, scatter=50.0, rotation_vary=25.0)
for mode in ("fit", "fill", "stretch"):
    for seed in range(100):
        for pl in pm.layout(p, 8, 1920, 1080, [(4032, 3024), (3024, 4032), None] * 3, seed, mode):
            w0, h0 = pl["size"]
            bw, bh = pm._rotated_box(w0 * pl["zoom"], h0 * pl["zoom"], pl["angle"])
            bad += abs(pl["pan"]) + bw / 2 > 960.01 or abs(pl["tilt"]) + bh / 2 > 540.01
check("scatter keeps every picture inside the frame (2,400 layouts)", bad == 0)

# the numbers Resolve gets: a Pan of p moves a picture p * (its width at zoom 1 / the frame's width)
# pixels (measured in Resolve 21.1.1) - with those, every picture must still be wholly inside
bad = 0
for (fw, fh), mode in (((3840, 2160), "fit"), ((1920, 1080), "fill"), ((1080, 1920), "fit"), ((3840, 2160), "native")):
    for seed in range(50):
        for pl in pm.layout(p, 6, fw, fh, [(4032, 3024), (3024, 4032), (1280, 720)] * 2, seed, mode):
            props = pm.props_for(p, pl)
            w0, h0 = pl["size"]
            zoom = props.get("ZoomX", 1.0)
            bw, bh = pm._rotated_box(w0 * zoom, h0 * zoom, props.get("RotationAngle", 0.0))
            dx, dy = props.get("Pan", 0.0) * w0 / fw, props.get("Tilt", 0.0) * h0 / fh
            bad += abs(dx) + bw / 2 > fw / 2 + 0.5 or abs(dy) + bh / 2 > fh / 2 + 0.5
check("... and still is with the Pan / Tilt numbers Resolve is given", bad == 0)

# a margin below 0: pictures may go over the edge, but never further than that
over = 0.0
p_over = dict(p, margin=-5.0)
for seed in range(100):
    for pl in pm.layout(p_over, 8, 1920, 1080, [(4032, 3024), (3024, 4032), None] * 3, seed):
        w0, h0 = pl["size"]
        bw, bh = pm._rotated_box(w0 * pl["zoom"], h0 * pl["zoom"], pl["angle"])
        over = max(over, (abs(pl["pan"]) + bw / 2 - 960) / 1920, (abs(pl["tilt"]) + bh / 2 - 540) / 1080)
check("a margin of -5 % lets pictures over the edge, by 5 % at most", 0.03 < over <= 0.05)

soft = pm.gaps(dict(pm.FIELDS, gap=30, gap_end=3, curve=list(pm.CURVES["ease_in"])), 9)
hard = pm.gaps(dict(pm.FIELDS, gap=30, gap_end=3, curve=list(pm.CURVES["ease_in"]), curve_strength=3), 9)
check("Strength 3 eases much harder, between the same first and last gap",
      soft[0] == hard[0] == 30 and soft[-1] == hard[-1] == 3 and hard[4] > soft[4] + 4 and hard == sorted(hard)[::-1])


class Old:
    presets = {"user": [], "edits": {"compound": {"x": -5.0}, "normal": {"length": 2.0}}, "active": "compound",
               "seeds": {"fusion": 1}, "migrated": True}


pm.tidy(Old)
kept = Old.presets["user"]
check("a retired preset you had changed becomes one of your own",
      len(kept) == 1 and kept[0]["name"] == "As a compound clip" and kept[0]["convert"] == "compound"
      and kept[0]["x"] == -5.0 and Old.presets["active"] == kept[0]["id"] and "compound" not in Old.presets["edits"]
      and Old.presets["edits"]["normal"] == {"length": 2.0} and len(pm.all_presets(Old)) == len(pm.BUILTINS) + 1)
check("Normal is the one built-in: At every marker and On every cut were Where's own choices twice over",
      pm.BUILTIN_IDS == ["normal"] and pm.placing(s, "markers")["where"] == "markers"
      and pm.placing(s, "cuts")["align_pictures"] == "centre")
check("Back to back is no Basic of its own any more (Normal, one after another): Ctrl+Enter does that",
      "back_to_back" not in pm.BUILTIN_IDS and pm.back_to_back(s)["spacing"] == "back_to_back"
      and pm.back_to_back(s)["where"] == "playhead")

F.TRACKS.clear()
every = w._place_frames(F.CURRENT[0], "markers")
red = w._place_frames(F.CURRENT[0], "markers", ["Red"])
check("At every marker can take only the colours you choose",
      len(every) == 3 and len(red) == 1 and red[0] in every
      and sorted(w._timeline_markers(F.CURRENT[0]).values()) == ["Blue", "Blue", "Red"])

item = F.Item("cam.mp4", 0, 300)
item.GetMarkers = lambda: {40: {}, 140: {}}
item.GetLeftOffset = lambda: 10
F.TRACKS[("video", 1)] = [item]
F.TL.GetMarkers = lambda self: {}
check("markers on clips are found", w._place_frames(F.CURRENT[0], "markers") == [30, 130])

# -- In the frame: what Size counts from - the whole picture, the frame's width or height, or filling it --
def _sized(by, scale, aspect):
    place = pm.layout(dict(pm._clean(pm.FIELDS), size_by=by, scale=scale), 1, 1920, 1080, aspects=[aspect])[0]
    return round(place["size"][0] * place["zoom"]), round(place["size"][1] * place["zoom"])
check("100 % of the frame's width / height: a picture of any shape reaches those edges",
      all(_sized("width", 100.0, a)[0] == 1920 and _sized("height", 100.0, a)[1] == 1080 for a in (16 / 9, 9 / 16, 4 / 3)))
check("...filling the frame covers it whatever the shape, and 50 % of the width is half of it",
      all(min(_sized("fill", 100.0, a)[0] - 1920, _sized("fill", 100.0, a)[1] - 1080) == 0 for a in (16 / 9, 9 / 16, 4 / 3))
      and _sized("width", 50.0, 9 / 16)[0] == 960)
check("...they're never made smaller to stay inside (they're meant to reach the edges) - the whole picture still is",
      _sized("width", 100.0, 9 / 16)[1] > 1080 and _sized("fit", 100.0, 9 / 16)[1] <= 1080)
check("...and the preset says so",
      "50 % of the frame's width" in pm.summary(dict(pm._clean(pm.FIELDS), size_by="width", scale=50.0))
      and pm._clean(dict(pm.FIELDS, size_by="nonsense"))["size_by"] == "fit" and pm.has_picture_changes(
          dict(pm._clean(pm.FIELDS), size_by="fill")))

# -- At every cut: the cuts of the tracks you choose, not only V1's --
_tracks_before = dict(F.TRACKS)
F.TRACKS.clear()
F.TRACKS[("video", 1)] = [F.Item("a", 0, 100), F.Item("b", 100, 250), F.Item("c", 250, 400)]
F.TRACKS[("video", 2)] = [F.Item("d", 50, 120), F.Item("e", 120, 300)]
F.TRACKS[("audio", 1)] = [F.Item("f", 0, 80), F.Item("g", 80, 200)]
F.TRACKS[("audio", 2)] = [F.Item("h", 0, 50), F.Item("i", 70, 90)]  # (a gap: the next clip's start is the cut)
by_track = w._clips_by_track(F.CURRENT[0])
check("every track's clips are read, and its cuts are where a clip on it begins after another",
      {t: pm.cut_frames(by_track, [t]) for t in by_track} == {"V1": [100, 250], "V2": [120], "A1": [80], "A2": [70]})
check("...or every clip's start (the first one too), every end (the last one too), or both",
      w._place_frames(F.CURRENT[0], "cuts", tracks=["V1"], edges="starts") == [0, 100, 250]
      and w._place_frames(F.CURRENT[0], "cuts", tracks=["V1"], edges="ends") == [100, 250, 400]
      and w._place_frames(F.CURRENT[0], "cuts", tracks=["A2"], edges="both") == [0, 50, 70, 90]
      and w._place_frames(F.CURRENT[0], "cuts", tracks=["A2"]) == [70])
check("...V1's when nothing else is chosen - the way it always was", w._place_frames(F.CURRENT[0], "cuts") == [100, 250])
check("...several tracks: a cut on any of them, each once",
      w._place_frames(F.CURRENT[0], "cuts", tracks=["V1", "V2", "A1"]) == [80, 100, 120, 250]
      and pm.cut_frames({"V1": [10], "A1": [10]}, ["V1", "A1"]) == [10])
_tracks = pm._clean(dict(pm.FIELDS, where="cuts", cut_tracks=["A1", "V2", "nonsense", "V2"]))
check("the tracks are kept tidy (V before A, each once, only real ones) - and say so in the preset's line",
      _tracks["cut_tracks"] == ["V2", "A1"] and pm._clean(dict(pm.FIELDS, cut_tracks=[]))["cut_tracks"] == ["V1"]
      and pm.summary(_tracks).startswith("At every cut on V2 and A1")
      and pm.changes(_tracks) == [("at every cut", ("where",)), ("cuts on V2, A1", ("cut_tracks",))]
      and pm.summary(dict(_tracks, cut_edges="starts")).startswith("At every clip start on V2 and A1")
      and pm._clean(dict(_tracks, cut_edges="nonsense"))["cut_edges"] == "between")
from clipse.insert_as_dialog import CutTiles  # noqa: E402
_cut_dialog = InsertAsDialog(s, sample=[("still", 150, "a")], fps=30.0, markers={},
                             events={"markers": {}, "clips_by_track": by_track, "start": 0, "playhead": 0, "now": []})
_cut_dialog.preset.update(where="cuts")
_cut_dialog._build_editor() if hasattr(_cut_dialog, "_build_editor") else None
_cut_tiles = _cut_dialog.findChildren(CutTiles)
check("Insert as at every cut: a tile for every track on the timeline, V1 chosen",
      len(_cut_tiles) == 1 and _cut_tiles[0].tracks == ["V1", "V2", "A1", "A2"] and _cut_tiles[0].chosen == ["V1"])
if _cut_tiles:
    _t = _cut_tiles[0]
    _t.resize(_t.sizeHint())
    for _track in ("A1", "V1"):  # A1 on, then V1 off
        _at = _t._rect(_t.tracks.index(_track)).center()
        _t.mousePressEvent(QMouseEvent(QEvent.MouseButtonPress, _at, _t.mapToGlobal(_at), Qt.LeftButton,
                                       Qt.LeftButton, Qt.NoModifier))
    _only = _t._rect(_t.tracks.index("A1")).center()
    _t.mousePressEvent(QMouseEvent(QEvent.MouseButtonPress, _only, _t.mapToGlobal(_only), Qt.LeftButton,
                                   Qt.LeftButton, Qt.NoModifier))
    check("...click to choose, several or one - never none (the last one stays)",
          _t.chosen == ["A1"] and _cut_dialog.preset["cut_tracks"] == ["A1"]
          and _cut_dialog._nowhere(_cut_dialog.preset) == "")
    _cut_dialog.preset["cut_tracks"] = ["V3"]
    check("...a track with no cuts says so", _cut_dialog._nowhere(_cut_dialog.preset) == "No cuts on V3 to put them at")
_cut_dialog.close()
pm.used(s, pm.get(s, "normal"))  # (Normal as it ships again for what follows)
F.TRACKS.clear()
F.TRACKS.update(_tracks_before)

crashed = 0
for preset in pm.all_presets(s):
    for count in (1, 2, 3, 5):
        try:
            plan = pm.timeline_plan(preset, [("video", 100, "a"), ("still", 150, "b"), ("audio", 80, "c"),
                                             ("video", 60, "d"), ("still", 150, "e")][:count])
            crashed += any("track" not in it for it in plan["items"])
        except Exception as e:
            print(f"     {preset['name']} with {count}: {type(e).__name__} {e}")
            crashed += 1
check("the preview works for every preset with 1, 2, 3 and 5 clips", crashed == 0)

# -- a clip whose sound is two tracks, many times at once (what Resolve does: see the fake) --
def tracks(kind):
    return sorted(k[1] for k, items in F.TRACKS.items() if k[0] == kind and items)


def insert(rows):
    """Inserts the rows the normal way; what it reported at the end."""
    import contextlib
    import io
    said = io.StringIO()
    with contextlib.redirect_stdout(said):
        w._insert_with(dict(pm.get(s, "normal")), rows)
    return said.getvalue().strip().splitlines()[-1]


F.TL.GetMarkers = real_markers
rec, mics = names.index("screen rec.mp4"), names.index("two mics.wav")
F.TRACKS.clear()
F.TRACKS[("video", 1)], F.TRACKS[("audio", 1)] = [], []  # a new timeline: V1 and A1, nothing on them
message = insert([rec] * 10)
check("ten copies of a clip with two-track sound: all ten land", len(tracks("video")) == 10
      and sum(len(v) for k, v in F.TRACKS.items() if k[0] == "video") == 10)
check("...each with both of its sound tracks, on audio tracks made for them", tracks("audio") == list(range(1, 21)))
check("...and no empty video tracks left in between", tracks("video") == list(range(1, 11))
      and F.CURRENT[0].GetTrackCount("video") == 10)
check("...and it says so", message == "Inserted 10 clips.")
pictures = [i for k, v in F.TRACKS.items() if k[0] == "video" for i in v]
check("...every copy still linked to its own two sound tracks (not to all twenty, or none)",
      all(len(i.GetLinkedItems()) == 2 for i in pictures)
      and len({id(x) for i in pictures for x in i.GetLinkedItems()}) == 20)
F.TRACKS.clear()
F.TRACKS[("video", 1)], F.TRACKS[("audio", 1)] = [], []
F.TRACKS[("audio", 2)] = [F.Item("music.wav", 0, 9000)]  # A2 already has music under the playhead
insert([rec])
check("a sound track that's taken is stepped over: the sound goes on the next two free ones",
      sorted(k for k, v in F.TRACKS.items() if any(i.n == "screen rec.mp4" for i in v)) ==
      [("audio", 3), ("audio", 4), ("video", 2)] and len(F.TRACKS[("audio", 2)]) == 1)
F.TRACKS.clear()
F.TRACKS[("video", 1)], F.TRACKS[("audio", 1)] = [], []
insert([mics])
check("a sound with two tracks, on its own: both land (a second audio track is made)", tracks("audio") == [1, 2])
F.TRACKS.clear()
F.TRACKS[("video", 1)], F.TRACKS[("audio", 1)] = [], []
real_add = F.TL.AddTrack
F.TL.AddTrack = lambda self, kind, sub=None: False if kind == "audio" else real_add(self, kind, sub)  # Resolve says no
shown = []
real_say, w._say = w._say, lambda text, ms=3500, **_kw: shown.append(text)
open(F.LOG, "w").close()
message = insert([rec] * 3)
F.TL.AddTrack = real_add
w._say = real_say
tried = open(F.LOG).read().count("APPEND ")
check("when Resolve won't take the first clip, the insert stops there - it doesn't go on to try twenty tracks for "
      "every clip - and says so on screen, not only in the log",
      shown == [w.NOTHING_LANDS] and "nothing was inserted" in shown[0] and tried <= 20)
check("...and leaves no empty tracks behind", F.CURRENT[0].GetTrackCount("video") <= 1)

# -- Enter once is one insert: the keyboard's repeat doesn't add a clip after the ones asked for --
from PySide6.QtCore import QEvent, Qt
# -- Repeat to match: 1 picture and 3 sounds, the picture goes in with every sound --
placed = run("normal", [photos[0]] + sounds, spacing="back_to_back", repeat="match")
heard = sorted({(p[2], p[3]) for p in placed if p[0][0] == "a"})
seen = sorted((p[2], p[3]) for p in placed if p[0][0] == "v")
check("Repeat, back to back: the one picture with every sound, as long as it - the sounds one after another",
      len(heard) == 3 and seen == heard and all(a[1] == b[0] for a, b in zip(heard, heard[1:])))
placed = run("normal", [photos[0]] + sounds, spacing="back_to_back")
check("...Each once: the picture once", sum(p[0][0] == "v" for p in placed) == 1)
placed = run("normal", [photos[0]] + sounds, spacing="interval", gap=20, gap_end=20, length=0.5, repeat="match")
check("...spaced out: a picture at every sound's start",
      sorted(p[2] for p in placed if p[0][0] == "v") == sorted({p[2] for p in placed if p[0][0] == "a"}) == [30, 50, 70])
placed = run("normal", photos + sounds[:1], spacing="back_to_back", repeat="match", length=1.0)
check("...the other way round: the sound with every picture, cut where the picture ends",
      sorted({(p[2], p[3]) for p in placed if p[0][0] == "a"}) == [(30, 60), (60, 90), (90, 120)])
plan = pm.timeline_plan(dict(pm.get(s, "normal"), spacing="back_to_back", repeat="match"),
                        [("still", 1, "photo")] + [("audio", 40, "a"), ("audio", 25, "b")])
check("...the drawing shows it the same way", [(i["kind"], i["start"], i["end"]) for i in plan["items"]] ==
      [("audio", 0, 40), ("still", 0, 40), ("audio", 40, 65), ("still", 40, 65)])
check("...and says so under the name", ("repeated to match", ("repeat",)) in
      pm.changes(dict(pm.get(s, "normal"), spacing="back_to_back", repeat="match")))

# -- Repeat: how many pictures and how many sounds, in all (2026-10-16: "2 of the same sounds and 1
# picture, and I want 20 of each" - "the most versatile and simple options") --
placed = run("normal", [sounds[0], sounds[0], photos[0]], spacing="back_to_back", repeat="match",
             pictures_count=20, sounds_count=20)
heard = sorted({(p[2], p[3]) for p in placed if p[0][0] == "a"})
seen = sorted((p[2], p[3]) for p in placed if p[0][0] == "v")
check("2 of the same sound and 1 picture, 20 of each: twenty pairs one after another, each picture its sound's length",
      len(heard) == 20 and seen == heard and all(a[1] == b[0] for a, b in zip(heard, heard[1:])))
plan = pm.timeline_plan(dict(pm.get(s, "normal"), spacing="back_to_back", repeat="match", pictures_count=20),
                        [("audio", 40, "bonk"), ("audio", 40, "bonk"), ("still", 150, "meme")])
check("...only Pictures set: the sounds match it - twenty of each in the drawing",
      sum(i["kind"] == "still" for i in plan["items"]) == 20 and sum(i["kind"] == "audio" for i in plan["items"]) == 20)
plan = pm.timeline_plan(dict(pm.get(s, "normal"), spacing="back_to_back", repeat="match", pictures_count=5,
                             sounds_count=12), [("still", 150, "meme"), ("audio", 40, "bonk")])
check("...5 pictures and 12 sounds: five pairs, then the sounds by themselves",
      sum(i["kind"] == "still" for i in plan["items"]) == 5 and sum(i["kind"] == "audio" for i in plan["items"]) == 12
      and max(i["end"] for i in plan["items"]) == 12 * 40)
placed = run("normal", [photos[0]] + sounds, spacing="back_to_back", repeat="match")
check("...both on Match: as before - 1 picture and 3 sounds, the picture with every sound",
      sum(p[0][0] == "v" for p in placed) == 3)
placed = run("normal", [photos[0]], spacing="back_to_back", repeat="match", pictures_count=3, length=1.0)
check("...one picture by itself, 3: one after another",
      [(p[2], p[3]) for p in placed if p[0][0] == "v"] == [(30, 60), (60, 90), (90, 120)])
placed = run("normal", broll[:2], spacing="interval", gap=12, gap_end=12, repeat="match", pictures_count=3)
check("...spaced out: 2 staged, 3 - the first starts over", sorted(p[2] for p in placed if p[0][0] == "v") == [30, 42, 54])
placed = run("normal", [sounds[0], photos[0]], spacing="back_to_back", pictures_count=20, sounds_count=20)
check("...Each once: the numbers do nothing", sum(p[0][0] == "v" for p in placed) == 1)
check("...and the chips say it plainly", [w for w, _k in pm.changes(dict(pm.get(s, "normal"), spacing="back_to_back",
      repeat="match", pictures_count=20, sounds_count=20))][1:] == ["repeated", "20 pictures", "20 sounds"])
from clipse.insert_as_dialog import InsertAsDialog as _IA, ChoiceTiles as _CT  # noqa: E402
s.presets["edits"].pop("normal", None)  # (Normal as it ships - an editor's change stays for the insert)
_ia = _IA(s, sample=[("still", 150, "meme"), ("audio", 40, "bonk")])
_ia.show()
_ia._pick("normal")
_tiles = next(t for t in _ia.findChildren(_CT) if [k for k, _l, _a in t.options] == ["once", "match"])
check("Insert as: Pictures and sounds is there with Stacked too", _ia.preset["spacing"] == "together")
_tiles._choose(1)
_setup.pump(0.1)
check("...Repeat picked while stacked: one after another instead (copies on one spot are no use)",
      _ia.preset["repeat"] == "match" and _ia.preset["spacing"] == "back_to_back")
_ia.close()
s.presets["edits"].pop("normal", None)
_ia = _IA(s, sample=[("still", 150, "a"), ("still", 150, "b"), ("audio", 40, "bonk")])
_ia.resize(700, 800)
_ia.show()
_ia._pick("normal")
_wide = []
for _spacing in ("together", "back_to_back", "interval"):
    _ia.preset["spacing"] = _spacing
    _ia._save(rebuild=True)
    _setup.pump(0.2)
    _wide.append(_ia.scroll.widget().width() - _ia.scroll.viewport().width())
check("Insert as narrow: nothing wider than the window (rows of tiles wrap) - every spacing", max(_wide) <= 0)
_ia.close()
from clipse.insert_as_dialog import SideOrUnder as _SOU, FramePad as _FPad  # noqa: E402
for _width in (700, 1000):  # (it lay flat - In the frame gone - at full width once)
    _ia = _IA(s, sample=[("still", 150, "a"), ("audio", 40, "bonk")])
    _ia.resize(_width, 800)
    _ia.show()
    _ia._pick("normal")
    _setup.pump(0.2)
    _row, _pad = _ia.findChildren(_SOU)[0], _ia.findChildren(_FPad)[0]
    check(f"In the frame at {_width} px: the frame has its room", _row.height() >= _pad.height() > 0
          and _pad.geometry().bottom() <= _row.height())
    _ia.close()
from clipse.insert_as_dialog import FramePad as _FP  # noqa: E402
s.presets["edits"].pop("normal", None)
_ia = _IA(s, sample=[("audio", 40, "bonk"), ("audio", 40, "bonk"), ("still", 150, "meme")], shapes=[(1080, 1080)])
_ia.show()
_ia._pick("normal")
check("In the frame: as many pictures as go in - one staged, one drawn", _ia.findChildren(_FP)[0].count == 1)
_ia.preset.update(spacing="back_to_back", repeat="match", pictures_count=20)
_ia._save(rebuild=True)
_setup.pump(0.1)
check("...Repeat, 20 pictures: twenty in the frame, each the shape of its picture",
      _ia._pad.count == 20 and _ia._pad.shapes == [(1080, 1080)] * 20)
_ia.preset["pictures_count"] = 7
_ia._save()
check("...the number changed: the frame follows at once", _ia._pad.count == 7)
_ia.close()
s.presets["edits"].pop("normal", None)  # (the tests after this one: Normal as it ships)

from clipse.insert_as_dialog import MarkerNudge  # noqa: E402
_many = [{"kind": "still", "frames": 150, "label": f"logo {n}", "peaks": None, "loudest": None} for n in range(10)]
_nudge = MarkerNudge(s, pm._clean({"where": "markers"}), _many + [dict(_many[0], kind="audio", label="whoosh")], 30)
check("ten pictures and a sound on the marker: the sound has a row too, not just the first six pictures",
      [c["kind"] for c in _nudge.clips].count("audio") == 1 and len(_nudge.clips) == 6 and _nudge.more == 5)

# -- Swap clip: what's under the playhead goes out (shown at the top), the clip highlighted comes in --
placed = run("normal", [photos[0], photos[1], photos[0]], spacing="back_to_back", length=1.0)
spots = sorted((p[2], p[3]) for p in placed if p[0] == "v1")
F.UNDER_PLAYHEAD[0] = next(i for i in F.TRACKS[("video", 1)] if i.a == spots[0][0])
s.display["swap_everywhere"] = False
w.hide()
F.UNDER_PLAYHEAD[0] = None
# -- the drag cursor only where something can be dragged ("it almost always shows a dragging symbol", 2026-10-19) --
from PySide6.QtGui import QMouseEvent as _QMouseEvent  # noqa: E402
from clipse.insert_as_dialog import CurveEditor as _Curve, FramePad as _Pad  # noqa: E402


def _hover(widget, x, y):
    widget.mouseMoveEvent(_QMouseEvent(QEvent.MouseMove, QPointF(x, y), QPointF(x, y), Qt.NoButton, Qt.NoButton,
                                       Qt.NoModifier))
    return widget.cursor().shape()


_cv = _Curve(s, dict(pm.get(s, "normal"), spacing="interval", gap=24, gap_end=3), 6, 30.0)
_cv.resize(520, 196)
_plot = _cv._plot()
_slot = _plot.width() / len(_cv._gaps())
_last_x = _plot.left() + _slot * (len(_cv._gaps()) - 1) + _slot / 2  # (the last, shortest pillar)
check("the gap curve: the drag cursor on a pillar, the arrow in the empty space above it",
      _hover(_cv, _last_x, _plot.bottom() - 2) == Qt.SizeVerCursor and _hover(_cv, _last_x, _plot.top() + 2) == Qt.ArrowCursor)
_fp = _Pad(s, dict(pm.get(s, "normal")), lambda: 1)
_fr = _fp._frame()
check("In the frame: the hand over the frame, the arrow beside it",
      _hover(_fp, _fr.center().x(), _fr.center().y()) == Qt.OpenHandCursor and _hover(_fp, 2, 2) == Qt.ArrowCursor)

# -- a number field keeps every press it gets: one on its edge went through to the picker, which moved the window
#    while the number was dragged ("it starts glitching", 2026-10-19) --
from PySide6.QtCore import QPoint as _QPoint  # noqa: E402
from PySide6.QtTest import QTest as _QTest  # noqa: E402
from PySide6.QtWidgets import QWidget as _QWidget, QVBoxLayout as _QVBox  # noqa: E402
from clipse.drag_spinbox import DragSpinBox as _DragSpinBox  # noqa: E402


class _Behind(_QWidget):
    pressed = 0

    def mousePressEvent(self, event):
        _Behind.pressed += 1


_behind = _Behind()
_field = _DragSpinBox()
_field.setFixedWidth(120)
_QVBox(_behind).addWidget(_field)
_behind.show()
_setup.pump(0.05)
for _pt in (_QPoint(_field.width() // 2, 1), _QPoint(3, _field.height() // 2), _field.lineEdit().geometry().center()):
    _QTest.mousePress(_field, Qt.LeftButton, Qt.NoModifier, _pt)
    _QTest.mouseRelease(_field, Qt.LeftButton, Qt.NoModifier, _pt)
check("a press anywhere on a number field stays with it - never moves the window behind it", _Behind.pressed == 0)

# -- a plain click on a number field: the whole number, ready to be typed over - on the number or anywhere on the box
#    around it, and again after another field was edited (2026-10-21) --
from clipse.drag_spinbox import DragDoubleSpinBox as _DragDouble  # noqa: E402
_two = _QWidget()
_two_v = _QVBox(_two)
_fa, _fb = _DragDouble(), _DragDouble()
for _f in (_fa, _fb):
    _f.setRange(0, 1000)
    _f.setDecimals(1)
    _f.setValue(100)
    _f.setFixedSize(170, 40)  # (tall, as in Insert as: most of it is the box around the number)
    _two_v.addWidget(_f)
_behind.close()  # (left open, it took the keyboard back now and then: the first click went to its field)
_two.show()
_two.activateWindow()
_QTest.qWaitForWindowActive(_two)
_setup.pump(0.1)


def _clicked(field, on_box=None):
    if on_box is None:
        _QTest.mouseClick(field.lineEdit(), Qt.LeftButton, Qt.NoModifier, _QPoint(10, field.lineEdit().height() // 2))
    else:
        _QTest.mouseClick(field, Qt.LeftButton, Qt.NoModifier, on_box)
    _setup.pump(0.05)
    return field.lineEdit().selectedText()


_on_number = _clicked(_fa)
_QTest.keyClicks(_fa.lineEdit(), "50")
_clicked(_fb)
_back = _clicked(_fa)
_fa.clearFocus()
_fb.clearFocus()
_setup.pump(0.05)
_above = _clicked(_fb, _QPoint(40, 1))
_edge = _clicked(_fa, _QPoint(_fa.width() - 3, _fa.height() - 4))
check("a click on a number field chooses the whole number - on the number, above it, at its edge, and back in one "
      "edited a moment ago", _on_number and _back.startswith("50") and _above.startswith("100")
      and _edge.startswith("50"))
check("...and a click at its edge doesn't step the number (its arrows are hidden: 50 became 49)", _fa.value() == 50)
_two.hide()

w.start_swap(); _setup.pump(0.2)
w.search_edit.setText("photo_3"); _setup.pump(0.2)
before = sorted((i.n, i.a) for i in F.TRACKS[("video", 1)])
w.confirm(); _setup.pump(0.1)
check("Swap clip with nothing on the timeline picked yet: it opens and waits - Enter swaps nothing",
      w.swap_strip.isVisible() and w.swap_strip.out_name == "" and w._swap is not None
      and sorted((i.n, i.a) for i in F.TRACKS[("video", 1)]) == before)
F.UNDER_PLAYHEAD[0] = next(i for i in F.TRACKS[("video", 1)] if i.a == spots[1][0])
w._swap_watch()
check("...a clip clicked in Resolve afterwards is the one going out", w.swap_strip.out_name == "photo_2.jpg")
w.swap_strip.pick.emit(); _setup.pump(0.1)
stepped_aside = not w.isVisible() and w._swap is not None
F.UNDER_PLAYHEAD[0] = next(i for i in F.TRACKS[("video", 1)] if i.a == spots[2][0])
w._swap_pick_step(); _setup.pump(0.2)
check("...its target: the picker steps aside (the swap kept) and comes back with the clip clicked - and the "
      "search as it was", stepped_aside and w.isVisible() and w.swap_strip.out_name == "photo_1.jpg"
      and w._swap["spots"][0][2] == spots[2][0] and w.search_edit.text() == "photo_3")
_real_selected = F.TL.GetSelectedClips if hasattr(F.TL, "GetSelectedClips") else None
F.TL.GetSelectedClips = lambda self: list(F.TRACKS[("video", 1)][:2])
w._swap_watch()
before = sorted((i.n, i.a) for i in F.TRACKS[("video", 1)])
w.confirm(); _setup.pump(0.1)
check("...two clips selected on the timeline: the strip says it's one at a time (in red), and Enter swaps nothing",
      w.swap_strip.several == 2 and sorted((i.n, i.a) for i in F.TRACKS[("video", 1)]) == before and w._swap is not None)
if _real_selected:
    F.TL.GetSelectedClips = _real_selected
else:
    del F.TL.GetSelectedClips
F.UNDER_PLAYHEAD[0] = next(i for i in F.TRACKS[("video", 1)] if i.a == spots[1][0])
w.end_swap()
w.start_swap(); _setup.pump(0.2)
check("Swap clip opens the picker with what goes out at the top", w.isVisible() and w.swap_strip.isVisible()
      and w.swap_strip.out_name == "photo_2.jpg" and w.swap_strip.uses == 1)
F.UNDER_PLAYHEAD[0] = next(i for i in F.TRACKS[("video", 1)] if i.a == spots[0][0])
w._swap_watch()
check("...another clip clicked in Resolve is the one going out now - with how often it's on the timeline",
      w.swap_strip.out_name == "photo_1.jpg" and w.swap_strip.uses == 2 and w._swap["spots"][0][2] == spots[0][0])
w.end_swap()
w.search_edit.setText("swap"); _setup.pump(0.2)
row = next(i for i in w.model.visible if w.model.rows[i].name == "Swap clip")
w._select_row(w.model.visible.index(row)); w.confirm(); _setup.pump(0.2)
check("...found by a search: Enter on it is the plain list again, with the swap on",
      w._swap is not None and w.search_edit.text() == "" and w.swap_strip.isVisible())
w.search_edit.setText("photo_3"); _setup.pump(0.2)
check("...what comes in follows the highlighted clip", w.swap_strip.in_name == "photo_3.jpg" and w.swap_strip.in_fits)

w.swap_strip.everywhere = True
w.swap_strip.everywhere_changed.emit(True)
w.confirm(); _setup.pump(0.1)
now = sorted((i.n, i.a, i.b) for i in F.TRACKS[("video", 1)])
check("...Everywhere and Enter: every use of it, same spots, same lengths - the strip gone, the choice remembered",
      now == sorted([("photo_3.jpg", *spots[0]), ("photo_2.jpg", *spots[1]), ("photo_3.jpg", *spots[2])])
      and not w.swap_strip.isVisible() and s.display["swap_everywhere"] is True)
F.UNDER_PLAYHEAD[0] = next(i for i in F.TRACKS[("video", 1)] if i.a == spots[1][0])
w.start_swap(); _setup.pump(0.2)
w.search_edit.setText("whoosh"); _setup.pump(0.2)
check("...a sound for a picture is shown faded, and Enter doesn't swap it",
      not w.swap_strip.in_fits and (w.confirm() or True) and w.swap_strip.isVisible())
w.search_edit.setText("photo_1"); _setup.pump(0.2)
w.confirm(); _setup.pump(0.1)
check("...Here (it's there once): just that one",
      [i.n for i in sorted(F.TRACKS[("video", 1)], key=lambda i: i.a)] == ["photo_3.jpg", "photo_1.jpg", "photo_3.jpg"])
F.UNDER_PLAYHEAD[0] = next(i for i in F.TRACKS[("video", 1)] if i.a == spots[0][0])
w.start_swap(); _setup.pump(0.1)
from PySide6.QtGui import QKeyEvent as _QKeyEvent  # noqa: E402
w.handle_action_key(_QKeyEvent(QEvent.KeyPress, Qt.Key_Escape, Qt.NoModifier))
check("...Esc stops the swap, and the picker stays", not w.swap_strip.isVisible() and w._swap is None and w.isVisible())
F.UNDER_PLAYHEAD[0] = None
s.display["swap_everywhere"] = False
w.show(); w.open_picker(); _setup.pump(0.1)

# -- Not touching: scattered pictures keep room between them, all smaller where there isn't enough --
def _touching(places):
    return sum(abs(a["pan"] - b["pan"]) < (a["box"][0] + b["box"][0]) / 2
               and abs(a["tilt"] - b["tilt"]) < (a["box"][1] + b["box"][1]) / 2
               for i, a in enumerate(places) for b in places[i + 1:])
_sc = pm._clean({"scatter": 100, "scatter_random": 80, "scale": 50, "rotation_vary": 6, "margin": 3})
_loose = _touching(pm.layout(_sc, 20, 1920, 1080, seed=3))
_kept = [pm.layout(dict(_sc, apart=True), n, 1920, 1080, seed=s_) for n in (3, 8, 20, 30) for s_ in (1, 2, 3)]
check("Not touching: twenty big scattered pictures that overlapped don't touch at all - whatever the number or shuffle",
      _loose > 20 and all(_touching(L) == 0 for L in _kept)
      and all(abs(p["pan"]) + p["box"][0] / 2 <= 1920 * 0.47 + 1 for L in _kept for p in L))
check("...and the summary says so", "not touching" in pm.summary(dict(_sc, apart=True)))
# hovering Size in Insert as swings the pictures up to the frame's size: no room up and down but a rounding
# error, and the scatter's grid for that was 70 million columns - the app filled 20 GB and was killed (2026-10-15)
import time  # noqa: E402
_t0 = time.time()
_big = [pm.layout(dict(_sc, scale=v, apart=a), n, 222, 124.875, seed=434665387)
        for v in (97.8, 99.9, 100.0) for n in (2, 5, 9) for a in (False, True)]
check("pictures as big as the frame, scattered: laid out at once, not a grid of millions",
      time.time() - _t0 < 0.5 and all(len(L) in (2, 5, 9) for L in _big))

# -- the tempo: to a twentieth of a BPM, the beat grid held against the whole stretch --
from array import array as _array  # noqa: E402
import math as _math  # noqa: E402
from clipse import bpm as _bpm  # noqa: E402
def _clicks(tempo, seconds=60, rate=11025):
    out = [0.0] * (seconds * rate)
    beat = 60.0 / tempo
    k = 0
    while k * beat < seconds - 0.1:
        start = int(k * beat * rate)
        for i in range(int(0.03 * rate)):
            out[start + i] += _math.sin(2 * _math.pi * (80 if k % 2 == 0 else 400) * i / rate) * _math.exp(-i / (0.01 * rate))
        k += 1
    return _array("h", (int(max(-1, min(1, v)) * 20000) for v in out))
check("the tempo of a 106 BPM beat is 106.0 - not a few tenths off (half a beat late by the end of a song)",
      abs(_bpm.tempo(_clicks(106.0)) - 106.0) <= 0.1)

# -- Swap clip's ⋯: how long, where, which part (rc.swap_plan; timeline frames at 30 fps, the clips 30 fps too) --
_old = {"start": 100, "end": 160, "prev_end": 80, "next_start": 200, "source_start": 90, "rate": 30.0, "loudest": 20}
_new = {"rate": 30.0, "loudest": 50}
def _plan(**opts):
    return rc.swap_plan(dict({"swap_length": "old", "swap_align": "start", "swap_same_part": False}, **opts),
                        _old, _new, 30.0, 300, False, 150)
check("Swap clip as it ships: in the old one's place, as long as it, from the new one's beginning",
      _plan() == (100, 60, 0))
check("...Same end, as long as the old one: the new one's end part fills the place", _plan(swap_align="end") == (100, 60, 240))
check("...loudest moments lined up: the part of it that puts its loudest moment where the old one's was",
      _plan(swap_align="loudest") == (100, 60, 30))
check("...its own length, up to the next clip: cut where that starts", _plan(swap_length="own_stop") == (100, 100, 0))
check("...its own length over the next clip: all of it", _plan(swap_length="own_over") == (100, 300, 0))
check("...its own length, ending where the old one ended - not into the clip before (its beginning goes)",
      _plan(swap_length="own_stop", swap_align="end") == (80, 80, 220))
check("...the same part of the recording: from the moment the old one started at",
      _plan(swap_same_part=True) == (100, 60, 90))

# -- Next / Previous use of clip from the picker: the highlighted clip - or, when that isn't on the timeline, the
# clip under the playhead (it used to crash there: the steps were handed over as words) --
from clipse import timeline_tools as _tt  # noqa: E402
jumped = []
_real_steps = _tt.jump_steps
_tt.jump_steps = lambda timeline, starts, steps, label, fps=None: jumped.append((label, steps, list(starts))) or "x: 1 of 2"
w.show(); w.open_picker(); _setup.pump(0.1)
w.search_edit.setText("whoosh"); _setup.pump(0.2)
F.UNDER_PLAYHEAD[0] = next(i for i in F.TRACKS[("video", 1)] if i.n == "photo_3.jpg")
w._jump_use(1); _setup.pump(0.2)
check("Next use of clip with a clip highlighted that isn't on the timeline: the clip under the playhead's uses",
      jumped and jumped[-1][0] == "photo_3.jpg" and jumped[-1][1] == 1 and len(jumped[-1][2]) == 2)
_tt.jump_steps = _real_steps
F.UNDER_PLAYHEAD[0] = None
w.show(); w.open_picker(); _setup.pump(0.1)

# -- mk: the timeline's markers as rows; Enter puts the playhead there --
w.search_edit.setText("mk:"); _setup.pump(0.2)
marks = [w.model.rows[i] for i in w.model.visible]
check("mk: lists the timeline's markers, in order, each tagged in its own colour",
      [(r.category, r.color, r.path) for r in marks] == [("marker", "Blue", "30"), ("marker", "Red", "90"),
                                                          ("marker", "", "150")])
w.search_edit.setText(""); _setup.pump(0.1)

# -- a bin staged: Insert as knows what's in it --
w.model.clear_staged()
music = next(i for i, r in enumerate(w.model.clip_rows) if r.category == "bin" and r.name.startswith("Music"))
w.model.staged[music] = 1
sample, _fps, _paths = w._preview_sample()
check("a staged bin is its clips in Insert as - the sound and the videos in it",
      [n for _k, _f, n in sample] == ["Upbeat Corporate.wav"] + sorted(n for n in names if n.startswith("B-roll"))
      and sample[0][0] == "audio" and len(sample) > 1)
w._update_staged_summary_text()
check("...and the bottom bar says what's in it, not just \"1 bin\"",
      "Music:" in w.staged_summary_label.text() and "1 audio" in w.staged_summary_label.text()
      and "bin" not in w.staged_summary_label.text())
w.model.clear_staged()

from PySide6.QtGui import QKeyEvent
F.TRACKS.clear()
w.show()
w.search_edit.setText("photo_1")
_setup.pump(0.1)
for _ in range(3):
    w.toggle_staged() if not w.model.staged else w.increment_staged()
w.handle_action_key(QKeyEvent(QEvent.KeyPress, Qt.Key_Return, Qt.NoModifier, "\r"))
w.handle_action_key(QKeyEvent(QEvent.KeyPress, Qt.Key_Return, Qt.NoModifier, "\r", True))  # the repeat, arriving late
_setup.pump(0.3)
landed = sum(len(v) for k, v in F.TRACKS.items() if k[0] == "video")
check("three staged, Enter (and its late repeat): three land, not four", landed == 3 and not w.isVisible())
w.show()
w.handle_action_key(QKeyEvent(QEvent.KeyPress, Qt.Key_Return, Qt.NoModifier, "\r", True))
_setup.pump(0.2)
check("Enter held down doesn't insert over and over either",
      sum(len(v) for k, v in F.TRACKS.items() if k[0] == "video") == 3 and w.isVisible())

print("\nall good" if not fails else f"\n{fails} failed")
raise SystemExit(1 if fails else 0)
