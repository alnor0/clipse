"""The expression cheat sheet: what you can write in a Fusion expression,
as tiles laid over the picker (x: then its row, > expression cheat sheet,
or Cheat sheet in the bottom bar on the Fusion page). Each tile is a piece
of code and one line on what it gives.

Two fields along the top. Find: typing narrows the tiles down. Node name:
where a piece names another node, this name is written into it. It's the
node selected in Fusion - click another node there while the sheet is open
and the sheet follows (WATCH_MS) - or type one (Tab, or a click on the
field); fusion_expressions.NODE stands there while it's empty. The picker
is usually over the node you want, so the field's ring (or Enter in the
field before typing) hides the picker until you click a node in Fusion,
then brings the sheet back with that name in it. The key for Copy node
name (Settings > Keybindings), or the field's copy mark, copies just the name.

A tile says what a piece gives first, in plain words, with a small drawing
of it where there's something to draw (fusion_expressions.sheet_curve) -
then the code. The accent colour is kept for the caret and "Copied".

Enter copies the highlighted piece and closes the picker - you paste it in
Fusion next. Shift+Enter, Ctrl/Cmd+C or a click copies and stays, to take
several. Page Down / Up (or a click on a group's name) goes to the next
group, Esc goes back to the list."""
import re
import time

from PySide6.QtCore import Qt, QRectF, QPointF, QTimer
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from . import fusion_expressions as fx
from .glyphs import draw_glyph
from .settings import is_light
from .fonts import SMALL, TINY, TITLE, at as font_at  # (the one scale of sizes)

GROUP_GLYPH = {"Composition": "x_comp", "Time": "x_time", "Waves": "x_waves", "Maths": "x_sums",
               "Fusion": "x_nodes", "Comparing and choosing": "x_choices", "Text": "x_words", "Lists": "x_sums",
               "Date and time": "x_dates", "Bits": "x_sums", "Lua": "x_comp",
               "Choices": "x_choices", "Other nodes": "x_nodes", "Picture size": "x_size", "Words": "x_words",
               "Dates": "x_dates"}
PAD, GAP = 20.0, 10.0
TILE_PAD = 12.0
FOOTER = 38.0
COPIED_SECONDS = 1.4
CURVE_W, CURVE_H = 74.0, 30.0  # the small drawing in a tile
WATCH_MS = 350  # how often Fusion is asked which node is selected, while the sheet is open
_BREAK_AFTER = " ,(/"


# The stand-ins, always the same letters: x, y, z a number - s, w words - t a list - c yes or no - f a function -
# ... as many more as you like. In a colour of their own (not the accent: that's for what's chosen).
STAND_IN_DARK, STAND_IN_LIGHT = "#9fd4a8", "#2c7a4b"
_BLANK = re.compile(r"(?<![\w.:])[a-z](?![\w(])|(?:(?<=\()|(?<=, ))\.\.\.")


def _blanks(text):
    """[(start, end)] of the stand-ins in a piece - the a, b, s, x ... (and ...) that mean "yours goes here", not
    something to type as it is. Not inside quotes, after a -- note, or in a piece of several steps (there a
    letter is a real name)."""
    if text.startswith(":"):
        return []
    code = text.split("--")[0]
    spans, quoted, start = [], None, 0
    for k, ch in enumerate(code + "\0"):
        if quoted is None and ch in "\"'" or k == len(code):
            spans += [(start + m.start(), start + m.end()) for m in _BLANK.finditer(code[start:k])]
            quoted = ch if k < len(code) else None
        elif quoted is not None and ch == quoted:
            quoted, start = None, k + 1
    return spans


def _with_node(code, node):
    """(the code with the node's name in, [(start, end) of each place it is, and (start, end, "blank") of each stand-in])."""
    if isinstance(code, tuple):  # several small pieces, each its own box
        return code, []
    name = node or fx.NODE
    text, marks = "", []
    parts = code.split(fx.NODE)
    for k, part in enumerate(parts):
        text += part
        if k < len(parts) - 1:
            marks.append((len(text), len(text) + len(name)))
            text += name
    return text, sorted(marks + [(a, b, "blank") for a, b in _blanks(text)])


def _wrap_code(text, fm, width):
    """[(start, end)] - the code cut into lines that fit, after a space, comma, bracket or slash where it can."""
    lines, start = [], 0
    while start < len(text):
        end = start + 1
        while end < len(text) and fm.horizontalAdvance(text[start:end + 1]) <= width:
            end += 1
        if end < len(text):  # never in the middle of a word when there's a better place
            best = max((k + 1 for k in range(start + 5, end) if text[k] in _BREAK_AFTER), default=0)
            if best:
                end = best
        lines.append((start, end))
        start = end
        while start < len(text) and text[start] == " ":
            start += 1
    return lines or [(0, 0)]


class ExpressionSheet(QWidget):
    def __init__(self, picker):
        super().__init__(picker)
        self.picker = picker
        self.settings = picker.settings
        self.setMouseTracking(True)
        self.node = ""          # the name written into the pieces
        self.from_fusion = ""   # the node that was selected in Fusion when the sheet opened
        self.filter = ""
        self.field = "find"     # the field typing goes into: "find" or "node"
        self._node_fresh = False  # the node field was just entered: the first letter typed replaces the name
        self.index = 0          # the highlighted tile, counted over the ones showing
        self.scroll = 0.0
        self._hover = None
        self._copied = (None, 0.0)  # (the code that was just copied, when)
        self._laid = (None, None)
        self._chips = []        # [(rect, group)] as painted
        self._fields = {}       # {"find": rect, "node": rect} as painted
        self._max_scroll = 0.0
        self._caret_on = True
        self._caret = QTimer(self)
        self._caret.setInterval(530)
        self._caret.timeout.connect(self._blink)
        self._node_copy = QRectF()  # the copy mark in the Node name field, as painted
        self._node_pick = QRectF()  # ...and the ring that picks a node by a click in Fusion
        self._mouse = QPointF(-1, -1)
        self._note = ("", 0.0)  # a few words in the Node name field for a moment, and when they were put there
        self._name_copied = 0.0     # when the name was last copied (a tick shows for a moment)
        self._followed = 0.0        # when the name last followed a click in Fusion (the field lights up for a moment)
        self._watch = QTimer(self)
        self._watch.setInterval(WATCH_MS)
        self._watch.timeout.connect(self.follow_fusion)
        self.hide()

    # -- its own zoom (Ctrl and + / - / 0 while it's open, as the Actions panel): everything in it drawn at that size,
    # the sheet as big as it was - zoomed out, more columns and rows (2026-10-22: it zoomed the picker's words only,
    # and on Linux nothing at all); below, sizes and the mouse are in the sheet's own units --
    def _k(self):
        from .fonts import own_zoom
        return own_zoom(self.settings, "expressions")

    def _vw(self):
        return self.width() / self._k()

    def _vh(self):
        return self.height() / self._k()

    def _v(self, pos):
        k = self._k()
        return QPointF(pos.x() / k, pos.y() / k)

    def zoom_sheet(self, direction):
        from .fonts import step_zoom
        step_zoom(self.settings, "expressions", direction)
        self.settings.save()
        self._ensure_visible()
        self.update()

    VIEWS = (("sheet", "Cheat sheet"), ("everything", "Everything"))

    def source(self):
        """What's shown: the cheat sheet (what's used often, put together) - or everything an expression can use."""
        return fx.EVERYTHING if getattr(self, "view", "sheet") == "everything" else fx.CHEAT_SHEET

    def set_view(self, view):
        if view != getattr(self, "view", "sheet"):
            self.view = view
            self.index, self.scroll, self._hover, self._keys_group = 0, 0.0, None, None
            self.update()

    def open(self, node=""):
        self.node = self.from_fusion = node or ""
        self.filter, self.field, self._node_fresh = "", "find", False
        self.index, self.scroll, self._keys_group = 0, 0.0, None
        self._hover, self._copied = None, (None, 0.0)
        self.setGeometry(self.picker.picker_column.geometry())
        self.raise_()
        self.show()
        self._caret_on = True
        self._caret.start()
        self._watch.start()
        self._ticks = 0
        self.update()
        self.picker.expressions_shown(True)

    def follow_fusion(self):
        """A node clicked in Fusion while the sheet is open: its name goes into the pieces.
        Only when the selection there changes - a name typed by hand stays until then."""
        try:
            name = fx.selected_node_now(self.picker.resolve)
        except Exception:
            return
        if name and name != self.from_fusion:
            self.from_fusion = name
            self._followed = time.monotonic()
            self.set_node(name)
            QTimer.singleShot(900, self.update)
        self._ticks = getattr(self, "_ticks", 0) + 1
        self.picker.show_node_in_preview(self.node, values_only=self._ticks % 2 == 0)  # (its values twice a second)

    def pick_in_fusion(self):
        """The picker out of the way until a node is clicked in Fusion; then the sheet again, as
        it was, with that node's name in it."""
        picker = self.picker
        was = {"filter": self.filter, "index": self.index, "scroll": self.scroll, "node": self.node,
               "search": picker.search_edit.text()}

        def back(name):
            picker.open_picker()
            picker.search_edit.setText(was["search"])
            self.open(name or was["node"])
            self.filter, self.index, self.scroll = was["filter"], was["index"], was["scroll"]
            if name:
                self._followed = time.monotonic()
                QTimer.singleShot(900, self.update)
            self.update()
        if picker.pick_node_in_fusion(back, "Click a node in Fusion"):
            return True
        self._note = ("on the Fusion page only", time.monotonic())  # nowhere to click a node from here
        QTimer.singleShot(2600, self.update)
        self.update()
        return False

    def copy_name(self):
        """Just the node's name onto the clipboard. The name ("" when the field is empty)."""
        if self.node:
            self.picker._copy(self.node)
            print(f"[expression] copied the node name {self.node}")
            self._name_copied = time.monotonic()
            QTimer.singleShot(int(COPIED_SECONDS * 1000) + 40, self.update)
            self.update()
        return self.node

    def close_sheet(self):
        self.hide()
        self.picker.search_edit.setFocus()

    def hideEvent(self, event):
        self._caret.stop()
        self._watch.stop()
        super().hideEvent(event)
        self.picker.expressions_shown(False)

    def _blink(self):
        self._caret_on = not self._caret_on
        for rect in self._fields.values():
            self.update(rect.toAlignedRect())

    # -- what's on it --
    def entries(self, source=None):
        """[(group, [(the code with the node's name in, where the name is, what it gives, what to draw)])]
        for what's typed (in `source`: the view shown). Something typed and no source asked for: both lists -
        the view's own pieces first, then the other's that it hasn't got (their groups "Everything: Maths" ...)."""
        from .fuzzy import fold
        words = fold(self.filter).split()
        if source is None and words:
            here = self.entries(self.source())
            other = fx.EVERYTHING if self.source() is fx.CHEAT_SHEET else fx.CHEAT_SHEET
            seen = {str(text) for _g, hits in here for text, *_rest in hits}
            name = "Everything" if other is fx.EVERYTHING else "Cheat sheet"
            more = [(f"{name}: {group}", [h for h in hits if str(h[0]) not in seen])
                    for group, hits in self.entries(other)]
            return here + [(group, hits) for group, hits in more if hits]
        out = []
        for group, rows in (source or self.source()):
            hits = []
            for code, about, show in rows:
                text, marks = _with_node(code, self.node)
                said = " ".join(text) if isinstance(text, tuple) else text
                if all(w in fold(f"{said} {about}") for w in words):
                    hits.append((text, marks, about, show))
            if not hits and words and all(w in fold(group) for w in words):  # the group's name: all of it
                hits = [(*_with_node(code, self.node), about, show) for code, about, show in rows]
            if hits:
                out.append((group, hits))
        return out

    def _fonts(self):
        base = QFont(self.picker.font())
        text = font_at(SMALL, base)
        mono = QFont(text)
        from .fonts import mono_families
        mono.setFamilies(mono_families())
        for tag in ("calt", "liga"):  # code as it's typed: <= stays <=, not one joined sign (Fusion wants the two)
            mono.setFeature(QFont.Tag(tag), 0)
        head = font_at(TINY, base, QFont.DemiBold)
        head.setCapitalization(QFont.AllUppercase)
        head.setLetterSpacing(QFont.PercentageSpacing, 112)
        title = font_at(TITLE, base, QFont.DemiBold)
        field = font_at(1.0, base)
        return title, head, text, mono, field

    def _columns(self):
        return max(1, min(6, int((self._vw() - 2 * PAD + GAP) // (300 + GAP))))

    def _layout(self):
        """Everything's place for this width and what's typed: the two fields, the group names
        under them (chips), where the tiles' area begins, and the tiles and headings in it
        (before scrolling)."""
        key = (self._vw(), self._vh(), self._k(), self.filter, self.node, self.picker.font().toString(),
               getattr(self, "view", "sheet"))
        if self._laid[0] == key:
            return self._laid[1]
        title_f, head_f, text_f, mono_f, field_f = self._fonts()
        hfm, tfm, mfm = QFontMetricsF(head_f), QFontMetricsF(text_f), QFontMetricsF(mono_f)
        groups = self.entries()
        width = self._vw() - 2 * PAD
        title = QRectF(PAD, 14, width, QFontMetricsF(title_f).height() + 4)
        field_h = QFontMetricsF(field_f).height() + 18
        node_w = max(190.0, min(320.0, width * 0.34))
        find = QRectF(PAD, title.bottom() + 10, width - node_w - GAP, field_h)
        node = QRectF(find.right() + GAP, find.top(), node_w, field_h)
        # the group names, flowing onto as many lines as they need
        chips, x, y = [], PAD, find.bottom() + 14
        chip_h = tfm.height() + 10
        for group, hits in groups:
            w = 28 + tfm.horizontalAdvance(group) + 8 + tfm.horizontalAdvance(str(len(hits))) + 12
            if x > PAD and x + w > PAD + width:
                x, y = PAD, y + chip_h + 6
            chips.append((QRectF(x, y, w, chip_h), group, len(hits)))
            x += w + 6
        rule = (y + chip_h + 14) if chips else (find.bottom() + 14)
        # the tiles
        columns = self._columns()
        tile_w = (width - (columns - 1) * GAP) / columns
        code_w = tile_w - 2 * TILE_PAD - 20 - 24  # the tile's edge, the code box's, and the copy mark
        tiles, heads, y, n = [], [], 16.0, 0
        for group, hits in groups:
            heads.append((group, y, len(hits)))
            y += hfm.height() + 12
            for first in range(0, len(hits), columns):
                row = []
                for text, marks, about, show in hits[first:first + columns]:
                    if isinstance(text, tuple):  # its pieces side by side, each in a box of its own
                        parts, px, py, part_h = [], 0.0, 0.0, mfm.height() + 12
                        for piece in text:
                            pw = max(part_h, mfm.horizontalAdvance(piece) + 22)
                            if px and px + pw > tile_w - 2 * TILE_PAD:
                                px, py = 0.0, py + part_h + 6
                            parts.append((piece, QRectF(px, py, pw, part_h)))
                            px += pw + 6
                        lines, box_h = parts, py + part_h
                    else:
                        lines = _wrap_code(text, mfm, code_w)
                        box_h = len(lines) * mfm.height() + 16
                    # beside what it gives: a small curve of it, or what it comes to
                    curve = fx.sheet_curve(show) if isinstance(show, tuple) else None
                    drawing_w = CURVE_W if curve else (min(mfm.horizontalAdvance(show) + 2, tile_w * 0.45) if show else 0.0)
                    about_w = tile_w - 2 * TILE_PAD - 2 - (drawing_w + 14 if drawing_w else 0)
                    about_h = tfm.boundingRect(QRectF(0, 0, about_w, 4000), Qt.AlignLeft | Qt.TextWordWrap, about).height()
                    head_h = max(about_h, CURVE_H if curve else 0.0)
                    row.append((text, marks, about, lines, box_h, show, curve, drawing_w, about_w, head_h))
                height = max(TILE_PAD + item[-1] + 10 + item[4] + TILE_PAD for item in row)
                for col, (text, marks, about, lines, box_h, show, curve, drawing_w, about_w, head_h) in enumerate(row):
                    rect = QRectF(PAD + col * (tile_w + GAP), y, tile_w, height)
                    pieces = isinstance(text, tuple)
                    tiles.append({"n": n, "rect": rect, "group": group, "code": text[0] if pieces else text,
                                  "parts": lines if pieces else None, "marks": marks, "about": about,
                                  "lines": [] if pieces else lines, "box_h": box_h, "show": show, "curve": curve,
                                  "drawing_w": drawing_w, "about_w": about_w})
                    n += 1
                y += height + GAP
            y += 18
        laid = {"title": title, "find": find, "node": node, "chips": chips, "rule": rule, "view_top": rule + 1,
                "tiles": tiles, "heads": heads, "bottom": y, "pieces": sum(len(rows) for _g, rows in self.source())}
        self._laid = (key, laid)
        return laid

    def _group_in_view(self, laid):
        """The group whose chip is lit: the one at the top of what's scrolled into view (the last one, scrolled
        to the bottom) - it follows the scrolling, not only the tile picked with the keys."""
        heads = laid["heads"]
        if not heads:
            return None
        if getattr(self, "_keys_group", None) in [g for g, _y, _c in heads]:  # picked with the keys or a chip
            return self._keys_group
        _top, view_h = self._view(laid)
        bottom = max(0.0, laid["bottom"] - view_h)
        at = max(0.0, min(self.scroll, bottom))
        if bottom > 0 and at >= bottom - 1:
            return heads[-1][0]
        current = heads[0][0]
        for group, y, _count in heads:
            if y <= at + 24:
                current = group
        return current

    def _view(self, laid):
        return laid["view_top"], max(40.0, self._vh() - laid["view_top"] - FOOTER)

    # -- painting --
    def _paint_field(self, p, rect, focused, glyph, label, value, placeholder, value_font, tag="", marks=(), lit=False,
                     chosen=False):
        """A text field: its symbol or label, what's typed (or what could be), the caret.
        marks: [(name, glyph)] - small symbols to click at its right end. lit: edged like the one
        in use. Returns {name: where that mark is}."""
        t = self.settings.theme
        text_c, muted, accent = QColor(t["picker_text"]), QColor(t["picker_folder"]), QColor(t["picker_accent"])
        edge = QColor(text_c)
        edge.setAlphaF(0.55 if lit else 0.38)
        p.setPen(QPen(edge if focused or lit else QColor(t["picker_border"]), 1.2 if focused or lit else 1))
        p.setBrush(QColor(t.get("picker_bar_bg", t["picker_bg"])))
        from . import look
        r = look.radius(self.settings, "control")
        p.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), r, r)
        x = rect.left() + 13
        small = font_at(SMALL, self._fonts()[2])
        sfm = QFontMetricsF(small)
        if glyph:
            draw_glyph(p, glyph, QPointF(x + 7, rect.center().y()), 15, text_c if focused else muted)
            x += 24
        if label:
            p.setFont(small)
            p.setPen(muted)
            p.drawText(QRectF(x, rect.top(), sfm.horizontalAdvance(label) + 2, rect.height()), Qt.AlignLeft | Qt.AlignVCenter, label)
            x += sfm.horizontalAdvance(label) + 10
            p.setPen(QPen(QColor(t["picker_border"]), 1))
            p.drawLine(QPointF(x, rect.top() + 9), QPointF(x, rect.bottom() - 9))
            x += 10
        fm = QFontMetricsF(value_font)
        places, right = {}, rect.right() - (4 if marks else 0)
        for name, mark in reversed(marks):
            places[name] = QRectF(right - 28, rect.top(), 28, rect.height())
            draw_glyph(p, mark, places[name].center(), 14,
                       accent if mark == "tick" else text_c if places[name].contains(self._mouse) else muted)
            right = places[name].left()
        tag_w = 0.0
        if tag and right - x - fm.horizontalAdvance(value) > sfm.horizontalAdvance(tag) + 30:
            tag_w = sfm.horizontalAdvance(tag) + (6 if marks else 12)
            p.setFont(small)
            p.setPen(muted)
            p.drawText(QRectF(right - tag_w, rect.top(), tag_w, rect.height()), Qt.AlignLeft | Qt.AlignVCenter, tag)
        room = right - (0 if marks else 12) - tag_w - x
        p.setFont(value_font)
        shown = fm.elidedText(value, Qt.ElideLeft, room) if value else fm.elidedText(placeholder, Qt.ElideRight, room)
        if chosen and value:  # all of it chosen (Ctrl+A): the selection colour behind it
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(t["picker_select_bg"]))
            p.drawRoundedRect(QRectF(x - 2, rect.center().y() - fm.height() / 2 - 1, fm.horizontalAdvance(shown) + 4,
                                     fm.height() + 2), 3, 3)
        p.setPen(text_c if value else muted)
        p.drawText(QRectF(x, rect.top(), room, rect.height()), Qt.AlignLeft | Qt.AlignVCenter, shown)
        if focused and self._caret_on:
            cx = x + (fm.horizontalAdvance(shown) + 1.5 if value else 0)
            p.setPen(QPen(accent, 1.4))
            p.drawLine(QPointF(cx, rect.center().y() - fm.ascent() * 0.62), QPointF(cx, rect.center().y() + fm.ascent() * 0.62))
        return places

    def _paint_curve(self, p, rect, curve, strong, quiet):
        """A piece drawn over the sample clip: its line, and faint behind it the one it's compared with."""
        values, behind, lo, hi = curve

        def path(numbers):
            line = QPainterPath()
            for k, value in enumerate(numbers):
                share = max(0.0, min(1.0, (value - lo) / (hi - lo)))
                at = QPointF(rect.left() + rect.width() * k / (len(numbers) - 1), rect.bottom() - 2 - share * (rect.height() - 4))
                line.moveTo(at) if k == 0 else line.lineTo(at)
            return line
        p.setBrush(Qt.NoBrush)
        if behind:
            faint = QColor(quiet)
            faint.setAlphaF(0.55)
            p.setPen(QPen(faint, 1.0, Qt.DashLine))
            p.drawPath(path(behind))
        p.setPen(QPen(strong, 1.4, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.drawPath(path(values))

    def paintEvent(self, event):
        t, d = self.settings.theme, self.settings.display
        from .fonts import picker_scale
        radius = d["outer_corner_radius"] * picker_scale(self.settings)
        text_c, muted, accent = QColor(t["picker_text"]), QColor(t["picker_folder"]), QColor(t["picker_accent"])
        border, inset = QColor(t["picker_border"]), QColor(t.get("picker_bar_bg", t["picker_bg"]))
        quiet = QColor(border)
        quiet.setAlphaF(0.6)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        k = self._k()
        p.scale(k, k)  # (its own zoom: everything below in the sheet's units)
        radius /= k
        shape = QPainterPath()
        shape.addRoundedRect(QRectF(0, 0, self._vw(), self._vh()).adjusted(0.5 / k, 0.5 / k, -0.5 / k, -0.5 / k),
                             radius, radius)
        p.fillPath(shape, QColor(t["picker_bg"]))
        p.setClipPath(shape)

        title_f, head_f, text_f, mono_f, field_f = self._fonts()
        hfm, tfm, mfm = QFontMetricsF(head_f), QFontMetricsF(text_f), QFontMetricsF(mono_f)
        laid = self._layout()
        tiles = laid["tiles"]
        self.index = max(0, min(self.index, len(tiles) - 1))
        current = self._group_in_view(laid)

        # the two views: the cheat sheet, and everything an expression can use - the one shown in the text colour
        p.setFont(title_f)
        tfm_title = QFontMetricsF(title_f)
        x = laid["title"].left()
        self._view_tabs = []
        for view, words in self.VIEWS:
            w = tfm_title.horizontalAdvance(words)
            rect = QRectF(x, laid["title"].top(), w, laid["title"].height())
            on = view == getattr(self, "view", "sheet")
            p.setPen(text_c if on else (text_c if rect.contains(self._mouse) else muted))
            p.drawText(rect, Qt.AlignLeft | Qt.AlignVCenter, words)
            if on:
                p.setPen(QPen(text_c, 2, Qt.SolidLine, Qt.RoundCap))
                p.drawLine(QPointF(rect.left(), rect.bottom() + 1), QPointF(rect.right(), rect.bottom() + 1))
            self._view_tabs.append((rect.adjusted(-6, -4, 6, 4), view))
            x += w + 26
        p.setFont(text_f)
        p.setPen(muted)
        p.drawText(laid["title"], Qt.AlignRight | Qt.AlignVCenter,
                   f"{len(tiles)} found" if self.filter else f"{laid['pieces']} pieces")

        # the two fields
        self._fields = {"find": laid["find"], "node": laid["node"]}
        self._paint_field(p, laid["find"], self.field == "find", "search", "", self.filter,
                          "Find a piece - time, countdown, width ...", field_f,
                          chosen=getattr(self, "_all", None) == "find")
        node_font = font_at(SMALL, mono_f)
        now = time.monotonic()
        name_copied = now - self._name_copied < COPIED_SECONDS
        fresh = self.field == "node" and self._node_fresh
        places = self._paint_field(
            p, laid["node"], self.field == "node", "", "Node name", self.node, fx.NODE, node_font,
            tag="Copied" if name_copied else self._note[0] if now - self._note[1] < 2.5
            else "Enter, then click it in Fusion" if fresh
            else "selected in Fusion" if self.node and self.node == self.from_fusion else "",
            marks=[("pick", "pick_node")] + ([("copy", "tick" if name_copied else "copy_code")] if self.node else []),
            lit=now - self._followed < 0.8, chosen=getattr(self, "_all", None) == "node")
        self._node_copy, self._node_pick = places.get("copy", QRectF()), places.get("pick", QRectF())

        # the groups, to jump to
        self._chips = []
        for rect, group, count in laid["chips"]:
            self._chips.append((rect, group))
            on = group == current
            fill = QColor(t["picker_select_bg"])
            fill.setAlphaF(1.0 if on else 0.28)
            p.setPen(Qt.NoPen)
            p.setBrush(fill)
            p.drawRoundedRect(rect, rect.height() / 2, rect.height() / 2)
            draw_glyph(p, GROUP_GLYPH.get(group.split(": ")[-1], "expression"), QPointF(rect.left() + 16, rect.center().y()), 12,
                       text_c if on else muted)
            p.setFont(text_f)
            p.setPen(text_c if on else muted)
            p.drawText(QRectF(rect.left() + 28, rect.top(), rect.width(), rect.height()), Qt.AlignLeft | Qt.AlignVCenter, group)
            p.setPen(muted)
            p.drawText(QRectF(rect.left(), rect.top(), rect.width() - 12, rect.height()), Qt.AlignRight | Qt.AlignVCenter,
                       str(count))
        p.setPen(QPen(quiet, 1))
        p.drawLine(QPointF(0, laid["rule"] + 0.5), QPointF(self._vw(), laid["rule"] + 0.5))

        # the tiles
        view_top, view_h = self._view(laid)
        self._max_scroll = max(0.0, laid["bottom"] - view_h)
        self.scroll = max(0.0, min(self.scroll, self._max_scroll))
        copied = self._copied[0] if time.monotonic() - self._copied[1] < COPIED_SECONDS else None
        lift, lit, chosen = QColor(t["picker_select_bg"]), QColor(t["picker_select_bg"]), QColor(t["picker_select_bg"])
        lift.setAlphaF(0.26)
        lit.setAlphaF(0.45)
        chosen.setAlphaF(0.62)
        p.save()
        p.setClipRect(QRectF(0, view_top, self._vw(), view_h), Qt.IntersectClip)
        p.translate(0, view_top - self.scroll)
        for group, y, count in laid["heads"]:
            mid = y + hfm.height() / 2
            draw_glyph(p, GROUP_GLYPH.get(group.split(": ")[-1], "expression"), QPointF(PAD + 7, mid), 13, muted)
            p.setFont(head_f)
            p.setPen(muted)
            p.drawText(QRectF(PAD + 22, y, self._vw(), hfm.height()), Qt.AlignLeft | Qt.AlignVCenter, group)
            p.setPen(QPen(quiet, 1))  # a quiet line from the name to the edge: where one group ends and the next begins
            p.drawLine(QPointF(PAD + 22 + hfm.horizontalAdvance(group.upper()) + 14, mid + 0.5), QPointF(self._vw() - PAD, mid + 0.5))
        soft, chip = QColor(text_c), QColor(text_c)
        soft.setAlphaF(0.5)
        chip.setAlphaF(0.12)
        for tile in tiles:
            rect = tile["rect"]
            if rect.bottom() < self.scroll or rect.top() > self.scroll + view_h:
                continue
            selected, hovered = tile["n"] == self.index, tile["n"] == self._hover
            p.setPen(QPen(soft, 1.2) if selected else Qt.NoPen)  # the one Enter copies: a lighter tile with a pale edge
            p.setBrush(chosen if selected else lit if hovered else lift)
            p.drawRoundedRect(rect.adjusted(0.6, 0.6, -0.6, -0.6), 10, 10)
            done = copied == tile["code"] or (tile["parts"] and copied in [piece for piece, _r in tile["parts"]])
            # what it gives, in plain words - and a small drawing of it beside that
            p.setFont(text_f)
            p.setPen(accent if done else text_c)
            head = QRectF(rect.left() + TILE_PAD + 2, rect.top() + TILE_PAD, tile["about_w"], rect.height())
            p.drawText(head, Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap, "Copied" if done else tile["about"])
            if tile["curve"]:
                self._paint_curve(p, QRectF(rect.right() - TILE_PAD - CURVE_W, rect.top() + TILE_PAD, CURVE_W, CURVE_H),
                                  tile["curve"], text_c, muted)
            elif tile["show"]:
                p.setFont(mono_f)
                p.setPen(muted)
                p.drawText(QRectF(rect.right() - TILE_PAD - tile["drawing_w"], rect.top() + TILE_PAD, tile["drawing_w"],
                                  tfm.height()), Qt.AlignRight | Qt.AlignVCenter,
                           mfm.elidedText(tile["show"], Qt.ElideRight, tile["drawing_w"]))
            # ...then what to write
            box = QRectF(rect.left() + TILE_PAD, rect.bottom() - TILE_PAD - tile["box_h"], rect.width() - 2 * TILE_PAD,
                         tile["box_h"])
            if tile["parts"]:  # several pieces: a box each, the one under the mouse lit, the copied one in the accent
                at = QPointF(self._mouse.x(), self._mouse.y() - view_top + self.scroll)
                for piece, r in tile["parts"]:
                    part = r.translated(box.topLeft())
                    over = part.contains(at)
                    p.setPen(QPen(soft, 1) if over else Qt.NoPen)
                    p.setBrush(inset)
                    p.drawRoundedRect(part, 7, 7)
                    p.setFont(mono_f)
                    p.setPen(accent if copied == piece else text_c)
                    p.drawText(part, Qt.AlignCenter, piece)
                continue
            p.setPen(Qt.NoPen)
            p.setBrush(inset)
            p.drawRoundedRect(box, 7, 7)
            p.setFont(mono_f)
            stand_in = QColor(STAND_IN_LIGHT if is_light(t["picker_bg"]) else STAND_IN_DARK)
            for k, (a, b) in enumerate(tile["lines"]):
                base_y = box.top() + 8 + k * mfm.height()
                blanks = []
                for mark in tile["marks"]:  # the node's name: on a pale chip, the way a filled-in blank looks
                    lo, hi = max(mark[0], a), min(mark[1], b)
                    if lo >= hi:
                        continue
                    if len(mark) > 2:
                        blanks.append((lo, hi))
                        continue
                    left = box.left() + 10 + mfm.horizontalAdvance(tile["code"][a:lo])
                    p.setPen(Qt.NoPen)
                    p.setBrush(chip)
                    p.drawRoundedRect(QRectF(left - 2.5, base_y + 0.5, mfm.horizontalAdvance(tile["code"][lo:hi]) + 5,
                                             mfm.height() - 1), 3.5, 3.5)
                at = a
                for lo, hi in blanks + [(b, b)]:  # the line in pieces: as it is, then a stand-in, ...
                    left = box.left() + 10 + mfm.horizontalAdvance(tile["code"][a:at])
                    p.setPen(text_c)
                    p.drawText(QPointF(left, base_y + mfm.ascent()), tile["code"][at:lo])
                    if hi > lo:
                        p.setPen(stand_in)
                        p.drawText(QPointF(box.left() + 10 + mfm.horizontalAdvance(tile["code"][a:lo]), base_y + mfm.ascent()),
                                   tile["code"][lo:hi])
                    at = hi
            mark_at = QPointF(box.right() - 16, box.top() + 8 + mfm.height() / 2)
            draw_glyph(p, "tick" if done else "copy_code", mark_at, 13,
                       accent if done else (text_c if selected or hovered else muted))
        if not tiles:
            p.setFont(text_f)
            p.setPen(muted)
            other = fx.EVERYTHING if self.source() is fx.CHEAT_SHEET else fx.CHEAT_SHEET
            found = sum(len(hits) for _g, hits in self.entries(other))
            where = "Everything" if other is fx.EVERYTHING else "the cheat sheet"
            p.drawText(QRectF(0, 40, self._vw(), 30), Qt.AlignCenter,
                       f"Nothing here matches “{self.filter}”" + (f" - {found} in {where}" if found else ""))
            self._elsewhere = QRectF(0, 40, self._vw(), 30) if found else None
        p.restore()

        # the keys, the way the picker's own bottom bar shows them
        bar = QRectF(0, self._vh() - FOOTER, self._vw(), FOOTER)
        p.fillRect(bar, inset)
        p.setPen(QPen(quiet, 1))
        p.drawLine(QPointF(0, bar.top() + 0.5), QPointF(self._vw(), bar.top() + 0.5))
        from . import keycaps
        x = PAD
        name_key = keycaps.key_name(self.settings.keybinds.get("copy_node_name", "")) \
            if self.settings.keybinds.get("copy_node_name") else ""
        hints = [("Enter", "Copy and close"), ("Shift+Enter", "Copy, stay"), ("Tab", "Type a node name")] \
            + ([(name_key, "Copy the name")] if name_key else []) + [("PgDn", "Next group")]
        for key, label in hints:
            if x + keycaps.width(text_f, key, label) > self._vw() - PAD:
                break
            x = keycaps.draw(p, x, bar.center().y(), key, label, text_f, self.settings.theme)
        p.end()

    # -- keys --
    def _ensure_visible(self, head=False):
        """Scrolls the highlighted tile into view (head: with its group's name at the top)."""
        laid = self._layout()
        tile = next((x for x in laid["tiles"] if x["n"] == self.index), None)
        if tile is None:
            return
        _top, view_h = self._view(laid)
        rect = tile["rect"]
        if head:
            self.scroll = next((y for g, y, _c in laid["heads"] if g == tile["group"]), rect.top()) - 14
        elif rect.top() < self.scroll:
            first_of_group = all(x["rect"].top() >= rect.top() for x in laid["tiles"] if x["group"] == tile["group"])
            self.scroll = rect.top() - (44 if first_of_group else 10)
        elif rect.bottom() > self.scroll + view_h:
            self.scroll = rect.bottom() - view_h + 10
        self.scroll = max(0.0, min(self.scroll, max(0.0, laid["bottom"] - view_h)))

    def _move(self, dx, dy):
        tiles = self._layout()["tiles"]
        if not tiles:
            return
        self.index = max(0, min(self.index, len(tiles) - 1))
        cur = tiles[self.index]["rect"]
        if dx:
            self.index = max(0, min(len(tiles) - 1, self.index + dx))
        else:  # the nearest tile in the next row up / down, across groups too
            cands = [x for x in tiles if (x["rect"].top() > cur.top() + 1 if dy > 0 else x["rect"].top() < cur.top() - 1)]
            if cands:
                row_y = min(x["rect"].top() for x in cands) if dy > 0 else max(x["rect"].top() for x in cands)
                row = [x for x in cands if abs(x["rect"].top() - row_y) < 1]
                self.index = min(row, key=lambda x: abs(x["rect"].center().x() - cur.center().x()))["n"]
        self._keys_group = tiles[self.index]["group"]  # (moved with the keys: the picked tile's group is lit)
        self._ensure_visible()
        self.update()

    def go_to_group(self, group=None, step=1):
        """The first tile of `group` - or of the group after (step 1) / before (-1) the one you're in."""
        laid = self._layout()
        tiles, names = laid["tiles"], [g for g, _y, _c in laid["heads"]]
        if not tiles:
            return
        if group is None:  # (from the group lit - the one scrolled to, or picked)
            here = names.index(self._group_in_view(laid) or tiles[min(self.index, len(tiles) - 1)]["group"])
            group = names[(here + step) % len(names)]
        first = next((x for x in tiles if x["group"] == group), None)
        if first is not None:
            self.index = first["n"]
            self._keys_group = group
            self._ensure_visible(head=True)
            self.update()

    def set_field(self, field):
        """Typing goes to the Find field or the Node name field."""
        self.field, self._all = field, None
        self._node_fresh = field == "node"
        self._caret_on = True
        self.update()

    def set_node(self, name):
        """The name written into every piece that names a node (letters, digits and _ : Fusion's names have nothing else)."""
        self.node = "".join(ch for ch in name if ch.isalnum() or ch == "_")
        self._node_fresh = False
        self.index = max(0, min(self.index, len(self._layout()["tiles"]) - 1))
        self.update()

    def copy(self, n, close=False, piece=None):
        """The tile's code (or one of its pieces) onto the clipboard. What was copied ("" when there's no such
        tile)."""
        tile = next((x for x in self._layout()["tiles"] if x["n"] == n), None)
        if tile is None:
            return ""
        code = piece or tile["code"]
        self.picker._copy(code)
        print(f"[expression] copied from the cheat sheet: {code}")
        if close:
            self.hide()
            self.picker.hide()
            return code
        self._copied = (code, time.monotonic())
        QTimer.singleShot(int(COPIED_SECONDS * 1000) + 40, self.update)
        self.update()
        return code

    def _piece_at(self, n, pos):
        """The piece of tile n under the mouse (a tile of several), or None."""
        laid = self._layout()
        tile = next((x for x in laid["tiles"] if x["n"] == n), None)
        if tile is None or not tile["parts"]:
            return None
        view_top, _h = self._view(laid)
        at = QPointF(pos.x(), pos.y() - view_top + self.scroll)
        rect = tile["rect"]
        box_top = QPointF(rect.left() + TILE_PAD, rect.bottom() - TILE_PAD - tile["box_h"])
        return next((piece for piece, r in tile["parts"] if r.translated(box_top).contains(at)), None)

    def handle_key(self, ev):
        """Keys while the sheet is open. Returns True (always takes them)."""
        from .fonts import zoom_key
        direction = zoom_key(ev, self.settings)
        if direction is not None:  # Ctrl and + / - / 0: the sheet by itself
            self.zoom_sheet(direction)
            return True
        key, mods = ev.key(), ev.modifiers()
        command = bool(mods & (Qt.ControlModifier | Qt.MetaModifier))
        in_node = self.field == "node"
        self._caret_on = True
        # Ctrl+A: all of what's typed in the field in use - typing then replaces it, Backspace / Delete clears it,
        # Ctrl+C copies it. Any other key lets go of it first.
        if key == Qt.Key_A and command:
            self._all = self.field if (self.node if in_node else self.filter) else None
            self.update()
            return True
        chosen, self._all = getattr(self, "_all", None) == self.field, None
        if chosen and key == Qt.Key_C and command:
            self.picker._copy(self.node if in_node else self.filter)
            self.update()
            return True
        if chosen and (key in (Qt.Key_Backspace, Qt.Key_Delete) or (ev.text() and ev.text().isprintable() and not command)):
            typed = ev.text() if key not in (Qt.Key_Backspace, Qt.Key_Delete) else ""
            if in_node:
                self.set_node(typed)
            else:
                self.filter, self.index, self.scroll = typed, 0, 0.0
                self.update()
            return True
        if self.picker.key_is(ev, "copy_node_name"):
            self.copy_name()
        elif key in (Qt.Key_Tab, Qt.Key_Backtab):
            self.set_field("find" if in_node else "node")
        elif key == Qt.Key_Escape:
            if in_node:
                self.set_field("find")
            elif self.filter:
                self.filter, self.index, self.scroll = "", 0, 0.0
                self.update()
            else:
                self.close_sheet()
        elif key in (Qt.Key_Return, Qt.Key_Enter):
            if in_node and self._node_fresh:  # nothing typed: click it in Fusion instead
                self.set_field("find")
                self.pick_in_fusion()
            elif in_node:  # the name is in: back to finding
                self.set_field("find")
            else:
                self.copy(self.index, close=not (mods & Qt.ShiftModifier))
        elif key == Qt.Key_C and command:
            self.copy(self.index)
        elif key == Qt.Key_Left:
            self._move(-1, 0)
        elif key == Qt.Key_Right:
            self._move(1, 0)
        elif key == Qt.Key_Up:
            self.go_to_group(step=-1) if command else self._move(0, -1)
        elif key == Qt.Key_Down:
            self.go_to_group(step=1) if command else self._move(0, 1)
        elif key == Qt.Key_PageDown:
            self.go_to_group(step=1)
        elif key == Qt.Key_PageUp:
            self.go_to_group(step=-1)
        elif key == Qt.Key_Backspace:
            if in_node:
                self.set_node("" if command or self._node_fresh else self.node[:-1])
            else:
                self.filter = "" if command else self.filter[:-1]
                self.index, self.scroll = 0, 0.0
                self.update()
        elif ev.text() and ev.text().isprintable() and not command and not mods & Qt.AltModifier:
            if in_node:
                self.set_node(ev.text() if self._node_fresh else self.node + ev.text())
            else:
                self.filter += ev.text()
                self.index, self.scroll = 0, 0.0
                self.update()
        return True

    # -- mouse --
    def _tile_at(self, pos):
        laid = self._layout()
        view_top, view_h = self._view(laid)
        if not view_top <= pos.y() <= view_top + view_h:
            return None
        at = QPointF(pos.x(), pos.y() - view_top + self.scroll)
        return next((x["n"] for x in laid["tiles"] if x["rect"].contains(at)), None)

    def mouseMoveEvent(self, ev):
        n = self._tile_at(self._v(ev.position()))
        on_mark = self._node_copy.contains(self._v(ev.position())) or self._node_pick.contains(self._v(ev.position()))
        over_field = any(rect.contains(self._v(ev.position())) for rect in self._fields.values()) and not on_mark
        self.setCursor(Qt.PointingHandCursor if on_mark else Qt.IBeamCursor if over_field else Qt.ArrowCursor)
        was_on = self._node_copy.contains(self._mouse) or self._node_pick.contains(self._mouse)
        piece_was = self._piece_at(n, self._mouse) if n is not None else None
        self._mouse = self._v(ev.position())
        if n is not None and self._piece_at(n, self._mouse) != piece_was:
            self.update()  # (a tile of pieces: the one under the mouse is lit)
        self.setToolTip("Hide the picker and click a node in Fusion" if self._node_pick.contains(self._v(ev.position()))
                        else "Copy the name" if self._node_copy.contains(self._v(ev.position())) else "")
        if on_mark or was_on:
            self.update()
        if n != self._hover:
            self._hover = n
            self.update()

    def leaveEvent(self, ev):
        self._hover = None
        self.update()

    def mousePressEvent(self, ev):
        tab = next((view for rect, view in getattr(self, "_view_tabs", []) if rect.contains(self._v(ev.position()))), None)
        laid = self._layout()
        if tab is None and not laid["tiles"] and getattr(self, "_elsewhere", None) is not None:
            view_top, _h = self._view(laid)
            if self._elsewhere.translated(0, view_top).contains(self._v(ev.position())):  # "... - 3 in Everything": there
                tab = "everything" if self.source() is fx.CHEAT_SHEET else "sheet"
        if tab is not None:
            self.set_view(tab)
            return
        if self._node_copy.contains(self._v(ev.position())):
            self.copy_name()
            return
        if self._node_pick.contains(self._v(ev.position())):
            self.pick_in_fusion()
            return
        field = next((name for name, rect in self._fields.items() if rect.contains(self._v(ev.position()))), None)
        if field is not None:
            self.set_field(field)
            return
        group = next((g for rect, g in self._chips if rect.contains(self._v(ev.position()))), None)
        if group is not None:
            self.go_to_group(group)
            return
        n = self._tile_at(self._v(ev.position()))
        if n is not None:
            self.index = n
            self.copy(n, piece=self._piece_at(n, self._v(ev.position())))

    def wheelEvent(self, ev):
        self.scroll = max(0.0, min(self._max_scroll, self.scroll - ev.angleDelta().y() / 2))
        self._keys_group = None  # (scrolled by hand: the group in view is lit again)
        self.update()

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self.update()
