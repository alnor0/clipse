import pathlib, re, textwrap

OUT = pathlib.Path(__file__).resolve().parents[1] / "build" / "clipse"
RULE = "-" * 72


def b(s):
    return textwrap.dedent(s).strip("\n")


def sec(title, body):
    return f"{RULE}\n{title}\n{RULE}\n\n{b(body)}\n"


def readme(os_name, install_file, uninstall_file, opt, install_note, data_dir, terminal, python_hint,
           extra_sections="", ctrl_note="", needs="", autostart_note="", settings_dir="", log_dir=""):
    keys = [
        ("Open", f"{opt}+S"),
        ("Adjustment Clip Over Clip", f"{opt}+A"),
        ("Adjustment Clip Over Footage", f"{opt}+Shift+A"),
        ("Adjustment Clip at Playhead", f"{opt}+Ctrl+A"),
        ("Fusion Composition Over Clip", f"{opt}+F"),
        ("Next Use of Clip", f"{opt}+C"),
        ("Previous Use of Clip", f"{opt}+Z"),
        ("Tidy Fusion Nodes", f"{opt}+T"),
        ("Pull Out Fusion Node", f"{opt}+D"),
        ("Grab Frame", f"{opt}+G"),
        ("Undo Last Action", f"{opt}+U"),
    ]
    # multi-line values keep the template's indentation (it's dedented afterwards)
    install_note = install_note.replace("\n", "\n" + " " * 11)
    python_hint = python_hint.replace("\n", "\n" + " " * 10)
    needs = needs.replace("\n", "\n" + " " * 8)
    sep = "\\" if os_name == "Windows" else "/"
    data_dir_log = f"{log_dir}{sep}service.log"  # (each system's own places - clipse/paths.py)
    table = "\n".join(f"  {n.ljust(36)}{k}" for n, k in keys)

    parts = [
        b(f"""
        Clipse for DaVinci Resolve  ({os_name})
        Search everything in Resolve and put it on the timeline from the keyboard.
        """) + "\n",

        sec("GET STARTED", f"""
        Needs DaVinci Resolve Studio{needs}.

        1. In Resolve: Preferences -> System -> General ->
           "External scripting using" -> Local.
        2. Double-click  {install_file}
           {install_note}
        3. Restart Resolve, open Keyboard Customization, search
           "Clipse" and give the scripts a key.

        Suggested keys:
        """) + "\n" + table + "\n\n" + b(f"""
        ({opt}+S takes over Resolve's own {opt}+S, Add Serial Node on the Color
        page. If you grade a lot, pick another key for Open.)
        """) + "\n",

        sec("USING IT", f"""
        Type part of a name and press Enter: the clip goes in at the
        playhead, on the first free track. Typos are fine.

          Tab           stage a clip, so several go in at once
          Ctrl+Tab      stage it once more
          :             choose what to search (Videos, Scripts, Markers ...)
          Ctrl+I        Insert as: back to back, at every marker or cut,
                        with gaps, where pictures sit in the frame
          Ctrl+K        Actions
          Ctrl+H        History, to insert the same thing again
          Alt+Enter     insert as one compound clip
          Ctrl+Shift+P  the preview; Ctrl+Space plays it
          Alt+I / Alt+O mark in and out - only that part goes in
          Ctrl+L        sounds that sound like this one
          Alt+T         a sound's tags, while it plays
          Alt+1, 2, 3   a sound's energy
          Ctrl+,        Settings

        Every key of the picker is on Settings -> Keybindings. The scripts
        in Resolve's menu (Workspace -> Scripts -> !Clipse) are keyed in Resolve's
        Keyboard Customization - search "Clipse". What they do is set on
        Settings -> Scripts.

        Clipse starts with Resolve and stops when Resolve closes.
        """) + (f"\n{autostart_note}\n" if autostart_note else "") + (f"\n{ctrl_note}\n" if ctrl_note else ""),
        extra_sections,

        sec("IF SOMETHING DOESN'T WORK", f"""
        - Check "External scripting using" is set to Local, then restart
          Resolve.
        - The scripts aren't in Resolve's menu: restart Resolve once.
        - Settings -> About -> Send feedback sends what happened, with the
          logs. Or write to support@alnor.store.
        - The log: {data_dir_log}
        """),

        sec("UPDATE / UNINSTALL", f"""
        Update: Settings -> About -> Update (a dot on the gear in the picker
        means a new version is out). Your settings are kept (in {settings_dir}).

        The app goes in its own folder ("app" in {data_dir})
        and uses your Python - nothing else on your computer is changed.

        Uninstall: double-click {uninstall_file}.
        """),
    ]
    return "\n".join(p for p in parts if p)


LINUX_EXTRA = sec("OPTIONAL: WINDOW MANAGER KEYS (LINUX)", """
Sway, i3 and Hyprland don't start autostart files - add this so the
helper starts when you log in (the first open is instant):

  exec clipse --watch

Tiling WM users can bind the same actions there instead, e.g. Sway:

  bindsym Mod1+s exec clipse
  bindsym Mod1+a exec clipse adjust match
  bindsym Mod1+c exec clipse jump next
  for_window [app_id="clipse"] floating enable

The preview can be its own window (Settings -> Preview -> Preview window).
Wayland lets the window manager decide where it goes, e.g. Sway:

  for_window [title="Clipse preview"] move position 2600 100

Other commands: --refresh, adjust match-skip-adj, adjust fixed,
jump previous, undo last, grab frame, fusion pullout.
""")

files = {
    "README_Linux.txt": readme(
        "Linux", "install.sh", "uninstall.sh", "Alt",
        '(or run  bash install.sh  in a terminal)', "~/.clipse", "a terminal",
        "Install python3 with your package manager.", LINUX_EXTRA,
        settings_dir="~/.config/clipse", log_dir="~/.local/state/clipse"),
    "README_macOS.txt": readme(
        "macOS", "Install.command", "Uninstall.command", "Option",
        "(if macOS blocks it: System Settings -> Privacy & Security,\n"
        "scroll down and click Open Anyway, then Open)", "~/.clipse", "Terminal",
        "Install Python from python.org (Resolve doesn't\nfind Homebrew's Python), then restart Resolve.",
        ctrl_note="All the keys can be changed in Settings -> Keybindings.",
        autostart_note="macOS says \"Background Items Added\" once - that's the helper.\n"
                       "Media on an external drive: macOS may ask once whether\n"
                       "Python may read it - click Allow (previews need it).",
        settings_dir="~/Library/Application Support/Clipse", log_dir="~/Library/Logs/Clipse",
        needs=", from blackmagicdesign.com\n(the Mac App Store version may not allow scripting)"),
    "README_Windows.txt": readme(
        "Windows", "Install.bat", "Uninstall.bat", "Alt",
        '(if Windows warns: "More info" -> "Run anyway")',
        "%USERPROFILE%\\.clipse", "PowerShell",
        "Install the 64-bit Python from python.org, then\nrestart Resolve.",
        settings_dir="%APPDATA%\\Clipse", log_dir="%LOCALAPPDATA%\\Clipse\\Logs"),
}

for name, text in files.items():
    text = re.sub(r"\n{3,}", "\n\n", text).rstrip() + "\n"
    if "macOS" in name:
        text = text.replace("Ctrl+Space    play/pause", "Option+Space  play/pause").replace(
            "Alt+Shift+Left/Right", "Option+Shift+Left/Right").replace("Alt+Enter     insert", "Option+Enter  insert").replace(
            "Alt+I / Alt+O mark", "Option+I / O  mark").replace(
            "Alt+M / Alt+C the", "Option+M / C  the").replace(
            "Alt+L         mark", "Option+L      mark").replace(
            "Alt+V / Alt+A just", "Option+V / A  just").replace(
            "Alt+F         big", "Option+F      big").replace(
            "Alt+Shift+Up/Down ", "Option+Shift+Up/Down")
        # in the picker Ctrl is the Command key on a Mac
        text = re.sub(r"(?m)^  Ctrl\+(\S+)( *)", lambda m: f"  Cmd+{m.group(1)}{m.group(2)} ", text)
    data = text.replace("\n", "\r\n") if "Windows" in name else text
    (OUT / name).write_bytes(data.encode("utf-8"))
    lines = text.splitlines()
    print(f"{name}: {len(lines)} lines, widest {max(len(l) for l in lines)}")
