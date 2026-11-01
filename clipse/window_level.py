"""Stay on top of DaVinci Resolve only.

The picker, its preview and Settings float above Resolve - but the moment
you switch to another app (a browser, Finder, Slack) they drop back like
normal windows, so they're never in your way there. Back in Resolve (or
clicking one of them) they float above it again.

Checked a few times a second while one of them is open, by asking the
system which app is in front - nothing is read from other apps.
macOS and Windows; on Linux the window manager decides (window rules).
"""
import os
import platform

from PySide6.QtCore import Qt, QObject, QTimer
from PySide6.QtWidgets import QApplication

SYSTEM = platform.system()
KEEP_ALWAYS = ("Clipse keys",)  # demo-mode key labels: always on top while recording


def _front_app_macos():
    """("us" | "resolve" | "other")."""
    from AppKit import NSWorkspace
    app = NSWorkspace.sharedWorkspace().frontmostApplication()
    if app is None:
        return "other"
    if app.processIdentifier() == os.getpid():
        return "us"
    bundle = str(app.bundleIdentifier() or "")
    name = str(app.localizedName() or "")
    if bundle.startswith("com.blackmagic-design.DaVinciResolve") or "DaVinci Resolve" in name:
        return "resolve"
    return "other"


def _front_app_windows():
    import ctypes
    from ctypes import wintypes
    user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return "other", None
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if pid.value == os.getpid():
        return "us", hwnd
    handle = kernel32.OpenProcess(0x1000, False, pid.value)  # PROCESS_QUERY_LIMITED_INFORMATION
    name = ""
    if handle:
        buf = ctypes.create_unicode_buffer(1024)
        size = wintypes.DWORD(1024)
        if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            name = os.path.basename(buf.value).lower()
        kernel32.CloseHandle(handle)
    return ("resolve" if name in ("resolve.exe",) else "other"), hwnd


def front_app():
    """"us", "resolve" or "other" - the app in front right now. None where
    that can't be asked (Linux: the window manager decides)."""
    try:
        if SYSTEM == "Darwin":
            return _front_app_macos()
        if SYSTEM == "Windows":
            return _front_app_windows()[0]
    except Exception:
        pass
    return None


def on_active_space_macos():
    """macOS: is one of our windows on the Space you're looking at? (They
    stay on Resolve's Space; swiping to another one leaves them behind.)"""
    try:
        from AppKit import NSApp
        windows = [w for w in NSApp.windows() if w.isVisible()]
        return not windows or any(w.isOnActiveSpace() for w in windows)
    except Exception:
        return True


def _modal_windows_macos(widgets):
    """The system windows of our open dialogs (Settings, Insert as, History)."""
    found = []
    try:
        import objc
        for w in widgets:
            if w.isModal():
                found.append(objc.objc_object(c_void_p=int(w.winId())).window())
    except Exception:
        pass
    return found


class ResolveOnlyFloat(QObject):
    """Keeps Clipse's windows floating only while Resolve (or
    Clipse itself) is the app in front."""

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self._timer = QTimer(self)
        self._timer.setInterval(350)
        self._timer.timeout.connect(self._tick)
        self._floating = None

    def start(self):
        self._floating = None  # look again, whatever was set before
        if SYSTEM in ("Darwin", "Windows") and not self._timer.isActive():
            self._timer.start()

    def _ours(self):
        # real windows only: tooltips, menus and popups come and go all the time - re-ordering the
        # windows for each of them made the cursor flicker and the keyboard wander
        return [w for w in QApplication.topLevelWidgets()
                if w.isVisible() and w.windowTitle() not in KEEP_ALWAYS
                and w.windowType() not in (Qt.ToolTip, Qt.Popup, Qt.SplashScreen)]

    def _tick(self):
        windows = self._ours()
        if not windows:
            self._timer.stop()
            return
        ids = {id(w) for w in windows}
        if ids != getattr(self, "_seen", None):  # a window opened (Settings, preview): set it up too
            self._seen = ids
            self._floating = None
        if not self.settings.general.get("float_only_over_resolve", True):
            self._apply(True, windows, None, front_is_us=True)
            return
        try:
            if SYSTEM == "Darwin":
                front, hwnd = _front_app_macos(), None
            else:
                front, hwnd = _front_app_windows()
        except Exception:
            return
        self._apply(front in ("us", "resolve"), windows, hwnd, front_is_us=front == "us")

    def _apply(self, floating, windows, front_hwnd, front_is_us=False):
        if floating == self._floating:
            return
        self._floating = floating
        try:
            if SYSTEM == "Darwin":
                from AppKit import NSApp, NSFloatingWindowLevel, NSModalPanelWindowLevel, NSNormalWindowLevel
                level = NSFloatingWindowLevel if floating else NSNormalWindowLevel
                key = NSApp.keyWindow()
                modal, panel, moved = _modal_windows_macos(windows), NSModalPanelWindowLevel, False
                for window in NSApp.windows():
                    if window.isVisible() and str(window.title() or "") not in KEEP_ALWAYS:
                        # a dialog that just opened (or a menu, a tooltip) is already above the picker:
                        # pulling it down and re-ordering it made the cursor flicker
                        above = floating and window.level() > level and (window in modal or window.level() > panel)
                        if window.level() != level and not above:
                            window.setLevel_(level)
                            moved = True
                        if floating and not front_is_us and window != key:
                            window.orderFrontRegardless()  # back above Resolve, without taking the keyboard
                            moved = True
                if floating and moved and key is not None:
                    key.orderFrontRegardless()  # the window you're typing in stays on top (a dialog over the picker)
            elif SYSTEM == "Windows":
                import ctypes
                flags = 0x0001 | 0x0002 | 0x0010  # SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE
                # the window you're in (a dialog over the picker) last, so it stays on top: in the order Qt lists
                # them the picker was made topmost after Settings and covered it (Windows, 2026-10-22)
                front = [QApplication.activeModalWidget(), QApplication.activeWindow()]
                windows = sorted(windows, key=lambda w: (any(w is f for f in front), w is front[0]))
                for w in windows:
                    hwnd = int(w.winId())
                    if floating:
                        ctypes.windll.user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, flags)       # HWND_TOPMOST
                    else:
                        ctypes.windll.user32.SetWindowPos(hwnd, -2, 0, 0, 0, 0, flags)       # HWND_NOTOPMOST
                        if front_hwnd:  # and just behind the app you switched to
                            ctypes.windll.user32.SetWindowPos(hwnd, front_hwnd, 0, 0, 0, 0, flags)
        except Exception as e:
            print(f"[windows] couldn't change how the windows float: {e}")
