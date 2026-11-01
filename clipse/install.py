"""Linux: Clipse as one AppImage file, installed by a terminal line (install.sh runs it with --install). Run
from anywhere it installs itself quietly in ~/.local/share/clipse (XDG_DATA_HOME's) - no window, Linux's way - and runs from
there: Resolve's scripts, the login start and the app launcher's entry point there from then on (opened by hand
instead, the picker opens and says "Installed"). A newer one opened later replaces it (an update), the same or an older one just opens the installed one.
The Update button replaces it in place by itself (update_from). Settings > About > Uninstall takes it all away again
(the settings, the key and what it learned stay, for when it comes back - paths.py).
A Mac's Clipse.app opened from anywhere but Applications (the .dmg, Downloads) puts itself there the same way."""
import os
import shutil
import sys

from . import __version__
from . import paths

NAME = "clipse.AppImage"
NOTE = paths.log("install_note")  # a toast for the picker's next opening (take_note)


def appimage():
    """The AppImage file this copy runs from (its runtime says so), else None."""
    path = os.environ.get("APPIMAGE")
    return path if path and os.path.isfile(path) else None


def folder():
    return os.path.join(os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share"), "clipse")


def target():
    return os.path.join(folder(), NAME)


def installed_version():
    try:
        with open(os.path.join(folder(), "version"), encoding="utf-8") as f:
            return f.read().strip() if os.path.isfile(target()) else None
    except OSError:
        return None


def is_installed_copy():
    here = appimage()
    return bool(here) and os.path.realpath(here) == os.path.realpath(target())


def icon():
    """The icon for the app launcher's entry: a copy next to the installed AppImage (what's inside one is only there
    while it runs, somewhere new every time), else the package's own."""
    kept = os.path.join(folder(), "icon.png")
    if appimage() and os.path.isfile(kept):
        return kept
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "icon.png")


def mac_app():
    """The Clipse.app this compiled copy runs from (a Mac), else None."""
    from .launch import COMPILED, program
    if sys.platform != "darwin" or not COMPILED:
        return None
    bundle = os.path.dirname(os.path.dirname(os.path.dirname(program())))  # .../Clipse.app/Contents/MacOS/clipse.bin
    return bundle if bundle.endswith(".app") else None


def mac_target():
    """Where Clipse.app goes on a Mac: Applications - the user's own when the computer's can't be written to."""
    if os.access("/Applications", os.W_OK):
        return "/Applications/Clipse.app"
    return os.path.expanduser("~/Applications/Clipse.app")


def mac_out_of_place(bundle):
    """Opened from the .dmg, Downloads, the Desktop ... - not from an Applications folder. Opened straight from the
    .dmg (or a download never moved), macOS runs it from a random folder of its own that's gone after a restart
    (App Translocation, seen 2026-10-20): Resolve's scripts and the login start pointed there."""
    real = os.path.realpath(bundle)
    return not any(real.startswith(os.path.realpath(place) + os.sep)
                   for place in ("/Applications", os.path.expanduser("~/Applications")))


def mac_version(bundle):
    import plistlib
    try:
        with open(os.path.join(bundle, "Contents", "Info.plist"), "rb") as f:
            return str(plistlib.load(f).get("CFBundleShortVersionString") or "") or None
    except (OSError, ValueError):
        return None


def what_to_do():
    """Opened by hand: "install" (none installed yet), "update" (this one is newer), "open" (the installed one is the
    same or newer - it's the one to open) or None (not an AppImage / a Clipse.app out of place, or the installed one
    itself)."""
    bundle = mac_app()
    if bundle:
        if not mac_out_of_place(bundle):
            return None
        there = mac_version(mac_target()) if os.path.isdir(mac_target()) else None
    elif not sys.platform.startswith("linux") or not appimage() or is_installed_copy():
        return None
    else:
        there = installed_version()
    if there is None:
        return "install"
    from .updater import is_newer
    return "update" if is_newer(__version__, there) else "open"


def _put(source, version):
    """`source` becomes the installed AppImage (an older one is replaced in one step), the icon and the version
    beside it."""
    os.makedirs(folder(), exist_ok=True)
    part = target() + ".part"
    shutil.copyfile(source, part)
    os.chmod(part, 0o755)
    os.replace(part, target())
    shutil.copyfile(os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "icon.png"),
                    os.path.join(folder(), "icon.png"))
    with open(os.path.join(folder(), "version"), "w", encoding="utf-8") as f:
        f.write(version)


def _put_mac(source, target):
    """`source` (a Clipse.app) becomes `target` - an older one there swapped out in one step (self_update's way).
    The copy loses the download's quarantine mark: with it, macOS would run it from a folder of its own again (it
    was opened once already, when macOS asked)."""
    import subprocess
    from .self_update import swap_mac_app
    os.makedirs(os.path.dirname(target), exist_ok=True)
    if os.path.isdir(target):
        swap_mac_app(source, target)
    else:
        staging = target + ".part"
        shutil.rmtree(staging, ignore_errors=True)
        if shutil.which("ditto"):  # (ditto keeps the app's signature)
            subprocess.run(["ditto", source, staging], check=True, capture_output=True, timeout=300)
        else:
            shutil.copytree(source, staging, symlinks=True)
        os.rename(staging, target)
    if shutil.which("xattr"):
        subprocess.run(["xattr", "-dr", "com.apple.quarantine", target], capture_output=True, timeout=60)


def place(kind, say=True):
    """This AppImage installed - or on a Mac this Clipse.app in Applications (`kind` "install" / "update" - what the
    picker's toast will say, with `say`)."""
    bundle = mac_app()
    if bundle:
        _put_mac(bundle, mac_target())
    else:
        _put(appimage(), __version__)
    if say:
        installed = "Installed in Applications. The download can go." if bundle else "Installed"
        note(installed if kind == "install" else f"Updated to {__version__}")


def update_from(url, version, sha256=""):
    """The Update button: the AppImage of `version` at `url` downloaded (checked against `sha256`, the release's
    fingerprint) and put in place of this one (the running
    service keeps the file it started from until it's restarted - client.open_app's takeover does that). Raises on
    failure, leaving the installed one as it was."""
    import tempfile
    import urllib.request
    work = tempfile.mkdtemp(prefix="clipse-update-")
    try:
        download = os.path.join(work, NAME)
        request = urllib.request.Request(url, headers={"User-Agent": "clipse"})
        with urllib.request.urlopen(request, timeout=60) as response, open(download, "wb") as out:
            shutil.copyfileobj(response, out)
        with open(download, "rb") as f:
            if f.read(4) != b"\x7fELF":
                raise ValueError("the download isn't the app")
        if sha256:  # (the release's fingerprint: a broken, half or stale download never replaces a working app)
            import hashlib
            with open(download, "rb") as f:
                if hashlib.file_digest(f, "sha256").hexdigest() != sha256.lower():
                    raise ValueError("the download doesn't match the release - try again later")
        _put(download, version)
        note(f"Updated to {version}")
    finally:
        shutil.rmtree(work, ignore_errors=True)


def open_installed(*args):
    """Becomes the installed copy (it sets itself up, and opens the picker unless `args` is --install) - this process
    ends here."""
    path = os.path.join(mac_target(), "Contents", "MacOS", "clipse.bin") if mac_app() else target()
    env = {k: v for k, v in os.environ.items() if k not in ("APPIMAGE", "APPDIR", "ARGV0", "OWD")}
    os.execve(path, [path, *args], env)


def note(text):
    try:
        os.makedirs(os.path.dirname(NOTE), exist_ok=True)
        with open(NOTE, "w", encoding="utf-8") as f:
            f.write(text)
    except OSError:
        pass


def take_note():
    """What installing left to say, once ("" when nothing). "Updated to X" said by a version that isn't X: the update
    didn't get as far as starting it (self_update) - that's said instead."""
    try:
        with open(NOTE, encoding="utf-8") as f:
            text = f.read().strip()
        os.remove(NOTE)
    except OSError:
        return ""
    if text.startswith("Updated to ") and text[len("Updated to "):] != __version__:
        return f"The update to {text[len('Updated to '):]} didn't finish - it's on alnor.store"
    return text


def can_uninstall():
    """Settings > About shows Uninstall: the installed AppImage (Linux), or Clipse.app on a Mac (2026-10-19: dragged
    to the Bin, it left its scripts in Resolve's menu and its login start behind). Windows has its own uninstaller."""
    from .self_update import mac_bundle
    return is_installed_copy() or bool(mac_bundle())


def uninstall():
    """Everything installing put in place: Resolve's scripts, the login start, the app launcher's entry, the
    AppImage - or on a Mac Clipse.app itself. Returns what's left to say ("" when all went)."""
    from . import autostart, watcher
    from . import resolve_shortcuts as rs
    problems = []
    for what, step in (("Resolve's scripts", rs.uninstall), ("the login start", lambda: autostart.set_enabled(False)),
                       ("the watcher", watcher.quit_running),
                       ("the app entry", autostart.remove_app_entry), ("the app", _remove_files)):
        try:
            step()
        except Exception as e:
            problems.append(f"{what}: {e}")
    return "; ".join(problems)


def _remove_files():
    """Only what installing put there - the folder too once it's empty. On a Mac: Clipse.app (it's running - that's
    fine, it quits next), and the one before an update if it's still beside it."""
    from .self_update import OLD_MAC_APP, mac_bundle
    for made in (paths.CACHE_DIR, paths.LOG_DIR):  # (made again if it comes back; settings and data stay)
        shutil.rmtree(made, ignore_errors=True)
    bundle = mac_bundle()
    if bundle:
        shutil.rmtree(os.path.join(os.path.dirname(bundle), OLD_MAC_APP), ignore_errors=True)
        shutil.rmtree(bundle)
        return
    for name in (NAME, "icon.png", "version", NAME + ".part"):
        try:
            os.remove(os.path.join(folder(), name))
        except FileNotFoundError:
            pass
    try:
        os.rmdir(folder())
    except OSError:
        pass
