"""Small notes on the screen while the picker is out of the way: a toast (Toast - "Tidy up needs the Fusion page")
and the notice that waits while you pick a node in Fusion (PickNotice). `place` puts our windows where they go
on Sway, where an app can't place its own."""
from PySide6.QtCore import Qt, QTimer, QRectF, QPropertyAnimation, QEasingCurve, Signal
from PySide6.QtCore import QPointF
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPen, QGuiApplication, QCursor
from PySide6.QtWidgets import QWidget
from .fonts import at as font_at  # (the one scale of sizes)

def sway_focused():
    """On Sway, the window that has the keyboard now (its con id), or None - to hand it back after a message
    (2026-10-30, the owner: such messages "remove the focus from the app so i have to click on some empty space")."""
    import json
    import os
    import shutil
    import subprocess
    if not (os.environ.get("SWAYSOCK") and shutil.which("swaymsg")):
        return None
    try:
        tree = json.loads(subprocess.run(["swaymsg", "-t", "get_tree"], capture_output=True, encoding="utf-8",
                                         errors="replace", timeout=1).stdout)  # (titles have symbols: UTF-8 always)
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
    stack = [tree]
    while stack:
        node = stack.pop()
        if node.get("focused") and node.get("type") in ("con", "floating_con"):
            return node.get("id")
        stack += node.get("nodes", []) + node.get("floating_nodes", [])
    return None


def sway_refocus(con):
    """Gives the keyboard back to `con` (sway_focused's)."""
    import subprocess
    if con is None:
        return
    try:
        subprocess.Popen(["swaymsg", f"[con_id={int(con)}] focus"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        pass


def place(window, x, y):
    """Puts one of our small windows at x, y on the screen. On Sway an app can't place its own windows - a
    floating one lands in the middle of the screen - so Sway is asked to move it there (its own window
    command; only ever our window, found by its title). Out of full screen, floating and its own size too: once
    (2026-10-30) "Organising the project..." came up as a window over the whole screen."""
    import os
    import shutil
    import subprocess
    window.move(int(x), int(y))
    if os.environ.get("SWAYSOCK") and shutil.which("swaymsg"):
        title = window.windowTitle().replace('"', "")
        try:
            subprocess.Popen(["swaymsg", f'[title="^{title}$"] fullscreen disable, floating enable, '
                                         f'resize set {window.width()} {window.height()}, '
                                         f'move absolute position {int(x)} {int(y)}'],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            pass


class Toast(QWidget):
    """A few words on the screen while the picker is out of the way ("Tidy up needs the Fusion page"): a
    small rounded card low in the middle of the screen, over Resolve, that fades in and out by itself - about
    two seconds, a little longer for more words. Never takes the keyboard or a click. (It used to be demo
    mode's big key label: 17 pt, for seven seconds, and on Sway in the middle of the screen.)"""

    def __init__(self, settings):
        super().__init__(None, Qt.Window | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
                         | Qt.WindowDoesNotAcceptFocus | Qt.WindowTransparentForInput | Qt.NoDropShadowWindowHint)
        self.settings = settings
        self.text = ""
        self.lead = ""     # a quiet word before the text ("Copied")
        self.steps = []    # a second line: where to go, a soft chip each with > between ("DaVinci Resolve" ...)
        self.setWindowTitle("Clipse message")
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(lambda: self._fade_to(0.0, 260))
        self._anim = QPropertyAnimation(self, b"windowOpacity", self)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.finished.connect(self._faded)

    def _font(self):
        return font_at(1.0, self.font())

    CHIP_PAD, CHIP_GAP = 9.0, 22.0  # inside a step's chip; between two (the > sits in the middle)

    def _steps_width(self, fm):
        return sum(fm.horizontalAdvance(step) + 2 * self.CHIP_PAD for step in self.steps) \
            + self.CHIP_GAP * max(0, len(self.steps) - 1)

    def say(self, text, ms=None, lead="", steps=()):
        """text on one line - after a quiet `lead` word, and with `steps` (where to go, one after another) as
        a second line of soft chips: two lines read far more easily than one long one."""
        self.text = " ".join(str(text).split())
        self.lead, self.steps = lead, [str(step) for step in steps]
        fm = QFontMetricsF(self._font())
        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        area = screen.availableGeometry()
        line = fm.horizontalAdvance(self.text) + (fm.horizontalAdvance(lead + "  ") if lead else 0)
        width = int(min(area.width() * 0.6, 44 + 22 + max(line, self._steps_width(fm)) + 18))
        rows = 2 if self.steps else 1
        self.setFixedSize(width, int(fm.height() + 22 + (fm.height() + 20) * (rows - 1)))  # one size only: on Sway it floats
        self._anim.stop()
        if self.isVisible():  # (shown again from scratch: one left over - closed by Sway, or still up - showed nothing)
            self.hide()
        self.setWindowOpacity(0.0)
        before = sway_focused()  # (Sway gives a new window the keyboard, however it's flagged: handed back below)
        self.show()
        x, y = area.center().x() - width // 2, area.bottom() - self.height() - int(area.height() * 0.08)
        place(self, x, y)
        QTimer.singleShot(60, lambda: sway_refocus(before))
        QTimer.singleShot(180, lambda: sway_refocus(before))  # (and once more after it's placed)
        QTimer.singleShot(120, lambda: self.isVisible() and place(self, x, y))  # (on Sway once it's there: asked
        # before, a rule centring the app's windows came after and it sat in the middle of the screen)
        self.raise_()
        self.update()
        QTimer.singleShot(40, lambda: self._fade_to(1.0, 140))  # (once it's where it goes)
        self._timer.start(int(ms) if ms else int(max(1800, min(4500, 1300 + 38 * len(self.text)))))

    def clear(self):
        self._timer.stop()
        self._anim.stop()
        self.hide()

    def _fade_to(self, opacity, ms):
        self._anim.stop()
        self._anim.setDuration(ms)
        self._anim.setStartValue(self.windowOpacity())
        self._anim.setEndValue(opacity)
        self._anim.start()

    def _faded(self):
        if self.windowOpacity() <= 0.01:
            self.hide()

    def paintEvent(self, event):
        t = self.settings.theme
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        bg = QColor(t.get("picker_bar_bg", t["picker_bg"]))
        bg.setAlphaF(0.97)
        edge = QColor(t["picker_text"])
        edge.setAlphaF(0.14)
        p.setPen(edge)
        p.setBrush(bg)
        fm = QFontMetricsF(self._font())
        first_h = fm.height() + 22  # (the first line's height: the i sits beside it)
        p.drawRoundedRect(r, min(r.height(), first_h) / 2, min(r.height(), first_h) / 2)
        mark = QColor(t["picker_folder"])  # a small i in a ring
        cx, cy, rad = 25.0, (first_h if self.steps else self.height()) / 2 + (3 if self.steps else 0), 7.0
        p.setPen(QPen(mark, 1.3))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QPointF(cx, cy), rad, rad)
        p.drawLine(QPointF(cx, cy - 0.5), QPointF(cx, cy + 3.5))
        p.setPen(Qt.NoPen)
        p.setBrush(mark)
        p.drawEllipse(QPointF(cx, cy - 3.3), 0.95, 0.95)
        p.setFont(self._font())
        top = 3 if self.steps else 0
        line = QRectF(42, top, self.width() - 58, first_h if self.steps else self.height())
        x = line.left()
        if self.lead:
            p.setPen(QColor(t["picker_folder"]))
            p.drawText(QRectF(x, line.top(), line.width(), line.height()), Qt.AlignLeft | Qt.AlignVCenter, self.lead)
            x += fm.horizontalAdvance(self.lead + "  ")
        p.setPen(QColor(t["picker_text"]))
        p.drawText(QRectF(x, line.top(), line.right() - x, line.height()), Qt.AlignLeft | Qt.AlignVCenter,
                   fm.elidedText(self.text, Qt.ElideRight, line.right() - x))
        if self.steps:  # where to go: a soft chip each, a quiet > between
            chip_h = fm.height() + 8
            y = line.bottom() - 6
            x = 42.0
            surface = QColor(t["picker_text"])
            surface.setAlphaF(0.08)
            for n, step in enumerate(self.steps):
                w = fm.horizontalAdvance(step) + 2 * self.CHIP_PAD
                chip = QRectF(x, y, w, chip_h)
                p.setPen(Qt.NoPen)
                p.setBrush(surface)
                p.drawRoundedRect(chip, chip_h * 0.3, chip_h * 0.3)
                p.setPen(QColor(t["picker_text"]))
                p.drawText(chip, Qt.AlignCenter, step)
                x = chip.right()
                if n < len(self.steps) - 1:
                    p.setPen(QColor(t["picker_folder"]))
                    p.drawText(QRectF(x, y, self.CHIP_GAP, chip_h), Qt.AlignCenter, "\u203a")
                    x += self.CHIP_GAP
        p.end()


class PickNotice(QWidget):
    """Shown while the picker is out of the way and waiting for a click in
    Fusion: what it's waiting for, and how to call it off - Esc, or a click
    on this. It takes the keyboard when it appears so that Esc reaches it;
    once you've clicked into Resolve, a click on it (or opening the picker)
    is the way out. On a Mac it doesn't take the keyboard: there the first
    click into Resolve would only bring Resolve to the front."""
    cancelled = Signal()

    def __init__(self, settings):
        import sys
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.settings = settings
        self.takes_keys = sys.platform != "darwin"
        self.setAttribute(Qt.WA_MacAlwaysShowToolWindow)  # (else hidden on a Mac while Resolve is in front)
        self.text = ""
        self.setWindowTitle("Clipse - waiting for a click")
        self.setAttribute(Qt.WA_TranslucentBackground)
        if not self.takes_keys:
            self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setCursor(Qt.PointingHandCursor)

    def _fonts(self):
        text = font_at(1.0, self.font())
        small = QFont(text)
        small.setPointSizeF(text.pointSizeF() - 1.5)
        return text, small

    def wait_for(self, text):
        self.text = text
        text_font, small = self._fonts()
        way_out = "Cancel" if self.takes_keys else "Click here to cancel"
        width = 22 + QFontMetricsF(text_font).horizontalAdvance(text) + 26 + (34 if self.takes_keys else 0) \
            + QFontMetricsF(small).horizontalAdvance(way_out) + 22
        self.setFixedSize(int(width), 46)  # one size only: a tiling window manager (Sway) then lets it float
        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        area = screen.availableGeometry()
        self.show()
        place(self, area.center().x() - self.width() // 2, area.bottom() - self.height() - int(area.height() * 0.08))
        self.raise_()
        if self.takes_keys:
            self.activateWindow()
            self.setFocus()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.cancelled.emit()

    def mousePressEvent(self, event):
        self.cancelled.emit()

    def paintEvent(self, event):
        t = self.settings.theme
        text_font, small = self._fonts()
        text_c, muted = QColor(t["picker_text"]), QColor(t["picker_folder"])
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        bg = QColor(t.get("picker_bar_bg", t["picker_bg"]))
        p.setPen(QColor(t["picker_border"]))
        p.setBrush(bg)
        p.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 11, 11)
        p.setFont(text_font)
        p.setPen(text_c)
        x = 22.0
        p.drawText(QRectF(x, 0, self.width(), self.height()), Qt.AlignLeft | Qt.AlignVCenter, self.text)
        x += QFontMetricsF(text_font).horizontalAdvance(self.text) + 26
        p.setFont(small)
        if self.takes_keys:  # the key, drawn as everywhere (keycaps.py)
            from . import keycaps
            keycaps.draw(p, x, self.height() / 2, "Esc", "Cancel", small, t)
        else:
            p.setPen(muted)
            p.drawText(QRectF(x, 0, self.width(), self.height()), Qt.AlignLeft | Qt.AlignVCenter, "Click here to cancel")
        p.end()
