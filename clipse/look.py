"""One look for the pieces every window shares (2026-10-16: "I really want consistency").

Corners come in three sizes, Vicinae's: a control (button, field, menu, dropdown) 6, a tile or a row 10, a card
12 - all moved together by Settings > Appearance > Inner corners (4 is how they ship). Every tile in the app -
the Actions panel, Insert as's presets and options, the marker colours, Settings' list tiles, the guides - is
drawn by paint_tile, so a tile at rest, under the mouse and chosen looks the same wherever it is.
"""
from PySide6.QtGui import QColor, QPen

SHIPS = 4  # Inner corners as it ships: the sizes below are at this


def radius(settings, kind):
    """"control" 6, "tile" 10, "card" 12 (at Inner corners 4) - never under 2."""
    base = {"control": 6, "tile": 10, "card": 12}[kind]
    return float(max(2, base + int(settings.display.get("corner_radius", SHIPS)) - SHIPS))


def _alpha(colour, a):
    c = QColor(colour)
    c.setAlphaF(a)
    return c


def tile_colours(settings, chosen=False, hover=False, focus=False):
    """(edge pen, fill) of a tile. At rest: a faint edge and fill in the text's colour; under the mouse a little
    more; chosen (or the one the keys are on): the accent's edge and a soft accent fill."""
    t = settings.theme
    text = QColor(t["picker_text"])
    accent = QColor(t.get("picker_accent", t["picker_text"]))
    if chosen:
        return QPen(accent, 2.0 if focus else 1.4), _alpha(accent, 0.17 if hover else 0.12)
    return QPen(_alpha(text, 0.17 if hover else 0.1), 1.0), _alpha(text, 0.065 if hover else 0.03)


def paint_tile(p, rect, settings, chosen=False, hover=False, focus=False):
    """A tile's ground: its edge and fill, its corners the tile size."""
    pen, fill = tile_colours(settings, chosen, hover, focus)
    r = radius(settings, "tile")
    p.save()
    p.setPen(pen)
    p.setBrush(fill)
    p.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), r, r)
    p.restore()
