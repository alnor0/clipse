"""The app's slider: a short track with its number beside it, to drag or type (a drag_spinbox field).

Click or drag anywhere on the track: the knob follows the mouse and settles on the steps (Alt: anywhere), and
glides there when the track is clicked. A soft halo while it's under the hand. The arrow keys step;
double-click: back to how it ships (a small mark on the track shows where that is, once it's moved off it).
A dot marks each whole number when there are few of them (Strength 1x - 4x). Used for every setting that is a
range - Insert as's Strength, Settings' volume, sizes, spacing, corners."""
from PySide6.QtCore import QEasingCurve, QPointF, QRectF, Qt, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

from .drag_spinbox import DragDoubleSpinBox, DragSpinBox


def _alpha(color, a):
    c = QColor(color)
    c.setAlphaF(a)
    return c


class Slider(QWidget):
    changed = Signal(float)
    valueChanged = changed  # (like the number fields)

    SPIN_W = 74

    def __init__(self, settings, minimum, maximum, value, suffix="", step=1.0, default=None, decimals=None,
                 width=236, scale=1.0):
        super().__init__()
        self._s = float(scale)  # (a window's own zoom - Insert as: everything in it grows together)
        self._spin_w = round(self.SPIN_W * self._s)
        self.settings = settings
        self.minimum, self.maximum, self.step = float(minimum), float(maximum), float(step)
        self.decimals = (0 if float(step).is_integer() else 2) if decimals is None else decimals
        self.value = self._tidy(float(value))
        self.default_value = self.minimum if default is None else float(default)
        self._shown = self.value   # where the knob is drawn - it glides, the value doesn't
        self._held = False
        self._hover = False
        self.setFixedSize(round(width * self._s), round(30 * self._s))
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMouseTracking(True)
        self._glide = QVariantAnimation(self)
        self._glide.setDuration(140)
        self._glide.setEasingCurve(QEasingCurve.OutCubic)
        self._glide.valueChanged.connect(self._glided)
        if self.decimals:
            self.box = DragDoubleSpinBox(self)
            self.box.setDecimals(self.decimals)
        else:
            self.box = DragSpinBox(self)
        self.box.setRange(self.minimum, self.maximum) if self.decimals else self.box.setRange(int(minimum), int(maximum))
        self.box.setSingleStep(step if self.decimals else max(1, int(step)))
        if suffix:
            self.box.setSuffix(suffix)
        self.box.setValue(self.value if self.decimals else int(self.value))
        self.box.default_value = self.default_value
        self.box.setGeometry(self.width() - self._spin_w, 0, self._spin_w, self.height())
        self.box.valueChanged.connect(lambda v: self._set(float(v), snap=False, glide=True))

    def _tidy(self, value):
        return round(value, self.decimals) if self.decimals else float(round(value))

    def _glided(self, at):
        self._shown = float(at)
        self.update()

    def _track(self):
        s = self._s
        return QRectF(9 * s, self.height() / 2 - 2 * s, self.width() - self._spin_w - 22 * s, 4 * s)

    def _x(self, value):
        track = self._track()
        return track.left() + track.width() * (value - self.minimum) / max(1e-9, self.maximum - self.minimum)

    def _set(self, value, snap=True, glide=False):
        value = max(self.minimum, min(self.maximum, round(value / self.step) * self.step if snap else value))
        value = self._tidy(value)
        if glide:
            self._glide.stop()
            self._glide.setStartValue(self._shown)
            self._glide.setEndValue(float(value))
            self._glide.start()
        if value != self.value:
            self.value = value
            self.box.blockSignals(True)
            self.box.setValue(value if self.decimals else int(value))
            self.box.blockSignals(False)
            self.box._after_change()
            self.update()
            self.changed.emit(value)

    def _at(self, event, glide):
        track = self._track()
        part = max(0.0, min(1.0, (event.position().x() - track.left()) / track.width()))
        raw = self.minimum + part * (self.maximum - self.minimum)
        free = bool(event.modifiers() & Qt.AltModifier)
        if not glide:  # dragged: the knob is under the mouse, the value on its step
            self._glide.stop()
            snapped = raw if free else round(raw / self.step) * self.step
            # a step pulls the knob in when it's close - it settles there rather than sliding past
            self._shown = snapped if abs(raw - snapped) < self.step * 0.18 else raw
            self.update()
        self._set(raw, snap=not free, glide=glide)

    def _on_track(self, x):
        return x < self._track().right() + 10 * self._s

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self._on_track(event.position().x()):
            self.setFocus()
            self._held = True
            self._at(event, glide=True)

    def mouseMoveEvent(self, event):
        over = self._on_track(event.position().x())
        if over != self._hover:
            self._hover = over
            self.update()
        if self._held and event.buttons() & Qt.LeftButton:
            self._at(event, glide=False)

    def mouseReleaseEvent(self, event):
        if self._held:
            self._held = False
            self._set(self.value, snap=False, glide=True)  # (the knob settles on the value)
            self.update()

    def leaveEvent(self, event):
        self._hover = False
        self.update()

    def mouseDoubleClickEvent(self, event):
        self.setValue(self.default_value)

    def setValue(self, value):
        self._set(float(value), snap=False, glide=True)

    def scrub_from(self, widget):  # (its name drags the number beside it)
        self.box.scrub_from(widget)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Right, Qt.Key_Up):
            self._set(self.value + self.step, glide=True)
        elif event.key() in (Qt.Key_Left, Qt.Key_Down):
            self._set(self.value - self.step, glide=True)
        else:
            super().keyPressEvent(event)

    def paintEvent(self, event):
        t = self.settings.theme
        accent = QColor(t.get("picker_accent", t["picker_text"]))
        muted = QColor(t["picker_folder"])
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        track = self._track()
        p.setPen(Qt.NoPen)
        p.setBrush(_alpha(muted, 0.3))
        s = self._s
        p.drawRoundedRect(track, 2 * s, 2 * s)
        knob = self._x(self._shown)
        p.setBrush(accent)
        p.drawRoundedRect(QRectF(track.left(), track.top(), knob - track.left(), track.height()), 2 * s, 2 * s)
        if self.maximum - self.minimum <= 8:  # a dot on each whole number, when there are few
            for step in range(int(self.minimum), int(self.maximum) + 1):
                p.setBrush(accent if step <= self._shown + 1e-6 else _alpha(muted, 0.55))
                p.drawEllipse(QPointF(self._x(step), track.center().y()), 2.2 * s, 2.2 * s)
        if abs(self.value - self.default_value) > 1e-9:  # where it ships (a double-click goes back there)
            home = self._x(self.default_value)
            p.setBrush(_alpha(muted, 0.9))
            p.drawRoundedRect(QRectF(home - 0.75 * s, track.top() - 3.5 * s, 1.5 * s, track.height() + 7 * s), 0.75 * s, 0.75 * s)
        if self._held or self._hover:  # a soft halo while it's under the hand
            p.setBrush(_alpha(accent, 0.18 if self._held else 0.1))
            p.drawEllipse(QPointF(knob, track.center().y()), 12 * s, 12 * s)
        p.setBrush(QColor(t.get("picker_bar_bg", t["picker_bg"])))
        p.setPen(QPen(accent, (2 if self.hasFocus() or self._held else 1.6) * s))
        size = (7.5 if self._held else 7) * s
        p.drawEllipse(QPointF(knob, track.center().y()), size, size)
        p.end()
