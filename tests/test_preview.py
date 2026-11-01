"""The preview beside the picker (the window makes room for it and keeps
that size) and the options behind its three dots - against the fake Resolve.
python3 tests/test_preview.py"""
import os

import _setup
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest

w, s, F = _setup.picker()
pp = w.preview_panel
# (it ships in its space - the first tests are about Next to it; In its space has its own further down)
s.listen.update(preview_place="side", preview_dock="side")
s.display["ui_scale"] = 1.15 / 1.4  # (the test screen is 800 wide: its sizes are picked for 1.15 - the picker's zoom,
#  1.4 as it ships, sizes nothing since 2026-10-21: Ctrl and + / - change only what's inside)
w.apply_theme()
fails = 0


def check(what, ok):
    global fails
    print(("ok   " if ok else "FAIL ") + what)
    fails += not ok


def handed(width, height):
    """The window system gives the window a size (as a Wayland compositor
    does along with the focus, or you dragging an edge) - not the picker."""
    w.windowHandle().resize(width, height)
    _setup.pump(0.05)


# -- the window's size: the picker decides it, and holds on to it --
picker_w, height = w.width(), w.height()
w.preview_clip()
_setup.pump(0.1)
both = picker_w + w._gap() + pp.width()
check("preview on: the window has room for the picker and the preview", w.width() == both)
handed(picker_w, height)  # what Wayland does: the size from before, along with the focus
check("handed the old size back: it takes its own again (no preview on top of the list)", w.width() == both)
check("...and the picker is as wide as it was", w.picker_column.width() == picker_w)
w.preview_clip()
_setup.pump(0.1)
check("preview off: just the picker again", w.width() == picker_w)
handed(both, height)
check("handed the wide size back: still just the picker", w.width() == picker_w)
w.preview_clip()
_setup.pump(0.1)
check("on again: the picker hasn't grown to the width of both",
      w.picker_column.width() == picker_w and w.width() == both)
w.toggle_big_preview(True)
_setup.pump(0.3)
handed(picker_w, height)
check("big view: the preview's place beside the picker is kept", w.width() == both)
w.toggle_big_preview(False)
_setup.pump(0.3)
check("back from the big view: beside the picker, with room", w.width() == both and w._preview_docked())
w._toggle_popout()
_setup.pump(0.1)
check("popped out: just the picker", w.width() == picker_w and w._popped_out())
w._toggle_popout()
handed(picker_w, height)
_setup.pump(0.1)
check("popped back in: room for both, whatever size comes back", w.width() == both and w._preview_docked())
w._resizing = True  # you, dragging an edge - that size is yours
w.preview_clip()
check("an edge drag from before doesn't stop it holding its size", not w._resizing)
w._wanted_until = 0.0  # ...a while later
w._resizing = True
handed(picker_w + 60, height + 40)
check("dragging an edge: the picker is the size you made it",
      (w.width(), w.height()) == (picker_w + 60, height + 40) and w._picker_w == picker_w + 60)
w._resizing = False
w.preview_clip()
_setup.pump(0.1)
check("...and the preview goes beside that", w.width() == picker_w + 60 + w._gap() + pp.width())

# -- the options behind the three dots --
def click(row):
    pp.open_menu()
    _setup.pump(0.05)
    QTest.mouseClick(row, Qt.LeftButton, Qt.NoModifier, QPoint(20, 8))
    _setup.pump(0.05)


def ticked():
    return [mode for mode, row in pp.space_rows.items() if row.checked]


w.search_edit.setText("whoosh")  # a sound effect: Auto starts those over
_setup.pump(0.3)
w._video_timer.stop()
check("what Space does: Auto to begin with, as in Settings", ticked() == ["auto"] and w._space_replays())
click(pp.space_rows["pause"])
check("picked Pause: Space pauses, and it's saved", ticked() == ["pause"] and not w._space_replays()
      and s.listen["space_action"] == "pause")
check("...the menu stays, so you see the tick move", pp.menu.isVisible())
click(pp.space_rows["replay"])
check("picked Start over: Space starts over - one or the other, never both",
      ticked() == ["replay"] and w._space_replays())
done = []
w.replay, w.play_pause = (lambda: done.append("start over")), (lambda: done.append("pause"))
w.space_play()
click(pp.space_rows["pause"])
w.space_play()
check("...and Space does what's ticked", done == ["start over", "pause"])
s.listen["space_action"] = "auto"
w.apply_theme()
check("changed in Settings: the tick follows", ticked() == ["auto"])
click(pp.loop_toggle)
check("a switch flips with a click, the menu stays open", pp.menu.isVisible() and s.listen["loop"] and pp.loop_toggle.checked)
click(pp.loop_toggle)
check("...and back", not s.listen["loop"] and not pp.loop_toggle.checked)
pp.menu.hide()
names = [type(pp.menu.box.itemAt(i).widget()).__name__ for i in range(pp.menu.box.count())]
check("the Space choice comes first, then a line, then the switches",
      names[:6] == ["MenuTitle", "MenuRow", "MenuRow", "MenuRow", "MenuRule", "MenuTitle"])
check("Stay open only shows when the preview is popped out", pp.stay_toggle.isHidden())

# -- the preview opens together with the picker (Settings -> Preview, or the three dots) --
w._wanted_until = 0.0
w.hide()
_setup.pump(0.1)
w.open_picker()
_setup.pump(0.2)
picker_w = w._picker_w
check("off: the picker opens alone, as always", not pp.isVisible() and w.width() == picker_w)
w.preview_clip()
_setup.pump(0.1)
click(pp.with_picker_toggle)
pp.menu.hide()
check("switched on in the options: it's saved", s.listen["preview_with_picker"] and pp.with_picker_toggle.checked)
w.hide()
_setup.pump(0.1)
check("they close together", not pp.isVisible() and not w.isVisible())
played = []
real_play = w.video.play
w.video.play = lambda path, autoplay=True: played.append(autoplay)
s.listen["autoplay"] = True
w.open_picker()
at_show = w.width()
_setup.pump(0.3)
both = picker_w + w._gap() + pp.width()
check("on: the picker opens with the preview beside it", w.isVisible() and pp.isVisible() and w._preview_docked())
check("...at its full size from the start, the picker as wide as ever",
      at_show == both == w.width() and w.picker_column.width() == picker_w)
check("...and typing still goes to the search", w.search_edit.hasFocus())
w.search_edit.setText("whoosh")
_setup.pump(0.5)
check("the first clip waits quietly, the next one plays (Autoplay)", played[:1] == [False] and played[-1] is True)
w.preview_clip()
_setup.pump(0.1)
check("closing just the preview still works", not pp.isVisible() and w.isVisible() and w.width() == picker_w)
w.open_picker()
_setup.pump(0.2)
check("the shortcut again while it's open doesn't bring the preview back", not pp.isVisible())
w.hide()
_setup.pump(0.1)
w.open_picker()
_setup.pump(0.3)
check("...the next time the picker opens, it's there again", pp.isVisible() and w.width() == both)
w.hide()
_setup.pump(0.1)
s.listen["preview_place"] = "window"
w.open_picker()
_setup.pump(0.3)
check("popped out: its own window opens with the picker", w._popped_out() and w.width() == picker_w)
w.hide()
_setup.pump(0.1)
check("...and closes with it", not w.preview_window.isVisible())
s.listen["preview_place"] = "side"
s.listen["preview_with_picker"] = False
w.apply_theme()
w.open_picker()
_setup.pump(0.2)
check("switched off in Settings: alone again, and the switch follows",
      not pp.isVisible() and not pp.with_picker_toggle.checked and w.width() == picker_w)

# -- One window: the preview inside the picker's window, its room taken from the list (2026-10-16) --
w.preview_clip()
_setup.pump(0.2)
edge = QPoint(w.width() - 2, w.height() // 2)
check("next to it, the preview open: the window's outer edge can be dragged", w._edges_at(edge) is not None)
pick_before, prev_before, wide_before = w.picker_column.width(), pp.width(), w.width()
QTest.mousePress(w, Qt.LeftButton, Qt.NoModifier, edge)  # (offscreen: no system resize - it's ours)
handed(wide_before - 100, w.height())
check("...dragged in: the list gives the room, the preview keeps its width",
      w.width() == wide_before - 100 and pp.width() == prev_before and w.picker_column.width() == pick_before - 100)
w._remember_position()
check("...and the list's width is kept for next time", s.display["window_width"] == pick_before - 100
      and w.picker_column.width() == pick_before - 100 and w._picker_w == pick_before - 100)
w._resizing = True
w.picker_column.setMinimumWidth(w._picker_min_width())
w.picker_column.setMaximumWidth(16777215)
kept_w, kept_prev = s.display["window_width"], s.listen["preview_width"]
handed(3000, w.height())  # a size the window system hands over (wider than the screen)
w._remember_position()
check("...a size wider than the screen isn't kept",
      s.display["window_width"] == kept_w and s.listen["preview_width"] == kept_prev)
w._resizing = False
w._set_size(780, w.height())  # (a size that fits the test screen, then the window system's turn)
_setup.pump(1.2)
pick1, prev1 = w.picker_column.width(), pp.width()
handed(700, w.height())  # Sway's Super + right-drag: the window resized from outside, smaller
check("resized from outside (Sway's Super + right-drag): it can get smaller, list and preview together",
      w.width() == 700 and w.picker_column.width() + w._gap() + pp.width() == 700
      and w.picker_column.width() < pick1 and pp.width() <= prev1)
handed(790, w.height())
check("...and bigger: both grow, nothing left empty", w.width() == 790
      and w.picker_column.width() + w._gap() + pp.width() == 790)
s.display["window_width"] = 0
w.preview_clip()
_setup.pump(0.1)
w.apply_theme()
_setup.pump(0.1)
w.preview_clip()
_setup.pump(0.1)
w.preview_clip()
_setup.pump(0.1)
w.hide()
_setup.pump(0.1)
s.listen["preview_place"] = "shared"
s.listen["preview_gap"] = 0  # (what One window was)
s.listen["preview_width"] = 0  # (as it ships - the steps before kept one)
w.open_picker()
_setup.pump(0.2)
w._set_size(760, w.height())  # (room for both, on the test's 800 px screen)
_setup.pump(0.2)
width0 = w.width()
w.preview_clip()
_setup.pump(0.2)
check("One window: the preview opens inside - the window keeps its size, the list makes room",
      pp.isVisible() and w.width() == width0 and w.picker_column.width() + pp.width() == width0 and w._gap() == 0)
seam = w.seam_handle
check("...the line between them can be grabbed", seam.isVisible()
      and seam.geometry().left() < pp.geometry().left() < seam.geometry().right())
shot = w.grab().toImage()
ratio = shot.devicePixelRatio()
check("...and it's one card (no screen showing between the two)",
      shot.pixelColor(round(pp.geometry().left() * ratio), round(w.height() / 2 * ratio)).alpha() == 255)
pick0, prev0 = w.picker_column.width(), pp.width()
w._seam_dragged(70, w._seam_start())
_setup.pump(0.1)
check("the line dragged right: the list grows into the preview, the window stays",
      w.width() == width0 and pp.width() == prev0 - 70 and w.picker_column.width() == pick0 + 70)
w._seam_dragged(-50, w._seam_start())
_setup.pump(0.1)
check("...and left: the preview grows into the list", w.width() == width0 and pp.width() == prev0 - 20)
w._seam_dragged(-5000, w._seam_start())
_setup.pump(0.1)
check("...never past the list's smallest", w.picker_column.width() == w._picker_min_width() and w.width() == width0)
w._seam_dragged(5000, w._seam_start())
_setup.pump(0.1)
check("...nor the preview's", pp.width() == w._preview_min_width() and w.width() == width0)
w._seam_dragged(-30, w._seam_start())
_setup.pump(0.1)
w._remember_split()
kept = pp.width()
w.preview_clip()
_setup.pump(0.2)
check("preview off: the list takes its room back, the window stays",
      not pp.isVisible() and w.width() == width0 and w.picker_column.width() == width0)
w.preview_clip()
_setup.pump(0.2)
check("...on again: the preview the width it was dragged to", pp.width() == kept and w.width() == width0)
w._resizing = True
handed(width0 + 30, w.height())  # an outer edge dragged 30 px out
check("an outer edge dragged: the window grows, the list and the preview with it, each its share",
      w.width() == width0 + 30 and pp.width() > kept and w.picker_column.width() + pp.width() == width0 + 30
      and abs(pp.width() / (width0 + 30) - kept / width0) < 0.02)
w._remember_position()
check("...and the window's size is kept for next time", s.display["window_width"] == width0 + 30)
w._toggle_popout()
_setup.pump(0.2)
check("popped out", w._popped_out() and s.listen["preview_place"] == "window")
w._toggle_popout()
_setup.pump(0.2)
check("...and back in: in its space again", s.listen["preview_place"] == "shared" and w._preview_docked()
      and w.width() == width0 + 30)
w.preview_clip()
_setup.pump(0.1)
w._set_size(500, w.height())
_setup.pump(0.2)
w.preview_clip()
_setup.pump(0.2)
least = w._picker_min_width() + w._preview_min_width()
check("a window too narrow for both: it grows just enough", w.width() == least and pp.isVisible())
w.preview_clip()
_setup.pump(0.2)
check("...and goes back when the preview closes", w.width() == 500)

# -- Beside, in the picker's space: the card and its gap as beside, the room taken from the list --
s.listen["preview_place"] = "shared"
s.listen["preview_gap"] = 12
w._set_size(760, w.height())
_setup.pump(0.2)
width0 = w.width()
w.preview_clip()
_setup.pump(0.2)
check("beside in its space: the window keeps its size, the list makes room - with the gap between the cards",
      pp.isVisible() and w.width() == width0 and w._gap() == w.PREVIEW_GAP
      and w.picker_column.width() + w.PREVIEW_GAP + pp.width() == width0)
shot = w.grab().toImage()
ratio = shot.devicePixelRatio()
middle = (w.picker_column.geometry().right() + pp.geometry().left()) / 2
check("...two cards: the screen shows through the gap",
      shot.pixelColor(round(middle * ratio), round(w.height() / 2 * ratio)).alpha() == 0)
pick0, prev0 = w.picker_column.width(), pp.width()
w._seam_dragged(-40, w._seam_start())
_setup.pump(0.1)
check("...the gap dragged: they trade width, the window stays",
      w.width() == width0 and pp.width() == prev0 + 40 and w.picker_column.width() == pick0 - 40)
check("...the window's own edges resize it", w._edges_at(QPoint(w.width() - 2, w.height() // 2)) is not None)
w.preview_clip()
_setup.pump(0.2)
check("...closed: the list has its room back", w.width() == width0 and w.picker_column.width() == width0)

# -- Settings > Preview: the drawing to choose where it opens, and the gap --
from clipse.preview_place import PreviewPlace  # noqa: E402
w.preview_clip()
_setup.pump(0.2)
pick0, prev0 = w.picker_column.width(), pp.width()
s.listen["preview_gap"] = 20
w.apply_theme()
_setup.pump(0.2)
check("the gap changed with the preview open: in its space, the list gives up the room, the preview stays",
      pp.width() == prev0 and w.layout().spacing() == 20 and w.picker_column.width() + 20 + pp.width() == w.width())
w.preview_clip()
_setup.pump(0.2)
chooser = PreviewPlace(s)
seen = []
chooser.changed.connect(lambda where, gap: seen.append((where, gap)))
chooser.resize(700, chooser.sizeHint().height())
chooser.show()
_setup.pump(0.1)
check("the chooser starts where the setting is", chooser.tiles.current == "shared" and chooser.slider.value == 20)
chooser.tiles._pick(0)
check("a tile picked: Next to it", seen[-1] == ("side", 20) and chooser.scene.place == "side")
chooser.tiles._pick(2)
check("...A window of its own: no gap to set", seen[-1][0] == "window" and chooser.slider.isHidden())
chooser.tiles._pick(1)
chooser.slider.setValue(4)
check("the slider: the gap", seen[-1] == ("shared", 4) and chooser.scene.gap == 4)
chooser.scene._share = 1.0
_scale, pick_r, prev_r, _whole = chooser.scene._layout()
middle = QPoint(round((pick_r.right() + prev_r.left()) / 2), round(pick_r.center().y()))
QTest.mousePress(chooser.scene, Qt.LeftButton, Qt.NoModifier, middle)
QTest.mouseMove(chooser.scene, middle + QPoint(round(10 * _scale) + 1, 0))
chooser.scene.mouseMoveEvent(type("E", (), {"position": lambda self: (middle + QPoint(round(10 * _scale) + 1, 0)).toPointF(),
                                            "buttons": lambda self: Qt.LeftButton})())
QTest.mouseRelease(chooser.scene, Qt.LeftButton, Qt.NoModifier, middle)
check("...or the gap dragged in the drawing, the slider follows", seen[-1][1] > 4 and chooser.slider.value == seen[-1][1])
grabbed = chooser.grab()
check("...and it draws", not grabbed.isNull())
chooser.close()
w.preview_clip()
_setup.pump(0.1)
s.listen["preview_place"] = "side"
s.listen["preview_width"] = 0
s.display["window_width"] = 0
w.apply_theme()
_setup.pump(0.1)
w.video.play = real_play

# -- the macro visualiser: what's inside a .setting file, readably --
from clipse import fusion_graph as fg

MACRO = """{ Tools = ordered() {
  my_glitch = GroupOperator {
    Inputs = ordered() {
      MainInput1 = InstanceInput { SourceOp = "Transform1", Source = "Input", },
      Text1_StyledText = InstanceInput { SourceOp = "Text1", Source = "StyledText", },
      Blur1_Size = InstanceInput { SourceOp = "Blur1", Source = "XBlurSize", Name = "Softness", },
    },
    Outputs = { MainOutput1 = InstanceOutput { SourceOp = "Merge1", Source = "Output", }, },
    ViewInfo = GroupInfo { Pos = { 0, 0 } },
    Tools = ordered() {
      Transform1 = Transform { Inputs = { Size = Input { SourceOp = "Transform1Size", Source = "Value", },
                                           Center = Input { SourceOp = "Path1", Source = "Position", }, },
                               ViewInfo = OperatorInfo { Pos = { 0, 0 } }, },
      Transform1Size = BezierSpline { KeyFrames = { [0] = { 1 }, [20] = { 1.4 } } },
      Path1 = PolyPath { Inputs = { Displacement = Input { SourceOp = "Path1Displacement", Source = "Value", }, }, },
      Path1Displacement = BezierSpline { },
      Shake1 = Shake { },
      Blur1 = ofx.com.blackmagicdesign.resolvefx.MosaicBlur { Inputs = { Source = Input { SourceOp = "Transform1", Source = "Output", },
                                           Amount = Input { SourceOp = "Shake1", Source = "Position", }, },
                               ViewInfo = OperatorInfo { Pos = { 110, 0 } }, },
      Elbow = PipeRouter { Inputs = { Input = Input { SourceOp = "Blur1", Source = "Output", }, },
                           ViewInfo = PipeRouterInfo { Pos = { 220, 0 } }, },
      Text1 = TextPlus { Inputs = { StyledText = Input { Value = "SUBSCRIBE", }, Font = Input { Value = "Inter", }, },
                         ViewInfo = OperatorInfo { Pos = { 220, 60 } }, },
      Merge1 = Merge { Inputs = { Background = Input { SourceOp = "Elbow", Source = "Output", },
                                  Foreground = Input { SourceOp = "Text1", Source = "Output", }, },
                       ViewInfo = OperatorInfo { Pos = { 330, 0 } }, },
    },
  },
  StrayCurve = BezierSpline { },
} }"""
g = fg.parse(MACRO)
node_names = [n for n, _k, _p in g["nodes"]]
check("a macro is opened, even with a keyframe curve saved beside it", g["kind"] == "group"
      and node_names == ["Transform1", "Blur1", "Text1", "Merge1"])
check("keyframe curves, paths and shakes aren't nodes - the node they move is marked instead",
      g["animated"] == {"Transform1": {"keyframes", "a path"}, "Blur1": {"shake"}})
check("a wire elbow is left out: the wire goes straight on", ("Blur1", "Merge1", "Background") in g["edges"]
      and "Elbow" not in node_names)
check("a node Fusion named is called what it is, one you named keeps its name",
      g["labels"]["Transform1"] == "Transform" and fg.label("MosaicBlur1_2", "ofx.x.MosaicBlur") == "Mosaic Blur"
      and fg.label("TitleBar", "Background") == "TitleBar" and fg.label("JPEGDamage1", "ofx.x.JPEGDamage") == "JPEG Damage")
check("the controls it gives you, by the names they show", g["controls"] == ["Styled Text", "Softness"])
check("in a line: how big, what moves, what it needs, what it uses",
      fg.describe(g) == "4 nodes  ·  animated: keyframes, a path, shake  ·  goes on a clip  ·  Mosaic Blur  ·  font: Inter"
      and g["texts"] == ["SUBSCRIBE"])
place = fg.arrange(g, 8)
check("its own layout: the main line left to right, the title under the node before the one it joins",
      [place[n][:2] for n in ("Transform1", "Blur1", "Merge1")] == [(0, 0), (1, 0), (2, 0)] and place["Text1"][:2] == (1, 1))
long_chain = {"nodes": [(f"N{i}", "Blur", None) for i in range(11)],
              "edges": [(f"N{i}", f"N{i + 1}", "Input") for i in range(10)]}
place = fg.arrange(long_chain, 4)
check("a long line carries on underneath instead of being squeezed", max(b for _c, _r, b in place.values()) == 2
      and max(c for c, _r, _b in place.values()) <= 3 and len(set(place.values())) == 11)
import tempfile
folder = tempfile.mkdtemp()
with open(os.path.join(folder, "my_glitch.setting"), "w") as f:
    f.write(MACRO)
from PySide6.QtGui import QImage, QPainter
QImage(8, 8, QImage.Format_RGB32).save(os.path.join(folder, "my_glitch.png"))
g = fg.load(os.path.join(folder, "my_glitch.setting"))
check("a picture with the macro's name beside it is found", g["picture"].endswith("my_glitch.png"))
canvas = QImage(460, 300, QImage.Format_ARGB32)
painter = QPainter(canvas)
fg.draw(painter, canvas.rect().toRectF(), g, s, w.font())
fg.draw(painter, canvas.rect().toRectF(), dict(long_chain, controls=[], animated={}, labels={}), s, w.font())
painter.end()
check("it draws (with the picture, and a long plain chain) without a hitch", True)
check("a file that isn't a macro at all is left alone", fg.parse("this is not lua") is None and fg.parse("{ Tools = {} }") is None)

# -- parts of a clip that are on the timeline already --
from clipse import timeline_tools as tt
clip = next(c for c in F.MUSIC.GetClipList() if c.GetName() == "B-roll 001.mp4")
other = next(c for c in F.MUSIC.GetClipList() if c.GetName() == "B-roll 002.mp4")
F.TRACKS.clear()
uses = [F.Item("B-roll 001.mp4", 0, 90, clip), F.Item("B-roll 001.mp4", 300, 420, clip),
        F.Item("B-roll 001.mp4", 500, 560, clip), F.Item("B-roll 002.mp4", 90, 200, other), F.Item("Text+", 0, 50)]
for item, part in zip(uses, ((1.0, 4.0), (10.0, 14.0), (3.5, 5.5), (0.0, 3.0), None)):
    if part:
        item.src = part
F.TRACKS[("video", 1)] = uses[:2] + uses[3:]
F.TRACKS[("video", 2)] = [uses[2]]
F.TRACKS[("audio", 1)] = [F.Item("B-roll 001.mp4", 0, 90, clip)]  # its own sound: the same part, not a second use
F.TRACKS[("audio", 1)][0].src = (1.0, 4.0)
reader = tt.UsedParts(F.CURRENT[0])
steps = 0
while not reader.step(0.0) and steps < 50:  # a little at a time
    steps += 1
check("the timeline is read a little at a time", reader.done and steps >= 4)
check("which parts of a clip are used: overlapping ones joined, its own sound not counted twice",
      reader.of([clip.GetMediaId()]) == ([(1.0, 5.5), (10.0, 14.0)], 3))
check("...per clip; titles and the like are passed over", reader.of([other.GetMediaId()]) == ([(0.0, 3.0)], 1)
      and reader.of(["nothing"]) == ([], 0))
w.hide()
_setup.pump(0.1)
w.open_picker()
_setup.pump(0.2)
if not pp.isVisible():
    w.preview_clip()
w.search_edit.setText("B-roll 001")
_setup.pump(0.6)
check("the preview marks them for the highlighted clip", pp.canvas.used == [(1.0, 5.5), (10.0, 14.0)]
      and pp.canvas.used_times == 3)
w.search_edit.setText("B-roll 000")
_setup.pump(0.6)
check("a clip that isn't on the timeline has no marks", pp.canvas.used == [] and pp.canvas.used_times == 0)
s.listen["show_used_parts"] = False
w.search_edit.setText("B-roll 001")
_setup.pump(0.6)
check("switched off in Settings: no marks", pp.canvas.used == [])
s.listen["show_used_parts"] = True
F.TRACKS.clear()

# Ctrl+R with a picture in the preview: once the list is rebuilt the picture is shown again (it used to stay
# empty until you moved off the clip and back)
import tempfile  # noqa: E402
from PySide6.QtGui import QImage as _QImage  # noqa: E402
picture = os.path.join(tempfile.mkdtemp(), "still.png")
_QImage(64, 36, _QImage.Format_RGB32).save(picture)
real_path = w._row_file_path
w._row_file_path = lambda orig: picture
w.search_edit.setText("B-roll 001")
_setup.pump(0.3)
w._preview_current()
_setup.pump(0.3)
shown = pp.canvas.image is not None
w._install_rows(w.session["rows"], w.session["filtered_group_list"], w.session["id_paths"])
_setup.pump(0.6)
check("the list rebuilt under the clip (a rescan): its picture is shown again", shown and pp.canvas.image is not None)
w._row_file_path = real_path
w.video.stop()

# Expressions open: the preview shows the node its pieces point at, and goes back to the clip after
from PySide6.QtCore import QPointF  # noqa: E402
from clipse import node_settings as ns  # noqa: E402
w.search_edit.setText("B-roll 001")
_setup.pump(0.4)
w._show_cheat_sheet()
_setup.pump(0.2)
w.expression_sheet._watch.stop()
check("Expressions open: the preview has no clip and no play bar, only a node (none selected here)",
      pp.isVisible() and pp.canvas.node_view is not None and pp.canvas.node_view.node in ("", "away")
      and pp.footer.isHidden())
node = {"name": "Merge1", "kind": "Merge", "pages": [("Merge", [
    {"id": "Center", "label": "Center", "kind": "point"}, {"id": "Overlap1", "label": "Blending 1", "kind": "number"}]),
    ("Text", [{"id": "StyledText", "label": "Styled Text", "kind": "text"}])]}
view = pp.canvas.node_view = ns.NodeView(node, {"Center": "0.5, 0.5", "Overlap1": "2", "StyledText": "Hi"})
pp.canvas.grab()  # (painted: where everything is)
copied = sorted({text for _rect, text in view._spots})
check("a setting copies as an expression writes it - a position's X and Y too, a text's .Value",
      copied == ["Merge1", "Merge1.Center", "Merge1.Center.X", "Merge1.Center.Y", "Merge1.Overlap1",
                 "Merge1.StyledText.Value"])
row = next(r for r, t in view._spots if t == "Merge1.Overlap1")
x_spot = next(r for r, t in view._spots if t == "Merge1.Center.X")
check("a click on a row copies the row; on its X, the X",
      view.click(row.center()) == "Merge1.Overlap1" and view.click(x_spot.center()) == "Merge1.Center.X")
w.expression_sheet.close_sheet()
_setup.pump(0.3)
check("Expressions closed: the clip is back in the preview, with its bar",
      pp.canvas.node_view is None and pp.footer.isVisible() and pp.canvas.title.startswith("B-roll 001"))

# -- in / out while scrubbing: where the mouse is, not where it plays --
v, c = w.video, pp.canvas
was = (v.current_path, v.is_video, v.position, c.duration, w._apply_range)
v.current_path, v.is_video, v.position, c.duration = "/nowhere/scrub.mp4", True, 2.0, 10.0
w._apply_range = lambda path: None
c.scrub_x, c.scrub_seconds = 50.0, 6.5
w._mark("in")
check("in while scrubbing: where the mouse is (6.5 s), not where it plays (2 s)", c.mark_in == 6.5)
c.scrub_x = None
w._mark("out")
check("not scrubbing: where it plays - an out before the in starts a new range",
      c.mark_in is None and c.mark_out == 2.0)
c.scrub_x, c.scrub_seconds = 50.0, 1.0
w._mark("in")
c.scrub_x, c.scrub_seconds = 80.0, 4.0
w._mark("out")
check("in and out both from the mouse while scrubbing", (c.mark_in, c.mark_out) == (1.0, 4.0))
w._mark(None)
c.scrub_x = None
v.current_path, v.is_video, v.position, c.duration, w._apply_range = was

# -- Ctrl and + / -: what's inside grows, the window stays as it is (2026-10-21: "the zoom is only supposed to make
#    the pickers inside be smaller, adjust the size should only be done in settings and by dragging the sides") --
from clipse.fonts import picker_scale as _inside  # noqa: E402
w.hide()
_setup.pump(0.1)
w.open_picker()
_setup.pump(0.2)
_size, _was = (w.width(), w.height()), _inside(s)
w.zoom_window(1)
_setup.pump(0.2)
_grown = (w.width(), w.height()), _inside(s)
w.zoom_window(-1)
w.zoom_window(-1)
_setup.pump(0.2)
_shrunk = (w.width(), w.height()), _inside(s)
w.zoom_window(0)
_setup.pump(0.2)
check("Ctrl and +: what's inside bigger, the window the same size - and Ctrl and -: smaller, the same size",
      _grown[0] == _size and _grown[1] > _was and _shrunk[0] == _size and _shrunk[1] < _was)
w.windowHandle().resize(w.width() - 60, w.height() - 40)  # (an edge dragged - or Sway's Super + right-drag)
_setup.pump(0.3)
_size = (w.width(), w.height())
w.zoom_window(1)
_setup.pump(0.3)
_kept = (w.width(), w.height())
w.zoom_window(0)
_setup.pump(0.3)
w.hide()
_setup.pump(0.1)
w.open_picker()
_setup.pump(0.3)
check("...a size you gave it stays too, and it opens with it next time (zooming went back to the automatic size)",
      _kept == _size and (w.width(), w.height()) == _size)
w.hide()
_setup.pump(0.1)

# -- Insert as in the picker's place, the keyboard still in the search: Ctrl and + zooms Insert as - all of it -
#    not the picker (only Insert as's words changed: "I have to click on an empty space", 2026-10-21) --
from PySide6.QtCore import QTimer as _QTimer  # noqa: E402
from PySide6.QtTest import QTest as _QTest  # noqa: E402
_seen = {}


def _zoom_inside():
    from clipse.insert_as_dialog import FramePad
    d = w._placed
    pad = d.findChildren(FramePad)[0].width()
    picker_zoom = dict(s.display.get("zoom") or {}).get("picker")
    w.search_edit.setFocus()
    _setup.pump(0.1)
    _QTest.keyClick(w.search_edit, Qt.Key_Equal, Qt.ControlModifier)
    _setup.pump(0.3)
    _seen.update(grew=d.findChildren(FramePad)[0].width() > pad,
                 picker_same=dict(s.display.get("zoom") or {}).get("picker") == picker_zoom)
    d.zoom_window(0)
    d.reject()


w.open_picker()
_setup.pump(0.2)
_QTimer.singleShot(600, _zoom_inside)
w.open_insert_options()
check("Insert as in the picker's place, the keyboard in the search: Ctrl and + zooms all of Insert as, not the picker",
      _seen.get("grew") and _seen.get("picker_same"))


# Expressions open, its preview in the picker's space, the window dragged wider: closing the preview keeps that
# width (it went back to the size from before the drag), and Expressions fills the list's room (it lay over the preview)
from PySide6.QtGui import QKeyEvent as _QKeyEvent  # noqa: E402
from PySide6.QtCore import QEvent as _QEvent  # noqa: E402
s.listen.update(preview_place="shared", preview_gap=0)
s.display["expressions_preview"] = True
w.open_picker()
_setup.pump(0.2)
if pp.isVisible():
    w._close_preview()
w._show_cheat_sheet()
_setup.pump(0.3)
w.expression_sheet._watch.stop()
_setup.pump(1.2)  # (past the time it holds on to its own size)
w._resizing = True
handed(w.width() + 300, w.height())
_setup.pump(0.2)
dragged = w.width()
check("Expressions, window dragged wider: the sheet covers the list only, not the preview",
      w.expression_sheet.geometry() == w.picker_column.geometry())
w.handle_action_key(_QKeyEvent(_QEvent.KeyPress, Qt.Key_P, Qt.ControlModifier | Qt.ShiftModifier))
_setup.pump(0.3)
check("...the preview closed there: the window keeps the dragged width, Expressions fills it",
      not pp.isVisible() and w.width() == dragged and w.expression_sheet.width() == dragged)
w.handle_action_key(_QKeyEvent(_QEvent.KeyPress, Qt.Key_P, Qt.ControlModifier | Qt.ShiftModifier))
_setup.pump(0.3)
w.expression_sheet.close_sheet()
_setup.pump(0.2)

print("\nall good" if not fails else f"\n{fails} FAILED")
raise SystemExit(1 if fails else 0)
