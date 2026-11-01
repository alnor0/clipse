"""QAbstractListModel + QStyledItemDelegate for the clip list. This
replaces the hand-rolled Text-widget-with-tags rendering and the manual
click->line-number math from the Tk version with a real virtualized list
view — Qt handles hit-testing, scrolling, and keyboard navigation for us."""
import re

from PySide6.QtCore import Qt, QAbstractListModel, QModelIndex, QSize, QRectF, QPointF, QObject, QEvent
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPen, QLinearGradient
from PySide6.QtWidgets import QStyledItemDelegate, QStyle

from .fuzzy import match_positions, scorer
from . import picks
from .settings import PREFIX_CATEGORY_TARGETS, PREFIX_SPECIAL_TARGETS, PREFIX_EXTERNAL_TARGETS, ICON_DEFAULTS
from .symbols import draw_symbol, draw_star, draw_check
from .fonts import SMALL, TINY, at as font_at  # (the one scale of sizes)

ROLE_ORIG_INDEX = Qt.UserRole + 1
ENERGY_BARS_WIDTH = 13  # (three bars and their gaps, at scale 1)
_ENERGY_WORD = re.compile(r"(?<!\S)e([1-3])(?!\S)", re.I)


def shown_energy(row, settings):
    """(1-3 or 0, whether it's a guess): the file's own tag; without one, the analysis's guess if Settings asks for it."""
    own = getattr(row, "energy", 0)
    if own:
        return own, False
    guess = getattr(row, "energy_guess", 0) if settings.listen.get("guess_energy") else 0
    return guess, bool(guess)


def draw_energy(p, x, cy, scale, level, strong, theme, hollow=False):
    """A sound's energy, 1-3: three rising bars, that many lit, stronger on the list and the chosen tile. A guess:
    outlined, so it can't be taken for a tag of yours (a fainter filled one was: 2026-11-01). (2026-11-01: e1 e2 e3 on
    clips in the picker.)"""
    p.save()
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    lit = QColor(theme["picker_text"] if strong else theme["picker_folder"])
    if strong:
        lit.setAlphaF(0.8)
    off = QColor(theme["picker_text"])
    off.setAlphaF(0.16)
    width, gap = 3 * scale, 2 * scale
    for n in range(3):
        height = (5 + n * 3) * scale
        bar = QRectF(x + n * (width + gap), cy + 5.5 * scale - height, width, height)
        if hollow and n < level:
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(lit, max(1.0, 0.9 * scale)))
            bar = bar.adjusted(0.5, 0.5, -0.5, -0.5)
        else:
            p.setPen(Qt.NoPen)
            p.setBrush(lit if n < level else off)
        p.drawRoundedRect(bar, 1 * scale, 1 * scale)
    p.restore()


def _build_prefix_maps(settings):
    """Builds the three prefix->target lookup dicts fresh from
    settings.prefixes (fully user-configurable — Settings -> Search
    Prefixes). Cheap enough (a handful of entries) to rebuild on every
    keystroke rather than cache, which avoids any staleness bugs."""
    category_prefixes, special_prefixes, external_prefixes = {}, {}, {}

    def which(target):
        return category_prefixes if target in PREFIX_CATEGORY_TARGETS else special_prefixes \
            if target in PREFIX_SPECIAL_TARGETS else external_prefixes if target in PREFIX_EXTERNAL_TARGETS else None
    for target, prefix_list in settings.prefixes.items():
        for p in prefix_list:
            p = str(p).strip().lower()
            if p and which(target) is not None:
                which(target)[p] = target
    # ...and, where nothing else has them, each prefix's plural and the kind's own name: scripts:, macros:,
    # markers:, bin:, image: (the words set in Settings come first)
    taken = set(category_prefixes) | set(special_prefixes) | set(external_prefixes)
    for target, prefix_list in settings.prefixes.items():
        found = which(target)
        if found is None:
            continue
        plural = [] if target.endswith(("s", "ed", "ing", "x")) or target in ("music", "audio", "like", "recent") \
            else [target + "s"]
        for p in [target] + plural:
            if p not in taken:
                found[p] = target
                taken.add(p)
    return category_prefixes, special_prefixes, external_prefixes


class ClipListModel(QAbstractListModel):
    """Holds the full row set plus the currently-visible (filtered/sorted)
    subset. `staged` maps orig_index -> stage count, same semantics as the
    Tk version's session["staged"].

    `rows` is whichever row set is currently active — normally an alias
    for `clip_rows` (the Media Pool rows from the last open_picker), but
    swapped to a freshly-fetched external row set while a script/macro/
    comp/project prefix is active, then swapped back when it isn't."""

    def __init__(self, settings, insert_frequency, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.insert_frequency = insert_frequency
        self.clip_rows = []     # list[RowData] — the Media Pool rows
        self.rows = []          # list[RowData] — whichever set is currently active
        self.visible = []       # list[orig_index], in display order
        self.staged = {}        # orig_index -> count
        self.chain = []         # staged nodes / macros (Fusion), in order: [{"key", "category", "path", "name", "seq"}]
        self.showing_external = False
        self.query = ""         # search text without its prefix - rows highlight what matched
        self.external_provider = None       # set by PickerWindow: kind -> list[RowData]
        self.default_view_provider = None   # set by PickerWindow: () -> list[RowData], page-aware
        self.favorite_external_provider = None  # set by PickerWindow: () -> starred scripts/macros/...
        self.page_hides = ()  # kinds of row left out of the plain list on this page (sounds on the Fusion page)
        self.recent_provider = None  # set by PickerWindow: () -> [("clip", index) | ("ext", RowData)], newest first
        self.unused_provider = None  # set by PickerWindow: () -> clip row indices not on the current timeline
        self.used_provider = None    # set by PickerWindow: () -> [(clip row index, times on the timeline)], most first
        self.similar_provider = None  # set by PickerWindow: clip name -> [(clip row index, 0-100)]
        self.title_provider = None   # set by PickerWindow: text -> [RowData] (the one "add title" row)
        self.basic_provider = None   # ... (basics:, the rows whose names have what's typed)
        self.template_provider = None  # set by PickerWindow: text -> [RowData] (templates + "save as")
        self.layout_provider = None    # set by PickerWindow: text -> [RowData] (Resolve's layouts + "save as")
        self.prefix_menu_provider = None  # set by PickerWindow: text -> [RowData] - ":" on its own: every kind
        self.actions_provider = None   # set by PickerWindow: text -> [RowData] (the > action list)
        self.search_actions_provider = None  # text -> [RowData]: actions mixed into a normal search
        self.info_override = {}      # orig_index -> text shown instead of the bin
        self.checkup_provider = None  # set by PickerWindow: "missing"/"duplicate"/"clipping" -> [(clip row index, what's wrong)]

    def set_rows(self, rows):
        self.clip_rows = rows
        self.rows = rows
        self.showing_external = False
        self.staged = {}
        self.set_filter("")

    def _by_energy(self, rest, candidates):
        """`e2` in a search means sounds at that energy - not any name with an e and a 2 in it. A clip with the word in
        its name stays. No sound has an energy: it's a word like any other."""
        found = _ENERGY_WORD.search(rest or "")
        rows = self.rows
        if not found or not any(shown_energy(rows[i], self.settings)[0] for i in candidates):
            return rest, candidates
        level, word = int(found.group(1)), found.group(0).lower()
        kept = [i for i in candidates
                if shown_energy(rows[i], self.settings)[0] == level or word in rows[i].name.lower().split()]
        return _ENERGY_WORD.sub(" ", rest, 1).strip(), kept

    def set_filter(self, filter_text):
        self.beginResetModel()
        filter_text = filter_text.strip()
        if filter_text.startswith(">"):  # the action list - everything Clipse can do
            self.info_override = {}
            self.rows = self.actions_provider(filter_text[1:].strip()) if self.actions_provider else []
            self.showing_external = True
            self.query = filter_text[1:].strip()
            self.visible = list(range(len(self.rows)))
            self.endResetModel()
            return
        if filter_text.startswith(":") and ":" not in filter_text[1:]:  # the prefix menu: every kind, to pick one
            self.info_override = {}
            self.rows = self.prefix_menu_provider(filter_text[1:].strip()) if self.prefix_menu_provider else []
            self.showing_external = True
            self.query = ""
            self.visible = list(range(len(self.rows)))
            self.endResetModel()
            return
        category_prefixes, special_prefixes, external_prefixes = _build_prefix_maps(self.settings)

        category, special, external_kind, rest = None, None, None, filter_text
        if ":" in filter_text:
            prefix, remainder = filter_text.split(":", 1)
            prefix_key = prefix.strip().lower()
            if prefix_key in category_prefixes:
                category = category_prefixes[prefix_key]
                rest = remainder.strip()
            elif prefix_key in special_prefixes:
                special = special_prefixes[prefix_key]
                rest = remainder.strip()
            elif prefix_key in external_prefixes:
                external_kind = external_prefixes[prefix_key]
                rest = remainder.strip()
            elif prefix_key:
                print(f"[search] '{prefix_key}:' isn't a recognized prefix — "
                      f"searching '{filter_text}' as plain text instead.")

        # A colon prefix (a:, run:, s:, ...) always targets that specific
        # source regardless of page — only the truly unprefixed view
        # (blank, or plain text with no colon at all) is page-aware, so
        # there's always an explicit escape hatch back to clips.
        self.info_override = {}
        if external_kind in ("template", "layout"):  # (what's typed is a name to match or to save as)
            provider = self.template_provider if external_kind == "template" else self.layout_provider
            self.rows = provider(rest) if provider else []
            self.showing_external = True
            self.query = ""
            self.visible = list(range(len(self.rows)))
            self.endResetModel()
            return
        if external_kind in ("title", "basic"):
            # title: the typed text IS the row; basics: the provider looks for it itself
            provider = self.title_provider if external_kind == "title" else self.basic_provider
            self.rows = provider(rest) if provider else []
            self.showing_external = True
            self.query = ""
            self.visible = list(range(len(self.rows)))
            self.endResetModel()
            return
        if external_kind:
            self.rows = self.external_provider(external_kind) if self.external_provider else []
            self.showing_external = True
        elif special == "recent":
            order = self.recent_provider() if self.recent_provider else []
            extra = [item for kind, item in order if kind == "ext"]
            self.rows = self.clip_rows + extra
            self.showing_external = False
            recent_candidates, ext_i = [], len(self.clip_rows)
            for kind, item in order:
                if kind == "clip":
                    recent_candidates.append(item)
                else:
                    recent_candidates.append(ext_i)
                    ext_i += 1
        elif special in ("unused", "used", "like", "missing", "duplicate", "clipping"):
            self.rows = self.clip_rows
            self.showing_external = False
        elif special == "favorite":
            # starred clips plus starred scripts/macros/comps/projects (appended
            # after the clips, so clip row indices stay the same)
            extra = self.favorite_external_provider() if self.favorite_external_provider else []
            self.rows = self.clip_rows + extra
            self.showing_external = False
        elif category or special:
            self.rows = self.clip_rows
            self.showing_external = False
        else:
            self.rows = (self.default_view_provider() if self.default_view_provider else self.clip_rows)
            self.showing_external = False

        if special == "recent":
            candidates = recent_candidates
        elif special == "unused":
            candidates = sorted(self.unused_provider() if self.unused_provider else [],
                                key=lambda i: self.rows[i].name.lower())
        elif special == "used":
            counts = self.used_provider() if self.used_provider else []
            candidates = [i for i, _n in counts]
            self.info_override = {i: (f"{n}\u00d7 on this timeline" if n > 1 else "once on this timeline")
                                  for i, n in counts}
        elif special == "like":
            pairs = self.similar_provider(rest) if self.similar_provider else []
            candidates = [i for i, _pct in pairs]
            self.info_override = {i: ("the original" if pct is None else f"{pct}% alike") for i, pct in pairs}
            rest = ""  # the name is what to compare with, not a filter
        elif special in ("missing", "duplicate", "clipping"):  # the project check-up's lists
            pairs = self.checkup_provider(special) if self.checkup_provider else []
            candidates = [i for i, _why in pairs]
            self.info_override = dict(pairs)
        elif special == "staged":
            # staging order, not row order — first staged, first shown
            candidates = [i for i in self.staged if i < len(self.rows)]
        elif special == "selected":
            candidates = [i for i, row in enumerate(self.rows) if row.category == "selected"]
        elif special == "favorite":
            candidates = [i for i, row in enumerate(self.rows) if row.favorited]
        elif special in ("music", "sfx"):
            want = special == "music"
            # not analysed yet (None): in both, so nothing goes missing
            candidates = [i for i, row in enumerate(self.rows) if row.category == "audio"
                          and (getattr(row, "music", False) is None or bool(row.music) == want)]
        elif category:
            candidates = [i for i, row in enumerate(self.rows) if row.category == category]
        else:
            candidates = list(range(len(self.rows)))
            if self.page_hides:  # a prefix (a: ...) still reaches them
                hides = self.page_hides
                candidates = [i for i in candidates if self.rows[i].category not in hides]

        rest, candidates = self._by_energy(rest, candidates)
        self.query = rest
        if rest:
            scored = []
            score = scorer(rest)
            rows = self.rows
            folder_scores, not_yet = {}, object()  # many clips share a bin: its name is scored once
            for orig_index in candidates:
                row = rows[orig_index]
                best = score(row.name)
                folders = row.folder_list
                if folders:
                    folder_score = folder_scores.get(folders, not_yet)
                    if folder_score is not_yet:
                        folder_score = score(folders)
                        if folder_score is not None:
                            folder_score *= 0.6  # a match in the bin / category name counts, below one in the name
                        folder_scores[folders] = folder_score
                    if folder_score is not None and (best is None or folder_score > best):
                        best = folder_score
                tags = f"{row.tags} {row.extra_tags} {' '.join(row.file_tags)}".strip() \
                    if (row.tags or row.extra_tags or row.file_tags) else ""
                if tags:
                    # keywords / comments / clip colour count too ("whoosh dark", "teal"),
                    # a little below a match in the name itself
                    tag_score = score(f"{row.name} {tags}")
                    if tag_score is not None:
                        tag_score *= 0.7
                        best = tag_score if best is None else max(best, tag_score)
                if best is not None:
                    scored.append((best, orig_index))
            mode = self.settings.general.get("result_order", "best")
            learned = picks.boosts(rest) if mode == "best" and self.settings.general.get("learn_picks", True) else {}
            if mode == "used":  # most-used first, then best match
                scored.sort(key=lambda t: (-self.insert_frequency.get(self.rows[t[1]].name, 0), -t[0], t[1]))
            elif mode == "name":
                scored.sort(key=lambda t: (self.rows[t[1]].name.lower(), t[1]))
            else:  # best match - what you use often gets a small nudge, enough to break near-ties
                import math
                nudge = {i: min(6.0, 2.5 * math.log1p(self.insert_frequency.get(self.rows[i].name, 0)))
                         + (FAVOURITE_FIRST if self.rows[i].favorited else 0.0)  # a starred one: ahead of its equals
                         for _sc, i in scored}
                if learned:  # ...and what you picked for this text before, a big one (picks.py)
                    for _sc, i in scored:
                        nudge[i] += learned.get(picks.key_for(self.rows[i]), 0.0)
                scored.sort(key=lambda t: (-(t[0] + nudge[t[1]]), t[1]))
            self.visible = [i for _, i in scored]
            if not (category or special or external_kind) and self.search_actions_provider \
                    and self.settings.general.get("actions_in_search", True):
                extra = self.search_actions_provider(rest)
                # ...never one that's there already: Clipse's own scripts are in the list as their actions (scripts
                # on the Fusion page) - "Before / after" showed twice (2026-10-22)
                there = {(self.rows[i].category, self.rows[i].path) for i in self.visible
                         if self.rows[i].category == "action"}
                extra = [row for row in extra if (row.category, row.path) not in there]
                if extra:  # after the best few clips, so Enter still inserts the clip you typed
                    # (first, once you've picked the action for this text a couple of times)
                    extra.sort(key=lambda row: -learned.get(picks.key_for(row), 0.0))
                    start = len(self.rows)
                    self.rows = list(self.rows) + extra
                    at = 0 if learned.get(picks.key_for(extra[0]), 0.0) >= 20 else min(3, len(self.visible))
                    self.visible = self.visible[:at] + list(range(start, start + len(extra))) + self.visible[at:]
        elif category or special in ("selected", "favorite", "music", "sfx") or external_kind:
            if external_kind:
                self.visible = candidates
            elif self.settings.general["sort_by_insert_frequency"]:
                self.visible = self._nothing_typed(candidates)
            else:
                self.visible = candidates
        elif special in ("staged", "recent", "unused", "used", "like", "missing", "duplicate", "clipping"):
            self.visible = candidates  # staging / recency / name order — frequency sort would defeat the point
        else:
            if self.settings.general["sort_by_insert_frequency"]:
                self.visible = self._nothing_typed(candidates)
            else:
                self.visible = list(candidates)
        self.endResetModel()

    def _nothing_typed(self, candidates):
        """The order with nothing typed (Settings > General, With nothing typed): most used first, recently added
        to the Media Pool, or recently used (the r: list's order) - the rest after them as they were."""
        mode = self.settings.general.get("empty_order", "used")
        if mode == "added":
            # only Media Pool clips have a date: they're put in order in the places clips had - on the Fusion
            # page the macros and nodes stay above them
            slots = [n for n, i in enumerate(candidates) if getattr(self.rows[i], "added", 0.0)]
            newest = sorted((candidates[n] for n in slots), key=lambda i: -self.rows[i].added)
            out = list(candidates)
            for n, i in zip(slots, newest):
                out[n] = i
            return out
        if mode == "recent":
            from .resolve_client import load_recent
            rank = {}
            for n, key in enumerate(load_recent()):  # (newest first)
                rank.setdefault(key, n)
            last = len(rank)

            def when(i):
                row = self.rows[i]
                own = rank.get(f"{row.category}:{row.path or row.name}")  # a script, macro ... by its file
                if own is None and row.path is None:  # a Media Pool clip: by its name
                    own = rank.get(row.name)
                return last if own is None else own
            return sorted(candidates, key=when)
        return sorted(candidates, key=lambda i: -self.insert_frequency.get(self.rows[i].name, 0))

    def toggle_staged(self, orig_index):
        if orig_index in self.staged:
            del self.staged[orig_index]
        else:
            self.staged[orig_index] = 1

    def increment_staged(self, orig_index):
        self.staged[orig_index] = self.staged.get(orig_index, 0) + 1

    def decrement_staged(self, orig_index):
        if orig_index not in self.staged:
            return
        if self.staged[orig_index] <= 1:
            del self.staged[orig_index]
        else:
            self.staged[orig_index] -= 1

    def clear_staged(self):
        self.staged = {}
        self.chain = []

    def chain_positions(self, row):
        """Where a node / macro row sits in the staged chain: [1, 3] = 1st and 3rd."""
        key = f"{row.category}:{row.path or row.name}"
        return [n + 1 for n, entry in enumerate(self.chain) if entry["key"] == key]

    # -- QAbstractListModel interface --
    def rowCount(self, parent=QModelIndex()):
        return len(self.visible)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        orig_index = self.visible[index.row()]
        if role == ROLE_ORIG_INDEX:
            return orig_index
        if role == Qt.DisplayRole:
            return self.rows[orig_index].name
        return None


# How much a star is worth in a search (scores run from about 10, a loose match, to about 65, the
# name itself): a favourite comes before others that match about as well, not before a far better match.
FAVOURITE_FIRST = 14.0

# Resolve's clip colours (right-click a clip -> Clip Color)
CLIP_COLORS = {
    "Orange": "#e8812a", "Apricot": "#f2a65a", "Yellow": "#e3c341", "Lime": "#a2c83f", "Olive": "#6b9a35",
    "Green": "#3fa35b", "Teal": "#2aa198", "Navy": "#36608f", "Blue": "#4a8fd6", "Purple": "#8c62c4",
    "Violet": "#c35fc0", "Pink": "#e573a8", "Tan": "#c6a67c", "Beige": "#dccaa6", "Brown": "#9b6b40",
    "Chocolate": "#734d30",
}


class RowHover(QObject):
    """The row under the mouse gets a faint highlight - but only once the
    mouse has really moved (as Vicinae does it): a list that appears or
    changes under a resting mouse doesn't light a row up by itself."""

    def __init__(self, view, delegate):
        super().__init__(view)
        self.view, self.delegate = view, delegate
        view.viewport().setMouseTracking(True)
        view.viewport().installEventFilter(self)
        view.model().modelReset.connect(self.clear)

    def clear(self):
        self._set(None)

    def _set(self, row):
        if row != self.delegate.hover_row:
            self.delegate.hover_row = row
            self.view.viewport().update()

    def eventFilter(self, obj, event):
        kind = event.type()
        if kind == QEvent.MouseMove:
            index = self.view.indexAt(event.position().toPoint())
            self._set(index.row() if index.isValid() else None)
        elif kind in (QEvent.Leave, QEvent.Hide, QEvent.Wheel):
            self._set(None)  # (scrolling moves the rows, not the mouse)
        return False


class ClipItemDelegate(QStyledItemDelegate):
    """Paints one row:  [tag]  name ........ bin            [staged] [star]

    The tag is a small tinted box in the clip type's colour holding its
    symbol (see symbols.py). Matched letters of the search are drawn in
    the accent colour. Bins line up in a column at 60% of the width (or
    right-aligned, Settings -> General)."""

    TAG_ALPHA = 48       # tint of the tag box (0-255)
    BIN_COLUMN = 0.60    # where the bin column starts, as a share of the row width

    def __init__(self, model: ClipListModel, settings, parent=None):
        super().__init__(parent)
        self.model = model
        self.settings = settings
        self.hover_row = None  # the row under the mouse (set by RowHover), or None

    def _scale(self):
        from .fonts import picker_scale
        return picker_scale(self.settings)  # (the UI scale times the picker's zoom)

    def sizeHint(self, option, index):
        fm = QFontMetricsF(option.font)
        pad = self.settings.display["row_spacing"] * self._scale()
        return QSize(option.rect.width(), int(round(fm.height() + 2 * pad)))

    @staticmethod
    def _baseline(rect, fm):
        return rect.center().y() + (fm.ascent() - fm.descent()) / 2 + 0.5

    def paint(self, painter, option, index):
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)
        orig_index = index.data(ROLE_ORIG_INDEX)
        row = self.model.rows[orig_index]
        t = self.settings.theme
        scale = self._scale()
        rect = QRectF(option.rect)
        selected = bool(option.state & QStyle.State_Selected)

        # a soft, well-rounded highlight (a row's corners: look.radius "tile") -
        # full strength on the selected row, faint under the mouse
        if selected or index.row() == self.hover_row:
            from . import look
            radius = min(look.radius(self.settings, "tile") * scale, rect.height() / 2)
            fill = QColor(t["picker_select_bg"])
            if not selected:
                fill.setAlphaF(0.42)
            painter.setPen(Qt.NoPen)
            painter.setBrush(fill)
            painter.drawRoundedRect(rect.adjusted(0, 0.5, 0, -0.5), radius, radius)

        name_font = QFont(option.font)
        fm = QFontMetricsF(name_font)

        # -- tag with the clip type's symbol
        color = QColor(self.settings.icon_color(row.category))
        if row.category == "prefix" and getattr(row, "color", ""):  # the : menu: each kind in its own colour
            color = QColor(row.color)
        if row.category == "marker" and getattr(row, "color", ""):  # a marker's tag in its own colour
            from .presets import MARKER_HEX
            color = QColor(MARKER_HEX.get(row.color, color.name()))
        tag_h = round(fm.height() * 0.95 + self.settings.display["icon_size_offset"])
        tag_w = round(tag_h * 1.38)
        # a narrow column in front of the tag holds the staged tick, so tags line up
        tick_col = QRectF(rect.left() + round(6 * scale), rect.top(), round(tag_h * 1.3), rect.height())
        tag = QRectF(tick_col.right() + round(3 * scale), rect.center().y() - tag_h / 2, tag_w, tag_h)
        symbol_color = self._paint_tag(painter, tag, color)
        custom_icon = self.settings.icons.get(row.category)
        if custom_icon and custom_icon != ICON_DEFAULTS.get(row.category):
            icon_font = QFont(name_font)
            icon_font.setPixelSize(max(6, int(tag_h * 0.72)))
            painter.setFont(icon_font)
            painter.setPen(symbol_color)
            painter.drawText(tag, Qt.AlignCenter, custom_icon)
        else:
            symbol = row.category
            if symbol == "audio" and self.settings.listen.get("split_music", True):
                music = getattr(row, "music", False)
                symbol = "audio" if music is None else "music" if music else "sound"  # None: not analysed yet
            if symbol == "action" and getattr(row, "glyph", None):  # each action its own line icon
                from .glyphs import draw_glyph
                draw_glyph(painter, row.glyph, tag.center(), tag_h * 0.78, symbol_color)
            elif symbol == "title" and getattr(row, "glyph", None):  # (the Solid colour row)
                draw_symbol(painter, row.glyph, tag.center(), tag_h * 0.68, symbol_color)
            elif symbol == "prefix" and getattr(row, "glyph", None):  # the : menu: the kind's symbol ("g:" a line icon)
                if row.glyph.startswith("g:"):
                    from .glyphs import draw_glyph
                    draw_glyph(painter, row.glyph[2:], tag.center(), tag_h * 0.78, symbol_color)
                else:
                    draw_symbol(painter, row.glyph, tag.center(), tag_h * 0.68, symbol_color)
            else:
                draw_symbol(painter, symbol, tag.center(), tag_h * 0.68, symbol_color)

        # -- right-hand markers (star, staged count), reserved first so text never runs under them
        right = rect.right() - round(12 * scale)
        gap = round(10 * scale)
        dot_color = CLIP_COLORS.get(getattr(row, "color", "") or "") if self.settings.general.get(
            "show_clip_color", True) else None
        show_bin = bool(row.info_segments) or bool(dot_color) or orig_index in self.model.info_override or (
            row.folder_list and self.settings.general["show_folder_names"])
        right_aligned_bin = self.settings.general["right_align_folder_names"] and not row.info_segments
        far_bin = None
        if show_bin and right_aligned_bin:  # the bin (and its clip colour dot) at the very right, the symbols before it
            bin_font = font_at(SMALL, option.font)
            bfm = QFontMetricsF(bin_font)
            folder_text = row.folder_list if self.settings.general["show_folder_names"] else ""
            override = self.model.info_override.get(orig_index)
            if override:
                folder_text, dot_color = override, None
            dot_r = bfm.height() * 0.2
            dot_w = (2 * dot_r + 7 * scale) if dot_color else 0
            text = bfm.elidedText(folder_text, Qt.ElideLeft, max(0.0, rect.width() * 0.35 - dot_w))
            width = bfm.horizontalAdvance(text) + dot_w
            far_bin = (text, right - width, dot_r)
            if width:
                right -= width + gap
        if row.favorited:
            fav = self.settings.icons["favorite_marker"]
            star_color = QColor(t["favorite_marker_color"])
            if fav != ICON_DEFAULTS["favorite_marker"]:
                painter.setFont(name_font)
                painter.setPen(star_color)
                w = fm.horizontalAdvance(fav)
                painter.drawText(QPointF(right - w, self._baseline(rect, fm)), fav)
                right -= w + gap
            else:
                size = tag_h * 0.66
                draw_star(painter, QRectF(right - size, rect.center().y() - size / 2, size, size),
                          star_color, self.STAR_STYLE)
                right -= size + gap
        if row.category in ("action", "script"):  # a script: the red symbol, as in the Actions panel - the app's own
            from .settings import RESOLVE_KEYED       # in Resolve's menu, and every other one (2026-10-17)
            if row.category == "script" or row.name in RESOLVE_KEYED:
                from .actions_panel import script_red
                from .glyphs import draw_glyph
                size = tag_h * 0.7
                draw_glyph(painter, "scripts", QPointF(right - size / 2, rect.center().y()), size, script_red(t))
                right -= size + gap
        positions = self.model.chain_positions(row) if row.category in ("node", "macro") else []
        if positions:
            # its place(s) in the chain, small on the right: "1st", "2nd and 4th" -> "1", "2 · 4"
            count, count_text = 1, ""
            order = font_at(TINY, name_font, QFont.DemiBold)
            painter.setFont(order)
            painter.setPen(QColor(t["staged_marker_color"]))
            text = " \u00b7 ".join(str(p) for p in positions)
            w = QFontMetricsF(order).horizontalAdvance(text)
            painter.drawText(QRectF(right - w, rect.top(), w, rect.height()), Qt.AlignRight | Qt.AlignVCenter, text)
            right -= w + gap
        else:
            count = 0 if self.model.showing_external else self.model.staged.get(orig_index, 0)
            count_text = str(count)
        if count:  # staged tick in front of the tag, "2", "3"... next to it when staged more than once
            staged_color = QColor(t["staged_marker_color"])
            size = tag_h * 0.56
            marker = self.settings.icons.get("staged_marker")
            if marker and marker != ICON_DEFAULTS["staged_marker"]:  # custom staged icon from Settings
                painter.setFont(name_font)
                painter.setPen(staged_color)
                painter.drawText(QRectF(tick_col.left(), rect.top(), size * 1.4, rect.height()),
                                 Qt.AlignLeft | Qt.AlignVCenter, marker)
            else:
                draw_check(painter, QRectF(tick_col.left(), rect.center().y() - size / 2, size, size), staged_color)
            if count > 1:
                small = font_at(TINY, name_font, QFont.DemiBold)
                sfm = QFontMetricsF(small)
                painter.setFont(small)
                painter.setPen(staged_color)
                painter.drawText(QPointF(tick_col.left() + size + 1 * scale, rect.center().y() + sfm.ascent() * 0.3),
                                 count_text)

        # -- name, with the matched letters in the accent colour
        name_x = tag.right() + round(10 * scale)
        bin_x = rect.left() + rect.width() * self.BIN_COLUMN
        name_limit = (bin_x - round(14 * scale)) if (show_bin and not right_aligned_bin) else right
        if selected:
            name_font.setWeight(QFont.Medium)
        # music: its tempo, small, right after the name ("128 BPM")
        bpm = getattr(row, "bpm", None) if row.category == "audio" else None
        bpm_text = f"{round(bpm)} BPM" if bpm and self.settings.listen.get("show_bpm", True) else ""
        bpm_font = font_at(SMALL, option.font)
        bpm_gap = round(9 * scale)
        bpm_w = (QFontMetricsF(bpm_font).horizontalAdvance(bpm_text) + bpm_gap) if bpm_text else 0
        energy, guessed = shown_energy(row, self.settings) if row.category == "audio" else (0, False)
        bars_w = (ENERGY_BARS_WIDTH * scale + bpm_gap) if energy else 0
        name_end = self._draw_name(painter, row.name, name_font, QPointF(name_x, self._baseline(rect, fm)),
                                   name_limit - name_x - bpm_w - bars_w, QColor(t["picker_text"]),
                                   QColor(t.get("picker_accent", t["color_video"])))
        if energy and name_limit - name_x > bars_w + 20 * scale:
            draw_energy(painter, name_end + bpm_gap, rect.center().y(), scale, energy, not guessed, t, hollow=guessed)
            name_end += bars_w
        if bpm_text and name_limit - name_x > bpm_w + bars_w + 20 * scale:
            painter.setFont(bpm_font)
            painter.setPen(QColor(t["picker_folder"]))
            painter.drawText(QPointF(name_end + bpm_gap, self._baseline(rect, QFontMetricsF(bpm_font))), bpm_text)

        # -- bin column (or the project's created/modified info)
        if far_bin is not None:  # right-aligned: where it was kept room for, at the very right
            text, x, dot_r = far_bin
            painter.setFont(bin_font)
            painter.setPen(QColor(t["picker_folder"]))
            painter.drawText(QPointF(x, self._baseline(rect, bfm)), text)
            if dot_color:
                painter.save()
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor(dot_color))
                painter.drawEllipse(QPointF(rect.right() - round(12 * scale) - dot_r, rect.center().y()), dot_r, dot_r)
                painter.restore()
        elif show_bin:
            bin_font = font_at(SMALL, option.font)
            bfm = QFontMetricsF(bin_font)
            painter.setFont(bin_font)
            base = self._baseline(rect, bfm)
            if row.info_segments:
                age_colors = {"recent": t["age_recent_color"], "medium": t["age_medium_color"],
                              "old": t["age_old_color"], None: t["picker_folder"]}
                x = bin_x
                for text, color_key in row.info_segments:
                    painter.setPen(QColor(age_colors.get(color_key, t["picker_folder"])))
                    painter.drawText(QPointF(x, base), text)
                    x += bfm.horizontalAdvance(text)
            else:
                folder_text = row.folder_list if self.settings.general["show_folder_names"] else ""
                override = self.model.info_override.get(orig_index)
                if override:
                    folder_text, dot_color = override, None
                dot_r = bfm.height() * 0.2
                dot_w = (2 * dot_r + 7 * scale) if dot_color else 0

                def dot(x):  # the clip colour from Resolve
                    painter.save()
                    painter.setPen(Qt.NoPen)
                    painter.setBrush(QColor(dot_color))
                    painter.drawEllipse(QPointF(x + dot_r, rect.center().y()), dot_r, dot_r)
                    painter.restore()

                painter.setPen(QColor(t["picker_folder"]))
                # bin, then the dot right after it
                text = bfm.elidedText(folder_text, Qt.ElideRight, max(0, right - bin_x - dot_w))
                painter.drawText(QPointF(bin_x, base), text)
                if dot_color:
                    gap = 7 * scale if text else 0
                    dot(bin_x + bfm.horizontalAdvance(text) + gap)

        painter.restore()

    TAG_STYLE = "tint"          # "tint" | "solid" | "gradient"
    STAR_STYLE = "fill"         # favourite marker: "fill" | "line" | "dot"
    SOLID_SYMBOL = "#ffffff"    # symbol colour on solid tags

    def _paint_tag(self, painter, tag, color):
        """Draws the tag box; returns the colour to draw its symbol in."""
        radius = max(2.0, tag.height() * 0.24)
        painter.setPen(Qt.NoPen)
        if self.TAG_STYLE == "tint":
            tint = QColor(color)
            tint.setAlpha(self.TAG_ALPHA)
            painter.setBrush(tint)
            painter.drawRoundedRect(tag, radius, radius)
            return color
        if self.TAG_STYLE == "gradient":
            grad = QLinearGradient(tag.topLeft(), tag.bottomLeft())
            grad.setColorAt(0, color.lighter(118))
            grad.setColorAt(1, color.darker(112))
            painter.setBrush(grad)
        else:
            painter.setBrush(color)
        painter.drawRoundedRect(tag, radius, radius)
        return QColor(self.SOLID_SYMBOL)

    def _draw_name(self, painter, name, font, pos, max_width, color, accent):
        fm = QFontMetricsF(font)
        shown = fm.elidedText(name, Qt.ElideRight, max(0, max_width))
        hits = match_positions(self.model.query, name) if self.model.query else set()
        if not hits:
            painter.setFont(font)
            painter.setPen(color)
            painter.drawText(pos, shown)
            return pos.x() + fm.horizontalAdvance(shown)
        hit_font = QFont(font)
        hit_font.setWeight(QFont.DemiBold)
        elided = shown != name  # then the last character is the "..."

        def is_hit(k):
            return k in hits and not (elided and k == len(shown) - 1)

        x, i = pos.x(), 0
        while i < len(shown):
            hit = is_hit(i)
            j = i + 1
            while j < len(shown) and is_hit(j) == hit:
                j += 1
            seg = shown[i:j]
            f = hit_font if hit else font
            painter.setFont(f)
            painter.setPen(accent if hit else color)
            painter.drawText(QPointF(x, pos.y()), seg)
            x += QFontMetricsF(f).horizontalAdvance(seg)
            i = j
        return x
