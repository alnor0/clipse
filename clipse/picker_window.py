"""The picker window itself. Built once, shown/hidden on trigger — same
"stay warm" model as the Tk daemon, just as a QWidget instead of a Tk
root that gets withdrawn/deiconified."""
import html as _html
import math
import platform
import random
import time

from PySide6.QtCore import Qt, QTimer, Signal, QObject, QItemSelection, QItemSelectionModel, QKeyCombination, QEvent
from PySide6.QtGui import (QKeySequence, QFont, QFontMetrics, QPainter, QPainterPath, QColor, QPen, QLinearGradient, QCursor)
from PySide6.QtCore import QRectF, QPointF, QSize, QRect, QPoint
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QListView, QLabel,
                                QApplication, QAbstractItemView)

from . import library
from . import resolve_client as rc
from . import scripts_fusion
from . import timeline_tools as tt
from .clip_model import ClipListModel, ClipItemDelegate, RowHover, ROLE_ORIG_INDEX
from . import stats
from .settings_dialog import SettingsDialog
from .settings import FUSION_SKIPPED_CATEGORIES
from .settings import ACTION_KEY_BY_LABEL, RESOLVE_KEYED
from .audio_preview import AudioPreview
from .video_preview import VideoPlayer, Scrubber, available as VideoPreviewAvailable
from .symbols import draw_symbol
from .glyphs import ACTION_GLYPH, GROUP_GLYPH
from .preview_menu import BarMenu, MenuRow, MenuRule, MenuTitle
from . import picks
from . import resolve_commands as commands
from . import fusion_animate
from . import fusion_expressions
from .settings import AUDIO_EXTENSIONS
from .insert_as_dialog import InsertAsDialog
from . import presets as presets_mod
from . import keycaps
from .history_dialog import HistoryDialog
from .theme import build_stylesheet

PICKER_WIDTH = 900
PICKER_HEIGHT = 500
SELECTION_ORDER_POLL_MS = 250
LIVE_COUNT_REFRESH_MS = 1500
EXTERNAL_ROW_CATEGORIES = {"script", "macro", "comp", "node", "expression", "project", "folder", "timeline", "marker",
                           "layout", "prefix", "title",
                           "template", "action", "shortcut"}
# Set CLIPSE_DEBUG_KEYS=1 when starting the daemon to print every
# key the picker receives — for diagnosing keybinds that "do nothing".
import os as _os
from .fonts import SMALL, TINY, TITLE, at as font_at  # (the one scale of sizes)
DEBUG_KEYS = _os.environ.get("CLIPSE_DEBUG_KEYS") == "1"


_MOD_MASK = Qt.ControlModifier | Qt.ShiftModifier | Qt.AltModifier | Qt.MetaModifier


def _pressed_combo(event):
    """The pressed key + only the four real modifiers. Some keyboard
    layouts/compositors (notably non-US layouts on Wayland) add extra
    modifier bits like GroupSwitchModifier or KeypadModifier to every key
    event, which made e.g. Ctrl+N fail to match a "Ctrl+N" binding."""
    return QKeyCombination(Qt.KeyboardModifiers(event.modifiers() & _MOD_MASK), Qt.Key(event.key()))


def _seq_matches(event, seq_str) -> bool:
    if not seq_str:
        return False
    seq = QKeySequence(seq_str)
    if seq.count() == 0:
        return False
    wanted = seq[0]
    pressed = _pressed_combo(event)
    if pressed.key() == wanted.key() and \
            (pressed.keyboardModifiers() & _MOD_MASK) == (wanted.keyboardModifiers() & _MOD_MASK):
        return True
    # Fallback: the original string comparison (keeps any edge cases like
    # Shift+Tab -> Backtab behaving exactly as before).
    combo = QKeySequence(event.keyCombination())
    return combo.toString(QKeySequence.PortableText) == seq.toString(QKeySequence.PortableText)


class SearchEdit(QLineEdit):
    """A QLineEdit that forwards the picker's action keys to the owning
    window instead of doing default focus-traversal (Tab) or newline
    (Return) behavior.

    A prefix typed (scripts:, mk: ...) becomes a pill at the start - "Scripts ×", like Raycast's scope - and the
    field holds what's typed after it. text() / setText() still speak in whole searches ("mk: intro"), so the rest
    of the picker reads and sets it as before; Backspace at the start or the × leaves the scope."""

    def __init__(self, window):
        super().__init__()
        self.window_ = window
        self.scope = None  # (the word typed, its kind, its name) while a prefix is a pill
        self._pill = self._pill_x = None  # where the pill and its × are drawn

    # -- whole searches in and out, the prefix as the pill --
    def _recognise(self, whole):
        """("mk", "marker", "Markers", rest) when `whole` starts with a prefix this picker knows - else None."""
        import re
        found = re.match(r"^\s*([A-Za-z]+):\s?(.*)$", whole or "", re.S)
        if not found:
            return None
        from .clip_model import _build_prefix_maps
        from .settings import PREFIX_TITLES
        word = found.group(1).lower()
        for prefixes in _build_prefix_maps(self.window_.settings):
            if word in prefixes:
                target = prefixes[word]
                return word, target, PREFIX_TITLES.get(target, target.title()), found.group(2)
        return None

    def text(self):
        rest = super().text()
        if self.scope is None:
            return rest
        return f"{self.scope[0]}: {rest}"

    def setText(self, whole):
        hit = self._recognise(whole)
        before = (self.scope, super().text())
        self.scope = hit[:3] if hit else None
        super().setText(hit[3] if hit else (whole or ""))
        self._scope_changed(before)

    def clear(self):
        self.setText("")

    def take_prefix(self):
        """A prefix just typed into the field ("mk:") becomes the pill - called as the text changes."""
        if self.scope is not None:
            return
        hit = self._recognise(super().text())
        if hit:
            self.scope = hit[:3]
            self.blockSignals(True)
            super().setText(hit[3])
            self.blockSignals(False)
            self._scope_changed(None)

    def drop_scope(self):
        if self.scope is not None:
            before = (self.scope, super().text())
            self.scope = None
            self._scope_changed(before)

    def _scope_changed(self, before):
        """Room for the pill (or none), the placeholder, and - the field's own text unchanged - the search again."""
        from PySide6.QtGui import QFontMetricsF
        was = before[0] if before is not None else None
        if self.scope is None:
            self.setTextMargins(0, 0, 0, 0)
            if was is not None:
                self.setPlaceholderText(getattr(self, "_placeholder", "Search clips"))
        else:
            self.setTextMargins(int(self._pill_width(QFontMetricsF(self._pill_font())) + 10), 0, 0, 0)
            if self.placeholderText():
                self._placeholder = self.placeholderText()
            self.setPlaceholderText("")
        self.update()
        if before is not None and before[1] == super().text() and before[0] != self.scope:
            self.textChanged.emit(super().text())  # (the field didn't change, the scope did: search again)

    def _pill_font(self):
        return font_at(SMALL, self.font(), QFont.DemiBold)

    def _pill_width(self, fm):
        return fm.horizontalAdvance(self.scope[2]) + 14 + 18

    def paintEvent(self, ev):
        super().paintEvent(ev)
        if self.scope is None:
            return
        from PySide6.QtGui import QFontMetricsF, QPainter, QPen
        t = self.window_.settings.theme
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        font = self._pill_font()
        fm = QFontMetricsF(font)
        h = fm.height() + 8
        rect = QRectF(self.contentsRect().left() + 2, (self.height() - h) / 2, self._pill_width(fm), h)
        try:
            tint = QColor(self.window_.settings.icon_color(self.scope[1]))
        except KeyError:
            tint = QColor(t["picker_text"])
        back = QColor(tint)
        back.setAlphaF(0.18)
        p.setPen(Qt.NoPen)
        p.setBrush(back)
        p.drawRoundedRect(rect, 6, 6)
        p.setFont(font)
        p.setPen(QColor(t["picker_text"]))
        p.drawText(QRectF(rect.left() + 9, rect.top(), fm.horizontalAdvance(self.scope[2]) + 2, h),
                   Qt.AlignLeft | Qt.AlignVCenter, self.scope[2])
        x = QRectF(rect.right() - 16, rect.top(), 12, h)
        hover = x.adjusted(-3, 0, 3, 0).contains(self.mapFromGlobal(QCursor.pos()).toPointF()) if self.underMouse() else False
        colour = QColor(t["picker_text"] if hover else t["picker_folder"])
        p.setPen(QPen(colour, 1.3, Qt.SolidLine, Qt.RoundCap))
        cx, cy, k = x.center().x(), x.center().y(), 3.0
        p.drawLine(QPointF(cx - k, cy - k), QPointF(cx + k, cy + k))
        p.drawLine(QPointF(cx - k, cy + k), QPointF(cx + k, cy - k))
        p.end()
        self._pill, self._pill_x = rect, x.adjusted(-4, -2, 4, 2)

    def mousePressEvent(self, ev):
        if self.scope is not None and self._pill_x is not None and self._pill_x.contains(ev.position()):
            self.drop_scope()  # the pill's ×: out of the scope
            self.setFocus()
            return
        self.window_._set_in_list(False)  # a click in the search: typing again
        super().mousePressEvent(ev)

    def mouseMoveEvent(self, ev):
        if self.scope is not None:
            self.update()  # (the × lights under the mouse)
        super().mouseMoveEvent(ev)

    def event(self, ev):
        # Backspace at the very start (nothing chosen): out of the pill's scope, back to every kind
        if ev.type() == ev.Type.KeyPress and ev.key() == Qt.Key_Backspace and self.scope is not None \
                and self.cursorPosition() == 0 and not self.hasSelectedText() and ev.modifiers() == Qt.NoModifier:
            self.drop_scope()
            return True
        # Intercept Tab/Shift+Tab/Ctrl+Tab at the event() level — QWidget
        # normally steals these for focus traversal before keyPressEvent
        # ever sees them.
        if ev.type() == ev.Type.KeyPress:
            try:
                if self.window_.handle_action_key(ev):
                    return True
            except Exception:
                import traceback
                traceback.print_exc()
                return True
        return super().event(ev)

    def keyPressEvent(self, ev):
        if self.window_.handle_action_key(ev):
            return
        super().keyPressEvent(ev)

    def keyReleaseEvent(self, ev):
        self.window_.handle_key_release(ev)
        super().keyReleaseEvent(ev)


class ClickableLabel(QLabel):
    """A plain text label that acts like a link — used for the "Settings"
    / "Insert options" footer, replacing the old full keybind cheat-sheet
    text."""
    clicked = Signal()

    def __init__(self, text):
        super().__init__(text)
        self.setObjectName("FooterLink")
        self.setCursor(Qt.PointingHandCursor)

    def mousePressEvent(self, event):
        self.clicked.emit()


class FooterHints(QLabel):
    """The left of the bottom bar: what the main keys do, each key drawn as
    a small keycap (the way Vicinae shows shortcuts) - or, for a moment, a
    message in plain words (setText)."""

    def __init__(self, settings):
        super().__init__("")
        self.settings = settings
        self.hints = []  # [(key, what it does, an addition in the accent colour or "")]

    def set_hints(self, hints):
        self.hints = list(hints)
        super().setText("")
        self.updateGeometry()
        self.update()

    def setText(self, text):
        self.hints = []
        super().setText(text)
        self.updateGeometry()

    def text(self):
        if self.hints:
            return "   ".join(" ".join(part for part in hint if part) for hint in self.hints)
        return super().text()

    def sizeHint(self):
        if not self.hints:
            return super().sizeHint()
        from . import keycaps
        _cap_h, _pad, _gap, between = keycaps.sizes(self.font())
        total = sum(keycaps.width(self.font(), key, label, tail) for key, label, tail in self.hints)
        return QSize(int(total + between * (len(self.hints) - 1) + 2), int(keycaps.sizes(self.font())[0] + 2))

    minimumSizeHint = sizeHint

    def paintEvent(self, event):
        if not self.hints:
            return super().paintEvent(event)
        from . import keycaps
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        x, cy = 0.5, self.height() / 2
        for key, label, tail in self.hints:
            x = keycaps.draw(p, x, cy, key, label, self.font(), self.settings.theme, tail)
        p.end()


def _fmt_time(sec, tenths=False):
    if tenths:
        sec = max(0.0, sec)
        return f"{int(sec // 60)}:{sec % 60:04.1f}"
    sec = max(0, int(sec))
    return f"{sec // 60}:{sec % 60:02d}"


# Framing guides for the preview (the Guides menu in its bar): key -> label
GUIDES = [
    ("16:9", "16:9 - YouTube, a 16:9 timeline"),
    ("9:16", "9:16 - Shorts, Reels, TikTok"),
    ("4:5", "4:5 - Instagram portrait"),
    ("1:1", "1:1 - Square"),
    ("2.39:1", "2.39:1 - Cinema"),
    ("thirds", "Rule of thirds"),
    ("centre", "Centre"),
]
from .guides_popup import RATIOS as _RATIOS  # (the guides' shapes: one list)


def _paint_guides(p, target, guides, theme):
    """Draws the chosen guides over the picture in `target`. A crop guide
    dims what falls outside it; with several, the narrowest dims and the
    others are outlined."""
    p.save()
    line = QColor(255, 255, 255, 150)
    faint = QColor(255, 255, 255, 90)
    crops = []
    for key in guides:
        r = _RATIOS.get(key)
        if r is None:
            continue
        if target.width() / target.height() > r:
            w, h = target.height() * r, target.height()
        else:
            w, h = target.width(), target.width() / r
        crops.append((w * h, key, QRectF(target.center().x() - w / 2, target.center().y() - h / 2, w, h)))
    crops.sort(key=lambda c: c[0])
    if crops:
        outside = QPainterPath()
        outside.addRect(target)
        inner = QPainterPath()
        inner.addRect(crops[0][2])
        p.fillPath(outside.subtracted(inner), QColor(0, 0, 0, 120))
    small = font_at(TINY, p.font())
    p.setFont(small)
    for _area, key, rect in crops:
        p.setPen(QPen(line, 1.0))
        p.setBrush(Qt.NoBrush)
        p.drawRect(rect.adjusted(0.5, 0.5, -0.5, -0.5))
        p.setPen(line)
        p.drawText(rect.adjusted(6, 4, -6, -4), Qt.AlignLeft | Qt.AlignTop, key)
    if "thirds" in guides:
        p.setPen(QPen(faint, 1.0))
        for i in (1, 2):
            x = target.left() + target.width() * i / 3
            y = target.top() + target.height() * i / 3
            p.drawLine(QPointF(x, target.top()), QPointF(x, target.bottom()))
            p.drawLine(QPointF(target.left(), y), QPointF(target.right(), y))
    if "centre" in guides:
        c = target.center()
        arm = max(6.0, min(target.width(), target.height()) * 0.03)
        p.setPen(QPen(line, 1.2))
        p.drawLine(QPointF(c.x() - arm, c.y()), QPointF(c.x() + arm, c.y()))
        p.drawLine(QPointF(c.x(), c.y() - arm), QPointF(c.x(), c.y() + arm))
    p.restore()


class PreviewCanvas(QWidget):
    """The picture part of the preview: the frame (or a symbol and a
    message), with the clip's name and a thin progress bar underneath.
    Click or drag on the bar (or a sound's waveform) to move through the
    clip; the in/out marks on the bar can be dragged too."""
    seek = Signal(float)              # seconds
    mark_moved = Signal(str, float)   # "in"/"out", seconds
    scrubbing = Signal(bool)          # hover scrub started (True) / ended (False)
    scrub_to = Signal(float)          # hover scrub: show the frame at these seconds (playback stays put)
    enlarge = Signal()                # double-click on the picture: the big view
    copy_code = Signal(str)           # the copy mark on an expression's code was clicked
    copy_setting = Signal(str)        # a node's setting was clicked (Merge1.Size) - Expressions is open
    flip_node = Signal(int)           # ...or the previous (-1) / next (+1) node arrow
    entered = Signal()                # the mouse came onto the preview - get scrub frames ready

    def __init__(self, settings):
        super().__init__()
        self.settings = settings
        self.mark_in = None   # seconds, or None
        self.mark_out = None
        self.dragging = None  # None, "seek", "in" or "out"
        self._wave_span = None  # x range the waveform bars cover
        self.setMouseTracking(True)
        self.image = None
        self.position = 0.0
        self.duration = 0.0
        self.title = ""
        self.message = ""
        self.category = None
        self.peaks = None  # a sound's waveform (0..1 per slice), or None
        self.clipped = None  # per slice of the waveform: does the sound clip there? (None: nowhere)
        self.beats = None  # music: (bpm, seconds to the first beat) - the beat grid behind the waveform
        self.loop = None   # music: (start s, end s, bars) of its clean loop - a bracket over the waveform
        self.waiting = False  # a sound's waveform is on its way - don't flash the symbol first
        self.symbol = None    # a symbol of its own, not its category's (a Basics row)
        self.graph = None     # a macro's / comp's nodes (fusion_graph.py), drawn instead of a picture
        self.card = None      # an expression (fusion_expressions.py): what it does, drawn, and its code
        self.node_view = None  # while Expressions is open: the node and its settings (node_settings.NodeView)
        self.card_values = {}  # expression key -> {slider id: number}: where you've put its sliders
        self._card_sliders = []  # [(slider, the rect its track is drawn in)] of the card on show
        self._card_drag = None   # the slider being dragged
        self._card_copy = QRectF()  # the copy mark on the card's code, as painted
        self._card_copied = 0.0     # when it was last clicked (a tick shows for a moment)
        self._card_stage = QRectF()  # the demonstration's frame (a click starts it over)
        self.used = []        # parts of the clip on the timeline already: [(start s, end s)] (timeline_tools.UsedParts)
        self.used_times = 0   # ...and how many times it's used there
        self.scrub_x = None   # hover scrub: where the mouse is over the picture
        self._picture = None  # where the picture itself is drawn (not the empty space above / beside it)
        self.scrub_image = None  # ...and the frame shown there (the playing frame stays in self.image)
        self.scrub_seconds = 0.0
        self.guides = []      # framing guides drawn over the picture (see GUIDES)
        self.time_text = None  # seconds -> timecode text, or None for m:ss.t

    def image_area(self):
        pad = 12
        below = 10 + 3 + 8 + QFontMetrics(self.font()).height() + 8  # progress bar + name
        return QRectF(pad, pad, self.width() - 2 * pad, self.height() - pad - below)

    def paintEvent(self, event):
        t = self.settings.theme
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        area = self.image_area()
        from . import look
        radius = look.radius(self.settings, "control")
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(t.get("picker_bar_bg", t["picker_bg"])))
        p.drawRoundedRect(area, radius, radius)
        muted = QColor(t["picker_folder"])
        if self.node_view is not None:  # Expressions is open: the node and what its settings are called
            full = QRectF(12, 12, self.width() - 24, self.height() - 24)
            p.drawRoundedRect(full, radius, radius)
            self.node_view.paint(p, full, self.settings, self.font())
            p.end()
            return
        if self.card:  # an expression: what it does over four seconds, and the code
            self._paint_card(p, area)
            p.end()
            return
        if self.graph:  # a macro / comp: its nodes (nothing from a clip played before counts)
            from . import fusion_graph
            try:
                fusion_graph.draw(p, area, self.graph, self.settings, self.font())
            except Exception as e:
                print(f"[preview] couldn't draw the nodes: {e}")
                self.graph = None
        elif self.image is not None and not self.image.isNull():
            img = self.scrub_image if self.scrub_x is not None and self.scrub_image is not None else self.image
            scale = min(area.width() / img.width(), area.height() / img.height())
            w, h = img.width() * scale, img.height() * scale
            target = QRectF(area.center().x() - w / 2, area.center().y() - h / 2, w, h)
            self._picture = target
            clip = QPainterPath()
            clip.addRoundedRect(target, radius, radius)
            p.save()
            p.setClipPath(clip)
            p.drawImage(target, img)
            if self.guides:
                _paint_guides(p, target, self.guides, t)
            if self.scrub_x is not None:  # hover scrub: a hairline where you are
                line = QColor(t["picker_text"])
                line.setAlphaF(0.55)
                p.setPen(QPen(line, 1.0))
                p.drawLine(QPointF(self.scrub_x, target.top()), QPointF(self.scrub_x, target.bottom()))
                p.setPen(Qt.NoPen)
            p.restore()
        elif self.peaks:
            self._paint_waveform(p, area)
        else:
            if self.category and (self.message or not self.waiting):
                size = min(area.width(), area.height()) * 0.18
                draw_symbol(p, self.symbol or self.category, area.center(), size,
                            QColor(self.settings.icon_color(self.category)))
            if self.message:
                p.setPen(muted)
                p.drawText(area.adjusted(12, area.height() * 0.62, -12, 0), Qt.AlignHCenter | Qt.AlignTop | Qt.TextWordWrap,
                           self.message)
        # progress bar (with in/out and a handle) and the name underneath
        bottom = area.bottom() + 10
        if self.duration > 0:
            bar = self.bar_rect()
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(t["picker_border"]))
            p.drawRoundedRect(bar, 1.5, 1.5)
            x_in, x_out = self._marked_span(bar.left(), bar.right())
            marked = self.mark_in is not None or self.mark_out is not None
            p.setBrush(QColor(t["picker_text"]))
            x_pos = bar.left() + bar.width() * min(1.0, self.position / self.duration)
            p.drawRoundedRect(QRectF(bar.left(), bar.top(), x_pos - bar.left(), bar.height()), 1.5, 1.5)
            if marked:  # the in-to-out part, in the accent colour
                accent = QColor(t.get("picker_accent", t["picker_text"]))
                band = QColor(accent)
                band.setAlphaF(0.75)
                p.setBrush(band)
                p.drawRect(QRectF(x_in, bar.top() - 1, x_out - x_in, bar.height() + 2))
            if marked:  # an upright tick at each end of the in-to-out part
                p.setBrush(accent)
                for x, mark in ((x_in, self.mark_in), (x_out, self.mark_out)):
                    if mark is not None:
                        p.drawRoundedRect(QRectF(x - 1, bar.top() - 5, 2, bar.height() + 10), 1, 1)
            p.setBrush(QColor(t["picker_text"]))
            knob = 4.5 if self.dragging == "seek" or self.underMouse() else 3.5
            p.drawEllipse(QPointF(x_pos, bar.center().y()), knob, knob)
        fm = QFontMetrics(self.font())
        fm_width = fm.horizontalAdvance
        p.setFont(self.font())
        p.setPen(QColor(t["picker_text"]))
        marks_text = ""
        if self.duration > 0 and (self.mark_in is not None or self.mark_out is not None):
            a = self.mark_in or 0.0
            b = self.mark_out if self.mark_out is not None else self.duration
            fmt = (lambda x: (self.time_text(x) if self.time_text else None) or _fmt_time(x, True))
            marks_text = f"In {fmt(a)}   Out {fmt(b)}"
            if fm_width(marks_text) > area.width() * 0.62:
                marks_text = f"{fmt(a)} \u2013 {fmt(b)}"  # narrow: just the two times
        used_text = ""
        if not marks_text and self.used_times and self.duration > 0:
            used_text = f"{self.used_times}\u00d7"  # on the timeline that many times (the bar stays as it is)
        marks_w = fm.horizontalAdvance(marks_text or used_text)
        if marks_text:
            p.setPen(QColor(t.get("picker_accent", t["picker_text"])))
            p.drawText(QPointF(area.right() - marks_w, bottom + 8 + fm.ascent()), marks_text)
            p.setPen(QColor(t["picker_text"]))
        elif used_text:
            p.setPen(muted)
            p.drawText(QPointF(area.right() - marks_w, bottom + 8 + fm.ascent()), used_text)
            p.setPen(QColor(t["picker_text"]))
        title = fm.elidedText(self.title, Qt.ElideRight, int(area.width() - marks_w - (12 if marks_w else 0)))
        p.drawText(QPointF(area.left(), bottom + 8 + fm.ascent()), title)
        p.end()

    def _card_time(self):
        """Where the demonstration is in its four second clip, in frames - it plays round and round."""
        from . import fusion_expressions as fx
        if not hasattr(self, "_card_clock"):
            from PySide6.QtCore import QElapsedTimer
            self._card_clock = QElapsedTimer()
            self._card_clock.start()
            self._card_tick = QTimer(self)
            self._card_tick.timeout.connect(lambda: self.update() if self.card and self.isVisible() else self._card_tick.stop())
        if not self._card_tick.isActive():
            self._card_tick.start(33)
        seconds = (self._card_clock.elapsed() / 1000.0) % ((fx.END - fx.START) / fx.FPS + 0.6)  # a short rest at the end
        return min(fx.END, fx.START + seconds * fx.FPS)

    def _paint_card(self, p, area):
        """An expression, explained and shown: its name, what it does, exactly
        which setting it goes on, then - as large as there's room for - a frame
        in which a sample picture really does it (moving, turning, growing,
        fading, or the text changing), a slider for each of its numbers (drag
        one and both the picture and the code follow), and the code."""
        from . import fusion_expressions as fx
        entry, t = self.card, self.settings.theme
        text, muted = QColor(t["picker_text"]), QColor(t["picker_folder"])
        accent = QColor(t.get("picker_accent", t["picker_text"]))
        font = QFont(self.font())
        small = font_at(SMALL, font)
        mono = QFont(small)
        from .fonts import mono_families
        mono.setFamilies(mono_families())
        for tag in ("calt", "liga"):  # code as it's typed: <= stays <=, not one joined sign
            mono.setFeature(QFont.Tag(tag), 0)
        sfm, mfm = QFontMetrics(small), QFontMetrics(mono)
        inner = QRectF(area).adjusted(16, 14, -16, -12)
        width = int(inner.width())
        words = Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap
        y = inner.top()
        numbers = self.card_numbers()
        code, yours = fx.code_parts(entry, numbers)

        def paragraph(content, a_font, metrics, color, gap=6):
            nonlocal y
            height = metrics.boundingRect(QRect(0, 0, width, 4000), words, content).height()
            p.setFont(a_font)
            p.setPen(color)
            p.drawText(QRectF(inner.left(), y, inner.width(), height + 2), words, content)
            y += height + gap

        title = QFont(font)
        title.setWeight(QFont.DemiBold)
        paragraph(entry["name"], title, QFontMetrics(title), text, 5)
        paragraph(entry["about"], small, sfm, text, 5)
        paragraph(fx.goes_on(entry), small, sfm, muted, 8)

        # From the bottom up: the code, the sliders over it; the demonstration gets the rest. It
        # comes first: the code has two lines (the bottom bar says how to copy all of it) and only
        # more once the demonstration is as large as the card is wide.
        slider_h = sfm.height() + 10.0
        sliders_h = slider_h * len(entry["params"]) + (4 if entry["params"] else 0)
        lines = fx.code_lines(code, max(8, int((width - 20 - 24) // max(1, mfm.horizontalAdvance("0")))))  # (24: the copy mark)
        code_lines = len(lines) * mfm.height()
        full_demo = inner.width() * 9 / 16 + 16
        room = inner.bottom() - y - sliders_h - 14 - 16 - full_demo  # what's left for code once the demonstration is full size
        code_h = min(code_lines, max(mfm.height() * 2, min(mfm.height() * 6, room))) + 16
        code_box = QRectF(inner.left(), inner.bottom() - code_h, inner.width(), code_h)
        sliders_top = code_box.top() - 8 - sliders_h
        stage = QRectF(inner.left(), y, inner.width(), max(0.0, sliders_top - 6 - y))
        if stage.height() > full_demo:  # room to spare: everything sits together under the demonstration
            spare = stage.height() - full_demo
            stage.setHeight(full_demo)
            sliders_top -= spare
            code_box.translate(0, -spare)
        self._card_stage = QRectF(stage)
        if stage.height() > 46:
            self._paint_demo(p, stage, entry, self._card_time(), numbers)

        from .expression_sheet import STAND_IN_DARK, STAND_IN_LIGHT
        from .settings import is_light
        stand_in = QColor(STAND_IN_LIGHT if is_light(t["picker_bg"]) else STAND_IN_DARK)
        self._card_sliders = []
        label_w = max([sfm.horizontalAdvance(param["label"]) for param in entry["params"]] + [0]) + 12
        def widest(param):  # as wide as its number can get, so the track doesn't move while it's dragged
            most = max(abs(param["low"]), abs(param["high"]))
            return ("-" if param["low"] < 0 else "") + "0" * len(str(int(most))) + ("" if param["whole"] else ".0000")
        value_w = max([sfm.horizontalAdvance(widest(param)) for param in entry["params"]] + [0]) + 8
        for k, param in enumerate(entry["params"]):  # a slider for each number: its name, the track, where it's at
            row = QRectF(inner.left(), sliders_top + k * slider_h, inner.width(), slider_h)
            track = QRectF(row.left() + label_w, row.center().y() - 1.5, max(20.0, row.width() - label_w - value_w - 6), 3)
            self._card_sliders.append((param, track))
            value = numbers[param["id"]]
            share = fx.slider_share(param, value)
            changed = value != param["default"]
            p.setFont(small)
            p.setPen(muted)
            p.drawText(QRectF(row.left(), row.top(), label_w, row.height()), Qt.AlignLeft | Qt.AlignVCenter, param["label"])
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(t["picker_border"]))
            p.drawRoundedRect(track, 1.5, 1.5)
            filled = QColor(text)
            filled.setAlphaF(0.72)
            p.setBrush(filled)
            p.drawRoundedRect(QRectF(track.left(), track.top(), track.width() * share, track.height()), 1.5, 1.5)
            if changed:  # where it started (a double click goes back there)
                home = track.left() + track.width() * fx.slider_share(param, param["default"])
                p.setBrush(muted)
                p.drawRoundedRect(QRectF(home - 0.75, track.top() - 3, 1.5, track.height() + 6), 0.75, 0.75)
            p.setBrush(text)
            knob = QPointF(track.left() + track.width() * share, track.center().y())
            p.drawEllipse(knob, 5.0 if self._card_drag and self._card_drag[0] is param else 4.2, 5.0 if self._card_drag and self._card_drag[0] is param else 4.2)
            p.setPen(stand_in)  # yours to change: in the code too, in the same green
            p.drawText(QRectF(row.right() - value_w, row.top(), value_w, row.height()), Qt.AlignRight | Qt.AlignVCenter,
                       fx._number(value))
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(t["picker_bg"]))
        p.drawRoundedRect(code_box, 6, 6)
        p.setFont(mono)
        p.setPen(text)
        p.save()
        p.setClipRect(code_box.adjusted(0, 0, 0, -6))
        # what's yours to change stands out: a slider's numbers in green (lit while its slider is under the mouse
        # or dragged), the node it reads on a pale chip - the cheat sheet's way; the rest is the formula
        lit = (self._card_drag or self._slider_at(QPointF(self.mapFromGlobal(QCursor.pos()))) or (None,))[0]
        node_chip, lit_chip = QColor(text), QColor(stand_in)
        node_chip.setAlphaF(0.12)
        lit_chip.setAlphaF(0.2)
        for k, (a, b) in enumerate(lines):
            top = code_box.top() + 8 + k * mfm.height()
            left = code_box.left() + 10
            for lo, hi, field in yours:
                lo, hi = max(lo, a), min(hi, b)
                if lo < hi and (field is None or (lit and field == lit["id"])):
                    p.setPen(Qt.NoPen)
                    p.setBrush(node_chip if field is None else lit_chip)
                    p.drawRoundedRect(QRectF(left + mfm.horizontalAdvance(code[a:lo]) - 2.5, top + 0.5,
                                             mfm.horizontalAdvance(code[lo:hi]) + 5, mfm.height() - 1), 3.5, 3.5)
            at = a
            for lo, hi, field in [s for s in yours if s[2] is not None] + [(b, b, "")]:
                lo, hi = max(lo, a), min(hi, b)
                if hi < lo or lo < at:
                    continue
                p.setPen(text)
                p.drawText(QPointF(left + mfm.horizontalAdvance(code[a:at]), top + mfm.ascent()), code[at:lo])
                if hi > lo:
                    p.setPen(stand_in)
                    p.drawText(QPointF(left + mfm.horizontalAdvance(code[a:lo]), top + mfm.ascent()), code[lo:hi])
                at = hi
        p.restore()
        if code_lines + 16 > code_h + 1:  # there's more of it than fits: fades out rather than stopping mid-line
            fade = QLinearGradient(0, code_box.bottom() - mfm.height() - 6, 0, code_box.bottom() - 4)
            clear = QColor(t["picker_bg"])
            clear.setAlpha(0)
            fade.setColorAt(0, clear)
            fade.setColorAt(1, QColor(t["picker_bg"]))
            p.setPen(Qt.NoPen)
            p.setBrush(fade)
            p.drawRoundedRect(QRectF(code_box.left(), code_box.bottom() - mfm.height() - 6, code_box.width(), mfm.height() + 6), 6, 6)
        # copy it: the mark in the corner of the code (a tick for a moment once it's copied)
        from .glyphs import draw_glyph
        self._card_copy = QRectF(code_box)  # a click anywhere on the code copies it
        just_copied = time.monotonic() - self._card_copied < 1.4
        over = self._card_copy.contains(QPointF(self.mapFromGlobal(QCursor.pos())))
        draw_glyph(p, "tick" if just_copied else "copy_code", QPointF(code_box.right() - 15, code_box.top() + 15), 14,
                   accent if just_copied else text if over else muted)
        if over and not just_copied:  # ...and the whole of it says so under the mouse
            edge = QColor(text)
            edge.setAlphaF(0.22)
            p.setPen(QPen(edge, 1))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(code_box.adjusted(0.5, 0.5, -0.5, -0.5), 6, 6)

    def _paint_demo(self, p, stage, entry, now, numbers=None):
        """A 16:9 frame, as large as `stage` lets it be, with a sample picture
        in it doing what the expression does at frame `now` - at its true
        size, so a wiggle of a hundredth of the frame looks as small as it will be."""
        from . import fusion_expressions as fx
        t = self.settings.theme
        text, muted = QColor(t["picker_text"]), QColor(t["picker_folder"])
        tone = QColor(text)  # the sample picture and what moves are in the text's own colour: no accent here
        tone.setAlphaF(0.86)
        side = min(stage.width() * 9 / 16, stage.height() - 8)
        frame = QRectF(stage.center().x() - side * 8 / 9, stage.top(), side * 16 / 9, side)
        clip = QPainterPath()
        clip.addRoundedRect(frame, 6, 6)
        p.save()
        p.setClipPath(clip)
        p.fillPath(clip, QColor(t["picker_bg"]))
        guide = QColor(t["picker_border"])
        guide.setAlphaF(0.6)
        p.setPen(QPen(guide, 1, Qt.DashLine))
        p.drawLine(QPointF(frame.center().x(), frame.top()), QPointF(frame.center().x(), frame.bottom()))
        p.drawLine(QPointF(frame.left(), frame.center().y()), QPointF(frame.right(), frame.center().y()))
        value = fx.value_at(entry, now, numbers)
        target = entry["target"]

        def spot(v):  # Fusion's 0..1 positions (0.5, 0.5 = the middle, up is up) in this frame
            return QPointF(frame.left() + v[0] * frame.width(), frame.bottom() - v[1] * frame.height())

        def picture(centre, size=1.0, angle=0.0, alpha=1.0, color=None, ghost=False):
            """The sample picture: a small card with a mountain on it."""
            w, h = frame.width() * 0.42 * size, frame.height() * 0.42 * size
            p.save()
            p.translate(centre)
            p.rotate(-angle)  # Fusion turns anticlockwise for a positive angle
            p.setOpacity(max(0.0, min(1.0, alpha)) * (0.3 if ghost else 1.0))
            body = QColor(color or tone)
            p.setPen(Qt.NoPen)
            p.setBrush(body)
            p.drawRoundedRect(QRectF(-w / 2, -h / 2, w, h), h * 0.12, h * 0.12)
            hill = QPainterPath()
            hill.moveTo(-w * 0.36, h * 0.3)
            hill.lineTo(-w * 0.1, -h * 0.12)
            hill.lineTo(w * 0.06, h * 0.1)
            hill.lineTo(w * 0.2, -h * 0.04)
            hill.lineTo(w * 0.38, h * 0.3)
            hill.closeSubpath()
            p.setBrush(QColor(t["picker_bg"]))
            p.drawPath(hill)
            p.drawEllipse(QPointF(w * 0.26, -h * 0.24), h * 0.08, h * 0.08)
            p.restore()

        if isinstance(value, str):  # words: the text as it is right now
            big = QFont(self.font())
            big.setPixelSize(max(12, int(frame.height() * 0.2)))
            big.setWeight(QFont.DemiBold)
            p.setFont(big)
            p.setPen(text)
            p.drawText(frame, Qt.AlignCenter, value)
        elif isinstance(value, tuple):  # a position
            if entry["copy_only"]:  # ...tied to another node: that one, faint, moving by itself
                other = (0.5 + 0.2 * math.sin(now / 20), 0.5)
                picture(spot(other), color=muted, ghost=True)
            trail = QPainterPath()
            for k in range(0, 49):
                at = spot(fx.value_at(entry, max(fx.START, now - 48 + k), numbers))
                trail.moveTo(at) if k == 0 else trail.lineTo(at)
            faint = QColor(text)
            faint.setAlphaF(0.3)
            p.setPen(QPen(faint, 1.2))
            p.setBrush(Qt.NoBrush)
            p.drawPath(trail)
            picture(spot(value))
        elif target == "rotation":
            picture(frame.center(), angle=value)
        elif target == "size":
            if entry["copy_only"]:
                picture(QPointF(frame.left() + frame.width() * 0.3, frame.center().y()), size=value * 2, color=muted, ghost=True)
                picture(QPointF(frame.left() + frame.width() * 0.72, frame.center().y()), size=value)
            else:
                picture(frame.center(), size=value)
        elif target == "fade":
            picture(frame.center(), alpha=value)
        else:  # a number to build with: the level it's at, and its curve going by
            values = fx.samples(entry, values=numbers)
            lo, hi = min(values), max(values)
            box = frame.adjusted(18, 16, -18, -16)
            curve = QPainterPath()
            for k, v in enumerate(values):
                at = QPointF(box.left() + box.width() * k / (len(values) - 1),
                             box.bottom() - (v - lo) / ((hi - lo) or 1) * box.height())
                curve.moveTo(at) if k == 0 else curve.lineTo(at)
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(muted, 1.4))
            p.drawPath(curve)
            share = (now - fx.START) / (fx.END - fx.START)
            dot = QPointF(box.left() + box.width() * share, box.bottom() - (value - lo) / ((hi - lo) or 1) * box.height())
            p.setPen(Qt.NoPen)
            p.setBrush(text)
            p.drawEllipse(dot, 4.5, 4.5)
            p.setPen(text)
            p.setFont(self.font())
            p.drawText(box, Qt.AlignLeft | Qt.AlignTop, f"{value:.2f}")
        p.restore()
        p.setPen(QPen(QColor(t["picker_border"]), 1))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(frame, 6, 6)
        # the clip going by underneath: where in its four seconds the frame above is
        bar = QRectF(frame.left(), frame.bottom() + 5, frame.width(), 2.5)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(t["picker_border"]))
        p.drawRoundedRect(bar, 1.2, 1.2)
        p.setBrush(tone)
        p.drawRoundedRect(QRectF(bar.left(), bar.top(), bar.width() * (now - fx.START) / (fx.END - fx.START), bar.height()), 1.2, 1.2)

    # -- the bar: geometry and dragging --
    def bar_rect(self):
        area = self.image_area()
        return QRectF(area.left(), area.bottom() + 10, area.width(), 3)

    def _marked_span(self, left, right):
        """x of the in and out marks between `left` and `right` (the ends when unset)."""
        width = right - left
        x_in = left + width * (self.mark_in / self.duration) if self.mark_in is not None else left
        x_out = left + width * (self.mark_out / self.duration) if self.mark_out is not None else right
        return x_in, x_out

    def _time_at(self, x, left, right):
        return max(0.0, min(1.0, (x - left) / max(1.0, right - left))) * self.duration

    def _hit(self, pos):
        """What a press at `pos` grabs: ("in"/"out"/"seek", left, right) or None."""
        if self.duration <= 0:
            return None
        bar = self.bar_rect()
        if bar.top() - 9 <= pos.y() <= bar.bottom() + 9 and bar.left() - 6 <= pos.x() <= bar.right() + 6:
            x_in, x_out = self._marked_span(bar.left(), bar.right())
            for which, x, mark in (("out", x_out, self.mark_out), ("in", x_in, self.mark_in)):
                if mark is not None and abs(pos.x() - x) <= 5:
                    return which, bar.left(), bar.right()
            return "seek", bar.left(), bar.right()
        if self.peaks and self._wave_span and self.image_area().contains(pos):
            left, right = self._wave_span
            if left - 6 <= pos.x() <= right + 6:
                return "seek", left, right
        return None

    def _drag_to(self, x):
        _which, left, right = self._grab
        seconds = self._time_at(x, left, right)
        if self.dragging == "seek":
            self.position = seconds
            self.seek.emit(seconds)
        else:
            if self.dragging == "in" and self.mark_out is not None:
                seconds = min(seconds, self.mark_out - 0.04)
            if self.dragging == "out" and self.mark_in is not None:
                seconds = max(seconds, self.mark_in + 0.04)
            setattr(self, "mark_" + self.dragging, seconds)
            self.mark_moved.emit(self.dragging, seconds)
        self.update()

    def restart_card(self):
        """The demonstration from its first frame again - after a slider is let go, so what the new
        number does shows straight away, not when the four seconds come round."""
        if hasattr(self, "_card_clock"):
            self._card_clock.restart()
        self.update()

    def card_numbers(self, entry=None):
        """The numbers the card's sliders are at (the ones it comes with, until you move one)."""
        from . import fusion_expressions as fx
        entry = entry or self.card
        return dict(fx.defaults(entry), **self.card_values.get(entry["key"], {})) if entry else {}

    def _slide(self, x):
        param, track = self._card_drag
        from . import fusion_expressions as fx
        share = (x - track.left()) / max(1.0, track.width())
        if abs(share - 0.5) < 0.025:
            share = 0.5  # the number it came with holds on a little as you pass it
        self.card_values.setdefault(self.card["key"], {})[param["id"]] = fx.slider_value(param, share)
        self.update()

    def _slider_at(self, pos):
        return next(((param, track) for param, track in self._card_sliders
                     if track.adjusted(-6, -9, 6, 9).contains(pos)), None)

    def mousePressEvent(self, event):
        if self.node_view is not None:
            step = self.node_view.flip_at(event.position()) if event.button() == Qt.LeftButton else None
            if step is not None:
                self.flip_node.emit(step)
                return
            text = self.node_view.click(event.position()) if event.button() == Qt.LeftButton else None
            if text:
                self.copy_setting.emit(text)
                QTimer.singleShot(1450, self.update)
                self.update()
            return
        if self.card:  # an expression's card: its sliders (a double click puts one back), the copy mark, the frame
            hit = self._slider_at(event.position())
            if hit is not None and event.button() == Qt.LeftButton:
                self._card_drag = hit
                self._slide(event.position().x())
            elif self._card_copy.contains(event.position()):
                from . import fusion_expressions as fx
                self._card_copied = time.monotonic()
                self.copy_code.emit(fx.code(self.card, self.card_numbers()))
                QTimer.singleShot(1450, self.update)
                self.update()
            elif self._card_stage.contains(event.position()):
                self.restart_card()  # a click on the demonstration: from the start
            return
        hit = self._hit(event.position())
        if hit is None and self.scrub_x is not None and event.button() == Qt.LeftButton:
            # a click while scrubbing: play from here
            self.position = self.scrub_seconds
            self.seek.emit(self.scrub_seconds)
            self.update()
            return
        if hit is None or event.button() != Qt.LeftButton:
            return
        self._grab = hit
        self.dragging = hit[0]
        self._drag_to(event.position().x())

    def mouseMoveEvent(self, event):
        if self.node_view is not None:
            self.node_view.mouse = event.position()
            step = self.node_view.flip_at(event.position())
            self.setCursor(Qt.PointingHandCursor) if self.node_view.hit(event.position()) or step is not None \
                else self.unsetCursor()
            tip = {-1: "Previous node", 1: "Next node"}.get(step, "")
            if tip != self.toolTip():
                self.setToolTip(tip)
            self.update()
            return
        if self.card:
            if self._card_drag is not None:
                self._slide(event.position().x())
            else:
                on = self._slider_at(event.position()) or self._card_copy.contains(event.position())
                self.setCursor(Qt.PointingHandCursor) if on else self.unsetCursor()
                self.setToolTip("Copy the code" if self._card_copy.contains(event.position()) else "")
                self.update(self._card_copy.toAlignedRect())
            return
        if self.dragging:
            self._drag_to(event.position().x())
            return
        hit = self._hit(event.position())
        if hit is None:
            self.unsetCursor()
        else:
            self.setCursor(Qt.SizeHorCursor if hit[0] in ("in", "out") else Qt.PointingHandCursor)
        self._hover_scrub(event.position() if hit is None else None)
        self.update()

    def _hover_scrub(self, pos):
        """Moving across a video's picture moves through the clip - left
        edge the start, right edge the end (Settings -> Preview & listen).
        Only on the picture itself: the empty space above and below a wide
        clip is somewhere to rest the mouse without the clip running off."""
        area = self._picture
        can = (pos is not None and area is not None and self.image is not None and self.duration > 0
               and not self.peaks and not self.graph and self.settings.listen.get("hover_scrub", True)
               and area.contains(pos))
        if not can:
            self._end_scrub()
            return
        if self.scrub_x is None:
            self.scrubbing.emit(True)
        self.scrub_x = pos.x()
        self.scrub_seconds = self._time_at(pos.x(), area.left() + 2, area.right() - 2)
        self.scrub_to.emit(self.scrub_seconds)  # only the picture changes - the bar stays where it plays

    def _end_scrub(self):
        if self.scrub_x is not None:
            self.scrub_x = None
            self.scrub_image = None
            self.scrubbing.emit(False)
            self.update()

    def enterEvent(self, event):
        self.entered.emit()

    def mouseDoubleClickEvent(self, event):
        if self.node_view is not None:
            self.mousePressEvent(event)  # (a second quick click copies again)
            return
        if self.card:
            hit = self._slider_at(event.position())
            if hit is not None:  # back to the number it came with
                self.card_values.get(self.card["key"], {}).pop(hit[0]["id"], None)
                self._card_drag = None
                self.restart_card()
            return
        if self.image is not None and self.image_area().contains(event.position()):
            self.enlarge.emit()

    def mouseReleaseEvent(self, event):
        self.dragging = None
        if self._card_drag is not None:
            self._card_drag = None
            self.restart_card()
        self.update()

    def leaveEvent(self, event):
        if self.node_view is not None:
            self.node_view.mouse = QPointF(-1, -1)
        self._end_scrub()
        self.update()

    def wheelEvent(self, event):
        if self.node_view is not None:  # a node with many settings (a Text+ has 170) scrolls
            self.node_view.wheel(event.pixelDelta().y() or event.angleDelta().y() / 2)
            self.update()
            event.accept()
            return
        super().wheelEvent(event)


    def _paint_waveform(self, p, area):
        """Thin rounded bars, mirrored around the middle; the part already
        heard in the sound colour, the rest muted."""
        t = self.settings.theme
        inner = area.adjusted(20, 0, -20, 0)
        bar_w, gap = 2.4, 2.0
        count = max(8, int((inner.width() + gap) / (bar_w + gap)))
        peaks, n = self.peaks, len(self.peaks)
        raw = []
        for i in range(count):
            a, b = i * n // count, max(i * n // count + 1, (i + 1) * n // count)
            raw.append(max(peaks[a:b]))
        # lightly smoothed, so it reads as a shape rather than spikes
        heights = [(raw[max(0, i - 1)] + 2 * raw[i] + raw[min(count - 1, i + 1)]) / 4 for i in range(count)]
        max_h = inner.height() * 0.3
        cy = inner.center().y()
        played = self.position / self.duration if self.duration > 0 else 0.0
        heard = QColor(self.settings.icon_color("audio"))
        rest = QColor(t["picker_folder"])
        rest.setAlphaF(0.55)
        p.setPen(Qt.NoPen)
        x = inner.left() + (inner.width() - (count * (bar_w + gap) - gap)) / 2
        self._wave_span = (x, x + count * (bar_w + gap) - gap)
        lo = self.mark_in / self.duration if self.mark_in is not None and self.duration else 0.0
        hi = self.mark_out / self.duration if self.mark_out is not None and self.duration else 1.0
        outside = QColor(rest)
        outside.setAlphaF(0.22)
        self._paint_beat_grid(p, cy, max_h * 1.18)
        p.setPen(Qt.NoPen)
        for i, h in enumerate(heights):
            half = max(1.2, (h ** 0.7) * max_h)
            frac = (i + 0.5) / count
            if not lo <= frac <= hi:
                p.setBrush(outside)  # outside the in/out range
            else:
                p.setBrush(heard if frac <= played else rest)
            p.drawRoundedRect(QRectF(x, cy - half, bar_w, 2 * half), 1.0, 1.0)
            x += bar_w + gap
        if self.clipped and len(self.clipped) == n:
            self._paint_clipping(p, count, bar_w + gap, cy, max_h * 1.18)
        if self.beats and self.duration > 0:
            self._paint_loop(p, cy, max_h * 1.18 + 7, heard)
            self._paint_beat_dots(p, area, heard, rest)

    def _paint_clipping(self, p, count, step, cy, half):
        """Dashed red lines where the sound clips (is louder than a file can
        hold, so its tops are cut flat): one line for a moment, a dashed box
        around a longer stretch."""
        n, left = len(self.clipped), self._wave_span[0]
        red = QColor("#ff5f6d")
        runs, start = [], None
        for i in range(count + 1):
            on = i < count and any(self.clipped[i * n // count:max(i * n // count + 1, (i + 1) * n // count)])
            if on and start is None:
                start = i
            elif not on and start is not None:
                runs.append((start, i))
                start = None
        if not runs:
            return
        p.setPen(QPen(red, 1.0, Qt.DashLine))
        tint = QColor(red)
        tint.setAlphaF(0.07)
        for a, b in runs:
            if b - a <= 2:
                x = round(left + (a + b) / 2 * step - 1.0) + 0.5
                p.drawLine(QPointF(x, cy - half), QPointF(x, cy + half))
            else:
                p.setBrush(tint)
                p.drawRoundedRect(QRectF(left + a * step - 2.5, cy - half, (b - a) * step + 3.0, 2 * half), 3, 3)
                p.setBrush(Qt.NoBrush)
        small = font_at(TINY, self.font())
        p.setFont(small)
        p.setPen(red)
        p.drawText(QRectF(left, cy - half - 20, 200, 16), Qt.AlignLeft | Qt.AlignVCenter, "Clipping")


    def _paint_beat_grid(self, p, cy, half):
        """Faint lines on the beats, a little clearer on each bar's first
        beat - behind the waveform, so cuts can be lined up by eye. A long
        song has no room for every beat: then it's bars, or groups of bars."""
        if not self.beats or self.duration <= 0 or not self._wave_span:
            return
        bpm, first = self.beats
        left, right = self._wave_span
        beat_px = (right - left) * (60.0 / bpm) / self.duration
        for every in (1, 4, 16, 32, 64):  # beats, bars, 4 / 8 / 16 bars
            if beat_px * every >= 5:
                break
        else:
            return  # too dense to mean anything at this size
        line = QColor(self.settings.theme["picker_folder"])
        n = 0
        t = first
        while t <= self.duration:
            strong = n % (every * 4) == 0
            line.setAlphaF(0.34 if strong else 0.15)
            p.setPen(QPen(line, 1.0))
            x = left + (right - left) * t / self.duration
            h = half if strong else half * 0.82
            p.drawLine(QPointF(x, cy - h), QPointF(x, cy + h))
            n += every
            t = first + n * 60.0 / bpm

    def _paint_beat_dots(self, p, area, heard, rest):
        """Four dots under the waveform, one per beat of the bar: the one
        playing lights up and settles again, so the beat can be seen."""
        bpm, first = self.beats
        at = (self.position - first) * bpm / 60.0
        now = math.floor(at) % 4 if at >= 0 else None
        glow = (1.0 - (at - math.floor(at))) ** 2  # bright on the beat, fading until the next
        step = 13.0
        x = area.center().x() - 1.5 * step
        y = area.bottom() - 14
        p.setPen(Qt.NoPen)
        for i in range(4):
            if i == now:
                on = QColor(heard)
                on.setAlphaF(0.6 + 0.4 * glow)
                p.setBrush(on)
                r = 2.6 + 1.6 * glow
            else:
                p.setBrush(rest)
                r = 2.6 if i else 3.0  # the bar's first beat: a touch bigger
            p.drawEllipse(QPointF(x + i * step, y), r, r)

    def _paint_loop(self, p, cy, away, color):
        """A thin bracket over the part that loops cleanly (Mark the loop
        puts in and out there) - under it when "Clipping" is written above."""
        if not self.loop or not self._wave_span:
            return
        left, right = self._wave_span
        a = left + (right - left) * min(1.0, self.loop[0] / self.duration)
        b = left + (right - left) * min(1.0, self.loop[1] / self.duration)
        if b - a < 6:
            return
        line = QColor(color)
        line.setAlphaF(0.7)
        p.setPen(QPen(line, 1.2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.setBrush(Qt.NoBrush)
        under = bool(self.clipped and any(self.clipped))
        y = cy + away if under else cy - away
        tick = -5 if under else 5
        bracket = QPainterPath(QPointF(a, y + tick))
        bracket.lineTo(a, y)
        bracket.lineTo(b, y)
        bracket.lineTo(b, y + tick)
        p.drawPath(bracket)
        if under:
            return  # no room for words between the bracket and the dots
        small = font_at(TINY, self.font())
        p.setFont(small)
        text = f"Loop  \u00b7  {self.loop[2]} bars"
        w = QFontMetrics(small).horizontalAdvance(text) + 8
        cx = min(max((a + b) / 2, left + w / 2), right - w / 2)
        p.drawText(QRectF(cx - w / 2, y - 18, w, 15), Qt.AlignCenter, text)


class PlayPauseButton(QWidget):
    """Play / pause in the preview's bottom bar."""
    clicked = Signal()

    def __init__(self, settings):
        super().__init__()
        self.settings = settings
        self.playing = False
        self._hover = False
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(16, 16)

    def set_playing(self, playing):
        if playing != self.playing:
            self.playing = playing
            self.update()

    def enterEvent(self, event):
        self._hover = True
        self.update()

    def leaveEvent(self, event):
        self._hover = False
        self.update()

    def mousePressEvent(self, event):
        self.clicked.emit()

    def paintEvent(self, event):
        t = self.settings.theme
        color = QColor(t["picker_text"] if self._hover and self.isEnabled() else t["picker_folder"])
        if not self.isEnabled():
            color.setAlphaF(0.45)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        s = min(self.width(), self.height())
        ox, oy = (self.width() - s) / 2, (self.height() - s) / 2
        p.setPen(Qt.NoPen)
        p.setBrush(color)
        if self.playing:  # pause: two bars
            w = s * 0.2
            for x in (0.27, 0.53):
                p.drawRoundedRect(QRectF(ox + s * x, oy + s * 0.2, w, s * 0.6), s * 0.05, s * 0.05)
        else:
            tri = QPainterPath()
            tri.moveTo(ox + s * 0.28, oy + s * 0.18)
            tri.lineTo(ox + s * 0.82, oy + s * 0.5)
            tri.lineTo(ox + s * 0.28, oy + s * 0.82)
            tri.closeSubpath()
            p.drawPath(tri)
        p.end()


class InfoView(QWidget):
    """Clip info (Ctrl+D) under the preview picture: quiet label / value
    rows - length, format, audio, BPM, mood, file - only what's known."""

    def __init__(self, settings):
        super().__init__()
        self.settings = settings
        self.rows = []
        self.hide()

    def set_rows(self, rows):
        self.rows = [(k, v) for k, v in rows if v]
        self.setFixedHeight(int(self._line() * max(1, len(self.rows)) + 24))
        self.update()

    def _font(self):
        return font_at(SMALL, self.font())

    def _line(self):
        return QFontMetrics(self._font()).height() * 1.38

    def paintEvent(self, event):
        t = self.settings.theme
        p = QPainter(self)
        p.setRenderHint(QPainter.TextAntialiasing)
        p.setPen(QPen(QColor(t["picker_border"]), 1))
        p.drawLine(QPointF(0, 0.5), QPointF(self.width(), 0.5))
        font = self._font()
        fm = QFontMetrics(font)
        p.setFont(font)
        label_w = max([fm.horizontalAdvance(k) for k, _v in self.rows] + [0]) + 18
        y, line, pad = 12.0, self._line(), 16.0
        for key, value in self.rows:
            p.setPen(QColor(t["picker_folder"]))
            p.drawText(QRectF(pad, y, label_w, line), Qt.AlignLeft | Qt.AlignVCenter, key)
            p.setPen(QColor(t["picker_text"]))
            room = int(self.width() - pad * 2 - label_w)
            p.drawText(QRectF(pad + label_w, y, room, line), Qt.AlignLeft | Qt.AlignVCenter,
                       fm.elidedText(str(value), Qt.ElideMiddle, room))
            y += line
        p.end()


class BarSymbol(QWidget):
    """A small drawn button in the preview's bar: "popout" / "popin" (the
    preview into a window of its own, and back), "full" / "unfull"."""
    clicked = Signal()

    def __init__(self, settings, kind):
        super().__init__()
        self.settings = settings
        self.kind = kind
        self._hover = False
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(16, 16)

    def set_kind(self, kind):
        if kind != self.kind:
            self.kind = kind
            self.update()

    def enterEvent(self, event):
        self._hover = True
        self.update()

    def leaveEvent(self, event):
        self._hover = False
        self.update()

    def mousePressEvent(self, event):
        self.clicked.emit()

    def paintEvent(self, event):
        t = self.settings.theme
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(QColor(t["picker_text"] if self._hover else t["picker_folder"]), 1.3, Qt.SolidLine,
                      Qt.RoundCap, Qt.RoundJoin))
        p.setBrush(Qt.NoBrush)
        if self.kind == "more":  # three dots: the preview's options
            p.setBrush(p.pen().color())
            p.setPen(Qt.NoPen)
            for x in (3.0, 8.0, 13.0):
                p.drawEllipse(QPointF(x, 8.0), 1.5, 1.5)
            p.end()
            return
        path = QPainterPath()
        if self.kind in ("popout", "popin"):  # a window with an arrow leaving (or coming back into) its corner
            path.moveTo(7.0, 3.5)
            path.lineTo(4.5, 3.5)
            path.quadTo(2.5, 3.5, 2.5, 5.5)
            path.lineTo(2.5, 11.5)
            path.quadTo(2.5, 13.5, 4.5, 13.5)
            path.lineTo(10.5, 13.5)
            path.quadTo(12.5, 13.5, 12.5, 11.5)
            path.lineTo(12.5, 9.0)
            path.moveTo(7.5, 8.5)
            path.lineTo(13.5, 2.5)
            if self.kind == "popout":
                path.moveTo(9.8, 2.5)
                path.lineTo(13.5, 2.5)
                path.lineTo(13.5, 6.2)
            else:
                path.moveTo(7.5, 4.8)
                path.lineTo(7.5, 8.5)
                path.lineTo(11.2, 8.5)
        else:  # four corners: pointing out to fill the screen, in to leave it
            for sx, sy in ((1, 1), (-1, 1), (1, -1), (-1, -1)):
                cx, cy = 8 - sx * 5.5, 8 - sy * 5.5  # this corner of the symbol
                if self.kind == "full":
                    path.moveTo(cx + sx * 3.6, cy)
                    path.lineTo(cx, cy)
                    path.lineTo(cx, cy + sy * 3.6)
                else:
                    path.moveTo(cx + sx * 3.6, cy)
                    path.lineTo(cx + sx * 3.6, cy + sy * 3.6)
                    path.lineTo(cx, cy + sy * 3.6)
        p.drawPath(path)
        p.end()


class VolumeSlider(QWidget):
    """The preview's volume: a small speaker and a thin line to drag (or scroll over)."""
    changed = Signal(int)  # percent

    def __init__(self, settings):
        super().__init__()
        self.settings = settings
        self.value = int(settings.listen["volume"])
        self._hover = False
        self.setFixedSize(78, 16)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("Volume")

    def set_value(self, value):
        if value != self.value:
            self.value = value
            self.update()

    def _line(self):
        return 22.0, self.width() - 5.0  # where the line starts and ends

    def _to(self, event):
        left, right = self._line()
        value = int(round(100 * max(0.0, min(1.0, (event.position().x() - left) / (right - left)))))
        if value != self.value:
            self.changed.emit(value)

    def mousePressEvent(self, event):
        self._to(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton:
            self._to(event)

    def wheelEvent(self, event):
        if event.angleDelta().y():
            self.changed.emit(max(0, min(100, self.value + (5 if event.angleDelta().y() > 0 else -5))))
        event.accept()

    def enterEvent(self, event):
        self._hover = True
        self.update()

    def leaveEvent(self, event):
        self._hover = False
        self.update()

    def paintEvent(self, event):
        t = self.settings.theme
        color = QColor(t["picker_text"] if self._hover else t["picker_folder"])
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        s, oy = 14.0, (self.height() - 14.0) / 2
        body = QPainterPath()  # the same speaker as the bottom bar's
        body.moveTo(s * 0.1, oy + s * 0.38)
        body.lineTo(s * 0.28, oy + s * 0.38)
        body.lineTo(s * 0.5, oy + s * 0.16)
        body.lineTo(s * 0.5, oy + s * 0.84)
        body.lineTo(s * 0.28, oy + s * 0.62)
        body.lineTo(s * 0.1, oy + s * 0.62)
        body.closeSubpath()
        p.setPen(Qt.NoPen)
        p.setBrush(color)
        p.drawPath(body)
        p.setPen(QPen(color, 1.2, Qt.SolidLine, Qt.RoundCap))
        p.setBrush(Qt.NoBrush)
        if self.value > 0:
            for r in (0.16, 0.3)[:1 if self.value < 50 else 2]:
                p.drawArc(QRectF(s * 0.5 - s * r, oy + s * 0.5 - s * r, 2 * s * r, 2 * s * r), -50 * 16, 100 * 16)
        left, right = self._line()
        y = self.height() / 2
        at = left + (right - left) * self.value / 100
        faint = QColor(t["picker_folder"])
        faint.setAlphaF(0.4)
        p.setPen(QPen(faint, 2.4, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(left, y), QPointF(right, y))
        p.setPen(QPen(color, 2.4, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(left, y), QPointF(at, y))
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(t["picker_text"]))
        p.drawEllipse(QPointF(at, y), 4.0, 4.0)
        p.end()


# What Space does with the clip that's playing: (setting, name in the preview's options, icon, hover text)
SPACE_ACTIONS = [
    ("pause", "Pause", "pause", "Space pauses the clip, and carries on from there"),
    ("replay", "Start over", "start_over", "Space plays the clip from its start again, every time"),
    ("auto", "Auto", "auto", "Short clips start over, long ones pause (how short: Settings \u203a Preview)"),
]


class PartSwitches(QWidget):
    """A song's stems in one file (DRUMS, BASS ...): a tile for each under the preview, lit while it's heard - a
    click switches it off or on (2026-10-31: "they should be put on the timeline switched off"). Kept for that file
    only (stems.py). Hidden for a file of one sound track."""
    toggled = Signal(object)  # the parts switched off now (places 0 ...)

    def __init__(self, settings):
        super().__init__()
        self.settings = settings
        self.names, self.off = [], set()
        self._hover = None
        self._tiles = []
        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)
        self.hide()

    def set_parts(self, names, off):
        self.names, self.off = list(names or []), set(off or ())
        self.setVisible(len(self.names) > 1)
        self.updateGeometry()
        self.update()

    def _font(self):
        from . import fonts
        return fonts.at(fonts.SMALL)

    def _layout(self, width=None):
        """Each tile's rect - side by side, wrapping onto the next line when the preview is narrow - and the
        height they take."""
        width = self.width() if width is None else width
        fm = QFontMetrics(self._font())
        pad, gap, height = 12, 6, fm.height() + 10
        side = 12  # (the canvas's own inset: under the name, from its first letter)
        x, y, tiles = side, 2, []
        for name in self.names:
            w = fm.horizontalAdvance(name) + pad * 2
            if x + w > width - side and x > side:
                x, y = side, y + height + gap
            tiles.append(QRectF(x, y, w, height))
            x += w + gap
        return tiles, (y + height + 6 if tiles else 0)

    def sizeHint(self):
        return QSize(200, self.heightForWidth(max(self.width(), 200)))

    def minimumSizeHint(self):
        return QSize(0, self.sizeHint().height())

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._layout(width)[1]

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.updateGeometry()  # (narrower: the tiles may wrap onto another line)

    def _at(self, pos):
        for i, rect in enumerate(self._layout()[0]):
            if rect.contains(QPointF(pos)):
                return i
        return None

    def mouseMoveEvent(self, event):
        hover = self._at(event.position().toPoint())
        if hover != self._hover:
            self._hover = hover
            self.update()

    def leaveEvent(self, event):
        self._hover = None
        self.update()

    def mousePressEvent(self, event):
        i = self._at(event.position().toPoint())
        if i is None:
            return
        self.off ^= {i}
        self.update()
        self.toggled.emit(set(self.off))

    def paintEvent(self, event):
        from . import look
        t = self.settings.theme
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setFont(self._font())
        for i, rect in enumerate(self._layout()[0]):
            on = i not in self.off
            look.paint_tile(p, rect, self.settings, chosen=on, hover=i == self._hover)
            colour = QColor(t["picker_text"])
            if not on:
                colour.setAlphaF(0.45)
            p.setPen(colour)
            p.drawText(rect, Qt.AlignCenter, self.names[i])
        p.end()


class PreviewPanel(QWidget):
    """The preview window to the right of the picker: the picture on top
    and its own bottom bar (play/pause, time, Autoplay, Loop)."""
    space_action_picked = Signal(str)  # "pause" / "replay" / "auto", from the options

    def __init__(self, settings):
        super().__init__()
        self.settings = settings
        self.canvas = PreviewCanvas(settings)
        self.footer = QWidget()
        self.footer.setObjectName("PreviewFooter")
        bar = QHBoxLayout(self.footer)
        self.footer_layout = bar
        self.play_button = PlayPauseButton(settings)
        self.time_label = QLabel("")
        self.time_label.setObjectName("FooterHint")
        self.info_toggle = MenuRow(settings, "Info", "info", checked=settings.listen.get("show_info", True))
        self.autoplay_toggle = MenuRow(settings, "Autoplay", "autoplay", checked=settings.listen["autoplay"])
        self.loop_toggle = MenuRow(settings, "Loop", "repeat", checked=settings.listen["loop"])
        self.guides_toggle = MenuRow(settings, "Guides", "guides", kind="more")
        self.with_picker_toggle = MenuRow(settings, "Open with picker", "with_picker",
                                          checked=settings.listen.get("preview_with_picker", False))
        self.with_picker_toggle.setToolTip("The preview opens together with the picker, every time")
        self.volume = VolumeSlider(settings)
        self.stay_toggle = MenuRow(settings, "Stay open", "pin", checked=settings.listen.get("preview_stay", False))
        self.stay_toggle.setToolTip("Stays open when the picker closes")
        self.more_button = BarSymbol(settings, "more")
        self.more_button.setToolTip("Preview options - what Space does, Info, Autoplay, Loop, Guides, "
                                    "Open with picker")
        self.more_button.clicked.connect(self.open_menu)
        self.menu = BarMenu(settings)
        self.space_title = MenuTitle(settings, "Space key")
        self.menu.box.addWidget(self.space_title)
        self.space_rows = {}  # "pause" / "replay" / "auto" -> its row: one of them has the tick
        for mode, text, glyph, tip in SPACE_ACTIONS:
            row = MenuRow(settings, text, glyph, kind="choice")
            row.setToolTip(tip)
            row.clicked.connect(lambda mode=mode: self.space_action_picked.emit(mode))
            self.space_rows[mode] = row
            self.menu.box.addWidget(row)
        self.set_space_action(settings.listen.get("space_action", "auto"))
        self.menu.box.addWidget(MenuRule(settings))
        self.show_title = MenuTitle(settings, "Preview")
        self.menu.box.addWidget(self.show_title)
        for toggle in (self.info_toggle, self.autoplay_toggle, self.loop_toggle, self.guides_toggle,
                       self.with_picker_toggle, self.stay_toggle):
            self.menu.box.addWidget(toggle)
        self.full_button = BarSymbol(settings, "full")
        self.popout_button = BarSymbol(settings, "popout")
        self.time_text = None  # seconds -> text (timecode when Settings says so), else mm:ss
        bar.addWidget(self.play_button, 0, Qt.AlignVCenter)
        bar.addWidget(self.time_label, 0, Qt.AlignVCenter)
        bar.addStretch()
        bar.addWidget(self.volume, 0, Qt.AlignVCenter)
        bar.addWidget(self.more_button, 0, Qt.AlignVCenter)
        bar.addWidget(self.full_button, 0, Qt.AlignVCenter)
        bar.addWidget(self.popout_button, 0, Qt.AlignVCenter)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.info = InfoView(settings)
        self.parts = PartSwitches(settings)  # a song's stems, each to switch off or on
        layout.addWidget(self.canvas, 1)
        layout.addWidget(self.parts)
        layout.addWidget(self.info)
        layout.addWidget(self.footer)
        self.set_controls(False)
        self.set_place("side")

    def set_place(self, place, full=False):
        """Where the preview is - "side" (beside the picker), "window" (popped
        out) or "big" - decides which of the pop-out buttons its bar has."""
        self.popout_button.setVisible(place != "big")
        self.popout_button.set_kind("popin" if place == "window" else "popout")
        self.popout_button.setToolTip("Back beside the picker" if place == "window" else
                                      "Pop out - a window of its own, to drag anywhere (another screen ...)")
        self.full_button.setVisible(place == "window")
        self.full_button.set_kind("unfull" if full else "full")
        self.full_button.setToolTip("Leave full screen (Esc)" if full else "Fill the screen it's on")
        self.stay_toggle.setVisible(place == "window")
        self.menu.hide()
        self.fit_bar()

    def open_menu(self):
        """The options, just above the three dots."""
        menu, dots = self.menu, self.more_button
        menu.setParent(self.window(), menu.windowFlags())  # a popup belongs to the window it opens from
        menu.adjustSize()
        anchor = dots.mapToGlobal(QPoint(dots.width(), 0))
        x, y = anchor.x() - menu.width(), anchor.y() - menu.height() - 10
        area = _screen_area(QRect(anchor, QSize(1, 1)))
        x = max(area.left() + 8, min(x, area.right() - menu.width() - 8))
        if y < area.top() + 8:
            y = dots.mapToGlobal(QPoint(0, dots.height())).y() + 10
        menu.move(x, y)
        menu.show()

    def image_area(self):
        return self.canvas.image_area()

    def bar_min_width(self):
        """How wide the bar must be for its button and toggles (not the time)."""
        bar = self.footer_layout
        margins = bar.contentsMargins()
        items = [w for w in (self.play_button, self.volume, self.more_button, self.full_button,
                             self.popout_button) if not w.isHidden()]
        return margins.left() + margins.right() + sum(w.sizeHint().width() for w in items) \
            + bar.spacing() * (len(items) + 1) + 12

    def fit_bar(self):
        """A narrow preview can't fit the time and every toggle in its bar:
        the time steps aside then, rather than everything overlapping."""
        need = self.bar_min_width()
        fm = QFontMetrics(self.time_label.font())
        need_time = fm.horizontalAdvance(self.time_label.text() or "00:00:00:00 / 00:00:00:00")
        self.time_label.setVisible(self.footer.width() >= need + need_time)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.fit_bar()

    def menu_rows(self):
        """Everything in the options that's drawn with the bar's font."""
        return [self.space_title, self.show_title, *self.space_rows.values(), self.info_toggle,
                self.autoplay_toggle, self.loop_toggle, self.guides_toggle, self.with_picker_toggle,
                self.stay_toggle]

    def set_space_action(self, mode):
        """The tick in the options goes to what Space does now."""
        for key, row in self.space_rows.items():
            row.set_checked(key == mode)

    def set_controls(self, enabled):
        """Play/pause and the time only mean something for a video."""
        self.play_button.setEnabled(enabled)
        if not enabled:
            self.play_button.set_playing(False)
            self.time_label.setText("")
        self.play_button.update()

    def show_frame(self, image, position, duration):
        c = self.canvas
        if c.graph:
            return  # showing a macro's nodes
        if c.dragging == "seek":
            position = c.position  # the handle follows the mouse, not the frames catching up
        c.image, c.position, c.duration, c.message = image, position, duration, ""
        self.update_time()
        c.update()

    def update_time(self):
        c = self.canvas
        if c.duration <= 0:
            return
        fmt = (lambda x: (self.time_text(x) if self.time_text else None) or _fmt_time(x))
        text = f"{fmt(c.position)} / {fmt(c.duration)}"
        if len(text) != len(self.time_label.text()):
            self.time_label.setText(text)
            self.fit_bar()
        else:
            self.time_label.setText(text)
        c.update()

    def show_message(self, text):
        self.canvas.message = text
        self.canvas.update()

    def reset(self, title, category):
        c = self.canvas
        c.image, c.position, c.duration = None, 0.0, 0.0
        c.title, c.category, c.message, c.symbol = title, category, "", None
        c.peaks = None
        c.clipped = None
        c.beats = None
        c.loop = None
        c.used, c.used_times = [], 0
        c.card = None
        c.node_view = None
        c.scrub_x = None
        c.scrub_image = None
        c._picture = None
        c.graph = None
        c.mark_in = c.mark_out = None
        c.dragging = None
        c.waiting = category in ("audio", "video")
        self.parts.set_parts([], ())
        self.set_controls(False)
        c.update()


def _screen_area(rect):
    """The usable area (without dock / menu bar / panels) of the screen
    `rect` is mostly on - or of the one under the mouse."""
    from PySide6.QtGui import QCursor, QGuiApplication
    screen = QGuiApplication.screenAt(rect.center()) or QGuiApplication.screenAt(QCursor.pos()) \
        or QGuiApplication.primaryScreen()
    return screen.availableGeometry()


def _fit_rect(rect, area):
    """`rect` moved (and if it must, shrunk) so it's fully inside `area`."""
    from PySide6.QtCore import QRect
    r = QRect(rect)
    r.setWidth(min(r.width(), area.width()))
    r.setHeight(min(r.height(), area.height()))
    r.moveLeft(max(area.left(), min(r.left(), area.right() - r.width() + 1)))
    r.moveTop(max(area.top(), min(r.top(), area.bottom() - r.height() + 1)))
    return r


class PreviewWindow(QWidget):
    """The preview in a window of its own (Settings -> Preview -> Preview
    window: "A window of its own") - drag it anywhere, e.g. onto a second
    screen; it opens there again next time. Keys typed while it has focus
    still go to the picker."""

    def __init__(self, picker):
        super().__init__(None, Qt.Window | Qt.WindowStaysOnTopHint)
        self.picker = picker
        self.settings = picker.settings
        self.setWindowTitle("Clipse preview")
        self.setObjectName("PreviewWindow")
        self.setAttribute(Qt.WA_ShowWithoutActivating)  # typing stays in the picker
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self.resize(560, 400)

    def set_panel(self, panel):
        self._layout.addWidget(panel)

    def open(self):
        saved = self.settings.display.get("preview_geometry", "")
        if not getattr(self, "_restored", False):
            self._restored = True
            if saved:
                from PySide6.QtCore import QByteArray
                self.restoreGeometry(QByteArray.fromHex(saved.encode()))
            else:  # first time: beside the picker, on whichever side has room
                p = self.picker.frameGeometry()
                area = _screen_area(p)
                x = p.right() + 16 if p.right() + 16 + self.width() <= area.right() else p.left() - 16 - self.width()
                self.move(x, p.top())
        # never (partly) off screen - e.g. saved on a screen that's gone, or a smaller one now
        fitted = _fit_rect(self.frameGeometry(), _screen_area(self.frameGeometry()))
        if fitted != self.frameGeometry():
            self.move(fitted.topLeft())
            if fitted.size() != self.frameGeometry().size():
                self.resize(self.width() - (self.frameGeometry().width() - fitted.width()),
                            self.height() - (self.frameGeometry().height() - fitted.height()))
        self.show()
        self.raise_()
        self.picker.activateWindow()  # keep the keyboard in the search box
        self.picker.search_edit.setFocus()

    def close_and_remember(self):
        if self.isFullScreen():
            self.showNormal()  # remember where the window is, not that it filled the screen
        self.settings.display["preview_geometry"] = bytes(self.saveGeometry().toHex()).decode()
        self.settings.save()
        self.hide()

    def closeEvent(self, event):  # the window's own close button
        event.ignore()
        self.picker._close_preview()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape and self.isFullScreen():
            self.picker._toggle_preview_fullscreen()
        elif not self.picker.isVisible():
            return  # it stayed open after the picker closed: nothing to type into
        elif not self.picker.handle_action_key(event):  # anything else is typing - into the search box
            self.picker.activateWindow()
            QApplication.sendEvent(self.picker.search_edit, event)

    def paintEvent(self, event):
        t = self.settings.theme
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(t["picker_bg"]))
        panel = self.picker.preview_panel
        if panel.parentWidget() is self:
            bar = QRectF(panel.footer.geometry()).translated(panel.geometry().topLeft())
            p.fillRect(bar, QColor(t.get("picker_bar_bg", t["picker_bg"])))
            p.setPen(QPen(QColor(t["picker_border"]), 1))
            p.drawLine(QPointF(0, bar.top() + 0.5), QPointF(self.width(), bar.top() + 0.5))
        p.end()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        area = self.picker.preview_panel.image_area()
        self.picker.video.max_size = (int(max(area.width(), 320) * 2), int(max(area.height(), 180) * 2))


class BigPreview(PreviewWindow):
    """The big view: the preview (picture, bar, info - everything) on most
    of the screen. Tap the big-view key (or double-click the picture) to
    open and close it; hold the key to peek - it shrinks back when you let
    go. Esc closes it too."""

    def __init__(self, picker):
        super().__init__(picker)
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_MacAlwaysShowToolWindow, True)
        self.setWindowTitle("Clipse big preview")

    def open(self):
        area = _screen_area(self.picker.frameGeometry())
        w, h = int(area.width() * 0.86), int(area.height() * 0.86)
        self.setGeometry(area.x() + (area.width() - w) // 2, area.y() + (area.height() - h) // 2, w, h)
        self.show()
        self.raise_()
        self.picker.activateWindow()
        self.picker.search_edit.setFocus()

    def closeEvent(self, event):
        event.ignore()
        self.picker.toggle_big_preview(False)

    def keyReleaseEvent(self, event):
        self.picker.handle_key_release(event)

    def paintEvent(self, event):
        super().paintEvent(event)
        p = QPainter(self)
        p.setPen(QPen(QColor(self.settings.theme["picker_border"]), 1))
        p.drawRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5))
        p.end()


class PreviewButton(QWidget):
    """Bottom-bar button that opens/closes the preview window: a small
    window with a panel on its right."""
    clicked = Signal()
    toggled = Signal(bool)  # the preview opened / closed

    def __init__(self, settings):
        super().__init__()
        self.settings = settings
        self.active = False
        self._hover = False
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(16, 16)

    def set_active(self, active):
        if active != self.active:
            self.active = active
            self.update()
            self.toggled.emit(active)

    def enterEvent(self, event):
        self._hover = True
        self.update()

    def leaveEvent(self, event):
        self._hover = False
        self.update()

    def mousePressEvent(self, event):
        self.clicked.emit()

    def paintEvent(self, event):
        t = self.settings.theme
        color = QColor(t["picker_text"] if self._hover else t["picker_folder"])
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        s = min(self.width(), self.height())
        ox, oy = (self.width() - s) / 2, (self.height() - s) / 2
        # a window with a panel on its right side - the preview window
        pen_w = max(1.05, s * 0.066)  # (a little finer than the other line icons: sharp, like the gear)
        frame = QRectF(ox + s * 0.08, oy + s * 0.18, s * 0.84, s * 0.64)
        inset = frame.adjusted(pen_w / 2, pen_w / 2, -pen_w / 2, -pen_w / 2)
        split = frame.left() + frame.width() * 0.56
        radius = s * 0.075
        p.setPen(QPen(color, pen_w))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(inset, radius, radius)
        if self.active:  # open: the panel is filled
            panel = QPainterPath()
            panel.addRoundedRect(inset, radius, radius)
            right = QPainterPath()
            right.addRect(QRectF(split, frame.top(), frame.right() - split, frame.height()))
            p.setPen(Qt.NoPen)
            p.setBrush(color)
            p.drawPath(panel.intersected(right))
        else:
            p.drawLine(QPointF(split, inset.top()), QPointF(split, inset.bottom()))
        p.end()


class GlyphButton(QWidget):
    """A line icon in the bottom bar (glyphs.py): Settings' gear, Autoplay. on: a soft pill behind it, like a
    keycap (not the accent: a switch that's on nearly all the time would be the loudest thing in the bar);
    dot: a small dot in its corner (a newer version is out)."""
    clicked = Signal()

    def __init__(self, settings, glyph):
        super().__init__()
        self.settings = settings
        self.glyph = glyph
        self.on = False
        self.dot = False
        self._hover = False
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(16, 16)

    def set_on(self, on):
        if on != self.on:
            self.on = on
            self.update()

    def set_dot(self, dot):
        if dot != self.dot:
            self.dot = dot
            self.update()

    def enterEvent(self, event):
        self._hover = True
        self.update()

    def leaveEvent(self, event):
        self._hover = False
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()

    def paintEvent(self, event):
        from .glyphs import draw_glyph
        t = self.settings.theme
        accent = QColor(t.get("picker_accent", t["picker_text"]))
        text = QColor(t["picker_text"])
        color = text if self.on or self._hover else QColor(t["picker_folder"])
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        side = min(self.width(), self.height())
        if self.width() > self.height():  # room for the pill: the icon a little smaller inside it
            if self.on:
                pill = QColor(text)
                pill.setAlphaF(0.1)
                p.setPen(Qt.NoPen)
                p.setBrush(pill)
                p.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), side / 2.6, side / 2.6)
            side = self.height() - 6
        draw_glyph(p, self.glyph, QPointF(self.width() / 2, self.height() / 2), side, color)
        if self.dot:
            p.setPen(Qt.NoPen)
            p.setBrush(accent)
            p.drawEllipse(QPointF(self.width() - side * 0.12, side * 0.12), side * 0.13, side * 0.13)
        p.end()


class RefreshButton(QWidget):
    """The small circular-arrow button in the bottom bar - rescans the
    Media Pool, same as the refresh key."""
    clicked = Signal()

    def __init__(self, settings):
        super().__init__()
        self.settings = settings
        self._hover = False
        self._angle = 0.0
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(16, 16)
        self._spin = None

    def set_busy(self, busy):
        """Turns slowly while the Media Pool is being read; one last quick
        turn when it's done."""
        from PySide6.QtCore import QVariantAnimation, QEasingCurve
        if busy:
            if getattr(self, "_turning", None) is None:
                self._turning = QVariantAnimation(self)
                self._turning.setStartValue(0.0)
                self._turning.setEndValue(360.0)
                self._turning.setDuration(1100)
                self._turning.setLoopCount(-1)
                self._turning.setEasingCurve(QEasingCurve.Linear)
                self._turning.valueChanged.connect(self._set_angle)
            if self._turning.state() != QVariantAnimation.Running:
                self._turning.start()
        elif getattr(self, "_turning", None) is not None and self._turning.state() == QVariantAnimation.Running:
            self._turning.stop()
            self._angle = 0.0
            self.spin()

    def spin(self):
        """One quick turn - shown after a rescan finishes."""
        from PySide6.QtCore import QVariantAnimation, QEasingCurve
        if self._spin is None:
            self._spin = QVariantAnimation(self)
            self._spin.setStartValue(0.0)
            self._spin.setEndValue(360.0)
            self._spin.setDuration(450)
            self._spin.setEasingCurve(QEasingCurve.OutCubic)
            self._spin.valueChanged.connect(self._set_angle)
        self._spin.stop()
        self._spin.start()

    def _set_angle(self, value):
        self._angle = float(value) % 360
        self.update()

    def enterEvent(self, event):
        self._hover = True
        self.update()

    def leaveEvent(self, event):
        self._hover = False
        self.update()

    def mousePressEvent(self, event):
        self.clicked.emit()

    def paintEvent(self, event):
        import math
        t = self.settings.theme
        color = QColor(t["picker_text"] if self._hover else t["picker_folder"])
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        side = min(self.width(), self.height())
        r = side * 0.32
        cx, cy = self.width() / 2, self.height() / 2
        if self._angle:
            p.translate(cx, cy)
            p.rotate(self._angle)
            p.translate(-cx, -cy)
        pen_w = max(1.3, side * 0.1)
        p.setPen(QPen(color, pen_w, Qt.SolidLine, Qt.RoundCap))
        p.setBrush(Qt.NoBrush)
        start, span = 80, -290  # degrees, clockwise
        p.drawArc(QRectF(cx - r, cy - r, 2 * r, 2 * r), int(start * 16), int(span * 16))
        end = math.radians(start + span)
        px, py = cx + r * math.cos(end), cy - r * math.sin(end)
        tx, ty = math.sin(end), math.cos(end)      # direction of travel (clockwise)
        nx, ny = math.cos(end), -math.sin(end)     # outward
        a = side * 0.2
        head = QPainterPath()
        head.moveTo(px + tx * a, py + ty * a)
        head.lineTo(px - tx * a * 0.25 + nx * a * 0.8, py - ty * a * 0.25 + ny * a * 0.8)
        head.lineTo(px - tx * a * 0.25 - nx * a * 0.8, py - ty * a * 0.25 - ny * a * 0.8)
        head.closeSubpath()
        p.setPen(Qt.NoPen)
        p.setBrush(color)
        p.drawPath(head)
        p.end()


def bring_to_front(window):
    """Makes sure keystrokes go to `window` right away.

    The picker belongs to a background process, and Windows and macOS
    don't let a background process take keyboard focus by itself — the
    window would appear, but typing would still go to Resolve.
      Windows: briefly attach to the foreground window's input queue,
               the standard way around the focus lock.
      macOS:   activate this app (it has no Dock icon, see
               daemon.hide_dock_icon_macos).
    Linux window managers handle this through activateWindow()."""
    system = platform.system()
    if system == "Windows":
        try:
            import ctypes
            from ctypes import wintypes
            user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
            user32.GetForegroundWindow.restype = wintypes.HWND
            user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.c_void_p]
            user32.GetWindowThreadProcessId.restype = wintypes.DWORD
            user32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
            user32.SetForegroundWindow.argtypes = [wintypes.HWND]
            user32.BringWindowToTop.argtypes = [wintypes.HWND]
            hwnd = wintypes.HWND(int(window.winId()))
            fg_thread = user32.GetWindowThreadProcessId(user32.GetForegroundWindow(), None)
            own_thread = kernel32.GetCurrentThreadId()
            attached = bool(fg_thread and fg_thread != own_thread
                            and user32.AttachThreadInput(own_thread, fg_thread, True))
            user32.BringWindowToTop(hwnd)
            user32.SetForegroundWindow(hwnd)
            if attached:
                user32.AttachThreadInput(own_thread, fg_thread, False)
        except Exception as e:
            print(f"Couldn't bring the picker to the front: {e}")
    elif system == "Darwin":
        try:
            from AppKit import NSApp
            NSApp.unhide_(None)  # give_focus_back() hides the app when the picker closes
            NSApp.activateIgnoringOtherApps_(True)
        except Exception:
            pass


def remember_front_app():
    """The app that had focus before the picker opened (macOS/Windows),
    so focus can go straight back to it when the picker closes."""
    system = platform.system()
    try:
        if system == "Darwin":
            from AppKit import NSWorkspace
            app = NSWorkspace.sharedWorkspace().frontmostApplication()
            if app is not None and app.processIdentifier() != _os.getpid():
                return app
        elif system == "Windows":
            import ctypes
            return ctypes.windll.user32.GetForegroundWindow() or None
    except Exception:
        pass
    return None


def give_focus_back(front):
    """Hands keyboard focus back to the app the picker was opened from.
    macOS doesn't do this by itself for a background helper like this one:
    without it, Resolve's own shortcuts (Cmd+S ...) stop working after an
    insert until you click into Resolve. Linux window managers do it on
    their own."""
    if front is None:
        return
    system = platform.system()
    try:
        if system == "Darwin":
            from AppKit import NSApp
            try:  # macOS 14 and later: an app can't push another to the front, it hands over to it - without this
                NSApp.yieldActivationToApplication_(front)  # the keyboard went elsewhere, not to Resolve (macOS 26)
            except AttributeError:
                pass
            front.activateWithOptions_(1 << 1)  # Resolve (ActivateIgnoringOtherApps, for older macOS)...
            NSApp.hide_(None)  # ...and step back
        elif system == "Windows":
            import ctypes
            ctypes.windll.user32.SetForegroundWindow(front)
    except Exception as e:
        print(f"Couldn't give focus back: {e}")


def _set_energy(row):
    """A sound's energy: the file's own tag - and what the analysis makes of it (music only, cut where its words calm /
    steady / energetic are), which shows only with Settings > Sound > Guess energy on (clip_model.shown_energy)."""
    from .file_tags import energy_of
    row.energy = energy_of(row.file_tags)
    guess = (row.analysis or {}).get("energy") if row.music else None
    row.energy_guess = 0 if guess is None else 1 if guess < 0.36 else 3 if guess > 0.62 else 2


class SoundAnalyser(QObject):
    """Music vs sound effects, BPM, key, mood, loops and "sounds like
    this" (sound_analysis.py). Results already worked out are applied when
    the picker opens - instantly, nothing is analysed then. The analysis
    itself runs when you ask for it (Settings -> General -> Analyse sounds),
    or for new sounds on open if you've turned that on."""
    found = Signal(object, object)   # (row, result)
    progress = Signal(int, int)      # (done, total)
    finished = Signal(int)           # how many were analysed

    def __init__(self, parent=None):
        super().__init__(parent)
        self._generation = 0
        self.running = False
        self.rows = []

    def apply_cached(self, rows, settings):
        from . import sound_analysis as sa
        self.rows = rows
        self._generation += 1  # a new list: any running analysis stops
        self.running = False
        split = settings.listen.get("split_music", True)
        for row in rows:
            if row.category != "audio":
                continue
            if not split:
                row.music, row.bpm = False, None
                continue
            result = sa.cached(row.file) if row.file else None
            if result is not None:
                self.apply(row, result)

    def missing(self, rows=None):
        """Audio rows not analysed yet (that can be)."""
        from . import sound_analysis as sa
        out = []
        for r in (rows if rows is not None else self.rows):
            if r.category == "audio" and r.file and (not r.secs or r.secs <= 15 * 60):
                hit = sa.cached(r.file)
                if not sa.complete(hit, r.music):  # new, failed (tried again), from before 1.32, or music taken for an effect
                    out.append(r)
        return out

    def failed(self):
        """Audio rows whose file couldn't be analysed: [(row, reason)]."""
        from . import sound_analysis as sa
        out = []
        for r in self.rows:
            if r.category == "audio" and r.file:
                hit = sa.cached(r.file)
                if hit and hit.get("error"):
                    out.append((r, hit["error"] if isinstance(hit["error"], str) else "unreadable"))
        return out

    def start(self, rows=None, only_missing=True):
        """Analyses (the missing) audio rows on a background thread."""
        import threading
        from . import sound_analysis as sa
        if not sa.available():
            return False
        todo = self.missing(rows) if only_missing else [r for r in (rows or self.rows) if r.category == "audio" and r.file]
        if not todo:
            self.finished.emit(0)
            return True
        todo.sort(key=lambda r: r.music is not True)  # clear music first
        self._generation += 1
        generation = self._generation
        self.running = True

        def work():
            done = 0
            for row in todo:
                if generation != self._generation:
                    return  # stopped, or the Media Pool was rescanned
                result = sa.analyse(row.file, row.music, retry_errors=True)
                done += 1
                if result is not None:
                    self.found.emit(row, result)
                self.progress.emit(done, len(todo))
                time.sleep(0.01)  # let the picker breathe between files
            if generation == self._generation:
                self.running = False
                self.finished.emit(done)
        threading.Thread(target=work, name="clipse-analyse", daemon=True).start()
        return True

    def stop(self):
        self._generation += 1
        self.running = False

    @staticmethod
    def apply(row, result):
        if result.get("error") or result.get("partial"):
            return
        row.analysis = result
        if row.music is None and "music" in result:
            row.music = result["music"]
        row.bpm = result.get("bpm") if row.music else None
        words = []
        if row.music:
            if row.bpm:
                words.append(f"{round(row.bpm)} bpm")
            words += result.get("mood") or []
            if result.get("key"):
                words.append(result["key"].lower())
        row.extra_tags = " ".join(words)
        _set_energy(row)


class ScanBar(QWidget):
    """A hairline across the top of the list while the Media Pool is read:
    filled as far as it's got, or a light running along when the total
    isn't known yet. Gone when there's nothing to wait for."""

    def __init__(self, settings, parent):
        super().__init__(parent)
        self.settings = settings
        self.progress = None
        self._run = 0.0
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self.hide()

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Resize:
            self.setGeometry(0, 0, obj.width(), 2)
            self.raise_()
        return False

    def set_progress(self, value):
        """0-1, -1 for "working, total unknown", or None to hide."""
        self.progress = value
        if value is None:
            self._timer.stop()
            self.hide()
            return
        if not self.isVisible():
            self.setGeometry(0, 0, self.parentWidget().width(), 2)
            self.show()
            self.raise_()
            self._timer.start(30)
        self.update()

    def _tick(self):
        self._run = (self._run + 0.02) % 1.0
        self.update()

    def paintEvent(self, event):
        if self.progress is None:
            return
        p = QPainter(self)
        accent = QColor(self.settings.theme.get("picker_accent", self.settings.theme["picker_text"]))
        track = QColor(accent)
        track.setAlphaF(0.18)
        p.fillRect(self.rect(), track)
        w = self.width()
        if self.progress >= 0:
            p.fillRect(QRectF(0, 0, w * self.progress, self.height()), accent)
        else:
            x = (w + w * 0.3) * self._run - w * 0.3
            p.fillRect(QRectF(x, 0, w * 0.3, self.height()), accent)
        p.end()


class SeamHandle(QWidget):
    """The seam between the picker and the preview beside it: a strip to drag, nothing drawn. Dragged, the picker
    and the preview trade width (PickerWindow._seam_dragged); let go, the sizes are kept (_remember_split)."""

    def __init__(self, picker):
        super().__init__(picker)
        self.picker = picker
        self.setCursor(Qt.SizeHorCursor)
        self._from = None
        self.hide()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._from = (event.globalPosition().x(), self.picker._seam_start())
            event.accept()

    def mouseMoveEvent(self, event):
        if self._from is not None and event.buttons() & Qt.LeftButton:
            x, start = self._from
            self.picker._seam_dragged(round(event.globalPosition().x() - x), start)

    def mouseReleaseEvent(self, event):
        if self._from is not None:
            self._from = None
            self.picker._remember_split()

    def mouseDoubleClickEvent(self, event):
        self.picker._reset_split()


class _NothingLands(Exception):
    """The first clip of an insert found no track that would take it (PickerWindow._run_preset)."""


class PickerWindow(QWidget):
    opened = Signal()  # the picker is on screen (the start-up card hands over)

    def __init__(self, settings, insert_frequency):
        super().__init__()
        self.settings = settings
        self.insert_frequency = insert_frequency
        self.favorited_names = rc.load_favorites()
        self.resolve = None
        self.session = {"rows": [], "filtered_group_list": [], "project": None, "timeline": None,
                         "media_pool": None, "root_folder": None, "cache_file": None, "project_name": None}
        self._scan = None           # the Media Pool read that's running (see _start_scan)
        self._media_reads = {}      # project -> {"any", "full"}: when it was last looked at, last read in full
        self._prescanned = None     # project already read ahead of the first open
        self._scan_timer = QTimer(self)
        self._scan_timer.setSingleShot(True)
        self._scan_timer.timeout.connect(self._scan_step)
        self.selection_order_ids = []
        self.selection_order_project = None
        self._preset_used = None     # a preset that isn't kept goes back to Normal on the next open
        self._preset_once = None     # History -> restore: the preset that insert used, for the next one
        self._live_count_rows = []  # (RowData, filtered_group_list index) for bin/selected rows
        from . import history_dialog
        self.history = history_dialog.load()  # every insert kept, all projects (history.json) - see history_dialog.py
        self._pre_prefix_filter_text = None  # for toggle_search_prefix's toggle-back
        self._external_action_pending = False  # guards against a repeated/queued Enter
        # re-triggering a script/macro/comp action more than once per open

        self.setObjectName("PickerRoot")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        # macOS hides tool windows whenever another app is clicked; the
        # picker stays (Settings -> General -> "Close the picker when you click outside it")
        self.setAttribute(Qt.WA_MacAlwaysShowToolWindow, True)
        # Transparent outside the rounded corners — the window paints its
        # own background in paintEvent.
        self.setAttribute(Qt.WA_TranslucentBackground)
        self._wanted_size = None  # the size this window gave itself a moment ago (see _set_size)
        self._wanted_until = 0.0
        self._size_tries = 0
        self.resize(*self.window_size())
        self._picker_w = self.width()  # the picker's own width, without a preview beside it

        self.model = ClipListModel(settings, insert_frequency)
        self.model.external_provider = self._provide_external_rows
        self.model.default_view_provider = self._provide_default_rows
        self.model.favorite_external_provider = self._favorite_external_rows
        self.model.recent_provider = self._recent_order
        self.model.unused_provider = self._unused_rows
        self.model.checkup_provider = self._checkup_rows
        self.model.used_provider = self._used_rows
        self.model.similar_provider = self._similar_rows
        self.model.title_provider = self._title_rows
        self.model.basic_provider = self._basic_rows
        self.model.template_provider = self._template_rows
        self.model.layout_provider = self._layout_rows
        self.model.prefix_menu_provider = self._prefix_menu_rows
        self.model.actions_provider = self._action_rows
        self.model.search_actions_provider = self._search_action_rows
        self.delegate = ClipItemDelegate(self.model, settings)

        self.search_edit = SearchEdit(self)
        self.search_edit.setObjectName("PickerSearch")
        self.count_label = QLabel("")
        self.count_label.setObjectName("PickerCount")
        self.list_view = QListView()
        self.list_view.setObjectName("PickerList")
        self.list_view.setModel(self.model)
        self.list_view.clicked.connect(lambda _index: self._set_in_list(True))  # a click on a row: in the list
        self.list_view.setItemDelegate(self.delegate)
        self.row_hover = RowHover(self.list_view, self.delegate)
        self.list_view.setFocusPolicy(Qt.NoFocus)  # keyboard stays on the search box
        self.list_view.setSelectionMode(QAbstractItemView.ContiguousSelection)
        self.list_view.doubleClicked.connect(lambda _i: self.confirm())
        self.list_view.setContextMenuPolicy(Qt.CustomContextMenu)  # right-click a script: Resolve's menu
        self.list_view.customContextMenuRequested.connect(self._row_menu)
        self._selection_anchor = None  # row where a Shift+Down/Up range started, or None
        # every row is the same height: say so, or the list asks each of them (thousands, on every key)
        self.list_view.setUniformItemSizes(True)
        # No visible scrollbars — wheel/Up/Down still scroll via QListView's
        # own handling, this just hides the drag handles.
        self.list_view.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list_view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        from .scroll_hint import ScrollHint
        self.scroll_hint = ScrollHint(self.list_view, self.settings)  # (a thin bar while it scrolls, Vicinae's)

        # Layout:  search line (+ result count) / divider / list / bottom bar
        self.search_area = QWidget()
        self._search_layout = QHBoxLayout(self.search_area)
        self._search_layout.addWidget(self.search_edit, 1)
        self._search_layout.addWidget(self.count_label, 0, Qt.AlignVCenter)

        self.list_area = QWidget()
        self._list_layout = QVBoxLayout(self.list_area)
        self._list_layout.addWidget(self.list_view)
        self.scan_bar = ScanBar(self.settings, self.list_area)  # over the list's top edge
        self.list_area.installEventFilter(self.scan_bar)
        # The preview is its own card to the right of the picker (drawn as a
        # separate floating window with a gap, but part of the same window,
        # so it works on Wayland too, where apps can't place windows).
        self.preview_panel = PreviewPanel(self.settings)
        self.preview_panel.hide()
        self.preview_window = None  # created when the preview first opens in its own window

        self.footer = QWidget()
        self.footer.setObjectName("PickerFooter")
        footer = QHBoxLayout(self.footer)
        self._footer_layout = footer
        # on the left, drawn: Settings, Rescan - then the keys worth saying (not Enter inserts) and what's staged;
        # at the right Actions, Insert as, History, and last the preview - on the side it opens (Autoplay is in
        # the preview's own options, nowhere else)
        self.settings_link = GlyphButton(self.settings, "gear_fine")
        self.settings_link.clicked.connect(self.open_settings)
        footer.addWidget(self.settings_link, 0, Qt.AlignVCenter)
        self.refresh_button = RefreshButton(self.settings)
        self.refresh_button.clicked.connect(self.refresh_rows)
        footer.addWidget(self.refresh_button, 0, Qt.AlignVCenter)
        self.hints_label = FooterHints(self.settings)  # only keys that aren't plain - set in apply_theme
        self.hints_label.setObjectName("FooterHint")
        footer.addWidget(self.hints_label)
        self.staged_summary_label = ClickableLabel("")
        self.staged_summary_label.setTextFormat(Qt.RichText)
        self.staged_summary_label.clicked.connect(self.show_staged_only)
        self.staged_summary_label.hide()
        footer.addWidget(self.staged_summary_label)
        footer.addStretch()
        self.insert_options_link = ClickableLabel("Insert as")
        self.insert_options_link.setToolTip("How clips land on the timeline - stacked, back to back, spaced out, "
                                            "at every marker, scaled ...")
        self.insert_options_link.clicked.connect(self._page_link_clicked)
        self._page_link_fusion = False  # on the Fusion page that link is Expressions (_set_page_link)
        self._page_seen = None  # the page Resolve was on when last looked (_watch_page)
        self._page_timer = QTimer(self)
        self._page_timer.setInterval(700)
        self._page_timer.timeout.connect(self._watch_page)
        self._pick = None  # waiting for a node to be clicked in Fusion (pick_node_in_fusion)
        self._pick_timer = QTimer(self)
        self._pick_timer.timeout.connect(self._pick_step)
        self.history_link = ClickableLabel("History")
        self.history_link.clicked.connect(self.open_history)
        self.actions_link = ClickableLabel("Actions")
        self.actions_link.clicked.connect(lambda: self.actions_panel.toggle())
        for link in (self.actions_link, self.insert_options_link, self.history_link):
            footer.addWidget(link)
        self.preview_button = PreviewButton(self.settings)
        self.preview_button.clicked.connect(self.toggle_preview)
        footer.addWidget(self.preview_button, 0, Qt.AlignVCenter)

        from .swap_strip import SwapStrip
        self.swap_strip = SwapStrip(self.settings)  # Swap clip: what goes out, what comes in (start_swap)
        self.swap_strip.everywhere_changed.connect(self._swap_everywhere)
        self.swap_strip.cancelled.connect(self.end_swap)
        self.swap_strip.pick.connect(self._swap_pick)
        self._swap_picking = None  # while the picker is out of the way for a click in Resolve (_swap_pick)
        self._swap = None

        self.picker_column = QWidget()
        self._layout = QVBoxLayout(self.picker_column)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)
        self._layout.addWidget(self.search_area)
        self._layout.addWidget(self.swap_strip)
        from .tag_strip import TagKeeper, TagStrip
        self.tag_strip = TagStrip(self.settings, self)  # a sound's energy and tags, while it plays (open_tags)
        self.tag_strip.tags_changed.connect(lambda tags: self._set_tags(self._tag_row(), tags))
        self.tag_strip.energy_chosen.connect(self.set_energy)
        self.tag_strip.play.connect(self.play_pause)
        self.tag_strip.closed.connect(self.close_tags)
        self._layout.addWidget(self.tag_strip)
        self.tag_keeper = TagKeeper(self)
        self.tag_keeper.found.connect(self._on_tags_read)
        self.tag_keeper.read_done.connect(self._on_tags_done)
        self.tag_keeper.failed.connect(self._on_tag_failed)
        self._layout.addWidget(self.list_area, 1)
        self._layout.addWidget(self.footer)
        outer = QHBoxLayout(self)
        # the window's smallest size is the picker's own (_set_least_size), not the sum of its parts' widths: with
        # the preview's width fixed, that sum let the window grow but never shrink (Sway's Super + right-drag)
        from PySide6.QtWidgets import QLayout
        outer.setSizeConstraint(QLayout.SetNoConstraint)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(self._gap())
        outer.addWidget(self.picker_column, 1)
        outer.addWidget(self.preview_panel)
        self.seam_handle = SeamHandle(self)
        self.model.modelReset.connect(self._update_count)

        # Listening to sounds (Ctrl+P). While on, moving to another sound plays that one.
        self.audio = AudioPreview()
        self._audio_follow = False
        self._audio_paths = {}  # filtered_group_list index -> file path
        self._audio_timer = QTimer(self)
        self._audio_timer.setSingleShot(True)
        self._audio_timer.timeout.connect(self._audio_follow_current)
        self._in_palette = False
        self.list_view.selectionModel().currentChanged.connect(
            lambda *_: None if self._in_palette else setattr(self, "_last_plain_index", self._current_orig_index()))
        self.list_view.selectionModel().currentChanged.connect(
            lambda *_: self._audio_follow and self._audio_timer.start(140))
        self.list_view.selectionModel().currentChanged.connect(lambda *_: self._swap and self._swap_follow())
        self.list_view.selectionModel().currentChanged.connect(
            lambda *_: self.tag_strip.isVisible() and self._tags_follow())

        # Watching clips in the picker (the preview key, Ctrl+Shift+P). While open, the preview
        # follows the highlighted row.
        self.video = VideoPlayer(self.audio)
        self.scrubber = Scrubber()  # hover scrub frames, read apart from playback
        from .scrub_sound import ScrubSound
        self.scrub_sound = ScrubSound(lambda: self.audio.gain)  # ...and the sound under the mouse (a setting)
        self._scrub_quiet = QTimer(self)  # lets go of the sound device a moment after the last step
        self._scrub_quiet.setSingleShot(True)
        self._scrub_quiet.timeout.connect(self.scrub_sound.quiet)
        self.scrubber.ready.connect(self._on_scrub_frame)
        self.video.frame.connect(self._on_video_frame)  # a method, so it runs on the GUI thread
        self.video.message.connect(self._on_video_message)
        self.video.state.connect(self._on_video_state)
        self.video.waveform.connect(self._on_waveform)
        self.video.clipping.connect(self._on_clipping)
        self.video.parts.connect(self._on_parts)
        self.preview_panel.parts.toggled.connect(self._parts_toggled)
        # Ctrl+Space with the preview closed: just the sound of any clip (mp4s too)
        self.sound = VideoPlayer(self.audio, audio_only=True)
        self.sound.message.connect(self._on_sound_message)
        from .window_level import ResolveOnlyFloat
        self.floater = ResolveOnlyFloat(self.settings, self)  # above Resolve only, not other apps
        from .hover_focus import HoverFocus
        self.hover_focus = HoverFocus(self.settings, self)  # mouse on a window = keyboard to it
        from .actions_panel import ActionsPanel
        self.actions_panel = ActionsPanel(self)
        from .expression_sheet import ExpressionSheet
        self.expression_sheet = ExpressionSheet(self)
        from .wheel_zoom import install as _wheel_zoom
        _wheel_zoom(QApplication.instance())  # Ctrl + the wheel zooms what's under the mouse
        from .tour import Tour
        self.tour = Tour(self)
        self.analyser = SoundAnalyser(self)  # music vs sound effects, BPM, mood, loops
        self.analyser.found.connect(self._on_analysed)
        self.analyser.finished.connect(self._on_analysis_done)
        SettingsDialog.sound_analyser = self.analyser
        # the first preview used to wait for the video/audio libraries to load -
        # load them quietly in the background a moment after start instead
        QTimer.singleShot(1500, self._warm_up)
        SettingsDialog.picker_place_reset = self.reset_place
        # edge cursors where a drag resizes (see eventFilter / mousePressEvent)
        self.setMouseTracking(True)
        for area in (self.footer, self.search_area):
            area.setMouseTracking(True)
            area.installEventFilter(self)
        self.preview_panel.play_button.clicked.connect(self.play_pause)
        self.preview_panel.space_action_picked.connect(self._set_space_action)
        self._volume_save = QTimer(self)
        self._volume_save.setSingleShot(True)
        self._volume_save.timeout.connect(self.settings.save)
        self.preview_panel.volume.changed.connect(self._set_volume)
        self.preview_panel.canvas.seek.connect(self.video.seek_to)
        self.preview_panel.canvas.seek.connect(self._on_seek_sound)
        self.preview_panel.canvas.scrubbing.connect(self._on_scrubbing)
        self.preview_panel.canvas.scrub_to.connect(self._on_scrub_to)
        self.preview_panel.canvas.entered.connect(self._prepare_scrub)
        self.preview_panel.canvas.mark_moved.connect(self._on_mark_moved)
        self._marks = {}  # file path -> {"in": s, "out": s}, for this open of the picker
        self._used = None  # what's on the timeline already (tt.UsedParts), read when the preview first asks
        self._used_timer = QTimer(self)
        self._used_timer.setSingleShot(True)
        self._used_timer.timeout.connect(self._used_step)
        self.preview_panel.autoplay_toggle.toggled.connect(lambda on: self._set_preview_option("autoplay", on))
        self.preview_panel.info_toggle.toggled.connect(lambda on: self._set_info_shown(on))
        for w in (self.preview_panel.info_toggle, self.preview_panel.info):
            w.setContextMenuPolicy(Qt.CustomContextMenu)
            w.customContextMenuRequested.connect(lambda pos, w=w: self._info_fields_menu(w.mapToGlobal(pos)))
        self.preview_panel.loop_toggle.toggled.connect(lambda on: self._set_preview_option("loop", on))
        self.preview_panel.guides_toggle.clicked.connect(self._guides_menu)
        self.preview_panel.canvas.enlarge.connect(self._enlarge_preview)
        self.preview_panel.canvas.copy_code.connect(self._copy_card_code)
        self.preview_panel.canvas.copy_setting.connect(self._copy)
        self.preview_panel.canvas.flip_node.connect(self.flip_node)
        self.preview_panel.popout_button.clicked.connect(self._toggle_popout)
        self.preview_panel.full_button.clicked.connect(self._toggle_preview_fullscreen)
        self.preview_panel.stay_toggle.toggled.connect(lambda on: self._set_preview_option("preview_stay", on))
        self.preview_panel.with_picker_toggle.toggled.connect(
            lambda on: self._set_preview_option("preview_with_picker", on))
        self.preview_panel.time_text = self.preview_panel.canvas.time_text = self._time_text
        self._clip_tc = (0.0, 0)  # (frame rate, start timecode in frames) of the clip in the preview
        self._big = None          # the big view (BigPreview), made on first use
        self._preview_slot = None  # see-through stand-in beside the picker while the preview is in the big view
        self._big_opening = False  # the big view opens in a moment (see toggle_big_preview)
        self._render_presets = None  # Resolve's render presets, read when the > list first needs them
        self._expression_asked = None  # the expression Enter asked about ("Enter again adds a Transform")
        self.list_view.selectionModel().currentChanged.connect(lambda *_: self._show_expression_card())
        self._card_opened_preview = False  # the preview was opened just to show an expression
        self._on_expression_before = False
        self._in_list = False        # you've moved down into the rows (Space plays there - see _space_plays)
        self._last_replay = 0.0      # when Space last started a sound over (holding it down repeats)
        self._checkup_cache = {}     # the project check-up's lists (see _checkup_rows)
        self._big_key = None      # (key, when pressed) - holding it peeks
        listen = self.settings.listen
        self._guides = list(listen.get("guides") or []) if listen.get("remember_guides") else []
        self._sync_guides()
        self._video_timer = QTimer(self)
        self._video_timer.setSingleShot(True)
        self._video_timer.timeout.connect(self._preview_current)
        self.list_view.selectionModel().currentChanged.connect(
            lambda *_: self.preview_panel.isVisible() and self._video_timer.start(220))

        self.search_edit.textChanged.connect(self._on_text_changed)
        self._clip_seq = {}         # clip row -> when it was staged (orders a Fusion chain)
        self._history = None        # searches being browsed with Up/Down (None = not browsing)
        self._history_pos = -1
        self._history_draft = ""    # what was typed before browsing started
        self._setting_history_text = False
        self.apply_theme()

        self._selection_timer = QTimer(self)
        self._selection_timer.timeout.connect(self._poll_selection_order)
        self._selection_timer.start(SELECTION_ORDER_POLL_MS)

        self._live_count_timer = QTimer(self)
        self._live_count_timer.timeout.connect(self._refresh_live_counts)
        self._live_count_timer.start(LIVE_COUNT_REFRESH_MS)

    # -- theming --
    def apply_theme(self):
        # Applied at the QApplication level, not just on self: a QDialog
        # (like SettingsDialog) is its own top-level window and doesn't
        # inherit a stylesheet set only on the picker widget — it'd fall
        # back to the OS default (plain white) otherwise.
        # Only re-apply the app-wide stylesheet when it actually changed:
        # setStyleSheet re-polishes EVERY widget, and doing that on each
        # keystroke while you type in a Settings field (font size, window
        # size, clip name...) could knock the cursor/focus out of the field.
        # The font picked in Settings, first: with the app's stylesheet on, a new app font doesn't reach the widgets
        # made before it (the Actions panel, Expressions, the toasts kept the old one) - the stylesheet is put on
        # again after it, which hands every widget the new font.
        from .fonts import apply_ui_font
        app = QApplication.instance()
        app.setFont(apply_ui_font(app.font(), self.settings))
        sheet = build_stylesheet(self.settings)
        font_key = app.font().toString()
        if sheet != getattr(self, "_applied_stylesheet", None) or font_key != getattr(self, "_applied_font", None):
            app.setStyleSheet(sheet)
            self._applied_stylesheet, self._applied_font = sheet, font_key

        d = self.settings.display
        from .fonts import picker_scale
        scale = picker_scale(self.settings)  # (the UI scale times the picker's own zoom - Ctrl and + / -)
        pad = round(d["outer_padding"] * scale)

        base = apply_ui_font(QFont(), self.settings)
        small = font_at(SMALL, base)
        search_font = font_at(TITLE, base, QFont.Light)  # (Vicinae's search: 1.2 the base)

        self.search_edit.setFont(search_font)
        self.list_view.setFont(base)
        self.count_label.setFont(small)
        pp = self.preview_panel
        for w in (self.hints_label, self.staged_summary_label,
                  self.insert_options_link, self.history_link, self.actions_link,
                  pp.time_label, *pp.menu_rows()):
            w.setFont(small)
        pp.canvas.setFont(small)

        self._search_layout.setContentsMargins(pad, pad, pad, pad)
        self._list_layout.setContentsMargins(round(8 * scale), round(8 * scale), round(8 * scale), round(6 * scale))
        self._footer_layout.setContentsMargins(pad, 0, pad, 0)
        self._footer_layout.setSpacing(round(18 * scale))
        self.footer.setFixedHeight(round(QFontMetrics(small).height() + 14 * scale))
        pp.footer.setFixedHeight(self.footer.height())
        pp.footer_layout.setContentsMargins(pad, 0, pad, 0)
        pp.footer_layout.setSpacing(round(14 * scale))
        for row in pp.menu_rows():
            row.setFixedHeight(row.sizeHint().height())
            row.updateGeometry()
        pp.set_space_action(self.settings.listen.get("space_action", "auto"))
        pp.fit_bar()
        pp.info_toggle.set_checked(self.settings.listen.get("show_info", True))
        if pp.isVisible():
            self._sync_info()  # Settings changed what the info shows
        pp.info_toggle.setToolTip(f"Clip info under the preview ({self._key_text('show_info')}) - "
                                  "right-click to choose what it shows")
        pp.autoplay_toggle.set_checked(self.settings.listen["autoplay"])
        pp.loop_toggle.set_checked(self.settings.listen["loop"])
        pp.with_picker_toggle.set_checked(self.settings.listen.get("preview_with_picker", False))
        self.video.loop = self.settings.listen["loop"]
        pp.autoplay_toggle.setToolTip("Start clips as soon as they show here (off: wait for play)")
        pp.guides_toggle.setToolTip("Framing guides over the picture - 16:9, 9:16, thirds ...")
        pp.loop_toggle.setToolTip("Start over at the end (off: play once)")
        pp.play_button.setToolTip(
            f"Play/pause ({self._key_text('play_pause')}, or Space once you're in the list)\n"
            f"In the list: 1 second back / forward ({self._key_text('list_seek_back')} / "
            f"{self._key_text('list_seek_forward')})\n"
            f"5 seconds back / forward ({self._key_text('seek_back')} / {self._key_text('seek_forward')})\n"
            f"Mark in / out ({self._key_text('mark_in')} / {self._key_text('mark_out')}) - Enter then inserts "
            f"just that part\nClick or drag the bar to move through the clip")
        self.hints_label.set_hints(self._footer_hints())
        icon_side = round(QFontMetrics(small).height() * 1.05)
        for button in (self.settings_link, self.refresh_button, self.preview_button):
            button.setFixedSize(icon_side, icon_side)
        pp.play_button.setFixedSize(icon_side, icon_side)
        self.preview_button.setToolTip(f"Preview window on/off ({self._key_text('preview')})")
        self.audio.volume = self.settings.listen["volume"]
        # hovering the bottom bar shows each item's key
        self.refresh_button.setToolTip(f"Rescan the Media Pool ({self._key_text('refresh')})")
        self._set_page_link(self._page_link_fusion)
        self.history_link.setToolTip(f"History ({self._key_text('toggle_history')})")
        self.actions_link.setToolTip(f"Actions - everything Clipse can do ({self._key_text('show_actions')})")
        self.settings_link.setToolTip(f"Settings ({self._key_text('toggle_settings')})")
        self.update()

        # Live-applies window size even while the window is currently
        # visible (e.g. Settings open on top of it) — previously this only
        # resized when hidden, which in practice meant "next app restart".
        extra = 0
        width, height = self.window_size()
        self._picker_w = width
        self.layout().setSpacing(self._gap())
        self._set_least_size()
        if self._slot_held() and not self._shares():
            extra = self._preview_slot.width() + self._gap()
            self.picker_column.setFixedWidth(width)
        elif self.preview_panel.isVisible() and self._preview_docked() and not self._shares():
            extra = self.preview_panel.width() + self._gap()
            self.picker_column.setFixedWidth(width)
        target_size = (width + extra, height)
        if (self.width(), self.height()) != target_size:
            was_visible = self.isVisible()
            self._set_size(*target_size)
            if was_visible:
                self._keep_on_screen()

        # Row heights are cached from the delegate's sizeHint() and won't
        # recompute on their own just because the font/scale changed —
        # force it so rows don't render at a stale size for a moment.
        self.list_view.doItemsLayout()
        self.list_view.viewport().update()

    def zoom_window(self, direction):
        """Ctrl and + / - / 0: what's inside bigger or smaller - the window keeps the size it has, as after a drag
        (2026-10-21: "the zoom is only supposed to make the pickers inside be smaller"; it went back to the
        automatic size with every step)."""
        from .fonts import step_zoom
        if self.isVisible():
            self._keep_size()
        step_zoom(self.settings, "picker", direction)
        self.settings.save()
        self.apply_theme()

    def window_size(self):
        """The picker's size: the one set in Settings, or (0 = automatic) Vicinae's 770 x 480 grown with the text
        (fonts.zoom) - it went by the screen before, and on a big one the text sat small in a wide window (
        "really zoomed out"). Never more than most of the screen."""
        d = self.settings.display
        width, height = d.get("window_width", 0), d.get("window_height", 0)
        if width and height:
            return width, height
        from PySide6.QtGui import QCursor, QGuiApplication
        from .fonts import window_zoom, zoom
        k = zoom(self.settings) * window_zoom(self.settings, "picker")
        auto_w, auto_h = round(770 * k), round(480 * k)
        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        area = screen.availableGeometry() if screen else None
        if area:
            auto_w, auto_h = min(auto_w, round(area.width() * 0.8)), min(auto_h, round(area.height() * 0.8))
        return (width or auto_w), (height or auto_h)

    def _say(self, text, ms=None, lead="", steps=()):
        """A few words on the screen while the picker is out of the way (keycast.Toast: small, low in the middle,
        gone by itself in a couple of seconds)."""
        if getattr(self, "toast", None) is None:
            from .keycast import Toast
            self.toast = Toast(self.settings)
            self.toast.setFont(self.font())
        self.toast.say(text, ms, lead, steps)

    PICK_SECONDS = 25.0

    def pick_node_in_fusion(self, done, say):
        """The picker gets out of the way until a node is clicked in Fusion, then done(its name) -
        done("") when none was within PICK_SECONDS, or it was called off (Esc or a click on the
        small notice that waits with you - keycast.PickNotice). Nothing is selected first, so a
        click on the node that was selected counts too. False away from the Fusion page. Opening
        the picker again calls it off without a word."""
        if self._current_page_key() != "fusion":
            return False
        fusion_expressions.clear_selection(self.resolve)
        self._pick = {"before": fusion_expressions.selected_node_now(self.resolve), "done": done,
                      "until": time.monotonic() + self.PICK_SECONDS}
        self.hide()
        if getattr(self, "pick_notice", None) is None:
            from .keycast import PickNotice
            self.pick_notice = PickNotice(self.settings)
            self.pick_notice.setFont(self.font())
            self.pick_notice.cancelled.connect(lambda: self._end_pick(""))
        self.pick_notice.wait_for(say)
        self._pick_timer.start(150)
        return True

    def _pick_step(self):
        pick = self._pick
        if pick is None:
            self._pick_timer.stop()
            return
        name = fusion_expressions.selected_node_now(self.resolve)
        if name and name != pick["before"]:
            self._end_pick(name)
        elif time.monotonic() > pick["until"]:
            self._end_pick("")

    def _end_pick(self, name, tell=True):
        pick, self._pick = self._pick, None
        self._pick_timer.stop()
        if getattr(self, "pick_notice", None) is not None:
            self.pick_notice.hide()
        if pick is not None and tell:
            print(f"[expression] picked in Fusion: {name or 'nothing'}")
            pick["done"](name)

    def _copy_card_code(self, code):
        self._copy(code)
        self._flash_hint("Copied the code - right-click a setting \u203a Expression to paste it", 4000)

    def _schedule_apply_theme(self):
        """Settings changes are applied a moment after the last change
        rather than on every keystroke — typing "18" in a size field then
        restyles once, not twice, and never mid-edit."""
        if not hasattr(self, "_theme_timer"):
            self._theme_timer = QTimer(self)
            self._theme_timer.setSingleShot(True)
            self._theme_timer.timeout.connect(self.apply_theme)
        self._theme_timer.start(250)

    def paintEvent(self, event):
        """The picker: a rounded card with a hairline outline, a divider
        under the search line and the darker bottom bar. The preview (when
        open) is a second card to its right."""
        t = self.settings.theme
        d = self.settings.display
        from .fonts import picker_scale
        radius = d["outer_corner_radius"] * picker_scale(self.settings)
        outline = d["outer_outline_width"]
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        beside = self.preview_panel.isVisible() and self._preview_docked()
        inside = beside and self._inside()
        bar_color = QColor(t.get("picker_bar_bg", t["picker_bg"]))
        divider = QColor(t["picker_border"])
        divider.setAlphaF(0.6)  # quieter than the card's own edge

        def card(rect):
            r = QRectF(rect).adjusted(0.5, 0.5, -0.5, -0.5)
            shape = QPainterPath()
            shape.addRoundedRect(r, radius, radius)
            p.fillPath(shape, QColor(t["picker_bg"]))
            return r, shape

        if inside:  # One window: the picker's card, the preview inside it on the right, a line between
            rect, shape = card(self.rect())
            pick = QRectF(self.picker_column.geometry())
            prev = QRectF(self.preview_panel.geometry())
            p.save()
            p.setClipPath(shape)
            bar = QRectF(self.footer.geometry()).translated(pick.topLeft())
            pbar = QRectF(self.preview_panel.footer.geometry()).translated(prev.topLeft())
            p.fillRect(bar, bar_color)
            p.fillRect(pbar, bar_color)
            p.setPen(QPen(divider, 1))
            y = pick.top() + self.search_area.geometry().bottom() + 0.5
            p.drawLine(QPointF(pick.left(), y), QPointF(pick.right(), y))
            p.drawLine(QPointF(pick.left(), bar.top() + 0.5), QPointF(pick.right() + 1, bar.top() + 0.5))
            p.drawLine(QPointF(prev.left(), pbar.top() + 0.5), QPointF(rect.right(), pbar.top() + 0.5))
            p.setPen(QPen(QColor(t["picker_border"]), 1))
            p.drawLine(QPointF(prev.left() + 0.5, rect.top()), QPointF(prev.left() + 0.5, rect.bottom()))
            p.restore()
            if outline > 0:
                p.setPen(QPen(QColor(t["outer_outline_color"]), outline))
                p.setBrush(Qt.NoBrush)
                p.drawRoundedRect(rect, radius, radius)
            p.end()
            return

        rect, shape = card(self.picker_column.geometry())
        p.save()
        p.setClipPath(shape)
        bar = QRectF(self.footer.geometry())
        p.fillRect(bar, bar_color)
        p.setPen(QPen(divider, 1))
        y = self.search_area.geometry().bottom() + 0.5
        p.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
        p.drawLine(QPointF(rect.left(), bar.top() + 0.5), QPointF(rect.right(), bar.top() + 0.5))
        p.restore()
        rects = [rect]
        if beside:
            prect, pshape = card(self.preview_panel.geometry())
            rects.append(prect)
            p.save()
            p.setClipPath(pshape)
            pbar = QRectF(self.preview_panel.footer.geometry()).translated(self.preview_panel.geometry().topLeft())
            p.fillRect(pbar, bar_color)
            p.setPen(QPen(QColor(t["picker_border"]), 1))
            p.drawLine(QPointF(prect.left(), pbar.top() + 0.5), QPointF(prect.right(), pbar.top() + 0.5))
            p.restore()
        if outline > 0:
            p.setPen(QPen(QColor(t["outer_outline_color"]), outline))
            p.setBrush(Qt.NoBrush)
            for r in rects:
                p.drawRoundedRect(r, radius, radius)
        p.end()

    def _key_text(self, action):
        """A keybind as shown to the user, e.g. "Ctrl+R" (both keys if a second one is set)."""
        keys = [self.settings.keybinds.get(action), self.settings.keybinds_secondary.get(action)]
        texts = [QKeySequence(k).toString(QKeySequence.NativeText) for k in keys if k]
        return " or ".join(texts) if texts else "no key set"

    def _footer_hints(self):
        def key(action, fallback):
            from .keycaps import key_name
            return key_name(self.settings.keybinds.get(action) or fallback)
        orig = self._current_orig_index() if hasattr(self, "list_view") else None
        if orig is not None and orig < len(self.model.rows) and self.model.rows[orig].category in ("shortcut", "action"):
            return []  # (Enter opens it, Enter runs it: plain)
        expression = self._on_expression() if hasattr(self, "list_view") else None
        if expression is not None:
            entry = fusion_expressions.BY_KEY.get(expression.path) or {}
            if entry.get("copy_only") and fusion_expressions.NAMES_A_NODE in entry.get("template", "") \
                    and self._page_link_fusion:
                return [(key("confirm", "Return"), "Click the node to follow", ""),
                        ("Shift+" + key("confirm", "Return"), "Copy the code", "")]
            if entry.get("copy_only"):
                return [(key("confirm", "Return"), "Copy the code", "")]
            return [(key("confirm", "Return"), "Put on a node", ""), ("Shift+" + key("confirm", "Return"), "Copy the code", "")]
        # Enter inserts, Tab stages, Space plays: plain (2026-10-14) - only an Insert as that isn't
        # Normal is said, since Enter then does more than it looks
        preset = presets_mod.active(self.settings)
        return [] if preset["id"] == "normal" else [(key("confirm", "Return"), "Insert", f"as {preset['name']}")]

    def _update_count(self):
        n = self.model.rowCount()
        mixed = any(self.model.rows[i].category in EXTERNAL_ROW_CATEGORIES for i in self.model.visible[:200])
        if self.model.showing_external or mixed:
            noun = "result" if n == 1 else "results"
        else:
            noun = "clip" if n == 1 else "clips"
        self.count_label.setText(f"{n} {noun}")

    # -- opening the resolve project --
    def set_resolve(self, resolve):
        self.resolve = resolve

    def open_picker(self, force_refresh=False):
        if getattr(self, "_force_refresh_next", False):
            self._force_refresh_next = False
            force_refresh = True
        stats.record("open")
        self._set_in_list(False)  # it opens in the search
        self._render_presets = None
        if self._pick is not None:
            self._end_pick("", tell=False)  # the picker was asked for while waiting for a click in Fusion: that's off
        self._page_changed(self._current_page_key(), search_again=False)
        self._page_timer.start()
        self._checkup_cache = {}
        if self._preset_used and self._preset_used == self.settings.presets.get("active"):  # used once: Normal again
            presets_mod.set_active(self.settings, "normal")
            self.settings.save()
            self.hints_label.set_hints(self._footer_hints())
        self._preset_used = None

        project = self.resolve.GetProjectManager().GetCurrentProject()
        if project is None:
            print("No project open in Resolve.")
            return
        timeline = project.GetCurrentTimeline()
        if timeline is None:
            print("No timeline in the current project yet — you can browse, but inserting needs one created first.")
        media_pool = project.GetMediaPool()
        root_folder = media_pool.GetRootFolder()
        project_name = project.GetName()

        kept, kept_chain = {}, list(self.model.chain) if self.settings.g("keep_staged") else []
        if self.settings.g("keep_staged") and self.session.get("project") is not None:
            try:
                if self.session["project"].GetName() == project_name:
                    kept = self._staged_name_snapshot()  # same project: bring them back below
            except Exception:
                kept = {}
        self.model.clear_staged()
        self._update_staged_summary()
        self._selection_anchor = None
        self._external_action_pending = False
        rows, filtered_group_list, cache_file, id_paths = self._rows_now(
            project_name, root_folder, media_pool, force_refresh)
        self._audio_paths = {}
        self.session.update(rows=rows, filtered_group_list=filtered_group_list, cache_file=cache_file,
                             id_paths=id_paths, project=project, timeline=timeline, media_pool=media_pool,
                             root_folder=root_folder, project_name=project_name)
        self._live_count_rows = [
            (rows[i], i) for i, (_name, _instances, category) in enumerate(filtered_group_list)
            if category == "selected"
        ]

        self.setWindowTitle(f"Insert clip ({project_name})")
        self.search_edit.blockSignals(True)
        self.search_edit.clear()
        self.search_edit.blockSignals(False)
        self._history = None
        self._marks = {}
        self._used = None  # the timeline may have changed since: read again when the preview asks
        self._apply_analysis(rows)
        self.model.set_rows(rows)
        if kept:
            self._restore_staged_by_name(kept)
        if kept_chain:
            self.model.chain = kept_chain
            self._update_staged_summary()
        self._select_row(0)

        self._update_notice()
        with_preview = False
        if not self.isVisible():
            self._front_app = remember_front_app()
            self._place_window()  # already open: it stays where it is
            # Settings -> Preview -> Open the preview together with the picker
            with_preview = bool(self.settings.listen.get("preview_with_picker")) and not self.preview_panel.isVisible() \
                and not self._slot_held()
            if with_preview and self.settings.listen.get("preview_place", "side") == "side":
                # its place beside the picker before the window shows: it comes
                # up at its full size, nothing grows or jumps afterwards
                self._reserve_preview_place()
        self.show()
        self.raise_()
        self.activateWindow()
        self._float_over_all_spaces_macos()
        bring_to_front(self)
        self.search_edit.setFocus()
        if with_preview:
            self._open_preview_panel()
            # the picker first, then the clip; and quietly - opening the picker never starts a sound
            QTimer.singleShot(0, lambda: self.preview_panel.isVisible() and self._preview_current(quiet=True))
            self.search_edit.setFocus()
        self.floater.start()
        self.hover_focus.start()
        self.opened.emit()
        self._update_scan_bar()
        if not self.settings.general.get("tour_done", False) and not self.tour.isVisible():
            QTimer.singleShot(350, lambda: self.isVisible() and self.tour.start())

    def _update_notice(self):
        """A small dot after "Settings" when a newer version is out (checked
        at most once a day, in the background)."""
        from . import updater
        if not self.settings.general.get("check_for_updates", True):
            self.settings_link.set_dot(False)
            return
        import threading
        threading.Thread(target=updater.check, daemon=True).start()  # refreshes the daily answer
        latest = updater.cached_update()
        self.settings_link.set_dot(bool(latest))
        tip = f"Settings ({self._key_text('toggle_settings')})"
        if latest:
            tip += f"\nVersion {latest['version']} is available - Settings -> About"
        self.settings_link.setToolTip(tip)

    def _float_over_all_spaces_macos(self):
        """Qt.WindowStaysOnTopHint already keeps this above other windows;
        making it follow you across macOS Spaces (including full-screen
        apps) needs Cocoa's NSWindow collection-behavior API directly,
        same as the Tk version required PyObjC for the same reason."""
        if platform.system() != "Darwin":
            return
        try:
            from AppKit import (NSApp, NSWindowCollectionBehaviorCanJoinAllSpaces,
                                 NSWindowCollectionBehaviorFullScreenAuxiliary, NSFloatingWindowLevel)
            # over a full-screen Resolve; following you to every Space only when
            # it isn't meant to stay with Resolve (Settings -> General)
            behavior = NSWindowCollectionBehaviorFullScreenAuxiliary
            if not self.settings.g("float_only_over_resolve"):
                behavior |= NSWindowCollectionBehaviorCanJoinAllSpaces
            for window in NSApp.windows():
                window.setCollectionBehavior_(behavior)
                window.setLevel_(NSFloatingWindowLevel)
        except ImportError:
            pass  # pip3 install pyobjc-framework-Cocoa for cross-Space floating
        except Exception as e:
            print(f"Couldn't set macOS cross-Space floating behavior: {e}")

    # -- filtering / selection --
    def _on_text_changed(self, _typed):
        self.search_edit.take_prefix()  # (a prefix just typed: the pill)
        text = self.search_edit.text()  # (the whole search, the pill's prefix included)
        self._last_typed = time.monotonic()
        self._expression_asked = None
        if text.startswith(">") and not getattr(self, "_in_palette", False):
            self._in_palette = True
            previous = getattr(self, "_last_plain_text", "")
            self._before_palette = (previous, getattr(self, "_last_plain_index", None))
        elif not text.startswith(">"):
            self._in_palette = False
            self._last_plain_text = text
        if not self._setting_history_text:
            self._history = None  # typing ends history browsing
        self.model.set_filter(text)
        self._select_row(0)

    # -- search history (like a terminal: Up on the top row goes back) --
    def _history_step(self, step):
        """step=+1: an older search, -1: a newer one. Returns False when
        there's nothing to step to."""
        if self._history is None:
            if step < 0:
                return False
            current = self.search_edit.text().strip()
            self._history = [h for h in rc.load_search_history() if h != current]
            self._history_pos = -1
            self._history_draft = self.search_edit.text()
        pos = self._history_pos + step
        if pos >= len(self._history):
            return bool(self._history)  # already at the oldest - stay put
        if pos < 0:
            text = self._history_draft
            self._history = None  # back at what you typed
        else:
            self._history_pos = pos
            text = self._history[pos]
        self._setting_history_text = True
        self.search_edit.setText(text)
        self.search_edit.end(False)
        self._setting_history_text = False
        return True

    def _remember_search(self):
        rc.record_search(self.search_edit.text())
        self._history = None

    def _select_row(self, row):
        """Plain single-row navigation — always collapses any active
        multi-selection back down to just this one row."""
        if self.model.rowCount() == 0:
            return
        row = max(0, min(self.model.rowCount() - 1, row))
        self._selection_anchor = None
        index = self.model.index(row, 0)
        self.list_view.selectionModel().select(index, QItemSelectionModel.ClearAndSelect)
        self.list_view.setCurrentIndex(index)
        self.list_view.scrollTo(index)
        self._update_staged_summary()

    def _set_selection_range(self, row_a, row_b):
        lo, hi = min(row_a, row_b), max(row_a, row_b)
        selection = QItemSelection(self.model.index(lo, 0), self.model.index(hi, 0))
        self.list_view.selectionModel().select(selection, QItemSelectionModel.ClearAndSelect)
        target = self.model.index(row_b, 0)
        # setCurrentIndex() on the view (not the selection model) applies
        # its own default selection command internally, which was
        # silently collapsing the range we just set back down to a single
        # row — NoUpdate moves the current index without touching
        # selection at all.
        self.list_view.selectionModel().setCurrentIndex(target, QItemSelectionModel.NoUpdate)
        self.list_view.scrollTo(target)
        self._update_staged_summary()

    def _extend_selection(self, direction):
        """Shift+Down/Up — extends the selected range by one row from
        wherever it started (the anchor), in `direction` (+1 or -1)."""
        if self.model.rowCount() == 0:
            return
        current_row = self.list_view.currentIndex().row()
        if self._selection_anchor is None:
            self._selection_anchor = current_row
        new_row = max(0, min(self.model.rowCount() - 1, current_row + direction))
        self._set_selection_range(self._selection_anchor, new_row)

    def _jump_to_edge(self, bottom):
        """Ctrl+Down/Up — jump straight to the last/first row, no range
        selection (same as plain Down/Up repeated, just instant)."""
        if self.model.rowCount() == 0:
            return
        self._select_row(self.model.rowCount() - 1 if bottom else 0)

    def _select_to_edge(self, bottom):
        """Ctrl+Shift+Down/Up — extends the selected range all the way
        to the last/first row from wherever it started."""
        if self.model.rowCount() == 0:
            return
        current_row = self.list_view.currentIndex().row()
        if self._selection_anchor is None:
            self._selection_anchor = current_row
        self._set_selection_range(self._selection_anchor, self.model.rowCount() - 1 if bottom else 0)

    def _clear_multi_selection(self):
        self._selection_anchor = None
        current = self.list_view.currentIndex()
        if current.isValid():
            self.list_view.selectionModel().select(current, QItemSelectionModel.ClearAndSelect)

    def _get_multi_selected_orig_indices(self):
        return [idx.data(ROLE_ORIG_INDEX) for idx in self.list_view.selectionModel().selectedIndexes()]

    def _current_orig_index(self):
        index = self.list_view.currentIndex()
        if not index.isValid():
            return None
        return index.data(ROLE_ORIG_INDEX)

    def _is_external_row(self, orig_index):
        if orig_index is None or orig_index >= len(self.model.rows):
            return False
        return self.model.rows[orig_index].category in EXTERNAL_ROW_CATEGORIES

    # -- key routing --
    def handle_key_release(self, ev):
        held = self._big_key
        if held and ev.key() == held[0] and not ev.isAutoRepeat():
            self._big_key = None
            if time.monotonic() - held[1] > 0.4:  # held down: it was a peek - back to normal
                print(f"[preview] big view: the key was held {time.monotonic() - held[1]:.2f} s - a peek, so back again")
                self.toggle_big_preview(False)

    def key_is(self, ev, action):
        """True when the key pressed is the one set for `action` (Settings > Keybindings)."""
        return _seq_matches(ev, self.settings.keybinds.get(action, "")) \
            or _seq_matches(ev, self.settings.keybinds_secondary.get(action, ""))

    def handle_action_key(self, ev) -> bool:
        kb = self.settings.keybinds
        kb2 = self.settings.keybinds_secondary
        if DEBUG_KEYS:
            pressed = QKeySequence(ev.keyCombination()).toString(QKeySequence.PortableText)
            hit = [a for a in kb if _seq_matches(ev, kb[a]) or _seq_matches(ev, kb2.get(a, ""))]
            print(f"[key] {pressed!r} key={ev.key()} mods={int(ev.modifiers().value)} -> {hit or 'no action'}")

        def matches(action):
            return _seq_matches(ev, kb[action]) or _seq_matches(ev, kb2[action])

        # A key for a picker that has closed isn't meant for it. It happens: Enter starts a long
        # insert, the app is busy with Resolve for a second, and the keyboard's own repeat (which
        # on Wayland the app makes itself) then fires a second Enter - the highlighted clip went
        # in once more, after the ones you asked for. Enter never repeats, held down or not.
        if not self.isVisible():
            return True
        if ev.isAutoRepeat() and ev.key() in (Qt.Key_Return, Qt.Key_Enter):
            return True
        if self.tour.isVisible():  # the first-run tour: Enter next, Esc skip
            return self.tour.handle_key(ev)
        # the Actions panel takes every key while it's open (arrows, Enter, typing to narrow)
        if self.actions_panel.isVisible():
            if matches("show_actions"):
                self.actions_panel.close_panel()
                return True
            return self.actions_panel.handle_key(ev)
        if self.expression_sheet.isVisible():  # ...and so does the expression cheat sheet (its own zoom too)
            if matches("preview"):  # but the preview's key opens / closes the preview (showing the node) - 2026-10-22
                self.preview_clip()  # (Expressions' own: remembered for it, the picker's is put back after)
                self.settings.display["expressions_preview"] = self.preview_panel.isVisible()
                self.settings.save()
                self.layout().activate()
                self.expression_sheet.setGeometry(self.picker_column.geometry())  # (the list's room changed)
                return True
            return self.expression_sheet.handle_key(ev)
        if matches("show_actions"):
            self.actions_panel.open()
            return True
        expression = self._on_expression()
        if expression is not None and ev.type() == QEvent.KeyPress:
            copy_key = ev.key() == Qt.Key_C and ev.modifiers() in (Qt.ControlModifier, Qt.MetaModifier) \
                and not self.search_edit.hasSelectedText()
            if copy_key or (ev.key() in (Qt.Key_Return, Qt.Key_Enter) and ev.modifiers() == Qt.ShiftModifier):
                self._confirm_expression(expression, only_copy=True)  # just its code, nothing put anywhere
                return True
        if ev.type() == QEvent.KeyPress and ev.key() == Qt.Key_C \
                and ev.modifiers() in (Qt.ControlModifier, Qt.MetaModifier) and not self.search_edit.hasSelectedText():
            if self._copy_files():  # a clip's file, as a file manager copies it - to paste in Resolve
                return True
        # In the search, keys write. In the list - once you've moved down into
        # it - Space plays and the arrows to the sides move through what's playing.
        self._note_where(ev)
        if ev.key() == Qt.Key_Space and ev.modifiers() == Qt.NoModifier and self._space_plays():
            self._in_list or self._set_in_list(True)  # it played: the next Space plays too
            self.space_play(held=ev.isAutoRepeat())
            return True
        if self._in_list:
            for action, seconds in (("list_seek_back", -1), ("list_seek_forward", 1),
                                    ("list_seek_back_far", -5), ("list_seek_forward_far", 5)):
                if matches(action) and self._seek_playing(seconds):
                    return True

        # an action you've given a key (Settings > Keybindings > Actions, or right-click its tile)
        if any(kb.get(name) or kb2.get(name) for name in ACTION_KEY_BY_LABEL.values()):
            for _g, label, key, fn in self._actions():
                if key.startswith("act_") and matches(key):
                    fn()
                    return True

        if matches("preview_large"):
            if not ev.isAutoRepeat():
                opened = self.toggle_big_preview()
                self._big_key = (ev.key(), time.monotonic()) if opened else None
            return True
        if matches("cancel") and self._big is not None and self._big.isVisible():
            self.toggle_big_preview(False)
            return True
        if matches("cancel") and self.tag_strip.isVisible():
            self.close_tags()
            return True
        if matches("cancel") and self._swap is not None:  # Esc: the swap is off, the picker stays
            self.end_swap()
            return True
        if matches("cancel"):
            self.cancel()
            return True
        from .fonts import zoom_key
        direction = zoom_key(ev, self.settings)
        if direction is not None:  # Ctrl and + / - / 0: the picker by itself larger, smaller, as it ships
            placed = getattr(self, "_placed", None)
            if placed is not None and hasattr(placed, "zoom_window"):
                # Insert as / History in the picker's place, the keyboard still in the search: theirs - it zoomed the
                # picker, so only their words changed size (2026-10-21: "I have to click on an empty space")
                placed.zoom_window(direction)
            else:
                self.zoom_window(direction)
            return True
        if matches("toggle_settings"):
            self.open_settings()
            return True
        if matches("toggle_insert_options"):
            self.open_insert_options()
            return True
        if matches("toggle_history"):
            self.open_history()
            return True
        if matches("refresh"):
            self.refresh_rows()
            return True
        if matches("play_pause"):
            self.play_pause()
            return True
        if self.preview_panel.isVisible() and (matches("mark_in") or matches("mark_out") or matches("clear_marks")):
            self._mark("in" if matches("mark_in") else "out" if matches("mark_out") else None)
            return True
        if self.preview_panel.isVisible() and (matches("seek_back") or matches("seek_forward")):
            self.video.seek_relative(-5 if matches("seek_back") else 5)
            return True
        if matches("preview_audio"):
            self.toggle_listening()
            return True
        if matches("confirm_sequential"):
            self.confirm(sequential=True)
            return True
        if matches("insert_video_only") or matches("insert_audio_only"):
            self.confirm_only("video" if matches("insert_video_only") else "audio")
            return True
        if matches("insert_compound"):
            self.confirm_compound()
            return True
        if matches("confirm"):
            self.confirm()
            return True
        if matches("show_info"):
            self.toggle_info()
            return True
        if matches("mark_loop"):
            self.mark_loop()
            return True
        if matches("similar_sounds"):
            self.similar_sounds()
            return True
        if matches("tag_clip"):
            self.close_tags() if self.tag_strip.isVisible() else self.open_tags()
            return True
        for level in (1, 2, 3):
            if matches(f"energy_{level}"):
                self.set_energy(level)
                return True
        if matches("place_at_markers"):
            self.place_at("markers")
            return True
        if matches("place_at_cuts"):
            self.place_at("cuts")
            return True
        if matches("reveal_only"):
            self.reveal_only()
            return True
        if matches("reveal_keep_open"):
            self.reveal_only(keep_open=True)
            return True
        if matches("show_in_file_manager"):
            self.show_in_file_manager()
            return True
        if matches("preview"):
            self.preview_clip()
            return True
        if matches("increment_staged"):
            self.increment_staged()
            return True
        if matches("decrement_staged"):
            self.decrement_staged()
            return True
        if matches("toggle_staged"):
            self.toggle_staged()
            return True
        if matches("toggle_favorite"):
            self.toggle_favorite()
            return True
        if matches("history_prev"):
            self._history_step(1)
            return True
        if matches("history_next"):
            self._history_step(-1)
            return True
        if matches("select_to_bottom"):
            self._select_to_edge(bottom=True)
            return True
        if matches("select_to_top"):
            self._select_to_edge(bottom=False)
            return True
        if matches("jump_to_bottom"):
            self._jump_to_edge(bottom=True)
            return True
        if matches("jump_to_top"):
            self._jump_to_edge(bottom=False)
            return True
        if matches("select_extend_down"):
            self._extend_selection(1)
            return True
        if matches("select_extend_up"):
            self._extend_selection(-1)
            return True
        # Shift/Ctrl are excluded here since they're already handled by
        # the dedicated selection checks above — any other modifier (or
        # none), including Alt, still falls through to plain navigation.
        no_selection_modifier = not (ev.modifiers() & (Qt.ShiftModifier | Qt.ControlModifier))
        if ev.key() == Qt.Key_Down and no_selection_modifier:
            self._history = None  # Down moves into the results (Alt+Shift+Down goes to newer searches)
            self._select_row(self.list_view.currentIndex().row() + 1)
            return True
        if ev.key() == Qt.Key_Up and no_selection_modifier:
            self._select_row(self.list_view.currentIndex().row() - 1)
            return True

        # User-configurable per-prefix keybinds (Settings -> Search
        # Prefixes) — empty by default for every target, so this loop is
        # a no-op unless the person actually set one.
        for target, seq_str in self.settings.prefix_keybinds.items():
            if seq_str and _seq_matches(ev, seq_str):
                self.toggle_search_prefix(target)
                return True
        return False

    def open_settings(self, page=None, key=None, field=None):
        """page: the page to open on, by its title ("Appearance") - else where it was last. key: a keybind's name -
        Keybindings, at that key, its box ready for the new one (right-click an action > Change key). field: a
        setting on that page (SettingsDialog.go_to_field), its row lit."""
        dialog = SettingsDialog(self.settings, self)
        index = next((i for i, (title, _icon, _builder) in enumerate(SettingsDialog.PAGES)
                      if title == ("Keybindings" if key else page)), None)
        if index is not None:
            dialog._show_page(index)
        if key:
            QTimer.singleShot(0, lambda: dialog.go_to_key(key))
        elif field and index is not None:
            QTimer.singleShot(0, lambda: dialog.go_to_field(index, field))
        dialog.settingsChanged.connect(self._schedule_apply_theme)
        dialog.exec()
        # (thrown away, not kept hidden in the picker: each one kept was ~2000 more widgets that every zoom step and
        # theme change restyled - half a second a step, more with every time Settings had been opened)
        dialog.deleteLater()
        self.apply_theme()
        self.model.page_hides = self.settings.hidden_categories(self._page_seen or "other")
        if getattr(dialog, "next_action", None) == "insert_options":
            self.open_insert_options()
            return
        self.search_edit.setFocus()

    def _sample_rows(self):
        """The rows the next insert would use, in order (staged ones as often as staged, or the highlighted
        one) - a bin or Selected Clips as the clips in it, so Insert as knows what they hold."""
        indices = [i for i, count in self.model.staged.items() for _ in range(count)]
        if not indices:
            orig = self._current_orig_index()
            if orig is not None and not self._is_external_row(orig) and orig < len(self.model.clip_rows):
                indices = [orig]
        out = []
        for i in indices:
            if i >= len(self.model.rows):
                continue
            category = self.model.rows[i].category
            out.extend(self._rows_inside(i) if category in ("bin", "selected") else [i])
        return out

    def _rows_inside(self, i):
        """The clip rows of a bin (its sub-bins too, when a bin inserts them) or of Selected Clips - in the
        order an insert takes them. A bin from the scan, without asking Resolve."""
        groups = self.session.get("filtered_group_list") or []
        if i >= len(groups):
            return []
        name, instances, category = groups[i]
        if getattr(self, "_row_of", (None,))[0] is not groups:  # media id -> its row (made once per list)
            made = {}
            for n, (_name, members, kind) in enumerate(groups):
                if kind not in ("bin", "selected"):
                    for member in members:
                        made.setdefault(member[0], n)
            self._row_of = (groups, made)
        row_of = self._row_of[1]
        if category == "selected":
            try:
                ids = [item.GetMediaId() for item in self.session["media_pool"].GetSelectedClips() or []]
            except Exception:
                return []
            ordered = [m for m in self.selection_order_ids if m in ids] + \
                [m for m in ids if m not in self.selection_order_ids]
            return [row_of[m] for m in ordered if m in row_of]
        path = tuple(instances[0][0])
        deep = self.settings.general["bin_insert_recursive"]
        inside = []
        for media_id, where in (self.session.get("id_paths") or {}).items():
            where = tuple(where or ())
            if (where[:len(path)] == path if deep else where == path) and media_id in row_of:
                inside.append(row_of[media_id])
        return inside

    def _preview_sample(self):
        """The clips the next insert would use (staged, or the highlighted
        one), as (kind, frames, name) - for Insert as's timeline preview."""
        fps = 30.0
        try:
            timeline = self.session.get("timeline")
            if timeline is not None:
                fps = float(timeline.GetSetting("timelineFrameRate")) or 30.0
        except Exception:
            pass
        sample, paths = [], []  # (paths: each one's file, for its sound - At every marker)
        for i in self._sample_rows()[:200]:  # (the drawing fits its lanes to however many there are)
            row = self.model.rows[i]
            kind = "audio" if row.category == "audio" else "still" if row.category == "image" else "video"
            secs = float(getattr(row, "secs", 0) or 0) or (2.0 if kind == "audio" else 10.0)
            sample.append((kind, max(1, int(round(secs * fps))), row.name))
            paths.append(getattr(row, "source", "") or "")
        return sample, fps, paths

    def _preview_shapes(self):
        """(width, height) of each staged picture, in the order they go on - for Insert as's frame, which
        shows a square logo with the room a square has. The first 24: what the frame draws."""
        shapes, known = [], {}
        for i in self._sample_rows():
            if len(shapes) >= 24:
                break
            if self.model.rows[i].category == "audio":
                continue
            if i not in known:
                known[i] = None
                try:
                    item = rc.expand_row_to_items(self.session, self.settings, i, self.selection_order_ids)[0][0]
                    w, h = (float(v) for v in str(item.GetClipProperty("Resolution")).lower().replace(" ", "").split("x")[:2])
                    known[i] = (w, h) if w > 0 and h > 0 else None
                except Exception:
                    pass
            shapes.append(known[i])
        return shapes

    def open_insert_options(self):
        sample, fps, paths = self._preview_sample()
        markers, events = {}, None
        try:  # the markers on this timeline (counted by colour - for At every marker), and its cuts
            timeline = self.session.get("timeline")
            found = self._timeline_markers(timeline)
            for colour in found.values():
                markers[colour] = markers.get(colour, 0) + 1
            events = {"markers": found, "clips_by_track": self._clips_by_track(timeline),
                      "start": int(timeline.GetStartFrame()),
                      "playhead": rc.tc_to_frame(timeline.GetCurrentTimecode(), fps),
                      "now": self._timeline_layout(timeline)}
        except Exception:
            markers = None  # no timeline open
        dialog = InsertAsDialog(self.settings, self, sample=sample, fps=fps, markers=markers,
                                shapes=self._preview_shapes() if sample else None, paths=paths, events=events)
        self._in_place(dialog, self.INSERT_AS_ROOM, "insert_as")
        self.settings.save()
        self.hints_label.set_hints(self._footer_hints())
        if getattr(dialog, "next_action", None) == "settings":
            self.open_settings()
            return
        if getattr(dialog, "insert_now", False):
            self.confirm()
            return
        self.search_edit.setFocus()

    def _placed_rect(self):
        """Where a dialog in the picker's place goes: over the list - and over the preview too while it shares the
        picker's space (2026-10-17), not beside it as a card of its own."""
        from PySide6.QtCore import QRect
        mapped = lambda w: QRect(w.mapTo(self, w.rect().topLeft()), w.size())  # (in the window, wherever they sit)
        rect = mapped(self.picker_column)
        if self.preview_panel.isVisible() and self._preview_docked() and self._mode() in self.SHARING:
            rect = rect.united(mapped(self.preview_panel))
        return rect

    INSERT_AS_ROOM = (720, 560)  # the least room Insert as needs in the picker's place, at its own 100 %
    HISTORY_ROOM = (520, 420)    # ...and History

    def _in_place(self, dialog, room, zoom_of=None):
        """A dialog in the picker's own place instead of a window of its own (2026-10-17, of Insert as: "I
        actually quite like that it takes over the space of the picker"; History too - "like the actions"): over the
        list as the Actions panel is, in the picker's colour and corners. Where there isn't `room` the window grows
        while it's there, and goes back after - unless it was resized meanwhile. Waits until it's done, as exec()
        did; the picker closing closes it too."""
        from PySide6.QtCore import QEventLoop
        from .fonts import picker_scale, window_zoom, zoom
        before = (self.width(), self.height())
        k = zoom(self.settings) * (window_zoom(self.settings, zoom_of) if zoom_of else 1.0)  # (the dialog's own size)
        col = self._placed_rect()
        grow_w = max(0, round(room[0] * k) - col.width())
        grow_h = max(0, round(room[1] * k) - col.height())
        screen = self.screen().availableGeometry() if self.screen() else None
        if screen is not None:
            grow_w = max(0, min(grow_w, screen.width() - self.width()))
            grow_h = max(0, min(grow_h, screen.height() - self.height()))
        if grow_w or grow_h:
            self._set_size(self.width() + grow_w, self.height() + grow_h)
            QApplication.processEvents()
        grown = (self.width(), self.height())
        dialog.setParent(self, Qt.Widget)
        t, radius = self.settings.theme, float(self.settings.display.get("outer_corner_radius", 9)) * picker_scale(self.settings)
        dialog.in_place_css = f"""
            QDialog#AppDialog {{ background: {t['picker_bg']}; border: none; border-radius: {radius:.0f}px; }}"""
        dialog.setStyleSheet(dialog.styleSheet() + dialog.in_place_css)  # (said again after a zoom: Ctrl + / -)
        dialog.setGeometry(self._placed_rect())
        self._placed = dialog
        loop = QEventLoop()
        dialog.finished.connect(loop.quit)
        gone = QTimer(self)
        gone.timeout.connect(lambda: None if self.isVisible() else dialog.reject())
        gone.start(250)
        dialog.show()
        dialog.raise_()
        (getattr(dialog, "grid", None) or getattr(dialog, "filter", None) or dialog).setFocus()
        loop.exec()
        gone.stop()
        self._placed = None
        dialog.hide()
        dialog.deleteLater()
        if (grow_w or grow_h) and (self.width(), self.height()) == grown and self.isVisible():
            self._set_size(*before)

    def open_history(self):
        from . import history_dialog
        page = "fusion" if self._current_page_key() == "fusion" else "edit"  # (each page its own History)
        dialog = HistoryDialog(self.history, self.settings, self, project=self.session.get("project_name"),
                               changed=lambda: history_dialog.save(self.history), page=page)
        self._in_place(dialog, self.HISTORY_ROOM)
        if dialog.selected_entry is not None:
            self.restore_history_entry(dialog.selected_entry)
        self.search_edit.setFocus()

    def restore_history_entry(self, entry):
        """History: the clips of that insert staged again - and Insert as set up the way it was, to
        see, change and use for the next insert. The Fusion page's: its nodes and macros staged in the same
        order, its clips too; an expression is found in the list, highlighted."""
        if entry.get("page") == "fusion":
            self._restore_fusion_entry(entry)
            return
        how = presets_mod.restore(self.settings, entry.get("preset")) if entry.get("preset") else ""
        self.settings.save()
        self._preset_once = None
        self._restore_staged_by_name(entry["clip_names"])
        self.hints_label.set_hints(self._footer_hints())
        if how:
            self._flash_hint(f"Insert as is set up as it was: {how}", 5000)
        print(f"Restored from history: {entry['summary']}")

    def _restore_fusion_entry(self, entry):
        items = entry.get("items") or []
        expressions = [item for item in items if item["kind"] == "expression"]
        if expressions and len(items) == 1:
            self.search_edit.setText(f"x: {expressions[0]['name']}")
            self._select_row(next((n for n, i in enumerate(self.model.visible)
                                   if self.model.rows[i].path == expressions[0].get("path")), 0))
            return
        clips = {}
        for item in items:
            if item["kind"] == "clip":
                clips[item["name"]] = clips.get(item["name"], 0) + 1
        self._restore_staged_by_name(clips)
        self.model.chain[:] = []
        self._clip_seq = {}
        rows_by_name = {self.model.clip_rows[i].name: i for i in self.model.staged}
        for item in items:  # in the order they went in - nodes, macros and clips in one line again
            if item["kind"] in ("node", "macro"):
                self.model.chain.append({"key": f"{item['kind']}:{item.get('path') or item['name']}",
                                         "category": item["kind"], "path": item.get("path"), "name": item["name"],
                                         "seq": self._next_seq()})
            elif item["kind"] == "clip" and item["name"] in rows_by_name:
                self._clip_seq.setdefault(rows_by_name[item["name"]], self._next_seq())
        self._update_staged_summary()
        self.list_view.viewport().update()
        print(f"Restored from history: {entry['summary']}")

    def _record_fusion_history(self, items):
        """What went into a composition, for the Fusion page's History: [(kind, name, path)] - kind "node",
        "macro", "expression" or "clip" - in the order it went in."""
        items = [{"kind": kind, "name": name, "path": path} for kind, name, path in items if name]
        if not items:
            return
        from . import history_dialog
        names = {}
        for item in items:
            names[item["name"]] = names.get(item["name"], 0) + 1
        self.history.append({"timestamp": time.time(), "project": self.session.get("project_name") or "",
                             "page": "fusion", "clip_names": names, "items": items,
                             "summary": history_dialog.fusion_summary(items)})
        self.history[:] = history_dialog.save(self.history)

    def _record_history(self, indices, preset=None):
        """Called right as an insert is kicked off — records intent, not
        confirmed per-clip success (matches how insert failures already
        just print and move on rather than halting the batch)."""
        name_counts = {}
        for i in indices:
            if i is not None and i < len(self.model.clip_rows):
                name = self.model.clip_rows[i].name
                name_counts[name] = name_counts.get(name, 0) + 1
        if not name_counts:
            return
        total = sum(name_counts.values())
        how = ""
        if preset and preset.get("id") not in ("normal", "history", None):
            how = f" as {preset['name']}"
        elif preset and not presets_mod.plain(preset):  # Normal, set up for this insert: say how
            how = f" - {presets_mod.summary(preset)}"
        entry = {
            "timestamp": time.time(),
            "project": self.session.get("project_name") or "",
            "clip_names": name_counts,
            "preset": {k: v for k, v in preset.items() if k not in ("builtin", "group", "edited")} if preset else None,
            "summary": f"{total} clip{'s' if total != 1 else ''}{how}",
        }
        from . import history_dialog
        self.history.append(entry)
        self.history[:] = history_dialog.save(self.history)  # (kept on disk: a restart of the service keeps it)

    # -- listening to sounds --
    def toggle_listening(self):
        """Listening on: the highlighted sound plays, and moving to another
        sound plays that one. Off: silence."""
        if self._audio_follow:
            self._stop_audio()
            return
        self._close_preview()
        self._audio_follow = True
        self._audio_follow_current()

    def _stop_audio(self):
        self.sound.stop()
        self._audio_follow = False
        self._audio_timer.stop()
        self.audio.stop()

    def _set_volume(self, volume):
        volume = max(0, min(100, int(volume)))
        self.settings.listen["volume"] = volume
        self.audio.volume = volume
        self.preview_panel.volume.set_value(volume)
        self._volume_save.start(400)  # dragging the slider: save once it rests


    def _audio_follow_current(self, restart=False):
        """Plays the highlighted row if it's a sound, otherwise stays quiet.
        restart=True plays it again from the start even if it's playing."""
        orig_index = self._current_orig_index()
        row = self.model.rows[orig_index] if orig_index is not None and orig_index < len(self.model.rows) else None
        if row is None or row.category != "audio" or orig_index >= len(self.session.get("filtered_group_list", [])):
            self.audio.stop()
            return
        path = self._row_file_path(orig_index)
        if path and path == self.audio.current_path and self.audio.playing and not restart:
            return
        self.sound.stop()
        problem = self.audio.play(path)
        if problem:
            print(problem)
            self._flash_hint(problem)

    def _flash_hint(self, text, ms=3500):
        self.hints_label.setText(text)
        # one timer for it: a hint shown a moment ago mustn't take this one away early
        if getattr(self, "_hint_back", None) is None:
            self._hint_back = QTimer(self)
            self._hint_back.setSingleShot(True)
            self._hint_back.timeout.connect(lambda: self.hints_label.set_hints(self._footer_hints()))
        self._hint_back.start(ms)

    def hideEvent(self, event):
        if self._swap_picking is None:  # (stepping aside for a click in Resolve keeps the swap)
            self.end_swap()
        self.tag_strip.hide()
        self.expression_sheet.hide()
        self.actions_panel.hide()
        self.actions_panel._slide = 0.0
        self._page_timer.stop()
        self._stop_audio()
        if self._popped_out() and self.settings.listen.get("preview_stay"):
            if self.video.is_video and not self.video.paused:
                self.video.toggle_pause()  # the window stays, on the frame it was showing - quietly
        else:
            self._close_preview()
        super().hideEvent(event)
        QTimer.singleShot(1500, self._give_memory_back)
        front, self._front_app = getattr(self, "_front_app", None), None
        if getattr(self, "_keep_focus_elsewhere", False):
            self._keep_focus_elsewhere = False  # e.g. a file manager window was just opened
        elif front is not None:
            QTimer.singleShot(0, lambda: give_focus_back(front))

    def _give_memory_back(self):
        """A moment after the picker closes: what the preview needed (video
        frames, sound) goes back to the system instead of staying with the
        service while you edit. Python and the C library otherwise keep
        freed memory for themselves - hundreds of MB after a few previews."""
        if self.isVisible() or self._popped_out():
            return
        import gc
        gc.collect()
        if platform.system() == "Linux":
            try:
                import ctypes
                ctypes.CDLL("libc.so.6").malloc_trim(0)
            except (OSError, AttributeError):
                pass  # not glibc (musl ...): nothing to do

    # -- where the picker sits: drag it anywhere, it opens there again --
    def _place_window(self):
        """Opens where you last dragged it (if that's still on a screen), or
        in the middle of the screen the mouse is on."""
        pos = self.settings.display.get("picker_pos") or []
        if self.settings.g("remember_position") and len(pos) == 2:
            from PySide6.QtCore import QRect
            from PySide6.QtGui import QGuiApplication
            target = QRect(int(pos[0]), int(pos[1]), self.width(), self.height())
            if any(sc.availableGeometry().contains(target.center()) for sc in QGuiApplication.screens()):
                self.move(target.topLeft())
                self._keep_on_screen()
                return
        from PySide6.QtGui import QCursor, QGuiApplication
        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        area = screen.availableGeometry()
        self.move(area.x() + (area.width() - self.width()) // 2, area.y() + (area.height() - self.height()) // 2)

    EDGE = 7  # px from the picker's border where a drag resizes instead of moving

    def _edges_at(self, pos):
        """Which edges `pos` (picker coordinates) is on - for resizing. With the preview beside it, the window's own
        edges: the two grow and shrink together (_follow_window - 2026-10-16: "I want to be able to do
        both")."""
        if self._slot_held():
            return None
        beside = self.preview_panel.isVisible() and self._preview_docked()
        r = self.rect() if beside or self._shares() else self.picker_column.geometry()
        e = Qt.Edges()
        if abs(pos.x() - r.left()) <= self.EDGE:
            e |= Qt.LeftEdge
        elif abs(pos.x() - r.right()) <= self.EDGE:
            e |= Qt.RightEdge
        if abs(pos.y() - r.top()) <= self.EDGE:
            e |= Qt.TopEdge
        elif abs(pos.y() - r.bottom()) <= self.EDGE:
            e |= Qt.BottomEdge
        return e if e != Qt.Edges() else None

    _EDGE_CURSORS = None

    def _cursor_for(self, edges):
        if edges is None:
            return None
        horizontal = bool(edges & (Qt.LeftEdge | Qt.RightEdge))
        vertical = bool(edges & (Qt.TopEdge | Qt.BottomEdge))
        if horizontal and vertical:
            main = (edges & Qt.LeftEdge and edges & Qt.TopEdge) or (edges & Qt.RightEdge and edges & Qt.BottomEdge)
            return Qt.SizeFDiagCursor if main else Qt.SizeBDiagCursor
        return Qt.SizeHorCursor if horizontal else Qt.SizeVerCursor

    def eventFilter(self, obj, event):
        """Edge cursors over the search area and bottom bar (where a drag
        resizes the picker)."""
        from PySide6.QtCore import QEvent
        if event.type() == QEvent.MouseMove and not event.buttons():
            pos = obj.mapTo(self, event.position().toPoint())
            cursor = self._cursor_for(self._edges_at(pos))
            if cursor is None:
                obj.unsetCursor()
            else:
                obj.setCursor(cursor)
        elif event.type() == QEvent.Leave and isinstance(obj, QWidget):
            obj.unsetCursor()  # (left from the edge: no move inside came to take the resize pointer back)
        return super().eventFilter(obj, event)

    def mousePressEvent(self, event):
        """A press on an empty spot (bottom bar, around the search box)
        drags the whole picker; on its very edge it resizes it. The window
        system does the moving, so it feels native on macOS, Windows, X11
        and Wayland; where it can't, we move/resize it ourselves."""
        if event.button() == Qt.LeftButton and self.windowHandle() is not None:
            edges = self._edges_at(event.position().toPoint())
            if edges is not None:
                self._resizing = True
                if self.windowHandle().startSystemResize(edges):
                    return
                self._resize_from = (event.globalPosition().toPoint(), self.geometry(), edges)
                return
            self._dragging = True
            if self.windowHandle().startSystemMove():
                return
            self._drag_from = event.globalPosition().toPoint() - self.pos()  # fallback: move it ourselves
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        start = getattr(self, "_drag_from", None)
        if start is not None and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - start)
            return
        resize = getattr(self, "_resize_from", None)
        if resize is not None and event.buttons() & Qt.LeftButton:
            origin, geo, edges = resize
            d = event.globalPosition().toPoint() - origin
            g = QRect(geo)
            min_w, min_h = 480, 300
            if edges & Qt.LeftEdge:
                g.setLeft(min(g.left() + d.x(), g.right() - min_w))
            if edges & Qt.RightEdge:
                g.setRight(max(g.right() + d.x(), g.left() + min_w))
            if edges & Qt.TopEdge:
                g.setTop(min(g.top() + d.y(), g.bottom() - min_h))
            if edges & Qt.BottomEdge:
                g.setBottom(max(g.bottom() + d.y(), g.top() + min_h))
            self.setGeometry(g)
            return
        if not event.buttons():
            cursor = self._cursor_for(self._edges_at(event.position().toPoint()))
            self.setCursor(cursor) if cursor is not None else self.unsetCursor()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_from = None
        self._resize_from = None
        super().mouseReleaseEvent(event)

    def leaveEvent(self, event):
        if not QApplication.mouseButtons():
            self.unsetCursor()  # (left from the edge: the resize pointer doesn't stay for the next visit)
        super().leaveEvent(event)

    def moveEvent(self, event):
        super().moveEvent(event)
        if getattr(self, "_dragging", False) or getattr(self, "_resizing", False):
            self._schedule_place_save()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._hold_size():
            return  # not the size it's meant to have: asked for again, the next one counts
        self._follow_window(event)
        self._place_seam()
        if getattr(self, "tour", None) is not None and self.tour.isVisible():
            self.tour.setGeometry(self.picker_column.geometry())
        if getattr(self, "_resizing", False):
            self._schedule_place_save()
        self._note_cramped()
        for overlay in (getattr(self, "sheet", None), getattr(self, "expression_sheet", None)):
            if overlay is not None and overlay.isVisible():
                overlay.setGeometry(self.picker_column.geometry())
        if getattr(self, "actions_panel", None) is not None and self.actions_panel.isVisible():
            self.actions_panel.setGeometry(self._placed_rect())
        if getattr(self, "_placed", None) is not None and self._placed.isVisible():
            self._placed.setGeometry(self._placed_rect())

    LEAST = (360, 240)  # the picker by itself, at 100 %

    def _set_least_size(self):
        """The smallest the window may get: the picker alone, or with the preview beside it the smallest list, the
        gap and the smallest preview."""
        from .fonts import picker_size_scale
        k = picker_size_scale(self.settings)
        width = round(self.LEAST[0] * k)
        if self.preview_panel.isVisible() and self._preview_docked() and not self._slot_held():
            width = self._picker_min_width() + self._gap() + self._preview_min_width()
        self.setMinimumSize(width, round(self.LEAST[1] * k))

    def _follow_window(self, event):
        """The window got a size the picker didn't give it - an edge dragged, Sway's Super + right-drag, a window
        rule: the list and the preview beside it grow and shrink together, each keeping its share of the width
        (2026-10-16: "they should work in unison"), neither under its smallest. Sizes the picker gives
        itself (the preview opening, closing) are left to the layout."""
        if not (self.preview_panel.isVisible() and self._preview_docked()) or self._slot_held():
            return
        gap = self._gap()
        fits = self.picker_column.width() + gap + self.preview_panel.width() == self.width()
        if self._wanted_size is not None and self.size() == self._wanted_size and fits:
            return  # (its own, and the parts add up)
        old = event.oldSize().width()
        if old <= 0 or (old == self.width() and fits):
            return
        before = old - gap
        share = max(0.05, min(0.95, (before - self.preview_panel.width()) / max(1, before)))
        room = self.width() - gap
        picker = max(self._picker_min_width(), min(round(room * share), room - self._preview_min_width()))
        self.preview_panel.setFixedWidth(max(self._preview_min_width(), room - picker))
        if not self._shares():  # (next to it the list's width is fixed - in its space it takes what's left by itself)
            self.picker_column.setFixedWidth(picker)
            self._picker_w = picker
        else:
            self._grown_from = None  # (your size now: closing the preview keeps it - it went back to the one before)
        self.layout().activate()  # (the list's new room, before what lies over it follows)

    SIZE_SETTLE_SECONDS = 1.0  # how long the picker insists on a size it just gave itself
    SIZE_TRIES = 40

    def _set_size(self, width, height):
        """The picker gives its window a new size (room for the preview
        beside it, or without). Every such change goes through here.

        A window system may hand back the size from before: on Wayland the
        compositor sends its idea of the size along with every change of
        focus, Qt takes that as an order, tells the compositor, which
        answers again... The two sizes then chase each other for a while
        and either one wins - the preview on top of the list, or a picker
        as wide as both. So for a moment after a change the picker holds
        on to the size it chose (see _hold_size)."""
        if getattr(self, "_resizing", False):  # an edge was dragged a moment ago (or only clicked): that's over
            timer = getattr(self, "_pos_timer", None)
            if timer is not None and timer.isActive():
                timer.stop()
                self._remember_position()
            self._resizing = False
        self._wanted_size = QSize(int(width), int(height))
        self._wanted_until = time.monotonic() + self.SIZE_SETTLE_SECONDS
        self._size_tries = 0
        self.resize(self._wanted_size)

    def _hold_size(self):
        """From resizeEvent: True if the window just got a size other than
        the one it gave itself a moment ago, and asked for that one again.
        Dragging an edge is your size, and one that keeps coming back
        (a tiling window manager) is the window system's - those stand."""
        if not hasattr(self, "preview_panel") or not hasattr(self, "_preview_slot"):
            return False  # still being built
        wanted = self._wanted_size
        if wanted is not None and self.size() != wanted:
            if (not getattr(self, "_resizing", False) and not (self.windowState() & (Qt.WindowMaximized | Qt.WindowFullScreen))
                    and time.monotonic() < self._wanted_until and self._size_tries < self.SIZE_TRIES):
                self._size_tries += 1
                self.resize(wanted)
                return True
            self._wanted_size = None
        if not self._grows_window():
            self._picker_w = self.width()
        return False

    def _note_cramped(self):
        """For the log: the window came out narrower than the picker and the
        preview beside it need (the preview then sits on top of the list) -
        with what the compositor was asked for, to find out why."""
        if not hasattr(self, "preview_panel") or not hasattr(self, "_preview_slot"):
            return  # still being built
        if not self._grows_window():
            return
        other = self._preview_slot.width() if self._slot_held() else self.preview_panel.width()
        need = self.picker_column.maximumWidth() + self._gap() + other
        if self.picker_column.maximumWidth() < 16777215 and self.width() < need - 2:
            print(f"[preview] the window is {self.width()} wide but needs {need} "
                  f"(picker {self.picker_column.maximumWidth()} + preview {other}) - the preview overlaps the list")

    def _schedule_place_save(self):
        if not hasattr(self, "_pos_timer"):
            self._pos_timer = QTimer(self)
            self._pos_timer.setSingleShot(True)
            self._pos_timer.timeout.connect(self._remember_position)
        self._pos_timer.start(400)

    def _remember_position(self):
        """After a drag or resize: where the picker is and how big, so it
        opens like that next time (Settings -> Appearance -> Window -> Reset
        position and size goes back to automatic)."""
        resized = getattr(self, "_resizing", False)
        self._dragging = self._resizing = False
        from PySide6.QtGui import QGuiApplication
        if resized:
            self._keep_size()
        if not QGuiApplication.platformName().startswith("wayland"):  # Wayland doesn't say where windows are
            x = self.x() + self.picker_column.x()  # the picker itself, not a preview on its left
            self.settings.display["picker_pos"] = [x, self.y()]
        self.settings.save()

    def _keep_size(self):
        """The size the window has now is the one it opens with from now on (an edge dragged, a zoom)."""
        room = _screen_area(self.frameGeometry()).width()
        if not (self.windowState() & (Qt.WindowMaximized | Qt.WindowFullScreen)) and self.width() <= room:
            # (a size wider than the screen, or a maximised window, is the window system's - a tiling layout -
            # not one you chose; once 1922 px was kept that way)
            beside = self.preview_panel.isVisible() and self._preview_docked() and not self._slot_held()
            if beside:  # (the two grew together: the preview's width is kept too)
                from .fonts import picker_size_scale
                self.settings.listen["preview_width"] = round(self.preview_panel.width() / picker_size_scale(self.settings))
            if self._shares():
                self.settings.display["window_width"] = min(self.width(), room)
            else:
                most = room - (self._gap() + self.preview_panel.width() if beside else 0)
                width = max(self._picker_min_width(), min(self.picker_column.width(), most))
                self.settings.display["window_width"] = width
                if beside:
                    self.picker_column.setFixedWidth(width)
                    self._picker_w = width
            self.settings.display["window_height"] = self.height()

    def reset_place(self):
        """Settings -> Reset position and size: automatic size, centred."""
        width, height = self.window_size()
        self.picker_column.setMinimumWidth(0)
        self.picker_column.setMaximumWidth(16777215)
        self._picker_w = width
        self._set_size(width, height)
        if self.isVisible():
            self._place_window()

    def changeEvent(self, event):
        """Clicking outside: the picker stays open (unless Settings says
        otherwise) - it only closes when another app is clicked, never for
        its own preview window or Settings."""
        from PySide6.QtCore import QEvent
        super().changeEvent(event)
        if event.type() == QEvent.ActivationChange and self.isActiveWindow():
            # Insert as / Settings / History open over it: a click on the picker gives the keyboard back
            # to the dialog (on Sway the window under a dialog takes it otherwise)
            QTimer.singleShot(0, self._back_to_dialog)
        if event.type() == QEvent.ActivationChange and self.isVisible() and not self.isActiveWindow() \
                and self.settings.g("close_on_click_outside") and self._swap is None:  # (a swap: you click in Resolve)
            QTimer.singleShot(150, self._close_if_app_inactive)

    def _back_to_dialog(self):
        modal = QApplication.activeModalWidget()
        if modal is not None and modal is not self and modal.isVisible() and self.isActiveWindow():
            modal.raise_()
            modal.activateWindow()

    def _close_if_app_inactive(self):
        if self.isVisible() and QApplication.activeWindow() is None:
            self._front_app = None  # the click already went where you wanted
            self.cancel_all()

    def cancel_all(self):
        """Closes the preview and the picker together (keeps the search history and staged clips as Esc would)."""
        if not self.settings.g("keep_staged"):
            self.model.clear_staged()
        self._update_staged_summary()
        self._clear_multi_selection()
        self.hide()

    def cancel(self):
        if self.settings.g("esc_clears_search_first") and self.search_edit.text():
            self.search_edit.clear()
            return
        if self.preview_panel.isVisible() and not self.settings.g("esc_closes_everything"):
            self._close_preview()  # Esc closes the preview first
            return
        if not self.settings.g("keep_staged"):
            self.model.clear_staged()
        self._update_staged_summary()
        self._clear_multi_selection()
        self.hide()

    # -- staging --
    def toggle_staged(self):
        multi = [i for i in self._get_multi_selected_orig_indices() if not self._is_external_row(i)]
        if len(multi) > 1:
            all_already_staged = all(i in self.model.staged for i in multi)
            for i in multi:
                if all_already_staged:
                    self.model.staged.pop(i, None)
                elif i not in self.model.staged:
                    self.model.staged[i] = 1
            self._update_staged_summary()
            self.list_view.viewport().update()
            return
        orig_index = self._current_orig_index()
        if orig_index is None:
            return
        if self._is_external_row(orig_index):
            self._chain_change(orig_index, "toggle")
            return
        if orig_index not in self.model.staged:
            self._clip_seq[orig_index] = self._next_seq()
        self.model.toggle_staged(orig_index)
        self._update_staged_summary()
        self.list_view.viewport().update()

    # -- Fusion: staged nodes / macros, added in order --
    def _next_seq(self):
        self._stage_seq = getattr(self, "_stage_seq", 0) + 1
        return self._stage_seq

    def _chain_change(self, orig_index, how):
        """Tab / Ctrl+Tab / Ctrl+Shift+Tab on a Fusion node or macro row:
        it joins (or leaves) the chain that Enter adds in order."""
        row = self.model.rows[orig_index]
        if row.category not in ("node", "macro"):
            return
        key = f"{row.category}:{row.path or row.name}"
        chain = self.model.chain
        if how == "toggle" and any(e["key"] == key for e in chain):
            chain[:] = [e for e in chain if e["key"] != key]
        elif how == "remove_one":
            for n in range(len(chain) - 1, -1, -1):
                if chain[n]["key"] == key:
                    del chain[n]
                    break
        else:
            chain.append({"key": key, "category": row.category, "path": row.path, "name": row.name,
                          "seq": self._next_seq()})
        self._update_staged_summary()
        self.list_view.viewport().update()

    def toggle_favorite(self):
        """Ctrl+F — stars/unstars the highlighted row (or the whole
        multi-selection at once, same pattern as Tab). Persisted to disk
        immediately (unlike staged clips, which are session-only), so
        find:st later brings it back across restarts too. Identified by
        clip name via filtered_group_list, not the display name, since
        bin rows carry a "(N)" count suffix that shouldn't be part of
        the saved key."""
        multi = self._get_multi_selected_orig_indices()
        if len(multi) > 1:
            indices = multi
        else:
            idx = self._current_orig_index()
            indices = [idx] if idx is not None else []
        if not indices:
            return

        pairs = [(i, key) for i in indices if (key := self._favorite_key(i))]
        if not pairs:
            return

        all_favorited = all(name in self.favorited_names for _i, name in pairs)
        for i, name in pairs:
            if all_favorited:
                self.favorited_names.discard(name)
            else:
                self.favorited_names.add(name)
            if i < len(self.model.rows):
                self.model.rows[i].favorited = not all_favorited
        rc.save_favorites(self.favorited_names)
        self.list_view.viewport().update()

    def _favorite_key(self, orig_index):
        """What a favourite is saved as: a clip's (or bin's) name, or for
        scripts/macros/comps/projects "macro:<file path>" etc., so they
        can't clash with a clip of the same name."""
        if orig_index is None or orig_index >= len(self.model.rows):
            return None
        row = self.model.rows[orig_index]
        if row.category in EXTERNAL_ROW_CATEGORIES:
            return f"{row.category}:{row.path or row.name}"
        filtered_group_list = self.session.get("filtered_group_list", [])
        return filtered_group_list[orig_index][0] if orig_index < len(filtered_group_list) else None

    def _recent_order(self):
        """The r: view - recently inserted clips and recently used
        scripts/macros/comps/projects, newest first."""
        index_by_name = {}
        for i, (name, _instances, category) in enumerate(self.session.get("filtered_group_list", [])):
            if category != "selected":
                index_by_name.setdefault(name, i)
        external, order = {}, []
        for key in rc.load_recent():
            if key in index_by_name:
                order.append(("clip", index_by_name[key]))
                continue
            kind = key.split(":", 1)[0] if ":" in key else None
            if kind in EXTERNAL_ROW_CATEGORIES:
                if kind not in external:
                    external[kind] = {f"{r.category}:{r.path or r.name}": r for r in self._provide_external_rows(kind)}
                row = external[kind].get(key)
                if row is not None:
                    order.append(("ext", row))
        return order

    def _unused_rows(self):
        """u: - Media Pool clips that aren't on the current timeline."""
        timeline = self.session.get("timeline")
        if timeline is None:
            return []
        try:
            used = tt.used_media_ids(timeline)
        except Exception as e:
            print(f"Couldn't read the timeline: {e}")
            return []
        out = []
        for i, (_name, instances, category) in enumerate(self.session.get("filtered_group_list", [])):
            if category in ("bin", "selected") or i >= len(self.model.clip_rows):
                continue
            if not any(instance[0] in used for instance in instances):
                out.append(i)
        return out

    def _used_rows(self):
        """used: - clips on the current timeline with how often, most used first."""
        timeline = self.session.get("timeline")
        if timeline is None:
            return []
        try:
            uses = tt.media_use_counts(timeline)
        except Exception as e:
            print(f"Couldn't read the timeline: {e}")
            return []
        out = []
        for i, (_name, instances, category) in enumerate(self.session.get("filtered_group_list", [])):
            if category in ("bin", "selected") or i >= len(self.model.clip_rows):
                continue
            n = sum(uses.get(instance[0], 0) for instance in instances)
            if n:
                out.append((i, n))
        out.sort(key=lambda t: (-t[1], self.model.clip_rows[t[0]].name.lower()))
        return out

    # Basics (2026-10-20: "one that's called basics ... adjustment clips, fusion compositions, solid color, text plus"):
    # what Resolve makes rather than your footage, each at the playhead on a free track - (name, its source, its
    # symbol, words it's found by). Nothing is added here without asking him ("I'm a little bit selective").
    BASICS = (("Title", "title", "title", "text+ text words caption lower third"),
              ("Solid colour", "solid", "solid", "solid color colour background matte fill"),
              ("Adjustment clip", "adjust", "adjustment", "adjustment effect"),
              ("Fusion composition", "comp", "comp", "fusion composition comp"))
    _BASIC_ACTIONS = {"Adjustment clip at playhead", "Fusion composition at playhead"}  # (a Basics row does it)

    def _basic_row(self, name, source, glyph, tags, words=""):
        if source == "title":
            source = "|".join(library.title(self.settings.timeline_tools["title_name"]))
        elif source == "solid":
            source = "|".join(library.SOLID)
        row = rc.RowData(self.settings.icons["title"], "title", words or name,
                         f"Add as {name}" if words else "Basics", path=words or None, tags=tags)
        row.source, row.glyph = source, glyph
        return row

    def _basic_rows(self, text):
        """basics: - Title, Solid colour, Adjustment clip, Fusion composition (those with what's typed in their name).
        The same rows are in the Edit page's own list, so "solid" finds Solid colour there too."""
        from .fuzzy import fold
        words = fold(text).split()
        return [self._basic_row(*basic) for basic in self.BASICS
                if all(w in fold(f"{basic[0]} {basic[3]}") for w in words)]

    def _title_rows(self, text):
        """title: - one row: a Title with what's typed as its words (nothing typed: as it comes)."""
        title = self.BASICS[0]
        return [self._basic_row(*title, words=text.strip())]


    # each kind's symbol in the : menu - its own, or (a view of the list, "g:") a line icon
    _PREFIX_SYMBOL = {"basic": "solid", "staged": "g:stage", "favorite": "g:favourite", "recent": "g:history", "unused": "g:timeline",
                      "used": "g:timeline", "music": "music", "sfx": "sound", "like": "g:similar",
                      "missing": "g:checkup", "duplicate": "g:checkup", "clipping": "g:checkup"}
    _PREFIX_TINT = {"basic": "title", "music": "audio", "sfx": "audio", "like": "audio", "staged": "video", "favorite": "video",
                    "recent": "video", "unused": "video", "used": "video"}

    def _prefix_menu_rows(self, text):
        """":" on its own - every kind of row there is to search in, by group: its name, symbol and colour, and
        what to type for it ("mk:  marker:"). Enter picks one (the pill in the search). Typing after the colon
        narrows them down; Actions (">") last."""
        from .fuzzy import fold
        from .settings import PREFIX_SCHEMA, PREFIX_TITLES
        words = fold(text).split()
        rows = []
        for _group, targets in PREFIX_SCHEMA:
            for target in targets:
                forms = self.settings.prefixes.get(target) or [target]
                title = PREFIX_TITLES.get(target, target.title())
                if words and not all(any(w in fold(f) for f in [title, target] + forms) for w in words):
                    continue
                row = rc.RowData("", "prefix", title, "  ".join(f + ":" for f in forms), path=target)
                row.glyph = self._PREFIX_SYMBOL.get(target, target)
                try:
                    row.color = self.settings.icon_color(self._PREFIX_TINT.get(target, target))
                except KeyError:
                    row.color = self.settings.theme["picker_folder"]
                rows.append(row)
        if not words or all(w in fold("actions >") for w in words):
            row = rc.RowData("", "prefix", "Actions", ">", path=">")
            row.glyph, row.color = "action", self.settings.icon_color("action")
            rows.append(row)
        return rows

    def _layout_rows(self, text):
        """layout: - Resolve's saved UI layouts (Workspace > Layout Presets); Enter switches to one. (Saving one
        from here was taken out, 2026-10-17 - Resolve's own Layout Presets menu does that.)"""
        from .fuzzy import fuzzy_score
        icon = self.settings.icons.get("layout", "")
        q = text.strip()
        try:
            names = [str(n) for n in (self.resolve.GetLayoutPresetList() or [])]
        except Exception as e:
            print(f"[layout] couldn't list Resolve's layouts: {e}")
            names = []
        scored = sorted(((-(fuzzy_score(q, n) or 0), n) for n in names if not q or fuzzy_score(q, n) is not None))
        return [rc.RowData(icon, "layout", n, "", path="load:" + n) for _s, n in (scored if q else [(0, n) for n in names])]

    def _layout_action(self, path):
        """Enter on a layout: row - switch to it."""
        _action, _sep, name = (path or "").partition(":")
        try:
            ok = self.resolve.LoadLayoutPreset(name)
            return f"Layout \u201c{name}\u201d" if ok else f"Resolve didn't switch to \u201c{name}\u201d"
        except Exception as e:
            return f"Couldn't do that with Resolve's layouts: {e}"

    def _template_rows(self, text):
        """tpl: - your templates and the built-in ones (Enter applies to the
        open project); with a new name typed, the first row saves this
        project as a template."""
        from . import project_templates as pt
        from .fuzzy import fuzzy_score
        icon = self.settings.icons.get("template", "")
        q = text.strip()
        templates = pt.all_templates()
        exact = next((n for n, _t, _b in templates if n.lower() == q.lower()), None)
        rows = []
        save_row = rc.RowData(icon, "template", f"Save this project as \u201c{q}\u201d", "new template",
                              path="save:" + q) if q and exact is None else None
        scored = []
        for name, template, built_in in templates:
            score = fuzzy_score(q, name) if q else 0
            if score is not None:
                scored.append((-(score or 0), name, template, built_in))
        for _s, name, template, built_in in sorted(scored, key=lambda t: t[0]) if q else scored:
            about = ("built in \u00b7 " if built_in else "") + pt.describe(template)
            rows.append(rc.RowData(icon, "template", name, about, path="apply:" + name))
            if name == exact and not built_in:
                rows.append(rc.RowData(icon, "template", f"Update \u201c{name}\u201d from this project",
                                       "replaces the saved template", path="save:" + name))
        if save_row is not None:  # first when nothing matches, else after the matches
            rows.insert(0, save_row) if not rows else rows.append(save_row)
        if not q:
            rows.append(rc.RowData(icon, "template", "Save this project as a template",
                                   "type its name after tpl:", path="save:"))
        return rows

    def _favorite_external_rows(self):
        """Starred scripts/macros/comps/projects, for the favourites (f:) view."""
        kinds = {key.split(":", 1)[0] for key in self.favorited_names if ":" in key}
        rows = []
        for kind in ("script", "macro", "comp", "node", "expression", "project", "folder", "timeline", "shortcut"):
            if kind in kinds:
                rows.extend(r for r in self._provide_external_rows(kind) if r.favorited)
        return rows

    def increment_staged(self):
        multi = [i for i in self._get_multi_selected_orig_indices() if not self._is_external_row(i)]
        if len(multi) > 1:
            for i in multi:
                self.model.increment_staged(i)
            self._update_staged_summary()
            self.list_view.viewport().update()
            return
        orig_index = self._current_orig_index()
        if orig_index is None:
            return
        if self._is_external_row(orig_index):
            self._chain_change(orig_index, "add")
            return
        if orig_index not in self.model.staged:
            self._clip_seq[orig_index] = self._next_seq()
        self.model.increment_staged(orig_index)
        self._update_staged_summary()
        self.list_view.viewport().update()

    def decrement_staged(self):
        multi = [i for i in self._get_multi_selected_orig_indices() if not self._is_external_row(i)]
        if len(multi) > 1:
            for i in multi:
                self.model.decrement_staged(i)
            self._update_staged_summary()
            self.list_view.viewport().update()
            return
        orig_index = self._current_orig_index()
        if orig_index is None:
            return
        if self._is_external_row(orig_index):
            self._chain_change(orig_index, "remove_one")
            return
        self.model.decrement_staged(orig_index)
        self._update_staged_summary()
        self.list_view.viewport().update()

    def toggle_search_prefix(self, target):
        """Jumps straight to a search prefix (e.g. target="favorite" ->
        types "f:"), or if the search box is already showing that exact
        prefix, goes back to whatever was typed before — same toggle
        pattern as clicking the staged summary. Used both by that click
        and by any configurable per-prefix keybind (Settings -> Search
        Prefixes)."""
        prefix_list = self.settings.prefixes.get(target) or []
        if not prefix_list:
            return
        prefix_str = f"{prefix_list[0]}:"
        if self.search_edit.text().strip() == prefix_str:
            self.search_edit.setText(self._pre_prefix_filter_text or "")
            self._pre_prefix_filter_text = None
        else:
            self._pre_prefix_filter_text = self.search_edit.text()
            self.search_edit.setText(prefix_str)

    def show_staged_only(self):
        """Clicking the staged summary — filters to exactly what Tab has
        marked (same as typing s: yourself). Clicking again while already
        on s: goes back to whatever search text was there before."""
        self.toggle_search_prefix("staged")

    def _resolved_row_count(self, orig_index, count):
        """How many actual clips a staged/selected row's `count` really
        represents. Normally that's just `count` itself — except for the
        "Selected Clips" row, which is one row standing in for however
        many clips are currently selected in the Media Pool, not one."""
        if orig_index < len(self.model.rows) and self.model.rows[orig_index].category == "selected":
            media_pool = self.session.get("media_pool")
            if media_pool is not None:
                try:
                    actual = len(media_pool.GetSelectedClips() or [])
                    return max(1, actual) * count
                except Exception:
                    pass
        return count

    def _update_staged_summary(self):
        self._update_staged_summary_text()
        has_summary = bool(self.staged_summary_label.text())
        self.staged_summary_label.setVisible(has_summary)
        self.hints_label.setVisible(not has_summary)

    def _update_staged_summary_text(self):
        """'1 video, 6 audio, 1 adjustment (8)' — a quick sanity check of
        what Enter would actually insert right now. Falls back to
        counting the active multi-selection when nothing is staged,
        since that's what Enter inserts in that case too."""
        staged = self.model.staged
        if staged or self.model.chain:
            picked = [(i, count) for i, count in staged.items() if i < len(self.model.clip_rows)]
        else:
            multi = [i for i in self._get_multi_selected_orig_indices() if not self._is_external_row(i)]
            if len(multi) <= 1:
                self.staged_summary_label.setText("")
                return
            picked = [(i, 1) for i in multi if i < len(self.model.rows)]
        # a bin is what's in it: "Music: 3 video, 2 image · 8 audio (13)" - what Enter puts in
        counts, bins = {}, []
        for orig_index, count in picked:
            category = self.model.rows[orig_index].category
            if category == "bin":
                inside = {}
                for i in self._rows_inside(orig_index):
                    kind = self.model.rows[i].category
                    inside[kind] = inside.get(kind, 0) + count
                name = self.model.rows[orig_index].name.rsplit(" (", 1)[0]
                bins.append((name if len(name) <= 20 else name[:18].rstrip() + "\u2026", count, inside))
            else:
                counts[category] = counts.get(category, 0) + self._resolved_row_count(orig_index, count)
        for entry in self.model.chain:
            counts[entry["category"]] = counts.get(entry["category"], 0) + 1
        total = sum(counts.values()) + sum(sum(inside.values()) for _n, _c, inside in bins)

        dim = self.settings.theme["picker_folder"]

        def kinds(found):
            parts = []
            for cat, n in found.items():
                try:
                    color = self.settings.icon_color(cat)
                except KeyError:
                    color = dim
                parts.append(f'<span style="color:{color};">{n} {cat}</span>')
            return ", ".join(parts) or f'<span style="color:{dim};">empty</span>'

        groups = []
        if len(bins) > 2:  # (several: their contents together)
            together = {}
            for _name, _count, inside in bins:
                for kind, n in inside.items():
                    together[kind] = together.get(kind, 0) + n
            bins = [(f"{len(bins)} bins", 1, together)]
        for name, count, inside in bins:
            times = f" \u00d7{count}" if count > 1 else ""
            groups.append(f'<span style="color:{self.settings.icon_color("bin")};">'
                          f'{_html.escape(name)}{times}:</span> {kinds(inside)}')
        if counts:
            groups.append(kinds(counts))
        html = f' <span style="color:{dim};">\u00b7</span> '.join(groups) + f' <span style="color:{dim};">({total})</span>'
        self.staged_summary_label.setText(html)

    def _staged_name_snapshot(self):
        """Captures currently staged clips as {name: count} — name-based
        rather than by row index, since indices don't survive a row
        reload (used by both Ctrl+R refresh and History restore)."""
        return {self.model.clip_rows[i].name: count for i, count in self.model.staged.items()
                if i < len(self.model.clip_rows)}

    def _restore_staged_by_name(self, name_counts):
        self.model.staged = {}
        if name_counts:
            for i, row in enumerate(self.model.clip_rows):
                if row.name in name_counts:
                    self.model.staged[i] = name_counts[row.name]
        self._update_staged_summary()
        self.list_view.viewport().update()

    @staticmethod
    def _warm_up():
        import threading

        def load():
            for name in ("av", "numpy", "miniaudio"):
                try:
                    __import__(name)
                except Exception:
                    pass
            try:
                import av
                av.codec.Codec("h264", "r")  # codec tables
            except Exception:
                pass
        threading.Thread(target=load, name="clipse-warm-up", daemon=True).start()

    def _apply_analysis(self, rows):
        """What's known about the sounds - right away; new ones are only
        analysed on open if Settings says so."""
        from . import file_tags as ft
        sounds = [row for row in rows if row.category == "audio" and ft.can_tag(row.file)]
        for row in sounds:
            row.file_tags = ft.known(row.file)
            _set_energy(row)
        self.analyser.apply_cached(rows, self.settings)
        self.tag_keeper.read(sounds)  # (on a thread: only a file changed since is read)
        if self.settings.listen.get("auto_analyse") and self.settings.listen.get("split_music", True):
            self.analyser.start(rows)

    def _on_analysed(self, row, result):
        if row not in self.model.clip_rows:
            return  # from a list that's been replaced since
        SoundAnalyser.apply(row, result)
        self.list_view.viewport().update()

    # -- a sound's energy and tags (tag_strip.py, file_tags.py) --
    def _on_tags_read(self, row, tags):
        row.file_tags = tags
        _set_energy(row)
        self.list_view.viewport().update()

    def _on_tags_done(self, changed):
        if not changed:
            return
        if self.tag_strip.isVisible():
            self._tags_follow()
        text = self.search_edit.text()
        if text.strip():  # (it may find other sounds now)
            current = self.list_view.currentIndex()
            keep = current.data(ROLE_ORIG_INDEX) if current.isValid() else None
            self.model.set_filter(text)
            if self.model.visible:
                self._select_row(self.model.visible.index(keep) if keep in self.model.visible else 0)

    def _on_tag_failed(self, path, why):
        from . import file_tags as ft
        tags = ft.read(path)
        for row in self.model.clip_rows:
            if row.category == "audio" and row.file == path:
                row.file_tags = tags
                _set_energy(row)
        self.list_view.viewport().update()
        if self.tag_strip.isVisible():
            self._tags_follow()
        self._flash_hint(f"Couldn't tag {_os.path.basename(path)}: {why}", 5000)

    def _tag_row(self):
        """The highlighted sound, or None."""
        index = self._current_orig_index()
        rows = self.model.rows
        row = rows[index] if index is not None and index < len(rows) else None
        return row if row is not None and row.category == "audio" else None

    def _why_no_tags(self, row):
        from . import file_tags as ft
        if row is None:
            return "Only sounds have tags"
        return "" if ft.can_tag(row.file) else "Clipse tags .wav, .mp3, .flac and .mov"

    def _known_tags(self):
        """Every tag on the sounds in this project, the most used first."""
        from collections import Counter
        counts = Counter(tag for row in self.model.clip_rows if row.category == "audio" for tag in row.file_tags)
        return [tag for tag, _n in counts.most_common()]

    def _tags_follow(self):
        row = self._tag_row()
        self.tag_strip.show_for(row.file_tags if row else [], row.energy if row else 0,
                                self._known_tags(), self._why_no_tags(row))

    def open_tags(self):
        self.end_swap()
        self.tag_strip.setFont(self.list_view.font())
        self.tag_strip.show()
        self._tags_follow()
        self.tag_strip.field.setFocus()

    def close_tags(self):
        if self.tag_strip.isVisible():
            self.tag_strip.field.clear()
            self.tag_strip.hide()
            self.search_edit.setFocus()

    def set_energy(self, level):
        """Alt+1, 2, 3 (or the strip): the highlighted sound's energy. The one it has again - or 0 - takes it away."""
        from . import file_tags as ft
        row = self._tag_row()
        why = self._why_no_tags(row)
        if why:
            return self._flash_hint(why, 3000)
        self._set_tags(row, ft.with_energy(row.file_tags, 0 if level == ft.energy_of(row.file_tags) else level))

    def _set_tags(self, row, tags):
        """On the row at once - every row of that file - and into the file behind it (TagKeeper)."""
        if row is None or self._why_no_tags(row):
            return
        for other in self.model.clip_rows:
            if other.category == "audio" and other.file == row.file:
                other.file_tags = list(tags)
                _set_energy(other)
        self.tag_keeper.write(row.file, tags)
        self.list_view.viewport().update()
        if self.tag_strip.isVisible():
            self._tags_follow()

    def _relink_missing(self):
        """(relink.py) The list read afresh after: what it knows of a clip's file is what the preview goes by."""
        from .relink import relink_missing
        try:
            worked, message = relink_missing(self.resolve)
        except Exception as e:
            print(f"[relink] failed: {e}")
            worked, message = False, "Resolve didn't answer - is a project open?"
        self._flash_hint(message, 5000)
        if worked:
            self.refresh_rows()

    # -- Mark the beats (beats.py) --
    def _mark_beats(self, bars=False):
        from . import beats
        timeline = self.session.get("timeline")
        if timeline is None:
            return self._flash_hint("Open a timeline first", 3000)
        running = getattr(self, "_beats_running", None)
        if running is not None and running.poll() is None:
            return self._flash_hint("Still marking", 2500)
        row = self._tag_row()
        run = str(int(time.time()))
        self.hide()  # (Resolve in front: a marker takes 4 ms instead of a second)
        self._beats_running = beats.start(bars, row.file if row is not None and row.music and row.file else "", run)
        self._push_action({"kind": "beats", "label": "the bars" if bars else "the beats", "run": run,
                           "timeline_id": self._timeline_id(timeline)})

    def _on_analysis_done(self, _count=0):
        """Every clip checked: m: / sfx: now know about all of them."""
        text = self.search_edit.text()
        prefix = text.split(":", 1)[0].strip().lower() if ":" in text else ""
        if prefix and prefix in (self.settings.prefixes.get("music", []) + self.settings.prefixes.get("sfx", [])):
            current = self.list_view.currentIndex()
            keep = current.data(ROLE_ORIG_INDEX) if current.isValid() else None
            self.model.set_filter(text)
            self._select_row(self.model.visible.index(keep) if keep in self.model.visible else 0)

    def refresh_rows(self):
        """Ctrl+R — rescan the Media Pool without closing the picker or
        losing your search text or staged clips (re-matched by name). The
        list stays usable while it's read; the button turns meanwhile."""
        project_name = self.session.get("project_name")
        media_pool = self.session.get("media_pool")
        root_folder = self.session.get("root_folder")
        if not project_name or media_pool is None or root_folder is None:
            print("Nothing to refresh — no project loaded yet.")
            return
        self._start_scan(project_name, root_folder, media_pool, previous=None, restart=True)
        self._scan["reload_preview"] = True  # (once it's read: the preview shows the clip afresh)

    # -- reading the Media Pool without ever waiting for it --
    def _rows_now(self, project_name, root_folder, media_pool, force_refresh=False):
        """The rows to show this instant: the last scan of this project
        (however old) - then, in the background, the Media Pool is looked at
        again (2026-10-19: instead of a "Rescan and Search" script) and the
        list updates when it's done, if anything changed. So opening the
        picker never waits for Resolve, and a clip added since shows a moment
        later. Every open a quick look (MediaPoolScan's `known`: new, renamed
        and moved clips), every CACHE_TTL_SECONDS a full read; none within
        LOOK_AGAIN_AFTER of the last (several inserts in a row)."""
        entries, bin_paths, _age = rc.read_cache(project_name)
        first = entries is None
        if first:
            entries, bin_paths = [], []
        rows, filtered_group_list, id_paths = rc.build_rows(
            self.settings, entries, bin_paths, media_pool, self.favorited_names)
        read = self._media_reads.get(project_name)
        now = time.monotonic()
        full = force_refresh or first or read is None or now - read["full"] >= rc.CACHE_TTL_SECONDS
        if full or now - read["any"] >= self.LOOK_AGAIN_AFTER:
            self._start_scan(project_name, root_folder, media_pool,  # (one under way for this project carries on)
                             previous=None if (first or force_refresh) else entries, restart=force_refresh,
                             first=first, known=None if full else {e[0]: e for e in entries})
        return rows, filtered_group_list, rc.cache_file_for(project_name), id_paths

    LOOK_AGAIN_AFTER = 10  # seconds: the picker opened again sooner than this doesn't look at the Media Pool again

    def _start_scan(self, project_name, root_folder, media_pool, previous=None, restart=False, first=False,
                    known=None):
        job = self._scan
        if job is not None and job["project"] == project_name and not restart:
            job["first"] = job["first"] or first
            return  # already being read (e.g. read ahead at start) - its result is shown when ready
        # (the look every open takes is quiet: no turning button, no bar - only a rescan asked for, or the first)
        quiet = previous is not None and not restart
        self._scan = {"project": project_name, "media_pool": media_pool, "previous": previous, "first": first,
                      "quiet": quiet, "full": known is None,
                      "scan": rc.MediaPoolScan(root_folder, rc.scan_with_tags(self.settings), known)}
        if not quiet:
            self.refresh_button.set_busy(True)
        if first:
            self.search_edit.setPlaceholderText("Reading the Media Pool\u2026")
        self._scan_timer.start(0)

    def _scan_step(self):
        job = self._scan
        if job is None:
            return
        visible = self.isVisible()
        if visible and time.monotonic() - getattr(self, "_last_typed", 0.0) < 0.35:
            self._scan_timer.start(120)  # you're typing: Resolve can wait a moment
            return
        try:
            # open: short slices, so typing stays instant; hidden: gentle on Resolve
            done = job["scan"].step(0.010 if visible else 0.02)
        except Exception as e:
            print(f"Couldn't read the Media Pool: {e}")
            self._finish_scan()
            return
        if not done:
            if visible:
                self._update_scan_bar()
                if job["first"]:
                    total = job["scan"].total
                    self.search_edit.setPlaceholderText(
                        f"Reading the Media Pool\u2026  {job['scan'].count}" + (f" of {total}" if total else "") + " clips")
                    # the first time, show what's read so far every second - search can start right away
                    now = time.monotonic()
                    if now - job.get("shown_at", now - 2) >= 1.0 and job["scan"].count:
                        job["shown_at"] = now
                        if self.session.get("project_name") == job["project"] and self.session.get("media_pool"):
                            rows, groups, id_paths = rc.build_rows(
                                self.settings, list(job["scan"].entries), list(job["scan"].bin_paths),
                                self.session["media_pool"], self.favorited_names)
                            at_top = self.list_view.currentIndex().row() <= 0
                            self._install_rows(rows, groups, id_paths)
                            if at_top:
                                self._select_row(0)  # still reading: stay at the top of the list
            self._scan_timer.start(0 if visible else 20)
            return
        scan = job["scan"]
        cached, cached_bins, _age = rc.read_cache(job["project"])
        changed = cached != scan.entries or cached_bins != scan.bin_paths
        if changed:  # (written only when something's different: a quick look every open mostly finds nothing)
            rc.write_cache(job["project"], scan.entries, scan.bin_paths)
        now = time.monotonic()
        before = self._media_reads.get(job["project"])
        self._media_reads[job["project"]] = {"any": now, "full": now if job["full"] else before["full"] if before else 0.0}
        self._finish_scan()
        if job["full"] or changed:
            print(f"Read the Media Pool of \"{job['project']}\" ({scan.count} clips{'' if job['full'] else ', a quick look'}).")
        if self.session.get("project_name") != job["project"] or self.session.get("media_pool") is None:
            return  # read ahead (or another project is open now) - it's ready for next time
        if job["previous"] is not None and job["previous"] == scan.entries:
            return  # nothing changed
        rows, filtered_group_list, id_paths = rc.build_rows(
            self.settings, scan.entries, scan.bin_paths, self.session["media_pool"], self.favorited_names)
        self._install_rows(rows, filtered_group_list, id_paths)
        if job.get("reload_preview") and self.preview_panel.isVisible():
            self._reload_preview()

    def _reload_preview(self):
        """After Ctrl+R: the highlighted clip read again from its file (it may have changed on disk) - from
        where it was, playing if it was. Moving off it and back used to be the only way."""
        self._video_timer.stop()
        playing = self.video.is_video and not self.video.paused
        self.video.stop()
        self.scrubber.stop()
        self._preview_current(play=playing, quiet=not playing)

    def _finish_scan(self):
        self._scan = None
        self.refresh_button.set_busy(False)
        self.search_edit.setPlaceholderText("Search clips")
        self._update_scan_bar()

    def _update_scan_bar(self):
        """The thin bar under the search: how much of the Media Pool is read."""
        bar = getattr(self, "scan_bar", None)
        if bar is None:
            return
        job = self._scan
        if job is None or job.get("quiet") or not self.isVisible():
            bar.set_progress(None)
            return
        scan = job["scan"]
        bar.set_progress(scan.count / scan.total if scan.total else None if not scan.count else -1.0)

    def _install_rows(self, rows, filtered_group_list, id_paths):
        """New rows under an open picker, keeping what you were doing: the
        search text, the highlighted clip and anything staged."""
        staged_snapshot = self._staged_name_snapshot()
        text = self.search_edit.text()
        current = self.list_view.currentIndex()
        keep = None
        if current.isValid() and not self.model.showing_external:
            orig = current.data(ROLE_ORIG_INDEX)
            if orig is not None and 0 <= orig < len(self.model.rows):
                keep = self.model.rows[orig].name
        self._audio_paths = {}
        self.session.update(rows=rows, filtered_group_list=filtered_group_list, id_paths=id_paths)
        self._live_count_rows = [
            (rows[i], i) for i, (_name, _instances, category) in enumerate(filtered_group_list)
            if category == "selected"
        ]
        self._apply_analysis(rows)
        self.model.set_rows(rows)  # resets staged — restored right after
        self._restore_staged_by_name(staged_snapshot)
        self.model.set_filter(text)
        self._update_staged_summary()
        position = 0
        if keep is not None and not self.model.showing_external:
            position = next((k for k, i in enumerate(self.model.visible)
                             if i < len(self.model.rows) and self.model.rows[i].name == keep), 0)
        self._select_row(position)

    def prewarm(self):
        """Right after the service starts (and whenever another project is
        opened): read the project's Media Pool ahead of time, so even the
        first open shows everything at once."""
        self._prescan_check()
        timer = QTimer(self)
        timer.timeout.connect(self._prescan_check)
        timer.start(5000)
        self._prescan_timer = timer

    def _prescan_check(self):
        if self.isVisible() or self._scan is not None:
            return
        try:
            project = self.resolve.GetProjectManager().GetCurrentProject()
            name = project.GetName() if project else None
        except Exception:
            return
        if not name or name == self._prescanned:
            return
        self._prescanned = name
        entries, _bins, age = rc.read_cache(name)
        if age is not None and age < rc.CACHE_TTL_SECONDS:
            return
        try:
            media_pool = project.GetMediaPool()
            root = media_pool.GetRootFolder()
        except Exception:
            return
        if root is not None:
            self._start_scan(name, root, media_pool, previous=entries)

    # -- timeline tools (see timeline_tools.py) — triggered only from the
    # client (system-wide keybinds), never from inside the picker --
    def run_direct_command(self, action, arg):
        """Client commands that skip the picker entirely (clipse
        jump next / adjust match ...) — reads the current project fresh,
        since the picker may not have been opened yet. Jump goes by the clip
        selected on the timeline or in the Media Pool, else the one under the
        playhead (timeline_tools.jump_targets), since there's no highlighted row."""
        try:
            if action == "fusion":
                if arg == "copyname":
                    print(self._copy_node_name())
                elif arg in ("nodeonoff", "beforeafter"):  # (no picker open: what went wrong is said on screen)
                    worked, message = (fusion_animate.toggle_nodes if arg == "nodeonoff"
                                       else fusion_animate.before_after)(self.resolve)
                    print(message)
                    if not worked:
                        self._say(message)
                else:
                    print(self._pull_out() if arg == "pullout" else self._tidy())
                return
            if action == "undo":
                print(self.undo_last_action())
                return
            if action == "organise":  # (organise.py, a program of its own: Resolve takes a second for each colour)
                from .organise import start
                start()
                self._say("Organising the project\u2026")
                return
            if action == "say":  # a program of Clipse's own saying how it went (organise.py)
                self._say(arg, 4000)
                return
            if action == "retired":  # its stand-in in Resolve's menu was pressed
                self._say(f"{arg} isn't part of Clipse any more")
                return
            if action == "step":  # arg = net presses (+/-), each Settings > Scripts' frames for that direction
                if arg:
                    tools = self.settings.timeline_tools
                    worked, message = tt.step_playhead(self.resolve, arg * int(
                        tools.get("step_forward_frames" if arg > 0 else "step_back_frames", 5)))
                    if not worked:
                        self._say(message)
                return
            if action == "swap":
                self.start_swap()
                return
            if action == "grab":
                print(self.grab_frame())
                return
            if action == "voice":
                self.toggle_voiceover()
                return
            project = self.resolve.GetProjectManager().GetCurrentProject()
            timeline = project.GetCurrentTimeline() if project else None
            if timeline is None:
                print("No timeline open.")
                return
            media_pool = project.GetMediaPool()
            if action == "marker":  # (markers.py: his Shift+C and Alt+C in Resolve)
                self._marker_command(timeline, arg)
                return
            if action == "jump":
                stats.record("jump")
                msg = tt.jump_selected_clip(timeline, media_pool, arg)  # arg = net steps (+/-)
                if msg:
                    print(msg)
                    if " of " not in msg:  # (it didn't jump - and there's no picker open to say why)
                        self._say(msg.rstrip("."), 3500)
            elif action in ("adjust", "comp"):  # a clip from the Media Pool over what's under the playhead
                lookup = tt.lookup_adjustment_clip if action == "adjust" else tt.lookup_composition_clip
                clip, message = lookup(self.settings, media_pool)
                if clip is not None:
                    tracks, landed = self._track_counts(timeline), []
                    message = tt.place_over(self.settings, timeline, media_pool, clip, arg, action, landed_out=landed)
                    if landed:  # (Undo takes it back, as when it's added from the picker - it said "Nothing to undo")
                        self._remember_timeline_action(timeline, [], tracks, f"the {tt.PLACED[action][0].lower()}",
                                                       items=landed)
                        self._colour_new(landed)
                    stats.record(action)
                print(message)
                if clip is None or not tt.placed_fine(message, action):
                    self._say(message, 7000)  # (no picker open to say it in)
        except Exception as e:
            print(f"{action} failed: {e}")  # never let a Resolve API hiccup kill the daemon

    # -- reveal / insert --
    def reveal_only(self, keep_open=False):
        self._remember_search()
        orig_index = self._current_orig_index()
        if self._is_external_row(orig_index):
            print("Reveal doesn't apply to scripts/macros/comps/projects — press the confirm key to run/activate/switch instead.")
            return
        orig_index_row = self.list_view.currentIndex().row()
        if orig_index_row < 0:
            return
        idx = self.model.visible[orig_index_row]
        if keep_open:
            try:
                self._do_reveal(idx)
            except Exception as e:
                print(f"Couldn't select the clip in the Media Pool: {e}")
            self._flash_hint("Selected in the Media Pool", 1500)
            return
        self.hide()
        QTimer.singleShot(0, lambda: self._do_reveal(idx))

    def show_in_file_manager(self):
        """The highlighted clip's file (or script, macro, comp, folder) in
        your file manager - or, with several clips selected or staged, all
        of them (one window per folder)."""
        from .file_manager import reveal_many
        staged = [i for i in self.model.staged if not self._is_external_row(i)]
        multi = [i for i in self._get_multi_selected_orig_indices() if not self._is_external_row(i)]
        indices = staged if staged else multi if len(multi) > 1 else [self._current_orig_index()]
        paths = []
        for orig_index in indices:
            if orig_index is None or orig_index >= len(self.model.rows):
                continue
            row = self.model.rows[orig_index]
            if self._is_external_row(orig_index):
                if row.category in ("script", "macro", "comp", "folder"):
                    paths.append(row.path)
            elif row.category in ("audio", "video", "image"):
                paths.append(self._row_file_path(orig_index))
            elif row.category in ("bin", "selected"):
                for item, _folder, _name, _cat in rc.expand_row_to_items(
                        self.session, self.settings, orig_index, self.selection_order_ids):
                    try:
                        paths.append(item.GetClipProperty("File Path") or "")
                    except Exception:
                        pass
        paths = [p for p in paths if p]
        if not paths:
            self._flash_hint("This row has no file", 2500)
            return
        problem = reveal_many(paths, max_windows=self.settings.files["max_windows"],
                              command=self.settings.files["file_manager"])
        if problem and not problem.startswith("Showed"):
            self._flash_hint(problem, 3000)
            return
        self._remember_search()
        self._keep_focus_elsewhere = True
        self.hide()  # the file manager comes up in front

    def _do_reveal(self, idx):
        name, instances, category = self.session["filtered_group_list"][idx]
        media_pool = self.session["media_pool"]

        if category == "bin":
            path = instances[0][0]
            bin_folder = rc.find_folder_by_path(self.session["root_folder"], path)
            if bin_folder is None:
                print(f"Bin '{name}' no longer found.")
                return None, None
            media_pool.SetCurrentFolder(bin_folder)
            print(f"Revealed bin '{name}' — not inserted.")
            return None, None
        if category == "selected":
            print("Selected Clips reflects whatever's already selected — nothing to reveal.")
            return None, None

        chosen_item, chosen_folder, clip_name = rc.find_clip_for_row(self.session, idx)
        if chosen_item is None:
            return None, None
        media_pool.SetCurrentFolder(chosen_folder)
        media_pool.SetSelectedClip(chosen_item)
        print(f"Revealed '{clip_name}' in [{chosen_folder.GetName()}] — not inserted.")
        return chosen_item, clip_name

    def preview_clip(self):
        """The preview key - opens (or closes) the preview window to the right of
        the picker and shows the highlighted clip there. Moving to another
        row previews that one."""
        if self.preview_panel.isVisible():
            self._close_preview()
            return
        self._stop_audio()  # one sound at a time
        self._open_preview_panel()
        self._preview_current()
        self.search_edit.setFocus()

    def _set_in_list(self, on):
        """Search or list? Typing (or a click in the search) is the search;
        moving through the rows (or a click on one) is the list."""
        if on != self._in_list:
            self._in_list = on
            self.hints_label.set_hints(self._footer_hints())

    def _note_where(self, ev):
        key = ev.key()
        if key in (Qt.Key_Up, Qt.Key_Down, Qt.Key_PageUp, Qt.Key_PageDown):
            self._set_in_list(True)
        elif key in (Qt.Key_Backspace, Qt.Key_Delete):
            self._set_in_list(False)
        elif key != Qt.Key_Space and ev.text() and ev.text().isprintable() \
                and not (ev.modifiers() & (Qt.ControlModifier | Qt.AltModifier | Qt.MetaModifier)):
            self._set_in_list(False)  # a letter: back to searching, no click needed

    def _space_plays(self):
        """Should Space play (the preview, or with it closed the highlighted
        sound) rather than write a space? Settings -> Preview -> Space plays.
        smart: in the list, yes; in the search, no - except where a space
        can't be meant: nothing is typed yet, or the mouse is on the preview."""
        mode = self.settings.listen.get("space_plays", "smart")
        if mode == "never":
            return False
        if mode == "always" or self._in_list:
            return True
        panel = self.preview_panel
        if panel.isVisible() and (panel.underMouse() or panel.canvas.underMouse()):
            return True
        return not self.search_edit.text().strip()

    def _seek_playing(self, seconds):
        """Moves through what's playing - the preview, or with it closed the
        sound being listened to. False when there's nothing to move through."""
        if self.preview_panel.isVisible() and self.video.is_video and self.video.duration > 0:
            self.video.seek_relative(seconds)
            return True
        if not self.preview_panel.isVisible() and self.sound.playing:
            self.sound.seek_relative(seconds)
            return True
        return False

    HELD_EVERY = 0.07  # Space held down: a short sound starts over this often (seconds)

    def space_play(self, held=False):
        """Space: a short clip - a sound effect - plays from the start again
        every time, which is what you want when listening through them; a
        long one (music, a take) pauses and carries on. Settings -> Preview.
        held: the key is being held down - a short sound then fires over
        and over (no use, but it feels good); a long one isn't toggled."""
        now = time.monotonic()
        if held and (not self._space_replays() or now - self._last_replay < self.HELD_EVERY):
            return
        if self._space_replays():
            self._last_replay = now
            self.replay()
        else:
            self.play_pause()

    def _space_replays(self):
        mode = self.settings.listen.get("space_action", "auto")
        if mode != "auto":
            return mode == "replay"
        orig_index = self._current_orig_index()
        if orig_index is None or orig_index >= len(self.model.rows) or self._is_external_row(orig_index):
            return False
        row = self.model.rows[orig_index]
        seconds = float(getattr(row, "secs", 0) or 0)
        if self.preview_panel.isVisible() and self.video.duration > 0 \
                and self.video.current_path == self._row_file_path(orig_index):
            seconds = self.video.duration  # as it really is (videos only have a length once they're open)
        if seconds <= 0:
            return row.category == "audio"  # length not known: a sound is most likely an effect
        return seconds < float(self.settings.listen.get("space_replay_under", 30) or 0)

    def replay(self):
        """The highlighted clip from its start, playing - in the preview, or
        with the preview closed just its sound."""
        if self.preview_panel.isVisible():
            orig_index = self._current_orig_index()
            path = (self._row_file_path(orig_index) if orig_index is not None and orig_index < len(self.model.rows)
                    and not self._is_external_row(orig_index) else "")
            if self._video_timer.isActive() or (path and path != self.video.current_path) or self.video.duration <= 0:
                self.play_pause()  # not the clip on show yet (or still opening): that starts it
            else:
                self.video.restart()
            return
        orig_index = self._current_orig_index()
        path = (self._row_file_path(orig_index) if orig_index is not None and orig_index < len(self.model.rows)
                and not self._is_external_row(orig_index) else "")
        if path and self.sound.is_video and self.sound.current_path == path and self.sound.running:
            self.sound.restart()  # the same sound again: straight from the top, nothing reopened
            return
        self.sound.stop()
        self.audio.stop()
        self.play_pause()  # nothing playing now: starts the highlighted one

    def play_pause(self):
        """Ctrl+Space - play/pause the clip in the preview window. With the
        preview closed: play (or stop) the highlighted clip's sound - sound
        files and videos alike."""
        if self.preview_panel.isVisible():
            # "play" means the highlighted clip - also when you've just moved to it
            # and its preview is still on its way (it used to toggle the old one, and
            # the new one then arrived paused)
            orig_index = self._current_orig_index()
            path = (self._row_file_path(orig_index) if orig_index is not None and orig_index < len(self.model.rows)
                    and not self._is_external_row(orig_index) else "")
            if self._video_timer.isActive() or (path and path != self.video.current_path):
                self._video_timer.stop()
                self._preview_current(play=True)
                return
            if self.video.is_video:
                if self.video.duration <= 0:  # still opening: make sure it plays, never pause it
                    if self.video.paused:
                        self.video.toggle_pause()
                    return
                self.video.toggle_pause()
            return
        if self.sound.playing or self.audio.playing:
            self.sound.stop()
            self.audio.stop()
            return
        orig_index = self._current_orig_index()
        if orig_index is None or orig_index >= len(self.model.rows) or self._is_external_row(orig_index):
            return
        if self.model.rows[orig_index].category not in ("audio", "video"):
            return
        path = self._row_file_path(orig_index)
        if not VideoPreviewAvailable():
            self._audio_follow_current(restart=True)  # sound files still play without PyAV
            return
        self.sound.loop = False
        self.sound.play(path, autoplay=True)

    def _on_sound_message(self, text):
        self._flash_hint(text)

    # -- in / out points --
    def _mark(self, which):
        """which: "in", "out", or None to clear both."""
        path = self.video.current_path
        canvas = self.preview_panel.canvas
        if not path or not self.video.is_video or canvas.duration <= 0:
            return
        marks = self._marks.setdefault(path, {})
        if which is None:
            marks.clear()
            self._flash_hint("In and out cleared", 1500)
        else:
            # where the mouse is while scrubbing the picture (2026-10-20: "add in an out from the cursor on the
            # scrubbing preview"), else where it plays
            t = canvas.scrub_seconds if canvas.scrub_x is not None else self.video.position
            marks[which] = t
            other = "out" if which == "in" else "in"
            if other in marks and (marks["in"] if "in" in marks else 0) >= marks.get("out", canvas.duration):
                marks.pop(other)  # an in after the out (or the reverse) starts a new range
            self._flash_hint(f"{which.capitalize()} {self._time_text(t) or _fmt_time(t)} - Enter inserts just this "
                             "part (playing stays inside it)", 2500)
        canvas.mark_in, canvas.mark_out = marks.get("in"), marks.get("out")
        self._apply_range(path)
        self.preview_panel.update_time()
        canvas.update()

    def toggle_info(self):
        """Ctrl+D: clip info under the preview on/off (with the preview
        closed: opens it, with the info). Remembered for next time."""
        if not self.preview_panel.isVisible():
            self.settings.listen["show_info"] = True
            self._stop_audio()
            self._open_preview_panel()
            self._preview_current()
        else:
            self._set_info_shown(not self.preview_panel.info.isVisible())
        self.search_edit.setFocus()

    def _set_info_shown(self, on):
        self.settings.listen["show_info"] = bool(on)
        self.settings.save()
        self._sync_info()

    def _sync_info(self):
        """Info under the preview: shown when the preview is and Settings says so."""
        pp = self.preview_panel
        on = self.settings.listen.get("show_info", True)
        pp.info_toggle.set_checked(on)
        if on and pp.isVisible():
            pp.info.set_rows(self._clip_info(self._current_orig_index()))
            pp.info.show()
        else:
            pp.info.hide()

    def _info_fields_menu(self, global_pos):
        """Right-click on the info (or its toggle): which lines it shows."""
        from PySide6.QtWidgets import QMenu
        from .settings import INFO_FIELDS, LISTEN_DEFAULTS
        fields = dict(self.settings.listen.get("info_fields") or LISTEN_DEFAULTS["info_fields"])
        menu = QMenu(self)
        title = menu.addAction("Show in clip info")
        title.setEnabled(False)
        for key, label, default in INFO_FIELDS:
            act = menu.addAction(label)
            act.setCheckable(True)
            act.setChecked(fields.get(key, default))

            def flip(checked, k=key):
                current = dict(self.settings.listen.get("info_fields") or LISTEN_DEFAULTS["info_fields"])
                current[k] = checked
                self.settings.listen["info_fields"] = current
                self.settings.save()
                self._sync_info()
            act.toggled.connect(flip)
        menu.exec(global_pos)

    def _clip_info(self, orig_index):
        """[(label, value)] about a row - from Resolve's clip properties, the
        file itself and the sound analysis."""
        import os as _o
        if orig_index is None or orig_index >= len(self.model.rows):
            return [("", "Nothing selected")]
        row = self.model.rows[orig_index]
        out = []
        if self._is_external_row(orig_index):
            path = row.path if isinstance(row.path, str) and _o.path.exists(row.path) else ""
            if row.category == "node":
                return [("Category", (row.folder_list or "").replace("Tools\\", "").replace("\\", " \u203a "))]
            out.append(("Kind", {"comp": "Fusion composition"}.get(row.category, row.category.capitalize())))
            if row.category in ("macro", "comp") and path:
                from . import fusion_graph
                graph = fusion_graph.load(path)
                out.append(("Nodes", fusion_graph.summary(graph)))
        else:
            props = {}
            try:
                items = rc.expand_row_to_items(self.session, self.settings, orig_index, self.selection_order_ids)
                if row.category in ("bin", "selected"):
                    return [("Clips", str(len(items)))]
                props = items[0][0].GetClipProperty() or {} if items else {}
            except Exception:
                props = {}
            path = props.get("File Path") or ""
            kind = {"audio": "Music" if getattr(row, "music", False) else "Sound", "video": "Video",
                    "image": "Still image", "adjustment": "Adjustment clip", "compound": "Compound clip"}
            out.append(("Kind", kind.get(row.category, row.category.capitalize())))
            duration = props.get("Duration") or ""
            secs = getattr(row, "secs", 0) or rc._seconds(props) if props else 0
            if duration or secs:
                out.append(("Length", f"{_fmt_time(secs)}  ({duration})" if duration and secs else duration or _fmt_time(secs)))
            video = [props.get("Resolution"), f"{props['FPS']} fps" if props.get("FPS") and row.category == "video" else "",
                     props.get("Video Codec")]
            if row.category in ("video", "image", "compound"):
                out.append(("Video", "  \u00b7  ".join(v for v in video if v)))
            sample = props.get("Sample Rate")
            audio = [props.get("Audio Codec"), f"{props['Audio Ch']} ch" if props.get("Audio Ch") else "",
                     f"{sample} Hz" if sample and str(sample).isdigit() else sample,
                     f"{props['Bit Depth']}-bit" if props.get("Bit Depth") and row.category == "audio" else ""]
            out.append(("Audio", "  \u00b7  ".join(str(a) for a in audio if a)))
            analysis = getattr(row, "analysis", None) or {}
            if row.category == "audio" and not analysis:
                out.append(("Analysis", "not yet - Actions \u203a Analyse sounds"))
            elif getattr(row, "music", False):
                tempo = f"{round(row.bpm)} BPM" if row.bpm else ""
                out.append(("Music", "  \u00b7  ".join(v for v in (tempo, analysis.get("key", "")) if v)))
                out.append(("Mood", ", ".join(analysis.get("mood") or [])))
                loop = analysis.get("loop")
                if loop:
                    out.append(("Loop", f"{_fmt_time(loop[0])}\u2013{_fmt_time(loop[1])}  \u00b7  {loop[2]} bars"))
            keywords = [str(props.get("Keyword") or props.get("Keywords") or "")] + list(row.file_tags)
            out.append(("Keywords", ", ".join(word for word in keywords if word)))
            out.append(("Comments", props.get("Comments") or ""))
            out.append(("Clip colour", props.get("Clip Color") or ""))
            out.append(("Used", f"{props['Usage']}\u00d7 in this project" if str(props.get("Usage") or "0") not in ("", "0") else ""))
            out.append(("Created", props.get("Date Created") or ""))
        if path:
            try:
                size = _o.path.getsize(path)
                size_text = f"{size / 1e9:.2f} GB" if size >= 1e9 else f"{size / 1e6:.1f} MB" if size >= 1e6 else f"{size / 1e3:.0f} KB"
            except OSError:
                size_text = "file missing"
            out.append(("File", f"{_o.path.basename(path)}  \u00b7  {size_text}"))
            out.append(("Folder", _o.path.dirname(path)))
        shown = self.settings.listen.get("info_fields") or {}
        keys = {"Kind": "kind", "Length": "length", "Video": "video", "Audio": "audio", "Music": "music",
                "Mood": "mood", "Loop": "loop", "Keywords": "keywords", "Comments": "comments",
                "Clip colour": "clip_colour", "Used": "used", "Created": "created", "File": "file",
                "Folder": "folder", "Analysis": "music"}
        return [(label, value) for label, value in out if shown.get(keys.get(label, ""), True)]

    def mark_loop(self):
        """Alt+L: in and out on the music's clean loop (found by Analyse
        sounds) - Enter then inserts exactly that part, which repeats
        seamlessly when placed back to back."""
        orig_index = self._current_orig_index()
        row = self.model.rows[orig_index] if orig_index is not None and orig_index < len(self.model.rows) else None
        loop = ((row.analysis or {}).get("loop") if row is not None and row.category == "audio"
                and getattr(row, "analysis", None) else None)
        if not loop:
            self._flash_hint("No loop found yet - Settings \u203a Sound \u203a Analyse sounds"
                             if row is not None and row.category == "audio" and not getattr(row, "analysis", None)
                             else "No clean loop found in this clip", 3000)
            return
        path = self._row_file_path(orig_index)
        if not path:
            return
        start, end, bars = loop
        self._marks[path] = {"in": start, "out": end}
        if path == self.video.current_path:
            canvas = self.preview_panel.canvas
            canvas.mark_in, canvas.mark_out = start, end
            self.preview_panel.update_time()
            canvas.update()
        self._flash_hint(f"Loop {_fmt_time(start)}-{_fmt_time(end)} ({bars} bars) marked - Enter inserts it", 3000)

    def similar_sounds(self):
        """Ctrl+L: sounds that sound like the highlighted one (like: <name>)."""
        orig_index = self._current_orig_index()
        if orig_index is None or orig_index >= len(self.model.rows):
            return
        row = self.model.rows[orig_index]
        if row.category != "audio":
            self._flash_hint("Sounds like this works on sounds", 2500)
            return
        if not (getattr(row, "analysis", None) or {}).get("features"):
            from . import sound_analysis as sa
            hit = sa.cached(row.file) if row.file else None
            if hit and hit.get("features"):
                SoundAnalyser.apply(row, hit)  # analysed after this list was loaded
            elif hit and hit.get("error"):
                self._flash_hint(f"Couldn't analyse this sound ({hit['error']})" if isinstance(hit["error"], str)
                                 else "Couldn't analyse this sound", 4000)
                return
            elif hit and "features" in hit:
                self._flash_hint("Too short to compare", 2500)
                return
            elif not row.file:
                self._flash_hint("Resolve didn't say where this sound's file is", 3000)
                return
            else:
                self._flash_hint("Not analysed yet - Settings \u203a Sound \u203a Analyse sounds", 3500)
                return
        prefix = (self.settings.prefixes.get("like") or ["like"])[0]
        self.search_edit.setText(f"{prefix}: {row.name}")

    def _similar_rows(self, name):
        """[(row index, 0-100)] of the analysed sounds most like `name` - the
        sound itself first (None), so you can play the original to compare."""
        from . import sound_analysis as sa
        rows = self.model.clip_rows
        target = next((r for r in rows if r.category == "audio" and r.name == name
                       and (getattr(r, "analysis", None) or {}).get("features")), None)
        if target is None:
            return []
        kind = bool(target.music)  # music next to music, sound effects next to sound effects
        others = {i: r.analysis["features"] for i, r in enumerate(rows)
                  if r is not target and r.category == "audio" and bool(r.music) == kind
                  and (getattr(r, "analysis", None) or {}).get("features")}
        alike = [(i, pct) for i, pct in sa.similar(target.analysis["features"], others)[:60] if pct >= 15]
        return [(rows.index(target), None)] + alike

    # -- the big view (BigPreview) --
    # -- the preview popped out: a window of its own --
    def _popped_out(self):
        w = self.preview_window
        return w is not None and w.isVisible() and self.preview_panel.parentWidget() is w

    def _toggle_popout(self):
        """The symbol at the end of the preview's bar: out into a window of
        its own (drag it anywhere - another screen ...), or back beside the
        picker. The same choice as Settings -> Preview -> Preview window."""
        place = self.settings.listen.get("preview_place", "side")
        out = place != "window"
        self._close_preview()
        if out:
            self.settings.listen["preview_dock"] = place
        self.settings.listen["preview_place"] = "window" if out else self.settings.listen.get("preview_dock", "side")
        self.settings.save()
        if not self.isVisible():
            return  # it had stayed open with the picker closed: back in means put away
        self._open_preview_panel()
        self._preview_current()

    def _toggle_preview_fullscreen(self):
        """Popped out: fills the screen its window is on, or back to the window."""
        w = self.preview_window
        if not self._popped_out():
            return
        if w.isFullScreen():
            w.showNormal()
        else:
            w.showFullScreen()
        self.preview_panel.set_place("window", w.isFullScreen())
        QTimer.singleShot(150, self._size_frames_for_big)

    def _enlarge_preview(self):
        """Double-click on the picture: full screen where it is when popped out, else the big view."""
        if self._popped_out():
            self._toggle_preview_fullscreen()
        else:
            self.toggle_big_preview()

    def toggle_big_preview(self, on=None):
        """The preview on most of the screen, or back. Returns True if it
        opened. With the preview closed, it opens straight into the big view."""
        big_now = (self._big is not None and self._big.isVisible()) or self._big_opening
        on = (not big_now) if on is None else on
        if on == big_now or self._big_opening:
            return False
        if not on:
            self._leave_big(reopen=True)
            return False
        # The picker's window is never resized while the big view's window
        # opens or closes: on Wayland the compositor can undo such a resize,
        # and the preview then came back on top of the list. So the preview's
        # place beside the picker is kept (empty, see-through) meanwhile.
        if self.preview_panel.isVisible():
            if self._preview_docked():
                self._hold_preview_place()
            elif self.preview_window is not None:
                self.preview_window.close_and_remember()
            self._enter_big()
            return True
        self._stop_audio()
        if self.settings.listen.get("preview_place", "side") == "window":
            self._open_preview_panel()
            self._preview_current()
            self.preview_window.close_and_remember()
            self._enter_big()
            return True
        # straight into the big view: first the room for coming back (One window has it)
        from PySide6.QtGui import QGuiApplication
        if self.settings.listen.get("preview_place", "side") in self.SHARING:
            self._open_mode = self.settings.listen["preview_place"]
            self._enter_big(fresh=True)
            return True
        self._reserve_preview_place()
        if QGuiApplication.platformName().startswith("wayland"):
            self._big_opening = True  # once the compositor has taken the new size
            QTimer.singleShot(90, lambda: self._enter_big(fresh=True))
        else:
            self._enter_big(fresh=True)
        return True

    def _enter_big(self, fresh=False):
        """The preview into the big view. fresh: it wasn't open before."""
        self._big_opening = False
        if fresh and not self.isVisible():  # the picker closed in the meantime
            self._release_preview_place()
            return
        if self._big is None:
            self._big = BigPreview(self)
        self.preview_panel.setMinimumWidth(0)
        self.preview_panel.setMaximumWidth(16777215)
        self._big.set_panel(self.preview_panel)
        self.preview_panel.set_place("big")
        self.preview_panel.show()
        self._big.open()
        if fresh:
            self.preview_button.set_active(True)
            self._sync_info()
            self._preview_current()
        QTimer.singleShot(0, self._size_frames_for_big)

    def _size_frames_for_big(self):
        area = self.preview_panel.image_area()
        dpr = self.preview_panel.devicePixelRatioF() or 1.0
        self.video.max_size = (int(area.width() * dpr), int(area.height() * dpr))
        self._prepare_scrub()  # sharper scrub frames for the bigger picture

    def _leave_big(self, reopen=True):
        """Back from the big view: to the picker's side / its own window
        (reopen), or put away with the preview closed."""
        self._big.hide()
        side = self.settings.listen.get("preview_place", "side") != "window"
        if reopen:
            if not side:
                self._release_preview_place()
            self._open_preview_panel()
            self.activateWindow()
            self.search_edit.setFocus()
            return
        self._dock_preview(side)
        self.preview_panel.hide()
        self._video_timer.stop()
        self.video.stop()
        self.preview_button.set_active(False)
        if self.isVisible():  # a moment later, not while the big view's window is closing
            QTimer.singleShot(200, self._release_unused_place)
        else:
            self._release_preview_place()

    # -- the preview's place beside the picker --
    def _slot_held(self):
        """True while the picker's window has room for the preview but the
        preview isn't in it (it's in the big view)."""
        return self._preview_slot is not None and not self._preview_slot.isHidden()

    def _reserve_preview_place(self):
        """Makes room for the preview beside the picker: the window grows,
        with an empty, see-through slot where the preview goes."""
        if self._preview_slot is None:
            self._preview_slot = QWidget(self)
            self._preview_slot.hide()
        slot, layout = self._preview_slot, self.layout()
        width = self._preview_start_width()
        layout.setSpacing(self._gap())  # (beside or joined: how much room between them)
        picker_width = self._picker_w  # known, not measured: the layout may be in the middle of a change
        # the picker itself doesn't move or change: the preview goes on the
        # side with room - right if it fits, else left; if neither, the pair
        # moves over and the preview gets narrower so both stay on screen
        frame = self.frameGeometry()
        area = _screen_area(frame)
        need = self._gap() + width
        if frame.right() + need > area.right() and frame.left() - need >= area.left():
            side = "left"
        else:
            side = "right"
            width = max(240, self.preview_panel.bar_min_width(),
                        min(width, area.width() - picker_width - self._gap()))
        self.picker_column.setFixedWidth(picker_width)
        slot.setFixedWidth(width)
        layout.removeWidget(slot)
        layout.insertWidget(0 if side == "left" else layout.count(), slot)
        slot.show()
        self._set_size(picker_width + self._gap() + width, self.height())
        if side == "left":
            self.move(self.x() - self._gap() - width, self.y())
        self._keep_on_screen()

    def _hold_preview_place(self):
        """The preview leaves for the big view; its place beside the picker stays."""
        if self._preview_slot is None:
            self._preview_slot = QWidget(self)
        slot = self._preview_slot
        slot.setFixedWidth(self.preview_panel.width())
        self.layout().replaceWidget(self.preview_panel, slot)
        slot.show()

    def _fill_preview_place(self):
        """The preview goes into the place kept for it."""
        slot, layout = self._preview_slot, self.layout()
        layout.removeWidget(self.preview_panel)
        self.preview_panel.setFixedWidth(slot.width())
        layout.replaceWidget(slot, self.preview_panel)
        slot.hide()

    def _release_preview_place(self):
        """The picker without room for a preview at its side."""
        if not self._slot_held():
            return
        picker_width = self._picker_w
        picker_x = self.x() + self.picker_column.x()
        self.layout().removeWidget(self._preview_slot)
        self._preview_slot.hide()
        self.picker_column.setMinimumWidth(0)
        self.picker_column.setMaximumWidth(16777215)
        self.layout().activate()
        self._set_size(picker_width, self.height())
        if picker_x != self.x():
            self.move(picker_x, self.y())

    def _release_unused_place(self):
        if not (self._big is not None and self._big.isVisible()):
            self._release_preview_place()

    # -- framing guides (the Guides menu in the preview's bar) --
    def _guides_menu(self):
        """The Guides picker: each guide drawn as a small picture, click to
        turn it on or off (guides_popup.py)."""
        from .guides_popup import GuidesPopup
        popup = GuidesPopup(self.settings, self._guides, bool(self.settings.listen.get("remember_guides")), self)
        popup.setFont(self.preview_panel.guides_toggle.font())
        popup.changed.connect(self._set_guides)
        popup.remember_changed.connect(self._remember_guides)
        self.preview_panel.menu.hide()  # Guides is one of the options: its picker takes their place
        toggle = self.preview_panel.more_button
        anchor = toggle.mapToGlobal(QPoint(toggle.width(), 0))
        x = anchor.x() - popup.width()
        y = anchor.y() - popup.height() - 8
        area = _screen_area(QRect(anchor, QSize(1, 1)))
        x = max(area.left() + 8, min(x, area.right() - popup.width() - 8))
        if y < area.top() + 8:
            y = toggle.mapToGlobal(QPoint(0, toggle.height())).y() + 8
        popup.move(x, y)
        popup.show()
        popup.setFocus()

    def _set_guide(self, key, on):
        guides = [k for k in self._guides if k != key]
        if on:
            guides.append(key)
        self._set_guides(guides)

    def _set_guides(self, guides):
        order = [k for k, _l in GUIDES]
        self._guides = sorted(set(guides), key=order.index)
        if self.settings.listen.get("remember_guides"):
            self.settings.listen["guides"] = list(self._guides)
            self.settings.save()
        self._sync_guides()

    def _remember_guides(self, on):
        self.settings.listen["remember_guides"] = on
        self.settings.listen["guides"] = list(self._guides) if on else []
        self.settings.save()

    def _sync_guides(self):
        self.preview_panel.canvas.guides = list(self._guides)
        self.preview_panel.guides_toggle.set_checked(bool(self._guides))
        self.preview_panel.canvas.update()

    # -- timecode (Settings -> Preview & listen) --
    def _time_text(self, seconds):
        """00:01:12:14 - the clip's own timecode, like Resolve shows it - or
        None for the plain minutes:seconds."""
        if not self.settings.listen.get("timecode"):
            return None
        fps, start = self._clip_tc
        fps = self.video.fps or fps or 25.0
        nominal = max(1, int(round(fps)))
        frames = int(round(max(0.0, seconds) * fps)) + start
        ff = frames % nominal
        total = frames // nominal
        return f"{total // 3600:02d}:{total // 60 % 60:02d}:{total % 60:02d}:{ff:02d}"

    def _read_clip_tc(self, orig_index):
        """The clip's frame rate and start timecode, from Resolve."""
        self._clip_tc = (0.0, 0)
        if not self.settings.listen.get("timecode"):
            return
        try:
            clip = rc.find_clip_for_row(self.session, orig_index)[0]
            props = clip.GetClipProperty() or {}
            fps = float(str(props.get("FPS") or 0).split()[0] or 0)
            start = str(props.get("Start TC") or "")
            frames = rc.tc_to_frame(start, round(fps)) if start.count(":") + start.count(";") == 3 and fps else 0
            self._clip_tc = (fps, frames)
        except Exception:
            pass

    # -- in/out: play just the marked part --
    def _apply_range(self, path=None):
        marks = self._marks.get(path or self.video.current_path) or {}
        if "in" in marks or "out" in marks:
            self.video.range = (marks.get("in", 0.0), marks.get("out"))
        else:
            self.video.range = None

    def _prepare_scrub(self):
        """The mouse is on the preview: start reading scrub frames for the
        video shown (a sound or a still has none)."""
        path = self.video.current_path
        if not path or not self.video.is_video or not self.settings.listen.get("hover_scrub", True):
            return
        if self.preview_panel.canvas.peaks or path.lower().endswith(AUDIO_EXTENSIONS):
            return
        canvas = self.preview_panel.canvas
        area = canvas.image_area()
        dpr = canvas.devicePixelRatioF() or 1.0
        # frames as big as the preview shows them, in real screen pixels
        size = (int(max(320, area.width()) * dpr), int(max(180, area.height()) * dpr))
        self.scrubber.start(path, self.video.duration, size)

    def _scrub_sound_at(self, seconds):
        """Settings -> Preview -> Play the sound while moving through a clip."""
        path = self.video.current_path
        if not path or not self.settings.listen.get("scrub_sound", False):
            return
        self.scrub_sound.load(path, self.video.muted)  # (read once per clip; silent until it's in)
        self.scrub_sound.at(seconds)
        self._scrub_quiet.start(1500)

    def _on_seek_sound(self, seconds):
        """Dragging (or clicking) along the bar or a sound's waveform while it's
        paused: hear where you are. While it plays, the playing itself is the sound."""
        if self.video.paused:
            self._scrub_sound_at(seconds)

    def _on_scrub_to(self, seconds):
        self._scrub_sound_at(seconds)
        if self.scrubber.path != self.video.current_path:
            self._prepare_scrub()
        canvas = self.preview_panel.canvas
        near = self.scrubber.nearest(seconds)
        if near is not None:
            canvas.scrub_image, self._scrub_shown_at = near
        self.scrubber.request(seconds)
        canvas.update()

    def _on_scrub_frame(self, image, seconds, generation):
        """A frame read for where the mouse is - shown if it's closer than
        the strip frame already on screen."""
        canvas = self.preview_panel.canvas
        if generation != self.scrubber.generation or canvas.scrub_x is None:
            return
        shown = getattr(self, "_scrub_shown_at", None)
        if canvas.scrub_image is None or shown is None or \
                abs(seconds - canvas.scrub_seconds) <= abs(shown - canvas.scrub_seconds):
            canvas.scrub_image, self._scrub_shown_at = image, seconds
            canvas.update()

    def _on_scrubbing(self, on):
        """Hover scrub pauses a playing clip; it plays on from where you
        left off when the mouse leaves the picture."""
        if on:
            self._resume_after_scrub = self.video.playing
            if self._resume_after_scrub:
                self.video.toggle_pause()
        elif getattr(self, "_resume_after_scrub", False):
            self._resume_after_scrub = False
            if self.video.is_video and self.video.paused:
                self.video.toggle_pause()

    def _on_mark_moved(self, which, seconds):
        path = self.video.current_path
        if path:
            self._marks.setdefault(path, {})[which] = seconds
            self._apply_range(path)
            self.preview_panel.update_time()

    def _source_range(self, chosen_item, name):
        """(first_frame, end_frame) of the in/out marked for this clip in
        the preview, or None to insert all of it."""
        try:
            path = chosen_item.GetClipProperty("File Path") or ""
            marks = self._marks.get(path)
            why = "in/out"
            if not marks:
                marks = self._sound_bounds(chosen_item, path)
                why = "silence"
            if not marks:
                return None
            fps = float(chosen_item.GetClipProperty("FPS") or 0) or float(
                self.session["timeline"].GetSetting("timelineFrameRate"))
            total = rc.compute_clip_duration(self.settings, chosen_item, name)
            start = int(round(marks.get("in", 0.0) * fps))
            end = int(round(marks["out"] * fps)) if marks.get("out") is not None else total
            end = min(end, total)
            if end - start < 1 or (why == "silence" and start == 0 and end >= total):
                return None
            print(f"[{why}] '{name}': frames {start}-{end}")
            return start, end
        except Exception as e:
            print(f"[in/out] couldn't use the marked range for '{name}': {e}")
            return None

    def _sound_bounds(self, chosen_item, path):
        """Settings -> Music & sound effects -> Leave out silence: where a
        sound really starts and ends, as {"in": s, "out": s or None}."""
        if not path or not self.settings.listen.get("trim_silence", True) or self.session.get("insert_media") == "video":
            return None
        if chosen_item.GetClipProperty("Type") != "Audio":
            return None
        from . import sound_analysis as sa
        hit = sa.levels_only(path)
        sound = (hit or {}).get("sound")
        if not sound:
            return None
        start, end = sound
        if start < 0.02 and end is None:
            return None
        return {"in": start if start >= 0.02 else 0.0, "out": end}

    def _stop_waiting(self, generation):
        if generation == self.video.generation and self.preview_panel.canvas.waiting:
            self.preview_panel.canvas.waiting = False
            self.preview_panel.canvas.update()

    def _on_clipping(self, clipped, generation):
        if generation == self.video.generation:
            self.preview_panel.canvas.clipped = clipped or None

    def _on_parts(self, names, off, generation):
        """The clip in the preview has several sound tracks (a song's stems): their switches."""
        if generation == self.video.generation:
            self.preview_panel.parts.set_parts(names, off)

    def _parts_toggled(self, off):
        """A part switched off or on: heard at once, kept for this file (only), and an insert puts it on the timeline
        switched off."""
        from . import stems
        path = self.video.current_path
        names = self.preview_panel.parts.names
        if not path or not names:
            return
        stems.set_muted(path, names, off)
        self.video.set_muted(off)
        self.sound.muted = set(off)

    def _on_waveform(self, peaks, generation):
        if generation == self.video.generation:
            canvas = self.preview_panel.canvas
            canvas.peaks = peaks or None
            canvas.waiting = False
            canvas.update()

    def _set_space_action(self, mode):
        """The preview's options: what Space does with the clip that's
        playing - the same choice as Settings -> Preview -> What Space does."""
        self.settings.listen["space_action"] = mode
        self.settings.save()
        self.preview_panel.set_space_action(mode)

    def _set_preview_option(self, key, on):
        self.settings.listen[key] = on
        self.settings.save()
        if key == "loop":
            self.video.loop = on
        elif key == "autoplay" and on and self.video.is_video and self.video.paused and self.video.position < 0.05:
            self.video.toggle_pause()  # turning autoplay on starts the clip that's waiting

    def _on_video_state(self, playing, generation):
        if generation == self.video.generation:
            self.preview_panel.set_controls(True)
            self.preview_panel.play_button.set_playing(playing)

    def _on_video_message(self, text):
        self.preview_panel.set_controls(False)
        self.preview_panel.show_message(text)

    PREVIEW_WIDTH = 460
    PREVIEW_GAP = 12  # beside: two cards with this much air between
    SEAM_GRAB = 12    # how wide the line between the picker and the preview is to grab

    SHARING = ("shared",)  # the places where the preview takes its room from the list

    def _mode(self):
        """How the preview sits beside the picker: "side", "shared" or "inside". While it's open, the way it
        opened counts (a change in Settings meanwhile shows the next time)."""
        held = getattr(self, "_preview_slot", None) is not None and self._slot_held()  # (still being built: none)
        if (self.preview_panel.isVisible() and self._preview_docked()) or held:
            return getattr(self, "_open_mode", None) or "side"
        return self.settings.listen.get("preview_place", "side")

    def _shares(self):
        """In its space (2026-10-16): the preview takes its room from the list - the window keeps its size,
        and the list has it back when the preview closes."""
        return self._mode() in self.SHARING

    def _inside(self):
        """No gap: the preview in the picker's own card, a line between (one card drawn)."""
        return self._gap() == 0

    def _gap(self):
        """The room between the picker and the preview beside it (Settings > Preview: dragged or the slider)."""
        try:
            return max(0, min(64, int(self.settings.listen.get("preview_gap", 0))))
        except (TypeError, ValueError):
            return self.PREVIEW_GAP

    def _grows_window(self):
        """Beside: the window is wider than the picker by the preview (and its gap)."""
        held = getattr(self, "_preview_slot", None) is not None and self._slot_held()
        beside = (self.preview_panel.isVisible() and self._preview_docked()) or held
        return beside and not self._shares()

    def _preview_start_width(self):
        """The preview's width beside the picker: the one it was dragged to, else PREVIEW_WIDTH (both at 100 %)."""
        from .fonts import picker_size_scale
        return round((self.settings.listen.get("preview_width") or self.PREVIEW_WIDTH) * picker_size_scale(self.settings))

    def _preview_min_width(self):
        return max(240, self.preview_panel.bar_min_width())

    def _picker_min_width(self):
        from .fonts import picker_size_scale
        return round(360 * picker_size_scale(self.settings))

    def _preview_on_right(self):
        """By the layout's order, not where they're drawn (in the middle of a resize those overlap)."""
        layout = self.layout()
        return layout.indexOf(self.preview_panel) > layout.indexOf(self.picker_column)

    def _place_seam(self):
        """The handle between the picker and the preview beside it: drag it and the one grows into the other."""
        handle = getattr(self, "seam_handle", None)
        if handle is None:
            return
        beside = self.preview_panel.isVisible() and self._preview_docked() and not self._slot_held()
        if not beside:
            handle.hide()
            return
        pick, prev = self.picker_column.geometry(), self.preview_panel.geometry()
        middle = (pick.right() + prev.left() + 1) / 2 if self._preview_on_right() else (prev.right() + pick.left() + 1) / 2
        grab = max(self.SEAM_GRAB, self._gap() + 4)
        handle.setGeometry(round(middle - grab / 2), 0, grab, self.height())
        handle.show()
        handle.raise_()

    def _seam_start(self):
        return (self.picker_column.width(), self.preview_panel.width(), self._preview_on_right())

    def _seam_dragged(self, dx, start):
        """The line moved dx px from where the drag began: the picker and the preview trade width, the window stays."""
        picker_w, preview_w, right = start
        total = picker_w + preview_w
        new = picker_w + (dx if right else -dx)
        new = max(self._picker_min_width(), min(new, total - self._preview_min_width()))
        self.preview_panel.setFixedWidth(total - new)
        if not self._shares():  # (sharing its space: the list takes what's left by itself)
            self.picker_column.setFixedWidth(new)
            self._picker_w = new
        self._place_seam()

    def _remember_split(self):
        """After a drag: the preview's width for next time (Beside: the picker's too - One window's window didn't
        change)."""
        from .fonts import picker_size_scale
        if not self._shares():
            self._picker_w = self.picker_column.width()
            self.settings.display["window_width"] = self.picker_column.width()
        self.settings.listen["preview_width"] = round(self.preview_panel.width() / picker_size_scale(self.settings))
        self.settings.save()

    def _open_inside(self):
        """One window / Beside in the picker's space: the preview into the right of the picker's own window. The window stays as it is - unless
        it's too narrow for both, then it grows that much, and goes back when the preview closes."""
        layout = self.layout()
        layout.setSpacing(self._gap())
        self.picker_column.setMaximumWidth(16777215)
        self.picker_column.setMinimumWidth(self._picker_min_width())
        if self._slot_held():  # back from the big view: into the place it kept
            self._fill_preview_place()
            return
        layout.removeWidget(self.preview_panel)
        layout.addWidget(self.preview_panel)  # (always on the right)
        least = self._picker_min_width() + self._gap() + self._preview_min_width()
        self._grown_from = None
        if self.width() < least:
            self._grown_from = self.width()
            self._set_size(least, self.height())
            self._keep_on_screen()
        room = max(self.width(), least) - self._picker_min_width() - self._gap()
        self.preview_panel.setFixedWidth(max(self._preview_min_width(), min(self._preview_start_width(), room)))

    def _close_inside(self):
        self.preview_panel.hide()
        self.seam_handle.hide()
        self.picker_column.setMinimumWidth(0)
        self.picker_column.setMaximumWidth(16777215)
        self._set_least_size()  # (smaller allowed first, then asked for)
        grown, self._grown_from = getattr(self, "_grown_from", None), None
        if grown:
            self.layout().activate()  # forget the hidden preview's width before shrinking
            self._set_size(grown, self.height())

    def _reset_split(self):
        """A double-click on the seam: the preview back to its own width, the picker keeps the rest."""
        from .fonts import picker_size_scale
        start = self._seam_start()
        width = round(self.PREVIEW_WIDTH * picker_size_scale(self.settings))
        self._seam_dragged(start[1] - width if start[2] else width - start[1], start)
        self._remember_split()

    def _on_video_frame(self, image, position, duration, generation):
        if generation == self.video.generation:  # ignore frames from a clip we've moved away from
            self.preview_panel.show_frame(image, position, duration)

    def toggle_preview(self):
        """The preview button / its key."""
        self.preview_clip()

    def _keep_on_screen(self):
        """Moves the window back inside its screen if any of it sticks out."""
        frame = self.frameGeometry()
        fitted = _fit_rect(frame, _screen_area(frame))
        if fitted.topLeft() != frame.topLeft():
            self.move(self.x() + fitted.left() - frame.left(), self.y() + fitted.top() - frame.top())

    def _preview_docked(self):
        """True when the preview sits next to the picker (not in its own window)."""
        return self.preview_panel.parentWidget() is self

    def _dock_preview(self, docked):
        """Moves the preview between the picker's side and its own window."""
        parent = self.preview_panel.parentWidget()
        if docked and parent is self:
            return
        if not docked and self.preview_window is not None and parent is self.preview_window:
            return
        if docked:
            self.layout().addWidget(self.preview_panel)
        else:
            if self.preview_window is None:
                self.preview_window = PreviewWindow(self)
            self.preview_window.set_panel(self.preview_panel)

    def _open_preview_panel(self):
        if self.settings.listen.get("preview_place", "side") == "window":
            self._dock_preview(False)
            self.preview_panel.setMinimumWidth(0)
            self.preview_panel.setMaximumWidth(16777215)
            self.preview_panel.show()
            self.preview_window.open()
            self.preview_panel.set_place("window", self.preview_window.isFullScreen())
            self.preview_button.set_active(True)
            self._sync_info()
            area = self.preview_panel.image_area()
            self.video.max_size = (int(max(area.width(), 640) * 2), int(max(area.height(), 360) * 2))
            return
        self._dock_preview(True)
        self.preview_panel.set_place("side")
        place = self.settings.listen.get("preview_place", "side")
        self._open_mode = place if place in self.SHARING else "side"
        if self._open_mode in self.SHARING:
            self._open_inside()
        else:
            if not self._slot_held():
                self._reserve_preview_place()
            self._fill_preview_place()
        self.preview_panel.show()
        self.preview_button.set_active(True)
        self._sync_info()
        self._set_least_size()
        QTimer.singleShot(0, self._place_seam)
        area = self.preview_panel.image_area()
        self.video.max_size = (int(area.width() * 2), int(max(120, self.height() - 80) * 2))

    def _close_preview(self):
        self._card_opened_preview = False
        self.preview_panel.info.hide()
        self.scrub_sound.forget()
        if not self.preview_panel.isVisible():
            return
        if not self.settings.listen.get("remember_guides") and self._guides:
            self._set_guides([])
        if self._big is not None and self.preview_panel.parentWidget() is self._big:
            self._leave_big(reopen=False)
            return
        self._video_timer.stop()
        self.video.stop()
        self.preview_button.set_active(False)
        if not self._preview_docked():
            self.preview_window.close_and_remember()
            return
        if self._shares():  # the list takes its room back, the window stays
            self._close_inside()
            self._set_least_size()
            self.update()
            return
        picker_width = self._picker_w
        picker_x = self.x() + self.picker_column.x()
        self.preview_panel.hide()
        self.seam_handle.hide()
        self._set_least_size()
        self.picker_column.setMinimumWidth(0)
        self.picker_column.setMaximumWidth(16777215)
        self.layout().activate()  # forget the hidden preview's width before shrinking
        self._set_size(picker_width, self.height())
        if picker_x != self.x():  # it was on the left: the picker stays where it is
            self.move(picker_x, self.y())

    def _preview_current(self, play=False, quiet=False):
        """The highlighted clip into the preview. play: start it whatever
        Autoplay says. quiet: wait on the first frame whatever Autoplay says."""
        if getattr(self, "expression_sheet", None) is not None and self.expression_sheet.isVisible():
            self.show_node_in_preview(self.expression_sheet.node)  # Expressions is open: the node it points at
            return
        orig_index = self._current_orig_index()
        if orig_index is None or orig_index >= len(self.model.rows):
            return
        row = self.model.rows[orig_index]
        if row.category != "expression" and self.settings.listen.get("show_info", True) \
                and self.preview_panel.isVisible() and self.preview_panel.info.isHidden():
            self.preview_panel.info.show()  # (an expression before this one had put it away)
        if self.preview_panel.info.isVisible():
            self.preview_panel.info.set_rows(self._clip_info(orig_index))
        self.preview_panel.reset(row.name, row.category)
        analysis = getattr(row, "analysis", None) or {}
        if row.category == "audio" and getattr(row, "music", False) and row.bpm and "beat0" in analysis \
                and self.settings.listen.get("show_beat_grid", True):
            # the tempo tuned to the whole song where there is one (it keeps the lines on the beat to the end)
            self.preview_panel.canvas.beats = (float(analysis.get("beat_bpm") or row.bpm), float(analysis["beat0"]))
            self.preview_panel.canvas.loop = analysis.get("loop") or None
        if row.category == "node" and row.path:  # a Fusion node: what it does, in a line
            self.video.stop()
            what = scripts_fusion.TOOL_DESCRIPTIONS.get(row.path)
            category = (row.folder_list or "").replace("Tools\\", "").replace("\\", " \u203a ")
            self.preview_panel.show_message(what or (f"A {category} node." if category else "A Fusion node."))
            return
        if row.category in ("macro", "comp") and row.path:
            from . import fusion_graph
            self.video.stop()
            graph = fusion_graph.load(row.path)
            if graph:
                self.preview_panel.canvas.graph = graph
                self.preview_panel.canvas.update()
            else:
                self.preview_panel.show_message("Couldn't read the nodes in this file.")
            return
        if row.category == "expression" and row.path in fusion_expressions.BY_KEY:
            self.video.stop()  # an expression: what it does, played, and its code
            self.preview_panel.info.hide()  # (all the room goes to that; clip info has nothing to say here)
            self.preview_panel.canvas.card = fusion_expressions.BY_KEY[row.path]
            self.preview_panel.canvas.update()
            return
        if row.category == "title" and row.glyph:  # Basics: its symbol, nothing to say
            self.video.stop()
            self.preview_panel.canvas.symbol = row.glyph
            self.preview_panel.show_message("")
            return
        if self._is_external_row(orig_index) or row.category in ("bin", "selected", "adjustment", "compound"):
            self.video.stop()
            self.preview_panel.show_message("Nothing to preview for this row.")
            return
        path = self._row_file_path(orig_index)
        keep_place = False
        if path and path == self.video.current_path and self.video.is_video and not self.video.paused:
            return  # still playing: its next frame is on its way
        if path and path == self.video.current_path:
            # the same clip (the list was rebuilt under it): reset() above took its picture away - read it
            # again, from where it was, rather than leave the preview empty until you move off it and back
            was_paused = self.video.is_video and self.video.paused
            keep_place = True
            self.video.stop()
            play = play or (not was_paused and self.settings.listen["autoplay"] and not quiet)
            quiet = quiet or was_paused
        self.video.loop = self.settings.listen["loop"]
        if path != self.scrubber.path:
            self.scrubber.stop()  # its frames belonged to the clip before
        self.video.remember = keep_place or self.settings.listen.get("remember_place", True)
        self._apply_range(path)
        self._read_clip_tc(orig_index)
        if not self.settings.listen.get("remember_guides") and self._guides:
            self._set_guides([])  # guides that aren't remembered belong to the clip they were set on
        self._show_used_parts()
        self.video.play(path, autoplay=play or (self.settings.listen["autoplay"] and not quiet))
        self._analyse_when_seen(row)
        marks = self._marks.get(path, {})
        self.preview_panel.canvas.mark_in, self.preview_panel.canvas.mark_out = marks.get("in"), marks.get("out")
        # the first frame / the waveform normally arrives at once; show the symbol if it doesn't
        generation = self.video.generation
        QTimer.singleShot(800, lambda: self._stop_waiting(generation))

    def _analyse_when_seen(self, row):
        """A sound not analysed yet is, once it's been in the preview a moment - quietly, one at a time: music or
        a sound effect, its tempo (2026-11-01: a song whose name doesn't say so had the plain sound symbol until
        Analyse sounds was run from Settings)."""
        if row.category != "audio" or not row.file or not self.settings.listen.get("split_music", True) \
                or (row.secs and row.secs > 15 * 60):
            return
        from . import sound_analysis as sa
        if not sa.available() or sa.complete(sa.cached(row.file)):
            return
        if not hasattr(self, "_seen_timer"):
            self._seen_timer = QTimer(self)
            self._seen_timer.setSingleShot(True)
            self._seen_timer.timeout.connect(self._analyse_seen)
            self._seen_busy = False
        self._seen_row = row
        self._seen_timer.start(1000)  # (not every row the arrows pass over)

    def _analyse_seen(self):
        row = getattr(self, "_seen_row", None)
        orig = self._current_orig_index()
        here = self.model.rows[orig] if orig is not None and orig < len(self.model.rows) else None
        if row is None or self._seen_busy or row is not here:
            return  # (moved on meanwhile: the next one it rests on is analysed)
        self._seen_busy = True
        from . import sound_analysis as sa

        def work():
            try:
                result = sa.analyse(row.file, row.music, retry_errors=True)
                if result is not None:
                    self.analyser.found.emit(row, result)  # (applied on the picker's own thread)
            except Exception as e:
                print(f"[analyse] '{row.name}': {e}")
            finally:
                self._seen_busy = False
        import threading
        threading.Thread(target=work, name="clipse-analyse-seen", daemon=True).start()

    def _show_used_parts(self):
        """The preview's marks for the parts of the highlighted clip that are
        on the timeline already (Settings -> Preview). The timeline is read
        a little at a time; the marks fill in as it goes."""
        canvas = self.preview_panel.canvas
        canvas.used, canvas.used_times = [], 0
        timeline = self.session.get("timeline")
        orig_index = self._current_orig_index()
        groups = self.session.get("filtered_group_list") or []
        if timeline is None or orig_index is None or orig_index >= len(groups) \
                or not self.settings.listen.get("show_used_parts", True):
            return
        if self._used is None:
            self._used = tt.UsedParts(timeline)
        ids = [instance[0] for instance in groups[orig_index][1] if instance and isinstance(instance[0], str)]
        canvas.used, canvas.used_times = self._used.of(ids)
        canvas.update()
        if not self._used.done:
            self._used_timer.start(0)

    def _used_step(self):
        if self._used is None or self._used.done or not self.preview_panel.isVisible():
            return
        try:
            self._used.step()
        except Exception as e:
            print(f"[preview] couldn't read what's on the timeline: {e}")
            self._used.done = True
        self._show_used_parts()

    def _row_file_path(self, orig_index):
        """The file on disk behind a Media Pool row (cached per open)."""
        if orig_index >= len(self.session.get("filtered_group_list", [])):
            return ""
        path = self._audio_paths.get(orig_index)
        if path is None:
            try:
                clip, _folder, _name = rc.find_clip_for_row(self.session, orig_index)
                path = (clip.GetClipProperty("File Path") or "") if clip else ""
            except Exception:
                path = ""
            self._audio_paths[orig_index] = path
        return path

    def confirm_only(self, media):
        """Alt+V / Alt+A: insert just the picture or just the sound of the
        highlighted (or staged) clips. The inserts themselves run a moment
        later (after the picker hides), so the choice is cleared after them."""
        self.session["insert_media"] = media
        self.confirm()
        QTimer.singleShot(0, lambda: self.session.update(insert_media=None))

    def confirm_compound(self):
        """Alt+Enter: insert as Enter does, then wrap what went in into one compound clip (as Insert as >
        Afterwards > Compound clip, for this insert only)."""
        self.session["insert_convert"] = "compound"
        self.confirm()
        QTimer.singleShot(0, lambda: self.session.update(insert_convert=None))

    def confirm(self, sequential=False, preset_id=None, place=None):
        """Enter: insert with the preset in use (Insert as). Ctrl+Enter uses
        Back to back, Alt+M / Alt+C At every marker / On every cut."""
        if self._swap is not None and not (sequential or preset_id or place):
            self._finish_swap()
            return
        orig = self._current_orig_index()
        if orig is not None and orig < len(self.model.rows) and self.settings.general.get("learn_picks", True):
            picks.record(self.model.query, self.model.rows[orig])  # "wh" -> this whoosh: first next time
        if orig is not None and orig < len(self.model.rows) and self.model.rows[orig].category == "action":
            self._run_palette_action(self.model.rows[orig])
            return
        if orig is not None and orig < len(self.model.rows) and self.model.rows[orig].category == "shortcut":
            self._open_shortcut(self.model.rows[orig])
            return
        if orig is not None and orig < len(self.model.rows) and self.model.rows[orig].category == "prefix":
            target = self.model.rows[orig].path  # (the : menu: search in that kind - the pill)
            forms = self.settings.prefixes.get(target) or [target]
            self.search_edit.setText(">" if target == ">" else f"{forms[0]}:")
            self.search_edit.setFocus()
            return
        if orig is not None and orig < len(self.model.rows) and self.model.rows[orig].category == "expression":
            self._confirm_expression(self.model.rows[orig])  # (asks before it hides, when it has to)
            return
        if self._fusion_target() and orig is not None and orig < len(self.model.rows) and not self.model.staged \
                and self.model.rows[orig].category in FUSION_SKIPPED_CATEGORIES:
            what = "A sound" if self.model.rows[orig].category == "audio" else "An adjustment clip"
            self._flash_hint(f"{what} can't go into a Fusion composition", 3500)
            return
        if self.model.chain:
            self._remember_search()
            self._add_fusion_chain(connect=not sequential)
            return
        self._remember_search()
        if self._is_external_row(self._current_orig_index()):
            # Ctrl+Enter on a macro: insert it without connecting it
            self._do_external_action(connect_macro=not sequential)
            return
        if place is not None:  # Alt+M / Alt+C: at every marker or cut
            preset = presets_mod.placing(self.settings, place)
        elif preset_id is None and sequential:  # Ctrl+Enter: one after another
            preset = presets_mod.back_to_back(self.settings)
        elif preset_id is not None:
            preset = presets_mod.get(self.settings, preset_id) or presets_mod.active(self.settings)
        elif self._preset_once:
            preset = presets_mod._clean(self._preset_once)
            preset["id"], preset["name"] = "history", "History"
        else:
            preset = presets_mod.active(self.settings)
        self._preset_once = None
        if preset["where"] in ("markers", "cuts") and not self._fusion_target():
            # nothing to place at? say so here, while the picker is still open
            timeline = self.session.get("timeline")
            try:
                found = self._place_frames(timeline, preset["where"], preset.get("marker_colours"),
                                           preset.get("cut_tracks"), preset.get("cut_edges", "between")) \
                    if timeline is not None else []
            except Exception:
                found = []
            if not found:
                only = " or ".join(c.lower() for c in preset.get("marker_colours") or [])
                self._flash_hint((f"No {only} markers on the timeline - Insert as chooses which ones count." if only
                                  else "No markers on the timeline or its clips - add one with M first.")
                                 if preset["where"] == "markers" else
                                 f"No cuts on {', '.join(preset.get('cut_tracks') or ['V1'])} - Insert as chooses "
                                 f"which tracks count.", 4000)
                return
        staged = self.model.staged
        multi = [i for i in self._get_multi_selected_orig_indices() if not self._is_external_row(i)]
        if staged:
            indices = [idx for idx, count in staged.items() for _ in range(count)]
            highlighted_row = self.list_view.currentIndex().row()
            if self.settings.general["also_insert_highlighted_on_enter"] and highlighted_row >= 0:
                highlighted_idx = self.model.visible[highlighted_row]
                if highlighted_idx not in staged:
                    indices.append(highlighted_idx)
            self.model.clear_staged()
            self._update_staged_summary()
            self._clear_multi_selection()
            self.hide()
            QTimer.singleShot(0, lambda: self._insert_with(preset, indices))
        elif len(multi) > 1:
            self._clear_multi_selection()
            self.hide()
            QTimer.singleShot(0, lambda: self._insert_with(preset, multi))
        else:
            row = self.list_view.currentIndex().row()
            if row < 0 or row >= len(self.model.visible):
                self._flash_hint("Nothing to insert", 1800)  # stay open
                return
            self.hide()
            idx = self.model.visible[row]
            QTimer.singleShot(0, lambda: self._insert_with(preset, [idx]))

    def _current_page_key(self):
        """Maps Resolve's current page to a page_defaults key — only
        "fusion" gets its own config, every other page (edit, cut, color,
        fairlight, deliver, media) shares "other"."""
        try:
            page = self.resolve.GetCurrentPage()
        except Exception:
            page = None
        return "fusion" if page == "fusion" else "other"

    # what comes first with nothing typed: on the Fusion page the macros, then nodes and expressions - the scripts
    # last (2026-10-17: they came first; "nodes are the priority", then "macros are arguably one of the most
    # important fusion things")
    DEFAULT_ORDER = {"fusion": ("macros", "nodes", "expressions", "comps", "scripts", "clips"),
                     "other": ("clips", "scripts", "macros", "comps", "nodes", "expressions")}

    def _provide_default_rows(self):
        """What shows with no search prefix at all — page-dependent per
        Settings -> General -> Page Defaults. A colon prefix always
        bypasses this and searches that specific source directly."""
        page = self._current_page_key()
        cfg = self.settings.page_defaults.get(page, self.settings.page_defaults["other"])
        rows = []
        for source in self.DEFAULT_ORDER.get(page, self.DEFAULT_ORDER["other"]):
            if not cfg.get(source):
                continue
            if source == "clips":
                rows.extend(self.model.clip_rows)
            elif source == "expressions":
                expressions = self._provide_external_rows("expression")
                if cfg.get("shortcuts", True):  # (the way to the cheat sheet is a shortcut row already: not twice)
                    expressions = [r for r in expressions if r.path != "bar:cheat_sheet"]
                rows.extend(expressions)
            else:
                rows.extend(self._provide_external_rows(source[:-1]))
        if page != "fusion":  # Basics (on the Fusion page a title or a solid colour is a node, under n:)
            rows.extend(self._basic_rows(""))
        if cfg.get("shortcuts", True):
            rows.extend(self._provide_external_rows("shortcut"))
        return rows

    def _provide_external_rows(self, kind):
        rows = self._external_rows(kind)
        for row in rows:
            row.favorited = f"{row.category}:{row.path or row.name}" in self.favorited_names
        return rows

    def _external_rows(self, kind):
        """Called by ClipListModel when a run:/script:/macro:/comp:/p:/
        project: prefix is typed — fetches that kind's rows fresh each
        time (cheap enough: a folder scan or a project-list call, not
        pre-loaded at every picker open)."""
        if kind == "shortcut":  # ways into Clipse itself (go:)
            icon = self.settings.icons.get("shortcut", "")
            # (the name says it: nothing in the second column. What it's about only helps find it.)
            return [rc.RowData(icon, "shortcut", name, "", path=key, tags=f"{words} {about}")
                    for key, name, about, words, _open in self._shortcuts()]
        print(f"[external] '{kind}:' prefix fired")
        if kind == "script":
            folders = list(self.settings.folders["scripts"]) + scripts_fusion.system_scripts_folders()
            files = scripts_fusion.scan_folders(folders, {".py", ".lua"})  # (Lua too: Resolve runs both)
            print(f"[external] scanning scripts folders {folders} -> found {len(files)} script(s)")
            icon = self.settings.icons["script"]
            # ...and Clipse's own scripts in Resolve's menu - as their actions (the red symbol), Enter runs it
            own = [self._action_row(i, g, label, key, "Clipse")
                   for i, (g, label, key, _fn) in enumerate(self._all_actions()) if label in RESOLVE_KEYED]
            return [rc.RowData(icon, "script", name, parent, path=path) for path, name, parent in files] + own
        if kind == "macro":
            folders = self.settings.folders["macros"]
            files = scripts_fusion.scan_folders(folders, {".setting"})
            print(f"[external] scanning macros folders {folders} -> found {len(files)} .setting file(s)")
            icon = self.settings.icons["macro"]
            return [rc.RowData(icon, "macro", name, parent, path=path) for path, name, parent in files]
        if kind == "comp":
            folders = self.settings.folders["fusion_comps"]
            files = scripts_fusion.scan_folders(folders, {".comp"})
            print(f"[external] scanning fusion_comps folders {folders} -> found {len(files)} .comp file(s)")
            icon = self.settings.icons["comp"]
            return [rc.RowData(icon, "comp", name, parent, path=path) for path, name, parent in files]
        if kind == "timeline":
            return self._timeline_rows()
        if kind == "marker":
            return self._marker_rows()
        if kind == "folder":
            icon = self.settings.icons["folder"]
            return [rc.RowData(icon, "folder", name, where, path=path)
                    for path, name, where in scripts_fusion.useful_folders(self.settings.folders)]
        if kind == "node":
            icon = self.settings.icons["node"]
            return [rc.RowData(icon, "node", name, category, path=tool_id)
                    for tool_id, name, category in scripts_fusion.list_fusion_tools(self.resolve)]
        if kind == "expression":  # code that moves things by itself: the name, and the setting it goes on
            icon = self.settings.icons["expression"]
            # first, and unlike the rest: the way to the cheat sheet (its shortcut row)
            sheet = rc.RowData(self.settings.icons.get("shortcut", ""), "shortcut", "Expressions", "Write your own",
                               path="bar:cheat_sheet")
            return [sheet] + [rc.RowData(icon, "expression", entry["name"], fusion_expressions.where(entry),
                                         path=entry["key"], tags=fusion_expressions.search_words(entry))
                              for entry in fusion_expressions.LIBRARY]
        if kind == "project":
            try:
                project_manager = self.resolve.GetProjectManager()
                current_project = self.session.get("project")
                current_name = current_project.GetName() if current_project else None
                names = scripts_fusion.list_other_projects(project_manager, current_name)
                print(f"[external] other projects found: {names}")
            except Exception as e:
                print(f"Couldn't list other projects: {e}")
                names = []
                project_manager = None

            icon = self.settings.icons["project"]
            entries = []  # (name, segments, sort_key)
            for n in names:
                created_ts, modified_ts = (None, None)
                if project_manager is not None:
                    created_ts, modified_ts = scripts_fusion.get_project_timestamps(project_manager, n)
                segments = self._build_project_info_segments(created_ts, modified_ts)
                if created_ts is not None or modified_ts is not None:
                    by_created = self.settings.general["sort_projects_by_created"]
                    primary_ts = created_ts if by_created else modified_ts
                    sort_key = -(primary_ts if primary_ts is not None else (created_ts or modified_ts))  # newest first
                else:
                    sort_key = 0
                entries.append((n, segments, sort_key))

            # Only actually reorder if at least one project had a real
            # timestamp — otherwise keep Resolve's own list order rather
            # than pretending everything is equally "now".
            if any(e[2] != 0 for e in entries):
                entries.sort(key=lambda e: e[2])

            return [rc.RowData(icon, "project", name, "", info_segments=segments)
                    for name, segments, _key in entries]
        return []

    # Settings pages are also found by what's on them ("theme" -> Appearance)
    _SETTINGS_WORDS = {
        "General": "list rows startup tour demo learning search order",
        "Preview": "player video scrub guides",
        "Sound": "audio volume listening analyse music bpm",
        "Timeline": "insert tracks subtitles titles",
        "Organise": "templates template bins colours colors organize sort project media pool tpl",
        "Fusion": "nodes expressions sliders",
        "Scripts": "resolve menu adjustment composition grab frame tidy step",
        "Appearance": "theme themes colours colors font size look dark icons",
        "Keybindings": "shortcuts keys hotkeys keyboard keybinds",
        "Folders": "paths macros files where scripts",
        "Search Prefixes": "prefix letters",
        "About": "version update report problem feedback bug help idea backup move share",
    }

    def _shortcuts(self):
        """Shortcuts: rows that take you somewhere in Clipse itself - what's in the bottom
        bar, and every page of Settings. (key, name, a line about it, words it's also found by, what
        opens it.) Their own kind of row (a grey gear, go:), switched on per page in Settings >
        General like any other source; what they open is never listed a second time as an action."""
        from .settings_dialog import SettingsDialog
        rows = [
            ("bar:actions", "Actions", "Everything Clipse can do", "commands tiles do run",
             lambda: self.actions_panel.toggle()),
            ("bar:insert_as", "Insert as", "How clips land on the timeline", "presets stacked back to back spaced markers",
             self.open_insert_options),
            ("bar:cheat_sheet", "Expressions", "What you can write in a Fusion expression",
             "expressions expression code fusion cheat sheet functions",
             self._show_cheat_sheet),
            ("bar:history", "History", "What you searched for before", "search searches earlier", self.open_history),
            ("bar:settings", "Settings", "All of it, page by page", "preferences options", self.open_settings),
        ]
        rows += [(f"settings:{title}", f"Settings: {title}", SettingsDialog.PAGE_ABOUT.get(title, ""),
                  f"preferences {self._SETTINGS_WORDS.get(title, '')}", (lambda page=title: self.open_settings(page)))
                 for title, _icon, _builder in SettingsDialog.PAGES]
        # one setting of its own (2026-10-21 - the owner wanted it from the picker, "only in Settings"): Settings >
        # Scripts, its rows lit
        rows.append(("settings:step", "Settings: Step back / forward", "How far each moves the playhead",
                     "step steps frames skip playhead forward back",
                     lambda: self.open_settings("Scripts", field=("step_back_frames", "step_forward_frames"))))
        return rows

    # (the actions that open the same places - left out of a plain search while shortcuts are listed)
    _SHORTCUT_ACTIONS = set()  # (no action opens what a shortcut does any more)

    def _open_shortcut(self, row):
        for key, _name, _about, _words, open_it in self._shortcuts():
            if key == row.path:
                rc.record_recent(f"shortcut:{key}")
                QTimer.singleShot(0, open_it)
                return

    def _go_to_frame(self, frame):
        """The playhead to a timeline frame (a marker's)."""
        timeline = self.session.get("timeline")
        try:
            fps = float(timeline.GetSetting("timelineFrameRate"))
            timeline.SetCurrentTimecode(tt.frame_to_tc(frame, fps))
            return f"Playhead at frame {frame}"
        except Exception as e:
            return f"Couldn't move the playhead: {e}"

    def _switch_timeline(self, name):
        project = self.session.get("project")
        try:
            for i in range(1, int(project.GetTimelineCount() or 0) + 1):
                timeline = project.GetTimelineByIndex(i)
                if timeline.GetName() == name:
                    if project.SetCurrentTimeline(timeline):
                        self.session["timeline"] = timeline
                        return f"Switched to timeline '{name}'."
                    return f"Resolve didn't switch to '{name}'."
        except Exception as e:
            return f"Couldn't switch timeline: {e}"
        return f"Timeline '{name}' wasn't found."

    def _timeline_rows(self):
        """t: - the project's timelines with their length; the open one is marked."""
        project = self.session.get("project")
        if project is None:
            return []
        try:
            current = project.GetCurrentTimeline()
            current_id = current.GetUniqueId() if current else None
            count = int(project.GetTimelineCount() or 0)
        except Exception as e:
            print(f"Couldn't list the timelines: {e}")
            return []
        icon = self.settings.icons["timeline"]
        rows = []
        for i in range(1, count + 1):
            try:
                timeline = project.GetTimelineByIndex(i)
                name = timeline.GetName()
                fps = float(timeline.GetSetting("timelineFrameRate") or 24) or 24
                length = (int(timeline.GetEndFrame()) - int(timeline.GetStartFrame())) / fps
                is_current = current_id is not None and timeline.GetUniqueId() == current_id
            except Exception:
                continue
            minutes, seconds = divmod(int(length), 60)
            hours, minutes = divmod(minutes, 60)
            length_text = f"{hours}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes}:{seconds:02d}"
            segments = [(length_text, None)] + ([("   open now", "recent")] if is_current else [])
            rows.append(rc.RowData(icon, "timeline", name, "", info_segments=segments))
        return rows

    def _marker_rows(self):
        """mk: - the open timeline's markers in timeline order: the name (or its note, or its colour), where it is,
        its note. The tag is the marker's colour."""
        timeline = self.session.get("timeline")
        if timeline is None:
            return []
        try:
            markers = timeline.GetMarkers() or {}
            fps = float(timeline.GetSetting("timelineFrameRate") or 24) or 24
            start = int(timeline.GetStartFrame())
        except Exception as e:
            print(f"Couldn't read the markers: {e}")
            return []
        icon = self.settings.icons["marker"]
        rows = []
        for frame in sorted(markers, key=float):
            info = markers[frame] or {}
            name, note, colour = str(info.get("name") or ""), str(info.get("note") or ""), str(info.get("color") or "")
            at = int(float(frame))
            seconds = at / fps
            minutes, secs = divmod(int(seconds), 60)
            hours, minutes = divmod(minutes, 60)
            when = f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"
            segments = [(when, None)] + ([("   " + note, None)] if note and name else [])
            row = rc.RowData(icon, "marker", name or note or f"{colour or 'A'} marker", "", path=str(start + at),
                             info_segments=segments, tags=f"{colour} {note}".lower())
            row.color = colour
            rows.append(row)
        return rows

    def _build_project_info_segments(self, created_ts, modified_ts):
        """(text, color_key) pairs for a project row's Created/Modified
        info — color_key is None for label text, or 'recent'/'medium'/
        'old' for the age value itself, colored by the delegate."""
        medium_days = self.settings.display["project_age_medium_days"]
        old_days = self.settings.display["project_age_old_days"]
        segments = []
        if created_ts is not None:
            segments.append(("Created: ", None))
            segments.append((scripts_fusion.format_relative_time(created_ts),
                              scripts_fusion.age_color_category(created_ts, medium_days, old_days)))
        if modified_ts is not None:
            if segments:
                segments.append(("   ", None))
            segments.append(("Modified: ", None))
            segments.append((scripts_fusion.format_relative_time(modified_ts),
                              scripts_fusion.age_color_category(modified_ts, medium_days, old_days)))
        return segments

    def _do_external_action(self, connect_macro=True):
        if self._external_action_pending:
            print("[external] ignoring a repeated trigger — an action is already in progress for this open.")
            return
        self._external_action_pending = True

        row_index = self.list_view.currentIndex().row()
        if 0 <= row_index < len(self.model.visible) and \
                self.model.rows[self.model.visible[row_index]].category == "folder":
            self._keep_focus_elsewhere = True  # the file manager opening should keep focus
        self.hide()
        if row_index < 0:
            return
        orig_index = self.model.visible[row_index]
        row = self.model.rows[orig_index]

        if row.category not in ("title", "template"):
            rc.record_recent(f"{row.category}:{row.path or row.name}")
        if row.category == "script":
            print(scripts_fusion.run_script(row.path, self.resolve))
        elif row.category == "macro":
            ok, message = scripts_fusion.import_macro(self.resolve, row.path, self.session.get("timeline"),
                                                      connect=connect_macro)
            print(message)
            if ok:
                self._remember_fusion_action(f"adding {row.name}")
                self._record_fusion_history([("macro", row.name, row.path)])
        elif row.category == "timeline":
            print(self._switch_timeline(row.name))
        elif row.category == "marker":
            print(self._go_to_frame(int(row.path)))
        elif row.category == "layout":
            message = self._layout_action(row.path)
            print(message)
            if message.startswith(("Resolve didn't", "Couldn't")):
                self._say(message, 3500)
        elif row.category == "title":
            print(self._add_basic(row))
        elif row.category == "folder":
            from .file_manager import open_folder
            print(open_folder(row.path, command=self.settings.files["file_manager"]) or f"Opened {row.path}")
        elif row.category == "node":
            ok, message = scripts_fusion.insert_tool(self.resolve, row.path, row.name, self.session.get("timeline"),
                                                     connect=connect_macro)
            print(message)
            if ok:
                self._remember_fusion_action(f"adding {row.name}")
                self._record_fusion_history([("node", row.name, row.path)])
        elif row.category == "comp":
            print(scripts_fusion.load_comp(self.resolve, row.path, self.session.get("timeline")))
        elif row.category == "project":
            print(scripts_fusion.switch_project(self.resolve.GetProjectManager(), row.name))
        elif row.category == "template":
            from . import project_templates as pt
            action, _sep, name = (row.path or "").partition(":")
            if action == "save":
                print(pt.save_current(self.resolve, name))
            else:
                template = dict(pt.all_templates_by_name().get(name) or {})
                print(pt.apply(self.resolve, template, name) if template else f"No template called {name}.")
                if template:
                    stats.record("template")
                self._force_refresh_next = True  # new bins: rescan next time

    # -- placing at every marker / cut --
    def place_at(self, kind):
        """Alt+M / Alt+C: the highlighted clip at every timeline marker, or
        at every cut on track V1 - e.g. a whoosh on every cut. With clips
        staged, they take turns (whoosh 1, whoosh 2, whoosh 1 ...). Uses the
        Insert as setup at every marker / cut (presets.placing)."""
        orig = self._current_orig_index()
        if not self.model.staged and (orig is None or self._is_external_row(orig)
                                      or orig >= len(self.model.clip_rows)):
            self._flash_hint("Highlight a clip first", 2000)
            return
        self.confirm(place=kind)

    @staticmethod
    def _timeline_markers(timeline):
        """Every marker as {timeline frame: colour} - the ones on the
        timeline's ruler, and the ones on its clips (M with a clip selected)."""
        start = int(timeline.GetStartFrame())
        found = {}
        for f, info in (timeline.GetMarkers() or {}).items():
            found[start + int(float(f))] = str((info or {}).get("color") or "Blue")
        for track_type in ("video", "audio"):
            for index in range(1, int(timeline.GetTrackCount(track_type) or 0) + 1):
                for item in timeline.GetItemListInTrack(track_type, index) or []:
                    try:
                        marks = item.GetMarkers() or {}
                    except Exception:
                        continue
                    if not marks:
                        continue
                    try:
                        offset = int(item.GetLeftOffset() or 0)  # clip markers count from the clip's source start
                    except Exception:
                        offset = 0
                    begin, end = int(item.GetStart()), int(item.GetEnd())
                    for f, info in marks.items():
                        frame = begin + int(float(f)) - offset
                        if begin <= frame < end:
                            found.setdefault(frame, str((info or {}).get("color") or "Blue"))
        return found

    @staticmethod
    def _timeline_layout(timeline, most=4000):
        """What's on the timeline now, as [(kind "video" / "audio", start, end)] - Insert as draws it faintly
        behind what the insert puts down."""
        out = []
        for kind in ("video", "audio"):
            for index in range(1, int(timeline.GetTrackCount(kind) or 0) + 1):
                for item in timeline.GetItemListInTrack(kind, index) or []:
                    out.append((kind, int(item.GetStart()), int(item.GetEnd())))
                    if len(out) >= most:
                        return out
        return out

    def _place_frames(self, timeline, kind, colours=None, tracks=None, edges="between"):
        """Absolute timeline frames of every marker (only the `colours`
        named, if any), or of every cut on the `tracks` named (V1 when none) -
        where clips meet, or every clip's start / end (`edges`)."""
        if kind == "markers":
            return sorted(frame for frame, colour in self._timeline_markers(timeline).items()
                          if not colours or colour in colours)
        return presets_mod.cut_frames(self._clips_by_track(timeline), tracks, edges)

    @staticmethod
    def _clips_by_track(timeline):
        """{"V1": [(start, end) of each clip], "A2": [...] ...}: every track on the timeline - At every cut picks
        which tracks count, and which of their clips' edges (presets.track_edges)."""
        out = {}
        for kind, letter in (("video", "V"), ("audio", "A")):
            for index in range(1, int(timeline.GetTrackCount(kind) or 0) + 1):
                out[f"{letter}{index}"] = sorted((int(it.GetStart()), int(it.GetEnd()))
                                                 for it in timeline.GetItemListInTrack(kind, index) or [])
        return out

    def _add_fusion_chain(self, connect=True):
        """Enter with nodes / macros staged: adds them - and, on the Fusion
        page, staged clips too - one after another, in the order you staged
        them, as one straight line in the node editor."""
        entries = []
        for e in self.model.chain:
            kind = "tool" if e["category"] == "node" else "macro"
            entries.append((e["seq"], (kind, e["path"], e["name"])))
        if self._fusion_target():
            for idx, count in self.model.staged.items():
                for chosen_item, _folder, name, category in rc.expand_row_to_items(
                        self.session, self.settings, idx, self.selection_order_ids):
                    if category == "audio":
                        continue
                    try:
                        path = chosen_item.GetClipProperty("File Path") or ""
                    except Exception:
                        path = ""
                    media_id, frames = self._media_id_and_frames(chosen_item, name)
                    for _ in range(count):
                        entries.append((self._clip_seq.get(idx, 0), ("clip", path, name,
                                                                    self._source_range(chosen_item, name),
                                                                    media_id, frames)))
        entries = [entry for _seq, entry in sorted(entries, key=lambda t: t[0])]
        went_in = [({"tool": "node", "macro": "macro", "clip": "clip"}[e[0]], e[2], e[1]) for e in entries]
        self.model.clear_staged()
        self._clip_seq = {}
        self._update_staged_summary()
        self.hide()
        def run():
            print(scripts_fusion.insert_chain(self.resolve, entries, self.session.get("timeline"), connect=connect))
            self._remember_fusion_action(f"adding {len(entries)} nodes")
            self._record_fusion_history(went_in)
        QTimer.singleShot(0, run)

    def _media_id_and_frames(self, chosen_item, name):
        try:
            media_id = chosen_item.GetMediaId()
        except Exception:
            media_id = None
        try:
            frames = int(chosen_item.GetClipProperty("Frames") or 0) or None
        except Exception:
            frames = None
        return media_id, frames

    # -- undo the last Clipse action (Ctrl+Z / "Undo Last Action" in Resolve) --
    def _pull_out(self):
        message = scripts_fusion.pull_out_nodes(self.resolve)
        if message.startswith("Pulled"):
            self._remember_fusion_action("pulling the node out")
            stats.record("pullout")
        return message

    def _tidy(self):
        message = scripts_fusion.tidy_nodes(self.resolve, self.settings.timeline_tools.get("tidy_style", "lines"),
                                            fit=self.settings.timeline_tools.get("tidy_fit_view", True))
        if message.startswith("Tidied"):
            self._remember_fusion_action("the tidy up")
            stats.record("tidy")
        else:  # nothing moved on the screen, so say why
            self._say(message)
        return message

    def _add_basic(self, row):
        """A Basics row: the adjustment clip or Fusion composition at the playhead (Settings > Scripts: which clip,
        how long - the same as their scripts' "at playhead"), or a title / solid colour (_add_from_library)."""
        if row.source not in ("adjust", "comp"):
            return self._add_from_library(row)
        timeline, media_pool = self.session.get("timeline"), self.session.get("media_pool")
        what = tt.PLACED[row.source][0]
        if timeline is None or media_pool is None:
            return f"No timeline to add the {what.lower()} to."
        lookup = tt.lookup_adjustment_clip if row.source == "adjust" else tt.lookup_composition_clip
        clip, message = lookup(self.settings, media_pool)
        if clip is None:
            self._say(message, 7000)
            return message
        tracks, landed = self._track_counts(timeline), []
        message = tt.place_over(self.settings, timeline, media_pool, clip, "fixed", row.source, landed_out=landed)
        if landed:
            self._remember_timeline_action(timeline, [], tracks, f"the {what.lower()}", items=landed)
            self._colour_new(landed)
            stats.record(row.source)
        if not tt.placed_fine(message, row.source):
            self._say(message, 3500)
        return message

    def _add_from_library(self, row):
        """A title or Solid colour (Basics, title:) at the playhead, on the lowest
        track free for it, as long as a picture lasts (Insert as) - from the Media Pool, so it never cuts into V1
        (library.py); typed words go into its Text+."""
        timeline, media_pool = self.session.get("timeline"), self.session.get("media_pool")
        entry = tuple(row.source.split("|", 2)) if row.source else library.TEXT_PLUS
        what = "Solid colour" if entry == library.SOLID else "Title"
        if timeline is None or media_pool is None:
            return f"No timeline to add {what} to."
        clip, message = library.clip_for(media_pool, entry)
        if clip is None:
            self._say(message, 3500)
            return message
        fps = float(timeline.GetSetting("timelineFrameRate") or 24)
        tracks, landed = self._track_counts(timeline), []
        message = tt.place_over(self.settings, timeline, media_pool, clip, "fixed", "library", what=what,
                                frames=round(float(self.settings.presets["still_length"]) * fps), landed_out=landed)
        if landed:
            if row.path:
                library.set_words(landed[0], row.path)
            self._remember_timeline_action(timeline, [], tracks, f"the {what.lower()}", items=landed)
            self._colour_new(landed)
            stats.record("title")
        if not tt.placed_fine(message, "library", what):
            self._say(message, 3500)
        return message

    def _marker_command(self, timeline, arg):
        """Add Marker (C: the note window, the marker placed on its Enter - or the one at the playhead opened), Stretch
        Marker to Clips (Shift+C: the marker as long as the selected clips, then the window), Hide - Show Markers -
        markers.py, marker_note.py. What went wrong is said on screen."""
        from . import markers
        from .resolve_commands import _when as rc_when  # (times as Copy timeline writes them: 0:21.7)
        if arg == "toggle":  # (quiet: the markers going and coming is the answer - a message took Resolve's keyboard)
            message = markers.toggle(timeline)
            print(f"[marker] hide / show: {message}")
            return
        new = remove_if_left = False  # (C: placed only on Enter; Shift+C's new one goes again on Esc)
        if arg == "fit":
            worked, message, frame, remove_if_left = markers.fit(timeline)
            print(f"[marker] fit: {'done' if worked else message} (span {markers.span(timeline)})")
            if not worked:
                self._say(message)
                return
            hit = (frame, markers.markers(timeline).get(frame, {}))
        elif arg == "add":
            here = markers.playhead(timeline)
            hit = markers.at(timeline, here)
            if hit is None:  # (the playhead on a marker, or in a range marker: that one, to change - Edit Marker went)
                hit, new = (here, {"duration": 1}), True
            print(f"[marker] add: playhead {here}, {'new' if new else 'the one there'}")
        else:
            return
        frame, info = hit
        fps = float(timeline.GetSetting("timelineFrameRate") or 24) or 24
        length = max(1, int(float(info.get("duration") or 1)))
        when = rc_when(frame / fps) + (f" to {rc_when((frame + length) / fps)}" if length > 1 else "")
        if getattr(self, "marker_note", None) is None:
            from .marker_note import MarkerNote
            self.marker_note = MarkerNote(self.settings)
            self.marker_note.setFont(self.font())
        note = self.marker_note
        for signal in (note.done, note.cancelled):
            try:
                signal.disconnect()
            except (RuntimeError, TypeError):
                pass
        front = remember_front_app()

        def finished(kind=None, words=""):
            print(f"[marker] note window: {'kind ' + kind + ', words ' + repr(words) if kind is not None else 'closed'}")
            if kind is None:
                if remove_if_left:
                    timeline.DeleteMarkerAtFrame(frame)
            elif new:
                if not markers.add(timeline, frame, kind, words):
                    self._say("Resolve didn't add the marker")
            else:
                worked, message = markers.describe(timeline, frame, kind, words)
                if not worked:
                    self._say(message)
            give_focus_back(front)
        note.done.connect(finished)
        note.cancelled.connect(lambda: finished())
        note.ask(when, markers.kind_of(info), str(info.get("note") or ""))
        bring_to_front(note)

    def _colour_new(self, things):
        """What Clipse has just made (a grabbed frame, an adjustment clip, a composition, a title) gets its colour by
        the project's template at once, here (organise.colour_now: a program of its own took 0.1 s to start, and the
        clip showed plain first - "look glitchy")."""
        try:
            from .organise import colour_now
            colour_now(self.resolve, things)
        except Exception as e:
            print(f"[organise] couldn't colour the new clip: {e}")

    def _track_counts(self, timeline):
        try:
            return timeline.GetTrackCount("video"), timeline.GetTrackCount("audio")
        except Exception:
            return None

    def _remember_timeline_action(self, timeline, inserted, tracks_before, label, items=(),
                                  pool_items=(), media_pool=None):
        """pool_items: Media Pool clips the action made (a frame grab) - undo removes them too."""
        self._push_action({"kind": "timeline", "timeline_id": self._timeline_id(timeline), "label": label,
                           "locations": [loc for loc, _a in inserted if loc], "items": list(items),
                           "tracks": tracks_before, "pool_items": list(pool_items), "media_pool": media_pool})

    def _remember_fusion_action(self, label, steps=1):
        if label.startswith("adding"):
            stats.record("node", steps)
            if self.settings.timeline_tools.get("tidy_after_insert", True):
                # Settings > Fusion: the nodes tidied after every insert - mostly it's just the new one that moves.
                # (Undo takes the tidy back with the insert: it's one more step in Fusion's undo, if it moved any)
                if scripts_fusion.tidy_quietly(self.resolve, self.settings.timeline_tools.get("tidy_style", "lines")):
                    steps += 1
        self._push_action({"kind": "fusion", "label": label, "steps": steps})

    UNDO_DEPTH = 20

    def _push_action(self, action):
        """Remembers an action for Undo - the last 20, newest last."""
        actions = getattr(self, "_undo_stack", [])
        actions.append(action)
        self._undo_stack = actions[-self.UNDO_DEPTH:]

    @staticmethod
    def _timeline_id(timeline):
        try:
            return timeline.GetUniqueId()
        except Exception:
            return None

    def undo_last_action(self):
        """Takes back the last thing Clipse did - every clip of it,
        e.g. all 12 clips placed at markers - in one go. Press again for the
        one before (up to 20)."""
        actions = getattr(self, "_undo_stack", [])
        if not actions:
            return "Nothing to undo."
        action = actions.pop()
        stats.record("undo")
        if action["kind"] == "fusion":
            try:
                comp = self.resolve.Fusion().GetCurrentComp()
                comp.Undo(action["steps"])
                return f"Undid {action['label']}."
            except Exception as e:
                return f"Couldn't undo in Fusion: {e} - use Cmd/Ctrl+Z in Fusion."
        try:
            project = self.resolve.GetProjectManager().GetCurrentProject()
            timeline = project.GetCurrentTimeline() if project else None
        except Exception:
            timeline = None
        if timeline is None or self._timeline_id(timeline) != action["timeline_id"]:
            actions.append(action)  # kept for when you're back on that timeline
            return "That was on another timeline - switch back to it to undo."
        if action["kind"] == "beats":
            from . import beats
            running = getattr(self, "_beats_running", None)
            if running is not None and running.poll() is None:
                running.terminate()
                running.wait(2)
            self._beats_running = beats.start(run=action["run"], undo=True)
            return f"Undid {action['label']}."
        if action["locations"] or action["items"]:
            message = rc.remove_inserted(timeline, action["locations"], action["items"], action["tracks"],
                                         action["label"])
        else:
            message = f"Undid {action['label']}."
        if action.get("pool_items") and action.get("media_pool") is not None:
            try:  # the grabbed still out of the frame_grabs bin as well
                action["media_pool"].DeleteClips(action["pool_items"])
            except Exception as e:
                print(f"Couldn't remove the still from the Media Pool: {e}")
        return message

    # -- the Actions menu (bottom bar) and the > command list --
    # What an action is (2026-10-14 - "start from scratch"): something Clipse or Resolve does
    # that's smart, or takes several steps by hand - and worth a key. Not the picker's own views (preview, clip
    # info, listening: keys of their own), not its windows (the bottom bar), not what Resolve has a click away
    # (markers, tracks, pages, clip colours). The panel: what's for the page you're on, four to a row.
    # The panel puts your favourites first (right-click a tile), then the scripts in Resolve's menu (their red
    # symbol: settings.RESOLVE_KEYED, in its order), then the rest by group.
    PANEL_EDIT = [("Insert", ["Picture only", "Sound only", "Grab frame", "Record voiceover",
                              "Undo Clipse\u2019s last step"]),
                  ("Clip", ["Favourite", "Show in Media Pool", "Show in file manager", "Sounds like this", "Tags",
                            "Swap clip", "Next use of clip",
                            "Previous use of clip"]),
                  ("Timeline", ["Adjustment clip over clip", "Adjustment clip over footage", "Adjustment clip at playhead",
                                "Fusion composition over clip", "Fusion composition over footage",
                                "Fusion composition at playhead", "Switch timeline\u2026", "Remove empty tracks",
                                "Mark the beats", "Mark the bars",
                                "Copy markers", "Copy timeline", "Copy transcript", "Copy project",
                                "Render\u2026"]),
                  ("Project", ["Switch project\u2026", "Project templates\u2026", "Project check-up", "Relink missing clips"])]
    # (the Fusion page's are for the composition only - switching timelines or rendering is the Edit page's business)
    PANEL_FUSION = [("Nodes", ["Tidy up nodes", "Pull node out", "Node off / on", "Before / after", "Copy node name",
                               "Undo Clipse\u2019s last step"])]

    def is_favourite_action(self, label):
        return f"act:{label}" in self.favorited_names

    def favourite_action(self, label, on=True):
        """An action at the top of the Actions panel (kept with the clips' favourites, as "act:<name>")."""
        (self.favorited_names.add if on else self.favorited_names.discard)(f"act:{label}")
        rc.save_favorites(self.favorited_names)

    def panel_actions(self, typed=""):
        """What the Actions panel shows on the page Resolve is on: [(group, label, key, function)]. Typed
        words narrow it down - and reach every action when none of the page's own match."""
        from .fuzzy import fold
        everything = self._actions()
        by_label = {label: (g, label, key, fn) for g, label, key, fn in everything}
        fusion = self._current_page_key() == "fusion"
        plan, other = (self.PANEL_FUSION, self.PANEL_EDIT) if fusion else (self.PANEL_EDIT, self.PANEL_FUSION)
        shown = []
        for group, labels in plan:
            if labels is None:
                shown += [a for a in everything if a[0] == "Insert as"]
            else:
                shown += [(group, *by_label[label][1:]) for label in labels if label in by_label]
        # your favourites first (not the other page's own), then the scripts in Resolve's menu, then the rest
        here = {a[1] for a in shown}
        elsewhere = {label for _g, labels in other for label in labels or () if label not in here}
        favourites = [("Favourites", *a[1:]) for a in everything
                      if self.is_favourite_action(a[1]) and a[1] not in elsewhere]
        taken = {a[1] for a in favourites}
        order = list(RESOLVE_KEYED)
        scripts = sorted((("Scripts", *a[1:]) for a in shown if a[1] in RESOLVE_KEYED and a[1] not in taken),
                         key=lambda a: order.index(a[1]))
        shown = favourites + scripts + [a for a in shown if a[1] not in RESOLVE_KEYED and a[1] not in taken]
        words = fold(typed).split()
        if not words:
            return shown

        def hits(pool, text):
            return [a for a in pool if all(w in fold(text(a)) for w in words)]
        # the action's own name first; the group's name ("sound") only when nothing else matches
        return (hits(shown, lambda a: a[1]) or hits(everything, lambda a: a[1])
                or hits(shown, lambda a: a[0]) or hits(everything, lambda a: a[0]))

    def _actions(self):
        """[(group, label, keybind name or "", function)] - everything, in the order the > list shows it. Every
        action has a key to set (settings.ACTION_KEYS for the ones that come with none)."""
        return [(g, label, key or ACTION_KEY_BY_LABEL.get(label, ""), fn) for g, label, key, fn in self._action_list()]

    def _action_list(self):
        """Every action, as the > list shows them (keys: settings.ACTION_KEYS, RESOLVE_KEYED, RESOLVE_NATIVE)."""
        def text(prefix):
            return lambda: (self.search_edit.setText(prefix), self.search_edit.setFocus())

        def later(fn):
            def run():
                self.hide()
                QTimer.singleShot(0, lambda: print(fn()))
            return run

        def direct(action, arg):  # what its script in Resolve's menu does
            def run():
                self.hide()
                QTimer.singleShot(0, lambda: self.run_direct_command(action, arg))
            return run
        return [
            ("Insert", "Picture only", "insert_video_only", lambda: self.confirm_only("video")),
            ("Insert", "Sound only", "insert_audio_only", lambda: self.confirm_only("audio")),
            ("Insert", "As compound clip", "insert_compound", self.confirm_compound),
            ("Insert", "Grab frame", "", later(self.grab_frame)),  # (keyed in Resolve: settings.RESOLVE_KEYED)
            ("Insert", "Record voiceover", "", direct("voice", "record")),
            ("Insert", "Undo Clipse\u2019s last step", "", lambda: self._flash_hint(self.undo_last_action(), 3000)),
            ("Clip", "Favourite", "toggle_favorite", self.toggle_favorite),
            ("Clip", "Show in Media Pool", "reveal_keep_open", lambda: self.reveal_only(keep_open=True)),
            ("Clip", "Show in file manager", "show_in_file_manager", self.show_in_file_manager),
            ("Clip", "Sounds like this", "similar_sounds", self.similar_sounds),
            ("Clip", "Tags", "tag_clip", self.open_tags),
            ("Clip", "Swap clip", "", self.start_swap),
            ("Clip", "Next use of clip", "", lambda: self._jump_use(1)),
            ("Clip", "Previous use of clip", "", lambda: self._jump_use(-1)),
            ("Timeline", "Step back", "", direct("step", -1)),
            ("Timeline", "Step forward", "", direct("step", 1)),
            ("Timeline", "Switch timeline\u2026", "", text("t: ")),
            ("Timeline", "Remove empty tracks", "", self._command(commands.remove_empty_tracks)),  # (closes, like the rest)
            ("Timeline", "Mark the beats", "", lambda: self._mark_beats()),
            ("Timeline", "Mark the bars", "", lambda: self._mark_beats(bars=True)),
            ("Timeline", "Copy markers", "", self._copy_markers),
            ("Timeline", "Copy timeline", "", self._copy_timeline),
            ("Timeline", "Copy transcript", "", self._copy_transcript),
            ("Timeline", "Copy project", "", lambda: self._copy_timeline(every=True)),
            ("Timeline", "Adjustment clip over clip", "", direct("adjust", "match")),
            ("Timeline", "Adjustment clip over footage", "", direct("adjust", "match-skip-adj")),
            ("Timeline", "Adjustment clip at playhead", "", direct("adjust", "fixed")),
            ("Timeline", "Fusion composition over clip", "", direct("comp", "match")),
            ("Timeline", "Fusion composition over footage", "", direct("comp", "match-skip-adj")),
            ("Timeline", "Fusion composition at playhead", "", direct("comp", "fixed")),
            ("Timeline", "Render\u2026", "", text("> render ")),
            ("Project", "Switch project\u2026", "", text("p: ")),
            ("Project", "Project templates\u2026", "", text("tpl: ")),
            ("Project", "Organise project", "", direct("organise", "project")),
            ("Timeline", "Add marker", "", direct("marker", "add")),
            ("Timeline", "Stretch marker to clips", "", direct("marker", "fit")),
            ("Timeline", "Hide - show markers", "", direct("marker", "toggle")),
            ("Project", "Project check-up", "", text("> check-up ")),
            ("Project", "Relink missing clips", "", self._relink_missing),
            ("Fusion", "Tidy up nodes", "", later(self._tidy)),
            ("Fusion", "Pull node out", "", later(self._pull_out)),
            ("Fusion", "Node off / on", "", self._command(fusion_animate.toggle_nodes, stay=True)),
            ("Fusion", "Before / after", "", self._command(fusion_animate.before_after, stay=True)),
            ("Fusion", "Copy node name", "", self._copy_node_name),
            ("Clipse", "Restart Clipse", "", self.restart_service),
            ("Clipse", "Quit Clipse", "", self.quit_service),
        ] + ([] if fusion_animate.PARKED else [("Fusion", "Animate\u2026", "", text("> animate "))])

    def reload_yours(self):
        """After a setup was loaded (Settings > About, transfer.py): favourites and what's inserted most, read again
        from their files - in place, as everything holding them holds these very ones."""
        self.favorited_names.clear()
        self.favorited_names.update(rc.load_favorites())
        self.insert_frequency.clear()
        self.insert_frequency.update(rc.load_insert_frequency())
        self._force_refresh_next = True  # (the list is built again with them next time)

    # -- Restart / Quit (2026-10-19: "make restarting or stopping more convenient") - also at the foot of Settings'
    #    sidebar. Quit lasts until Clipse is wanted again: a key in Resolve, or Resolve opened again, starts it --
    def restart_service(self):
        from .launch import restart_service
        self.hide()
        restart_service()

    def quit_service(self):
        self.hide()
        QApplication.instance().quit()

    # -- Swap clip: what's on the timeline goes out, the clip picked here comes in --
    def start_swap(self):
        """Swap clip (its tile, a row found in a search, or its script in Resolve's menu): the picker's plain list
        with the clip to swap out at the top (SwapStrip) - read off the timeline, and following it while the swap
        is on: click another clip in Resolve and that's the one (_swap_watch). The highlighted clip is what comes
        in. Enter swaps (_finish_swap), Esc stops."""
        if not self.isVisible():
            self.open_picker()
        if self.search_edit.text():
            self.search_edit.setText("")  # (back to the plain list: "swap" found the action, not a clip)
        timeline = self.session.get("timeline")
        if timeline is None:
            return self._flash_hint("Open a timeline first", 3000)
        target = self._swap_target(timeline)  # (nothing there yet: it waits - click one in Resolve, _swap_watch)
        self._swap = dict(target or {"spots": None, "name": "", "kind": "", "symbol": "", "count": 0, "media_id": None},
                          everywhere=bool(self.settings.display.get("swap_everywhere")),
                          uses=self._uses(timeline, target) if target else 0)
        self.swap_strip.setFont(self.list_view.font())  # (the list's size, a touch smaller - SwapStrip._font)
        self.swap_strip.updateGeometry()
        self._show_swap_out()
        self._swap_follow()
        self.search_edit.setFocus()
        if not hasattr(self, "_swap_timer"):
            self._swap_timer = QTimer(self)
            self._swap_timer.setInterval(400)
            self._swap_timer.timeout.connect(self._swap_watch)
        self._swap_timer.start()

    def _swap_pick(self):
        """The strip's target: the picker steps aside until another clip is clicked in Resolve (or the playhead
        put on one), then comes back with it to swap out - like picking a node for an expression. Esc, a click
        on the small notice, or PICK_SECONDS without a click: back as it was."""
        timeline = self.session.get("timeline")
        if self._swap is None or timeline is None:
            return
        self._swap_picking = {"before": self._swap["spots"], "until": time.monotonic() + self.PICK_SECONDS,
                              "search": self.search_edit.text(), "row": self._current_orig_index()}
        self.hide()
        if getattr(self, "swap_notice", None) is None:
            from .keycast import PickNotice
            self.swap_notice = PickNotice(self.settings)
            self.swap_notice.setFont(self.font())
            self.swap_notice.cancelled.connect(lambda: self._swap_picked(None))
        self.swap_notice.wait_for("Click the clip to swap out")
        if not hasattr(self, "_swap_pick_timer"):
            self._swap_pick_timer = QTimer(self)
            self._swap_pick_timer.timeout.connect(self._swap_pick_step)
        self._swap_pick_timer.start(150)

    def _swap_pick_step(self):
        picking, timeline = self._swap_picking, self.session.get("timeline")
        if picking is None or timeline is None:
            return self._swap_picked(None)
        target = self._swap_target(timeline)
        if target is not None and target["spots"] != picking["before"]:
            self._swap_picked(target)
        elif time.monotonic() > picking["until"]:
            self._swap_picked(None)

    def _swap_picked(self, target):
        """Back from picking: the picker again, with the clip clicked (None: as it was)."""
        if self._swap_picking is None:
            return
        self._swap_pick_timer.stop()
        if getattr(self, "swap_notice", None) is not None:
            self.swap_notice.hide()
        picking = self._swap_picking
        self.open_picker()
        self._swap_picking = None
        if picking["search"]:  # (what was typed and highlighted for the clip coming in, as it was)
            self.search_edit.setText(picking["search"])
        if picking["row"] is not None and picking["row"] in self.model.visible:
            self._select_row(self.model.visible.index(picking["row"]))
        if self._swap is None:
            return
        if target is not None:
            self._swap.update(target, everywhere=bool(self.settings.display.get("swap_everywhere")),
                              uses=self._uses(self.session.get("timeline"), target))
        self._show_swap_out()
        self._swap_follow()
        self._swap_timer.start()
        self.search_edit.setFocus()

    def _swap_target(self, timeline):
        """What a swap takes out, read off the timeline: the clip(s) selected there, else the one under the
        playhead - {"spots", "media_id", "name", "kind", "symbol", "count"}, or None. (Asked 2.5 times a second
        while a swap is on: only what's quick - how often it's used is counted when it changes, _uses.)"""
        try:
            chosen = timeline.GetSelectedClips() or []
            chosen = list(chosen.values()) if isinstance(chosen, dict) else list(chosen)
        except Exception:
            chosen = []
        if not chosen:
            try:
                under = timeline.GetCurrentVideoItem()
            except Exception:
                under = None
            chosen = [under] if under is not None else []
        chosen = [item for item in chosen if item is not None and item.GetMediaPoolItem() is not None]
        if not chosen:
            return None
        # (a picture and its own sound are one clip: Resolve selects both)
        clips = {(item.GetMediaPoolItem().GetMediaId(), int(item.GetStart())) for item in chosen}
        if len(clips) > 1:  # several: one at a time - the strip says so, Enter doesn't swap
            return {"spots": sorted(clips), "media_id": None, "name": "", "kind": "", "symbol": "",
                    "count": len(clips)}
        chosen = chosen[:1] if chosen[0].GetTrackTypeAndIndex()[0] == "video" else \
            [next((it for it in chosen if it.GetTrackTypeAndIndex()[0] == "video"), chosen[0])]
        first = chosen[0].GetMediaPoolItem()
        name = first.GetName()
        kind = rc.get_category(name, first.GetClipProperty("Type") or "", self.settings)
        if kind == "timeline":  # a timeline put inside this one goes out like a video
            kind = "video"
        if chosen[0].GetTrackTypeAndIndex()[0] == "audio":
            kind = "audio"
        return {"spots": [(*item.GetTrackTypeAndIndex(), int(item.GetStart())) for item in chosen],
                "media_id": first.GetMediaId(), "name": name, "kind": kind, "symbol": self._symbol_of(name, kind),
                "count": len(chosen)}

    @staticmethod
    def _uses(timeline, target):
        """How often the clip a swap takes out is on the timeline."""
        if not target.get("media_id"):
            return 0
        return len(tt.find_instance_starts(timeline, {target["media_id"]}, {target["name"]}))

    def _symbol_of(self, name, kind):
        """The list's symbol for a clip: a sound is music or a sound effect there."""
        if kind != "audio" or not self.settings.listen.get("split_music", True):
            return kind
        row = next((r for r in self.model.clip_rows if r.category == "audio" and r.name == name), None)
        music = getattr(row, "music", None) if row is not None else None
        return "audio" if music is None else "music" if music else "sound"

    def _show_swap_out(self):
        swap = self._swap
        if not swap["spots"]:
            self.swap_strip.show_swap("", "", 1, False)
            return
        if swap["count"] > 1:
            self.swap_strip.show_swap("", "", 1, False, several=swap["count"])
            return
        swap["everywhere"] = swap["everywhere"] and swap["uses"] > 1
        self.swap_strip.show_swap(swap["name"], swap["kind"], swap["uses"], swap["everywhere"], symbol=swap["symbol"])

    def _swap_watch(self):
        """While a swap is on: another clip clicked (or the playhead moved onto one) in Resolve is the one to swap
        out now. Nothing there - the playhead on a gap - leaves it as it was."""
        timeline = self.session.get("timeline")
        if self._swap is None or not self.isVisible() or timeline is None:
            self._swap_timer.stop()
            return
        target = self._swap_target(timeline)
        if target is None or target["spots"] == self._swap["spots"]:
            return
        self._swap.update(target, everywhere=bool(self.settings.display.get("swap_everywhere")),
                          uses=self._uses(timeline, target))
        self._show_swap_out()
        self._swap_follow()

    def _swap_in(self):
        """(row index, name, kind, fits) of the highlighted clip - what would come in - or None."""
        orig = self._current_orig_index()
        groups = self.session.get("filtered_group_list") or []
        if orig is None or self._is_external_row(orig) or orig >= len(groups) or groups[orig][2] in ("bin", "selected"):
            return None
        name, _instances, kind = groups[orig]
        sound_out = self._swap["kind"] == "audio"
        fits = kind == "audio" or (kind == "video" and sound_out) if sound_out else \
            kind != "audio" or not self._swap["spots"]
        return orig, name, kind, fits

    def _swap_follow(self):
        found = self._swap_in() if self._swap else None
        if found:
            self.swap_strip.set_in(found[1], found[2], found[3], symbol=self._symbol_of(found[1], found[2]))
        else:
            self.swap_strip.set_in("", "", True)

    def _swap_everywhere(self, on):
        if self._swap is not None:
            self._swap["everywhere"] = on
            self.settings.display["swap_everywhere"] = on
            self.settings.save()

    def end_swap(self):
        if self._swap is not None:
            self._swap = None
            self.swap_strip.hide()
            if hasattr(self, "_swap_timer"):
                self._swap_timer.stop()

    def _finish_swap(self):
        """Enter in a swap: the highlighted clip in place of the one(s) shown at the top - or every use of it."""
        swap, found = self._swap, self._swap_in()
        if not swap["spots"]:
            return self._flash_hint("Click the clip to swap out in Resolve first", 3500)
        if swap["count"] > 1:
            return self._flash_hint("Select just one clip on the timeline", 3500)
        if found is None:
            return self._flash_hint("Highlight the clip to swap in", 3000)
        orig, new_name, _kind, fits = found
        if not fits:
            return self._flash_hint("A sound can only take a sound's place" if swap["kind"] == "audio"
                                    else "A sound can't take a picture's place", 3500)
        clips = rc.expand_row_to_items(self.session, self.settings, orig, self.selection_order_ids)
        if not clips:
            return self._flash_hint("That clip isn't in the Media Pool any more", 3000)
        new = clips[0][0]
        if new.GetMediaId() == swap["media_id"]:
            return self._flash_hint("That's the clip that's there already", 3000)
        timeline, media_pool = self.session.get("timeline"), self.session.get("media_pool")
        if swap["everywhere"]:
            items = [it for kind in ("video", "audio") for n in range(1, int(timeline.GetTrackCount(kind)) + 1)
                     for it in (timeline.GetItemListInTrack(kind, n) or [])
                     if it.GetMediaPoolItem() is not None and it.GetMediaPoolItem().GetMediaId() == swap["media_id"]]
        else:
            items = [it for it in (rc.lookup_item(timeline, *spot) for spot in swap["spots"]) if it is not None]
        self.end_swap()
        self.hide()
        if not items:
            return self._say(f"'{swap['name']}' isn't there any more", 4000)
        fps = float(timeline.GetSetting("timelineFrameRate"))
        swapped, skipped = rc.swap_items(self.settings, timeline, media_pool, items, new, new_name, fps,
                                         self._picture_look)
        what = f"'{swap['name']}'" if swapped == 1 else f"{swapped} uses of '{swap['name']}'"
        message = (f"Swapped {what} for '{new_name}'" if swapped else f"Couldn't swap '{swap['name']}'") \
            + (f" ({skipped} couldn't be)" if swapped and skipped else "")
        print(message)
        self._say(message, 3000)

    def _jump_use(self, steps):
        """Next / Previous use of clip: the playhead to where the highlighted clip is used on the timeline - and
        when it isn't (a clip is nearly always highlighted), as its script in Resolve does: the clip selected on
        the timeline, in the Media Pool, under the playhead (timeline_tools.jump_targets)."""
        orig = self._current_orig_index()
        groups = self.session.get("filtered_group_list") or []
        timeline = self.session.get("timeline")
        if timeline is not None and orig is not None and not self._is_external_row(orig) and orig < len(groups) \
                and groups[orig][2] not in ("bin", "selected"):
            name, instances, _category = groups[orig]
            starts = tt.find_instance_starts(timeline, {member[0] for member in instances}, {name})
            if starts:
                print(tt.jump_steps(timeline, starts, steps, name))
                self.hide()
                return
        self.hide()
        QTimer.singleShot(0, lambda: self.run_direct_command("jump", steps))  # (steps: +1 / -1, as the script's)

    def _command(self, fn, *args, stay=False):
        """An action that tells Resolve to do something (resolve_commands.py).
        When it worked the picker closes - the result is there to see in
        Resolve; when it didn't (or with stay: nothing to see), it says so here."""
        def run():
            try:
                worked, message = fn(self.resolve, *args)
            except Exception as e:
                print(f"[commands] {getattr(fn, '__name__', fn)} failed: {e}")
                worked, message = False, "Resolve didn't answer - is a project open?"
            print(f"[commands] {message}")
            if worked and not stay:
                self.hide()
            else:
                self._flash_hint(message, 4500)
        return run

    def _sound_kind(self, name):
        """True: music, False: a sound effect, None: not known - for naming tracks."""
        row = next((r for r in self.model.clip_rows if r.category == "audio" and r.name == name), None)
        return None if row is None or row.music is None else bool(row.music)

    def _show_expression_card(self):
        """An expression's row can't say what it does in the room it has: the
        preview opens by itself while one is highlighted (Settings -> Preview),
        and closes again when you move on - if it was opened just for that."""
        if not self.isVisible():
            return
        orig = self._current_orig_index()
        on_one = orig is not None and orig < len(self.model.rows) and self.model.rows[orig].category == "expression"
        other_enter = on_one or (orig is not None and orig < len(self.model.rows)
                                 and self.model.rows[orig].category in ("action", "shortcut"))
        if not self.hints_label.hints or other_enter or self._on_expression_before:
            self.hints_label.set_hints(self._footer_hints())  # Enter means something else on an expression, or an action
        self._on_expression_before = other_enter
        self._expression_asked = None if not on_one or self._expression_asked != self.model.rows[orig].path \
            else self._expression_asked
        if on_one and not self.preview_panel.isVisible() and self.settings.listen.get("expression_preview", True):
            self._card_opened_preview = True
            self._open_preview_panel()
            self._preview_current()
            self.search_edit.setFocus()
        elif not on_one and self._card_opened_preview and self.preview_panel.isVisible():
            self._card_opened_preview = False
            self._close_preview()

    def _copy(self, text):
        """`text` onto the clipboard. Wayland only lets the app in front set
        it, and a Resolve shortcut runs with Resolve in front - wl-copy
        (from wl-clipboard, if it's there) does it then."""
        from . import clipboard
        clipboard.set_text(text)  # (on a Mac written out at once - Resolve hung waiting for it, see clipboard.py)
        from PySide6.QtGui import QGuiApplication
        if QGuiApplication.platformName().startswith("wayland") and not self.isActiveWindow():
            import shutil
            import subprocess
            tool = shutil.which("wl-copy")
            if tool:
                try:
                    subprocess.run([tool, "--", text], timeout=2, check=False)
                except (OSError, subprocess.SubprocessError) as e:
                    print(f"[clipboard] wl-copy: {e}")

    def _copy_files(self):
        """Ctrl+C: the file path of what's highlighted, wherever there is one (2026-10-15) - a clip's
        file, a script's, macro's, Fusion comp's or folder's; the staged clips, else the ones selected in the
        list (a bin: what's in it), one per line. As text, and the way a file manager copies files (file://
        links, and the GNOME / KDE way of saying "copied"), so a file manager pastes the file. A Fusion node: its
        name. False when there's nothing of that kind to copy."""
        orig = self._current_orig_index()
        row = self.model.rows[orig] if orig is not None and orig < len(self.model.rows) else None
        if row is not None and row.category == "node":
            self._copy(row.name)
            self._flash_hint(f"Copied {row.name}", 2500)
            return True
        if row is not None and row.category in ("script", "macro", "comp", "folder"):
            paths = [row.path] if row.path else []
        else:
            indices = [i for i in self.model.staged if not self._is_external_row(i)] or \
                [i for i in self._get_multi_selected_orig_indices() if not self._is_external_row(i)]
            if not indices:
                indices = [orig] if orig is not None and not self._is_external_row(orig) else []
            paths = []
            for i in indices:
                if i >= len(self.model.clip_rows):
                    continue
                for n in (self._rows_inside(i) if self.model.clip_rows[i].category in ("bin", "selected") else [i]):
                    path = getattr(self.model.clip_rows[n], "source", "") or ""
                    if path and path not in paths:  # (a file that's gone too: where it was is worth knowing)
                        paths.append(path)
        if not paths:
            return False
        from PySide6.QtCore import QMimeData, QUrl
        urls = [QUrl.fromLocalFile(path) for path in paths]
        data = QMimeData()
        data.setUrls(urls)
        listed = "\n".join(url.toString() for url in urls)
        data.setData("x-special/gnome-copied-files", ("copy\n" + listed).encode())
        data.setData("application/x-kde-cutselection", b"0")
        data.setText("\n".join(paths))
        from . import clipboard
        if clipboard.set_files(paths, data) and not getattr(self, "_clipboard_let_go", False):  # (Qt crashes on its way out holding our files on the
            self._clipboard_let_go = True                  # clipboard - so they're let go of when it quits)
            QApplication.instance().aboutToQuit.connect(
                lambda: QApplication.clipboard().ownsClipboard() and QApplication.clipboard().clear())
        print(f"[clipboard] copied {len(paths)} path(s): {paths[:3]}")
        self._flash_hint(f"Copied {paths[0]}" if len(paths) == 1 else f"Copied {len(paths)} file paths", 2500)
        return True

    def _row_menu_choices(self, row):
        """What a right-click on `row` offers: [(text, glyph, what it does)]. A script: Resolve's Scripts menu, so
        Resolve can give it a key - Add to Resolve's menu, or once it's there Key in Resolve… (and Take it out, when
        it was added from here). Clipse's own scripts (the red action rows): Key in Resolve…. (
        2026-10-17 - this was Settings > Scripts.)"""
        from . import resolve_shortcuts as rs
        if row.category == "action" and row.name in RESOLVE_KEYED:
            return [("Key in Resolve\u2026", "scripts", lambda: self._key_in_resolve(RESOLVE_KEYED[row.name]))]
        if row.category == "audio":
            return [("Tags", "tags", self.open_tags)]
        if row.category != "script" or not row.path:
            return []
        name = _os.path.splitext(_os.path.basename(row.path))[0]  # (as Resolve's menu and its key list call it)
        place = rs.menu_place(row.path)
        if not place:
            return [("Add to Resolve's menu", "insert", lambda: self._add_to_resolve(row.path))]
        choices = [("Key in Resolve\u2026", "scripts", lambda: self._key_in_resolve(name))]
        if place == "added":
            choices.append(("Take out of Resolve's menu", "pull_out",
                            lambda: (rs.remove_user_launcher(rs.user_launcher_path(row.path)),
                                     self._flash_hint(f"{name} is out of Resolve's menu", 3000))))
        return choices

    def _row_menu(self, pos):
        index = self.list_view.indexAt(pos)
        if not index.isValid() or index.row() >= len(self.model.visible):
            return
        self.list_view.setCurrentIndex(index)
        choices = self._row_menu_choices(self.model.rows[self.model.visible[index.row()]])
        if not choices:
            return
        menu = BarMenu(self.settings)
        menu.setParent(self, menu.windowFlags())
        for text, glyph, run in choices:
            row = MenuRow(self.settings, text, glyph, kind="more")
            row.setFixedHeight(row.sizeHint().height())
            row.clicked.connect(lambda run=run: (menu.hide(), run()))
            menu.box.addWidget(row)
        menu.adjustSize()
        at = self.list_view.viewport().mapToGlobal(pos)
        menu.move(at.x() + 2, at.y() + 2)
        menu.show()
        self._row_menu_shown = menu

    def _add_to_resolve(self, path):
        from . import resolve_shortcuts as rs
        ok, message, _launcher = rs.add_user_launcher(path)
        print(f"[scripts] {message}: {path}")
        self._flash_hint(message + (" - restart Resolve if it isn't there yet" if ok else ""), 5000)

    def _key_in_resolve(self, name):
        """A key in Resolve's own Keyboard Customization. No script can open that window: the name goes onto the
        clipboard, the picker out of the way so Resolve is in front, and a note says where to paste it."""
        self._copy(name)
        self.hide()
        # (the way there through Resolve's menu - its key may have been changed)
        self._say(name, 7000, lead="Copied", steps=("DaVinci Resolve", "Keyboard Customization", "Paste into the search"))

    def _copy_markers(self):
        """The open timeline's markers - when, colour, name, note - and what's said, as text to paste into a chat
        assistant (commands.markers_text). The picker steps aside, a toast says it's copied."""
        timeline = self.session.get("timeline")
        if timeline is None:
            return self._flash_hint("Open a timeline first", 3000)
        try:
            text = commands.markers_text(timeline)
        except Exception as e:
            print(f"[commands] copy markers failed: {e}")
            return self._flash_hint("Couldn't read the markers", 3000)
        if not text:
            return self._flash_hint("This timeline has no markers", 3000)
        self._copy(text)
        count = len(timeline.GetMarkers() or {})
        self.hide()
        self._say(f"Copied {count} marker{'s' if count != 1 else ''}")

    def _copy_timeline(self, every=False):
        """The open timeline - or, every=True, the whole project: its settings, Media Pool and every timeline - as
        text with times: each clip on each track, the markers, what's said (commands.timeline_text /
        project_text), to paste into a chat assistant so it can follow the edit (2026-10-28). The picker steps
        aside, a toast says it's copied."""
        try:
            if every:
                project = self.resolve.GetProjectManager().GetCurrentProject()
                if project is None:
                    return self._flash_hint("Open a project first", 3000)
                text, count = commands.project_text(project), int(project.GetTimelineCount() or 0)
            else:
                timeline = self.session.get("timeline")
                if timeline is None:
                    return self._flash_hint("Open a timeline first", 3000)
                text, count = commands.timeline_text(timeline), 1
        except Exception as e:
            print(f"[commands] copy timeline failed: {e}")
            return self._flash_hint("Couldn't read the timeline", 3000)
        self._copy(text)
        self.hide()
        self._say("Copied the timeline" if not every else
                  f"Copied the project ({count} timeline{'s' if count != 1 else ''})")

    def _copy_transcript(self):
        """What's said on the open timeline, with times (its subtitles - Resolve's Timeline > Create Subtitles from Audio makes
        them; they can stay switched off), to paste into a chat assistant. The picker steps aside, a toast says it's copied."""
        timeline = self.session.get("timeline")
        if timeline is None:
            return self._flash_hint("Open a timeline first", 3000)
        try:
            text = commands.transcript_text(timeline)
        except Exception as e:
            print(f"[commands] copy transcript failed: {e}")
            return self._flash_hint("Couldn't read the subtitles", 3000)
        if not text:
            return self._flash_hint("No subtitles yet: Timeline \u203a Create Subtitles from Audio in Resolve", 4000)
        self._copy(text)
        self.hide()
        self._say("Copied the transcript")

    def _copy_node_name(self):
        """The selected Fusion node's name onto the clipboard - to write in
        an expression (Transform1.Center). What it said, for the log."""
        name, problem = fusion_expressions.selected_node_name(self.resolve)
        if name:
            self._copy(name)
        message = f"Copied {name} - write {name}.Center, {name}.Size ... in an expression" if name else problem
        if self.isVisible():
            self._flash_hint(message, 4500)
        return message

    def _confirm_expression(self, row, only_copy=False):
        """Enter on an expression: its code (with the numbers its sliders are
        at) onto the clipboard, and onto the node it belongs on. only_copy
        (Shift+Enter, Ctrl+C): just the clipboard. With nothing selected in
        Fusion a node has to be added for it - asked first (Enter again),
        unless Settings says not to."""
        entry = fusion_expressions.BY_KEY.get(row.path)
        if entry is None:
            return
        values = self.preview_panel.canvas.card_numbers(entry)
        self._copy(fusion_expressions.code(entry, values))
        if only_copy:
            self._flash_hint(f"Copied the code of {entry['name']} - right-click a setting \u203a Expression to paste it", 5000)
            return
        state, node = fusion_expressions.plan(self.resolve, entry["key"])
        if state == "copy":
            names = fusion_expressions.NAMES_A_NODE in entry["template"]
            if names:  # it follows another node: click that node in Fusion, and its name is written in
                code = fusion_expressions.code(entry, values)

                def picked(name):
                    if name:
                        self._copy(fusion_expressions.with_node(code, name))
                        self._say(f"Copied, following {name} - paste it on the node that should follow", 6000)
                    else:
                        self.open_picker()
                        self._flash_hint(f"No node was clicked - copied with {fusion_expressions.NAMES_A_NODE} in it", 6000)
                if self.pick_node_in_fusion(picked, "Click the node to follow"):
                    return
            self._flash_hint("Copied - paste it on a setting (right-click \u203a Expression)"
                             + (f", with your node's name for {fusion_expressions.NAMES_A_NODE}" if names else ""), 7000)
            return
        if state == "away":
            self._flash_hint("Copied the code - on the Fusion page, right-click a setting \u203a Expression and paste it", 6000)
            return
        new_node = fusion_expressions.new_node_name(entry)
        if state == "none" and self.settings.timeline_tools.get("expression_ask", True) \
                and self._expression_asked != entry["key"]:
            self._expression_asked = entry["key"]
            where = f" after {node}" if node else ""
            self._flash_hint(f"No node is selected in Fusion - Enter again adds a {new_node}{where} with it", 8000)
            return
        self._expression_asked = None
        try:
            worked, message = fusion_expressions.apply(
                self.resolve, entry["key"], values=values,
                sliders=bool(self.settings.timeline_tools.get("expression_sliders", True)))
        except Exception as e:
            print(f"[expression] {entry['name']} failed: {e}")
            worked, message = False, "Copied the code - Fusion didn't answer"
        print(f"[expression] {message}")
        if worked:
            rc.record_recent(f"expression:{entry['key']}")
            self._remember_fusion_action(f"the expression {entry['name']}")
            self._record_fusion_history([("expression", entry["name"], entry["key"])])
            self.hide()
        else:
            self._flash_hint(message, 6000)

    def _set_page_link(self, fusion):
        """The bottom bar's link for the page Resolve is on: Insert as (how clips land on a
        timeline) - or, on the Fusion page, where there's no timeline to land on, Cheat sheet.
        (The ready-made expressions need no link: they're in the Fusion page's list, and under x:.)"""
        self._page_link_fusion = fusion
        if fusion:
            self.insert_options_link.setText("Expressions")
            self.insert_options_link.setToolTip("Everything you can write in a Fusion expression, ready to copy")
        else:
            self.insert_options_link.setText("Insert as")
            self.insert_options_link.setToolTip(
                f"Insert as - how clips land on the timeline ({self._key_text('toggle_insert_options')})")

    def _watch_page(self):
        """While the picker is open: has Resolve gone to another page? (Edit to Fusion: a different
        list, and a different bottom bar.)"""
        if not self.isVisible():
            self._page_timer.stop()
            return
        page = self._current_page_key()
        if page != self._page_seen:
            print(f"[page] Resolve went to the {'Fusion' if page == 'fusion' else 'Edit'} page's layout")
            self._page_changed(page)

    def _page_changed(self, page, search_again=True):
        self._page_seen = page
        self._set_page_link(page == "fusion")
        # each page lists its own kinds of Media Pool row (Settings > General) - on the Fusion page never
        # a sound or an adjustment clip, which a composition has no use for
        self.model.page_hides = self.settings.hidden_categories(page)
        if search_again:
            self.hints_label.set_hints(self._footer_hints())
            if not any(overlay.isVisible() for overlay in (self.expression_sheet, self.actions_panel)):
                at = self.list_view.currentIndex().row()
                self.model.set_filter(self.search_edit.text())
                self._select_row(0 if self.search_edit.text().strip() else max(0, min(at, self.model.rowCount() - 1)))

    def _page_link_clicked(self):
        if self._page_link_fusion:
            self._show_cheat_sheet()
        else:
            self.open_insert_options()

    def show_node_in_preview(self, name, values_only=False):
        """While Expressions is open the preview shows the node its pieces point at: what each setting is
        called, its value now, a click to copy (node_settings.py). values_only: the same node, its values again."""
        from . import node_settings
        canvas = self.preview_panel.canvas
        if not self.preview_panel.isVisible():
            return
        view = canvas.node_view
        if values_only and view is not None and view.same_node(name):
            fresh = node_settings.values(self.resolve, view.node)
            if fresh != view.values:
                view.values = fresh
                canvas.update()
            return
        if view is not None and (view.same_node(name) or (not name and view.node == "")):
            return
        if view is None:
            self.video.stop()
            self.preview_panel.reset("", None)
            self.preview_panel.info.hide()
            self.preview_panel.footer.hide()  # (play, the time, the volume: nothing to play)
        node = node_settings.read(self.resolve, name) if name else ""
        canvas.node_view = node_settings.NodeView(node, node_settings.values(self.resolve, node))
        canvas.update()

    def flip_node(self, step):
        """The previous / next node of the composition (as the node editor lays them out) in the preview, and its
        name in Expressions' pieces - to look through them for the right one. Fusion's own selection is left alone."""
        from . import node_settings
        names = node_settings.names_in_order(self.resolve)
        if not names:
            return
        view = self.preview_panel.canvas.node_view
        now = view.node["name"] if view is not None and isinstance(view.node, dict) else self.expression_sheet.node
        if now in names:
            name = names[(names.index(now) + step) % len(names)]
        else:
            name = names[0] if step > 0 else names[-1]
        self.expression_sheet.set_node(name)
        self.show_node_in_preview(name)

    def expressions_shown(self, shown):
        """Expressions opened or closed. It has its own preview, open or not, remembered
        (`display["expressions_preview"]`, the preview key while it's open - 2026-10-22: "should not be on just because
        the picker has the preview on"), showing the node meanwhile; closed, the picker's preview is as it was."""
        panel = self.preview_panel
        if shown:
            self._preview_before_sheet = panel.isVisible()
            want = self.settings.display.get("expressions_preview", True)
            if want and not panel.isVisible():
                self._open_preview_panel()
            elif not want and panel.isVisible():
                self._close_preview()
            self.layout().activate()
            self.expression_sheet.setGeometry(self.picker_column.geometry())  # (the list's room may have changed)
            self.show_node_in_preview(self.expression_sheet.node)
            return
        canvas = panel.canvas
        if canvas.node_view is not None:
            canvas.node_view = None
            panel.footer.show()
        if not self.isVisible():
            return  # (the picker closing: it closes the preview its own way)
        before = getattr(self, "_preview_before_sheet", panel.isVisible())
        if before and not panel.isVisible():
            self._open_preview_panel()
        elif not before and panel.isVisible():
            self._close_preview()
        if panel.isVisible():
            self._preview_current(quiet=True)

    def _show_cheat_sheet(self):
        """The expression cheat sheet over the list, with the node selected in Fusion written into it."""
        node = ""
        if self._current_page_key() == "fusion":
            try:
                node, _problem = fusion_expressions.selected_node_name(self.resolve)
            except Exception as e:
                print(f"[expression] couldn't ask Fusion which node is selected: {e}")
        self.expression_sheet.open(node)

    def _on_expression(self):
        """The highlighted row, if it's an expression."""
        orig = self._current_orig_index()
        if orig is not None and orig < len(self.model.rows) and self.model.rows[orig].category == "expression":
            return self.model.rows[orig]
        return None

    def _animate_seconds(self):
        """How long a ready-made Fusion animation takes."""
        try:
            return max(0.05, float(self.settings.timeline_tools.get("animate_seconds", fusion_animate.DEFAULT_SECONDS)))
        except (TypeError, ValueError):
            return fusion_animate.DEFAULT_SECONDS

    def _commands(self):
        """More actions, only in the > list and the search (too many for the
        Actions panel's tiles): one per page, render preset and clip colour,
        and the project check-up's four lists."""
        def text(prefix):
            return lambda: (self.search_edit.setText(prefix), self.search_edit.setFocus())
        if self._render_presets is None:  # asked once each time the picker opens
            self._render_presets = commands.render_presets(self.resolve)
        return [
            ("Check-up", label, "", text(prefix)) for label, prefix in self._CHECKUP
        ] + [
            ("Render", f"Render: {preset}", "", self._command(commands.render, preset, stay=True))
            for preset in self._render_presets
        ] + [  # ...or only the clip under the playhead
            ("Render", f"Render this clip: {preset}", "", self._command(commands.render, preset, True, stay=True))
            for preset in self._render_presets
        ] + [
            ("Render", "Stop rendering", "", self._command(commands.stop_rendering, stay=True)),

        ] + ([] if fusion_animate.PARKED else [  # Fusion: ready-made moves instead of keyframes by hand (parked for now)
            ("Animate", f"Animate in: {fusion_animate.name_of(key, 'in')}", "",
             self._command(fusion_animate.animate, key, "in", self._animate_seconds()))
            for key in fusion_animate.ANIMATIONS
        ] + [
            ("Animate", f"Animate out: {fusion_animate.name_of(key, 'out')}", "",
             self._command(fusion_animate.animate, key, "out", self._animate_seconds()))
            for key in fusion_animate.ANIMATIONS
        ] + [
            ("Animate", label, "", self._command(fusion_animate.existing, what))
            for label, what in (("Keyframes: smooth them", "smooth"), ("Keyframes: turn them round", "reverse"),
                                ("Keyframes: take them off", "remove"))
        ])

    # the check-up: (row in the > list, the search that lists them, its kind)
    _CHECKUP = [("Missing files", "missing: "), ("Duplicates", "dup: "), ("Unused clips", "u: "),
                ("Clipping sounds", "clipping: ")]

    def _all_actions(self):
        return self._actions() + self._commands()

    def _checkup_rows(self, kind):
        """[(clip row index, what's wrong)] for missing: / dup: / clipping: -
        worked out once each time the picker opens (or the Media Pool is read again)."""
        from . import checkup
        cache = self._checkup_cache
        if cache.get("rows") is not self.model.clip_rows:
            cache.clear()
            cache["rows"] = self.model.clip_rows
        if kind not in cache:
            rows = self.model.clip_rows
            try:
                if kind == "missing":
                    cache[kind] = checkup.missing(rows)
                elif kind == "duplicate":
                    cache[kind] = checkup.duplicates(rows, self.session.get("filtered_group_list", []))
                else:
                    cache[kind] = checkup.clipping(rows)
            except Exception as e:
                print(f"[check-up] {kind}: {e}")
                cache[kind] = []
        return cache[kind]

    def _checkup_summary(self, label):
        """What a check-up row says next to its name: how many, or all good."""
        kind = {"Missing files": "missing", "Duplicates": "duplicate", "Clipping sounds": "clipping"}.get(label)
        if kind is None and "unused" not in self._checkup_cache:
            self._checkup_rows("missing")  # (starts the cache over if the Media Pool was read again)
            self._checkup_cache["unused"] = self._unused_rows()
        n = len(self._checkup_rows(kind)) if kind else len(self._checkup_cache["unused"])
        if kind == "clipping" and not n and not any("clips" in (getattr(r, "analysis", None) or {})
                                                    for r in self.model.clip_rows if r.category == "audio"):
            return "not checked yet - run Actions \u203a Analyse sounds"
        if not n:
            return "none - all good"
        what = {"Missing files": "whose file is gone", "Duplicates": "in the Media Pool more than once",
                "Unused clips": "not on this timeline", "Clipping sounds": "too loud for the file"}[label]
        return f"{n} clip{'s' if n != 1 else ''} {what}"

    def _reset_place_and_save(self):
        d = self.settings.display
        d["window_width"] = d["window_height"] = 0
        d["picker_pos"] = []
        self.settings.save()
        self.reset_place()

    # the rows that open a family of actions in the > list (see _commands)
    _OPENERS = {"Project check-up", "Render\u2026", "Animate\u2026"}
    # other words a row is found by: what's on that page of Settings
    _LABEL_WORDS = {
        "Grab frame": "still screenshot picture",
        "Record voiceover": "voice over narration microphone mic",
        "Undo Clipse\u2019s last step": "undo back",
        "Project check-up": "missing duplicates unused clipping health",
        "Organise project": "organize sort bins colours colors clip colour tidy media pool",
        "Add marker": "marker add place note b-roll broll explain",
        "Stretch marker to clips": "range marker selected clips stretch length duration b-roll broll",
        "Hide - show markers": "hide show markers toggle visible clean timeline",
    }
    # words that also find a group of actions in the > list
    _GROUP_WORDS = {"Check-up": "checkup check up health",
                    "Render": "export deliver", "Animate": "animation keyframes motion move ease"}

    def _action_row(self, i, group, label, key, info=None):
        shown = keycaps.key_name(self.settings.keybinds.get(key, "")) if key and self.settings.keybinds.get(key) else ""
        row = rc.RowData(self.settings.icons.get("action", ""), "action", label,
                         info if info is not None else f"{group}   {shown}".rstrip(), path=str(i))
        row.glyph = "insert_as" if group == "Insert as" else ACTION_GLYPH.get(label) or GROUP_GLYPH.get(group)
        if group == "Clip colour" and not label.endswith("None"):
            row.color = label.split(": ", 1)[1]
        return row

    def _action_rows(self, text):
        """> in the search: the actions as rows, searchable, Enter runs one."""
        from .fuzzy import fold, fuzzy_score
        from . import picks
        learned = picks.boosts(text) if text and self.settings.general.get("learn_picks", True) else {}
        rows = []
        counting = "check" in text.lower()  # the check-up's numbers only when it's what was asked for
        for i, (group, label, key, _fn) in enumerate(self._all_actions()):
            # a family (pages, render presets, clip colours, the check-up) is one
            # row that opens it until something is typed - then it's its members
            if (group in self._GROUP_WORDS) != bool(text) and (group in self._GROUP_WORDS or label in self._OPENERS):
                continue
            target = f"{label} {group} {self._GROUP_WORDS.get(group, '')}"
            score = fuzzy_score(text, target) if text else 0
            if score is None and label in self._LABEL_WORDS:
                # found by what's on it ("theme" -> Settings: Appearance) - whole words only, or the
                # long lists of words would match almost anything typed
                words = fold(f"{label} {self._LABEL_WORDS[label]}").replace(":", " ").split()
                if all(any(word.startswith(typed) for word in words) for typed in fold(text).split()):
                    score = 30.0
            if score is None:
                continue
            row = self._action_row(i, group, label, key,
                                   self._checkup_summary(label) if group == "Check-up" and counting
                                   else None)
            # whole points only: a family (the pages, the presets) keeps its own order
            rows.append(((-math.floor((score or 0) + learned.get(picks.key_for(row), 0.0)) if text else 0, i), row))
        rows.sort(key=lambda t: t[0])
        return [r for _s, r in rows]

    # actions that work on the highlighted clip - only offered in the > list,
    # not mixed into a normal search (there the highlighted row IS the action)
    _CLIP_ACTIONS = {"Favourite", "Show in Media Pool", "Show in file manager", "Picture only", "Sound only",
                     "Sounds like this", "Tags"}

    def _search_action_rows(self, text):
        """Actions shown among normal search results (Settings -> General):
        only clear hits - every typed word starts a word of the action's
        name ("grab" -> Grab frame, "tpl" no, "temp" -> Project templates)."""
        from .fuzzy import fold
        words = fold(text).split()
        if not words or len(text.strip()) < 3:
            return []
        rows = []
        shortcuts_listed = self.settings.page_defaults.get(self._current_page_key(), {}).get("shortcuts", True)
        for i, (group, label, key, _fn) in enumerate(self._all_actions()):
            # a clip colour's name is far more often a clip you're looking for
            if label in self._CLIP_ACTIONS or group in ("Insert as", "Clip colour"):
                continue
            if shortcuts_listed and label in self._SHORTCUT_ACTIONS:  # its shortcut row is in the list already
                continue
            if label in self._BASIC_ACTIONS and self._current_page_key() != "fusion":  # (its Basics row is there)
                continue
            label_words = fold(f"{label} {self._LABEL_WORDS.get(label, '')}").replace("\u2026", "").replace(":", " ").split()
            if all(any(lw.startswith(w) for lw in label_words) for w in words):
                shown = keycaps.key_name(self.settings.keybinds.get(key, "")) if key and self.settings.keybinds.get(key) else ""
                rows.append(self._action_row(i, group, label, key, f"Action   {shown}".rstrip()))
        return rows[:2]

    def _run_palette_action(self, row):
        """Enter on a > row: back to the list you came from (so actions on
        "the highlighted clip" mean the clip you had highlighted), then run it."""
        actions = self._all_actions()
        try:
            _g, _label, _key, fn = actions[int(row.path)]
        except (ValueError, IndexError, TypeError):
            return
        if self.search_edit.text().startswith(">"):  # back to where you were before >
            before_text, before_index = getattr(self, "_before_palette", ("", None))
            self._before_palette = ("", None)
            self.search_edit.setText(before_text)
            if before_index is not None and before_index in self.model.visible:
                self._select_row(self.model.visible.index(before_index))
        QTimer.singleShot(0, fn)

    def grab_frame(self):
        """The frame under the playhead into the "frame_grabs" bin as a PNG in
        your folder (stills.py) - and, per Settings, onto the timeline at the
        playhead. Undo takes it back out of both."""
        from . import stills
        try:
            page = self.resolve.GetCurrentPage()
        except Exception:
            page = None
        try:
            return self._grab_frame(stills)
        finally:
            stills.come_back(self.resolve, page)  # (once it's on the timeline: Fusion can't tell where the playhead is)

    def _grab_frame(self, stills):
        files = self.settings.files
        path, message, back = stills.save_frame(self.resolve, self.settings, return_to_page=False)
        if not path:
            return message
        if not back:  # (still on the Color page: an import or insert now can bring Resolve down)
            return f"{message}. Resolve stayed on the Color page, so it isn't in the Media Pool."
        project = self.resolve.GetProjectManager().GetCurrentProject()
        timeline = project.GetCurrentTimeline()
        media_pool = project.GetMediaPool()
        item, folder = stills.import_grab(media_pool, path)
        if item is None:
            return f"{message}, but Resolve couldn't import it."
        where = [f"in the \"{stills.GRABS_BIN}\" bin"]
        inserted, tracks_before = [], self._track_counts(timeline)
        if files.get("grabs_on_timeline", True):
            fps = float(timeline.GetSetting("timelineFrameRate"))
            timecode = timeline.GetCurrentTimecode()
            session = {"media_pool": media_pool, "timeline": timeline, "project": project}
            msg, _, _item, is_audio, location = rc.insert_clip_item(
                self.settings, session, self.insert_frequency, item, folder, item.GetName(),
                rc.tc_to_frame(timecode, fps))
            print(msg)
            inserted.append((location, is_audio))
            where.insert(0, "on the timeline")
        where.append(f"saved as {_os.path.basename(path)}")
        self._remember_timeline_action(timeline, inserted, tracks_before, "the frame grab",
                                       pool_items=[item], media_pool=media_pool)
        self._colour_new([item])
        stats.record("grab")
        return "Grabbed the frame: " + ", ".join(where[:-1]) + (" and " if len(where) > 1 else "") + where[-1] + "."

    def toggle_voiceover(self):
        """Clipse 21 - Record Voiceover (and its tile): pressed once it records - after the count-down, or once
        the timeline plays (Settings > Scripts) - pressed again it stops and the take goes on the timeline
        (voiceover_pill.VoiceoverTake)."""
        take = getattr(self, "_voiceover", None)
        if take is not None and take.active:
            return take.finish()
        from .voiceover_pill import VoiceoverTake
        take = VoiceoverTake(self)
        problem = take.begin()
        if problem:
            take.deleteLater()
            return self._say(problem)
        self._voiceover = take
        take.done.connect(lambda: setattr(self, "_voiceover", None))

    def _place_voiceover(self, path, frame, timeline_id):
        """The take at `path` into the clipse/voiceovers bin, and on the timeline at `frame` on a free audio track.
        Undo takes it back out of both. (on the timeline, what happened)"""
        from . import stills
        name = _os.path.basename(path)
        project = self.resolve.GetProjectManager().GetCurrentProject()
        timeline = project.GetCurrentTimeline() if project else None
        media_pool = project.GetMediaPool() if project else None
        if media_pool is None:
            return False, f"Saved as {name}"
        item, folder = stills.import_grab(media_pool, path, stills.VOICE_BIN)
        if item is None:
            return False, f"Saved as {name}, but Resolve couldn't import it"
        if timeline is None or self._timeline_id(timeline) != timeline_id:  # (another timeline open by now)
            self._remember_timeline_action(timeline, [], None, "the voiceover", pool_items=[item], media_pool=media_pool)
            return False, f"Another timeline is open: {name} is in the {stills.VOICE_BIN} bin"
        tracks_before = self._track_counts(timeline)
        session = {"media_pool": media_pool, "timeline": timeline, "project": project}
        msg, _, _item, is_audio, location = rc.insert_clip_item(
            self.settings, session, self.insert_frequency, item, folder, item.GetName(), frame)
        print(msg)
        self._remember_timeline_action(timeline, [(location, is_audio)], tracks_before, "the voiceover",
                                       pool_items=[item], media_pool=media_pool)
        if not location:
            return False, f"{name} didn't land on the timeline - it's in the {stills.VOICE_BIN} bin"
        return True, f"Voiceover on A{location[1]}"

    def _fusion_target(self):
        """On the Fusion page, Enter adds clips to the composition instead
        of the timeline (Settings -> General)."""
        return self.settings.general.get("fusion_enter_adds_clips", True) and self._current_page_key() == "fusion"

    def _add_to_fusion(self, indices, connect=True):
        added = 0
        went_in = []
        for idx in indices:
            for chosen_item, _folder, name, category in rc.expand_row_to_items(
                    self.session, self.settings, idx, self.selection_order_ids):
                if category == "audio":
                    print(f"'{name}' is a sound - Fusion has no use for it, skipped.")
                    continue
                try:
                    path = chosen_item.GetClipProperty("File Path") or ""
                except Exception:
                    path = ""
                media_id, frames = self._media_id_and_frames(chosen_item, name)
                ok, message = scripts_fusion.add_clip_to_comp(
                    self.resolve, path, name, self.session.get("timeline"), connect=connect,
                    trim=self._source_range(chosen_item, name), media_id=media_id, frames=frames)
                print(message)
                rc.record_recent(name)
                if ok:
                    added += 1
                    went_in.append(("clip", name, path))
        if added:
            self._remember_fusion_action(f"adding {added} clip{'s' if added != 1 else ''}", steps=added)
            self._record_fusion_history(went_in)

    def _insert_with(self, preset, indices):
        """Puts the clips of `indices` (rows; staged ones repeat) on the
        timeline the way `preset` says - see presets.py."""
        if self._fusion_target():
            self._add_to_fusion(indices, connect=preset["spacing"] != "back_to_back")
            return
        if self.session.get("insert_convert"):  # Alt+Enter: this insert ends as a compound clip
            preset = dict(preset, convert=self.session["insert_convert"])
        self._preset_used = preset.get("id")
        self._record_history(indices, preset)
        timeline = self.session["timeline"]
        if timeline is None:
            print("No timeline in the current Resolve project \u2014 create one before inserting.")
            return
        clips = []
        for idx in indices:
            clips.extend(rc.expand_row_to_items(self.session, self.settings, idx, self.selection_order_ids))
        if not clips:
            print("Nothing to insert.")
            return
        set_media = preset["media"] != "both" and not self.session.get("insert_media")
        if set_media:
            self.session["insert_media"] = preset["media"]
        try:
            said = self._run_preset(timeline, preset, clips)
            print(said)
            if "didn't land" in said or said == self.NOTHING_LANDS:  # (the picker is closed: say it on screen)
                self._say(said if said == self.NOTHING_LANDS else said.replace(" (details in service.log)", ""), 8000)
        finally:
            if set_media:
                self.session["insert_media"] = None
            # Insert as is for the one insert: the next is plain again (History puts it back)
            if presets_mod.used(self.settings, preset):
                self.settings.save()
                self.hints_label.set_hints(self._footer_hints())
            self._preset_used = None

    def _clip_range(self, item, name, preset, fps):
        """The part of a clip to use: in/out (or the sound without its
        silence), cut to the preset's length."""
        source_range = self._source_range(item, name)
        # a sound has its own Length (also a video's sound, inserted by itself)
        sound = item.GetClipProperty("Type") == "Audio" or self.session.get("insert_media") == "audio"
        seconds = preset.get("length_audio", 0.0) if sound else preset["length"]
        if not seconds:
            return source_range
        try:
            clip_fps = float(item.GetClipProperty("FPS") or 0) or fps
        except Exception:
            clip_fps = fps
        length = max(1, int(round(seconds * clip_fps)))
        if source_range:
            return source_range[0], min(source_range[1], source_range[0] + length)
        if rc.is_still_image(name, item.GetClipProperty("Type")):
            return 0, length
        return 0, min(length, rc.compute_clip_duration(self.settings, item, name, fps))

    NOTHING_LANDS = ("Resolve isn't taking clips on this timeline right now - nothing was inserted. "
                     "If a compound clip is open in the timeline, go back to the timeline itself and try again.")

    def _remove_tracks_added(self, timeline, before):
        """The empty tracks an insert that came to nothing made on the way: gone again."""
        try:
            for kind, was in zip(("video", "audio"), before):
                for index in range(int(timeline.GetTrackCount(kind)), int(was), -1):
                    if not (timeline.GetItemListInTrack(kind, index) or []):
                        timeline.DeleteTrack(kind, index)
        except Exception as e:
            print(f"[insert] couldn't take the empty tracks away again: {e}")

    def _run_preset(self, timeline, preset, clips):
        fps = float(timeline.GetSetting("timelineFrameRate"))
        original_timecode = timeline.GetCurrentTimecode()
        base = rc.tc_to_frame(original_timecode, fps)
        timeline_start = int(timeline.GetStartFrame())
        tracks_before = self._track_counts(timeline)
        rng = random.Random()
        inserted, skipped_tracks = [], []
        pictures_placed = False
        self._end_target = None

        def put(item, folder, name, start, source_range):
            msg, end, _ti, is_audio, location = rc.insert_clip_item(
                self.settings, self.session, self.insert_frequency, item, folder, name, max(timeline_start, start),
                skipped_tracks_out=skipped_tracks, source_range=source_range)
            print(msg)
            inserted.append((location, is_audio))
            # The very first clip found no track that would take it: Resolve isn't taking clips on this
            # timeline at the moment. Stop here - going on tried twenty tracks for every one of forty
            # clips (2026-10-13: 800 appends that landed nowhere, and forty empty tracks left behind).
            if location is None and msg.startswith("Insert failed") and not any(l for l, _a in inserted):
                raise _NothingLands(name)
            return end

        try:
            where = preset["where"]
            if where in ("markers", "cuts"):
                try:
                    frames = self._place_frames(timeline, where, preset.get("marker_colours"), preset.get("cut_tracks"),
                                                preset.get("cut_edges", "between"))
                except Exception as e:
                    return f"Couldn't read the timeline's {where}: {e}"
                if not frames:
                    return ("No markers on the timeline or its clips - add one with M." if where == "markers"
                            else f"No cuts on {', '.join(preset.get('cut_tracks') or ['V1'])} - Insert as chooses "
                                 f"which tracks count.")
                # each staged clip's length on this timeline (and its loudest moment, if that goes on the
                # marker) - then where every one goes, overlaps settled, before anything is put down
                staged = []
                for item, folder, name, category in clips:
                    source_range = self._clip_range(item, name, preset, fps)
                    still = rc.is_still_image(name, item.GetClipProperty("Type"))
                    if source_range:  # (asked in the clip's own frames)
                        length = rc.on_timeline(item, source_range[1] - source_range[0], fps)
                    elif still:
                        length = rc.compute_clip_duration(self.settings, item, name, fps)  # (what a picture lasts)
                    else:
                        length = rc.on_timeline(item, rc.compute_clip_duration(self.settings, item, name, fps), fps)
                    loudest = None
                    if preset["align" if category == "audio" else "align_pictures"] == "loudest" and not still:
                        loudest = self._loudest_frame(item, source_range, fps)
                    staged.append({"length": length, "loudest": loudest, "sound": category == "audio",
                                   "range": source_range, "still": still, "name": name})
                plan = presets_mod.marker_plan(preset, frames, staged, fps, rng)
                for e in plan:
                    item, folder, name, _category = clips[e["clip"]]
                    own = staged[e["clip"]]
                    source_range = own["range"]
                    if e["head"] or e["length"] != own["length"]:  # cut where it would overlap another
                        first = (source_range[0] if source_range else 0) + \
                            (rc.of_clip(item, e["head"], fps) if e["head"] else 0)
                        source_range = (first, first + rc.of_clip(item, e["length"], fps))
                    put(item, folder, name, max(timeline_start, e["start"]), source_range)
                what = "marker" if where == "markers" else "cut"
                kinds = {bool(st["sound"]) for st in staged}
                each = 2 if preset.get("pair", "both") == "both" and len(kinds) == 2 else 1  # (a picture and a sound)
                done = (f"Placed {len(plan)} clip{'s' if len(plan) != 1 else ''}, one at every {what}." if each == 1
                        else f"Placed {len(plan)} clips, a picture and a sound at every {what}.")
                if len(plan) < len(frames) * each:
                    left = len(frames) * each - len(plan)
                    done += f" {left} had no room left - the clip{'s' if left != 1 else ''} before covered {'them' if left != 1 else 'it'}."
            else:
                # Repeat with one kind staged: it starts over until there are as many as asked (pairs: `repeated`)
                clips = presets_mod.up_to(preset, clips, [c[3] == "audio" for c in clips])
                spacing = preset["spacing"] if len(clips) > 1 else "together"
                # Repeat to match: 1 picture and 10 sounds - the picture goes in with every sound
                pairs = presets_mod.repeated(dict(preset, spacing=spacing), [c[3] == "audio" for c in clips])
                if pairs and spacing == "interval":  # (picture n and sound n land together on the curve)
                    clips = [clips[i] for pair in pairs for i in pair if i is not None]
                if pairs and spacing == "back_to_back":
                    self._insert_pairs(clips, pairs, preset, fps, base, put)
                elif spacing in ("interval", "together"):
                    plan = []
                    if spacing == "interval":
                        # pictures and sounds each keep their own rhythm: staged photo 1 + whoosh 1 land together
                        pictures = [c for c in clips if c[3] != "audio"]
                        sounds = [c for c in clips if c[3] == "audio"]
                        at = {"p": presets_mod.offsets(preset, len(pictures), rng),
                              "s": presets_mod.offsets(preset, len(sounds), rng)}
                        count = {"p": 0, "s": 0}
                        for item, folder, name, category in clips:
                            kind = "s" if category == "audio" else "p"
                            plan.append([item, folder, name, base + at[kind][count[kind]],
                                         self._clip_range(item, name, preset, fps)])
                            count[kind] += 1
                    else:
                        plan = [[item, folder, name, base, self._clip_range(item, name, preset, fps)]
                                for item, folder, name, _category in clips]
                    # pictures and sounds each end by themselves or together (Ends, Sounds end)
                    kinds = [c[3] == "audio" for c in clips]
                    with_sounds = preset.get("ends") == "audio" and False in kinds and True in kinds
                    with_pictures = preset.get("ends_audio") == "pictures" and False in kinds and True in kinds
                    together = {"pictures": with_sounds or (preset.get("ends") in ("together", "audio")
                                                            and kinds.count(False) > 1),
                                "sounds": with_pictures or (preset.get("ends_audio") in ("together", "first")
                                                            and kinds.count(True) > 1)}
                    if any(together.values()):  # each its own length first; Length is how long the LAST one shows
                        own = dict(preset, length=0.0 if together["pictures"] else preset["length"],
                                   length_audio=0.0 if together["sounds"] else preset.get("length_audio", 0.0))
                        for entry in plan:
                            entry[4] = self._clip_range(entry[0], entry[2], own, fps)
                    first = len(inserted)
                    for item, folder, name, start, source_range in plan:
                        put(item, folder, name, start, source_range)
                    if any(together.values()):
                        self._place_pictures(timeline, preset, inserted[first:])  # (a clip put back keeps its look)
                        pictures_placed = True
                        ours = inserted[first:]
                        self._end_together(timeline, preset, ours, plan, fps, together, with_sounds, with_pictures)
                        inserted[first:] = ours  # (a clip moved up a track has its new place)
                else:
                    cursor = base
                    for item, folder, name, _category in clips:
                        end = put(item, folder, name, cursor, self._clip_range(item, name, preset, fps))
                        if spacing == "back_to_back":
                            cursor = end
                landed = sum(1 for location, _is_audio in inserted if location)
                done = f"Inserted {landed} clip{'s' if landed != 1 else ''}" + \
                    (f" as {preset['name']}." if preset.get("id") not in (None, "normal") else ".")
                if landed < len(inserted):  # say so - not "Inserted 18 clips" when 16 of them didn't land
                    done += f" {len(inserted) - landed} didn't land - Resolve wouldn't take them (details in service.log)."

        except _NothingLands:
            rc.clean_skipped_tracks(timeline, skipped_tracks)
            self._remove_tracks_added(timeline, tracks_before)
            return self.NOTHING_LANDS
        rc.clean_skipped_tracks(timeline, skipped_tracks)
        self._finish_preset(timeline, preset, inserted, rng, pictures_placed)
        self._remember_timeline_action(timeline, inserted, tracks_before,
                                       "the insert" if len(inserted) == 1 else f"inserting {len(inserted)} clips")
        return done

    def _insert_pairs(self, clips, pairs, preset, fps, base, put):
        """Repeat to match, back to back: a picture and a sound together, then the next pair after them.
        A pair lasts as long as its clip of the kind there's more of; the other one fills it - a picture
        exactly (it takes any length), a video or sound as far as it goes (presets.pair_lengths)."""
        by_sound = presets_mod.pairs_lead(pairs, [c[3] == "audio" for c in clips])
        cursor = base
        for p_index, s_index in pairs:
            first, second = (s_index, p_index) if by_sound else (p_index, s_index)
            if first is None:  # (the other kind has run out: this one by itself)
                first, second = second, None
            item, folder, name, _category = clips[first]
            length = put(item, folder, name, cursor, self._clip_range(item, name, preset, fps)) - cursor
            if length <= 0:  # (it didn't land: nothing to go with)
                continue
            if second is None:
                cursor += length
                continue
            item, folder, name, _category = clips[second]
            own = self._clip_range(item, name, preset, fps)
            still = rc.is_still_image(name, item.GetClipProperty("Type"))
            first = own[0] if own else 0
            whole = (own[1] - own[0]) if own else rc.compute_clip_duration(self.settings, item, name, fps)
            if still:
                lasts = length
            else:
                lasts = presets_mod.pair_lengths(length, rc.on_timeline(item, whole, fps), False)
            put(item, folder, name, cursor, (first, first + rc.of_clip(item, lasts, fps)))
            cursor += length

    @staticmethod
    def _loudest_frame(item, source_range, fps):
        """Timeline frames from where the clip starts (its in mark, or where its sound starts) to its
        loudest moment - or None when there's no sound to go by."""
        from . import sound_analysis as sa
        try:
            seconds = sa.loudest(item.GetClipProperty("File Path") or "")
        except Exception as e:
            print(f"[loudest] couldn't read '{item.GetName()}': {e}")
            return None
        if seconds is None:
            return None
        rate = rc.clip_rate(item, fps)
        into = seconds * rate - (source_range[0] if source_range else 0)  # (in the clip's own frames)
        return max(0, int(round(into * fps / rate))) if rate else None

    @staticmethod
    def _picture_size(item):
        """(width, height) in pixels of a timeline item's picture, from its clip's Resolution ("4032x3024")."""
        try:
            text = str(item.GetMediaPoolItem().GetClipProperty("Resolution") or "")
            w, h = (float(v) for v in text.lower().replace(" ", "").split("x")[:2])
            return (w, h) if w > 0 and h > 0 else None
        except Exception:
            return None

    @staticmethod
    def _picture_look(item):
        """A timeline item's size, place, turn and opacity - to give them to the clip that replaces it."""
        look = {}
        for key, plain in (("ZoomX", 1.0), ("ZoomY", 1.0), ("Pan", 0.0), ("Tilt", 0.0), ("RotationAngle", 0.0),
                           ("Opacity", 100.0)):
            try:
                value = float(item.GetProperty(key))
            except Exception:
                continue
            if abs(value - plain) > 1e-6:
                look[key] = value
        return look

    def _scaling_mode(self, timeline):
        """How Resolve sizes a picture that isn't the timeline's size (Project Settings -> Image Scaling ->
        Mismatched resolution files) - the timeline's own setting first, then the project's."""
        names = {"scaletofit": "fit", "scaletocrop": "fill", "stretch": "stretch", "centercrop": "native"}
        for source in (timeline, self.session.get("project")):
            try:
                value = str(source.GetSetting("timelineInputResMismatchBehavior") or "").replace(" ", "").lower()
            except Exception:
                value = ""
            if value in names:
                return names[value]
        return "fit"

    def _end_together(self, timeline, preset, inserted, plan, fps, together, with_sounds=False, with_pictures=False):
        """Insert as -> End together, for the pictures (videos and stills), the sounds, or both -
        each by themselves (`together`: {"pictures": bool, "sounds": bool}). A group ends where its
        clip that starts last ends: its own length, or that group's Length after it starts - or,
        the pictures `with_sounds`, where the sound that ends last ends (the sounds `with_pictures`, where the
        picture that ends last ends; each with the other, where the last of all ends). Each clip is put back cut
        to that point - or lengthened, as far as it goes; a still takes any length
        (rc.append_clip), so it gets there whatever its start."""
        entries = []
        for slot, ((location, _is_audio), (item, _folder, name, start, source_range)) in enumerate(zip(inserted, plan)):
            live = rc.lookup_item(timeline, *location) if location else None
            if live is None:
                continue
            try:
                end = int(live.GetEnd())
            except Exception:
                continue
            still = rc.is_still_image(name, item.GetClipProperty("Type"))
            entries.append({"slot": slot, "location": location, "sound": location[0] == "audio", "item": item, "name": name,
                            "start": start, "end": end, "range": source_range, "still": still})
        media_pool = self.session.get("media_pool")
        targets = []
        # (the sounds first: the pictures may be ending where they do - or the other way round)
        groups = [("sounds", preset.get("length_audio", 0.0)), ("pictures", preset["length"])]
        if with_pictures and not with_sounds:
            groups.reverse()
        last_of_all = max((e["end"] for e in entries), default=0)
        for what, seconds in groups:
            members = [e for e in entries if e["sound"] == (what == "sounds")]
            if not together.get(what) or not members or media_pool is None:
                continue
            heard = [e["end"] for e in entries if e["sound"]]
            seen = [e["end"] for e in entries if not e["sound"]]
            if with_sounds and with_pictures:
                target = last_of_all
            elif what == "pictures" and with_sounds and heard:
                target = max(heard)
            elif what == "sounds" and with_pictures and seen:
                target = max(seen)
            else:
                # the one the others follow: the last to start - or, sounds ending with the first, the first
                first_leads = what == "sounds" and preset.get("ends_audio") == "first"
                lead = min(members, key=lambda e: (e["start"], -e["end"])) if first_leads \
                    else max(members, key=lambda e: (e["start"], e["end"]))
                target = lead["end"]
                if seconds:  # (a sound or video is never longer than it is)
                    asked = lead["start"] + int(round(seconds * fps))
                    target = asked if lead["still"] else min(asked, lead["end"])
            targets.append(target)
            for e in members:
                if e["end"] == target:
                    continue
                first = e["range"][0] if e["range"] else 0
                # (a length is asked for in the clip's own frames - a 24 fps sound on a 60 fps timeline!)
                length = rc.of_clip(e["item"], max(1, target - e["start"]), fps)
                if not e["still"]:
                    whole = rc.compute_clip_duration(self.settings, e["item"], e["name"], fps)
                    length = max(1, min(length, whole - first))
                if e["start"] + rc.on_timeline(e["item"], length, fps) == e["end"]:  # already as long as it can be
                    continue
                live = rc.lookup_item(timeline, *e["location"])
                track_type, track_index, start = e["location"]
                reach = start + rc.on_timeline(e["item"], length, fps)
                try:
                    # Lengthened, it may run into the next clip on its track (two short videos one after the
                    # other on V1): Resolve then takes nothing and the clip was gone (2026-10-24). It goes on
                    # the lowest track with room instead.
                    own = {(kind, at, it.GetStart()) for it in [live] + list(live.GetLinkedItems() or [])
                           for kind, at in [it.GetTrackTypeAndIndex() or ("", 0)]}
                    stays = rc.room_on(timeline, track_type, track_index, start, reach,
                                       rc.sound_tracks_of(e["item"])[0], besides=own)
                    look = self._picture_look(live) if track_type == "video" else {}
                    timeline.DeleteClips([live])

                    def put_back(index):
                        info = {"mediaPoolItem": e["item"], "trackIndex": index, "recordFrame": start}
                        if track_type == "audio":
                            info["mediaType"] = 2
                        rc.append_clip(media_pool, e["item"], info, first, length, e["still"])
                        return rc.lookup_item(timeline, track_type, index, start)

                    index = track_index if stays else rc.lowest_room(timeline, e["item"], track_type, start, reach)
                    again = put_back(index)
                    if again is None and stays:  # Resolve wouldn't take it there after all
                        index = rc.lowest_room(timeline, e["item"], track_type, start, reach)
                        again = put_back(index)
                    if again is not None:
                        if index != track_index:
                            print(f"[end together] '{e['name']}' ran into the next clip on {track_type[0].upper()}"
                                  f"{track_index} - put on {track_type[0].upper()}{index}")
                        e["location"] = (track_type, index, start)
                        inserted[e["slot"]] = (e["location"], inserted[e["slot"]][1])
                        for key, value in look.items():  # the size and place it was just given
                            again.SetProperty(key, value)
                        e["end"] = int(again.GetEnd())
                    else:
                        print(f"[end together] '{e['name']}' didn't land again")
                except Exception as ex:
                    print(f"[end together] '{e['name']}': {ex}")
        # Wrapped up afterwards (Afterwards > Wrap them into), the one clip is cut at the end point too -
        # only when everything in it ends together, or a sound left to run on would be cut with it.
        everything = all(together.get("sounds" if e["sound"] else "pictures") for e in entries)
        self._end_target = max(targets) if targets and everything else None

    def _cut_wrapper(self, timeline, item, target):
        """End together + Wrap them into: the compound / Fusion clip that holds
        everything is cut at the end point - so the stills end there too."""
        media_pool = self.session.get("media_pool")
        try:
            start, end = int(item.GetStart()), int(item.GetEnd())
            if end <= target or media_pool is None:
                return
            pool_item = item.GetMediaPoolItem()
            _kind, track_index = item.GetTrackTypeAndIndex()
            if pool_item is None:
                return
            timeline.DeleteClips([item])
            media_pool.AppendToTimeline([{"mediaPoolItem": pool_item, "startFrame": 0, "endFrame": target - start,
                                          "trackIndex": track_index, "recordFrame": start}])
            print(f"[end together] the wrapped clip is cut at frame {target}")
        except Exception as e:
            print(f"[end together] couldn't cut the wrapped clip: {e}")

    def _tuck_away(self, media_pool, pool_items):
        """The compound / Fusion clips the app made go in one bin (stills.COMPOUND_BIN), out of the way - Resolve
        puts a new one in whatever bin is open."""
        pool_items = [p for p in pool_items if p is not None]
        if media_pool is None or not pool_items:
            return
        try:
            from . import stills
            current = media_pool.GetCurrentFolder()
            target = stills.app_bin(media_pool, stills.COMPOUND_BIN)
            if current is not None:
                media_pool.SetCurrentFolder(current)  # (making a bin moves you into it)
            if target is not None:
                media_pool.MoveClips(pool_items, target)
        except Exception as e:
            print(f"[convert] couldn't put the new clip in {stills.COMPOUND_BIN}: {e}")

    def _finish_preset(self, timeline, preset, inserted, rng, pictures_placed=False):
        """Size and place in the frame, clip colour, then wrapping up."""
        if not pictures_placed:
            self._place_pictures(timeline, preset, inserted)
        if preset["colour"]:
            for location, _is_audio in inserted:
                item = rc.lookup_item(timeline, *location) if location else None
                if item is not None:
                    try:
                        item.SetClipColor(preset["colour"])
                    except Exception as e:
                        print(f"[preset] couldn't colour the clip: {e}")
        self._switch_off_parts(timeline, inserted)
        self._convert_and_clean(inserted, preset["convert"])  # (it unlinks them itself, before wrapping)
        if preset["convert"] in (None, "none"):
            self._unlink_sounds(timeline, inserted)

    @staticmethod
    def _switch_off_parts(timeline, inserted):
        """A song's stems switched off in the preview go on the timeline switched off (2026-10-31): its sound
        tracks land on audio tracks N, N+1 ... in the file's order, linked - the one on N + i is part i."""
        from . import stems
        for location, _is_audio in inserted:
            item = rc.lookup_item(timeline, *location) if location is not None else None
            if item is None:
                continue
            try:
                pool_item = item.GetMediaPoolItem()
                path = pool_item.GetClipProperty("File Path") if pool_item is not None else ""
                names = stems.part_names(path)
                off = stems.muted(path, names)
                if not off:
                    continue
                pieces = [x for x in [item] + list(item.GetLinkedItems() or []) if x.GetTrackTypeAndIndex()[0] == "audio"]
                pieces.sort(key=lambda x: int(x.GetTrackTypeAndIndex()[1]))
                if len(pieces) != len(names):
                    print(f"[parts] '{item.GetName()}': {len(pieces)} sound pieces for {len(names)} parts - left on")
                    continue
                for i in sorted(off):
                    pieces[i].SetClipEnabled(False)
                print(f"[parts] '{item.GetName()}': switched off {', '.join(names[i] for i in sorted(off))}")
            except Exception as e:
                print(f"[parts] couldn't switch the parts off: {e}")

    @staticmethod
    def _unlink_sounds(timeline, inserted):
        """A sound whose file has several tracks (a song's stems) lands as that many pieces, linked by Resolve: they
        go apart, each to move by itself (2026-10-31: "i dont want the audio clips to be linked"). A video's picture
        and sound stay linked."""
        for location, is_audio in inserted:
            if location is None or not is_audio:
                continue
            item = rc.lookup_item(timeline, *location)
            try:
                linked = list(item.GetLinkedItems() or []) if item is not None else []
                if linked and all(other.GetTrackTypeAndIndex()[0] == "audio" for other in linked):
                    ok = timeline.SetClipsLinked([item] + linked, False)
                    print(f"[link] '{item.GetName()}': its {len(linked) + 1} sound tracks unlinked -> {ok}")
            except Exception as e:
                print(f"[link] couldn't unlink the sound's tracks: {e}")

    def _place_pictures(self, timeline, preset, inserted):
        """Size, place and turn each picture (Insert as -> In the frame)."""
        if presets_mod.has_picture_changes(preset):
            try:
                width = float(timeline.GetSetting("timelineResolutionWidth") or 1920)
                height = float(timeline.GetSetting("timelineResolutionHeight") or 1080)
            except Exception:
                width, height = 1920.0, 1080.0
            items = [rc.lookup_item(timeline, *location) for location, is_audio in inserted
                     if location is not None and not is_audio]
            items = [item for item in items if item is not None]
            # the same layout the editor's preview showed (its seed), every picture inside the frame
            pid = preset.get("id") or "history"
            places = presets_mod.layout(preset, len(items), width, height,
                                        [self._picture_size(item) for item in items],
                                        presets_mod.seed_for(self.settings, pid), self._scaling_mode(timeline))
            for item, place in zip(items, places):
                for key, value in presets_mod.props_for(preset, place).items():
                    try:
                        item.SetProperty(key, value)
                    except Exception as e:
                        print(f"[preset] couldn't set {key}: {e}")
            presets_mod.reshuffle(self.settings, pid)  # the next insert gets a fresh layout (the preview follows)
            self.settings.save()

    @staticmethod
    def _sound_inside(timeline, item, locations):
        """(file, seconds into it at the compound clip's first frame) of a sound about to be wrapped - or None."""
        try:
            pool = item.GetMediaPoolItem()
            if pool is None or pool.GetClipProperty("Type") != "Audio":
                return None
            fps = float(timeline.GetSetting("timelineFrameRate") or 24) or 24
            starts = [found.GetStart() for found in (rc.lookup_item(timeline, *loc) for loc in locations) if found is not None]
            return (str(pool.GetClipProperty("File Path") or ""),
                    (float(item.GetLeftOffset() or 0) - (float(item.GetStart()) - float(min(starts)))) / fps)
        except Exception:
            return None

    @staticmethod
    def _remember_song(new_item, song):
        try:
            from .beats import remember_compound
            remember_compound(new_item.GetMediaPoolItem().GetMediaId(), *song)
        except Exception as e:
            print(f"[beats] couldn't remember what's in the compound clip: {e}")

    def _convert_and_clean(self, inserted, clip_type="none"):
        """Post-insert step: wrap everything just inserted into a
        Compound or Fusion clip (Insert as -> Afterwards),
        then remove any track left empty afterward.

        `inserted` is a list of (location, is_audio_only), where location
        is the (track_type, track_index, start_frame) needed to re-fetch
        a fresh TimelineItem — confirmed in practice that a REJECTED
        CreateCompoundClip call leaves the item objects it was given in a
        dead state (GetName() returns None afterward) even though nothing
        raised, so retrying with the same objects silently fails again.
        Always re-fetch fresh right before each attempt instead of
        reusing anything from a previous attempt.

        Resolve can also reject wrapping a mix of video AND audio clips
        into one compound/fusion clip in a single call — if the combined
        attempt is rejected, this retries video and audio as two separate
        groups instead of giving up outright.

        CreateCompoundClip/CreateFusionClip do NOT remove the original
        clips from their tracks on their own — they have to be deleted
        explicitly first, or clean_empty_tracks will never find those
        tracks empty."""
        if clip_type in (None, "none"):
            return
        timeline = self.session["timeline"]
        valid = [(loc, is_audio) for loc, is_audio in inserted if loc is not None]
        if not valid:
            return

        def fresh_items(locations, kind=None):
            """The clips at those places, each with what's linked to it - a clip whose sound is several tracks
            (a song's stems: A1-A4) is that many linked pieces, and they all go in. `kind`: only video / audio."""
            items, seen = [], set()

            def add(item):
                try:
                    track_kind, index = item.GetTrackTypeAndIndex()
                    key = (track_kind, int(index), int(item.GetStart()))
                except Exception:
                    track_kind, key = None, id(item)
                if key in seen or (kind and track_kind and track_kind != kind):
                    return
                seen.add(key)
                items.append(item)

            for location in locations:
                item = rc.lookup_item(timeline, *location)
                if item is None:
                    continue
                add(item)
                try:
                    for other in item.GetLinkedItems() or []:
                        add(other)
                except Exception:
                    pass
            return items

        # Every piece by its place first (a sound of several tracks is that many, linked), then a sound's pieces
        # unlinked - Resolve keeps the links inside the compound clip (2026-10-31: "still linked inside")
        pieces = []
        for location, is_audio in valid:
            pieces.append((tuple(location), is_audio))
            item = rc.lookup_item(timeline, *location)
            try:
                for other in (item.GetLinkedItems() or []) if item is not None else []:
                    kind, index = other.GetTrackTypeAndIndex()
                    pieces.append(((kind, int(index), int(other.GetStart())), kind == "audio"))
            except Exception as e:
                print(f"[convert] couldn't read what's linked to a clip: {e}")
        self._unlink_sounds(timeline, valid)
        valid = list(dict.fromkeys(pieces))
        all_locations = [loc for loc, _is_audio in valid]
        any_converted = False
        media_pool = self.session.get("media_pool")
        open_bin = None
        try:  # (what's in the open bin now: the new clip appears there - Resolve doesn't always hand it back)
            open_bin = media_pool.GetCurrentFolder() if media_pool is not None else None
            there_before = {c.GetMediaId() for c in (open_bin.GetClipList() or [])} if open_bin is not None else set()
        except Exception:
            there_before = set()

        # named after what went in (2026-10-31: "the name of the song") - like_this, as every name Clipse gives
        names = []
        song = None  # (the first sound: what Mark the beats goes by, once it's inside the compound clip)
        for location in all_locations:
            item = rc.lookup_item(timeline, *location)
            try:
                plain = _os.path.splitext(str(item.GetName() or ""))[0] if item is not None else ""
            except Exception:
                plain = ""
            if plain and plain not in names:
                names.append(plain)
            if song is None and item is not None:
                song = self._sound_inside(timeline, item, all_locations)
        from .stills import like_this
        wrap_name = like_this(names[0]) if names else ""
        if wrap_name and len(names) > 1:
            wrap_name += f"_and_{len(names) - 1}_more"

        made = []
        new_item = rc.convert_clips(timeline, fresh_items(all_locations), clip_type, wrap_name)
        if new_item:
            rc.delete_original_clips(timeline, fresh_items(all_locations), new_item)
            any_converted = True
            made.append(new_item)
            if song and len(names) == 1:
                self._remember_song(new_item, song)
        else:
            # The return value has been confirmed unreliable on some Resolve
            # versions (same issue as AppendToTimeline) — a falsy result
            # doesn't necessarily mean it failed. Check whether the original
            # items are actually still there before retrying: if they're
            # gone, it almost certainly succeeded silently, and retrying
            # would find and re-wrap the compound clip it just created.
            still_there = [loc for loc in all_locations if rc.lookup_item(timeline, *loc) is not None]
            if len(still_there) < len(all_locations):
                print(f"[convert] returned a falsy result, but only {len(still_there)}/{len(all_locations)} "
                      f"original clip(s) are still on the timeline — it almost certainly succeeded "
                      f"despite the falsy return. Not retrying (that would wrap the new clip in another one).")
                any_converted = True
            else:
                print("[convert] combined video+audio conversion was genuinely rejected — "
                      "retrying video and audio as two separate groups instead.")
                groups = (
                    ("video", [loc for loc, is_audio in valid if not is_audio]),
                    ("audio", [loc for loc, is_audio in valid if is_audio]),
                )
                for group_name, group_locations in groups:
                    if not group_locations:
                        continue
                    group_new_item = rc.convert_clips(timeline, fresh_items(group_locations, group_name), clip_type,
                                                      f"{wrap_name}_{group_name}" if wrap_name else None)
                    if group_new_item:
                        rc.delete_original_clips(timeline, fresh_items(group_locations, group_name), group_new_item)
                        any_converted = True
                        made.append(group_new_item)
                    else:
                        print(f"[convert] {group_name} clips also couldn't be converted as a group — left as-is.")

        pool_items = []
        for item in made:
            try:
                pool_items.append(item.GetMediaPoolItem())
            except Exception:
                pass
        if any_converted and open_bin is not None:  # (20 pictures and sounds: made, but None handed back - 2026-10-19)
            try:
                known = {p.GetMediaId() for p in pool_items if p is not None}
                pool_items += [c for c in (open_bin.GetClipList() or []) if c.GetMediaId() not in there_before
                               and c.GetMediaId() not in known
                               and str(c.GetClipProperty("Type") or "").lower().startswith(("compound", "fusion"))]
            except Exception as e:
                print(f"[convert] couldn't look for the new clip in the open bin: {e}")
        self._tuck_away(media_pool, pool_items)
        target = getattr(self, "_end_target", None)
        if target is not None:
            for item in made:
                self._cut_wrapper(timeline, item, target)
        if any_converted and self.settings.timeline_tools.get("remove_empty_tracks", True):
            rc.clean_empty_tracks(timeline)
            rc.nudge_timeline_ui_refresh(timeline)

    # -- selection-order tracking for the Selected Clips row — runs
    # continuously, independent of whether the picker is open, same as
    # the Tk version's poll_selection_order(). --
    def _poll_selection_order(self):
        if self.resolve is None:
            return
        try:
            project = self.resolve.GetProjectManager().GetCurrentProject()
            if project is not None:
                project_name = project.GetName()
                if project_name != self.selection_order_project:
                    self.selection_order_ids = []
                    self.selection_order_project = project_name
                current_ids = [item.GetMediaId() for item in (project.GetMediaPool().GetSelectedClips() or [])]
                current_set = set(current_ids)
                self.selection_order_ids = [i for i in self.selection_order_ids if i in current_set]
                known = set(self.selection_order_ids)
                for media_id in current_ids:
                    if media_id not in known:
                        self.selection_order_ids.append(media_id)
                        known.add(media_id)
        except Exception:
            pass

    # -- live Selected-Clips count — updates the "(N)" on the Selected Clips
    # row in place while the picker is open, so changing your Media Pool
    # selection reflects without reopening. (Bin counts used to be
    # re-walked here every 1.5 s too — on large libraries that was
    # thousands of Resolve calls on the UI thread, making typing stutter.
    # They're now computed from the open/refresh scan instead; Ctrl+R
    # updates them.) Gated on visibility since it's purely cosmetic. Mutates each
    # RowData's .name in place rather than rebuilding the row list, so
    # your current search text, staged clips, and scroll position are
    # all left untouched. --
    def _refresh_live_counts(self):
        if not self.isVisible() or self.model.showing_external or not self._live_count_rows:
            return
        filtered_group_list = self.session.get("filtered_group_list", [])
        root_folder = self.session.get("root_folder")
        media_pool = self.session.get("media_pool")
        changed = False
        for row, idx in self._live_count_rows:
            if idx >= len(filtered_group_list):
                continue
            name, instances, category = filtered_group_list[idx]
            try:
                if category == "bin":
                    path = instances[0][0]
                    bin_folder = rc.find_folder_by_path(root_folder, path)
                    if bin_folder is None:
                        continue
                    count = rc.count_bin_clips(bin_folder, self.settings)
                    new_name = f"{name} ({count})"
                elif category == "selected":
                    count = len(media_pool.GetSelectedClips() or [])
                    new_name = f"Selected Clips ({count})"
                else:
                    continue
            except Exception:
                continue
            if row.name != new_name:
                row.name = new_name
                changed = True
        if changed:
            self.list_view.viewport().update()
        if any(self.model.rows[i].category == "selected" for i in self.model.staged
               if i < len(self.model.rows)):
            self._update_staged_summary()
