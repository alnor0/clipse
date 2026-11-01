"""Swap clip's strip, under the picker's search while a swap is under way (PickerWindow.start_swap): what goes
out - the clip on the timeline, and how often it's there - an arrow, and what comes in: the highlighted clip,
following the list. At the right, Here | Everywhere (only when it's on the timeline more than once) and a ✕.

    [▶] logo_old.png  ×4   →   [▶] logo_new.png                  [ Here | Everywhere ]  ✕

A clip that can't go in (a sound for a picture) is shown faded. Painted, like the rest of the picker's bars.
The ⋯ beside the ✕ opens how a swap is done (SwapOptions: how long, where, which part, grade, size and place) -
set there and nowhere else, kept in settings.timeline_tools ("swap_...")."""
from PySide6.QtCore import Qt, QRectF, QPointF, Signal
from PySide6.QtGui import QColor, QFontMetricsF, QPainter, QPen
from PySide6.QtWidgets import QWidget

from .preview_menu import BarMenu, MenuRow, MenuRule, MenuTitle
from .symbols import draw_symbol
from .fonts import SMALL, at as font_at  # (the one scale of sizes)

# Swap clip's ⋯: (setting, title, [(value, words, glyph, hover)]) - a tick on the one chosen
SWAP_CHOICES = [
    ("swap_length", "Length", [
        ("old", "As long as the old one", "swap_len_old", "It takes the old one's place exactly"),
        ("own_stop", "Its own - up to the next clip", "swap_len_stop", "As long as it is, but not over the clip after it"),
        ("own_over", "Its own - over the next clip", "swap_len_over",
         "As long as it is - where it would cover a clip, it goes a track up"),
    ]),
    ("swap_align", "Where it sits", [
        ("start", "Same start", "swap_start", "It starts where the old one started"),
        ("end", "Same end", "swap_end", "It ends where the old one ended"),
        ("loudest", "Loudest moments lined up", "swap_loudest",
         "Its loudest moment where the old one's was - a new whoosh hits at the same moment"),
    ]),
]
# ...and the switches
SWAP_SWITCHES = [
    ("swap_same_part", "Same part of the recording", "swap_part",
     "It starts at the same moment of its own recording as the old one did - for another take of the same shot"),
    ("swap_grade", "Keep the colour grade", "grade", "The old one's grade goes onto the new one"),
    ("swap_look", "Keep size and position", "size_place", "The old one's zoom, position, rotation and opacity"),
]


class SwapStrip(QWidget):
    everywhere_changed = Signal(bool)
    cancelled = Signal()
    pick = Signal()  # the target in front (or the empty slot): out of the way to click the clip in Resolve

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.out_name = self.out_kind = self.out_symbol = ""
        self.in_name = self.in_kind = self.in_symbol = ""
        self.in_fits = True
        self.uses = 1
        self.several = 0   # more than one clip selected on the timeline: shown as a warning, nothing swaps
        self.everywhere = False
        self._spots = {}   # what can be clicked: "here", "everywhere", "close" -> rect
        self._hover = None
        self.setMouseTracking(True)
        self.hide()

    # -- what it shows --
    def show_swap(self, name, kind, uses, everywhere, symbol=None, several=0):
        self.out_name, self.out_kind, self.uses = name, kind, max(1, int(uses))
        self.several = several
        self.out_symbol = symbol or kind
        self.everywhere = bool(everywhere) and self.uses > 1
        self.in_name = self.in_kind = ""
        self.show()
        self.update()

    def set_in(self, name, kind, fits=True, symbol=None):
        if (name, kind, fits, symbol) != (self.in_name, self.in_kind, self.in_fits, self.in_symbol):
            self.in_name, self.in_kind, self.in_fits, self.in_symbol = name, kind, fits, symbol or kind
            self.update()

    def sizeHint(self):
        from PySide6.QtCore import QSize
        return QSize(400, self._height())

    def minimumSizeHint(self):
        return self.sizeHint()

    def _height(self):
        return int(QFontMetricsF(self._font()).height() + 24)

    def _font(self):
        return font_at(SMALL, self.font())

    # -- painting --
    def paintEvent(self, event):
        t = self.settings.theme
        d = self.settings.display
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        font = self._font()
        fm = QFontMetricsF(font)
        text, muted = QColor(t["picker_text"]), QColor(t["picker_folder"])
        line = QColor(t["picker_border"])
        line.setAlphaF(0.6)  # (dividers are quieter than edges)
        p.setPen(QPen(line, 1))
        p.drawLine(QPointF(0, self.height() - 0.5), QPointF(self.width(), self.height() - 0.5))
        from .fonts import picker_scale
        pad = float(d.get("outer_padding", 16)) * picker_scale(self.settings)
        cy = self.height() / 2
        self._spots = {}

        # at the right: ✕, ⋯ (how a swap is done), then Here | Everywhere
        right = self.width() - pad
        close = QRectF(right - 18, cy - 9, 18, 18)
        self._spots["close"] = close
        x_colour = QColor(text if self._hover == "close" else muted)
        p.setPen(QPen(x_colour, 1.4, Qt.SolidLine, Qt.RoundCap))
        k = 4.0
        p.drawLine(QPointF(close.center().x() - k, cy - k), QPointF(close.center().x() + k, cy + k))
        p.drawLine(QPointF(close.center().x() - k, cy + k), QPointF(close.center().x() + k, cy - k))
        more = QRectF(close.left() - 26, cy - 9, 22, 18)
        self._spots["more"] = more
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(text if self._hover == "more" else muted))
        for n in (-1, 0, 1):
            p.drawEllipse(QPointF(more.center().x() + n * 5.0, cy), 1.5, 1.5)
        right = more.left() - 10
        p.setFont(font)
        if self.uses > 1:
            words = [("here", "Here"), ("everywhere", f"Everywhere ({self.uses})")]
            widths = [fm.horizontalAdvance(w) + 20 for _k, w in words]
            h = fm.height() + 8
            pill = QRectF(right - sum(widths) - 4, cy - h / 2, sum(widths) + 4, h)
            soft = QColor(text)
            soft.setAlphaF(0.07)
            p.setPen(Qt.NoPen)
            p.setBrush(soft)
            p.drawRoundedRect(pill, 6, 6)
            x = pill.left() + 2
            for (key, word), w in zip(words, widths):
                seg = QRectF(x, pill.top() + 2, w, pill.height() - 4)
                self._spots[key] = seg
                chosen = (key == "everywhere") == self.everywhere
                if chosen or self._hover == key:
                    lit = QColor(text)
                    lit.setAlphaF(0.12 if chosen else 0.06)
                    p.setBrush(lit)
                    p.drawRoundedRect(seg, 5, 5)
                p.setPen(text if chosen else muted)
                p.drawText(seg, Qt.AlignCenter, word)
                p.setPen(Qt.NoPen)
                x += w
            right = pill.left() - 14

        # out -> in, from the left: first the target to pick it in Resolve (the picker steps aside), then what
        # goes out (nothing yet: an empty slot, waiting for a click in Resolve)
        from .glyphs import draw_glyph
        side = fm.height() * 1.05
        target = QRectF(pad - 2, cy - side / 2 - 2, side + 4, side + 4)
        self._spots["pick"] = target
        draw_glyph(p, "pick_node", target.center(), side, QColor(text if self._hover == "pick" else muted))
        x = target.right() + 8
        if self.several:
            x = self._empty(p, x, cy, self._red(), fm, font, f"{self.several} clips selected - one at a time")
        elif self.out_name:
            x = self._clip(p, x, cy, self.out_kind, self.out_symbol, self.out_name, text, fm, font, (right - pad) * 0.42)
        else:
            end = self._empty(p, x, cy, muted, fm, font)
            self._spots["pick_slot"] = QRectF(x, cy - fm.height() / 2, end - x, fm.height())
            x = end
        arrow = QColor(muted)
        p.setPen(QPen(arrow, 1.4, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        a, b = x + 12, x + 30
        p.drawLine(QPointF(a, cy), QPointF(b, cy))
        p.drawLine(QPointF(b - 4, cy - 4), QPointF(b, cy))
        p.drawLine(QPointF(b - 4, cy + 4), QPointF(b, cy))
        x = b + 12
        if self.in_name:
            colour = QColor(text)
            if not self.in_fits:
                colour.setAlphaF(0.4)
            self._clip(p, x, cy, self.in_kind, self.in_symbol, self.in_name, colour, fm, font, right - x,
                       faded=not self.in_fits)
        p.end()

    def _red(self):
        from .actions_panel import script_red
        return script_red(self.settings.theme)

    def _empty(self, p, x, cy, muted, fm, font, words="Click a clip in Resolve"):
        """No clip to swap out yet: a dashed slot, and where it comes from (or, several selected, that it's one
        at a time - in red)."""
        side = fm.height() * 0.95
        tag = QRectF(x, cy - side / 2, side * 1.38, side)
        p.setPen(QPen(muted, 1, Qt.DashLine))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(tag.adjusted(0.5, 0.5, -0.5, -0.5), 4, 4)
        p.setFont(font)
        p.setPen(muted)
        p.drawText(QRectF(tag.right() + 8, cy - fm.height() / 2, fm.horizontalAdvance(words) + 2, fm.height()),
                   Qt.AlignLeft | Qt.AlignVCenter, words)
        return tag.right() + 8 + fm.horizontalAdvance(words)

    def _clip(self, p, x, cy, kind, symbol, name, colour, fm, font, room, faded=False):
        """A clip's kind as a small tag, then its name (cut short to fit `room`). Returns where it ends."""
        side = fm.height() * 0.95
        tag = QRectF(x, cy - side / 2, side * 1.38, side)
        try:
            tint = QColor(self.settings.icon_color(kind))
        except KeyError:
            tint = QColor(self.settings.theme["picker_folder"])
        back = QColor(tint)
        back.setAlphaF(0.18 * (0.5 if faded else 1.0))
        p.setPen(Qt.NoPen)
        p.setBrush(back)
        p.drawRoundedRect(tag, 4, 4)
        if faded:
            tint.setAlphaF(0.45)
        draw_symbol(p, symbol or kind, tag.center(), side * 0.66, tint)
        p.setFont(font)
        p.setPen(colour)
        width = max(20.0, room - tag.width() - 8)
        shown = fm.elidedText(name, Qt.ElideMiddle, width)
        p.drawText(QRectF(tag.right() + 8, cy - fm.height() / 2, width, fm.height()), Qt.AlignLeft | Qt.AlignVCenter,
                   shown)
        return tag.right() + 8 + fm.horizontalAdvance(shown)

    # -- the mouse --
    def _spot_at(self, pos):
        return next((key for key, rect in self._spots.items() if rect.adjusted(-3, -3, 3, 3).contains(pos)), None)

    def mouseMoveEvent(self, event):
        spot = self._spot_at(event.position())
        self.setToolTip("Out of the way - click the clip in Resolve" if spot in ("pick", "pick_slot") else "")
        if spot != self._hover:
            self._hover = spot
            self.setCursor(Qt.PointingHandCursor if spot else Qt.ArrowCursor)
            self.update()

    def leaveEvent(self, event):
        self._hover = None
        self.update()

    def mousePressEvent(self, event):
        spot = self._spot_at(event.position())
        if spot == "close":
            self.cancelled.emit()
        elif spot == "more":
            self.open_options()
        elif spot in ("pick", "pick_slot"):
            self.pick.emit()
        elif spot in ("here", "everywhere") and (spot == "everywhere") != self.everywhere:
            self.everywhere = spot == "everywhere"
            self.everywhere_changed.emit(self.everywhere)
            self.update()

    # -- ⋯: how a swap is done --
    def open_options(self):
        """The ⋯'s menu, under the dots - rows like the preview's options: a tick on each group's choice, then
        the switches. A change is in use at once and kept."""
        tools = self.settings.timeline_tools
        menu = BarMenu(self.settings)
        menu.setParent(self.window(), menu.windowFlags())  # (a popup belongs to the window it opens from)
        rows = {}
        for n, (key, title, choices) in enumerate(SWAP_CHOICES):
            if n:
                menu.box.addWidget(MenuRule(self.settings))
            menu.box.addWidget(MenuTitle(self.settings, title))
            for value, words, glyph, tip in choices:
                row = MenuRow(self.settings, words, glyph, kind="choice", checked=tools.get(key) == value)
                row.setToolTip(tip)
                row.clicked.connect(lambda key=key, value=value: pick(key, value))
                rows[(key, value)] = row
                menu.box.addWidget(row)
        menu.box.addWidget(MenuRule(self.settings))
        for key, words, glyph, tip in SWAP_SWITCHES:
            row = MenuRow(self.settings, words, glyph, checked=bool(tools.get(key)))
            row.setToolTip(tip)
            row.toggled.connect(lambda on, key=key: (tools.__setitem__(key, bool(on)), self.settings.save()))
            menu.box.addWidget(row)

        def pick(key, value):
            tools[key] = value
            self.settings.save()
            for (k, v), row in rows.items():
                if k == key:
                    row.set_checked(v == value)
        for w in menu.findChildren(QWidget):
            w.setFont(self.font())
        menu.adjustSize()
        dots = self._spots.get("more", QRectF(self.width() - 40, 0, 20, self.height()))
        from PySide6.QtCore import QPoint
        anchor = self.mapToGlobal(QPoint(int(dots.right()), int(dots.bottom()) + 6))
        menu.move(anchor.x() - menu.width(), anchor.y())
        menu.show()
        self.menu = menu
