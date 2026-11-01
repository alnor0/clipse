"""The keys given in Resolve's Keyboard Customization to the scripts in its Workspace > Scripts menu - read, never
written (Resolve doesn't let an app set its keys). Settings > Scripts shows them (2026-10-21, the owner: "Can i
somehow get the keybinds shown here").

Resolve keeps every key in configs/keyboard.preset.xml: <PresetListBA> is hex of a Qt data stream - each command's
name (uint32 byte length + UTF-16BE), then how many keys it has, and each key as its count of presses and the presses
(Qt's key | modifiers: 0x04000053 is Ctrl+S). A script in the menu is "workspace_sub1_menu<N>": its PLACE in the
menu, Resolve's Utility scripts sorted by name - not its name (found 2026-10-19): a loose script sorting before another
moves its key (a 123.lua took Open's Alt+S, 2026-10-21). A script in a folder there is in a submenu with places of its
own, "workspace_sub1_sub001_menu1" - so Clipse's are in one (resolve_shortcuts.MENU_FOLDER)."""
import os
import re
import sys

from .scripts_fusion import _resolve_support_dir, system_scripts_folders

SCRIPT_TYPES = (".py", ".lua")


def preset_files():
    """Where Resolve keeps its keys: Support/configs on Linux; on Windows Preferences beside Support
    (%APPDATA%\\Blackmagic Design\\DaVinci Resolve\\Preferences - there was no key shown there, 2026-10-22); on a Mac
    ~/Library/Preferences/Blackmagic Design/DaVinci Resolve (no key shown there either, the same day - it was looked
    for in Support/configs only)."""
    support = _resolve_support_dir()
    if os.name == "nt":
        return [os.path.join(os.path.dirname(support), "Preferences", "keyboard.preset.xml")]
    out = [os.path.join(support, "configs", "keyboard.preset.xml")]
    if sys.platform == "darwin":
        prefs = os.path.expanduser("~/Library/Preferences/Blackmagic Design/DaVinci Resolve")
        out += [os.path.join(prefs, "keyboard.preset.xml"), os.path.join(prefs, "configs", "keyboard.preset.xml")]
        for root in (prefs, support):  # (and anywhere a level or two inside either, should it be elsewhere)
            for folder, subs, files in os.walk(root):
                if folder[len(root):].count(os.sep) >= 2:
                    subs[:] = []
                subs[:] = [d for d in subs if d not in ("Fusion", "LUT", "Resolve Disk Database", "logs", ".cache")]
                if "keyboard.preset.xml" in files:
                    out.append(os.path.join(folder, "keyboard.preset.xml"))
    return list(dict.fromkeys(out))


def preset_file():
    """The newest of them there is (the first when there's none)."""
    found = [path for path in preset_files() if os.path.isfile(path)]
    return max(found, key=os.path.getmtime) if found else preset_files()[0]


def _blob():
    """The keys' data in Resolve's file - b"" when it can't be read."""
    try:
        with open(preset_file(), encoding="utf-8", errors="ignore") as f:
            text = f.read()
        return bytes.fromhex(re.search(r"<PresetListBA>([0-9a-fA-F]+)</PresetListBA>", text).group(1))
    except (OSError, AttributeError, ValueError):
        return b""


def _keys_at(blob, name):
    enc = name.encode("utf-16-be")
    i = blob.find(len(enc).to_bytes(4, "big") + enc)
    if i < 0:
        return []
    j = i + 4 + len(enc)
    count = int.from_bytes(blob[j:j + 4], "big")
    if count > 8:  # (not a key list: something else of the same name)
        return []
    j += 4
    keys = []
    for _ in range(count):
        presses = int.from_bytes(blob[j:j + 4], "big")
        j += 4
        if presses > 4:
            return keys
        keys.append([int.from_bytes(blob[j + 4 * m:j + 4 * m + 4], "big") for m in range(presses)])
        j += 4 * presses
    return keys


def _utility_folders():
    from .resolve_shortcuts import utility_scripts_folder
    return [utility_scripts_folder()] + [os.path.join(base, "Utility") for base in system_scripts_folders()]


def _sorted(names):
    return sorted(names, key=lambda n: (n.lower(), n))


def _scripts_in(folder):
    try:
        return {os.path.splitext(entry)[0] for entry in os.listdir(folder)
                if os.path.splitext(entry)[1].lower() in SCRIPT_TYPES and os.path.isfile(os.path.join(folder, entry))}
    except OSError:
        return set()


def menu_order():
    """The loose scripts at the top of Resolve's Scripts menu, in its order: every Utility folder's (yours,
    everyone's on the computer, Reactor's), by name - "123" before "Clipse 01 - ..." ("-" before digits)."""
    names = set()
    for folder in _utility_folders():
        names |= _scripts_in(folder)
    return _sorted(names)


def submenus():
    """[(the folder's name, [its scripts in order])] - the Utility folders' folders, each a submenu, by name."""
    inside = {}
    for folder in _utility_folders():
        try:
            entries = os.listdir(folder)
        except OSError:
            continue
        for entry in entries:
            path = os.path.join(folder, entry)
            if os.path.isdir(path):
                inside.setdefault(entry, set()).update(_scripts_in(path))
    return [(name, _sorted(inside[name])) for name in _sorted(inside)]


def script_keys():
    """{a script's name in the menu ("Clipse 03 - Grab Frame"): its keys, as the app writes them ("Alt+G")} - the
    loose ones by their place ("workspace_sub1_menu4"), the ones in a submenu by its place and theirs in it
    ("workspace_sub1_sub001_menu3": Clipse's, in their folder)."""
    from PySide6.QtGui import QKeySequence
    from .keycaps import key_name
    blob = _blob()
    if not blob:
        return {}
    folders = submenus()
    # the menu's entries are the folders and the loose scripts together, by name - a folder (a submenu) takes a
    # place too: with "!Clipse" there, a loose 123sadas was place 2 (seen 2026-10-21)
    entries = _sorted([name for name, _s in folders] + menu_order())
    loose = set(menu_order())
    places = [(f"workspace_sub1_menu{place}", name) for place, name in enumerate(entries, start=1) if name in loose]
    for sub, (_folder, names) in enumerate(folders, start=1):
        places += [(f"workspace_sub1_sub{sub:03d}_menu{place}", name) for place, name in enumerate(names, start=1)]
    out = {}
    for where, name in places:
        keys = _keys_at(blob, where)
        if keys:
            out[name] = [key_name(QKeySequence(*presses).toString(QKeySequence.PortableText)) for presses in keys]
    return out
