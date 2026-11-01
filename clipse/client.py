#!/usr/bin/env python3
"""The client: tiny (stdlib only), it sends a command to the service and starts it when needed. USAGE is its help."""
import socket
import os
import sys

from . import paths
# signal / subprocess / time are only needed for --restart, so they're
# imported inside those functions — keeps every normal keypress as cheap
# as possible (subprocess alone is a noticeable chunk of startup time).

USAGE = """Bind your keybind to the `clipse` command (installed by
the installer) — not to this file directly, and not to the daemon.

Picker:
  (no args)          Open the picker.
  --refresh          Open the picker with a fresh Media Pool scan.
  --open             As opening the app by hand: set it up (Resolve's scripts,
                     starting at login the first time, its place among the
                     apps) and open the picker.

Shortcuts inside DaVinci Resolve (Workspace -> Scripts, bind them in
Keyboard Customization):
  --install-resolve-shortcuts     add them (the installer does this for you)
  --uninstall-resolve-shortcuts   remove them

Checking the setup:
  --check            Check everything needed to talk to DaVinci Resolve
                     and say what to fix (Python, Resolve, its scripting
                     setting, the shortcuts, previewing).
  --update           Install the newest version (from alnor.store).

Background service (normally automatic: it starts as soon as DaVinci
Resolve opens - or with the first shortcut - and stops when Resolve closes):
  --restart          Start the service, or restart it if it's running.
  --stop             Stop the service.
  --watch            Run the login helper that starts the service when
                     Resolve opens (Settings -> General -> "Start in the
                     background" sets this up for you; on Sway & co. add
                     `exec clipse --watch` to your config).
  --autostart        Make starting at login match that setting (installers).
  --no-autostart     Stop starting at login (uninstallers).
  --shutdown         Stop the service and the login helper (installers).
  --app-entry        Put Clipse among the apps (Linux: the app
                     launcher's list), opening the picker (installers).

Timeline tools — bind each one to its own system-wide key in your window
manager / OS (they run instantly, without opening the picker):
  jump next | jump previous
      Jump the playhead to the next/previous timeline use of the clip
      selected in the Media Pool (wraps around).
  adjust match | adjust match-skip-adj | adjust fixed
      Place an adjustment clip matching the clip under the playhead /
      the same but ignoring existing adjustment clips / fixed length.
      (Clip name and lengths: Settings -> Timeline -> Adjustment clip.)
  comp match | comp match-skip-adj | comp fixed
      The same with an empty Fusion composition from the Media Pool
      (Settings -> Timeline -> Fusion composition).
  fusion tidy | fusion pullout
      Sort the open Fusion composition's node editor into clean lines /
      take the selected node out of its chain (the chain stays connected).
  undo last
      Take back the last thing Clipse did (every clip of it).
  grab frame
      Grab the frame under the playhead into the "frame_grabs" bin in "clipse" (and,
      per Settings, onto the timeline and/or as a PNG in your folder).

No PySide6/Qt import here on purpose — this stays a plain-stdlib script so
a keypress doesn't pay any GUI-toolkit startup cost; it just opens a
socket to the already-running daemon.
"""  # (a string, not the docstring: the compiled program has no docstrings)


HOST = "127.0.0.1"
PORT = 51823
PID_FILE = paths.log("daemon.pid")
LOG_FILE = paths.log("service.log")
PREVIOUS_LOG_FILE = paths.log("service.previous.log")
START_WAIT_TIMEOUT_SECONDS = 45  # Resolve itself can take a while to open


def send(message):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((HOST, PORT))
    s.sendall(message)
    s.close()


def probe():
    """None if the service isn't running, else "READY" (connected to
    Resolve) or "WAITING" (running, still waiting for Resolve)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(1.0)
        s.connect((HOST, PORT))
        s.sendall(b"PROBE")
        reply = s.recv(16).decode(errors="ignore").strip()
        s.close()
        return reply or "READY"  # an older service doesn't reply — it only listens once ready
    except (ConnectionRefusedError, OSError):
        return None


def _launch_daemon(extra_args=()):
    """Launches the daemon via `python -m clipse.daemon` — works
    the same whether this package was installed by the installer, pip, or is
    just being run from a source checkout, without needing to guess
    where an installed console-script entry point ended up on PATH."""
    import subprocess
    from .launch import command
    # (the compiled program, compiled - launch.py; from Python on Windows pythonw: a project folder's Python starts
    #  the real one under it, and that one opened a console window of its own - closing it ended the service)
    args = command("daemon", *extra_args, windowless=True)
    # Output goes to a log file - the first thing to look at, or to send along, when something doesn't work. Added
    # to here: the service that really starts begins it afresh (daemon._fresh_log, once it holds the port) - moved
    # aside here, a second start that found one running took the running one's log away (2026-10-19).
    try:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        log = open(LOG_FILE, "a", encoding="utf-8")
    except OSError:
        log = open(os.devnull, "w")
    env = dict(os.environ, PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8", CLIPSE_LOG=LOG_FILE)
    if os.name == "nt":
        flags = (subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
                 | getattr(subprocess, "CREATE_NO_WINDOW", 0))
        subprocess.Popen(args, creationflags=flags, stdin=subprocess.DEVNULL, stdout=log,
                         stderr=subprocess.STDOUT, env=env)
    else:
        subprocess.Popen(args, start_new_session=True, stdin=subprocess.DEVNULL, stdout=log,
                         stderr=subprocess.STDOUT, env=env)
    log.close()


def _wait_until_ready(timeout):
    import time
    deadline = time.monotonic() + timeout
    seen_running = False
    while time.monotonic() < deadline:
        state = probe()
        if state == "READY":
            return True
        if state is None and seen_running:
            return False  # the service started, then gave up (Resolve isn't open)
        seen_running = seen_running or state is not None
        time.sleep(0.2)
    return False


def _daemon_running():
    return probe() is not None


def daemon_pid():
    """The service's process id from its PID file - only if that process is
    there and really is the service (a stale file could otherwise point at
    an unrelated process that happens to have reused the number)."""
    try:
        with open(PID_FILE) as f:
            pid = int(f.read().strip())
    except (OSError, ValueError):
        return None
    return pid if _is_daemon(pid) else None


def _is_daemon(pid):
    """Is `pid` the service? Run from Python its command says clipse.daemon; compiled it's the program
    started with --service (launch.py)."""
    import subprocess
    try:
        if sys.platform.startswith("linux"):
            with open(f"/proc/{pid}/cmdline", "rb") as f:
                command = f.read().replace(b"\0", b" ").decode(errors="ignore")
        elif os.name == "nt":  # (its command line, as on the others: by the process's name alone any Python - this
            command = subprocess.run(  # one, the watcher - was taken for the service, and a restart could end it)
                [os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "WindowsPowerShell", "v1.0",
                              "powershell.exe"),  # (by its full path, whatever the PATH it's started with)
                 "-NoProfile", "-NonInteractive", "-Command",
                 f"(Get-CimInstance Win32_Process -Filter 'ProcessId={int(pid)}').CommandLine"],
                capture_output=True, text=True, timeout=10, stdin=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
        else:
            command = subprocess.run(["ps", "-p", str(pid), "-o", "command="], capture_output=True, text=True,
                                     timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    return is_service_command(command)


def is_service_command(command):
    """A process's command line, as it is the service's: Python's clipse.daemon, or the compiled program
    with --service (its other copies - --client, --watcher, opened by hand - aren't)."""
    import re
    if "clipse.daemon" in command or "clipse-daemon" in command:
        return True
    if os.name == "nt":  # (in quotes, a folder with a space in it - C:\Users\Jo Lee\...)
        compiled = re.match(r'\s*"?([^"]*[/\\])?clipse(\.exe)?"?(\s|$)', command, re.IGNORECASE)
    else:
        compiled = re.match(r"\s*(\S*[/\\])?clipse(\.exe|\.bin)?(\s|$)", command)  # (.bin: Linux / Mac - launch.py)
    return bool(compiled) and bool(re.search(r"\s--service\b", command))


def _alive(pid):
    if os.name == "nt":
        return _is_daemon(pid)
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def stop_daemon(quiet=False):
    """Stops the background service - also one that has stopped answering
    (stuck inside a call to Resolve, where it can't even hear a shortcut):
    that one is found by its PID file and ended the hard way."""
    import signal
    import time
    pid = daemon_pid()
    if pid is None:
        if not quiet:
            print("The background service isn't running.")
        return False
    try:
        os.kill(pid, signal.SIGTERM)  # TerminateProcess on Windows
        deadline = time.monotonic() + 3.0
        while _alive(pid) and time.monotonic() < deadline:
            time.sleep(0.1)
        if _alive(pid) and hasattr(signal, "SIGKILL"):
            os.kill(pid, signal.SIGKILL)
            time.sleep(0.3)
        try:  # a service ended this way didn't get to tidy up after itself
            with open(PID_FILE) as f:
                ours = f.read().strip() == str(pid)
            if ours:  # (closed first: Windows can't remove an open file - left, every restart read as a crash)
                os.remove(PID_FILE)
        except OSError:
            pass
        print(f"Stopped the background service (PID {pid}).")
        return True
    except OSError as e:
        print(f"Couldn't stop the background service: {e}")
        return False


def start_or_restart_daemon(message):
    """--restart: starts the service if it isn't running, restarts it if it
    is. With no other command it returns right away — the service waits for
    Resolve by itself. With a command (e.g. --restart adjust match) it waits
    until the service is connected and then sends it."""
    import time
    if stop_daemon(quiet=True):
        time.sleep(1)  # let the old process release the port
    _launch_daemon()
    if message is None:
        print("Background service started.")
        return
    if not _wait_until_ready(START_WAIT_TIMEOUT_SECONDS):
        print("The service is waiting for DaVinci Resolve — open Resolve and try again.")
        sys.exit(1)
    send(message)


def _claim_start():
    """Only one press starts the service. Pressing again while it's still
    starting would otherwise start a second wait and open the picker
    twice; that press is dropped - the first one opens it."""
    import time
    for _ in range(2):
        try:
            fd = os.open(START_LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            return True
        except FileExistsError:
            try:
                if time.time() - os.path.getmtime(START_LOCK) < START_WAIT_TIMEOUT_SECONDS + 10:
                    return False
                os.remove(START_LOCK)  # left over from a start that crashed
            except OSError:
                return False
        except OSError:
            return True  # can't use the lock - just go ahead
    return True


def _release_start():
    try:
        os.remove(START_LOCK)
    except OSError:
        pass


def auto_start_and_send(message):
    """A shortcut was pressed but the service isn't running: start it and
    deliver the command once it's connected. Gives up (and the service
    exits again) if Resolve isn't open, so nothing is left running."""
    os.makedirs(os.path.dirname(START_LOCK), exist_ok=True)
    if not _claim_start():
        return
    try:
        if probe() is None:  # (it may have just been started by the login helper)
            _launch_daemon(["--give-up-after", str(START_WAIT_TIMEOUT_SECONDS)])
        if _wait_until_ready(START_WAIT_TIMEOUT_SECONDS + 5):
            send(message)
        else:
            print("Couldn't connect to DaVinci Resolve (is it open?) - the background service wasn't "
                  f"started. Details: {LOG_FILE}")
            sys.exit(1)
    finally:
        _release_start()


TOOL_ARGS = {
    "jump": ("next", "previous"),
    "step": ("forward", "back"),
    "adjust": ("match", "match-skip-adj", "fixed"),
    "comp": ("match", "match-skip-adj", "fixed"),
    "fusion": ("tidy", "pullout", "copyname", "nodeonoff", "beforeafter"),
    "undo": ("last",),
    "swap": ("clip",),
    "grab": ("frame", "insert", "save"),  # insert/save: older names, same thing
    "voice": ("record",),
    "organise": ("project",),
    "marker": ("fit", "add", "toggle"),
}
FLAGS = ("--refresh", "--restart", "--stop")
START_LOCK = paths.log("starting")


def resolve_shortcuts(install):
    from . import resolve_shortcuts as rs
    if install:
        folder, written = rs.install()
        print(f"Added {len(written)} Clipse shortcuts to DaVinci Resolve:\n  {folder}")
        print("Restart Resolve, then give them keys in DaVinci Resolve -> Keyboard Customization "
              "(search for \"Clipse\").")
    else:
        folder, removed = rs.uninstall()
        print(f"Removed {len(removed)} Clipse shortcuts from DaVinci Resolve.")


def build_message(argv):
    """Turns the command line into the one message the daemon understands.
    Returns None for a bare --restart / --stop (nothing to send)."""
    args = [a for a in argv if a not in FLAGS]
    if not args:
        if "--refresh" in argv:
            return b"REFRESH"
        if "--restart" in argv or "--stop" in argv:
            return None
        return b"TRIGGER"
    tool = args[0]
    choice = args[1].lstrip("-") if len(args) > 1 else None
    if tool not in TOOL_ARGS or choice not in TOOL_ARGS[tool]:
        print(USAGE)
        sys.exit(2)
    prefix = {"jump": "JUMP", "step": "STEP", "adjust": "ADJ", "comp": "COMP", "fusion": "FUSION", "undo": "UNDO", "grab": "GRAB",
              "swap": "SWAP", "voice": "VOICE", "organise": "ORGANISE",
              "marker": "MARKER"}[tool]
    return f"{prefix}:{choice}".encode()


def running_identity():
    """The running service's launch.identity(), "" from a service too old to say, None when none is running."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(1.0)
        s.connect((HOST, PORT))
        s.sendall(b"WHO")
        reply = b""
        while chunk := s.recv(4096):
            reply += chunk
        s.close()
        return reply.decode(errors="ignore").strip()
    except socket.timeout:
        return ""
    except (ConnectionRefusedError, OSError):
        return None


def open_app(picker=True):
    """Clipse opened by hand - a double-click, Applications, the Start menu, the app launcher. It sets itself
    up (the scripts in Resolve's menu, starting at login the first time, its place among the apps) and opens the
    picker, starting the service if it isn't running: never a click that does nothing (2026-10-18). The copy opened
    by hand is the one in use from then on: the scripts, the login start and a running service of another copy (an
    older version, another install) all go over to it. picker=False is Linux's terminal line (--install, install.sh):
    set up, a line for each step, no picker - Resolve may not be open yet."""
    paths.move_old()
    from . import autostart
    from . import install
    from . import resolve_shortcuts as rs
    from . import self_update
    self_update.clear_away()  # (a Mac's version before an update, kept aside while it was still running)
    kind = install.what_to_do()  # (an AppImage / a Mac's Clipse.app run from anywhere but its place: it goes there)
    if kind in ("install", "update"):
        install.place(kind, say=picker)  # (the terminal says it itself)
    if kind:
        install.open_installed(*([] if picker else ["--install"]))
    for step in (rs.install, autostart.first_open, autostart.point_here, autostart.install_app_entry):
        try:
            step()
        except Exception as e:  # (the picker opens anyway)
            print(f"  Couldn't {step.__name__.replace('_', ' ')}: {e}")
    if not picker:  # (the terminal line: what's in place now, a tick each)
        place = install.folder().replace(os.path.expanduser("~"), "~", 1)
        for done, line in ((install.is_installed_copy(), f"Installed in {place}"),
                           (bool(rs.utility_scripts_folder()), "Added to Resolve's Scripts menu"),
                           (autostart.is_enabled(), "Starts by itself when Resolve opens"),
                           (os.path.isfile(autostart.APP_ENTRY), "Among your apps")):
            if done:
                try:  # (a terminal that can't show a tick gets a plain one)
                    "\u2713".encode(sys.stdout.encoding or "ascii")
                    tick = "\u2713"
                except (UnicodeEncodeError, LookupError):
                    tick = "+"
                tick = f"\033[32m{tick}\033[0m" if sys.stdout.isatty() else tick
                print(f"  {tick} {line}")
    from .launch import identity
    running = running_identity()
    if running is not None and running != identity():  # another copy's service (an older version, another install)
        import time
        if picker:
            print(f"Taking over from the service that's running ({running or 'an older version'}).")
        if stop_daemon(quiet=True):
            time.sleep(1)  # let it let go of the port
    if picker:
        sys.argv = sys.argv[:1]
        main()


def main():
    paths.move_old()  # (from ~/.clipse, once - whichever part of the app starts first)
    argv = sys.argv[1:]
    if "--open" in argv:
        open_app()
        return
    if "--app-entry" in argv:  # (the installers: Clipse among the apps - Linux)
        from . import autostart
        print(autostart.install_app_entry() or "Nothing to add here.")
        return
    if os.name == "nt":
        # Started by the active app (a hotkey tool, Resolve) — let the
        # picker take focus from it; Windows blocks that otherwise.
        try:
            import ctypes
            ctypes.windll.user32.AllowSetForegroundWindow(-1)
        except Exception:
            pass
    if "--check" in argv:
        from . import diagnose
        print(diagnose.report(diagnose.run_checks()))
        return
    if "--update" in argv:
        from . import updater
        sys.exit(0 if updater.update_from_cli() else 1)
    if "--install-resolve-shortcuts" in argv or "--uninstall-resolve-shortcuts" in argv:
        resolve_shortcuts(install="--install-resolve-shortcuts" in argv)
        return
    if "--watch" in argv:
        from . import watcher
        watcher.main()
        return
    if "--autostart" in argv or "--no-autostart" in argv:
        from . import autostart
        print(autostart.sync() if "--autostart" in argv else autostart.set_enabled(False))
        return
    if "--shutdown" in argv:
        from . import watcher
        watcher.quit_running()
        stop_daemon(quiet=True)
        return
    if "--stop" in argv:
        stop_daemon()
        return
    message = build_message(argv)
    if "--restart" in argv:
        start_or_restart_daemon(message)
        return

    try:
        send(message)
    except (ConnectionRefusedError, OSError):
        auto_start_and_send(message)  # first press after Resolve opened — start the service


if __name__ == "__main__":
    main()
