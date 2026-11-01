#!/usr/bin/env python3
"""Persistent background picker for inserting Media Pool clips into the
current DaVinci Resolve timeline. Runs once, stays warm, and shows/hides
its window when triggered — instead of paying Python + Qt startup cost on
every keypress.

Lifecycle:
- Started by `clipse --restart`, or automatically by the
  client the first time any shortcut is pressed while it isn't running.
- Claims the port immediately (so only one instance can ever run), then
  waits for DaVinci Resolve. Messages that arrive before Resolve is
  connected are ignored; a PROBE is answered with READY or WAITING.
- Quits by itself when Resolve closes (Settings -> General, on by
  default), so it only runs while you're editing.
- With "Start in the background" on (the default), a tiny login helper
  (watcher.py) starts it as soon as Resolve opens, and it reads the open
  project's Media Pool ahead of time - so even the first press is instant.

Bind your keybind to the client (`clipse`), not this file.
"""
import argparse
import atexit
import os
import socket
import sys
import threading
import time

from . import paths
from . import resolve_client as rc
from .timeline_tools import ADJUSTMENT_MODES, JUMP_DIRECTIONS, STEP_DIRECTIONS

HOST = "127.0.0.1"
PORT = 51823
PID_FILE = paths.log("daemon.pid")
APP_ID = "clipse"
RESOLVE_CHECK_MS = 3000           # how often to check Resolve is still running
RESOLVE_CHECK_FAILURES_TO_QUIT = 2  # consecutive failed checks before quitting

# Socket message -> what to do. TRIGGER/REFRESH open the picker; the rest
# are the timeline tools (see timeline_tools.py), run straight from the
# client without opening the picker.
DIRECT_COMMANDS = {
    **{f"JUMP:{d}".encode(): ("jump", d) for d in JUMP_DIRECTIONS},
    **{f"STEP:{d}".encode(): ("step", d) for d in STEP_DIRECTIONS},
    **{f"ADJ:{m}".encode(): ("adjust", m) for m in ADJUSTMENT_MODES},
    **{f"COMP:{m}".encode(): ("comp", m) for m in ADJUSTMENT_MODES},
    b"FUSION:tidy": ("fusion", "tidy"),
    b"FUSION:pullout": ("fusion", "pullout"),
    b"FUSION:copyname": ("fusion", "copyname"),
    b"FUSION:nodeonoff": ("fusion", "nodeonoff"),
    b"FUSION:beforeafter": ("fusion", "beforeafter"),
    b"UNDO:last": ("undo", "last"),
    b"SWAP:clip": ("swap", "clip"),
    b"GRAB:frame": ("grab", "frame"),
    b"VOICE:record": ("voice", "record"),  # (pressed again while it records: it stops)
    b"ORGANISE:project": ("organise", "project"),  # (2026-10-30)
    b"MARKER:fit": ("marker", "fit"),  # (markers.py)
    b"MARKER:add": ("marker", "add"),
    b"MARKER:toggle": ("marker", "toggle"),
    b"GRAB:insert": ("grab", "frame"),  # v1.24.0 shortcut names - still work
    b"GRAB:save": ("grab", "frame"),
}

_ready = threading.Event()   # set once Resolve is connected and the UI exists
_bridge_holder = {"bridge": None}
# A shortcut pressed while the service is still starting isn't lost: the
# last one is kept and carried out the moment everything is ready.
_early = {"message": None}
_early_lock = threading.Lock()
# The picker doesn't toggle, so a second "open" right after the first
# (a double press) would only make it flicker and wipe what was typed.
# That only counts while it's open: once it's closed, the next press
# opens it at once.
DUPLICATE_OPEN_SECONDS = 1.0
_last_open = {"at": -10.0}

# Rapid next/previous presses (and steps - a key held down) are coalesced: the socket thread just adds
# +1/-1 to a running total and only signals the GUI thread if a flush
# isn't already pending. However fast you press, the GUI thread does one
# jump of the net step count instead of working through a backlog — so
# nothing lags behind your fingers.
COUNTED = ("jump", "step")
_pending = {action: {"steps": 0, "scheduled": False} for action in COUNTED}
_pending_lock = threading.Lock()


def _queue_jump(bridge, step, action="jump"):
    with _pending_lock:
        pending = _pending[action]
        pending["steps"] += step
        if pending["scheduled"]:
            return
        pending["scheduled"] = True
    bridge.command.emit(action, "")


def _take_pending_jump(action="jump"):
    with _pending_lock:
        pending = _pending[action]
        steps = pending["steps"]
        pending["steps"] = 0
        pending["scheduled"] = False
    return steps


class _Timed:
    """Puts the time in front of every line written to the log - so "it
    glitched just now" can be found in service.log."""

    def __init__(self, stream):
        self.stream = stream
        self.line_start = True

    def write(self, text):
        import time
        for part in text.splitlines(True):
            if self.line_start:
                self.stream.write(time.strftime("%H:%M:%S  "))
            self.stream.write(part)
            self.line_start = part.endswith("\n")
        return len(text)

    def __getattr__(self, name):  # flush, fileno, isatty ...
        return getattr(self.stream, name)


def _time_the_log():
    """Only when writing to a file (the service's log), not to a terminal."""
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name, None)
        try:
            if stream is None or stream.isatty():
                continue
        except (AttributeError, ValueError):
            continue
        try:  # each line in the file as it's written: the compiled program ignores PYTHONUNBUFFERED, and the
            stream.reconfigure(line_buffering=True)  # running service's log stayed empty until it ended (Windows)
        except (AttributeError, ValueError, OSError):
            pass
        setattr(sys, name, _Timed(stream))


def _fresh_log():
    """The service that really starts (it holds the port): the log so far becomes service.previous.log - after a
    crash it's the one that says why - and this run's begins empty. Copied and emptied rather than moved: the file
    is open (on Windows it couldn't be moved)."""
    import shutil
    import time
    path = os.environ.get("CLIPSE_LOG")
    if path and isinstance(sys.stdout, _Timed):
        try:
            sys.stdout.flush()
            if os.path.getsize(path) > 0:
                shutil.copyfile(path, os.path.join(os.path.dirname(path), "service.previous.log"))
            os.ftruncate(sys.stdout.fileno(), 0)  # (opened to add to: what's written next starts it again)
            # (Windows doesn't hand "add to" on to the service: it went on writing where the old log ended, after a
            os.lseek(sys.stdout.fileno(), 0, os.SEEK_SET)  # run of zero bytes as long as the old log)
        except OSError:
            pass
    if isinstance(sys.stdout, _Timed):
        print(time.strftime("Started %A %d %B %Y"))


def _claim_port():
    """Binds the port right away. Failing to bind means another instance
    already owns it — the cheapest, race-free single-instance check."""
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    if os.name == "nt":
        # On Windows SO_REUSEADDR would let a SECOND process bind the same
        # port; exclusive use is what guarantees a single instance there.
        srv.setsockopt(socket.SOL_SOCKET, getattr(socket, "SO_EXCLUSIVEADDRUSE", socket.SO_REUSEADDR), 1)
    else:
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        srv.bind((HOST, PORT))
    except OSError:
        srv.close()
        return None
    srv.listen(16)
    return srv


def socket_listener(srv):
    while True:
        try:
            conn, _ = srv.accept()
        except OSError:
            return  # socket closed — the service is shutting down
        try:
            data = b""
            conn.settimeout(1.0)  # (one that never hangs up keeps the listener a second at most)
            while len(data) < 4096:  # (a few words from organise.py can be longer than one read)
                try:
                    part = conn.recv(4096 - len(data))
                except TimeoutError:
                    break
                if not part:
                    break
                data += part
                if data in (b"PROBE", b"WHO"):  # (these wait for an answer: no more is coming)
                    break
            data = data.strip()
            if data == b"PROBE":
                conn.sendall(b"READY" if _ready.is_set() else b"WAITING")
            elif data == b"WHO":  # (which copy this is - client.open_app)
                from .launch import identity
                conn.sendall(identity().encode())
        except OSError:
            data = b""
        finally:
            conn.close()

        if data not in (b"TRIGGER", b"REFRESH") and data not in DIRECT_COMMANDS \
                and not data.startswith((b"SAY:", b"RETIRED:")):  # (these two were turned away here until 2026-10-30:
            continue                                           # Organise's "Organised ..." never showed)
        with _early_lock:
            if not _ready.is_set():
                _early["message"] = data  # carried out as soon as the service is ready
                continue
        _dispatch(_bridge_holder["bridge"], data)


def open_from_shortcut(window, force_refresh):
    """The "Search" shortcut, on the GUI thread. A repeated press is only
    dropped while the picker is still open from the press before."""
    import time
    if (not force_refresh and window.isVisible()
            and time.monotonic() - _last_open["at"] < DUPLICATE_OPEN_SECONDS):
        return False
    window.open_picker(force_refresh=force_refresh)
    _last_open["at"] = time.monotonic()  # after it's up: a slow open covers the presses made meanwhile
    from .install import take_note
    said = take_note()  # ("Installed", "Updated to ..." - left by install.py)
    if said:
        window._say(said)
    return True


def _dispatch(bridge, data):
    if data in (b"TRIGGER", b"REFRESH"):
        bridge.triggered.emit(data == b"REFRESH")
    elif data.startswith(b"SAY:"):  # a program of Clipse's own (organise.py) saying how it went, as a toast
        bridge.command.emit("say", data[4:].decode("utf-8", "replace"))
    elif data.startswith(b"RETIRED:"):  # a stand-in in Resolve's menu for a script that's gone (resolve_shortcuts)
        bridge.command.emit("retired", data[8:].decode("utf-8", "replace"))
    elif data in DIRECT_COMMANDS:
        action, arg = DIRECT_COMMANDS[data]
        if action in COUNTED:
            _queue_jump(bridge, 1 if arg in ("next", "forward") else -1, action)
        else:
            bridge.command.emit(action, arg)


def _bye(signum, _frame):
    """Stopped by the system (logging out, shutting down) or asked to: the PID file taken away."""
    print("Stopped.")
    _remove_pid_file()
    os._exit(0)


def _remove_pid_file():
    try:
        with open(PID_FILE) as f:
            ours = f.read().strip() == str(os.getpid())
        if ours:  # (closed first: Windows can't remove an open file)
            os.remove(PID_FILE)
    except OSError:
        pass


NO_CONNECTION_HELP = (
    "Clipse couldn't connect to DaVinci Resolve.\n\n"
    "Check that:\n"
    "  \u2022 you're using DaVinci Resolve Studio (the free version doesn't allow this)\n"
    "  \u2022 Preferences \u2192 System \u2192 General \u2192 \"External scripting using\" is set to Local\n"
    "  \u2022 you restarted Resolve after changing that setting"
)


def show_error(text):
    """A shortcut pressed inside Resolve has no terminal to print to, so
    problems that stop the service are shown in a small dialog."""
    try:
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QApplication, QMessageBox
        if QApplication.instance() is None:
            _no_dock_flash_macos()
        app = QApplication.instance() or QApplication(sys.argv[:1])  # noqa: F841 (must stay alive)
        box = QMessageBox(QMessageBox.Warning, "Clipse", text)
        box.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        if sys.platform == "darwin":
            hide_dock_icon_macos()
            try:
                from AppKit import NSApp
                NSApp.activateIgnoringOtherApps_(True)
            except Exception:
                pass
        box.exec()
    except Exception as e:
        print(f"(couldn't show the error dialog: {e})")


def show_connection_problem(fallback_text):
    """The connection check window (each step with what to do), or a plain
    message if that can't be shown."""
    try:
        from .connection_dialog import show_connection_check
        show_connection_check()
    except Exception as e:
        print(f"(couldn't show the connection check: {e})")
        show_error(fallback_text)


def hide_dock_icon_macos():
    """macOS: run as a background helper — no Dock icon or menu bar for
    "Python" — while the picker can still take keyboard focus."""
    if sys.platform != "darwin":
        return
    try:
        from AppKit import NSApp, NSApplicationActivationPolicyAccessory
        NSApp.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
    except Exception:
        pass


def _no_dock_flash_macos():
    """macOS: Qt turns a plain Python process into a regular app (Dock icon,
    menu bar) while it starts, and hide_dock_icon_macos() takes that back a
    moment later - visible as a bouncing icon. Asking Qt not to do it at
    all stops the flash; only when PyObjC is there to make the process an
    accessory app afterwards (otherwise the picker couldn't take focus)."""
    if sys.platform != "darwin":
        return
    try:
        import AppKit  # noqa: F401
    except Exception:
        return
    os.environ.setdefault("QT_MAC_DISABLE_FOREGROUND_APPLICATION_TRANSFORM", "1")


def _start_qt():
    """QApplication, the app font and the settings - (app, settings)."""
    from PySide6.QtWidgets import QApplication
    from .settings import Settings
    settings = Settings()
    settings.load()
    # Must be set before QApplication() is constructed — Qt's Wayland
    # platform plugin reads this at init time. Without it, Sway (and
    # other wlroots compositors) sees app_id "python3" for every
    # Python/Qt app, making window rules ambiguous.
    os.environ.setdefault("QT_WAYLAND_CLIENT_APP_ID", APP_ID)
    _no_dock_flash_macos()
    app = QApplication(sys.argv[:1])
    app.setQuitOnLastWindowClosed(False)
    hide_dock_icon_macos()
    from .fonts import apply_ui_font
    app.setFont(apply_ui_font(app.font(), settings))  # dialogs (Settings, Insert as, History) use the app font
    app.setApplicationName(APP_ID)
    app.setDesktopFileName(APP_ID)  # X11/XWayland equivalent of the above
    return app, settings


def main():
    parser = argparse.ArgumentParser(prog="clipse-daemon")
    parser.add_argument("--give-up-after", type=float, default=None, metavar="SECONDS",
                        help="exit if DaVinci Resolve isn't running within this many seconds "
                             "(used when the client starts the service automatically)")
    parser.add_argument("--background", action="store_true",
                        help="started ahead of time by the login helper (watcher.py): Resolve is "
                             "still opening, so wait for it patiently and don't show any dialogs")
    args, _unknown = parser.parse_known_args()
    _time_the_log()
    paths.move_old()
    rc.prune_caches()

    srv = _claim_port()
    if srv is None:
        print(f"Another start: Clipse is already running on {HOST}:{PORT} — exiting.")
        sys.exit(0)
    _fresh_log()
    import faulthandler  # (a crash deep inside - Qt, Resolve's library - leaves where it was in the log)
    faulthandler.enable(file=sys.__stderr__)

    os.makedirs(os.path.dirname(PID_FILE), exist_ok=True)
    from . import crash_report
    crash_report.note_at_start(PID_FILE)  # (the run before crashed: its log goes to alnor.store, if that's on)
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))
    atexit.register(_remove_pid_file)
    import signal
    for name in ("SIGTERM", "SIGHUP"):  # (logging out, shutting down: a stop, not a crash)
        if hasattr(signal, name):
            signal.signal(getattr(signal, name), _bye)

    threading.Thread(target=socket_listener, args=(srv,), daemon=True).start()

    # Started by you (the shortcut): Qt comes up first, so a small card can
    # say what's happening while Resolve answers and the picker gets ready.
    # Started at login in the background: no window until Resolve is there.
    app = splash = settings = None
    if not args.background:
        app, settings = _start_qt()
        try:
            from .splash import Splash
            splash = Splash(settings.theme)
            splash.step("Connecting to DaVinci Resolve", 0.12)
        except Exception as e:
            print(f"(no start-up card: {e})")
            splash = None

    def on_waiting():
        print("Waiting for DaVinci Resolve to start...")
        if splash is not None:
            splash.step("Waiting for DaVinci Resolve", 0.12)

    from .watcher import resolve_running
    wait = None
    if splash is not None:
        def wait(seconds):
            """The card keeps moving while Resolve is waited for - and the waiting stops
            once Resolve isn't open at all (opened from the app launcher without it)."""
            end = time.monotonic() + seconds
            while time.monotonic() < end:
                app.processEvents()
                time.sleep(0.02)
            return resolve_running()

    give_up_after = args.give_up_after
    if give_up_after is not None and not args.background and rc._running_resolve_libs():
        # Resolve is already open, so it answers within seconds if it's
        # going to — don't keep someone waiting 45 s for the error.
        give_up_after = min(give_up_after, 12)
    try:
        resolve = rc.connect_to_resolve(on_waiting=on_waiting, timeout=give_up_after, wait=wait)
    except SystemExit as e:  # Resolve's scripting library wasn't found
        print(e)
        if splash is not None:
            splash.hide()
        if args.give_up_after is not None and not args.background:
            srv.close()  # free the port while the message is up
            show_connection_problem(str(e))
        sys.exit(1)
    if resolve is None and splash is not None:
        if resolve_running():
            splash.hide()
        else:
            splash.say("Open DaVinci Resolve first")
            end = time.monotonic() + 2.4
            while splash.isVisible() and time.monotonic() < end:
                app.processEvents()
                time.sleep(0.02)
    if resolve is None:
        if args.give_up_after is not None and not args.background and rc._running_resolve_libs():
            # Resolve IS open but won't answer — almost always the setting
            print("DaVinci Resolve is open but doesn't accept scripting connections — exiting.")
            srv.close()  # free the port while the message is up
            show_connection_problem(NO_CONNECTION_HELP)
        else:
            print("DaVinci Resolve isn't running — exiting.")
        sys.exit(1)
    print("Connected to DaVinci Resolve.")

    if splash is not None:
        splash.step("Getting the picker ready", 0.45)
    # Qt is imported only now (or just above): the port is already claimed,
    # so a second instance started meanwhile exits instead of loading Qt.
    if app is None:
        app, settings = _start_qt()
    from PySide6.QtCore import QObject, Signal, Qt, QTimer
    from .picker_window import PickerWindow

    class TriggerBridge(QObject):
        """Qt signals are the thread-safe way to hand work from the socket
        thread to the GUI thread (queued connection across threads)."""
        triggered = Signal(bool)    # force_refresh
        command = Signal(str, str)  # (action, arg) — timeline tools

    insert_frequency = rc.load_insert_frequency()

    window = PickerWindow(settings, insert_frequency)
    window.set_resolve(resolve)
    if splash is not None:
        splash.step("Reading your Media Pool", 0.8)
        window.opened.connect(splash.finish)  # the picker takes over from here
        QTimer.singleShot(4000, splash.finish)  # started without opening it: don't linger

    bridge = TriggerBridge()
    bridge.triggered.connect(lambda force_refresh: open_from_shortcut(window, force_refresh),
                              Qt.QueuedConnection)

    def on_command(action, arg):
        if action in COUNTED:
            window.run_direct_command(action, _take_pending_jump(action))
        else:
            window.run_direct_command(action, arg)
    bridge.command.connect(on_command, Qt.QueuedConnection)

    # Quit by itself when Resolve closes (Settings -> General). A closed
    # Resolve makes API calls return None or raise; two misses in a row
    # avoids quitting over a single hiccup (e.g. while Resolve is busy).
    failures = {"count": 0}

    def check_resolve_alive():
        if not settings.general.get("stop_with_resolve", True):
            failures["count"] = 0
            return
        try:
            alive = resolve.GetProjectManager() is not None
        except Exception:
            alive = False
        failures["count"] = 0 if alive else failures["count"] + 1
        if failures["count"] >= RESOLVE_CHECK_FAILURES_TO_QUIT:
            print("DaVinci Resolve closed — stopping the background service.")
            app.quit()

    alive_timer = QTimer()
    alive_timer.timeout.connect(check_resolve_alive)
    alive_timer.start(RESOLVE_CHECK_MS)
    # (Python handles a stop from the system - _bye - only when some of its own code runs: this lets it, at once)
    wake = QTimer()
    wake.timeout.connect(lambda: None)
    wake.start(200)

    with _early_lock:
        _bridge_holder["bridge"] = bridge
        _ready.set()
        early, _early["message"] = _early["message"], None
    print(f"Clipse listening on {HOST}:{PORT}")
    try:  # its scripts in Resolve's menu: any that went missing are put back, quietly
        from . import resolve_shortcuts
        put_back = resolve_shortcuts.put_back_missing()
        if put_back:
            print(f"Put back in Resolve's Scripts menu: {', '.join(put_back)}")
    except Exception as e:
        print(f"Couldn't check the scripts in Resolve's menu: {e}")
    if early is not None:
        _dispatch(bridge, early)
    # read the open project's Media Pool now, so the first open is instant
    QTimer.singleShot(300, window.prewarm)
    code = app.exec()
    sys.exit(code)


if __name__ == "__main__":
    main()
