"""Shared setup for the tests: a throwaway HOME, Qt without a screen, the fake Resolve."""
import os
import pathlib
import sys
import tempfile
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
os.environ["HOME"] = os.environ["USERPROFILE"] = tempfile.mkdtemp()  # (Windows' ~ is USERPROFILE: without it the
# tests wrote over the real settings and history - 2026-10-22)
for _name in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME", "APPDATA", "LOCALAPPDATA"):
    os.environ.pop(_name, None)  # (set, they'd lead the app's files out of the throwaway HOME - clipse/paths.py)
if os.name == "nt":  # (Windows' own places, inside the throwaway home - Resolve's Scripts folder is under APPDATA)
    os.environ["APPDATA"] = os.path.join(os.environ["HOME"], "AppData", "Roaming")
    os.environ["LOCALAPPDATA"] = os.path.join(os.environ["HOME"], "AppData", "Local")
    import contextlib
    import winreg  # the login start is in the registry: kept here instead (a test once pointed the real one at itself)
    _keys, _real = {}, (winreg.OpenKey, winreg.QueryValueEx)  # (only the user's part: the machine's id is read)

    @contextlib.contextmanager
    def _fake_key(path):
        yield _keys.setdefault(path, {})

    def _key(root, path, *args):
        return _fake_key(path) if root == winreg.HKEY_CURRENT_USER else _real[0](root, path, *args)

    def _query(key, name):
        if not isinstance(key, dict):
            return _real[1](key, name)
        if name not in key:
            raise FileNotFoundError(name)
        return key[name], winreg.REG_SZ

    def _delete(key, name):
        if name not in key:
            raise FileNotFoundError(name)
        del key[name]

    winreg.OpenKey = _key
    winreg.CreateKey = lambda root, path: _key(root, path)
    winreg.SetValueEx = lambda key, name, _r, _t, value: key.__setitem__(name, value)
    winreg.QueryValueEx, winreg.DeleteValue = _query, _delete
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("FAKE_CLIPS", "5")
os.environ.setdefault("FAKE_DELAY", "0")
sys.path[:0] = [str(ROOT / "tests" / "fake_resolve"), str(ROOT)]

from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([])


def pump(seconds):
    """Lets Qt run for a moment (timers, slices of the Media Pool scan ...)."""
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.processEvents()


def picker():
    """A picker connected to the fake Resolve, opened once."""
    from clipse.settings import Settings
    from clipse.picker_window import PickerWindow
    import DaVinciResolveScript as fake
    settings = Settings()
    settings.load()
    settings.general["tour_done"] = True
    settings.general["check_for_updates"] = False  # tests stay off the network
    settings.listen["trim_silence"] = False
    window = PickerWindow(settings, {})
    window.set_resolve(fake.scriptapp("Resolve"))
    window.open_picker()
    pump(0.4)
    return window, settings, fake
