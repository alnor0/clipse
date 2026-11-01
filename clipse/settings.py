"""All user-configurable state, plus the schemas that drive the Settings
dialog. Pure Python/JSON — no Qt import here, so it stays testable and
reusable if the UI layer ever changes again."""
import json
import os
import sys

from . import paths
from . import scripts_fusion

SETTINGS_FILE = paths.SETTINGS_FILE
# The settings file's layout. Raised when a change needs more than "an unknown name is left out, a missing one is
# the default" (apply): then apply() looks at saved["format"] and moves the old values over.
FORMAT = 1

AUDIO_EXTENSIONS = (".wav", ".mp3", ".aac", ".flac", ".ogg", ".m4a", ".wma", ".aiff")
STILL_IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".gif",
                           ".exr", ".dpx", ".psd", ".tga", ".webp")

DEFAULT_DURATION_FRAMES = 100

# ---------------------------------------------------------------
# Folders — where to look for scripts, Fusion macros, and Fusion
# compositions. Fully user-configurable: script/macro folders default to
# Resolve's own standard locations, but Fusion compositions have no
# standard location at all, so that list starts empty.
# ---------------------------------------------------------------
FOLDER_DEFAULTS = {
    # all of Resolve's Scripts folder (Utility, Edit, Comp, ...) - Clipse's own shortcuts are skipped
    "scripts": [os.path.dirname(scripts_fusion.default_scripts_folder())],
    "macros": [scripts_fusion.default_macros_folder()],
    "fusion_comps": [],
}

# ---------------------------------------------------------------
# Page defaults — which sources show up with NO search prefix, and it
# depends on which Resolve page you're on. Colon prefixes (a:, run:,
# etc) always override this and search that specific source regardless
# of page — this only controls the plain/unprefixed view.
# ---------------------------------------------------------------
PAGE_DEFAULTS_DEFAULT = {
    # (the show_* here: which kinds of Media Pool row the Fusion page lists - the Edit page's are in "general")
    "fusion": {"clips": False, "scripts": True, "macros": True, "comps": True, "nodes": True, "expressions": True,
               "shortcuts": True,
               "show_video": True, "show_images": True, "show_compound_clips": True, "show_bins": True,
               "show_selected_clips_option": True},
    "other": {"clips": True, "scripts": False, "macros": False, "comps": False, "nodes": False, "expressions": False,
              "shortcuts": True},
}
# the same, as tiles in Settings: (key, what the tile says, its symbol)
SOURCE_TILES = [("clips", "Media Pool", "video"), ("scripts", "Scripts", "script"), ("macros", "Macros", "macro"),
                ("comps", "Compositions", "comp"), ("nodes", "Nodes", "node"), ("expressions", "Expressions", "expression"),
                ("shortcuts", "Shortcuts", "shortcut")]

# ---------------------------------------------------------------
# General (bool toggles) — {key: (label, section, track)}
# ---------------------------------------------------------------
# What the picker's list shows - tiles at the top of Settings -> General
# (key, label, the clip-type symbol it shows)
# Kinds of Media Pool row a Fusion composition has no use for: the Fusion page leaves them out
# (while Enter adds to the composition there), and Settings draws them as "only on the Edit page".
FUSION_SKIPS = ("show_audio", "show_adjustment_clips")
FUSION_SKIPPED_CATEGORIES = ("audio", "adjustment")
# a kind's switch -> what its rows are called
KIND_CATEGORY = {"show_video": "video", "show_audio": "audio", "show_images": "image",
                 "show_adjustment_clips": "adjustment", "show_compound_clips": "compound", "show_bins": "bin",
                 "show_selected_clips_option": "selected"}

LIST_TILES = [
    ("show_video", "Videos", "video"),
    ("show_audio", "Sounds & music", "sound"),
    ("show_images", "Stills", "image"),
    ("show_adjustment_clips", "Adjustment clips", "adjustment"),
    ("show_compound_clips", "Compound clips", "compound"),
    ("show_bins", "Bins", "bin"),
    ("show_selected_clips_option", "Selected Clips", "selected"),
]

GENERAL_SCHEMA = [
    ("List", [
        ("search_metadata", "Search keywords, comments and clip colours", None),
        ("right_align_folder_names", "Bin name at the right edge", None),
        ("show_clip_color", "Show clip colours", None),
        ("bin_insert_recursive", "Include sub-bins", None),
    ]),
    ("Inserting", [
        ("reveal_in_media_pool", "Show inserted clips in the Media Pool", None),
        ("also_insert_highlighted_on_enter", "Insert the highlighted row with staged clips", None),
        ("keep_staged", "Keep staged clips when the picker closes", None),
    ]),
    ("Window", [
        ("close_on_click_outside", "Close the picker when you click outside it", None),
        ("float_only_over_resolve", "Stay above Resolve only", None),
        ("focus_on_hover", "Type where the mouse is", None),
        ("remember_position", "Open where it was last moved", None),
        ("esc_clears_search_first", "Esc clears the search first", None),
        ("esc_closes_everything", "Esc closes the preview too", None),
    ]),
    ("Start-up", [
        ("start_in_background", "Start when you log in", None),
    ]),
]
# What were settings and are fixed now (went through Settings, 2026-10-17: "you have good points") - each
# the way everyone wants it, or fine-tuning that Raycast and Vicinae don't offer either
FIXED = {
    "general": {"sort_by_insert_frequency": True, "learn_picks": True, "actions_in_search": True,
                "show_folder_names": True, "sort_projects_by_created": False, "link_video_audio_on_insert": True,
                "fusion_enter_adds_clips": True, "stop_with_resolve": True},
    "listen": {"show_used_parts": True, "expression_preview": True, "remember_place": True, "split_music": True,
               "show_beat_grid": True},
    "timeline_tools": {"remove_empty_tracks": True, "expression_sliders": True},
    "display": {"icon_size_offset": 0, "row_spacing": 9, "outer_padding": 16, "outer_outline_width": 1,
                "corner_radius": 4, "project_age_medium_days": 7, "project_age_old_days": 30},
    "files": {"max_windows": 8},
}

GENERAL_DEFAULTS = {
    "show_audio": True, "show_video": True, "show_adjustment_clips": True, "show_compound_clips": True,
    "show_bins": True, "bin_insert_recursive": True, "show_selected_clips_option": True,
    "sort_by_insert_frequency": True, "reveal_in_media_pool": False,
    "also_insert_highlighted_on_enter": True, "sort_projects_by_created": False,
    "preview_auto_play": False, "show_images": True,
    "show_folder_names": True, "right_align_folder_names": False,
    "link_video_audio_on_insert": True,
    "stop_with_resolve": True,
    "tour_done": False,           # the first-run tour (tour.py) has been shown
    "app_set_up": False,          # the app has been opened by hand once (client.open_app: login start set up then)
    "start_in_background": True,  # login helper (watcher.py) starts the service when Resolve opens
    "search_metadata": True,
    "result_order": "best",   # search results: "best" match first, most "used" first, or by "name"
    "empty_order": "used",    # with nothing typed: most "used" first, recently "added" to the Media Pool, or "recent"ly
                              # used (2026-10-20: "an option to sort by most recent when nothing is typed" - both)
    "learn_picks": True,      # best match: what you picked for the same text before goes first (picks.py)
    "keep_staged": False,
    "show_clip_color": True,
    "fusion_enter_adds_clips": True,
    "check_for_updates": True,
    "send_crash_reports": True,  # (the log of a run that crashed, at the next start - crash_report.py)
    "esc_clears_search_first": True,
    "esc_closes_everything": True,
    "close_on_click_outside": False,  # off: it stays open while you click around in Resolve
    "focus_on_hover": True,
    "actions_in_search": True,        # "grab" also lists the Grab frame action (below the best clips)           # mouse resting on one of our windows gives it the keyboard
    "float_only_over_resolve": True,  # picker/preview/Settings float over Resolve, not over other apps
    "remember_position": False,       # on: it opens where you last dragged it; off (how it ships, 2026-10-16):
                                      # in the middle of the screen every time
}

# ---------------------------------------------------------------
# Theme colors
# ---------------------------------------------------------------
ICON_COLOR_VARS = [
    "color_audio", "color_video", "color_adjustment", "color_compound", "color_bin", "color_selected",
    "color_image", "color_script", "color_macro", "color_comp", "color_node", "color_project",
    "staged_marker_color", "favorite_marker_color",
]
INTERFACE_COLOR_VARS = [
    "picker_bg", "picker_border", "picker_text", "picker_input_text",
    "picker_select_bg", "picker_folder", "picker_accent", "picker_bar_bg", "outer_outline_color",
]
THEME_COLOR_VARS = ICON_COLOR_VARS + INTERFACE_COLOR_VARS

# Clip colours that read on a light page (the dark themes' are too pale on white)
_LIGHT_CLIPS = {
    "color_audio": "#16a05d", "color_video": "#2f6fe4", "color_adjustment": "#8a4fe0",
    "color_compound": "#b98900", "color_bin": "#6b7280", "color_selected": "#b7860b",
    "color_image": "#3d5ce0", "color_script": "#0f9bb0", "color_macro": "#e0405a",
    "color_comp": "#5a67d8", "color_node": "#0f9f94", "color_project": "#4b5563",
    "staged_marker_color": "#16a05d", "favorite_marker_color": "#b98900",
}
# The themes: a few that people really pick (2026-10-14: "dont have some weird options that no one
# would realisticly pick") - One Dark (a twin of Default), Dracula, Solarized, Gruvbox, Monokai and One Light
# went; Gruvbox and Monokai had orange in them besides.
THEME_PRESETS = {
    "Default": {  # One Dark interface with vivid clip-type colours
        "picker_bg": "#282c34", "picker_border": "#3e4451", "picker_text": "#dfe3ea",
        "picker_input_text": "#e8ebf0", "picker_select_bg": "#4b5362", "picker_folder": "#8b929e",
        "picker_accent": "#61afef", "picker_bar_bg": "#23272d", "outer_outline_color": "#3e4451",
        "color_audio": "#3ee08f", "color_video": "#4f9dff", "color_adjustment": "#b67cff",
        "color_compound": "#ffcc33", "color_bin": "#9a9ea6", "color_selected": "#e5c07b",
        "color_image": "#6383ff", "color_script": "#4fd6e8", "color_macro": "#ff5f6d",
        "color_comp": "#8f9cff", "color_project": "#d6d9e0",
        "staged_marker_color": "#3ee08f", "favorite_marker_color": "#e5c07b",
    },
    "Graphite": {  # neutral grey, a little lifted (2026-10-14: #242529 - it was "a little too dark")
        "picker_bg": "#242529", "picker_border": "#323339", "picker_text": "#e6e7eb",
        "picker_input_text": "#e6e7eb", "picker_select_bg": "#303137", "picker_folder": "#7a7c86",
        "picker_accent": "#7fb4ff", "picker_bar_bg": "#1d1e21", "outer_outline_color": "#3b3c42",
        "color_audio": "#3ee08f", "color_video": "#4f9dff", "color_adjustment": "#b67cff",
        "color_compound": "#ffcc33", "color_bin": "#a7b0c2", "color_selected": "#e5c07b",
        "staged_marker_color": "#3ee08f",
    },
    "Midnight": {  # the darker grey Graphite was until 2026-10-14
        "picker_bg": "#1e1f23", "picker_border": "#2c2d33", "picker_text": "#e6e7eb",
        "picker_input_text": "#e6e7eb", "picker_select_bg": "#292a30", "picker_folder": "#71737d",
        "picker_accent": "#7fb4ff", "picker_bar_bg": "#18191c", "outer_outline_color": "#36373d",
        "color_audio": "#3ee08f", "color_video": "#4f9dff", "color_adjustment": "#b67cff",
        "color_compound": "#ffcc33", "color_bin": "#a7b0c2", "color_selected": "#e5c07b",
        "staged_marker_color": "#3ee08f",
    },
    "Nord": {
        "picker_bg": "#2e3440", "picker_border": "#4c566a", "picker_text": "#e5e9f0",
        "picker_input_text": "#eceff4", "picker_select_bg": "#434c5e", "picker_folder": "#81a1c1",
        "color_audio": "#a3be8c", "color_video": "#88c0d0", "color_adjustment": "#b48ead",
        "color_compound": "#ebcb8b", "color_bin": "#8fbcbb", "color_selected": "#e5c07b",
        "color_script": "#5e81ac", "color_macro": "#bf616a", "color_comp": "#81a1c1", "color_project": "#d8dee9",
        "staged_marker_color": "#a3be8c",
    },
    "Light": {  # light, not white (2026-10-14: "light mode doesn't have to be white mode")
        "picker_bg": "#e9ebee", "picker_border": "#cfd3d9", "picker_text": "#1f2328",
        "picker_input_text": "#14171b", "picker_select_bg": "#d9dce2", "picker_folder": "#646a74",
        "picker_accent": "#2f6fe4", "picker_bar_bg": "#e0e3e7", "outer_outline_color": "#c0c5cd",
        **_LIGHT_CLIPS,
    },
    "Soft light": {  # a little greyer still - easy on the eyes beside Resolve
        "picker_bg": "#dcdfe4", "picker_border": "#c3c8cf", "picker_text": "#1e2227",
        "picker_input_text": "#121519", "picker_select_bg": "#cdd1d8", "picker_folder": "#5f6670",
        "picker_accent": "#2d68d6", "picker_bar_bg": "#d2d6dc", "outer_outline_color": "#b4bac3",
        **_LIGHT_CLIPS,
    },
}
# Colours added in v1.6 — presets that don't set them get one derived from
# their own palette (accent = their video colour, bar = a darker background).
for _preset in THEME_PRESETS.values():
    _preset.setdefault("color_node", "#7fdbca")  # Fusion nodes (v1.12)
    _preset.setdefault("picker_accent", _preset["color_video"])
    _preset.setdefault("picker_bar_bg", None)  # filled in below, once blend_bar() exists
AGE_COLOR_VARS = ["age_recent_color", "age_medium_color", "age_old_color"]
AGE_COLOR_DEFAULTS = {
    "age_recent_color": "#4ade80",   # 0 to project_age_medium_days
    "age_medium_color": "#facc15",   # up to project_age_old_days
    "age_old_color": "#888888",      # beyond that
}
MARKER_COLOR_DEFAULTS = {"favorite_marker_color": "#facc15", "outer_outline_color": "#6b7280",
                          "color_image": "#008DEB"}


def is_light(hex_color):
    """A light page (a light theme)?"""
    h = str(hex_color).lstrip("#")
    try:
        return sum(int(h[i:i + 2], 16) for i in (0, 2, 4)) > 3 * 160
    except ValueError:
        return False


def _darker(hex_color, amount=0.22):
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return "#{:02x}{:02x}{:02x}".format(*(round(c * (1 - amount)) for c in (r, g, b)))


for _preset in THEME_PRESETS.values():
    if not _preset.get("picker_bar_bg"):
        _h = _preset["picker_bg"].lstrip("#")
        _light = sum(int(_h[i:i + 2], 16) for i in (0, 2, 4)) > 3 * 160
        _preset["picker_bar_bg"] = _darker(_preset["picker_bg"], 0.05 if _light else 0.22)

THEME_DEFAULTS = {**AGE_COLOR_DEFAULTS, **MARKER_COLOR_DEFAULTS, **dict(THEME_PRESETS["Default"])}

# The defaults before v1.6 (Nord colours, bigger sizes). A saved setting
# that still equals its old default was never changed by the user, so it
# moves to the new default on upgrade — see Settings.load().
OLD_THEME_DEFAULTS = {**{k: v for k, v in THEME_PRESETS["Nord"].items()
                         if k not in ("picker_accent", "picker_bar_bg")},
                      **AGE_COLOR_DEFAULTS, **MARKER_COLOR_DEFAULTS}
OLD_DISPLAY_DEFAULTS = {"font_size": 14, "outer_padding": 16, "row_spacing": 6, "icon_size_offset": 4,
                        "corner_radius": 8, "outer_corner_radius": 8, "window_width": 900,
                        "window_height": 500}
# Defaults shipped by v1.6.0/1.6.1 — saved values still equal to one of these
# move to the current default as well.
# v1.6.0-1.6.2 shipped the Graphite colours as the default interface colours
# (Moving those on was right while 1.6 settings were about - but the same colours were also the Graphite
# theme, so picking Graphite never lasted past a restart. It's only done for a file from before 1.7 now.)
V16_THEME_DEFAULTS = {k: THEME_PRESETS["Midnight"][k] for k in INTERFACE_COLOR_VARS}
# Graphite until 2026-10-14 (now Midnight): who had picked it gets the lighter Graphite
GRAPHITE_BEFORE = dict(V16_THEME_DEFAULTS)
# v1.7.0 had greyer text
V170_THEME_DEFAULTS = {"picker_text": "#abb2bf", "picker_input_text": "#abb2bf", "picker_folder": "#838a95",
                       "color_image": "#ff8a4c", "favorite_marker_color": "#f2c94c",
                       "color_bin": "#a7b0c2"}
# v1.8-1.10 had a darker image blue (hard to see on the highlighted row)
V18_THEME_DEFAULTS = {"color_image": "#3d63dd"}
# until 1.41 the Selected Clips row was pink; it's golden now (2026-10-13)
V141_THEME_DEFAULTS = {"color_selected": "#ff7eb6"}
V16_DISPLAY_DEFAULTS = {"font_size": (9,), "row_spacing": (5, 6), "window_width": (600, 900),
                        "window_height": (380, 500)}  # 900x500: the fixed size before "automatic" (v1.17)

ICON_DEFAULTS = {
    "audio": "\u266a", "video": "\u25b6", "adjustment": "\u2726", "compound": "\u29c9",
    "bin": "\U0001F5C0", "selected": "\u25c8", "image": "\u25a0",
    "script": "\u2699", "macro": "\u25a7", "comp": "\u25a6", "node": "\u25a3", "expression": "\u0192", "project": "\u2302",
    "folder": "\U0001F4C1", "timeline": "\u2261", "title": "T", "template": "\u25a6", "action": "\u21af", "shortcut": "\u2699", "staged_marker": "\u2713", "favorite_marker": "\u2605",
    "marker": "\u25bc", "layout": "\u25eb",
}
ICON_LABELS = {
    "audio": "Audio", "video": "Video", "adjustment": "Adjustment",
    "compound": "Compound", "bin": "Bin", "selected": "Selected Clips", "image": "Image",
    "script": "Script", "macro": "Macro", "comp": "Fusion Comp", "node": "Fusion Node", "expression": "Expression", "project": "Project",
    "folder": "Folder", "timeline": "Timeline", "title": "Title", "template": "Template", "action": "Action", "shortcut": "Shortcut", "staged_marker": "Staged Marker", "favorite_marker": "Favorite Marker",
    "marker": "Timeline Marker", "layout": "Resolve Layout",
}

# ---------------------------------------------------------------
# Display — font, scale, spacing, icon size, window size. All of this
# was baked-in constants in the Tk version (PICKER_FONT_FAMILY,
# UI_SCALE, OUTER_PADDING, ICON_FONT_SIZE_OFFSET, PICKER_WIDTH/HEIGHT,
# etc) — here it's live-editable via Settings -> Appearance.
# ---------------------------------------------------------------
DISPLAY_DEFAULTS = {
    "font_family": "",   # "" = use the system default font
    "font_size": 14,
    "ui_scale": 1.0,
    "outer_padding": 16,
    "row_spacing": 9,
    "icon_size_offset": 0,   # clip-type tag size = text height + this
    "corner_radius": 4,      # inner elements — selected row, inputs, buttons, tabs, group boxes
    "outer_corner_radius": 9,  # the window's own outer corner curve, independent of the above
    "outer_outline_width": 1,  # the window's thin edge outline
    "window_width": 0,    # 0 = automatic: sized to fit the screen (see PickerWindow.window_size)
    "window_height": 0,
    "preview_geometry": "",  # where the separate preview window was last (Qt saveGeometry, hex)
    "picker_pos": [],        # where you dragged the picker: [x, y] of its top-left ([] = centred)
    "settings_size": [],     # Settings window size, if you resized it
    "zoom": {},              # a window's own zoom when it isn't how it ships: {"picker": 1.25} (fonts.WINDOW_ZOOM)
    "action_shown": {},      # Actions panel: the way a shared tile shows ("Adjustment clip" -> its action's name)
    "actions_width": 0.0,    # Actions panel: dragged wider by its left edge (0 = its own 640, actions_panel.PANEL_W)
    "expressions_preview": True,  # Expressions: its own preview open or not (the preview key while it's open)
    "swap_everywhere": False,  # Swap clip: Everywhere chosen last time (else Here)
    "project_age_medium_days": 7,   # p: Created/Modified turns yellow after this many days
    "project_age_old_days": 30,     # ...and grey after this many days
}

# ---------------------------------------------------------------
# Keybinds — stored as Qt key-sequence strings (QKeySequence syntax),
# e.g. "Ctrl+Return", "Shift+Return". Editable live via Settings ->
# Keybindings using QKeySequenceEdit.
# ---------------------------------------------------------------
KEYBIND_DEFAULTS = {
    "confirm": "Return",
    "confirm_sequential": "Ctrl+Return",
    "place_at_markers": "Alt+M",
    "place_at_cuts": "Alt+C",
    "reveal_only": "Shift+Return",
    "reveal_keep_open": "Ctrl+Shift+Return",
    "preview": "Ctrl+Shift+P",   # (Alt+Return until 2026-10-31: it went to insert_compound)
    "play_pause": "Ctrl+Space",
    "seek_back": "Alt+Shift+Left",
    "seek_forward": "Alt+Shift+Right",
    "list_seek_back": "Left",            # these four only while you're in the list (see PickerWindow._in_list):
    "list_seek_forward": "Right",        # in the search the same keys move the text cursor
    "list_seek_back_far": "Ctrl+Left",
    "list_seek_forward_far": "Ctrl+Right",
    "mark_in": "Alt+I",
    "mark_out": "Alt+O",
    "clear_marks": "Alt+X",
    "toggle_staged": "Tab",
    "increment_staged": "Ctrl+Tab",
    "decrement_staged": "Ctrl+Shift+Tab",
    "toggle_favorite": "Ctrl+F",
    "show_in_file_manager": "Ctrl+E",
    "preview_audio": "Ctrl+P",
    "cancel": "Escape",
    "toggle_settings": "Ctrl+,",
    "toggle_insert_options": "Ctrl+I",
    "toggle_history": "Ctrl+H",
    "refresh": "Ctrl+R",
    "history_prev": "Alt+Shift+Up",
    "history_next": "Alt+Shift+Down",
    "select_extend_down": "Shift+Down",
    "select_extend_up": "Shift+Up",
    "jump_to_bottom": "Ctrl+Down",
    "jump_to_top": "Ctrl+Up",
    "select_to_bottom": "Ctrl+Shift+Down",
    "select_to_top": "Ctrl+Shift+Up",
    "show_actions": "Ctrl+K",
    "zoom_in": "Ctrl++",     # the window you're in: the picker, Settings, Insert as (fonts.step_zoom)
    "zoom_out": "Ctrl+-",
    "zoom_reset": "Ctrl+0",
    "show_info": "Ctrl+D",
    "mark_loop": "Alt+L",
    "similar_sounds": "Ctrl+L",
    "tag_clip": "Alt+T",
    "energy_1": "Alt+1",
    "energy_2": "Alt+2",
    "energy_3": "Alt+3",
    "insert_video_only": "Alt+V",
    "insert_audio_only": "Alt+A",
    "insert_compound": "Alt+Return",  # (2026-10-31: "i want alt + enter to be convert to compound clip on insert")
    "preview_large": "Alt+F",
}
# Every action in the Actions panel can have a key (Settings > Keybindings > Actions, or right-click its tile >
# Change key): these have none until you give them one. (name, the action's name in the panel)
# (What can be keyed in Resolve - RESOLVE_KEYED, RESOLVE_NATIVE below - has no key here: one key, in Resolve.)
ACTION_KEYS = [
    ("act_switch_timeline", "Switch timeline\u2026"), ("act_render", "Render\u2026"),
    ("act_switch_project", "Switch project\u2026"), ("act_project_templates", "Project templates\u2026"),
    ("act_check_up", "Project check-up"),
    ("act_copy_markers", "Copy markers"), ("act_copy_timeline", "Copy timeline"),
    ("act_copy_project", "Copy project"),
    ("act_copy_transcript", "Copy transcript"),
    ("act_relink", "Relink missing clips"), ("act_mark_beats", "Mark the beats"), ("act_mark_bars", "Mark the bars"),
]
ACTION_KEY_BY_LABEL = {label: name for name, label in ACTION_KEYS}
# Actions that are also a script in Resolve's Workspace > Scripts menu (resolve_shortcuts.ACTIONS): the action's
# name -> the script. A key given to it in Resolve's Keyboard Customization works without the picker open - the
# better key (2026-10-14) - and the only one: none of these has a key in the picker ("I just want 1
# keybind in davinci"). (A script can't open that window: the name is copied, to paste into its search.)
# (In this order they lead the Actions panel, as Scripts.)
RESOLVE_KEYED = {"Adjustment clip over clip": "Clipse 06 - Adjustment Clip Over Clip",
                 "Adjustment clip over footage": "Clipse 07 - Adjustment Clip Over Footage",
                 "Adjustment clip at playhead": "Clipse 08 - Adjustment Clip at Playhead",
                 "Fusion composition over clip": "Clipse 09 - Fusion Composition Over Clip",
                 "Fusion composition over footage": "Clipse 10 - Fusion Composition Over Footage",
                 "Fusion composition at playhead": "Clipse 11 - Fusion Composition at Playhead",
                 "Swap clip": "Clipse 01 - Swap Clip",
                 "Next use of clip": "Clipse 04 - Next Use of Clip",
                 "Previous use of clip": "Clipse 05 - Previous Use of Clip",
                 "Grab frame": "Clipse 03 - Grab Frame",
                 "Record voiceover": "Clipse 21 - Record Voiceover",
                 "Organise project": "Clipse 22 - Organise Project",
                 "Stretch marker to clips": "Clipse 23 - Stretch Marker to Clips",
                 "Add marker": "Clipse 25 - Add Marker",
                 "Hide - show markers": "Clipse 26 - Hide - Show Markers",
                 "Tidy up nodes": "Clipse 12 - Tidy Fusion Nodes",
                 "Pull node out": "Clipse 13 - Pull Out Fusion Node",
                 "Copy node name": "Clipse 14 - Copy Node Name",
                 "Node off / on": "Clipse 15 - Fusion Node Off - On",
                 "Before / after": "Clipse 16 - Fusion Before - After",
                 "Step back": "Clipse 19 - Step Back",
                 "Step forward": "Clipse 20 - Step Forward",
                 "Quit Clipse": "Clipse - Quit",
                 "Restart Clipse": "Clipse - Restart",
                 "Undo Clipse\u2019s last step": "Clipse 02 - Undo Last Action"}
# ...and actions Resolve has a command of its own for, keyed the same way: the name to search in its Keyboard
# Customization (seen in Resolve 21.1's keyboard.preset.xml: TrackControls_deleteEmptyTracks).
RESOLVE_NATIVE = {"Remove empty tracks": "Delete Empty Tracks"}
for _name, _label in ACTION_KEYS:
    KEYBIND_DEFAULTS[_name] = ""
# On a Mac, Qt's "Ctrl" is the Command key (and "Meta" is Control), so
# Ctrl+, is Cmd+, for Settings etc. - natural there. A few would clash with
# macOS itself and get their own Mac default:
MAC_KEYBIND_FIXES = {
    "play_pause": ("Ctrl+Space", "Alt+Space"),          # Cmd+Space is Spotlight
    "increment_staged": ("Ctrl+Tab", "Meta+Tab"),       # Cmd+Tab switches apps -> Control+Tab
    "decrement_staged": ("Ctrl+Shift+Tab", "Meta+Shift+Tab"),
    "toggle_history": ("Ctrl+H", "Ctrl+Y"),             # Cmd+H hides the app; Cmd+Y is History in Safari
}
if sys.platform == "darwin":
    for _name, (_generic, _mac) in MAC_KEYBIND_FIXES.items():
        KEYBIND_DEFAULTS[_name] = _mac
KEYBIND_LABELS = {
    "confirm": "Insert",
    "confirm_sequential": "Insert one after another",
    "place_at_markers": "Insert at every marker",
    "place_at_cuts": "Insert at every cut",
    "reveal_only": "Show in Media Pool",
    "reveal_keep_open": "Show in Media Pool, keep the picker open",
    "show_in_file_manager": "Show in file manager",
    "preview": "Preview",
    "play_pause": "Play or pause",
    "seek_back": "Back 5 seconds",
    "seek_forward": "Forward 5 seconds",
    "list_seek_back": "Back 1 second, in the list",
    "list_seek_forward": "Forward 1 second, in the list",
    "list_seek_back_far": "Back 5 seconds, in the list",
    "list_seek_forward_far": "Forward 5 seconds, in the list",
    "mark_in": "Mark in",
    "mark_out": "Mark out",
    "clear_marks": "Clear in and out",
    "toggle_staged": "Stage",
    "increment_staged": "Stage once more",
    "decrement_staged": "Stage once less",
    "toggle_favorite": "Favourite",
    "preview_audio": "Listening",
    "cancel": "Close",
    "toggle_settings": "Settings",
    "toggle_insert_options": "Insert as",
    "toggle_history": "History",
    "zoom_in": "Zoom in",
    "zoom_out": "Zoom out",
    "zoom_reset": "Reset zoom",
    "refresh": "Rescan the Media Pool",
    "history_prev": "Previous search",
    "history_next": "Next search",
    "select_extend_down": "Select one more down",
    "select_extend_up": "Select one more up",
    "jump_to_bottom": "Last row",
    "jump_to_top": "First row",
    "select_to_bottom": "Select to the last row",
    "select_to_top": "Select to the first row",
    "show_actions": "Actions",
    "show_info": "Clip info",
    "mark_loop": "Mark the music's loop",
    "similar_sounds": "Sounds like this",
    "tag_clip": "Tags",
    "energy_1": "Energy 1",
    "energy_2": "Energy 2",
    "energy_3": "Energy 3",
    "insert_video_only": "Insert picture only",
    "insert_audio_only": "Insert sound only",
    "insert_compound": "Insert as a compound clip",
    "preview_large": "Big preview",
}
KEYBIND_LABELS.update({name: label.rstrip("\u2026") for name, label in ACTION_KEYS})
KEYBIND_SCHEMA = [
    ("Insert", ["confirm", "confirm_sequential", "insert_video_only", "insert_audio_only", "insert_compound", "place_at_markers", "place_at_cuts"]),
    ("Media Pool", ["reveal_only", "reveal_keep_open", "show_in_file_manager"]),
    ("Preview", ["preview", "preview_large", "play_pause", "seek_back", "seek_forward",
                 "list_seek_back", "list_seek_forward", "list_seek_back_far", "list_seek_forward_far",
                 "mark_in", "mark_out", "clear_marks", "mark_loop", "preview_audio", "show_info",
                 "similar_sounds", "tag_clip", "energy_1", "energy_2", "energy_3"]),
    ("Staging", ["toggle_staged", "increment_staged", "decrement_staged", "toggle_favorite"]),
    ("Moving around", ["history_prev", "history_next", "select_extend_down", "select_extend_up",
                                 "jump_to_bottom", "jump_to_top",
                                 "select_to_bottom", "select_to_top"]),
    ("Windows", ["cancel", "toggle_settings", "toggle_insert_options", "toggle_history", "refresh",
                 "show_actions", "zoom_in", "zoom_out", "zoom_reset"]),
    ("Actions", [name for name, _label in ACTION_KEYS]),
]

# Every keybind gets a second, optional slot — empty by default, except
# these two: Alt+Right/Alt+Left double as quick Settings <-> Insert
# Options navigation (see picker_window.py's dialog-chaining), in
# addition to their primary Ctrl+,/Ctrl+I bindings.
KEYBIND_SECONDARY_DEFAULTS = {name: "" for name in KEYBIND_DEFAULTS}
KEYBIND_SECONDARY_DEFAULTS["toggle_settings"] = "Alt+Left"
KEYBIND_SECONDARY_DEFAULTS["toggle_insert_options"] = "Alt+Right"
KEYBIND_SECONDARY_DEFAULTS["zoom_in"] = "Ctrl+="  # (+ without Shift, on a keyboard where it shares the = key)

# ---------------------------------------------------------------
# Insert options — per-use modifiers for how staged clips land on the
# timeline (stagger timing, scale, speed, still duration). These are
# deliberately NOT part of the Settings dialog: unlike General/
# Appearance/Keybindings, you flip these before a specific insert, not
# once as app configuration — so they live in their own small dialog.
# Grouped by what they affect (video clips / audio clips / stills)
# rather than by property type, matching Resolve's own video=blue /
# audio=green convention.
# ---------------------------------------------------------------
INSERT_OPTIONS_DEFAULTS = {
    "stagger_video_offset_frames": 0,   # linear: flat gap · ease_out: starting gap
    "stagger_audio_offset_frames": 0,
    "stagger_video_curve": "linear",    # "linear" | "ease_out" | "custom"
    "stagger_audio_curve": "linear",
    "stagger_video_decay": 0.75,        # ease_out only — gap shrinks by this factor each step
    "stagger_audio_decay": 0.75,
    "stagger_video_floor": 2,           # ease_out only — gap never shrinks below this
    "stagger_audio_floor": 2,
    "stagger_video_custom_gaps": "",    # custom only — comma-separated frame gaps, e.g. "17,13,9,8,4,3,3"
    "stagger_audio_custom_gaps": "",    # holds at the last value once the list runs out
    "link_audio_video_timing": True,    # audio uses the video curve/settings above instead of its own
    "audio_custom_length_enabled": False,  # off by default — native length used unless this is on
    "audio_custom_length_frames": 180,     # the length used when the above is on
    "video_track_scale_percent": 100,
    "convert_to_clip_type": "none",
    "delete_empty_tracks_after_convert": True,
}
STAGGER_CURVE_LABELS = {"linear": "Linear", "ease_out": "Ease out", "custom": "Custom"}
# kept for anything still importing the old name
EXTENDED_OPTIONS_DEFAULT = INSERT_OPTIONS_DEFAULTS

# Namespace name -> defaults dict, used by Settings.reset_key/reset_namespace
# so every control's "double-click to reset" and every tab's "Reset tab"
# button can go through one generic path instead of one-off code per field.
# ---------------------------------------------------------------
# Search prefixes — fully user-configurable. Each target maps to a list
# of prefix strings that all mean the same thing (e.g. bin could be
# both "b:" and "folder:" at once). f: moves off bin by default to make
# room for the new favorite/star feature.
# ---------------------------------------------------------------
# Every kind of row answers to its name (and its plural - clip_model._build_prefix_maps) and to at most ONE short
# form, only where the name is long and it's used a lot (2026-10-15: "one shortform and one name").
PREFIX_DEFAULTS = {
    "audio": ["a", "audio"],
    "video": ["v", "video"],
    "adjustment": ["adj", "adjustment"],
    "compound": ["c", "compound"],
    "bin": ["b", "bin"],
    "image": ["i", "image"],
    "staged": ["s", "staged"],
    "favorite": ["f", "favorite"],
    "recent": ["r", "recent"],
    "unused": ["u", "unused"],
    "missing": ["missing"],
    "duplicate": ["dup", "duplicate"],
    "clipping": ["clipping"],
    "used": ["on", "used"],
    "music": ["m", "music"],
    "sfx": ["sfx"],
    "like": ["like"],
    "script": ["script"],
    "macro": ["macro"],
    "comp": ["comp"],
    "node": ["n", "node"],
    "expression": ["x", "expression"],
    "project": ["p", "project"],
    "folder": ["folder"],
    "timeline": ["t", "timeline"],
    "marker": ["mk", "marker"],
    "layout": ["layout"],
    "title": ["title"],
    "basic": ["basics"],
    "template": ["tpl", "template"],
    "shortcut": ["go", "shortcut"],
}
# ...as they were until 2026-10-15: a saved list that's still one of these is the new one now
# the Media Pool names before they were like_this (2026-10-20)
OLD_TIMELINE_TOOLS_DEFAULTS = {"adj_clip_name": "Adjustment Clip", "comp_clip_name": "Fusion Composition"}
OLD_PREFIX_DEFAULTS = {
    "audio": ["a"], "video": ["v"], "adjustment": ["ad", "adj"], "compound": ["c"], "bin": ["b"], "image": ["i"],
    "staged": ["s"], "favorite": ["st", "f"], "recent": ["r", "recent"], "unused": ["u", "unused"],
    "missing": ["missing"], "duplicate": ["dup", "duplicates"], "clipping": ["clipping"], "used": ["used", "on"],
    "music": ["m", "music"], "sfx": ["sfx"], "like": ["like"], "script": ["run", "script"], "macro": ["macro"],
    "comp": ["comp"], "node": ["n", "node"], "expression": ["x", "expr", "expression"], "project": ["p", "project"],
    "folder": ["folder", "dir"], "timeline": ["t", "timeline"], "title": ["title", "text"],
    "template": ["tpl", "template"], "shortcut": ["go", "open"],
}
# The prefix menu (type : on its own) and the pill in the search: each kind's name, short
PREFIX_TITLES = {
    "audio": "Sounds", "video": "Videos", "adjustment": "Adjustment clips", "compound": "Compound clips",
    "bin": "Bins", "image": "Pictures", "staged": "Staged", "favorite": "Favourites", "recent": "Recent",
    "unused": "Not on the timeline", "used": "On the timeline", "music": "Music", "sfx": "Sound effects",
    "like": "Sounds like", "missing": "Missing files", "duplicate": "Duplicates", "clipping": "Clipping sounds",
    "script": "Scripts", "macro": "Macros", "comp": "Fusion compositions", "node": "Fusion nodes",
    "expression": "Expressions", "project": "Projects", "timeline": "Timelines", "marker": "Markers",
    "template": "Project templates", "layout": "Layouts", "folder": "Folders", "title": "Title", "basic": "Basics",
    "shortcut": "Shortcuts",
}
PREFIX_LABELS = PREFIX_TITLES  # (Settings > Search Prefixes names each kind as the prefix menu does)
PREFIX_SCHEMA = [
    ("Media Pool", ["audio", "video", "adjustment", "compound", "bin", "image"]),
    ("Views", ["staged", "favorite", "recent", "unused", "used", "music", "sfx", "like"]),
    ("Project check-up", ["missing", "duplicate", "clipping"]),
    ("Scripts & Fusion", ["script", "macro", "comp", "node", "expression"]),
    ("Project", ["project", "timeline", "marker", "template", "layout", "folder"]),
    ("Basics", ["basic", "title"]),
    ("Clipse", ["shortcut"]),
]
# Which "kind" of filtering each target uses in clip_model.py's
# set_filter() — category (filters clip_rows by RowData.category),
# special (staged/selected/favorite row-set filters), or external
# (swaps in a whole different data source: scripts/macros/comps/projects).
PREFIX_CATEGORY_TARGETS = {"audio", "video", "adjustment", "compound", "bin", "image"}
PREFIX_SPECIAL_TARGETS = {"staged", "selected", "favorite", "recent", "unused", "used", "music", "sfx", "like",
                          "missing", "duplicate", "clipping"}
PREFIX_EXTERNAL_TARGETS = {"script", "macro", "comp", "node", "expression", "project", "folder", "timeline", "marker",
                           "layout", "title", "basic", "template",
                           "shortcut"}

# Optional keybind per prefix target — jumps straight to that search (e.g.
# Ctrl+Alt+F -> "f:"), pressing it again while already there clears back
# to whatever was typed before. Empty (unset) by default for all of them.
PREFIX_KEYBIND_DEFAULTS = {target: "" for target in PREFIX_DEFAULTS}
PREFIX_KEYBIND_DEFAULTS["favorite"] = "Ctrl+Shift+F"  # (2026-10-17)

# ---------------------------------------------------------------
# Timeline tools (Settings -> General -> Adjustment clip) — used by
# `clipse adjust ...`, which you bind to a system-wide key
# (see README). The clip is looked up by name anywhere in the
# Media Pool (first match wins). "Fallback" is the length used by the
# match modes when there's nothing under the playhead to size against.
# ---------------------------------------------------------------
# Showing files and folders (Ctrl+E, folder:) - Settings -> General -> File manager
FILES_DEFAULTS = {
    "file_manager": "",    # command to run instead of the system's choice ("" = automatic)
    "max_windows": 8,      # Ctrl+E on clips in many folders opens at most this many windows
    "grabs_on_timeline": True,  # Grab Frame also puts the still on the timeline at the playhead
    "grabs_folder": "",    # where Grab Frame's PNGs go ("" = Pictures/Clipse) - Settings > Scripts
    "voice_folder": "",    # where Record Voiceover's takes go ("" = Music/Clipse) - Settings > Scripts
}

# Listening to sounds (Ctrl+P / the speaker in the bottom bar)
LISTEN_DEFAULTS = {
    "volume": 70,          # percent
    "autoplay": False,     # preview window: start playing as soon as a clip shows (off: a sound starting by itself startles)
    "loop": False,         # preview window: start over at the end (off = play once)
    "timecode": False,        # preview: times as the clip's timecode (01:00:12:14) instead of m:ss
    "remember_guides": True,  # preview: the framing guides stay on for every clip (Guides menu)
    "guides": [],             # ...which ones
    "remember_place": True,   # preview: going back to a clip carries on where you left it
    "hover_scrub": True,      # preview: moving the mouse across a video's picture moves through it
    "show_used_parts": True,  # preview: mark the parts of a clip that are on the timeline already
    "expression_preview": True,  # the preview opens by itself to show what a Fusion expression does
    "scrub_sound": False,     # preview: moving through a clip (hover, or dragging while paused) plays the sound there
    "space_action": "auto",   # ...and what it does: "auto" (short clips start over, long ones pause), "pause", "replay"
    "space_replay_under": 30, # auto: clips shorter than this many seconds start over
    "space_plays": "smart",   # the Space key: "smart" (plays unless you're typing), "always", or "never" (only Ctrl+Space)
    "preview_place": "shared",  # (ships in its space, no gap - 2026-10-17) "side" (next to the picker - the window grows), "shared" (in its space: the room taken
                              # from the list, the window stays) or "window" (its own window, anywhere)
    "preview_gap": 0,         # beside the picker: px between the two (0: one card, a line between - how it ships,
                              # 2026-10-16) - Settings > Preview
    "preview_dock": "shared", # ...back from a window of its own: the way it sat before ("side" / "shared")
    "preview_width": 0,       # the preview beside the picker, in px at 100 % (0: PickerWindow.PREVIEW_WIDTH) - dragged
    "preview_stay": False,    # its own window: stays open when the picker closes
    "preview_with_picker": False,  # the preview opens together with the picker, every time
    "split_music": True,      # tell music from sound effects (own symbols, m: and sfx:)
    "show_bpm": True,         # music: its tempo next to the name
    "guess_energy": False,    # music with no energy tag: bars from the analysis, outlined (2026-11-01: his choice, off)
    "show_beat_grid": True,   # music: faint beat lines behind the waveform in the preview
    "trim_silence": True,     # sounds: leave out silence at the start and end on insert (unless in/out is marked)
    "music_min_seconds": 30,  # unnamed audio this long or longer is checked for a steady beat (a minute: music anyway)
    "auto_analyse": False,    # analyse new sounds when the picker opens (off: only from Settings)
    "show_info": False,       # clip info under the preview (Info in the preview's bar, or Ctrl+D)
    "info_fields": None,      # clip info (Ctrl+D): which lines show - filled from INFO_FIELDS below
}

# Clip info (Ctrl+D): (key, label, shown by default)
INFO_FIELDS = [
    ("kind", "Kind", True), ("length", "Length", True), ("video", "Video format", True),
    ("audio", "Audio format", True), ("music", "BPM & key", True), ("mood", "Mood", True),
    ("loop", "Loop", True), ("keywords", "Keywords", True), ("comments", "Comments", False),
    ("clip_colour", "Clip colour", False), ("used", "Times used", True), ("created", "Created", False),
    ("file", "File & size", True), ("folder", "Folder", False),
]
LISTEN_DEFAULTS["info_fields"] = {key: on for key, _label, on in INFO_FIELDS}

TIMELINE_TOOLS_DEFAULTS = {
    # Swap clip (its strip's ⋯ - set there and nowhere else): how long the new clip is - "old" (the old one's
    # length), "own_stop" (its own, up to the next clip), "own_over" (its own, over the next - a track up);
    # where it sits - "start", "end" or "loudest" (the loudest moments lined up); the same part of its recording
    # as the old one; the old one's colour grade; its size and position
    "swap_length": "old", "swap_align": "start", "swap_same_part": False, "swap_grade": False, "swap_look": True,
    "title_name": "Text+",   # title: - which Fusion title gets added (Text+, or one of your own)
    "place_align": "start",
    "tidy_after_insert": False,
    "tidy_fit_view": True,      # Fusion: Tidy up also centres the node view on the nodes (the zoom stays)  # Fusion: the nodes tidied up after every insert (the new ones go into place)
    "tidy_style": "lines",   # Fusion tidy up: "lines" (left to right) or "vertical" (top to bottom)  # markers/cuts: the clip "start"s there, is "centre"d on it, or "end"s there
    "adj_clip_name": "adjustment_clip",
    "adj_fixed_frames": 180,
    # Step Forward / Step Back (scripts in Resolve's menu): how far one press moves the playhead, each its own
    "step_forward_frames": 5, "step_back_frames": 5,
    # Record Voiceover (voiceover.py): the microphone by its name ("" = the system's); it starts when you "speak", after
    # a "countdown" (3 s) or at once ("now"); the audio tracks off while it records; the quiet at the take's ends left out
    "voice_mic": "", "voice_start": "speech", "voice_mute": True, "voice_trim": True,
    "comp_clip_name": "fusion_composition",  # the Media Pool clip the Fusion Composition shortcuts place
    "comp_fixed_frames": 180,
    "animate_seconds": 0.4,  # Fusion: how long a ready-made animation takes (> animate)
    "expression_ask": True,  # Fusion: with no node selected, ask before adding a node for an expression
    "expression_sliders": True,  # Fusion: an expression's numbers become sliders on the node (off: written into the code)
    # Subtitles from speech - what Resolve lets a script decide (resolve_commands.SUBTITLE_*)
    "subtitle_language": "auto",   # or one of the languages Resolve knows
    "subtitle_chars": 42,          # the longest a line may be, in characters (1-60)
    "subtitle_lines": "single",    # "single": one line at a time, "double": two
    "subtitle_gap": 0,             # frames left empty between one subtitle and the next (0-10)
    "subtitle_preset": "default",  # "default", "teletext" or "netflix" - Resolve's rules for timing and length
    "remove_empty_tracks": True,  # after wrapping inserted clips into a compound / Fusion clip
}

from .presets import DEFAULTS as PRESET_DEFAULTS  # noqa: E402

NAMESPACE_DEFAULTS = {
    "general": GENERAL_DEFAULTS,
    "theme": THEME_DEFAULTS,
    "keybinds": KEYBIND_DEFAULTS,
    "keybinds_secondary": KEYBIND_SECONDARY_DEFAULTS,
    "advanced": INSERT_OPTIONS_DEFAULTS,
    "display": DISPLAY_DEFAULTS,
    "icons": ICON_DEFAULTS,
    "folders": FOLDER_DEFAULTS,
    "page_defaults": PAGE_DEFAULTS_DEFAULT,
    "prefixes": PREFIX_DEFAULTS,
    "prefix_keybinds": PREFIX_KEYBIND_DEFAULTS,
    "timeline_tools": TIMELINE_TOOLS_DEFAULTS,
    "listen": LISTEN_DEFAULTS,
    "files": FILES_DEFAULTS,
    "presets": PRESET_DEFAULTS,
}

INSERT_OPTIONS_SCHEMA = [
    ("Video clips", "video", [
        {"key": "video_track_scale_percent", "label": "Scale", "suffix": "%", "step": 5, "min": 1, "max": 1000},
    ]),
]


class Settings:
    """One object holding everything Settings covers. Load once at
    startup; every reader/writer in the app goes through this instance
    instead of scattered globals."""

    def __init__(self):
        self.general = dict(GENERAL_DEFAULTS)
        self.theme = dict(THEME_DEFAULTS)
        self.keybinds = dict(KEYBIND_DEFAULTS)
        self.keybinds_secondary = dict(KEYBIND_SECONDARY_DEFAULTS)
        self.advanced = dict(EXTENDED_OPTIONS_DEFAULT)
        self.display = dict(DISPLAY_DEFAULTS)
        self.icons = dict(ICON_DEFAULTS)
        self.folders = {k: list(v) for k, v in FOLDER_DEFAULTS.items()}
        self.page_defaults = {page: dict(cfg) for page, cfg in PAGE_DEFAULTS_DEFAULT.items()}
        self.prefixes = {target: list(v) for target, v in PREFIX_DEFAULTS.items()}
        self.prefix_keybinds = dict(PREFIX_KEYBIND_DEFAULTS)
        self.timeline_tools = dict(TIMELINE_TOOLS_DEFAULTS)
        self.listen = dict(LISTEN_DEFAULTS)
        self.files = dict(FILES_DEFAULTS)
        self.presets = {"user": [], "edits": {}, "active": "normal", "keep": False, "migrated": False, "seeds": {},
                        "still_length": 5.0}

    # -- convenience accessors used throughout the app --
    def g(self, name):
        return self.general[name]

    def icon_color(self, category):
        return {
            "audio": self.theme["color_audio"], "video": self.theme["color_video"],
            "adjustment": self.theme["color_adjustment"], "compound": self.theme["color_compound"],
            "bin": self.theme["color_bin"], "selected": self.theme["color_selected"],
            "image": self.theme["color_image"],
            "script": self.theme["color_script"], "macro": self.theme["color_macro"],
            "comp": self.theme["color_comp"], "project": self.theme["color_project"],
            "node": self.theme.get("color_node", "#7fdbca"),
            "expression": self.theme.get("color_expression", "#c792ea"),
            "folder": self.theme["color_bin"],
            "timeline": self.theme["color_project"],
            "marker": self.theme["color_project"],  # (each row's own tag is its marker's colour - clip_model)
            "layout": self.theme["color_project"],
            "title": self.theme["color_comp"],
            "template": self.theme["color_project"],
            "action": self.theme.get("picker_accent", self.theme["color_video"]),
            "shortcut": self.theme.get("picker_folder", "#9a9ea6"),  # a way into the app itself: grey, on purpose
            "prefix": self.theme.get("picker_folder", "#9a9ea6"),  # (the : menu - each row tinted as its kind)
        }[category]

    def kind_on(self, key, page="other"):
        """Is this kind of Media Pool row (show_video ...) listed on that page? Each page has its
        own answer: the Edit page's in `general`, the Fusion page's in page_defaults["fusion"]."""
        if page == "fusion":
            return key not in FUSION_SKIPS and bool(self.page_defaults["fusion"].get(key, True))
        return bool(self.general[key])

    def kind_built(self, key):
        """Rows of this kind are made when either page lists them."""
        return self.kind_on(key) or self.kind_on(key, "fusion")

    def hidden_categories(self, page):
        """The kinds of row that exist (the other page lists them) but aren't in this page's plain list."""
        return tuple(category for key, category in KIND_CATEGORY.items()
                     if self.kind_built(key) and not self.kind_on(key, page))

    def category_enabled(self, category):
        key = next((key for key, cat in KIND_CATEGORY.items() if cat == category), None)
        return key is not None and self.kind_built(key)

    def scaled_font_size(self):
        """The base size in points (fonts.base_points: Font size is pixels, times the UI scale)."""
        from .fonts import base_points
        return base_points(self)

    @staticmethod
    def _copy_default_value(value):
        if isinstance(value, list):
            return list(value)
        if isinstance(value, dict):
            return dict(value)
        return value

    def reset_key(self, namespace, key):
        """Reset one setting to its default — what a double-click on its
        label does."""
        defaults = NAMESPACE_DEFAULTS[namespace]
        if key in defaults:
            getattr(self, namespace)[key] = self._copy_default_value(defaults[key])

    def reset_namespace(self, namespace):
        """Reset every setting in one namespace (one Settings tab, or the
        Insert Options dialog) to defaults."""
        defaults = NAMESPACE_DEFAULTS[namespace]
        setattr(self, namespace, {k: self._copy_default_value(v) for k, v in defaults.items()})

    def theme_after(self, name):
        """What applying the theme `name` gives: its picker colours with your clip colours - unless it goes
        from dark to light or back, when the clip colours come with it (a dark theme's are too pale on white,
        a light theme's too dark on black)."""
        preset = THEME_PRESETS.get(name) or {}
        out = {**self.theme, **{k: v for k, v in preset.items() if k in INTERFACE_COLOR_VARS}}
        if preset and is_light(preset["picker_bg"]) != is_light(self.theme.get("picker_bg", "#000000")):
            clips = preset if is_light(preset["picker_bg"]) else THEME_PRESETS["Default"]
            out.update({k: v for k, v in clips.items() if k in ICON_COLOR_VARS or k == "color_node"})
        return out

    def apply_theme_preset(self, name):
        if name in THEME_PRESETS:
            self.theme.update(self.theme_after(name))

    def load(self):
        saved = paths.read_json(SETTINGS_FILE)  # (one that can't be read is kept aside, never written over)
        if not isinstance(saved, dict):
            return
        self.apply(saved)
        if getattr(self, "_resave", False):
            self._resave = False
            self.save()

    def apply(self, saved):
        """Takes over what a settings file holds (settings.json, or one
        brought in with Settings -> About -> Import): only what this
        version knows, and only values of the right kind."""
        for name, value in saved.get("general", {}).items():
            if name in self.general:
                self.general[name] = value
        # Saved by a version before the Graphite look (no accent colour yet):
        # settings still at their old default move to the new default.
        upgrading = "picker_accent" not in saved.get("theme", {"picker_accent": ""})

        def untouched(old_defaults, name, value):
            old = old_defaults.get(name)
            return upgrading and old is not None and str(old).lower() == str(value).lower()

        theme_saved = saved.get("theme", {})
        if all(str(theme_saved.get(k, "")).lower() == v.lower() for k, v in GRAPHITE_BEFORE.items()):
            theme_saved = {**theme_saved, **{k: THEME_PRESETS["Graphite"][k] for k in INTERFACE_COLOR_VARS}}
        for name, value in theme_saved.items():
            if name in self.theme and not untouched(OLD_THEME_DEFAULTS, name, value) \
                    and not (upgrading and str(V16_THEME_DEFAULTS.get(name, "")).lower() == str(value).lower()) \
                    and str(V170_THEME_DEFAULTS.get(name, "")).lower() != str(value).lower() \
                    and str(V18_THEME_DEFAULTS.get(name, "")).lower() != str(value).lower() \
                    and str(V141_THEME_DEFAULTS.get(name, "")).lower() != str(value).lower():
                self.theme[name] = value
        for name, value in saved.get("keybinds", {}).items():
            if name in self.keybinds and isinstance(value, str) and not value.startswith("<"):
                # Guards against a settings.json left over from the old
                # Tk version, which stored keybinds as "<Return>" etc —
                # not valid QKeySequence syntax. Falls back to the Qt
                # default for that action instead of silently breaking it.
                self.keybinds[name] = value
        if sys.platform == "darwin":  # Mac: saved generic defaults that clash with macOS -> the Mac ones
            for name, (generic, mac) in MAC_KEYBIND_FIXES.items():
                if self.keybinds.get(name) == generic:
                    self.keybinds[name] = mac
        # Alt+Enter opened the preview until it became Insert as a compound clip (2026-10-31): a preview
        # still on it, saved before there was one, goes to the preview's new key
        if self.keybinds.get("preview") == "Alt+Return" and "insert_compound" not in saved.get("keybinds", {}):
            self.keybinds["preview"] = KEYBIND_DEFAULTS["preview"]
        # v1.12-1.15 defaults for search history -> the new ones
        for name, old in (("history_prev", "Alt+Up"), ("history_next", "Alt+Down")):
            if self.keybinds.get(name) == old:
                self.keybinds[name] = KEYBIND_DEFAULTS[name]
        for name, value in saved.get("keybinds_secondary", {}).items():
            if name in self.keybinds_secondary and isinstance(value, str) and not value.startswith("<"):
                self.keybinds_secondary[name] = value
        for key, value in saved.get("advanced", {}).items():
            if key in self.advanced:
                self.advanced[key] = value
        for key, value in saved.get("display", {}).items():
            if key in self.display and not untouched(OLD_DISPLAY_DEFAULTS, key, value) \
                    and value not in V16_DISPLAY_DEFAULTS.get(key, ()):
                self.display[key] = value
        for key, value in saved.get("icons", {}).items():
            if key in self.icons and isinstance(value, str) and value:
                self.icons[key] = value
        for key, value in saved.get("folders", {}).items():
            if key in self.folders and isinstance(value, list):
                self.folders[key] = [str(p) for p in value]
        # older default: only Scripts/Edit -> the whole Scripts folder (Utility, Edit, Comp ...)
        if self.folders.get("scripts") == [scripts_fusion.default_scripts_folder()]:
            self.folders["scripts"] = list(FOLDER_DEFAULTS["scripts"])
        for page, sub in saved.get("page_defaults", {}).items():
            if page in self.page_defaults and isinstance(sub, dict):
                for k, v in sub.items():
                    if k in self.page_defaults[page]:
                        self.page_defaults[page][k] = bool(v)
        for target, value in saved.get("prefixes", {}).items():
            if target in self.prefixes and isinstance(value, list):
                value = [str(p).strip().lower() for p in value if str(p).strip()]
                if value != OLD_PREFIX_DEFAULTS.get(target):  # (never changed: the new list)
                    self.prefixes[target] = value
        for target, value in saved.get("prefix_keybinds", {}).items():
            if target in self.prefix_keybinds and isinstance(value, str) and not value.startswith("<"):
                self.prefix_keybinds[target] = value
        for key, value in saved.get("listen", {}).items():
            if key in self.listen and isinstance(value, type(LISTEN_DEFAULTS[key])):
                if isinstance(value, dict):  # keep defaults for keys added since
                    value = {**LISTEN_DEFAULTS[key], **value}
                self.listen[key] = value
        for key in ("preview_place", "preview_dock"):  # (2026-10-16, a day of trying: "joined" and "inside" -
            if self.listen.get(key) in ("joined", "inside"):  # One window - are In its space with no gap)
                self.listen[key] = "shared"
                self.listen["preview_gap"] = 0
        for key, value in saved.get("files", {}).items():
            if key in self.files and isinstance(value, type(FILES_DEFAULTS[key])):
                self.files[key] = value
        for key, value in saved.get("timeline_tools", {}).items():
            if key in self.timeline_tools and isinstance(value, type(TIMELINE_TOOLS_DEFAULTS[key])) \
                    and OLD_TIMELINE_TOOLS_DEFAULTS.get(key) != value:  # (never changed: the new name)
                self.timeline_tools[key] = value
        old_step = saved.get("timeline_tools", {}).get("step_frames")  # (one for both, for a day - 2026-10-21)
        if isinstance(old_step, int) and "step_forward_frames" not in saved.get("timeline_tools", {}):
            self.timeline_tools.update(step_forward_frames=old_step, step_back_frames=old_step)
            self._resave = True  # (Resolve's step scripts read the file itself)
        if "delete_empty_tracks_after_convert" in saved.get("advanced", {}):
            self.timeline_tools["remove_empty_tracks"] = bool(saved["advanced"]["delete_empty_tracks_after_convert"])
        for key, value in saved.get("presets", {}).items():
            if key in self.presets and isinstance(value, type(self.presets[key])):
                self.presets[key] = value
        if not 0.03 <= float(self.presets.get("still_length") or 0) <= 3600:
            self.presets["still_length"] = 5.0
        # ("still_seconds", until 1.42: Resolve's still length as read off inserted stills - often wrongly.
        # The app sets a picture's length itself now, so that guess is left behind.)
        from . import presets
        presets.migrate(self)
        for namespace, values in FIXED.items():  # (no longer settings: a value saved before doesn't count)
            getattr(self, namespace).update(values)

    def save(self):
        data = self.as_dict()
        try:
            paths.write_json(SETTINGS_FILE, data, indent=2)
        except OSError:
            pass  # non-critical — worst case this session's changes aren't saved

    def as_dict(self):
        return {
            "format": FORMAT,
            "general": self.general, "theme": self.theme,
            "keybinds": self.keybinds, "keybinds_secondary": self.keybinds_secondary, "advanced": self.advanced,
            "display": self.display, "icons": self.icons,
            "folders": self.folders, "page_defaults": self.page_defaults, "prefixes": self.prefixes,
            "prefix_keybinds": self.prefix_keybinds,
            "timeline_tools": self.timeline_tools,
            "listen": self.listen,
            "files": self.files,
            # (changes to the built-in presets are for the insert at hand, never kept: Save as mine keeps them)
            "presets": {**self.presets, "edits": {}},
        }
