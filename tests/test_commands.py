"""Learning what you pick, the Resolve commands in the > list, the project
check-up and settings / presets as a file - against the fake Resolve.
python3 tests/test_commands.py"""
import json
import os

import time

import _setup
from clipse import checkup, picks, presets as pm, resolve_commands as commands, transfer
from clipse.settings import Settings

w, s, F = _setup.picker()
fails = 0


def check(what, ok):
    global fails
    print(("ok   " if ok else "FAIL ") + what)
    fails += not ok


def shown(text):
    w.search_edit.setText(text)
    _setup.pump(0.05)
    return [w.model.rows[i] for i in w.model.visible]


def log():
    return open(F.LOG).read() if os.path.exists(F.LOG) else ""


# -- learns what you pick --
picks.forget()
first = [r.name for r in shown("b")][:6]
target = next(r for r in shown("b") if r.name == "B-roll 003.mp4")
check("before: B-roll 003 isn't first for 'b'", first[0] != "B-roll 003.mp4")
picks.record("bro", target)
picks.record("bro", target)
check("picked twice for 'bro': first for 'bro'", shown("bro")[0].name == "B-roll 003.mp4")
check("...and for 'b' on the way there", shown("b")[0].name == "B-roll 003.mp4")
check("...and for 'broll' typed further", shown("broll")[0].name == "B-roll 003.mp4")
check("...but an exact name still wins", shown("B-roll 001.mp4")[0].name == "B-roll 001.mp4")
check("...and other searches aren't touched", shown("photo")[0].name.startswith("photo"))
s.general["learn_picks"] = False
check("switched off: the old order", [r.name for r in shown("b")][:6] == first)
s.general["learn_picks"] = True
picks.forget()
check("forgotten: the old order", [r.name for r in shown("b")][:6] == first)
check("forgetting removes its file", not os.path.exists(picks.FILE))

# -- commands in the > list --
everything = [r.name for r in shown(">")]
check("> lists the actions and the openers, not every preset",
      "Render…" in everything and "Grab frame" in everything and not any(n.startswith("Render: ") for n in everything))
# (a plain Add marker was Resolve's own twice over; "Add marker" is now Clipse 25's - a marker and what it's for at
#  once, 2026-10-30)
check("> has only what's smart or saves steps: no listening, clip info, tracks, pages or colours",
      not {"Listening on / off", "Clip info", "Add video track", "Add audio track", "Go to page…",
           "Clip colour…", "Save project", "Settings", "Keyboard shortcuts", "Take the tour"} & set(everything)
      and not any(n.startswith(("Go to ", "Clip colour: ")) for n in [r.name for r in shown("> color")]))
check("> render lists Resolve's presets", [r.name for r in shown("> render")][:3] ==
      ["Render: H.265 Master", "Render: YouTube - 1080p", "Render: YouTube - 2160p"])
check("every action has a symbol", all(r.glyph for r in shown(">") + shown("> render") + shown("> check-up")))


def run(text, label):
    open(F.LOG, "w").close()
    rows = shown(text)
    row = next(r for r in rows if r.name == label)
    w.show()
    w._run_palette_action(row)
    _setup.pump(0.1)
    return w.hints_label.text()


def direct(fn, *args, stay=True):  # (a Resolve command the > list doesn't offer any more - kept, tested)
    open(F.LOG, "w").close()
    w.show()
    w._command(fn, *args, stay=stay)()
    return w.hints_label.text()


from clipse import settings as _settings_module
_old = _settings_module.Settings()
_old.apply({"timeline_tools": {"step_frames": 10}})
check("one step for both (as it was for a day) becomes Step forward and Step back, each 10",
      _old.timeline_tools["step_forward_frames"] == 10 and _old.timeline_tools["step_back_frames"] == 10)
check("step: one row, Settings at Step back / forward - no rows of steps to choose from",
      [r.name for r in shown("step")][:1] == ["Settings: Step back / forward"] and not any(r.name.startswith("Step by") for r in shown("step 10")))

direct(commands.open_page, "color")
check("Go to Color opens the Color page", "PAGE color" in log())
before = F.TL().GetTrackCount("video")
direct(commands.add_track, "video")
check("Add video track adds one", F.TL().GetTrackCount("video") == before + 1)
F.TRACKS.clear(); F.NAMES.clear()
still, video, song, hit = (F.MPI("photo_1.jpg", "s", "Still"), F.MPI("av.mp4", "v", "Video + Audio"),
                           F.MPI("Upbeat Corporate.wav", "m", "Audio"), F.MPI("whoosh.wav", "w", "Audio"))
F.TRACKS.update({("video", 1): [F.Item("av.mp4", 0, 100, video)], ("video", 2): [],
                 ("video", 3): [F.Item("photo_1.jpg", 0, 50, still), F.Item("photo_1.jpg", 60, 90, still)],
                 ("video", 4): [F.Item("Text+", 0, 50)], ("video", 5): [],
                 ("audio", 1): [F.Item("av.mp4", 0, 100, video)], ("audio", 2): [F.Item("Upbeat Corporate.wav", 0, 900, song)],
                 ("audio", 3): [F.Item("whoosh.wav", 0, 9, hit), F.Item("whoosh.wav", 40, 49, hit),
                                F.Item("Upbeat Corporate.wav", 100, 900, song)], ("audio", 4): []})
F.NAMES[("video", 4)] = "My titles"
hint = direct(commands.name_tracks, w._sound_kind)
check("Name the tracks: each after what's on it; yours and empty ones left alone",
      [F.NAMES.get(k) for k in (("video", 1), ("video", 2), ("video", 3), ("video", 4), ("audio", 1), ("audio", 2), ("audio", 3))]
      == ["Video", None, "Pictures", "My titles", "Video sound", "Music", "Sound effects + music"] and hint == "Named 5 tracks")
hint = direct(commands.name_tracks, w._sound_kind)
check("...again: nothing left to name", "Nothing to name" in hint)
hint = run("> tracks", "Remove empty tracks")
check("Remove empty tracks: the three with nothing on them go, the rest stay - and the picker closes, like the rest",
      F.TL().GetTrackCount("video") == 3 and F.TL().GetTrackCount("audio") == 3 and not w.isVisible())
hint = run("> tracks", "Remove empty tracks")
check("...again: says there are none", "No empty tracks" in hint)
F.TRACKS.clear(); F.NAMES.clear()
direct(commands.new_timeline)
check("New timeline makes one with a free name and opens it",
      "NEWTIMELINE Timeline 4" in log() and F.CURRENT[0].GetName() == "Timeline 4")
F.CURRENT[0] = F.TIMELINES[0]
direct(commands.add_marker)
check("Add marker: at the playhead (1 s at 30 fps)", "MARKER 30 Blue" in log())
hint = direct(commands.add_marker)
check("...a second one there says why not", "already" in hint)
hint = direct(commands.save_project)
check("Save project says so (nothing to see in Resolve)", "SAVE" in log() and hint == "Project saved")
hint = direct(commands.color_clip, "Teal")
check("Clip colour with nothing under the playhead says so", "No clip under the playhead" in hint)
F.UNDER_PLAYHEAD[0] = F.Item("clip.mp4", 0, 100)
direct(commands.color_clip, "Teal")
check("Clip colour colours the clip under the playhead", "COLOUR clip.mp4 Teal" in log())
direct(commands.color_clip, None)
check("...and None clears it", "COLOUR clip.mp4 none" in log())

import sys
home = os.environ["HOME"]
renders = os.path.join(home, "Renders")
linux = sys.platform.startswith("linux")
if linux:
    F.RENDER["dir"] = ""
    hint = run("> render", "Render: YouTube - 1080p")
    check("Render with no place chosen: a Renders folder in Resolve's media storage, named after the timeline",
          "RENDER YouTube - 1080p" in log() and F.RENDER["dir"] == renders and F.RENDER["name"] == "Timeline 1"
          and "Rendering" in hint and renders in hint)
    run("> render", "Stop rendering")
    F.RENDER["dir"] = "/somewhere/outside"
    run("> render", "Render: YouTube - 1080p")
    check("...and when the chosen place is outside the media storage", F.RENDER["dir"] == renders and "RENDER" in log())
    run("> render", "Stop rendering")
    open(os.path.join(renders, "Timeline 1.mp4"), "w").close()
    F.RENDER["dir"] = ""
    run("> render", "Render: YouTube - 1080p")
    check("...with a name no file there has yet", F.RENDER["name"] == "Timeline 1 2")
    run("> render", "Stop rendering")
    F.RENDER["dir"], F.RENDER["storage"] = "", []
    hint = run("> render", "Render: YouTube - 1080p")
    check("...no media storage at all: says where to add one", "Media Storage" in hint and "RENDER" not in log())
    F.RENDER["storage"] = [home]
F.RENDER["dir"], F.RENDER["name"] = home, "out"
hint = run("> render", "Render: YouTube - 1080p")
check("Render: a place chosen on the Deliver page is used as it is", "RENDER YouTube - 1080p" in log()
      and F.RENDER["dir"] == home and "Rendering" in hint)
hint = run("> render", "Render: YouTube - 1080p")
check("...not twice at once", "rendering already" in hint)
run("> render", "Stop rendering")
open(os.path.join(home, "out.mp4"), "w").close()
hint = run("> render", "Render: YouTube - 1080p")
check("Render never writes over a file that's there", "already in" in hint and "RENDER" not in log())
# -- render just the clip under the playhead --
os.remove(os.path.join(home, "out.mp4"))
F.RENDER["jobs"].clear()
F.UNDER_PLAYHEAD[0] = F.Item("interview take 2.mp4", 300, 900)
F.CURRENT[0].SetMarkInOut(50, 2000)  # marks of your own on the timeline
hint = run("> render", "Render this clip: YouTube - 1080p")
job = F.RENDER["jobs"][-1]
check("Render this clip: only the clip under the playhead goes into the job", (job["MarkIn"], job["MarkOut"]) == (300, 899)
      and "RENDER YouTube - 1080p" in log() and len(F.RENDER["jobs"]) == 1)
check("...under a name of its own, next to the timeline's renders",
      job["OutputFilename"] == "Timeline 1 - interview take 2.mp4" and job["TargetDir"] == home and "interview take 2" in hint)
check("...your own in / out marks are back afterwards", F.CURRENT[0].GetMarkInOut()["video"] == {"in": 50, "out": 2000})
check("...and the timeline's next render keeps its usual name", F.RENDER["name"] == "out")
run("> render", "Stop rendering")
F.CURRENT[0].ClearMarkInOut()
F.UNDER_PLAYHEAD[0] = None
F.RENDER["jobs"].clear()
hint = run("> render", "Render this clip: YouTube - 1080p")
check("...with the playhead on no clip: says so, renders nothing", "isn't over a clip" in hint and not F.RENDER["jobs"]
      and "RENDER" not in log())
F.UNDER_PLAYHEAD[0] = F.Item("clip.mp4", 0, 100)
check("typing 'youtube' in a normal search offers the render", any(r.name.startswith("Render: YouTube")
                                                                   for r in shown("youtube")))
check("typing a colour in a normal search doesn't offer clip colours",
      not any(r.category == "action" for r in shown("teal")))

# -- project check-up --
rows = w.model.clip_rows
names = [r.name for r in rows]
check("every clip row knows its file", rows[names.index("av.mp4")].source.endswith("av.mp4"))
there = os.path.join(os.environ["HOME"], "here.wav")
open(there, "wb").write(b"a" * 3000)
copy_of = os.path.join(os.environ["HOME"], "copy.wav")
open(copy_of, "wb").write(b"a" * 3000)
other = os.path.join(os.environ["HOME"], "other.wav")
open(other, "wb").write(b"b" * 3000)
for name, path in (("whoosh.wav", there), ("SFX_034.wav", copy_of), ("untitled_01.wav", other),
                   ("av.mp4", "/nowhere/av.mp4"), ("recording_02.wav", "/nowhere/take.[0001-0100].png")):
    rows[names.index(name)].source = path
rows[names.index("whoosh.wav")].analysis = {"peak": 0.0, "clips": 340}   # tops cut flat
rows[names.index("SFX_034.wav")].analysis = {"peak": 0.0, "clips": 0}    # as loud as a file goes, but whole
w._checkup_cache.clear()
found = {rows[i].name: why for i, why in checkup.missing(rows)}
check("missing: the clip whose file is gone, with where it was", found.get("av.mp4") == "not found: /nowhere/av.mp4")
check("missing: files that are there aren't listed", "whoosh.wav" not in found and "untitled_01.wav" not in found)
check("missing: an image sequence is judged by its folder", "recording_02.wav" in found)
dupes = {rows[i].name: why for i, why in checkup.duplicates(rows, w.session["filtered_group_list"])}
check("duplicates: two clips that are copies of one file",
      dupes.get("whoosh.wav") == "a copy of SFX_034.wav" and dupes.get("SFX_034.wav") == "a copy of whoosh.wav")
check("duplicates: same size, different content isn't one", "untitled_01.wav" not in dupes)
check("clipping: flattened tops count, loud alone doesn't", [rows[i].name for i, _w in checkup.clipping(rows)] == ["whoosh.wav"])
check("missing: lists them in the picker", "av.mp4" in [r.name for r in shown("missing:")])
check("dup: lists them", {"whoosh.wav", "SFX_034.wav"} <= {r.name for r in shown("dup:")})
check("clipping: lists them", [r.name for r in shown("clipping:")] == ["whoosh.wav"])
summary = {r.name: r.folder_list for r in shown("> check-up")}
check("> check-up: four rows with what was found",
      list(summary) == ["Missing files", "Duplicates", "Unused clips", "Clipping sounds"]
      and summary["Missing files"].startswith(f"{len(checkup.missing(rows))} clips whose") and summary["Clipping sounds"].startswith("1 clip "))
w.search_edit.setText("> check-up")
_setup.pump(0.05)
w.show()
w._run_palette_action(next(r for r in shown("> check-up") if r.name == "Missing files"))
_setup.pump(0.1)
check("Enter on Missing files opens that list", w.search_edit.text() == "missing: ")

# -- the app's own bins are named like_this --
from clipse import stills
pool = F.Pool()
def top(name):
    return next((f for f in F.ROOT.subs if f.GetName() == name), None)
made = stills.app_bin(pool, stills.GRABS_BIN)
check("a bin the app makes is named frame_grabs - inside the clipse bin, not at the top",
      made.GetName() == "frame_grabs" and top("clipse") and made in top("clipse").subs and made not in F.ROOT.subs)
check("...and found again, not made twice", stills.app_bin(pool, stills.GRABS_BIN) is made
      and [f.GetName() for f in top("clipse").subs].count("frame_grabs") == 1)
F.ROOT.subs[:] = [f for f in F.ROOT.subs if f.GetName() != "clipse"]
old_top = F.Folder("frame_grabs", [F.MPI("old_grab.png", "og0", "Still")])
old_compounds = F.Folder("compound_clips", [])
old_home = F.Folder("Clipse", [F.MPI("Adjustment Clip", "adj0", "Generator")])
F.ROOT.subs += [old_top, old_compounds, old_home]
made = stills.app_bin(pool, stills.CLIPSE_BIN)
check("what earlier versions made moves in, all at once: frame_grabs and compound_clips from the top as they are, "
      "Clipse's clips into clipse", made is top("clipse") and old_top in made.subs and old_compounds in made.subs
      and top("Clipse") is None and top("frame_grabs") is None and top("compound_clips") is None
      and "Adjustment Clip" in [c.GetName() for c in made.GetClipList()])
check("...and frame_grabs is found there", stills.app_bin(pool, stills.GRABS_BIN) is old_top)
from clipse import timeline_tools as tt
clip, _problem = tt.lookup_adjustment_clip(s, pool)
check("...and the app's own adjustment clip there by its old name is used, renamed adjustment_clip",
      clip is not None and clip.GetName() == "adjustment_clip" and clip in top("clipse").GetClipList())
from clipse.settings import Settings as _S
_old = _S()
_old.apply({"timeline_tools": {"adj_clip_name": "Adjustment Clip", "comp_clip_name": "my comp"}})
check("a settings file with the old names: the new ones - a name of your own stays",
      _old.timeline_tools["adj_clip_name"] == "adjustment_clip" and _old.timeline_tools["comp_clip_name"] == "my comp")
F.ROOT.subs[:] = [f for f in F.ROOT.subs if f.GetName() != "clipse"]
old_grab = F.MPI("grab_001.png", "og", "Compound")
F.ROOT.subs.append(F.Folder("grouped_stills", [old_grab]))
moved_to = stills.app_bin(pool, stills.COMPOUND_BIN)
check("a bin with the earlier name is moved over: its clips into compound_clips, the old one gone",
      moved_to.GetName() == "compound_clips" and old_grab in moved_to.GetClipList()
      and "grouped_stills" not in [f.GetName() for f in F.ROOT.subs])

# -- pictures all come in the same length --
from clipse import resolve_client as rc
photo = F.MPI("photo_1.jpg", "x1", "Still")
s.presets["still_length"] = 5.0
check("a picture lasts what Insert as says - in the timeline's frames", rc.compute_clip_duration(s, photo, "photo_1.jpg", 30.0) == 150
      and rc.compute_clip_duration(s, photo, "photo_1.jpg", 60.0) == 300)
broken = Settings()
broken.apply({"presets": {"still_length": 0.0, "still_seconds": 12.5}})
check("a length that makes no sense goes back to 5 s - and the old guess at Resolve's own is left behind",
      broken.presets["still_length"] == 5.0 and "still_seconds" not in broken.presets)

# -- the preview: scrub only on the picture, Space plays --
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QImage, QKeyEvent
from clipse.picker_window import PreviewCanvas
canvas = PreviewCanvas(s)
canvas.resize(460, 420)
canvas.image, canvas.duration = QImage(320, 90, QImage.Format_RGB888), 10.0   # a wide clip: space above and below
canvas.show(); _setup.pump(0.05); canvas.grab()
scrubs = []
canvas.scrub_to.connect(scrubs.append)
area, picture = canvas.image_area(), canvas._picture
canvas._hover_scrub(QPointF(area.center().x(), area.top() + 12))
check("hover scrub: not in the empty space above the picture", scrubs == [] and canvas.scrub_x is None)
canvas._hover_scrub(QPointF(picture.left() + picture.width() * 0.5, picture.center().y()))
check("hover scrub: on the picture, halfway across is halfway through", len(scrubs) == 1 and abs(scrubs[0] - 5.0) < 0.2)
canvas._hover_scrub(QPointF(area.center().x(), area.bottom() - 12))
check("hover scrub: moving off the picture into the space below ends it", canvas.scrub_x is None)
canvas.hide()

def key(k, text="", mods=Qt.NoModifier):
    return w.handle_action_key(QKeyEvent(QEvent.KeyPress, k, mods, text))


def typed(word):
    for ch in word:
        key(getattr(Qt, "Key_" + ch.upper()), ch)
    w.search_edit.setText(word)


played = []
w.space_play = lambda held=False: played.append("held" if held else 1)
w.show(); w.open_picker(); _setup.pump(0.2); w.search_edit.setText(""); w.preview_panel.hide()
check("the picker opens in the search", not w._in_list and "Space" not in w.hints_label.text())
check("Space with nothing typed plays (a space can't be meant)", key(Qt.Key_Space, " ") and played == [1])
w._set_in_list(False)
typed("dark")
check("in the search, Space is a space: two-word searches work", not key(Qt.Key_Space, " ") and played == [1])
w.search_edit.setText("dark ")
check("...however often", not key(Qt.Key_Space, " ") and played == [1])
typed("animation")
key(Qt.Key_Down)
check("arrow down: you're in the list - the bar doesn't say what Space does (it's plain)",
      w._in_list and "Space" not in w.hints_label.text())
check("...Space plays that one", key(Qt.Key_Space, " ") and played == [1, 1])
check("...and again", key(Qt.Key_Space, " ") and played == [1, 1, 1])
typed("s")
check("a letter takes you back to searching, no click needed", not w._in_list and not key(Qt.Key_Space, " "))
w.list_view.clicked.emit(w.model.index(0, 0))
check("a click on a row is the list too", w._in_list and key(Qt.Key_Space, " "))
from PySide6.QtGui import QMouseEvent
from PySide6.QtCore import QPointF as _P
click = QMouseEvent(QEvent.MouseButtonPress, _P(5, 5), _P(5, 5), Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
w.search_edit.mousePressEvent(click)
check("a click in the search is the search again", not w._in_list and not key(Qt.Key_Space, " "))
key(Qt.Key_Down); key(Qt.Key_Backspace)
check("Backspace too", not w._in_list)
w.preview_panel.show(); w.preview_panel.setAttribute(Qt.WA_UnderMouse, True)
n = len(played)
check("the mouse on the preview: Space plays even in the search", key(Qt.Key_Space, " ") and len(played) == n + 1)
w.preview_panel.setAttribute(Qt.WA_UnderMouse, False); w.preview_panel.hide()
w._set_in_list(False)
s.listen["space_plays"] = "always"
typed("dark"); n = len(played)
check("set to Always: plays in the search too", key(Qt.Key_Space, " ") and len(played) == n + 1)
check("...and Shift+Space still writes a space", not key(Qt.Key_Space, " ", Qt.ShiftModifier) and len(played) == n + 1)
s.listen["space_plays"] = "never"
key(Qt.Key_Down)
check("set to Never: Space is only ever a space, in the list as well", not key(Qt.Key_Space, " ") and len(played) == n + 1)
s.listen["space_plays"] = "smart"
held = QKeyEvent(QEvent.KeyPress, Qt.Key_Space, Qt.NoModifier, " ", True)
w.handle_action_key(held)
check("Space held down is passed on as held", played[-1] == "held")
del w.space_play

# the arrows to the sides: the text cursor in the search, a second through the sound in the list
moved = []
class FakeSound:
    playing = True
    def seek_relative(self, seconds): moved.append(seconds)
real_sound, w.sound = w.sound, FakeSound()
typed("whoosh")
check("in the search, Left moves the text cursor", not key(Qt.Key_Left) and moved == [])
key(Qt.Key_Down)
check("in the list, Left / Right move a second through what's playing",
      key(Qt.Key_Left) and key(Qt.Key_Right) and moved == [-1, 1])
check("...Ctrl with them, five", key(Qt.Key_Left, "", Qt.ControlModifier) and key(Qt.Key_Right, "", Qt.ControlModifier)
      and moved == [-1, 1, -5, 5])
FakeSound.playing = False
check("...with nothing playing they're left alone", not key(Qt.Key_Right) and len(moved) == 4)
w.sound = real_sound

# holding Space on a short sound fires it over and over; a long one isn't toggled
did = []
w.replay, w.play_pause = (lambda: did.append("replay")), (lambda: did.append("pause"))
audio_rows = {r.name: r for r in w.model.clip_rows if r.category == "audio"}
def space_on(name, secs):
    audio_rows[name].secs = secs
    w.search_edit.setText(name); _setup.pump(0.05)
    did.clear(); w.space_play()
    return did
check("Space on a 2 s sound effect starts it over", space_on("whoosh.wav", 2.0) == ["replay"])
check("Space on a 60 s song pauses / resumes", space_on("Upbeat Corporate.wav", 60.0) == ["pause"])
check("...a sound whose length isn't known counts as an effect", space_on("whoosh.wav", 0.0) == ["replay"])
s.listen["space_replay_under"] = 90
check("the limit is yours to set (90 s: the song starts over too)", space_on("Upbeat Corporate.wav", 60.0) == ["replay"])
s.listen["space_replay_under"] = 30
s.listen["space_action"] = "pause"
check("set to Play / pause: the effect pauses too", space_on("whoosh.wav", 2.0) == ["pause"])
s.listen["space_action"] = "replay"
check("set to Start over: the song starts over too", space_on("Upbeat Corporate.wav", 60.0) == ["replay"])
s.listen["space_action"] = "auto"
audio_rows["whoosh.wav"].secs = 2.0
w.search_edit.setText("whoosh.wav"); _setup.pump(0.05)
did.clear(); w._last_replay = 0.0
w.space_play(); w.space_play(held=True)
check("Space held on a short sound: not faster than it can be heard", did == ["replay"])
_time_mod = __import__("time"); _time_mod.sleep(w.HELD_EVERY + 0.02)
w.space_play(held=True)
check("...but again and again", did == ["replay", "replay"])
audio_rows["Upbeat Corporate.wav"].secs = 60.0
w.search_edit.setText("Upbeat Corporate.wav"); _setup.pump(0.05)
did.clear(); w.space_play(held=True)
check("Space held on a song doesn't flicker it on and off", did == [])
del w.replay, w.play_pause
w.search_edit.setText("")

# -- a problem report, and a service that has stopped answering --
import zipfile
from clipse import client, report, paths
os.makedirs(paths.LOG_DIR, exist_ok=True)
open(paths.log("service.log"), "w").write("the log\n")
open(paths.log("service.previous.log"), "w", newline="\n").write("the run before\n")  # (Windows: no \r)
s.save()
made = report.make(os.environ["HOME"])
inside = zipfile.ZipFile(made)
check("report: one zip with the logs, the settings and what it ran on",
      {"about.txt", "service.log", "service.previous.log", "settings.json"} <= set(inside.namelist())
      and "Clipse" in inside.read("about.txt").decode() and inside.read("service.previous.log") == b"the run before\n")
from clipse import feedback
boundary_type, body = feedback._multipart([("kind", "idea"), ("text", "æ")], [("image", "a.png", "image/png", b"\x89PNG")])
check("feedback: a form with its words (any letters) and its pictures, as the site reads it",
      boundary_type.startswith("multipart/form-data; boundary=") and "æ".encode() in body
      and b'filename="a.png"\r\nContent-Type: image/png\r\n\r\n\x89PNG\r\n' in body
      and body.endswith(f"--{boundary_type.split('=')[1]}--\r\n".encode()))
saved = zipfile.ZipFile(feedback.save("problem", "it broke", "a@b.c", [("image/png", b"png")], logs=True))
check("feedback saved as a file when it can't be sent: the words, the pictures, the logs",
      {"feedback.txt", "picture-1.png", "service.log", "about.txt"} <= set(saved.namelist())
      and "it broke" in saved.read("feedback.txt").decode())

check("client: a process that isn't the service is never taken for it", not client._is_daemon(os.getpid()))

# -- themes --
from clipse.settings import THEME_PRESETS, GRAPHITE_BEFORE
picked = Settings()
picked.apply_theme_preset("Graphite")
again = Settings()
again.apply(json.loads(json.dumps(picked.as_dict())))
check("Graphite lasts past a restart (the colours of 1.6 were Graphite's, and were taken for never changed)",
      again.theme["picker_bg"] == THEME_PRESETS["Graphite"]["picker_bg"] == "#242529")
before = Settings()
before.apply({"theme": dict(GRAPHITE_BEFORE)})
check("...and who had the darker Graphite of before gets the lighter one", before.theme["picker_bg"] == "#242529")
light = Settings()
light.apply_theme_preset("Light")
dark_again = Settings()
dark_again.theme.update(light.theme)
dark_again.apply_theme_preset("Graphite")
check("a light theme brings clip colours that read on white - and a dark one after it the dark ones",
      light.theme["picker_bg"] == THEME_PRESETS["Light"]["picker_bg"] and light.theme["color_audio"] == THEME_PRESETS["Light"]["color_audio"]
      and dark_again.theme["color_audio"] == THEME_PRESETS["Default"]["color_audio"])
check("only themes people pick: two light ones, no orange", {"Light", "Soft light"} <= set(THEME_PRESETS)
      and not {"Gruvbox", "Monokai", "Dracula"} & set(THEME_PRESETS))

# -- settings and presets as a file --
s.listen["volume"] = 37
s.keybinds["preview"] = "Ctrl+Shift+P"
s.display["picker_pos"] = [11, 22]
s.folders["macros"] = ["/my/macros"]
own = pm.duplicate(s, dict(pm.get(s, "normal"), spacing="back_to_back", name="Back to back"))
pm.save(s, {**pm.get(s, "normal"), "gap": 7})
settings_file, presets_file = os.path.join(home, "s.json"), os.path.join(home, "p.json")
from clipse import picks as _picks, project_templates as _pt  # noqa: E402
_kept = (rc.load_favorites(), rc.load_insert_frequency(), open(_picks.FILE).read() if os.path.exists(_picks.FILE) else None)
rc.save_favorites({"whoosh.wav", "act:Grab frame"})
os.makedirs(_pt.TEMPLATES_DIR, exist_ok=True)
json.dump({"name": "Vlog", "bins": [["01_footage", []]]}, open(os.path.join(_pt.TEMPLATES_DIR, "Vlog.json"), "w"))
json.dump({"hit": {"audio|hit.wav": [4, 20000]}}, open(_picks.FILE, "w"))
json.dump({"hit.wav": 9}, open(rc.INSERT_FREQUENCY_FILE, "w"))
transfer.export_settings(s, settings_file)
_setup_file = json.load(open(settings_file))
check("your setup: favourites, project templates and what it learned go in the file too",
      _setup_file["favourites"] == ["act:Grab frame", "whoosh.wav"] and [t["name"] for t in _setup_file["templates"]] == ["Vlog"]
      and _setup_file["picks"]["hit"]["audio|hit.wav"] == [4, 20000] and _setup_file["inserted"] == {"hit.wav": 9})
# (another computer: a favourite of its own, no template, a pick it made more often)
rc.save_favorites({"doom.wav"})
os.remove(os.path.join(_pt.TEMPLATES_DIR, "Vlog.json"))
json.dump({"hit": {"audio|hit.wav": [7, 19000]}}, open(_picks.FILE, "w"))
json.dump({}, open(rc.INSERT_FREQUENCY_FILE, "w"))
_said = transfer.import_settings(Settings(), settings_file)
check("...loaded, they're added to what's there - nothing of it goes, the higher count stays",
      rc.load_favorites() == {"doom.wav", "whoosh.wav", "act:Grab frame"} and "Vlog" in _pt.saved_templates()
      and json.load(open(_picks.FILE))["hit"]["audio|hit.wav"] == [7, 20000] and rc.load_insert_frequency() == {"hit.wav": 9}
      and "2 favourites" in _said and "1 project template" in _said and "what it learned" in _said)
check("...and a file of presets only is told apart (it adds presets)", transfer.kind_of(settings_file) == "settings")
rc.save_favorites(_kept[0]); json.dump(_kept[1], open(rc.INSERT_FREQUENCY_FILE, "w"))
if _kept[2] is None:
    os.remove(_picks.FILE)
else:
    open(_picks.FILE, "w").write(_kept[2])
os.remove(os.path.join(_pt.TEMPLATES_DIR, "Vlog.json"))
_picks._data = None
transfer.export_settings(s, settings_file)
exported = json.load(open(settings_file))
check("settings file: no window position, folders or script paths in it",
      "picker_pos" not in exported["settings"]["display"] and "folders" not in exported["settings"]
      and "script_keys" not in exported["settings"]["general"])
check("presets file: your own and your changes", transfer.export_presets(s, presets_file) == 2)

other_pc = Settings()
other_pc.display["picker_pos"] = [500, 600]
other_pc.folders["macros"] = ["/their/macros"]
other_pc.listen["hover_scrub"] = not s.listen["hover_scrub"]
kept_dict = other_pc.listen
message = transfer.import_settings(other_pc, settings_file)
check("import settings: values come over", other_pc.listen["volume"] == 37
      and other_pc.keybinds["preview"] == "Ctrl+Shift+P" and other_pc.listen["hover_scrub"] == s.listen["hover_scrub"])
check("...presets too - your own; a change to a built-in one is for the insert at hand, never written down",
      [p["name"] for p in other_pc.presets["user"]] == [own["name"]]
      and pm.get(other_pc, "normal")["gap"] == pm.get(Settings(), "normal")["gap"] != 7)
check("...this computer's window position and folders stay", other_pc.display["picker_pos"] == [500, 600]
      and other_pc.folders["macros"] == ["/their/macros"])
check("...in place (the app keeps its dictionaries)", other_pc.listen is kept_dict and "in use now" in message)

viewer = Settings()
pm.duplicate(viewer, dict(pm.get(viewer, "normal"), spacing="back_to_back", name="Back to back"))  # they have one of the same name already
message = transfer.import_presets(viewer, presets_file)
names_now = [p["name"] for p in viewer.presets["user"]]
check("import presets: added next to theirs, renamed on a clash",
      len(names_now) == 2 and names_now[1] == own["name"] + " 2" and "1 preset added" in message)
check("...and a built-in they haven't changed takes the change", pm.get(viewer, "normal")["gap"] == 7)
check("...twice adds again but never removes", "added" in transfer.import_presets(viewer, presets_file)
      and len(viewer.presets["user"]) == 3)
for wrong, kind, fn in ((presets_file, "settings", transfer.import_settings), (settings_file, "presets", transfer.import_presets),
                        (F.LOG, "junk", transfer.import_settings)):
    try:
        fn(Settings(), wrong)
        check(f"a {kind} file in the wrong place is refused", False)
    except transfer.NotOurs as e:
        check(f"the wrong kind of file is refused with a reason ({e})", True)

# -- the Search shortcut: open, close, open again straight away --
from clipse import daemon
w.hide()
_setup.pump(0.05)
check("the shortcut opens the picker", daemon.open_from_shortcut(w, False) and w.isVisible())
w.search_edit.setText("bro")
check("a double press while it's open is dropped (what you typed stays)",
      not daemon.open_from_shortcut(w, False) and w.search_edit.text() == "bro")
w.hide()
check("closed and pressed again at once: it opens, no waiting",
      daemon.open_from_shortcut(w, False) and w.isVisible())
check("a rescan asked for (Ctrl+R) always goes through", daemon.open_from_shortcut(w, True))

# -- every open looks at the Media Pool again: a quick look (only new, renamed or moved clips asked about) --
import DaVinciResolveScript as _F  # noqa: E402
_root = _F.ROOT
_full = rc.MediaPoolScan(_root); _full.step(None)
_asked = []
_real_prop = _F.MPI.GetClipProperty
_F.MPI.GetClipProperty = lambda self, k=None: (_asked.append(self.n), _real_prop(self, k))[1]
_known = {e[0]: e for e in _full.entries}
_gone = _full.entries[0]
del _known[_gone[0]]
_quick = rc.MediaPoolScan(_root, True, _known); _quick.step(None)
_F.MPI.GetClipProperty = _real_prop
check("the quick look every open: what it knew it keeps, only a clip it didn't know is asked about in full",
      _quick.entries == _full.entries and _asked == [_gone[1]])

# -- the row under the mouse lights up, but only once the mouse has moved --
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
w.search_edit.setText("b")
_setup.pump(0.05)
view = w.list_view
check("a list that just appeared has no row lit up", w.delegate.hover_row is None)
QTest.mouseMove(view.viewport(), view.visualRect(w.model.index(2, 0)).center())
_setup.pump(0.05)
check("the mouse moved onto the third row: that one", w.delegate.hover_row == 2)
w.search_edit.setText("br")
_setup.pump(0.05)
check("the list changed under a resting mouse: nothing lit up again", w.delegate.hover_row is None)
check("the bottom bar doesn't say Enter inserts or Tab stages - only an Insert as that isn't Normal",
      w.hints_label.hints == [])
from clipse import presets as _presets  # noqa: E402
_was = s.presets.get("active")
s.presets["user"].append({"id": "own_hint_test", "name": "Spread out"})
s.presets["active"] = "own_hint_test"
w.hints_label.set_hints(w._footer_hints())
check("...said when one is in use", w.hints_label.hints and w.hints_label.hints[0][1:] == ("Insert", "as Spread out"))
s.presets["user"].pop()
s.presets["active"] = _was
w.hints_label.set_hints(w._footer_hints())
w.hints_label.set_hints([("Tab", "Stage", "")])  # (a key, to see a message take its place)
w._flash_hint("Nothing highlighted to insert.", 50)
check("a message takes their place for a moment", w.hints_label.text() == "Nothing highlighted to insert."
      and not w.hints_label.hints)
_setup.pump(0.2)
check("...then what was there is back", w.hints_label.hints == w._footer_hints())

# -- adjustment clips with nothing to set up --
from clipse import timeline_tools as tt
pool = F.Pool()
check("the adjustment clip's bin file comes with the app", os.path.getsize(tt.ADJUSTMENT_CLIP_FILE) > 1000)
clip, problem = tt.lookup_adjustment_clip(s, pool)
check("a project without an adjustment clip gets one, in a bin of its own, called adjustment_clip",
      clip is not None and clip.GetClipProperty("Type") == "Generator" and problem is None
      and clip.GetName() == "adjustment_clip" and "clipse" in [f.GetName() for f in F.ROOT.GetSubFolderList()])
bins = len(F.ROOT.GetSubFolderList())
clip, problem = tt.lookup_adjustment_clip(s, pool)
check("...once: the next time that one is used", clip is not None and len(F.ROOT.GetSubFolderList()) == bins)
s.timeline_tools["adj_clip_name"] = "my look"
clip, problem = tt.lookup_adjustment_clip(s, pool)
check("a clip of your own by name that isn't there: told so, nothing brought in instead",
      clip is None and "my look" in problem and len(F.ROOT.GetSubFolderList()) == bins)
s.timeline_tools["adj_clip_name"] = "adjustment_clip"
F.ROOT.subs[:] = [f for f in F.ROOT.subs if f.GetName() != "clipse"]
os.environ["FAKE_OLD_RESOLVE"] = "1"
clip, problem = tt.lookup_adjustment_clip(s, pool)
del os.environ["FAKE_OLD_RESOLVE"]
check("a Resolve that won't read the file: the old message, how to add one by hand",
      clip is None and "add an adjustment clip" in problem)

# -- subtitles from speech, and Fusion animations without keyframes --
def listed(text):
    w.search_edit.setText(text)
    _setup.pump(0.05)
    return [w.model.rows[i] for i in w.model.visible]


# -- with nothing typed: most used, recently added or recently used (Settings > General) --
check("Resolve's Date Added is read (\"Tue Oct 20 2026 13:36:41\"), nothing to go by is 0",
      rc._added({"Date Added": "Tue Oct 20 2026 13:36:41"}) == time.mktime((2026, 10, 20, 13, 36, 41, 0, 0, -1))
      and rc._added({"Date Added": ""}) == 0.0 and rc._added({}) == 0.0)
check("...and it reaches the rows from a scan",
      all(r.added > 0 for r in w.model.clip_rows if r.category in ("video", "audio", "image")))
_clips = [r for r in w.model.clip_rows if r.category in ("video", "audio", "image")]
_saved_added = [r.added for r in _clips]
for _n, _r in enumerate(_clips):
    _r.added = 1000.0 + _n  # the last one came in last
s.general["empty_order"] = "added"
_order = [r for r in listed("") if r in _clips]
check("Recently added: the clip that came into the Media Pool last comes first",
      [r.name for r in _order[:3]] == [r.name for r in reversed(_clips)][:3])
_v = [r for r in listed("v: ") if r.category == "video"]
check("...in a kind's own list (v:) too", [r.added for r in _v] == sorted((r.added for r in _v), reverse=True))
for _r, _a in zip(_clips, _saved_added):
    _r.added = _a
s.general["empty_order"] = "recent"
rc.record_recent(_clips[4].name)
rc.record_recent(_clips[2].name)  # (the newest)
_first = [r.name for r in listed("") if r in _clips][:2]
check("Recently used: what was inserted last comes first", _first == [_clips[2].name, _clips[4].name])
s.general["empty_order"] = "used"
listed("")


def do(text, label):
    open(F.LOG, "w").close()
    row = next(r for r in listed(text) if r.name == label)
    w.show()
    w._run_palette_action(row)
    _setup.pump(0.1)
    return w.hints_label.text()


direct(commands.subtitles_from_speech, s.timeline_tools, stay=False)
check("Subtitles from speech: Resolve is asked once, the picker gets out of the way",
      open(F.LOG).read().count("SUBTITLES") == 1 and not w.isVisible())
check("...with the usual choices: language worked out, one line of up to 42 characters, no gap",
      "SUBTITLES chars=42 gap=0 language=auto lines=one preset=normal" in open(F.LOG).read())
s.timeline_tools.update(subtitle_language="danish", subtitle_chars=20, subtitle_lines="double", subtitle_gap=2,
                        subtitle_preset="netflix")
direct(commands.subtitles_from_speech, s.timeline_tools, stay=False)
check("...and with your own from Settings > Timeline > Subtitles",
      "SUBTITLES chars=20 gap=2 language=da lines=two preset=netflix" in open(F.LOG).read())
s.timeline_tools.update(subtitle_language="klingon", subtitle_chars=900)
direct(commands.subtitles_from_speech, s.timeline_tools, stay=False)
check("...a language this Resolve doesn't know is left to Resolve; numbers stay in what it accepts",
      "SUBTITLES chars=60 gap=2 lines=two preset=netflix" in open(F.LOG).read())
s.timeline_tools.update(subtitle_language="auto", subtitle_chars=42, subtitle_lines="single", subtitle_gap=0,
                        subtitle_preset="default")
# -- shortcuts: rows that take you somewhere in Clipse itself --
from clipse.settings_dialog import SettingsDialog
go = listed("go: ")
check("go: lists the shortcuts - what's in the bottom bar, every page of Settings and Step back / forward - as their own kind of row",
      {r.category for r in go} == {"shortcut"}
      and [r.name for r in go][:5] == ["Actions", "Insert as", "Expressions", "History", "Settings"]
      and [r.name for r in go][5:] == [f"Settings: {title}" for title, _i, _b in SettingsDialog.PAGES]
      + ["Settings: Step back / forward"])
check("Keyboard shortcuts is gone: no row, no key, no sheet - Settings: Keybindings is where keys are",
      not any(r.name == "Keyboard shortcuts" for r in listed("keyboard cu"))
      and "Settings: Keybindings" in [r.name for r in listed("keyboard cu")] and "show_shortcuts" not in s.keybinds
      and not hasattr(w, "sheet"))
check("a page of Settings is found by what's on it, with nothing but the word typed: theme, hotkeys",
      "Settings: Appearance" in [r.name for r in listed("theme") if r.category == "shortcut"]
      and "Settings: Keybindings" in [r.name for r in listed("hotkeys") if r.category == "shortcut"]
      and not any(r.name == "Settings: Statistics" for r in listed("go: ")))  # (Statistics is gone)
check("...and nothing is listed twice: Settings and History are shortcuts, not actions as well",
      [(r.name, r.category) for r in listed("settings") if r.name == "Settings"] == [("Settings", "shortcut")]
      and not any(r.category == "action" for r in listed("history"))
      and not any(r.name.startswith("Settings:") for r in listed("> settings")))
opened = []
real_open, w.open_settings = w.open_settings, lambda page=None: opened.append(page)
w._open_shortcut(next(r for r in listed("go: appearance") if r.name == "Settings: Appearance"))
_setup.pump(0.05)
check("Enter on one opens it: the Appearance page of Settings", opened == ["Appearance"])
w.open_settings = real_open
w.show()
w._open_shortcut(next(r for r in listed("go: cheat")))
_setup.pump(0.05)
check("...and the cheat sheet", w.expression_sheet.isVisible())
w.expression_sheet.close_sheet()
s.page_defaults["other"]["shortcuts"] = False
check("with the Shortcuts tile off for the page they stay out of the list (go: still reaches them)",
      not any(r.category == "shortcut" for r in listed("theme")) and len(listed("go: theme")) >= 1)
s.page_defaults["other"]["shortcuts"] = True
check("a theme is changed in one place - Settings: Appearance - and isn't an action as well",
      [(r.name, r.category) for r in listed("theme")] == [("Settings: Appearance", "shortcut")]
      and not any("theme" in r.name.lower() for r in listed("> theme")))
check("a shortcut's row is its name and nothing after it", all(not r.folder_list for r in listed("go: ")))
from clipse.settings import V141_THEME_DEFAULTS
check("the Selected Clips row is golden - and settings saved while it was pink move on to it",
      Settings().theme["color_selected"] == "#e5c07b" and V141_THEME_DEFAULTS == {"color_selected": "#ff7eb6"})
from clipse import report
check("Send feedback (Settings > About) isn't an action", not listed("> idea"))
check("Node off / on is keyed in Resolve only (its script) - no picker key",
      "node_on_off" not in s.keybinds and ("Fusion", "Node off / on", "") in [(g, label, k) for g, label, k, _f in w._actions()])
plain = [r.name for r in listed("b-roll")]
starred = next(r for r in w.model.clip_rows if r.name == plain[-1])
starred.favorited = True
listed("")
check("a favourite comes first among those that match as well", [r.name for r in listed("b-roll")][0] == plain[-1] != plain[0])
starred.favorited = False
listed("")
from clipse import fusion_animate as fa
check("Animate is parked for now: not a tile, not in the > list - but all still there",
      fa.PARKED and not [r.name for r in listed("> animate") if r.name.startswith(("Animate", "Keyframes"))]
      and "Animate\u2026" not in [label for _g, label, _k, _f in w._actions()] and len(fa.ANIMATIONS) > 5)
fa.PARKED = False  # ...and it still works when it's brought back
listed(">")
names = [r.name for r in listed("> animate")]
check("> animate lists the moves, in and out, and what to do with keyframes that are there",
      "Animate in: Slide from the left" in names and "Animate out: Fade" in names and "Keyframes: smooth them" in names
      and len(names) == 2 * len(fa.ANIMATIONS) + 3)
check("...each with a symbol, and none of them in the plain > list", all(r.glyph for r in listed("> animate"))
      and "Animate\u2026" in [r.name for r in listed(">")] and "Animate in: Fade" not in [r.name for r in listed(">")])
hint = do("> animate", "Animate in: Pop")
check("away from the Fusion page it says where it works", "Fusion page" in hint)
node, label, fixed, channels = fa.plan("slide_left", "in", 0, 119, 60.0)
keys = channels[0][3]
check("Slide from the left: a Transform, 0.4 s at the start, from outside the frame to the middle",
      (node, label) == ("Transform", "SlideLeftIn") and sorted(keys) == [0, 24]
      and (keys[0][0], keys[24][0]) == (-0.5, 0.5) and channels[0][:3] == ("Center", "X", 0.5))
check("...arriving softly: the handles pull it to its place early", keys[0][2][1] == 0.5 and 0 < keys[0][2][0] < keys[24][1][0] < 24)
keys = fa.plan("slide_left", "out", 0, 119, 60.0)[3][0][3]
check("Slide to the left: the same at the end, leaving softly", sorted(keys) == [95, 119]
      and (keys[95][0], keys[119][0]) == (0.5, -0.5) and keys[95][2][1] == 0.5)
check("a pop goes past its size and settles", max(v[2][1] for v in fa.plan("pop", "in", 0, 119, 60.0)[3][0][3].values() if v[2]) > 1.0)
check("a short clip: never more than half of it", fa.frames_for(0.4, 60.0, 0, 10) == 5)


class FakeComp:
    def __init__(self):
        self.ran, self.undo, self.data = [], [], {}
    def GetAttrs(self): return {"COMPN_RenderStart": 0.0, "COMPN_RenderEnd": 119.0}
    def GetPrefs(self, key): return 60.0
    def StartUndo(self, title): self.undo.append(title)
    def EndUndo(self, keep): self.undo.append("end")
    def SetData(self, key, value): self.data[key] = value
    def GetData(self, key): return self.data.get(key)
    def Execute(self, lua): self.ran.append(lua); self.data["ClipseResult"] = "ok"


comp = FakeComp()
worked, message = fa.animate_comp(comp, "fade", "out", add_tool=lambda c, kind, title, undo: f"connected after MediaIn1 ({kind})")
check("Animate out: Fade - one node, one undo step, and it says what it did",
      worked and comp.undo == ["Animate out: Fade", "end"] and len(comp.ran) == 1 and "BrightnessContrast" in message
      and "24 frames at the end" in message and 'TOOLS_Name = "FadeOut"' in comp.ran[0] and "tool.Alpha = 1.0" in comp.ran[0])
comp = FakeComp()
worked, message = fa.animate_comp(comp, "pop", "in", add_tool=lambda c, kind, title, undo: "unknown tool")
check("...a node Fusion doesn't have: says so, no keyframes, the undo step still closed",
      not worked and not comp.ran and comp.undo[-1] == "end")
comp = FakeComp()
comp.Execute = lambda lua: comp.data.update(ClipseResult="2 3")
check("Keyframes: smooth them - says how many settings it changed", fa.change_existing(comp, "smooth") == (True, "Smoothed 3 animated settings"))
comp.Execute = lambda lua: comp.data.update(ClipseResult="0 0")
check("...with no node selected: says to select one", "Select" in fa.change_existing(comp, "reverse")[1])

# -- Tidy the subtitles: the same words, cut where a phrase ends --
from clipse import subtitles as st
resolve_wrote = [(30, 174, "So today I want to show you a small tool"), (174, 324, "that I made for DaVinci Resolve, because I"),
                 (324, 456, "was tired of clicking through the media"), (456, 600, "pool every time I needed a sound effect."),
                 (672, 798, "It opens with one key, you type a few"), (798, 930, "letters, and the clip is on the timeline.")]
tidied = st.tidy(resolve_wrote, 42, 60.0)
texts = [t for _a, _b, t in tidied]
check("cut where a phrase ends: after the comma, before 'because'",
      "that I made for DaVinci Resolve," in texts and "because I was tired of clicking" in texts)
check("...not a word lost or moved", " ".join(texts).split() == " ".join(t for _a, _b, t in resolve_wrote).split())
check("...no line longer than asked, none ending on 'the' or 'to'",
      all(len(t) <= 42 for t in texts) and not any(t.split()[-1].lower() in ("the", "to", "a", "i") for t in texts))
check("...in step with the speech: starts and ends where it did, nothing overlaps, the pause stays a pause",
      tidied[0][0] == 30 and tidied[-1][1] == 930 and all(a < b for a, b, _t in tidied)
      and all(tidied[k][1] <= tidied[k + 1][0] for k in range(len(tidied) - 1))
      and any(b == 600 for _a, b, _t in tidied) and any(a == 672 for a, _b, _t in tidied))
double = st.tidy(resolve_wrote, 42, 60.0, "double")
check("two lines: lines that belong together share a subtitle, never across a full stop or a pause",
      "It opens with one key,\nyou type a few letters," in [t for _a, _b, t in double]
      and all(len(line) <= 42 for _a, _b, t in double for line in t.split("\n")) and len(double) < len(tidied))
short = st.tidy(resolve_wrote, 20, 60.0)
check("short lines for a vertical video: more subtitles, still whole phrases",
      len(short) > len(tidied) and all(len(t) <= 20 for _a, _b, t in short) and "a small tool" in [t for _a, _b, t in short])
check("Danish too", "fordi jeg var tr\u00e6t af at klikke rundt" in [t for _a, _b, t in st.tidy(
    [(0, 150, "I dag vil jeg vise jer et lille v\u00e6rkt\u00f8j, som jeg"), (150, 300, "har lavet til DaVinci Resolve, fordi jeg var tr\u00e6t"),
     (300, 460, "af at klikke rundt i mediepuljen hver gang jeg skulle bruge en lydeffekt.")], 42, 60.0)])
check("the subtitle file counts from the start of the timeline",
      st.srt_text([(86430, 86490, "Hi")], 60.0, 86400).splitlines()[1] == "00:00:00,500 --> 00:00:01,500")
F.TRACKS.clear()
F.OFF.clear()
st.FOLDER = os.path.join(home, "subtitles")
hint = direct(st.tidy_subtitles, s.timeline_tools)
check("with no subtitles on the timeline it says what to do first", "Subtitles from speech first" in hint)
F.TRACKS[("subtitle", 1)] = [F.Item(t, a // 2, b // 2) for a, b, t in resolve_wrote]  # (the fake timeline runs at 30)
hint = direct(st.tidy_subtitles, s.timeline_tools)
tidy_track = [i.n for i in F.TRACKS.get(("subtitle", 1), [])]
check("Tidy the subtitles: the tidied ones on a new subtitle track, in first place and switched on",
      len(tidy_track) == 8 and "because I was tired of clicking" in tidy_track and "6 subtitles are now 8" in hint
      and F.CURRENT[0].GetIsTrackEnabled("subtitle", 1))
check("...yours are still there, one track up, switched off", len(F.TRACKS[("subtitle", 2)]) == 6
      and not F.CURRENT[0].GetIsTrackEnabled("subtitle", 2) and "track 2" in hint)
check("...at the same moments as before", F.TRACKS[("subtitle", 1)][0].a == 15 and F.TRACKS[("subtitle", 1)][-1].b == 465)
hint = direct(st.tidy_subtitles, s.timeline_tools)
check("run again: nothing more to do, and it says so", "already split" in hint and ("subtitle", 3) not in F.TRACKS)
F.TRACKS.clear()
F.OFF.clear()
F.TRACKS[("subtitle", 1)] = [F.Item(t, a // 2, b // 2) for a, b, t in resolve_wrote]
real_enable = F.TL.SetTrackEnable
F.TL.SetTrackEnable = lambda self, kind, index, on: True  # a Resolve where the new track won't switch on
hint = direct(st.tidy_subtitles, s.timeline_tools)
F.TL.SetTrackEnable = real_enable
check("a new track that won't switch on: nothing is put anywhere, yours exactly as they were",
      "as they were" in hint and F.CURRENT[0].GetTrackCount("subtitle") == 1 and "APPENDSUBTITLES" not in open(F.LOG).read()
      and [i.n for i in F.TRACKS[("subtitle", 1)]] == [t for _a, _b, t in resolve_wrote]
      and F.CURRENT[0].GetIsTrackEnabled("subtitle", 1))
real_enabled = F.TL.GetIsTrackEnabled
F.TL.SetTrackEnable = lambda self, kind, index, on: True
F.TL.GetIsTrackEnabled = lambda self, kind, index: True if index == 1 else real_enabled(self, kind, index)  # ...and says it did
hint = direct(st.tidy_subtitles, s.timeline_tools)
F.TL.SetTrackEnable, F.TL.GetIsTrackEnabled = real_enable, real_enabled
check("subtitles that land on the wrong track: found, taken off again, yours exactly as they were",
      "as they were" in hint and F.CURRENT[0].GetTrackCount("subtitle") == 1 and "APPENDSUBTITLES" in open(F.LOG).read()
      and [i.n for i in F.TRACKS[("subtitle", 1)]] == [t for _a, _b, t in resolve_wrote])

# -- Fusion expressions: rows of their own (x:), played in the preview, put where they belong --
from PySide6.QtWidgets import QApplication
from clipse import fusion_expressions as fx
w.hide()
_setup.pump(0.05)
w.open_picker()
_setup.pump(0.2)
rows = listed("x: ")
check("x: lists the expressions, each with the setting it goes on - and the way to the cheat sheet first, a row of its own",
      len(rows) == len(fx.LIBRARY) + 1 and all(r.category == "expression" for r in rows[1:])
      and (rows[0].category, rows[0].name, rows[0].path) == ("shortcut", "Expressions", "bar:cheat_sheet")
      and next(r for r in rows if r.name == "Swing like a sign").folder_list == "Transform \u203a Angle")
F.PAGE_NOW[0] = "fusion"
check("a plain search on the Fusion page lists Expressions once (the shortcut row, not the x: one as well)",
      [r.name for r in listed("expressions")].count("Expressions") == 1)
F.PAGE_NOW[0] = "edit"
rows = listed("x: ")
w.list_view.setCurrentIndex(w.model.index(1, 0))
_setup.pump(0.4)
check("...and the preview opens by itself to show the highlighted one", w.preview_panel.isVisible()
      and w.preview_panel.canvas.card is not None and w.preview_panel.canvas.card["key"] == rows[1].path)
w.list_view.setCurrentIndex(w.model.index(0, 0))
w.confirm()
_setup.pump(0.05)
sheet = w.expression_sheet
check("Enter on the cheat sheet lays it over the list as tiles, in groups",
      sheet.isVisible() and [g for g, _r in sheet.entries()][:3] == ["Composition", "Time", "Waves"]
      and len(sheet._layout()["tiles"]) == sum(len(r) for _g, r in fx.CHEAT_SHEET))
sheet.set_view("everything")
check("Everything: every function an expression can use, in groups - the cheat sheet keeps what's used",
      [g for g, _r in sheet.entries()][:3] == ["Fusion", "Maths", "Comparing and choosing"]
      and len(sheet._layout()["tiles"]) == sum(len(r) for _g, r in fx.EVERYTHING)
      and sum(len(r) for _g, r in fx.EVERYTHING) > sum(len(r) for _g, r in fx.CHEAT_SHEET))
laid = sheet._layout()
lists_y = next(y for g, y, _c in laid["heads"] if g == "Lists")
sheet.scroll = lists_y + 30   # scrolled down to Lists by hand
sheet._keys_group = None
check("the group lit is the one scrolled to - not the one of the tile picked before", sheet._group_in_view(laid) == "Lists")
sheet.go_to_group(step=1)
check("...and PgDn goes on from there", sheet._group_in_view(sheet._layout()) == "Date and time")
sheet.filter = "bswap"
check("...and Find searches both lists: on the cheat sheet, bswap is found in Everything",
      len(sheet._layout()["tiles"]) == 1 and (sheet.set_view("sheet") or True)
      and [g for g, _h in sheet.entries()] == ["Everything: Bits"] and len(sheet._layout()["tiles"]) == 1)
sheet.filter = "floor"
check("...the cheat sheet's own first, then what only Everything has - nothing twice",
      [g for g, _h in sheet.entries()][0] in [g for g, _r in fx.CHEAT_SHEET]
      and len([t for _g, h in sheet.entries() for t, *_r in h if t == "floor(x)"]) == 1)
sheet.filter = ""
sheet.set_view("sheet")
# Ctrl and + / - in the sheet: its own zoom - the sheet keeps its size, zoomed out more columns; the picker's zoom stays
from clipse.fonts import window_zoom as _wz
sheet.resize(1141, 700)
picker_zoom, columns_before, size_before = _wz(w.settings, "picker"), sheet._columns(), sheet.size()
for _ in range(8):
    key(Qt.Key_Minus, "-", Qt.ControlModifier)
check("Ctrl+- with Expressions open zooms the sheet by itself: more columns, the same size, the picker's zoom as it was",
      _wz(w.settings, "expressions") < 1.0 and sheet._columns() > columns_before and sheet.size() == size_before
      and _wz(w.settings, "picker") == picker_zoom)
key(Qt.Key_0, "0", Qt.ControlModifier)
check("...and Ctrl+0 gives it back", _wz(w.settings, "expressions") == 1.0 and sheet._columns() == columns_before)
was_open = w.preview_panel.isVisible()
from PySide6.QtGui import QKeySequence as _QS
_pv = _QS(w.settings.keybinds["preview"])[0]  # the preview's key (Alt+Enter as it ships)
key(_pv.key(), "", _pv.keyboardModifiers())
_setup.pump(0.1)
now_open = w.preview_panel.isVisible()
key(_pv.key(), "", _pv.keyboardModifiers())
_setup.pump(0.1)
check("the preview's key with Expressions open opens / closes the preview, the sheet staying open over the list",
      now_open != was_open and w.preview_panel.isVisible() == was_open and sheet.isVisible()
      and sheet.geometry() == w.picker_column.geometry())
# the picker's zoom and Expressions' are each their own
from PySide6.QtGui import QWheelEvent as _WE
from PySide6.QtCore import QPoint as _QP, QPointF as _QPF
from PySide6.QtWidgets import QApplication as _QA


def _sheet_text():  # (the font's size, not its height in pixels: Windows rounds that to whole pixels)
    font = sheet._fonts()[2]
    return (font.pointSizeF() if font.pointSizeF() > 0 else font.pixelSize()) * sheet._k()


text_before = _sheet_text()
w.zoom_window(-1)
w.zoom_window(-1)
_setup.pump(0.05)
check("zooming the picker leaves Expressions as it was", abs(_sheet_text() - text_before) < 0.02 * text_before)
w.zoom_window(0)


def wheel(widget, up, mods=Qt.ControlModifier):
    at = _QPF(widget.width() / 2, widget.height() / 2)
    _QA.sendEvent(widget, _WE(at, widget.mapToGlobal(at), _QP(0, 0), _QP(0, 120 if up else -120),
                              Qt.NoButton, mods, Qt.NoScrollPhase, False))


picker_zoom = _wz(w.settings, "picker")
wheel(sheet, False)
wheel(sheet, False)
check("Ctrl + the wheel over Expressions zooms it, and only it",
      _wz(w.settings, "expressions") == 0.9 and _wz(w.settings, "picker") == picker_zoom)
scroll_before = sheet.scroll
wheel(sheet, False, Qt.NoModifier)
check("...a plain wheel still scrolls it", _wz(w.settings, "expressions") == 0.9 and sheet.scroll >= scroll_before)
key(Qt.Key_0, "0", Qt.ControlModifier)
# Expressions' own preview: open or not, remembered; the picker's put back after
sheet.close_sheet()
_setup.pump(0.05)
if not w.preview_panel.isVisible():
    w.preview_clip()
w.settings.display["expressions_preview"] = False
w._show_cheat_sheet()
_setup.pump(0.05)
closed_in_sheet = not w.preview_panel.isVisible()
sheet.close_sheet()
_setup.pump(0.05)
check("Expressions with its preview off closes the picker's while it's open, and puts it back after",
      closed_in_sheet and w.preview_panel.isVisible())
w._show_cheat_sheet()
key(_pv.key(), "", _pv.keyboardModifiers())
check("...the preview key there is remembered for Expressions", w.settings.display["expressions_preview"] is True)
sheet.close_sheet()
_setup.pump(0.05)
w.preview_clip()  # the picker's preview closed
_setup.pump(0.05)
picker_closed = not w.preview_panel.isVisible()
w._show_cheat_sheet()
_setup.pump(0.05)
check("...the picker's preview closed, Expressions opens with its own, open",
      picker_closed and w.preview_panel.isVisible() and sheet.isVisible())
sheet.close_sheet()
_setup.pump(0.05)
check("...and the picker's is closed again after", not w.preview_panel.isVisible())
# Ctrl + the wheel over the picker's list: the picker
sheet.close_sheet()
wheel(w.list_view.viewport(), True)
check("Ctrl + the wheel over the list zooms the picker", _wz(w.settings, "picker") > picker_zoom)
w.zoom_window(0)
w._show_cheat_sheet()
_setup.pump(0.05)
# Ctrl+A in the sheet's fields: all of it chosen - typing replaces it, Backspace clears it
from PySide6.QtGui import QKeyEvent as _K
sheet.set_field("find")
sheet.filter = "countdown"
sheet.handle_key(_K(QEvent.KeyPress, Qt.Key_A, Qt.ControlModifier, "a"))
chosen_all = sheet._all == "find"
sheet.handle_key(_K(QEvent.KeyPress, Qt.Key_W, Qt.NoModifier, "w"))
check("Ctrl+A in the cheat sheet's Find: all of it chosen, and typing replaces it", chosen_all and sheet.filter == "w")
sheet.filter = "sin"
sheet.handle_key(_K(QEvent.KeyPress, Qt.Key_A, Qt.ControlModifier, "a"))
sheet.handle_key(_K(QEvent.KeyPress, Qt.Key_Backspace, Qt.NoModifier, ""))
check("...and Backspace clears it", sheet.filter == "")
several = [t for t in sheet._layout()["tiles"] if t["parts"]]
check("tiles of several small pieces (comparisons, date letters) have a box each, copied by itself",
      ["==", "~=", "<", ">", "<=", ">="] in [[piece for piece, _r in t["parts"]] for t in several]
      and any("%B" in [piece for piece, _r in t["parts"]] for t in several)
      and sheet.copy(next(t["n"] for t in several if t["parts"][0][0] == "=="), piece="<=") == "<=")
check("...with no node selected, NodeName stands where a node's name goes",
      any(code == "NodeName.Center.X" for _g, rows in sheet.entries() for code, _m, *_ in rows))
sheet.open("Text1")
check("...and the selected node's name is written in instead",
      any(code == "Text1.Center.X" and marks == [(0, 5)] for _g, rows in sheet.entries() for code, marks, *_ in rows)
      and not any("NodeName" in code for _g, rows in sheet.entries() for code, _m, *_ in rows))
QApplication.clipboard().setText("")
w.handle_action_key(QKeyEvent(QEvent.KeyPress, Qt.Key_Return, Qt.ShiftModifier, "\r"))
check("Shift+Enter copies the highlighted piece and stays", QApplication.clipboard().text() == "time"
      and sheet.isVisible() and w.isVisible())
key(Qt.Key_Right)
key(Qt.Key_Down)
check("the arrows move over the tiles", sheet.index == 1 + sheet._columns())
key(Qt.Key_PageDown)
check("Page Down goes to the next group", sheet._layout()["tiles"][sheet.index]["code"] == "time - comp.RenderStart")
key(Qt.Key_PageUp)
check("...Page Up back", sheet.index == 0)
key(Qt.Key_Tab)
check("Tab goes to the Node name field", sheet.field == "node")
for letter in "Merge3":
    key(getattr(Qt, "Key_" + letter.upper()), letter)
check("...typing there replaces the name, and every piece that names a node follows",
      sheet.node == "Merge3" and sheet.filter == ""
      and any(code == "Merge3.Center.X" for _g, rows in sheet.entries() for code, _m, *_ in rows))
key(Qt.Key_Backspace)
key(Qt.Key_4, "4")
key(Qt.Key_Space, " ")
check("...a name has no spaces", sheet.node == "Merge4")
key(Qt.Key_Return, "\r")
check("...Enter there goes back to finding, and copies nothing", sheet.field == "find" and sheet.isVisible()
      and QApplication.clipboard().text() == "time")
key(Qt.Key_N, "n", Qt.AltModifier)
check("Alt+N in the sheet does nothing now (Copy node name is keyed in Resolve) - and doesn't type an n",
      QApplication.clipboard().text() == "time" and sheet.isVisible() and sheet.filter == "")
now_selected = [""]
real_now, fx.selected_node_now = fx.selected_node_now, lambda resolve: now_selected[0]
sheet.follow_fusion()
check("with the same node still selected in Fusion, a typed name stays", sheet.node == "Merge4")
now_selected[0] = "Background2"
sheet.follow_fusion()
check("a node clicked in Fusion while the sheet is open goes into every piece",
      sheet.node == "Background2" and any(code == "Background2.Size" for _g, rows in sheet.entries() for code, _m, *_ in rows))
check("...and the sheet keeps asking while it's open, not after", sheet._watch.isActive())
fx.selected_node_now = real_now
for letter in "countdown":
    key(getattr(Qt, "Key_" + letter.upper()), letter)
check("typing narrows the tiles down", [x["about"] for x in sheet._layout()["tiles"]] == ["A countdown from 60 seconds, stopping at 0."]
      and w.search_edit.text() == "x: ")
key(Qt.Key_Escape)
check("Esc clears what was typed first", sheet.isVisible() and sheet.filter == "")
for letter in "dates":
    key(getattr(Qt, "Key_" + letter.upper()), letter)
check("a group's name finds all of it", len(sheet._layout()["tiles"]) == 5)
key(Qt.Key_Escape)
key(Qt.Key_Escape)
check("...and then goes back to the list", not sheet.isVisible() and w.isVisible() and not sheet._watch.isActive())
w.confirm()
_setup.pump(0.05)
sheet.go_to_group("Words")
key(Qt.Key_Return, "\r")
check("Enter copies the piece and closes the picker", QApplication.clipboard().text() == 'Text("Hello")'
      and not sheet.isVisible() and not w.isVisible())
w.open_picker()
_setup.pump(0.2)
check("the bottom bar says Insert as on the Edit page", w.insert_options_link.text() == "Insert as")
F.PAGE_NOW[0] = "fusion"
w.hide()
w.open_picker()
_setup.pump(0.2)
w.insert_options_link.clicked.emit()
check("...and Cheat sheet on the Fusion page, which opens it", w.insert_options_link.text() == "Expressions" and sheet.isVisible())
key(Qt.Key_Escape)
F.PAGE_NOW[0] = "edit"
w._watch_page()
check("Resolve goes to another page while the picker is open: the bottom bar follows", w.insert_options_link.text() == "Insert as"
      and w._page_timer.isActive())
sounds_here = sum(r.category == "audio" for r in listed(""))
F.PAGE_NOW[0] = "fusion"
w._watch_page()
s.page_defaults["fusion"]["clips"] = True
w.model.set_filter("")
check("...and so does the list: on the Fusion page no sounds, which a composition can't take",
      w.insert_options_link.text() == "Expressions" and sounds_here > 0
      and not any(w.model.rows[i].category == "audio" for i in w.model.visible)
      and any(w.model.rows[i].category == "video" for i in w.model.visible))
check("...a: still reaches them, and Enter says why it won't add one", any(r.category == "audio" for r in listed("a: ")))
w.confirm()
_setup.pump(0.05)
check("...", "can't go into a Fusion composition" in w.hints_label.text() and w.isVisible())
s.page_defaults["fusion"]["show_video"] = False  # each page its own kinds: stills only on the Fusion page, say
w.model.page_hides = s.hidden_categories("fusion")
kinds = {r.category for r in listed("") if r.category in ("video", "image", "audio")}
F.PAGE_NOW[0] = "edit"
w._watch_page()
kinds_edit = {r.category for r in listed("") if r.category in ("video", "image", "audio")}
check("the Fusion page can list other kinds than the Edit page: only stills there, everything here",
      kinds == {"image"} and kinds_edit == {"video", "image", "audio"} and s.kind_built("show_video"))
s.page_defaults["fusion"]["show_video"] = True
F.PAGE_NOW[0] = "fusion"
w._watch_page()
from clipse import sound_analysis as _sa  # noqa: E402
_audio = [r for r in w.model.clip_rows if r.category == "audio"][:3]
for _n, _r in enumerate(_audio):  # three analysed sounds: the third sounds like the first, the second doesn't
    _r.music = False
    _r.analysis = {"features": {g: [1.0, 2.0, 3.0] if _n != 1 else [9.0, -4.0, 7.0] for g in _sa.GROUP_WEIGHTS}}
_similar = w._similar_rows(_audio[0].name)
check("Sounds like this is back (2026-10-15): an action with its key, and like: lists the sound itself "
      "first, then the ones that sound like it",
      "Sounds like this" in [label for _g, label, _k, _f in w._all_actions()] and s.keybinds["similar_sounds"] == "Ctrl+L"
      and s.prefixes["like"] == ["like"] and _similar[0] == (w.model.clip_rows.index(_audio[0]), None)
      and _similar[1][0] == w.model.clip_rows.index(_audio[2]))
for _r in _audio:
    _r.analysis = None
s.page_defaults["fusion"]["clips"] = False
# a node picked by a click in Fusion: the picker gets out of the way, and the sheet comes back with its name
w.search_edit.setText("")
w._show_cheat_sheet()
_setup.pump(0.05)
picked_now = ["Text1"]
real_now2, real_clear = fx.selected_node_now, fx.clear_selection
fx.selected_node_now = lambda resolve: picked_now[0]
fx.clear_selection = lambda resolve: picked_now.__setitem__(0, "")
sheet.filter = "width"
node_before = sheet.node
sheet.set_field("node")
key(Qt.Key_Return, "\r")
check("Enter in the Node name field before typing: the picker hides and waits for a click in Fusion",
      not w.isVisible() and w._pick is not None and w._pick_timer.isActive() and w.pick_notice.isVisible()
      and w.pick_notice.text == "Click a node in Fusion")
w.pick_notice.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_Escape, Qt.NoModifier))
_setup.pump(0.05)
check("...Esc calls it off: the sheet is back as it was, nothing changed", w.isVisible() and sheet.isVisible()
      and sheet.node == node_before and sheet.filter == "width" and w._pick is None and not w.pick_notice.isVisible())
sheet.set_field("node")
key(Qt.Key_Return, "\r")
w._pick_step()
check("...nothing clicked yet: still waiting", w._pick is not None and not w.isVisible())
picked_now[0] = "Merge7"
w._pick_step()
_setup.pump(0.05)
check("...a node clicked: the sheet is back as it was, with that name in every piece",
      w.isVisible() and sheet.isVisible() and sheet.node == "Merge7" and sheet.filter == "width" and w._pick is None
      and not w.pick_notice.isVisible() and any(code == "Merge7.Output.Width" for _g, rows in sheet.entries() for code, _m, *_ in rows))
key(Qt.Key_Escape)
key(Qt.Key_Escape)
key(Qt.Key_Escape)
copied_code = enter_follow = None
listed("x: follow another node's position")
w.confirm()
_setup.pump(0.05)
check("Enter on an expression that follows another node: click that node in Fusion", not w.isVisible() and w._pick is not None)
picked_now[0] = "Transform3"
w._pick_step()
check("...its name is written into the code, which is copied - and the picker stays out of the way",
      QApplication.clipboard().text() == "Transform3.Center" and not w.isVisible() and w.toast.isVisible()
      and not w.pick_notice.isVisible())
w.toast.clear()
w.open_picker()
_setup.pump(0.1)
listed("x: mirror another")
w.confirm()
w.open_picker()
check("...opening the picker again while it waits calls the waiting off", w._pick is None and not w._pick_timer.isActive())
fx.selected_node_now, fx.clear_selection = real_now2, real_clear
F.PAGE_NOW[0] = "edit"
w.hide()
w.open_picker()
_setup.pump(0.2)
listed("x: ")
listed("B-roll 001")
check("...and closes again when you move on to something else", not w.preview_panel.isVisible())
check("on the Edit page they stay out of the plain list", not any(r.category == "expression" for r in listed("wiggle")))
F.PAGE_NOW[0] = "fusion"
listed("")  # (the same words again wouldn't search again)
check("on the Fusion page they're in it (Settings > What the list shows)",
      any(r.category == "expression" for r in listed("wiggle")))
F.PAGE_NOW[0] = "edit"
real_plan, real_apply, real_name = fx.plan, fx.apply, fx.selected_node_name
applied = []
used = []
fx.apply = lambda resolve, key, values=None, sliders=True: (applied.append(key), used.append((values, sliders)), (True, "done"))[2]


def enter_on(text, name):
    row = next(i for i, r in enumerate(listed(text)) if r.name == name)
    w.show()
    w.list_view.setCurrentIndex(w.model.index(row, 0))
    _setup.pump(0.05)
    w.confirm()
    _setup.pump(0.05)
    return w.hints_label.text()


fx.plan = lambda resolve, key: ("none", "MediaIn1")
hint = enter_on("x: wiggle the position", "Wiggle the position")
check("Enter with no node selected in Fusion: it asks first, and says what it would add",
      "Enter again adds a Transform after MediaIn1" in hint and not applied and w.isVisible())
check("...the code is on the clipboard already", QApplication.clipboard().text() == fx.BY_KEY["wiggle_position"]["code"])
w.preview_panel.canvas.card_values["wiggle_position"] = {"far": 0.05}  # a slider dragged in the preview
w.confirm()
_setup.pump(0.05)
check("...Enter again: done, and the picker gets out of the way", applied == ["wiggle_position"] and not w.isVisible())
check("...with the numbers its sliders were at, to become sliders on the node",
      used[-1][0]["far"] == 0.05 and used[-1][0]["fast"] == 0.12 and used[-1][1] is True
      and "0.05*sin" in QApplication.clipboard().text())
s.timeline_tools["expression_ask"] = False
enter_on("x: pulse", "Pulse the size")
check("asking switched off in Settings: straight away", applied[-1] == "pulse" and not w.isVisible())
s.timeline_tools["expression_ask"] = True
fx.plan = lambda resolve, key: ("has", "Transform1")
enter_on("x: spin", "Spin steadily")
check("with the right kind of node selected there's nothing to ask", applied[-1] == "spin" and not w.isVisible())
from PySide6.QtCore import QEvent
from PySide6.QtGui import QKeyEvent
row = next(i for i, r in enumerate(listed("x: bounce")) if r.name == "Bounce on the spot")
w.show()
w.list_view.setCurrentIndex(w.model.index(row, 0))
_setup.pump(0.05)
before = len(applied)
w.handle_action_key(QKeyEvent(QEvent.KeyPress, Qt.Key_Return, Qt.ShiftModifier, "\r"))
check("Shift+Enter only copies the code - nothing is put on a node, the picker stays",
      QApplication.clipboard().text() == fx.BY_KEY["bounce"]["code"] and len(applied) == before and w.isVisible()
      and "Copied the code" in w.hints_label.text())
QApplication.clipboard().setText("")
w.handle_action_key(QKeyEvent(QEvent.KeyPress, Qt.Key_C, Qt.ControlModifier, "c"))
check("...and so does Ctrl+C", QApplication.clipboard().text() == fx.BY_KEY["bounce"]["code"])
_setup.pump(5.8)  # (the hint "Copied the code" lasts 5 s)
check("on an expression the bottom bar says what Enter and Shift+Enter do",
      [h[1] for h in w.hints_label.hints] == ["Put on a node", "Copy the code"])
fx.plan = real_plan
hint = enter_on("x: follow", "Follow another node's position")
check("one that names another node is only copied - with what to change in it",
      QApplication.clipboard().text() == "Transform1.Center" and "Transform1" in hint and w.isVisible() and applied[-1] == "spin")
check("the sliders' numbers go into the code, and can be sliders on the node instead",
      fx.code(fx.BY_KEY["swing"], {"degrees": 20}) == "20*sin(time/10)"
      and fx.control_code(fx.BY_KEY["swing"]) == "SwingDegrees*sin(time/SwingSlow)")
hint = enter_on("x: blink", "Blink on and off")
check("away from the Fusion page: copied, and told where to paste it", "right-click a setting" in hint and applied[-1] == "spin")
fx.selected_node_name = lambda resolve: ("Transform7", "")
w.show()
message = w._copy_node_name()
check("Copy node name: the selected node's name, ready to write in an expression",
      QApplication.clipboard().text() == "Transform7" and "Transform7.Center" in message)
fx.selected_node_name = lambda resolve: ("", "Select a node in Fusion first")
fx.selected_node_name = lambda resolve: ("", "Select a node in Fusion first")
check("...with nothing selected it says so", w._copy_node_name() == "Select a node in Fusion first")
fx.plan, fx.apply, fx.selected_node_name = real_plan, real_apply, real_name
check("Copy Node Name is there in Resolve's menu to give a key to; Next / Previous Keyframe went (Resolve has its own)", (
    lambda names: "Copy Node Name" in names and "Next Keyframe" not in names)(
    [a[0] for a in __import__("clipse.resolve_shortcuts", fromlist=["x"]).ACTIONS]))

# -- Step Forward / Step Back: timecodes there and back, drop-frame too --
from clipse import timeline_tools as _tt
check("a step's timecodes go there and back - 24, 25, 23.976, 29.97 / 59.94 drop-frame", all(
    _tt.tc_frames(_tt.frames_tc(n, fps, drop), fps) == n
    for fps, drop in ((24, False), (25, False), (23.976, False), (29.97, True), (59.94, True))
    for n in list(range(0, 4000, 7)) + [86313, 107892, 107893, 215784, 300000]))
check("...and drop-frame skips the numbers it should", _tt.frames_tc(1800, 29.97, True) == "00:01:00;02"
      and _tt.frames_tc(17982, 29.97, True) == "00:10:00;00" and _tt.tc_frames("01:00:00;00", 29.97) == 107892)

# -- Settings > What the list shows: the small picker drawn there follows the tiles --
from clipse.settings_cards import PickerSketch
edit_page, fusion_page = PickerSketch(s, "other", ""), PickerSketch(s, "fusion", "")
check("the Edit page's sketch lists Media Pool rows, the Fusion page's macros, nodes and expressions",
      ("video", "interview_take2.mp4") in edit_page.rows() and ("expression", "Wiggle the position") in fusion_page.rows()
      and ("video", "interview_take2.mp4") not in fusion_page.rows())
s.general["show_bins"] = False
s.page_defaults["fusion"]["clips"] = True
check("...a kind switched off leaves it, a source switched on joins it",
      not any(symbol == "bin" for symbol, _n in edit_page.rows()) and ("video", "interview_take2.mp4") in fusion_page.rows())
s.general["show_bins"] = True
s.page_defaults["fusion"]["clips"] = False
s.page_defaults["other"] = dict.fromkeys(s.page_defaults["other"], False)
check("...and with everything off it's empty until a prefix is typed", edit_page.rows() == [])
s.page_defaults["other"]["clips"] = True

s.page_defaults["other"]["shortcuts"] = True
check("...Shortcuts is a source like the others, on both pages",
      ("shortcut", "Settings: Appearance") in edit_page.rows() and ("shortcut", "Settings: Appearance") in fusion_page.rows())

# -- Settings: a setting lives on one page, and a page resets only what it shows --
from PySide6.QtWidgets import QGroupBox, QLabel, QPushButton
from clipse import scripts_fusion as sf
from clipse.settings_dialog import KeyField
dialog = SettingsDialog(s)
dialog._build_rest(all_now=True)
titles = [title for title, _i, _b in SettingsDialog.PAGES]
folders_text = " ".join(label.text() for label in dialog.tabs.widget(titles.index("Folders")).findChildren(QLabel))
from clipse.resolve_shortcuts import ACTIONS as _MENU
from clipse import scripts_page as _sp
check("the folders with your scripts are on Folders; Scripts is a table of every script of Clipse's in Resolve's menu, "
      "by the page it's for",
      "Searched with script:" in folders_text
      and sorted(script for _h, rows in _sp.SCRIPTS for _s, script, _g, _c in rows) == sorted(n for n, _m, _a in _MENU)
      and [h for h, _rows in _sp.SCRIPTS] == ["Clipse", "Edit page", "Fusion page"]
      and _sp.menu_short("Grab Frame") == "Clipse 03" and _sp.menu_short("Open") == "Clipse")
dialog._script_table.select("Step Back")
check("...choosing one shows what it has to set beside it (Step back: how far)",
      dialog._script_chosen == "Step Back" and "step_back_frames" in dialog._fields)
dialog._script_table.select("Swap Clip")
# a script of yours: Add puts a launcher in Resolve's menu, and the page shows it as added
_mine = os.path.join(os.environ["HOME"], "my_scripts")
os.makedirs(_mine, exist_ok=True)
open(os.path.join(_mine, "rename_clips.lua"), "w").write("-- test\n")
s.folders["scripts"] = [_mine]
_mine_path = os.path.join(_mine, "rename_clips.lua")
_page = dialog._your_scripts_card()
_buttons = {b.text(): b for b in _page.findChildren(QPushButton)}
_foot_row = dialog._scripts_buttons()
_foot = [_foot_row.itemAt(i).widget() for i in range(3)]
check("a script of yours not in Resolve's menu: Add - and after your scripts: Open scripts folder, Add a script…",
      "Add" in _buttons and "Open scripts folder" in _buttons and "Add a script\u2026" in _buttons
      and [w.text() if w else None for w in _foot] == ["Open scripts folder", "Add a script\u2026", None])
_buttons["Add"].click()
check("...clicked: it's in the menu (a launcher of ours, found again)",
      __import__("clipse.resolve_shortcuts", fromlist=["x"]).menu_place(_mine_path) == "added"
      and _mine_path in __import__("clipse.resolve_shortcuts", fromlist=["x"]).user_launcher_targets())
s.folders["scripts"] = []
# Resolve's keys for its Scripts menu, read from its own file: by the place in the menu - Clipse's in a submenu of
# their own, so a loose script sorting before them doesn't move their keys (tried in Resolve 21.1.1, 2026-10-21)
from clipse import resolve_keys as _rk, resolve_shortcuts as _rs
from clipse.keycaps import key_name as _kn  # (named as this system names them: a Mac says Option, Cmd ...)
def _entry(name, presses):
    enc = name.encode("utf-16-be")
    out = len(enc).to_bytes(4, "big") + enc + len(presses).to_bytes(4, "big")
    for keys in presses:
        out += len(keys).to_bytes(4, "big") + b"".join(k.to_bytes(4, "big") for k in keys)
    return out
_rs.install()
check("Clipse's scripts are in a folder of their own in Resolve's Utility folder, !Clipse - first of its submenus",
      os.path.isfile(os.path.join(_rs.utility_scripts_folder(), "!Clipse", "Clipse - Open.lua"))
      and not any(n.startswith("Clipse ") for n in os.listdir(_rs.utility_scripts_folder())))
_blob = b"\x00" * 12 + _entry("fileSaveProject", [[0x04000053]]) + _entry("workspace_sub1_sub001_menu1", [[0x08000053]]) \
    + _entry("workspace_sub1_sub001_menu20", [[0x02000051]]) + _entry("workspace_sub1_sub001_menu21", [[0x02000045]])
os.makedirs(os.path.dirname(_rk.preset_file()), exist_ok=True)
open(_rk.preset_file(), "w").write(f"<x><PresetListBA>{_blob.hex()}</PresetListBA></x>")
_keys = _rk.script_keys()
check("Resolve's keys read by the place in its menu: Open's Alt+S, Step back's Shift+Q, Step forward's Shift+E",
      _keys.get("Clipse - Open") == [_kn("Alt+S")] and _keys.get("Clipse 19 - Step Back") == [_kn("Shift+Q")]
      and _keys.get("Clipse 20 - Step Forward") == [_kn("Shift+E")] and len(_keys) == 3)
_old = os.path.join(_rs.utility_scripts_folder(), "Clipse")  # (where they were for an hour)
os.makedirs(_old, exist_ok=True)
open(os.path.join(_old, "Clipse - Open.lua"), "w").write(_rs.launcher_text(b"TRIGGER", []))
_rs.install()
check("...the folder they were in before (Clipse) is taken out", not os.path.exists(_old))
_rs.STAND_INS[30] = "Old Thing"
_rs.install()
_stand_in = os.path.join(_rs.clipse_scripts_folder(), "Clipse 30 - Old Thing.lua")
check("a script taken out of the middle keeps its place with a stand-in: it only tells the service, never starts it",
      os.path.isfile(_stand_in) and "[[RETIRED:Old Thing]]" in open(_stand_in).read()
      and "local COMMAND = {}" in open(_stand_in).read())
del _rs.STAND_INS[30]
_rs.install()
check("...and goes when it's no longer listed", not os.path.exists(_stand_in))
_early = os.path.join(_rs.utility_scripts_folder(), "123.lua")
open(_early, "w").write("-- mine\n")
check("...a loose script of yours sorting before them doesn't move them", _rk.script_keys() == _keys)
open(_rk.preset_file(), "w").write(f"<x><PresetListBA>{(_blob + _entry('workspace_sub1_menu2', [[0x0600004A]])).hex()}</PresetListBA></x>")
check("...and its own key is read too - place 2, after the !Clipse folder (a folder takes a place in the menu)",
      _rk.script_keys().get("123") == [_kn("Ctrl+Shift+J")])
os.remove(_early)
check("every page says what it's for", set(SettingsDialog.PAGE_ABOUT) == set(titles))
from clipse.settings_dialog import KeyEdit as _KeyEdit  # noqa: E402
from PySide6.QtGui import QKeyEvent as _KE  # noqa: E402
_box = _KeyEdit("Return")
from PySide6.QtGui import QFocusEvent as _FE  # noqa: E402
_box.focusInEvent(_FE(QEvent.FocusIn))
_box.keyPressEvent(_KE(QEvent.KeyPress, Qt.Key_Escape, Qt.NoModifier))
check("Esc in a key box that's listening: it stops, the key as it was - Esc never becomes the key",
      _box.keySequence().toString() == "Return")
dialog._set_prefix("bin", "b:, folder:")
check("Search Prefixes shows each prefix with its colon, as it's typed - and takes them with or without",
      s.prefixes["bin"] == ["b", "folder"])
dialog._set_prefix("bin", "b")
s.listen.update(volume=11, show_bpm=False)
s.timeline_tools.update(tidy_style="vertical", adj_fixed_frames=77, tidy_after_insert=True, subtitle_chars=30)
s.files.update(max_windows=3, grabs_on_timeline=False)
dialog._show_page(titles.index("Sound"))
dialog._reset_current_tab()
check("Reset page on Sound puts the BPM setting back and leaves the preview's volume alone",
      s.listen["show_bpm"] is True and s.listen["volume"] == 11)
dialog._show_page(titles.index("Fusion"))
dialog._reset_current_tab()
check("...on Fusion the tidy after inserts, not the tidy's own style (that's Scripts')",
      s.timeline_tools["tidy_after_insert"] is False and s.timeline_tools["tidy_style"] == "vertical")
dialog._show_page(titles.index("Timeline"))
dialog._reset_current_tab()
check("...on Timeline the subtitles, not the adjustment clip (Scripts')",
      s.timeline_tools["subtitle_chars"] == 42 and s.timeline_tools["adj_fixed_frames"] == 77)
dialog._show_page(titles.index("Scripts"))
dialog._reset_current_tab()
check("...on Scripts the adjustment clip, the tidy and Grab frame, not the file manager's windows (Folders')",
      s.timeline_tools["adj_fixed_frames"] == 180 and s.timeline_tools["tidy_style"] == "lines"
      and s.files["grabs_on_timeline"] is True and s.files["max_windows"] == 3)
s.listen["volume"], s.files["max_windows"] = 70, 8
dialog.close()

# -- Fusion composition over the clip under the playhead (a script in Resolve's menu, like the adjustment clip) --
from clipse import resolve_shortcuts as rs
from clipse import client, daemon
said = []
w._say = lambda text, ms=3500, **_kw: said.append(text)
os.environ["FAKE_OLD_RESOLVE"] = "1"
w.run_direct_command("comp", "fixed")
check("Fusion Composition at Playhead, no composition in the Media Pool and a Resolve that won't take the app's "
      "own: it says how to make one", said and "New Fusion Composition" in said[-1])
del os.environ["FAKE_OLD_RESOLVE"]
said.clear()
w.run_direct_command("comp", "fixed")
bins = {f.GetName(): [c.GetName() for c in f.GetClipList()] for f in F.ROOT.subs}
check("...otherwise the app brings its own, like the adjustment clip: into the clipse bin as fusion_composition, "
      "the bin it came in gone again, the composition placed and nothing to say",
      not said and "fusion_composition" in bins.get("clipse", []) and "davinci-search composition" not in bins
      and any(i.n == "fusion_composition" for lst in F.TRACKS.values() for i in lst))
count = sum(names.count("fusion_composition") for names in bins.values())
w.run_direct_command("comp", "match")
check("...once: the next one uses the same composition",
      sum(c.GetName() == "fusion_composition" for f in F.ROOT.subs for c in f.GetClipList()) == count == 1)
s.timeline_tools["comp_clip_name"] = "Not there"
w.run_direct_command("comp", "match")
check("...a name of your own in Settings > Scripts is the one looked for", said and "'Not there'" in said[-1])
s.timeline_tools["comp_clip_name"] = "fusion_composition"
check("the three Fusion Composition scripts are in Resolve's menu and reach the service",
      all(client.build_message(args) in daemon.DIRECT_COMMANDS
          for name, _m, args in rs.ACTIONS if name.startswith("Fusion Composition"))
      and sum(name.startswith("Fusion Composition") for name, _m, _a in rs.ACTIONS) == 3)

from clipse.settings import RESOLVE_KEYED as _RK, RESOLVE_NATIVE as _RN  # noqa: E402
check("what can be keyed in Resolve has one key, there: none of it has a picker key",
      all(not key for _g, label, key, _f in w._actions() if label in _RK or label in _RN)
      and not {"tidy_nodes", "undo_last", "pull_out_node", "copy_node_name", "node_on_off"} & set(s.keybinds))

# The Actions panel: the page's everyday actions, four to a row; any action has a key to give it
F.PAGE_NOW[0] = "edit"
labels = [label for _g, label, _k, _f in w.panel_actions()]
check("Actions on the Edit page: the owner's list (2026-10-14), the scripts first (2026-10-15) - nothing of Fusion's, "
      "nothing the bottom bar has",
      labels == ["Adjustment clip over clip", "Adjustment clip over footage", "Adjustment clip at playhead",
                 "Fusion composition over clip", "Fusion composition over footage", "Fusion composition at playhead",
                 "Swap clip", "Next use of clip", "Previous use of clip", "Grab frame", "Record voiceover",
                 "Undo Clipse\u2019s last step",
                 "Picture only", "Sound only", "Favourite", "Show in Media Pool",
                 "Show in file manager", "Sounds like this", "Tags", "Switch timeline\u2026", "Remove empty tracks",
                 "Mark the beats", "Mark the bars", "Copy markers", "Copy timeline", "Copy transcript", "Copy project", "Render\u2026",
                 "Switch project\u2026", "Project templates\u2026", "Project check-up", "Relink missing clips"])
F.PAGE_NOW[0] = "fusion"
labels = [label for _g, label, _k, _f in w.panel_actions()]
check("...on the Fusion page: Fusion's", "Tidy up nodes" in labels and "Switch timeline\u2026" not in labels
      and "Grab frame" not in labels and "Favourite" not in labels)
check("...typing finds any action when the page has none by that name",
      [label for _g, label, _k, _f in w.panel_actions("grab")] == ["Grab frame"])
F.PAGE_NOW[0] = "edit"
from clipse import actions_panel as _ap  # noqa: E402
check("...four to a row", _ap.COLUMNS == 4)
from clipse import look  # noqa: E402
import re as _re  # noqa: E402
from clipse.theme import build_stylesheet as _sheet  # noqa: E402
check("...and the stylesheet has a size wherever it says px - never a colour (a name clash once gave the "
      "Settings cards '#363a42px' corners)", not _re.search(r"#[0-9a-fA-F]{3,8}px", _sheet(s)))
check("one look: corners in three sizes as they ship - a control 6, a tile 10, a card 12",
      [look.radius(s, k) for k in ("control", "tile", "card")] == [6.0, 10.0, 12.0]
      if s.display["corner_radius"] == 4 else True)
_panel = w.actions_panel
_panel.open()
_setup.pump(0.2)
_shown = _panel._visible_actions()
_panel.index = next(n for n, a in enumerate(_shown) if a[1] == "Grab frame")
_panel.handle_key(QKeyEvent(QKeyEvent.KeyPress, Qt.Key_F, Qt.ControlModifier, "f"))
_shown = _panel._visible_actions()
check("...the favourite key there favourites the selected tile, and the selection goes with it",
      w.is_favourite_action("Grab frame") and _shown[_panel.index][:2] == ("Favourites", "Grab frame"))
_panel.handle_key(QKeyEvent(QKeyEvent.KeyPress, Qt.Key_F, Qt.ControlModifier, "f"))
check("...and again takes it back", not w.is_favourite_action("Grab frame"))
_panel.close_panel()
_setup.pump(0.3)
from clipse.settings import RESOLVE_KEYED  # noqa: E402
check("every action in either panel has a key to set - in the picker, or in Resolve", all(
    key for plan in (w.PANEL_EDIT, w.PANEL_FUSION) for _g, labels_ in plan if labels_
    for _g2, label, key, _f in w._actions() if label in labels_ and label not in RESOLVE_KEYED and label not in _RN))
shown = w.panel_actions()
heads = [g for g, _l, _k, _f in shown]
check("the Actions panel: the scripts in Resolve's menu first, the Undo last of them, then the rest",
      heads[:heads.count("Scripts")] == ["Scripts"] * heads.count("Scripts")
      and [l for g, l, _k, _f in shown if g == "Scripts"][-1] == "Undo Clipse\u2019s last step"
      and "Adjustment clip over clip" in [l for _g, l, _k, _f in shown])
check("every action named in either panel is an action", all(
    label in [l for _g, l, _k, _f in w._actions()] for plan in (w.PANEL_EDIT, w.PANEL_FUSION)
    for _g, labels_ in plan for label in labels_ or ()))
w.favourite_action("Render\u2026")
shown = w.panel_actions()
check("a favourite action comes first of all - and only once", shown[0][:2] == ("Favourites", "Render\u2026")
      and [l for _g, l, _k, _f in shown].count("Render\u2026") == 1)
F.PAGE_NOW[0] = "fusion"
check("...not on the Fusion page, when it's the Edit page's own",
      "Render\u2026" not in [l for _g, l, _k, _f in w.panel_actions()])
F.PAGE_NOW[0] = "edit"
w.favourite_action("Render\u2026", False)
check("...and Unfavourite puts it back in its group", w.panel_actions()[0][0] == "Scripts")
panel_ = w.actions_panel
tiles, _h, _b = panel_._layout(panel_._panel_rect())
shared = [(part["family"], label) for _r, _n, _g, label, *_k, part in tiles if part]
check("look-alike actions share a tile, showing one way: Adjustment clip, Fusion composition, Use of clip",
      shared == [("Adjustment clip", "Adjustment clip over clip"), ("Fusion composition", "Fusion composition over clip"),
                 ("Use of clip", "Next use of clip"), ("Mark the beat", "Mark the beats")])
first = next(n for _r, n, _g, label, *_k, part in tiles if part)
panel_._slide_way(first, 1)
tiles, _h, _b = panel_._layout(panel_._panel_rect())
check("...its arrow slides to the next way - and it's remembered", s.display["action_shown"] == {
    "Adjustment clip": "Adjustment clip over footage"} and "Adjustment clip over footage" in [t[3] for t in tiles])
panel_._slide_way(next(t[1] for t in tiles if t[3] == "Adjustment clip over footage"), -2)
check("...and goes round, either way", s.display["action_shown"]["Adjustment clip"] == "Adjustment clip at playhead")
w.favourite_action("Adjustment clip at playhead")
tiles, _h, _b = panel_._layout(panel_._panel_rect())
check("...a favourited one is a whole tile of its own in Favourites; the other two still share theirs",
      [(g, part is None) for _r, _n, g, label, *_k, part in tiles if label == "Adjustment clip at playhead"]
      == [("Favourites", True)]
      and [part["members"] for *_r, part in tiles if part and part["family"] == "Adjustment clip"]
      == [["Adjustment clip over clip", "Adjustment clip over footage"]])
w.favourite_action("Adjustment clip at playhead", False)
s.display["action_shown"] = {}
# -- a kind's own name and its plural reach it too: scripts:, macros:, bin:, markers: --
from clipse.clip_model import _build_prefix_maps  # noqa: E402
_c, _s, _e = _build_prefix_maps(s)
check("scripts:, macros:, nodes:, markers:, bins:, images: work as well as script:, macro: ...",
      _e.get("scripts") == "script" and _e.get("macros") == "macro" and _e.get("nodes") == "node"
      and _e.get("markers") == "marker" and _c.get("bins") == "bin" and _c.get("images") == "image"
      and "runs" not in _e and _s.get("s") == "staged")

# -- scripts: Lua as well as Python, each once, run inside Resolve the way its Scripts menu does --
import tempfile as _tf  # noqa: E402
from clipse import scripts_fusion as _sf  # noqa: E402
_root = _tf.mkdtemp()
os.makedirs(os.path.join(_root, "Utility"))
for _name in ("Utility/tidy.lua", "reveal.py", "notes.txt"):
    open(os.path.join(_root, _name), "w").close()
_found = sorted(n for _p, n, _w in _sf.scan_folders([_root, os.path.join(_root, "Utility")], {".py", ".lua"}))
check("scripts: lists Lua scripts too - and a folder inside another listed one only once", _found == ["reveal", "tidy"])
open(F.LOG, "w").close()
_sf.run_script(os.path.join(_root, "Utility/tidy.lua"), w.resolve)
check("...and runs them inside Resolve, as its Scripts menu does", "RUNSCRIPT" in open(F.LOG).read())

w.show(); w.open_picker(); _setup.pump(0.1)
w.search_edit.setText("scripts:"); _setup.pump(0.2)
_listed = [w.model.rows[i] for i in w.model.visible]
check("...Clipse's own scripts are in scripts: too, as their actions (Enter runs it)",
      {"Grab frame", "Swap clip", "Tidy up nodes"} <= {r.name for r in _listed if r.category == "action"})
w.search_edit.setText(""); _setup.pump(0.1)

# -- the prefix menu (":" on its own) and the pill --
w.show(); w.open_picker(); _setup.pump(0.1)
w.search_edit.setText(":"); _setup.pump(0.2)
_menu = [w.model.rows[i] for i in w.model.visible]
check("':' on its own lists every kind to search in - with what to type for it - Actions last",
      _menu[0].name == "Sounds" and _menu[0].folder_list == "a:  audio:" and _menu[-1].name == "Actions"
      and "Markers" in [r.name for r in _menu] and all(r.category == "prefix" for r in _menu))
w.search_edit.setText(":mark"); _setup.pump(0.2)
check("...typing after the colon narrows them", [w.model.rows[i].name for i in w.model.visible] == ["Markers"])
w.confirm(); _setup.pump(0.2)
check("...Enter searches in that kind: its pill in the search", w.search_edit.scope is not None
      and w.search_edit.scope[2] == "Markers" and w.search_edit.text() == "mk: "
      and all(w.model.rows[i].category == "marker" for i in w.model.visible))
w.search_edit.setText(""); _setup.pump(0.1)
from PySide6.QtWidgets import QLineEdit as _QLE  # noqa: E402
_QLE.setText(w.search_edit, "scripts:"); _setup.pump(0.2)
check("a prefix typed becomes the pill, the field empty after it", w.search_edit.scope[2] == "Scripts"
      and _QLE.text(w.search_edit) == "" and w.search_edit.text() == "scripts: ")
w.search_edit.event(QKeyEvent(QEvent.KeyPress, Qt.Key_Backspace, Qt.NoModifier)); _setup.pump(0.1)
check("...Backspace at the start takes it away again", w.search_edit.scope is None and w.search_edit.text() == "")
w.search_edit.setText("t: edit"); _setup.pump(0.1)
w.search_edit.drop_scope(); _setup.pump(0.1)
check("...and so does its x - what was typed after it stays", w.search_edit.scope is None and w.search_edit.text() == "edit")
w.search_edit.setText(""); _setup.pump(0.1)

# -- layout: Resolve's saved layouts; Enter switches (saving one from here was taken out, 2026-10-17) --
w.show(); w.open_picker(); _setup.pump(0.1)
w.search_edit.setText("layout:"); _setup.pump(0.2)
check("layout: lists Resolve's saved layouts - and nothing to save one with",
      [w.model.rows[i].name for i in w.model.visible] == ["Editing", "Colour big viewer"])
w.search_edit.setText("layout: Podcast"); _setup.pump(0.2)
check("...a name that isn't one finds nothing", not w.model.visible)
w.search_edit.setText("layout: editing"); _setup.pump(0.2)
open(F.LOG, "w").close()
w._do_external_action(); _setup.pump(0.1)
check("...Enter on one switches to it", "LAYOUT Editing" in open(F.LOG).read())
w.show(); w.open_picker(); _setup.pump(0.1)

# -- Ctrl+C: a file path wherever there is one, a node's name --
from PySide6.QtWidgets import QApplication as _QApp  # noqa: E402
w.show(); w.open_picker(); _setup.pump(0.1)
w.search_edit.setText("whoosh"); _setup.pump(0.2)
_path = w.model.rows[w._current_orig_index()].source
check("Ctrl+C on a clip copies its file's path (and the file, for a file manager)",
      w._copy_files() and _QApp.clipboard().text() == _path and _QApp.clipboard().mimeData().hasUrls())
_QApp.clipboard().clear()  # (as the app does when it quits: Qt crashes on exit holding files on the clipboard)
w.search_edit.setText(""); _setup.pump(0.1)
from clipse.help_text import ACTIONS as _HELP  # noqa: E402
check("every action says what it does when the mouse rests on it", all(
    _HELP.get(label) for g, label, _k, _f in w._actions() if g != "Insert as"))
check("hovering Actions in the bottom bar says its key",
      ("⌘K" if sys.platform == "darwin" else "Ctrl+K") in w.actions_link.toolTip())  # (a Mac's own way)
markers = []
real_actions = w._action_list
w._action_list = lambda: [(g, label, key, (lambda: markers.append(1)) if label == "Switch project\u2026" else fn)
                          for g, label, key, fn in real_actions()]
s.keybinds["act_switch_project"] = "Ctrl+Shift+M"
w.show(); w.open_picker(); _setup.pump(0.1)
key(Qt.Key_M, "M", Qt.ControlModifier | Qt.ShiftModifier)
check("an action given a key (Switch project: Ctrl+Shift+M) runs when it's pressed", markers == [1])
s.keybinds["act_switch_project"] = ""
w._action_list = real_actions
asked = []
w.open_settings = lambda page=None, key=None: asked.append(key)
w.actions_panel.open(); _setup.pump(0.3)
panel = w.actions_panel
tile = next((r, n, i) for r, n, i in panel._tiles if panel._shown[i][1] == "Picture only")
panel._change_key(panel._shown[tile[2]][2])
check("right-click a tile > Change key: Settings at that action's key", asked == ["insert_video_only"])
copied = []
real_copy, w._copy = w._copy, copied.append
panel._key_in_resolve("Clipse 03 - Grab Frame")
check("Grab frame is keyed in Resolve: no key in the picker, its script's name copied to find it there",
      "grab_still" not in s.keybinds and copied == ["Clipse 03 - Grab Frame"])
w._copy = real_copy
from PySide6.QtCore import QPoint as _QPoint  # noqa: E402
from clipse.preview_menu import MenuRow as _MenuRow  # noqa: E402
F.PAGE_NOW[0] = "fusion"
panel._visible_actions()
tidy = next(i for i, a in enumerate(panel._shown) if a[1] == "Tidy up nodes")
panel._key_menu(tidy, _QPoint(10, 10))
check("an action that's also a script in Resolve: right-click says Favourite and Key in Resolve, nothing else",
      [r.text for r in panel._menu.findChildren(_MenuRow)] == ["Favourite", "Key in Resolve\u2026"])
panel._menu.hide()
F.PAGE_NOW[0] = "edit"
panel._visible_actions()
empty = next(i for i, a in enumerate(panel._shown) if a[1] == "Remove empty tracks")
panel._key_menu(empty, _QPoint(10, 10))
check("Remove empty tracks is Resolve's own command: keyed there, by its name in Resolve",
      [r.text for r in panel._menu.findChildren(_MenuRow)] == ["Favourite", "Key in Resolve\u2026"]
      and _ap.key_places("Remove empty tracks", "") == [("resolve", "Delete Empty Tracks")])
render = next(i for i, a in enumerate(panel._shown) if a[1] == "Render\u2026")
panel._key_menu(render, _QPoint(10, 10))
check("an action only the picker has: Change key, and no Resolve", [r.text for r in panel._menu.findChildren(_MenuRow)]
      == ["Favourite", "Change key\u2026"])
panel._menu.hide()
panel._menu.hide()
del w.open_settings
from clipse.settings_dialog import SettingsDialog  # noqa: E402
dialog = SettingsDialog(s, w)
dialog.show(); _setup.pump(0.2)
dialog.go_to_key("act_switch_timeline")
_setup.pump(0.3)
_row = dialog._key_fields["act_switch_timeline"].parentWidget()
check("...Keybindings opens there with its row lit - but not listening for a key: that's a click on its box",
      dialog.page_title.text() == "Keybindings" and "SettingRow" in _row.styleSheet()
      and dialog.focusWidget() is not dialog._key_fields["act_switch_timeline"].edit)
dialog.close()

# -- a script in Resolve's menu: a right-click on it in the picker (it was Settings > Scripts) --
import tempfile as _tf  # noqa: E402
from clipse import resolve_shortcuts as _rs  # noqa: E402
_resolve_scripts = _tf.mkdtemp()
_utility, _mine = os.path.join(_resolve_scripts, "Utility"), _tf.mkdtemp()
_real = (_rs.utility_scripts_folder, _rs.default_scripts_folder)
_rs.utility_scripts_folder = lambda: _utility  # (never Resolve's real folder)
_rs.default_scripts_folder = lambda: os.path.join(_resolve_scripts, "Edit")
for _f in ("batch_rename.py", "make_proxies.lua"):
    open(os.path.join(_mine, _f), "w").write("print(1)\n")
os.makedirs(_utility)
open(os.path.join(_utility, "already_there.py"), "w").write("print(2)\n")


def _script_row(path):
    return rc.RowData("", "script", os.path.splitext(os.path.basename(path))[0], "", path=path)


def _menu(path):
    return [text for text, _g, _run in w._row_menu_choices(_script_row(path))]


_py, _lua = os.path.join(_mine, "batch_rename.py"), os.path.join(_mine, "make_proxies.lua")
check("right-click a script of yours: Add to Resolve's menu", _menu(_py) == ["Add to Resolve's menu"])
dict((t, run) for t, _g, run in w._row_menu_choices(_script_row(_py)))["Add to Resolve's menu"]()
dict((t, run) for t, _g, run in w._row_menu_choices(_script_row(_lua)))["Add to Resolve's menu"]()
check("...then it's there (a Lua one too): Key in Resolve..., or take it out again",
      _menu(_py) == _menu(_lua) == ["Key in Resolve\u2026", "Take out of Resolve's menu"]
      and "runpy" in open(os.path.join(_utility, "batch_rename.py")).read()
      and "dofile" in open(os.path.join(_utility, "make_proxies.lua")).read())
check("...and the launchers in Resolve's folder aren't listed as scripts of their own",
      sorted(n for _p, n, _par in sf.scan_folders([_mine, _resolve_scripts], {".py", ".lua"}))
      == ["already_there", "batch_rename", "make_proxies"])
dict((t, run) for t, _g, run in w._row_menu_choices(_script_row(_py)))["Take out of Resolve's menu"]()
check("...taken out, it can be added again", _menu(_py) == ["Add to Resolve's menu"]
      and not os.path.exists(os.path.join(_utility, "batch_rename.py")))
check("a script that's in Resolve's own folder already: only Key in Resolve...",
      _menu(os.path.join(_utility, "already_there.py")) == ["Key in Resolve\u2026"])
check("Clipse's own scripts (red rows): Key in Resolve..., with the name Resolve knows them by",
      [t for t, _g, _r in w._row_menu_choices(rc.RowData("", "action", "Grab frame", ""))] == ["Key in Resolve\u2026"]
      and not w._row_menu_choices(rc.RowData("", "video", "clip.mp4", "")))
check("the service puts back its scripts that went missing from Resolve's menu - and nothing when none are",
      len(_rs.put_back_missing()) == len(_rs.ACTIONS) and _rs.put_back_missing() == []
      and os.path.exists(os.path.join(_utility, "!Clipse", "Clipse - Open.lua")))
os.remove(os.path.join(_utility, "!Clipse", "Clipse 03 - Grab Frame.lua"))
check("...one deleted by hand comes back", _rs.put_back_missing() == ["Grab Frame"])
open(os.path.join(_utility, "davinci-search - Search.py"), "w").write("# made under the old name\n")
_rs.put_back_missing()
check("...and the scripts made under the app's old name go", not os.path.exists(
    os.path.join(_utility, "davinci-search - Search.py")))
open(os.path.join(_utility, "Clipse - Search.py"), "w").write("# before they were numbered\n")
open(os.path.join(_utility, "Clipse news.py"), "w").write("# somebody else's\n")
_rs.put_back_missing()
check("...those from before the numbers too - and a script of somebody else's that starts with Clipse stays",
      not os.path.exists(os.path.join(_utility, "Clipse - Search.py"))
      and os.path.exists(os.path.join(_utility, "Clipse news.py")))
# -- the launchers are Lua (2026-10-21): Resolve runs a .py from its menu only where Python is installed --
for _old in ("Clipse - Open.py", "Clipse 03 - Grab Frame.py"):  # (as every version before wrote them)
    open(os.path.join(_utility, _old), "w").write("# Clipse launcher - the Python one\n")
open(os.path.join(_utility, "Clipse - Mine.lua"), "w").write("-- somebody's own, named like ours\n")
_rs.put_back_missing()
_there, _ours = sorted(os.listdir(_utility)), sorted(os.listdir(os.path.join(_utility, "!Clipse")))
check("the scripts in Resolve's menu are Lua, in their folder - the Python ones before them, loose in Utility, go",
      "Clipse - Open.lua" in _ours and "Clipse 03 - Grab Frame.lua" in _ours
      and not any(n.startswith("Clipse") and n.endswith(".py") and n != "Clipse news.py" for n in _there)
      and len([n for n in _ours if n.endswith(".lua") and _rs._marked(os.path.join(_utility, "!Clipse", n))])
      == len(_rs.ACTIONS) + len(_rs.STAND_INS))  # (a stand-in keeps a taken-out script's place)
check("...and a .lua named like ours without the mark stays", "Clipse - Mine.lua" in _there)
_open = open(os.path.join(_utility, "!Clipse", "Clipse - Open.lua")).read()
check("...each sends its message, else starts the client: Open sends TRIGGER, Quit only starts the client",
      "local MESSAGE = [[TRIGGER]]" in _open and "local MESSAGE = nil" in open(
          os.path.join(_utility, "!Clipse", "Clipse - Quit.lua")).read() and "clipse.client" in _open)
import shutil as _shutil, subprocess as _subprocess  # noqa: E401,E402
if _shutil.which("luajit"):  # (LuaJIT is Resolve's Lua: every launcher has to read as Lua)
    _bad = [n for n in _ours if n.endswith(".lua") and _subprocess.run(
        ["luajit", "-b", os.path.join(_utility, "!Clipse", n), os.devnull], capture_output=True).returncode]  # (compiled, never run)
    check("...every one reads as Lua (LuaJIT, as Resolve's)", not _bad)
_numbered = [name for name, _m, _a in _rs.ACTIONS if name not in _rs.UNNUMBERED]
_numbers = [_rs.MENU_NUMBERS[name] for name in _numbered]
check("Resolve's menu: Open, Quit and Restart, then the rest numbered - each number once, 1 up, none missing "
      "but the ones taken out",
      sorted(_numbers + list(_rs.RETIRED_NUMBERS) + list(_rs.STAND_INS))
      == list(range(1, len(_numbers) + len(_rs.RETIRED_NUMBERS) + len(_rs.STAND_INS) + 1))
      and not set(_numbers) & (set(_rs.RETIRED_NUMBERS) | set(_rs.STAND_INS)) and set(_rs.MENU_NUMBERS) == set(_numbered)
      and set(_rs.UNNUMBERED) == {n for n, _m, _a in _rs.ACTIONS} - set(_numbered))
_menu_order = [_rs.menu_name(n) for n in _rs.UNNUMBERED] + [_rs.menu_name(n) for n in sorted(_numbered, key=_rs.MENU_NUMBERS.get)]
check("...sorted by name (either case) they're Open, Quit, Restart, then by number: a new one sorts last, no keys move",
      sorted(_menu_order) == _menu_order and sorted(_menu_order, key=str.lower) == _menu_order
      and _menu_order[:3] == ["Clipse - Open", "Clipse - Quit", "Clipse - Restart"])
check("every action keyed in Resolve names a script that's really in its menu",
      set(RESOLVE_KEYED.values()) <= {_rs.menu_name(n) for n, _m, _a in _rs.ACTIONS})
_rs.utility_scripts_folder, _rs.default_scripts_folder = _real

# -- Update on every system: the release file names each download, the Mac's app swapped in safely --
import io as _io, urllib.request as _ur  # noqa: E401,E402
from clipse import self_update as _su, updater as _up, install as _inst  # noqa: E402
_real_open = _ur.urlopen
_ur.urlopen = lambda req, timeout=0: _io.BytesIO(json.dumps({
    "version": "9.0.0", "page_url": "https://x/d", "windows_url": "https://x/w.exe", "windows_sha256": "ab",
    "mac_url": "https://x/m.dmg", "linux_url": "https://x/l"}).encode())
_rel = _up.fetch_latest()
_ur.urlopen = _real_open
check("the update check hands on every system's download and fingerprint (one it doesn't name: \"\")",
      _rel["windows_url"] == "https://x/w.exe" and _rel["windows_sha256"] == "ab" and _rel["mac_url"] == "https://x/m.dmg"
      and _rel["linux_url"] == "https://x/l")
check("...from Python, not installed, no update in place (pip's way, or the download page)",
      _su.kind() is None and not _su.can(_rel))
_mac = os.path.join(home, "Applications")
os.makedirs(os.path.join(_mac, "Clipse.app", "Contents"))
open(os.path.join(_mac, "Clipse.app", "Contents", "v"), "w").write("old")
os.makedirs(os.path.join(home, "mount", "Clipse.app", "Contents"))
open(os.path.join(home, "mount", "Clipse.app", "Contents", "v"), "w").write("new")
_su.swap_mac_app(os.path.join(home, "mount", "Clipse.app"), os.path.join(_mac, "Clipse.app"))
check("a Mac's update: the new Clipse.app in place, the old one kept aside (it may still be running)",
      open(os.path.join(_mac, "Clipse.app", "Contents", "v")).read() == "new"
      and open(os.path.join(_mac, _su.OLD_MAC_APP, "Contents", "v")).read() == "old")
try:
    _su.swap_mac_app(os.path.join(home, "mount", "Nothing.app"), os.path.join(_mac, "Clipse.app"))
    check("...a download with no app in it is refused", False)
except ValueError:
    check("...a download with no app in it is refused, the app there stays",
          open(os.path.join(_mac, "Clipse.app", "Contents", "v")).read() == "new")
_inst.note("Updated to 9.9.9")
_said = _inst.take_note()
_inst.note(f"Updated to {_inst.__version__}")
check("an update that didn't get as far as starting the new version says so - not \"Updated\"",
      "didn't finish" in _said and _inst.take_note() == f"Updated to {_inst.__version__}")

# -- a Mac's Clipse.app opened from the .dmg (macOS runs it from a folder that's gone after a restart): it goes
#    into Applications, as an AppImage goes into its place --
import plistlib as _plist  # noqa: E402


def _fake_app(where, version):
    os.makedirs(os.path.join(where, "Contents", "MacOS"), exist_ok=True)
    with open(os.path.join(where, "Contents", "Info.plist"), "wb") as f:
        _plist.dump({"CFBundleShortVersionString": version}, f)
    open(os.path.join(where, "Contents", "v"), "w").write(version)


_dmg = os.path.join(home, "Volumes", "Clipse", "Clipse.app")
_fake_app(_dmg, _inst.__version__)
_to = os.path.join(home, "Apps", "Clipse.app")
_real_mac = (_inst.mac_app, _inst.mac_target, _inst.mac_out_of_place)
_inst.mac_app, _inst.mac_target = (lambda: _dmg), (lambda: _to)
check("a Mac: Clipse.app in Applications is in its place, one on the .dmg or in Downloads isn't",
      not _real_mac[2]("/Applications/Clipse.app") and not _real_mac[2](os.path.expanduser("~/Applications/Clipse.app"))
      and _real_mac[2]("/Volumes/Clipse/Clipse.app") and _real_mac[2](os.path.expanduser("~/Downloads/Clipse.app"))
      and _real_mac[2]("/private/var/folders/x/T/AppTranslocation/E6/d/Clipse.app"))
check("...opened from the .dmg with none in Applications: it installs itself there", _inst.what_to_do() == "install")
_inst.place("install")
check("...it's there (its own version), and the picker says so once",
      _inst.mac_version(_to) == _inst.__version__ and _inst.take_note().startswith("Installed in Applications"))
check("...opened from the .dmg again, the same version: the one in Applications opens", _inst.what_to_do() == "open")
_fake_app(_to, "0.9.0")
check("...an older one in Applications: it's an update", _inst.what_to_do() == "update")
_inst.place("update")
check("...swapped in, the old one kept aside until the new one's first start",
      open(os.path.join(_to, "Contents", "v")).read() == _inst.__version__
      and os.path.isdir(os.path.join(os.path.dirname(_to), _su.OLD_MAC_APP))
      and _inst.take_note() == f"Updated to {_inst.__version__}")
_inst.mac_app = lambda: _to
_inst.mac_out_of_place = lambda bundle: False
check("...the one in Applications opened: nothing to do", _inst.what_to_do() is None)
_inst.mac_app, _inst.mac_target, _inst.mac_out_of_place = _real_mac
check("...and from Python (not a Clipse.app) none of this", _inst.mac_app() is None)

# -- crash reports: only a run that really crashed is sent, by itself, with home written ~ --
from clipse import crash_report as _cr, feedback as _fb  # noqa: E402
_pidf = os.path.join(home, "gone.pid")
check("a run that tidied up after itself (no PID file left) isn't a crash", not _cr.crashed(_pidf, "", None))
open(_pidf, "w").write("12345")
check("...one that left it is",
      _cr.crashed(_pidf, "10:00  Inserted 3 clips.\n", None))
check("...unless the screen went away (Sway closing at a shutdown)",
      not _cr.crashed(_pidf, "...\nThe Wayland connection broke. Did the Wayland compositor die?\n", None))
check("...or the computer started again since, with no sign of a crash in its log",
      not _cr.crashed(_pidf, "10:00  Inserted 3 clips.\n", time.time() + 60))
check("...but a crash the log shows counts, restarted or not",
      _cr.crashed(_pidf, "Fatal Python error: Segmentation fault\n", time.time() + 60))
check("in what's sent, the home folder is ~", _cr.private(f"{home}/Videos/a.mp4") == "~/Videos/a.mp4")
_posted, _real_post = [], _fb.post
_fb.post = lambda fields, files: _posted.append((fields, files))
open(_cr.PREVIOUS_LOG, "w").write(f"10:00  Read {home}/clip.mp4\nFatal Python error: Aborted\n")
_cr.note_at_start(_pidf)
for _ in range(50):
    if _posted:
        break
    time.sleep(0.05)
check("a crash is sent at the next start, nothing asked: its log, the home folder ~",
      _posted and _posted[0][0]["kind"] == "crash" and "Fatal Python error" in _posted[0][0]["text"]
      and home not in _posted[0][0]["text"] and _posted[0][1][0][1] == "logs.zip" and not os.path.exists(_cr.PENDING))
_fb.post = lambda fields, files: (_ for _ in ()).throw(RuntimeError("offline"))
_cr.note_at_start(_pidf)
time.sleep(0.3)
check("...offline it's kept for the next start", os.path.exists(_cr.PENDING))
_fb.post = lambda fields, files: _posted.append((fields, files))
s.general["send_crash_reports"] = False
s.save()
_cr.send_waiting(wait=True)
check("...and with Send crash reports off, nothing goes (what was kept is dropped)",
      len(_posted) == 1 and not os.path.exists(_cr.PENDING))
_cr.note_at_start(_pidf)
check("...nor is a new one kept", not os.path.exists(_cr.PENDING))
s.general["send_crash_reports"] = True
s.save()
_fb.post = _real_post
os.remove(_pidf)

check("Uninstall shows only where nothing else would take Clipse away (here: not installed)",
      not _inst.can_uninstall())

# -- the app opened by hand: set up, and the picker (never a click that does nothing) - compiled or not --
from clipse import autostart as _auto, launch as _launch, client as _client  # noqa: E402
check("from Python, opening the app is the client's --open; the service, the watcher as they were",
      _launch.command("app")[1:] == ["-m", "clipse.client", "--open"]
      and _launch.command("daemon")[1:] == ["-m", "clipse.daemon"])
_was = (_launch.COMPILED, _launch.program)
_launch.COMPILED, _launch.program = True, lambda: "/opt/ds/clipse"
check("compiled: opened by hand it's the program alone; the service --service, the others their switch",
      _launch.command("app") == ["/opt/ds/clipse"] and _launch.command("daemon") == ["/opt/ds/clipse", "--service"]
      and _launch.command("client", "grab") == ["/opt/ds/clipse", "--client", "grab"]
      and _launch.command("watcher") == ["/opt/ds/clipse", "--watcher"])
_launch.COMPILED, _launch.program = _was
check("...and only the service is taken for the service (a restart stops that one, never the others)",
      _client.is_service_command("/opt/ds/clipse --service ")
      and _client.is_service_command("/usr/bin/python3 -m clipse.daemon ")
      and not any(_client.is_service_command(c) for c in ("/opt/ds/clipse ", "/opt/ds/clipse --client ",
                                                           "/opt/ds/clipse --watcher ", "python3 -m clipse.client ")))
_entry_dir = _tf.mkdtemp()
_auto.APP_ENTRY = os.path.join(_entry_dir, "applications", "clipse.desktop")  # (never the real one)
_set, _ran = _auto.set_enabled, []
_auto.set_enabled = lambda on: _ran.append(on)  # (no watcher started from a test)
_main, _opened = _client.main, []
_client.main = lambda: _opened.append(True)
_who = _client.running_identity
_client.running_identity = lambda: None  # (never the real service on this computer's port)
s.general["app_set_up"] = False
s.save()
_client.open_app()
_entry = open(_auto.APP_ENTRY).read() if os.path.exists(_auto.APP_ENTRY) else ""
check("opened by hand: it opens the picker, starts at login from then on, and is among the apps with its icon",
      _opened == [True] and _ran == [True] and (
          "Exec=" in _entry and "--open" in _entry and "icon.png" in _entry
          and os.path.exists(_entry.split("Icon=")[1].split("\n")[0])
          if sys.platform.startswith("linux") else not _entry))  # (a Mac: Clipse.app; Windows: the Start menu)
_client.open_app()
check("...the second time: the picker again, the login start left as it is (turned off, it stays off)",
      _opened == [True, True] and _ran == [True])
_auto.set_enabled, _client.main, _client.running_identity = _set, _main, _who

# -- a Text+ on the Edit page: a row of its own in the list, not only under title: --
F.PAGE_NOW[0] = "edit"
rows = listed("text+")
text_row = next((i for i, r in enumerate(rows) if r.category == "title"), None)
check("on the Edit page, searching text+ finds a Title to add", text_row is not None and rows[text_row].name == "Title")


def enter_row(text, name):
    rows = listed(text)
    at = next((i for i, r in enumerate(rows) if r.name == name), None)
    if at is None:
        return False
    w.session["media_pool"], w.session["timeline"] = F.Pool(), F.TL()
    w._external_action_pending = False  # (a new opening)
    w.show()
    w.list_view.setCurrentIndex(w.model.index(at, 0))
    _setup.pump(0.05)
    w.confirm()
    _setup.pump(0.3)
    return True


def landed(name):
    return [(k, i) for k, lst in F.TRACKS.items() for i in lst if i.n == name]


def app_bin_clips():
    home = next((f for f in F.ROOT.subs if f.GetName() == "clipse"), None)
    return [c.GetName() for c in home.GetClipList()] if home else []


# Resolve's own title / generator inserts cut into V1 and push everything along: they come from the Media Pool instead
_v1 = F.TRACKS.get(("video", 1), [])
F.TRACKS[("video", 1)] = [F.Item("long take.mp4", 0, 900)]
enter_row("text+", "Title")
check("...Enter puts one at the playhead from the Media Pool - over a clip on V1, on a track that's free, as long as "
      "a picture lasts, kept in the clipse bin as text_plus",
      len(landed("text_plus")) == 1 and landed("text_plus")[0][0] != ("video", 1)
      and landed("text_plus")[0][1].b - landed("text_plus")[0][1].a == round(s.presets["still_length"] * 30)
      and F.TRACKS[("video", 1)][0].n == "long take.mp4" and app_bin_clips().count("text_plus") == 1)
enter_row("text+", "Title")
check("...the next one uses the same clip", len(landed("text_plus")) == 2 and app_bin_clips().count("text_plus") == 1)
F.TRACKS[("video", 1)] = _v1

# -- a solid colour the same way --
check("searching solid finds Solid colour", enter_row("solid", "Solid colour"))
check("...Enter puts one at the playhead, kept in the clipse bin",
      len(landed("solid_color")) == 1 and "solid_color" in app_bin_clips())
check("...and Undo knows it", w._undo_stack and w._undo_stack[-1]["label"] == "the solid colour")

# -- Basics: one place for what Resolve makes rather than your footage --
check("basics: lists Title, Solid colour, Adjustment clip, Fusion composition, each with its own symbol",
      [(r.name, r.glyph) for r in listed("basics: ")] == [("Title", "title"), ("Solid colour", "solid"),
                                                          ("Adjustment clip", "adjustment"), ("Fusion composition", "comp")])
check("...what's typed narrows them", [r.name for r in listed("basics: fus")] == ["Fusion composition"])
check("title: words - a Title with them", [(r.name, r.folder_list) for r in listed("title: Hello")] == [("Hello", "Add as Title")])
check("a plain search finds the Basics row, not the action that does the same",
      [r.name for r in listed("adjustment clip") if r.category in ("title", "action") and "playhead" in r.name.lower()
       or r.name == "Adjustment clip"] == ["Adjustment clip"])
_before = len([i for lst in F.TRACKS.values() for i in lst])
enter_row("basics: adjust", "Adjustment clip")
check("...Enter on it: an adjustment clip at the playhead, and Undo knows it",
      len([i for lst in F.TRACKS.values() for i in lst]) == _before + 1
      and w._undo_stack and w._undo_stack[-1]["label"] == "the adjustment clip")
listed("basics: solid")
w._preview_current()
check("...its preview shows its own symbol (not a title's T)", w.preview_panel.canvas.symbol == "solid")
from clipse import resolve_client as _rc
_rows, _g, _ids = _rc._build_rows(s, [("a1", "adjustment_clip", "clipse", "Generator", ("clipse",), "", "", 0, "", 0.0),
                                      ("g1", "drone_0m03s.png", "frame_grabs", "Still", ("clipse", "frame_grabs"), "", "", 0, "", 0.0),
                                      ("v1", "take.mp4", "footage", "Video", ("footage",), "", "", 0, "", 0.0)],
                                  [("clipse",), ("clipse", "frame_grabs"), ("footage",)])
check("the app's own clips in the clipse bin aren't listed (Basics places them), its frame grabs are",
      [r.name for r in _rows if r.category != "bin"] == ["drone_0m03s.png", "take.mp4"]
      and not any(r.name.startswith("clipse ") for r in _rows) and any(r.name.startswith("frame_grabs") for r in _rows))

from clipse import library
try:
    library.write_bin(os.path.join(os.path.expanduser("~"), "x.drb"), ("generator", "No Such Generator", ""))
    _made = True
except ValueError:
    _made = False
check("...no generator but Solid Color is ever made (an unknown one, placed, crashes Resolve)", not _made)

# -- a frame grab is named after the clip the frame is from, and where in it --
from clipse import stills as _st
F.UNDER_PLAYHEAD[0] = F.Item("Drone Mountains.mp4", 0, 300)
F.UNDER_PLAYHEAD[0].src = (2.0, 12.0)
check("a grab's name: the clip it's from, like_this, and where in that clip",
      _st.grab_name(F.TL()) == "drone_mountains_0m03s")
_drone = F.UNDER_PLAYHEAD[0]
_grabs = os.path.join(home, "Pictures", "Clipse")
F.FILES["drone_mountains_0m03s.png"] = os.path.join(_grabs, "P", "drone_mountains_0m03s.png")
_on_top = F.Item("drone_mountains_0m03s.png", 0, 150, F.MPI("drone_mountains_0m03s.png", "g1", "Still"))
_tracks = dict(F.TRACKS)
F.TRACKS[("video", 1)], F.TRACKS[("video", 2)] = [_drone], [_on_top]
F.UNDER_PLAYHEAD[0] = _on_top
check("...the grab before it on top (on the timeline over its clip): named after the clip underneath, not the grab",
      _st.grab_name(F.TL(), _grabs) == "drone_mountains_0m03s")
_adj = F.Item("adjustment_clip", 0, 300, F.MPI("adjustment_clip", "a1", "Generator"))
_adj.src = (3600.0, 3610.0)  # (a generator's own time starts at 01:00:00:00 - it was "adjustment_clip_1h00m01s")
F.TRACKS[("video", 3)] = [_adj]
F.UNDER_PLAYHEAD[0] = _adj
check("...an adjustment clip over it (and the grab): named after the footage underneath",
      _st.grab_name(F.TL(), _grabs) == "drone_mountains_0m03s")
F.TRACKS.clear()
F.TRACKS.update(_tracks)
del F.FILES["drone_mountains_0m03s.png"]
F.UNDER_PLAYHEAD[0] = None
check("...nothing under the playhead: the timeline's name and where on it", _st.grab_name(F.TL("Timeline 1")) == "timeline_1_0m01s")

F.PAGE_NOW[0] = "fusion"
w._watch_page()
listed("")
check("...not on the Fusion page (a Text+ is a node there)",
      not any(r.category == "title" for r in listed("text+")))
F.PAGE_NOW[0] = "edit"

# -- Copy timeline / Copy project: everything on a timeline as text with times --
F.TRACKS.clear()
F.TRACKS.update({("video", 1): [F.Item("av.mp4", 0, 100)], ("audio", 1): [F.Item("whoosh.wav", 30, 90)]})
text = commands.timeline_text(F.TL("Timeline 1", "TL", 1717))
check("timeline text: name, length, frame rate, size", text.startswith("Timeline: Timeline 1 (0:57.2 long, 30 fps, 1920x1080)"))
check("...a section per track, each clip with when it starts and ends",
      "Video 1" in text and "Audio 1" in text and " to " in text and "[00:00:" in text)
check("...the markers, with their timecode", "Markers:" in text and "- 0:01.0  [00:00:01:00]  Blue" in text)
check("...says so when there are no subtitles", "no subtitles" in text or "What's said:" in text)
every = commands.project_text(F.Project())
check("Copy project: the project, its settings and the open timeline", every.startswith("Project: P")
      and f"{len(F.TIMELINES)} timelines" in every and "Open timeline: " in every)
check("...the Media Pool's bins and clips", "Media Pool:" in every and "photo_1.jpg" in every)
check("...every timeline, the open one first", all(f"Timeline: {t.name} " in every for t in F.TIMELINES)
      and every.index(f"Timeline: {F.CURRENT[0].name} ") < min(every.index(f"Timeline: {t.name} ") for t in F.TIMELINES
                                                               if t.name != F.CURRENT[0].name))
check("markers text unchanged by the split", commands.markers_text(F.TL()).splitlines()[3] == "Markers:")
check("Copy transcript: nothing to copy without subtitles", commands.transcript_text(F.TL("Timeline 1", "TL", 1717)) is None
      or "Transcript:" in commands.transcript_text(F.TL("Timeline 1", "TL", 1717)))

print("\nall good" if not fails else f"\n{fails} FAILED")
raise SystemExit(1 if fails else 0)
