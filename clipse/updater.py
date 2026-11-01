"""Update notice + one-click update.

Checking: reads the newest version from alnor.store's downloads
(LATEST_URL, written by tools/publish_release.py - the test folder's while
test_updates is in the settings folder - paths.config) at most once a day
(Settings -> General -> "Check for updates" turns it off). Nothing else
is sent.

Updating: the compiled program opens the download page. A
Python install, where the release names a zip (`zip_url`), downloads it
and runs its own installer for this
system - the same thing as installing by hand, so the app's own Python
environment, the preview
libraries and the Resolve shortcuts are all handled the usual way. It
runs as a separate process from a copy of this file, with the Python
Clipse was installed with, because the installer replaces the
app's own files (Windows can't replace files that are in use). When it's
done it opens the picker, so you can see it worked; what it did is in
update.log (paths.log).

This file only uses the standard library, so the copy runs on its own.
"""
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile

LATEST_URL = "https://downloads.alnor.store/clipse.json"  # {"version", "page_url", "<kind>_url"/"_sha256"?, "zip_url"?}
DOWNLOAD_KINDS = ("linux", "windows", "mac")  # (each a download a copy updates itself from - self_update)
TEST_LATEST_URL = "https://downloads.alnor.store/test/clipse.json"  # (publish_release.py --test)
DOWNLOAD_PAGE = "https://alnor.store/download.html"
try:
    from . import paths
    CHECK_FILE = paths.cache("update_check.json")
    LOG_FILE = paths.log("update.log")
    TEST_SWITCH = paths.config("test_updates")  # there: updates come from the test folder (a release tried first)
except ImportError:  # (run as a copy of this file by itself - run_update: none of these is used there)
    paths = None
    CHECK_FILE = LOG_FILE = TEST_SWITCH = os.path.join(tempfile.gettempdir(), "clipse-update")
CHECK_EVERY_SECONDS = 24 * 3600
APP = "clipse"


def installed_version():
    """This copy's own number (an older install's package record could say another)."""
    try:
        from . import __version__
        return __version__
    except Exception:  # (run as a copy of this file by itself - run_update)
        try:
            from importlib.metadata import version
            return version(APP)
        except Exception:
            return "0"


def _parts(version):
    out = []
    for piece in str(version).lstrip("vV").split("."):
        digits = "".join(ch for ch in piece if ch.isdigit())
        out.append(int(digits) if digits else 0)
    return tuple(out + [0] * (3 - len(out)))


def is_newer(candidate, current):
    return _parts(candidate) > _parts(current)


def latest_url():
    return TEST_LATEST_URL if os.path.exists(TEST_SWITCH) else LATEST_URL


def fetch_latest(timeout=6):
    """{"version", "page_url", "zip_url", "<kind>_url", "<kind>_sha256"} of the newest release ("" for a file there's
    none of), or None. The <kind>_url ones are the downloads a copy updates itself from (self_update), each with
    its fingerprint."""
    request = urllib.request.Request(latest_url(), headers={"User-Agent": APP})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        data = json.load(response)
    version = str(data.get("version") or "").lstrip("vV")
    if not version:
        return None
    release = {"version": version, "zip_url": str(data.get("zip_url") or ""),
               "page_url": str(data.get("page_url") or DOWNLOAD_PAGE)}
    for k in DOWNLOAD_KINDS:
        release[f"{k}_url"], release[f"{k}_sha256"] = str(data.get(f"{k}_url") or ""), str(data.get(f"{k}_sha256") or "")
    return release


_last = {"failed": False}  # the last check got no answer (offline, or nowhere to ask) - not "up to date"


def last_check_failed():
    return _last["failed"]


def check(force=False):
    """The newest release if it's newer than what's installed, else None.
    Uses the answer from the last day unless force=True. Never raises."""
    state = {}
    try:
        with open(CHECK_FILE, encoding="utf-8") as f:
            state = json.load(f)
    except (OSError, ValueError):
        pass
    latest = state.get("latest")
    if force or not latest or time.time() - state.get("checked", 0) > CHECK_EVERY_SECONDS \
            or state.get("from", LATEST_URL) != latest_url():  # (the test switch flipped: ask the other place)
        try:
            latest = fetch_latest()
        except Exception as e:
            print(f"[update] couldn't check for updates: {e}")
            _last["failed"] = True
            return None
        _last["failed"] = False
        try:
            paths.write_json(CHECK_FILE, {"checked": time.time(), "latest": latest, "from": latest_url()})
        except OSError:
            pass
    if latest and is_newer(latest.get("version", "0"), installed_version()):
        return latest
    return None


def cached_update():
    """The newer release found by the last check, without asking again - only one asked of where updates come from
    now (one from the test folder doesn't count once the test switch is off)."""
    try:
        with open(CHECK_FILE, encoding="utf-8") as f:
            state = json.load(f)
        latest = state.get("latest") if state.get("from", LATEST_URL) == latest_url() else None
        if latest and is_newer(latest.get("version", "0"), installed_version()):
            return latest
    except (OSError, ValueError, AttributeError):
        pass
    return None


def base_python():
    """The Python Clipse's own environment was made from (not the
    environment itself - that's what gets replaced)."""
    candidates = [getattr(sys, "_base_executable", None)]
    try:
        with open(os.path.join(sys.prefix, "pyvenv.cfg"), encoding="utf-8") as f:
            for line in f:
                key, _, value = line.partition("=")
                if key.strip() == "home":
                    home = value.strip()
                    candidates += [os.path.join(home, n) for n in ("python3", "python", "python.exe")]
    except OSError:
        pass
    candidates += [shutil.which("python3"), shutil.which("python")]
    for c in candidates:
        if c and os.path.isfile(c) and not os.path.realpath(c).startswith(os.path.realpath(sys.prefix) + os.sep):
            return c
    return sys.executable


def start_update(zip_url):
    # (the compiled program can't update itself this way - it installs with pip: Settings > About opens the download
    #  page instead, launch.COMPILED - as it does when the release has no zip)
    """Starts the update in the background (a copy of this file, run by
    the base Python). The running service gets stopped by the installer."""
    work = tempfile.mkdtemp(prefix="clipse-update-")
    script = os.path.join(work, "run_update.py")
    shutil.copy(os.path.abspath(__file__), script)
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    log = open(LOG_FILE, "w", encoding="utf-8")
    kwargs = {"stdout": log, "stderr": subprocess.STDOUT, "stdin": subprocess.DEVNULL, "cwd": work}
    if os.name == "nt":
        kwargs["creationflags"] = 0x00000008 | 0x00000200 | 0x08000000  # detached, new group, no window
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen([base_python(), "-I", script, "--run", zip_url], **kwargs)


def run_update(zip_url):
    """Download, run the installer, open the picker. Returns True on success."""
    print(f"Downloading {zip_url}", flush=True)
    work = tempfile.mkdtemp(prefix="clipse-download-")
    archive = os.path.join(work, "release.zip")
    request = urllib.request.Request(zip_url, headers={"User-Agent": APP})
    with urllib.request.urlopen(request, timeout=60) as response, open(archive, "wb") as out:
        shutil.copyfileobj(response, out)
    with zipfile.ZipFile(archive) as z:
        z.extractall(work)
    system = platform.system()
    wanted = {"Windows": "Install.bat", "Darwin": "Install.command"}.get(system, "install.sh")
    installer = None
    for root, _dirs, files in os.walk(work):
        if wanted in files and "pyproject.toml" in files:
            installer = os.path.join(root, wanted)
            break
    if installer is None:
        print(f"No {wanted} in the download - update stopped.", flush=True)
        return False
    print(f"Running {installer}", flush=True)
    env = dict(os.environ, CLIPSE_UNATTENDED="1")
    if system == "Windows":
        command = ["cmd", "/c", installer]
    else:
        command = ["bash", installer]
    result = subprocess.run(command, cwd=os.path.dirname(installer), env=env, stdin=subprocess.DEVNULL)
    shutil.rmtree(work, ignore_errors=True)
    if result.returncode != 0:
        print(f"The installer stopped with an error ({result.returncode}).", flush=True)
        return False
    print("Updated. Opening the picker.", flush=True)
    client = _client_path()
    if client:
        subprocess.Popen([client], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return True


def _client_path():
    name = "clipse.exe" if os.name == "nt" else "clipse"
    for folder in (os.path.expanduser("~/.local/bin"), os.path.dirname(sys.executable)):
        path = os.path.join(folder, name)
        if os.path.isfile(path):
            return path
    return shutil.which(name)


def update_from_cli():
    """clipse --update: check, then update in the foreground."""
    latest = check(force=True)
    if latest is None:
        print(f"Clipse {installed_version()} is the newest version.")
        return True
    from . import self_update
    if self_update.can(latest):  # (the download put in place of this one, then opened - self_update)
        print(f"Updating Clipse {installed_version()} -> {latest['version']} ...")
        try:
            self_update.finish(self_update.prepare(latest), in_service=False)
        except Exception as e:
            print(f"Couldn't update: {e}\nDownload it from {latest.get('page_url') or DOWNLOAD_PAGE}")
            return False
        return True
    from .launch import COMPILED
    if COMPILED or not latest.get("zip_url"):  # (the compiled program is downloaded again - it can't pip install)
        print(f"Clipse {latest['version']} is out: {latest.get('page_url') or DOWNLOAD_PAGE}")
        return True
    print(f"Updating Clipse {installed_version()} -> {latest['version']} ...")
    work = tempfile.mkdtemp(prefix="clipse-update-")
    script = os.path.join(work, "run_update.py")
    shutil.copy(os.path.abspath(__file__), script)
    return subprocess.run([base_python(), "-I", script, "--run", latest["zip_url"]], cwd=work).returncode == 0


if __name__ == "__main__" and len(sys.argv) >= 3 and sys.argv[1] == "--run":
    ok = False
    try:
        ok = run_update(sys.argv[2])
    except Exception as e:
        print(f"Update failed: {e}", flush=True)
    sys.exit(0 if ok else 1)
