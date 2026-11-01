"""History - Ctrl+H. Every insert (single, staged batch, or multi-
selection) gets recorded as one entry: which clips (by name, with
counts), and the Insert as settings it was made with. Picking an entry
restores both - the clips are staged again (re-matched by name against the
current row list) and Insert as is set up the way it was, so Enter repeats
the insert and Insert as shows what it will do (presets.restore).

Kept in history.json (paths.data), per project (the last
MAX_HISTORY_ENTRIES of each) - it used to live only in the service's
memory, so every restart of the service emptied it.

Shown as rows like the rest of the app: a small drawing of how it was
inserted (the Insert as tile's), the clips, how - and when, under a
heading for each day."""
import json
import os
import time

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QPushButton,
                               QStyle, QStyledItemDelegate, QVBoxLayout)

from .scripts_fusion import format_relative_time
from .settings_dialog import restrict_tab_to_inputs
from .fonts import SMALL, at as font_at  # (the one scale of sizes)
from . import paths

MAX_HISTORY_ENTRIES = 50  # per project
HISTORY_FILE = paths.data("history.json")

HEADING, ENTRY = 1, 2  # what a row is (Qt.UserRole + 1)


# -- kept on disk --
def load():
    """Every entry kept, oldest first (all projects)."""
    entries = paths.read_json(HISTORY_FILE, [])
    return [e for e in entries if isinstance(e, dict) and isinstance(e.get("clip_names"), dict)] \
        if isinstance(entries, list) else []


def save(entries):
    """Writes the entries down - the last MAX_HISTORY_ENTRIES of each project. Returns what's kept."""
    kept, seen = [], {}
    for entry in reversed(entries):
        project = entry.get("project") or ""
        seen[project] = seen.get(project, 0) + 1
        if seen[project] <= MAX_HISTORY_ENTRIES:
            kept.append(entry)
    kept.reverse()
    try:
        paths.write_json(HISTORY_FILE, kept)
    except OSError:
        pass
    return kept


def of_project(entries, project, page=None):
    """The entries of this project (and the ones from before projects were noted) - of one page's History when
    `page` is given: "edit" (clips on the timeline - every entry from before pages were noted) or "fusion" (what
    went into a composition). Each page has its own (2026-10-14)."""
    return [e for e in entries if (not e.get("project") or not project or e.get("project") == project)
            and (page is None or e.get("page", "edit") == page)]


# what went into a composition, by kind: (its colour among the picker's symbols, its name, the plural)
FUSION_KINDS = {"node": ("node", "node", "nodes"), "macro": ("macro", "macro", "macros"),
                "expression": ("expression", "expression", "expressions"), "clip": ("video", "clip", "clips")}


def fusion_summary(items):
    """'Merge1' for one thing, else '2 nodes · 1 clip'."""
    if len(items) == 1:
        return items[0]["name"]
    counts = {}
    for item in items:
        counts[item["kind"]] = counts.get(item["kind"], 0) + 1
    return " \u00b7 ".join(f"{n} {FUSION_KINDS[k][1] if n == 1 else FUSION_KINDS[k][2]}"
                            for k, n in counts.items() if k in FUSION_KINDS)


def day_heading(stamp, now=None):
    """'Today', 'Yesterday', 'Monday', or '12 October' for an older day."""
    now = time.localtime(now or time.time())
    then = time.localtime(stamp)
    days = (time.mktime((now.tm_year, now.tm_mon, now.tm_mday, 0, 0, 0, 0, 0, -1))
            - time.mktime((then.tm_year, then.tm_mon, then.tm_mday, 0, 0, 0, 0, 0, -1))) // 86400
    if days <= 0:
        return "Today"
    if days == 1:
        return "Yesterday"
    if days < 7:
        return time.strftime("%A", then)
    return time.strftime("%-d %B", then) if os.name != "nt" else time.strftime("%d %B", then).lstrip("0")


# -- the dialog --
class _Rows(QStyledItemDelegate):
    """A heading for each day; an entry as its drawing, its clips and how - and when, on the right."""

    TILE_W, TILE_H = 72, 44  # (at History's own 100 %: times its zoom - Ctrl + / -)

    def __init__(self, settings, font, k=1.0):
        super().__init__()
        self.settings = settings
        self.font = font
        self.k = k
        self.hover_row = None  # (clip_model.RowHover)

    @property
    def tile_w(self):
        return self.TILE_W * self.k

    @property
    def tile_h(self):
        return self.TILE_H * self.k

    def sizeHint(self, option, index):
        h = QFontMetrics(self.font).height()
        if index.data(Qt.UserRole + 1) == HEADING:
            return QSize(0, int(h + 18))
        return QSize(0, int(max(self.tile_h + 14, 2 * h + 22)))

    def paint(self, p, option, index):
        from . import presets as pm
        from .insert_as_dialog import _colors, draw_preset
        t = self.settings.theme
        c = _colors(t)
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(option.rect)
        if index.data(Qt.UserRole + 1) == HEADING:
            small = font_at(SMALL, self.font, QFont.DemiBold)  # (a heading: Vicinae's, smaller and semibold)
            p.setFont(small)
            p.setPen(QColor(t["picker_folder"]))
            p.drawText(r.adjusted(14, 8, -14, 0), Qt.AlignLeft | Qt.AlignVCenter, index.data(Qt.DisplayRole))
            p.restore()
            return
        entry = index.data(Qt.UserRole)
        chosen = bool(option.state & QStyle.State_Selected)
        if chosen or index.row() == self.hover_row:  # a soft rounded highlight, like the picker's rows
            fill = QColor(t["picker_select_bg"])
            fill.setAlpha(255 if chosen else 110)
            p.setPen(Qt.NoPen)
            p.setBrush(fill)
            p.drawRoundedRect(r.adjusted(6, 2, -6, -2), 8, 8)
        # how it was inserted: the Insert as tile's drawing - or, for a composition, its nodes in a little line
        tile = QRectF(r.left() + 16, r.center().y() - self.tile_h / 2, self.tile_w, self.tile_h)
        p.setPen(QPen(QColor(t["picker_border"]), 1))
        p.setBrush(QColor(t.get("picker_bar_bg", t["picker_bg"])))
        p.drawRoundedRect(tile, 6, 6)
        fusion = entry.get("page") == "fusion"
        preset = pm._clean(entry.get("preset") or {})
        p.save()
        if fusion:
            self._draw_chain(p, tile, entry.get("items") or [])
        else:
            draw_preset(p, tile.adjusted(7, 6, -7, -6), preset, c)
        p.restore()
        # the clips, and how
        text_left = tile.right() + 14
        when = format_relative_time(entry.get("timestamp")) or ""
        fm = QFontMetrics(self.font)
        when_w = fm.horizontalAdvance(when) + 18
        names = list(entry["clip_names"].items())
        if entry.get("page") == "fusion" and entry.get("items"):  # (in the order they went in)
            order = []
            for item in entry["items"]:
                if item["name"] not in order:
                    order.append(item["name"])
            names = [(n, entry["clip_names"].get(n, 1)) for n in order]
        shown = ", ".join(f"{name}" + (f" ×{count}" if count > 1 else "") for name, count in names[:3])
        if len(names) > 3:
            shown += f"  +{len(names) - 3} more"
        width = r.right() - 14 - when_w - text_left
        line_h = fm.height()
        top = r.center().y() - line_h - 1
        p.setFont(self.font)
        p.setPen(QColor(t["picker_text"]))
        p.drawText(QRectF(text_left, top, width, line_h), Qt.AlignLeft | Qt.AlignVCenter,
                   fm.elidedText(shown, Qt.ElideRight, int(width)))
        total = sum(count for _n, count in names)
        how = pm.summary(preset) if entry.get("preset") and not pm.plain(preset) else ""
        own = entry.get("preset") or {}
        if own.get("id") not in (None, "normal", "history") and own.get("name"):  # one of your presets: its name first
            how = own["name"] + (f" · {how}" if how else "")
        if fusion:
            items = entry.get("items") or []
            under = fusion_summary(items) if len(items) > 1 else FUSION_KINDS.get(
                items[0]["kind"] if items else "", ("", "", ""))[1].capitalize()
        else:
            under = f"{total} clip{'s' if total != 1 else ''}" + (f" · {how}" if how else " · a plain insert")
        small = font_at(SMALL, self.font)
        p.setFont(small)
        sfm = QFontMetrics(small)
        p.setPen(QColor(t["picker_folder"]))
        p.drawText(QRectF(text_left, top + line_h + 3, width, sfm.height()), Qt.AlignLeft | Qt.AlignVCenter,
                   sfm.elidedText(under, Qt.ElideRight, int(width)))
        p.drawText(QRectF(r.right() - 14 - when_w, r.top(), when_w, r.height()), Qt.AlignRight | Qt.AlignVCenter, when)
        p.restore()

    def _draw_chain(self, p, tile, items):
        """Up to four small nodes joined by a line, each in its kind's colour (a node, a macro, a clip ...)."""
        shown = items[:4] or [{"kind": "node"}]
        w, h, gap = 12.0, 9.0, 5.0
        total = len(shown) * w + (len(shown) - 1) * gap
        x = tile.center().x() - total / 2
        y = tile.center().y()
        line = QColor(self.settings.theme["picker_folder"])
        p.setPen(QPen(line, 1.2))
        p.drawLine(QPointF(x + w / 2, y), QPointF(x + total - w / 2, y))
        for item in shown:
            colour = QColor(self.settings.icon_color(FUSION_KINDS.get(item.get("kind"), ("node",))[0]))
            p.setPen(Qt.NoPen)
            p.setBrush(colour)
            p.drawRoundedRect(QRectF(x, y - h / 2, w, h), 2.5, 2.5)
            x += w + gap


class HistoryDialog(QDialog):
    def showEvent(self, event):
        # Make sure the dialog gets keyboard focus over the always-on-top
        # picker (Wayland compositors don't always do this by themselves).
        super().showEvent(event)
        self.raise_()
        if self.isWindow():  # (in the picker's own place it's no window - PickerWindow._in_place)
            self.activateWindow()

    def __init__(self, history, settings, parent=None, project=None, changed=None, page="edit"):
        super().__init__(parent)
        self.history = history       # every entry kept (all projects) - changed in place
        self.project = project
        self.page = page             # "edit" or "fusion": each page has its own History
        self.changed = changed       # () -> None: something was removed - write it down
        self.settings = settings
        self.selected_entry = None
        self.setObjectName("AppDialog")
        self.setWindowTitle("History")
        muted = settings.theme["picker_folder"]

        font = self._zoomed_font()
        self.setFont(font)
        from .theme import window_sheet
        self.setStyleSheet(window_sheet(settings, "history"))  # (its own zoom: every word in it)

        header = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(2)
        title = QLabel("History")
        title.setObjectName("DialogTitle")
        titles.addWidget(title)
        header.addLayout(titles, 1)
        self.clear_button = QPushButton("Clear")
        self.clear_button.setObjectName("QuietButton")  # (like Settings' Reset page)
        self.clear_button.setFocusPolicy(Qt.NoFocus)
        self.clear_button.setAutoDefault(False)
        self.clear_button.setToolTip("Forget what's listed here - this page, this project")
        self.clear_button.clicked.connect(self._clear)
        header.addWidget(self.clear_button, 0, Qt.AlignVCenter)

        # the search field every dialog has (Settings' sidebar too): a magnifier, a deeper shade, no edge
        from .settings_cards import nav_icon
        self.filter = QLineEdit()
        self.filter.setObjectName("DialogSearch")
        self.filter.setPlaceholderText("Search...")
        self.filter.setClearButtonEnabled(True)
        self.filter.addAction(nav_icon("search", muted, 15), QLineEdit.LeadingPosition)
        self.filter.textChanged.connect(lambda _t: self._populate())

        self.list_widget = QListWidget()
        self.list_widget.setFont(font)
        self.list_widget.setFrameShape(QListWidget.NoFrame)
        self.list_widget.setObjectName("HistoryList")
        self.list_widget.setStyleSheet("QListWidget#HistoryList { background: transparent; border: none; outline: none; }"
                                       "QListWidget#HistoryList::item { background: transparent; border: none; }")
        self.rows = _Rows(settings, QFont(font), self._k())
        self.list_widget.setItemDelegate(self.rows)
        self.list_widget.setVerticalScrollMode(QListWidget.ScrollPerPixel)
        from .clip_model import RowHover
        self._hover = RowHover(self.list_widget, self.rows)
        self.list_widget.itemActivated.connect(self._activate)
        self.list_widget.itemClicked.connect(self._activate)

        self.empty = QLabel("Nothing inserted yet")
        self.empty.setAlignment(Qt.AlignCenter)
        self.empty.setStyleSheet(f"color: {muted};")

        # (no key hints at the bottom: Delete still takes an entry out, Enter and Esc go without saying)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 18, 22, 14)  # (as Insert as)
        layout.setSpacing(12)
        layout.addLayout(header)
        layout.addWidget(self.filter)
        layout.addWidget(self.list_widget, 1)
        layout.addWidget(self.empty, 1)
        self.resize(680, 560)
        self._populate()
        restrict_tab_to_inputs(self)
        self.filter.setFocus()
        self.filter.installEventFilter(self)

    def shown(self):
        """This project's entries that pass the filter, newest first."""
        words = self.filter.text().strip().lower().split()
        out = []
        for entry in reversed(of_project(self.history, self.project, self.page)):
            text = " ".join(entry["clip_names"]).lower() + " " + (entry.get("summary") or "").lower()
            if all(w in text for w in words):
                out.append(entry)
        return out

    def _populate(self):
        self.list_widget.clear()
        last_day = None
        first = None
        for entry in self.shown():
            day = day_heading(entry.get("timestamp") or time.time())
            if day != last_day:
                head = QListWidgetItem(day)
                head.setData(Qt.UserRole + 1, HEADING)
                head.setFlags(Qt.NoItemFlags)
                self.list_widget.addItem(head)
                last_day = day
            item = QListWidgetItem(entry.get("summary") or "")
            item.setData(Qt.UserRole, entry)
            item.setData(Qt.UserRole + 1, ENTRY)
            item.setToolTip(", ".join(f"{n} ×{k}" if k > 1 else n for n, k in entry["clip_names"].items()))
            self.list_widget.addItem(item)
            first = first or item
        anything = first is not None
        self.list_widget.setVisible(anything)
        self.empty.setVisible(not anything)
        if self.filter.text() and not anything:
            self.empty.setText("Nothing like that")
        self.clear_button.setEnabled(bool(of_project(self.history, self.project, self.page)))
        if first is not None:
            self.list_widget.setCurrentItem(first)

    def _step(self, way):
        """The next entry up or down (headings are stepped over)."""
        row = self.list_widget.currentRow()
        for n in range(row + way, -1 if way < 0 else self.list_widget.count(), way):
            if self.list_widget.item(n).data(Qt.UserRole + 1) == ENTRY:
                self.list_widget.setCurrentRow(n)
                return

    def eventFilter(self, obj, event):
        from PySide6.QtCore import QEvent
        if obj is self.filter and event.type() == QEvent.KeyPress:
            key = event.key()
            if key in (Qt.Key_Down, Qt.Key_Up):
                self._step(1 if key == Qt.Key_Down else -1)
                return True
            if key in (Qt.Key_Return, Qt.Key_Enter):
                item = self.list_widget.currentItem()
                if item is not None and item.data(Qt.UserRole + 1) == ENTRY:
                    self._activate(item)
                return True
            if key == Qt.Key_Delete and not self.filter.text():
                self._remove_current()
                return True
        return super().eventFilter(obj, event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Delete:
            self._remove_current()
            return
        from .fonts import zoom_key
        direction = zoom_key(event, self.settings)
        if direction is not None:
            self.zoom_window(direction)
            return
        super().keyPressEvent(event)
        if not self.isWindow():
            event.accept()  # in the picker's place: a key it has no use for never reaches the picker's own keys

    def _k(self):
        from .fonts import rel
        return rel(self.settings, "history")

    def _zoomed_font(self):
        from .fonts import apply_ui_font
        font = apply_ui_font(QFont(), self.settings)
        font.setPointSizeF(font.pointSizeF() * self._k())
        return font

    def zoom_window(self, direction):
        """Ctrl and + / - / 0: History by itself larger, smaller, as it ships (fonts.step_zoom) - in the picker's
        place there may not be room for everything (2026-10-17)."""
        from .fonts import step_zoom
        from .theme import window_sheet
        step_zoom(self.settings, "history", direction)
        self.settings.save()
        font = self._zoomed_font()
        self.setFont(font)
        self.setStyleSheet(window_sheet(self.settings, "history") + getattr(self, "in_place_css", ""))
        self.list_widget.setFont(font)
        self.rows.font, self.rows.k = QFont(font), self._k()
        self._populate()

    def _activate(self, item):
        if item is None or item.data(Qt.UserRole + 1) != ENTRY:
            return
        self.selected_entry = item.data(Qt.UserRole)
        self.accept()

    def _remove_current(self):
        item = self.list_widget.currentItem()
        if item is None or item.data(Qt.UserRole + 1) != ENTRY:
            return
        entry = item.data(Qt.UserRole)
        row = self.list_widget.currentRow()
        self.history[:] = [e for e in self.history if e is not entry and e != entry]
        if self.changed:
            self.changed()
        self._populate()
        self.list_widget.setCurrentRow(min(row, self.list_widget.count() - 1))
        if self.list_widget.currentItem() is not None and self.list_widget.currentItem().data(Qt.UserRole + 1) != ENTRY:
            self._step(1)

    def _clear(self):
        mine = of_project(self.history, self.project, self.page)
        self.history[:] = [e for e in self.history if e not in mine]
        if self.changed:
            self.changed()
        self._populate()
