"""Keys as small quiet caps beside what they do - the picker's bottom bar, the cheat sheet's, the Actions
panel's. The key's name in words ("Enter", "Tab", "Shift+Enter"), in a soft rounded cap with no border
(picked from samples, 2026-10-14: the symbols in outlined caps were "too much", not elegant)."""
import sys

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QKeySequence
from .fonts import TINY, at as font_at  # (the one scale of sizes)

_WORDS = {"Return": "Enter", "Enter": "Enter", "Escape": "Esc", "PgDown": "PgDn", "PgUp": "PgUp",
          "Backspace": "Backspace", "Del": "Del", "Delete": "Del"}
_MAC = {"Ctrl": "Cmd", "Meta": "Ctrl", "Alt": "Option"}


def key_name(sequence):
    """'Return' -> 'Enter', 'Shift+Return' -> 'Shift+Enter', a Mac's Ctrl -> 'Cmd'. Accepts what a keybind
    holds ("Ctrl+K") or a QKeySequence."""
    text = QKeySequence(sequence).toString(QKeySequence.PortableText) if not isinstance(sequence, str) else sequence
    parts = []
    for part in text.split("+") if text != "+" else ["+"]:
        part = _WORDS.get(part, part)
        if sys.platform == "darwin":
            part = _MAC.get(part, part)
        parts.append(part)
    return "+".join(parts)


def cap_font(font):
    f = font_at(TINY, font, QFont.Medium)
    return f


def sizes(font):
    """(cap height, padding inside it, gap before what it does, room between two hints)."""
    h = QFontMetricsF(font).height()
    return h + 3, round(h * 0.4), round(h * 0.42), round(h * 1.2)


def width(font, key, label, tail=""):
    fm, kfm = QFontMetricsF(font), QFontMetricsF(cap_font(font))
    cap_h, pad, gap, _between = sizes(font)
    return max(cap_h, kfm.horizontalAdvance(key) + 2 * pad) + gap + fm.horizontalAdvance(label) \
        + (fm.horizontalAdvance(" " + tail) if tail else 0)


def cap(p, cx, cy, key, font, theme, glyph=None, room=None):
    """Just the key, in its cap, centred on (cx, cy) - under an Actions tile's name; glyph: a small line icon
    before it (glyphs.py - whose key it is). Never wider than `room`: the icon goes first, then the key's words
    get smaller (Ctrl+Shift+Enter in a small tile). Its rect."""
    text = QColor(theme["picker_text"])
    surface = QColor(text)
    surface.setAlphaF(0.075)
    kf = cap_font(font)
    kfm = QFontMetricsF(kf)
    cap_h, pad, _gap, _between = sizes(font)

    def needed(with_glyph):
        icon = cap_h * 0.62 if with_glyph else 0.0
        return max(cap_h, kfm.horizontalAdvance(key) + 2 * pad + (icon + pad * 0.6 if with_glyph else 0))
    if room is not None and glyph and needed(True) > room:
        glyph = None
    if room is not None and needed(False) > room:
        kf.setPointSizeF(kf.pointSizeF() * max(0.6, (room - 2 * pad) / max(1.0, kfm.horizontalAdvance(key))))
        kfm = QFontMetricsF(kf)
    icon = cap_h * 0.62 if glyph else 0.0
    w = max(cap_h, kfm.horizontalAdvance(key) + 2 * pad + (icon + pad * 0.6 if glyph else 0))
    rect = QRectF(cx - w / 2, cy - cap_h / 2, w, cap_h)
    p.setPen(Qt.NoPen)
    p.setBrush(surface)
    p.drawRoundedRect(rect, cap_h * 0.26, cap_h * 0.26)
    muted = QColor(text)
    muted.setAlphaF(0.78)
    if glyph:
        from .glyphs import draw_glyph
        draw_glyph(p, glyph, QPointF(rect.left() + pad + icon / 2, rect.center().y()), icon, QColor(theme["picker_folder"]))
    p.setFont(kf)
    p.setPen(muted)
    p.drawText(rect.adjusted(icon + pad * 0.6 if glyph else 0, 0, 0, 0), Qt.AlignCenter, key)
    return rect


def draw(p, x, cy, key, label, font, theme, tail=""):
    """One hint at x, centred on cy: the key in its cap, what it does beside it (and `tail` in the accent).
    Returns where the next one starts."""
    text, muted = QColor(theme["picker_text"]), QColor(theme["picker_folder"])
    surface = QColor(text)
    surface.setAlphaF(0.075)
    fm, kf = QFontMetricsF(font), cap_font(font)
    kfm = QFontMetricsF(kf)
    cap_h, pad, gap, between = sizes(font)
    cap = QRectF(x, cy - cap_h / 2, max(cap_h, kfm.horizontalAdvance(key) + 2 * pad), cap_h)
    p.setPen(Qt.NoPen)
    p.setBrush(surface)
    p.drawRoundedRect(cap, cap_h * 0.26, cap_h * 0.26)
    p.setFont(kf)
    p.setPen(text)
    p.drawText(cap, Qt.AlignCenter, key)
    x = cap.right() + gap
    baseline = cy + (fm.ascent() - fm.descent()) / 2
    p.setFont(font)
    p.setPen(muted)
    p.drawText(QPointF(x, baseline), label)
    x += fm.horizontalAdvance(label)
    if tail:
        p.setPen(QColor(theme.get("picker_accent", theme["picker_text"])))
        p.drawText(QPointF(x, baseline), " " + tail)
        x += fm.horizontalAdvance(" " + tail)
    return x + between
