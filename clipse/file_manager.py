"""Shows files and folders in the system's file manager (with the files
selected where the file manager supports it): Explorer on Windows,
Finder on macOS. On Linux, in this order:
  1. the command set in Settings -> General -> File manager, if any
  2. the standard "show these items" request that GUI file managers
     answer (Dolphin, Nautilus, Nemo, Thunar, ...)
  3. a GUI file manager found on the system
  4. xdg-open (whatever the system opens folders with - on some setups
     that's a terminal, which is why 1-3 come first)
"""
import os
import platform
import shlex
import shutil
import subprocess
from urllib.parse import quote

# Linux GUI file managers: (program, arguments that select a file, or None to just open its folder)
_KNOWN = [("dolphin", ["--select"]), ("nautilus", []), ("nemo", []), ("caja", ["--select"]),
          ("thunar", None), ("pcmanfm-qt", None), ("pcmanfm", None), ("spacefm", None),
          ("doublecmd", None), ("krusader", None)]


def _spawn(command):
    kwargs = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    if os.name == "nt":
        kwargs["creationflags"] = 0x08000000  # no console window
    else:
        kwargs["start_new_session"] = True
    return subprocess.Popen(command, **kwargs)


def _custom(command, folder, file=None):
    """Runs the user's file manager command. {folder} / {file} are filled
    in; with neither, the folder goes at the end."""
    parts = shlex.split(command)
    if not parts:
        return False
    if any("{folder}" in p or "{file}" in p for p in parts):
        parts = [p.replace("{folder}", folder).replace("{file}", file or folder) for p in parts]
    else:
        parts.append(folder)
    _spawn(parts)
    return True


def _dbus(method, uris):
    """org.freedesktop.FileManager1 ShowItems / ShowFolders. True if a file manager answered."""
    if shutil.which("gdbus"):
        array = "[" + ", ".join(f"'{u}'" for u in uris) + "]"
        result = subprocess.run(
            ["gdbus", "call", "--session", "--dest", "org.freedesktop.FileManager1",
             "--object-path", "/org/freedesktop/FileManager1",
             "--method", f"org.freedesktop.FileManager1.{method}", array, ""],
            stdin=subprocess.DEVNULL, capture_output=True, timeout=4)
        return result.returncode == 0
    if shutil.which("dbus-send"):
        result = subprocess.run(
            ["dbus-send", "--session", "--print-reply", "--dest=org.freedesktop.FileManager1",
             "/org/freedesktop/FileManager1", f"org.freedesktop.FileManager1.{method}",
             "array:string:" + ",".join(uris), "string:"],
            stdin=subprocess.DEVNULL, capture_output=True, timeout=4)
        return result.returncode == 0
    return False


def _known(folder, file=None):
    for program, select in _KNOWN:
        if shutil.which(program):
            if file and select is not None:
                _spawn([program] + select + [file])
            else:
                _spawn([program, folder])
            return True
    return False


def _uri(path):
    return "file://" + quote(path)


def open_folder(path, command=""):
    """Opens a folder in the file manager. Returns None or a message."""
    if not path or not os.path.isdir(path):
        return "The folder wasn't found."
    path = os.path.abspath(path)
    try:
        if command and _custom(command, path):
            return None
        system = platform.system()
        if system == "Windows":
            os.startfile(path)  # Windows only
        elif system == "Darwin":
            _spawn(["open", path])
        elif not (_dbus("ShowFolders", [_uri(path)]) or _known(path)):
            _spawn(["xdg-open", path])
        return None
    except Exception as e:
        return f"Couldn't open the folder: {e}"


def reveal(path, command=""):
    """One file (or folder), selected in its folder. Returns None or a message."""
    if not path or not os.path.exists(path):
        return "The file wasn't found on disk."
    path = os.path.abspath(path)
    folder = os.path.dirname(path)
    try:
        if command and _custom(command, folder, path):
            return None
        system = platform.system()
        if system == "Windows":
            _spawn(["explorer", "/select,", os.path.normpath(path)])
        elif system == "Darwin":
            _spawn(["open", "-R", path])
        elif not (_dbus("ShowItems", [_uri(path)]) or _known(folder, path)):
            _spawn(["xdg-open", folder])
        return None
    except Exception as e:
        return f"Couldn't open the file manager: {e}"


def _windows_select_many(folder, paths):
    """Explorer: one window for `folder` with all of `paths` selected."""
    import ctypes
    from ctypes import wintypes
    shell32, ole32 = ctypes.windll.shell32, ctypes.windll.ole32
    shell32.ILCreateFromPathW.restype = ctypes.c_void_p
    shell32.ILCreateFromPathW.argtypes = [wintypes.LPCWSTR]
    shell32.SHOpenFolderAndSelectItems.argtypes = [ctypes.c_void_p, wintypes.UINT,
                                                   ctypes.POINTER(ctypes.c_void_p), wintypes.DWORD]
    shell32.ILFree.argtypes = [ctypes.c_void_p]
    ole32.CoInitialize(None)
    parent = shell32.ILCreateFromPathW(folder)
    items = [shell32.ILCreateFromPathW(os.path.normpath(p)) for p in paths]
    items = [i for i in items if i]
    try:
        array = (ctypes.c_void_p * len(items))(*items)
        result = shell32.SHOpenFolderAndSelectItems(parent, len(items), array, 0)
        if result != 0:
            raise OSError(f"SHOpenFolderAndSelectItems returned {result}")
    finally:
        for i in items + [parent]:
            if i:
                shell32.ILFree(i)


def reveal_many(paths, max_windows=8, command=""):
    """Several files: one file manager window per folder (at most
    max_windows), with that folder's files selected. Returns None or a message."""
    paths = [os.path.abspath(p) for p in dict.fromkeys(paths) if p and os.path.exists(p)]
    if not paths:
        return "None of the files were found on disk."
    if len(paths) == 1:
        return reveal(paths[0], command)
    by_folder = {}
    for p in paths:
        by_folder.setdefault(os.path.dirname(p), []).append(p)
    max_windows = max(1, int(max_windows))
    folders = list(by_folder.items())[:max_windows]
    system = platform.system()
    try:
        if command:
            for folder, files in folders:
                _custom(command, folder, files[0])
        elif system == "Windows":
            for folder, files in folders:
                try:
                    _windows_select_many(folder, files)
                except Exception:
                    _spawn(["explorer", "/select,", os.path.normpath(files[0])])
        elif system == "Darwin":
            _spawn(["open", "-R"] + [files[0] for _f, files in folders])
        elif not _dbus("ShowItems", [_uri(p) for _f, files in folders for p in files]):
            for folder, files in folders:
                reveal(files[0])
    except Exception as e:
        return f"Couldn't open the file manager: {e}"
    if len(by_folder) > max_windows:
        return f"Showed the first {max_windows} of {len(by_folder)} folders (Settings -> Folders -> File manager)."
    return None
