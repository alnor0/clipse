"""The login helper: waits quietly for DaVinci Resolve, and starts the
background service the moment Resolve opens - so the picker is already
warm (and the open project's Media Pool already read) by the time the
first shortcut is pressed.

Started at login when Settings -> General -> "Start in the background" is
on (see autostart.py). Plain standard library on purpose: until Resolve
opens it is one small process that looks for Resolve every few seconds
and does nothing else - no Qt, no connection to Resolve.

If the service stops while Resolve is still open (Stop Service, or it
couldn't connect) it is left stopped until Resolve is opened again; a
shortcut press still starts it as before.

Run:  clipse --watch      (normally started for you)
"""
import os
import socket
import sys

HOST = "127.0.0.1"
PORT = 51824          # held while running: one watcher per user, and how --shutdown reaches it
CHECK_SECONDS = 4     # how often to look for Resolve
CONNECT_PATIENCE = 240  # Resolve can take minutes to open a big project


def resolve_running():
    """Is DaVinci Resolve open? Cheap enough to ask every few seconds."""
    try:
        if sys.platform == "darwin":
            import subprocess
            out = subprocess.run(["ps", "-axo", "comm"], capture_output=True, text=True, timeout=5).stdout
            return any(line.endswith("/Contents/MacOS/Resolve") for line in out.splitlines())
        if os.name == "nt":
            found = _windows_process_running("resolve.exe")
            if found is not None:
                return found
            import subprocess
            out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq Resolve.exe", "/NH", "/FO", "CSV"],
                                 capture_output=True, text=True, timeout=5,
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
            return '"resolve.exe"' in out.lower()
        # (by the program it runs: once it's up, Resolve's process calls itself "GUI Thread" - by its name it was
        #  only found while it was starting, 2026-10-19)
        for pid in os.listdir("/proc"):
            if pid.isdigit():
                try:
                    if os.path.basename(os.readlink(f"/proc/{pid}/exe")) == "resolve":
                        return True
                except OSError:
                    try:
                        with open(f"/proc/{pid}/comm") as f:
                            if f.read().strip() == "resolve":
                                return True
                    except OSError:
                        pass
    except Exception:
        pass
    return False


def _windows_process_running(exe_name):
    """Windows: the process list straight from the system (no tasklist
    process every few seconds). None if that isn't available."""
    try:
        import ctypes
        from ctypes import wintypes

        class PROCESSENTRY32W(ctypes.Structure):
            _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
                        ("th32ProcessID", wintypes.DWORD), ("th32DefaultHeapID", ctypes.c_size_t),
                        ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                        ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", ctypes.c_long),
                        ("dwFlags", wintypes.DWORD), ("szExeFile", wintypes.WCHAR * 260)]

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
        kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
        for fn in (kernel32.Process32FirstW, kernel32.Process32NextW):
            fn.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
            fn.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        snapshot = kernel32.CreateToolhelp32Snapshot(0x00000002, 0)  # TH32CS_SNAPPROCESS
        if not snapshot or snapshot == wintypes.HANDLE(-1).value:
            return None
        try:
            entry = PROCESSENTRY32W()
            entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
            more = kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
            while more:
                if entry.szExeFile.lower() == exe_name:
                    return True
                more = kernel32.Process32NextW(snapshot, ctypes.byref(entry))
            return False
        finally:
            kernel32.CloseHandle(snapshot)
    except Exception:
        return None


def _claim():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    if os.name == "nt":
        srv.setsockopt(socket.SOL_SOCKET, getattr(socket, "SO_EXCLUSIVEADDRUSE", socket.SO_REUSEADDR), 1)
    else:
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        srv.bind((HOST, PORT))
    except OSError:
        srv.close()
        return None
    srv.listen(4)
    return srv


def running():
    try:
        socket.create_connection((HOST, PORT), timeout=0.5).close()
        return True
    except OSError:
        return False


def quit_running():
    """Asks a running watcher to exit (installers do this before replacing
    the files it runs from). True if one was running."""
    try:
        s = socket.create_connection((HOST, PORT), timeout=1.0)
        s.sendall(b"QUIT")
        s.close()
        return True
    except OSError:
        return False


def _wait(srv, seconds):
    """Sleeps, but wakes up for a QUIT. Returns False when asked to quit."""
    srv.settimeout(seconds)
    try:
        conn, _ = srv.accept()
    except socket.timeout:
        return True
    except OSError:
        return False
    try:
        conn.settimeout(1.0)
        data = conn.recv(16).strip()
    except OSError:
        data = b""
    finally:
        conn.close()
    return data != b"QUIT"


def main():
    from . import paths
    paths.move_old()
    srv = _claim()
    if srv is None:
        return  # already watching
    from .client import probe, _launch_daemon
    print("Waiting for DaVinci Resolve...", flush=True)
    started_for_this_session = False
    while True:
        if resolve_running():
            if not started_for_this_session:
                started_for_this_session = True
                try:  # Clipse's scripts back in Resolve's menu before it lists them: one gone moves the keys after it
                    from .resolve_shortcuts import put_back_missing
                    put_back_missing()
                except Exception as e:
                    print(f"Couldn't check the scripts in Resolve's menu: {e}", flush=True)
                if probe() is None:
                    print("DaVinci Resolve opened - starting the service.", flush=True)
                    _launch_daemon(["--give-up-after", str(CONNECT_PATIENCE), "--background"])
        else:
            started_for_this_session = False
        if not _wait(srv, CHECK_SECONDS):
            break
    srv.close()


if __name__ == "__main__":
    main()
