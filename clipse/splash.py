"""A small card that shows while Clipse starts - so the first
press of the shortcut answers at once, with what it's doing and how far
along it is, instead of 5-10 quiet seconds.

Shown only when you started it (the shortcut, the client); a start in
the background at login stays invisible. The picker takes over as soon
as it opens - its own bar then shows the Media Pool being read."""
from PySide6.QtCore import QEasingCurve, QRectF, Qt, QTimer, QVariantAnimation
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QGuiApplication, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QApplication, QWidget
from .fonts import TITLE, at as font_at  # (the one scale of sizes)

BG, CARD, LINE, TEXT, MUTED, ACCENT = "#1e2128", "#262a33", "#353a46", "#e6e8ee", "#8b93a5", "#61afef"


class Splash(QWidget):
    def __init__(self, theme=None):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        t = theme or {}
        self.colors = {"bg": t.get("picker_bg", BG), "card": t.get("picker_bar_bg", CARD),
                       "line": t.get("picker_border", LINE), "text": t.get("picker_text", TEXT),
                       "muted": t.get("picker_folder", MUTED), "accent": t.get("picker_accent", ACCENT)}
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_MacAlwaysShowToolWindow)  # (a Mac hides an app's tool windows while another app
        #  is in front - Resolve, always: the card never showed there, 2026-10-21)
        self.setWindowTitle("Clipse")
        self.text = "Starting"
        self._said = False
        self.shown = 0.0       # where the bar is drawn
        self.target = 0.0      # where it's heading
        self._spin = 0.0
        self.setFixedSize(360, 132)
        screen = QGuiApplication.primaryScreen()
        if screen is not None:
            geo = screen.availableGeometry()
            self.move(geo.center().x() - self.width() // 2, geo.top() + int(geo.height() * 0.3))
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(16)
        self._fade = None

    def step(self, text, fraction):
        """Moves on: `text` is what it's doing now, `fraction` (0-1) how far it is."""
        self.text = text
        self.target = max(self.target, min(1.0, fraction))
        if not self.isVisible():
            self.show()
        self.update()
        QApplication.processEvents()  # the next step may block for a moment - show this one first

    def say(self, text):
        """Says something that ends the start (not a step - no "…"), then fades out."""
        self.text = text
        self._said = True
        self.update()
        QTimer.singleShot(1800, self._fade_out)

    def _tick(self):
        self.shown += (self.target - self.shown) * 0.12
        self._spin = (self._spin + 0.012) % 1.0
        self.update()

    def finish(self):
        """Fills the bar and fades out."""
        if self._fade is not None:
            return
        self.target = 1.0
        self._fade_out()

    def _fade_out(self):
        if self._fade is not None:
            return
        self._fade = QVariantAnimation(self)
        self._fade.setDuration(260)
        self._fade.setStartValue(1.0)
        self._fade.setEndValue(0.0)
        self._fade.setEasingCurve(QEasingCurve.InCubic)
        self._fade.valueChanged.connect(lambda v: self.setWindowOpacity(float(v)))
        self._fade.finished.connect(self._done)
        QTimer.singleShot(120, self._fade.start)

    def _done(self):
        self._timer.stop()
        self.hide()
        self.deleteLater()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        card = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QPen(QColor(self.colors["line"]), 1))
        p.setBrush(QColor(self.colors["card"]))
        p.drawRoundedRect(card, 14, 14)
        # the mark (logo.py), on a tile
        mark = QRectF(22, 24, 44, 44)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(self.colors["bg"]))
        p.drawRoundedRect(mark, 11, 11)
        from . import logo
        logo.paint(p, mark.left(), mark.top(), mark.width(), 0.64)
        title = font_at(TITLE, self.font())
        title.setWeight(QFont.DemiBold)
        p.setFont(title)
        p.setPen(QColor(self.colors["text"]))
        fm = QFontMetricsF(title)
        p.drawText(QRectF(82, 26, self.width() - 100, fm.height()), Qt.AlignLeft | Qt.AlignVCenter, "Clipse")
        body = QFont(self.font())
        p.setFont(body)
        p.setPen(QColor(self.colors["muted"]))
        bfm = QFontMetricsF(body)
        p.drawText(QRectF(82, 28 + fm.height(), self.width() - 100, bfm.height()), Qt.AlignLeft | Qt.AlignVCenter,
                   bfm.elidedText(self.text + ("" if self._said else "…"), Qt.ElideRight, self.width() - 100))
        # the bar: how far along it is, with a soft light running over it so it never looks stuck
        bar = QRectF(22, self.height() - 34, self.width() - 44, 5)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(self.colors["line"]))
        p.drawRoundedRect(bar, 2.5, 2.5)
        filled = QRectF(bar.left(), bar.top(), max(bar.height(), bar.width() * self.shown), bar.height())
        p.setBrush(QColor(self.colors["accent"]))
        p.drawRoundedRect(filled, 2.5, 2.5)
        glow = QColor(255, 255, 255, 70)
        x = filled.left() + filled.width() * self._spin
        path = QPainterPath()
        path.addRoundedRect(filled, 2.5, 2.5)
        p.setClipPath(path)
        p.setBrush(glow)
        p.drawRect(QRectF(x - 18, bar.top(), 36, bar.height()))
        p.setClipping(False)
        p.end()
