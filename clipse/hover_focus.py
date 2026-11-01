"""Hover to focus: rest the mouse on the picker (or Settings, Insert
Options, History, the preview) and it takes the keyboard - no click
needed after you've clicked something in Resolve.

The mouse position is checked a few times a second while one of
Clipse's windows is open; when it has rested on one for a
quarter of a second (and no mouse button is held - you might be dragging
something in Resolve), that window is brought to the front with the
keyboard. It happens once per visit: move off and back on to do it again.
On Wayland the window manager decides about focus, so it does nothing there.

It only ever takes the keyboard from DaVinci Resolve: with another app in
front (a browser on another Space, say) resting the mouse where the picker
would be does nothing - otherwise macOS would pull you back to Resolve.
"""
import platform

from PySide6.QtCore import QObject, QTimer, Qt
from PySide6.QtGui import QCursor, QGuiApplication
from PySide6.QtWidgets import QApplication, QMenu

SYSTEM = platform.system()
SKIP_TITLES = ("Clipse keys",)  # demo-mode key labels never take focus
DWELL_TICKS = 2                          # 2 x 120 ms on the window before it takes the keyboard


def _buttons_down():
    """A mouse button is held - also while another app is in front."""
    try:
        if SYSTEM == "Darwin":
            from AppKit import NSEvent
            return bool(NSEvent.pressedMouseButtons())
        if SYSTEM == "Windows":
            import ctypes
            gks = ctypes.windll.user32.GetAsyncKeyState
            return bool(gks(0x01) & 0x8000 or gks(0x02) & 0x8000)
    except Exception:
        pass
    return QApplication.mouseButtons() != Qt.NoButton


def _cursor_after_switch(state):
    """A Mac: while another app is in front Qt hears no mouse moves, so a window kept the last pointer it had - a
    number field's drag pointer, the edge's resize one - and showed it on coming back until the mouse moved
    (2026-10-21: "my cursor changes symbol to a dragging symbol"). Another app in front: a plain arrow; back in
    front: the pointer of what's under the mouse, at once."""
    for w in QApplication.topLevelWidgets():
        handle = w.windowHandle() if w.isVisible() else None
        if handle is None:
            continue
        if state != Qt.ApplicationActive:
            handle.setCursor(Qt.ArrowCursor)
            continue
        under = QApplication.widgetAt(QCursor.pos())
        handle.setCursor(under.cursor() if under is not None and under.window() is w else Qt.ArrowCursor)


class HoverFocus(QObject):
    def __init__(self, settings, picker):
        super().__init__(picker)
        self.settings = settings
        self.picker = picker
        self._timer = QTimer(self)
        self._timer.setInterval(120)
        self._timer.timeout.connect(self._tick)
        self._over, self._ticks, self._done = None, 0, None
        if SYSTEM == "Darwin":
            QGuiApplication.instance().applicationStateChanged.connect(_cursor_after_switch)

    def start(self):
        if QGuiApplication.platformName().startswith("wayland"):
            return
        if not self._timer.isActive():
            self._timer.start()

    @staticmethod
    def _may_take_focus():
        from .window_level import front_app, on_active_space_macos
        if front_app() not in (None, "us", "resolve"):
            return False
        return SYSTEM != "Darwin" or on_active_space_macos()

    def _window_under_mouse(self, windows):
        pos = QCursor.pos()
        under = [w for w in windows if w.frameGeometry().contains(pos)]
        if not under:
            return None
        # where windows overlap, the dialog (Settings, History ...) is the one on top
        return max(under, key=lambda w: 0 if w is self.picker else 1 if w is getattr(
            self.picker, "preview_window", None) else 2)

    def _tick(self):
        windows = [w for w in QApplication.topLevelWidgets()
                   if w.isVisible() and not isinstance(w, QMenu) and w.windowTitle() not in SKIP_TITLES
                   and w.windowType() not in (Qt.ToolTip, Qt.Popup, Qt.SplashScreen)]
        if not windows:
            self._timer.stop()
            self._over, self._done = None, None
            return
        if not self.settings.general.get("focus_on_hover", True) or QApplication.activePopupWidget():
            return
        w = self._window_under_mouse(windows)
        if w is None:
            self._over, self._ticks, self._done = None, 0, None  # left our windows: next visit counts again
            return
        if w is not self._over:
            self._over, self._ticks = w, 0
        self._ticks += 1
        if self._ticks < DWELL_TICKS or self._done is w or _buttons_down():
            return
        if not self._may_take_focus():
            self._done = w  # this visit is over - another app is in front
            return
        target = self.picker if w is getattr(self.picker, "preview_window", None) else w  # typing goes to the search
        modal = QApplication.activeModalWidget()
        if modal is not None and target is not modal:
            # Settings / Insert as / History is open: the window under it can't take the keyboard -
            # bringing it forward would only hide the dialog behind it
            self._done = w
            return
        if QApplication.activeWindow() is target and QGuiApplication.applicationState() == Qt.ApplicationActive:
            self._done = w
            return
        self._done = w
        from .picker_window import bring_to_front
        target.raise_()
        target.activateWindow()
        bring_to_front(target)
        if target is self.picker:
            self.picker.search_edit.setFocus()
