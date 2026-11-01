"""A thin scroll bar laid over a list (Vicinae's): 6 px, rounded, only there while the list scrolls or the mouse is on
it, then it fades out. The list itself keeps no scroll bar - so its rows keep their width - and this one can be
dragged like any other."""
from PySide6.QtCore import QEasingCurve, QEvent, QRectF, Qt, QTimer, QVariantAnimation
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QWidget

WIDTH = 6.0       # the bar
EDGE = 3.0        # from the list's right edge
STAYS_MS = 700    # after the last scroll, before it fades
FADE_MS = 200


class ScrollHint(QWidget):
    def __init__(self, view, settings):
        super().__init__(view)
        self.view, self.settings = view, settings
        self.bar = view.verticalScrollBar()
        self.setMouseTracking(True)
        self._shown = 0.0
        self._over = False
        self._drag = None  # (mouse y, scroll value) where a drag started
        self._fade = QVariantAnimation(self)
        self._fade.setDuration(FADE_MS)
        self._fade.setEasingCurve(QEasingCurve.OutCubic)
        self._fade.valueChanged.connect(self._faded)
        self._wait = QTimer(self)
        self._wait.setSingleShot(True)
        self._wait.timeout.connect(lambda: self._to(0.0))
        self.bar.valueChanged.connect(self.poke)
        self.bar.rangeChanged.connect(lambda *_: self.update())
        view.installEventFilter(self)
        self.hide()

    # -- where it is --
    def _place(self):
        r = self.view.rect()
        self.setGeometry(int(r.right() - EDGE - WIDTH - 4), 2, int(WIDTH + EDGE + 4), max(0, r.height() - 4))

    def _handle(self):
        """The handle's rect in this widget, or None when everything fits."""
        top, room = 2.0, self.height() - 4.0
        span = self.bar.maximum() - self.bar.minimum()
        if span <= 0 or room <= 0:
            return None
        length = max(24.0, room * self.bar.pageStep() / (span + self.bar.pageStep()))
        y = top + (room - length) * (self.bar.value() - self.bar.minimum()) / span
        return QRectF(self.width() - EDGE - WIDTH, y, WIDTH, length)

    # -- showing and fading --
    def poke(self, *_):
        """It scrolled: the bar shows, and fades a moment after the last scroll."""
        if self.bar.maximum() <= self.bar.minimum():
            return
        self._to(1.0)
        if not self._over and self._drag is None:
            self._wait.start(STAYS_MS)
        self.update()

    def _to(self, value):
        if value <= 0.0 and (self._over or self._drag is not None):
            return
        if value > 0.0 and not self.isVisible():
            self._place()
            self.show()
            self.raise_()
        if abs(self._fade.endValue() or 0.0) == value and self._fade.state() == QVariantAnimation.Running:
            return
        self._fade.stop()
        self._fade.setStartValue(self._shown)
        self._fade.setEndValue(value)
        self._fade.start()

    def _faded(self, value):
        self._shown = float(value)
        if self._shown <= 0.001:
            self.hide()
        self.update()

    def eventFilter(self, obj, event):
        if obj is self.view and event.type() == QEvent.Resize:
            self._place()
        return False

    # -- the mouse: drag the handle, or click above / below it to page --
    def enterEvent(self, event):
        self._over = True
        self._wait.stop()
        self._to(1.0)

    def leaveEvent(self, event):
        self._over = False
        if self._drag is None:
            self._wait.start(STAYS_MS)
        self.update()

    def mousePressEvent(self, event):
        handle = self._handle()
        if handle is None or event.button() != Qt.LeftButton:
            return
        y = event.position().y()
        if handle.top() <= y <= handle.bottom():
            self._drag = (y, self.bar.value())
        else:
            self.bar.setValue(self.bar.value() + (self.bar.pageStep() if y > handle.bottom() else -self.bar.pageStep()))

    def mouseMoveEvent(self, event):
        if self._drag is None:
            return
        handle = self._handle()
        if handle is None:
            return
        room = self.height() - 4.0 - handle.height()
        span = self.bar.maximum() - self.bar.minimum()
        if room > 0:
            self.bar.setValue(round(self._drag[1] + (event.position().y() - self._drag[0]) * span / room))

    def mouseReleaseEvent(self, event):
        self._drag = None
        if not self._over:
            self._wait.start(STAYS_MS)

    def paintEvent(self, event):
        handle = self._handle()
        if handle is None or self._shown <= 0.0:
            return
        t = self.settings.theme
        colour = QColor(t["picker_text"])
        colour.setAlphaF((0.42 if self._over or self._drag is not None else 0.24) * self._shown)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(colour)
        p.drawRoundedRect(handle, WIDTH / 2, WIDTH / 2)
        p.end()
