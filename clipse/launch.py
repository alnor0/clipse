"""How to start a part of Clipse - the service, the client, the watcher - as a program of its own.

Run from Python (an install, or the project folder) it's this Python with `-m clipse.<part>`. Compiled
(tools/build_compiled.sh) there is no Python to hand that to: the one compiled program is started with a switch
(tools/compiled_main.py: --service, --client, --watcher, --playhead, --organise - and nothing at all is the app opened by hand, which opens
the picker: client.open_app). Everything that starts one of them asks here, so the two can't drift apart."""
import os
import sys

# Nuitka puts __compiled__ into every module it compiles
COMPILED = "__compiled__" in globals()

_SWITCH = {"daemon": ["--service"], "client": ["--client"], "watcher": ["--watcher"], "playhead": ["--playhead"],
           "organise": ["--organise"], "beats": ["--beats"], "app": []}
_MODULE = {"app": ("client", "--open")}  # (from Python, opening the app by hand is the client's --open)


def program():
    """The compiled program itself (its full path), or this Python. (Compiled, sys.executable is a "python" that
    doesn't exist, next to the program - so: that folder, and the name the program was started by.)"""
    if not COMPILED:
        return sys.executable
    if os.environ.get("APPIMAGE"):  # (Linux: the AppImage file - what runs inside it is somewhere new every time)
        return os.environ["APPIMAGE"]
    # (the program is clipse.exe on Windows, clipse.bin elsewhere: a file called clipse would collide with the
    #  app's own folder of the same name beside it)
    started_as = getattr(globals()["__compiled__"], "original_argv0", "") or ("clipse.exe" if os.name == "nt" else "clipse.bin")
    return os.path.join(os.path.dirname(os.path.abspath(sys.executable)), os.path.basename(started_as))


def quiet(exe):
    """On Windows the windowless twin of a Python (pythonw), so nothing opens a console window - a compiled
    program is built without one."""
    if os.name == "nt" and not COMPILED:
        twin = os.path.join(os.path.dirname(exe), "pythonw.exe")
        if os.path.exists(twin):
            return twin
    return exe


def command(part, *args, windowless=False):
    """The command line that starts `part` ("daemon", "client", "watcher", or "app": Clipse opened by hand)
    with `args`."""
    exe = quiet(program()) if windowless else program()
    if COMPILED:
        return [exe, *_SWITCH[part], *args]
    module, *switch = _MODULE.get(part, (part,))
    return [exe, "-m", f"clipse.{module}", *switch, *args]


def restart_service():
    """Restarts the service from inside it (Restart Clipse, Settings' Restart): a client of its own stops this one
    and starts it again (client --restart) - the start-up card shows meanwhile - and the picker opens again once it's
    up (--refresh: 2026-10-19, "please reopen the picker")."""
    import subprocess
    subprocess.Popen(command("client", "--restart", "--refresh", windowless=True), start_new_session=True,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def identity():
    """Which copy this is: its version and the program that runs its service - asked of a running service (WHO) by
    a copy opened by hand, which takes over when it's another one (an older version, or another install)."""
    from . import __version__
    return f"{__version__} {os.path.realpath(command('daemon')[0])}"
