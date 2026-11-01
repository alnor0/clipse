"""Fonts ship with the app (fonts/, all SIL Open Font License - OFL-*.txt), so the picker looks the same on
Windows, macOS and Linux instead of falling back to each system's own font: Outfit - Vicinae's, the app's own
since 2026-10-16 ("I want vicinaes font") - and Geist Mono for code and numbers in
code. Outfit and Geist Mono come as one file a weight, made from Google Fonts' variable files (fontTools'
instancer): Qt took the variable file as Thin only, at every weight."""
import os

BUNDLED_FAMILY = "Outfit"
MONO_FAMILIES = ["Geist Mono", "JetBrains Mono", "DejaVu Sans Mono", "Menlo", "Consolas", "monospace"]
_loaded = None


def load_bundled_fonts():
    """Registers the bundled font files with Qt (once). Returns the family
    name, or None if they couldn't be loaded."""
    global _loaded
    if _loaded is not None:
        return _loaded or None
    from PySide6.QtGui import QFontDatabase
    folder = os.path.join(os.path.dirname(__file__), "fonts")
    families = set()
    for name in sorted(os.listdir(folder)) if os.path.isdir(folder) else []:
        if name.lower().endswith((".otf", ".ttf")):
            font_id = QFontDatabase.addApplicationFont(os.path.join(folder, name))
            if font_id >= 0:
                families.update(QFontDatabase.applicationFontFamilies(font_id))
    _loaded = BUNDLED_FAMILY if BUNDLED_FAMILY in families else ""
    return _loaded or None


# -- one scale of sizes for every window (2026-10-16: "everything has to fit together well") --
# Vicinae's: one base size, smaller text at 0.9 of it, its search and dialog titles about 1.2. Every font in the
# app is the base at one of these steps - never a size of its own, never "a bit smaller than the one next to it".
TITLE = 1.2   # the search field, a dialog's or panel's title
SMALL = 0.9   # second lines, hints, the bottom bar, section headings (semibold)
TINY = 0.8    # keycaps, chips, counts, the labels inside a drawing
HERO = 1.4    # the app's name on About

# -- each window's own zoom (2026-10-16: the picker larger by itself; Ctrl and + / - / 0 in a window) --
# On top of Font size x UI scale, kept in display["zoom"]. The app font is the picker's size; another window's text
# is its zoom over the picker's (rel). Settings started a step smaller ("a little more zoomed out"), Insert as
# smaller still ("easier to get an overview").
# the picker ships at the size it's used at (2026-10-17: his UI scale 1.25 x zoom 1.1 - "what ever gives the picker on
# the screen should be the default"), the other windows as they were; History is the picker's size
WINDOW_ZOOM = {"picker": 1.4, "settings": 0.9, "insert_as": 0.85, "history": 1.4,
               # the Actions panel: over the picker's own size, 1 as it ships - smaller fits more rows (2026-10-21:
               # "when you zoom out you might be able to fit 4 or 5 rows")
               "actions": 1.0,
               # Expressions, the same way (2026-10-22: zooming out should give more columns and rows)
               "expressions": 1.0}
ZOOM_STEP, ZOOM_LOW, ZOOM_HIGH = 0.05, 0.6, 2.0


def window_zoom(settings, name):
    try:
        return float((settings.display.get("zoom") or {}).get(name, WINDOW_ZOOM[name]))
    except (TypeError, ValueError):
        return WINDOW_ZOOM[name]


def own_zoom(settings, name):
    """What a panel drawn with the picker's font is scaled by (the Actions panel, Expressions): its own zoom, the
    picker's taken back out - zooming the picker doesn't change it, nor it the picker (2026-10-22: "the zoom on
    expressions should not transfer to the picker")."""
    return window_zoom(settings, name) * WINDOW_ZOOM["picker"] / window_zoom(settings, "picker")


def rel(settings, name):
    """A window's text size over the picker's (the app font's)."""
    return window_zoom(settings, name) / window_zoom(settings, "picker")


def picker_scale(settings):
    """What the picker's spacing grows by: the UI scale times its zoom."""
    return float(settings.display.get("ui_scale", 1.0)) * window_zoom(settings, "picker")


def picker_size_scale(settings):
    """What the picker's sizes grow by - the window, the preview beside the list, their smallest: the UI scale times
    its zoom as it ships. Ctrl and + / - change only what's inside (2026-10-21: "the zoom is only supposed to make
    the pickers inside be smaller" - the size is Settings' and the edges')."""
    return float(settings.display.get("ui_scale", 1.0)) * WINDOW_ZOOM["picker"]


def step_zoom(settings, name, direction):
    """Ctrl and + (1), - (-1), 0 (0: as it ships) in a window. The new zoom, kept in the settings."""
    now = window_zoom(settings, name)
    new = WINDOW_ZOOM[name] if direction == 0 else min(ZOOM_HIGH, max(ZOOM_LOW, round(now + direction * ZOOM_STEP, 2)))
    zooms = dict(settings.display.get("zoom") or {})
    if new == WINDOW_ZOOM[name]:
        zooms.pop(name, None)
    else:
        zooms[name] = new
    settings.display["zoom"] = zooms
    return new


def zoom_key(event, settings):
    """1 / -1 / 0 when the key pressed is Zoom in / out / back (Settings > Keybindings), else None. Shift is let
    through: on many keyboards + is Shift and =."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QKeySequence
    mods = event.modifiers() & ~Qt.ShiftModifier & ~Qt.KeypadModifier
    for name, direction in (("zoom_in", 1), ("zoom_out", -1), ("zoom_reset", 0)):
        for slot in (settings.keybinds, getattr(settings, "keybinds_secondary", {}) or {}):
            seq = QKeySequence(slot.get(name, "") or "")
            if seq.count() == 0:
                continue
            want = seq[0]
            if event.key() == want.key() and mods == (want.keyboardModifiers() & ~Qt.ShiftModifier):
                return direction
    return None


def _dpi():
    """Points to pixels: 72 a inch on a Mac (a point is a pixel there), the screen's logical DPI elsewhere (96)."""
    import sys
    if sys.platform == "darwin":
        return 72.0
    try:
        from PySide6.QtGui import QGuiApplication
        screen = QGuiApplication.primaryScreen()
        if screen is not None and screen.logicalDotsPerInch() > 0:
            return float(screen.logicalDotsPerInch())
    except Exception:
        pass
    return 96.0


def base_points(settings):
    """The base size - the picker's - in points: Settings' Font size is in pixels (14 = Vicinae's own 10.5 pt), times
    the UI scale and the picker's zoom - the same on a Mac and on Linux (as points it was 14 px on one, 19 on the
    other)."""
    d = settings.display
    return max(6.0, float(d.get("font_size", 14)) * float(d.get("ui_scale", 1.0)) * window_zoom(settings, "picker")
               * 72.0 / _dpi())


def zoom(settings):
    """How much bigger than Vicinae's 14 px the text is (Font size x UI scale / 14): what a drawing that was made
    for 14 px text grows by, so its words still fit."""
    d = settings.display
    return max(0.5, float(d.get("font_size", 14)) * float(d.get("ui_scale", 1.0)) / 14.0)


def base():
    """The base size the app font has (apply_ui_font put it there)."""
    from PySide6.QtWidgets import QApplication
    size = QApplication.font().pointSizeF()
    return size if size > 0 else 10.5


def at(step=1.0, font=None, weight=None):
    """`font` (else the app's) at a step of the scale, e.g. at(SMALL, mono) - optionally in a weight."""
    from PySide6.QtGui import QFont
    from PySide6.QtWidgets import QApplication
    f = QFont(font) if font is not None else QFont(QApplication.font())
    f.setPointSizeF(round(base() * step, 2))
    if weight is not None:
        f.setWeight(weight)
    return f


def css(step=1.0):
    """A stylesheet's font-size at a step of the scale."""
    return f"font-size: {base() * step:.2f}pt;"


def mono_families():
    """Geist Mono (bundled - loaded here if nothing has yet), then what a system might have."""
    load_bundled_fonts()
    return list(MONO_FAMILIES)


# A family picked by one of its weights ("Outfit Light" - the bundled files register that name too, so Settings
# offers it): the family is the plain one with that weight. Asked for as "Outfit Light", everything bolder than
# light - headings, keys, the chosen tab - had no face of its own and came out in another font (FreeSans here).
_WEIGHT_NAMES = (("Thin", "Thin"), ("ExtraLight", "ExtraLight"), ("Light", "Light"), ("Medium", "Medium"),
                 ("SemiBold", "DemiBold"), ("Bold", "Bold"))


def ui_font(settings):
    """(family, weight or None): the font picked in Settings, else Outfit - the bundled fonts always loaded
    first, so a name of one ("Outfit Light") is found whatever the system has installed. A font that's no longer
    there - Inter, bundled until 1.1.0 - is Outfit."""
    from PySide6.QtGui import QFont, QFontDatabase
    bundled = load_bundled_fonts()
    family = settings.display.get("font_family") or bundled or ""
    families = set(QFontDatabase.families())
    for word, weight in _WEIGHT_NAMES:
        base = family[:-len(word) - 1]
        if family.endswith(" " + word) and base in families:
            return base, getattr(QFont, weight)
    return (family if family in families or not bundled else bundled), None


def ui_family(settings):
    """The font family to use: the one picked in Settings, else Outfit."""
    return ui_font(settings)[0]


def apply_ui_font(font, settings):
    """`font` in the family (and weight) picked in Settings, at the base size. Returns it."""
    family, weight = ui_font(settings)
    if family:
        font.setFamily(family)
    if weight is not None:
        font.setWeight(weight)
    font.setPointSizeF(round(base_points(settings), 2))
    return font
