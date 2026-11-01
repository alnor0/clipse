"""Number fields you drag or type (like Blender's and Resolve's Inspector).

- Not typing (the left-right cursor): drag over the number - or over the
  setting's name (`scrub_from`) - to change it. Slow movements are fine,
  quick ones travel further. It moves in the field's own steps and catches
  for a moment on round numbers and on its default; hold Alt to drag freely
  and finer, Shift for bigger steps (`shift_snap`). While it's dragged its
  edge lights up, with a thin line along the bottom for where in its range
  it is.
- A plain click: the whole number is selected - type a new one. It's used
  when you press Enter (or click elsewhere), not half-typed. Esc puts the
  old number back. "." and "," both work as the decimal point.
- With a `default_value` set, a small reset arrow shows in its corner while
  it's anything else; a click on it puts the default back (`reset_action`
  when there's more to resetting than the number).
- The mouse wheel does nothing, so scrolling the page never changes a
  number by accident.
"""
import math

from PySide6.QtCore import QEvent, QObject, QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPalette, QPen
from PySide6.QtWidgets import QDoubleSpinBox, QSpinBox, QWidget

DRAG_START_THRESHOLD_PX = 4  # how far the mouse must move before a click becomes a drag
RESET_W = 18                 # the reset arrow's room at the right
ACCENT = None                # the theme's accent (theme.build_stylesheet sets it) - the lit edge while dragged


class _Overlay(QWidget):
    """Drawn over the field, never in the mouse's way: the lit edge and range line while it's dragged,
    the reset arrow while it's off its default."""

    def __init__(self, box):
        super().__init__(box)
        self.box = box
        self.setAttribute(Qt.WA_TransparentForMouseEvents)

    def paintEvent(self, event):
        box = self.box
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        text = box.palette().color(QPalette.Text)
        lit = QColor(ACCENT) if ACCENT else box.palette().color(QPalette.Highlight)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        if box._dragging:
            p.setPen(QPen(lit, 1.2))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(r, 5, 5)
            share = box._share()
            if share is not None:  # where in its range it is
                left, right = r.left() + 6, r.right() - 6
                y = r.bottom() - 2.5
                p.setPen(QPen(QColor(text.red(), text.green(), text.blue(), 45), 2, Qt.SolidLine, Qt.RoundCap))
                p.drawLine(QPointF(left, y), QPointF(right, y))
                p.setPen(QPen(lit, 2, Qt.SolidLine, Qt.RoundCap))
                p.drawLine(QPointF(left, y), QPointF(left + (right - left) * share, y))
        if box._off_default():
            c = box._reset_rect().center()
            hover = box._over_reset
            colour = QColor(text)
            colour.setAlpha(230 if hover else 120)
            p.setPen(QPen(colour, 1.3, Qt.SolidLine, Qt.RoundCap))
            p.setBrush(Qt.NoBrush)
            rad = 4.2
            p.drawArc(QRectF(c.x() - rad, c.y() - rad, 2 * rad, 2 * rad), 60 * 16, 270 * 16)  # a circle, open at the top
            tip = QPointF(c.x() + rad * math.cos(math.radians(60)), c.y() - rad * math.sin(math.radians(60)))
            head = QPainterPath()
            head.moveTo(tip.x() - 2.6, tip.y() - 2.2)
            head.lineTo(tip.x() + 0.4, tip.y() + 0.2)
            head.lineTo(tip.x() - 3.0, tip.y() + 1.6)
            p.drawPath(head)
        p.end()


class _DragMixin:
    """Shared by the whole-number and the decimal field. `drag_pixels_per_step`: how far the mouse goes
    for one step, slowly (quick movements go further)."""

    def _drag_init(self, drag_pixels_per_step, shift_snap):
        self._drag_from = None       # global x the mouse was last at, while the button is down
        self._dragging = False
        self._raw = 0.0              # the value as dragged, before it's caught on a step
        self._drag_pixels_per_step = drag_pixels_per_step
        self._shift_snap = shift_snap
        self._over_reset = False
        self.default_value = None    # set by whoever makes the field: then it has a reset arrow
        self.reset_action = None     # () -> None, when resetting is more than setting the number
        self.setCursor(Qt.SizeHorCursor)
        # The number itself is a text field inside the spin box that gets the
        # mouse first - drag over the number works too, not just the edges.
        self.lineEdit().setCursor(Qt.SizeHorCursor)
        self.lineEdit().setMouseTracking(True)
        self.lineEdit().installEventFilter(self)
        self.setKeyboardTracking(False)   # "45" isn't 4 and then 45
        self.setFocusPolicy(Qt.StrongFocus)  # not by the wheel
        self._typed_from = None
        # typing only after a plain click has let go: the press itself already gives the field the keyboard
        # (Qt does that before the press arrives), so "has the keyboard" can't tell a drag from typing
        self._editing = False
        self.lineEdit().textEdited.connect(self._decimal_point)
        self._overlay = _Overlay(self)
        self.valueChanged.connect(self._after_change)

    # -- what's shown --
    def _share(self):
        """0-1: where the value is in its range - None when the range is too wide to say (0-3600 s)."""
        low, high = float(self.minimum()), float(self.maximum())
        if high <= low or (high - low) / max(1e-9, float(self.singleStep())) > 2000:
            return None
        return (float(self.value()) - low) / (high - low)

    def _off_default(self):
        return self.default_value is not None and abs(float(self.value()) - float(self.default_value)) > 1e-9 \
            and self.isEnabled()

    def _reset_rect(self):
        return QRectF(self.width() - RESET_W - 3, 0, RESET_W, self.height())

    def _after_change(self, *_):
        self.lineEdit().setTextMargins(0, 0, RESET_W - 4 if self._off_default() else 0, 0)
        self._overlay.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._overlay.setGeometry(self.rect())
        self._overlay.raise_()

    def showEvent(self, event):
        super().showEvent(event)
        self._overlay.setGeometry(self.rect())
        self._overlay.raise_()
        self._after_change()

    def focusOutEvent(self, event):
        # Typing ends when the field loses the keyboard - a click on anything else, Tab, the window going.
        # (The spin box gets this, not the text inside it: watching only the text left a field that had been
        # typed into stuck in typing, and it never dragged again.)
        super().focusOutEvent(event)
        self._editing = False
        self._typed_from = None
        self.lineEdit().setCursor(Qt.SizeHorCursor)
        self.lineEdit().deselect()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.EnabledChange:
            self._after_change()

    def reset(self):
        """Back to its default (the arrow in its corner)."""
        if self.reset_action is not None:
            self.reset_action()
        elif self.default_value is not None:
            self.setValue(self.default_value)

    # -- typing --
    def _decimal_point(self, text):
        point = self.locale().decimalPoint()
        other = "." if point == "," else "," if point == "." else ""
        if other and other in text:
            edit = self.lineEdit()
            at = edit.cursorPosition()
            edit.setText(text.replace(other, point))
            edit.setCursorPosition(at)

    def wheelEvent(self, event):
        event.ignore()  # the page scrolls instead

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self.interpretText()
            self._typed_from = None
            self._editing = False
            self.clearFocus()
            event.accept()
            return
        if event.key() == Qt.Key_Escape and self._typed_from is not None:
            self.setValue(self._typed_from)
            self._typed_from = None
            self.clearFocus()
            event.accept()
            return
        super().keyPressEvent(event)

    # -- dragging --
    def _begin(self, global_x):
        self._drag_from = global_x
        self._drag_travel = 0.0
        self._raw = float(self.value())
        self._dragging = False

    def _move(self, global_x, modifiers):
        """The mouse moved to global_x with the button down. True once it's a drag."""
        if self._drag_from is None:
            return False
        dx = global_x - self._drag_from
        self._drag_travel += abs(dx)
        if not self._dragging and self._drag_travel < DRAG_START_THRESHOLD_PX:
            return False
        self._drag_from = global_x
        if not self._dragging:
            self._dragging = True
            if self._editing:  # it was being typed in: what's typed counts, then it's dragged from there
                self.interpretText()
                self._editing = False
            self._raw = float(self.value())
            self._overlay.update()
            return True
        step = float(self.singleStep())
        free = bool(modifiers & Qt.AltModifier)
        # quick movements travel further, slow ones stay fine; Alt: finer still
        speed = 1.0 + min(3.0, max(0.0, (abs(dx) - 3.0) / 5.0))
        self._raw += dx / self._drag_pixels_per_step * step * speed * (0.25 if free else 1.0)
        self._raw = max(float(self.minimum()), min(float(self.maximum()), self._raw))
        self._apply_dragged_value(self._caught(self._raw, modifiers))
        return True

    def _caught(self, raw, modifiers):
        """What the dragged value shows: on the field's steps (Shift: bigger ones), catching for a moment on
        round numbers and the default - or, Alt held, just as dragged."""
        if modifiers & Qt.AltModifier:
            return raw
        step = float(self.singleStep())
        if modifiers & Qt.ShiftModifier:
            big = self._shift_snap or step * 10
            return round(raw / big) * big
        for round_number in [self.default_value, 0.0, *self._round_numbers(raw, step)]:
            if round_number is not None and abs(raw - float(round_number)) <= step * 1.2:
                return float(round_number)
        return round(raw / step) * step

    @staticmethod
    def _round_numbers(raw, step):
        """The round numbers near raw: every tenth step, and every hundredth."""
        out = []
        for every in (step * 10, step * 100):
            out.append(round(raw / every) * every)
        return out

    def _end(self):
        was = self._dragging
        self._drag_from = None
        self._dragging = False
        if was:
            self._overlay.update()
        return was

    def eventFilter(self, obj, event):
        if obj is self.lineEdit():
            t = event.type()
            if t == QEvent.FocusIn:
                self._typed_from = self.value()
            elif t == QEvent.FocusOut:
                obj.setCursor(Qt.SizeHorCursor)  # not typing: drag left / right to change it
                self._typed_from = None
                self._editing = False
                obj.deselect()
            elif t == QEvent.MouseMove and not (event.buttons() & Qt.LeftButton):
                over = self._off_default() and self._reset_rect().contains(
                    QPointF(obj.mapTo(self, event.position().toPoint())))
                if over != self._over_reset:
                    self._over_reset = over
                    obj.setCursor(Qt.PointingHandCursor if over else
                                  (Qt.IBeamCursor if self._editing else Qt.SizeHorCursor))
                    self._overlay.update()
            elif t == QEvent.Leave and self._over_reset:
                self._over_reset = False
                self._overlay.update()
            if t == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
                if self._off_default() and self._reset_rect().contains(QPointF(obj.mapTo(self, event.position().toPoint()))):
                    self.reset()
                    return True
                # every press can become a drag - even mid-typing (what's typed is used first). Only a press
                # that doesn't move is a click into the text
                self._begin(event.globalPosition().x())
            elif t == QEvent.MouseMove and self._drag_from is not None and (event.buttons() & Qt.LeftButton):
                if self._move(event.globalPosition().x(), event.modifiers()):
                    self.lineEdit().deselect()
                    return True
            elif t == QEvent.MouseButtonRelease and event.button() == Qt.LeftButton:
                pressed = self._drag_from is not None
                if self._end():
                    self.lineEdit().deselect()
                    self.clearFocus()  # a drag isn't typing: stay ready for the next drag
                    return True
                if pressed and not self._editing:  # a plain click: the whole number, ready to be typed over
                    self._typed_from = self.value()
                    self._editing = True
                    obj.setCursor(Qt.IBeamCursor)
                    QTimer.singleShot(0, self.selectAll)
        return super().eventFilter(obj, event)

    def scrub_from(self, widget):
        """Dragging left/right over `widget` (the setting's name) changes the value too. (Its cursor stays the
        arrow: a name isn't where one expects a drag, and every name saying "drag" made it say so everywhere -
        2026-10-19. The field itself shows it.)"""
        widget.installEventFilter(_Scrubber(self, widget))

    # (Every press on the field is the field's: Qt's spin box lets one on its edge - around the text - through to
    #  what's behind it, and in the picker's place - Insert as - that's the window, which a press on an empty spot
    #  moves. Dragging a number there moved the picker too: "it starts glitching", 2026-10-19.)
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._begin(event.globalPosition().x())
            self.setFocus(Qt.MouseFocusReason)
            event.accept()  # (not the spin box's own: its arrows are hidden, yet a click near the edge stepped the
            return          #  number - 50 became 49, seen 2026-10-21)
        super().mousePressEvent(event)
        event.accept()

    def mouseMoveEvent(self, event):
        if self._drag_from is not None and (event.buttons() & Qt.LeftButton):
            if self._move(event.globalPosition().x(), event.modifiers()):
                event.accept()
                return
        super().mouseMoveEvent(event)
        event.accept()

    def mouseReleaseEvent(self, event):
        if self._end():
            event.accept()
            return
        if event.button() == Qt.LeftButton and not self._editing:
            # a plain click on the box around the number (above, below, beside it - a tall field is mostly that):
            # the whole number, ready to be typed over, as a click on the number itself (2026-10-21)
            self._typed_from = self.value()
            self._editing = True
            self.lineEdit().setCursor(Qt.IBeamCursor)
            QTimer.singleShot(0, self.selectAll)
        event.accept()


class DragSpinBox(_DragMixin, QSpinBox):
    def __init__(self, *args, drag_pixels_per_step=6, shift_snap=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._drag_init(drag_pixels_per_step, shift_snap)

    def _apply_dragged_value(self, value):
        self.setValue(max(self.minimum(), min(self.maximum(), int(round(value)))))


class DragDoubleSpinBox(_DragMixin, QDoubleSpinBox):
    def __init__(self, *args, drag_pixels_per_step=6, shift_snap=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._drag_init(drag_pixels_per_step, shift_snap)

    def _apply_dragged_value(self, value):
        self.setValue(max(self.minimum(), min(self.maximum(), value)))


class _Scrubber(QObject):
    """Drag over a label to change its field (like Resolve's Inspector) - the same drag as on the number."""

    def __init__(self, box, label):
        super().__init__(label)
        self.box = box

    def eventFilter(self, obj, event):
        t = event.type()
        if t == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
            self.box._begin(event.globalPosition().x())
            return True
        if t == QEvent.MouseMove and self.box._drag_from is not None and (event.buttons() & Qt.LeftButton):
            self.box._move(event.globalPosition().x(), event.modifiers())
            return True
        if t == QEvent.MouseButtonRelease and self.box._drag_from is not None:
            self.box._end()
            return True
        return False
