"""Settings > Organise (2026-10-30, the owner: "make the organising and settings page work"): your project templates
and what Organise project (organise.py) does with them - the template's bins, each with its colour and what goes in
it, where each kind of clip goes and its colour, and folders on disk whose files go in a bin. Every change is
written into the template's file at once (templates are files, not settings - no Reset page).

A built-in template changed here is saved as yours under its name (yours is used in its place); Reset takes yours
away again. Bins are a template's tree ([name, [sub-bins]]), every rule names a bin by its path ("02_b-roll/screen"),
and a bin renamed or taken away takes its rules with it (organise.bin_moved)."""
import copy
import os

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QFileDialog, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                               QMenu, QPushButton, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from . import look, organise, paths, project_templates as pt
from .settings_cards import ToggleSwitch
from .resolve_commands import CLIP_COLORS, CLIP_COLOR_HEX

# the kinds as the page names them, in its order (organise.KINDS); timelines get no colour (only Media Pool clips and
# what's on a video track do)
KIND_NAMES = [("video", "Videos"), ("still", "Stills"), ("music", "Music"), ("sfx", "Sound effects"),
              ("fusion", "Fusion compositions"), ("compound", "Compound clips"), ("adjustment", "Adjustment clips"),
              ("generator", "Generators"), ("timeline", "Timelines")]
NO_COLOUR = ("timeline",)
MASTER = "Stays in Master"


def _tree(bins):
    """A template's bins as [[name, [...]]] all the way down (a bin may be saved as a plain name)."""
    return [[name, _tree(sub)] for name, sub in pt._entries(bins)]


def _find(tree, path):
    """The [name, sub] entry at `path`, and the list it's in."""
    parts, here, entry = path.split("/"), tree, None
    for i, part in enumerate(parts):
        entry = next((e for e in here if e[0] == part), None)
        if entry is None:
            return None, None
        if i < len(parts) - 1:
            here = entry[1]
    return entry, here


def _home(path):
    """~ for the home folder, as the template keeps it."""
    home = os.path.expanduser("~")
    return "~" + path[len(home):] if path == home or path.startswith(home + os.sep) else path


def swatch_icon(colour, size, settings):
    """A clip colour's chip (Resolve's own colour) - "" is none: an outline with a line through it."""
    pm = QPixmap(QSize(size * 2, size * 2))
    pm.setDevicePixelRatio(2.0)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    rect = QRectF(1, 1, size - 2, size - 2)
    r = min(look.radius(settings, "control"), size / 3)
    if colour:
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(CLIP_COLOR_HEX.get(colour, "#888888")))
        p.drawRoundedRect(rect, r, r)
    else:
        faint = QColor(settings.theme["picker_text"])
        faint.setAlphaF(0.35)
        p.setPen(QPen(faint, 1.2))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), r, r)
        p.drawLine(QPointF(rect.left() + 3, rect.bottom() - 3), QPointF(rect.right() - 3, rect.top() + 3))
    p.end()
    return QIcon(pm)


class ColourButton(QPushButton):
    """A clip colour: its chip and name; a click shows Resolve's colours to pick from (None first)."""
    picked = Signal(str)

    def __init__(self, settings, colour=""):
        super().__init__()
        self.settings = settings
        self.setObjectName("ColourButton")
        self.setCursor(Qt.PointingHandCursor)
        self._size = round(self.fontMetrics().height() * 0.95)
        self.setIconSize(QSize(self._size, self._size))
        self.setMinimumWidth(round(self.fontMetrics().horizontalAdvance("Chocolate") + self._size * 3))
        self.clicked.connect(self._menu)
        self.set_colour(colour)

    def set_colour(self, colour):
        self.colour = colour or ""
        self.setIcon(swatch_icon(self.colour, self._size, self.settings))
        self.setText(self.colour or "None")

    def _menu(self):
        menu = QMenu(self)
        for colour in [""] + CLIP_COLORS:
            action = menu.addAction(swatch_icon(colour, self._size, self.settings), colour or "None")
            action.setCheckable(True)
            action.setChecked(colour == self.colour)
            action.triggered.connect(lambda _c=False, colour=colour: self._pick(colour))
        menu.exec(self.mapToGlobal(self.rect().bottomLeft()))

    def _pick(self, colour):
        if colour != self.colour:
            self.set_colour(colour)
            self.picked.emit(colour)


class BinChoice(QComboBox):
    """A bin of the template's, or Stays in Master ("")."""
    picked = Signal(str)

    def __init__(self):
        super().__init__()
        self.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.activated.connect(lambda i: self.picked.emit(self.itemData(i) or ""))

    def fill(self, bins, chosen):
        self.blockSignals(True)
        self.clear()
        self.addItem(MASTER, "")
        for path in bins:
            self.addItem(path.replace("/", " › "), path)
        if chosen and chosen not in bins:  # (a bin the template doesn't have: still shown, so it isn't lost silently)
            self.addItem(chosen.replace("/", " › "), chosen)
        self.setCurrentIndex(max(0, self.findData(chosen or "")))
        self.blockSignals(False)


class OrganisePage:
    """The page's pieces and the template being changed. build() gives the page."""

    def __init__(self, dialog):
        self.dialog = dialog
        self.settings = dialog.settings
        self.muted = self.settings.theme["picker_folder"]
        self.name = None
        self.template = {}
        self.own = None  # organise.editable(template)
        self.tree = []

    # -- the template --
    def _names(self):
        return [name for name, _t, _b in pt.all_templates()]

    def load(self, name):
        names = self._names()
        if name not in names:
            name = names[0] if names else None
        self.name = name
        self.dialog._organise_template = name
        self.template = copy.deepcopy(pt.all_templates_by_name().get(name) or {}) if name else {}
        self.tree = _tree(self.template.get("bins") or [])
        self.own = organise.editable(self.template) if name else None

    def save(self):
        if not self.name:
            return
        data = dict(self.template)
        data["name"] = self.name
        data["bins"] = self.tree
        data["organise"] = self.own
        self.template = data
        paths.write_json(pt._file(self.name), data, indent=1)
        self._update_template_buttons()

    def _bins(self):
        return organise.bin_paths(self.tree)

    # -- building --
    def build(self):
        from .settings_cards import Card, FreeRow, Section, SettingRow
        page = QWidget()
        page.setObjectName("SettingsPage")
        layout = QVBoxLayout(page)
        self.load(getattr(self.dialog, "_organise_template", None))

        # Template
        card = Card(self.settings)
        self.chooser = QComboBox()
        self.chooser.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.chooser.activated.connect(lambda i: self._choose(self.chooser.itemText(i)))
        card.add(SettingRow(self._title("Template"), "", self.chooser, self.muted))
        self.recolour = QPushButton("Recolour all")
        self.recolour.clicked.connect(self._recolour)
        card.add(SettingRow(self._title("Clip colours"), "", self.recolour, self.muted))
        buttons = QHBoxLayout()
        self.remove_button = QPushButton("Delete")
        self.remove_button.clicked.connect(self._remove_template)
        folder = QPushButton(_file_manager_name())
        folder.clicked.connect(self._show_folder)
        buttons.addWidget(self.remove_button)
        buttons.addWidget(folder)
        buttons.addStretch()
        self.save_hint = QLabel("Type tpl: and a name in the picker to save this project as a template.")
        self.save_hint.setWordWrap(True)
        self.save_hint.setStyleSheet(f"color: {self.muted};")
        holder = QVBoxLayout()
        holder.setSpacing(8)
        holder.addLayout(buttons)
        holder.addWidget(self.save_hint)
        card.add(FreeRow(holder))
        layout.addWidget(Section("Project template", card))

        # Bins: the tree, each bin's colour and what goes in it
        card = Card(self.settings)
        self.bin_tree = QTreeWidget()
        self.bin_tree.setObjectName("OrganiseBins")
        self.bin_tree.setColumnCount(3)
        self.bin_tree.setHeaderHidden(True)
        self.bin_tree.setRootIsDecorated(False)  # (always open: what's inside a bin is shown by how far in it is)
        self.bin_tree.setIndentation(round(self.bin_tree.fontMetrics().height() * 1.3))
        self.bin_tree.setUniformRowHeights(True)
        self.bin_tree.setSelectionMode(QAbstractItemView.SingleSelection)
        self.bin_tree.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed)
        self.bin_tree.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.bin_tree.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        header = self.bin_tree.header()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.Fixed)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        self.bin_tree.itemChanged.connect(self._renamed)
        self.bin_tree.currentItemChanged.connect(lambda *_a: self._update_bin_buttons())
        tree_box = QVBoxLayout()
        tree_box.setSpacing(8)
        tree_box.addWidget(self.bin_tree)
        row = QHBoxLayout()
        add = QPushButton("Add bin")
        add.clicked.connect(lambda: self._add_bin(inside=False))
        self.add_inside = QPushButton("Add inside")
        self.add_inside.clicked.connect(lambda: self._add_bin(inside=True))
        self.take_out = QPushButton("Remove")
        self.take_out.clicked.connect(self._remove_bin)
        for b in (add, self.add_inside, self.take_out):
            row.addWidget(b)
        row.addStretch()
        tree_box.addLayout(row)
        card.add(FreeRow(tree_box))
        layout.addWidget(Section("Bins", card))

        # Kinds: where each kind goes and its colour
        card = Card(self.settings)
        self.kind_rows = {}
        for kind, shown in KIND_NAMES:
            choice = BinChoice()
            choice.picked.connect(lambda path, kind=kind: self._kind_place(kind, path))
            controls = QHBoxLayout()
            controls.setSpacing(8)
            controls.addWidget(choice)
            colour = None
            if kind not in NO_COLOUR:
                colour = ColourButton(self.settings)
                colour.picked.connect(lambda c, kind=kind: self._kind_colour(kind, c))
                controls.addWidget(colour)
            else:  # (the dropdowns in one column all the same: an unseen one holds its place)
                gap = ColourButton(self.settings)
                policy = gap.sizePolicy()
                policy.setRetainSizeWhenHidden(True)
                gap.setSizePolicy(policy)
                gap.hide()
                controls.addWidget(gap)
            card.add(SettingRow(self._title(shown), "", controls, self.muted))
            self.kind_rows[kind] = (choice, colour)
        layout.addWidget(Section("Clips by kind", card))

        # Folders on disk
        card = Card(self.settings)
        self.folder_box = QVBoxLayout()
        self.folder_box.setSpacing(6)
        folders = QVBoxLayout()
        folders.setSpacing(8)
        folders.addLayout(self.folder_box)
        add_folder = QPushButton("Add folder…")
        add_folder.clicked.connect(self._add_folder)
        line = QHBoxLayout()
        line.addWidget(add_folder)
        line.addStretch()
        folders.addLayout(line)
        card.add(FreeRow(folders))
        layout.addWidget(Section("Clips by folder", card))
        layout.addStretch()

        self._fill()
        return page

    def _title(self, words):
        from .help_text import HELP
        title = QLabel(words)
        title.setObjectName("SettingTitle")
        if HELP.get(words):
            title.setToolTip(HELP[words])
        return title

    # -- filling in what the template says --
    def _fill(self):
        self.chooser.blockSignals(True)
        self.chooser.clear()
        names = self._names()
        self.chooser.addItems(names or ["No templates"])
        self.chooser.setEnabled(bool(names))
        if self.name:
            self.chooser.setCurrentText(self.name)
        self.chooser.blockSignals(False)
        self._update_template_buttons()
        editing = self.own is not None
        for widget in [self.bin_tree, self.add_inside, self.take_out] + \
                [w for pair in self.kind_rows.values() for w in pair if w is not None]:
            widget.setEnabled(editing)
        self._fill_bins()
        self._fill_kinds()
        self._fill_folders()

    def _update_template_buttons(self):
        mine = self.name in pt.saved_templates()
        self.remove_button.setText("Reset" if self.name in pt.BUILTIN else "Delete")
        self.remove_button.setEnabled(bool(mine))
        self.save_hint.setVisible(not pt.saved_templates())

    def _goes_here(self, path):
        """What goes in a bin, in a few words: its kinds, and how many folders."""
        names = dict(KIND_NAMES, fusion="Fusion", compound="Compound", adjustment="Adjustment")  # (short: one line)
        if self.own is None:
            return ""
        kinds = [names[k] for k, _n in KIND_NAMES if self.own["places"]["kinds"].get(k) == path]
        n = sum(1 for p in self.own["places"]["folders"].values() if p == path)
        if n:
            kinds.append(f"{n} folder{'s' if n != 1 else ''}")
        return ", ".join(kinds)

    def _fill_bins(self, current=None):
        tree = self.bin_tree
        tree.blockSignals(True)
        tree.clear()
        muted = QColor(self.muted)
        colours = self.own["colours"]["bins"] if self.own else {}

        def add(parent, entries, prefix):
            for name, sub in entries:
                path = f"{prefix}/{name}" if prefix else name
                item = QTreeWidgetItem([name, "", self._goes_here(path)])
                item.setData(0, Qt.UserRole, path)
                item.setFlags(item.flags() | Qt.ItemIsEditable)
                item.setForeground(2, muted)
                (parent.addChild if parent is not None else tree.addTopLevelItem)(item)
                button = ColourButton(self.settings, colours.get(path, ""))
                button.picked.connect(lambda c, path=path: self._bin_colour(path, c))
                tree.setItemWidget(item, 1, button)
                add(item, sub, path)
                if path == current:
                    tree.setCurrentItem(item)
        add(None, self.tree, "")
        tree.expandAll()
        tree.blockSignals(False)
        width = max([tree.itemWidget(it, 1).sizeHint().width() for it in self._items()] + [120])
        tree.header().resizeSection(1, width + 8)
        self._fit_tree()
        QTimer.singleShot(0, self._fit_tree)  # (again once it's laid out: the rows' real height)
        self._update_bin_buttons()

    def _fit_tree(self):
        """The list as tall as its bins - the page scrolls, never the list."""
        items = self._items()
        tree = self.bin_tree
        bottom = tree.visualItemRect(items[-1]).bottom() if items else -1
        if bottom < 0:
            bottom = len(items) * max(tree.sizeHintForRow(0), tree.fontMetrics().height() + 12)
        tree.setFixedHeight(max(bottom, tree.fontMetrics().height() + 12) + 4)

    def _items(self):
        out = []

        def walk(item):
            out.append(item)
            for i in range(item.childCount()):
                walk(item.child(i))
        for i in range(self.bin_tree.topLevelItemCount()):
            walk(self.bin_tree.topLevelItem(i))
        return out

    def _update_bin_buttons(self):
        chosen = self.bin_tree.currentItem() is not None and self.own is not None
        self.add_inside.setEnabled(chosen)
        self.take_out.setEnabled(chosen)

    def _fill_kinds(self):
        bins = self._bins()
        for kind, (choice, colour) in self.kind_rows.items():
            choice.fill(bins, self.own["places"]["kinds"].get(kind, "") if self.own else "")
            if colour is not None:
                colour.set_colour(self.own["colours"]["kinds"].get(kind, "") if self.own else "")

    def _fill_folders(self):
        while self.folder_box.count():
            item = self.folder_box.takeAt(0)
            if item.layout() is not None:
                while item.layout().count():
                    w = item.layout().takeAt(0).widget()
                    if w is not None:
                        w.deleteLater()
            elif item.widget() is not None:
                item.widget().deleteLater()
        if self.own is None:
            return
        bins = self._bins()
        for folder, path in self.own["places"]["folders"].items():
            line = QHBoxLayout()
            line.setSpacing(8)
            field = QLineEdit(folder)
            field.setToolTip("A folder, or a pattern: ~/footage/*_broll_*")
            field.editingFinished.connect(lambda field=field, old=folder: self._folder_renamed(old, field.text()))
            choice = BinChoice()
            choice.fill(bins, path)
            choice.picked.connect(lambda p, folder=folder: self._folder_place(folder, p))
            split = QCheckBox()  # (its folders as bins inside its bin: the switch stands in for it)
            split.setChecked(folder in self.own["places"]["split"])
            split.toggled.connect(lambda on, folder=folder: self._folder_split(folder, on))
            split.hide()
            switch = ToggleSwitch(self.settings, split)
            words = QLabel("Subfolders")
            words.setStyleSheet(f"color: {self.muted};")
            tip = "Each file into a bin named after its folder, inside this bin"
            for w in (switch, words):
                w.setToolTip(tip)
            words.mousePressEvent = lambda _e, split=split: split.setChecked(not split.isChecked())
            remove = QPushButton("✕")
            remove.setObjectName("QuietButton")
            remove.setFixedWidth(remove.sizeHint().height())
            remove.setToolTip("Remove")
            remove.clicked.connect(lambda _c=False, folder=folder: self._remove_folder(folder))
            line.addWidget(field, 1)
            line.addWidget(choice)
            line.addSpacing(4)
            line.addWidget(split)
            line.addWidget(switch, 0, Qt.AlignVCenter)
            line.addWidget(words)
            line.addSpacing(4)
            line.addWidget(remove)
            self.folder_box.addLayout(line)

    # -- changes --
    def _choose(self, name):
        self.load(name)
        self._fill()

    def _recolour(self):
        """Every clip in the open project its colour again (organise.py, colours only) - how it went comes as a
        message on screen when it's done."""
        organise.start(colours=True)
        self.recolour.setEnabled(False)
        self.recolour.setText("Recolouring\u2026")

        def back():
            try:
                self.recolour.setText("Recolour all")
                self.recolour.setEnabled(True)
            except RuntimeError:  # (Settings closed meanwhile)
                pass
        QTimer.singleShot(4000, back)

    def _remove_template(self):
        if self.name and pt.delete(self.name):
            self.load(self.name if self.name in pt.BUILTIN else None)
            self._fill()

    def _show_folder(self):
        from .file_manager import open_folder
        os.makedirs(pt.TEMPLATES_DIR, exist_ok=True)
        open_folder(pt.TEMPLATES_DIR, self.settings.files.get("file_manager", ""))

    def _changed(self, bins=False, current=None):
        self.save()
        if bins:
            self._fill_bins(current)
            self._fill_kinds()
            self._fill_folders()

    def _renamed(self, item, column):
        if column != 0:
            return
        old = item.data(0, Qt.UserRole)
        name = item.text(0).strip().replace("/", "_")
        parent_path = old.rpartition("/")[0]
        entry, siblings = _find(self.tree, old)
        if not name or entry is None or any(e[0] == name for e in siblings if e is not entry):
            QTimer.singleShot(0, lambda: self._fill_bins(old))  # (empty, or a name its neighbour has: as it was)
            return
        new = f"{parent_path}/{name}" if parent_path else name
        entry[0] = name
        organise.bin_moved(self.own, old, new)
        QTimer.singleShot(0, lambda: self._changed(bins=True, current=new))  # (not inside the tree's own signal)

    def _add_bin(self, inside):
        item = self.bin_tree.currentItem()
        parent_path = item.data(0, Qt.UserRole) if inside and item is not None else ""
        siblings = _find(self.tree, parent_path)[0][1] if parent_path else self.tree
        taken = {e[0] for e in siblings}
        name = next(n for n in (f"new_bin{'' if i == 1 else f'_{i}'}" for i in range(1, 999)) if n not in taken)
        siblings.append([name, []])
        path = f"{parent_path}/{name}" if parent_path else name
        self._changed(bins=True, current=path)
        new_item = self.bin_tree.currentItem()
        if new_item is not None:
            self.bin_tree.editItem(new_item, 0)

    def _remove_bin(self):
        item = self.bin_tree.currentItem()
        if item is None:
            return
        path = item.data(0, Qt.UserRole)
        entry, siblings = _find(self.tree, path)
        if entry is None:
            return
        siblings.remove(entry)
        organise.bin_moved(self.own, path, None)
        self._changed(bins=True)

    def _was(self, old, new):
        """A colour the template gave and gives no more: a clip in it is still Organise's to change."""
        was = self.own["colours"].setdefault("was", [])
        if old and old != new and old not in was:
            was.append(old)

    def _bin_colour(self, path, colour):
        self._was(self.own["colours"]["bins"].get(path, ""), colour)
        self.own["colours"]["bins"][path] = colour
        self._changed()

    def _kind_place(self, kind, path):
        self.own["places"]["kinds"][kind] = path
        self._changed(bins=True, current=self._current_path())

    def _kind_colour(self, kind, colour):
        self._was(self.own["colours"]["kinds"].get(kind, ""), colour)
        self.own["colours"]["kinds"][kind] = colour
        self._changed()

    def _current_path(self):
        item = self.bin_tree.currentItem()
        return item.data(0, Qt.UserRole) if item is not None else None

    def _add_folder(self):
        if self.own is None:
            return
        folder = QFileDialog.getExistingDirectory(self.dialog, "A folder whose files go in a bin", os.path.expanduser("~"))
        if not folder:
            return
        folder = _home(folder)
        if folder not in self.own["places"]["folders"]:
            self.own["places"]["folders"][folder] = ""
        self._changed(bins=True, current=self._current_path())

    def _folder_renamed(self, old, text):
        text = _home(text.strip())
        folders = self.own["places"]["folders"]
        if text == old or old not in folders:
            return
        if not text or text in folders:  # (emptied, or another row's: as it was)
            QTimer.singleShot(0, self._fill_folders)
            return
        self.own["places"]["folders"] = {(text if f == old else f): p for f, p in folders.items()}  # (its place kept)
        self.own["places"]["split"] = [text if f == old else f for f in self.own["places"]["split"]]
        QTimer.singleShot(0, lambda: self._changed(bins=True, current=self._current_path()))

    def _folder_place(self, folder, path):
        self.own["places"]["folders"][folder] = path
        self._changed(bins=True, current=self._current_path())

    def _folder_split(self, folder, on):
        split = [f for f in self.own["places"]["split"] if f != folder]
        self.own["places"]["split"] = split + [folder] if on else split
        self._changed()

    def _remove_folder(self, folder):
        self.own["places"]["folders"].pop(folder, None)
        self.own["places"]["split"] = [f for f in self.own["places"]["split"] if f != folder]
        QTimer.singleShot(0, lambda: self._changed(bins=True, current=self._current_path()))


def _file_manager_name():
    from .settings_dialog import _file_manager_name as name
    return name()
