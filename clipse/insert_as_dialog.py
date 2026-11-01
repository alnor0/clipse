"""Insert as - the presets for how clips land on the timeline (presets.py
has what they mean). Each preset is a tile with a little drawing of what
it does; pick one and Enter in the picker inserts with it. Below the
tiles, the picked preset can be changed: where, how several clips are
spaced (with a curve you drag), each clip's length and place in the
frame, and what happens afterwards.

Built-in presets can be changed and reset; Duplicate makes one of your
own to name. Changes are saved as you make them."""
import copy
import math
import time

from PySide6.QtCore import QEvent, QObject, QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QKeySequence, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QAbstractSpinBox, QCheckBox, QDialog, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea,
                               QSizePolicy, QVBoxLayout, QWidget)

from . import look
from . import presets as pm
from .drag_spinbox import DragDoubleSpinBox, DragSpinBox
from .settings_cards import Card, FreeRow, Section, SettingRow
from .symbols import draw_symbol
from .fonts import SMALL, TINY, at as font_at, rel, window_zoom  # (the one scale of sizes)


_REL = [0.85 / 1.15]  # Insert as's text over the picker's (fonts.rel) - set when it opens and zooms


def _f(step=1.0, font=None, weight=None):
    """A font on the scale, in Insert as - at its own zoom (fonts.window_zoom "insert_as")."""
    return font_at(step * _REL[0], font, weight)


# Insert as's sizes over how it ships - its zoom, Settings' text size and UI scale: everything in it grows and
# shrinks together, not only the words (2026-10-21: "it is like it is only the font that becomes smaller") - set
# when it opens and zooms
_K = [1.0]


def size_of(settings):
    from .fonts import WINDOW_ZOOM, zoom
    return zoom(settings) * window_zoom(settings, "insert_as") / WINDOW_ZOOM["insert_as"]


def _px(n):
    """A size in Insert as at its zoom - `n` the size as it ships."""
    return int(round(n * _K[0]))


def _card(settings):
    return Card(settings, scale=_K[0])


def _free_row(content):
    return FreeRow(content, scale=_K[0])


def _section(title, card):
    return Section(title, card, scale=_K[0])


def _setting_row(title_widget, description, control, muted):
    return SettingRow(title_widget, description, control, muted, scale=_K[0])


def _switch(settings, box):
    """An on / off switch at Insert as's size (Vicinae's 34 x 18 as it ships)."""
    from .settings_cards import ToggleSwitch
    switch = ToggleSwitch(settings, box)
    switch.setFixedSize(_px(34), _px(18))
    return switch


def _fd(step=1.0, font=None, weight=None):
    """A font in a drawing (_Scaled): the size as it ships - its painter grows it with the rest."""
    return font_at(step * _REL[0] / _K[0], font, weight)


class _Scaled:
    """A drawing made at Insert as's size as it ships, drawn at its zoom: the painter is scaled, and it measures
    itself (_w, _h) and the mouse (_mouse) in its own units."""

    def _w(self):
        return self.width() / _K[0]

    def _h(self):
        return self.height() / _K[0]

    @staticmethod
    def _mouse(event):
        return event.position() / _K[0]

    @staticmethod
    def _painter(widget):
        p = QPainter(widget)
        p.scale(_K[0], _K[0])
        return p


def _colors(t):
    return {
        "text": QColor(t["picker_text"]), "muted": QColor(t["picker_folder"]),
        "border": QColor(t["picker_border"]), "accent": QColor(t.get("picker_accent", t["picker_text"])),
        "video": QColor(t["color_video"]), "audio": QColor(t["color_audio"]),
        "bg": QColor(t["picker_bg"]), "bar": QColor(t.get("picker_bar_bg", t["picker_bg"])),
        "compound": QColor(t["color_compound"]), "comp": QColor(t["color_comp"]),
    }


def _alpha(color, a):
    c = QColor(color)
    c.setAlphaF(a)
    return c


# -- the drawings --
def _block(p, rect, preset, c, natural=True):
    """One clip: a bar in its kind's colour (a sound underneath if it has one)."""
    fill = QColor(pm.COLOUR_HEX.get(preset["colour"], "")) if preset["colour"] else None
    media = preset["media"]
    main = c["audio"] if media == "audio" else c["video"]
    if fill is not None and fill.isValid():
        main = fill
    radius = min(2.5, rect.height() / 3)
    p.setPen(Qt.NoPen)
    if media == "both":
        top = QRectF(rect.left(), rect.top(), rect.width(), rect.height() * 0.62)
        under = QRectF(rect.left(), top.bottom() + rect.height() * 0.1, rect.width(), rect.height() * 0.28)
        _slab(p, top, main, radius)
        p.setBrush(_alpha(c["audio"], 0.8))
        p.drawRoundedRect(under, radius * 0.7, radius * 0.7)
    else:
        _slab(p, rect, main, radius)


def _shaded(color, rect):
    """`color` a little lighter at the top of rect than at the bottom."""
    shade = QLinearGradient(rect.topLeft(), rect.bottomLeft())
    shade.setColorAt(0.0, QColor(color).lighter(114))
    shade.setColorAt(1.0, QColor(color).darker(108))
    return shade


def _slab(p, rect, color, radius):
    """A clip's bar: softly shaded, with a thin light edge along the top."""
    p.setBrush(_shaded(color, rect))
    p.drawRoundedRect(rect, radius, radius)
    if rect.height() >= 5 and rect.width() >= 6:
        p.setBrush(QColor(255, 255, 255, 46))
        p.drawRoundedRect(QRectF(rect.left() + 1.2, rect.top() + 0.6, rect.width() - 2.4, 1.0), 0.5, 0.5)


def _appear(t, at, over=0.16):
    """How far in (0-1) something that shows up at `at` (0 first, 1 last) is,
    `t` of the way through a tile's animation. None: not playing, all there."""
    if t is None:
        return 1.0
    k = min(1.0, max(0.0, (t / 0.62 - 0.05 - at * 0.85) / over))
    return 1 - (1 - k) ** 3


def _fade(t):
    """The animation's last tenth fades out, before it starts again."""
    return 1.0 if t is None or t < 0.9 else max(0.0, 1 - (t - 0.9) / 0.1)


def _clock(seconds):
    """Timeline time, as on Resolve's ruler: 1:05, 12:30, 1:02:03."""
    seconds = max(0.0, seconds)
    whole = int(seconds)
    h, m, sec = whole // 3600, whole % 3600 // 60, whole % 60
    text = f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"
    return text + (f".{int(round((seconds - whole) * 10))}" if seconds - whole > 0.04 else "")


def _pin(p, x, top, size, color):
    path = QPainterPath()
    path.moveTo(x - size / 2, top)
    path.lineTo(x + size / 2, top)
    path.lineTo(x + size / 2, top + size * 0.7)
    path.lineTo(x, top + size * 1.15)
    path.lineTo(x - size / 2, top + size * 0.7)
    path.closeSubpath()
    p.setPen(Qt.NoPen)
    p.setBrush(color)
    p.drawPath(path)


def draw_timeline_art(p, r, preset, c, clips=6, t=None, lanes=False):
    """A few tracks' worth of timeline with the clips where the preset puts them.
    t (0-1): playing - the clips land one by one, in the preset's own rhythm.
    lanes: faint track lines behind them."""
    row_h = r.height() * 0.17
    gap_y = r.height() * 0.05
    rows_bottom = r.bottom() - r.height() * 0.06
    block_w = r.width() * 0.2
    widths = [1.0, 0.75, 1.2, 0.85, 1.05, 0.7]
    placed = []   # (x, width) in r's coordinates, row decided below
    ats = []      # when each one lands while playing: 0 first, 1 last
    where, spacing = preset["where"], preset["spacing"]
    marker_xs = []
    base = None
    if where in ("markers", "cuts"):
        n = 3
        marker_xs = [r.left() + r.width() * f for f in (0.2, 0.52, 0.84)]
        if where == "cuts":
            base = [(r.left(), marker_xs[0]), (marker_xs[0], marker_xs[1]), (marker_xs[1], marker_xs[2]),
                    (marker_xs[2], r.right())]
        w = block_w * 0.7
        for i, mx in enumerate(marker_xs[:n]):
            shift = {"start": 0.0, "centre": -w / 2, "end": -w, "loudest": -w * 0.3}[preset["align"]]
            placed.append((mx + shift, w))
            ats.append(i / n)
    else:
        x0 = r.left() + r.width() * 0.12
        if spacing == "back_to_back" and True:
            x = x0
            n = 6 if 0 < preset["length"] < 1.5 else 4  # short clips: more of them, narrower
            for i in range(n):
                w = block_w * ((0.85 if n == 4 else 0.52) if preset["length"] else widths[i] * 0.85)
                placed.append((x, w - 1.5))
                ats.append(i / n)
                x += w
        elif spacing == "interval":
            offs = pm.offsets(preset, clips)
            span = max(1, offs[-1]) if offs else 1
            usable = r.width() * 0.68
            for o in offs:
                placed.append((x0 + usable * o / span, block_w * 0.75))
                ats.append(o / span)
        else:
            for i in range(3):
                placed.append((x0, block_w * (1.2, 0.8, 1.5)[i]))
                ats.append(i * 0.2)
        if preset.get("ends") == "together" and spacing != "back_to_back" and len(placed) > 1:
            end = max(min(x + w for x, w in placed), placed[-1][0] + block_w * 0.4)
            placed = [(x, end - x) for x, w in placed]
    # rows: like Resolve, a clip that overlaps goes up a track
    rows = []
    blocks = []
    for x, w in placed:
        row = 0
        while any(not (x + w <= ox or ox + ow <= x) for ox, ow, orow in rows if orow == row):
            row += 1
        rows.append((x, w, row))
        if base is not None:
            row += 1  # the cuts' own clips are on the bottom track
        top = rows_bottom - (row + 1) * row_h - row * gap_y
        blocks.append(QRectF(x, max(r.top() + 2, top), w, row_h))
    fade = _fade(t)
    p.setOpacity(fade)
    if lanes:
        p.setPen(QPen(_alpha(c["text"], 0.055), 1))
        for row in range(4):
            y = round(rows_bottom - row * (row_h + gap_y) + gap_y / 2) + 0.5
            if y > r.top() + row_h:
                p.drawLine(QPointF(r.left(), y), QPointF(r.right(), y))
    if base is not None:
        p.setPen(Qt.NoPen)
        for a, b in base:
            seg = QRectF(a + 1, rows_bottom - row_h, b - a - 2, row_h)
            p.setBrush(_shaded(_alpha(c["muted"], 0.42), seg))
            p.drawRoundedRect(seg, 2, 2)
    if preset["convert"] != "none" and blocks:
        box = blocks[0]
        for b in blocks[1:]:
            box = box.united(b)
        box = box.adjusted(-3, -3, 3, 3)
        tint = c["compound"] if preset["convert"] == "compound" else c["comp"]
        p.setOpacity(fade * _appear(t, 1.0))
        p.setPen(QPen(_alpha(tint, 0.9), 1.2))
        p.setBrush(_alpha(tint, 0.14))
        p.drawRoundedRect(box, 4, 4)
    for b, at in zip(blocks, ats):
        k = _appear(t, at)
        if k > 0:
            p.setOpacity(fade * k)
            _block(p, b.translated(0, -(1 - k) * 4), preset, c)
    p.setOpacity(fade)
    if marker_xs and where == "markers":
        for mx in marker_xs:
            _pin(p, mx, r.top() + 1, max(5.0, r.height() * 0.13), c["accent"])
            p.setPen(QPen(_alpha(c["accent"], 0.5), 1, Qt.DotLine))
            p.drawLine(QPointF(mx, r.top() + r.height() * 0.16), QPointF(mx, rows_bottom))
    elif marker_xs:
        p.setPen(QPen(_alpha(c["text"], 0.55), 1))
        for mx in marker_xs:
            p.drawLine(QPointF(mx, r.top() + 2), QPointF(mx, rows_bottom))
    else:
        x0 = r.left() + r.width() * 0.12
        p.setPen(QPen(c["accent"], 1.1))
        p.drawLine(QPointF(x0, r.top() + 3), QPointF(x0, rows_bottom))
        head = QPainterPath()
        head.moveTo(x0 - 3.2, r.top())
        head.lineTo(x0 + 3.2, r.top())
        head.lineTo(x0, r.top() + 4.2)
        head.closeSubpath()
        p.setPen(Qt.NoPen)
        p.setBrush(c["accent"])
        p.drawPath(head)
    p.setOpacity(1.0)


def draw_frame_art(p, r, preset, c, seed=7, count=None, frame=None, numbers=False, overflow=False, t=None,
                   shapes=None):
    """The frame, with where the pictures land in it - the same layout
    presets.layout() gives Resolve. shapes: each picture's (width, height) in
    pixels, where known - a square logo has more room to the sides than a
    16:9 picture, which is what's drawn without.
    overflow: show the parts that fall outside the frame, faintly.
    t (0-1): playing - several pictures land one by one; a single one
    goes from filling the frame to its place."""
    if frame is None:
        fw = min(r.width(), r.height() * 16 / 9)
        fh = fw * 9 / 16
        frame = QRectF(r.center().x() - fw / 2, r.center().y() - fh / 2, fw, fh)
    fw, fh = frame.width(), frame.height()
    fade = _fade(t)
    p.setOpacity(fade)
    p.setPen(QPen(_alpha(c["muted"], 0.75), 1))
    p.setBrush(_alpha(c["bar"], 0.75))
    p.drawRoundedRect(frame, 3, 3)
    if count is None:
        count = 5 if (preset["scatter"] or preset["scale_vary"] or preset["rotation_vary"]) else 1
    # (as width / height: the frame here is a few hundred pixels, the picture's own aren't)
    aspects = [(s[0] / s[1]) if s and s[1] else None for s in shapes] if shapes else None
    places = pm.layout(preset, count, fw, fh, aspects, seed)
    fill = QColor(pm.COLOUR_HEX.get(preset["colour"], "")) if preset["colour"] else QColor(c["video"])
    if not fill.isValid():
        fill = QColor(c["video"])

    def draw_all(alpha, outline):
        for n, place in enumerate(places):
            w, h = place["size"]
            zoom, pan, tilt, angle, see = place["zoom"], place["pan"], place["tilt"], place["angle"], 1.0
            if t is not None and len(places) == 1:  # from filling the frame to its place
                k = _appear(t, 0.05, 0.6)
                zoom, pan, tilt, angle = 1 + (zoom - 1) * k, pan * k, tilt * k, angle * k
            elif t is not None:
                see = _appear(t, n / len(places))
                zoom *= 1 + (1 - see) * 0.25
            if see <= 0:
                continue
            w, h = w * zoom, h * zoom
            p.save()
            p.setOpacity(fade * see)
            p.translate(frame.center().x() + pan, frame.center().y() - tilt)
            p.rotate(-angle)
            body = QColor(fill)
            body.setAlphaF((0.2 + 0.45 * preset["opacity"] / 100) * alpha)
            box = QRectF(-w / 2, -h / 2, w, h)
            p.setPen(QPen(_alpha(c["text"], 0.5 * alpha), 0.8, Qt.DashLine if outline else Qt.SolidLine))
            p.setBrush(_shaded(body, box))
            p.drawRoundedRect(box, 2, 2)
            p.restore()
    if overflow:
        draw_all(0.35, True)
    p.save()
    p.setClipRect(frame.adjusted(0.5, 0.5, -0.5, -0.5))
    draw_all(1.0, False)
    p.restore()
    p.setOpacity(1.0)
    if numbers:  # on top of everything, so every number can be read
        for n, place in enumerate(places):
            center = QPointF(frame.center().x() + place["pan"], frame.center().y() - place["tilt"])
            p.setPen(Qt.NoPen)
            p.setBrush(_alpha(c["bg"], 0.75))
            p.drawEllipse(center, 7.5, 7.5)
            p.setPen(c["text"])
            p.drawText(QRectF(center.x() - 8, center.y() - 8, 16, 16), Qt.AlignCenter, str(n + 1))


def draw_preset(p, r, preset, c, t=None, lanes=False):
    """The preset's drawing. t (0-1): playing, see the two kinds of art."""
    if pm.has_picture_changes(preset):
        draw_frame_art(p, r, preset, c, t=t)
    else:
        draw_timeline_art(p, r, preset, c, t=t, lanes=lanes)


# -- the tiles of presets --
class PresetGrid(QWidget):
    """Every preset as a tile, wrapping to the width. Click picks one; the
    arrow keys move; Enter inserts with it."""
    picked = Signal(str)
    activated = Signal(str)
    add_new = Signal()

    TILE = QSize(124, 100)
    GAP = 10
    HEAD = 18
    PLAY = 2.8  # seconds a tile's animation takes

    def __init__(self, settings):
        super().__init__()
        self.settings = settings
        self.size_tiles()
        self.items = []
        self.current = None
        self.in_use = None
        self.ghost = None    # (preset, name): what Save / Duplicate would make, faint in the New slot
        self.fading = None   # a preset's id: Delete's mouse-over fades its tile
        self._hover = None
        self._playing = None  # (preset id, since when, again and again) - the tile showing what it does
        self._clock = QTimer(self)
        self._clock.setInterval(16)
        self._clock.timeout.connect(self._tick)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        sp = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        sp.setHeightForWidth(True)
        self.setSizePolicy(sp)

    def set_fading(self, pid):
        self.fading = pid
        self.update()

    def set_items(self, items, current, in_use):
        picked = current != self.current
        self.items, self.current, self.in_use = items, current, in_use
        self.updateGeometry()
        self.update()
        if picked and self._hover is None and self.isVisible():
            self._play(current, False)  # picked with the keys: it shows once what it does

    # -- a tile plays what its preset does: while the mouse is on it, or once when picked --
    def _play(self, pid, again):
        self._playing = (pid, time.monotonic(), again)
        self._clock.start()

    def settle(self):
        """Stop playing: every tile back to its still drawing."""
        self._playing = None
        self._clock.stop()
        self.update()

    def _tick(self):
        pid, since, again = self._playing
        if not self.isVisible() or (not again and time.monotonic() - since >= self.PLAY * 0.9):
            self.settle()  # played once: stop before the fade, on the whole drawing
        else:
            self.update(self._rect(self._index_of(pid)).toAlignedRect())

    def _time(self, pid):
        if not self._playing or self._playing[0] != pid:
            return None
        return ((time.monotonic() - self._playing[1]) / self.PLAY) % 1.0

    def _count(self):
        return len(self.items) + 1  # + "New"

    def size_tiles(self):
        """The tiles' size at Insert as's zoom (they're made for 14 px text)."""
        from .fonts import zoom
        k = zoom(self.settings) * window_zoom(self.settings, "insert_as")
        self.TILE = QSize(round(124 * k), round(100 * k))
        self.GAP, self.HEAD = round(10 * k), round(18 * k)
        self.updateGeometry()

    def _columns(self, width):
        return max(1, int((width + self.GAP) // (self.TILE.width() + self.GAP)))

    def _arrange(self, width):
        """Where everything goes at this width: a heading for each group
        (just one now: Normal and yours), its tiles under it. "New" is the last tile
        of Yours. Returns (tile rects, [(heading rect, text)], height)."""
        key = (width, tuple((item["id"], item.get("group")) for item in self.items))
        if getattr(self, "_arranged", (None,))[0] == key:
            return self._arranged[1]
        cols = self._columns(width)
        rects, heads, y = [None] * self._count(), [], 1.0
        for group, title in pm.GROUPS:
            members = [i for i, item in enumerate(self.items) if item.get("group", "yours") == group]
            if group == "yours":
                members.append(len(self.items))
            if not members:
                continue
            if title:  # (one group: no heading)
                heads.append((QRectF(2, y, max(10, width - 4), self.HEAD), title))
                y += self.HEAD + 6
            for n, i in enumerate(members):
                r, col = divmod(n, cols)
                rects[i] = QRectF(1 + col * (self.TILE.width() + self.GAP), y + r * (self.TILE.height() + self.GAP),
                                  self.TILE.width() - 2, self.TILE.height() - 2)
            rows = (len(members) + cols - 1) // cols
            y += rows * self.TILE.height() + (rows - 1) * self.GAP + 14
        out = (rects, heads, int(y - 12))
        self._arranged = (key, out)
        return out

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._arrange(width)[2]

    def sizeHint(self):
        w = 5 * self.TILE.width() + 4 * self.GAP
        return QSize(w, self.heightForWidth(w))

    def minimumSizeHint(self):
        return QSize(self.TILE.width(), self.heightForWidth(self.width() or self.sizeHint().width()))

    def resizeEvent(self, event):
        self.setMinimumHeight(self.heightForWidth(self.width()))

    def _rect(self, i):
        return self._arrange(self.width())[0][i]

    def _step(self, i, down):
        """The tile under (or above) tile i - the nearest one in the next row, across the groups."""
        here = self._rect(i)
        rows = sorted({round(self._rect(n).top()) for n in range(len(self.items))})
        at = rows.index(round(here.top())) + (1 if down else -1)
        if not 0 <= at < len(rows):
            return i
        row = [n for n in range(len(self.items)) if round(self._rect(n).top()) == rows[at]]
        return min(row, key=lambda n: abs(self._rect(n).center().x() - here.center().x()))

    def _hit(self, pos):
        for i in range(self._count()):
            if self._rect(i).contains(pos):
                return i
        return None

    def _index_of(self, pid):
        return next((i for i, item in enumerate(self.items) if item["id"] == pid), 0)

    def mouseMoveEvent(self, event):
        hit = self._hit(event.position())
        if hit != self._hover:
            self._hover = hit
            self.setCursor(Qt.PointingHandCursor if hit is not None else Qt.ArrowCursor)
            if hit is not None and hit < len(self.items):
                self._play(self.items[hit]["id"], True)
            else:
                self.settle()
            self.update()

    def leaveEvent(self, event):
        self._hover = None
        self.settle()

    def mousePressEvent(self, event):
        hit = self._hit(event.position())
        if hit is None or event.button() != Qt.LeftButton:
            return
        if hit == len(self.items):
            self.add_new.emit()
        else:
            self.picked.emit(self.items[hit]["id"])

    def mouseDoubleClickEvent(self, event):
        hit = self._hit(event.position())
        if hit is not None and hit < len(self.items):
            self.activated.emit(self.items[hit]["id"])

    def keyPressEvent(self, event):
        if not self.items:
            return super().keyPressEvent(event)
        i = self._index_of(self.current)
        k = event.key()
        n = len(self.items)
        if k == Qt.Key_Right:
            i = (i + 1) % n
        elif k == Qt.Key_Left:
            i = (i - 1) % n
        elif k == Qt.Key_Down:
            i = self._step(i, True)
        elif k == Qt.Key_Up:
            i = self._step(i, False)
        elif k in (Qt.Key_Return, Qt.Key_Enter):
            self.activated.emit(self.items[i]["id"])
            return
        elif Qt.Key_1 <= k <= Qt.Key_9 and not event.modifiers():
            i = min(n - 1, k - Qt.Key_1)
        else:
            return super().keyPressEvent(event)
        self.picked.emit(self.items[i]["id"])

    def paintEvent(self, event):
        t = self.settings.theme
        c = _colors(t)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        radius = look.radius(self.settings, "tile")
        small = _f(SMALL, self.font())
        fm = QFontMetricsF(small)
        head = _f(TINY, small)  # the group names: small capitals, a little spread
        head.setCapitalization(QFont.AllUppercase)
        head.setLetterSpacing(QFont.PercentageSpacing, 108)
        head.setWeight(QFont.Medium)
        chosen = QFont(small)
        chosen.setWeight(QFont.Medium)
        p.setFont(head)
        p.setPen(_alpha(c["muted"], 0.9))
        for rect, title in self._arrange(self.width())[1]:
            p.drawText(rect, Qt.AlignLeft | Qt.AlignVCenter, title)
        for i in range(self._count()):
            r = self._rect(i)
            hover = self._hover == i
            p.setOpacity(1.0)
            if i == len(self.items) and self.ghost is not None:  # what Save / Duplicate makes - right here
                ghost, ghost_name = self.ghost
                p.setPen(QPen(_alpha(c["accent"], 0.8), 1.2, Qt.DashLine))
                p.setBrush(_alpha(c["accent"], 0.08))
                p.drawRoundedRect(r.adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)
                art = QRectF(r.left() + 12, r.top() + 11, r.width() - 24, r.height() - fm.height() - 28)
                p.save()
                p.setOpacity(0.7)
                draw_preset(p, art, ghost, c, lanes=True)
                p.restore()
                p.setFont(small)
                p.setPen(c["text"])
                p.drawText(QRectF(r.left() + 7, r.bottom() - fm.height() - 9, r.width() - 14, fm.height()),
                           Qt.AlignHCenter | Qt.AlignVCenter, fm.elidedText(ghost_name, Qt.ElideRight, r.width() - 14))
                continue
            if i == len(self.items):  # New
                p.setPen(QPen(_alpha(c["muted"], 0.55), 1, Qt.DashLine))
                p.setBrush(_alpha(c["text"], 0.05) if hover else Qt.NoBrush)
                p.drawRoundedRect(r.adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)
                p.setPen(QPen(c["text"] if hover else c["muted"], 1.6, Qt.SolidLine, Qt.RoundCap))
                cc = QPointF(r.center().x(), r.top() + r.height() * 0.4)
                p.drawLine(QPointF(cc.x() - 8, cc.y()), QPointF(cc.x() + 8, cc.y()))
                p.drawLine(QPointF(cc.x(), cc.y() - 8), QPointF(cc.x(), cc.y() + 8))
                p.setFont(small)
                p.drawText(QRectF(r.left(), r.bottom() - fm.height() - 9, r.width(), fm.height()),
                           Qt.AlignHCenter | Qt.AlignVCenter, "New")
                continue
            item = self.items[i]
            current = item["id"] == self.current
            using = item["id"] == self.in_use
            p.setOpacity(0.3 if item["id"] == self.fading else 1.0)
            look.paint_tile(p, r, self.settings, chosen=current, hover=hover)  # (the app's one tile)
            art = QRectF(r.left() + 12, r.top() + 11, r.width() - 24, r.height() - fm.height() - 28)
            p.save()
            draw_preset(p, art, item, c, t=self._time(item["id"]), lanes=True)
            p.restore()
            p.setFont(chosen if current else small)
            p.setPen(c["text"] if current or hover else c["muted"])
            label = fm.elidedText(item["name"], Qt.ElideRight, r.width() - 14)
            p.drawText(QRectF(r.left() + 7, r.bottom() - fm.height() - 9, r.width() - 14, fm.height()),
                       Qt.AlignHCenter | Qt.AlignVCenter, label)
            if using:  # a small dot: this is what Enter uses
                p.setPen(Qt.NoPen)
                p.setBrush(c["accent"])
                p.drawEllipse(QPointF(r.right() - 9, r.top() + 9), 3.2, 3.2)
            if item.get("edited") or not item.get("builtin"):
                p.setPen(Qt.NoPen)
                p.setBrush(_alpha(c["muted"], 0.8))
                if not item.get("builtin"):  # yours: a small corner mark
                    tri = QPainterPath()
                    tri.moveTo(r.left() + 6, r.top() + 6)
                    tri.lineTo(r.left() + 14, r.top() + 6)
                    tri.lineTo(r.left() + 6, r.top() + 14)
                    tri.closeSubpath()
                    p.drawPath(tri)
        p.end()


# -- small tiles to choose one of a few --
class ChoiceTiles(QWidget):
    """A row of small drawn tiles - one is chosen. Too narrow for all of them in a row, they wrap onto the next
    (never wider than there's room for: a row that couldn't shrink pushed all of Insert as off to the right)."""
    changed = Signal(str)

    def __init__(self, settings, options, value, tile_w=96, tile_h=66):
        super().__init__()
        self.settings = settings
        self.options = options      # [(key, label, draw(p, rect, colors, on))]
        self.value = value
        # (sizes are for 14 px text: grown with it, and wide enough for the longest name)
        from .fonts import zoom
        k = zoom(settings) * window_zoom(settings, "insert_as")
        longest = max((QFontMetricsF(_f(SMALL)).horizontalAdvance(label) for _k, label, _d in options), default=0)
        tile_w, tile_h = round(max(tile_w * k, longest + 16)), round(tile_h * k)
        self.tile_w, self.tile_h = tile_w, tile_h
        self._hover = None
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        policy = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        policy.setHeightForWidth(True)
        self.setSizePolicy(policy)
        self.setMinimumWidth(tile_w + 2)
        self.setMinimumHeight(tile_h + 2)

    def _cols(self, width):
        return max(1, min(len(self.options), int((width - 2 + 8) // (self.tile_w + 8))))

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        rows = -(-len(self.options) // self._cols(width))
        return rows * (self.tile_h + 8) - 8 + 2

    def sizeHint(self):
        return QSize(len(self.options) * (self.tile_w + 8), self.tile_h + 2)

    def minimumSizeHint(self):
        return QSize(self.tile_w + 2, self.tile_h + 2)

    def resizeEvent(self, event):
        height = self.heightForWidth(self.width())
        if self.minimumHeight() != height:  # (a layout doesn't always ask: the rows it needs, as its least)
            self.setMinimumHeight(height)
            self.setMaximumHeight(height)
        super().resizeEvent(event)

    def _rect(self, i):
        row, col = divmod(i, self._cols(self.width()))
        return QRectF(1 + col * (self.tile_w + 8), 1 + row * (self.tile_h + 8), self.tile_w, self.tile_h)

    def _hit(self, pos):
        for i in range(len(self.options)):
            if self._rect(i).contains(pos):
                return i
        return None

    def set_value(self, key):
        self.value = key
        self.update()

    def _choose(self, i):
        key = self.options[i][0]
        if key != self.value:
            self.value = key
            self.update()
            self.changed.emit(key)

    def mouseMoveEvent(self, event):
        hit = self._hit(event.position())
        if hit != self._hover:
            self._hover = hit
            self.setCursor(Qt.PointingHandCursor if hit is not None else Qt.ArrowCursor)
            self.update()

    def leaveEvent(self, event):
        self._hover = None
        self.update()

    def mousePressEvent(self, event):
        hit = self._hit(event.position())
        if hit is not None:
            self._choose(hit)

    def keyPressEvent(self, event):
        keys = [k for k, _l, _d in self.options]
        i = keys.index(self.value) if self.value in keys else 0
        if event.key() == Qt.Key_Right:
            self._choose(min(len(keys) - 1, i + 1))
        elif event.key() == Qt.Key_Left:
            self._choose(max(0, i - 1))
        else:
            super().keyPressEvent(event)

    def paintEvent(self, event):
        c = _colors(self.settings.theme)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        small = _f(SMALL, self.font())
        fm = QFontMetricsF(small)
        for i, (key, label, draw) in enumerate(self.options):
            r = self._rect(i)
            on = key == self.value
            hover = self._hover == i
            focus = self.hasFocus() and on
            look.paint_tile(p, r, self.settings, chosen=on, hover=hover, focus=focus)
            art = QRectF(r.left() + 12, r.top() + 8, r.width() - 24, r.height() - fm.height() - 18)
            p.save()
            draw(p, art, c, on or hover)
            p.restore()
            p.setFont(small)
            p.setPen(c["text"] if on or hover else c["muted"])
            p.drawText(QRectF(r.left() + 4, r.bottom() - fm.height() - 7, r.width() - 8, fm.height()),
                       Qt.AlignHCenter | Qt.AlignVCenter, fm.elidedText(label, Qt.ElideRight, r.width() - 8))
        p.end()


def _art_with(preset, **change):
    """A drawing of `preset` with a few fields changed - for the choice tiles."""
    def draw(p, r, c, on):
        variant = copy.deepcopy(preset)
        variant.update(change)
        if not any(k in change for k in ("scale", "x", "y", "scatter")):
            for k in ("scale", "scale_vary", "x", "y", "scatter", "rotation", "rotation_vary", "opacity"):
                variant[k] = pm.FIELDS[k]
        draw_preset(p, r, variant, c)
    return draw


def _curve_art(curve):
    def draw(p, r, c, on):
        x1, y1, x2, y2 = curve
        path = QPainterPath()
        path.moveTo(r.left(), r.bottom())
        path.cubicTo(QPointF(r.left() + x1 * r.width(), r.bottom() - y1 * r.height()),
                     QPointF(r.left() + x2 * r.width(), r.bottom() - y2 * r.height()),
                     QPointF(r.right(), r.top()))
        p.setPen(QPen(_alpha(c["muted"], 0.5), 1))
        p.drawLine(QPointF(r.left(), r.bottom()), QPointF(r.right(), r.bottom()))
        p.setPen(QPen(c["accent"] if on else c["text"], 1.6, Qt.SolidLine, Qt.RoundCap))
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)
    return draw


def _symbol_art(category):
    def draw(p, r, c, on):
        if category is None:
            p.setPen(QPen(_alpha(c["muted"], 0.8), 1, Qt.DashLine))
            p.setBrush(Qt.NoBrush)
            s = min(r.width(), r.height()) * 0.8
            p.drawRoundedRect(QRectF(r.center().x() - s / 2, r.center().y() - s / 2, s, s), 3, 3)
            return
        color = c["compound"] if category == "compound" else c["comp"]
        draw_symbol(p, category, r.center(), min(r.width(), r.height()) * 0.85, color)
    return draw


# -- the curve --
class CurveEditor(_Scaled, QWidget):
    """The gap between clips, clip after clip - for the clips of the next insert: a bar for every
    gap with its frames on it, the curve from the first gap to the last, and in words what it adds
    up to. Drag the ends up and down to set the first and last gap, the two handles to shape the
    change. Rest the mouse on a bar for that gap, in frames and seconds, and when its clip starts."""
    changed = Signal()

    EXAMPLE = 9  # clips drawn when fewer than three are staged

    def __init__(self, settings, preset, count=0, fps=30.0):
        super().__init__()
        self.settings = settings
        self.preset = preset
        self.example = count < 3
        self.count = self.EXAMPLE if self.example else min(int(count), 120)
        self.fps = fps or 30.0
        self._drag = None
        self._drag_top = None    # the scale, held still while a pillar is dragged
        self._back = QRectF()    # "Back to the curve", shown while the gaps are set by hand
        # Play: a click where each clip starts - to hear the rhythm while shaping it
        from .click_track import ClickTrack
        volume = max(0, min(100, int(settings.listen.get("volume", 70)))) / 100
        self.clicks = ClickTrack(lambda: max(0.25, volume * volume))
        self._play = QRectF()
        self._again = False      # played once: it plays again after every change (until stopped)
        self._said = ""          # why it can't play, if it can't
        self._tick = QTimer(self)
        self._tick.setInterval(16)
        self._tick.timeout.connect(self._playing_on)
        self._over = None  # the gap under the mouse
        self.setMouseTracking(True)
        self.setMinimumHeight(_px(196))

    def sizeHint(self):
        return QSize(_px(520), _px(196))

    # geometry
    def _plot(self):
        return QRectF(50, 40, self._w() - 70, self._h() - 40 - 30)

    def _gaps(self):
        return pm.gaps(self.preset, self.count)

    def _bar_at(self, pos):
        plot, n = self._plot(), len(self._gaps())
        if not n or not plot.adjusted(0, -6, 0, 24).contains(pos):
            return None
        return min(n - 1, max(0, int((pos.x() - plot.left()) / (plot.width() / n))))

    def _on_bar(self, pos):
        """The pillar under the mouse - on it, or just above its top - not anywhere in its column (the cursor said
        "drag" over the whole curve, 2026-10-19). None elsewhere."""
        i = self._bar_at(pos)
        if i is None:
            return None
        plot, gaps = self._plot(), self._gaps()
        slot = plot.width() / len(gaps)
        x = plot.left() + slot * i
        if not (x + slot * 0.1 <= pos.x() <= x + slot * 0.9) or pos.y() < self._y(gaps[i]) - 10:
            return None
        return i

    def _words(self, frames):
        return f"{frames} f \u00b7 {frames / self.fps:.2f} s"

    # -- hearing it --
    def click_times(self):
        """When each clip starts, in seconds - what Play ticks at."""
        return [frame / self.fps for frame in pm.offsets(self.preset, self.count)]

    def play(self):
        self._said = self.clicks.play(self.click_times()) or ""
        self._again = not self._said
        if not self._said:
            self._tick.start()
        self.update()

    def stop(self):
        self.clicks.stop()
        self._tick.stop()
        self.update()

    def _playing_on(self):
        if not self.clicks.playing:
            self.stop()
        self.update()

    def hideEvent(self, event):
        self.stop()
        super().hideEvent(event)

    def _top_value(self):
        if self._drag_top:
            return self._drag_top
        listed = pm.exact_gaps(self.preset)
        biggest = max([self.preset["gap"], self.preset["gap_end"]] + listed + [4])
        return biggest * 1.25

    def _y(self, frames):
        plot = self._plot()
        return plot.bottom() - plot.height() * frames / self._top_value()

    def _frames_at(self, y):
        plot = self._plot()
        return max(0, round((plot.bottom() - y) / plot.height() * self._top_value()))

    def _points(self):
        plot = self._plot()
        g0, g1 = self.preset["gap"], self.preset["gap_end"]
        x1, y1, x2, y2 = self.preset["curve"]
        p0 = QPointF(plot.left(), self._y(g0))
        p3 = QPointF(plot.right(), self._y(g1))
        p1 = QPointF(plot.left() + x1 * plot.width(), self._y(g0 + (g1 - g0) * y1))
        p2 = QPointF(plot.left() + x2 * plot.width(), self._y(g0 + (g1 - g0) * y2))
        return p0, p1, p2, p3

    def _handle_at(self, pos):
        if pm.exact_gaps(self.preset):
            return None
        p0, p1, p2, p3 = self._points()
        for name, pt in (("start", p0), ("end", p3), ("h1", p1), ("h2", p2)):  # the ends win where they overlap
            if (pt - pos).manhattanLength() < 12:
                return name
        return None

    def mousePressEvent(self, event):
        pos = self._mouse(event)
        if self._play.contains(pos):
            if self.clicks.playing:
                self.stop()
                self._again = False  # stopped by hand: quiet until Play is pressed again
            else:
                self.play()
            return
        if self._back.contains(pos):  # the gaps set by hand are let go of: the curve again
            self.preset["gaps"] = ""
            self.update()
            self.changed.emit()
            if self._again:
                self.play()
            return
        self._drag = self._handle_at(pos)
        if self._drag is None and self._on_bar(pos) is not None:
            # a pillar: its gap is set by hand from here on (all of them become "exact gaps")
            self._drag = ("bar", self._on_bar(pos))
            self._drag_top = self._top_value()

    def mouseMoveEvent(self, event):
        pos = self._mouse(event)
        if self._drag is None:
            over = self._bar_at(pos)
            self.setCursor(Qt.PointingHandCursor
                           if self._handle_at(pos) or self._back.contains(pos) or self._play.contains(pos)
                           else Qt.SizeVerCursor if self._on_bar(pos) is not None else Qt.ArrowCursor)
            if over != self._over:
                self._over = over
                self.update()
            return
        plot = self._plot()
        preset = self.preset
        if isinstance(self._drag, tuple):
            gaps = list(self._gaps())
            gaps[self._drag[1]] = int(min(self._frames_at(pos.y()), round(self._drag_top)))
            preset["gaps"] = ", ".join(str(g) for g in gaps)
            self._over = self._drag[1]
            self.update()
            self.changed.emit()
            return
        if self._drag == "start":
            preset["gap"] = int(self._frames_at(pos.y()))
        elif self._drag == "end":
            preset["gap_end"] = int(self._frames_at(pos.y()))
        else:
            g0, g1 = preset["gap"], preset["gap_end"]
            x = min(1.0, max(0.0, (pos.x() - plot.left()) / plot.width()))
            span = (g1 - g0) or 1
            y = min(1.6, max(-0.6, (self._frames_at(pos.y()) - g0) / span)) if g1 != g0 else 0.0
            curve = list(preset["curve"])
            if self._drag == "h1":
                curve[0], curve[1] = round(x, 3), round(y, 3)
            else:
                curve[2], curve[3] = round(x, 3), round(y, 3)
            preset["curve"] = curve
        self.update()
        self.changed.emit()

    def mouseReleaseEvent(self, event):
        changed = self._drag is not None
        self._drag = self._drag_top = None
        self.update()
        if changed and self._again:  # hear what that did
            self.play()

    def leaveEvent(self, event):
        if self._over is not None:
            self._over = None
            self.update()

    @staticmethod
    def _step(top):
        """A round number of frames between the lines across: about three of them."""
        for step in (1, 2, 5, 10, 20, 25, 50, 100, 200, 250, 500, 1000, 2500, 5000):
            if top / step <= 3.6:
                return step
        return 10000

    def paintEvent(self, event):
        c = _colors(self.settings.theme)
        p = self._painter(self)
        p.setRenderHint(QPainter.Antialiasing)
        plot = self._plot()
        small = _fd(SMALL, self.font())
        tiny = _fd(TINY, small)
        p.setFont(small)
        fm = QFontMetricsF(small)
        gaps = self._gaps()
        n = len(gaps)
        starts = pm.offsets(self.preset, self.count)
        listed = bool(pm.exact_gaps(self.preset))

        # where it is, while it plays: the gap being waited through, and how far through it
        playing_gap = playing_part = None
        if self.clicks.playing and starts:
            now = self.clicks.position() * self.fps
            playing_gap = max((i for i, s in enumerate(starts) if s <= now), default=0)
            if playing_gap < n:
                playing_part = min(1.0, (now - starts[playing_gap]) / max(1, gaps[playing_gap]))
        # in words, above: the whole of it - or the gap under the mouse
        if playing_gap is not None:
            words = f"Playing: clip <b>{min(self.count, playing_gap + 1)}</b> of {self.count}"
        elif self._said:
            words = self._said
        elif self._over is not None and self._over < n:
            g = gaps[self._over]
            words = (f"Gap {self._over + 1}: clip {self._over + 2} starts <b>{self._words(g)}</b> after clip "
                     f"{self._over + 1} - {starts[self._over + 1] / self.fps:.2f} s in")
        else:
            total = starts[-1] if starts else 0
            words = (f"{self.count} clips{' (an example)' if self.example else ''}: the last one starts "
                     f"<b>{total / self.fps:.2f} s</b> after the first ({total} frames)")
        from PySide6.QtGui import QTextDocument
        doc = QTextDocument()
        doc.setDefaultFont(small)
        doc.setHtml(f"<span style='color:{c['text'].name()}'>{words}</span>")
        p.save()
        p.translate(plot.left() - 4, 4)
        doc.drawContents(p)
        p.restore()

        # lines across, at round numbers of frames - named in frames and in seconds
        top = self._top_value()
        step = self._step(top)
        p.setPen(QPen(_alpha(c["muted"], 0.35), 1))
        p.drawLine(plot.bottomLeft(), plot.bottomRight())
        value = step
        while value <= top:
            y = self._y(value)
            p.setPen(QPen(_alpha(c["muted"], 0.18), 1, Qt.DotLine))
            p.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
            p.setPen(c["muted"])
            p.drawText(QRectF(0, y - fm.height() / 2, plot.left() - 8, fm.height()), Qt.AlignRight | Qt.AlignVCenter,
                       f"{value} f")
            value += step

        # the gaps, as bars - each with its frames on top, and under it the clip it comes after
        slot = plot.width() / max(1, n)
        p.setFont(tiny)
        tm = QFontMetricsF(tiny)
        widest = max([tm.horizontalAdvance(str(g)) for g in gaps] + [tm.horizontalAdvance(str(n))] + [1.0])
        every = max(1, int(-(-(widest + 5) // slot)))  # too many to name them all: every second, third ...
        for i, g in enumerate(gaps):
            x = plot.left() + slot * i + slot * 0.2
            y = self._y(g)
            over = i == self._over or i == playing_gap
            p.setPen(Qt.NoPen)
            p.setBrush(_alpha(c["video"], 0.6 if over else 0.32))
            p.drawRoundedRect(QRectF(x, y, slot * 0.6, max(1.5, plot.bottom() - y)), 2, 2)
            named = over or i % every == 0 or i == n - 1 and (n - 1) % every >= (every + 1) // 2
            centre = QRectF(plot.left() + slot * i - 20, 0, slot + 40, tm.height())
            if named:
                if listed or over or 0 < i < n - 1:  # (the first and the last gap are named on their plates)
                    p.setPen(c["text"] if over else _alpha(c["text"], 0.75))
                    p.drawText(centre.translated(0, y - tm.height() - 2), Qt.AlignHCenter | Qt.AlignBottom, str(g))
                p.setPen(c["text"] if over else c["muted"])
                p.drawText(centre.translated(0, plot.bottom() + 4), Qt.AlignHCenter | Qt.AlignTop, str(i + 1))
        p.setPen(c["muted"])
        p.drawText(QRectF(0, plot.bottom() + 4, plot.left() - 8, tm.height()), Qt.AlignRight | Qt.AlignTop, "after clip")
        p.setFont(small)
        if playing_part is not None:  # the wait for the next clip, running across its pillar
            px = plot.left() + slot * (playing_gap + playing_part)
            p.setPen(QPen(c["text"], 1.4))
            p.drawLine(QPointF(px, plot.top() - 4), QPointF(px, plot.bottom()))

        # Play / Stop, top right
        label = "Stop" if self.clicks.playing else "Play"
        self._play = QRectF(plot.right() - fm.horizontalAdvance("Stop") - 34, 4, fm.horizontalAdvance("Stop") + 34,
                            fm.height() + 4)
        p.setPen(QPen(_alpha(c["text"], 0.45), 1))
        p.setBrush(_alpha(c["text"], 0.1 if not self.clicks.playing else 0.2))
        p.drawRoundedRect(self._play, 4, 4)
        mark = QRectF(self._play.left() + 9, self._play.center().y() - 4.5, 9, 9)
        p.setPen(Qt.NoPen)
        p.setBrush(c["text"])
        if self.clicks.playing:
            p.drawRoundedRect(mark, 1.5, 1.5)
        else:
            triangle = QPainterPath()
            triangle.moveTo(mark.left(), mark.top())
            triangle.lineTo(mark.right(), mark.center().y())
            triangle.lineTo(mark.left(), mark.bottom())
            triangle.closeSubpath()
            p.drawPath(triangle)
        p.setPen(c["text"])
        p.drawText(self._play.adjusted(22, 0, -6, 0), Qt.AlignLeft | Qt.AlignVCenter, label)

        if not listed:
            p0, p1, p2, p3 = self._points()
            path = QPainterPath(p0)
            path.cubicTo(p1, p2, p3)
            p.setPen(QPen(_alpha(c["accent"], 0.5), 1, Qt.DashLine))
            p.drawLine(p0, p1)
            p.drawLine(p3, p2)
            strong = float(self.preset.get("curve_strength", 1)) > 1
            p.setPen(QPen(_alpha(c["accent"], 0.35) if strong else c["accent"], 1.2 if strong else 2.0,
                          Qt.SolidLine, Qt.RoundCap))
            p.setBrush(Qt.NoBrush)
            p.drawPath(path)
            if strong:  # the handles shape the faint line; this is what Strength makes of it
                g0, g1 = self.preset["gap"], self.preset["gap_end"]
                real = QPainterPath(p0)
                for k in range(1, 97):
                    x = k / 96
                    real.lineTo(plot.left() + x * plot.width(), self._y(g0 + (g1 - g0) * pm.eased(self.preset, x)))
                p.setPen(QPen(c["accent"], 2.0, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
                p.drawPath(real)
            for pt, big in ((p0, True), (p3, True), (p1, False), (p2, False)):
                p.setPen(QPen(c["accent"], 1.5))
                p.setBrush(c["accent"] if big else c["bar"])
                p.drawEllipse(pt, 5.0 if big else 4.0, 5.0 if big else 4.0)
            # the two ends, named - on a plate, so the bars' numbers don't run through the words
            for pt, words, right in ((p0, f"first gap  {self._words(self.preset['gap'])}", False),
                                     (p3, f"last gap  {self._words(self.preset['gap_end'])}", True)):
                width = fm.horizontalAdvance(words) + 12
                x = pt.x() - width - 9 if right else pt.x() + 9
                plate = QRectF(x, max(plot.top() - 13, pt.y() - fm.height() - 9), width, fm.height() + 4)
                p.setPen(Qt.NoPen)
                p.setBrush(_alpha(c["bar"], 0.9))
                p.drawRoundedRect(plate, 4, 4)
                p.setPen(c["text"])
                p.drawText(plate, Qt.AlignCenter, words)
            self._back = QRectF()
        else:  # set by hand: no curve - and the way back to it
            words = "Back to the curve"
            p.setFont(small)
            self._back = QRectF(self._play.left() - fm.horizontalAdvance(words) - 20, 4, fm.horizontalAdvance(words) + 12,
                                fm.height() + 4)
            p.setPen(QPen(_alpha(c["accent"], 0.7), 1))
            p.setBrush(_alpha(c["accent"], 0.14))
            p.drawRoundedRect(self._back, 4, 4)
            p.setPen(c["accent"])
            p.drawText(self._back, Qt.AlignCenter, words)
        p.end()


class TimelinePreview(_Scaled, QWidget):
    OWN_CTRL_WHEEL = True  # (Ctrl + the wheel zooms the drawing, not the window - wheel_zoom.py)
    """The next insert on a little timeline - your staged clips (or an
    example), placed the way the preset says. Every change in the editor
    redraws it. A still with no Length set lasts what "A picture lasts"
    says; End together shows where clips
    are cut (faint: the part that goes) and where a video or sound can't
    reach (dashed)."""

    LANE, GAP, RULER = 15.0, 4.0, 20.0
    # the end of the last picture, or the last sound, dragged: ("length" / "length_audio", seconds, let go)
    edited = Signal(str, float, bool)

    def __init__(self, settings, preset, sample, fps, loudest=None, events=None):
        super().__init__()
        self.settings = settings
        self.preset = preset
        self.sample = sample
        self.loudest = loudest  # each clip's loudest moment (frames into it), where known
        self.events = events    # the timeline's {"markers": {frame: colour}, "cuts": [frame], "start", "playhead",
                                # "now": [(kind, start, end)]}, when one is open
        self.zoom = 1.0         # Ctrl+scroll: closer in (the strip it's in scrolls sideways)
        self.holder = None
        self.fps = fps or 30.0
        self.plan = None
        self.lane, self.gap = self.LANE, self.GAP
        self._drag = None    # {"key", "start", "cap", "scale", "lead"} while an end is being dragged
        self._snap = None    # (frame, what it caught on) while it's caught
        self._hover = None   # the key of the handle under the mouse
        self.setMouseTracking(True)
        self.setMinimumHeight(_px(120))
        self.refresh()

    # -- the ends you can drag --
    def _scale(self):
        """(left, right, first frame, frames across) - held still while something is dragged."""
        if self._drag:
            return self._drag["scale"]
        items = self.plan["items"]
        plan = self.plan
        first = min([i["start"] - i.get("head", 0) for i in items] + plan["events"] + [0])
        last = max([i["own_end"] for i in items] + [i["end"] for i in items] + plan["events"]
                   + [i["start"] - i["head"] + i["whole"] for i in items if "whole" in i]
                   + ([plan["end"]] if plan["end"] else []))
        return 30.0, self._w() - 8.0, first, max(self.fps * 2, (last - first) * 1.08)

    def _x(self, frame):
        left, right, first, span = self._scale()
        return left + (right - left) * (frame - first) / span

    def _lane_y(self, kind, track):
        items = self.plan["items"]
        v_lanes = max([i["track"] for i in items if i["kind"] != "audio"], default=0)
        top = self.RULER + 8 + self._now_h()
        if kind != "audio":
            return top + (v_lanes - track) * (self.lane + self.gap)
        return top + v_lanes * (self.lane + self.gap) + (8 if v_lanes else 0) + (track - 1) * (self.lane + self.gap)

    def handles(self):
        """[(key, the clip whose end it is, its rect)]: the last picture's end sets how long pictures
        are (each one, or - ending together - the last one), the last sound's the same for sounds.
        Only where a length is counted from where the clip starts: at the playhead, not back to back -
        and not for pictures that end with the sounds."""
        preset, plan = self.preset, self.plan
        if not plan or not plan["items"] or preset["where"] != "playhead" or preset["spacing"] == "back_to_back":
            return []
        out = []
        for key, sound in (("length", False), ("length_audio", True)):
            members = [i for i in plan["items"] if (i["kind"] == "audio") == sound]
            if not members:
                continue
            if not sound and preset.get("ends") == "audio" and any(i["kind"] == "audio" for i in plan["items"]):
                continue
            if sound and preset.get("ends_audio") == "pictures" and any(i["kind"] != "audio" for i in plan["items"]):
                continue  # (they end where the pictures do: the pictures' handle moves them)
            # the one the others follow: the last to start - or, sounds ending with the first, the first
            if sound and preset.get("ends_audio") == "first":
                last = min(members, key=lambda i: (i["start"], -i["end"]))
            else:
                last = max(members, key=lambda i: (i["start"], i["end"]))
            x, y = self._x(last["end"]), self._lane_y(last["kind"], last["track"])
            out.append((key, last, QRectF(x - 3, y - 3, 6, self.lane + 6)))
        return out

    SNAP_PX = 7.0

    def _snap_points(self, key, lead):
        """[(frame, what it is)] an end being dragged catches on: where the other kind of clip starts
        and ends, the clip's own length, and every half second."""
        plan, out = self.plan, []
        sound = key == "length_audio"
        for n, it in enumerate(plan["items"]):
            if (it["kind"] == "audio") != sound:  # the other kind: pictures against sounds
                out.append((it["end"], f"end of {n + 1}"))
                out.append((it["start"], f"start of {n + 1}"))
        for what, frame in plan.get("ends", {}).items():
            if (what == "sounds") != sound:
                out.append((frame, f"where the {what} end"))
        own = lead["frames"] if lead["kind"] != "still" else self.still_frames()
        out.append((lead["start"] + own, "its own length" if lead["kind"] != "still" else "what a picture lasts"))
        left, right, first, span = self._scale()
        half = self.fps / 2
        k = 1
        while k * half <= first + span:
            out.append((int(round(k * half)), f"{k / 2:g} s"))
            k += 1
        return [(frame, label) for frame, label in out if frame > lead["start"]]

    def _snapped(self, frame, key, lead):
        """(frame, label) - the nearest point within reach, or the frame as it is."""
        left, right, first, span = self._scale()
        reach = self.SNAP_PX * span / (right - left)
        near = min(self._snap_points(key, lead), key=lambda s: abs(s[0] - frame), default=None)
        if near is not None and abs(near[0] - frame) <= reach:
            return near
        return int(round(frame)), ""

    def _handle_at(self, pos):
        for key, last, rect in self.handles():
            if rect.adjusted(-5, -4, 5, 4).contains(pos):
                return key, last
        return None, None

    def mouseMoveEvent(self, event):
        if self._drag:
            left, right, first, span = self._drag["scale"]
            frame = first + (self._mouse(event).x() - left) / (right - left) * span
            # it catches on things nearby - hold Alt to place it freely
            free = bool(event.modifiers() & Qt.AltModifier)
            frame, label = (int(round(frame)), "") if free else self._snapped(frame, self._drag["key"], self._drag["lead"])
            frames = max(1, int(round(frame - self._drag["start"])))
            if self._drag["cap"] and frames > self._drag["cap"]:
                frames, label = self._drag["cap"], "its own length"
            self._snap = (self._drag["start"] + frames, label) if label else None
            self.edited.emit(self._drag["key"], round(frames / self.fps, 4), False)
            return
        key, _last = self._handle_at(self._mouse(event))
        if key != self._hover:
            self._hover = key
            self.setCursor(Qt.SizeHorCursor if key else Qt.ArrowCursor)
            self.setToolTip("")
            self.update()

    def mousePressEvent(self, event):
        key, last = self._handle_at(self._mouse(event))
        if key and event.button() == Qt.LeftButton:
            # a video or a sound can't be made longer than it is; a picture can
            cap = 0 if last["kind"] == "still" else int(last["frames"])
            self._drag = {"key": key, "start": last["start"], "cap": cap, "scale": self._scale(), "lead": dict(last)}
            self._snap = None
            self.update()

    def mouseReleaseEvent(self, event):
        if self._drag:
            key = self._drag["key"]
            self._drag = self._snap = None
            self.edited.emit(key, float(self.preset[key]), True)

    def mouseDoubleClickEvent(self, event):
        key, _last = self._handle_at(self._mouse(event))
        if key:
            self._drag = None
            self.edited.emit(key, 0.0, True)

    def leaveEvent(self, event):
        if self._hover and not self._drag:
            self._hover = None
            self.setCursor(Qt.ArrowCursor)
            self.update()

    def still_frames(self):
        return int(round(float(self.settings.presets.get("still_length", 5.0)) * self.fps))

    def refresh(self):
        self.plan = pm.timeline_plan(self.preset, self.sample, self.fps, self.still_frames(),
                                     seed=pm.seed_for(self.settings, self.preset["id"]), loudest=self.loudest,
                                     events=self.real_events())
        items = self.plan["items"]
        v = max([i["track"] for i in items if i["kind"] != "audio"], default=0)
        a = max([i["track"] for i in items if i["kind"] == "audio"], default=0)
        lanes = v + a
        # up to 24 lanes at full height; more are drawn thinner, so 40 clips are 40 lanes, not a wall
        unit = self.LANE + self.GAP if lanes <= 24 else max(5.0, 24 * (self.LANE + self.GAP) / lanes)
        self.lane, self.gap = unit * self.LANE / (self.LANE + self.GAP), unit * self.GAP / (self.LANE + self.GAP)
        self.setMinimumHeight(_px(self.RULER + 10 + self._now_h() + lanes * unit + (8 if v and a else 0) + 8))
        if getattr(self, "holder", None) is not None:  # (the strip it scrolls sideways in, when zoomed)
            self.holder.setFixedHeight(self.minimumHeight() + 12)
        self.update()

    def _now_h(self):
        """Room for what's on the timeline already (a faint strip under the ruler) - when it's your timeline."""
        return 16.0 if self.events and self.events.get("now") and self.origin() is not None else 0.0

    def origin(self):
        """The timeline frame the drawing's frame 0 is - None when it isn't your timeline (an example)."""
        if not self.events:
            return None
        real = self.real_events()
        if self.preset["where"] != "playhead":
            return sorted(real)[0] - int(self.fps) if real else None
        return self.events.get("playhead")

    def wheelEvent(self, event):
        """Ctrl+scroll: closer in, or further out, around the mouse (the strip scrolls sideways then)."""
        if not event.modifiers() & Qt.ControlModifier or getattr(self, "holder", None) is None:
            event.ignore()
            return
        bar = self.holder.horizontalScrollBar()
        view = self.holder.viewport().width()
        at = event.position().x()
        share = at / max(1.0, self.width())
        self.zoom = max(1.0, min(60.0, self.zoom * (1.25 if event.angleDelta().y() > 0 else 0.8)))
        self.setMinimumWidth(int(view * self.zoom) if self.zoom > 1.0 else 0)
        in_view = at - bar.value()  # (the frame under the mouse stays under it)
        QTimer.singleShot(0, lambda: bar.setValue(int(share * self.width() - in_view)))
        event.accept()

    def real_events(self):
        """The markers (of the colours chosen) or cuts of the open timeline, or None."""
        where, found = self.preset["where"], self.events or {}
        if where == "markers":
            only = self.preset.get("marker_colours") or []
            return sorted(f for f, colour in (found.get("markers") or {}).items() if not only or colour in only) or None
        if where == "cuts":
            return _cuts(found, self.preset) or None
        return None

    def notes(self):
        plan = self.plan
        items = plan["items"]
        if not items:
            return ""
        start = min(i["start"] for i in items)
        end = max(i["end"] for i in items)
        parts = [f"{len(items)} clip{'s' if len(items) != 1 else ''}, {max(0, end - start) / self.fps:.1f} s"]
        with_sounds = self.preset.get("ends") == "audio" and any(i["kind"] == "audio" for i in items)
        for what, frame in plan.get("ends", {}).items():
            how = "with the sounds" if what == "pictures" and with_sounds else \
                "with the first one" if what == "sounds" and self.preset.get("ends_audio") == "first" else "together"
            parts.append(f"{what} end {how} at {(frame - start) / self.fps:.1f} s")
        if plan["group"] is not None:
            what = "compound" if self.preset["convert"] == "compound" else "Fusion"
            parts.append(f"wrapped in a {what} clip, cut there")
        real = self.real_events()
        if real:  # what the drawing is of
            what = "marker" if self.preset["where"] == "markers" else "cut"
            n = len(real)
            parts.append(f"your {f'first {pm.SHOWN_EVENTS} of {n}' if n > pm.SHOWN_EVENTS else n} {what}"
                         f"{'s' if n != 1 else ''}, as far apart as on the timeline")
        elif self.preset["where"] != "playhead":
            parts.append("three markers as an example - open a timeline to see yours")
        text = " \u00b7 ".join(parts)
        return text

    def paintEvent(self, event):
        c = _colors(self.settings.theme)
        p = self._painter(self)
        p.setRenderHint(QPainter.Antialiasing)
        plan = self.plan
        items = plan["items"]
        if not items:
            p.end()
            return
        small = _fd(TINY, self.font())
        p.setFont(small)
        fm = QFontMetricsF(small)
        left, right, first, span = self._scale()
        x = self._x

        v_lanes = max([i["track"] for i in items if i["kind"] != "audio"], default=0)
        a_lanes = max([i["track"] for i in items if i["kind"] == "audio"], default=0)
        top = self.RULER + 8 + self._now_h()

        def lane_y(kind, track):
            if kind != "audio":
                return top + (v_lanes - track) * (self.lane + self.gap)
            return top + v_lanes * (self.lane + self.gap) + (8 if v_lanes else 0) + (track - 1) * (self.lane + self.gap)

        # ruler: the timeline's own time, when it's your timeline - else seconds from the first clip
        p.setPen(QPen(_alpha(c["muted"], 0.5), 1))
        p.drawLine(QPointF(left, self.RULER), QPointF(right, self.RULER))
        origin = self.origin()
        zero = 0 if origin is None else origin - int((self.events or {}).get("start", 0))  # timeline time of frame 0
        per_sec = (right - left) / max(1.0, span / self.fps)
        step = next((st for st in (0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 1800) if st * per_sec >= 58), 3600)
        sec = math.floor(((first + zero) / self.fps) / step) * step
        while sec * self.fps - zero <= first + span:
            fx = x(sec * self.fps - zero)
            if fx >= left - 1:
                p.setPen(QPen(_alpha(c["muted"], 0.5), 1))
                p.drawLine(QPointF(fx, self.RULER - 4), QPointF(fx, self.RULER))
                p.setPen(c["muted"])
                p.drawText(QRectF(fx + 2, 0, 60, self.RULER - 4), Qt.AlignLeft | Qt.AlignBottom,
                           _clock(sec) if origin is not None else f"{sec:g}s")
            sec += step
        if self._now_h():  # what's on the timeline already, faintly, under the ruler
            band = QRectF(left, self.RULER + 4, right - left, self._now_h() - 6)
            p.setPen(Qt.NoPen)
            for kind, start, end in self.events.get("now") or []:
                a, b = x(start - origin), x(end - origin)
                if b < left or a > right:
                    continue
                y = band.top() if kind == "video" else band.top() + band.height() * 0.58
                h = band.height() * (0.5 if kind == "video" else 0.42)
                p.setBrush(_alpha(c["muted"], 0.32 if kind == "video" else 0.22))
                p.drawRoundedRect(QRectF(max(left, a), y, max(1.5, min(right, b) - max(left, a) - 0.5), h), 1.5, 1.5)
            p.setPen(c["muted"])
            p.drawText(QRectF(0, band.top() - 2, left - 6, band.height() + 4), Qt.AlignRight | Qt.AlignVCenter, "now")
        # lane names
        every = max(1, int(-(-(fm.height() + 1) // (self.lane + self.gap))))  # thin lanes: name every few
        for letter, kind, count in (("V", "video", v_lanes), ("A", "audio", a_lanes)):
            for n in range(1, count + 1):
                if every == 1 or n == 1 or n % every == 0:
                    p.setPen(c["muted"])
                    p.drawText(QRectF(0, lane_y(kind, n) - 6, left - 6, self.lane + 12), Qt.AlignRight | Qt.AlignVCenter,
                               f"{letter}{n}")
        colour = {"video": c["video"], "still": QColor(self.settings.theme["color_image"]), "audio": c["audio"]}
        bottom = lane_y("audio", a_lanes) + self.lane if a_lanes else lane_y("video", 1) + self.lane
        # the stills' compound clip
        if plan["group"] is not None:
            ys = [lane_y(i["kind"], i["track"]) for i in items]
            box = QRectF(x(plan["group"][0]) - 3, min(ys) - 3, x(plan["group"][1]) - x(plan["group"][0]) + 6,
                         max(ys) + self.lane - min(ys) + 6)
            p.setPen(QPen(_alpha(c["compound"], 0.9), 1.2, Qt.DashLine))
            p.setBrush(_alpha(c["compound"], 0.08))
            p.drawRoundedRect(box, 5, 5)
        for n, it in enumerate(items):
            y = lane_y(it["kind"], it["track"])
            col = colour[it["kind"]]
            if it["own_end"] > it["end"]:  # the part that's cut off
                p.setPen(Qt.NoPen)
                p.setBrush(_alpha(col, 0.16))
                p.drawRoundedRect(QRectF(x(it["end"]), y, x(it["own_end"]) - x(it["end"]), self.lane), 3, 3)
            if "whole" in it:  # at markers: what's cut where it would overlap the one before or after
                p.setPen(Qt.NoPen)
                p.setBrush(_alpha(col, 0.16))
                if it["head"]:
                    p.drawRoundedRect(QRectF(x(it["start"] - it["head"]), y, x(it["start"]) - x(it["start"] - it["head"]),
                                             self.lane), 3, 3)
                tail = it["start"] - it["head"] + it["whole"]
                if tail > it["end"]:
                    p.drawRoundedRect(QRectF(x(it["end"]), y, x(tail) - x(it["end"]), self.lane), 3, 3)
            rect = QRectF(x(it["start"]) + 0.5, y, max(3.0, x(it["end"]) - x(it["start"]) - 1), self.lane)
            p.setPen(Qt.NoPen)
            p.setBrush(col)
            p.drawRoundedRect(rect, 3, 3)
            if it["early"] and it.get("target") is not None:  # can't reach the end
                gap = QRectF(rect.right() + 1, y + 1, x(it["target"]) - rect.right() - 1, self.lane - 2)
                if gap.width() > 1:
                    p.setPen(QPen(_alpha(col, 0.9), 1, Qt.DashLine))
                    p.setBrush(Qt.NoBrush)
                    p.drawRoundedRect(gap, 3, 3)
            if rect.width() > fm.horizontalAdvance(str(n + 1)) + 6 and self.lane >= fm.height() - 3:
                p.setPen(QColor(self.settings.theme["picker_bg"]))
                p.drawText(rect, Qt.AlignCenter, str(n + 1))
        # where: playhead, markers or cuts
        if self.preset["where"] == "markers":
            for e in plan["events"]:
                _pin(p, x(e), self.RULER + 1, 7, c["accent"])
                p.setPen(QPen(_alpha(c["accent"], 0.45), 1, Qt.DotLine))
                p.drawLine(QPointF(x(e), self.RULER + 8), QPointF(x(e), bottom))
        elif self.preset["where"] == "cuts":
            p.setPen(QPen(_alpha(c["text"], 0.6), 1))
            for e in plan["events"]:
                p.drawLine(QPointF(x(e), self.RULER + 2), QPointF(x(e), bottom))
        else:
            px = x(0)
            p.setPen(QPen(c["accent"], 1.3))
            p.drawLine(QPointF(px, self.RULER - 2), QPointF(px, bottom))
            head = QPainterPath()
            head.moveTo(px - 4, self.RULER - 7)
            head.lineTo(px + 4, self.RULER - 7)
            head.lineTo(px, self.RULER - 1)
            head.closeSubpath()
            p.setPen(Qt.NoPen)
            p.setBrush(c["accent"])
            p.drawPath(head)
        for what, frame in plan.get("ends", {}).items():  # where the pictures end together, and the sounds
            ex = x(frame)
            if what == "sounds":
                y0, y1 = lane_y("audio", 1) - 3, lane_y("audio", a_lanes) + self.lane + 2
            else:
                y0, y1 = self.RULER + 2, lane_y("video", 1) + self.lane + 3
            p.setPen(QPen(c["text"], 1.2, Qt.DashLine))
            p.drawLine(QPointF(ex, y0), QPointF(ex, y1))
        if self._snap:  # what the end being dragged has caught on
            sx = x(self._snap[0])
            p.setPen(QPen(c["accent"], 1, Qt.DotLine))
            p.drawLine(QPointF(sx, self.RULER - 2), QPointF(sx, bottom + 4))
            words = self._snap[1]
            width = fm.horizontalAdvance(words) + 10
            tag = QRectF(min(max(left, sx - width / 2), right - width), 0, width, self.RULER - 5)
            p.setPen(Qt.NoPen)
            p.setBrush(c["accent"])
            p.drawRoundedRect(tag, 3, 3)
            p.setPen(QColor(self.settings.theme["picker_bg"]))
            p.drawText(tag, Qt.AlignCenter, words)
        # the ends that can be dragged: a small grip on the last picture and the last sound
        for key, _last, rect in self.handles():
            live = key == self._hover or (self._drag and self._drag["key"] == key)
            p.setPen(QPen(QColor(self.settings.theme["picker_bg"]), 1))
            p.setBrush(c["accent"] if live else c["text"])
            p.drawRoundedRect(rect if live else rect.adjusted(1, 1, -1, -1), 2.5, 2.5)
        p.end()


# -- a slider with a few steps --
class _SideStrip(QScrollArea):
    """Scrolls sideways only - with Shift+scroll or a sideways swipe. A plain scroll is the page's."""

    def wheelEvent(self, event):
        delta = event.angleDelta()
        if event.modifiers() & Qt.ShiftModifier or abs(delta.x()) > abs(delta.y()):
            bar = self.horizontalScrollBar()
            bar.setValue(bar.value() - (delta.x() or delta.y()))
            event.accept()
        else:
            event.ignore()


from .slider import Slider as StepSlider  # noqa: E402 (the app's slider, shared with Settings)


# -- which markers --
class ChangeChips(QWidget):
    """What's changed on a preset, as small chips under its name - "blue markers ✕", "30 % size ✕" - each
    taken back by itself with its ✕. Nothing changed: what the preset does, in plain words. Two rows high
    always (a header that grows as you change things moved everything under it). Reset's mouse-over fades
    them: that's what it takes back."""
    reverted = Signal(tuple)  # the keys of the chip taken back

    def __init__(self, settings):
        super().__init__()
        self.settings = settings
        self.changes, self.words, self.dim = [], "", False
        self._hover = None
        self._rects = []
        self.setMouseTracking(True)
        fm = QFontMetricsF(self.font())
        self.setFixedHeight(int(2 * (fm.height() + 10) + 6))

    def set_changes(self, changes, words):
        self.changes, self.words = list(changes), words
        self._hover = None
        self.update()

    def set_dim(self, on):
        self.dim = on
        self.update()

    def _layout(self):
        fm = QFontMetricsF(self.font())
        h = fm.height() + 8
        x, y, out = 0.0, 0.0, []
        for n, (words, keys) in enumerate(self.changes):
            w = fm.horizontalAdvance(words) + 12 + 16
            if x + w > self.width() and x > 0:
                x, y = 0.0, y + h + 6
            out.append((QRectF(x, y, w, h), words, keys))
            x += w + 6
        return out

    def mouseMoveEvent(self, event):
        hit = next((n for n, (r, _w, _k) in enumerate(self._layout()) if r.contains(event.position())), None)
        if hit != self._hover:
            self._hover = hit
            self.setCursor(Qt.PointingHandCursor if hit is not None else Qt.ArrowCursor)
            self.update()

    def leaveEvent(self, event):
        self._hover = None
        self.update()

    def mousePressEvent(self, event):
        for r, _w, keys in self._layout():
            if r.contains(event.position()):
                self.reverted.emit(tuple(keys))
                return

    def paintEvent(self, event):
        c = _colors(self.settings.theme)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        fm = QFontMetricsF(self.font())
        if not self.changes:
            p.setPen(c["muted"])
            p.drawText(QRectF(0, 0, self.width(), fm.height() + 8), Qt.AlignLeft | Qt.AlignVCenter,
                       fm.elidedText(self.words, Qt.ElideRight, self.width()))
            p.end()
            return
        p.setOpacity(0.35 if self.dim else 1.0)
        for n, (r, words, _keys) in enumerate(self._layout()):
            if r.bottom() > self.height():
                break
            hover = n == self._hover
            p.setPen(Qt.NoPen)
            p.setBrush(_alpha(c["accent"], 0.2 if hover else 0.12))
            p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
            p.setPen(c["text"])
            p.drawText(QRectF(r.left() + 10, r.top(), r.width() - 26, r.height()), Qt.AlignLeft | Qt.AlignVCenter, words)
            cx, cy = r.right() - 11, r.center().y()  # its ✕
            p.setPen(QPen(c["text"] if hover else c["muted"], 1.3, Qt.SolidLine, Qt.RoundCap))
            p.drawLine(QPointF(cx - 3, cy - 3), QPointF(cx + 3, cy + 3))
            p.drawLine(QPointF(cx + 3, cy - 3), QPointF(cx - 3, cy + 3))
        p.end()


class LengthField(QWidget):
    """A length that can also be the clip's whole length: a "Whole" switch, and the number beside it - which
    says "Whole clip" while that's on (a faded number read as broken). Changing the number (drag it, or type)
    switches Whole off; switching Whole on is 0 - the whole clip. Behaves like the number fields around it
    (value, setValue, valueChanged, scrub_from)."""
    valueChanged = Signal(float)

    def __init__(self, settings, value, whole="Whole", step=0.5, fallback=2.0, tip=""):
        super().__init__()
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(_px(8))
        self.last = float(value or fallback)  # the length it goes back to when Whole goes off
        self.check = QCheckBox()
        self.check.setChecked(not value)
        self.check.hide()
        switch = _switch(settings, self.check)
        switch.setToolTip(whole)
        self.box = DragDoubleSpinBox()
        self.box.setDecimals(2)
        self.box.setRange(0.0, 3600.0)
        self.box.setSpecialValueText(whole)  # 0: the whole clip
        self.box.setSingleStep(step)
        self.box.setSuffix(" s")
        self.box.setValue(float(value or 0.0))
        self.box.setFixedWidth(_px(116))
        if tip:
            self.box.setToolTip(tip)
        h.addWidget(self.check)
        h.addWidget(switch)
        h.addWidget(self.box)
        self.check.toggled.connect(self._whole)
        self.box.valueChanged.connect(self._number)

    def _whole(self, on):
        if getattr(self, "_following", False):
            return
        self.box.setValue(0.0 if on else self.last)  # (-> _number, which says so)

    def _number(self, v):
        if v:
            self.last = float(v)
        if self.check.isChecked() != (not v):  # the switch follows the box it stands for
            self._following = True
            self.check.setChecked(not v)
            self._following = False
        self.valueChanged.emit(self.value())

    def value(self):
        return float(self.box.value())

    def setValue(self, value):
        self.box.setValue(float(value or 0.0))

    def scrub_from(self, widget):
        self.box.scrub_from(widget)

    def lineEdit(self):
        return self.box.lineEdit()


def reset_on_double_click(label, control, default):
    """Double-clicking a setting's name puts it back to how it ships."""
    class _Back(QObject):
        def eventFilter(self, obj, event):
            if event.type() == QEvent.MouseButtonDblClick:
                control.setValue(default)
                return True
            return False
    label.installEventFilter(_Back(label))


class MarkerNudge(_Scaled, QWidget):
    """Your clips on one marker, one row each, drawn as they'll sit there - each by its own kind's start,
    middle, end or loudest moment (its sound's waveform inside it, the loudest moment marked).
    Drag a clip to move them off the marker, earlier or later: all of them together (one shift), or -
    Move together off - just that one (its own shift, on top). A dragged clip catches on its own start,
    middle, end and loudest moment being on the marker, and on the marker itself (Alt: freely).
    Arrow keys move them a frame, Shift+arrow ten. Double-click: back on the marker."""
    changed = Signal(float, bool)   # the shift in seconds, let go

    RULER, ROWS_MAX = 18.0, 6

    def __init__(self, settings, preset, clips, fps, more=0):
        super().__init__()
        self.settings, self.preset, self.fps = settings, preset, fps or 30.0
        # clips: [{"kind", "frames" (as it lands), "label", "peaks" (0-1, or None), "loudest" (frames, or None)}]
        self.clips = self._rows(clips)
        self.more = more + len(clips) - len(self.clips)  # staged, but not drawn
        self.row_h = 40.0 if len(self.clips) == 1 else 30.0 if len(self.clips) <= 3 else 22.0
        self.together = True  # dragging one moves them all
        self.chosen = 0       # the row the arrow keys move, when they move one by one
        self._drag = None     # (press x, its shift then, the scale held still, the clip grabbed)
        self._caught = None   # what it caught on, while it's caught
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMinimumHeight(_px(self._top(len(self.clips)) + 24))

    def _rows(self, clips):
        """The rows drawn: pictures and sounds share them - with more than fit, each kind gets half (the room
        the other doesn't need), so six pictures don't leave the sounds out."""
        pictures = [c for c in clips if c.get("kind") != "audio"]
        sounds = [c for c in clips if c.get("kind") == "audio"]
        room = self.ROWS_MAX
        n_sounds = min(len(sounds), max(room // 2, room - len(pictures)))
        return pictures[:room - n_sounds] + sounds[:n_sounds]

    def _top(self, row):
        return self.RULER + 14 + row * (self.row_h + 18)

    def _align(self, clip):
        return self.preset["align"] if clip.get("kind") == "audio" else self.preset.get("align_pictures", "start")

    def _anchor(self, clip, align=None):
        return pm.anchor(align or self._align(clip), max(1, int(clip["frames"])), clip.get("loudest"))

    def _shift(self):
        return int(round(self.preset["shift"] * self.fps))

    def _own(self, clip):
        """A clip's own frames on top of the shift they all have."""
        return int(round(float(self.preset.get("clip_shifts", {}).get(clip.get("label", ""), 0.0)) * self.fps))

    def _scale(self):
        """(px per frame, the marker's x) - held still while it's dragged."""
        if self._drag:
            return self._drag[2]
        moved = [self._shift() + self._own(c) for c in self.clips] or [0]
        before = max([self._anchor(c) - self._shift() - self._own(c) for c in self.clips] + [self.fps * 0.5])
        after = max([c["frames"] - self._anchor(c) + self._shift() + self._own(c) for c in self.clips]
                    + [self.fps * 0.5])
        reach = max(before, after, max(abs(m) for m in moved)) * 1.15
        return (self._w() - 24) / (2 * reach), self._w() / 2

    def _rect(self, n):
        per, mx = self._scale()
        clip = self.clips[n]
        start = -self._anchor(clip) + self._shift() + self._own(clip)
        return QRectF(mx + start * per, self._top(n), max(3.0, clip["frames"] * per), self.row_h)

    def _catches(self, clip):
        """[(its total shift in frames, what it means)] a dragged clip catches on."""
        out = [(0, "right on the marker")]
        here = self._anchor(clip)
        words = {"start": "its start on the marker", "centre": "its middle on the marker",
                 "end": "its end on the marker", "loudest": "its loudest moment on the marker"}
        for align, what in words.items():
            if align == "loudest" and clip.get("loudest") is None:
                continue
            out.append((here - self._anchor(clip, align), what))
        return out

    def _set(self, frames, released, clip=None):
        """Their shift (clip None) - or one clip's own - to `frames`."""
        limit = int(pm.SHIFT_MAX * self.fps)
        frames = max(-limit, min(limit, int(frames)))
        seconds = round(frames / self.fps, 4)
        if clip is None:
            if seconds == self.preset["shift"] and not released:
                return
            self.preset["shift"] = seconds
        else:
            own = dict(self.preset.get("clip_shifts") or {})
            if seconds:
                own[clip["label"]] = seconds
            else:
                own.pop(clip["label"], None)
            if own == self.preset.get("clip_shifts") and not released:
                return
            self.preset["clip_shifts"] = own
        self.update()
        self.changed.emit(self.preset["shift"], released)

    def caption(self):
        """What it says under the drawing."""
        several = len(self.clips) + self.more > 1
        shift = self._shift()
        aligns = {self._align(c) for c in self.clips} or {self.preset["align"]}
        words = {"start": "starts", "centre": "is centred", "end": "ends", "loudest": "is loudest"}
        point = words[aligns.pop()] if len(aligns) == 1 else "sits"
        subject = "Each one" if several else "It"
        if not shift:
            text = f"{subject} {point} on the marker."
        else:
            text = f"{subject} {point} {self._how(abs(shift))} {'after' if shift > 0 else 'before'} the marker."
        if any(self._own(c) for c in self.clips):
            text += " Some moved by themselves."
        if any(self._align(c) == "loudest" and c.get("loudest") is None for c in self.clips):
            text += " One with no sound to go by starts there."
        if self.more:
            text += f" (+{self.more} more, the same way.)"
        return text

    def _how(self, frames):
        return f"{frames} frame{'s' if frames != 1 else ''}" if frames < self.fps else f"{frames / self.fps:.2f} s"

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self.clips:
            pos = self._mouse(event)
            # the clip grabbed: the one under the mouse, else the row it's on
            grabbed = next((n for n in range(len(self.clips)) if self._rect(n).adjusted(0, -6, 0, 6).contains(pos)),
                           min(range(len(self.clips)), key=lambda n: abs(self._rect(n).center().y() - pos.y())))
            self.chosen = grabbed
            clip = self.clips[grabbed]
            self._drag = (pos.x(), self._shift() if self.together else self._own(clip), self._scale(), grabbed)
            self.setCursor(Qt.ClosedHandCursor)
            self.update()

    def mouseMoveEvent(self, event):
        if not self._drag:  # (the hand only over a clip - it was over the whole drawing, 2026-10-19)
            pos = self._mouse(event)
            on_clip = any(self._rect(n).adjusted(0, -6, 0, 6).contains(pos) for n in range(len(self.clips)))
            self.setCursor(Qt.OpenHandCursor if on_clip else Qt.ArrowCursor)
            return
        x0, before, (per, _mx), grabbed = self._drag
        clip = self.clips[grabbed]
        frames = before + round((self._mouse(event).x() - x0) / per)
        self._caught = None
        if not event.modifiers() & Qt.AltModifier:
            # (what it catches on is where THIS clip sits, all told: the shared shift and its own)
            other = self._own(clip) if self.together else self._shift()
            near = [(abs(frames + other - at) * per, at - other, what) for at, what in self._catches(clip)]
            gap, at, what = min(near)
            if gap <= 7:
                frames, self._caught = at, what
        self._set(frames, False, None if self.together else clip)

    def mouseReleaseEvent(self, event):
        if self._drag:
            grabbed = self._drag[3]
            self._drag = None
            self.setCursor(Qt.ArrowCursor)
            clip = self.clips[grabbed]
            self._set(self._shift() if self.together else self._own(clip), True, None if self.together else clip)

    def mouseDoubleClickEvent(self, event):
        self._caught = None
        if self.together:  # all of them back on it, their own moves too
            self.preset["clip_shifts"] = {}
            self._set(0, True)
        else:
            self._set(0, True, self.clips[self.chosen])

    def keyPressEvent(self, event):
        step = 10 if event.modifiers() & Qt.ShiftModifier else 1
        if event.key() in (Qt.Key_Left, Qt.Key_Right) and self.clips:
            self._caught = None
            way = step if event.key() == Qt.Key_Right else -step
            if self.together:
                self._set(self._shift() + way, True)
            else:
                clip = self.clips[self.chosen]
                self._set(self._own(clip) + way, True, clip)
        elif event.key() in (Qt.Key_Up, Qt.Key_Down) and not self.together and self.clips:
            self.chosen = (self.chosen + (1 if event.key() == Qt.Key_Down else -1)) % len(self.clips)
            self.update()
        else:
            super().keyPressEvent(event)

    def paintEvent(self, event):
        c = _colors(self.settings.theme)
        p = self._painter(self)
        p.setRenderHint(QPainter.Antialiasing)
        per, mx = self._scale()
        small = _fd(TINY, self.font())
        p.setFont(small)
        fm = QFontMetricsF(small)
        ruler = self.RULER
        bottom = self._top(len(self.clips)) - 12
        # time around the marker: a tick every second (half seconds, near in)
        step = self.fps / 2 if per * self.fps > 140 else self.fps if per * self.fps > 40 else self.fps * 5
        p.setPen(QPen(_alpha(c["muted"], 0.45), 1))
        p.drawLine(QPointF(8, ruler), QPointF(self._w() - 8, ruler))
        k = -int(mx / (per * step)) - 1
        while mx + k * step * per < self._w():
            tx = mx + k * step * per
            if 24 < tx < self._w() - 24 and k:
                p.setPen(QPen(_alpha(c["muted"], 0.45), 1))
                p.drawLine(QPointF(tx, ruler - 3), QPointF(tx, ruler))
                p.setPen(c["muted"])
                sec = k * step / self.fps
                p.drawText(QRectF(tx - 30, 0, 60, ruler - 4), Qt.AlignHCenter | Qt.AlignBottom, f"{sec:+g}s")
            k += 1
        colours = {"video": c["video"], "still": QColor(self.settings.theme["color_image"]), "audio": c["audio"]}
        for n, clip in enumerate(self.clips):
            rect = self._rect(n)
            top, h = rect.top(), rect.height()
            p.setPen(Qt.NoPen)
            _slab(p, rect, colours[clip.get("kind", "still")], 4 if h > 30 else 3)
            peaks = clip.get("peaks")
            if peaks:  # its sound, as a waveform inside it
                p.setBrush(_alpha(QColor(self.settings.theme["picker_bg"]), 0.55))
                bars = max(8, int(rect.width() / 2.5))
                for i in range(bars):
                    v = peaks[min(len(peaks) - 1, i * len(peaks) // bars)]
                    bh = max(1.0, v * (h - 8))
                    p.drawRect(QRectF(rect.left() + i * rect.width() / bars, rect.center().y() - bh / 2,
                                      max(1.0, rect.width() / bars - 0.8), bh))
            loud = clip.get("loudest")
            if loud is not None:  # its loudest moment
                lx = rect.left() + loud * per
                p.setPen(QPen(_alpha(c["text"], 0.85), 1.2))
                p.drawLine(QPointF(lx, top - 2), QPointF(lx, top + h + 2))
                tri = QPainterPath()
                tri.moveTo(lx - 3.5, top + h + 7)
                tri.lineTo(lx + 3.5, top + h + 7)
                tri.lineTo(lx, top + h + 2.5)
                tri.closeSubpath()
                p.setPen(Qt.NoPen)
                p.setBrush(_alpha(c["text"], 0.85))
                p.drawPath(tri)
                if n == len(self.clips) - 1:
                    p.setPen(c["muted"])
                    p.drawText(QRectF(lx - 50, top + h + 6, 100, 14), Qt.AlignHCenter | Qt.AlignTop, "loudest")
            if not self.together and n == self.chosen and self.hasFocus():  # the one the arrow keys move
                p.setPen(QPen(c["accent"], 1.4))
                p.setBrush(Qt.NoBrush)
                p.drawRoundedRect(rect.adjusted(-2, -2, 2, 2), 5, 5)
            label = clip.get("label") or ""
            own = self._own(clip)
            if own:  # moved by itself: how far, on top of the others
                label = f"{label}  {'+' if own > 0 else '-'}{self._how(abs(own))}"
            if label:  # its name beside it, on the side with room
                p.setPen(c["muted"])
                room_r, room_l = self._w() - rect.right() - 10, rect.left() - 10
                if room_r >= room_l:
                    p.drawText(QRectF(rect.right() + 6, top, room_r, h), Qt.AlignLeft | Qt.AlignVCenter,
                               fm.elidedText(label, Qt.ElideMiddle, max(30.0, room_r - 6)))
                else:
                    p.drawText(QRectF(4, top, room_l, h), Qt.AlignRight | Qt.AlignVCenter,
                               fm.elidedText(label, Qt.ElideMiddle, max(30.0, room_l - 6)))
        # the marker, on top
        _pin(p, mx, ruler + 1, 9, c["accent"])
        p.setPen(QPen(c["accent"], 1.3))
        p.drawLine(QPointF(mx, ruler + 10), QPointF(mx, bottom))
        if self._caught and self._drag:
            p.setPen(c["accent"])
            p.drawText(QRectF(mx + 8, ruler + 2, self._w() - mx - 12, 14), Qt.AlignLeft | Qt.AlignVCenter,
                       self._caught)
        p.end()


class MarkerTiles(QWidget):
    """The markers on this timeline, one tile per colour with how many
    there are. Click the colours that count; "Every marker" is all of them."""
    changed = Signal(list)

    TILE_W, TILE_H, GAP = 78, 62, 8

    def __init__(self, settings, counts, chosen):
        super().__init__()
        self.settings = settings
        self.counts = dict(counts or {})
        self.chosen = [c for c in pm.MARKER_HEX if c in (chosen or [])]
        # every colour in use, then any you chose that this timeline doesn't have (shown as 0)
        self.colours = [c for c in pm.MARKER_HEX if c in self.counts or c in self.chosen]
        from .fonts import zoom
        k = zoom(settings) * window_zoom(settings, "insert_as")
        self.TILE_W, self.TILE_H, self.GAP = round(78 * k), round(62 * k), round(8 * k)
        self._hover = None
        self.setMouseTracking(True)
        self.setFixedHeight(self.TILE_H + 2)
        self.setMinimumWidth((len(self.colours) + 1) * (self.TILE_W + self.GAP))

    def sizeHint(self):
        return QSize((len(self.colours) + 1) * (self.TILE_W + self.GAP), self.TILE_H + 2)

    def _rect(self, i):
        return QRectF(1 + i * (self.TILE_W + self.GAP), 1, self.TILE_W, self.TILE_H)

    def _hit(self, pos):
        return next((i for i in range(len(self.colours) + 1) if self._rect(i).contains(pos)), None)

    def placed(self):
        """How many markers the choice covers on this timeline."""
        return sum(n for colour, n in self.counts.items() if not self.chosen or colour in self.chosen)

    def mouseMoveEvent(self, event):
        hit = self._hit(event.position())
        if hit != self._hover:
            self._hover = hit
            self.setCursor(Qt.PointingHandCursor if hit is not None else Qt.ArrowCursor)
            self.update()

    def leaveEvent(self, event):
        self._hover = None
        self.update()

    def mousePressEvent(self, event):
        hit = self._hit(event.position())
        if hit is None:
            return
        if hit == 0:
            self.chosen = []
        else:
            colour = self.colours[hit - 1]
            self.chosen = [c for c in pm.MARKER_HEX if (c in self.chosen) != (c == colour)]
        self.update()
        self.changed.emit(list(self.chosen))

    def paintEvent(self, event):
        c = _colors(self.settings.theme)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        small = _f(SMALL, self.font())
        p.setFont(small)
        fm = QFontMetricsF(small)
        for i in range(len(self.colours) + 1):
            r = self._rect(i)
            colour = self.colours[i - 1] if i else None
            on = (not self.chosen) if i == 0 else colour in self.chosen
            count = sum(self.counts.values()) if i == 0 else self.counts.get(colour, 0)
            look.paint_tile(p, r, self.settings, chosen=on, hover=self._hover == i)
            top = r.top() + 10
            if i == 0:  # every colour in use, side by side
                shown = [k for k in pm.MARKER_HEX if k in self.counts][:4] or ["Blue"]
                for n, k in enumerate(shown):
                    _pin(p, r.center().x() + (n - (len(shown) - 1) / 2) * 11, top, 9, QColor(pm.MARKER_HEX[k]))
            else:
                _pin(p, r.center().x() - 12, top, 11, _alpha(QColor(pm.MARKER_HEX[colour]), 1.0 if count else 0.4))
                p.setPen(c["text"] if count else c["muted"])
                p.drawText(QRectF(r.center().x() - 2, top - 2, 34, 16), Qt.AlignLeft | Qt.AlignVCenter,
                           f"\u00d7 {count}")
            p.setPen(c["text"] if on or self._hover == i else c["muted"])
            label = f"All  \u00d7 {count}" if i == 0 else colour
            p.drawText(QRectF(r.left() + 4, r.bottom() - fm.height() - 7, r.width() - 8, fm.height()),
                       Qt.AlignHCenter | Qt.AlignVCenter, label)
        p.end()


def _by_track(events):
    """{track: [(start, end) of its clips]} handed over by the picker (an older {"cuts": [frames]} is V1's cuts)."""
    events = events or {}
    return events.get("clips_by_track") or ({"V1": events["cuts"]} if events.get("cuts") is not None else {})


def _cuts(events, preset):
    """The cuts that count for `preset`: on the tracks it names, at the clips' edges it names."""
    return pm.cut_frames(_by_track(events), preset.get("cut_tracks"), preset.get("cut_edges", "between"))


class CutTiles(QWidget):
    """The tracks on this timeline, a tile each: a strip in its kind's colour, cut where its clips meet, and
    how many cuts it has. Click the ones whose cuts count - one at least."""
    changed = Signal(list)

    def __init__(self, settings, by_track, chosen):
        super().__init__()
        self.settings = settings
        self.counts = {track: len(frames) for track, frames in (by_track or {}).items()}
        self.chosen = pm.track_order(chosen or ["V1"])
        # every track on the timeline, then any chosen that it doesn't have (shown as 0)
        self.tracks = pm.track_order(list(self.counts) + self.chosen)
        from .fonts import zoom
        k = zoom(settings) * window_zoom(settings, "insert_as")
        self.TILE_W, self.TILE_H, self.GAP = round(78 * k), round(62 * k), round(8 * k)
        self._hover = None
        self.setMouseTracking(True)
        self._fit()

    def _per_row(self, width=None):
        return max(1, int(((width or self.width()) + self.GAP) // (self.TILE_W + self.GAP)))

    def _fit(self):  # (a row of tiles wraps onto the next when there isn't room - never wider than the window)
        rows = -(-len(self.tracks) // self._per_row(max(self.width(), self.TILE_W)))
        self.setFixedHeight(rows * (self.TILE_H + self.GAP) - self.GAP + 2)

    def sizeHint(self):
        return QSize(len(self.tracks) * (self.TILE_W + self.GAP), self.TILE_H + 2)

    def minimumSizeHint(self):
        return QSize(self.TILE_W + 2, self.TILE_H + 2)

    def resizeEvent(self, event):
        self._fit()
        super().resizeEvent(event)

    def _rect(self, i):
        per = self._per_row()
        return QRectF(1 + (i % per) * (self.TILE_W + self.GAP), 1 + (i // per) * (self.TILE_H + self.GAP),
                      self.TILE_W, self.TILE_H)

    def _hit(self, pos):
        return next((i for i in range(len(self.tracks)) if self._rect(i).contains(pos)), None)

    def mouseMoveEvent(self, event):
        hit = self._hit(event.position())
        if hit != self._hover:
            self._hover = hit
            self.setCursor(Qt.PointingHandCursor if hit is not None else Qt.ArrowCursor)
            self.update()

    def leaveEvent(self, event):
        self._hover = None
        self.update()

    def mousePressEvent(self, event):
        hit = self._hit(event.position())
        if hit is None:
            return
        track = self.tracks[hit]
        chosen = [t for t in self.chosen if t != track] if track in self.chosen else self.chosen + [track]
        if not chosen:
            return  # (one at least: no tracks would be no cuts)
        self.chosen = pm.track_order(chosen)
        self.update()
        self.changed.emit(list(self.chosen))

    def paintEvent(self, event):
        c = _colors(self.settings.theme)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        small = _f(SMALL, self.font())
        p.setFont(small)
        fm = QFontMetricsF(small)
        for i, track in enumerate(self.tracks):
            r = self._rect(i)
            on, count = track in self.chosen, self.counts.get(track, 0)
            look.paint_tile(p, r, self.settings, chosen=on, hover=self._hover == i)
            # the track: a strip in its kind's colour, a gap where each cut is (four at most)
            strip = QRectF(r.left() + 12, r.top() + 12, r.width() - 24, 9)
            colour = _alpha(c["audio" if track[0] == "A" else "video"], 0.85 if count else 0.35)
            cuts = min(count, 4)
            edges = [strip.left() + strip.width() * k / (cuts + 1) for k in range(cuts + 2)]
            p.setPen(Qt.NoPen)
            p.setBrush(colour)
            for a, b in zip(edges, edges[1:]):
                p.drawRoundedRect(QRectF(a + (1 if a > strip.left() else 0), strip.top(),
                                         b - a - (2 if b < strip.right() else 0) - (1 if a > strip.left() else 0),
                                         strip.height()), 2, 2)
            p.setPen(c["text"] if on or self._hover == i else c["muted"])
            p.drawText(QRectF(r.left() + 4, r.bottom() - fm.height() - 7, r.width() - 8, fm.height()),
                       Qt.AlignHCenter | Qt.AlignVCenter, f"{track}  \u00d7 {count}")
        p.end()


class _HoverDemo(QObject):
    """Rest the mouse on a setting and the frame beside it plays what that setting does."""

    def __init__(self, pad, key, widgets):
        super().__init__(pad)
        self.pad, self.key = pad, key
        self.wait = QTimer(self)
        self.wait.setSingleShot(True)
        self.wait.setInterval(350)
        self.wait.timeout.connect(lambda: pad.demo(key))
        self.widgets = list(widgets)
        for w in widgets:
            w.installEventFilter(self)

    def eventFilter(self, obj, event):
        t = event.type()
        try:
            if t == QEvent.Enter:
                self.wait.start()
            elif t in (QEvent.Leave, QEvent.Hide, QEvent.MouseButtonPress, QEvent.KeyPress, QEvent.Wheel):
                if t == QEvent.Leave and any(w.underMouse() for w in self.widgets if w is not obj):
                    return False  # only moved from the number's edge onto the number
                self.wait.stop()  # leaving - or changing it yourself: back to the real thing
                if self.pad.demo_key == self.key:
                    self.pad.demo(None)
        except RuntimeError:  # the editor was rebuilt: the pad is gone
            pass
        return False


# -- where in the frame --
class SideOrUnder(QWidget):
    """Two parts side by side while there's room, the second under the first when there isn't (In the frame: the
    frame, its numbers) - so the editor is never wider than its window."""

    def __init__(self, spacing=22):
        super().__init__()
        from PySide6.QtWidgets import QBoxLayout, QLayout
        self._across, self._down = QBoxLayout.Direction.LeftToRight, QBoxLayout.Direction.TopToBottom
        self.box = QBoxLayout(self._across)
        self.box.setContentsMargins(0, 0, 0, 0)
        self.box.setSpacing(spacing)
        self.box.setSizeConstraint(QLayout.SetNoConstraint)  # (its least width is the stacked one: minimumSizeHint)
        self.setLayout(self.box)

    def _parts(self):
        return [self.box.itemAt(i) for i in range(self.box.count())]

    def _side_by_side(self):
        return sum(item.sizeHint().width() for item in self._parts()) + self.box.spacing() * max(0, self.box.count() - 1)

    def minimumSizeHint(self):
        width = max((item.minimumSize().width() for item in self._parts()), default=0)
        return QSize(width, self.heightForWidth(self.width() if self.width() > 0 else self._side_by_side()))

    def sizeHint(self):
        return QSize(self._side_by_side(), self.heightForWidth(self._side_by_side()))

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        parts = self._parts()
        if width >= self._side_by_side():
            return max((item.sizeHint().height() for item in parts), default=0)
        return sum(item.sizeHint().height() for item in parts) + self.box.spacing() * max(0, len(parts) - 1)

    def _fit(self):
        """Side by side or under, for the width it has - and its height said every time (a layout doesn't always
        ask: said only on a switch, the row lay flat - In the frame gone - at full width)."""
        want = self._across if self.width() >= self._side_by_side() else self._down
        if self.box.direction() != want:
            self.box.setDirection(want)
        height = self.heightForWidth(self.width())
        if self.minimumHeight() != height:
            self.setMinimumHeight(height)
            self.updateGeometry()

    def resizeEvent(self, event):
        self._fit()
        super().resizeEvent(event)

    def showEvent(self, event):
        self._fit()
        super().showEvent(event)


class FramePad(_Scaled, QWidget):
    """The frame with the next insert's pictures in it, numbered in the
    order they go on (later ones on top) - exactly where they'll land, for
    16:9 pictures. Drag to move them all; double-click to centre. Parts
    that would fall outside the frame show faintly around it."""
    changed = Signal()

    def __init__(self, settings, preset, seed_getter):
        super().__init__()
        self.settings = settings
        self.preset = preset
        self.seed_getter = seed_getter
        self.count = 6
        self.shapes = None  # [(width, height)] of the pictures of the next insert, when they're known
        self._drag = None
        self.setFixedSize(_px(300), _px(186))
        self.setMouseTracking(True)  # (the hand only over the frame - it was over the whole drawing, 2026-10-19)
        self.demo_key = None
        self._demo_t = 0.0
        self._demo_timer = QTimer(self)
        self._demo_timer.setInterval(33)
        self._demo_timer.timeout.connect(self._demo_tick)

    # what each setting does, played while the mouse rests on it:
    # key -> (what it is when it does nothing, a value worth showing, at least this many pictures, caption)
    DEMOS = {
        "scale": (100.0, 45.0, 1, "Size: how big each picture is"),
        "scale_vary": (0.0, 35.0, 4, "\u00b1 Size: each one a different size"),
        "x": (0.0, 30.0, 1, "X: left and right"),
        "y": (0.0, 30.0, 1, "Y: up and down"),
        "scatter": (0.0, 70.0, 5, "Scatter: each one lands somewhere else"),
        "scatter_random": (0.0, 100.0, 9, "Randomness: from a tidy grid to a loose pile"),
        "rotation": (0.0, 20.0, 1, "Turn: every picture turned the same"),
        "rotation_vary": (0.0, 14.0, 4, "\u00b1 Turn: each one turned differently"),
        "opacity": (100.0, 35.0, 2, "Opacity: how see-through they are"),
        "margin": (0.0, 12.0, 5, "Margin: room at the edges - below 0, over them"),
    }

    def demo(self, key):
        self.demo_key = key if key in self.DEMOS else None
        self._demo_t = 0.0
        if self.demo_key:
            self._demo_timer.start()
        else:
            self._demo_timer.stop()
        self.update()

    def _demo_tick(self):
        self._demo_t += 0.033
        self.update()

    def _shown(self):
        """(preset, count, caption) to draw: the real one, or a setting's demo swinging between off and on."""
        if not self.demo_key:
            return self.preset, self.count, ""
        off, example, least, caption = self.DEMOS[self.demo_key]
        value = self.preset[self.demo_key]
        on = value if abs(value - off) > 1e-6 else example
        swing = (1 - math.cos(self._demo_t * math.pi / 1.1)) / 2  # off -> on -> off, eased, every 2.2 s
        shown = dict(self.preset)
        shown[self.demo_key] = off + (on - off) * swing
        if self.demo_key in ("scale_vary", "scatter", "scatter_random", "margin"):
            if shown["scale"] > 60:
                shown["scale"] = 40.0  # room to see them move
        if self.demo_key in ("margin", "scatter_random") and not shown["scatter"]:
            shown["scatter"] = 100.0
        return shown, max(self.count, least), caption

    def _frame(self):
        fw = self._w() * 0.74
        fh = fw * 9 / 16
        return QRectF((self._w() - fw) / 2, (self._h() - fh) / 2, fw, fh)

    def mousePressEvent(self, event):
        if not self._frame().contains(self._mouse(event)):
            return
        self._drag = self._mouse(event)
        self._start = (self.preset["x"], self.preset["y"])
        self.setCursor(Qt.ClosedHandCursor)

    def mouseMoveEvent(self, event):
        if self._drag is None:
            self.setCursor(Qt.OpenHandCursor if self._frame().contains(self._mouse(event)) else Qt.ArrowCursor)
            return
        f = self._frame()
        d = self._mouse(event) - self._drag
        snap = 1 if event.modifiers() & Qt.ShiftModifier else 0.5
        x = max(-100.0, min(100.0, self._start[0] + d.x() / f.width() * 100))
        y = max(-100.0, min(100.0, self._start[1] - d.y() / f.height() * 100))
        self.preset["x"] = round(x / snap) * snap
        self.preset["y"] = round(y / snap) * snap
        self.update()
        self.changed.emit()

    def mouseReleaseEvent(self, event):
        self._drag = None
        self.setCursor(Qt.OpenHandCursor if self._frame().contains(self._mouse(event)) else Qt.ArrowCursor)

    def mouseDoubleClickEvent(self, event):
        self.preset["x"] = self.preset["y"] = 0.0
        self.update()
        self.changed.emit()

    def paintEvent(self, event):
        c = _colors(self.settings.theme)
        p = self._painter(self)
        p.setFont(_fd(1.0, self.font()))
        p.setRenderHint(QPainter.Antialiasing)
        f = self._frame()
        shown, count, caption = self._shown()
        draw_frame_art(p, f, shown, c, seed=self.seed_getter(), count=count, frame=f, numbers=not caption,
                       overflow=True, shapes=self.shapes if count == self.count else None)
        p.setPen(QPen(_alpha(c["muted"], 0.3), 1, Qt.DotLine))
        p.drawLine(QPointF(f.center().x(), f.top()), QPointF(f.center().x(), f.bottom()))
        p.drawLine(QPointF(f.left(), f.center().y()), QPointF(f.right(), f.center().y()))
        if shown.get("inside", True) and shown.get("margin", 0):
            m = shown["margin"] / 100
            p.setPen(QPen(_alpha(c["accent"], 0.6), 1, Qt.DashLine))
            p.setBrush(Qt.NoBrush)
            p.drawRect(f.adjusted(f.width() * m, f.height() * m, -f.width() * m, -f.height() * m))
        p.setPen(QPen(c["text"], 1.2))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(f, 3, 3)
        if caption:
            p.setPen(c["text"])
            p.drawText(QRectF(0, f.bottom() + 4, self._w(), self._h() - f.bottom() - 4),
                       Qt.AlignHCenter | Qt.AlignVCenter, caption)
        p.end()


# -- the dialog --
WHERE = [("playhead", "At the playhead"), ("markers", "At every marker"), ("cuts", "At every cut")]
ALIGN = [("start", "Starts there"), ("centre", "Centred"), ("end", "Ends there"), ("loudest", "Loudest there")]
OVERLAP = [("stack", "Stacked"), ("cut_first", "Cut the first"), ("cut_next", "Cut the next"),
           ("back_to_back", "Back to back")]
ORDER = [("turns", "In order"), ("random", "At random")]
PAIR = [("both", "Both on each"), ("turns", "One per marker")]
SIZE_BY = [("fit", "The whole picture"), ("width", "The frame's width"), ("height", "The frame's height"),
           ("fill", "Filling the frame")]
CUT_EDGES = [("between", "Where they meet"), ("starts", "Every start"), ("ends", "Every end"), ("both", "Both")]
REPEAT = [("once", "Each once"), ("match", "Repeat")]
RUN_OUT = [("repeat", "Start over"), ("once", "Each once"), ("sounds_repeat", "Sounds repeat"),
           ("pictures_repeat", "Pictures repeat")]
SPACING = [("together", "Stacked"), ("back_to_back", "Back to back"), ("interval", "Spaced out")]
MEDIA = [("both", "Picture & sound"), ("video", "Picture only"), ("audio", "Sound only")]
ENDS = [("own", "Own length"), ("together", "End together")]
ENDS_PICTURES = ENDS + [("audio", "With the sounds")]
ENDS_SOUNDS = ENDS + [("pictures", "With the pictures"), ("first", "With the first")]
CONVERT = [("none", "Leave them"), ("compound", "Compound clip"), ("fusion", "Fusion clip")]


class InsertAsDialog(QDialog):
    def __init__(self, settings, parent=None, sample=None, fps=30.0, markers=None, shapes=None, paths=None,
                 events=None):
        super().__init__(parent)
        self.events = events    # the open timeline's {"markers": {frame: colour}, "cuts": [frame]} - drawn as they are
        self.paths = paths      # the staged clips' files, in order - for their sound (At every marker)
        self.markers = markers  # {colour: how many} on this timeline; None: no timeline to look at
        self.shapes = shapes    # [(width, height)] of the staged pictures, in order - for In the frame
        self.settings = settings
        self.sample = sample or [("still", 150, f"Photo {i}") for i in range(1, 6)]
        self.sample_is_example = not sample
        self.fps = fps or 30.0
        self.setObjectName("AppDialog")
        self.setWindowTitle("Insert as")
        from .theme import window_sheet
        _REL[0] = rel(settings, "insert_as")
        _K[0] = size_of(settings)
        self.setFont(_f())
        self.setStyleSheet(window_sheet(settings, "insert_as"))  # (its own zoom: every word in it)
        self.next_action = None
        self.insert_now = False
        self.preset = copy.deepcopy(pm.active(settings))
        self.muted = settings.theme["picker_folder"]

        header = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(_px(2))
        title = QLabel("Insert as")
        title.setObjectName("DialogTitle")
        titles.addWidget(title)
        header.addLayout(titles, 1)
        # (undo / redo: Ctrl+Z, Ctrl+Shift+Z - no buttons for them, "that looks ridiculous", 2026-10-14)
        self._undo, self._redo = [], []
        self._last_state, self._last_push = None, 0.0

        self.grid = PresetGrid(settings)
        self.grid.picked.connect(self._pick)
        self.grid.activated.connect(self._use_now)
        self.grid.add_new.connect(self._duplicate)

        self.scroll = QScrollArea()
        self.scroll.setObjectName("SettingsScroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)


        footer = QHBoxLayout()
        # why Insert now didn't go: said here - in the picker's bar it came after this closed, and was missed
        self.cannot = QLabel("")
        from .actions_panel import script_red
        self.cannot.setStyleSheet(f"color: {script_red(settings.theme).name()};")
        self._cannot_timer = QTimer(self)
        self._cannot_timer.setSingleShot(True)
        self._cannot_timer.timeout.connect(lambda: self.cannot.setText(""))
        footer.addWidget(self.cannot)
        footer.addStretch()
        use = QPushButton("Insert now")
        use.clicked.connect(lambda: self._use_now(self.preset["id"]))
        done = QPushButton("Done")
        done.setDefault(False)
        done.setAutoDefault(False)
        use.setAutoDefault(False)
        done.clicked.connect(self.accept)
        footer.addWidget(use)
        footer.addWidget(done)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(_px(22), _px(18), _px(22), _px(14))
        outer.setSpacing(_px(12))
        outer.addLayout(header)
        outer.addWidget(self.scroll, 1)
        outer.addLayout(footer)
        self.resize(820, 760)
        self._refresh_grid()
        self._build_editor()
        self._settle()
        self.grid.setFocus()

    # -- presets --
    def _items(self):
        return pm.all_presets(self.settings)

    def zoom_window(self, direction):
        """Ctrl and + / - / 0: Insert as by itself larger, smaller, as it ships (fonts.step_zoom)."""
        from .fonts import step_zoom
        from .theme import window_sheet
        step_zoom(self.settings, "insert_as", direction)
        self.settings.save()
        _REL[0] = rel(self.settings, "insert_as")
        _K[0] = size_of(self.settings)
        self.setFont(_f())
        self.setStyleSheet(window_sheet(self.settings, "insert_as") + getattr(self, "in_place_css", ""))
        self.grid.size_tiles()
        self._refresh_grid()
        self._build_editor()

    def _refresh_grid(self):
        self.grid.set_items(self._items(), self.preset["id"], self.settings.presets.get("active"))

    def _pick(self, pid):
        preset = pm.get(self.settings, pid)
        if preset is None:
            return
        self.preset = copy.deepcopy(preset)
        pm.set_active(self.settings, pid)
        self.settings.save()
        self._refresh_grid()
        self._build_editor()
        if hasattr(self, "_undo"):
            self._settle()

    def _nowhere(self, preset):
        """What stops an insert at every marker / cut on this timeline ("" when nothing does) - the picker's
        own check, with what it was handed."""
        where = preset.get("where")
        if self.events is None or where not in ("markers", "cuts"):
            return ""
        if where == "cuts":
            return "" if _cuts(self.events, preset) else \
                f"No cuts on {', '.join(preset.get('cut_tracks') or ['V1'])} to put them at"
        colours = preset.get("marker_colours") or []
        if any(not colours or c in colours for c in (self.events.get("markers") or {}).values()):
            return ""
        only = " or ".join(c.lower() for c in colours)
        return f"No {only} markers on the timeline" if only else "No markers on the timeline"

    def _use_now(self, pid):
        why = self._nowhere(self.preset if pid == self.preset["id"] else (pm.get(self.settings, pid) or {}))
        if why:
            self.cannot.setText(why)
            self._cannot_timer.start(4000)
            return
        pm.set_active(self.settings, pid)
        self.settings.save()
        self.insert_now = True
        self.accept()

    # -- undo --
    def _remember(self):
        """Keeps how the presets were before this change (quick changes in a row - a drag - count as one)."""
        now = time.monotonic()
        if self._last_state is not None and now - self._last_push > 0.8:
            self._undo.append(self._last_state)
            del self._undo[:-100]
            self._redo.clear()
        self._last_push = now

    def _settle(self):
        self._last_state = copy.deepcopy(self.settings.presets)

    def undo(self, redo=False):
        source, target = (self._redo, self._undo) if redo else (self._undo, self._redo)
        if not source:
            return
        target.append(copy.deepcopy(self.settings.presets))
        self.settings.presets = source.pop()
        self._settle()
        self._last_push = 0.0
        self.settings.save()
        current = pm.get(self.settings, self.preset["id"]) or pm.active(self.settings)
        self.preset = copy.deepcopy(current)
        self._refresh_grid()
        self._build_editor()

    FRAME_MOST = 40  # pictures drawn in the frame at most (Not touching holds up to this many apart)

    def _frame_count(self):
        """(how many pictures the frame shows, their shapes): as many as the insert puts in - Repeat's numbers,
        every marker counted (2026-10-16: "20 pictures, then there should be 20 squares") - each in
        the shape of the picture it is."""
        if self.sample_is_example or not any(kind != "audio" for kind, _f, _n in self.sample):
            return 5, None
        drawing = getattr(self, "_timeline_preview", None)  # (your markers or cuts, as the drawing has them)
        plan = pm.timeline_plan(self.preset, self.sample, self.fps, int(round(float(
            self.settings.presets.get("still_length", 5.0)) * self.fps)),
            events=drawing.real_events() if drawing is not None else None)
        going = [i["label"] for i in plan["items"] if i["kind"] != "audio"][:self.FRAME_MOST]
        if not going:
            return 1, None
        staged = [name for kind, _f, name in self.sample if kind != "audio"]
        shapes = None
        if self.shapes:  # (one shape for each staged picture, in order: a repeat has its own picture's)
            by_name = {name: self.shapes[n] for n, name in enumerate(staged) if n < len(self.shapes)}
            shapes = [by_name.get(label) for label in going]
            shapes = shapes if all(shape is not None for shape in shapes) else None
        return len(going), shapes

    def _save(self, rebuild=False):
        self._remember()
        pm.save(self.settings, self.preset)  # (a built-in's change is for this insert: it's never written down)
        fresh = pm.get(self.settings, self.preset["id"])
        if fresh is not None:
            self.preset["edited"] = fresh.get("edited", False)
        self.settings.save()
        self._refresh_grid()
        if getattr(self, "summary_label", None) is not None:
            self._show_summary()
        if getattr(self, "reset_button", None) is not None:
            edited = bool(self.preset.get("edited"))
            self.reset_button.setVisible(edited)
            self.keep_button.setVisible(edited)
            self.dup_button.setVisible(not edited)
        pad = getattr(self, "_pad", None)
        if pad is not None and not rebuild:  # (as many pictures in the frame as go in)
            pad.count, pad.shapes = self._frame_count()
        for w in getattr(self, "_live", []):
            refresh = getattr(w, "refresh", None)
            refresh() if refresh else w.update()
        if getattr(self, "_timeline_notes", None) is not None:
            self._timeline_notes.setText(self._timeline_preview.notes())
        if rebuild:
            self._build_editor()
        self._settle()

    def _show_summary(self):
        """What's changed, as chips under the name (or, nothing changed, what it does)."""
        chips = getattr(self, "summary_label", None)
        if chips is None:
            return
        base_words = "As it ships" if self.preset.get("builtin") else "The same as Normal"
        chips.set_changes(pm.changes(self.preset), pm.summary(self.preset) if not self.preset.get("builtin")
                          else (pm.summary(self.preset) or base_words))
        chips.setToolTip(pm.summary(self.preset) or "")

    def _take_back(self, keys):
        """A chip's ✕: that change taken back by itself - to how it ships (yours: to Normal)."""
        base = pm.base_of(self.preset)
        for key in keys:
            self.preset[key] = copy.deepcopy(base[key])
        self._save(rebuild=True)

    def _save_as_mine(self):
        """A built-in preset as it's been changed, kept as one of your own ("My normal") - the built-in back
        to how it ships. The copy is the one in use, its name ready to change."""
        self._last_push = 0.0
        self._remember()
        pid, _name = pm.own_copy(self.settings, self.preset)
        self.settings.presets["edits"].pop(self.preset["id"], None)
        self.settings.save()
        self._pick(pid)
        if getattr(self, "name_edit", None) is not None:
            self.name_edit.setFocus()
            self.name_edit.selectAll()

    def _duplicate(self):
        self._last_push = 0.0
        self._remember()
        made = pm.duplicate(self.settings, self.preset)
        self._pick(made["id"])
        if getattr(self, "name_edit", None) is not None:
            self.name_edit.setFocus()
            self.name_edit.selectAll()

    def _delete(self):
        self._last_push = 0.0
        self._remember()
        pid = self.preset["id"]
        was_builtin = self.preset.get("builtin")
        pm.delete(self.settings, pid)
        self.settings.save()
        self._pick(pid if was_builtin else "normal")
        self._settle()

    # -- the editor --
    def _new_page(self, editor):
        """The tiles and the editor, as a fresh page in the scroll area."""
        keep = self.scroll.verticalScrollBar().value()
        old = self.scroll.takeWidget()
        if old is not None:
            self.grid.setParent(None)
            old.deleteLater()
        page = QWidget()
        page.setObjectName("SettingsPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, _px(6), 0)
        layout.addWidget(self.grid)
        layout.addWidget(editor)
        layout.addStretch()
        self.scroll.setWidget(page)
        self.scroll.verticalScrollBar().setValue(keep)

    def _row(self, title, description, control):
        label = QLabel(title)
        label.setObjectName("SettingTitle")
        if hasattr(control, "scrub_from"):  # a number: drag over its name to change it, too
            control.scrub_from(label)
        if hasattr(control, "default_value"):
            reset_on_double_click(label, control, control.default_value)
        return _setting_row(label, description, control, self.muted)

    def _spin(self, key, minimum, maximum, suffix="", decimals=None, step=1, special=None, rebuild=False):
        if decimals is None:
            box = DragSpinBox()
            box.setRange(int(minimum), int(maximum))
            box.setValue(int(self.preset[key]))
        else:
            box = DragDoubleSpinBox()
            box.setDecimals(decimals)
            box.setRange(minimum, maximum)
            box.setValue(float(self.preset[key]))
        box.setSingleStep(step)
        if suffix:
            box.setSuffix(f" {suffix}")
        if special:
            box.setSpecialValueText(special)
        box.setFixedWidth(_px(120))

        def changed(v):
            self.preset[key] = int(v) if decimals is None else float(v)
            self._save(rebuild=rebuild)
        box.valueChanged.connect(changed)
        box.default_value = pm.FIELDS.get(key, 0)
        self._spins[key] = box
        return box

    def _length_field(self, key, whole, step, fallback):
        """A length that can be the whole clip (LengthField) - a switch, not a 0 to type."""
        field = LengthField(self.settings, float(self.preset[key]), whole, step, fallback)

        def changed(v):
            self.preset[key] = float(v)
            self._save()
        field.valueChanged.connect(changed)
        field.default_value = pm.FIELDS.get(key, 0.0)
        self._spins[key] = field
        return field

    def _lengths_block(self, preset):
        """How long clips are and where they end, right under the drawing that shows it: the pictures
        (and videos) on the left, the sounds on the right - each with its own way of ending and its
        own number. The same numbers are set by dragging the end of the last picture or sound in the
        drawing (TimelinePreview.edited)."""
        from PySide6.QtWidgets import QGraphicsOpacityEffect
        can_end = preset["where"] == "playhead" and preset["spacing"] != "back_to_back"
        holder = QWidget()
        sides = QHBoxLayout(holder)
        sides.setContentsMargins(0, _px(6), 0, 0)
        sides.setSpacing(_px(26))

        def side(title, colour):
            column = QVBoxLayout()
            column.setSpacing(_px(7))
            head = QLabel(f"<span style='color:{colour}'>\u25cf</span>&nbsp; <b>{title}</b>")
            head.setTextFormat(Qt.RichText)
            column.addWidget(head)
            sides.addLayout(column, 1)
            return column

        def line(column, words, control):
            row = QWidget()
            h = QHBoxLayout(row)
            h.setContentsMargins(0, 0, 0, 0)
            label = QLabel(words)
            if hasattr(control, "scrub_from"):
                control.scrub_from(label)
            if hasattr(control, "default_value"):
                reset_on_double_click(label, control, control.default_value)
            h.addWidget(label)
            h.addStretch(1)
            h.addWidget(control)
            column.addWidget(row)
            return row

        def note(column, words):
            label = QLabel(words)
            label.setWordWrap(True)
            label.setStyleSheet(f"color: {self.muted};")
            column.addWidget(label)

        theme = self.settings.theme
        # -- pictures and videos --
        pictures = side("Pictures and videos", theme["color_video"])
        mode = preset.get("ends", "own") if can_end else "own"
        if can_end:
            pictures.addWidget(self._choice("ends", ENDS_PICTURES, lambda k: _end_tile(k, False), rebuild=True, tile_w=100))
        length = None
        if mode == "audio":
            note(pictures, "They all end when the last sound does.")
        elif mode == "together":
            note(pictures, "They all end when the last one does.")
            length = self._length_field("length", "As long as it is", 0.5, 2.0)
            line(pictures, "The last one lasts", length)
        else:
            length = self._length_field("length", "Whole clip", 0.5, 2.0)
            line(pictures, "Each one lasts", length)
        lasts = line(pictures, "A picture lasts", self._picture_length_spin())
        fade = QGraphicsOpacityEffect(lasts)
        lasts.setGraphicsEffect(fade)

        def lasts_matters(value):  # a picture has no length of its own: this is it, while nothing above says
            unused = bool(value) or mode == "audio"
            lasts.setEnabled(not unused)
            fade.setOpacity(0.4 if unused else 1.0)
            lasts.setToolTip("Not used now - the pictures' length is decided above." if unused else
                             "A picture has no length of its own: it lasts this long. The same in every preset.")
        self._lasts_matters = lasts_matters
        if length is not None:
            length.valueChanged.connect(lasts_matters)
        lasts_matters(preset["length"])
        pictures.addStretch(1)

        # -- sounds --
        sounds = side("Sounds", theme["color_audio"])
        mode_s = preset.get("ends_audio", "own") if can_end else "own"
        if can_end:
            sounds.addWidget(self._choice("ends_audio", ENDS_SOUNDS, lambda k: _end_tile(k, True), rebuild=True, tile_w=100))
        if mode_s == "first":
            note(sounds, "They all end when the first one does.")
            line(sounds, "The first one lasts", self._length_field("length_audio", "As long as it is", 0.1, 1.0))
        elif mode_s == "together":
            note(sounds, "They all end when the last one does.")
            line(sounds, "The last one lasts", self._length_field("length_audio", "As long as it is", 0.1, 1.0))
        else:
            line(sounds, "Each one lasts", self._length_field("length_audio", "Whole sound", 0.1, 1.0))
        sounds.addStretch(1)
        return holder

    def _length_dragged(self, key, seconds, done):
        """The end of the last picture or sound was dragged in the drawing: the same number as the field."""
        self.preset[key] = seconds
        spin = self._spins.get(key)
        if spin is not None:
            spin.blockSignals(True)
            spin.setValue(seconds)
            spin.blockSignals(False)
        if key == "length" and getattr(self, "_lasts_matters", None):
            self._lasts_matters(seconds)
        if done:
            self._save()
        else:  # while it's being dragged: just the drawing and what it says
            self._timeline_preview.refresh()
            self._timeline_notes.setText(self._timeline_preview.notes())
            self._show_summary()

    def _picture_length_spin(self):
        """How long a picture lasts with no Length set - one number for the whole app (presets "still_length")."""
        box = DragDoubleSpinBox()
        box.setDecimals(2)
        box.setRange(0.04, 3600.0)
        box.setValue(float(self.settings.presets.get("still_length", 5.0)))
        box.setSingleStep(0.5)
        box.setSuffix(" s")
        box.setFixedWidth(_px(120))

        def changed(v):
            self.settings.presets["still_length"] = round(float(v), 3)
            self._save()
        box.valueChanged.connect(changed)
        box.default_value = pm.DEFAULTS["still_length"]
        return box

    def _choice(self, key, options, art, rebuild=True, tile_w=104):
        tiles = ChoiceTiles(self.settings, [(k, label, art(k)) for k, label in options], self.preset[key],
                            tile_w=tile_w)

        def changed(value):
            self.preset[key] = value
            self._save(rebuild=rebuild)
        tiles.changed.connect(changed)
        return tiles

    def _build_editor(self):
        self._live = []
        self._pad = None
        self._spins = {}
        # (what belongs to the editor as it was - for another preset, or before a tile was clicked - is gone
        # with it: a name field only your own presets have, a Reset button only the built-in ones have ...
        # Holding on to one threw "already deleted" at every change after Duplicate.)
        self.name_edit = self.reset_button = self.keep_button = self.dup_button = self.summary_label = None
        self._curve = self._curve_tiles = self._exact_edit = self._lasts_matters = None
        self._timeline_preview = self._timeline_notes = None
        preset = self.preset
        holder = QWidget()
        v = QVBoxLayout(holder)
        v.setContentsMargins(0, _px(6), 0, 0)
        v.setSpacing(0)

        # the name, what's changed (each a chip to take back by itself), and its buttons - which show what they
        # do while the mouse is on them: Save puts a faint tile in Yours, Reset fades the changes it takes back
        from .glyphs import glyph_icon
        head = _card(self.settings)
        top = QWidget()
        h = QHBoxLayout(top)
        h.setContentsMargins(_px(16), _px(12), _px(16), _px(12))
        h.setSpacing(_px(10))
        text = QVBoxLayout()
        text.setSpacing(_px(6))
        if preset.get("builtin"):
            name = QLabel(preset["name"])
            name.setObjectName("AboutName")
            text.addWidget(name)
        else:
            self.name_edit = QLineEdit(preset["name"])
            self.name_edit.setPlaceholderText("Name")
            self.name_edit.textChanged.connect(self._rename)
            text.addWidget(self.name_edit)
        self.summary_label = ChangeChips(self.settings)
        self.summary_label.reverted.connect(self._take_back)
        self._show_summary()
        text.addWidget(self.summary_label)
        h.addLayout(text, 1)
        icon = lambda glyph, mirror=False: glyph_icon(glyph, self.settings.theme["picker_text"], mirror=mirror)

        def shows(button, enter, leave):  # the mouse on a button: what it does, shown before it's clicked
            class _Show(QObject):
                def eventFilter(self, obj, event):
                    if event.type() == QEvent.Enter:
                        enter()
                    elif event.type() == QEvent.Leave:
                        leave()
                    return False
            button.installEventFilter(_Show(button))

        def ghost():
            self.grid.ghost = (dict(self.preset), pm.copy_name(self.settings, self.preset))
            self.grid.update()

        def no_ghost():
            self.grid.ghost = None
            self.grid.update()
        dup = self.dup_button = QPushButton(" Duplicate")
        dup.setIcon(icon("copy_code"))
        dup.clicked.connect(self._duplicate)
        shows(dup, ghost, no_ghost)
        h.addWidget(dup, 0, Qt.AlignVCenter)
        if preset.get("builtin"):
            # a change to a built-in one is for this insert - Save keeps it as one of yours
            self.keep_button = QPushButton(" Save")
            self.keep_button.setIcon(icon("save"))
            self.keep_button.clicked.connect(self._save_as_mine)
            shows(self.keep_button, ghost, no_ghost)
            h.addWidget(self.keep_button, 0, Qt.AlignVCenter)
            self.reset_button = QPushButton(" Reset")
            self.reset_button.setIcon(icon("undo"))
            self.reset_button.clicked.connect(self._delete)
            shows(self.reset_button, lambda: self.summary_label.set_dim(True), lambda: self.summary_label.set_dim(False))
            h.addWidget(self.reset_button, 0, Qt.AlignVCenter)
            edited = bool(preset.get("edited"))
            self.reset_button.setVisible(edited)
            self.keep_button.setVisible(edited)
            dup.setVisible(not edited)
        else:
            delete = QPushButton(" Delete")
            delete.clicked.connect(self._delete)
            shows(delete, lambda: self.grid.set_fading(self.preset["id"]), lambda: self.grid.set_fading(None))
            h.addWidget(delete, 0, Qt.AlignVCenter)
        head.add(_free_row(top))
        v.addWidget(_section("", head))

        # the next insert on a little timeline - made first (what's below draws with it), shown after where
        at_markers = preset["where"] != "playhead"
        preview = TimelinePreview(self.settings, preset, self._landing() if at_markers else self.sample, self.fps,
                                  loudest=[self._sound_of(n)["loudest"] for n in range(len(self.sample))]
                                  if at_markers else None, events=self.events)
        self._live.append(preview)
        self._timeline_preview = preview

        # where - the first thing to decide; at markers or cuts everything about them right under it
        where = _card(self.settings)
        where.add(_free_row(self._choice("where", WHERE, lambda k: _art_with(
            {**preset, "convert": "none", "colour": ""}, where=k, spacing="together"), tile_w=112)))
        if preset["where"] != "playhead":
            self._marker_options(where, preset)

        # several clips at the playhead: how they follow each other (the curve beside its numbers)
        if preset["where"] == "playhead":
            several = where
            several.add(self._row("Several clips", "", self._choice(
                "spacing", SPACING, lambda k: _art_with({**preset, "convert": "none", "colour": ""}, spacing=k),
                tile_w=104)))
            # each once, or again: until they match (the fewer start over) or up to a number of your own
            heard = sum(kind == "audio" for kind, _frames, _name in self.sample)
            seen = len(self.sample) - heard
            if self.sample and not self.sample_is_example:
                kinds = [f"{seen} picture{'s' if seen != 1 else ''}"] * bool(seen) + \
                    [f"{heard} sound{'s' if heard != 1 else ''}"] * bool(heard)
                control = QHBoxLayout()
                control.setSpacing(_px(10))
                repeat = preset["repeat"] if preset["spacing"] in pm.REPEATS else "once"
                tiles = ChoiceTiles(self.settings, [(k, label, _repeat_art(k, preset["spacing"], seen <= heard))
                                                    for k, label in REPEAT], repeat, tile_w=96)

                def pick(value):
                    self.preset["repeat"] = value
                    if value == "match" and self.preset["spacing"] not in pm.REPEATS:
                        self.preset["spacing"] = "back_to_back"  # (twenty copies stacked on one spot: no use)
                    self._save(rebuild=True)
                tiles.changed.connect(pick)
                control.addWidget(tiles)
                if repeat == "match":  # how many of each, in all (Match: as many as the other kind)
                    for key, what, there in (("pictures_count", "Pictures", seen), ("sounds_count", "Sounds", heard)):
                        if not there:
                            continue
                        box = QVBoxLayout()
                        box.setSpacing(_px(2))
                        name = QLabel(what)
                        name.setStyleSheet(f"color: {self.muted};")
                        spin = self._spin(key, 0, pm.COUNT_MAX, special="Match")
                        spin.setFixedWidth(_px(96))
                        spin.scrub_from(name) if hasattr(spin, "scrub_from") else None
                        spin.setToolTip(f"How many {what.lower()} in all - they start over until there are this "
                                        "many. Match: as many as the other kind.")
                        box.addWidget(name)
                        box.addWidget(spin)
                        control.addLayout(box)
                several.add(self._row("Pictures and sounds", ", ".join(kinds) + ".", control))
            if preset["spacing"] == "interval":
                # (pictures and sounds each follow the curve by themselves: drawn for the bigger group)
                kinds = [kind == "audio" for kind, _frames, _name in self.sample]
                clips = 0 if self.sample_is_example else max(kinds.count(True), kinds.count(False))
                curve = CurveEditor(self.settings, preset, clips, self.fps)
                curve.changed.connect(self._curve_changed)
                self._live.append(curve)
                self._curve = curve
                several.add(_free_row(curve))
                several.add(self._row("First gap", "From one clip's start to the next.",
                                      self._spin("gap", 0, 10000, "frames")))
                several.add(self._row("Last gap", "The curve goes from the first to the last.",
                                      self._spin("gap_end", 0, 10000, "frames")))
                shapes = [(k, pm.CURVE_LABELS[k]) for k in pm.CURVES]
                current = next((k for k, cv in pm.CURVES.items() if cv == list(preset["curve"])), "custom")
                tiles = ChoiceTiles(self.settings, [(k, label, _curve_art(pm.CURVES[k])) for k, label in shapes],
                                    current, tile_w=84, tile_h=58)

                def shape(key):
                    preset["curve"] = list(pm.CURVES[key])
                    self._save()
                tiles.changed.connect(shape)
                self._curve_tiles = tiles
                several.add(self._row("Curve", "", tiles))
                strength = StepSlider(self.settings, 1.0, 4.0, float(preset.get("curve_strength", 1.0)), "\u00d7",
                                      step=0.25, default=pm.FIELDS["curve_strength"], scale=_K[0])
                strength.setToolTip("1\u00d7 is the curve as drawn. 2\u00d7 applies it twice: an ease in barely "
                                    "moves at first and then rushes. The bold line shows the result.")

                def set_strength(value):
                    preset["curve_strength"] = float(value)
                    self._save()
                strength.changed.connect(set_strength)
                several.add(self._row("Strength", "How hard it eases.", strength))
                several.add(self._row("Vary", "Each gap a little random.",
                                      self._spin("vary", 0, 500, "frames", special="Off")))
                exact = self._exact_edit = QLineEdit(preset["gaps"])
                exact.setPlaceholderText("e.g. 17, 13, 9, 8, 4, 3")
                exact.setFixedWidth(_px(220))

                def typed(text):
                    preset["gaps"] = text
                    self._save()
                exact.textChanged.connect(typed)
                several.add(self._row("Exact gaps", "In place of the curve. The last one repeats.", exact))
        v.addWidget(_section("Where", where))

        # on the timeline: the drawing, with what of each clip goes in and how long right under it
        on_timeline = _card(self.settings)
        box = QWidget()
        bv = QVBoxLayout(box)
        bv.setContentsMargins(0, 0, 0, 0)
        bv.setSpacing(_px(6))
        what = QLabel((f"Your {len(self.sample)} clip{'s' if len(self.sample) != 1 else ''}"
                       if not self.sample_is_example else "An example: 5 stills (stage clips first to see yours)")
)
        what.setStyleSheet(f"color: {self.muted};")
        bv.addWidget(what)
        strip = _SideStrip()  # (sideways, once Ctrl+scroll has zoomed in)
        strip.setFrameShape(QScrollArea.NoFrame)
        strip.setWidgetResizable(True)
        strip.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        strip.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        strip.setWidget(preview)
        strip.setStyleSheet("QScrollArea, QScrollArea > QWidget > QWidget { background: transparent; }")
        preview.holder = strip
        strip.setFixedHeight(preview.minimumHeight() + 12)
        bv.addWidget(strip)
        self._timeline_notes = QLabel(preview.notes())
        self._timeline_notes.setWordWrap(True)
        self._timeline_notes.setTextFormat(Qt.RichText)
        bv.addWidget(self._timeline_notes)
        on_timeline.add(_free_row(box))
        if preset["where"] != "playhead":  # (right under the drawing that shows them)
            on_timeline.add(self._row("Where they'd overlap", "Markers closer together than a clip is long.",
                                      self._choice("overlap", OVERLAP, lambda k: _overlap_art(k, preset),
                                                   rebuild=False, tile_w=96)))
        media_art = {"both": lambda: _media_art("both"), "video": lambda: _media_art("video"),
                     "audio": lambda: _media_art("audio")}
        on_timeline.add(self._row("Picture & sound", "", self._choice("media", MEDIA, lambda k: media_art[k](), tile_w=96)))
        on_timeline.add(_free_row(self._lengths_block(preset)))  # how long, and where they end - beside what shows it
        preview.edited.connect(self._length_dragged)
        v.addWidget(_section("On the timeline", on_timeline))

        # in the frame - only when pictures go in (Sound only, or nothing but sounds staged: nothing to place)
        pictures_in = preset["media"] != "audio" and (self.sample_is_example
                                                      or any(kind != "audio" for kind, _f, _n in self.sample))
        if pictures_in:
            # in the frame: the picture on the left, everything that changes it right beside it
            frame = _card(self.settings)
            pad = FramePad(self.settings, preset, lambda pid=preset["id"]: pm.seed_for(self.settings, pid))
            pad.count, pad.shapes = self._frame_count()
            self._pad = pad
            pad.changed.connect(self._pad_moved)
            pad.setToolTip("Picture 1 goes on first, the rest on top.")
            self._live.append(pad)
            pad_row = SideOrUnder(_px(22))  # (the numbers under the frame when the window is narrow)
            ph = pad_row.box
            left = QVBoxLayout()
            left.setSpacing(_px(8))
            left.addWidget(pad)
            under = QHBoxLayout()
            shuffle = QPushButton("Shuffle")
            shuffle.setAutoDefault(False)
            shuffle.setToolTip("Another layout with the same settings - the next insert uses the one you see")

            def reroll():
                pm.reshuffle(self.settings, preset["id"])
                self.settings.save()
                pad.update()
            shuffle.clicked.connect(reroll)
            under.addWidget(shuffle)
            under.addStretch()
            left.addLayout(under)
            left.addStretch()
            ph.addLayout(left)

            grid = QGridLayout()
            grid.setHorizontalSpacing(_px(8))
            grid.setVerticalSpacing(_px(9))
            grid.setColumnStretch(4, 1)

            def line(at, title, tip, first, second=None, vary=False):
                label = QLabel(title)
                label.setObjectName("SettingTitle")
                label.setToolTip(tip)
                first.scrub_from(label)

                class _BackBoth(QObject):  # double-click the name: its numbers back to how they ship
                    def eventFilter(self, obj, event):
                        if event.type() == QEvent.MouseButtonDblClick:
                            for box in (first, second):
                                if box is not None:
                                    box.setValue(box.default_value)
                            return True
                        return False
                label.installEventFilter(_BackBoth(label))
                grid.addWidget(label, at, 0)
                keys = {id(box): key for key, box in self._spins.items()}
                for column, box in ((1, first), (3, second)):
                    if box is not None:
                        box.setFixedWidth(_px(104))
                        box.setToolTip(tip)
                        grid.addWidget(box, at, column)
                        # rest the mouse on it: the frame plays what it does
                        _HoverDemo(pad, keys[id(box)], [box, box.lineEdit()] + ([label] if box is first else []))
                if vary:  # the second number is "give or take, at random"
                    sign = QLabel("\u00b1")
                    sign.setStyleSheet(f"color: {self.muted};")
                    sign.setToolTip(tip)
                    grid.addWidget(sign, at, 2, Qt.AlignCenter)

            line(0, "Size", "How big each picture is. \u00b1: each one a random amount bigger or smaller.",
                 self._spin("scale", 1.0, 1000.0, "%", decimals=1, step=5),
                 self._spin("scale_vary", 0.0, 90.0, "%", decimals=0, step=5, special="Off"), vary=True)
            line(1, "Place", "Where the middle goes, from the centre of the frame: X to the right, Y up.",
                 self._spin("x", -100.0, 100.0, "%", decimals=1, step=1),
                 self._spin("y", -100.0, 100.0, "%", decimals=1, step=1))
            self._spins["x"].setPrefix("X  ")
            self._spins["y"].setPrefix("Y  ")
            line(2, "Scatter", "How far from that place the pictures are spread - at 100 % over the whole frame.",
                 self._spin("scatter", 0.0, 100.0, "%", decimals=0, step=5, special="Off"))
            line(3, "Randomness", "How loosely they're scattered: 0 % a tidy grid that fills the frame, 50 % a little "
                 "out of line, towards 100 % a loose pile that no longer reaches every edge.",
                 self._spin("scatter_random", 0.0, 100.0, "%", decimals=0, step=10))
            line(4, "Turn", "How far each picture is turned. \u00b1: each one a random amount more or less.",
                 self._spin("rotation", -360.0, 360.0, "\u00b0", decimals=1, step=5),
                 self._spin("rotation_vary", 0.0, 180.0, "\u00b0", decimals=0, step=2, special="Off"), vary=True)
            line(5, "Opacity", "How see-through each picture is.",
                 self._spin("opacity", 0.0, 100.0, "%", decimals=0, step=5))
            right = QVBoxLayout()
            right.addLayout(grid)
            right.addStretch()
            ph.addLayout(right, 1)
            frame.add(_free_row(pad_row))
            # what Size counts from (2026-10-17: "scale with the width or the height until they hit the side")
            frame.add(self._row("100 % is", "What Size counts from.",
                                self._choice("size_by", SIZE_BY, _size_by_art, tile_w=96)))

            def random_now(*_):  # Shuffle only has something to do when chance is involved
                shuffle.setEnabled(bool(preset["scatter"] or preset["scale_vary"] or preset["rotation_vary"]))
                # (Randomness stays usable with Scatter off, like every other box - greyed out it took no click, typing
                #  or drag, 2026-10-23: "does not work like the other text boxes". Its hover shows a scatter anyway.)
            for key in ("scatter", "scale_vary", "rotation_vary"):
                self._spins[key].valueChanged.connect(random_now)
            random_now()

            inside_box = QCheckBox()
            inside_box.setChecked(bool(preset.get("inside", True)))
            inside_switch = _switch(self.settings, inside_box)
            inside_box.hide()
            inside_holder = QHBoxLayout()
            inside_holder.addWidget(inside_box)
            inside_holder.addWidget(inside_switch)
            frame.add(self._row("Keep inside the frame", "A picture too big is made smaller.",
                                inside_holder))
            margin = self._spin("margin", -30.0, 40.0, "%", decimals=0, step=1)
            margin.setToolTip("Above 0: that much room stays free at the edges.\n"
                              "Below 0: pictures may go that far over the edge - a pile that touches the frame.")
            margin_row = self._row("Margin", "Below 0, pictures may go over the edges.",
                                   margin)
            _HoverDemo(pad, "margin", [margin_row])
            frame.add(margin_row)
            margin_row.setVisible(inside_box.isChecked())

            def set_inside(on):
                preset["inside"] = bool(on)
                margin_row.setVisible(bool(on))
                self._save()
            inside_box.toggled.connect(set_inside)
            # scattered: none touching another (2026-10-15) - presets._apart
            apart_box = QCheckBox()
            apart_box.setChecked(bool(preset.get("apart", False)))
            apart_switch = _switch(self.settings, apart_box)
            apart_box.hide()
            apart_holder = QHBoxLayout()
            apart_holder.addWidget(apart_box)
            apart_holder.addWidget(apart_switch)
            apart_row = self._row("Not touching", "Scattered pictures keep apart.", apart_holder)
            frame.add(apart_row)

            def apart_matters(*_):  # (only scattered pictures are moved apart)
                apart_row.setEnabled(bool(preset["scatter"]))
            self._spins["scatter"].valueChanged.connect(apart_matters)
            apart_matters()

            def set_apart(on):
                preset["apart"] = bool(on)
                self._save()
            apart_box.toggled.connect(set_apart)
            v.addWidget(_section("In the frame", frame))

        # afterwards
        after = _card(self.settings)
        after.add(self._row("Wrap them into", "",
                            self._choice("convert", CONVERT, lambda k: _symbol_art(
                                {"none": None, "compound": "compound", "fusion": "node"}[k]),
                                rebuild=False, tile_w=96)))
        after.add(self._row("Clip colour", "", self._swatches()))
        v.addWidget(_section("Afterwards", after))
        v.addSpacing(10)
        self._new_page(holder)
        from .settings_dialog import restrict_tab_to_inputs
        restrict_tab_to_inputs(self)

    def _sound_of(self, n):
        """The n-th staged clip's sound, as it lands: {"peaks" (0-1, or None), "loudest" (timeline frames from
        where it starts, or None), "frames" (a sound's length without its silence, or None)} - read once per
        file. Leave out silence counts: the drawing starts and ends where the sound does, as the insert will."""
        if not hasattr(self, "_sounds"):
            self._sounds = {}
        path = self.paths[n] if self.paths and n < len(self.paths) else ""
        kind, frames, _name = self.sample[n]
        if not path or kind == "still":
            return {"peaks": None, "loudest": None}
        if path not in self._sounds:
            found = {"peaks": None, "loudest": None}
            try:
                import threading
                from . import sound_analysis as sa
                from .video_preview import VideoPlayer
                seconds = frames / self.fps
                begin, end = 0.0, seconds
                if kind == "audio" and self.settings.listen.get("trim_silence", True):
                    sound = (sa.levels_only(path) or {}).get("sound")
                    if sound:
                        begin, end = sound[0], min(seconds, sound[1]) if sound[1] is not None else seconds
                        found["frames"] = max(1, int(round((end - begin) * self.fps)))
                loud = sa.loudest(path)
                if loud is not None:
                    found["loudest"] = max(0, int(round((loud - begin) * self.fps)))
                if seconds <= 90:  # (a long video: its loudest moment is enough)
                    peaks, _clipped = VideoPlayer._waveform_peaks(path, threading.Event(), 400)
                    if peaks and seconds > 0:
                        a, b = int(len(peaks) * begin / seconds), int(len(peaks) * min(1.0, end / seconds))
                        found["peaks"] = peaks[a:max(a + 1, b)]
            except Exception as e:
                print(f"[insert as] couldn't read the sound of {path}: {e}")
            self._sounds[path] = found
        return self._sounds[path]

    def _landing(self):
        """The staged clips as they land: a sound without its silence (the whole file was 2.3 s, the drawing
        drew it so, its waveform stretched over that - and its loudest moment, counted from where the sound
        starts, sat off the waveform's peak, 2026-10-20)."""
        return [(kind, self._sound_of(n).get("frames") or frames, label)
                for n, (kind, frames, label) in enumerate(self.sample)]

    def _nudge_block(self, preset):
        """Your clips on one marker - drag them off it, earlier or later. Each different clip once (the same
        one staged three times is one row)."""
        clips, seen = [], set()
        for n, (kind, frames, label) in enumerate(self._landing()):
            path = self.paths[n] if self.paths and n < len(self.paths) else ""
            if (label, path) in seen:
                continue
            seen.add((label, path))
            sound = self._sound_of(n)
            lands = pm.clip_length(preset, kind, frames, self.fps, self._timeline_preview.still_frames())
            peaks = sound["peaks"]
            if peaks and frames and lands < frames:  # (cut to its Length: only that much of it)
                peaks = peaks[:max(1, len(peaks) * lands // frames)]
            loudest = sound["loudest"] if sound["loudest"] is not None and sound["loudest"] <= lands else None
            clips.append({"kind": kind, "frames": lands, "label": label, "peaks": peaks, "loudest": loudest})
        clips.sort(key=lambda clip: clip["kind"] == "audio")  # pictures above sounds, as on the timeline
        nudge = MarkerNudge(self.settings, preset, clips, self.fps)
        nudge.together = getattr(self, "_together", True)
        caption = QLabel(nudge.caption())
        caption.setStyleSheet(f"color: {self.muted};")
        nudge.refresh = lambda: (nudge.update(), caption.setText(nudge.caption()))
        # together, or one by one
        together_box = QCheckBox()
        together_box.setChecked(nudge.together)
        together_box.hide()
        switch = _switch(self.settings, together_box)
        together_words = QLabel("Move together")
        together_words.setStyleSheet(f"color: {self.muted};")

        def set_together(on):
            self._together = nudge.together = bool(on)
            nudge.update()
        together_box.toggled.connect(set_together)

        def moved(seconds, done):
            caption.setText(nudge.caption())
            if done:
                self._save()
            else:
                self._timeline_preview.refresh()
                self._show_summary()
        nudge.changed.connect(moved)
        self._live.append(nudge)
        box = QWidget()
        bv = QVBoxLayout(box)
        bv.setContentsMargins(0, 0, 0, 0)
        bv.setSpacing(_px(2))
        bv.addWidget(nudge)
        under = QHBoxLayout()
        under.setContentsMargins(0, 0, 0, 0)
        under.addWidget(caption, 1)
        if len(clips) > 1:
            under.addWidget(together_words)
            under.addWidget(together_box)
            under.addWidget(switch)
        bv.addLayout(under)
        return box

    def _marker_options(self, card, preset):
        """At markers or cuts, in the order they're decided: which markers, which clip goes on each (and when
        there are more markers than clips), what of each is on the marker (the drawing right under it), and
        what happens where they'd overlap."""
        if preset["where"] == "markers":
            self._marker_rows(card, preset)
        elif preset["where"] == "cuts":
            self._cut_rows(card, preset)
        kinds = [kind for kind, _frames, _name in self.sample]
        has_sounds = "audio" in kinds
        has_pictures = any(k != "audio" for k in kinds) or self.sample_is_example
        both = not self.sample_is_example and has_sounds and has_pictures
        if both:
            card.add(self._row("Pictures and sounds", "",
                               self._choice("pair", PAIR, lambda k: _pair_art(k), rebuild=False, tile_w=96)))
        distinct = {}
        for kind, _frames, label in self.sample:
            group = "all" if not both or preset["pair"] == "turns" else ("audio" if kind == "audio" else "picture")
            distinct.setdefault(group, set()).add(label)
        if any(len(labels) > 1 for labels in distinct.values()):
            card.add(self._row("Several clips", "Which clip goes on each one.",
                               self._choice("order", ORDER, _order_art, rebuild=False, tile_w=96)))
        runs = RUN_OUT if both else RUN_OUT[:2]
        card.add(self._row("More markers than clips", "",
                           self._choice("run_out", runs, lambda k: _run_out_art(k), rebuild=False, tile_w=96)))
        # what of each clip is on the marker - for pictures and sounds each (a still has no loudest moment)
        videos = "video" in kinds
        if has_pictures:
            options = ALIGN if videos else ALIGN[:3]
            if preset["align_pictures"] not in [k for k, _l in options]:
                preset["align_pictures"] = "start"
            card.add(self._row("Pictures on the marker" if both else "On the marker",
                               "A video's loudest moment is its sound's." if videos else "",
                               self._choice("align_pictures", options,
                                            lambda k: _align_art(k, {**preset, "media": "video"}), tile_w=96)))
        if has_sounds:
            card.add(self._row("Sounds on the marker" if both else "On the marker",
                               "",
                               self._choice("align", ALIGN, lambda k: _align_art(k, {**preset, "media": "audio"}),
                                            tile_w=96)))
        card.add(_free_row(self._nudge_block(preset)))

    def _marker_rows(self, card, preset):
        """Which markers count: the colours on this timeline, with how many of each."""
        if self.markers is None:
            counts, about = {}, "Open a timeline to see its markers here."
        else:
            counts = self.markers
            about = "" if counts else "No markers on this timeline yet - add one with M."
        tiles = MarkerTiles(self.settings, counts, preset.get("marker_colours"))
        total = QLabel()
        total.setStyleSheet(f"color: {self.muted};")

        def tell():
            n = tiles.placed()
            only = ", ".join(c.lower() for c in tiles.chosen)
            total.setText(about or (f"{n} {only} marker{'s' if n != 1 else ''} on this timeline." if only else
                                    f"All {n} marker{'s' if n != 1 else ''} on this timeline."))

        def choose(colours):
            preset["marker_colours"] = colours
            tell()
            self._save()
        tiles.changed.connect(choose)
        tell()
        box = QWidget()
        bv = QVBoxLayout(box)
        bv.setContentsMargins(0, 0, 0, 0)
        bv.setSpacing(_px(8))
        title = QLabel("Which markers")
        title.setObjectName("SettingTitle")
        title.setToolTip("Click the colours that count - several is fine. All: every marker, whatever its colour.\n"
                         "The number is how many of that colour this timeline has, clip markers included.")
        bv.addWidget(title)
        bv.addWidget(tiles)
        bv.addWidget(total)
        card.add(_free_row(box))

    def _cut_rows(self, card, preset):
        """Which tracks' cuts count: every track on this timeline, with how many cuts it has."""
        by_track = _by_track(self.events)
        edges = preset.get("cut_edges", "between")
        tiles = CutTiles(self.settings, {t: pm.cut_frames(by_track, [t], edges) for t in by_track},
                         preset.get("cut_tracks"))
        total = QLabel()
        total.setStyleSheet(f"color: {self.muted};")

        def tell():
            if self.events is None:
                total.setText("Open a timeline to see its tracks here.")
                return
            n = len(pm.cut_frames(by_track, tiles.chosen, edges))
            total.setText(f"{n} cut{'s' if n != 1 else ''} on {', '.join(tiles.chosen)}.")

        def choose(tracks):
            preset["cut_tracks"] = tracks
            tell()
            self._save()
        tiles.changed.connect(choose)
        tell()
        box = QWidget()
        bv = QVBoxLayout(box)
        bv.setContentsMargins(0, 0, 0, 0)
        bv.setSpacing(_px(8))
        title = QLabel("Which cuts")
        title.setObjectName("SettingTitle")
        title.setToolTip("The tracks whose cuts count - several is fine: a cut on any of them is one.\n"
                         "The number is how many cuts that track has: where one clip begins after another.")
        bv.addWidget(title)
        bv.addWidget(tiles)
        bv.addWidget(total)
        card.add(_free_row(box))
        card.add(self._row("On the clips", "", self._choice("cut_edges", CUT_EDGES, _edges_art, tile_w=96)))

    def _rename(self, text):
        self.preset["name"] = text.strip() or "Untitled"
        self._save()

    def _curve_changed(self):
        for key in ("gap", "gap_end"):
            box = self._spins.get(key)
            if box is not None and box.value() != self.preset[key]:
                box.blockSignals(True)
                box.setValue(self.preset[key])
                box.blockSignals(False)
        tiles = getattr(self, "_curve_tiles", None)
        if tiles is not None:
            tiles.set_value(next((k for k, cv in pm.CURVES.items() if cv == list(self.preset["curve"])), "custom"))
        exact = getattr(self, "_exact_edit", None)
        try:
            if exact is not None and exact.text() != self.preset["gaps"]:  # a pillar was dragged
                exact.blockSignals(True)
                exact.setText(self.preset["gaps"])
                exact.blockSignals(False)
        except RuntimeError:  # (the field of an editor built before this one)
            self._exact_edit = None
        self._save()

    def _pad_moved(self):
        for key in ("x", "y"):
            box = self._spins.get(key)
            if box is not None:
                box.blockSignals(True)
                box.setValue(self.preset[key])
                box.blockSignals(False)
        self._save()

    def _swatches(self):
        dots = ColourDots(self.settings, self.preset["colour"])

        def pick(name):
            self.preset["colour"] = name
            self._save()
        dots.changed.connect(pick)
        return dots

    # -- keys --
    def keyPressEvent(self, event):
        combo = QKeySequence(event.keyCombination()).toString(QKeySequence.PortableText)
        if combo == QKeySequence("Alt+Left").toString(QKeySequence.PortableText):
            self.next_action = "settings"
            self.accept()
            return
        from .fonts import zoom_key
        direction = zoom_key(event, self.settings)
        if direction is not None:
            self.zoom_window(direction)
            return
        typing = isinstance(self.focusWidget(), QLineEdit) and not isinstance(
            self.focusWidget().parent(), QAbstractSpinBox)
        if event.matches(QKeySequence.Undo) and not typing:
            self.undo()
            return
        if event.matches(QKeySequence.Redo) and not typing:
            self.undo(redo=True)
            return
        if event.key() in (Qt.Key_Return, Qt.Key_Enter) and not isinstance(self.focusWidget(), QLineEdit):
            self._use_now(self.preset["id"])
            return
        super().keyPressEvent(event)
        if not self.isWindow():
            event.accept()  # in the picker's place: a key it has no use for never reaches the picker's own keys

    def showEvent(self, event):
        # over the always-on-top picker, with the keyboard (Wayland compositors and macOS don't
        # always hand focus to a dialog of a background app by themselves)
        super().showEvent(event)
        if not self.isWindow():
            return
        self.raise_()
        self.activateWindow()
        try:
            from .picker_window import bring_to_front
            bring_to_front(self)
        except Exception:
            pass

    def accept(self):
        self.settings.save()
        super().accept()


def _media_art(kind):
    def draw(p, r, c, on):
        h = r.height() * 0.42
        top = r.center().y() - h / 2
        rect = QRectF(r.left() + r.width() * 0.1, top, r.width() * 0.8, h)
        _block(p, rect, {**pm.FIELDS, "media": kind}, c)
    return draw


def _align_art(align, preset):
    def draw(p, r, c, on):
        x = r.center().x()
        w = r.width() * 0.42
        bars, peak = 14, 4  # (the loudest's waveform: its peak bar right under the marker)
        left = {"start": x, "centre": x - w / 2, "end": x - w, "loudest": x - w * (peak + 0.5) / bars}[align]
        h = r.height() * 0.36
        block = QRectF(left, r.center().y() - h / 2 + 3, w, h)
        if align == "loudest":  # a sound, its loudest moment on the marker
            _slab(p, block, c["audio"], min(2.5, h / 3))
            p.setPen(Qt.NoPen)
            p.setBrush(_alpha(c["bg"], 0.5))
            for i in range(bars):
                d = abs(i - peak) / bars
                bh = max(1.0, (h - 4) * max(0.12, 1 - d * 2.2))
                p.drawRect(QRectF(block.left() + i * w / bars + 0.4, block.center().y() - bh / 2, w / bars - 0.9, bh))
        else:
            _block(p, block, {**pm.FIELDS, "media": preset["media"]}, c)
        if preset["where"] == "markers":
            _pin(p, x, r.top(), max(5.0, r.height() * 0.22), c["accent"])
        p.setPen(QPen(c["accent"] if preset["where"] == "markers" else c["text"], 1.2))
        p.drawLine(QPointF(x, r.top() + r.height() * 0.2), QPointF(x, r.bottom()))
    return draw


def _overlap_art(rule, preset):
    """Two clips on two markers close together - what happens where they'd overlap."""
    def draw(p, r, c, on):
        m1, m2 = r.left() + r.width() * 0.2, r.left() + r.width() * 0.5
        w, h = r.width() * 0.5, r.height() * 0.2
        low, high = r.bottom() - h - 4, r.bottom() - 2 * h - 7
        look = {**pm.FIELDS, "media": "video"}
        first_end = m2 if rule == "cut_first" else m1 + w
        second = m2 if rule in ("stack", "cut_first") else first_end
        second_end = (m2 + w) if rule != "back_to_back" else first_end + w
        _block(p, QRectF(m1, low, first_end - m1 - 1, h), look, c)
        if rule == "cut_first":  # the part that goes
            p.setPen(Qt.NoPen)
            p.setBrush(_alpha(c["video"], 0.18))
            p.drawRoundedRect(QRectF(m2, low, m1 + w - m2, h), 2, 2)
        if rule == "cut_next":
            p.setPen(Qt.NoPen)
            p.setBrush(_alpha(c["video"], 0.18))
            p.drawRoundedRect(QRectF(m2, high, first_end - m2, h), 2, 2)
        _block(p, QRectF(second, high if rule == "stack" else low, min(second_end, r.right() - 2) - second, h), look, c)
        for mx in (m1, m2):
            _pin(p, mx, r.top(), max(5.0, r.height() * 0.2), c["accent"])
            p.setPen(QPen(_alpha(c["accent"], 0.6), 1, Qt.DotLine))
            p.drawLine(QPointF(mx, r.top() + r.height() * 0.2), QPointF(mx, r.bottom()))
    return draw


def _size_by_art(by):
    """A 16:9 frame and an upright photo in it, as big as `by` makes it at 100 % (cut off at the frame's edge)."""
    def draw(p, r, c, on):
        fh = r.height() - 4
        fw = min(r.width() - 4, fh * 16 / 9)
        frame = QRectF(r.center().x() - fw / 2, r.center().y() - fh / 2, fw, fh)
        aspect = 3 / 4
        base_w, base_h = fh * aspect, fh  # (fitted: as tall as the frame)
        k = pm.size_zoom(by, base_w, base_h, fw, fh)
        w, h = base_w * k, base_h * k
        p.save()
        p.setClipRect(frame)
        p.setPen(Qt.NoPen)
        p.setBrush(_alpha(c["accent"] if on else c["text"], 0.55 if on else 0.35))
        p.drawRoundedRect(QRectF(frame.center().x() - w / 2, frame.center().y() - h / 2, w, h), 2, 2)
        p.restore()
        p.setPen(QPen(c["text"] if on else c["muted"], 1.2))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(frame, 2, 2)
    return draw


def _edges_art(edges):
    """Three clips on a track, a gap before the last: a line at each place an insert goes."""
    def draw(p, r, c, on):
        h = r.height() * 0.24
        y = r.bottom() - h - 6
        spans = [(0.08, 0.36), (0.36, 0.62), (0.72, 0.92)]
        p.setPen(Qt.NoPen)
        for a, b in spans:
            _slab(p, QRectF(r.left() + r.width() * a + 1, y, r.width() * (b - a) - 2, h), c["video"], 2)
        frames = pm.track_edges(spans, edges)
        p.setPen(QPen(c["accent"] if on else c["text"], 1.4))
        for f in frames:
            x = r.left() + r.width() * f
            p.drawLine(QPointF(x, r.top() + 2), QPointF(x, r.bottom() - 2))
    return draw


def _pair_art(pair):
    """Pictures and sounds at markers: one of each on every marker, or taking turns."""
    def draw(p, r, c, on):
        w, h = r.width() * 0.2, r.height() * 0.17
        for n in range(3):
            x = r.left() + r.width() * (0.14 + n * 0.29)
            _pin(p, x, r.top(), max(5.0, r.height() * 0.2), c["accent"])
            p.setPen(Qt.NoPen)
            picture = pair == "both" or n % 2 == 0
            sound = pair == "both" or n % 2 == 1
            if picture:
                _slab(p, QRectF(x, r.bottom() - 2 * h - 7, w, h), c["video"], 2)
            if sound:
                _slab(p, QRectF(x, r.bottom() - h - 4, w, h), c["audio"], 2)
    return draw


def _repeat_art(rule, spacing, pictures_fewer=True):
    """One picture and three sounds (or the other way), back to back or spaced out: the picture once, or with
    every sound."""
    def draw(p, r, c, on):
        p.setPen(Qt.NoPen)
        h = r.height() * 0.2
        rows = {"few": r.bottom() - 2 * h - 8, "many": r.bottom() - h - 4}
        if not pictures_fewer:
            rows = {"few": rows["many"], "many": rows["few"]}
        few, many = (c["video"], c["audio"]) if pictures_fewer else (c["audio"], c["video"])
        for n in range(3):
            step, w = (0.28, 0.27) if spacing == "back_to_back" else (0.3, 0.18)  # (spaced out: gaps between)
            x = r.left() + r.width() * (0.08 + n * step)
            _slab(p, QRectF(x, rows["many"], w * r.width(), h), many, 2)
            if n == 0 or rule == "match":
                _slab(p, QRectF(x, rows["few"], w * r.width(), h), few, 2)
    return draw


def _run_out_art(rule):
    """Four markers, two pictures and a sound: what's on the markers after every clip has had one."""
    def draw(p, r, c, on):
        w, h = r.width() * 0.15, r.height() * 0.17
        picture_cols = [c["video"], QColor(c["video"]).lighter(135)]
        for n in range(4):
            x = r.left() + r.width() * (0.1 + n * 0.215)
            _pin(p, x, r.top(), max(5.0, r.height() * 0.2), c["accent"])
            again = n >= 2
            p.setPen(Qt.NoPen)
            if not again or rule in ("repeat", "pictures_repeat"):
                _slab(p, QRectF(x, r.bottom() - 2 * h - 7, w, h), picture_cols[n % 2], 2)
            if not again or rule in ("repeat", "sounds_repeat"):
                _slab(p, QRectF(x, r.bottom() - h - 4, w, h), c["audio"], 2)
    return draw


def _order_art(order):
    def draw(p, r, c, on):
        cols = [c["video"], c["audio"], QColor(c["video"]).lighter(130)]
        picks = [0, 1, 2, 0] if order == "turns" else [1, 0, 2, 1]
        w = r.width() * 0.17
        h = r.height() * 0.3
        for n, which in enumerate(picks):
            x = r.left() + r.width() * (0.12 + n * 0.21)
            _pin(p, x, r.top(), max(5.0, r.height() * 0.2), c["accent"])
            p.setPen(Qt.NoPen)
            _slab(p, QRectF(x, r.bottom() - h - 4, w, h), cols[which], 2)
    return draw


class ColourDots(_Scaled, QWidget):
    """Resolve's clip colours as dots - the first one is "no colour"."""
    changed = Signal(str)

    def __init__(self, settings, value):
        super().__init__()
        self.settings = settings
        self.value = value
        self.names = [""] + pm.CLIP_COLOURS
        self._hover = None
        self.setMouseTracking(True)
        self.setFixedSize(_px(len(self.names) * 21), _px(22))

    def _at(self, x):
        i = int(x // 21)
        return i if 0 <= i < len(self.names) else None

    def mouseMoveEvent(self, event):
        i = self._at(self._mouse(event).x())
        if i != self._hover:
            self._hover = i
            self.setToolTip(self.names[i] or "No colour" if i is not None else "")
            self.update()

    def leaveEvent(self, event):
        self._hover = None
        self.update()

    def mousePressEvent(self, event):
        i = self._at(self._mouse(event).x())
        if i is not None:
            self.value = self.names[i]
            self.update()
            self.changed.emit(self.value)

    def paintEvent(self, event):
        c = _colors(self.settings.theme)
        p = self._painter(self)
        p.setRenderHint(QPainter.Antialiasing)
        for i, name in enumerate(self.names):
            center = QPointF(i * 21 + 10.5, 11)
            if name == self.value:
                p.setPen(QPen(c["text"], 1.5))
                p.setBrush(Qt.NoBrush)
                p.drawEllipse(center, 9.5, 9.5)
            rad = 7.0 if self._hover == i else 6.2
            if name:
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(pm.COLOUR_HEX[name]))
                p.drawEllipse(center, rad, rad)
            else:  # no colour: an empty ring with a slash
                p.setPen(QPen(c["muted"], 1.2))
                p.setBrush(Qt.NoBrush)
                p.drawEllipse(center, rad, rad)
                p.drawLine(QPointF(center.x() - rad * 0.7, center.y() + rad * 0.7),
                           QPointF(center.x() + rad * 0.7, center.y() - rad * 0.7))
        p.end()


def _end_tile(kind, sound):
    """A way of ending, drawn: four clips each their own length, all ending on one line, or ending where a clip
    of the other kind under them does (pictures with the sounds, sounds with the pictures)."""
    def draw(p, r, c, on):
        colour = c["audio"] if sound else c["video"]
        follows = kind in ("audio", "pictures")  # (ending where the other kind does)
        rows = 4 if not follows else 3
        h = r.height() / ((rows + (1 if follows else 0)) * 1.5)
        line = r.left() + r.width() * 0.9
        p.setPen(Qt.NoPen)
        for i in range(rows):
            x = r.left() + r.width() * (0.05 + i * 0.15)
            y = r.top() + (rows - 1 - i) * h * 1.45 + h * 0.2
            end = x + r.width() * (0.46 if i % 2 == 0 else 0.3) if kind == "own" else line
            p.setBrush(_alpha(colour, 1.0 if on else 0.75))
            p.drawRoundedRect(QRectF(x, y, max(4.0, end - x), h), 2, 2)
        if follows:  # the clip of the other kind they end with
            p.setBrush(_alpha(c["audio"] if kind == "audio" else c["video"], 1.0 if on else 0.75))
            p.drawRoundedRect(QRectF(r.left() + r.width() * 0.2, r.top() + rows * h * 1.45 + h * 0.5,
                                     line - r.left() - r.width() * 0.2, h), 2, 2)
        if kind == "first":  # the first one, whole - the rest stop where it does (what's cut off, faint)
            for i in range(1, rows):
                x = r.left() + r.width() * (0.05 + i * 0.15)
                y = r.top() + (rows - 1 - i) * h * 1.45 + h * 0.2
                p.setBrush(_alpha(colour, 0.22))
                p.drawRoundedRect(QRectF(line, y, min(r.right() - line, r.width() * 0.09 * i), h), 2, 2)
        if kind != "own":
            p.setPen(QPen(c["text"] if on else c["muted"], 1.2, Qt.DashLine))
            p.drawLine(QPointF(line + 2, r.top()), QPointF(line + 2, r.bottom()))
    return draw
