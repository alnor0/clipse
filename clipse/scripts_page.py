"""Settings > Scripts: every script of Clipse's in Resolve's menu as a table - its coloured square, its name, its
name in Resolve's menu - grouped by the page it's for; the one chosen is described beside it, with what it has to
set (settings_dialog._script_details). The owner picked this from samples (2026-10-21: "Try the f table", after
"It is not setup up so you can get a good overview of the scripts")."""
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPainterPath
from PySide6.QtWidgets import QWidget

from .fonts import SMALL, TINY, at as font_at, rel
from .resolve_shortcuts import menu_name

# the colours of the squares - a family shares one (the sidebar's squares: settings_cards.nav_tile)
_BLUE, _PURPLE, _VIOLET, _TEAL, _GREEN, _PINK, _GREY = ("#5b8def", "#9a6cf0", "#7a5cf0", "#2fb3a3", "#3fbf6f",
                                                        "#e0558f", "#8f9bb3")
_GOLD = "#d4a72c"  # (the markers - no orange)
# (heading, [(name shown, its name in resolve_shortcuts.ACTIONS, glyph, colour)])
SCRIPTS = [  # (Clipse's own first, as in Resolve's menu - 2026-10-21: "Put these at the top")
    ("Clipse", [("Open", "Open", "search", _GREY), ("Restart", "Restart", "restart", _GREY),
                ("Quit", "Quit", "power", _GREY)]),
    ("Edit page", [("Swap clip", "Swap Clip", "swap", _BLUE),
                   ("Undo", "Undo Last Action", "undo", _GREY),
                   ("Grab frame", "Grab Frame", "grab", _PINK),
                   ("Record voiceover", "Record Voiceover", "voiceover", _PINK),
                   ("Organise project", "Organise Project", "organise", _GREY),
                   ("Add marker", "Add Marker", "marker_add", _GOLD),
                   ("Stretch marker to clips", "Stretch Marker to Clips", "marker_fit", _GOLD),
                   ("Hide - show markers", "Hide - Show Markers", "markers_hide", _GOLD),
                   ("Next use of clip", "Next Use of Clip", "jump_next", _BLUE),
                   ("Previous use of clip", "Previous Use of Clip", "jump_prev", _BLUE),
                   ("Adjustment clip over clip", "Adjustment Clip Over Clip", "adj_over", _PURPLE),
                   ("Adjustment clip over footage", "Adjustment Clip Over Footage", "adj_footage", _PURPLE),
                   ("Adjustment clip at playhead", "Adjustment Clip at Playhead", "adj_playhead", _PURPLE),
                   ("Fusion composition over clip", "Fusion Composition Over Clip", "comp_over", _VIOLET),
                   ("Fusion composition over footage", "Fusion Composition Over Footage", "comp_footage", _VIOLET),
                   ("Fusion composition at playhead", "Fusion Composition at Playhead", "comp_playhead", _VIOLET),
                   ("Step back", "Step Back", "step_back", _TEAL),
                   ("Step forward", "Step Forward", "step_forward", _TEAL)]),
    ("Fusion page", [("Tidy nodes", "Tidy Fusion Nodes", "tidy", _GREEN),
                     ("Pull out node", "Pull Out Fusion Node", "pull_out", _GREEN),
                     ("Copy node name", "Copy Node Name", "copy_name", _GREEN),
                     ("Node off / on", "Fusion Node Off - On", "node_off", _GREEN),
                     ("Before / after", "Fusion Before - After", "before_after", _GREEN)]),
]
BY_SCRIPT = {script: (shown, glyph, colour) for _h, rows in SCRIPTS for shown, script, glyph, colour in rows}


def menu_short(script):
    """How it's told apart in Resolve's menu: "Clipse 03" (the three without a number: "Clipse")."""
    return menu_name(script).split(" - ")[0].strip()


class ScriptTable(QWidget):
    """The table - the name, the key given in Resolve: a heading row, then each page's scripts - one chosen (the accent's soft fill), one under the mouse.
    Up / Down move the choice."""
    chosen = Signal(str)  # the script's name in resolve_shortcuts.ACTIONS

    def __init__(self, settings, current=None):
        super().__init__()
        self.settings = settings
        self.current = current or SCRIPTS[0][1][0][1]
        self._hover = None
        self._rows = []  # [(rect, script)]
        from .resolve_keys import script_keys
        self.keys = script_keys()  # {its name in Resolve's menu: [keys given there]} - read from Resolve's own file
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self._fonts()
        lines = sum(len(rows) for _h, rows in SCRIPTS)
        self.setMinimumHeight(round(self._head_h + len(SCRIPTS) * (self._group_h + 4) + lines * self._row_h + 10))
        self.setMinimumWidth(round(self._row_h * 13))

    def _fonts(self):
        k = rel(self.settings, "settings")
        self._name_f = font_at(SMALL * k)
        self._small_f = font_at(SMALL * k)
        self._group_f = font_at(SMALL * k, None, QFont.DemiBold)
        self._key_f = font_at(TINY * k, None, QFont.Medium)
        self._head_f = font_at(TINY * k, None, QFont.DemiBold)
        self._head_f.setCapitalization(QFont.AllUppercase)
        self._head_f.setLetterSpacing(QFont.PercentageSpacing, 106)
        h = QFontMetricsF(self._name_f).height()
        self._row_h = h + 12
        self._group_h = h + 14
        self._head_h = QFontMetricsF(self._head_f).height() + 18
        self._square = round(h + 3)

    def select(self, script):
        if script != self.current:
            self.current = script
            self.update()
            self.chosen.emit(script)

    def paintEvent(self, event):
        from .settings_cards import nav_tile
        t = self.settings.theme
        text, muted = QColor(t["picker_text"]), QColor(t["picker_folder"])
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w = float(self.width())
        pad = 8.0
        # the heading row: what each column is
        p.setFont(self._head_f)
        p.setPen(muted)
        name_x = pad + 10 + self._square + 12
        # (two columns: the name, the key - the name in Resolve's menu is in the details, 2026-10-21: full names here)
        key_w = self._row_h * 4.2
        key_cx = w - pad - 10 - key_w / 2
        p.drawText(QRectF(name_x, 0, w / 2, self._head_h), Qt.AlignLeft | Qt.AlignVCenter, "Name")
        p.drawText(QRectF(key_cx - key_w / 2, 0, key_w, self._head_h), Qt.AlignCenter, "Key")
        line = QColor(text)
        line.setAlphaF(0.08)
        p.fillRect(QRectF(pad, self._head_h - 1, w - 2 * pad, 1), line)
        y = self._head_h + 4
        self._rows = []
        nfm = QFontMetricsF(self._name_f)
        for heading, rows in SCRIPTS:
            p.setFont(self._group_f)
            p.setPen(muted)
            p.drawText(QRectF(pad + 10, y, w, self._group_h), Qt.AlignLeft | Qt.AlignVCenter, heading)
            y += self._group_h
            for shown, script, glyph, colour in rows:
                rect = QRectF(pad, y, w - 2 * pad, self._row_h)
                self._rows.append((rect, script))
                if script == self.current or script == self._hover:
                    fill = QColor(t.get("picker_accent", t["picker_text"]) if script == self.current else t["picker_text"])
                    fill.setAlphaF(0.16 if script == self.current else 0.05)
                    path = QPainterPath()
                    path.addRoundedRect(rect, 7, 7)
                    p.fillPath(path, fill)
                square = nav_tile(glyph, colour, self._square).pixmap(self._square, self._square)
                p.drawPixmap(QPointF(rect.left() + 10, rect.center().y() - self._square / 2).toPoint(), square)
                room = key_cx - key_w / 2 - name_x - 8
                p.setFont(self._name_f)
                p.setPen(text)
                p.drawText(QRectF(name_x, y, room, self._row_h), Qt.AlignLeft | Qt.AlignVCenter,
                           nfm.elidedText(shown, Qt.ElideRight, room))
                keys = self.keys.get(menu_name(script))
                if keys:  # the key given in Resolve, in a soft cap like the app's (keycaps) at this table's size
                    kw = QFontMetricsF(self._key_f).horizontalAdvance(keys[0]) + self._row_h * 0.6
                    cap = QRectF(key_cx - kw / 2, rect.center().y() - self._row_h * 0.36, kw, self._row_h * 0.72)
                    surface = QColor(text)
                    surface.setAlphaF(0.075)
                    path = QPainterPath()
                    path.addRoundedRect(cap, 5, 5)
                    p.fillPath(path, surface)
                    p.setFont(self._key_f)
                    p.setPen(text)
                    p.drawText(cap, Qt.AlignCenter, keys[0])
                y += self._row_h
            y += 4
        p.end()

    def _at(self, pos):
        return next((script for rect, script in self._rows if rect.contains(QPointF(pos))), None)

    def mouseMoveEvent(self, event):
        hover = self._at(event.position())
        if hover != self._hover:
            self._hover = hover
            self.setCursor(Qt.PointingHandCursor) if hover else self.unsetCursor()
            self.update()

    def leaveEvent(self, event):
        self._hover = None
        self.update()

    def mousePressEvent(self, event):
        script = self._at(event.position())
        if script is not None and event.button() == Qt.LeftButton:
            self.setFocus()
            self.select(script)

    def keyPressEvent(self, event):
        order = [script for _h, rows in SCRIPTS for _s, script, _g, _c in rows]
        at = order.index(self.current) if self.current in order else 0
        if event.key() in (Qt.Key_Down, Qt.Key_Up):
            self.select(order[max(0, min(len(order) - 1, at + (1 if event.key() == Qt.Key_Down else -1)))])
            return
        super().keyPressEvent(event)
