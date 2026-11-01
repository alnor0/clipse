"""Settings dialog — General, Appearance, Keybindings only. Insert
options (per-use clip modifiers) live in insert_as_dialog.py (presets)
instead, since those aren't app configuration.

Every control supports "double-click its label/text to reset that one
setting to default", and every tab has a small reset button (top-right)
that resets everything in that tab. Both go through Settings.reset_key /
Settings.reset_namespace — see settings.py — then a full tab rebuild, so
every widget's displayed value stays in sync with no per-widget update
code to maintain."""
import os
import sys

from PySide6.QtCore import Qt, Signal, QObject, QEvent, QSize, QTimer, QPointF
from PySide6.QtGui import QColor, QFont, QFontMetrics, QKeySequence, QPen
from .drag_spinbox import DragDoubleSpinBox, DragSpinBox
from PySide6.QtWidgets import (
    QDialog, QTabWidget, QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QGridLayout,
    QGroupBox, QCheckBox, QAbstractSpinBox, QPushButton, QLabel,
    QKeySequenceEdit, QColorDialog, QFontComboBox, QLineEdit, QSizePolicy,
    QListWidget, QListWidgetItem, QFileDialog, QComboBox, QScrollArea, QFrame, QApplication, QStyledItemDelegate,
)

from .settings import GENERAL_SCHEMA, ICON_COLOR_VARS, INTERFACE_COLOR_VARS, THEME_PRESETS, \
    KEYBIND_LABELS, ICON_DEFAULTS, KEYBIND_SCHEMA, ICON_LABELS, \
    PREFIX_SCHEMA, PREFIX_LABELS, LISTEN_DEFAULTS, TIMELINE_TOOLS_DEFAULTS
from . import clipboard, scripts_fusion
from .fonts import SMALL, at as font_at, css, rel  # (the one scale of sizes)


def _file_manager_name():
    """What the system calls its file manager, for the button text."""
    import platform
    return {"Darwin": "Show in Finder", "Windows": "Show in Explorer"}.get(platform.system(), "Open folder")


class KeyEdit(QKeySequenceEdit):
    """A key box that takes ONE key combination and is done - no waiting
    around for a second key (Qt's default allows multi-key sequences,
    which made it feel stuck). A small x on the right clears it."""

    def __init__(self, sequence=""):
        super().__init__()
        try:
            self.setMaximumSequenceLength(1)
        except AttributeError:  # Qt older than 6.5
            self.keySequenceChanged.connect(lambda seq: seq.count() and self.clearFocus())
        self.setKeySequence(sequence)
        self.editingFinished.connect(self.clearFocus)  # captured - stop listening

    def focusInEvent(self, event):
        self._before = self.keySequence()  # (what Esc goes back to)
        super().focusInEvent(event)

    def keyPressEvent(self, event):
        """Esc while it's listening: stop listening, the key as it was - never Esc as the key (2026-10-15: Esc
        pressed to get out of a box had become the key that inserts)."""
        if event.key() == Qt.Key_Escape and event.modifiers() == Qt.NoModifier:
            self.setKeySequence(getattr(self, "_before", self.keySequence()))
            self.clearFocus()
            event.accept()
            return
        super().keyPressEvent(event)


class _ClearKeyButton(QPushButton):
    """The small x next to a key box."""

    def __init__(self, settings):
        super().__init__()
        self.settings = settings
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self.setToolTip("Remove this key")
        self.setFixedSize(22, 22)
        self.setFlat(True)
        self.setStyleSheet("QPushButton { background: transparent; border: none; padding: 0; }")

    def paintEvent(self, event):
        from PySide6.QtGui import QPainter, QPen
        t = self.settings.theme
        color = QColor(t["picker_text"] if self.underMouse() and self.isEnabled() else t["picker_folder"])
        if not self.isEnabled():
            color.setAlphaF(0.35)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(color, 1.5, Qt.SolidLine, Qt.RoundCap))
        from PySide6.QtCore import QPointF
        cx, cy, r = self.width() / 2, self.height() / 2, 4.0
        p.drawLine(QPointF(cx - r, cy - r), QPointF(cx + r, cy + r))
        p.drawLine(QPointF(cx + r, cy - r), QPointF(cx - r, cy + r))
        p.end()


class KeyField(QWidget):
    """A key box with a remove button on its right."""

    def __init__(self, settings, sequence=""):
        super().__init__()
        self.edit = KeyEdit(sequence)
        self.edit.setFixedWidth(150)  # every key box the same width, so the columns line up
        self.clear_button = _ClearKeyButton(settings)
        self.clear_button.clicked.connect(self.edit.clear)
        self.keySequenceChanged = self.edit.keySequenceChanged
        self.edit.keySequenceChanged.connect(self._update_button)
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(2)
        h.addWidget(self.edit, 1)
        h.addWidget(self.clear_button)
        self._update_button(self.edit.keySequence())
        self.setFixedWidth(150 + 2 + 22)

    def _update_button(self, seq):
        self.clear_button.setEnabled(seq.count() > 0)

    def setToolTip(self, text):
        self.edit.setToolTip(text)


class ResettableLabel(QLabel):
    """A row label that resets its setting to default on double-click."""
    doubleClicked = Signal()

    def __init__(self, text):
        super().__init__(text)
        self.setCursor(Qt.PointingHandCursor)

    def mouseDoubleClickEvent(self, event):
        self.doubleClicked.emit()
        event.accept()


class ResettableCheckBox(QCheckBox):
    """A checkbox whose own label text doubles as the row descriptor —
    double-click resets instead of toggling twice."""
    doubleClicked = Signal()

    def mouseDoubleClickEvent(self, event):
        self.doubleClicked.emit()
        event.accept()  # swallow it — don't let the base class toggle twice


class KeyboardFriendlyComboBox(QComboBox):
    """Up/Down opens the dropdown popup (like a native web <select>)
    instead of silently cycling the value with the popup closed — makes
    it possible to see and pick an option with arrow keys alone, no
    mouse needed."""

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Down, Qt.Key_Up) and not self.view().isVisible():
            self.showPopup()
            event.accept()
            return
        super().keyPressEvent(event)


class _NoWheelOnInputs(QObject):
    """Scrolling over a number box or drop-down never changes it - the
    scroll goes to the page instead (changing a setting by accident while
    scrolling past it was too easy)."""

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Wheel:
            area = obj.parentWidget()
            while area is not None and not isinstance(area, QScrollArea):
                area = area.parentWidget()
            if area is not None:
                QApplication.sendEvent(area.viewport(), event)
            return True
        return False


_NO_WHEEL = None


def _block_wheel(widget):
    global _NO_WHEEL
    if _NO_WHEEL is None:
        _NO_WHEEL = _NoWheelOnInputs()
    widget.removeEventFilter(_NO_WHEEL)
    widget.installEventFilter(_NO_WHEEL)
    widget.setFocusPolicy(Qt.StrongFocus)  # no focus by hovering + scrolling either


def restrict_tab_to_inputs(root_widget):
    """Tab should only stop on actual settable controls — checkboxes,
    spin boxes, combo boxes, text fields, key sequence editors, color
    swatches — not on action buttons (Reset, OK, Add folder, preset
    buttons, etc). Removes plain QPushButtons from the tab order; leaves
    ColorSwatchButton (a real input — click opens a color picker) alone."""
    for btn in root_widget.findChildren(QPushButton):
        if not isinstance(btn, ColorSwatchButton):
            btn.setFocusPolicy(Qt.ClickFocus)
    # A little room between a number box's border and its number (the
    # stylesheet can't reach the field inside a spin box reliably).
    for spin in root_widget.findChildren(QAbstractSpinBox):
        spin.lineEdit().setTextMargins(6, 0, 0, 0)
    for box in root_widget.findChildren(QAbstractSpinBox) + root_widget.findChildren(QComboBox):
        _block_wheel(box)
    # Every dialog runs this after (re)building — also the one place that
    # gives each setting its hover explanation (see help_text.py).
    from .help_text import apply_help
    apply_help(root_widget)
    # A single "&" in a title would be read as a keyboard-shortcut marker
    # and shown as an underline ("Link audio _video") - show it as "&".
    for box in root_widget.findChildren(QGroupBox):
        if "&" in box.title() and "&&" not in box.title():
            box.setTitle(box.title().replace("&", "&&"))
    for cb in root_widget.findChildren(QCheckBox):
        if "&" in cb.text() and "&&" not in cb.text():
            cb.setText(cb.text().replace("&", "&&"))


def _align_forms(page):
    """Every form on a page shares one label column, so labels and fields
    line up from section to section; fields get steady widths instead of
    stretching to whatever is left."""
    from PySide6.QtWidgets import QFontComboBox, QComboBox
    forms = page.findChildren(QFormLayout)
    labels = []
    for form in forms:
        form.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        form.setFormAlignment(Qt.AlignLeft | Qt.AlignTop)
        form.setFieldGrowthPolicy(QFormLayout.FieldsStayAtSizeHint)
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(8)
        for row in range(form.rowCount()):
            label = form.itemAt(row, QFormLayout.LabelRole)
            field = form.itemAt(row, QFormLayout.FieldRole)
            widget = field.widget() if field is not None else None
            if label is not None and label.widget() is not None:
                labels.append(label.widget())
                if isinstance(label.widget(), QLabel):
                    label.widget().setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                    hint = (widget.sizeHint().height() if widget is not None else
                            field.sizeHint().height() if field is not None else 0)
                    label.widget().setMinimumHeight(max(label.widget().sizeHint().height(), hint))
            if isinstance(widget, (QLineEdit, QComboBox, QFontComboBox)) and widget.maximumWidth() > 2000:
                widget.setFixedWidth(320)
            elif isinstance(widget, QAbstractSpinBox):
                widget.setFixedWidth(140)
    return labels


class _AppMark(QWidget):
    """The app's mark (logo.py) on its dark rounded tile, as on the website (its .app-mark: 76 px, corners 18, the
    mark 0.51 of it) - About. In a dark theme it has a faint edge, as the website's has."""

    def __init__(self, settings):
        super().__init__()
        self.settings = settings
        self.setFixedSize(78, 78)

    def paintEvent(self, event):
        from PySide6.QtCore import QRectF
        from PySide6.QtGui import QPainter, QPen
        from . import logo
        from .settings import is_light
        t = self.settings.theme
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        tile = QRectF(1, 1, 76, 76)
        p.setPen(Qt.NoPen if is_light(t["picker_bg"]) else QPen(QColor(t["picker_border"]), 1))
        p.setBrush(QColor(logo.TILE))
        p.drawRoundedRect(tile.adjusted(0.5, 0.5, -0.5, -0.5), 18, 18)
        logo.paint(p, tile.left(), tile.top(), tile.width(), 0.51)
        p.end()


class ThemeCard(QPushButton):
    """A theme as a tile with the picker and its preview drawn in its colours - the same drawing as the tiles of
    Settings > Preview > Preview window (preview_place.Drawer, 2026-10-16: "a more similar style"). Click to
    use it."""

    def __init__(self, name, preset, current, parent=None, settings=None):
        super().__init__(parent)
        self.name, self.preset, self.current = name, preset, current
        self.settings = settings
        from PySide6.QtGui import QFontMetricsF
        self._label_font = font_at(SMALL * rel(settings, "settings")) if settings is not None else QFont(self.font())
        width = QFontMetricsF(self._label_font).horizontalAdvance(name) + 24
        self.setFixedSize(round(max(152, width)), 116)  # (still six to a row)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(f"{name} - click to use it")
        self.setStyleSheet("background: transparent; border: none; padding: 0;")
        self.setAttribute(Qt.WA_Hover)

    def enterEvent(self, event):
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):
        from PySide6.QtGui import QPainter, QPen, QFontMetricsF
        from PySide6.QtCore import QRectF
        from . import look
        from .preview_place import Drawer
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(1, 1, self.width() - 2, self.height() - 2)
        if self.settings is not None:
            look.paint_tile(p, r, self.settings, chosen=self.current, hover=self.underMouse(),
                            focus=self.current and self.hasFocus())
        d = Drawer(self.settings, theme=self.preset)
        fm = QFontMetricsF(self._label_font)
        art = QRectF(r.left() + 12, r.top() + 10, r.width() - 24, r.height() - fm.height() - 24)
        h = art.height()
        pw, vw = h * 1.05, h * 0.62
        x = art.center().x() - (pw + 3 + vw) / 2
        pick, prev = QRectF(x, art.top(), pw, h), QRectF(x + pw + 3, art.top(), vw, h)
        d.picker(p, pick, 4, rows=4)
        d.preview(p, prev, 4)
        p.setPen(QPen(d.edge, 1))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(pick, 4, 4)
        p.drawRoundedRect(prev, 4, 4)
        text = QColor(self.settings.theme["picker_text"]) if self.settings is not None else self.palette().color(self.foregroundRole())
        if not self.current:
            text.setAlphaF(0.75)
        p.setPen(text)
        p.setFont(self._label_font)
        p.drawText(QRectF(r.left() + 4, r.bottom() - fm.height() - 10, r.width() - 8, fm.height() + 4), Qt.AlignCenter,
                   self.name)
        p.end()


class ColorSwatchButton(QPushButton):
    """A small colour chip with its hex code beside it - click to change."""
    colorChanged = Signal(str)

    def __init__(self, hex_color, parent=None, show_hex=True):
        super().__init__(parent)
        self._hex = hex_color
        self._show_hex = show_hex
        self.setFixedSize(108 if show_hex else 34, 28)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setStyleSheet("background: transparent; border: none; padding: 0;")
        self.clicked.connect(self._pick)

    def _refresh(self):
        self.update()

    def paintEvent(self, event):
        from PySide6.QtGui import QPainter, QPen
        from PySide6.QtCore import QRectF
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        chip = QRectF(1.5, 4.5, 30, self.height() - 9)
        p.setPen(QPen(QColor(255, 255, 255, 40) if QColor(self._hex).lightness() < 60 else QColor(0, 0, 0, 50), 1))
        p.setBrush(QColor(self._hex))
        p.drawRoundedRect(chip, 5, 5)
        p.setPen(self.palette().color(self.foregroundRole()) if not self.underMouse() else QColor(self._hex).lighter(130))
        if self._show_hex:
            p.drawText(QRectF(chip.right() + 10, 0, self.width() - chip.right() - 10, self.height()),
                       Qt.AlignLeft | Qt.AlignVCenter, self._hex.lower())
        if self.hasFocus():
            p.setPen(QPen(QColor(self._hex), 1.2))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(chip.adjusted(-1.5, -1.5, 1.5, 1.5), 6, 6)
        p.end()

    def _pick(self):
        color = QColorDialog.getColor(QColor(self._hex), self, "Choose color")
        if color.isValid():
            self._hex = color.name()
            self._refresh()
            self.colorChanged.emit(self._hex)


class _UpdateBridge(QObject):
    done = Signal(object)  # the newest release (dict), or {} when up to date / unknown


# Namespaces of Settings that are spread over two pages: which keys are on which (for "Reset page")
_SOUND_KEYS = ("split_music", "show_bpm", "guess_energy", "show_beat_grid", "trim_silence", "music_min_seconds", "auto_analyse")
_PREVIEW_KEYS = tuple(k for k in LISTEN_DEFAULTS if k not in _SOUND_KEYS)
_FUSION_KEYS = ("tidy_after_insert", "expression_ask", "expression_sliders")
_SCRIPT_KEYS = ("adj_clip_name", "adj_fixed_frames", "comp_clip_name", "comp_fixed_frames", "tidy_style",
                "tidy_fit_view", "step_back_frames", "step_forward_frames", "voice_mic", "voice_start",
                "voice_mute", "voice_trim")
_TIMELINE_KEYS = tuple(k for k in TIMELINE_TOOLS_DEFAULTS if k not in _FUSION_KEYS + _SCRIPT_KEYS)
_GRAB_KEYS = ("grabs_on_timeline", "grabs_folder", "voice_folder")


class _NavDelegate(QStyledItemDelegate):
    """The sidebar's rows - and the thin line between its groups (an item marked "line")."""

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings

    def paint(self, painter, option, index):
        if index.data(Qt.UserRole) != "line":
            return super().paint(painter, option, index)
        r = option.rect
        y = r.center().y() + 0.5
        painter.save()
        painter.setPen(QPen(QColor(self.settings.theme["picker_border"]), 1))
        painter.drawLine(QPointF(r.left() + 8, y), QPointF(r.right() - 8, y))
        painter.restore()


class SettingsDialog(QDialog):
    settingsChanged = Signal()
    sound_analyser = None  # the picker's SoundAnalyser (Analyse sounds button)
    picker_place_reset = None  # the picker's "back to the middle, automatic size"

    # Where a setting lives - one page per question, and a setting on one page only:
    PAGE_ABOUT = {
        "General": "What the list shows, searching, inserting, start-up",
        "Preview": "The preview window and the clip info under it",
        "Sound": "Music, sound effects and BPM",
        "Timeline": "Titles and subtitles",
        "Organise": "Project templates: their bins, where clips go and their colours",
        "Fusion": "Tidying after inserts, and expressions",
        "Scripts": "What the scripts in Resolve's menu do",
        "Appearance": "Theme, colours, text size, the window",
        "Keybindings": "Every key that works while the picker is open",
        "Folders": "Where scripts, macros and compositions are looked for",
        "Search Prefixes": "The letters that search one kind of thing (a:, macro: ...)",
        "About": "Version, updates, backup, reporting a problem",
    }
    # page -> what its "Reset page" button clears: a whole namespace of Settings, or (namespace, its keys
    # on this page) where a namespace is spread over pages. A page resets what it shows, nothing else.
    TAB_NAMESPACES = {
        "General": ["general", "page_defaults"],
        "Preview": [("listen", _PREVIEW_KEYS)],
        "Sound": [("listen", _SOUND_KEYS)],
        "Timeline": [("timeline_tools", _TIMELINE_KEYS)],
        "Fusion": [("timeline_tools", _FUSION_KEYS)],
        "Scripts": [("timeline_tools", _SCRIPT_KEYS), ("files", _GRAB_KEYS)],
        "Appearance": ["theme", "display", "icons"],
        "Keybindings": ["keybinds", "keybinds_secondary"],
        "Folders": ["folders", ("files", ("file_manager", "max_windows"))],
        "Search Prefixes": ["prefixes"]}
    # (title, sidebar icon, builder name)
    # as Vicinae's sidebar (2026-10-21, the owner: "their look a little more profeesional"): the app's own pages first,
    # plain grey symbols; then the ones with a colour, each on its small square (settings_cards.nav_tile)
    PAGES = [("General", "general", "_build_general_tab"), ("Appearance", "appearance", "_build_appearance_tab"),
             ("Keybindings", "keys", "_build_keybindings_tab"), ("About", "about", "_build_about_tab"),
             ("Preview", "preview", "_build_preview_tab"), ("Sound", "sound", "_build_sound_tab"),
             ("Timeline", "timeline", "_build_timeline_tab"), ("Organise", "organise", "_build_organise_tab"),
             ("Fusion", "fusion", "_build_fusion_tab"),
             ("Scripts", "scripts", "_build_scripts_tab"), ("Folders", "folders", "_build_folders_tab"),
             ("Search Prefixes", "prefixes", "_build_prefixes_tab")]
    START = [title for title, _i, _b in PAGES].index("General")  # where Settings opens when no page is asked for
    # the sidebar's groups, a thin line between them (like Vicinae's): after these pages
    NAV_BREAKS = ("About",)

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.setObjectName("AppDialog")
        self.setWindowTitle("Settings")
        if sys.platform == "win32":  # (the picker stays on top: without it too Settings opened behind it on Windows)
            self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        from .theme import settings_sheet
        self.setFont(font_at(rel(settings, "settings")))  # (its own zoom - for what's drawn by hand)
        self.setStyleSheet(settings_sheet(settings))  # (...and every label and field, at its zoom)
        # Settings' own text follows a size change once the change stops (a slider dragged, a number typed): every
        # restyle of it is ~0.4 s with all its pages built, and it ran on each step of the UI scale
        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.setInterval(250)
        self._resize_timer.timeout.connect(self._resize_text)
        self.settingsChanged.connect(self._resize_timer.start)
        self.next_action = None  # set to "insert_options" by Alt+Right — picker_window chains into it

        # Layout:  sidebar | back / forward, the page's title, "Reset page" / the page. No OK: a change is in use at once,
        # and closing saves it (done)
        self.tabs = QTabWidget(self)
        self.tabs.setObjectName("SettingsPages")
        self.tabs.tabBar().hide()  # the sidebar does the switching
        self._build_tabs(current=self.START)
        self.tabs.currentChanged.connect(self._update_tab_sizing)

        from .settings_cards import nav_icon
        self.nav = QListWidget()
        self.nav.setObjectName("SettingsNav")
        self.nav.setFocusPolicy(Qt.NoFocus)
        self.nav.setIconSize(QSize(18, 18))
        muted = self.settings.theme["picker_folder"]
        from .settings_cards import nav_color, nav_tile
        for title, icon, _builder in self.PAGES:  # (a coloured one on its small square, the app's own plain)
            color = nav_color(icon)
            self.nav.addItem(QListWidgetItem(nav_tile(icon, color) if color else nav_icon(icon, muted), title))
            if title in self.NAV_BREAKS:  # a thin line before the next group
                gap = QListWidgetItem("")
                gap.setFlags(Qt.NoItemFlags)
                gap.setSizeHint(QSize(10, 17))
                gap.setData(Qt.UserRole, "line")
                self.nav.addItem(gap)
        self.nav.setItemDelegate(_NavDelegate(self.settings, self.nav))
        self.nav.currentRowChanged.connect(self._nav_changed)

        # search: finds any setting on any page
        self.search = QLineEdit()
        self.search.setObjectName("SettingsSearch")
        self.search.setPlaceholderText("Search...")
        self.search.setClearButtonEnabled(True)
        self.search.addAction(nav_icon("search", muted, 15), QLineEdit.LeadingPosition)
        self.search.textChanged.connect(self._search_changed)
        self.search.returnPressed.connect(self._open_first_result)
        sidebar = QWidget()
        sidebar.setObjectName("SettingsSidebar")
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(12, 14, 12, 12)
        side.setSpacing(10)
        side.addWidget(self.search)
        side.addWidget(self.nav, 1)
        # (at its foot: Restart and Quit - 2026-10-19, also actions in the picker)
        foot = QHBoxLayout()
        foot.setSpacing(6)
        for text, glyph, tip, slot in (
                ("Restart", "restart", "Stops Clipse and starts it again", self._restart_service),
                ("Quit", "power", "Stops Clipse until you next use it", self._quit_service)):
            b = QPushButton(text)
            b.setObjectName("QuietButton")
            b.setIcon(nav_icon(glyph, muted, 14))
            b.setFocusPolicy(Qt.NoFocus)
            b.setAutoDefault(False)
            b.setToolTip(tip)
            b.clicked.connect(slot)
            foot.addWidget(b, 1)
        side.addLayout(foot)
        sidebar.setFixedWidth(max(210, self.nav.sizeHintForColumn(0) + 60))

        # back / forward through the pages you've been on
        self._history, self._history_at = [self.START], 0
        # (one soft pill with both arrows in it, a hairline between them - Vicinae's)
        self.back_btn = QPushButton("\u2039")
        self.fwd_btn = QPushButton("\u203a")
        pill = QFrame()
        pill.setObjectName("NavPill")
        pill_box = QHBoxLayout(pill)
        pill_box.setContentsMargins(0, 0, 0, 0)
        pill_box.setSpacing(0)
        for n, (b, tip) in enumerate(((self.back_btn, "Back"), (self.fwd_btn, "Forward"))):
            b.setObjectName("NavArrow")
            b.setToolTip(tip)
            b.setFixedSize(34, 30)
            b.setFocusPolicy(Qt.NoFocus)
            if n:
                cut = QFrame()
                cut.setObjectName("SettingsHairline")
                cut.setFixedSize(1, 16)
                pill_box.addWidget(cut, 0, Qt.AlignVCenter)
            pill_box.addWidget(b)
        self.back_btn.clicked.connect(lambda: self._step_history(-1))
        self.fwd_btn.clicked.connect(lambda: self._step_history(1))
        self.page_title = QLabel(self.PAGES[self.START][0])
        self.page_title.setObjectName("SettingsTitle")
        self.reset_tab_btn = QPushButton("Reset page")
        self.reset_tab_btn.setObjectName("QuietButton")
        self.reset_tab_btn.setFocusPolicy(Qt.NoFocus)
        self.reset_tab_btn.setToolTip("Reset every setting on this page to default")
        self.reset_tab_btn.clicked.connect(self._reset_current_tab)
        header = QHBoxLayout()
        header.setSpacing(4)
        header.addWidget(pill)
        header.addSpacing(12)
        header.addWidget(self.page_title)
        header.addStretch()
        header.addWidget(self.reset_tab_btn)

        # search results take the page's place while there's a search
        self.results = QScrollArea()
        self.results.setObjectName("SettingsScroll")
        self.results.setWidgetResizable(True)
        self.results.setFrameShape(QFrame.NoFrame)
        self.results.hide()

        content = QVBoxLayout()
        content.setContentsMargins(18, 14, 18, 0)
        content.setSpacing(12)
        content.addLayout(header)
        content.addWidget(self.tabs, 1)
        content.addWidget(self.results, 1)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(sidebar)
        layout.addLayout(content, 1)
        self.tabs.setCurrentIndex(self.START)
        self._select_nav(self.START)
        self._update_history_buttons()
        self._update_tab_sizing(self.START)
        restrict_tab_to_inputs(self)

    # -- pages, the sidebar and back / forward --
    def _nav_row_to_page(self, row):
        item = self.nav.item(row)
        if item is None or not item.text():
            return None
        titles = [t for t, _i, _b in self.PAGES]
        return titles.index(item.text()) if item.text() in titles else None

    def _select_nav(self, page):
        title = self.PAGES[page][0]
        for row in range(self.nav.count()):
            if self.nav.item(row).text() == title:
                self.nav.blockSignals(True)
                self.nav.setCurrentRow(row)
                self.nav.blockSignals(False)
                return

    def _nav_changed(self, row):
        page = self._nav_row_to_page(row)
        if page is not None:
            self._show_page(page)

    def _show_page(self, index, remember=True):
        if index is None or index < 0:
            return
        if self.search.text():
            self.search.blockSignals(True)
            self.search.clear()
            self.search.blockSignals(False)
            self._search_changed("")
        self._ensure_page(index)
        self.tabs.setCurrentIndex(index)
        self.page_title.setText(self.PAGES[index][0])
        self.reset_tab_btn.setVisible(self.PAGES[index][0] in self.TAB_NAMESPACES)
        self._select_nav(index)
        if remember and self._history[self._history_at] != index:
            self._history = self._history[:self._history_at + 1] + [index]
            self._history_at = len(self._history) - 1
        self._update_history_buttons()

    def _step_history(self, step):
        target = self._history_at + step
        if 0 <= target < len(self._history):
            self._history_at = target
            self._show_page(self._history[target], remember=False)

    def _update_history_buttons(self):
        if hasattr(self, "back_btn"):
            self.back_btn.setEnabled(self._history_at > 0)
            self.fwd_btn.setEnabled(self._history_at < len(self._history) - 1)

    # -- search --
    def _search_changed(self, text):
        from .settings_cards import Card
        text = text.strip().lower()
        if not text:
            self.results.hide()
            self.tabs.show()
            self.page_title.setText(self.PAGES[self.tabs.currentIndex()][0])
            self.reset_tab_btn.setVisible(self.PAGES[self.tabs.currentIndex()][0] in self.TAB_NAMESPACES)
            self._select_nav(self.tabs.currentIndex())
            return
        self.nav.blockSignals(True)
        self.nav.setCurrentRow(-1)
        self.nav.blockSignals(False)
        self.reset_tab_btn.hide()
        self._build_rest(all_now=True)
        words = text.split()
        hits = []
        for page, row in self._search_rows:
            hay = f"{row.search_text()} {getattr(row, 'section_title', '')} {self.PAGES[page][0]}".lower()
            if all(w in hay for w in words):
                hits.append((page, row))
        page_widget = QWidget()
        page_widget.setObjectName("SettingsPage")
        v = QVBoxLayout(page_widget)
        v.setContentsMargins(0, 0, 6, 0)
        self._results_list = hits
        if hits:
            card = Card(self.settings)
            for page, row in hits[:60]:
                card.add(self._result_row(page, row))
            v.addWidget(card)
        else:
            empty = QLabel("No setting matches that.")
            empty.setStyleSheet(f"color: {self.settings.theme['picker_folder']};")
            v.addWidget(empty)
        v.addStretch()
        self.results.setWidget(page_widget)
        self.tabs.hide()
        self.results.show()
        self.page_title.setText(f"{len(hits)} result{'s' if len(hits) != 1 else ''}")

    def _result_row(self, page, row):
        muted = self.settings.theme["picker_folder"]
        title = row.title_widget.text() if hasattr(row, "title_widget") and isinstance(row.title_widget, QLabel) \
            else (row.search_text()[:60] or "Setting")
        where = self.PAGES[page][0] + (f"  \u203a  {row.section_title}" if getattr(row, "section_title", "") else "")
        button = QPushButton()
        button.setObjectName("SearchResult")
        button.setCursor(Qt.PointingHandCursor)
        lay = QVBoxLayout(button)
        lay.setContentsMargins(16, 10, 16, 10)
        lay.setSpacing(2)
        name = QLabel(title.replace("&&", "&"))
        place = QLabel(where)
        place.setStyleSheet(f"color: {muted};")
        for lbl in (name, place):
            lbl.setAttribute(Qt.WA_TransparentForMouseEvents)
            lay.addWidget(lbl)
        button.setMinimumHeight(name.sizeHint().height() + place.sizeHint().height() + 24)
        button.clicked.connect(lambda: self._go_to_row(page, row))
        return button

    def _open_first_result(self):
        hits = getattr(self, "_results_list", [])
        if self.search.text().strip() and hits:
            self._go_to_row(*hits[0])

    def go_to_key(self, name):
        """Keybindings, scrolled to the key `name` and its row lit for a moment - what right-click > Change key on
        an action opens. Only lit: changing it is a click on its box ("dont do that for me")."""
        index = next((i for i, (title, *_rest) in enumerate(self.PAGES) if title == "Keybindings"), None)
        if index is None:
            return
        self._show_page(index)
        field = getattr(self, "_key_fields", {}).get(name)
        if field is None:
            return
        self._light_up(index, field)

    def go_to_field(self, index, names):
        """Settings on page `index` (their fields kept in _fields by name - one, or several), scrolled to and lit. On
        Scripts, the script they belong to is chosen first."""
        names = (names,) if isinstance(names, str) else names
        owner = {"step_back_frames": "Step Back", "step_forward_frames": "Step Forward"}
        if getattr(self, "_script_table", None) is not None and names and names[0] in owner:
            self._script_table.select(owner[names[0]])
        for name in names:
            field = getattr(self, "_fields", {}).get(name)
            if field is not None:
                self._light_up(index, field)

    def _light_up(self, index, field):
        row = field
        while row is not None and row.objectName() != "SettingRow":
            row = row.parentWidget()
        row = row or field
        self._flash(row)
        area = self.tabs.widget(index)

        def show():  # a third of the way down - not squeezed against the bottom edge
            if isinstance(area, QScrollArea) and area.widget() is not None:
                from PySide6.QtCore import QPoint
                top = row.mapTo(area.widget(), QPoint(0, 0)).y()
                area.verticalScrollBar().setValue(max(0, top - area.viewport().height() // 3))
        QTimer.singleShot(0, show)

    def _go_to_row(self, page, row):
        self._show_page(page)
        area = self.tabs.widget(page)
        if isinstance(area, QScrollArea):
            QTimer.singleShot(0, lambda: area.ensureWidgetVisible(row, 0, 80))
        self._flash(row)

    def _flash(self, row):
        """The setting you came for lights up: a soft wash of the accent with an edge, held a moment, then
        fading (a found setting, a key opened from an Actions tile)."""
        from PySide6.QtCore import QVariantAnimation
        accent = QColor(self.settings.theme.get("picker_accent", self.settings.theme["picker_text"]))
        row.setAttribute(Qt.WA_StyledBackground, True)  # (a plain QWidget draws no stylesheet background without it)
        anim = QVariantAnimation(row)
        anim.setDuration(2600)
        anim.setStartValue(1.0)
        anim.setKeyValueAt(0.55, 1.0)  # held while you find it...
        anim.setEndValue(0.0)          # ...then gone

        def paint(v):
            v = float(v)
            row.setStyleSheet(f"QWidget#SettingRow {{ background: rgba({accent.red()},{accent.green()},{accent.blue()},"
                              f"{0.16 * v:.3f}); border: 1px solid rgba({accent.red()},{accent.green()},{accent.blue()},"
                              f"{0.55 * v:.3f}); border-radius: 8px; }}")
        anim.valueChanged.connect(paint)
        anim.finished.connect(lambda: row.setStyleSheet(""))
        paint(1.0)  # (lit at once: while it's held the value doesn't change, so nothing would be said)
        anim.start()

    def showEvent(self, event):
        # The picker is an always-on-top tool window; explicitly activating
        # the dialog makes sure typing goes into its fields (Wayland
        # compositors don't always hand focus to a child dialog by itself).
        super().showEvent(event)
        self.raise_()
        self.activateWindow()
        if not getattr(self, "_rest_scheduled", False):  # the other pages, a moment later
            self._rest_scheduled = True
            QTimer.singleShot(400, self._build_rest)

    def keyPressEvent(self, event):
        combo = QKeySequence(event.keyCombination()).toString(QKeySequence.PortableText)
        if combo == QKeySequence("Alt+Right").toString(QKeySequence.PortableText):
            self.next_action = "insert_options"
            self.accept()
            return
        from .fonts import zoom_key
        direction = zoom_key(event, self.settings)
        if direction is not None:
            self.zoom_window(direction)
            return
        super().keyPressEvent(event)

    def zoom_window(self, direction):
        """Ctrl and + / - / 0, or Ctrl + the wheel: Settings by itself larger, smaller, as it ships."""
        from .fonts import step_zoom
        step_zoom(self.settings, "settings", direction)
        self.settings.save()
        self._rebuild_after_resize = True  # (the tiles and drawings take their size when they're made)
        self._resize_timer.start()  # (once the keys stop: a restyle and a rebuild per press lagged)

    def done(self, result):
        """However Settings closes (Esc, the window's close button, Alt+Right): what's changed is saved."""
        self.settings.save()
        super().done(result)

    # -- rebuilding (used after any reset, so every widget re-reads the
    # current settings value instead of needing individual sync code) --
    def _build_tabs(self, current=0):
        """Pages are built when they're first needed - the one you open
        straight away, the rest a moment later, one at a time, so Settings
        opens at once instead of building eleven pages first."""
        self._search_rows = []
        self._built = set()
        for title, _icon, _builder in self.PAGES:
            self.tabs.addTab(self._scrolled(None), title)
        self._ensure_page(current)

    def _ensure_page(self, index):
        if index in self._built or not 0 <= index < len(self.PAGES):
            return
        from .settings_cards import cardify
        self._built.add(index)
        title, _icon, builder = self.PAGES[index]
        page = getattr(self, builder)()
        _align_forms(page)  # field widths (labels now sit in the cards' rows)
        rows = cardify(page, self.settings)
        from .settings_cards import Section
        for section in page.findChildren(Section):  # pages built from cards directly (Scripts)
            for row in section.card.rows:
                if row not in rows and hasattr(row, "search_text"):
                    row.section_title = section.title
                    rows.append(row)
        for row in rows:
            self._search_rows.append((index, row))
        self._search_rows.sort(key=lambda pr: pr[0])
        restrict_tab_to_inputs(page)
        self.tabs.widget(index).setWidget(page)

    def _build_rest(self, all_now=False):
        """Builds the pages not built yet - one per moment, or all at once (a search needs them)."""
        for index in range(len(self.PAGES)):
            if index not in self._built:
                self._ensure_page(index)
                if not all_now:
                    QTimer.singleShot(30, self._build_rest)
                    return

    def _scrolled(self, page):
        """Each page scrolls when it's taller than the screen allows."""
        area = QScrollArea()
        area.setObjectName("SettingsScroll")
        if page is not None:
            area.setWidget(page)
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.NoFrame)
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        area.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)  # (a thin bar while it scrolls instead, Vicinae's)
        from .scroll_hint import ScrollHint
        area.scroll_hint = ScrollHint(area, self.settings)
        return area

    def _rebuild(self, restyle=None):
        """Every page made again. restyle (Settings' text size changed): done once the old pages are gone - restyled
        first, every page was given the new size and then thrown away (2026-10-22: "so laggy when zooming")."""
        idx = self.tabs.currentIndex()
        # (a reset rebuilds every page: the one you're on stays scrolled where it was, not back at its top)
        area = self.tabs.widget(idx)
        scrolled = area.verticalScrollBar().value() if hasattr(area, "verticalScrollBar") else 0
        self.tabs.blockSignals(True)
        while self.tabs.count():
            widget = self.tabs.widget(0)
            self.tabs.removeTab(0)
            if restyle is not None:  # (from a timer, never from a click inside the page: gone at once)
                from shiboken6 import delete
                delete(widget)
            else:
                widget.deleteLater()
        if restyle is not None:
            restyle()
        self._build_tabs(current=max(0, idx))
        self.tabs.setCurrentIndex(max(0, idx))
        self.tabs.blockSignals(False)
        if self.isVisible():
            QTimer.singleShot(400, self._build_rest)
        self._update_tab_sizing(max(0, idx))
        restrict_tab_to_inputs(self)
        if scrolled:
            self._keep_scrolled(max(0, idx), scrolled)

    def _keep_scrolled(self, index, value):
        area = self.tabs.widget(index)
        if not hasattr(area, "verticalScrollBar"):
            return
        if area.widget() is not None:
            area.widget().adjustSize()  # (its height now, so the bar reaches as far as before)
        area.verticalScrollBar().setValue(value)
        QTimer.singleShot(0, lambda: self.tabs.widget(index) is area and area.verticalScrollBar().setValue(value))

    def _update_tab_sizing(self, index):
        """One steady size for every page - switching pages never moves or
        resizes the window. Pages that are longer scroll. The size fits the
        widest page (within the screen), and if you resize Settings it
        opens at that size next time."""
        for i in range(self.tabs.count()):
            area = self.tabs.widget(i)
            if area is None:
                continue
            policy = QSizePolicy.Preferred if i == index else QSizePolicy.Ignored
            area.setSizePolicy(policy, policy)
            area.setMinimumSize(0, 0)
        if getattr(self, "_sized", False):
            return
        self._sized = True
        screen = (self.screen() or QApplication.primaryScreen()).availableGeometry()
        widths = [self.tabs.widget(i).widget().sizeHint().width() for i in range(self.tabs.count())
                  if isinstance(self.tabs.widget(i), QScrollArea) and self.tabs.widget(i).widget() is not None]
        nav = self.nav.width() if hasattr(self, "nav") else 160
        width = min(max(widths + [760]) + 60 + nav, int(screen.width() * 0.85))
        height = min(max(560, int(screen.height() * 0.72)), 760)
        saved = self.settings.display.get("settings_size") or []
        if len(saved) == 2:
            width = max(640, min(int(saved[0]), screen.width()))
            height = max(420, min(int(saved[1]), screen.height()))
        self.resize(width, height)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if getattr(self, "_sized", False) and self.isVisible():
            self.settings.display["settings_size"] = [self.width(), self.height()]

    def _reset_current_tab(self):
        for entry in self.TAB_NAMESPACES.get(self.PAGES[self.tabs.currentIndex()][0], []):
            if isinstance(entry, str):
                self.settings.reset_namespace(entry)
            else:
                namespace, keys = entry
                for key in keys:
                    self.settings.reset_key(namespace, key)
        self._rebuild()
        self.settingsChanged.emit()

    def _slider(self, namespace, key, low, high, step, suffix, apply):
        """A setting that is a range, as the app's slider (slider.py) - its number beside it, to drag or type."""
        from .slider import Slider
        from .settings import NAMESPACE_DEFAULTS
        default = NAMESPACE_DEFAULTS.get(namespace, {}).get(key, low)
        slider = Slider(self.settings, low, high, getattr(self.settings, namespace)[key], suffix, step,
                        default=default, width=300)
        slider.box.reset_action = lambda: self._reset_field(namespace, key)
        slider.changed.connect(apply)
        return slider

    def _draggable(self, box, label, namespace, key):
        """A number field like every other: drag it or its name, type into it, and a reset arrow in its
        corner while it isn't its default (double-clicking the name does the same)."""
        from .settings import NAMESPACE_DEFAULTS
        default = NAMESPACE_DEFAULTS.get(namespace, {}).get(key)
        if isinstance(default, (int, float)) and not isinstance(default, bool) and hasattr(box, "scrub_from"):
            box.default_value = default
            box.reset_action = lambda: self._reset_field(namespace, key)
            box.scrub_from(label)

    def _reset_field(self, namespace, key):
        self.settings.reset_key(namespace, key)
        self._rebuild()
        self.settingsChanged.emit()

    # -- Updates & Help --
    def _build_about_tab(self):
        """Who and what: the mark, the version, and the few things you'd come
        here for - updates, the docs, reporting a problem, the checks."""
        from . import updater
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtCore import QUrl
        from .glyphs import glyph_icon
        t = self.settings.theme
        muted = t["picker_folder"]
        page = QWidget()
        page.setObjectName("SettingsPage")
        layout = QVBoxLayout(page)
        layout.setSpacing(0)
        layout.addSpacing(26)
        layout.addWidget(_AppMark(self.settings), 0, Qt.AlignHCenter)
        layout.addSpacing(14)
        name = QLabel("Clipse")
        name.setObjectName("AboutTitle")
        name.setAlignment(Qt.AlignHCenter)
        layout.addWidget(name)
        layout.addSpacing(8)
        tagline = QLabel("A quick search for DaVinci Resolve")
        tagline.setAlignment(Qt.AlignHCenter)
        tagline.setWordWrap(True)
        layout.addWidget(tagline)
        layout.addSpacing(8)
        self.version_label = QLabel(f"Version {updater.installed_version()}")
        self.version_label.setAlignment(Qt.AlignHCenter)
        self.version_label.setStyleSheet(f"color: {muted};")
        layout.addWidget(self.version_label)
        layout.addSpacing(2)
        self.update_status = QLabel("")  # (what a button did: a report made, a computer freed ...)
        self.update_status.setWordWrap(True)
        self.update_status.setOpenExternalLinks(True)
        self.update_status.setAlignment(Qt.AlignHCenter)
        self.update_status.setStyleSheet(f"color: {muted};")
        self.update_status.hide()
        layout.addSpacing(4)
        layout.addWidget(self.update_status)
        layout.addSpacing(22)

        buttons = QVBoxLayout()
        buttons.setSpacing(8)

        def button(text, glyph, slot, tip=""):
            b = QPushButton(text)
            b.setObjectName("AboutButton")
            b.setIcon(glyph_icon(glyph, t["picker_text"], 15))
            b.setIconSize(QSize(15, 15))
            b.setFixedSize(220, 36)
            b.setCursor(Qt.PointingHandCursor)
            b.setAutoDefault(False)
            if tip:
                b.setToolTip(tip)
            b.clicked.connect(slot)
            buttons.addWidget(b, 0, Qt.AlignHCenter)
            return b
        self.update_button = button("Update", "save", self._start_update)  # (only when one is out)
        self.update_button.hide()
        button("Documentation", "book", lambda: QDesktopServices.openUrl(QUrl("https://alnor.store/docs.html")))
        button("Source code", "scripts", lambda: QDesktopServices.openUrl(QUrl("https://github.com/alnor0/clipse")),
               "Free under the GPL-3.0 license")
        button("Send feedback", "feedback", self._send_feedback, "A problem or an idea, with pictures if you like")
        from . import install
        if install.can_uninstall():  # (the installed AppImage, Clipse.app on a Mac: nothing else would take it away)
            button("Uninstall", "uninstall", self._uninstall,
                   "Takes Clipse off this computer: Resolve's scripts, starting at login, the app. Your "
                   "settings stay, for if it comes back.")
        layout.addLayout(buttons)
        layout.addSpacing(10)

        box = QGroupBox("Updates")
        v = QVBoxLayout(box)
        auto = ResettableCheckBox("Check for updates")
        auto.setChecked(self.settings.general["check_for_updates"])
        auto.toggled.connect(lambda checked: self._set_general("check_for_updates", checked))
        auto.doubleClicked.connect(lambda: self._reset_field("general", "check_for_updates"))
        v.addWidget(auto)
        row = QHBoxLayout()
        check = QPushButton("Check now")
        check.setToolTip("Asks alnor.store whether a newer Clipse is out. The answer is under the version.")
        check.clicked.connect(lambda: self._check_updates(force=True))
        row.addWidget(check)
        row.addStretch()
        v.addLayout(row)
        layout.addSpacing(8)
        layout.addWidget(box)
        privacy = QGroupBox("Privacy")
        v = QVBoxLayout(privacy)
        crashes = ResettableCheckBox("Send crash reports")  # (crash_report.py, 2026-10-22)
        crashes.setChecked(self.settings.general["send_crash_reports"])
        crashes.toggled.connect(lambda checked: self._set_general("send_crash_reports", checked))
        crashes.doubleClicked.connect(lambda: self._reset_field("general", "send_crash_reports"))
        v.addWidget(crashes)
        layout.addWidget(privacy)
        layout.addWidget(self._build_transfer_group())
        layout.addStretch()
        self._latest = None
        # (About is where people look: the answer of now, not the day's - unless checking is turned off)
        self._check_updates(force=self.settings.general["check_for_updates"])
        return page

    def _resize_text(self):
        """Font size, UI scale or Settings' zoom changed here: Settings' own text follows (once the change stops)."""
        from .theme import settings_sheet
        sheet = settings_sheet(self.settings)

        def restyle():
            if sheet != self.styleSheet():
                self.setFont(font_at(rel(self.settings, "settings")))
                self.setStyleSheet(sheet)
        if getattr(self, "_rebuild_after_resize", False):
            self._rebuild_after_resize = False
            self._rebuild(restyle=restyle)  # (the old pages gone first: only the new ones are styled)
        else:
            restyle()

    def _build_transfer_group(self):
        """Your setup as one file (transfer.py): everything in Settings, keys, presets, favourites, project templates
        and what it has learned - for another computer, or a backup (2026-10-19: one pair - it was settings and
        presets apart, and the settings folder)."""
        box = QGroupBox("Your setup")
        v = QVBoxLayout(box)
        self.transfer_status = QLabel("")
        self.transfer_status.setWordWrap(True)
        row = QHBoxLayout()
        save = QPushButton("Save to a file\u2026")
        save.setToolTip("Your settings, keys, presets, favourites, project templates and what Clipse has learned, "
                        "in one file - for another computer, or a backup. Folders and window positions stay with "
                        "each computer.")
        save.clicked.connect(lambda: self._export("settings"))
        load = QPushButton("Load from a file\u2026")
        load.setToolTip("Your setup from another computer, or a backup: Settings become what the file says, and "
                        "its favourites, templates and what it learned are added to yours.")
        load.clicked.connect(lambda: self._import("settings"))
        row.addWidget(save)
        row.addWidget(load)
        row.addStretch()
        v.addLayout(row)
        self.transfer_status.hide()  # until there's something to say
        v.addWidget(self.transfer_status)
        return box

    def _about_say(self, text):
        """A line under the version saying what a button did."""
        try:
            self.update_status.setText(text)
            self.update_status.setVisible(bool(text))
        except RuntimeError:
            pass  # (the page was rebuilt meanwhile)

    def _update_in_place(self, latest):
        """The new version downloaded and put in place (in the background - self_update), then started: it takes
        over from this service (client.open_app; on Windows the installer) and the picker says "Updated"."""
        import threading
        from . import self_update
        self.update_button.setEnabled(False)
        self._about_say(f"Downloading {latest['version']}\u2026")
        bridge = _UpdateBridge(self)

        def finished(answer):
            if answer.get("error"):
                accent = self.settings.theme.get("picker_accent", self.settings.theme["picker_text"])
                self._about_say(f"Couldn't update: {answer['error']} \u00b7 <a style='color:{accent}; "
                                f"text-decoration:none' href='{latest.get('page_url')}'>Download it</a>")
                try:
                    self.update_button.setEnabled(True)
                except RuntimeError:
                    pass
                return
            self._about_say(f"Opening {latest['version']}\u2026")
            self_update.finish(answer["ready"])
        bridge.done.connect(finished)

        def work():
            try:
                bridge.done.emit({"ready": self_update.prepare(latest)})
            except Exception as e:
                bridge.done.emit({"error": str(e)})
        threading.Thread(target=work, daemon=True).start()
        self._update_bridge = bridge

    def _uninstall(self):
        from PySide6.QtWidgets import QApplication, QMessageBox
        from . import install
        if QMessageBox.question(self, "Uninstall", "Take Clipse off this computer?") != QMessageBox.Yes:
            return
        left = install.uninstall()
        if left:
            self._about_say(f"Not all of it went - {left}")
            return
        QApplication.quit()  # (the service ends: nothing of it is left to start again)

    def _restart_service(self):
        from .launch import restart_service
        self.done(0)  # (saves)
        restart_service()

    def _quit_service(self):
        self.done(0)
        QApplication.quit()

    def _send_feedback(self):
        from .feedback_dialog import FeedbackDialog
        dialog = FeedbackDialog(self.settings, self)
        dialog.exec()
        dialog.deleteLater()
        self.settings.save()  # (the email, for next time)

    def _transfer_say(self, text):
        self.transfer_status.setText(text)
        self.transfer_status.show()

    def _export(self, kind):
        import os
        from . import transfer
        import time
        name = f"Clipse setup {time.strftime('%Y-%m-%d')}.json" if kind == "settings" else f"Clipse {kind}.json"
        start = os.path.join(os.path.expanduser("~"), name)
        path, _filter = QFileDialog.getSaveFileName(self, "Save your setup" if kind == "settings" else f"Export {kind}",
                                                    start, "Clipse file (*.json)")
        if not path:
            return
        if not path.lower().endswith(".json"):
            path += ".json"
        try:
            if kind == "settings":
                transfer.export_settings(self.settings, path)
                self._transfer_say(f"Saved to {path}")
            else:
                n = transfer.export_presets(self.settings, path)
                self._transfer_say(f"{n} preset{'s' if n != 1 else ''} saved to {path}" if n else
                                             f"Saved to {path} - with no presets in it: you haven't made or "
                                             f"changed any yet.")
        except OSError as e:
            self._transfer_say(f"Couldn't save the file: {e}")

    def _import(self, kind):
        import os
        from PySide6.QtWidgets import QMessageBox
        from . import transfer
        path, _filter = QFileDialog.getOpenFileName(self, "Load a setup" if kind == "settings" else f"Import {kind}",
                                                    os.path.expanduser("~"), "Clipse file (*.json)")
        if not path:
            return
        if kind == "settings":
            try:  # (a file of presets only - from before there was one setup file - adds its presets)
                kind = transfer.kind_of(path)
            except transfer.NotOurs as e:
                self._transfer_say(str(e))
                return
        if kind == "settings" and QMessageBox.question(
                self, "Load a setup", "Everything in Settings becomes what this file says. Its favourites, "
                "templates and what it learned are added to yours.\n\nFolders and window positions on this "
                "computer stay as they are.\n\nLoad it?") != QMessageBox.Yes:
            return
        try:
            message = (transfer.import_settings if kind == "settings" else transfer.import_presets)(self.settings, path)
        except transfer.NotOurs as e:
            self._transfer_say(str(e))
            return
        self.settingsChanged.emit()
        if kind == "settings":
            picker = self.parent()
            if hasattr(picker, "reload_yours"):  # (favourites and what it learned, read again)
                picker.reload_yours()
            self._rebuild()  # every page shows the new values (this makes a new status line, too)
        self._transfer_say(message)

    def _check_updates(self, force):
        """Asks in the background (a slow network never freezes Settings)."""
        import threading
        from . import updater
        if not force and not self.settings.general["check_for_updates"]:
            return
        self.version_label.setText(f"Version {updater.installed_version()} \u00b7 checking\u2026")
        bridge = _UpdateBridge(self)
        bridge.done.connect(self._show_update_result)

        def ask():
            latest = updater.check(force=force) or {}
            try:
                bridge.done.emit(latest)
            except RuntimeError:
                pass  # (Settings was closed meanwhile - its bridge went with it)
        threading.Thread(target=ask, daemon=True).start()
        self._bridge = bridge

    def _show_update_result(self, latest):
        from . import updater
        try:
            self.version_label.isVisible()
        except RuntimeError:
            return  # the page was rebuilt meanwhile
        self._latest = latest or None
        mine = f"Version {updater.installed_version()}"
        if latest:
            accent = self.settings.theme.get("picker_accent", self.settings.theme["picker_text"])
            link = (f" \u00b7 <a style='color:{accent}; text-decoration:none' href='{latest['page_url']}'>What's new</a>"
                    if latest.get("page_url") else "")
            self.version_label.setText(f"{mine} \u00b7 {latest['version']} is out{link}")
            self.version_label.setOpenExternalLinks(True)
            self.update_button.setText(f"Update to {latest['version']}")
            self.update_button.show()
        else:
            self.version_label.setText(f"{mine} \u00b7 couldn't check" if updater.last_check_failed()
                                       else f"{mine} \u00b7 up to date")
            self.update_button.hide()

    def _start_update(self):
        from PySide6.QtWidgets import QMessageBox
        from . import updater
        if not self._latest:
            return
        from . import self_update
        if self_update.can(self._latest):  # (the download put in place of this one, then opened)
            self._update_in_place(self._latest)
            return
        from .launch import COMPILED
        if COMPILED or not self._latest.get("zip_url"):  # (it installs with pip - the program is downloaded again)
            from PySide6.QtCore import QUrl
            from PySide6.QtGui import QDesktopServices
            QDesktopServices.openUrl(QUrl(self._latest.get("page_url") or updater.DOWNLOAD_PAGE))
            self._about_say(f"Download {self._latest['version']} and install it over this one.")
            return
        answer = QMessageBox.question(
            self, "Update Clipse",
            f"Update to {self._latest['version']}?\n\nClipse closes, updates in the background "
            f"(about a minute) and opens the picker again when it's done.")
        if answer != QMessageBox.Yes:
            return
        try:
            updater.start_update(self._latest["zip_url"])
        except Exception as e:
            self._about_say(f"Couldn't start the update: {e}")
            return
        self._about_say("Updating\u2026 the picker opens again when it's done.")
        self.update_button.setEnabled(False)

    def _build_general_tab(self):
        page = QWidget()
        page.setObjectName("SettingsPage")
        layout = QVBoxLayout(page)
        # what the list shows: one tile per kind of row, click to switch it on or off
        # Two questions, top to bottom, with the answer drawn above them:
        #  1. where do the rows come from when the picker opens (per page)?   -> page_defaults
        #  2. which kinds of Media Pool row are among them?                   -> general show_*
        from .settings import FUSION_SKIPS, LIST_TILES, SOURCE_TILES
        from .settings_cards import Card, FreeRow, PickerSketch, Section, ToggleTiles
        card = Card(self.settings)
        muted = f"color: {self.settings.theme['picker_folder']};"
        sketches = [PickerSketch(self.settings, "other", "Edit page"),
                    PickerSketch(self.settings, "fusion", "Fusion page")]

        def redraw(*_):
            for sketch in sketches:
                sketch.update()

        def heading(words, detail):
            label = QLabel(f"<b>{words}</b>&nbsp;&nbsp;<span style='{muted}'>{detail}</span>")
            label.setTextFormat(Qt.RichText)
            label.setWordWrap(True)
            return label

        holder = QWidget()
        hv = QVBoxLayout(holder)
        hv.setContentsMargins(0, 0, 0, 0)
        hv.setSpacing(10)
        # Each page: its drawing, where its rows come from, and which kinds of Media Pool row are among them
        sides = QHBoxLayout()
        sides.setSpacing(22)
        edit_kinds = list(LIST_TILES)
        fusion_kinds = [tile for tile in LIST_TILES if tile[0] not in FUSION_SKIPS]
        for sketch, page_key, kinds, values, set_kind in (
                (sketches[0], "other", edit_kinds, self.settings.general, self._set_general),
                (sketches[1], "fusion", fusion_kinds, self.settings.page_defaults["fusion"],
                 lambda key, on: self._set_page_default("fusion", key, on))):
            side = QVBoxLayout()
            side.setSpacing(8)
            side.addWidget(sketch)
            side.addWidget(heading("Sources", ""))
            sources = ToggleTiles(self.settings, SOURCE_TILES, self.settings.page_defaults[page_key], tile_w=102)
            sources.toggled.connect(lambda key, on, page=page_key: (self._set_page_default(page, key, on), redraw()))
            side.addWidget(sources)
            side.addWidget(heading("From the Media Pool", ""))
            tiles = ToggleTiles(self.settings, kinds, {k: bool(values.get(k)) for k, _l, _s in kinds}, tile_w=102)
            tiles.toggled.connect(lambda key, on, put=set_kind: (put(key, on), redraw()))
            side.addWidget(tiles)
            side.addStretch(1)
            sides.addLayout(side, 1)
        hv.addLayout(sides)
        card.add(FreeRow(holder))
        layout.addWidget(Section("What the list shows", card))
        for section_name, rows in GENERAL_SCHEMA:
            box = QGroupBox(section_name)
            box_layout = QVBoxLayout(box)
            for key, label, _track in rows:
                cb = ResettableCheckBox(label)
                cb.setChecked(self.settings.general[key])
                cb.toggled.connect(lambda checked, k=key: self._set_general(k, checked))
                cb.doubleClicked.connect(lambda k=key: self._reset_field("general", k))
                box_layout.addWidget(cb)
            layout.addWidget(box)
        layout.addWidget(self._build_search_group())
        layout.addStretch()
        return page

    def _page(self, *groups):
        page = QWidget()
        page.setObjectName("SettingsPage")
        layout = QVBoxLayout(page)
        for group in groups:
            layout.addWidget(group)
        layout.addStretch()
        return page

    def _build_preview_tab(self):
        return self._page(self._build_listen_group(), self._build_info_group())

    def _build_sound_tab(self):
        return self._page(self._build_music_group())

    def _build_timeline_tab(self):
        return self._page(self._build_title_group(), self._build_subtitles_group())

    def _build_organise_tab(self):  # (project templates and Organise project - organise_page.py)
        from .organise_page import OrganisePage
        self._organise_page = OrganisePage(self)
        return self._organise_page.build()

    def _build_fusion_tab(self):
        return self._page(self._build_nodes_group(), self._build_expressions_group())

    # -- Scripts (the owner picked "the f table" from samples, 2026-10-21): every script of Clipse's in a table
    # (scripts_page.ScriptTable), the chosen one described beside it with what it has to set and Key in Resolve, and
    # under that the scripts of yours --
    def _build_scripts_tab(self):
        from .scripts_page import ScriptTable
        from .settings_cards import Card, FreeRow, Section
        page = QWidget()
        page.setObjectName("SettingsPage")
        outer = QVBoxLayout(page)
        columns = QHBoxLayout()
        columns.setSpacing(14)
        outer.addLayout(columns)
        table = ScriptTable(self.settings, getattr(self, "_script_chosen", None))
        table.chosen.connect(self._show_script)
        self._script_table = table
        table_card = Card(self.settings)
        table_card.add(FreeRow(table))
        left = QVBoxLayout()
        left.addWidget(table_card)
        left.addStretch()
        right = QVBoxLayout()
        right.setSpacing(0)
        self._script_box = QVBoxLayout()
        right.addLayout(self._script_box)
        right.addWidget(Section("Your scripts", self._your_scripts_card()))
        right.addStretch()
        columns.addLayout(left, 11)
        columns.addLayout(right, 9)
        outer.addStretch()
        self._show_script(table.current)
        return page

    def _show_script(self, script):
        self._script_chosen = script
        while self._script_box.count():
            widget = self._script_box.takeAt(0).widget()
            if widget is not None:
                widget.deleteLater()
        self._script_box.addWidget(self._script_details(script))
        restrict_tab_to_inputs(self)

    def _script_details(self, script):
        """The chosen script: its square, name and name in Resolve's menu, what it does, what it has to set, and
        Key in Resolve (its name copied, to paste into Keyboard Customization's search)."""
        from .help_text import SHORT
        from .resolve_shortcuts import menu_name
        from .scripts_page import BY_SCRIPT
        from .settings_cards import Card, FreeRow, nav_tile
        shown, glyph, colour = BY_SCRIPT[script]
        muted = self.settings.theme["picker_folder"]
        card = Card(self.settings)
        head = QHBoxLayout()
        head.setSpacing(12)
        size = round(QFontMetrics(self.font()).height() * 2.2)
        icon = QLabel()
        icon.setPixmap(nav_tile(glyph, colour, size).pixmap(size, size))
        head.addWidget(icon, 0, Qt.AlignTop)
        names = QVBoxLayout()
        names.setSpacing(1)
        title = QLabel(shown)
        title.setObjectName("SettingTitle")
        title.setStyleSheet("font-weight: 600;")
        in_menu = QLabel(menu_name(script))
        in_menu.setStyleSheet(f"color: {muted};")
        names.addWidget(title)
        names.addWidget(in_menu)
        head.addLayout(names, 1)
        top = QVBoxLayout()
        top.setSpacing(10)
        top.addLayout(head)
        about = QLabel(SHORT.get(script, ""))
        about.setWordWrap(True)
        about.setStyleSheet(f"color: {muted};")
        top.addWidget(about)
        card.add(FreeRow(top))
        for row in self._script_settings(script):
            card.add(row)
        keys = self._script_table.keys.get(menu_name(script), []) if getattr(self, "_script_table", None) else []
        now = QLabel(" ".join(keys) if keys else "No key yet")
        if keys:  # (in a soft cap, as keys are everywhere in the app)
            now.setStyleSheet("background: rgba(%d, %d, %d, 0.075); border-radius: 5px; padding: 2px 8px;"
                              % QColor(self.settings.theme["picker_text"]).getRgb()[:3])
        else:
            now.setStyleSheet(f"color: {muted};")
        key = QPushButton("Key in Resolve\u2026")
        key.setToolTip("Copies its name - paste it into the search of Resolve's Keyboard Customization")

        def copy():
            clipboard.set_text(menu_name(script))
            key.setText("Copied - paste it in Keyboard Customization")
            QTimer.singleShot(3500, key, lambda: key.setText("Key in Resolve\u2026"))
        key.clicked.connect(copy)
        line = QHBoxLayout()
        line.addWidget(now)
        line.addStretch()
        line.addWidget(key)
        card.add(FreeRow(line))
        return card

    def _script_settings(self, script):
        """[rows] - what `script` has to set (scripts_page.SCRIPTS: those with none have none)."""
        from .settings_cards import FreeRow, SettingRow, ToggleSwitch
        from .stills import default_grabs_folder, grabs_folder
        tools, files = self.settings.timeline_tools, self.settings.files
        muted = self.settings.theme["picker_folder"]

        def label(text, namespace, key):
            title = ResettableLabel(text)
            title.setObjectName("SettingTitle")
            title.doubleClicked.connect(lambda: self._reset_field(namespace, key))
            return title

        def switch(text, namespace, key, default, about=""):
            box = ResettableCheckBox(text)
            box.setChecked(getattr(self.settings, namespace).get(key, default))
            box.toggled.connect(lambda on: (getattr(self.settings, namespace).__setitem__(key, on),
                                            self.settingsChanged.emit()))
            box.doubleClicked.connect(lambda: self._reset_field(namespace, key))
            holder = QHBoxLayout()
            holder.setSpacing(0)
            holder.addWidget(box)
            box.hide()
            holder.addWidget(ToggleSwitch(self.settings, box), 0, Qt.AlignRight | Qt.AlignVCenter)
            title = QLabel(text)
            title.setObjectName("SettingTitle")
            title.mouseDoubleClickEvent = lambda e: box.doubleClicked.emit()
            return SettingRow(title, about, holder, muted)

        def frames(text, key, low, high, default):
            title = label(text, "timeline_tools", key)
            spin = DragSpinBox()
            spin.setButtonSymbols(QAbstractSpinBox.NoButtons)
            spin.setKeyboardTracking(False)
            spin.setRange(low, high)
            spin.setSuffix(" frames")
            spin.setValue(int(tools.get(key, default)))
            spin.valueChanged.connect(lambda v: self._set_timeline_tool(key, v))
            self._draggable(spin, title, "timeline_tools", key)
            self._fields = {**getattr(self, "_fields", {}), key: spin}
            return SettingRow(title, "", spin, muted)

        def stacked(title, control):  # a name over a wide field
            holder = QVBoxLayout()
            holder.setSpacing(6)
            holder.addWidget(title)
            holder.addLayout(control) if isinstance(control, QHBoxLayout) else holder.addWidget(control)
            return FreeRow(holder)

        def clip_name(text, key):
            edit = QLineEdit(tools[key])
            edit.setToolTip("Found in any bin - the first clip with exactly this name is used")
            edit.textChanged.connect(lambda words: self._set_timeline_tool(key, words.strip()) if words.strip() else None)
            holder = QVBoxLayout()
            holder.setSpacing(4)
            holder.addWidget(label(text, "timeline_tools", key))
            holder.addWidget(edit)
            about = QLabel("From your Media Pool. Clipse adds its own if there's none.")
            about.setWordWrap(True)
            about.setStyleSheet(f"color: {muted};")
            holder.addWidget(about)
            return FreeRow(holder)

        if script == "Grab Frame":
            folder = QLineEdit(files.get("grabs_folder", ""))
            folder.setPlaceholderText(default_grabs_folder())
            folder.textChanged.connect(lambda words: self._set_files("grabs_folder", words.strip()))
            choose = QPushButton("Choose\u2026")

            def pick():
                chosen = QFileDialog.getExistingDirectory(self, "Where frame grabs go", grabs_folder(self.settings))
                if chosen:
                    folder.setText(chosen)
            choose.clicked.connect(pick)
            line = QHBoxLayout()
            line.addWidget(folder, 1)
            line.addWidget(choose)
            return [switch("On the timeline", "files", "grabs_on_timeline", True, "At the playhead, on the first free track."),
                    stacked(label("Saved in", "files", "grabs_folder"), line)]
        if script == "Record Voiceover":
            from . import voiceover

            def choices(key, pairs):  # a dropdown of (value, words), kept in timeline_tools[key]
                combo = KeyboardFriendlyComboBox()
                combo.addItems([words for _v, words in pairs])
                values = [v for v, _w in pairs]
                now = tools.get(key)
                combo.setCurrentIndex(values.index(now) if now in values else 0)
                combo.currentIndexChanged.connect(lambda i: self._set_timeline_tool(key, values[i]))
                return combo
            mics = voiceover.microphones()
            chosen = tools.get("voice_mic", "")
            if chosen and chosen not in mics:  # (unplugged: kept, and used again once it's back)
                mics.append(chosen)
            folder = QLineEdit(files.get("voice_folder", ""))
            folder.setPlaceholderText(voiceover.DEFAULT_FOLDER)
            folder.textChanged.connect(lambda words: self._set_files("voice_folder", words.strip()))
            choose = QPushButton("Choose…")

            def pick_folder():
                start = files.get("voice_folder") or voiceover.DEFAULT_FOLDER
                picked = QFileDialog.getExistingDirectory(self, "Where voiceovers go", start)
                if picked:
                    folder.setText(picked)
            choose.clicked.connect(pick_folder)
            line = QHBoxLayout()
            line.addWidget(folder, 1)
            line.addWidget(choose)
            return [SettingRow(label("Microphone", "timeline_tools", "voice_mic"), "",
                               choices("voice_mic", [("", "System default")] + [(m, m) for m in mics]), muted),
                    SettingRow(label("Start", "timeline_tools", "voice_start"), "",
                               choices("voice_start", [("speech", "When you speak"), ("countdown", "After 3 seconds"),
                                                       ("now", "At once")]), muted),
                    switch("Mute the timeline", "timeline_tools", "voice_mute", True),
                    switch("Trim silence", "timeline_tools", "voice_trim", True, "At the start and end."),
                    stacked(label("Saved in", "files", "voice_folder"), line)]
        # (over a clip or footage it's as long as that - only at the playhead is the length its own)
        if script.startswith("Adjustment Clip"):
            return [clip_name("Clip name", "adj_clip_name")] + \
                ([frames("Length", "adj_fixed_frames", 1, 100000, 180)] if script.endswith("Playhead") else [])
        if script.startswith("Fusion Composition"):
            return [clip_name("Composition name", "comp_clip_name")] + \
                ([frames("Length", "comp_fixed_frames", 1, 100000, 180)] if script.endswith("Playhead") else [])
        if script == "Step Back":
            return [frames("Back by", "step_back_frames", 1, 1000, 5)]
        if script == "Step Forward":
            return [frames("Forward by", "step_forward_frames", 1, 1000, 5)]
        if script == "Tidy Fusion Nodes":
            from .scripts_fusion import TIDY_STYLES
            styles = list(TIDY_STYLES.items())
            combo = KeyboardFriendlyComboBox()
            combo.addItems([words for _k, words in styles])
            keys = [k for k, _w in styles]
            combo.setCurrentIndex(keys.index(tools.get("tidy_style")) if tools.get("tidy_style") in keys else 0)
            combo.currentIndexChanged.connect(lambda i: self._set_timeline_tool("tidy_style", keys[i]))
            return [SettingRow(label("Layout", "timeline_tools", "tidy_style"), "", combo, muted),
                    switch("Centre the view after", "timeline_tools", "tidy_fit_view", True, "The zoom stays.")]
        return []

    def _your_scripts(self):
        """[(name, path, in Resolve's menu)] - scripts that aren't Clipse's: in your folders (Settings > Folders), in
        Resolve's own script folders and Reactor's, and the ones put in Resolve's menu from here."""
        from . import resolve_shortcuts as rs
        from .scripts_fusion import scan_folders
        found = {}
        for path, name, _parent in scan_folders(list(self.settings.folders.get("scripts", []))
                                                + rs.resolve_script_folders(), {".py", ".lua"}):
            found.setdefault(os.path.realpath(path), (path, name))
        for path in rs.user_launcher_targets():
            found.setdefault(os.path.realpath(path), (path, os.path.splitext(os.path.basename(path))[0]))
        return [(name, path, rs.menu_place(path) in ("there", "added"))
                for _real, (path, name) in sorted(found.items(), key=lambda kv: kv[1][1].lower())]

    def _your_scripts_card(self):
        """Your scripts, under the chosen one's details: each with its key in Resolve, or where it stands with Resolve's
        menu - Add, Take out - and, last, Open scripts folder and Add a script…"""
        from . import resolve_shortcuts as rs
        from .resolve_keys import script_keys
        from .settings_cards import Card, FreeRow, SettingRow
        card = Card(self.settings)
        muted = self.settings.theme["picker_folder"]
        their_keys = script_keys()

        def changed(worked):
            if worked:
                self._rebuild()
        for name, path, _there in self._your_scripts():
            title = QLabel(name)
            title.setObjectName("SettingTitle")
            title.setToolTip(path)
            place = rs.menu_place(path)
            keys = their_keys.get(name)
            if place in ("there", "added") and keys:  # (its key in Resolve, as Clipse's own show theirs)
                control = QLabel(keys[0])
                control.setStyleSheet("background: rgba(%d, %d, %d, 0.075); border-radius: 5px; padding: 2px 8px;"
                                      % QColor(self.settings.theme["picker_text"]).getRgb()[:3])
                if place == "added":
                    out = QPushButton("Take out")
                    out.clicked.connect(lambda _c=False, p=path: changed(rs.remove_user_launcher(rs.user_launcher_path(p))))
                    both = QHBoxLayout()
                    both.addWidget(control)
                    both.addWidget(out)
                    control = both
            elif place == "there":
                control = QLabel("In Resolve's menu")
                control.setStyleSheet(f"color: {muted};")
            elif place == "added":
                control = QPushButton("Take out")
                control.clicked.connect(lambda _c=False, p=path: changed(rs.remove_user_launcher(rs.user_launcher_path(p))))
            else:
                control = QPushButton("Add")
                control.setToolTip("Puts it in Resolve's Workspace \u203a Scripts menu")
                control.clicked.connect(lambda _c=False, p=path: changed(rs.add_user_launcher(p)[0]))
            card.add(SettingRow(title, "", control, muted))
        card.add(FreeRow(self._scripts_buttons()))
        return card

    def _scripts_buttons(self):
        """The last row of Your scripts: Open scripts folder (Resolve's own - a script put there is in its menu) and
        Add a script… (one anywhere, into Resolve's menu) - 2026-10-21, the owner: "after my scripts"."""
        from . import resolve_shortcuts as rs
        from .scripts_fusion import default_scripts_folder
        add = QPushButton("Add a script\u2026")

        def pick():
            path, _f = QFileDialog.getOpenFileName(self, "Add a script to Resolve's menu", os.path.expanduser("~"),
                                                   "Scripts (*.py *.lua)")
            if path:
                worked, message, _target = rs.add_user_launcher(path)
                if not worked:
                    from PySide6.QtWidgets import QMessageBox
                    QMessageBox.information(self, "Clipse", message)
                if worked:
                    self._rebuild()
        add.clicked.connect(pick)
        folder = QPushButton("Open scripts folder")
        folder.setToolTip("Resolve's own scripts folder - a script put in it is in Workspace \u203a Scripts")

        def reveal():
            from .file_manager import open_folder
            where = os.path.dirname(default_scripts_folder())
            os.makedirs(where, exist_ok=True)
            open_folder(where, self.settings.files.get("file_manager", ""))
        folder.clicked.connect(reveal)
        row = QHBoxLayout()
        row.addWidget(folder)
        row.addWidget(add)
        row.addStretch()
        return row

    def _build_listen_group(self):
        """Listening to sounds before inserting them (the listen key / the
        speaker in the picker's bottom bar)."""
        listen = self.settings.listen
        box = QGroupBox("Preview")
        form = QFormLayout(box)
        from .preview_place import PreviewPlace  # (where it opens: tiles, the drawing, the gap)
        place = PreviewPlace(self.settings)
        place.changed.connect(lambda where, gap: (listen.__setitem__("preview_place", where),
                                                  self._set_listen("preview_gap", gap)))
        form.addRow(place)
        for key, text in (("preview_with_picker", "Open the preview with the picker"),
                          ("autoplay", "Autoplay"),
                          ("loop", "Loop"),
                          ("hover_scrub", "Scrub with the mouse"),
                          ("scrub_sound", "Sound while scrubbing"),
                          ("timecode", "Show timecode")):
            cb = ResettableCheckBox(text)
            cb.setChecked(listen[key])
            cb.toggled.connect(lambda checked, k=key: self._set_listen(k, checked))
            cb.doubleClicked.connect(lambda k=key: self._reset_field("listen", k))
            form.addRow(cb)
        for key, label_text, choices in (
                ("space_plays", "Space plays", [("smart", "When I'm in the list"), ("always", "Always"), ("never", "Never")]),
                ("space_action", "What Space does", [("auto", "Short clips start over, long ones pause"),
                                                     ("pause", "Play / pause"), ("replay", "Start over")])):
            label = ResettableLabel(label_text)
            label.doubleClicked.connect(lambda k=key: self._reset_field("listen", k))
            combo = KeyboardFriendlyComboBox()
            modes = [mode for mode, _text in choices]
            combo.addItems([text for _mode, text in choices])
            combo.setCurrentIndex(modes.index(listen.get(key)) if listen.get(key) in modes else 0)
            combo.currentIndexChanged.connect(lambda i, k=key, m=modes: self._set_listen(k, m[i]))
            form.addRow(label, combo)
        short_label = ResettableLabel("Short clips are under")
        short_label.doubleClicked.connect(lambda: self._reset_field("listen", "space_replay_under"))
        short = DragSpinBox()
        short.setButtonSymbols(QAbstractSpinBox.NoButtons)
        short.setKeyboardTracking(False)
        short.setRange(1, 600)
        short.setSuffix(" s")
        short.setValue(int(listen.get("space_replay_under", 30)))
        short.valueChanged.connect(lambda v: self._set_listen("space_replay_under", v))
        form.addRow(short_label, short)
        self._draggable(short, short_label, "listen", "space_replay_under")
        volume_label = ResettableLabel("Volume")
        volume_label.doubleClicked.connect(lambda: self._reset_field("listen", "volume"))
        volume = self._slider("listen", "volume", 0, 100, 1, " %", lambda v: self._set_listen("volume", int(v)))
        form.addRow(volume_label, volume)
        volume.scrub_from(volume_label)
        return box

    def _build_music_group(self):
        """Music vs sound effects, and BPM (see bpm.py)."""
        listen = self.settings.listen
        box = QGroupBox("Music & sound effects")
        form = QFormLayout(box)
        for key, text in (("show_bpm", "Show BPM on music"), ("guess_energy", "Guess energy"),
                          ("trim_silence", "Trim silence when inserting sounds")):
            cb = ResettableCheckBox(text)
            cb.setChecked(listen.get(key, True))
            cb.toggled.connect(lambda checked, k=key: self._set_listen(k, checked))
            cb.doubleClicked.connect(lambda k=key: self._reset_field("listen", k))
            form.addRow(cb)
        secs_label = ResettableLabel("Music is at least")
        secs_label.doubleClicked.connect(lambda: self._reset_field("listen", "music_min_seconds"))
        secs = DragSpinBox()
        secs.setButtonSymbols(QAbstractSpinBox.NoButtons)
        secs.setKeyboardTracking(False)
        secs.setRange(5, 600)
        secs.setSuffix(" s")
        secs.setValue(listen.get("music_min_seconds", 30))
        secs.valueChanged.connect(lambda v: self._set_listen("music_min_seconds", v))
        form.addRow(secs_label, secs)
        self._draggable(secs, secs_label, "listen", "music_min_seconds")
        auto = ResettableCheckBox("Analyse new sounds automatically")
        auto.setChecked(listen.get("auto_analyse", False))
        auto.toggled.connect(lambda checked: self._set_listen("auto_analyse", checked))
        auto.doubleClicked.connect(lambda: self._reset_field("listen", "auto_analyse"))
        form.addRow(auto)
        row = QHBoxLayout()
        self.analyse_button = QPushButton("Analyse sounds")
        self.analyse_button.setToolTip("Listens to each sound once: music or sound effect, BPM, key, mood, "
                                       "clean loops, beats and what sounds alike. Runs in the background.")
        self.analyse_button.clicked.connect(self._analyse_clicked)
        self.analyse_status = QLabel("")
        self.analyse_status.setStyleSheet(f"color: {self.settings.theme['picker_folder']};")
        self.analyse_status.setWordWrap(True)
        row.addWidget(self.analyse_button)
        row.addWidget(self.analyse_status, 1)
        form.addRow(row)
        analyser = self.sound_analyser
        if analyser is not None:
            analyser.progress.connect(self._analysis_progress)
            analyser.finished.connect(self._analysis_finished)
        self._analysis_finished()
        return box

    def _analyse_clicked(self):
        analyser = self.sound_analyser
        if analyser is None:
            return
        if analyser.running:
            analyser.stop()
            self._analysis_finished()
            return
        if not analyser.start():
            self.analyse_status.setText("Needs numpy and PyAV - run the installer again to add them.")
            return
        if analyser.running:
            self.analyse_button.setText("Stop")
            self.analyse_status.setText("Starting\u2026")

    def _analysis_progress(self, done, total):
        try:
            self.analyse_button.setText("Stop")
            self.analyse_status.setText(f"Analysing {done} of {total}\u2026")
        except RuntimeError:
            pass  # this Settings window is gone

    def _analysis_finished(self, _count=0):
        analyser = self.sound_analyser
        try:
            if analyser is None or not analyser.rows:
                self.analyse_button.setEnabled(False)
                self.analyse_status.setText("Open the picker once to load this project's sounds.")
                return
            audio = [r for r in analyser.rows if r.category == "audio" and r.file]
            missing = len(analyser.missing())
            self.analyse_button.setEnabled(missing > 0 or analyser.running)
            self.analyse_button.setText("Stop" if analyser.running else "Analyse sounds")
            if analyser.running:
                return
            failed = analyser.failed()
            done = len(audio) - missing
            if failed:
                self.analyse_status.setText(
                    f"{done} of {len(audio)} sounds analysed - {len(failed)} couldn't be read "
                    f"(e.g. {failed[0][0].name}: {failed[0][1]}). Analyse sounds tries them again.")
            else:
                self.analyse_status.setText(
                    f"All {len(audio)} sounds in this project are analysed." if not missing else
                    f"{done} of {len(audio)} sounds analysed - {missing} to go.")
        except RuntimeError:
            pass

    def _build_info_group(self):
        """Which lines the clip info (Ctrl+D) shows under the preview."""
        box = QGroupBox("Clip info")
        outer = QVBoxLayout(box)
        show = ResettableCheckBox("Show clip info under the preview")
        show.setChecked(self.settings.listen.get("show_info", True))
        show.toggled.connect(lambda checked: self._set_listen("show_info", checked))
        show.doubleClicked.connect(lambda: self._reset_field("listen", "show_info"))
        outer.addWidget(show)  # (what it shows: a right-click on it, under the preview)
        return box

    def _build_files_group(self):
        """Ctrl+E and folder: - which file manager."""
        files = self.settings.files
        box = QGroupBox("File manager")
        form = QFormLayout(box)
        command_label = ResettableLabel("Command")
        command_label.doubleClicked.connect(lambda: self._reset_field("files", "file_manager"))
        command = QLineEdit(files["file_manager"])
        command.setPlaceholderText("automatic")
        command.textChanged.connect(lambda text: self._set_files("file_manager", text.strip()))
        form.addRow(command_label, command)
        return box

    def _set_files(self, key, value):
        self.settings.files[key] = value
        self.settingsChanged.emit()

    def _set_listen(self, key, value):
        self.settings.listen[key] = value
        self.settingsChanged.emit()

    def _combo_row(self, form, label_text, namespace, key, choices, default):
        label = ResettableLabel(label_text)
        label.doubleClicked.connect(lambda: self._reset_field(namespace, key))
        box = KeyboardFriendlyComboBox()
        box.addItems([text for _k, text in choices])
        keys = [k for k, _t in choices]
        current = getattr(self.settings, namespace).get(key, default)
        box.setCurrentIndex(keys.index(current) if current in keys else 0)

        def changed(i):
            getattr(self.settings, namespace)[key] = keys[i]
            self.settingsChanged.emit()
        box.currentIndexChanged.connect(changed)
        form.addRow(label, box)

    def _build_search_group(self):
        """The order results come in, and learning from what's picked."""
        box = QGroupBox("Search")
        form = QFormLayout(box)
        self._combo_row(form, "Sort results by", "general", "result_order",
                        [("best", "Best match"), ("used", "Most used first"), ("name", "Name (A-Z)")], "best")
        self._combo_row(form, "With nothing typed", "general", "empty_order",
                        [("used", "Most used first"), ("added", "Recently added"), ("recent", "Recently used")], "used")
        return box

    def _build_nodes_group(self):
        """Tidy up after every insert (the tidy's own settings: Scripts > Tidy Fusion nodes)."""
        box = QGroupBox("Nodes")
        form = QFormLayout(box)
        after = ResettableCheckBox("Tidy up after every insert")
        after.setChecked(self.settings.timeline_tools.get("tidy_after_insert", True))
        after.toggled.connect(lambda on: self._set_timeline_tool("tidy_after_insert", on))
        after.doubleClicked.connect(lambda: self._reset_field("timeline_tools", "tidy_after_insert"))
        form.addRow(after)
        return box

    def _build_expressions_group(self):
        box = QGroupBox("Expressions")
        form = QFormLayout(box)
        ask = ResettableCheckBox("Ask before adding a node for an expression")
        ask.setChecked(self.settings.timeline_tools.get("expression_ask", True))
        ask.toggled.connect(lambda on: self._set_timeline_tool("expression_ask", on))
        ask.doubleClicked.connect(lambda: self._reset_field("timeline_tools", "expression_ask"))
        form.addRow(ask)
        return box

    def _build_title_group(self):
        """title: in the picker adds this title with the typed text; and
        what happens to tracks after clips are wrapped up (Insert as)."""
        box = QGroupBox("Titles")
        form = QFormLayout(box)
        label = ResettableLabel("Default title")
        label.doubleClicked.connect(lambda: self._reset_field("timeline_tools", "title_name"))
        edit = QLineEdit(self.settings.timeline_tools["title_name"])
        edit.setPlaceholderText("Text+")
        edit.textChanged.connect(lambda text: self._set_timeline_tool("title_name", text.strip() or "Text+"))
        form.addRow(label, edit)
        return box

    def _build_subtitles_group(self):
        """Subtitles from speech (> subtitles): how Resolve splits them up.
        How they look is the subtitle track's style in Resolve's Inspector."""
        from . import resolve_commands as commands
        tools = self.settings.timeline_tools
        box = QGroupBox("Subtitles from speech")
        form = QFormLayout(box)
        hint = QLabel("How they look is set in Resolve: the subtitle track \u203a Inspector \u203a Track.")
        hint.setStyleSheet(f"color: {self.settings.theme['picker_folder']};")
        form.addRow(hint)
        for key, label_text, choices in (("subtitle_language", "Spoken language", commands.SUBTITLE_LANGUAGES),
                                         ("subtitle_lines", "Lines on screen", commands.SUBTITLE_LINES),
                                         ("subtitle_preset", "Made for", commands.SUBTITLE_PRESETS)):
            label = ResettableLabel(label_text)
            label.doubleClicked.connect(lambda k=key: self._reset_field("timeline_tools", k))
            combo = KeyboardFriendlyComboBox()
            keys = [k for k, _text in choices]
            combo.addItems([text for _k, text in choices])
            combo.setCurrentIndex(keys.index(tools.get(key)) if tools.get(key) in keys else 0)
            combo.currentIndexChanged.connect(lambda i, k=key, keys=keys: self._set_timeline_tool(k, keys[i]))
            form.addRow(label, combo)
        for key, label_text, low, high, suffix in (("subtitle_chars", "Longest line", 1, 60, " characters"),
                                                   ("subtitle_gap", "Gap between subtitles", 0, 10, " frames")):
            label = ResettableLabel(label_text)
            label.doubleClicked.connect(lambda k=key: self._reset_field("timeline_tools", k))
            spin = DragSpinBox()
            spin.setButtonSymbols(QAbstractSpinBox.NoButtons)
            spin.setKeyboardTracking(False)
            spin.setRange(low, high)
            spin.setSuffix(suffix)
            spin.setValue(int(tools.get(key, low)))
            spin.valueChanged.connect(lambda v, k=key: self._set_timeline_tool(k, v))
            form.addRow(label, spin)
            self._draggable(spin, label, "timeline_tools", key)
        return box

    def _set_timeline_tool(self, key, value):
        self.settings.timeline_tools[key] = value
        self.settingsChanged.emit()

    def _set_page_default(self, page_key, source_key, value):
        self.settings.page_defaults[page_key][source_key] = value
        self.settingsChanged.emit()

    def _set_general(self, key, value):
        self.settings.general[key] = value
        self.settingsChanged.emit()
        if key == "start_in_background":
            from . import autostart
            self.settings.save()  # the login helper reads it too
            print(autostart.set_enabled(value))

    # -- Appearance --
    COLOR_NAMES = {
        "picker_bg": "Background", "picker_bar_bg": "Bottom bar", "picker_border": "Lines",
        "outer_outline_color": "Window outline", "picker_text": "Text", "picker_input_text": "Search text",
        "picker_folder": "Quiet text", "picker_select_bg": "Highlighted row", "picker_accent": "Accent",
        "staged_marker_color": "Staged tick", "favorite_marker_color": "Favourite star",
        "age_recent_color": "Recent", "age_medium_color": "A while ago", "age_old_color": "Old",
    }

    def _build_appearance_tab(self):
        """Calm and in one column: theme, colours, text, window, extras."""
        page = QWidget()
        page.setObjectName("SettingsPage")
        layout = QVBoxLayout(page)

        theme_box = QGroupBox("Theme")
        from .settings_cards import Gallery
        gallery = Gallery()
        QVBoxLayout(theme_box).addWidget(gallery)
        current = next((n for n, preset in THEME_PRESETS.items()
                        if all(str(self.settings.theme.get(k, "")).lower() == str(v).lower()
                               for k, v in preset.items() if k in INTERFACE_COLOR_VARS)), None)
        for i, (name, preset) in enumerate(THEME_PRESETS.items()):
            # the theme's picker colours with your clip colours - what applying it gives you
            shown = self.settings.theme_after(name)
            card = ThemeCard(name, shown, name == current, settings=self.settings)
            card.clicked.connect(lambda _=False, n=name: self._apply_preset(n))
            gallery.add(card)
        if current is None:
            note = QLabel("Your own colours")
            note.setStyleSheet(f"color: {self.settings.theme['picker_folder']};")
            gallery.set_extra(note)
        layout.addWidget(theme_box)

        # three even columns: the picker itself, its clip types, the rest
        colors_box = QGroupBox("Colours")
        colors_body = QWidget()
        grid = QGridLayout(colors_body)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(2)
        clips = ["color_audio", "color_video", "color_image", "color_adjustment", "color_compound",
                 "color_bin", "color_selected"]
        rest = [v for v in ICON_COLOR_VARS if v not in clips]
        columns = (("Picker", INTERFACE_COLOR_VARS), ("Clips", clips), ("Fusion, projects & marks", rest))
        for col, (title, var_list) in enumerate(columns):
            head = QLabel(title)
            head.setStyleSheet(f"color: {self.settings.theme['picker_folder']};")
            grid.addWidget(head, 0, col * 3, 1, 2)
            for row, var in enumerate(var_list, start=1):
                label = ResettableLabel(self._color_name(var))
                label.doubleClicked.connect(lambda v=var: self._reset_field("theme", v))
                label.setMinimumHeight(28)
                swatch = ColorSwatchButton(self.settings.theme[var], show_hex=False)
                swatch.setToolTip(f"{self._color_name(var)}  {self.settings.theme[var].lower()}")
                swatch.colorChanged.connect(lambda hex_val, v=var: self._set_color(v, hex_val))
                grid.addWidget(swatch, row, col * 3)
                grid.addWidget(label, row, col * 3 + 1)
            if col < len(columns) - 1:
                grid.setColumnMinimumWidth(col * 3 + 2, 18)
        grid.setColumnStretch(len(columns) * 3, 1)
        self._foldable(colors_box, colors_body, "colours", "every colour", start_open=current is None)
        layout.addWidget(colors_box)

        text_box = QGroupBox("Text")
        text_form = QFormLayout(text_box)
        self._add_font_row(text_form)
        self._add_display_row(text_form, "font_size", "Font size", widget="int", min=6, max=32, slider=True)
        self._add_display_row(text_form, "ui_scale", "Scale", widget="float", min=0.5, max=3.0, step=0.05,
                              suffix="\u00d7", slider=True)
        layout.addWidget(text_box)

        window_box = QGroupBox("Window")
        window_form = QFormLayout(window_box)
        self._add_display_row(window_form, "outer_corner_radius", "Corners", widget="int", min=0, max=24,
                              suffix=" px", slider=True)
        reset_place = QPushButton("Reset position and size")
        reset_place.setToolTip("Back to automatic size, in the middle of the screen")
        reset_place.clicked.connect(self._reset_picker_place)
        window_form.addRow("", reset_place)
        layout.addWidget(window_box)

        icons_box = QGroupBox("Your own icons")
        own = [k for k in ICON_LABELS if self.settings.icons[k] != ICON_DEFAULTS.get(k)]
        body = QWidget()
        icons_layout = QVBoxLayout(body)
        icons_layout.setContentsMargins(0, 0, 0, 0)
        self._foldable(icons_box, body, "icons", "the icon fields", start_open=bool(own))
        hint = QLabel("A character or emoji instead of the symbol - empty for the built-in one.")
        hint.setStyleSheet(f"color: {self.settings.theme['picker_folder']};")
        hint.setWordWrap(True)
        icons_layout.addWidget(hint)
        igrid = QGridLayout()
        igrid.setHorizontalSpacing(18)
        igrid.setVerticalSpacing(4)
        per_col = (len(ICON_LABELS) + 2) // 3
        for i, (key, label_text) in enumerate(ICON_LABELS.items()):
            label = ResettableLabel(label_text)
            label.doubleClicked.connect(lambda k=key: self._reset_field("icons", k))
            current_icon = self.settings.icons[key]
            edit = QLineEdit("" if current_icon == ICON_DEFAULTS.get(key) else current_icon)
            edit.setPlaceholderText("\u2013")
            edit.setAlignment(Qt.AlignCenter)
            edit.setMaxLength(4)
            edit.setFixedWidth(52)
            edit.textChanged.connect(lambda text, k=key: self._set_icon(k, text))
            r, c = i % per_col, i // per_col
            igrid.addWidget(label, r, c * 2)
            igrid.addWidget(edit, r, c * 2 + 1)
        igrid.setColumnStretch(6, 1)
        icons_layout.addLayout(igrid)
        layout.addWidget(icons_box)

        layout.addStretch()
        return page

    def _foldable(self, box, body, key, what, start_open=False):
        """A section that stays tucked away behind a "Show ..." link until
        you want it (and stays open while this Settings window is)."""
        folds = self.__dict__.setdefault("_open_folds", set())
        if start_open:
            folds.add(key)
        outer = QVBoxLayout(box)
        toggle = QPushButton()
        toggle.setObjectName("LinkButton")
        toggle.setFlat(True)
        toggle.setCursor(Qt.PointingHandCursor)
        outer.addWidget(toggle, 0, Qt.AlignLeft)
        outer.addWidget(body)

        def show(on):
            body.setVisible(on)
            toggle.setText(("Hide " if on else "Show ") + what)
            (folds.add if on else folds.discard)(key)
        toggle.clicked.connect(lambda: show(not body.isVisible()))
        show(key in folds)

    def _color_name(self, var):
        return self.COLOR_NAMES.get(var) or var.replace("picker_", "").replace("color_", "").replace("_", " ").capitalize()

    def _reset_picker_place(self):
        """Automatic size, centred - forgets where the picker was dragged and sized."""
        d = self.settings.display
        d["window_width"] = d["window_height"] = 0
        d["picker_pos"] = []
        self.settings.save()
        self._rebuild()
        self.settingsChanged.emit()
        if self.picker_place_reset is not None:
            self.picker_place_reset()

    def _add_color_rows(self, box, var_list):
        form = QFormLayout(box)
        for var in var_list:
            label_text = var.replace("picker_", "").replace("color_", "").replace("_", " ").title()
            label = ResettableLabel(label_text)
            label.doubleClicked.connect(lambda v=var: self._reset_field("theme", v))
            swatch = ColorSwatchButton(self.settings.theme[var])
            swatch.colorChanged.connect(lambda hex_val, v=var: self._set_color(v, hex_val))
            form.addRow(label, swatch)

    def _add_font_row(self, form):
        label = ResettableLabel("Font")
        label.doubleClicked.connect(lambda: self._reset_field("display", "font_family"))
        ctrl = QFontComboBox()
        from .fonts import ui_family
        shown = self.settings.display.get("font_family") or ui_family(self.settings)  # (the name as picked)
        if shown:
            ctrl.blockSignals(True)  # just showing the current font, not changing it
            ctrl.setCurrentFont(QFont(shown))
            ctrl.blockSignals(False)
        ctrl.currentFontChanged.connect(lambda f: self._set_display("font_family", f.family()))
        form.addRow(label, ctrl)

    def _add_display_row(self, form, key, label_text, widget, **kw):
        label = ResettableLabel(label_text)
        label.doubleClicked.connect(lambda k=key: self._reset_field("display", k))
        if kw.get("slider"):  # a range: the app's slider, its number beside it
            ctrl = self._slider("display", key, kw["min"], kw["max"], kw.get("step", 1), kw.get("suffix", ""),
                                lambda v, k=key, w=widget: self._set_display(k, v if w == "float" else int(v)))
            form.addRow(label, ctrl)
            ctrl.scrub_from(label)
            return
        if widget == "float":
            ctrl = DragDoubleSpinBox()
            ctrl.setButtonSymbols(QAbstractSpinBox.NoButtons)
            ctrl.setKeyboardTracking(False)  # apply on Enter / leaving the field, not every keystroke
            ctrl.setRange(kw["min"], kw["max"])
            ctrl.setSingleStep(kw.get("step", 0.1))
            ctrl.setValue(self.settings.display[key])
            ctrl.valueChanged.connect(lambda v, k=key: self._set_display(k, v))
        else:
            ctrl = DragSpinBox()
            ctrl.setButtonSymbols(QAbstractSpinBox.NoButtons)
            ctrl.setKeyboardTracking(False)  # apply on Enter / leaving the field, not every keystroke
            if kw.get("auto"):  # 0 = sized to the screen; typing a number sets it
                ctrl.setRange(0, kw["max"])
                ctrl.setSpecialValueText("Automatic")
                ctrl.setValue(self.settings.display[key])
                ctrl.valueChanged.connect(lambda v, k=key, lo=kw["min"]: self._set_display(k, v if v == 0 else max(lo, v)))
            else:
                ctrl.setRange(kw["min"], kw["max"])
                ctrl.setValue(self.settings.display[key])
                ctrl.valueChanged.connect(lambda v, k=key: self._set_display(k, v))
        form.addRow(label, ctrl)
        self._draggable(ctrl, label, "display", key)

    def _apply_preset(self, name):
        self.settings.apply_theme_preset(name)
        self._rebuild()
        self.settingsChanged.emit()

    def _set_color(self, var, hex_val):
        self.settings.theme[var] = hex_val
        self.settingsChanged.emit()

    def _set_display(self, key, value):
        self.settings.display[key] = value
        self.settingsChanged.emit()

    def _set_icon(self, key, value):
        # an empty field means "use the built-in symbol"
        self.settings.icons[key] = value or ICON_DEFAULTS[key]
        self.settingsChanged.emit()

    # -- Keybindings --
    def _build_keybindings_tab(self):
        self._key_fields = {}  # keybind name -> its first key box (go_to_key)
        page = QWidget()
        page.setObjectName("SettingsPage")
        layout = QVBoxLayout(page)
        for section_name, names in KEYBIND_SCHEMA:
            box = QGroupBox(section_name)
            form = QFormLayout(box)
            for name in names:
                label_text = KEYBIND_LABELS.get(name, name.replace("_", " ").title())
                label = ResettableLabel(label_text)
                label.doubleClicked.connect(lambda n=name: self._reset_keybind_pair(n))

                primary = KeyField(self.settings, self.settings.keybinds[name])
                primary.keySequenceChanged.connect(lambda seq, n=name: self._set_keybind(n, seq.toString()))
                self._key_fields[name] = primary

                secondary = KeyField(self.settings, self.settings.keybinds_secondary[name])
                secondary.keySequenceChanged.connect(
                    lambda seq, n=name: self._set_keybind_secondary(n, seq.toString()))

                row = QHBoxLayout()
                row.addStretch()  # boxes line up on the right in every group
                row.addWidget(primary)
                row.addSpacing(10)
                row.addWidget(secondary)
                form.addRow(label, row)
            layout.addWidget(box)
        layout.addStretch()
        return page

    def _reset_keybind_pair(self, name):
        self.settings.reset_key("keybinds", name)
        self.settings.reset_key("keybinds_secondary", name)
        self._rebuild()
        self.settingsChanged.emit()

    def _set_keybind(self, name, seq_str):
        self.settings.keybinds[name] = seq_str
        self.settingsChanged.emit()

    def _set_keybind_secondary(self, name, seq_str):
        self.settings.keybinds_secondary[name] = seq_str
        self.settingsChanged.emit()

    # -- Folders --
    def _build_prefixes_tab(self):
        page = QWidget()
        page.setObjectName("SettingsPage")
        layout = QVBoxLayout(page)


        for section_name, targets in PREFIX_SCHEMA:
            box = QGroupBox(section_name)
            form = QFormLayout(box)
            for target in targets:
                label_text = PREFIX_LABELS.get(target, target.title())
                label = ResettableLabel(label_text)
                label.doubleClicked.connect(lambda t=target: self._reset_prefix(t))

                edit = QLineEdit("  ".join(p + ":" for p in self.settings.prefixes[target]))  # (as they're typed)
                edit.setPlaceholderText("b:  bin:")
                edit.textChanged.connect(lambda text, t=target: self._set_prefix(t, text))

                keybind_edit = KeyField(self.settings, self.settings.prefix_keybinds[target])
                keybind_edit.setToolTip("Goes straight to this search")
                keybind_edit.keySequenceChanged.connect(
                    lambda seq, t=target: self._set_prefix_keybind(t, seq.toString()))

                row = QHBoxLayout()
                row.addWidget(edit)
                row.addWidget(keybind_edit)
                form.addRow(label, row)
            layout.addWidget(box)

        layout.addStretch()
        return page

    def _set_prefix(self, target, text):
        import re  # (one after another: spaces, commas, colons - however they're typed)
        prefixes = [p.lower() for p in re.split(r"[\s,:]+", text) if p]
        self.settings.prefixes[target] = prefixes
        self.settingsChanged.emit()

    def _set_prefix_keybind(self, target, seq_str):
        self.settings.prefix_keybinds[target] = seq_str
        self.settingsChanged.emit()

    def _reset_prefix(self, target):
        self.settings.reset_key("prefixes", target)
        self.settings.reset_key("prefix_keybinds", target)
        self._rebuild()
        self.settingsChanged.emit()

    def _build_folders_tab(self):
        page = QWidget()
        page.setObjectName("SettingsPage")
        layout = QVBoxLayout(page)

        layout.addWidget(self._build_folder_list_group(
            "Scripts", "scripts",
            "Searched with script:, sub-folders too. Resolve's own are always searched."))
        layout.addWidget(self._build_folder_list_group(
            "Macros", "macros",
            "Searched with macro: (.setting files)."))
        layout.addWidget(self._build_folder_list_group(
            "Fusion compositions", "fusion_comps", "Searched with comp: (.comp files)."))
        layout.addWidget(self._build_files_group())

        layout.addStretch()
        return page

    def _build_folder_list_group(self, title, key, description):
        box = QGroupBox(title)
        layout = QVBoxLayout(box)

        desc = QLabel(description)
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {self.settings.theme['picker_folder']}; {css(SMALL * rel(self.settings, 'settings'))}")
        layout.addWidget(desc)

        list_widget = QListWidget()
        list_widget.addItems(self.settings.folders[key])
        list_widget.setMaximumHeight(90)
        layout.addWidget(list_widget)

        btn_row = QHBoxLayout()
        add_btn = QPushButton("Add folder")
        remove_btn = QPushButton("Remove")
        files_btn = QPushButton(_file_manager_name())
        terminal_btn = QPushButton("Open in Terminal")
        add_btn.clicked.connect(lambda: self._add_folder(key, list_widget))
        remove_btn.clicked.connect(lambda: self._remove_folder(key, list_widget))
        files_btn.clicked.connect(lambda: self._open_selected_folder(key, list_widget))
        terminal_btn.clicked.connect(lambda: self._open_selected_folder_in_terminal(key, list_widget))
        files_btn.setToolTip("Open the selected folder (or the first one) in your file manager")
        terminal_btn.setToolTip("Open a terminal in the selected folder (or the first one)")
        btn_row.addWidget(add_btn)
        btn_row.addWidget(remove_btn)
        btn_row.addWidget(files_btn)
        btn_row.addWidget(terminal_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        return box

    @staticmethod
    def _selected_folder(list_widget):
        row = list_widget.currentRow()
        if row < 0:
            row = 0 if list_widget.count() else -1
        return list_widget.item(row).text() if row >= 0 else None

    def _open_selected_folder_in_terminal(self, key, list_widget):
        folder = self._selected_folder(list_widget)
        if folder:
            scripts_fusion.open_terminal(folder)

    def _open_selected_folder(self, key, list_widget):
        from .file_manager import open_folder
        folder = self._selected_folder(list_widget)
        if folder:
            open_folder(folder, self.settings.files.get("file_manager", ""))

    def _add_folder(self, key, list_widget):
        folder = QFileDialog.getExistingDirectory(self, "Add a folder to search")
        if not folder:
            return
        if folder in self.settings.folders[key]:
            return
        self.settings.folders[key].append(folder)
        list_widget.addItem(folder)
        self.settingsChanged.emit()

    def _remove_folder(self, key, list_widget):
        row = list_widget.currentRow()
        if row < 0:
            return
        folder = list_widget.item(row).text()
        if folder in self.settings.folders[key]:
            self.settings.folders[key].remove(folder)
        list_widget.takeItem(row)
        self.settingsChanged.emit()
