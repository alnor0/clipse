"""The logs and settings in a zip: sent with a problem from Send feedback (Settings -> About, feedback.py), or kept
as a file on the Desktop when sending doesn't work. They hold clip names and folder paths, which the window says.
"""
import io
import os
import platform
import sys
import time
import zipfile

from . import __version__

from . import paths

FILES = (paths.log("service.log"), paths.log("service.previous.log"), paths.log("watcher.log"),
         paths.SETTINGS_FILE)
SUPPORT_EMAIL = "support@alnor.store"  # (where feedback saved as a file goes)


def _about(resolve_version=""):
    lines = [f"Clipse {__version__}",
             f"Made {time.strftime('%Y-%m-%d %H:%M:%S')}",
             f"System: {platform.platform()}",
             f"Python: {sys.version.split()[0]} ({sys.executable})",
             f"Session: {os.environ.get('XDG_SESSION_TYPE', '')} {os.environ.get('XDG_CURRENT_DESKTOP', '')}".rstrip(),
             f"DaVinci Resolve: {resolve_version or 'not asked'}"]
    try:
        from PySide6 import __version__ as qt
        lines.append(f"PySide6: {qt}")
    except Exception:
        lines.append("PySide6: not found")
    for module in ("av", "numpy", "miniaudio"):
        try:
            lines.append(f"{module}: {getattr(__import__(module), '__version__', 'yes')}")
        except Exception:
            lines.append(f"{module}: not installed")
    for label, folder in (("settings", paths.CONFIG_DIR), ("data", paths.DATA_DIR), ("logs", paths.LOG_DIR)):
        try:
            lines.append(f"In the {label} folder: " + ", ".join(sorted(os.listdir(folder))))
        except OSError:
            pass
    return "\n".join(lines) + "\n"


def where():
    """The Desktop if there is one, else the home folder."""
    home = os.path.expanduser("~")
    desktop = os.path.join(home, "Desktop")
    return desktop if os.path.isdir(desktop) else home


def _pack(z, resolve_version=""):
    z.writestr("about.txt", _about(resolve_version))
    for source in FILES:
        if os.path.isfile(source):
            z.write(source, os.path.basename(source))


def logs_zip(resolve_version=""):
    """The logs, the settings and what it runs on, as a zip's bytes."""
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        _pack(z, resolve_version)
    return out.getvalue()


def make(folder=None, resolve_version="", extra=(), logs=True):
    """Writes the report and returns its path. `extra`: (name, bytes) to put in too (feedback's words, pictures)."""
    path = os.path.join(folder or where(), f"Clipse report {time.strftime('%Y-%m-%d %H%M')}.zip")
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in extra:
            z.writestr(name, data)
        if logs:
            _pack(z, resolve_version)
    return path
