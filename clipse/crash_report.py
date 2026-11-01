"""Crash reports (Settings > About, "Send crash reports", 2026-10-22: "when a crash there should be sent data so i
can fix the problem ... automatically"): a run that didn't stop as it should - its PID file still there when the
next one starts - has its log sent to alnor.store by itself, the way Send feedback's go (feedback.send, kind
"crash"; tools/feedback.py lists them). Nothing is asked.

A shutdown isn't a crash: Sway (or X) closing as the computer goes down ends Qt there and then, before Clipse can
tidy up - "The Wayland connection broke" is its last line. Nor is a run the computer restarted under, unless its log
shows a crash. The home folder is written ~ in what's sent; the settings aren't sent. Offline it's kept and tried at
the next start, for a week. Plain Python: it runs as the service starts, before any window toolkit."""
import io
import os
import sys
import threading
import time
import zipfile

from . import paths

PENDING = paths.log("crash_report.json")
PREVIOUS_LOG = paths.log("service.previous.log")
KEEP_FOR = 7 * 24 * 3600
MOST_LOG = 200_000  # (the end of the log: what led up to the crash)

# The screen going away ends Qt with these words, and none of Clipse's tidying up.
SCREEN_GONE = ("The Wayland connection broke", "The X11 connection broke", "could not connect to display")
# What a crash leaves in the log (faulthandler, an uncaught error).
CRASH_SIGNS = ("Fatal Python error", "Traceback (most recent call last)")


def _read_tail(path, size=MOST_LOG):
    try:
        with open(path, "rb") as f:
            f.seek(max(0, os.path.getsize(path) - size))
            return f.read().decode("utf-8", "replace")
    except OSError:
        return ""


def booted_at():
    """When the computer last started (seconds since 1970), or None."""
    try:
        if sys.platform.startswith("linux"):
            with open("/proc/stat") as f:
                for line in f:
                    if line.startswith("btime "):
                        return float(line.split()[1])
        elif sys.platform == "darwin":
            import subprocess
            out = subprocess.run(["sysctl", "-n", "kern.boottime"], capture_output=True, text=True,
                                 timeout=2).stdout  # ("{ sec = 1729580000, usec = 0 } ...")
            return float(out.split("sec =")[1].split(",")[0])
        elif os.name == "nt":
            import ctypes
            ctypes.windll.kernel32.GetTickCount64.restype = ctypes.c_ulonglong
            return time.time() - ctypes.windll.kernel32.GetTickCount64() / 1000
    except Exception:
        pass
    return None


def crashed(pid_file, log_text, booted=None):
    """Did the run before crash? Its PID file is left behind, and it didn't go with the screen or the computer."""
    if not os.path.exists(pid_file):
        return False
    if any(line in log_text[-800:] for line in SCREEN_GONE):
        return False
    if any(sign in log_text for sign in CRASH_SIGNS):
        return True
    try:
        return not (booted is not None and os.path.getmtime(pid_file) < booted)
    except OSError:
        return True


def private(text):
    """The home folder (and so the person's user name in paths) written ~."""
    home = os.path.expanduser("~")
    if len(home) > 1:
        text = text.replace(home, "~")
        if os.name == "nt":
            text = text.replace(home.replace("\\", "/"), "~")
    return text


def _wanted():
    general = (paths.read_json(paths.SETTINGS_FILE, {}) or {}).get("general") or {}
    return general.get("send_crash_reports", True)


def note_at_start(pid_file):
    """At the start of the service that holds the port: the run before crashed - its report is kept to send (when
    sending is on). Then whatever is waiting goes, in the background."""
    log_text = _read_tail(PREVIOUS_LOG)
    if crashed(pid_file, log_text, booted_at()):
        print("The run before stopped unexpectedly - its log is service.previous.log.")
        if _wanted():
            from . import __version__
            try:
                paths.write_json(PENDING, {"at": time.time(), "version": __version__, "log": private(log_text)})
            except OSError:
                pass
    send_waiting()


def _zip(report):
    from . import report as rp
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("about.txt", private(rp._about()))
        z.writestr("service.previous.log", report["log"])
    return out.getvalue()


def _words(report):
    lines = [line for line in report["log"].splitlines() if line.strip()][-40:]
    when = time.strftime("%Y-%m-%d %H:%M", time.localtime(report.get("at", time.time())))
    return f"Clipse {report.get('version', '?')} stopped unexpectedly ({when}). The end of its log:\n\n" + \
        "\n".join(lines)


def _send(report):
    from . import feedback
    feedback.post({"kind": "crash", "text": _words(report)}, [("logs", "logs.zip", "application/zip", _zip(report))])


def send_waiting(wait=False):
    """A report kept from a crash goes now - quietly, in the background; kept for the next start when it can't."""
    report = paths.read_json(PENDING, None)
    if not report:
        return
    if not _wanted() or time.time() - report.get("at", 0) > KEEP_FOR:
        forget()
        return

    def go():
        try:
            _send(report)
        except Exception as e:
            print(f"[crash report] not sent yet: {e}")
            return
        forget()
        print("[crash report] sent.")
    if wait:
        go()
    else:
        threading.Thread(target=go, daemon=True).start()


def forget():
    try:
        os.remove(PENDING)
    except OSError:
        pass
