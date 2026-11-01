"""Little looping animations of what each of Clipse's Resolve
shortcuts does - shown when you rest the mouse on one in Settings ->
Scripts. Drawn with QPainter (a tiny timeline, bins, nodes), so they
match the theme and cost nothing to ship.

draw_demo(p, rect, name, t, colors): t runs 0 -> 1 and loops."""

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

LOOP_MS = 2600


def _ease(x):
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


def _phase(t, a, b):
    """0 before a, 1 after b, eased in between."""
    return _ease((t - a) / (b - a)) if b > a else float(t >= b)


def _alpha(color, a):
    c = QColor(color)
    c.setAlphaF(max(0.0, min(1.0, a)))
    return c


def colors_from(theme):
    return {"bg": QColor(theme["picker_bg"]), "bar": QColor(theme.get("picker_bar_bg", theme["picker_bg"])),
            "text": QColor(theme["picker_text"]), "muted": QColor(theme["picker_folder"]),
            "border": QColor(theme["picker_border"]), "accent": QColor(theme.get("picker_accent", theme["picker_text"])),
            "video": QColor(theme["color_video"]), "audio": QColor(theme["color_audio"]),
            "adjustment": QColor(theme["color_adjustment"]), "image": QColor(theme["color_image"]),
            "node": QColor(theme.get("color_node", "#7fdbca")), "bin": QColor(theme["color_bin"]),
            "comp": QColor(theme["color_comp"])}


class _Timeline:
    """Tracks laid out in a rect: track(n) is the rect of video track n (1 = bottom)."""

    def __init__(self, r, tracks=3):
        self.r = r
        self.tracks = tracks
        self.h = r.height() / (tracks + 0.6)

    def y(self, track):
        return self.r.bottom() - track * self.h

    def x(self, f):
        return self.r.left() + self.r.width() * f

    def clip(self, p, track, a, b, color, alpha=1.0, outline=False, dashed=False):
        rect = QRectF(self.x(a) + 1, self.y(track) + 2, self.x(b) - self.x(a) - 2, self.h - 4)
        if outline:
            p.setPen(QPen(_alpha(color, alpha), 1.2, Qt.DashLine if dashed else Qt.SolidLine))
            p.setBrush(_alpha(color, alpha * 0.12))
        else:
            p.setPen(Qt.NoPen)
            p.setBrush(_alpha(color, alpha))
        p.drawRoundedRect(rect, 3, 3)
        return rect

    def lanes(self, p, c):
        p.setPen(QPen(_alpha(c["border"], 0.6), 1))
        for n in range(1, self.tracks + 1):
            y = self.y(n) + self.h
            p.drawLine(QPointF(self.r.left(), y), QPointF(self.r.right(), y))

    def playhead(self, p, f, c):
        x = self.x(f)
        p.setPen(QPen(c["accent"], 1.4))
        p.drawLine(QPointF(x, self.r.top() + 6), QPointF(x, self.r.bottom()))
        head = QPainterPath()
        head.moveTo(x - 4, self.r.top())
        head.lineTo(x + 4, self.r.top())
        head.lineTo(x, self.r.top() + 6)
        head.closeSubpath()
        p.setPen(Qt.NoPen)
        p.setBrush(c["accent"])
        p.drawPath(head)


def _footage(tl, p, c, alpha=1.0):
    tl.clip(p, 1, 0.02, 0.3, c["video"], alpha)
    tl.clip(p, 1, 0.3, 0.66, c["video"], alpha * 0.8)
    tl.clip(p, 1, 0.66, 0.98, c["video"], alpha)


def _search(p, r, t, c):
    tl = _Timeline(QRectF(r.left(), r.top() + r.height() * 0.55, r.width(), r.height() * 0.45), 2)
    tl.lanes(p, c)
    _footage(tl, p, c, 0.55)
    tl.playhead(p, 0.42, c)
    show = _phase(t, 0.02, 0.18) * (1 - _phase(t, 0.62, 0.72))
    card = QRectF(r.left() + r.width() * 0.18, r.top() + 2, r.width() * 0.64, r.height() * 0.48)
    if show > 0:
        p.setPen(QPen(_alpha(c["border"], show), 1))
        p.setBrush(_alpha(c["bar"], show))
        p.drawRoundedRect(card, 6, 6)
        typed = "whoosh"[:int(len("whoosh") * _phase(t, 0.12, 0.34) + 0.01)]
        p.setPen(_alpha(c["text"], show))
        f = QFont(p.font())
        f.setPointSizeF(max(7.0, f.pointSizeF() * 0.82) if f.pointSizeF() > 0 else 8.0)
        p.setFont(f)
        p.drawText(QRectF(card.left() + 8, card.top() + 3, card.width() - 16, 16), Qt.AlignLeft | Qt.AlignVCenter,
                   typed + ("|" if int(t * 12) % 2 == 0 else ""))
        for i in range(3):
            row = QRectF(card.left() + 6, card.top() + 21 + i * 11, card.width() - 12, 9)
            if i == 0 and t > 0.36:
                p.setPen(Qt.NoPen)
                p.setBrush(_alpha(c["accent"], 0.25 * show))
                p.drawRoundedRect(row.adjusted(-2, -1, 2, 1), 3, 3)
            p.setPen(Qt.NoPen)
            p.setBrush(_alpha(c["audio"], show))
            p.drawRoundedRect(QRectF(row.left() + 2, row.top() + 2, 6, 5), 1.5, 1.5)
            p.setBrush(_alpha(c["muted"], show * 0.8))
            p.drawRoundedRect(QRectF(row.left() + 12, row.top() + 3, row.width() * (0.6 - i * 0.12), 3), 1.5, 1.5)
    fly = _phase(t, 0.5, 0.74)
    if t >= 0.5:
        start = QPointF(card.left() + 20, card.top() + 25)
        end = QPointF(tl.x(0.42), tl.y(2) + 2)
        pos = start + (end - start) * fly
        w = tl.x(0.62) - tl.x(0.42)
        p.setPen(Qt.NoPen)
        p.setBrush(c["audio"])
        p.drawRoundedRect(QRectF(pos.x(), pos.y(), 14 + (w - 14) * fly, tl.h - 4), 3, 3)


def _rescan(p, r, t, c):
    cx, cy = r.left() + r.width() * 0.3, r.center().y()
    from .glyphs import draw_glyph
    p.save()
    p.translate(cx, cy)
    p.rotate(360 * _phase(t, 0.0, 0.9))
    draw_glyph(p, "rescan", QPointF(0, 0), r.height() * 0.42, c["accent"])
    p.restore()
    for i in range(5):
        appear = _phase(t, 0.1 + i * 0.13, 0.22 + i * 0.13)
        y = r.top() + r.height() * (0.18 + i * 0.15)
        p.setPen(Qt.NoPen)
        p.setBrush(_alpha([c["video"], c["audio"], c["image"], c["video"], c["audio"]][i], appear))
        p.drawRoundedRect(QRectF(r.left() + r.width() * 0.55, y, 8, 7), 2, 2)
        p.setBrush(_alpha(c["muted"], appear * 0.8))
        p.drawRoundedRect(QRectF(r.left() + r.width() * 0.55 + 13, y + 2, r.width() * (0.28 - i * 0.02) * appear, 3),
                          1.5, 1.5)


def _adjustment(p, r, t, c, mode, kind="adjustment"):
    tl = _Timeline(r, 3)
    tl.lanes(p, c)
    _footage(tl, p, c)
    playhead = 0.48
    tl.playhead(p, playhead, c)
    grow = _phase(t, 0.25, 0.6)
    if mode == "footage":
        tl.clip(p, 2, 0.38, 0.56, c[kind], 0.5, outline=True, dashed=True)  # one already there
    if mode == "fixed":
        a, b = playhead, playhead + 0.4
    else:
        a, b = 0.3, 0.66
    track = 3 if mode == "footage" else 2
    if grow > 0:
        left = playhead + (a - playhead) * grow
        right = playhead + (b - playhead) * grow
        tl.clip(p, track, left, right, c[kind], 0.95)
    if mode != "fixed" and t > 0.62:  # the edges line up with the clip below
        k = _phase(t, 0.62, 0.7) * (1 - _phase(t, 0.9, 1.0))
        p.setPen(QPen(_alpha(c["text"], 0.6 * k), 1, Qt.DotLine))
        for f in (a, b):
            p.drawLine(QPointF(tl.x(f), tl.y(track)), QPointF(tl.x(f), tl.y(1) + tl.h))


def _use(p, r, t, c, direction):
    tl = _Timeline(r, 2)
    tl.lanes(p, c)
    spans = [(0.02, 0.2), (0.2, 0.42), (0.42, 0.6), (0.6, 0.8), (0.8, 0.98)]
    same = (1, 3)
    for i, (a, b) in enumerate(spans):
        tl.clip(p, 1, a, b, c["accent"] if i in same else c["video"], 1.0 if i in same else 0.45)
    first, second = spans[same[0]][0], spans[same[1]][0]
    if direction < 0:
        first, second = second, first
    move = _phase(t, 0.3, 0.55)
    tl.playhead(p, first + (second - first) * move, c)
    if 0.55 < t < 0.85:
        k = 1 - _phase(t, 0.55, 0.85)
        idx = same[1] if direction > 0 else same[0]
        a, b = spans[idx]
        p.setPen(QPen(_alpha(c["accent"], k), 2))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(QRectF(tl.x(a) - 2, tl.y(1), tl.x(b) - tl.x(a) + 4, tl.h + 2), 4, 4)


def _swap(p, r, t, c):
    """A clip on the track under the playhead; another comes down onto its place, the first fading out."""
    tl = _Timeline(r, 2)
    tl.lanes(p, c)
    tl.clip(p, 1, 0.02, 0.32, c["video"], 0.45)
    tl.clip(p, 1, 0.68, 0.98, c["video"], 0.45)
    swap = _phase(t, 0.3, 0.6) * (1 - _phase(t, 0.85, 0.98))
    tl.clip(p, 1, 0.32, 0.68, c["video"], 1 - swap)
    if swap > 0.01:  # the new one, coming down from above onto its place
        p.setPen(Qt.NoPen)
        p.setBrush(_alpha(c["accent"], swap))
        p.drawRoundedRect(QRectF(tl.x(0.32) + 1, tl.y(1) + 2 - tl.h * (1 - swap), tl.x(0.68) - tl.x(0.32) - 2,
                                 tl.h - 4), 3, 3)
    tl.playhead(p, 0.5, c)


def _grab(p, r, t, c):
    tl = _Timeline(QRectF(r.left(), r.top() + r.height() * 0.3, r.width() * 0.72, r.height() * 0.7), 2)
    tl.lanes(p, c)
    _footage(tl, p, c, 0.8)
    tl.playhead(p, 0.45, c)
    flash = _phase(t, 0.15, 0.22) * (1 - _phase(t, 0.22, 0.36))
    if flash > 0:
        x = tl.x(0.45)
        p.setPen(Qt.NoPen)
        p.setBrush(_alpha(QColor("white"), 0.7 * flash))
        p.drawRoundedRect(QRectF(x - 9, tl.y(1) - 2, 18, tl.h + 4), 3, 3)
    from .glyphs import draw_glyph
    bin_center = QPointF(r.right() - r.width() * 0.12, r.top() + r.height() * 0.22)
    draw_glyph(p, "folders", bin_center, r.height() * 0.3, c["bin"])
    fly = _phase(t, 0.3, 0.55)
    if 0.3 <= t < 0.6:
        start = QPointF(tl.x(0.45), tl.y(1) + tl.h / 2)
        pos = start + (bin_center - start) * fly
        p.setPen(Qt.NoPen)
        p.setBrush(c["image"])
        p.drawRoundedRect(QRectF(pos.x() - 7, pos.y() - 5, 14, 10), 2, 2)
    land = _phase(t, 0.62, 0.8)
    if land > 0:
        tl.clip(p, 2, 0.45, 0.45 + 0.22 * land, c["image"])


def _undo(p, r, t, c):
    tl = _Timeline(r, 3)
    tl.lanes(p, c)
    _footage(tl, p, c, 0.45)
    added = [(2, 0.2, 0.42), (2, 0.5, 0.7), (3, 0.3, 0.55)]
    for i, (track, a, b) in enumerate(added):
        gone = _phase(t, 0.35 + (2 - i) * 0.08, 0.5 + (2 - i) * 0.08) * (1 - _phase(t, 0.92, 1.0))
        tl.clip(p, track, a, b, c["audio"] if i == 1 else c["video"], 1 - gone)
    from .glyphs import draw_glyph
    k = _phase(t, 0.2, 0.32) * (1 - _phase(t, 0.6, 0.75))
    if k > 0:
        draw_glyph(p, "undo", QPointF(r.right() - 16, r.top() + 14), 20, _alpha(c["accent"], k))


def _node(p, center, size, color, label_color=None):
    rect = QRectF(center.x() - size, center.y() - size * 0.6, size * 2, size * 1.2)
    p.setPen(Qt.NoPen)
    p.setBrush(label_color if label_color is not None else QColor("#262a33"))
    p.drawRoundedRect(rect, 3, 3)  # opaque, so the links stop at the node
    p.setPen(QPen(color, 1.3))
    p.setBrush(_alpha(color, 0.18))
    p.drawRoundedRect(rect, 3, 3)
    return rect


def _tidy(p, r, t, c):
    messy = [(0.15, 0.25), (0.45, 0.75), (0.55, 0.2), (0.85, 0.6)]
    neat = [(0.12, 0.5), (0.37, 0.5), (0.62, 0.5), (0.87, 0.5)]
    k = _phase(t, 0.3, 0.7) * (1 - _phase(t, 0.92, 1.0))
    pts = [QPointF(r.left() + r.width() * (mx + (nx - mx) * k), r.top() + r.height() * (my + (ny - my) * k))
           for (mx, my), (nx, ny) in zip(messy, neat)]
    p.setPen(QPen(_alpha(c["muted"], 0.9), 1.2))
    for a, b in zip(pts, pts[1:]):
        p.drawLine(a, b)
    for pt in pts:
        _node(p, pt, r.width() * 0.07, c["node"], c["bar"])


def _pull_out(p, r, t, c):
    y = r.top() + r.height() * 0.66
    xs = [r.left() + r.width() * f for f in (0.15, 0.5, 0.85)]
    lift = _phase(t, 0.2, 0.5) * (1 - _phase(t, 0.92, 1.0))
    join = _phase(t, 0.5, 0.7) * (1 - _phase(t, 0.92, 1.0))
    mid = QPointF(xs[1], y - r.height() * 0.42 * lift)
    a, b = QPointF(xs[0], y), QPointF(xs[2], y)
    p.setPen(QPen(_alpha(c["muted"], 0.9 * (1 - join)), 1.2))
    p.drawLine(a, mid)
    p.drawLine(mid, b)
    if join > 0:
        p.setPen(QPen(_alpha(c["accent"], join), 1.6))
        p.drawLine(a, a + (b - a) * join)
    _node(p, a, r.width() * 0.07, c["node"], c["bar"])
    _node(p, b, r.width() * 0.07, c["node"], c["bar"])
    _node(p, mid, r.width() * 0.07, c["accent"] if lift > 0.5 else c["node"], c["bar"])


def _node_off(p, r, t, c):
    """Three nodes in a line; the middle one goes off (dimmed, the picture passing straight through it), then
    on again."""
    y = r.top() + r.height() * 0.55
    xs = [r.left() + r.width() * f for f in (0.15, 0.5, 0.85)]
    off = _phase(t, 0.25, 0.4) * (1 - _phase(t, 0.7, 0.85))
    a, mid, b = QPointF(xs[0], y), QPointF(xs[1], y), QPointF(xs[2], y)
    p.setPen(QPen(_alpha(c["muted"], 0.9), 1.2))
    p.drawLine(a, b)
    _node(p, a, r.width() * 0.07, c["node"], c["bar"])
    _node(p, b, r.width() * 0.07, c["node"], c["bar"])
    p.setOpacity(1 - 0.65 * off)
    _node(p, mid, r.width() * 0.07, c["node"], c["bar"])
    p.setOpacity(1.0)
    if off > 0.05:  # the line through it: the picture goes past
        p.setPen(QPen(_alpha(c["accent"], off), 1.6))
        p.drawLine(QPointF(xs[1] - r.width() * 0.09, y), QPointF(xs[1] + r.width() * 0.09, y))


def _before_after(p, r, t, c):
    """MediaIn, two effects, MediaOut: the effects go off together (dimmed, the picture passing straight through),
    then on again."""
    y = r.top() + r.height() * 0.55
    xs = [r.left() + r.width() * f for f in (0.12, 0.37, 0.63, 0.88)]
    off = _phase(t, 0.25, 0.4) * (1 - _phase(t, 0.7, 0.85))
    p.setPen(QPen(_alpha(c["muted"], 0.9), 1.2))
    p.drawLine(QPointF(xs[0], y), QPointF(xs[-1], y))
    for n, x in enumerate(xs):
        effect = 0 < n < len(xs) - 1
        p.setOpacity(1 - 0.65 * off if effect else 1.0)
        _node(p, QPointF(x, y), r.width() * 0.06, c["node"], c["bar"])
    p.setOpacity(1.0)
    if off > 0.05:  # the line through them: the picture goes past
        p.setPen(QPen(_alpha(c["accent"], off), 1.6))
        p.drawLine(QPointF(xs[1] - r.width() * 0.08, y), QPointF(xs[2] + r.width() * 0.08, y))


def _restart(p, r, t, c):
    from .glyphs import draw_glyph
    p.save()
    p.translate(r.center())
    p.rotate(360 * _phase(t, 0.1, 0.7))
    draw_glyph(p, "rescan", QPointF(0, 0), r.height() * 0.5, c["accent"])
    p.restore()
    k = _phase(t, 0.7, 0.8) * (1 - _phase(t, 0.92, 1.0))
    p.setPen(Qt.NoPen)
    p.setBrush(_alpha(c["audio"], k))
    p.drawEllipse(QPointF(r.center().x() + r.height() * 0.32, r.center().y() - r.height() * 0.26), 4, 4)


def _copy_name(p, r, t, c):
    """A node is selected; its name lifts off it and lands in an expression."""
    node = QRectF(r.left() + r.width() * 0.1, r.center().y() - 26, r.width() * 0.34, 22)
    field = QRectF(r.left() + r.width() * 0.42, r.center().y() + 10, r.width() * 0.5, 22)
    p.setPen(QPen(c["accent"], 1.4))
    p.setBrush(_alpha(c["node"], 0.25))
    p.drawRoundedRect(node, 5, 5)
    p.setPen(QPen(c["border"], 1))
    p.setBrush(c["bar"])
    p.drawRoundedRect(field, 5, 5)
    p.setPen(c["text"])
    p.drawText(node, Qt.AlignCenter, "Transform1")
    move = _phase(t, 0.25, 0.6)
    if move > 0:
        start, end = node.center(), QPointF(field.left() + 44, field.center().y())
        at = QPointF(start.x() + (end.x() - start.x()) * move, start.y() + (end.y() - start.y()) * move)
        p.setPen(c["accent"])
        p.drawText(QRectF(at.x() - 44, at.y() - 10, 88, 20), Qt.AlignCenter, "Transform1")
    if t > 0.6:
        p.setPen(_alpha(c["muted"], _phase(t, 0.6, 0.75)))
        p.drawText(QRectF(field.left() + 88, field.top(), field.width() - 90, field.height()), Qt.AlignLeft | Qt.AlignVCenter, ".Center")


DEMOS = {
    "search": _search, "rescan": _rescan,
    "adj_clip": lambda p, r, t, c: _adjustment(p, r, t, c, "clip"),
    "adj_footage": lambda p, r, t, c: _adjustment(p, r, t, c, "footage"),
    "adj_fixed": lambda p, r, t, c: _adjustment(p, r, t, c, "fixed"),
    "comp_clip": lambda p, r, t, c: _adjustment(p, r, t, c, "clip", "comp"),
    "comp_footage": lambda p, r, t, c: _adjustment(p, r, t, c, "footage", "comp"),
    "comp_fixed": lambda p, r, t, c: _adjustment(p, r, t, c, "fixed", "comp"),
    "swap": _swap,
    "next_use": lambda p, r, t, c: _use(p, r, t, c, 1), "prev_use": lambda p, r, t, c: _use(p, r, t, c, -1),
    "grab": _grab, "undo": _undo, "tidy": _tidy, "pull_out": _pull_out, "restart": _restart,
    "copy_name": _copy_name, "node_off": _node_off, "before_after": _before_after,
}


def draw_demo(p, r, name, t, c):
    fn = DEMOS.get(name)
    if fn is not None:
        p.save()
        fn(p, r, t % 1.0, c)
        p.restore()


class DemoPopup(QWidget):
    """The animation in a small card next to the row the mouse is on."""

    def __init__(self, settings):
        super().__init__(None, Qt.ToolTip | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.settings = settings
        self.name = None
        self.title = ""
        self._t0 = 0
        self._clock = 0.0
        self.setFixedSize(280, 170)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

    def show_for(self, name, title, anchor):
        """anchor: a global QRect of the row - the card goes to its right, or under it."""
        self.name, self.title = name, title
        self._clock = 0.0
        screen = self.screen().availableGeometry() if self.screen() else None
        x = anchor.right() + 12
        y = anchor.top() + anchor.height() // 2 - self.height() // 2
        if screen is not None and x + self.width() > screen.right():
            x = anchor.right() - self.width() - 12
            y = anchor.bottom() + 6
        self.move(x, y)
        self.show()
        self.raise_()
        self._timer.start(16)

    def hide_demo(self):
        self._timer.stop()
        self.hide()

    def _tick(self):
        self._clock += 16 / LOOP_MS
        self.update()

    def paintEvent(self, event):
        c = colors_from(self.settings.theme)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        card = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QPen(c["border"], 1))
        p.setBrush(c["bar"])
        p.drawRoundedRect(card, 10, 10)
        f = QFont(self.font())
        f.setWeight(QFont.DemiBold)
        p.setFont(f)
        fm = QFontMetricsF(f)
        p.setPen(c["text"])
        p.drawText(QRectF(14, 10, self.width() - 28, fm.height()), Qt.AlignLeft | Qt.AlignVCenter,
                   fm.elidedText(self.title, Qt.ElideRight, self.width() - 28))
        p.setFont(self.font())
        stage = QRectF(16, 18 + fm.height(), self.width() - 32, self.height() - fm.height() - 34)
        draw_demo(p, stage, self.name, self._clock, c)
        p.end()
