"""The Actions panel: the everyday actions of the page Resolve is on (PickerWindow.PANEL_EDIT / PANEL_FUSION),
as tiles four to a row in a panel that slides in from the right (the Actions link in the bottom bar, or
Ctrl/Cmd+K). Typing narrows them down - and finds any action when none of the page's own match. Right-click a
tile: Change key (Settings > Keybindings, at that key).

All groups are on one page - no tabs - so the arrow keys go anywhere:
left/right along a row, up/down to the tile above/below (across groups
too). Enter runs the highlighted tile, typing narrows the tiles down,
Esc (or a click on the list) closes it. Actions that work on a clip use
the clip highlighted in the list behind the panel."""
from PySide6.QtCore import Qt, QRectF, QPointF, QVariantAnimation, QEasingCurve, QTimer
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from .glyphs import ACTION_GLYPH, draw_glyph
from . import look
from .fonts import SMALL, TINY, TITLE, at as font_at  # (the one scale of sizes)

# each group's colour (the glyphs themselves: glyphs.ACTION_GLYPH - one per action)
GROUP_COLOUR = {"Insert": "video", "Insert as": "video", "Clip": "image", "Sound": "audio", "Fusion": "node",
                "Project": "project", "Picker": "action", "Timeline": "video", "Nodes": "node", "Expressions": "node",
                "More": "action", "Resolve": "video"}
COLUMNS = 4
PANEL_W = 640.0  # (four tiles to a row: wide enough that every name fits)
TILE_W = (PANEL_W - 2 * 16 - (COLUMNS - 1) * 8) / COLUMNS  # a tile's width as it ships - a wider panel fits more
LEAST_W = 2 * TILE_W + 2 * 16 + 8  # dragged narrower: two tiles a row at the least
EDGE = 6.0  # px either side of the panel's left edge that drag it wider (2026-10-21: "drag the actions slideout to
#             go more out") - kept in display["actions_width"], a double-click there gives it its own width back

# Where an action can be given a key - a small symbol each, quiet, in the tile's corner (and the picker's on its
# key): (glyph, what hovering it says). Resolve's work without the picker open.
KEY_PLACES = {
    "script": ("scripts", "Keyboard Customization in Resolve - a Clipse script there (Workspace \u203a Scripts): "
                          "its key works without the picker open"),
    "resolve": ("keys", "Keyboard Customization in Resolve - Resolve's own command: its key works without the picker"),
    "picker": ("search", "Clipse's own key - works while the picker is open"),
}


# Actions that are one thing done a few ways share a tile (2026-10-15): it shows one of them, with quiet
# grey arrows at its sides to slide to the others, and remembers which (display["action_shown"]). Each is still an
# action of its own - favourited, it's a whole tile in Favourites, and one left by itself is a plain tile.
FAMILIES = {
    "Adjustment clip": [("Adjustment clip over clip", "Over clip"), ("Adjustment clip over footage", "Over footage"),
                        ("Adjustment clip at playhead", "At playhead")],
    "Fusion composition": [("Fusion composition over clip", "Over clip"),
                           ("Fusion composition over footage", "Over footage"),
                           ("Fusion composition at playhead", "At playhead")],
    "Use of clip": [("Next use of clip", "Next"), ("Previous use of clip", "Previous")],
    "Step": [("Step back", "Back"), ("Step forward", "Forward")],
    "Mark the beat": [("Mark the beats", "Beats"), ("Mark the bars", "Bars")],
}
FAMILY_OF = {label: (family, short) for family, members in FAMILIES.items() for label, short in members}


def script_red(theme):
    """The red of a script's symbol - a little deeper on a light theme."""
    from .settings import is_light
    return QColor("#c9433c" if is_light(theme["picker_bg"]) else "#e5534b")


def key_places(label, key):
    """Where `label` can have a key: a few of "script", "resolve", "picker" (KEY_PLACES)."""
    from .settings import RESOLVE_KEYED, RESOLVE_NATIVE
    return ([("script", RESOLVE_KEYED[label])] if label in RESOLVE_KEYED else []) \
        + ([("resolve", RESOLVE_NATIVE[label])] if label in RESOLVE_NATIVE else []) + ([("picker", key)] if key else [])


class ActionsPanel(QWidget):
    def __init__(self, picker):
        super().__init__(picker)
        self.picker = picker
        self.settings = picker.settings
        self.setMouseTracking(True)
        self.hide()
        self.filter = ""
        self.index = 0
        self.scroll = 0.0
        self._tiles = []      # [(rect in panel coords, action index)], laid out for the current filter
        self._hover = None
        self._mouse = None     # where the mouse is (a shared tile's arrows light under it)
        self._slide = 0.0
        self._dragging = False  # the left edge, being dragged
        self._edge_hot = False  # the mouse on the left edge
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(170)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.valueChanged.connect(self._on_slide)
        self._anim.finished.connect(self._on_slide_done)
        self._caret_on = True  # the search field's caret, blinking
        self._caret = QTimer(self)
        self._caret.setInterval(530)
        self._caret.timeout.connect(self._blink)

    def _blink(self):
        self._caret_on = not self._caret_on
        k = self._k()
        field = self._field_rect()
        self.update(QRectF(field.left() * k, field.top() * k, field.width() * k, field.height() * k)
                    .toAlignedRect().adjusted(-3, -3, 3, 3))

    # -- its own zoom (Ctrl and + / - / 0 while it's open): what's in the panel drawn at that size, so everything in
    # it - tiles, symbols, words, gaps - shrinks or grows together, the panel as wide as it was (zoomed out, more
    # tiles a row: _columns); what's below works in the panel's own units --
    def _k(self):
        from .fonts import own_zoom
        return own_zoom(self.settings, "actions")

    def _vw(self):
        return self.width() / self._k()

    def _vh(self):
        return self.height() / self._k()

    def _v(self, pos):
        """A point on the widget in the panel's own units."""
        k = self._k()
        return QPointF(pos.x() / k, pos.y() / k)

    def zoom_panel(self, direction):
        from .fonts import step_zoom
        step_zoom(self.settings, "actions", direction)
        self.settings.save()
        self.scroll = 0.0
        self.update()

    # -- open / close --
    def open(self):
        self.filter, self.index, self.scroll = "", 0, 0.0
        self.setGeometry(self.picker._placed_rect())  # (over the preview too while it shares the window: room to widen)
        self.raise_()
        self.show()
        self._caret_on = True
        self._caret.start()
        self._anim.stop()
        self._anim.setStartValue(self._slide)
        self._anim.setEndValue(1.0)
        self._anim.start()

    def close_panel(self):
        if not self.isVisible():
            return
        self._caret.stop()
        self._anim.stop()
        self._anim.setStartValue(self._slide)
        self._anim.setEndValue(0.0)
        self._anim.start()

    def toggle(self):
        if self.isVisible() and self._anim.endValue() == 1.0:
            self.close_panel()
        else:
            self.open()

    def _on_slide(self, value):
        self._slide = float(value)
        self.update()

    def _on_slide_done(self):
        if self._slide <= 0.001:
            self.hide()
            self.picker.search_edit.setFocus()

    # -- the actions --
    def _visible_actions(self):
        """[(group, label, key, fn, index in self._shown)] - the page's actions, or what the typed filter finds."""
        self._shown = self.picker.panel_actions(self.filter)
        return [(g, label, key, fn, i) for i, (g, label, key, fn) in enumerate(self._shown)]

    def _panel_rect(self):
        # (its width on the screen stays as it is whatever the zoom - only what's in it grows or shrinks, 2026-10-21:
        # "The zoom should not change the action window, only content")
        width = min(self._wanted_width(), self.width() - 40.0) / self._k()
        x = self._vw() - width * self._slide
        return QRectF(x, 0, width, self._vh())

    def _wanted_width(self):
        try:
            return max(LEAST_W, float(self.settings.display.get("actions_width") or PANEL_W))
        except (TypeError, ValueError):
            return PANEL_W

    def _columns(self, panel):
        """Four tiles a row as it ships; dragged wider or narrower, as many as fit at the same tile width."""
        return max(2, int((panel.width() - 2 * 16 + 8) // (TILE_W + 8)))

    def _on_edge(self, pos):
        """`pos` (the panel's units) on its left edge - where it's dragged wider."""
        panel = self._panel_rect()
        return self._slide >= 0.999 and abs(pos.x() - panel.left()) <= EDGE / self._k()

    def _field_rect(self):
        """The search field at the top of the panel."""
        panel = self._panel_rect()
        height = QFontMetricsF(self._fonts()[4]).height() + 18
        return QRectF(panel.left() + 16, 14, panel.width() - 32, height)

    def _view_top(self):
        """Where the tiles start: under the search field."""
        return self._field_rect().bottom() + 12

    def _fonts(self):
        base = QFont(self.picker.font())
        label = font_at(SMALL, base)
        key = font_at(TINY, base, QFont.DemiBold)
        head = font_at(TINY, base, QFont.DemiBold)
        head.setCapitalization(QFont.AllUppercase)
        head.setLetterSpacing(QFont.PercentageSpacing, 110)
        title = font_at(TITLE, base, QFont.DemiBold)
        field = font_at(1.0, base)
        return title, head, label, key, field

    def _layout(self, panel):
        """Tile rects (relative to the panel's content, before scrolling) and section headers."""
        title_f, head_f, label_f, key_f, field_f = self._fonts()
        pad, gap = 16.0, 8.0
        columns = self._columns(panel)
        tile_w = (panel.width() - 2 * pad - (columns - 1) * gap) / columns
        # symbol, the name (two lines, three when one shown needs it - every tile the same height), the key
        lfm = QFontMetricsF(label_f)
        self._name_lines = max([2] + [len(_wrap(a[1].rstrip("\u2026"), lfm, tile_w - 12))
                                      for a in self._visible_actions()])
        tile_h = 10 + 30 + 6 + self._name_lines * lfm.height() + 6 + QFontMetricsF(key_f).height() + 3 + 10
        y = self._view_top() + 6
        tiles, heads = [], []
        group = None
        col = 0
        actions = self._visible_actions()
        n = 0
        while n < len(actions):
            g, label, key, fn, i = actions[n]
            # a family: this one and the next of the same family in the group, sharing a tile (not in Favourites)
            family = FAMILY_OF.get(label, (None,))[0] if g != "Favourites" else None
            count = 1
            while family and n + count < len(actions) and actions[n + count][0] == g \
                    and FAMILY_OF.get(actions[n + count][1], (None,))[0] == family:
                count += 1
            if g != group:
                if group is not None:
                    y += tile_h + 14
                heads.append((g, y))
                y += QFontMetricsF(head_f).height() + 8
                group, col = g, 0
            elif col == columns:
                y += tile_h + gap
                col = 0
            rect = QRectF(pad + col * (tile_w + gap), y, tile_w, tile_h)
            if count == 1:
                tiles.append((rect, n, g, label, key, i, None))
            else:  # one of them shown - the one shown last time
                members = list(range(n, n + count))
                remembered = self.settings.display.get("action_shown", {}).get(family)
                at = next((k for k, m in enumerate(members) if actions[m][1] == remembered), 0)
                g2, label2, key2, _fn2, i2 = actions[members[at]]
                tiles.append((rect, members[at], g2, label2, key2, i2,
                              {"family": family, "members": [actions[m][1] for m in members],
                               "ns": members, "at": at}))
            n += count
            col += 1
        bottom = (y + tile_h + 16) if tiles else y
        return tiles, heads, bottom

    # -- painting --
    def paintEvent(self, event):
        t = self.settings.theme
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        scrim = QColor(t["picker_bg"])
        scrim.setAlphaF(0.55 * self._slide)
        p.fillRect(self.rect(), scrim)
        p.scale(self._k(), self._k())
        panel = self._panel_rect()
        d = self.settings.display
        from .fonts import picker_scale
        radius = d["outer_corner_radius"] * picker_scale(self.settings)
        shape = QPainterPath()
        shape.addRoundedRect(panel.adjusted(0, 0.5, -0.5, -0.5), radius, radius)
        p.fillPath(shape, QColor(t.get("picker_bar_bg", t["picker_bg"])))
        p.setPen(QPen(QColor(t["picker_border"]), 1))
        p.drawLine(QPointF(panel.left() + 0.5, 0), QPointF(panel.left() + 0.5, self._vh()))
        if self._edge_hot or self._dragging:  # the edge that drags it wider, lit under the mouse
            lit = QColor(t["picker_text"])
            lit.setAlphaF(0.45)
            p.setPen(QPen(lit, 2.0 / self._k()))
            p.drawLine(QPointF(panel.left() + 0.5, 0), QPointF(panel.left() + 0.5, self._vh()))

        title_f, head_f, label_f, key_f, field_f = self._fonts()
        self._paint_field(p, field_f)

        from . import presets as pm
        self._presets = {preset["name"]: preset for preset in pm.all_presets(self.settings)}
        tiles, heads, bottom = self._layout(panel)
        origin = {label: group for group, label, _key, _fn in self.picker._actions()}  # (each action's own group)
        view_top = self._view_top()
        view_h = self._vh() - view_top - 26.0
        self._max_scroll = max(0.0, bottom - view_top - view_h)
        self.scroll = min(self.scroll, self._max_scroll)
        shown_ns = [tile[1] for tile in tiles]
        if self.index not in shown_ns:  # (a shared tile shows one of its ways: the highlight is on a shown one)
            self.index = shown_ns[0] if shown_ns else 0
        p.save()
        p.setClipRect(QRectF(panel.left(), view_top, panel.width(), view_h))
        p.translate(panel.left(), -self.scroll)
        hfm = QFontMetricsF(head_f)
        for g, y in heads:
            p.setFont(head_f)
            p.setPen(QColor(t["picker_folder"]))
            p.drawText(QRectF(16, y, panel.width() - 32, hfm.height()), Qt.AlignLeft | Qt.AlignVCenter, g)
        lfm = QFontMetricsF(label_f)
        tag_c = QColor(t["picker_folder"])
        tag_c.setAlphaF(0.85)
        red = script_red(t)  # (a Clipse script in Resolve's menu: red, so scripts are told apart)
        self._tiles = []
        self._tag_spots = []  # [(rect, what hovering it says)] - where a key can be set
        self._arrows = []     # [(rect, tile's action n, step)] - a shared tile's arrows to slide its ways
        for rect, n, g, label, key, i, part in tiles:
            self._tiles.append((rect.translated(panel.left(), -self.scroll), n, i))
            selected = n == self.index
            hovered = n == self._hover
            look.paint_tile(p, rect, self.settings, chosen=selected, hover=hovered)  # (the app's one tile)
            try:  # (the colour of the group it belongs to - Favourites and Scripts gather from several)
                colour = QColor(self.settings.icon_color(GROUP_COLOUR.get(origin.get(label, g), "action")))
            except KeyError:
                colour = QColor(t["picker_accent"])
            tint = QColor(colour)
            tint.setAlpha(46)
            p.setPen(Qt.NoPen)
            p.setBrush(tint)
            if g == "Insert as":  # a preset: its little drawing
                chip = QRectF(rect.center().x() - 24, rect.top() + 10, 48, 30)
                p.drawRoundedRect(chip, 8, 8)
                preset = self._presets.get(label)
                if preset is not None:
                    from .insert_as_dialog import _colors, draw_preset
                    draw_preset(p, chip.adjusted(6, 4, -6, -3), preset, _colors(t))
            else:
                chip = QRectF(rect.center().x() - 15, rect.top() + 10, 30, 30)
                p.drawRoundedRect(chip, 8, 8)
                draw_glyph(p, ACTION_GLYPH.get(label, "insert"), chip.center(), 17, colour)
            p.setFont(label_f)
            p.setPen(QColor(t["picker_text"]))
            # (no "..." after a name that opens something: in a tile it read as a name cut short)
            lines = _wrap(label.rstrip("\u2026"), lfm, rect.width() - 12)
            text_top = rect.top() + 46 + (self._name_lines - len(lines)) * lfm.height() / 2
            for k, line in enumerate(lines):
                p.drawText(QRectF(rect.left() + 6, text_top + k * lfm.height(), rect.width() - 12, lfm.height()),
                           Qt.AlignHCenter | Qt.AlignVCenter, line)
            if g != "Insert as":  # Resolve's Keyboard Customization: a quiet symbol in the corner (KEY_PLACES)
                spot_x = rect.right() - 9
                for place, _name in key_places(label, key):
                    if place == "picker":
                        continue
                    side = 13.0
                    spot = QRectF(spot_x - side, rect.top() + 8, side, side)
                    draw_glyph(p, KEY_PLACES[place][0], spot.center(), side, red if place == "script" else tag_c)
                    self._tag_spots.append((spot.translated(panel.left(), -self.scroll).adjusted(-3, -3, 3, 3),
                                            KEY_PLACES[place][1]))
                    spot_x -= side + 6
            if part is not None:  # a shared tile: quiet arrows to slide to its other ways (FAMILIES)
                self._paint_arrows(p, rect, n, panel, hovered, part)
            if key and self.settings.keybinds.get(key):  # the picker's own key, in the app's keycap, its symbol in it
                from . import keycaps
                cap_h = keycaps.sizes(label_f)[0]
                keycap = keycaps.cap(p, rect.center().x(), rect.bottom() - 10 - cap_h / 2,
                                     keycaps.key_name(self.settings.keybinds[key]), label_f, t, glyph="search",
                                     room=rect.width() - 12)
                self._tag_spots.append((keycap.translated(panel.left(), -self.scroll), KEY_PLACES["picker"][1]))
        if not tiles:
            p.setFont(label_f)
            p.setPen(QColor(t["picker_folder"]))
            p.drawText(QRectF(0, view_top + 18, panel.width(), 30), Qt.AlignCenter, "No action matches")
        p.restore()
        p.end()

    def _paint_arrows(self, p, rect, n, panel, hovered, part):
        """‹ and › in a shared tile's bottom corners, a dot for each way between them (the one shown lit) - faint,
        a little clearer with the mouse on the tile, clearest on the arrow itself."""
        t = self.settings.theme
        mouse = getattr(self, "_mouse", None)
        cy = rect.bottom() - 13
        count = len(part["members"])
        for k in range(count):
            dot = QColor(t["picker_text"] if k == part["at"] else t["picker_folder"])
            dot.setAlphaF(0.55 if k == part["at"] else 0.2)
            p.setPen(Qt.NoPen)
            p.setBrush(dot)
            p.drawEllipse(QPointF(rect.center().x() + (k - (count - 1) / 2) * 7, cy), 1.6, 1.6)
        for step in (-1, 1):
            spot = QRectF(rect.left() + 4 if step < 0 else rect.right() - 26, cy - 11, 22, 22)
            on = mouse is not None and spot.translated(panel.left(), -self.scroll).contains(mouse)
            colour = QColor(t["picker_text"] if on else t["picker_folder"])
            colour.setAlphaF(0.9 if on else 0.45 if hovered else 0.22)
            p.setPen(QPen(colour, 1.2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            p.setBrush(Qt.NoBrush)
            cx, cy, d = spot.center().x(), spot.center().y(), 3.0
            path = QPainterPath()
            path.moveTo(cx + d * step * -0.6, cy - d)
            path.lineTo(cx + d * step * 0.6, cy)
            path.lineTo(cx + d * step * -0.6, cy + d)
            p.drawPath(path)
            self._arrows.append((spot.translated(panel.left(), -self.scroll), n, step))

    def _slide_way(self, n, step):
        """A shared tile to its next (step 1) or previous way - remembered for next time."""
        panel = self._panel_rect()
        tiles, _heads, _bottom = self._layout(panel)
        part = next((part for _r, m, *_rest, part in tiles if m == n and part), None)
        if part is None:
            return
        at = (part["at"] + step) % len(part["members"])
        shown = dict(self.settings.display.get("action_shown") or {})
        shown[part["family"]] = part["members"][at]
        self.settings.display["action_shown"] = shown
        self.settings.save()
        if self.index == n:  # (the highlight goes with it)
            self.index = part["ns"][at]
        self.update()

    def _paint_field(self, p, font):
        """The search field: a magnifier, what's typed (or what to type), the caret - like Expressions' Find."""
        t = self.settings.theme
        rect = self._field_rect()
        text_c, muted = QColor(t["picker_text"]), QColor(t["picker_folder"])
        edge = QColor(text_c)
        edge.setAlphaF(0.38)
        p.setPen(QPen(edge, 1.2))
        p.setBrush(QColor(t["picker_bg"]))
        r = look.radius(self.settings, "control")
        p.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), r, r)
        draw_glyph(p, "search", QPointF(rect.left() + 20, rect.center().y()), 15, text_c)
        x = rect.left() + 37
        room = rect.right() - 12 - x
        fm = QFontMetricsF(font)
        shown = fm.elidedText(self.filter, Qt.ElideLeft, room) if self.filter \
            else fm.elidedText("Search actions", Qt.ElideRight, room)
        p.setFont(font)
        p.setPen(text_c if self.filter else muted)
        p.drawText(QRectF(x, rect.top(), room, rect.height()), Qt.AlignLeft | Qt.AlignVCenter, shown)
        if self._caret_on:
            cx = x + (fm.horizontalAdvance(shown) + 1.5 if self.filter else 0)
            p.setPen(QPen(QColor(t["picker_accent"]), 1.4))
            p.drawLine(QPointF(cx, rect.center().y() - fm.ascent() * 0.62),
                       QPointF(cx, rect.center().y() + fm.ascent() * 0.62))

    def _typed(self):
        """Something was typed or taken away: the caret shows, the tiles start over from the top."""
        self._caret_on = True
        self._caret.start()
        self.index, self.scroll = 0, 0.0
        self.update()

    # -- keys --
    def _move(self, dx, dy):
        tiles = self._tiles
        if not tiles:
            return
        cur = next((r for r, n, _i in tiles if n == self.index), tiles[0][0])
        if dx:
            order = [n for _r, n, _i in tiles]
            at = order.index(self.index) if self.index in order else 0
            self.index = order[max(0, min(len(order) - 1, at + dx))]
        else:
            # the nearest tile in the next row up / down (across groups too)
            cands = [(r, n) for r, n, _i in tiles if (r.top() > cur.top() + 1 if dy > 0 else r.top() < cur.top() - 1)]
            if cands:
                row_y = min(r.top() for r, _n in cands) if dy > 0 else max(r.top() for r, _n in cands)
                row = [(r, n) for r, n in cands if abs(r.top() - row_y) < 1]
                self.index = min(row, key=lambda rn: abs(rn[0].center().x() - cur.center().x()))[1]
        self._ensure_visible()
        self.update()

    def _ensure_visible(self):
        panel = self._panel_rect()
        tiles, _heads, _bottom = self._layout(panel)
        rect = next((r for r, n, *_ in tiles if n == self.index), None)
        if rect is None:
            return
        view_top = self._view_top()
        view_h = self._vh() - view_top - 26.0
        if rect.top() - self.scroll < view_top:
            self.scroll = max(0.0, rect.top() - view_top - 24)
        elif rect.bottom() - self.scroll > view_top + view_h:
            self.scroll = rect.bottom() - (view_top + view_h) + 8

    def _run(self, action_index):
        actions = getattr(self, "_shown", None) or self.picker.panel_actions(self.filter)
        if not 0 <= action_index < len(actions):
            return
        fn = actions[action_index][3]
        self.close_panel()
        QTimer.singleShot(0, fn)

    def handle_key(self, ev):
        """Keys while the panel is open. Returns True (always takes them)."""
        key = ev.key()
        from .fonts import zoom_key
        direction = zoom_key(ev, self.settings)
        if direction is not None:  # Ctrl and + / - / 0: the panel by itself
            self.zoom_panel(direction)
            return True
        if key == Qt.Key_Escape:
            if self.filter:
                self.filter = ""
                self._typed()
            else:
                self.close_panel()
        elif key in (Qt.Key_Return, Qt.Key_Enter):
            hit = next((i for _r, n, i in self._tiles if n == self.index), None)
            if hit is not None:
                self._run(hit)
        elif key in (Qt.Key_Left, Qt.Key_Right) and ev.modifiers() & Qt.ShiftModifier:
            self._slide_way(self.index, -1 if key == Qt.Key_Left else 1)  # (a shared tile: its other ways)
        elif key == Qt.Key_Left:
            self._move(-1, 0)
        elif key in (Qt.Key_Right, Qt.Key_Tab):
            self._move(1, 0)
        elif key == Qt.Key_Up:
            self._move(0, -1)
        elif key == Qt.Key_Down:
            self._move(0, 1)
        elif key == Qt.Key_Backspace:
            self.filter = self.filter[:-1]
            self._typed()
        elif ev.text() and ev.text().isprintable() and not (ev.modifiers() & (Qt.ControlModifier | Qt.MetaModifier)):
            self.filter += ev.text()
            self._typed()
        elif self._is_favourite_key(ev):
            self._favourite_selected()
        elif key in (Qt.Key_K,) and ev.modifiers() & Qt.ControlModifier:
            self.close_panel()
        return True

    def _is_favourite_key(self, ev):
        from .picker_window import _seq_matches
        return any(_seq_matches(ev, slot.get("toggle_favorite", ""))
                   for slot in (self.settings.keybinds, self.settings.keybinds_secondary))

    def _favourite_selected(self):
        """The favourite key (Ctrl+F) in the panel: the selected tile's action to Favourites, or back out - as
        right-click > Favourite does. The selection stays on it, wherever it moved to."""
        actions = getattr(self, "_shown", None) or []
        hit = next((i for _r, n, i in getattr(self, "_tiles", []) if n == self.index), None)
        if hit is None or not 0 <= hit < len(actions):
            return
        label = actions[hit][1]
        on = not self.picker.is_favourite_action(label)
        self.picker.favourite_action(label, on)
        shown = self._visible_actions()
        self.index = next((n for n, (g, lab, _k, _f, _i) in enumerate(shown)
                           if lab == label and (g == "Favourites") == on),
                          next((n for n, a in enumerate(shown) if a[1] == label), 0))
        self.update()

    # -- mouse --
    def _tile_at(self, pos):
        return next(((n, i) for r, n, i in self._tiles if r.contains(QPointF(pos))), (None, None))

    def mouseMoveEvent(self, ev):
        pos = self._v(ev.position())
        if self._dragging:
            width = max(LEAST_W, min((self._vw() - pos.x()) * self._k(), self.width() - 40.0))
            self.settings.display["actions_width"] = round(width, 1)
            self.update()
            return
        hot = self._on_edge(pos)
        if hot != self._edge_hot:
            self._edge_hot = hot
            self.setCursor(Qt.SizeHorCursor) if hot else self.unsetCursor()
            self.update()
        n, _i = self._tile_at(self._v(ev.position()))
        was = next((a for a in getattr(self, "_arrows", []) if self._mouse is not None and a[0].contains(self._mouse)),
                   None) if getattr(self, "_mouse", None) is not None else None
        self._mouse = self._v(ev.position())
        if was != next((a for a in getattr(self, "_arrows", []) if a[0].contains(self._mouse)), None):
            self.update()  # (an arrow lights under the mouse)
        tip = next((text for rect, text in getattr(self, "_tag_spots", []) if rect.contains(self._mouse)), "")
        on_arrow = any(rect.contains(self._mouse) for rect, _n, _s in getattr(self, "_arrows", []))
        if not tip and not on_arrow and _i is not None:  # resting on a tile: what it does
            tip = self._what_it_does(_i)
        if tip != self.toolTip():
            self.setToolTip(tip)
        if n != self._hover:
            self._hover = n
            self.update()

    def _what_it_does(self, action_index):
        """A tile's hover text: what its action does (help_text.ACTIONS; a preset: what it's set up to do)."""
        actions = getattr(self, "_shown", None) or []
        if not 0 <= action_index < len(actions):
            return ""
        g, label, _key, _fn = actions[action_index]
        if g == "Insert as":
            preset = getattr(self, "_presets", {}).get(label)
            from . import presets as pm
            return pm.summary(preset) if preset else ""
        from .help_text import ACTIONS
        return ACTIONS.get(label, "")

    def leaveEvent(self, ev):
        self._hover = self._mouse = None
        if self._edge_hot and not self._dragging:
            self._edge_hot = False
            self.unsetCursor()
        self.update()

    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton and self._on_edge(self._v(ev.position())):
            self._dragging = True
            return
        if not self._panel_rect().contains(self._v(ev.position())):
            self.close_panel()  # a click on the dimmed list closes the panel
            return
        arrow = next(((n, step) for rect, n, step in getattr(self, "_arrows", []) if rect.contains(self._v(ev.position()))), None)
        if arrow is not None and ev.button() == Qt.LeftButton:
            self._slide_way(*arrow)
            return
        n, i = self._tile_at(self._v(ev.position()))
        if i is None:
            return
        self.index = n
        if ev.button() == Qt.RightButton:
            self._key_menu(i, ev.globalPosition().toPoint())
        elif ev.button() == Qt.LeftButton:
            self._run(i)

    def _key_menu(self, action_index, at):
        """Right-click on a tile: Favourite (to the top of the panel) - and Change key: Settings > Keybindings, at
        this action's key (or Key in Resolve)."""
        actions = getattr(self, "_shown", None) or []
        if not 0 <= action_index < len(actions):
            return
        g, label, key, _fn = actions[action_index]
        places = [] if g == "Insert as" else key_places(label, key)
        from .preview_menu import BarMenu, MenuRow
        menu = BarMenu(self.settings)
        menu.setParent(self.window(), menu.windowFlags())
        in_resolve = any(place != "picker" for place, _n in places)
        favourite = self.picker.is_favourite_action(label)
        choices = [("Unfavourite" if favourite else "Favourite", "favourite",
                    lambda: (self.picker.favourite_action(label, not favourite), self.update()))]
        choices += [("Key in Resolve\u2026" if place != "picker" else
                     "Key in the picker\u2026" if in_resolve else "Change key\u2026", KEY_PLACES[place][0],
                     (lambda name=name: self._key_in_resolve(name)) if place != "picker"
                     else (lambda name=name: self._change_key(name)))
                    for place, name in places]
        for text, glyph, run in choices:
            row = MenuRow(self.settings, text, glyph, kind="more")
            row.setFont(self._fonts()[2])
            row.setFixedHeight(row.sizeHint().height())
            row.clicked.connect(lambda run=run: (menu.hide(), run()))
            menu.box.addWidget(row)
        menu.adjustSize()
        menu.move(at.x() + 2, at.y() + 2)
        menu.show()
        self._menu = menu

    def _key_in_resolve(self, name):
        """A key in Resolve's own Keyboard Customization (a Clipse script there, or Resolve's own
        command). No script can open that window: the name goes onto the clipboard, the picker out of the way
        so Resolve is in front, and a note says what to press and where to paste it."""
        self.hide()
        self._slide = 0.0
        self.picker._key_in_resolve(name)

    def _change_key(self, key):
        self.hide()
        self._slide = 0.0
        self.picker.open_settings(key=key)

    def mouseReleaseEvent(self, ev):
        if self._dragging:
            self._dragging = False
            self.settings.save()
            self.update()

    def mouseDoubleClickEvent(self, ev):
        if self._on_edge(self._v(ev.position())):  # its own width back
            self.settings.display.pop("actions_width", None)
            self.settings.save()
            self.update()
            return
        super().mouseDoubleClickEvent(ev)

    def wheelEvent(self, ev):
        self.scroll = max(0.0, min(getattr(self, "_max_scroll", 0.0), self.scroll - ev.angleDelta().y() / 2))
        self.update()

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self.update()


def _wrap(text, fm, width, most=3):
    """The name on as few lines as it fits on, up to `most` - split between words, or after a hyphen
    ("davinci-" / "search's") - the lines as even as can be. Only a name too long even for that ends in ..."""
    import re
    words = [w for w in re.split(r"(?<=-)|\s+", text) if w]
    pos, joined = 0, []
    for w in words:  # (after a hyphen the next piece follows with no space)
        at = text.index(w, pos)
        pos = at + len(w)
        joined.append(text[pos:pos + 1] != " ")

    def line(a, b):
        return "".join(words[k] + ("" if joined[k] or k == b - 1 else " ") for k in range(a, b))

    def split(a, lines):
        if lines == 1:
            one = line(a, len(words))
            return [one] if fm.horizontalAdvance(one) <= width else None
        best = None
        for cut in range(a + 1, len(words)):
            first = line(a, cut)
            if fm.horizontalAdvance(first) > width:
                break
            rest = split(cut, lines - 1)
            if rest is not None:
                widest = max(fm.horizontalAdvance(x) for x in [first] + rest)
                if best is None or widest < best[0]:
                    best = (widest, [first] + rest)
        return best[1] if best else None

    for lines in range(1, min(most, len(words)) + 1):
        got = split(0, lines)
        if got:
            return got
    out, a = [], 0  # too long even on `most` lines: filled as they come, the last cut short
    while a < len(words) and len(out) < most - 1:
        b = a + 1
        while b < len(words) and fm.horizontalAdvance(line(a, b + 1)) <= width:
            b += 1
        out.append(fm.elidedText(line(a, b), Qt.ElideRight, width))
        a = b
    if a < len(words):
        out.append(fm.elidedText(line(a, len(words)), Qt.ElideRight, width))
    return out
