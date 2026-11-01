"""Where the preview opens, as a drawing to choose from (Settings > Preview - 2026-10-16: "an interactive
illustration where I can add gaps next to or in the same space").

Three tiles - Next to it (the window grows by the preview), In its space (the window stays, the list makes room), A
window of its own - and under them the picker drawn as it will be, the preview opening and closing in it to show
what that place does to the window. The gap between the two is a slider and can be dragged in the drawing; at 0 they
are one card with a line between. Changes go to listen["preview_place"] / listen["preview_gap"] at once.
"""
from PySide6.QtCore import QEasingCurve, QPointF, QRectF, QSize, Qt, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QFontMetricsF, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from . import look
from .fonts import SMALL, at as font_at, rel, window_zoom, zoom

PLACES = [("side", "Next to it", "The window grows by the preview, the list keeps its width"),
          ("shared", "In its space", "The window stays, the list makes room - and has it back when the preview closes"),
          ("window", "A window of its own", "Drag it anywhere - another screen, a corner")]
GAP_MAX = 32


def _alpha(colour, a):
    c = QColor(colour)
    c.setAlphaF(a)
    return c


def _card_path(r, radius, left=True, right=True):
    """A rounded rect with only the sides asked for rounded."""
    path = QPainterPath()
    if left and right:
        path.addRoundedRect(r, radius, radius)
        return path
    rl, rr = (radius if left else 0), (radius if right else 0)
    path.moveTo(r.left() + rl, r.top())
    path.lineTo(r.right() - rr, r.top())
    path.quadTo(r.right(), r.top(), r.right(), r.top() + rr)
    path.lineTo(r.right(), r.bottom() - rr)
    path.quadTo(r.right(), r.bottom(), r.right() - rr, r.bottom())
    path.lineTo(r.left() + rl, r.bottom())
    path.quadTo(r.left(), r.bottom(), r.left(), r.bottom() - rl)
    path.lineTo(r.left(), r.top() + rl)
    path.quadTo(r.left(), r.top(), r.left() + rl, r.top())
    path.closeSubpath()
    return path


class Drawer:
    """Draws the picker and the preview small, in a theme's colours - for these tiles, the big drawing and the
    theme tiles on Settings > Appearance (one look for the drawings of the picker)."""

    def __init__(self, settings, theme=None):
        t = theme or settings.theme
        self.bg = QColor(t["picker_bg"])
        self.edge = QColor(t["picker_border"])
        self.bar = QColor(t.get("picker_bar_bg") or t["picker_bg"])
        self.select = QColor(t["picker_select_bg"])
        self.text = QColor(t["picker_text"])
        self.sound = QColor(t.get("color_audio", "#3ee08f"))
        self.video = QColor(t.get("color_video", "#4f9dff"))

    def picker(self, p, r, radius, left=True, right=True, rows=7, detail=True):
        shape = _card_path(r, radius, left, right)
        p.fillPath(shape, self.bg)
        p.save()
        p.setClipPath(shape)
        search = max(6.0, r.height() * 0.12)
        bar = max(5.0, r.height() * 0.08)
        p.fillRect(QRectF(r.left(), r.bottom() - bar, r.width(), bar), self.bar)
        p.setPen(QPen(_alpha(self.edge, 0.6), 1))
        p.drawLine(QPointF(r.left(), r.top() + search), QPointF(r.right(), r.top() + search))
        if detail:
            room = r.height() - search - bar
            step = room / (rows + 0.6)
            for i in range(rows):
                y = r.top() + search + step * (0.4 + i)
                if i == 0:
                    p.setPen(Qt.NoPen)
                    p.setBrush(self.select)
                    p.drawRoundedRect(QRectF(r.left() + 3, y, r.width() - 6, step * 0.86), 3, 3)
                p.setPen(Qt.NoPen)
                kind = self.sound if i % 3 else self.video
                tag = QRectF(r.left() + step * 0.55, y + step * 0.26, step * 0.5, step * 0.34)
                p.setBrush(_alpha(kind, 0.75))
                p.drawRoundedRect(tag, 1.5, 1.5)
                name = QRectF(tag.right() + step * 0.35, y + step * 0.32, min(r.width() * 0.42, r.width() - tag.right() + r.left() - 10)
                              * (0.55 + 0.4 * ((i * 37) % 10) / 10), step * 0.22)
                p.setBrush(_alpha(self.text, 0.55 if i == 0 else 0.32))
                p.drawRoundedRect(name, name.height() / 2, name.height() / 2)
        p.restore()
        return shape

    def preview(self, p, r, radius, left=True, right=True, detail=True):
        shape = _card_path(r, radius, left, right)
        p.fillPath(shape, self.bg)
        p.save()
        p.setClipPath(shape)
        bar = max(5.0, r.height() * 0.08)
        p.fillRect(QRectF(r.left(), r.bottom() - bar, r.width(), bar), self.bar)
        pad = max(3.0, r.width() * 0.04)
        pic = QRectF(r.left() + pad, r.top() + pad, r.width() - 2 * pad, (r.width() - 2 * pad) * 0.62)
        p.setPen(Qt.NoPen)
        p.setBrush(self.bar.darker(130))
        p.drawRoundedRect(pic, 3, 3)
        if detail and pic.width() > 20:
            n = max(8, int(pic.width() / 4))
            bw = pic.width() / n
            for i in range(n):
                x = i / max(1, n - 1)
                h = pic.height() * 0.62 * (0.35 + 0.6 * abs(((i * 7919) % 13) / 13 - 0.3)) * min(1, (1 - x) * 8, x * 20 + 0.3)
                p.setBrush(self.sound if x < 0.12 else _alpha(self.text, 0.4))
                p.drawRect(QRectF(pic.left() + i * bw + bw * 0.25, pic.center().y() - h / 2, bw * 0.5, h))
            for k in range(3):
                y = pic.bottom() + pad * 1.4 + k * pad * 1.5
                p.setBrush(_alpha(self.text, 0.3))
                p.drawRoundedRect(QRectF(r.left() + pad, y, r.width() * (0.5 - k * 0.1), pad * 0.55), 1.5, 1.5)
        p.restore()
        return shape

    def pair(self, p, pick, prev, gap, radius, detail=True, open_share=1.0):
        """The picker and the preview beside it: two cards, or (no gap) one card with a line between."""
        if gap < 0.5 and open_share > 0.02:
            whole = pick.united(prev)
            self.picker(p, pick, radius, True, False, detail=detail)
            self.preview(p, prev, radius, False, True, detail=detail)
            p.setPen(QPen(self.edge, 1))
            p.drawLine(QPointF(prev.left() + 0.5, whole.top()), QPointF(prev.left() + 0.5, whole.bottom()))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(whole, radius, radius)
            return
        self.picker(p, pick, radius, detail=detail)
        p.setPen(QPen(self.edge, 1))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(pick, radius, radius)
        if open_share > 0.02:
            p.setOpacity(min(1.0, open_share * 1.4))
            self.preview(p, prev, radius, detail=detail)
            p.setPen(QPen(self.edge, 1))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(prev, radius, radius)
            p.setOpacity(1.0)


class PlaceTiles(QWidget):
    """The three places, each a tile with its own small drawing."""
    picked = Signal(str)

    def __init__(self, settings, current):
        super().__init__()
        self.settings = settings
        self.current = current
        self._hover = None
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        k = zoom(settings) * window_zoom(settings, "settings")
        self.font_ = font_at(SMALL * rel(settings, "settings"))
        fm = QFontMetricsF(self.font_)
        longest = max(fm.horizontalAdvance(label) for _k, label, _t in PLACES)
        self.tile_w = round(max(172 * k, longest + 24))
        self.tile_h = round(110 * k)
        self.gap = round(8 * k)
        self.setFixedHeight(self.tile_h + 2)
        self.setMinimumWidth(3 * self.tile_w + 2 * self.gap + 2)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def sizeHint(self):
        return QSize(3 * self.tile_w + 2 * self.gap + 2, self.tile_h + 2)

    def _rect(self, i):
        return QRectF(1 + i * (self.tile_w + self.gap), 1, self.tile_w - 2, self.tile_h - 2)

    def _hit(self, pos):
        return next((i for i in range(len(PLACES)) if self._rect(i).contains(pos)), None)

    def mouseMoveEvent(self, event):
        hit = self._hit(event.position())
        if hit != self._hover:
            self._hover = hit
            self.setCursor(Qt.PointingHandCursor if hit is not None else Qt.ArrowCursor)
            self.setToolTip(PLACES[hit][2] if hit is not None else "")
            self.update()

    def leaveEvent(self, event):
        self._hover = None
        self.update()

    def mousePressEvent(self, event):
        hit = self._hit(event.position())
        if hit is not None and event.button() == Qt.LeftButton:
            self._pick(hit)

    def keyPressEvent(self, event):
        i = [k for k, _l, _t in PLACES].index(self.current)
        if event.key() in (Qt.Key_Right, Qt.Key_Left):
            self._pick((i + (1 if event.key() == Qt.Key_Right else -1)) % len(PLACES))
            return
        super().keyPressEvent(event)

    def _pick(self, i):
        key = PLACES[i][0]
        if key != self.current:
            self.current = key
            self.update()
            self.picked.emit(key)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        d = Drawer(self.settings)
        fm = QFontMetricsF(self.font_)
        p.setFont(self.font_)
        for i, (key, label, _tip) in enumerate(PLACES):
            r = self._rect(i)
            chosen = key == self.current
            look.paint_tile(p, r, self.settings, chosen=chosen, hover=i == self._hover, focus=chosen and self.hasFocus())
            art = QRectF(r.left() + 12, r.top() + 10, r.width() - 24, r.height() - fm.height() - 24)
            h = art.height()
            pw, vw = h * 1.05, h * 0.62
            if key == "side":  # the picker as wide as ever, the preview past its edge
                x = art.center().x() - (pw + 3 + vw) / 2
                d.pair(p, QRectF(x, art.top(), pw, h), QRectF(x + pw + 3, art.top(), vw, h), 3, 4, detail=False)
            elif key == "shared":  # the window the picker's width, the preview inside it
                x = art.center().x() - pw * 1.25 / 2
                frame = QRectF(x - 3, art.top() - 3, pw * 1.25 + 6, h + 6)
                p.setPen(QPen(_alpha(d.text, 0.35), 1, Qt.DashLine))
                p.setBrush(Qt.NoBrush)
                p.drawRoundedRect(frame, 6, 6)
                inner = pw * 1.25
                d.pair(p, QRectF(x, art.top(), inner - vw - 3, h), QRectF(x + inner - vw, art.top(), vw, h), 3, 4, detail=False)
            else:  # its own window, somewhere else
                x = art.center().x() - (pw + vw * 0.9) / 2
                d.picker(p, QRectF(x, art.top() + h * 0.18, pw, h * 0.82), 4, detail=False)
                p.setPen(QPen(d.edge, 1))
                p.setBrush(Qt.NoBrush)
                p.drawRoundedRect(QRectF(x, art.top() + h * 0.18, pw, h * 0.82), 4, 4)
                pv = QRectF(x + pw - vw * 0.15, art.top(), vw * 1.05, h * 0.62)
                d.preview(p, pv, 4, detail=False)
                p.drawRoundedRect(pv, 4, 4)
            p.setPen(QColor(self.settings.theme["picker_text"]) if chosen else _alpha(d.text, 0.75))
            p.drawText(QRectF(r.left() + 4, r.bottom() - fm.height() - 10, r.width() - 8, fm.height() + 4),
                       Qt.AlignCenter, label)
        p.end()


class PlaceScene(QWidget):
    """The picker and the preview drawn big: opening and closing (a click), the gap dragged to its size."""
    gap_dragged = Signal(int)

    PICKER, PREVIEW, HEIGHT = 660, 360, 480  # (shorter than the app's 770 x 480: at full length it read as a long
                                             # bar; 580 was a little too short - 2026-10-16)

    def __init__(self, settings, place, gap):
        super().__init__()
        self.settings = settings
        self.place, self.gap = place, gap
        self._share = 1.0  # how open the preview is (0 closed, 1 open)
        self._drag = None
        k = zoom(settings) * window_zoom(settings, "settings")
        self.setFixedHeight(round(176 * k))
        self.setFixedWidth(self.sizeHint().width())
        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("Click: the preview opens or closes")
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(240)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.valueChanged.connect(self._step)

    def _step(self, value):
        self._share = float(value)
        self.update()

    def show_place(self, place, gap):
        """Shown again: the preview closes and opens, so what the place does is seen."""
        changed = place != self.place
        self.place, self.gap = place, gap
        if changed:
            self._play(0.0, 1.0)
        self.update()

    def _play(self, start, end):
        self._anim.stop()
        self._anim.setStartValue(float(start))
        self._anim.setEndValue(float(end))
        self._anim.start()

    def _scale(self):
        return (self.height() - 4) / self.HEIGHT

    def sizeHint(self):
        return QSize(round((self.PICKER + GAP_MAX + self.PREVIEW) * self._scale()) + 6, self.height())

    def _layout(self):
        """(scale, picker rect, preview rect, the window's rect) at how open the preview is now."""
        s = self._scale()
        h = self.HEIGHT * s
        top = 2.0
        gap = self.gap * s * self._share
        prev_w = self.PREVIEW * s * self._share
        left = 6.0  # (room for the dashed edge of In its space)
        if self.place == "shared":
            pick_w = self.PICKER * s - gap - prev_w
            whole = QRectF(left, top, self.PICKER * s, h)
        else:
            pick_w = self.PICKER * s
            whole = QRectF(left, top, pick_w + gap + prev_w, h)
        pick = QRectF(left, top, pick_w, h)
        prev = QRectF(pick.right() + gap, top, max(0.0, prev_w), h)
        return s, pick, prev, whole

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        t = self.settings.theme
        d = Drawer(self.settings)
        s, pick, prev, whole = self._layout()
        radius = max(3.0, 12 * s * 1.6)
        if self.place == "window":  # its own window: the picker alone, the preview off by itself
            d.picker(p, pick, radius)
            p.setPen(QPen(d.edge, 1))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(pick, radius, radius)
            if self._share > 0.02:
                p.setOpacity(self._share)
                pw = self.PREVIEW * s * 0.85
                far = QRectF(pick.right() + GAP_MAX * s + 6, pick.top(), pw, pick.height() * 0.62)
                d.preview(p, far, radius)
                p.setPen(QPen(d.edge, 1))
                p.drawRoundedRect(far, radius, radius)
                p.setOpacity(1.0)
        else:
            d.pair(p, pick, prev, self.gap * s * self._share, radius, open_share=self._share)
            if self.place == "shared":  # where the window ends - it doesn't move
                p.setPen(QPen(_alpha(QColor(t["picker_text"]), 0.25), 1, Qt.DashLine))
                p.setBrush(Qt.NoBrush)
                p.drawRoundedRect(whole.adjusted(-3, -1.5, 3, 1.5), radius + 2, radius + 2)
        p.end()

    # -- clicks and the gap dragged --
    def _on_gap(self, pos):
        if self.place == "window" or self._share < 0.99:
            return False
        _s, pick, prev, _whole = self._layout()
        return pick.right() - 5 <= pos.x() <= prev.left() + 5 and pick.top() <= pos.y() <= pick.bottom()

    def mouseMoveEvent(self, event):
        pos = event.position()
        if self._drag is not None and event.buttons() & Qt.LeftButton:
            x0, gap0, s = self._drag
            gap = max(0, min(GAP_MAX, round(gap0 + (pos.x() - x0) / s)))
            if gap != self.gap:
                self.gap = gap
                self.update()
                self.gap_dragged.emit(gap)
            return
        self.setCursor(Qt.SizeHorCursor if self._on_gap(pos) else Qt.PointingHandCursor)
        self.setToolTip("Drag: the gap" if self._on_gap(pos) else "Click: the preview opens or closes")

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        if self._on_gap(event.position()):
            self._drag = (event.position().x(), self.gap, self._layout()[0])
            return
        self._play(self._share, 0.0 if self._share > 0.5 else 1.0)

    def mouseReleaseEvent(self, event):
        self._drag = None


class PreviewPlace(QWidget):
    """Settings > Preview: where the preview opens - the tiles, the drawing, the gap."""
    changed = Signal(str, int)  # (place, gap)

    def __init__(self, settings):
        super().__init__()
        self.settings = settings
        place = settings.listen.get("preview_place", "side")
        place = place if place in ("side", "shared", "window") else "side"
        gap = int(settings.listen.get("preview_gap", 0))
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(10)
        title = QLabel("Preview window")
        title.setObjectName("SettingTitle")
        v.addWidget(title)
        self.tiles = PlaceTiles(settings, place)
        self.tiles.picked.connect(self._picked)
        v.addWidget(self.tiles)
        self.scene = PlaceScene(settings, place, gap)
        self.scene.gap_dragged.connect(self._gap_moved)
        v.addWidget(self.scene, 0, Qt.AlignLeft)
        from .slider import Slider
        row = QHBoxLayout()
        row.setSpacing(12)
        self.gap_label = QLabel("Gap")
        self.gap_label.setObjectName("SettingTitle")
        self.slider = Slider(settings, 0, GAP_MAX, gap, suffix=" px", default=0)
        self.slider.changed.connect(lambda value: self._gap_moved(int(value), from_slider=True))
        self.slider.scrub_from(self.gap_label)  # (its name drags the number, as everywhere)
        row.addWidget(self.gap_label)
        row.addStretch(1)
        row.addWidget(self.slider)
        v.addLayout(row)
        self._show_gap(place)

    def _show_gap(self, place):
        self.gap_label.setVisible(place != "window")
        self.slider.setVisible(place != "window")

    def _picked(self, place):
        self._show_gap(place)
        self.scene.show_place(place, self.scene.gap)
        self.changed.emit(place, self.scene.gap)

    def _gap_moved(self, gap, from_slider=False):
        if not from_slider:  # (dragged in the drawing: the slider follows, quietly)
            self.slider.blockSignals(True)
            self.slider.setValue(gap)
            self.slider.blockSignals(False)
        self.scene.show_place(self.tiles.current, gap)
        self.changed.emit(self.tiles.current, gap)
