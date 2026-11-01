"""Starting the login helper (watcher.py) when you log in - Settings ->
General -> "Start in the background", on by default.

  macOS    a LaunchAgent:  ~/Library/LaunchAgents/store.alnor.clipse.plist
  Windows  a "Run" entry:  HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run
  Linux    an autostart file: ~/.config/autostart/clipse.desktop
           (tiling window managers such as Sway don't read those - add
           `exec clipse --watch` to your config instead)

Plain standard library: the installers and the client use this without Qt.
"""
import os
import subprocess
import sys

from . import watcher
from . import paths

LABEL = "store.alnor.clipse"
NAME = "clipse"
LOG_FILE = paths.log("watcher.log")
MAC_PLIST = os.path.expanduser(f"~/Library/LaunchAgents/{LABEL}.plist")
LINUX_DESKTOP = os.path.join(os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"),
                             "autostart", f"{NAME}.desktop")
WINDOWS_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def command():
    """What starts the watcher at login - pythonw on Windows, so nothing opens a console window (compiled: the
    program itself with --watcher - launch.py)."""
    from .launch import command as start
    return start("watcher", windowless=True)


def tiling_session():
    """Linux window managers that don't start ~/.config/autostart files."""
    if not sys.platform.startswith("linux"):
        return False
    desktop = (os.environ.get("XDG_CURRENT_DESKTOP") or "").lower()
    return bool(os.environ.get("SWAYSOCK") or os.environ.get("HYPRLAND_INSTANCE_SIGNATURE")
                or any(name in desktop for name in ("sway", "hyprland", "i3", "river", "niri")))


# -- macOS --
def _launchctl(*args):
    try:
        return subprocess.run(["launchctl", *args], capture_output=True, text=True, timeout=15).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _enable_macos():
    import plistlib
    os.makedirs(os.path.dirname(MAC_PLIST), exist_ok=True)
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    plist = {
        "Label": LABEL,
        "ProgramArguments": command(),
        "RunAtLoad": True,
        "LimitLoadToSessionType": "Aqua",  # your desktop session - the picker needs it
        "StandardOutPath": LOG_FILE,
        "StandardErrorPath": LOG_FILE,
        "EnvironmentVariables": {"PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8"},
    }
    with open(MAC_PLIST, "wb") as f:
        plistlib.dump(plist, f)
    domain = f"gui/{os.getuid()}"
    _launchctl("bootout", f"{domain}/{LABEL}")  # an older one (new paths after an update)
    if not _launchctl("bootstrap", domain, MAC_PLIST):  # loads it now, and at every login
        _launchctl("load", "-w", MAC_PLIST)


def _disable_macos():
    _launchctl("bootout", f"gui/{os.getuid()}/{LABEL}")
    try:
        os.remove(MAC_PLIST)
    except OSError:
        pass


# -- Windows --
def _quote(arg):
    return f'"{arg}"' if (" " in arg or not arg) else arg


def _enable_windows():
    import winreg
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, WINDOWS_RUN_KEY) as key:
        winreg.SetValueEx(key, NAME, 0, winreg.REG_SZ, " ".join(_quote(a) for a in command()))


def _disable_windows():
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, WINDOWS_RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, NAME)
    except OSError:
        pass


# -- Linux --
def _desktop_exec(arg):
    # the autostart spec: quote anything with spaces; escape " ` $ and backslashes
    if any(c in arg for c in ' \t"`$\\'):
        arg = '"' + "".join("\\" + c if c in '"`$\\' else c for c in arg) + '"'
    return arg


def _enable_linux():
    os.makedirs(os.path.dirname(LINUX_DESKTOP), exist_ok=True)
    with open(LINUX_DESKTOP, "w", encoding="utf-8") as f:
        f.write("[Desktop Entry]\n"
                "Type=Application\n"
                "Name=Clipse\n"
                "Comment=Gets the Clipse picker ready as soon as DaVinci Resolve opens\n"
                f"Exec={' '.join(_desktop_exec(a) for a in command())}\n"
                "Terminal=false\n"
                "NoDisplay=true\n"
                "X-GNOME-Autostart-enabled=true\n")


def _disable_linux():
    try:
        os.remove(LINUX_DESKTOP)
    except OSError:
        pass


def is_enabled():
    if sys.platform == "darwin":
        return os.path.exists(MAC_PLIST)
    if os.name == "nt":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, WINDOWS_RUN_KEY) as key:
                winreg.QueryValueEx(key, NAME)
            return True
        except OSError:
            return False
    return os.path.exists(LINUX_DESKTOP)


def start_now():
    """Runs the watcher right away (no need to log out and in again)."""
    if watcher.running():
        return
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    log = open(LOG_FILE, "w", encoding="utf-8")
    kwargs = {"stdin": subprocess.DEVNULL, "stdout": log, "stderr": subprocess.STDOUT,
              "env": dict(os.environ, PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8")}
    if os.name == "nt":
        kwargs["creationflags"] = (subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
                                   | getattr(subprocess, "CREATE_NO_WINDOW", 0))
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen(command(), **kwargs)
    log.close()


def set_enabled(on):
    """Turns starting at login on or off - and starts or stops the watcher
    now, so it takes effect straight away. Returns a line to show."""
    try:
        if on:
            {"darwin": _enable_macos, "win32": _enable_windows}.get(sys.platform, _enable_linux)()
            if sys.platform == "darwin":
                import time
                time.sleep(0.6)  # launchd starts it by itself (RunAtLoad) - this is only a fallback
            start_now()
            if tiling_session():
                return ("Starting in the background. Your window manager doesn't run autostart files - "
                        "add this line to its config so it also starts when you log in:\n"
                        f"  exec {' '.join(_quote(a) for a in command())}")
            return "Starting in the background when you log in."
        {"darwin": _disable_macos, "win32": _disable_windows}.get(sys.platform, _disable_linux)()
        watcher.quit_running()
        return "No longer starting in the background."
    except Exception as e:
        return f"Couldn't change starting in the background: {e}"


def first_open():
    """The first time the app is opened by hand: starting at login, as Settings ships it - and never again after
    that (turned off in Settings, it stays off)."""
    from .settings import Settings
    settings = Settings()
    settings.load()
    if settings.general.get("app_set_up"):
        return None
    settings.general["app_set_up"] = True
    settings.save()
    if settings.general.get("start_in_background", True) and not is_enabled():
        return set_enabled(True)
    return None


APP_ENTRY = os.path.join(os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share"), "applications",
                         f"{NAME}.desktop")


def point_here():
    """Opened by hand, this copy is the one in use: starting at login (when it's on) starts this copy's watcher, and
    one of another copy's (an older version, another install) is ended."""
    if not is_enabled():
        return None
    import time
    if watcher.quit_running():
        time.sleep(0.5)  # (it lets go of its port)
    {"darwin": _enable_macos, "win32": _enable_windows}.get(sys.platform, _enable_linux)()
    start_now()
    return None


def install_app_entry():
    """Linux: Clipse in the app launcher's list (GNOME, KDE, rofi / wofi's drun ...) with its icon - picked,
    it opens the picker (launch "app"). On a Mac it's the .app in Applications, on Windows the Start menu's
    shortcut: the installers make those. Rewritten only when something in it changed."""
    if not sys.platform.startswith("linux"):
        return None
    import shlex
    from .launch import command
    from .install import icon as entry_icon
    icon = entry_icon()  # (an AppImage's own files move every time it runs: the installed copy keeps one beside it)
    text = ("[Desktop Entry]\nType=Application\nName=Clipse\n"
            "Comment=Search DaVinci Resolve's Media Pool, scripts and Fusion - and put them on the timeline\n"
            f"Exec={shlex.join(command('app'))}\nIcon={icon}\nTerminal=false\nStartupNotify=false\n"
            "Categories=AudioVideo;Video;\n")
    try:
        with open(APP_ENTRY, encoding="utf-8") as f:
            if f.read() == text:
                return None
    except OSError:
        pass
    os.makedirs(os.path.dirname(APP_ENTRY), exist_ok=True)
    with open(APP_ENTRY, "w", encoding="utf-8") as f:
        f.write(text)
    return f"Clipse is among your apps ({APP_ENTRY})"


def remove_app_entry():
    try:
        os.remove(APP_ENTRY)
    except FileNotFoundError:
        pass


def sync():
    """Makes the login item match the setting (the installers run this)."""
    from .settings import Settings
    settings = Settings()
    settings.load()
    return set_enabled(settings.general.get("start_in_background", True))
