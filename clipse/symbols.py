"""The small clip-type symbols drawn inside each row's tag (waveform for
audio, play triangle for video, ...). Drawn with QPainter rather than
taken from a font, so they look the same on every OS and at every size.

A user who types their own icon in Settings -> Appearance -> Icons gets
that character instead (see clip_model.ClipItemDelegate)."""
import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainterPath, QPen


def _filled(p, color):
    p.setPen(Qt.NoPen)
    p.setBrush(color)


def _audio(p, r, c):  # music note
    x, y, w, h = r.x(), r.y(), r.width(), r.height()
    _filled(p, c)
    hw, hh = w * 0.25, h * 0.17
    hx, hy = x + w * 0.36, y + h * 0.8
    p.save()
    p.translate(hx, hy)
    p.rotate(-22)
    p.drawEllipse(QPointF(0, 0), hw, hh)
    p.restore()
    sx = hx + hw * 0.88
    stem = max(1.2, w * 0.11)
    p.drawRect(QRectF(sx - stem, y + h * 0.04, stem, hy - y - h * 0.04))
    flag = QPainterPath()
    flag.moveTo(sx - stem * 0.2, y + h * 0.04)
    flag.cubicTo(sx + w * 0.12, y + h * 0.22, sx + w * 0.42, y + h * 0.3, sx + w * 0.22, y + h * 0.6)
    flag.cubicTo(sx + w * 0.3, y + h * 0.38, sx + w * 0.1, y + h * 0.32, sx - stem * 0.2, y + h * 0.3)
    flag.closeSubpath()
    p.drawPath(flag)


def _sound(p, r, c):  # sound effect: a short waveform
    x, y, w, h = r.x(), r.y(), r.width(), r.height()
    _filled(p, c)
    heights = (0.36, 0.72, 1.0, 0.56, 0.3)
    bar = w / (len(heights) * 1.75)
    step = (w - bar) / (len(heights) - 1)
    for i, k in enumerate(heights):
        bh = max(bar, h * k)
        p.drawRoundedRect(QRectF(x + i * step, y + (h - bh) / 2, bar, bh), bar / 2, bar / 2)


def _music(p, r, c):  # music: two beamed notes
    x, y, w, h = r.x(), r.y(), r.width(), r.height()
    _filled(p, c)
    hw, hh = w * 0.17, h * 0.15
    stem = max(1.1, w * 0.085)
    heads = ((x + w * 0.22, y + h * 0.84), (x + w * 0.76, y + h * 0.72))
    tops = []
    for hx, hy in heads:
        p.save()
        p.translate(hx, hy)
        p.rotate(-22)
        p.drawEllipse(QPointF(0, 0), hw, hh)
        p.restore()
        sx = hx + hw * 0.86
        top = y + h * 0.1 + (hy - heads[0][1]) * 0.5
        p.drawRect(QRectF(sx - stem, top, stem, hy - top))
        tops.append((sx, top))
    beam = QPainterPath()
    (ax, at), (bx, bt) = tops
    thick = h * 0.17
    beam.moveTo(ax - stem, at)
    beam.lineTo(bx, bt)
    beam.lineTo(bx, bt + thick)
    beam.lineTo(ax - stem, at + thick)
    beam.closeSubpath()
    p.drawPath(beam)


def _video(p, r, c):
    _filled(p, c)
    cx, cy, w, h = r.center().x(), r.center().y(), r.width(), r.height()
    path = QPainterPath()
    path.moveTo(cx - w * 0.28, cy - h * 0.42)
    path.lineTo(cx + w * 0.38, cy)
    path.lineTo(cx - w * 0.28, cy + h * 0.42)
    path.closeSubpath()
    p.drawPath(path)


def _adjustment_layers(p, r, c):  # adjustment layer: a plane lying just above another
    x, y, w, h = r.x(), r.y(), r.width(), r.height()
    gap = 0.26                      # how far below the top plane the lower one sits
    start = (1 - (0.5 + gap)) / 2   # centred

    def rhombus(top):
        path = QPainterPath()
        path.moveTo(x + w * 0.5, y + h * top)
        path.lineTo(x + w, y + h * (top + 0.25))
        path.lineTo(x + w * 0.5, y + h * (top + 0.5))
        path.lineTo(x, y + h * (top + 0.25))
        path.closeSubpath()
        return path
    back = QColor(c)
    back.setAlpha(120)
    _filled(p, back)
    p.drawPath(rhombus(start + gap))
    _filled(p, c)
    p.drawPath(rhombus(start))


def _adjustment_sliders(p, r, c):  # two sliders
    x, y, w, h = r.x(), r.y(), r.width(), r.height()
    _filled(p, c)
    for row, knob in ((0.28, 0.68), (0.72, 0.3)):
        bar_h = h * 0.14
        p.drawRoundedRect(QRectF(x, y + h * row - bar_h / 2, w, bar_h), bar_h / 2, bar_h / 2)
        p.drawEllipse(QPointF(x + w * knob, y + h * row), h * 0.2, h * 0.2)


def _adjustment_sparkle(p, r, c):  # four-point sparkle - "effect"
    cx, cy = r.center().x(), r.center().y()
    rx, ry = r.width() / 2, r.height() / 2
    _filled(p, c)
    path = QPainterPath()
    path.moveTo(cx, cy - ry)
    path.quadTo(cx + rx * 0.14, cy - ry * 0.14, cx + rx, cy)
    path.quadTo(cx + rx * 0.14, cy + ry * 0.14, cx, cy + ry)
    path.quadTo(cx - rx * 0.14, cy + ry * 0.14, cx - rx, cy)
    path.quadTo(cx - rx * 0.14, cy - ry * 0.14, cx, cy - ry)
    p.drawPath(path)


_adjustment = _adjustment_layers


def _image(p, r, c):  # mountains and a sun
    _filled(p, c)
    x, y, w, h = r.x(), r.y(), r.width(), r.height()
    path = QPainterPath()
    path.moveTo(x + w * 0.05, y + h * 0.92)
    path.lineTo(x + w * 0.36, y + h * 0.35)
    path.lineTo(x + w * 0.58, y + h * 0.7)
    path.lineTo(x + w * 0.72, y + h * 0.5)
    path.lineTo(x + w * 0.95, y + h * 0.92)
    path.closeSubpath()
    p.drawPath(path)
    p.drawEllipse(QPointF(x + w * 0.78, y + h * 0.18), w * 0.11, w * 0.11)


def _compound(p, r, c):  # two stacked clips
    x, y, w, h = r.x(), r.y(), r.width(), r.height()
    s = min(w, h) * 0.66
    back = QColor(c)
    back.setAlpha(130)
    _filled(p, back)
    p.drawRoundedRect(QRectF(x + w - s, y, s, s), s * 0.2, s * 0.2)
    _filled(p, c)
    p.drawRoundedRect(QRectF(x, y + h - s, s, s), s * 0.2, s * 0.2)


def _bin(p, r, c):  # folder
    _filled(p, c)
    x, y, w, h = r.x(), r.y(), r.width(), r.height()
    path = QPainterPath()
    path.moveTo(x, y + h * 0.95)
    path.lineTo(x, y + h * 0.1)
    path.lineTo(x + w * 0.4, y + h * 0.1)
    path.lineTo(x + w * 0.52, y + h * 0.27)
    path.lineTo(x + w, y + h * 0.27)
    path.lineTo(x + w, y + h * 0.95)
    path.closeSubpath()
    p.drawPath(path)


def _diamond(cx, cy, radius, soft=0.12):
    """A diamond with slightly rounded corners."""
    points = [(cx, cy - radius), (cx + radius, cy), (cx, cy + radius), (cx - radius, cy)]

    def between(a, b, t):
        return QPointF(a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
    path = QPainterPath()
    path.moveTo(between(points[3], points[0], 1 - soft))
    for i in range(4):
        corner, after = points[i], points[(i + 1) % 4]
        path.quadTo(QPointF(*corner), between(corner, after, soft))
        path.lineTo(between(corner, after, 1 - soft))
    path.closeSubpath()
    return path


def _selected(p, r, c):  # a diamond in a diamond - "what's selected in the Media Pool" (the first symbol for it)
    cx, cy = r.center().x(), r.center().y()
    s = min(r.width(), r.height())
    width = max(1.2, s * 0.11)
    p.setPen(QPen(c, width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.setBrush(Qt.NoBrush)
    p.drawPath(_diamond(cx, cy, s / 2 - width / 2))
    _filled(p, c)
    p.drawPath(_diamond(cx, cy, s * 0.2))


def _script(p, r, c):  # terminal prompt  >_
    x, y, w, h = r.x(), r.y(), r.width(), r.height()
    p.setPen(QPen(c, max(1.2, h * 0.16), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.setBrush(Qt.NoBrush)
    path = QPainterPath()
    path.moveTo(x + w * 0.1, y + h * 0.18)
    path.lineTo(x + w * 0.42, y + h * 0.5)
    path.lineTo(x + w * 0.1, y + h * 0.82)
    p.drawPath(path)
    p.drawLine(QPointF(x + w * 0.55, y + h * 0.85), QPointF(x + w * 0.92, y + h * 0.85))


def _macro(p, r, c):  # two Fusion nodes, connected
    x, y, w, h = r.x(), r.y(), r.width(), r.height()
    s = min(w, h) * 0.42
    p.setPen(QPen(c, max(1.0, h * 0.12)))
    p.drawLine(QPointF(x + s / 2, y + s / 2), QPointF(x + w - s / 2, y + h - s / 2))
    _filled(p, c)
    p.drawRoundedRect(QRectF(x, y, s, s), s * 0.2, s * 0.2)
    p.drawRoundedRect(QRectF(x + w - s, y + h - s, s, s), s * 0.2, s * 0.2)


def _comp(p, r, c):  # three nodes merging into one
    x, y, w, h = r.x(), r.y(), r.width(), r.height()
    s = min(w, h) * 0.34
    p.setPen(QPen(c, max(1.0, h * 0.11)))
    end = QPointF(x + w - s / 2, y + h / 2)
    p.drawLine(QPointF(x + s / 2, y + s / 2), end)
    p.drawLine(QPointF(x + s / 2, y + h - s / 2), end)
    _filled(p, c)
    for rx, ry in ((x, y), (x, y + h - s), (x + w - s, y + h / 2 - s / 2)):
        p.drawRoundedRect(QRectF(rx, ry, s, s), s * 0.2, s * 0.2)


def _node(p, r, c):  # one Fusion node, with its input and output
    x, y, w, h = r.x(), r.y(), r.width(), r.height()
    cy = y + h / 2
    p.setPen(QPen(c, max(1.0, h * 0.12), Qt.SolidLine, Qt.RoundCap))
    p.drawLine(QPointF(x, cy), QPointF(x + w * 0.2, cy))
    p.drawLine(QPointF(x + w * 0.8, cy), QPointF(x + w, cy))
    _filled(p, c)
    p.drawRoundedRect(QRectF(x + w * 0.2, y + h * 0.2, w * 0.6, h * 0.6), h * 0.12, h * 0.12)


def _timeline(p, r, c):  # clips on three tracks
    x, y, w, h = r.x(), r.y(), r.width(), r.height()
    _filled(p, c)
    bar = h * 0.22
    for row, (a, b) in enumerate(((0.0, 0.55), (0.3, 1.0), (0.1, 0.7))):
        top = y + row * (h - bar) / 2
        p.drawRoundedRect(QRectF(x + w * a, top, w * (b - a), bar), bar * 0.3, bar * 0.3)


def _marker(p, r, c):  # a timeline marker: a flag with a point at the bottom
    x, y, w, h = r.x(), r.y(), r.width(), r.height()
    _filled(p, c)
    path = QPainterPath()
    path.moveTo(x + w * 0.12, y)
    path.lineTo(x + w * 0.88, y)
    path.lineTo(x + w * 0.88, y + h * 0.6)
    path.lineTo(x + w * 0.5, y + h)
    path.lineTo(x + w * 0.12, y + h * 0.6)
    path.closeSubpath()
    p.drawPath(path)


def _layout(p, r, c):  # Resolve's window: a bar on top, a big panel and two side by side under it
    x, y, w, h = r.x(), r.y(), r.width(), r.height()
    _filled(p, c)
    gap = h * 0.12
    p.drawRoundedRect(QRectF(x, y, w, h * 0.2), h * 0.05, h * 0.05)
    p.drawRoundedRect(QRectF(x, y + h * 0.2 + gap, w * 0.62, h * 0.8 - gap), h * 0.06, h * 0.06)
    p.drawRoundedRect(QRectF(x + w * 0.62 + gap, y + h * 0.2 + gap, w * 0.38 - gap, h * 0.8 - gap), h * 0.06, h * 0.06)


def _title(p, r, c):  # a capital T
    x, y, w, h = r.x(), r.y(), r.width(), r.height()
    _filled(p, c)
    bar = h * 0.22
    p.drawRoundedRect(QRectF(x + w * 0.1, y, w * 0.8, bar), bar * 0.25, bar * 0.25)
    p.drawRoundedRect(QRectF(x + w * 0.5 - bar / 2, y, bar, h), bar * 0.25, bar * 0.25)


def _solid(p, r, c):  # a solid colour: a filled frame
    x, y, w, h = r.x(), r.y(), r.width(), r.height()
    _filled(p, c)
    p.drawRoundedRect(QRectF(x, y + h * 0.08, w, h * 0.84), w * 0.16, w * 0.16)


def _template(p, r, c):  # a layout: four tiles
    x, y, w, h = r.x(), r.y(), r.width(), r.height()
    _filled(p, c)
    gap = w * 0.14
    tw, th = (w - gap) / 2, (h - gap) / 2
    for i, (cx, cy) in enumerate(((0, 0), (1, 0), (0, 1), (1, 1))):
        tile = QColor(c)
        if i == 3:
            tile.setAlpha(110)
        _filled(p, tile)
        p.drawRoundedRect(QRectF(x + cx * (tw + gap), y + cy * (th + gap), tw, th), tw * 0.22, tw * 0.22)


def _action(p, r, c):  # a lightning bolt - "do something"
    x, y, w, h = r.x(), r.y(), r.width(), r.height()
    _filled(p, c)
    path = QPainterPath()
    path.moveTo(x + w * 0.62, y)
    path.lineTo(x + w * 0.12, y + h * 0.58)
    path.lineTo(x + w * 0.46, y + h * 0.58)
    path.lineTo(x + w * 0.36, y + h)
    path.lineTo(x + w * 0.88, y + h * 0.4)
    path.lineTo(x + w * 0.54, y + h * 0.4)
    path.closeSubpath()
    p.drawPath(path)


def _project(p, r, c):  # clapperboard
    x, y, w, h = r.x(), r.y(), r.width(), r.height()
    _filled(p, c)
    p.drawRoundedRect(QRectF(x, y + h * 0.36, w, h * 0.64), h * 0.1, h * 0.1)
    top = QPainterPath()
    top.moveTo(x, y + h * 0.26)
    top.lineTo(x + w * 0.9, y)
    top.lineTo(x + w * 0.96, y + h * 0.14)
    top.lineTo(x + w * 0.06, y + h * 0.4)
    top.closeSubpath()
    p.drawPath(top)


def _star_path(r, inner=0.48):
    path = QPainterPath()
    cx, cy, rad = r.center().x(), r.center().y() + r.height() * 0.04, min(r.width(), r.height()) / 2
    for i in range(10):
        a = -math.pi / 2 + i * math.pi / 5
        k = rad if i % 2 == 0 else rad * inner
        pt = QPointF(cx + k * math.cos(a), cy + k * math.sin(a))
        if i == 0:
            path.moveTo(pt)
        else:
            path.lineTo(pt)
    path.closeSubpath()
    return path


def draw_star(p, r, color, style="line"):
    """Favourite marker. "line": a thin, sharp-pointed outline star.
    "fill": a solid star. "dot": just a small dot."""
    p.save()
    p.setRenderHint(p.RenderHint.Antialiasing)
    if style == "dot":
        p.setPen(Qt.NoPen)
        p.setBrush(color)
        rad = min(r.width(), r.height()) * 0.2
        p.drawEllipse(r.center(), rad, rad)
    elif style == "fill":
        # a hair of rounding on the points - between crisp and soft
        width = max(0.6, r.height() * 0.05)
        p.setPen(QPen(color, width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.setBrush(color)
        p.drawPath(_star_path(r.adjusted(width / 2, width / 2, -width / 2, -width / 2), inner=0.42))
    else:
        width = max(1.0, r.height() * 0.08)
        p.setPen(QPen(color, width, Qt.SolidLine, Qt.FlatCap, Qt.MiterJoin))
        p.setBrush(Qt.NoBrush)
        p.drawPath(_star_path(r.adjusted(width, width, -width, -width), inner=0.4))
    p.restore()


def draw_check(p, r, color):
    """Staged tick - a thin, slightly open check mark."""
    p.save()
    p.setRenderHint(p.RenderHint.Antialiasing)
    p.setPen(QPen(color, max(1.2, r.height() * 0.14), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.setBrush(Qt.NoBrush)
    path = QPainterPath()
    path.moveTo(r.x() + r.width() * 0.06, r.y() + r.height() * 0.56)
    path.lineTo(r.x() + r.width() * 0.36, r.y() + r.height() * 0.84)
    path.lineTo(r.x() + r.width() * 0.94, r.y() + r.height() * 0.2)
    p.drawPath(path)
    p.restore()


def _expression(p, r, c):  # code that moves things: a wave between two brackets
    x, y, w, h = r.x(), r.y(), r.width(), r.height()
    p.setPen(QPen(c, max(1.2, h * 0.13), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.setBrush(Qt.NoBrush)
    for edge, sx in ((0.0, 1), (1.0, -1)):
        bracket = QPainterPath()
        bracket.moveTo(x + w * edge + sx * w * 0.16, y)
        bracket.lineTo(x + w * edge, y)
        bracket.lineTo(x + w * edge, y + h)
        bracket.lineTo(x + w * edge + sx * w * 0.16, y + h)
        p.drawPath(bracket)
    wave = QPainterPath()
    wave.moveTo(x + w * 0.24, y + h * 0.5)
    wave.cubicTo(x + w * 0.36, y + h * 0.05, x + w * 0.44, y + h * 0.05, x + w * 0.5, y + h * 0.5)
    wave.cubicTo(x + w * 0.56, y + h * 0.95, x + w * 0.64, y + h * 0.95, x + w * 0.76, y + h * 0.5)
    p.drawPath(wave)


def _shortcut(p, r, c):  # a gear - a way into Clipse itself (a Settings page, Actions, Insert as ...)
    _filled(p, c)
    cx, cy = r.center().x(), r.center().y()
    s = min(r.width(), r.height())
    outer, inner, teeth = s * 0.5, s * 0.38, 8
    path = QPainterPath()
    for k in range(teeth):
        a = k * 2 * math.pi / teeth
        for i, (radius, off) in enumerate(((inner, -0.25), (outer, -0.14), (outer, 0.14), (inner, 0.25))):
            x, y = cx + radius * math.cos(a + off), cy + radius * math.sin(a + off)
            path.moveTo(x, y) if k == 0 and i == 0 else path.lineTo(x, y)
    path.closeSubpath()
    path.addEllipse(QPointF(cx, cy), s * 0.16, s * 0.16)  # (odd-even fill: the hole)
    p.drawPath(path)


_DRAW = {"audio": _audio, "music": _music, "sound": _sound, "video": _video, "adjustment": _adjustment, "image": _image,
         "compound": _compound, "bin": _bin, "selected": _selected, "script": _script,
         "macro": _macro, "comp": _comp, "node": _node, "expression": _expression, "project": _project, "folder": _bin, "timeline": _timeline, "title": _title,
         "solid": _solid,
         "marker": _marker, "layout": _layout,
         "template": _template, "action": _action, "shortcut": _shortcut}

# width/height of each symbol relative to the size it's given — some read
# better a little flatter
_ASPECT = {"adjustment": (1.0, 1.0), "audio": (0.8, 1.0), "music": (1.0, 1.0), "sound": (1.0, 0.85), "bin": (1.0, 0.8), "image": (1.0, 0.8), "script": (0.95, 0.8),
           "selected": (1.0, 1.0), "project": (1.0, 0.85), "node": (1.1, 0.8), "expression": (1.25, 0.8), "folder": (1.0, 0.8), "timeline": (1.0, 0.8), "title": (0.8, 0.85),
           "solid": (1.0, 0.8),
           "marker": (0.75, 0.95), "layout": (1.0, 0.8),
           "template": (0.9, 0.9), "action": (0.7, 1.0), "shortcut": (1.0, 1.0)}


def draw_symbol(p, category, center, size, color):
    """Draws `category`'s symbol centred on `center`, about `size` px big.
    Returns False for an unknown category."""
    fn = _DRAW.get(category)
    if fn is None:
        return False
    aw, ah = _ASPECT.get(category, (1.0, 0.85))
    w, h = size * aw, size * ah
    p.save()
    p.setRenderHint(p.RenderHint.Antialiasing)
    fn(p, QRectF(center.x() - w / 2, center.y() - h / 2, w, h), QColor(color))
    p.restore()
    return True
