"""Tagging a sound while it plays (2026-11-01: "allow me to set the energy while i listen. And allow tagging as well"):
a strip under the picker's search, like Swap clip's, for the highlighted sound - it follows the list, so you can go
from one sound to the next and keep listening.

    [E1] [E2] [E3]   bed ✕   home ✕   te                                         ✕
    tension

The tags live in the file (file_tags.py); the second line is there only while typing: the tags on other sounds that
match, so a tag is spelled one way (2026-11-01: the whole list always there, "Dont i just need the top row"). The keys are the picker's
(Settings > Keybindings: Tags, Energy 1-3), and with nothing typed 1, 2, 3 set the energy too and 0 takes it away.
Space plays, the arrows go on through the list."""
import queue
import threading

from PySide6.QtCore import QObject, QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFontMetricsF, QPainter, QPen
from PySide6.QtWidgets import QLineEdit, QToolTip, QWidget

from . import file_tags as ft
from . import look
from .clip_model import ENERGY_BARS_WIDTH, draw_energy
from .fonts import SMALL, at as font_at, picker_scale

MAX_SUGGESTED = 40
_WRITE_THEN_WAIT = 1.5  # seconds with no more tags before they're kept and after_tagging runs


class TagKeeper(QObject):
    """Reads and writes on a thread of its own: a WAV is rewritten whole, and a slow disk mustn't hold up the picker."""
    found = Signal(object, object)   # (row, tags) - read from the file, and not what the row had
    read_done = Signal(bool)         # whether anything changed
    failed = Signal(object, str)     # (file, why)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._generation = 0
        self._writes = queue.Queue()
        self._writer = None

    def read(self, rows):
        """Each sound's tags from its file, only where it has changed since they were last seen."""
        self._generation += 1
        generation = self._generation

        def work():
            changed = False
            for row in rows:
                if generation != self._generation:
                    return
                tags = ft.fresh(row.file)
                if tags != row.file_tags:
                    changed = True
                    self.found.emit(row, tags)
            ft.save()
            self.read_done.emit(changed)
        threading.Thread(target=work, name="clipse-tags", daemon=True).start()

    def write(self, path, tags):
        self._writes.put((path, list(tags)))
        if self._writer is None:
            self._writer = threading.Thread(target=self._write_all, name="clipse-tag-writer", daemon=True)
            self._writer.start()

    def _write_all(self):
        changed = []
        while True:
            try:
                path, tags = self._writes.get(timeout=_WRITE_THEN_WAIT if changed else None)
            except queue.Empty:
                ft.save()
                ft.after_tagging(changed)
                changed = []
                continue
            try:
                ft.write(path, tags)
                if path not in changed:
                    changed.append(path)
            except (OSError, ValueError) as e:
                print(f"[tags] {path}: {e}")
                self.failed.emit(path, str(e))


class _TagField(QLineEdit):
    def __init__(self, strip):
        super().__init__(strip)
        self.strip = strip
        self.setFrame(False)
        self.setPlaceholderText("Add a tag")
        self.setStyleSheet("QLineEdit { background: transparent; border: none; padding: 0; }")

    def event(self, ev):
        if ev.type() == ev.Type.KeyPress and ev.key() in (Qt.Key_Tab, Qt.Key_Backtab):  # (Qt keeps Tab for itself)
            self.strip.add_first()
            return True
        return super().event(ev)

    def keyPressEvent(self, ev):
        key, plain, text = ev.key(), ev.modifiers() in (Qt.NoModifier, Qt.KeypadModifier), self.text()
        if key == Qt.Key_Escape:
            if text:
                self.clear()
            else:
                self.strip.closed.emit()
        elif key in (Qt.Key_Return, Qt.Key_Enter):
            if ev.isAutoRepeat():
                return
            if text.strip():
                self.strip.add(text)
            else:
                self.strip.closed.emit()
        elif key == Qt.Key_Backspace and not text and plain:
            self.strip.remove_last()
        elif not text and plain and Qt.Key_0 <= key <= Qt.Key_3:
            self.strip.energy_chosen.emit(key - Qt.Key_0)
        elif not text and plain and key == Qt.Key_Space:
            self.strip.play.emit()
        elif text and (key in (Qt.Key_Left, Qt.Key_Right, Qt.Key_Home, Qt.Key_End, Qt.Key_Delete, Qt.Key_Backspace)
                       or (ev.modifiers() & (Qt.ControlModifier | Qt.MetaModifier)
                           and key in (Qt.Key_A, Qt.Key_C, Qt.Key_V, Qt.Key_X, Qt.Key_Z))):
            super().keyPressEvent(ev)
        elif self.strip.picker_key(ev):
            return
        else:
            super().keyPressEvent(ev)

    def keyReleaseEvent(self, ev):
        self.strip.picker_key_up(ev)
        super().keyReleaseEvent(ev)


class TagStrip(QWidget):
    tags_changed = Signal(list)   # the highlighted sound's whole list of tags, new
    energy_chosen = Signal(int)   # 1-3, the same again or 0 for none
    play = Signal()
    closed = Signal()

    def __init__(self, settings, picker, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.picker = picker
        self.tags = []
        self.energy = 0
        self.known = []
        self.why_not = ""   # what stands in the way of tagging this row (a picture, an .m4a)
        self._spots = []    # (rect, kind, value)
        self._hover = None
        self.field = _TagField(self)
        self.field.textChanged.connect(self._retyped)
        self.setMouseTracking(True)
        self.hide()

    # -- what it shows --
    def show_for(self, tags, energy, known, why_not=""):
        self.tags, self.energy, self.known, self.why_not = list(tags), energy, list(known), why_not
        self.field.setEnabled(not why_not)
        self._lay_out()
        self.update()

    def _plain_tags(self):
        return [tag for tag in self.tags if not ft.ENERGY.fullmatch(tag)]

    def suggested(self):
        """Tags on other sounds that match what's typed, the ones starting with it first. Nothing typed, none."""
        typed = self.field.text().strip().lower()
        if not typed:
            return []
        have = {tag.lower() for tag in self.tags}
        out = [tag for tag in self.known
               if tag.lower() not in have and not ft.ENERGY.fullmatch(tag) and typed in tag.lower()]
        return sorted(out, key=lambda tag: not tag.lower().startswith(typed))[:MAX_SUGGESTED]

    # -- what's done --
    def _spelled(self, word):
        """A tag as it's already written on other sounds, whatever the case it was typed in."""
        return next((tag for tag in self.known if tag.lower() == word.lower()), word)

    def add(self, text):
        words = [self._spelled(word) for word in ft.split_tags(text) if not ft.ENERGY.fullmatch(word)]
        self.field.clear()
        have = {tag.lower() for tag in self.tags}
        new = [word for word in words if word.lower() not in have]
        if new:
            self.tags_changed.emit(self.tags + new)

    def add_first(self):
        first = self.suggested()[:1]
        if first:
            self.add(first[0])
        elif self.field.text().strip():
            self.add(self.field.text())

    def remove_last(self):
        plain = self._plain_tags()
        if plain:
            self.tags_changed.emit([tag for tag in self.tags if tag != plain[-1]])

    def picker_key(self, ev):
        return self.picker.handle_action_key(ev)

    def picker_key_up(self, ev):
        self.picker.handle_key_release(ev)

    def _retyped(self):
        self._lay_out()
        self.update()

    # -- where everything goes --
    def _font(self):
        return font_at(SMALL, self.font())

    def _scale(self):
        return picker_scale(self.settings)

    def _pad(self):
        return float(self.settings.display.get("outer_padding", 16)) * self._scale()

    def _line_height(self):
        return QFontMetricsF(self._font()).height() + 10 * self._scale()

    def _lay_out(self):
        fm = QFontMetricsF(self._font())
        scale, pad, line = self._scale(), self._pad(), self._line_height()
        gap, top = 6 * scale, 8 * scale
        right = self.width() - pad - 24 * scale  # (the ✕)
        spots = []
        x, y = pad, top
        energy_w = fm.horizontalAdvance("E1") + (9 + 7 + ENERGY_BARS_WIDTH + 9) * scale
        for level in (1, 2, 3):
            spots.append((QRectF(x, y, energy_w, line), "energy", level))
            x += energy_w + gap
        x += 8 * scale
        for tag in self._plain_tags():
            width = fm.horizontalAdvance(tag) + 34 * scale
            if x + width > right and x > pad:
                x, y = pad, y + line + gap
            spots.append((QRectF(x, y, min(width, right - x), line), "tag", tag))
            x += width + gap
        field_w = max(fm.horizontalAdvance("Add a tag") + 16 * scale, fm.horizontalAdvance(self.field.text()) + 20 * scale)
        if x + field_w > right and x > pad:
            x, y = pad, y + line + gap
        self.field.setFont(self._font())
        self.field.setGeometry(round(x + 4 * scale), round(y), round(min(field_w, right - x)), round(line))
        y += line
        x, wrote = pad, False
        for tag in self.suggested():
            width = fm.horizontalAdvance(tag) + 20 * scale
            if x + width > self.width() - pad:
                break
            if not wrote:
                y += gap
            spots.append((QRectF(x, y, width, line), "suggest", tag))
            x, wrote = x + width + gap, True
        if wrote:
            y += line
        self._spots = spots
        height = round(y + top)
        if height != self.height():
            self.setFixedHeight(height)
            self.updateGeometry()

    def sizeHint(self):
        return QSize(400, max(self.height(), round(self._line_height() + 16 * self._scale())))

    def resizeEvent(self, event):
        self._lay_out()
        super().resizeEvent(event)

    def _close_rect(self):
        scale, pad = self._scale(), self._pad()
        side = 18 * scale
        return QRectF(self.width() - pad - side, 8 * scale + (self._line_height() - side) / 2, side, side)

    def paintEvent(self, _event):
        t = self.settings.theme
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        font = self._font()
        p.setFont(font)
        scale, fm = self._scale(), QFontMetricsF(font)
        text, muted = QColor(t["picker_text"]), QColor(t["picker_folder"])
        line = QColor(t["picker_border"])
        line.setAlphaF(0.6)
        p.setPen(QPen(line, 1))
        p.drawLine(QPointF(0, self.height() - 0.5), QPointF(self.width(), self.height() - 0.5))
        p.setOpacity(0.4 if self.why_not else 1.0)
        first = next((value for _r, kind, value in self._spots if kind == "suggest"), None)
        typed = bool(self.field.text().strip())
        for rect, kind, value in self._spots:
            hover = self._hover == (kind, value) and not self.why_not
            if kind == "energy":
                look.paint_tile(p, rect, self.settings, chosen=self.energy == value, hover=hover)
                p.setPen(text if self.energy == value else muted)
                inner = rect.adjusted(9 * scale, 0, 0, 0)
                p.drawText(inner, Qt.AlignVCenter | Qt.AlignLeft, f"E{value}")
                draw_energy(p, rect.right() - (ENERGY_BARS_WIDTH + 9) * scale, rect.center().y(), scale, value,
                            self.energy == value, t)
            elif kind == "tag":
                look.paint_tile(p, rect, self.settings, hover=hover)
                p.setPen(text)
                words = fm.elidedText(value, Qt.ElideRight, rect.width() - 30 * scale)
                p.drawText(rect.adjusted(10 * scale, 0, 0, 0), Qt.AlignVCenter | Qt.AlignLeft, words)
                self._cross(p, QPointF(rect.right() - 11 * scale, rect.center().y()), 3 * scale,
                            text if hover else muted)
            else:
                look.paint_tile(p, rect, self.settings, hover=hover, chosen=typed and value == first)
                p.setPen(text if hover or (typed and value == first) else muted)
                p.drawText(rect, Qt.AlignCenter, value)
        p.setOpacity(1.0)
        if self.why_not:
            p.setPen(muted)
            p.drawText(QRectF(self.field.geometry()).adjusted(0, 0, 400, 0), Qt.AlignVCenter | Qt.AlignLeft, self.why_not)
        close = self._close_rect()
        self._cross(p, close.center(), 4 * scale, text if self._hover == ("close", None) else muted)
        p.end()

    @staticmethod
    def _cross(p, at, k, colour):
        p.setPen(QPen(colour, 1.4, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(at + QPointF(-k, -k), at + QPointF(k, k))
        p.drawLine(at + QPointF(-k, k), at + QPointF(k, -k))

    # -- the mouse --
    def _at(self, pos):
        if self._close_rect().contains(pos):
            return "close", None
        for rect, kind, value in self._spots:
            if rect.contains(pos):
                return kind, value
        return None

    def mouseMoveEvent(self, event):
        hit = self._at(event.position())
        if hit != self._hover:
            self._hover = hit
            self.setCursor(Qt.PointingHandCursor if hit else Qt.ArrowCursor)
            self.update()
            if hit and hit[0] == "energy":
                from .help_text import ENERGY_LEVELS
                QToolTip.showText(event.globalPosition().toPoint(), ENERGY_LEVELS[hit[1]], self)

    def leaveEvent(self, _event):
        self._hover = None
        self.update()

    def mousePressEvent(self, event):
        hit = self._at(event.position()) if event.button() == Qt.LeftButton else None
        if hit is None:
            return
        kind, value = hit
        if kind == "close":
            self.closed.emit()
            return
        if self.why_not:
            return
        if kind == "energy":
            self.energy_chosen.emit(value)
        elif kind == "suggest":
            self.add(value)
        elif kind == "tag":
            self.tags_changed.emit([tag for tag in self.tags if tag != value])
        self.field.setFocus()
