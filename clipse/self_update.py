"""Update (Settings > About, clipse --update): the new version downloaded, checked and put in place
of this one, then started - it takes over from this service and the picker says "Updated to ..." (2026-10-19: on
every system - it was Linux only; on a Mac and Windows Update opened the download page and the old version ran on
until a restart). Whatever goes wrong leaves this version as it was and says so; the download page is the way then.

  Linux    the installed AppImage replaced (install.update_from), the new one opened.
  Windows  the installer downloaded and run quietly (/VERYSILENT ... /OPEN=1): this Clipse and its watcher end first,
           the installer puts the new one over it, sets it up (--install) and opens the picker (tools/windows/clipse.iss).
  Mac      the disk image downloaded, its Clipse.app copied beside this one and swapped in (the old one kept aside,
           hidden, until the new one's first start clears it away - the old one may still be loading parts of itself),
           the new one opened. Downloaded by the app, not a browser: no "downloaded from the internet" question.

Each download is checked against the fingerprint the release names (clipse.json's <kind>_sha256,
tools/publish_release.py) - a broken, half or stale download never replaces a working app."""
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request

OLD_MAC_APP = ".Clipse-old.app"   # (beside Clipse.app: the version before, until the new one's first start)
NEW_MAC_APP = ".Clipse-update.app"


def mac_bundle():
    """The Clipse.app this copy runs from - None when it isn't one, or it can't be written to (installed by another
    user: the download page then)."""
    from .launch import COMPILED, program
    if sys.platform != "darwin" or not COMPILED:
        return None
    bundle = os.path.dirname(os.path.dirname(os.path.dirname(program())))  # .../Clipse.app/Contents/MacOS/clipse.bin
    if not bundle.endswith(".app") or not os.access(os.path.dirname(bundle), os.W_OK):
        return None
    return bundle


def kind():
    """Which download updates this copy: "linux", "windows", "mac" (Apple silicon only) - or None (from Python: pip's
    update - updater.start_update; or one that can't update itself)."""
    from . import install
    from .launch import COMPILED
    if install.is_installed_copy():
        return "linux"
    if COMPILED and os.name == "nt":
        return "windows"
    if mac_bundle():
        return "mac"
    return None


def can(latest):
    """This copy can update itself to `latest` (clipse.json): it names the download for this system."""
    k = kind()
    return bool(k and latest and latest.get(f"{k}_url"))


def _download(url, path, sha256):
    request = urllib.request.Request(url, headers={"User-Agent": "clipse"})
    with urllib.request.urlopen(request, timeout=120) as response, open(path, "wb") as out:
        shutil.copyfileobj(response, out)
    if sha256:
        with open(path, "rb") as f:
            if hashlib.file_digest(f, "sha256").hexdigest() != sha256.lower():
                raise ValueError("the download doesn't match the release - try again later")


def prepare(latest):
    """The slow part, off the GUI thread: downloaded, checked and (Linux, Mac) put in place. Returns what finish()
    needs. Raises with what to say when it can't - this version is left as it was."""
    from . import install
    k = kind()
    version = latest["version"]
    if k == "linux":
        install.update_from(latest["linux_url"], version, latest.get("linux_sha256", ""))
        return {"kind": k, "version": version}
    work = tempfile.mkdtemp(prefix="clipse-update-")
    if k == "windows":
        installer = os.path.join(work, "clipse-windows.exe")
        _download(latest["windows_url"], installer, latest.get("windows_sha256", ""))
        with open(installer, "rb") as f:
            if f.read(2) != b"MZ":
                raise ValueError("the download isn't the installer")
        return {"kind": k, "version": version, "installer": installer}
    try:
        image = os.path.join(work, "clipse.dmg")
        _download(latest[f"{k}_url"], image, latest.get(f"{k}_sha256", ""))
        with open(image, "rb") as f:
            f.seek(-512, os.SEEK_END)
            if f.read(4) != b"koly":  # (every disk image ends in this mark)
                raise ValueError("the download isn't the app")
        mount = os.path.join(work, "mount")
        os.makedirs(mount)
        subprocess.run(["hdiutil", "attach", "-nobrowse", "-readonly", "-noautoopen", "-mountpoint", mount, image],
                       check=True, capture_output=True, timeout=120)
        try:
            swap_mac_app(os.path.join(mount, "Clipse.app"), mac_bundle())
        finally:
            subprocess.run(["hdiutil", "detach", mount, "-quiet"], capture_output=True, timeout=60)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return {"kind": k, "version": version}


def swap_mac_app(source, bundle):
    """`source` (the new Clipse.app) in place of `bundle`, the old one kept aside (OLD_MAC_APP) - one step that
    can't leave no app behind: anything failing puts the old one back."""
    if not os.path.isdir(source):
        raise ValueError("the download has no Clipse.app in it")
    parent = os.path.dirname(bundle)
    staging, old = os.path.join(parent, NEW_MAC_APP), os.path.join(parent, OLD_MAC_APP)
    for leftover in (staging, old):
        shutil.rmtree(leftover, ignore_errors=True)
    copier = ["ditto", source, staging] if shutil.which("ditto") else None  # (ditto keeps the app's signature)
    if copier:
        subprocess.run(copier, check=True, capture_output=True, timeout=300)
    else:
        shutil.copytree(source, staging, symlinks=True)
    os.rename(bundle, old)
    try:
        os.rename(staging, bundle)
    except OSError:
        os.rename(old, bundle)
        raise


def clear_away():
    """The new version's first start on a Mac: the one before, kept aside while it was still running, goes."""
    bundle = mac_bundle()
    if bundle:
        shutil.rmtree(os.path.join(os.path.dirname(bundle), OLD_MAC_APP), ignore_errors=True)


def finish(ready, in_service=True):
    """The new version started (on the GUI thread, once prepare() is done): it takes over from this service and
    opens the picker, which says "Updated to ...". On Windows the installer does that - this Clipse ends first, so
    its files can be replaced."""
    from . import install
    from .launch import command
    install.note(f"Updated to {ready['version']}")
    quiet = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    if ready["kind"] == "linux":
        subprocess.Popen([install.target()], start_new_session=True, **quiet)
    elif ready["kind"].startswith("mac"):
        subprocess.Popen(["open", "-n", mac_bundle() or command("app")[0]], start_new_session=True, **quiet)
    else:
        from . import watcher
        subprocess.Popen([ready["installer"], "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS",
                          "/FORCECLOSEAPPLICATIONS", "/OPEN=1"],
                         creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP, **quiet)
        watcher.quit_running()  # (its file is being replaced too)
        if in_service:
            from PySide6.QtWidgets import QApplication
            from .daemon import _remove_pid_file
            _remove_pid_file()  # (now: the installer may end it before it's quit - a stop, not a crash)
            QApplication.instance().quit()
        else:
            from .client import stop_daemon
            stop_daemon(quiet=True)
