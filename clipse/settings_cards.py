"""The look of Settings: each section a rounded card of rows - the
setting's name (and a line saying what it does) on the left, its control
on the right, a hairline between rows - and on/off settings as switches.

The pages are still built as plain group boxes and forms (settings_dialog.py);
cardify() rearranges each finished page into cards, so every setting keeps
its own wiring (signals, double-click to reset) untouched.
"""
from PySide6.QtCore import QEasingCurve, QEvent, QPointF, QRectF, QSize, Qt, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (QCheckBox, QFormLayout, QFrame, QGridLayout, QGroupBox, QHBoxLayout, QLabel, QLayout,
                               QSizePolicy, QVBoxLayout, QWidget)
from .fonts import SMALL, at as font_at, rel, window_zoom  # (the one scale of sizes; these are Settings' own)

DESCRIPTION_MAX = 130  # longer help stays in the tooltip, not under the name


class ToggleSwitch(QWidget):
    """An on/off switch, standing in for a check box (which stays, hidden,
    as the real setting - so all its wiring keeps working)."""
    toggled = Signal(bool)

    def __init__(self, settings, checkbox):
        super().__init__()
        self.settings = settings
        self.box = checkbox
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(34, 18)  # (Vicinae's: 34 x 18, a 14 px knob)
        self.setFocusPolicy(Qt.StrongFocus)
        self._pos = 1.0 if checkbox.isChecked() else 0.0
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(140)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.valueChanged.connect(self._moved)
        checkbox.toggled.connect(self._follow)
        self.setEnabled(checkbox.isEnabled())

    def _moved(self, value):
        self._pos = float(value)
        self.update()

    def _follow(self, on):
        self._anim.stop()
        self._anim.setStartValue(self._pos)
        self._anim.setEndValue(1.0 if on else 0.0)
        self._anim.start()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self.isEnabled():
            self.box.setChecked(not self.box.isChecked())

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Space, Qt.Key_Return, Qt.Key_Enter):
            self.box.setChecked(not self.box.isChecked())
            return
        super().keyPressEvent(event)

    def paintEvent(self, event):
        t = self.settings.theme
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        off = QColor(t["picker_text"])
        off.setAlphaF(0.2)  # (off: the text's colour, faint - it reads on every theme)
        on = QColor(t.get("picker_accent", t["picker_text"]))
        track = QColor(
            int(off.red() + (on.red() - off.red()) * self._pos),
            int(off.green() + (on.green() - off.green()) * self._pos),
            int(off.blue() + (on.blue() - off.blue()) * self._pos))
        track.setAlphaF(off.alphaF() + (1.0 - off.alphaF()) * self._pos)
        if not self.isEnabled():
            track.setAlphaF(track.alphaF() * 0.4)
        p.setPen(Qt.NoPen)
        p.setBrush(track)
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        d = r.height() - 4
        x = r.left() + 2 + (r.width() - d - 4) * self._pos
        p.setBrush(QColor("#ffffff"))
        p.drawEllipse(QRectF(x, r.top() + 2, d, d))
        if self.hasFocus():
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(on, 1.2))
            p.drawRoundedRect(r.adjusted(-1, -1, 1, 1), r.height() / 2 + 1, r.height() / 2 + 1)
        p.end()


class SettingRow(QWidget):
    """Name (+ a short description) on the left, the control on the right."""

    def __init__(self, title_widget, description, control, muted, scale=1.0):
        super().__init__()
        self.setObjectName("SettingRow")
        self.title_widget = title_widget
        row = QHBoxLayout(self)
        row.setContentsMargins(*(round(n * scale) for n in (16, 11, 16, 11)))
        row.setSpacing(round(18 * scale))
        text = QVBoxLayout()
        text.setSpacing(round(2 * scale))
        text.addWidget(title_widget)
        self.description = None
        if description:
            desc = QLabel(description)
            desc.setObjectName("SettingDescription")
            desc.setWordWrap(True)
            desc.setStyleSheet(f"color: {muted};")
            text.addWidget(desc)
            self.description = description
        row.addLayout(text, 1)
        if isinstance(control, QLayout):
            row.addLayout(control)
        elif control is not None:
            row.addWidget(control, 0, Qt.AlignRight | Qt.AlignVCenter)

    def search_text(self):
        title = self.title_widget.text() if isinstance(self.title_widget, QLabel) else ""
        return f"{title} {self.description or ''}"


class FreeRow(QWidget):
    """A full-width row: lists, buttons, hints, theme cards."""

    def __init__(self, content, scale=1.0):
        super().__init__()
        self.setObjectName("SettingRow")
        row = QVBoxLayout(self)
        row.setContentsMargins(*(round(n * scale) for n in (16, 11, 16, 11)))
        if isinstance(content, QLayout):
            row.addLayout(content)
        else:
            row.addWidget(content)
            # a folded part (the colours) folds its row away too
            if content.isHidden():  # (never shown here: with no parent yet it'd be a window of its own - Windows
                self.hide()          # flashed them on screen as Settings opened)
            content.installEventFilter(self)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.ShowToParent:
            self.show()
        elif event.type() == QEvent.HideToParent:
            self.hide()
        return False

    def search_text(self):
        words = [w.text() for w in self.findChildren(QLabel) if w.text() and not w.text().startswith("<")]
        for tiles in self.findChildren(ToggleTiles):  # "show audio" finds the list tiles
            words += [f"show {label}" for _k, label, _s in tiles.tiles]
        return " ".join(words)


class Gallery(QWidget):
    """Same-size tiles that wrap to the width they get (the theme gallery)."""

    def __init__(self, gap=10, vgap=8):
        super().__init__()
        self.tiles = []
        self.gap, self.vgap = gap, vgap
        self.extra = None   # a widget under the tiles, full width
        sp = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        sp.setHeightForWidth(True)
        self.setSizePolicy(sp)

    def add(self, tile):
        tile.setParent(self)
        self.tiles.append(tile)

    def set_extra(self, widget):
        widget.setParent(self)
        self.extra = widget

    def _cell(self):
        if not self.tiles:
            return QSize(0, 0)
        return self.tiles[0].sizeHint().expandedTo(self.tiles[0].minimumSize())

    def _columns(self, width):
        cell = self._cell()
        return max(1, int((width + self.gap) // max(1, cell.width() + self.gap)))

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        cell = self._cell()
        cols = self._columns(width)
        rows = (len(self.tiles) + cols - 1) // cols
        h = rows * cell.height() + max(0, rows - 1) * self.vgap
        if self.extra is not None:
            h += self.vgap + self.extra.heightForWidth(width) if self.extra.hasHeightForWidth() \
                else self.vgap + self.extra.sizeHint().height()
        return h

    def sizeHint(self):
        cell = self._cell()
        return QSize(cell.width() * 4 + self.gap * 3, self.heightForWidth(cell.width() * 4 + self.gap * 3))

    def minimumSizeHint(self):
        return QSize(self._cell().width(), self.heightForWidth(self._cell().width()))

    def resizeEvent(self, event):
        cell = self._cell()
        cols = self._columns(self.width())
        for i, tile in enumerate(self.tiles):
            r, c = divmod(i, cols)
            tile.setGeometry(c * (cell.width() + self.gap), r * (cell.height() + self.vgap),
                             cell.width(), cell.height())
        if self.extra is not None:
            rows = (len(self.tiles) + cols - 1) // cols
            y = rows * (cell.height() + self.vgap)
            self.extra.setGeometry(0, y, self.width(), self.height() - y)
        self.setMinimumHeight(self.heightForWidth(self.width()))


class Card(QFrame):
    def __init__(self, settings, scale=1.0):
        super().__init__()
        self.setObjectName("SettingsCard")
        self.settings = settings
        self._s = scale  # (a window's own zoom - Insert as: everything in it grows together)
        self.box = QVBoxLayout(self)
        self.box.setContentsMargins(0, round(2 * scale), 0, round(2 * scale))
        self.box.setSpacing(0)
        self.rows = []

    def add(self, row):
        if self.rows:
            line = QFrame()
            line.setObjectName("SettingsHairline")
            line.setFixedHeight(1)
            holder = QHBoxLayout()
            holder.setContentsMargins(round(16 * self._s), 0, round(16 * self._s), 0)
            holder.addWidget(line)
            self.box.addLayout(holder)
            row._hairline = line
            line.setVisible(not row.isHidden())
            row.installEventFilter(self)
        self.box.addWidget(row)
        self.rows.append(row)

    def eventFilter(self, obj, event):
        # a row that hides (the colours until "Show every colour") takes its line with it
        if event.type() in (QEvent.ShowToParent, QEvent.HideToParent) and getattr(obj, "_hairline", None) is not None:
            obj._hairline.setVisible(not obj.isHidden())
        return False


class Section(QWidget):
    """A heading above its card."""

    def __init__(self, title, card, scale=1.0):
        super().__init__()
        self.title = title
        self.card = card
        v = QVBoxLayout(self)
        v.setContentsMargins(0, round(14 * scale), 0, 0)
        v.setSpacing(round(8 * scale))
        if title:
            heading = QLabel(title.replace("&&", "&"))
            heading.setObjectName("SectionTitle")
            v.addWidget(heading)
        v.addWidget(card)


def _short_help(text):
    from .help_text import HELP, SHORT
    if text.strip() in SHORT:
        return SHORT[text.strip()]
    tip = HELP.get(text.strip())
    if not tip:
        return ""
    import re
    first = re.split(r"(?<!e\.g)(?<!i\.e)\. ", tip)[0].strip()
    if not first.endswith((".", "!", "?")):
        first += "."
    return first if len(first) <= DESCRIPTION_MAX else ""


def _long_help(text):
    from .help_text import HELP
    return HELP.get(text.strip(), "")


def _rows_of(layout):
    """[(kind, a, b)] for each row of a group box's layout:
    ("check", checkbox), ("field", label, field item), ("free", widget or layout)."""
    out = []
    if isinstance(layout, QFormLayout):
        for r in range(layout.rowCount()):
            label = layout.itemAt(r, QFormLayout.LabelRole)
            field = layout.itemAt(r, QFormLayout.FieldRole)
            span = layout.itemAt(r, QFormLayout.SpanningRole)
            if span is not None:
                out.append(_classify(span))
            elif label is not None and label.widget() is not None and field is not None:
                out.append(("field", label.widget(), field))
            elif field is not None:
                out.append(_classify(field))
        return out
    if isinstance(layout, QGridLayout):
        return [("free", _regrid(layout), None)]  # a grid (theme gallery) stays one piece
    for i in range(layout.count()):
        item = layout.itemAt(i)
        if item.spacerItem() is not None:
            continue
        out.append(_classify(item))
    return out


def _regrid(grid):
    """Moves a group box's own grid into a fresh widget, cell for cell."""
    holder = QWidget()
    new = QGridLayout(holder)
    new.setContentsMargins(0, 0, 0, 0)
    new.setHorizontalSpacing(grid.horizontalSpacing())
    new.setVerticalSpacing(grid.verticalSpacing())
    for c in range(grid.columnCount()):
        new.setColumnStretch(c, grid.columnStretch(c))
    for r in range(grid.rowCount()):
        new.setRowStretch(r, grid.rowStretch(r))
    cells = []
    for i in range(grid.count()):
        item = grid.itemAt(i)
        cells.append((item.widget(), item.layout(), item.alignment(), grid.getItemPosition(i)))
    while grid.count():
        grid.takeAt(0)
    for widget, sub, align, (r, c, rs, cs) in cells:
        if widget is not None:
            new.addWidget(widget, r, c, rs, cs, align)
        elif sub is not None:
            sub.setParent(None)
            new.addLayout(sub, r, c, rs, cs, align)
    return holder


def _classify(item):
    w = item.widget()
    if isinstance(w, QCheckBox):
        return ("check", w, None)
    return ("free", w if w is not None else item.layout(), None)


def _detach(item_or_widget):
    """Takes a widget / layout out of whatever layout holds it."""
    if isinstance(item_or_widget, QWidget):
        parent = item_or_widget.parentWidget()
        if parent is not None and parent.layout() is not None:
            parent.layout().removeWidget(item_or_widget)
        return item_or_widget
    if isinstance(item_or_widget, QLayout):
        parent = item_or_widget.parent()
        if isinstance(parent, QLayout):
            parent.removeItem(item_or_widget)
        elif isinstance(parent, QWidget) and parent.layout() is not None:
            parent.layout().removeItem(item_or_widget)
        return item_or_widget
    return None


def _field_content(field_item):
    return field_item.widget() if field_item.widget() is not None else field_item.layout()


def cardify(page, settings):
    """Turns every group box on `page` into a heading + card of rows.
    Returns the rows (for searching Settings)."""
    muted = settings.theme["picker_folder"]
    layout = page.layout()
    rows_out = []
    boxes = [layout.itemAt(i).widget() for i in range(layout.count())
             if isinstance(layout.itemAt(i).widget(), QGroupBox)]
    for box in boxes:
        index = layout.indexOf(box)
        card = Card(settings)
        inner = box.layout()
        entries = _rows_of(inner) if inner is not None else []
        for kind, a, b in entries:
            if kind == "check":
                cb = _detach(a)
                title = QLabel(cb.text().replace("&&", "&"))
                title.setObjectName("SettingTitle")
                title.setWordWrap(True)
                if hasattr(cb, "doubleClicked"):
                    title.mouseDoubleClickEvent = lambda e, cb=cb: cb.doubleClicked.emit()
                switch = ToggleSwitch(settings, cb)
                cb.hide()
                tip = _long_help(cb.text())
                if tip:
                    title.setToolTip(tip)
                    switch.setToolTip(tip)
                holder = QHBoxLayout()
                holder.setSpacing(0)
                holder.addWidget(cb)
                holder.addWidget(switch, 0, Qt.AlignRight | Qt.AlignVCenter)
                row = SettingRow(title, _short_help(cb.text()), holder, muted)
            elif kind == "field":
                label = _detach(a)
                label.setObjectName("SettingTitle")
                if isinstance(label, QLabel):
                    label.setWordWrap(True)
                    label.setMinimumWidth(0)
                    label.setMinimumHeight(0)
                content = _detach(_field_content(b))
                text = label.text() if isinstance(label, QLabel) else ""
                tip = _long_help(text)
                if tip and isinstance(label, QLabel):
                    label.setToolTip(tip)
                row = SettingRow(label, _short_help(text), content, muted)
            else:
                content = _detach(a)
                if content is None:
                    continue
                row = FreeRow(content)
            card.add(row)
            rows_out.append(row)
        section = Section(box.title(), card)
        layout.insertWidget(index, section)  # (in its page first: shown with no parent it's a window of its own -
        section.setVisible(box.isVisibleTo(page) if box.parentWidget() is not None else True)  # Windows flashed them)
        layout.removeWidget(box)
        box.hide()
        box.setParent(None)
        box.deleteLater()
        for row in card.rows:
            row.section_title = box.title().replace("&&", "&")
    return rows_out


# -- the sidebar's icons: the same line icons as the Actions panel (glyphs.py) --
NAV_GLYPH = {"general": "general", "preview": "preview_page", "sound": "sound", "timeline": "timeline",
             "appearance": "appearance", "keys": "keys", "scripts": "scripts", "folders": "folders",
             "prefixes": "prefixes", "stats": "stats", "about": "about", "fusion": "tidy",
             "organise": "organise"}


# each page's own colour (2026-10-21, the owner: "give the symbols colors here, if it makes sense") - no orange;
# Scripts in the red of a script's symbol everywhere else (actions_panel.script_red). Tiles even them out (_tile_tone)
# (General, Appearance, Keybindings and About have none: Clipse's own, plain grey symbols at the top - as Vicinae's
# own settings are, its extensions' coloured below them)
NAV_COLORS = {"preview": "#5b8def", "sound": "#e0558f", "timeline": "#2fb3a3", "fusion": "#9a6cf0",
              "scripts": "#e5534b", "folders": "#3d9fe0", "prefixes": "#3fbf6f",
              "organise": "#d4a72c"}


def nav_color(name, theme=None):
    """A page's colour in the sidebar (None: it has none - a plain grey symbol)."""
    return NAV_COLORS.get(name)


def nav_icon(name, color, size=18):
    from .glyphs import draw_glyph
    pm = QPixmap(QSize(size * 2, size * 2))
    pm.setDevicePixelRatio(2.0)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    draw_glyph(p, NAV_GLYPH.get(name, name), QPointF(size / 2, size / 2), size * 0.95, QColor(color))
    p.end()
    return QIcon(pm)


def _tile_tone(color):
    """Every tile in one band of brightness and strength, so a row of them reads as one set (Vicinae's way)."""
    h, sat, light, a = color.getHslF()
    h = max(h, 0.0)
    if sat > 0.05:
        sat = min(max(sat, 0.55), 0.8)
    return QColor.fromHslF(h, sat, min(max(light, 0.42), 0.52), a)


def _shifted(color, dh, ds, dl):
    h, sat, light, a = color.getHslF()
    return QColor.fromHslF((max(h, 0.0) + dh + 1.0) % 1.0, min(max(sat + ds, 0.0), 1.0),
                           min(max(light + dl, 0.0), 1.0), a)


def nav_tile(name, color, size=18):
    """The page's symbol in white on a small square of its colour - Vicinae's measurements (its settings sidebar,
    2026-10-21: "a little more profeesional"): the symbol in the middle 62 %, corners a quarter of the side, a soft
    light-to-dark fall from top to bottom, a faint light edge, a small shadow under the symbol."""
    from PySide6.QtGui import QLinearGradient, QPen
    from .glyphs import draw_glyph
    pm = QPixmap(QSize(size * 2, size * 2))
    pm.setDevicePixelRatio(2.0)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    tone = _tile_tone(QColor(color))
    rect, radius = QRectF(0, 0, size, size), size * 0.25
    fall = QLinearGradient(rect.topLeft(), rect.bottomLeft())
    fall.setColorAt(0, _shifted(tone, 0.025, -0.03, 0.10))
    fall.setColorAt(1, _shifted(tone, -0.015, 0.06, -0.05))
    p.setPen(Qt.NoPen)
    p.setBrush(fall)
    p.drawRoundedRect(rect, radius, radius)
    edge = max(0.5, size / 32)
    p.setBrush(Qt.NoBrush)
    p.setPen(QPen(QColor(255, 255, 255, 30), edge))
    p.drawRoundedRect(rect.adjusted(edge / 2, edge / 2, -edge / 2, -edge / 2), radius - edge / 2, radius - edge / 2)
    inner, glyph = size * 0.62, NAV_GLYPH.get(name, name)
    draw_glyph(p, glyph, QPointF(size / 2, size / 2 + size * 0.035), inner, QColor(0, 0, 0, 70))  # its shadow
    draw_glyph(p, glyph, QPointF(size / 2, size / 2), inner, QColor("#ffffff"))
    p.end()
    return QIcon(pm)


class PickerSketch(QWidget):
    """A small drawing of the picker as it opens on one of Resolve's pages:
    a sample row for everything that's switched on in "What the list
    shows" - so it's plain what each tile does to the list. Reads the
    settings every time it's drawn; call update() after a change."""

    # what a row of each kind looks like: (symbol, a likely name, where the name's colour comes from)
    SAMPLES = {
        "show_video": ("video", "interview_take2.mp4"), "show_audio": ("sound", "whoosh_dark.wav"),
        "show_images": ("image", "thumbnail.png"), "show_adjustment_clips": ("adjustment", "adjustment_clip"),
        "show_compound_clips": ("compound", "Intro (compound)"), "show_bins": ("bin", "B-roll (12)"),
        "show_selected_clips_option": ("selected", "Selected Clips (3)"),
        "scripts": ("script", "export_stills.py"), "macros": ("macro", "glitch_transition"),
        "comps": ("comp", "lower_third.comp"), "nodes": ("node", "Transform"),
        "expressions": ("expression", "Wiggle the position"), "shortcuts": ("shortcut", "Settings: Appearance"),
    }

    def __init__(self, settings, page, title):
        super().__init__()
        self.settings = settings
        self.page = page      # "other" or "fusion" (settings.page_defaults)
        self.title = title
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFixedHeight(round(self._metrics()[3]))
        self.setMinimumWidth(250)

    ROWS = 8  # at most - it's a sketch

    def _metrics(self):
        """(row height, search bar, bottom bar, the whole height) - from the text, so its rows never overlap."""
        from PySide6.QtGui import QFontMetricsF
        h = QFontMetricsF(font_at(SMALL * rel(self.settings, "settings"))).height()
        row_h, search_h, bar_h = round(h * 1.55), round(h * 2.0), round(h * 1.3)
        return row_h, search_h, bar_h, h + 8 + search_h + 5 + self.ROWS * row_h + bar_h + 12

    def sizeHint(self):
        return QSize(330, self.height())

    def rows(self):
        """[(symbol, name)] - what the list would start with."""
        from .settings import LIST_TILES
        sources = self.settings.page_defaults.get(self.page, {})
        out = []
        if sources.get("clips"):  # each page lists its own kinds of Media Pool row (Settings.kind_on)
            out += [self.SAMPLES[key] for key, _label, _symbol in LIST_TILES
                    if key in self.SAMPLES and self.settings.kind_on(key, self.page)]
        out += [self.SAMPLES[key] for key in ("scripts", "macros", "comps", "nodes", "expressions", "shortcuts")
                if sources.get(key)]
        return out

    def paintEvent(self, event):
        from .symbols import draw_symbol
        from PySide6.QtGui import QFontMetricsF
        t = self.settings.theme
        text, muted, border = QColor(t["picker_text"]), QColor(t["picker_folder"]), QColor(t["picker_border"])
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        small = font_at(SMALL * rel(self.settings, "settings"), self.font())
        fm = QFontMetricsF(small)
        p.setFont(small)
        p.setPen(muted)
        p.drawText(QRectF(2, 0, self.width() - 4, fm.height() + 2), Qt.AlignLeft | Qt.AlignVCenter, self.title)
        card = QRectF(1, fm.height() + 8, self.width() - 2, self.height() - fm.height() - 9)
        p.setPen(QPen(border, 1))
        p.setBrush(QColor(t["picker_bg"]))
        p.drawRoundedRect(card, 9, 9)
        row_h, search_h, bar_h, _whole = self._metrics()
        p.setPen(muted)
        p.drawText(QRectF(card.left() + 12, card.top(), card.width() - 24, search_h), Qt.AlignLeft | Qt.AlignVCenter, "Search\u2026")
        line = QColor(border)
        line.setAlphaF(0.6)
        p.setPen(QPen(line, 1))
        p.drawLine(QPointF(card.left() + 1, card.top() + search_h), QPointF(card.right() - 1, card.top() + search_h))
        p.drawLine(QPointF(card.left() + 1, card.bottom() - bar_h), QPointF(card.right() - 1, card.bottom() - bar_h))
        rows = self.rows()
        area = QRectF(card.left() + 6, card.top() + search_h + 5, card.width() - 12, card.height() - search_h - bar_h - 9)
        if not rows:
            p.setPen(muted)
            p.drawText(area, Qt.AlignCenter | Qt.TextWordWrap, "Empty until you type a prefix\n(macro:  n:  x: ...)")
            p.end()
            return
        for i, (symbol, name) in enumerate(rows[:self.ROWS]):
            row = QRectF(area.left(), area.top() + i * row_h, area.width(), row_h - 2)
            if i == 0:  # the highlighted one
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(t["picker_select_bg"]))
                p.drawRoundedRect(row, 5, 5)
            try:
                color = QColor(self.settings.icon_color("audio" if symbol in ("sound", "music") else symbol))
            except KeyError:
                color = QColor(text)
            th = min(row_h - 4, fm.height())
            tag = QRectF(row.left() + 8, row.center().y() - th / 2, th * 1.4, th)
            tint = QColor(color)
            tint.setAlphaF(0.2)
            p.setPen(Qt.NoPen)
            p.setBrush(tint)
            p.drawRoundedRect(tag, 3, 3)
            draw_symbol(p, symbol, tag.center(), th * 0.7, color)
            p.setPen(text)
            room = row.right() - tag.right() - 14
            p.drawText(QRectF(tag.right() + 8, row.top(), room, row.height()), Qt.AlignLeft | Qt.AlignVCenter,
                       fm.elidedText(name, Qt.ElideRight, room))
        p.end()


class ToggleTiles(QWidget):
    """Tiles that switch on and off - each a kind of row in the picker's
    list, drawn with its own symbol and colour. Wraps to the width."""
    toggled = Signal(str, bool)

    TILE_W, TILE_H, GAP = 112, 76, 8  # (at 14 px text - grown with it, and wide enough for the longest name)

    def __init__(self, settings, tiles, values, tile_w=None):
        super().__init__()
        self.settings = settings
        if tile_w:
            self.TILE_W = tile_w
        self.tiles = tiles            # [(key, label, symbol)]
        self.values = dict(values)    # key -> bool
        self._hover = None
        self._focus = 0
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        sp = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        sp.setHeightForWidth(True)
        self.setSizePolicy(sp)
        from .fonts import zoom
        from PySide6.QtGui import QFontMetricsF
        k = zoom(settings) * window_zoom(settings, "settings")
        fm = QFontMetricsF(font_at(SMALL * rel(settings, "settings")))
        longest = max((fm.horizontalAdvance(label) for _key, label, _symbol in tiles), default=0)
        self.TILE_W = round(max(self.TILE_W * k, longest + 22))
        self.TILE_H = round(self.TILE_H * k)
        self.GAP = round(self.GAP * k)
        self._k = k

    def _cols(self, width):
        return max(1, int((width + self.GAP) // (self.TILE_W + self.GAP)))

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        cols = self._cols(width)
        rows = (len(self.tiles) + cols - 1) // cols
        return rows * self.TILE_H + (rows - 1) * self.GAP + 2

    def sizeHint(self):
        w = 4 * self.TILE_W + 3 * self.GAP
        return QSize(w, self.heightForWidth(w))

    def minimumSizeHint(self):
        return QSize(self.TILE_W, self.heightForWidth(max(self.width(), self.TILE_W)))

    def resizeEvent(self, event):
        self.setMinimumHeight(self.heightForWidth(self.width()))

    def _rect(self, i):
        cols = self._cols(self.width())
        r, c = divmod(i, cols)
        return QRectF(1 + c * (self.TILE_W + self.GAP), 1 + r * (self.TILE_H + self.GAP), self.TILE_W - 2,
                      self.TILE_H - 2)

    def _hit(self, pos):
        return next((i for i in range(len(self.tiles)) if self._rect(i).contains(pos)), None)

    def _flip(self, i):
        key = self.tiles[i][0]
        self.values[key] = not self.values.get(key, False)
        self.update()
        self.toggled.emit(key, self.values[key])

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
        if hit is not None and event.button() == Qt.LeftButton:
            self._focus = hit
            self._flip(hit)

    def keyPressEvent(self, event):
        n = len(self.tiles)
        if event.key() == Qt.Key_Right:
            self._focus = (self._focus + 1) % n
        elif event.key() == Qt.Key_Left:
            self._focus = (self._focus - 1) % n
        elif event.key() in (Qt.Key_Space, Qt.Key_Return, Qt.Key_Enter):
            self._flip(self._focus)
            return
        else:
            return super().keyPressEvent(event)
        self.update()

    def paintEvent(self, event):
        from .symbols import draw_symbol
        t = self.settings.theme
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        accent = QColor(t.get("picker_accent", t["picker_text"]))
        text, muted = QColor(t["picker_text"]), QColor(t["picker_folder"])
        small = font_at(SMALL * rel(self.settings, "settings"), self.font())
        p.setFont(small)
        for i, (key, label, symbol) in enumerate(self.tiles):
            r = self._rect(i)
            on = self.values.get(key, False)
            hover = self._hover == i or (self.hasFocus() and self._focus == i)
            from . import look
            look.paint_tile(p, r, self.settings, chosen=on, hover=hover)  # (the app's one tile)
            try:
                color = QColor(self.settings.icon_color("audio" if symbol in ("sound", "music") else symbol))
            except KeyError:
                color = QColor(accent)
            if not on:
                color.setAlphaF(0.35)
            k = self._k
            draw_symbol(p, symbol, QPointF(r.center().x(), r.top() + 26 * k), 20 * k, color)
            p.setPen(text if on else muted)
            p.drawText(QRectF(r.left() + 4, r.bottom() - 26 * k, r.width() - 8, 18 * k), Qt.AlignHCenter | Qt.AlignVCenter,
                       label)
            # on: a small tick in the corner; off: an empty ring
            dot = QPointF(r.right() - 11 * k, r.top() + 11 * k)
            if on:
                p.setPen(Qt.NoPen)
                p.setBrush(accent)
                p.drawEllipse(dot, 6, 6)
                p.setPen(QPen(QColor(t["picker_bg"]), 1.6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
                path = QPainterPath()
                path.moveTo(dot.x() - 3, dot.y())
                path.lineTo(dot.x() - 0.8, dot.y() + 2.2)
                path.lineTo(dot.x() + 3.2, dot.y() - 2.2)
                p.setBrush(Qt.NoBrush)
                p.drawPath(path)
            else:
                p.setPen(QPen(muted, 1.1))
                p.setBrush(Qt.NoBrush)
                p.drawEllipse(dot, 5.5, 5.5)
        p.end()
