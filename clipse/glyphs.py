"""Line icons for things you DO (actions, Settings pages) - one per
action, none shared, so a tile says what it does at a glance.

Kinds of clips keep their own filled symbols (symbols.py): a filled
symbol is a thing in your project, a line icon is something you can do.
Where an action and a page are about the same thing (Preview, Settings,
your keys) they share an icon on purpose.

draw_glyph(p, name, center, size, color) draws one; GLYPHS lists them."""
import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainterPath, QPen


def _pen(p, c, s, width=1.0):
    p.setPen(QPen(c, max(1.1, s * 0.085 * width), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.setBrush(Qt.NoBrush)


def _fill(p, c):
    p.setPen(Qt.NoPen)
    p.setBrush(c)


def _arrow_head(p, tip, angle, size, c):
    """A small filled arrow head at `tip`, pointing along `angle` (radians)."""
    path = QPainterPath()
    path.moveTo(tip)
    for side in (2.6, -2.6):
        path.lineTo(QPointF(tip.x() - size * math.cos(angle + side * 0.2), tip.y() - size * math.sin(angle + side * 0.2)))
    path.closeSubpath()
    _fill(p, c)
    p.drawPath(path)


# each takes (painter, x, y, s, colour) - (x, y) the top-left of an s x s box
def _insert(p, x, y, s, c):  # an arrow down onto a track
    _pen(p, c, s)
    p.drawLine(QPointF(x + s * 0.5, y + s * 0.08), QPointF(x + s * 0.5, y + s * 0.58))
    p.drawLine(QPointF(x + s * 0.3, y + s * 0.4), QPointF(x + s * 0.5, y + s * 0.6))
    p.drawLine(QPointF(x + s * 0.7, y + s * 0.4), QPointF(x + s * 0.5, y + s * 0.6))
    p.drawRoundedRect(QRectF(x + s * 0.1, y + s * 0.74, s * 0.8, s * 0.18), s * 0.06, s * 0.06)


def _picture_only(p, x, y, s, c):  # a picture: frame with a mountain
    _pen(p, c, s)
    p.drawRoundedRect(QRectF(x + s * 0.08, y + s * 0.18, s * 0.84, s * 0.64), s * 0.08, s * 0.08)
    path = QPainterPath()
    path.moveTo(x + s * 0.18, y + s * 0.72)
    path.lineTo(x + s * 0.4, y + s * 0.46)
    path.lineTo(x + s * 0.56, y + s * 0.62)
    path.lineTo(x + s * 0.66, y + s * 0.52)
    path.lineTo(x + s * 0.82, y + s * 0.72)
    p.drawPath(path)
    p.drawEllipse(QPointF(x + s * 0.7, y + s * 0.34), s * 0.05, s * 0.05)


def _sound_only(p, x, y, s, c):  # a waveform
    _pen(p, c, s)
    for i, k in enumerate((0.25, 0.55, 0.85, 0.5, 0.7, 0.3)):
        px = x + s * (0.14 + i * 0.144)
        p.drawLine(QPointF(px, y + s * (0.5 - k / 2)), QPointF(px, y + s * (0.5 + k / 2)))


def _compound(p, x, y, s, c):  # clips stacked inside one
    _pen(p, c, s)
    p.drawRoundedRect(QRectF(x + s * 0.08, y + s * 0.18, s * 0.84, s * 0.64), s * 0.08, s * 0.08)
    for top, left, right in ((0.32, 0.2, 0.62), (0.47, 0.34, 0.8), (0.62, 0.2, 0.7)):
        p.drawLine(QPointF(x + s * left, y + s * (top + 0.03)), QPointF(x + s * right, y + s * (top + 0.03)))


def _grab(p, x, y, s, c):  # a viewfinder: corners and a dot
    _pen(p, c, s)
    a, b, k = s * 0.1, s * 0.9, s * 0.24
    for cx, cy, dx, dy in ((a, a, 1, 1), (b, a, -1, 1), (a, b, 1, -1), (b, b, -1, -1)):
        p.drawLine(QPointF(x + cx, y + cy), QPointF(x + cx + dx * k, y + cy))
        p.drawLine(QPointF(x + cx, y + cy), QPointF(x + cx, y + cy + dy * k))
    _fill(p, c)
    p.drawEllipse(QPointF(x + s / 2, y + s / 2), s * 0.12, s * 0.12)


def _undo(p, x, y, s, c):  # a curved arrow back
    _pen(p, c, s)
    path = QPainterPath()
    path.moveTo(x + s * 0.24, y + s * 0.42)
    path.lineTo(x + s * 0.62, y + s * 0.42)
    path.cubicTo(x + s * 0.95, y + s * 0.42, x + s * 0.95, y + s * 0.86, x + s * 0.62, y + s * 0.86)
    path.lineTo(x + s * 0.4, y + s * 0.86)
    p.drawPath(path)
    _arrow_head(p, QPointF(x + s * 0.1, y + s * 0.42), math.pi, s * 0.26, c)


def _insert_as(p, x, y, s, c):  # clips stepping up and along - a preset
    _pen(p, c, s)
    for i in range(3):
        p.drawRoundedRect(QRectF(x + s * (0.06 + i * 0.24), y + s * (0.7 - i * 0.29), s * 0.4, s * 0.16),
                          s * 0.05, s * 0.05)


def _eye(p, x, y, s, c):  # preview
    _pen(p, c, s)
    path = QPainterPath()
    path.moveTo(x + s * 0.06, y + s * 0.5)
    path.quadTo(x + s * 0.5, y + s * 0.08, x + s * 0.94, y + s * 0.5)
    path.quadTo(x + s * 0.5, y + s * 0.92, x + s * 0.06, y + s * 0.5)
    p.drawPath(path)
    p.drawEllipse(QPointF(x + s * 0.5, y + s * 0.5), s * 0.14, s * 0.14)


def _info_card(p, x, y, s, c):  # clip info: a card of lines
    _pen(p, c, s)
    p.drawRoundedRect(QRectF(x + s * 0.12, y + s * 0.12, s * 0.76, s * 0.76), s * 0.1, s * 0.1)
    for i, w in enumerate((0.44, 0.34, 0.4)):
        yy = y + s * (0.34 + i * 0.16)
        p.drawLine(QPointF(x + s * 0.28, yy), QPointF(x + s * (0.28 + w), yy))


def _stage(p, x, y, s, c):  # a tick in a box
    _pen(p, c, s)
    p.drawRoundedRect(QRectF(x + s * 0.12, y + s * 0.12, s * 0.76, s * 0.76), s * 0.16, s * 0.16)
    path = QPainterPath()
    path.moveTo(x + s * 0.3, y + s * 0.52)
    path.lineTo(x + s * 0.45, y + s * 0.66)
    path.lineTo(x + s * 0.71, y + s * 0.36)
    p.drawPath(path)


def _star(p, x, y, s, c):
    _pen(p, c, s)
    path = QPainterPath()
    cx, cy, r = x + s / 2, y + s * 0.53, s * 0.44
    for i in range(10):
        a = -math.pi / 2 + i * math.pi / 5
        k = r if i % 2 == 0 else r * 0.45
        pt = QPointF(cx + k * math.cos(a), cy + k * math.sin(a))
        path.moveTo(pt) if i == 0 else path.lineTo(pt)
    path.closeSubpath()
    p.drawPath(path)


def _folder_path(x, y, s):
    path = QPainterPath()
    path.moveTo(x + s * 0.08, y + s * 0.82)
    path.lineTo(x + s * 0.08, y + s * 0.2)
    path.lineTo(x + s * 0.38, y + s * 0.2)
    path.lineTo(x + s * 0.48, y + s * 0.32)
    path.lineTo(x + s * 0.92, y + s * 0.32)
    path.lineTo(x + s * 0.92, y + s * 0.82)
    path.closeSubpath()
    return path


def _folder(p, x, y, s, c):
    _pen(p, c, s)
    p.drawPath(_folder_path(x, y, s))


def _reveal_pool(p, x, y, s, c):  # a bin with a target in it - "show me where it is"
    _pen(p, c, s)
    p.drawPath(_folder_path(x, y, s))
    p.drawEllipse(QPointF(x + s * 0.5, y + s * 0.58), s * 0.12, s * 0.12)


def _organise(p, x, y, s, c):  # organise project: a bin with its clips in rows, each with its colour chip
    _pen(p, c, s)
    p.drawPath(_folder_path(x, y, s))
    for i, end in enumerate((0.74, 0.64, 0.7)):
        row = y + s * (0.46 + i * 0.13)
        p.drawLine(QPointF(x + s * 0.38, row), QPointF(x + s * end, row))
    _fill(p, c)
    for i in range(3):
        k = s * 0.08
        p.drawRoundedRect(QRectF(x + s * 0.22, y + s * (0.46 + i * 0.13) - k / 2, k, k), k * 0.25, k * 0.25)


def _file_manager(p, x, y, s, c):  # a folder with an arrow out of it
    _pen(p, c, s)
    path = QPainterPath()
    path.moveTo(x + s * 0.5, y + s * 0.82)
    path.lineTo(x + s * 0.08, y + s * 0.82)
    path.lineTo(x + s * 0.08, y + s * 0.2)
    path.lineTo(x + s * 0.36, y + s * 0.2)
    path.lineTo(x + s * 0.46, y + s * 0.32)
    path.lineTo(x + s * 0.6, y + s * 0.32)
    p.drawPath(path)
    p.drawLine(QPointF(x + s * 0.54, y + s * 0.66), QPointF(x + s * 0.86, y + s * 0.34))
    _arrow_head(p, QPointF(x + s * 0.92, y + s * 0.28), -math.pi / 4, s * 0.26, c)


def _headphones(p, x, y, s, c):  # listening
    _pen(p, c, s)
    path = QPainterPath()
    path.moveTo(x + s * 0.16, y + s * 0.62)
    path.lineTo(x + s * 0.16, y + s * 0.5)
    path.cubicTo(x + s * 0.16, y + s * 0.06, x + s * 0.84, y + s * 0.06, x + s * 0.84, y + s * 0.5)
    path.lineTo(x + s * 0.84, y + s * 0.62)
    p.drawPath(path)
    _fill(p, c)
    p.drawRoundedRect(QRectF(x + s * 0.08, y + s * 0.56, s * 0.2, s * 0.32), s * 0.06, s * 0.06)
    p.drawRoundedRect(QRectF(x + s * 0.72, y + s * 0.56, s * 0.2, s * 0.32), s * 0.06, s * 0.06)


def _loop(p, x, y, s, c):  # infinity
    _pen(p, c, s)
    path = QPainterPath()
    for i in range(61):
        t = i / 60 * 2 * math.pi
        d = 1 + math.sin(t) ** 2
        pt = QPointF(x + s * 0.5 + s * 0.42 * math.cos(t) / d, y + s * 0.5 + s * 0.42 * math.sin(t) * math.cos(t) / d)
        path.moveTo(pt) if i == 0 else path.lineTo(pt)
    p.drawPath(path)


def _metronome(p, x, y, s, c):  # analyse sounds: tempo
    _pen(p, c, s)
    path = QPainterPath()
    path.moveTo(x + s * 0.4, y + s * 0.1)
    path.lineTo(x + s * 0.6, y + s * 0.1)
    path.lineTo(x + s * 0.84, y + s * 0.9)
    path.lineTo(x + s * 0.16, y + s * 0.9)
    path.closeSubpath()
    p.drawPath(path)
    p.drawLine(QPointF(x + s * 0.5, y + s * 0.74), QPointF(x + s * 0.74, y + s * 0.26))
    p.drawLine(QPointF(x + s * 0.24, y + s * 0.74), QPointF(x + s * 0.76, y + s * 0.74))


def _node_box(p, r, s):
    p.drawRoundedRect(r, s * 0.05, s * 0.05)


def _tidy(p, x, y, s, c):  # three nodes in a straight line
    _pen(p, c, s)
    w = s * 0.22
    for i in range(3):
        _node_box(p, QRectF(x + s * (0.04 + i * 0.36), y + s * 0.5 - w / 2, w, w), s)
    for i in range(2):
        p.drawLine(QPointF(x + s * (0.26 + i * 0.36), y + s * 0.5), QPointF(x + s * (0.4 + i * 0.36), y + s * 0.5))


def _pull_out(p, x, y, s, c):  # a node lifted out of the line, the line closed under it
    _pen(p, c, s)
    w = s * 0.22
    _node_box(p, QRectF(x + s * 0.04, y + s * 0.7 - w / 2, w, w), s)
    _node_box(p, QRectF(x + s * 0.74, y + s * 0.7 - w / 2, w, w), s)
    p.drawLine(QPointF(x + s * 0.26, y + s * 0.7), QPointF(x + s * 0.74, y + s * 0.7))
    _node_box(p, QRectF(x + s * 0.39, y + s * 0.1, w, w), s)
    p.drawLine(QPointF(x + s * 0.5, y + s * 0.5), QPointF(x + s * 0.5, y + s * 0.38))
    _arrow_head(p, QPointF(x + s * 0.5, y + s * 0.34), -math.pi / 2, s * 0.18, c)


def _add_node(p, x, y, s, c):
    _pen(p, c, s)
    _node_box(p, QRectF(x + s * 0.14, y + s * 0.14, s * 0.72, s * 0.72), s * 2)
    p.drawLine(QPointF(x + s * 0.5, y + s * 0.32), QPointF(x + s * 0.5, y + s * 0.68))
    p.drawLine(QPointF(x + s * 0.32, y + s * 0.5), QPointF(x + s * 0.68, y + s * 0.5))


def _templates(p, x, y, s, c):
    _pen(p, c, s)
    k = s * 0.36
    for cx, cy in ((0.1, 0.1), (0.54, 0.1), (0.1, 0.54), (0.54, 0.54)):
        p.drawRoundedRect(QRectF(x + s * cx, y + s * cy, k, k), s * 0.06, s * 0.06)


def _checkup(p, x, y, s, c):  # project check-up: a clipboard with a tick
    _pen(p, c, s)
    p.drawRoundedRect(QRectF(x + s * 0.18, y + s * 0.16, s * 0.64, s * 0.74), s * 0.08, s * 0.08)
    p.drawRoundedRect(QRectF(x + s * 0.36, y + s * 0.08, s * 0.28, s * 0.16), s * 0.05, s * 0.05)
    path = QPainterPath()
    path.moveTo(x + s * 0.34, y + s * 0.56)
    path.lineTo(x + s * 0.46, y + s * 0.68)
    path.lineTo(x + s * 0.68, y + s * 0.42)
    p.drawPath(path)


def _pages(p, x, y, s, c):  # go to page: Resolve's row of page buttons, one picked
    _pen(p, c, s)
    p.drawRoundedRect(QRectF(x + s * 0.06, y + s * 0.3, s * 0.88, s * 0.4), s * 0.1, s * 0.1)
    _fill(p, c)
    for i, r in enumerate((0.045, 0.085, 0.045)):
        p.drawEllipse(QPointF(x + s * (0.27 + i * 0.23), y + s * 0.5), s * r, s * r)


def _render(p, x, y, s, c):  # render: a frame with an arrow out of it
    _pen(p, c, s)
    path = QPainterPath()
    path.moveTo(x + s * 0.5, y + s * 0.26)
    path.lineTo(x + s * 0.2, y + s * 0.26)
    path.quadTo(x + s * 0.1, y + s * 0.26, x + s * 0.1, y + s * 0.36)
    path.lineTo(x + s * 0.1, y + s * 0.78)
    path.quadTo(x + s * 0.1, y + s * 0.88, x + s * 0.2, y + s * 0.88)
    path.lineTo(x + s * 0.64, y + s * 0.88)
    path.quadTo(x + s * 0.74, y + s * 0.88, x + s * 0.74, y + s * 0.78)
    path.lineTo(x + s * 0.74, y + s * 0.52)
    p.drawPath(path)
    p.drawLine(QPointF(x + s * 0.44, y + s * 0.56), QPointF(x + s * 0.88, y + s * 0.12))
    p.drawLine(QPointF(x + s * 0.62, y + s * 0.12), QPointF(x + s * 0.88, y + s * 0.12))
    p.drawLine(QPointF(x + s * 0.88, y + s * 0.12), QPointF(x + s * 0.88, y + s * 0.38))


def _plus(p, cx, cy, s, c):
    p.drawLine(QPointF(cx - s * 0.12, cy), QPointF(cx + s * 0.12, cy))
    p.drawLine(QPointF(cx, cy - s * 0.12), QPointF(cx, cy + s * 0.12))


def _new_timeline(p, x, y, s, c):  # two tracks and a plus
    _pen(p, c, s)
    p.drawRoundedRect(QRectF(x + s * 0.06, y + s * 0.42, s * 0.62, s * 0.18), s * 0.05, s * 0.05)
    p.drawRoundedRect(QRectF(x + s * 0.06, y + s * 0.7, s * 0.88, s * 0.18), s * 0.05, s * 0.05)
    _plus(p, x + s * 0.76, y + s * 0.22, s, c)


def _dup_timeline(p, x, y, s, c):  # a timeline, and the same again behind it
    _pen(p, c, s)
    p.drawRoundedRect(QRectF(x + s * 0.06, y + s * 0.36, s * 0.66, s * 0.52), s * 0.07, s * 0.07)
    p.drawLine(QPointF(x + s * 0.18, y + s * 0.54), QPointF(x + s * 0.6, y + s * 0.54))
    p.drawLine(QPointF(x + s * 0.18, y + s * 0.7), QPointF(x + s * 0.46, y + s * 0.7))
    path = QPainterPath()
    path.moveTo(x + s * 0.28, y + s * 0.24)
    path.lineTo(x + s * 0.28, y + s * 0.2)
    path.quadTo(x + s * 0.28, y + s * 0.12, x + s * 0.36, y + s * 0.12)
    path.lineTo(x + s * 0.86, y + s * 0.12)
    path.quadTo(x + s * 0.94, y + s * 0.12, x + s * 0.94, y + s * 0.2)
    path.lineTo(x + s * 0.94, y + s * 0.56)
    path.quadTo(x + s * 0.94, y + s * 0.64, x + s * 0.86, y + s * 0.64)
    path.lineTo(x + s * 0.84, y + s * 0.64)
    p.drawPath(path)


def _add_video_track(p, x, y, s, c):  # a track with a picture in it, and a plus
    _pen(p, c, s)
    p.drawRoundedRect(QRectF(x + s * 0.06, y + s * 0.5, s * 0.88, s * 0.36), s * 0.07, s * 0.07)
    path = QPainterPath()
    path.moveTo(x + s * 0.2, y + s * 0.78)
    path.lineTo(x + s * 0.36, y + s * 0.62)
    path.lineTo(x + s * 0.48, y + s * 0.72)
    path.lineTo(x + s * 0.58, y + s * 0.64)
    path.lineTo(x + s * 0.74, y + s * 0.78)
    p.drawPath(path)
    _plus(p, x + s * 0.76, y + s * 0.2, s, c)


def _add_audio_track(p, x, y, s, c):  # a track with a waveform in it, and a plus
    _pen(p, c, s)
    p.drawRoundedRect(QRectF(x + s * 0.06, y + s * 0.5, s * 0.88, s * 0.36), s * 0.07, s * 0.07)
    for i, h in enumerate((0.05, 0.11, 0.07, 0.12, 0.05)):
        cx = x + s * (0.24 + i * 0.13)
        p.drawLine(QPointF(cx, y + s * (0.68 - h)), QPointF(cx, y + s * (0.68 + h)))
    _plus(p, x + s * 0.76, y + s * 0.2, s, c)


def _remove_tracks(p, x, y, s, c):  # three tracks, the empty one in the middle struck out
    _pen(p, c, s)
    p.drawRoundedRect(QRectF(x + s * 0.08, y + s * 0.12, s * 0.84, s * 0.18), s * 0.05, s * 0.05)
    p.drawRoundedRect(QRectF(x + s * 0.08, y + s * 0.7, s * 0.84, s * 0.18), s * 0.05, s * 0.05)
    faint = QColor(c)
    faint.setAlphaF(faint.alphaF() * 0.45)
    _pen(p, faint, s, 0.8)
    p.drawRoundedRect(QRectF(x + s * 0.08, y + s * 0.41, s * 0.84, s * 0.18), s * 0.05, s * 0.05)
    _pen(p, c, s)
    p.drawLine(QPointF(x + s * 0.36, y + s * 0.5), QPointF(x + s * 0.64, y + s * 0.5))


def _name_tracks(p, x, y, s, c):  # a track header with a name tag on it
    _pen(p, c, s)
    p.drawRoundedRect(QRectF(x + s * 0.06, y + s * 0.3, s * 0.88, s * 0.4), s * 0.08, s * 0.08)
    p.drawLine(QPointF(x + s * 0.44, y + s * 0.3), QPointF(x + s * 0.44, y + s * 0.7))
    p.drawLine(QPointF(x + s * 0.16, y + s * 0.44), QPointF(x + s * 0.34, y + s * 0.44))
    p.drawLine(QPointF(x + s * 0.16, y + s * 0.57), QPointF(x + s * 0.28, y + s * 0.57))
    for i, h in enumerate((0.05, 0.1, 0.06)):
        cx = x + s * (0.58 + i * 0.12)
        p.drawLine(QPointF(cx, y + s * (0.5 - h)), QPointF(cx, y + s * (0.5 + h)))


def _marker(p, x, y, s, c):  # a timeline marker over the ruler
    _pen(p, c, s)
    path = QPainterPath()
    path.moveTo(x + s * 0.32, y + s * 0.1)
    path.lineTo(x + s * 0.68, y + s * 0.1)
    path.lineTo(x + s * 0.68, y + s * 0.42)
    path.lineTo(x + s * 0.5, y + s * 0.62)
    path.lineTo(x + s * 0.32, y + s * 0.42)
    path.closeSubpath()
    p.drawPath(path)
    p.drawLine(QPointF(x + s * 0.08, y + s * 0.84), QPointF(x + s * 0.92, y + s * 0.84))
    for i in range(4):
        cx = x + s * (0.2 + i * 0.2)
        p.drawLine(QPointF(cx, y + s * 0.76), QPointF(cx, y + s * 0.84))


def _clip_colour(p, x, y, s, c):  # a clip on a track, its colour chip filled in
    _pen(p, c, s)
    p.drawRoundedRect(QRectF(x + s * 0.08, y + s * 0.26, s * 0.84, s * 0.48), s * 0.08, s * 0.08)
    _fill(p, c)
    p.drawRoundedRect(QRectF(x + s * 0.08, y + s * 0.26, s * 0.84, s * 0.16), s * 0.06, s * 0.06)


def _save(p, x, y, s, c):  # save: an arrow down into a tray
    _pen(p, c, s)
    p.drawLine(QPointF(x + s * 0.5, y + s * 0.1), QPointF(x + s * 0.5, y + s * 0.6))
    p.drawLine(QPointF(x + s * 0.3, y + s * 0.42), QPointF(x + s * 0.5, y + s * 0.62))
    p.drawLine(QPointF(x + s * 0.7, y + s * 0.42), QPointF(x + s * 0.5, y + s * 0.62))
    path = QPainterPath()
    path.moveTo(x + s * 0.1, y + s * 0.62)
    path.lineTo(x + s * 0.1, y + s * 0.8)
    path.quadTo(x + s * 0.1, y + s * 0.9, x + s * 0.2, y + s * 0.9)
    path.lineTo(x + s * 0.8, y + s * 0.9)
    path.quadTo(x + s * 0.9, y + s * 0.9, x + s * 0.9, y + s * 0.8)
    path.lineTo(x + s * 0.9, y + s * 0.62)
    p.drawPath(path)


def _timeline(p, x, y, s, c):  # tracks with a playhead
    _pen(p, c, s)
    for i, (a, b) in enumerate(((0.08, 0.55), (0.3, 0.92), (0.14, 0.72))):
        yy = y + s * (0.3 + i * 0.22)
        p.drawLine(QPointF(x + s * a, yy), QPointF(x + s * b, yy))
    col = QColor(c)
    col.setAlphaF(col.alphaF() * 0.7)
    _pen(p, col, s, 0.8)
    p.drawLine(QPointF(x + s * 0.62, y + s * 0.1), QPointF(x + s * 0.62, y + s * 0.9))


def _clapper(p, x, y, s, c):  # projects
    _pen(p, c, s)
    p.drawRoundedRect(QRectF(x + s * 0.1, y + s * 0.4, s * 0.8, s * 0.48), s * 0.06, s * 0.06)
    path = QPainterPath()
    path.moveTo(x + s * 0.1, y + s * 0.4)
    path.lineTo(x + s * 0.84, y + s * 0.16)
    p.drawPath(path)
    p.drawLine(QPointF(x + s * 0.36, y + s * 0.31), QPointF(x + s * 0.46, y + s * 0.4))
    p.drawLine(QPointF(x + s * 0.6, y + s * 0.24), QPointF(x + s * 0.7, y + s * 0.33))


def _refresh(p, x, y, s, c):  # rescan
    _pen(p, c, s)
    r = QRectF(x + s * 0.14, y + s * 0.14, s * 0.72, s * 0.72)
    p.drawArc(r, 40 * 16, 140 * 16)
    p.drawArc(r, 220 * 16, 140 * 16)
    cx, cy, rad = x + s / 2, y + s / 2, s * 0.36
    for deg in (40, 220):
        a = math.radians(deg)
        tip = QPointF(cx + rad * math.cos(a), cy - rad * math.sin(a))
        _arrow_head(p, tip, -a - math.pi / 2, s * 0.22, c)
        _pen(p, c, s)


def _history(p, x, y, s, c):  # a clock with an arrow back round it
    _pen(p, c, s)
    p.drawArc(QRectF(x + s * 0.12, y + s * 0.12, s * 0.76, s * 0.76), 200 * 16, -300 * 16)
    p.drawLine(QPointF(x + s * 0.5, y + s * 0.32), QPointF(x + s * 0.5, y + s * 0.5))
    p.drawLine(QPointF(x + s * 0.5, y + s * 0.5), QPointF(x + s * 0.64, y + s * 0.6))
    a = math.radians(200)
    tip = QPointF(x + s * 0.5 + s * 0.38 * math.cos(a), y + s * 0.5 - s * 0.38 * math.sin(a))
    _arrow_head(p, tip, math.pi / 2 + 0.3, s * 0.22, c)


def _keyboard(p, x, y, s, c):
    _pen(p, c, s)
    p.drawRoundedRect(QRectF(x + s * 0.06, y + s * 0.24, s * 0.88, s * 0.54), s * 0.08, s * 0.08)
    _fill(p, c)
    for row, n in ((0.4, 5), (0.54, 5)):
        for i in range(n):
            p.drawEllipse(QPointF(x + s * (0.2 + i * 0.15), y + s * row), s * 0.035, s * 0.035)
    _pen(p, c, s)
    p.drawLine(QPointF(x + s * 0.32, y + s * 0.66), QPointF(x + s * 0.68, y + s * 0.66))


def _compass(p, x, y, s, c):  # the tour
    _pen(p, c, s)
    p.drawEllipse(QPointF(x + s / 2, y + s / 2), s * 0.4, s * 0.4)
    path = QPainterPath()
    path.moveTo(x + s * 0.66, y + s * 0.34)
    path.lineTo(x + s * 0.55, y + s * 0.55)
    path.lineTo(x + s * 0.34, y + s * 0.66)
    path.lineTo(x + s * 0.45, y + s * 0.45)
    path.closeSubpath()
    _fill(p, c)
    p.drawPath(path)


def _reset_place(p, x, y, s, c):  # a window with arrows out to its corners
    _pen(p, c, s)
    p.drawRoundedRect(QRectF(x + s * 0.3, y + s * 0.3, s * 0.4, s * 0.4), s * 0.05, s * 0.05)
    for dx, dy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
        a = QPointF(x + s * (0.5 + dx * 0.26), y + s * (0.5 + dy * 0.26))
        b = QPointF(x + s * (0.5 + dx * 0.42), y + s * (0.5 + dy * 0.42))
        p.drawLine(a, b)


def _gear(p, x, y, s, c):
    _pen(p, c, s)
    cx, cy = x + s / 2, y + s / 2
    path = QPainterPath()
    teeth = 8
    for i in range(teeth * 4 + 1):
        a = i / (teeth * 4) * 2 * math.pi
        rad = s * (0.44 if (i % 4) in (1, 2) else 0.34)
        pt = QPointF(cx + rad * math.cos(a), cy + rad * math.sin(a))
        path.moveTo(pt) if i == 0 else path.lineTo(pt)
    p.drawPath(path)
    p.drawEllipse(QPointF(cx, cy), s * 0.13, s * 0.13)


def _gear_fine(p, x, y, s, c):  # the picker's bar: the Settings gear a little crisper - a finer line, square corners
    p.setPen(QPen(c, max(1.05, s * 0.07), Qt.SolidLine, Qt.FlatCap, Qt.MiterJoin))
    p.setBrush(Qt.NoBrush)
    cx, cy = x + s / 2, y + s / 2
    path = QPainterPath()
    teeth = 8
    for i in range(teeth * 4 + 1):  # (the same gear as Settings' own, _gear)
        a = i / (teeth * 4) * 2 * math.pi
        rad = s * (0.44 if (i % 4) in (1, 2) else 0.34)
        pt = QPointF(cx + rad * math.cos(a), cy + rad * math.sin(a))
        path.moveTo(pt) if i == 0 else path.lineTo(pt)
    p.drawPath(path)
    p.drawEllipse(QPointF(cx, cy), s * 0.13, s * 0.13)


def _screen_play(p, x, y, s, c):  # the Preview page
    _pen(p, c, s)
    p.drawRoundedRect(QRectF(x + s * 0.06, y + s * 0.16, s * 0.88, s * 0.62), s * 0.08, s * 0.08)
    path = QPainterPath()
    path.moveTo(x + s * 0.42, y + s * 0.34)
    path.lineTo(x + s * 0.62, y + s * 0.47)
    path.lineTo(x + s * 0.42, y + s * 0.6)
    path.closeSubpath()
    _fill(p, c)
    p.drawPath(path)


def _speaker(p, x, y, s, c):  # the Sound page
    _pen(p, c, s)
    path = QPainterPath()
    path.moveTo(x + s * 0.1, y + s * 0.38)
    path.lineTo(x + s * 0.26, y + s * 0.38)
    path.lineTo(x + s * 0.46, y + s * 0.18)
    path.lineTo(x + s * 0.46, y + s * 0.82)
    path.lineTo(x + s * 0.26, y + s * 0.62)
    path.lineTo(x + s * 0.1, y + s * 0.62)
    path.closeSubpath()
    p.drawPath(path)
    p.drawArc(QRectF(x + s * 0.4, y + s * 0.3, s * 0.3, s * 0.4), -50 * 16, 100 * 16)
    p.drawArc(QRectF(x + s * 0.36, y + s * 0.14, s * 0.52, s * 0.72), -50 * 16, 100 * 16)


def _palette(p, x, y, s, c):  # Appearance
    _pen(p, c, s)
    path = QPainterPath()
    path.moveTo(x + s * 0.5, y + s * 0.08)
    path.cubicTo(x + s * 0.98, y + s * 0.08, x + s * 1.0, y + s * 0.62, x + s * 0.72, y + s * 0.62)
    path.cubicTo(x + s * 0.56, y + s * 0.62, x + s * 0.58, y + s * 0.92, x + s * 0.44, y + s * 0.92)
    path.cubicTo(x + s * 0.14, y + s * 0.92, x + s * 0.04, y + s * 0.66, x + s * 0.06, y + s * 0.48)
    path.cubicTo(x + s * 0.08, y + s * 0.24, x + s * 0.26, y + s * 0.08, x + s * 0.5, y + s * 0.08)
    p.drawPath(path)
    _fill(p, c)
    for px, py in ((0.3, 0.32), (0.52, 0.24), (0.72, 0.36), (0.24, 0.56)):
        p.drawEllipse(QPointF(x + s * px, y + s * py), s * 0.06, s * 0.06)


def _terminal(p, x, y, s, c):  # Scripts: >_ in a window
    _pen(p, c, s)
    p.drawRoundedRect(QRectF(x + s * 0.06, y + s * 0.14, s * 0.88, s * 0.72), s * 0.1, s * 0.1)
    path = QPainterPath()
    path.moveTo(x + s * 0.24, y + s * 0.36)
    path.lineTo(x + s * 0.4, y + s * 0.5)
    path.lineTo(x + s * 0.24, y + s * 0.64)
    p.drawPath(path)
    p.drawLine(QPointF(x + s * 0.48, y + s * 0.66), QPointF(x + s * 0.72, y + s * 0.66))


def _prefix(p, x, y, s, c):  # Search Prefixes: a magnifier and a colon
    _pen(p, c, s)
    p.drawEllipse(QPointF(x + s * 0.4, y + s * 0.4), s * 0.27, s * 0.27)
    p.drawLine(QPointF(x + s * 0.6, y + s * 0.6), QPointF(x + s * 0.88, y + s * 0.88))
    _fill(p, c)
    p.drawEllipse(QPointF(x + s * 0.4, y + s * 0.3), s * 0.045, s * 0.045)
    p.drawEllipse(QPointF(x + s * 0.4, y + s * 0.5), s * 0.045, s * 0.045)


def _stats(p, x, y, s, c):
    _pen(p, c, s)
    for i, k in enumerate((0.3, 0.55, 0.42, 0.75)):
        px = x + s * (0.18 + i * 0.21)
        p.drawLine(QPointF(px, y + s * 0.86), QPointF(px, y + s * (0.86 - k)))


def _about(p, x, y, s, c):
    _pen(p, c, s)
    p.drawEllipse(QPointF(x + s / 2, y + s / 2), s * 0.4, s * 0.4)
    p.drawLine(QPointF(x + s / 2, y + s * 0.46), QPointF(x + s / 2, y + s * 0.7))
    _fill(p, c)
    p.drawEllipse(QPointF(x + s / 2, y + s * 0.32), s * 0.05, s * 0.05)


def _search(p, x, y, s, c):  # a magnifier
    _pen(p, c, s)
    p.drawEllipse(QPointF(x + s * 0.42, y + s * 0.42), s * 0.28, s * 0.28)
    p.drawLine(QPointF(x + s * 0.63, y + s * 0.63), QPointF(x + s * 0.9, y + s * 0.9))


def _adj_base(p, x, y, s, c, layer, between=False, playhead=None, nodes=False):
    """A clip on a track, and an adjustment layer above it - or, with nodes, a Fusion composition
    (two nodes joined up inside it)."""
    _pen(p, c, s)
    p.drawRoundedRect(QRectF(x + s * 0.06, y + s * 0.7, s * 0.88, s * 0.2), s * 0.05, s * 0.05)
    a, b = layer
    if between:
        col = QColor(c)
        col.setAlphaF(col.alphaF() * 0.5)
        p.setPen(QPen(col, max(1.0, s * 0.06), Qt.DashLine))
        p.drawRoundedRect(QRectF(x + s * (a + 0.12), y + s * 0.44, s * (b - a - 0.24), s * 0.16), s * 0.04, s * 0.04)
        _pen(p, c, s)
    top = 0.14 if between else 0.38
    if nodes:  # two nodes joined by a wire, where the adjustment clip has its one plane
        box = s * 0.2
        mid = y + s * (top + 0.1)
        p.drawRoundedRect(QRectF(x + s * a, y + s * top, box, box), s * 0.05, s * 0.05)
        p.drawRoundedRect(QRectF(x + s * b - box, y + s * top, box, box), s * 0.05, s * 0.05)
        p.drawLine(QPointF(x + s * a + box, mid), QPointF(x + s * b - box, mid))
    else:
        p.drawRoundedRect(QRectF(x + s * a, y + s * top, s * (b - a), s * 0.2), s * 0.05, s * 0.05)
        _fill(p, c)
        p.drawRect(QRectF(x + s * (a + 0.08), y + s * (top + 0.07), s * (b - a - 0.16), s * 0.06))
    if playhead is not None:
        col = QColor(c)
        col.setAlphaF(col.alphaF() * 0.75)
        _pen(p, col, s, 0.8)
        p.drawLine(QPointF(x + s * playhead, y + s * 0.04), QPointF(x + s * playhead, y + s * 0.96))


def _adj_over(p, x, y, s, c):
    _adj_base(p, x, y, s, c, (0.22, 0.78))


def _adj_footage(p, x, y, s, c):
    _adj_base(p, x, y, s, c, (0.22, 0.78), between=True)


def _adj_playhead(p, x, y, s, c):
    _adj_base(p, x, y, s, c, (0.4, 0.92), playhead=0.4)


def _comp_over(p, x, y, s, c):
    _adj_base(p, x, y, s, c, (0.22, 0.78), nodes=True)


def _comp_footage(p, x, y, s, c):
    _adj_base(p, x, y, s, c, (0.22, 0.78), between=True, nodes=True)


def _comp_playhead(p, x, y, s, c):
    _adj_base(p, x, y, s, c, (0.4, 0.92), playhead=0.4, nodes=True)


def _jump(p, x, y, s, c, direction):
    _pen(p, c, s)
    p.drawRoundedRect(QRectF(x + s * 0.06, y + s * 0.62, s * 0.3, s * 0.24), s * 0.05, s * 0.05)
    p.drawRoundedRect(QRectF(x + s * 0.64, y + s * 0.62, s * 0.3, s * 0.24), s * 0.05, s * 0.05)
    a, b = (0.2, 0.74) if direction > 0 else (0.8, 0.26)
    path = QPainterPath()
    path.moveTo(x + s * a, y + s * 0.5)
    path.quadTo(x + s * 0.5, y + s * 0.02, x + s * b, y + s * 0.4)
    p.drawPath(path)
    _arrow_head(p, QPointF(x + s * b, y + s * 0.48), math.pi / 2 + (-0.6 if direction > 0 else 0.6), s * 0.24, c)


def _jump_next(p, x, y, s, c):
    _jump(p, x, y, s, c, 1)


def _jump_prev(p, x, y, s, c):
    _jump(p, x, y, s, c, -1)


def _step(p, x, y, s, c, direction):  # a few frames on: frame ticks, the playhead, an arrow along them
    _pen(p, c, s)
    for i in range(6):
        tx = x + s * (0.12 + i * 0.152)
        p.drawLine(QPointF(tx, y + s * 0.72), QPointF(tx, y + s * 0.86))
    a, b = (0.24, 0.8) if direction > 0 else (0.76, 0.2)
    p.drawLine(QPointF(x + s * a, y + s * 0.18), QPointF(x + s * a, y + s * 0.86))
    p.drawLine(QPointF(x + s * a, y + s * 0.42), QPointF(x + s * (b - 0.08 * direction), y + s * 0.42))
    _arrow_head(p, QPointF(x + s * b, y + s * 0.42), 0.0 if direction > 0 else math.pi, s * 0.22, c)


def _step_forward(p, x, y, s, c):
    _step(p, x, y, s, c, 1)


def _step_back(p, x, y, s, c):
    _step(p, x, y, s, c, -1)


# -- the preview's options (the menu behind its three dots) --
def _pause(p, x, y, s, c):  # two bars
    _pen(p, c, s, 1.7)
    for bx in (0.36, 0.64):
        p.drawLine(QPointF(x + s * bx, y + s * 0.24), QPointF(x + s * bx, y + s * 0.76))


def _start_over(p, x, y, s, c):  # back to the start: a bar, and an arrow up against it
    _pen(p, c, s)
    p.drawLine(QPointF(x + s * 0.2, y + s * 0.22), QPointF(x + s * 0.2, y + s * 0.78))
    path = QPainterPath()
    path.moveTo(x + s * 0.82, y + s * 0.22)
    path.lineTo(x + s * 0.38, y + s * 0.5)
    path.lineTo(x + s * 0.82, y + s * 0.78)
    path.closeSubpath()
    p.drawPath(path)


def _sparkle_path(cx, cy, r):
    path = QPainterPath()
    path.moveTo(cx, cy - r)
    path.quadTo(cx, cy, cx + r, cy)
    path.quadTo(cx, cy, cx, cy + r)
    path.quadTo(cx, cy, cx - r, cy)
    path.quadTo(cx, cy, cx, cy - r)
    return path


def _auto(p, x, y, s, c):  # it decides for you: a spark, and a small one
    _pen(p, c, s)
    p.drawPath(_sparkle_path(x + s * 0.42, y + s * 0.56, s * 0.34))
    p.drawPath(_sparkle_path(x + s * 0.8, y + s * 0.22, s * 0.14))


def _autoplay(p, x, y, s, c):  # starts by itself: a play arrow already on its way
    _pen(p, c, s)
    path = QPainterPath()
    path.moveTo(x + s * 0.44, y + s * 0.2)
    path.lineTo(x + s * 0.9, y + s * 0.5)
    path.lineTo(x + s * 0.44, y + s * 0.8)
    path.closeSubpath()
    p.drawPath(path)
    for yy, x0 in ((0.34, 0.14), (0.5, 0.06), (0.66, 0.14)):
        p.drawLine(QPointF(x + s * x0, y + s * yy), QPointF(x + s * 0.26, y + s * yy))


def _repeat(p, x, y, s, c):  # round and round: two arrows chasing each other
    _pen(p, c, s)
    top = QPainterPath()
    top.moveTo(x + s * 0.14, y + s * 0.52)
    top.lineTo(x + s * 0.14, y + s * 0.44)
    top.quadTo(x + s * 0.14, y + s * 0.28, x + s * 0.3, y + s * 0.28)
    top.lineTo(x + s * 0.78, y + s * 0.28)
    p.drawPath(top)
    bottom = QPainterPath()
    bottom.moveTo(x + s * 0.86, y + s * 0.48)
    bottom.lineTo(x + s * 0.86, y + s * 0.56)
    bottom.quadTo(x + s * 0.86, y + s * 0.72, x + s * 0.7, y + s * 0.72)
    bottom.lineTo(x + s * 0.22, y + s * 0.72)
    p.drawPath(bottom)
    for tip_x, tip_y, d in ((0.84, 0.28, 1), (0.16, 0.72, -1)):
        head = QPainterPath()
        head.moveTo(x + s * (tip_x - d * 0.14), y + s * (tip_y - 0.13))
        head.lineTo(x + s * tip_x, y + s * tip_y)
        head.lineTo(x + s * (tip_x - d * 0.14), y + s * (tip_y + 0.13))
        p.drawPath(head)


def _guides(p, x, y, s, c):  # a frame cut into thirds
    _pen(p, c, s)
    p.drawRoundedRect(QRectF(x + s * 0.1, y + s * 0.16, s * 0.8, s * 0.68), s * 0.08, s * 0.08)
    _pen(p, c, s, 0.7)
    for f in (1 / 3, 2 / 3):
        p.drawLine(QPointF(x + s * (0.1 + 0.8 * f), y + s * 0.16), QPointF(x + s * (0.1 + 0.8 * f), y + s * 0.84))
        p.drawLine(QPointF(x + s * 0.1, y + s * (0.16 + 0.68 * f)), QPointF(x + s * 0.9, y + s * (0.16 + 0.68 * f)))


def _pin(p, x, y, s, c):  # stays where it is: a pin
    _pen(p, c, s)
    p.save()
    p.translate(x + s * 0.5, y + s * 0.5)
    p.rotate(40)
    u = s
    head = QPainterPath()
    head.moveTo(-u * 0.2, -u * 0.44)
    head.lineTo(u * 0.2, -u * 0.44)
    head.moveTo(-u * 0.13, -u * 0.44)
    head.lineTo(-u * 0.13, -u * 0.14)
    head.lineTo(-u * 0.27, u * 0.06)
    head.lineTo(u * 0.27, u * 0.06)
    head.lineTo(u * 0.13, -u * 0.14)
    head.lineTo(u * 0.13, -u * 0.44)
    p.drawPath(head)
    p.drawLine(QPointF(0, u * 0.06), QPointF(0, u * 0.46))
    p.restore()


def _with_picker(p, x, y, s, c):  # the picker and the preview, side by side
    _pen(p, c, s)
    p.drawRoundedRect(QRectF(x + s * 0.06, y + s * 0.2, s * 0.48, s * 0.6), s * 0.08, s * 0.08)
    p.drawRoundedRect(QRectF(x + s * 0.66, y + s * 0.2, s * 0.28, s * 0.6), s * 0.08, s * 0.08)
    _pen(p, c, s, 0.8)
    p.drawLine(QPointF(x + s * 0.17, y + s * 0.37), QPointF(x + s * 0.43, y + s * 0.37))


def _subtitles(p, x, y, s, c):  # a picture with two lines of words along the bottom
    _pen(p, c, s)
    p.drawRoundedRect(QRectF(x + s * 0.08, y + s * 0.16, s * 0.84, s * 0.68), s * 0.09, s * 0.09)
    p.drawLine(QPointF(x + s * 0.24, y + s * 0.56), QPointF(x + s * 0.76, y + s * 0.56))
    p.drawLine(QPointF(x + s * 0.34, y + s * 0.7), QPointF(x + s * 0.66, y + s * 0.7))


def _tidy_subtitles(p, x, y, s, c):  # the two lines of words, each cut off cleanly at its own length
    _pen(p, c, s)
    p.drawRoundedRect(QRectF(x + s * 0.08, y + s * 0.16, s * 0.84, s * 0.68), s * 0.09, s * 0.09)
    for yy in (0.4, 0.6):
        p.drawLine(QPointF(x + s * 0.22, y + s * yy), QPointF(x + s * 0.44, y + s * yy))
        p.drawLine(QPointF(x + s * 0.56, y + s * yy), QPointF(x + s * 0.78, y + s * yy))


def _animate(p, x, y, s, c):  # a move that eases in: a curve between two keyframes
    _pen(p, c, s)
    path = QPainterPath()
    path.moveTo(x + s * 0.16, y + s * 0.78)
    path.cubicTo(x + s * 0.5, y + s * 0.78, x + s * 0.5, y + s * 0.22, x + s * 0.84, y + s * 0.22)
    p.drawPath(path)
    _fill(p, c)
    for cx, cy in ((0.16, 0.78), (0.84, 0.22)):  # the keyframes: small diamonds
        diamond = QPainterPath()
        d = s * 0.1
        diamond.moveTo(x + s * cx, y + s * cy - d)
        diamond.lineTo(x + s * cx + d, y + s * cy)
        diamond.lineTo(x + s * cx, y + s * cy + d)
        diamond.lineTo(x + s * cx - d, y + s * cy)
        diamond.closeSubpath()
        p.drawPath(diamond)


def _swap(p, x, y, s, c):  # a clip on the track, the new one coming in over it and the old going out
    _pen(p, c, s)
    p.drawRoundedRect(QRectF(x + s * 0.24, y + s * 0.58, s * 0.52, s * 0.26), s * 0.06, s * 0.06)
    p.drawLine(QPointF(x + s * 0.2, y + s * 0.18), QPointF(x + s * 0.62, y + s * 0.18))
    _arrow_head(p, QPointF(x + s * 0.8, y + s * 0.18), 0.0, s * 0.2, c)
    _pen(p, c, s)
    p.drawLine(QPointF(x + s * 0.8, y + s * 0.38), QPointF(x + s * 0.38, y + s * 0.38))
    _arrow_head(p, QPointF(x + s * 0.2, y + s * 0.38), math.pi, s * 0.2, c)



def _swap_rows(p, x, y, s, c, top, bottom, line=None, wave=False):
    """Swap clip's ⋯: the old clip (below) and the new one (above) as bars, from-to in fractions; a line where
    they're lined up; the new one's loudest moment as a little peak."""
    faint = QColor(c)
    faint.setAlphaF(faint.alphaF() * 0.45)
    _pen(p, faint, s)
    p.drawRoundedRect(QRectF(x + s * bottom[0], y + s * 0.6, s * (bottom[1] - bottom[0]), s * 0.24), s * 0.05, s * 0.05)
    _pen(p, c, s)
    p.drawRoundedRect(QRectF(x + s * top[0], y + s * 0.2, s * (top[1] - top[0]), s * 0.24), s * 0.05, s * 0.05)
    if line is not None:
        _pen(p, c, s, 0.8)
        p.drawLine(QPointF(x + s * line, y + s * 0.06), QPointF(x + s * line, y + s * 0.96))
    if wave:
        _pen(p, c, s, 0.8)
        mid = x + s * line
        p.drawLine(QPointF(mid - s * 0.1, y + s * 0.32), QPointF(mid, y + s * 0.24))
        p.drawLine(QPointF(mid, y + s * 0.24), QPointF(mid + s * 0.1, y + s * 0.32))


def _swap_len_old(p, x, y, s, c):  # as long as the old one
    _swap_rows(p, x, y, s, c, (0.2, 0.8), (0.2, 0.8))


def _swap_len_stop(p, x, y, s, c):  # its own length, up to the next clip
    _swap_rows(p, x, y, s, c, (0.08, 0.72), (0.08, 0.5), line=0.72)


def _swap_len_over(p, x, y, s, c):  # its own length, over the next clip
    _swap_rows(p, x, y, s, c, (0.08, 0.95), (0.08, 0.5), line=0.66)


def _swap_start(p, x, y, s, c):  # starting where the old one started
    _swap_rows(p, x, y, s, c, (0.15, 0.92), (0.15, 0.6), line=0.15)


def _swap_end(p, x, y, s, c):  # ending where the old one ended
    _swap_rows(p, x, y, s, c, (0.08, 0.85), (0.4, 0.85), line=0.85)


def _swap_loudest(p, x, y, s, c):  # the loudest moments lined up
    _swap_rows(p, x, y, s, c, (0.1, 0.9), (0.3, 0.75), line=0.5, wave=True)


def _swap_part(p, x, y, s, c):  # the same part of the recording: a strip with a bracket over the same stretch
    _pen(p, c, s)
    p.drawRoundedRect(QRectF(x + s * 0.06, y + s * 0.5, s * 0.88, s * 0.28), s * 0.05, s * 0.05)
    p.drawLine(QPointF(x + s * 0.36, y + s * 0.18), QPointF(x + s * 0.64, y + s * 0.18))
    p.drawLine(QPointF(x + s * 0.36, y + s * 0.18), QPointF(x + s * 0.36, y + s * 0.38))
    p.drawLine(QPointF(x + s * 0.64, y + s * 0.18), QPointF(x + s * 0.64, y + s * 0.38))


def _grade(p, x, y, s, c):  # a colour wheel
    _pen(p, c, s)
    centre = QPointF(x + s * 0.5, y + s * 0.5)
    p.drawEllipse(centre, s * 0.38, s * 0.38)
    for angle in (90, 210, 330):
        a = math.radians(angle)
        p.drawLine(centre, QPointF(centre.x() + s * 0.38 * math.cos(a), centre.y() - s * 0.38 * math.sin(a)))


def _size_place(p, x, y, s, c):  # a frame with the picture in it moved and made smaller
    _pen(p, c, s)
    p.drawRoundedRect(QRectF(x + s * 0.06, y + s * 0.18, s * 0.88, s * 0.64), s * 0.06, s * 0.06)
    faint = QColor(c)
    faint.setAlphaF(faint.alphaF() * 0.4)
    _fill(p, faint)
    p.drawRoundedRect(QRectF(x + s * 0.44, y + s * 0.3, s * 0.38, s * 0.28), s * 0.04, s * 0.04)


def _similar(p, x, y, s, c):  # two waves, one over the other: "sounds like"
    for dy, alpha in ((-0.13, 1.0), (0.13, 0.55)):
        col = QColor(c)
        col.setAlphaF(col.alphaF() * alpha)
        _pen(p, col, s)
        path = QPainterPath()
        for i in range(25):
            t = i / 24
            pt = QPointF(x + s * (0.08 + 0.84 * t), y + s * (0.5 + dy) - s * 0.14 * math.sin(t * math.pi * 3))
            path.moveTo(pt) if i == 0 else path.lineTo(pt)
        p.drawPath(path)


def _before_after(p, x, y, s, c):  # a picture split down the middle: one half as it was, the other worked on
    _pen(p, c, s)
    frame = QRectF(x + s * 0.1, y + s * 0.2, s * 0.8, s * 0.6)
    p.drawRoundedRect(frame, s * 0.08, s * 0.08)
    p.drawLine(QPointF(x + s * 0.5, y + s * 0.1), QPointF(x + s * 0.5, y + s * 0.9))
    faint = QColor(c)
    faint.setAlphaF(faint.alphaF() * 0.4)
    _fill(p, faint)
    p.drawRoundedRect(QRectF(frame.center().x(), frame.top(), frame.width() / 2, frame.height()), s * 0.06, s * 0.06)


def _find_node(p, x, y, s, c):  # a node under a magnifier
    _pen(p, c, s)
    p.drawRoundedRect(QRectF(x + s * 0.08, y + s * 0.3, s * 0.5, s * 0.34), s * 0.08, s * 0.08)
    p.drawEllipse(QPointF(x + s * 0.64, y + s * 0.52), s * 0.2, s * 0.2)
    p.drawLine(QPointF(x + s * 0.78, y + s * 0.66), QPointF(x + s * 0.92, y + s * 0.82))


def _marker_list(p, x, y, s, c):  # a marker with lines of words beside it: the markers as text
    _pen(p, c, s)
    path = QPainterPath()
    path.moveTo(x + s * 0.1, y + s * 0.18)
    path.lineTo(x + s * 0.38, y + s * 0.18)
    path.lineTo(x + s * 0.38, y + s * 0.46)
    path.lineTo(x + s * 0.24, y + s * 0.62)
    path.lineTo(x + s * 0.1, y + s * 0.46)
    path.closeSubpath()
    p.drawPath(path)
    for yy, end in ((0.24, 0.9), (0.44, 0.78), (0.64, 0.9)):
        p.drawLine(QPointF(x + s * 0.52, y + s * yy), QPointF(x + s * end, y + s * yy))
    p.drawLine(QPointF(x + s * 0.1, y + s * 0.84), QPointF(x + s * 0.66, y + s * 0.84))


def _marker_shape(p, x, y, s, c, cx):  # the marker's flag, its point at cx (in s)
    path = QPainterPath()
    path.moveTo(x + s * (cx - 0.15), y + s * 0.1)
    path.lineTo(x + s * (cx + 0.15), y + s * 0.1)
    path.lineTo(x + s * (cx + 0.15), y + s * 0.36)
    path.lineTo(x + s * cx, y + s * 0.5)
    path.lineTo(x + s * (cx - 0.15), y + s * 0.36)
    path.closeSubpath()
    p.drawPath(path)


def _marker_fit(p, x, y, s, c):  # fit marker to clips: a marker whose range is stretched over two clips
    _pen(p, c, s)
    _marker_shape(p, x, y, s, c, 0.5)
    p.drawLine(QPointF(x + s * 0.1, y + s * 0.6), QPointF(x + s * 0.9, y + s * 0.6))  # (the range, as wide as the clips)
    p.drawLine(QPointF(x + s * 0.1, y + s * 0.54), QPointF(x + s * 0.1, y + s * 0.66))
    p.drawLine(QPointF(x + s * 0.9, y + s * 0.54), QPointF(x + s * 0.9, y + s * 0.66))
    p.drawRoundedRect(QRectF(x + s * 0.1, y + s * 0.74, s * 0.36, s * 0.14), s * 0.04, s * 0.04)
    p.drawRoundedRect(QRectF(x + s * 0.54, y + s * 0.74, s * 0.36, s * 0.14), s * 0.04, s * 0.04)


def _marker_add(p, x, y, s, c):  # add marker with note: a marker with a plus beside it
    _pen(p, c, s)
    _marker_shape(p, x, y, s, c, 0.3)
    p.drawLine(QPointF(x + s * 0.3, y + s * 0.5), QPointF(x + s * 0.3, y + s * 0.9))
    p.drawLine(QPointF(x + s * 0.58, y + s * 0.62), QPointF(x + s * 0.9, y + s * 0.62))
    p.drawLine(QPointF(x + s * 0.74, y + s * 0.46), QPointF(x + s * 0.74, y + s * 0.78))


def _tags(p, x, y, s, c):  # a sound's tags: a tag with a smaller one behind it
    _pen(p, c, s)
    for dx, dy, k in ((0.28, 0.08, 0.72), (0.0, 0.22, 1.0)):
        left, top, w, h = x + s * (0.08 + dx), y + s * dy, s * 0.56 * k, s * 0.5 * k
        path = QPainterPath()
        path.moveTo(left, top + h * 0.5)
        path.lineTo(left + w * 0.3, top)
        path.lineTo(left + w, top)
        path.lineTo(left + w, top + h)
        path.lineTo(left + w * 0.3, top + h)
        path.closeSubpath()
        p.drawPath(path)


def _relink(p, x, y, s, c):  # relink: two links of a chain, joined
    _pen(p, c, s)
    for dx in (0.08, 0.42):
        p.drawRoundedRect(QRectF(x + s * dx, y + s * 0.36, s * 0.5, s * 0.28), s * 0.14, s * 0.14)


def _beats(p, x, y, s, c):  # a marker on every beat: four even ticks
    _pen(p, c, s)
    for n in range(4):
        at = x + s * (0.14 + n * 0.24)
        p.drawLine(QPointF(at, y + s * 0.3), QPointF(at, y + s * 0.74))


def _bars(p, x, y, s, c):  # a marker on every bar: a tall tick, three small ones, a tall one
    _pen(p, c, s)
    for n in range(5):
        at = x + s * (0.12 + n * 0.19)
        tall = n in (0, 4)
        p.drawLine(QPointF(at, y + s * (0.18 if tall else 0.4)), QPointF(at, y + s * (0.82 if tall else 0.62)))


def _markers_hide(p, x, y, s, c):  # hide - show markers: two markers, a line through them
    _pen(p, c, s)
    _marker_shape(p, x, y + s * 0.12, s * 0.8, c, 0.3)
    _marker_shape(p, x + s * 0.32, y + s * 0.12, s * 0.8, c, 0.6)
    p.drawLine(QPointF(x + s * 0.1, y + s * 0.84), QPointF(x + s * 0.9, y + s * 0.84))
    p.drawLine(QPointF(x + s * 0.12, y + s * 0.12), QPointF(x + s * 0.88, y + s * 0.88))


def _voiceover(p, x, y, s, c):  # a microphone on its stand
    _pen(p, c, s)
    p.drawRoundedRect(QRectF(x + s * 0.37, y + s * 0.08, s * 0.26, s * 0.48), s * 0.13, s * 0.13)
    path = QPainterPath()
    path.moveTo(x + s * 0.24, y + s * 0.42)
    path.cubicTo(x + s * 0.24, y + s * 0.78, x + s * 0.76, y + s * 0.78, x + s * 0.76, y + s * 0.42)
    p.drawPath(path)
    p.drawLine(QPointF(x + s * 0.5, y + s * 0.69), QPointF(x + s * 0.5, y + s * 0.88))
    p.drawLine(QPointF(x + s * 0.34, y + s * 0.88), QPointF(x + s * 0.66, y + s * 0.88))


def _copy_name(p, x, y, s, c):  # a node's name tag, and a second one: the copy
    _pen(p, c, s)
    p.drawRoundedRect(QRectF(x + s * 0.28, y + s * 0.14, s * 0.6, s * 0.34), s * 0.08, s * 0.08)
    p.drawRoundedRect(QRectF(x + s * 0.1, y + s * 0.52, s * 0.6, s * 0.34), s * 0.08, s * 0.08)
    p.drawLine(QPointF(x + s * 0.24, y + s * 0.69), QPointF(x + s * 0.56, y + s * 0.69))


def _cheat_sheet(p, x, y, s, c):  # a page of short lines: this = that
    _pen(p, c, s)
    p.drawRoundedRect(QRectF(x + s * 0.18, y + s * 0.1, s * 0.64, s * 0.8), s * 0.08, s * 0.08)
    for yy in (0.3, 0.5, 0.7):
        p.drawLine(QPointF(x + s * 0.3, y + s * yy), QPointF(x + s * 0.42, y + s * yy))
        p.drawLine(QPointF(x + s * 0.52, y + s * yy), QPointF(x + s * 0.7, y + s * yy))


def _node_off(p, x, y, s, c):  # a node with a line through it: passed over
    _pen(p, c, s)
    p.drawRoundedRect(QRectF(x + s * 0.14, y + s * 0.3, s * 0.72, s * 0.4), s * 0.09, s * 0.09)
    p.drawLine(QPointF(x + s * 0.2, y + s * 0.84), QPointF(x + s * 0.8, y + s * 0.16))


def _expression(p, x, y, s, c):  # code that moves things: a wave between two brackets
    _pen(p, c, s)
    for side, sx in ((0.2, 1), (0.8, -1)):
        bracket = QPainterPath()
        bracket.moveTo(x + s * (side + sx * 0.06), y + s * 0.2)
        bracket.quadTo(x + s * (side - sx * 0.08), y + s * 0.2, x + s * (side - sx * 0.08), y + s * 0.36)
        bracket.quadTo(x + s * (side - sx * 0.08), y + s * 0.5, x + s * (side - sx * 0.16), y + s * 0.5)
        bracket.quadTo(x + s * (side - sx * 0.08), y + s * 0.5, x + s * (side - sx * 0.08), y + s * 0.64)
        bracket.quadTo(x + s * (side - sx * 0.08), y + s * 0.8, x + s * (side + sx * 0.06), y + s * 0.8)
        p.drawPath(bracket)
    wave = QPainterPath()
    wave.moveTo(x + s * 0.32, y + s * 0.5)
    wave.cubicTo(x + s * 0.42, y + s * 0.26, x + s * 0.46, y + s * 0.26, x + s * 0.5, y + s * 0.5)
    wave.cubicTo(x + s * 0.54, y + s * 0.74, x + s * 0.58, y + s * 0.74, x + s * 0.68, y + s * 0.5)
    p.drawPath(wave)


# -- the expression cheat sheet's groups: what kind of thing you're writing --
def _x_comp(p, x, y, s, c):  # the composition: a frame, and the frame you're on
    _pen(p, c, s)
    p.drawRoundedRect(QRectF(x + s * 0.1, y + s * 0.2, s * 0.8, s * 0.6), s * 0.1, s * 0.1)
    p.drawLine(QPointF(x + s * 0.4, y + s * 0.2), QPointF(x + s * 0.4, y + s * 0.8))


def _x_time(p, x, y, s, c):  # a clock
    _pen(p, c, s)
    p.drawEllipse(QPointF(x + s * 0.5, y + s * 0.5), s * 0.38, s * 0.38)
    p.drawLine(QPointF(x + s * 0.5, y + s * 0.28), QPointF(x + s * 0.5, y + s * 0.5))
    p.drawLine(QPointF(x + s * 0.5, y + s * 0.5), QPointF(x + s * 0.66, y + s * 0.6))


def _x_waves(p, x, y, s, c):  # a wave
    _pen(p, c, s)
    wave = QPainterPath()
    wave.moveTo(x + s * 0.08, y + s * 0.5)
    wave.cubicTo(x + s * 0.22, y + s * 0.0, x + s * 0.36, y + s * 0.0, x + s * 0.5, y + s * 0.5)
    wave.cubicTo(x + s * 0.64, y + s * 1.0, x + s * 0.78, y + s * 1.0, x + s * 0.92, y + s * 0.5)
    p.drawPath(wave)


def _x_sums(p, x, y, s, c):  # plus over minus
    _pen(p, c, s)
    p.drawLine(QPointF(x + s * 0.28, y + s * 0.36), QPointF(x + s * 0.72, y + s * 0.36))
    p.drawLine(QPointF(x + s * 0.5, y + s * 0.14), QPointF(x + s * 0.5, y + s * 0.58))
    p.drawLine(QPointF(x + s * 0.28, y + s * 0.82), QPointF(x + s * 0.72, y + s * 0.82))


def _x_choices(p, x, y, s, c):  # one way or the other: a line that forks
    _pen(p, c, s)
    p.drawLine(QPointF(x + s * 0.1, y + s * 0.5), QPointF(x + s * 0.4, y + s * 0.5))
    for end in (0.22, 0.78):
        p.drawLine(QPointF(x + s * 0.4, y + s * 0.5), QPointF(x + s * 0.62, y + s * end))
        p.drawLine(QPointF(x + s * 0.62, y + s * end), QPointF(x + s * 0.9, y + s * end))


def _x_nodes(p, x, y, s, c):  # one node reading another
    _pen(p, c, s)
    p.drawRoundedRect(QRectF(x + s * 0.06, y + s * 0.16, s * 0.4, s * 0.28), s * 0.07, s * 0.07)
    p.drawRoundedRect(QRectF(x + s * 0.54, y + s * 0.56, s * 0.4, s * 0.28), s * 0.07, s * 0.07)
    p.drawLine(QPointF(x + s * 0.46, y + s * 0.3), QPointF(x + s * 0.74, y + s * 0.3))
    p.drawLine(QPointF(x + s * 0.74, y + s * 0.3), QPointF(x + s * 0.74, y + s * 0.56))


def _x_size(p, x, y, s, c):  # how big a picture is: a frame, measured along the bottom
    _pen(p, c, s)
    p.drawRoundedRect(QRectF(x + s * 0.14, y + s * 0.12, s * 0.72, s * 0.46), s * 0.07, s * 0.07)
    p.drawLine(QPointF(x + s * 0.14, y + s * 0.82), QPointF(x + s * 0.86, y + s * 0.82))
    for end in (0.14, 0.86):
        p.drawLine(QPointF(x + s * end, y + s * 0.72), QPointF(x + s * end, y + s * 0.92))


def _x_words(p, x, y, s, c):  # a T
    _pen(p, c, s)
    p.drawLine(QPointF(x + s * 0.2, y + s * 0.2), QPointF(x + s * 0.8, y + s * 0.2))
    p.drawLine(QPointF(x + s * 0.5, y + s * 0.2), QPointF(x + s * 0.5, y + s * 0.84))
    p.drawLine(QPointF(x + s * 0.38, y + s * 0.84), QPointF(x + s * 0.62, y + s * 0.84))


def _x_dates(p, x, y, s, c):  # a calendar
    _pen(p, c, s)
    p.drawRoundedRect(QRectF(x + s * 0.14, y + s * 0.2, s * 0.72, s * 0.66), s * 0.08, s * 0.08)
    p.drawLine(QPointF(x + s * 0.14, y + s * 0.42), QPointF(x + s * 0.86, y + s * 0.42))
    for at in (0.34, 0.66):
        p.drawLine(QPointF(x + s * at, y + s * 0.1), QPointF(x + s * at, y + s * 0.28))


def _copy_code(p, x, y, s, c):  # two sheets, one over the other
    _pen(p, c, s)
    p.drawRoundedRect(QRectF(x + s * 0.34, y + s * 0.34, s * 0.52, s * 0.52), s * 0.1, s * 0.1)
    back = QPainterPath()
    back.moveTo(x + s * 0.22, y + s * 0.66)
    back.lineTo(x + s * 0.14, y + s * 0.66)
    back.lineTo(x + s * 0.14, y + s * 0.14)
    back.lineTo(x + s * 0.66, y + s * 0.14)
    back.lineTo(x + s * 0.66, y + s * 0.22)
    p.drawPath(back)


def _pick_node(p, x, y, s, c):  # click the one you mean: a ring with four marks, and its middle
    _pen(p, c, s)
    p.drawEllipse(QPointF(x + s * 0.5, y + s * 0.5), s * 0.28, s * 0.28)
    for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
        p.drawLine(QPointF(x + s * (0.5 + dx * 0.2), y + s * (0.5 + dy * 0.2)),
                   QPointF(x + s * (0.5 + dx * 0.44), y + s * (0.5 + dy * 0.44)))
    _fill(p, c)
    p.drawEllipse(QPointF(x + s * 0.5, y + s * 0.5), s * 0.05, s * 0.05)


def _idea(p, x, y, s, c):  # a wish for the app: a light bulb
    _pen(p, c, s)
    p.drawArc(QRectF(x + s * 0.24, y + s * 0.1, s * 0.52, s * 0.52), -40 * 16, 260 * 16)
    p.drawLine(QPointF(x + s * 0.34, y + s * 0.56), QPointF(x + s * 0.4, y + s * 0.7))
    p.drawLine(QPointF(x + s * 0.66, y + s * 0.56), QPointF(x + s * 0.6, y + s * 0.7))
    p.drawLine(QPointF(x + s * 0.4, y + s * 0.7), QPointF(x + s * 0.6, y + s * 0.7))
    p.drawLine(QPointF(x + s * 0.42, y + s * 0.82), QPointF(x + s * 0.58, y + s * 0.82))


def _tick(p, x, y, s, c):  # done
    _pen(p, c, s, 1.3)
    done = QPainterPath()
    done.moveTo(x + s * 0.2, y + s * 0.54)
    done.lineTo(x + s * 0.42, y + s * 0.74)
    done.lineTo(x + s * 0.82, y + s * 0.28)
    p.drawPath(done)


def _restart(p, x, y, s, c):  # restart Clipse: once round, an arrow at the end
    _pen(p, c, s)
    r = QRectF(x + s * 0.16, y + s * 0.16, s * 0.68, s * 0.68)
    p.drawArc(r, 70 * 16, 300 * 16)
    a = math.radians(70)
    tip = QPointF(x + s / 2 + s * 0.34 * math.cos(a), y + s / 2 - s * 0.34 * math.sin(a))
    _arrow_head(p, tip, -a + math.pi / 2, s * 0.24, c)


def _power(p, x, y, s, c):  # quit Clipse
    _pen(p, c, s)
    p.drawArc(QRectF(x + s * 0.14, y + s * 0.16, s * 0.72, s * 0.72), 125 * 16, 290 * 16)
    p.drawLine(QPointF(x + s * 0.5, y + s * 0.08), QPointF(x + s * 0.5, y + s * 0.48))


def _book(p, x, y, s, c):  # the documentation: an open book
    _pen(p, c, s)
    for side in (-1, 1):
        page = QPainterPath()
        page.moveTo(x + s * 0.5, y + s * 0.3)
        page.cubicTo(x + s * (0.5 + side * 0.12), y + s * 0.22, x + s * (0.5 + side * 0.28), y + s * 0.22,
                     x + s * (0.5 + side * 0.38), y + s * 0.25)
        page.lineTo(x + s * (0.5 + side * 0.38), y + s * 0.75)
        page.cubicTo(x + s * (0.5 + side * 0.28), y + s * 0.72, x + s * (0.5 + side * 0.12), y + s * 0.72,
                     x + s * 0.5, y + s * 0.8)
        p.drawPath(page)
    p.drawLine(QPointF(x + s * 0.5, y + s * 0.3), QPointF(x + s * 0.5, y + s * 0.8))


def _bug(p, x, y, s, c):  # report a problem: a beetle
    _pen(p, c, s)
    p.drawRoundedRect(QRectF(x + s * 0.32, y + s * 0.34, s * 0.36, s * 0.48), s * 0.18, s * 0.18)
    p.drawArc(QRectF(x + s * 0.38, y + s * 0.18, s * 0.24, s * 0.24), 0, 180 * 16)
    p.drawLine(QPointF(x + s * 0.5, y + s * 0.5), QPointF(x + s * 0.5, y + s * 0.74))
    for yy in (0.46, 0.6, 0.74):
        p.drawLine(QPointF(x + s * 0.32, y + s * yy), QPointF(x + s * 0.18, y + s * (yy - 0.04)))
        p.drawLine(QPointF(x + s * 0.68, y + s * yy), QPointF(x + s * 0.82, y + s * (yy - 0.04)))


def _envelope(p, x, y, s, c):  # send feedback: a letter - a problem or an idea, it goes the same way
    _pen(p, c, s)
    r = QRectF(x + s * 0.16, y + s * 0.26, s * 0.68, s * 0.48)
    p.drawRoundedRect(r, s * 0.07, s * 0.07)
    flap = QPainterPath()
    flap.moveTo(r.left() + s * 0.05, r.top() + s * 0.06)
    flap.lineTo(r.center().x(), r.top() + s * 0.27)
    flap.lineTo(r.right() - s * 0.05, r.top() + s * 0.06)
    p.drawPath(flap)


def _bin(p, x, y, s, c):  # uninstall: a bin, its lid and handle
    _pen(p, c, s)
    p.drawLine(QPointF(x + s * 0.2, y + s * 0.28), QPointF(x + s * 0.8, y + s * 0.28))
    p.drawLine(QPointF(x + s * 0.42, y + s * 0.28), QPointF(x + s * 0.42, y + s * 0.18))
    p.drawLine(QPointF(x + s * 0.42, y + s * 0.18), QPointF(x + s * 0.58, y + s * 0.18))
    p.drawLine(QPointF(x + s * 0.58, y + s * 0.18), QPointF(x + s * 0.58, y + s * 0.28))
    can = QPainterPath()
    can.moveTo(x + s * 0.28, y + s * 0.28)
    can.lineTo(x + s * 0.32, y + s * 0.82)
    can.lineTo(x + s * 0.68, y + s * 0.82)
    can.lineTo(x + s * 0.72, y + s * 0.28)
    p.drawPath(can)
    for xx in (0.43, 0.57):
        p.drawLine(QPointF(x + s * xx, y + s * 0.4), QPointF(x + s * xx, y + s * 0.7))


def _plug(p, x, y, s, c):  # the connection check: a plug
    _pen(p, c, s)
    p.drawLine(QPointF(x + s * 0.4, y + s * 0.14), QPointF(x + s * 0.4, y + s * 0.3))
    p.drawLine(QPointF(x + s * 0.6, y + s * 0.14), QPointF(x + s * 0.6, y + s * 0.3))
    body = QPainterPath()
    body.moveTo(x + s * 0.28, y + s * 0.3)
    body.lineTo(x + s * 0.72, y + s * 0.3)
    body.lineTo(x + s * 0.72, y + s * 0.48)
    body.cubicTo(x + s * 0.72, y + s * 0.6, x + s * 0.62, y + s * 0.66, x + s * 0.5, y + s * 0.66)
    body.cubicTo(x + s * 0.38, y + s * 0.66, x + s * 0.28, y + s * 0.6, x + s * 0.28, y + s * 0.48)
    body.closeSubpath()
    p.drawPath(body)
    p.drawLine(QPointF(x + s * 0.5, y + s * 0.66), QPointF(x + s * 0.5, y + s * 0.86))


GLYPHS = {
    # actions
    "insert": _insert, "picture_only": _picture_only, "compound": _compound, "sound_only": _sound_only, "grab": _grab, "undo": _undo,
    "insert_as": _insert_as, "preview": _eye, "info": _info_card, "stage": _stage, "favourite": _star,
    "reveal_pool": _reveal_pool, "file_manager": _file_manager, "listen": _headphones,
    "loop": _loop, "analyse": _metronome, "tidy": _tidy, "pull_out": _pull_out, "add_node": _add_node,
    "templates": _templates, "organise": _organise, "timeline": _timeline, "project": _clapper, "rescan": _refresh, "history": _history,
    "keys": _keyboard, "tour": _compass, "reset_place": _reset_place, "settings": _gear, "gear_fine": _gear_fine,
    "search": _search, "adj_over": _adj_over, "adj_footage": _adj_footage, "adj_playhead": _adj_playhead,
    "comp_over": _comp_over, "comp_footage": _comp_footage, "comp_playhead": _comp_playhead,
    "jump_next": _jump_next, "jump_prev": _jump_prev, "step_forward": _step_forward, "step_back": _step_back, "power": _power, "restart": _restart,
    "checkup": _checkup, "pages": _pages, "render": _render, "new_timeline": _new_timeline,
    "dup_timeline": _dup_timeline, "add_video_track": _add_video_track, "add_audio_track": _add_audio_track,
    "marker": _marker, "clip_colour": _clip_colour, "save": _save,
    "remove_tracks": _remove_tracks, "name_tracks": _name_tracks, "marker_list": _marker_list, "voiceover": _voiceover,
    "marker_fit": _marker_fit, "marker_add": _marker_add, "markers_hide": _markers_hide, "beats": _beats, "bars": _bars, "tags": _tags, "relink": _relink,
    # the preview's options
    "pause": _pause, "start_over": _start_over, "auto": _auto, "autoplay": _autoplay, "repeat": _repeat,
    "guides": _guides, "pin": _pin, "with_picker": _with_picker,
    "subtitles": _subtitles, "tidy_subtitles": _tidy_subtitles, "animate": _animate,
    "find_node": _find_node, "expression": _expression,
    "copy_name": _copy_name, "cheat_sheet": _cheat_sheet, "node_off": _node_off, "before_after": _before_after,
    "similar": _similar, "swap": _swap, "swap_len_old": _swap_len_old, "swap_len_stop": _swap_len_stop,
    "swap_len_over": _swap_len_over, "swap_start": _swap_start, "swap_end": _swap_end, "swap_loudest": _swap_loudest,
    "swap_part": _swap_part, "grade": _grade, "size_place": _size_place,
    # the expression cheat sheet
    "x_comp": _x_comp, "x_time": _x_time, "x_waves": _x_waves, "x_sums": _x_sums, "x_choices": _x_choices,
    "x_nodes": _x_nodes, "x_size": _x_size, "x_words": _x_words, "x_dates": _x_dates,
    "copy_code": _copy_code, "tick": _tick, "pick_node": _pick_node, "idea": _idea,
    "book": _book, "bug": _bug, "feedback": _envelope, "uninstall": _bin, "plug": _plug,
    # Settings pages
    "general": _gear, "preview_page": _screen_play, "sound": _speaker, "appearance": _palette,
    "scripts": _terminal, "folders": _folder, "prefixes": _prefix, "stats": _stats, "about": _about,
}

# the Actions panel: action -> glyph
ACTION_GLYPH = {
    "Insert": "insert", "Picture only": "picture_only", "Sound only": "sound_only", "As compound clip": "compound", "Grab frame": "grab",
    "Undo Clipse\u2019s last step": "undo", "Insert as…": "insert_as",
    "Preview": "preview", "Clip info": "info", "Stage": "stage", "Favourite": "favourite",
    "Show in Media Pool": "reveal_pool", "Show in file manager": "file_manager",
    "Listening on / off": "listen", "Mark the loop": "loop", "Analyse sounds": "analyse",
    "Tidy up nodes": "tidy", "Pull node out": "pull_out", "Add a node…": "add_node",
    "Project templates…": "templates", "Organise project": "organise", "Switch timeline…": "timeline", "Switch project…": "project",
    "Rescan Media Pool": "rescan", "Search history": "history", "Keyboard shortcuts": "keys", "Take the tour": "tour",
    "Reset position and size": "reset_place", "Settings": "settings",
    "Project check-up": "checkup", "Go to page…": "pages", "Render…": "render", "New timeline": "new_timeline",
    "Duplicate timeline": "dup_timeline", "Add video track": "add_video_track", "Add audio track": "add_audio_track",
    "Clip colour…": "clip_colour", "Save project": "save",
    "Remove empty tracks": "remove_tracks", "Name the tracks": "name_tracks", "Copy markers": "marker_list", "Stretch marker to clips": "marker_fit", "Add marker": "marker_add", "Hide - show markers": "markers_hide", "Copy timeline": "timeline", "Copy project": "project", "Copy transcript": "subtitles", "Record voiceover": "voiceover",
    "Subtitles from speech": "subtitles", "Tidy the subtitles": "tidy_subtitles", "Animate\u2026": "animate",
    "Ready-made expressions\u2026": "expression", "Copy node name": "copy_name",
    "Expressions": "cheat_sheet", "Node off / on": "node_off", "Before / after": "before_after",
    "Sounds like this": "similar", "Swap clip": "swap", "Tags": "tags", "Relink missing clips": "relink",
    "Mark the beats": "beats", "Mark the bars": "bars",
    "Suggest a feature": "idea", "Restart Clipse": "restart", "Quit Clipse": "power",
    # (the scripts' own, as Settings > Scripts draws them)
    "Adjustment clip over clip": "adj_over", "Adjustment clip over footage": "adj_footage",
    "Adjustment clip at playhead": "adj_playhead", "Fusion composition over clip": "comp_over",
    "Fusion composition over footage": "comp_footage", "Fusion composition at playhead": "comp_playhead",
    "Next use of clip": "jump_next", "Previous use of clip": "jump_prev",
    "Step forward": "step_forward", "Step back": "step_back",
}

# the > list's rows that come in families (one per page, render preset ...): family -> glyph
GROUP_GLYPH = {"Check-up": "checkup", "Page": "pages", "Render": "render", "Clip colour": "clip_colour",
               "Animate": "animate", "Node": "find_node", "Expression": "expression",
               "Step": "step_forward"}


def draw_glyph(p, name, center, size, color):
    fn = GLYPHS.get(name)
    if fn is None:
        return False
    p.save()
    p.setRenderHint(p.RenderHint.Antialiasing)
    fn(p, center.x() - size / 2, center.y() - size / 2, float(size), QColor(color))
    p.restore()
    return True


def glyph_icon(name, color, size=16, mirror=False, ratio=2.0):
    """A glyph as a QIcon, for a button (mirror: drawn the other way round - redo from undo)."""
    from PySide6.QtGui import QIcon, QPainter, QPixmap
    from PySide6.QtCore import Qt
    pix = QPixmap(int(size * ratio), int(size * ratio))
    pix.setDevicePixelRatio(ratio)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    if mirror:
        p.translate(size, 0)
        p.scale(-1, 1)
    draw_glyph(p, name, QPointF(size / 2, size / 2), size * 0.92, color)
    p.end()
    return QIcon(pix)
