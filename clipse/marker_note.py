"""The marker window (Add Marker, Stretch Marker to Clips - markers.py): a small card over Resolve in the picker's own
look (2026-10-30, the owner: "that text window is pretty bad") - a large line for what the marker is for, like the
picker's search, the kinds as tiles with drawn symbols in their marker colours, and the picker's foot: where the
marker is, Tab for the kind. Enter places it, words or not; Esc places nothing (the same day: "i dont have to put in
text to place the marker, but i have to click enter. If i click escape then the marker gets removed"). Tab or Up / Down
change the kind (Left / Right are the words')."""
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPainterPath
from PySide6.QtWidgets import QHBoxLayout, QLineEdit, QVBoxLayout, QWidget

from . import keycaps, look
from .fonts import SMALL, TITLE, at as font_at
from .glyphs import draw_glyph
from .markers import KINDS
from .presets import MARKER_HEX

SYMBOLS = {"B-roll": "preview", "Explain": "idea", "Note": "pin"}  # (drawn symbols, glyphs.py)


def _h(widget):
    return QFontMetricsF(widget.font()).height()


class KindTiles(QWidget):
    """The kinds side by side: each its symbol in its marker's colour and its name; the chosen one lit."""
    picked = Signal(int)

    def __init__(self, settings):
        super().__init__()
        self.settings = settings
        self.chosen = 0
        self._hover = None
        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)

    def fit(self):
        self.setFixedHeight(round(_h(self) * 2.9))

    def _rects(self):
        gap = round(_h(self) * 0.45)
        w = (self.width() - gap * (len(KINDS) - 1)) / len(KINDS)
        return [QRectF(i * (w + gap) + 0.5, 0.5, w - 1, self.height() - 1) for i in range(len(KINDS))]

    def choose(self, i):
        self.chosen = i % len(KINDS)
        self.update()
        self.picked.emit(self.chosen)

    def _at(self, pos):
        return next((i for i, r in enumerate(self._rects()) if r.contains(pos)), None)

    def mouseMoveEvent(self, event):
        hit = self._at(event.position())
        if hit != self._hover:
            self._hover = hit
            self.update()

    def leaveEvent(self, _event):
        self._hover = None
        self.update()

    def mousePressEvent(self, event):
        hit = self._at(event.position())
        if hit is not None:
            self.choose(hit)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        h = _h(self)
        fm = QFontMetricsF(self.font())
        for i, (rect, (name, colour)) in enumerate(zip(self._rects(), KINDS)):
            look.paint_tile(p, rect, self.settings, chosen=i == self.chosen, hover=i == self._hover)
            size = h * 1.35
            text_w = fm.horizontalAdvance(name)
            x = rect.center().x() - (size + h * 0.5 + text_w) / 2
            draw_glyph(p, SYMBOLS.get(name, "marker"), QPointF(x + size / 2, rect.center().y()), size,
                       QColor(MARKER_HEX.get(colour, "#888888")))
            p.setPen(QColor(self.settings.theme["picker_text"]))
            p.setFont(self.font())
            p.drawText(QRectF(x + size + h * 0.5, rect.top(), text_w + 4, rect.height()), Qt.AlignVCenter, name)


class MarkerNote(QWidget):
    done = Signal(str, str)  # kind, words
    cancelled = Signal()

    def __init__(self, settings):
        super().__init__(None, Qt.Window | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.settings = settings
        self.setWindowTitle("Clipse marker")
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.when = ""
        self._answered = False
        box = QVBoxLayout(self)
        self.top = QHBoxLayout()
        self.words = QLineEdit()
        self.words.setObjectName("PickerSearch")
        self.words.setPlaceholderText("What's this marker for?")
        self.words.installEventFilter(self)
        self.words.returnPressed.connect(lambda: self._answer(True))
        self.top.addWidget(self.words, 1)
        box.addLayout(self.top)
        self.tiles = KindTiles(settings)
        self.tiles.picked.connect(lambda _i: self.words.setFocus())
        box.addWidget(self.tiles, 0, Qt.AlignHCenter)
        self._sizes()

    def setFont(self, font):
        super().setFont(font)
        self.tiles.setFont(font)
        self._sizes()

    def _sizes(self):
        """Everything from the picker's text size: the words 1.2x it in a bar like the picker's search."""
        h = _h(self)
        self.words.setFont(font_at(TITLE, self.font()))
        self._symbol = round(h * 1.4)
        self._bar = round(h * 4.0)
        self._foot = round(h * 2.7)
        self._pad = round(h * 0.9)
        self.top.setContentsMargins(self._pad + self._symbol + round(h * 0.7), 0, self._pad, 0)
        self.words.setFixedHeight(self._bar)
        self.layout().setContentsMargins(0, 0, 0, self._foot + self._pad)
        self.layout().setSpacing(self._pad)
        self.tiles.fit()
        self.setFixedWidth(round(h * 34))
        self.tiles.setFixedWidth(self.width() - 2 * self._pad)

    def ask(self, when, kind, words):
        """Shows itself for the marker at `when` ("0:21.7 to 0:23.5"), its kind and words filled in."""
        self.when = when
        names = [name for name, _c in KINDS]
        self.tiles.chosen = names.index(kind) if kind in names else 0
        self.words.setText(words)
        self.words.selectAll()
        self._answered = False
        self.adjustSize()
        self.setFixedHeight(self.sizeHint().height())  # (one size: on Sway it floats)
        self.show()
        self.raise_()
        self.activateWindow()
        self.words.setFocus()
        self.update()

    def eventFilter(self, obj, event):
        if obj is self.words and event.type() == event.Type.KeyPress:
            key = event.key()
            if key in (Qt.Key_Tab, Qt.Key_Down):
                self.tiles.choose(self.tiles.chosen + 1)
                self.update()
                return True
            if key in (Qt.Key_Backtab, Qt.Key_Up):
                self.tiles.choose(self.tiles.chosen - 1)
                self.update()
                return True
            if key == Qt.Key_Escape:
                self._answer(False)
                return True
        return False

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self._answer(True)
        elif event.key() == Qt.Key_Escape:
            self._answer(False)
        else:
            super().keyPressEvent(event)

    def _answer(self, yes):
        if self._answered:
            return
        self._answered = True
        self.hide()
        if yes:
            self.done.emit(KINDS[self.tiles.chosen][0], self.words.text().strip())
        else:
            self.cancelled.emit()

    def closeEvent(self, event):
        self._answer(False)
        super().closeEvent(event)

    def paintEvent(self, _event):
        t = self.settings.theme
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = look.radius(self.settings, "card")
        card = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QColor(t["picker_border"]))
        p.setBrush(QColor(t["picker_bg"]))
        p.drawRoundedRect(card, r, r)
        line = QColor(t["picker_text"])
        line.setAlphaF(0.08)
        p.setPen(line)  # (the line under the words, as under the picker's search)
        p.drawLine(QPointF(card.left() + 1, self._bar + 0.5), QPointF(card.right() - 1, self._bar + 0.5))
        colour = QColor(MARKER_HEX.get(KINDS[self.tiles.chosen][1], t["picker_folder"]))
        draw_glyph(p, "marker", QPointF(self._pad + self._symbol / 2, self._bar / 2), self._symbol, colour)
        # the foot, the picker's bar: where the marker is, and the one key that isn't plain
        foot = QRectF(card.left(), card.bottom() - self._foot, card.width(), self._foot)
        path = QPainterPath()
        path.addRoundedRect(foot, r, r)
        path.addRect(QRectF(foot.left(), foot.top(), foot.width(), r))
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(t.get("picker_bar_bg", t["picker_bg"])))
        p.drawPath(path.simplified())
        p.setPen(line)
        p.drawLine(QPointF(foot.left() + 1, foot.top() + 0.5), QPointF(foot.right() - 1, foot.top() + 0.5))
        small = font_at(SMALL, self.font())
        p.setFont(small)
        p.setPen(QColor(t["picker_folder"]))
        words = f"Marker  {self.when}"
        p.drawText(QRectF(foot.left() + self._pad, foot.top(), foot.width() / 2, foot.height()), Qt.AlignVCenter, words)
        key_font = QFont(small)
        width = keycaps.width(key_font, "Tab", "Kind")
        keycaps.draw(p, foot.right() - self._pad - width, foot.center().y(), "Tab", "Kind", key_font, t)
