"""Finds out why Clipse can't talk to DaVinci Resolve - and says
what to do about it. Used by the connection check window (shown when the
service can't connect, and from Settings) and by
`clipse --check` (run at the end of the installers).

No Qt here: each check is (status, title, detail), status being "ok",
"fail", "warn" (works, but something optional is missing) or "skip"
(couldn't be checked because an earlier step failed).
"""
import os
import platform
import struct
import sys

from . import resolve_client as rc

MIN_PYTHON = (3, 9)


def _python():
    v = sys.version_info
    bits = struct.calcsize("P") * 8
    text = f"Python {v.major}.{v.minor}.{v.micro} ({bits}-bit)"
    if (v.major, v.minor) < MIN_PYTHON:
        return "fail", text, (f"Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]} or newer is needed. Install a newer "
                              "Python from python.org, then run the installer again.")
    if bits != 64:
        return "fail", text, ("DaVinci Resolve only works with 64-bit Python. Install the 64-bit Python "
                              "from python.org, then run the installer again.")
    return "ok", text, ""


def _library():
    paths = rc._fusionscript_candidates() + rc._running_resolve_libs()
    found = next((p for p in paths if p and os.path.isfile(p)), None)
    if found:
        return "ok", "DaVinci Resolve's scripting library found", found
    return "fail", "DaVinci Resolve's scripting library not found", (
        "Is DaVinci Resolve Studio installed? Looked in:\n  " + "\n  ".join(p for p in paths if p) +
        "\nIf it's installed somewhere else, set the RESOLVE_SCRIPT_LIB environment variable to the "
        "full path of fusionscript.")


def _load():
    try:
        return rc._load_fusionscript(), None
    except SystemExit as e:
        return None, str(e)
    except Exception as e:
        return None, str(e)


def _shortcuts():
    try:
        from . import resolve_shortcuts as rs
        folder = rs.clipse_scripts_folder()
        names = rs._existing_launchers(folder) if os.path.isdir(folder) else []
    except Exception as e:
        return "warn", "Couldn't check the shortcuts inside Resolve", str(e)
    if names:
        return "ok", f"{len(names)} shortcuts installed in Resolve", folder
    return "fail", "The shortcuts aren't installed in Resolve", (
        "Run the installer again, or: clipse --install-resolve-shortcuts")


def _preview():
    missing = []
    for module, what in (("miniaudio", "listening to sounds"), ("av", "the preview window")):
        try:
            __import__(module)
        except Exception:
            missing.append((module, what))
    if not missing:
        return "ok", "Previewing sounds and clips available", ""
    return "warn", "Previewing isn't fully available", (
        "Missing: " + ", ".join(f"{m} ({w})" for m, w in missing) +
        ". Everything else works. Running the installer again usually adds them.")


def run_checks():
    """Every check, in order. Stops asking Resolve once a step fails."""
    checks = [_python()]
    library = _library()
    checks.append(library)
    module, load_error = (None, None)
    if library[0] == "ok":
        module, load_error = _load()
        if module is None:
            checks.append(("fail", "Couldn't load the scripting library", load_error or ""))
    running = bool(rc._running_resolve_libs())
    checks.append(("ok", "DaVinci Resolve is running", "") if running else
                  ("fail", "DaVinci Resolve isn't running", "Open DaVinci Resolve, then check again."))
    resolve = None
    if module is not None and running:
        try:
            resolve = module.scriptapp("Resolve")
            if resolve is not None and resolve.GetProjectManager() is None:
                resolve = None
        except Exception:
            resolve = None
        if resolve is None:
            checks.append(("fail", "Resolve doesn't accept scripting connections", (
                "In Resolve: Preferences → System → General → \"External scripting using\": "
                "choose Local, then restart Resolve.\n"
                "This needs DaVinci Resolve Studio - the free version doesn't allow it.")))
        else:
            try:
                product = resolve.GetProductName() or "DaVinci Resolve"
                version = resolve.GetVersionString() or ""
            except Exception:
                product, version = "DaVinci Resolve", ""
            checks.append(("ok", f"Connected to {product} {version}".strip(), ""))
            try:
                project = resolve.GetProjectManager().GetCurrentProject()
            except Exception:
                project = None
            checks.append(("ok", f"Project open: {project.GetName()}", "") if project else
                          ("warn", "No project open", "Open a project to use the picker."))
    else:
        checks.append(("skip", "Scripting connection", "Fix the steps above first."))
    checks.append(_shortcuts())
    checks.append(_preview())
    return checks


def all_good(checks):
    return not any(status == "fail" for status, _t, _d in checks)


MARKS = {"ok": "✓", "fail": "✗", "warn": "!", "skip": "-"}


def report(checks):
    lines = [f"Clipse connection check ({platform.system()})", ""]
    for status, title, detail in checks:
        lines.append(f" {MARKS[status]}  {title}")
        if detail and status != "ok":
            lines += [f"      {line}" for line in detail.splitlines()]
    lines.append("")
    lines.append("Everything looks good." if all_good(checks) else "Fix the ✗ steps above, then check again.")
    return "\n".join(lines)
