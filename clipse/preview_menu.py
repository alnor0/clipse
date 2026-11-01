"""The preview's options - the menu behind the three dots in its bar.

The look is Vicinae's action menu: rows with a line icon and a soft
rounded highlight that follows the mouse, switches for what's on or off,
a tick on the one chosen of a few, quiet titles over each group. What the
rows do is wired up in picker_window.py (PreviewPanel)."""
from PySide6.QtCore import Qt, Signal, QVariantAnimation, QEasingCurve, QRectF, QPointF, QSize
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget, QVBoxLayout

from .glyphs import draw_glyph
from .fonts import SMALL, at as font_at  # (the one scale of sizes)


class MenuRow(QWidget):
    """A row in the preview's options, after Vicinae's action menu: a line
    icon, a name and, on the right, what the row is - "switch" (on / off),
    "choice" (a tick on the one picked of a few) or "more" (opens
    something). A soft rounded highlight follows the mouse."""
    toggled = Signal(bool)   # a switch was flipped
    clicked = Signal()       # a choice was picked, or a "more" row opened

    def __init__(self, settings, text, glyph, kind="switch", checked=False):
        super().__init__()
        self.settings = settings
        self.text = text
        self.glyph = glyph
        self.kind = kind
        self.checked = checked
        self._hover = False
        self._pos = 1.0 if checked else 0.0  # where the switch's knob is (0 off .. 1 on)
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(130)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.valueChanged.connect(self._moved)
        self.setCursor(Qt.PointingHandCursor)

    def _moved(self, value):
        self._pos = float(value)
        self.update()

    def set_checked(self, checked):
        if checked == self.checked:
            return
        self.checked = checked
        self._anim.stop()
        if self.kind == "switch" and self.isVisible():
            self._anim.setStartValue(self._pos)
            self._anim.setEndValue(1.0 if checked else 0.0)
            self._anim.start()
        else:
            self._pos = 1.0 if checked else 0.0
        self.update()

    def _sizes(self):
        """(row height, icon side, side padding, switch width) - all from the font."""
        h = QFontMetrics(self.font()).height()
        return round(h * 2.0), round(h * 1.1), round(h * 0.95), round(h * 1.8)

    def sizeHint(self):
        row, icon, pad, switch = self._sizes()
        fm = QFontMetrics(self.font())
        return QSize(pad + icon + round(pad * 0.7) + fm.horizontalAdvance(self.text) + round(pad * 1.6) + switch + pad, row)

    def enterEvent(self, event):
        self._hover = True
        self.update()

    def leaveEvent(self, event):
        self._hover = False
        self.update()

    def hideEvent(self, event):
        self._hover = False  # the menu closed under the mouse: no highlight left behind
        super().hideEvent(event)

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            return super().mousePressEvent(event)
        if self.kind == "switch":
            self.set_checked(not self.checked)
            self.toggled.emit(self.checked)
        else:
            self.clicked.emit()

    def paintEvent(self, event):
        t = self.settings.theme
        text, muted = QColor(t["picker_text"]), QColor(t["picker_folder"])
        accent = QColor(t.get("picker_accent", t["picker_text"]))
        row, icon, pad, switch = self._sizes()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        if self._hover:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(t["picker_select_bg"]))
            inset = pad * 0.4
            p.drawRoundedRect(QRectF(inset, 1, self.width() - 2 * inset, self.height() - 2), row * 0.27, row * 0.27)
        cy = self.height() / 2
        draw_glyph(p, self.glyph, QPointF(pad + icon / 2, cy), icon, text if self._hover else muted)
        fm = QFontMetrics(self.font())
        p.setFont(self.font())
        p.setPen(text)
        p.drawText(QPointF(pad + icon + round(pad * 0.7), cy + (fm.ascent() - fm.descent()) / 2), self.text)
        right = self.width() - pad
        if self.kind == "switch":
            track_h = round(fm.height() * 1.05)
            track = QRectF(right - switch, cy - track_h / 2, switch, track_h)
            off = QColor(t["picker_border"]).lighter(125)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(int(off.red() + (accent.red() - off.red()) * self._pos),
                              int(off.green() + (accent.green() - off.green()) * self._pos),
                              int(off.blue() + (accent.blue() - off.blue()) * self._pos)))
            p.drawRoundedRect(track, track_h / 2, track_h / 2)
            d = track_h - 4
            p.setBrush(QColor("#ffffff"))
            p.drawEllipse(QRectF(track.left() + 2 + (switch - d - 4) * self._pos, track.top() + 2, d, d))
        elif self.kind == "choice" and self.checked:
            u = fm.height() * 0.5
            tick = QPainterPath()
            tick.moveTo(right - u * 1.7, cy)
            tick.lineTo(right - u * 1.05, cy + u * 0.6)
            tick.lineTo(right, cy - u * 0.65)
            p.setPen(QPen(accent, max(1.6, u * 0.24), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            p.setBrush(Qt.NoBrush)
            p.drawPath(tick)
        elif self.kind == "more":
            u = fm.height() * 0.3
            arrow = QPainterPath()
            arrow.moveTo(right - u * 1.1, cy - u)
            arrow.lineTo(right - u * 0.1, cy)
            arrow.lineTo(right - u * 1.1, cy + u)
            p.setPen(QPen(muted, max(1.3, u * 0.32), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            p.setBrush(Qt.NoBrush)
            p.drawPath(arrow)
        p.end()


class MenuTitle(QWidget):
    """A small quiet title over a group of rows in the preview's options."""

    def __init__(self, settings, text):
        super().__init__()
        self.settings = settings
        self.text = text

    def _font(self):
        f = font_at(SMALL, self.font(), QFont.DemiBold)
        return f

    def sizeHint(self):
        fm = QFontMetrics(self._font())
        h = QFontMetrics(self.font()).height()
        return QSize(round(h * 1.9) + fm.horizontalAdvance(self.text), round(h * 1.75))

    def paintEvent(self, event):
        p = QPainter(self)
        p.setFont(self._font())
        p.setPen(QColor(self.settings.theme["picker_folder"]))
        pad = round(QFontMetrics(self.font()).height() * 0.95)
        p.drawText(QRectF(pad, 0, self.width() - 2 * pad, self.height() - 1), Qt.AlignLeft | Qt.AlignVCenter, self.text)
        p.end()


class MenuRule(QWidget):
    """A hairline between the groups in the preview's options."""

    def __init__(self, settings):
        super().__init__()
        self.settings = settings
        self.setFixedHeight(9)

    def paintEvent(self, event):
        line = QColor(self.settings.theme["picker_border"])
        p = QPainter(self)
        p.fillRect(QRectF(12, 4, self.width() - 24, 1), line)
        p.end()


class BarMenu(QWidget):
    """The preview's options, opened from the three dots in its bar: what
    Space does (one of a few), then the on/off switches one under the
    other, so the bar itself stays calm. The look is Vicinae's action menu."""

    def __init__(self, settings):
        super().__init__(None, Qt.Popup | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.settings = settings
        self.box = QVBoxLayout(self)
        self.box.setContentsMargins(0, 6, 0, 6)
        self.box.setSpacing(0)

    def paintEvent(self, event):
        t = self.settings.theme
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(QColor(t["picker_border"]), 1))
        p.setBrush(QColor(t["picker_bg"]))
        p.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 12, 12)
        p.end()
