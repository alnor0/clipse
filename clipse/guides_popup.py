"""The Guides picker that opens from the preview's bar: each guide as a
small drawing of what it puts over the picture - tick as many as you like
(they show at once), Remember keeps them on for every clip."""
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFontMetricsF, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget
from .fonts import SMALL, at as font_at  # (the one scale of sizes)

TILES = [  # (key, label)
    ("16:9", "16:9"), ("9:16", "9:16"), ("4:5", "4:5"), ("1:1", "1:1"),
    ("2.39:1", "2.39:1"), ("thirds", "Thirds"), ("centre", "Centre"),
]
# (16:9 for what isn't: a photo, a phone's upright video - what a 16:9 timeline keeps of it; 2026-10-17)
RATIOS = {"16:9": 16 / 9, "9:16": 9 / 16, "4:5": 4 / 5, "1:1": 1.0, "2.39:1": 2.39}
COLUMNS = 4


class GuidesPopup(QWidget):
    changed = Signal(list)          # the guides that are on, in TILES order
    remember_changed = Signal(bool)

    def __init__(self, settings, guides, remember, parent=None):
        super().__init__(parent, Qt.Popup | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setMouseTracking(True)
        self.settings = settings
        self.guides = list(guides)
        self.remember = remember
        self.focus = 0                 # keyboard: which tile
        self._hover = None             # tile index, "remember" or "clear"
        self.pad, self.gap = 12.0, 8.0
        fm = QFontMetricsF(self.font())
        names = QFontMetricsF(font_at(SMALL, self.font()))  # (a tile is never narrower than its longest name)
        self.tile_w = max(74.0, max(names.horizontalAdvance(label) for _key, label in TILES) + 16)
        self.tile_h = 70.0
        self.foot_h = fm.height() + 16
        rows = (len(TILES) + COLUMNS - 1) // COLUMNS
        width = self.pad * 2 + COLUMNS * self.tile_w + (COLUMNS - 1) * self.gap
        height = self.pad * 2 + rows * self.tile_h + (rows - 1) * self.gap + self.foot_h
        self.setFixedSize(int(width), int(height))

    # -- layout --
    def _tile_rect(self, i):
        r, c = divmod(i, COLUMNS)
        return QRectF(self.pad + c * (self.tile_w + self.gap), self.pad + r * (self.tile_h + self.gap),
                      self.tile_w, self.tile_h)

    def _foot_rect(self):
        return QRectF(self.pad, self.height() - self.pad - self.foot_h + 6, self.width() - 2 * self.pad,
                      self.foot_h - 6)

    def _remember_rect(self):
        f = self._foot_rect()
        fm = QFontMetricsF(self.font())
        return QRectF(f.left(), f.top(), fm.height() + fm.horizontalAdvance("Remember for every clip") + 4, f.height())

    def _clear_rect(self):
        f = self._foot_rect()
        w = QFontMetricsF(self.font()).horizontalAdvance("Clear") + 8
        return QRectF(f.right() - w, f.top(), w, f.height())

    def _hit(self, pos):
        for i in range(len(TILES)):
            if self._tile_rect(i).contains(pos):
                return i
        if self._remember_rect().contains(pos):
            return "remember"
        if self.guides and self._clear_rect().contains(pos):
            return "clear"
        return None

    # -- actions --
    def _toggle(self, i):
        key = TILES[i][0]
        on = [k for k in self.guides if k != key]
        if key not in self.guides:
            on.append(key)
        order = [k for k, _ in TILES]
        self.guides = sorted(on, key=order.index)
        self.changed.emit(list(self.guides))
        self.update()

    def _activate(self, what):
        if isinstance(what, int):
            self._toggle(what)
        elif what == "remember":
            self.remember = not self.remember
            self.remember_changed.emit(self.remember)
            self.update()
        elif what == "clear":
            self.guides = []
            self.changed.emit([])
            self.update()

    def mouseMoveEvent(self, event):
        hit = self._hit(event.position())
        if hit != self._hover:
            self._hover = hit
            self.setCursor(Qt.PointingHandCursor if hit is not None else Qt.ArrowCursor)
            self.update()

    def leaveEvent(self, event):
        self._hover = None
        self.update()

    def mousePressEvent(self, event):
        hit = self._hit(event.position())
        if hit is None and not self.rect().contains(event.position().toPoint()):
            self.close()
            return
        if hit is not None and event.button() == Qt.LeftButton:
            if isinstance(hit, int):
                self.focus = hit
            self._activate(hit)

    def keyPressEvent(self, event):
        k = event.key()
        n = len(TILES)
        if k in (Qt.Key_Escape,):
            self.close()
        elif k == Qt.Key_Right:
            self.focus = (self.focus + 1) % n
        elif k == Qt.Key_Left:
            self.focus = (self.focus - 1) % n
        elif k == Qt.Key_Down:
            self.focus = min(n - 1, self.focus + COLUMNS)
        elif k == Qt.Key_Up:
            self.focus = max(0, self.focus - COLUMNS)
        elif k in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            self._toggle(self.focus)
        else:
            return super().keyPressEvent(event)
        self.update()

    # -- drawing --
    def paintEvent(self, event):
        t = self.settings.theme
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        from . import look
        radius = look.radius(self.settings, "card")
        body = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QPen(QColor(t["picker_border"]), 1))
        p.setBrush(QColor(t.get("picker_bar_bg", t["picker_bg"])))
        p.drawRoundedRect(body, radius, radius)
        accent = QColor(t.get("picker_accent", t["picker_text"]))
        text = QColor(t["picker_text"])
        muted = QColor(t["picker_folder"])
        small = font_at(SMALL, self.font())
        for i, (key, label) in enumerate(TILES):
            r = self._tile_rect(i)
            on = key in self.guides
            hover = self._hover == i or (self._hover is None and self.focus == i and self.hasFocus())
            look.paint_tile(p, r, self.settings, chosen=on, hover=hover)  # (the app's one tile)
            pic = QRectF(r.center().x() - 23, r.top() + 10, 46, 46 * 9 / 16)  # (its own size, however wide the tile)
            self._draw_icon(p, key, pic, accent if on else (text if hover else muted), muted)
            p.setFont(small)
            p.setPen(text if on or hover else muted)
            p.drawText(QRectF(r.left(), pic.bottom() + 4, r.width(), r.bottom() - pic.bottom() - 6),
                       Qt.AlignHCenter | Qt.AlignVCenter, label)
        # the footer: Remember (a dot like the bar's toggles) and Clear
        p.setFont(self.font())
        rr = self._remember_rect()
        fm = QFontMetricsF(self.font())
        dot_r = fm.height() * 0.2
        c = QPointF(rr.left() + dot_r + 1, rr.center().y())
        lit = self.remember or self._hover == "remember"
        p.setPen(QPen(text if lit else muted, 1.2))
        p.setBrush(text if self.remember else Qt.NoBrush)
        p.drawEllipse(c, dot_r, dot_r)
        p.setPen(text if lit else muted)
        p.drawText(QRectF(rr.left() + fm.height() * 0.7, rr.top(), rr.width(), rr.height()),
                   Qt.AlignLeft | Qt.AlignVCenter, "Remember for every clip")
        if self.guides:
            p.setPen(text if self._hover == "clear" else muted)
            p.drawText(self._clear_rect(), Qt.AlignRight | Qt.AlignVCenter, "Clear")
        p.end()

    @staticmethod
    def _draw_icon(p, key, screen, color, muted):
        """A tiny 16:9 picture with the guide drawn on it (16:9 itself: a 4:3 photo, the band it keeps of it)."""
        p.save()
        if key == "16:9":
            w = screen.height() * 4 / 3
            screen = QRectF(screen.center().x() - w / 2, screen.top(), w, screen.height())
        frame = QColor(muted)
        frame.setAlphaF(0.8)
        p.setPen(QPen(frame, 1.0))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(screen, 2, 2)
        if key in RATIOS:
            ratio = RATIOS[key]
            if screen.width() / screen.height() > ratio:
                w, h = screen.height() * ratio, screen.height()
            else:
                w, h = screen.width(), screen.width() / ratio
            crop = QRectF(screen.center().x() - w / 2, screen.center().y() - h / 2, w, h)
            shade = QColor(color)
            shade.setAlphaF(0.22)
            outside = QPainterPath()
            outside.addRoundedRect(screen, 2, 2)
            inner = QPainterPath()
            inner.addRect(crop)
            p.fillPath(outside.subtracted(inner), shade)
            p.setPen(QPen(color, 1.4))
            p.drawRect(crop)
        elif key == "thirds":
            p.setPen(QPen(color, 1.2))
            for i in (1, 2):
                x = screen.left() + screen.width() * i / 3
                y = screen.top() + screen.height() * i / 3
                p.drawLine(QPointF(x, screen.top() + 1), QPointF(x, screen.bottom() - 1))
                p.drawLine(QPointF(screen.left() + 1, y), QPointF(screen.right() - 1, y))
        elif key == "centre":
            c = screen.center()
            arm = screen.height() * 0.28
            p.setPen(QPen(color, 1.4))
            p.drawLine(QPointF(c.x() - arm, c.y()), QPointF(c.x() + arm, c.y()))
            p.drawLine(QPointF(c.x(), c.y() - arm), QPointF(c.x(), c.y() + arm))
        p.restore()
