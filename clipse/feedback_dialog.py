"""Send feedback (Settings > About - 2026-10-19: one window for a problem and an idea, as Raycast and Linear do, with
pictures): Problem | Idea a small switch beside the title, a few words, pictures (pasted, dragged in or picked - small,
each with a cross; "Add pictures" a quiet button), an email to answer to, at the bottom with a problem the logs (on: a
switch) and Send. Kept small (the same day: "large buttons and stuff" - two big tiles came first). Sent by feedback.py; when that doesn't
work, Save as a file keeps it all on the Desktop instead."""
import sys
import threading

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QObject, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QImage, QKeySequence, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QDialog, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QPushButton,
                               QVBoxLayout, QWidget)

from . import feedback, look
from .fonts import SMALL, at as font_at
from .glyphs import draw_glyph

KINDS = (("problem", "Problem", "bug", "What happened?"), ("idea", "Idea", "idea", "What would help?"))
LONGEST_SIDE = 2560      # a picture is made smaller than this before it goes
JPEG_OVER = 3_000_000    # ... and a JPEG when a PNG of it is bigger


def _image_bytes(image):
    """(type, bytes) of a picture, made small enough to send."""
    if max(image.width(), image.height()) > LONGEST_SIDE:
        image = image.scaled(LONGEST_SIDE, LONGEST_SIDE, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    for kind, fmt, quality in (("image/png", "PNG", -1), ("image/jpeg", "JPG", 88)):
        data = QByteArray()
        buffer = QBuffer(data)
        buffer.open(QIODevice.WriteOnly)
        (image.convertToFormat(QImage.Format_RGB32) if fmt == "JPG" else image).save(buffer, fmt, quality)
        if fmt == "JPG" or data.size() <= JPEG_OVER:
            return kind, bytes(data.data())


class KindTiles(QWidget):
    """Problem | Idea: a small switch of two, each with its symbol - the chosen one lit as a chosen tile is."""
    changed = Signal(str)
    H, PAD, GLYPH = 30, 12, 14

    def __init__(self, settings, value="problem"):
        super().__init__()
        self.settings = settings
        self.value = value
        self._hover = None
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        fm = QFontMetricsF(font_at(SMALL, self.font()))
        self._widths = [round(self.PAD * 2 + self.GLYPH + 6 + fm.horizontalAdvance(label)) for _k, label, _g, _a in KINDS]
        self.setFixedSize(sum(self._widths) + 6, self.H)

    def _rect(self, i):
        x = 3 + sum(self._widths[:i])
        return QRectF(x, 3, self._widths[i], self.H - 6)

    def _hit(self, pos):
        return next((i for i in range(len(KINDS)) if self._rect(i).contains(pos)), None)

    def set_value(self, key):
        if key != self.value:
            self.value = key
            self.update()
            self.changed.emit(key)

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
            self.set_value(KINDS[hit][0])

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Left, Qt.Key_Right):
            self.set_value(KINDS[0 if event.key() == Qt.Key_Left else 1][0])
        else:
            super().keyPressEvent(event)

    def focusInEvent(self, event):
        self.update()
        super().focusInEvent(event)

    def focusOutEvent(self, event):
        self.update()
        super().focusOutEvent(event)

    def paintEvent(self, event):
        t = self.settings.theme
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        whole = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        _pen, ground = look.tile_colours(self.settings)
        p.setPen(Qt.NoPen)
        p.setBrush(ground)
        r_control = look.radius(self.settings, "control")
        p.drawRoundedRect(whole, r_control + 2, r_control + 2)
        font = font_at(SMALL, self.font())
        p.setFont(font)
        fm = QFontMetricsF(font)
        for i, (key, label, glyph, _ask) in enumerate(KINDS):
            r = self._rect(i)
            on = key == self.value
            if on or i == self._hover:
                pen, fill = look.tile_colours(self.settings, chosen=on, hover=i == self._hover, focus=on and self.hasFocus())
                p.setPen(pen if on else Qt.NoPen)
                p.setBrush(fill)
                p.drawRoundedRect(r.adjusted(0.5, 0.5, -0.5, -0.5), r_control, r_control)
            colour = QColor(t["picker_text"])
            if not on:
                colour.setAlphaF(0.66)
            x = r.left() + self.PAD
            draw_glyph(p, glyph, QPointF(x + self.GLYPH / 2, r.center().y()), self.GLYPH, colour)
            p.setPen(colour)
            p.drawText(QRectF(x + self.GLYPH + 6, r.top(), fm.horizontalAdvance(label) + 2, r.height()),
                       Qt.AlignLeft | Qt.AlignVCenter, label)
        p.end()


class Pictures(QWidget):
    """The pictures added: small, each with a cross under the mouse; after them a small square to add more (up to
    feedback.MAX_IMAGES) - with none yet, a quiet "Add pictures" button."""
    add_clicked = Signal()
    changed = Signal()
    H, GAP, BUTTON_H = 44, 6, 28

    def __init__(self, settings):
        super().__init__()
        self.settings = settings
        self.items = []          # [(QImage thumbnail, (type, bytes))]
        self._hover = None       # index, or "add"
        self.setMouseTracking(True)
        self.setToolTip("Paste a picture (Ctrl+V) or drag one in, too")
        self._fit()

    def _fit(self):
        self.setFixedHeight((self.H if self.items else self.BUTTON_H) + 2)

    def add(self, image):
        if len(self.items) >= feedback.MAX_IMAGES or image.isNull():
            return False
        thumb = image.scaled(int(self.H * 3), self.H * 2, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.items.append((thumb, _image_bytes(image)))
        self._fit()
        self.update()
        self.changed.emit()
        return True

    def images(self):
        return [data for _thumb, data in self.items]

    def _rects(self):
        rects, x = [], 1.0
        for thumb, _data in self.items:
            w = max(self.H * 0.6, min(self.H * 1.9, self.H * thumb.width() / max(1, thumb.height())))
            rects.append(QRectF(x, 1, w, self.H))
            x += w + self.GAP
        add = None
        if len(self.items) < feedback.MAX_IMAGES:
            if self.items:
                add = QRectF(x, 1, self.H, self.H)
            else:  # (none yet: a quiet button, as wide as its words)
                fm = QFontMetricsF(font_at(SMALL, self.font()))
                add = QRectF(1, 1, 12 + 14 + 6 + fm.horizontalAdvance("Add pictures") + 12, self.BUTTON_H)
        return rects, add

    def _cross(self, r):
        return QRectF(r.right() - 19, r.top() + 3, 16, 16)

    def _hit(self, pos):
        rects, add = self._rects()
        for i, r in enumerate(rects):
            if r.contains(pos):
                return i
        return "add" if add is not None and add.contains(pos) else None

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
        if event.button() != Qt.LeftButton:
            return
        hit = self._hit(event.position())
        if hit == "add":
            self.add_clicked.emit()
        elif hit is not None and self._cross(self._rects()[0][hit]).adjusted(-4, -4, 4, 4).contains(event.position()):
            del self.items[hit]
            self._hover = None
            self._fit()
            self.update()
            self.changed.emit()

    def paintEvent(self, event):
        t = self.settings.theme
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        rects, add = self._rects()
        corner = look.radius(self.settings, "tile")
        for i, ((thumb, _data), r) in enumerate(zip(self.items, rects)):
            path = QPainterPath()
            path.addRoundedRect(r, corner, corner)
            p.save()
            p.setClipPath(path)
            scaled = thumb.scaled(r.size().toSize() * 2, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            src = QRectF((scaled.width() - r.width() * 2) / 2, (scaled.height() - r.height() * 2) / 2,
                         r.width() * 2, r.height() * 2)
            p.drawImage(r, scaled, src)
            p.restore()
            edge = QColor(t["picker_text"])
            edge.setAlphaF(0.14)
            p.setPen(QPen(edge, 1))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(r.adjusted(0.5, 0.5, -0.5, -0.5), corner, corner)
            if self._hover == i:
                c = self._cross(r)
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(0, 0, 0, 170))
                p.drawEllipse(c)
                p.setPen(QPen(QColor("#ffffff"), 1.5, Qt.SolidLine, Qt.RoundCap))
                m = c.center()
                for dx, dy in ((1, 1), (1, -1)):
                    p.drawLine(QPointF(m.x() - 4 * dx, m.y() - 4 * dy), QPointF(m.x() + 4 * dx, m.y() + 4 * dy))
        if add is not None:
            colour = QColor(t["picker_text"])
            colour.setAlphaF(0.72)
            if self.items:
                look.paint_tile(p, add, self.settings, hover=self._hover == "add")
                draw_glyph(p, "picture_only", add.center(), 16, colour)
            else:  # (as a quiet button looks: a soft fill, no edge)
                fill = QColor(t["picker_text"])
                fill.setAlphaF(0.11 if self._hover == "add" else 0.06)
                p.setPen(Qt.NoPen)
                p.setBrush(fill)
                r_control = look.radius(self.settings, "control")
                p.drawRoundedRect(add, r_control, r_control)
                font = font_at(SMALL, self.font())
                p.setFont(font)
                draw_glyph(p, "picture_only", QPointF(add.left() + 12 + 7, add.center().y()), 14, colour)
                p.setPen(colour)
                p.drawText(add.adjusted(12 + 14 + 6, 0, 0, 0), Qt.AlignLeft | Qt.AlignVCenter, "Add pictures")
        p.end()


class _Words(QPlainTextEdit):
    """The words - a picture pasted or dropped on them goes to the pictures instead."""

    def __init__(self, take_picture):
        super().__init__()
        self._take = take_picture

    def canInsertFromMimeData(self, source):
        return source.hasImage() or source.hasUrls() or super().canInsertFromMimeData(source)

    def insertFromMimeData(self, source):
        if not self._take(source):
            super().insertFromMimeData(source)


class _Answer(QObject):
    done = Signal(bool, str)


class FeedbackDialog(QDialog):
    def __init__(self, settings, parent=None, kind="problem"):
        super().__init__(parent)
        self.settings = settings
        self.setObjectName("AppDialog")
        self.setWindowTitle("Send feedback")
        if sys.platform == "win32":  # (over Settings and the picker, which stay on top - see SettingsDialog)
            self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        self.setAcceptDrops(True)
        self.setMinimumWidth(500)
        from .fonts import apply_ui_font
        self.setFont(apply_ui_font(QFont(), settings))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(0)
        head = QHBoxLayout()
        title = QLabel("Send feedback")
        title.setObjectName("DialogTitle")
        head.addWidget(title)
        head.addStretch()
        self.kinds = KindTiles(settings, kind)
        self.kinds.changed.connect(self._kind_changed)
        head.addWidget(self.kinds)
        layout.addLayout(head)
        layout.addSpacing(14)

        self.words = _Words(self._take_mime)
        self.words.setMinimumHeight(130)
        self.words.setTabChangesFocus(True)
        layout.addWidget(self.words)
        layout.addSpacing(8)

        self.pictures = Pictures(settings)
        self.pictures.add_clicked.connect(self._pick_pictures)
        layout.addWidget(self.pictures)
        layout.addSpacing(10)

        self.email = QLineEdit(settings.display.get("feedback_email", ""))
        self.email.setPlaceholderText("Your email, to hear back (optional)")
        layout.addWidget(self.email)
        layout.addSpacing(16)

        from PySide6.QtWidgets import QCheckBox
        from .settings_cards import ToggleSwitch
        self.logs_box = QCheckBox()
        self.logs_box.setChecked(True)
        self.logs_row = QWidget()
        row = QHBoxLayout(self.logs_row)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)
        switch = ToggleSwitch(settings, self.logs_box)
        row.addWidget(switch)
        logs_label = QLabel("Include the logs")
        logs_label.setCursor(Qt.PointingHandCursor)
        logs_label.mousePressEvent = lambda _e: self.logs_box.toggle()
        row.addWidget(logs_label)
        tip = ("What Clipse noted while it ran, and your settings - they help find what went wrong. Clip names and "
               "folder paths are in there.")
        for w in (switch, logs_label):
            w.setToolTip(tip)

        bottom = QHBoxLayout()
        bottom.setSpacing(8)
        bottom.addWidget(self.logs_row)
        bottom.addSpacing(8)
        self.message = QLabel("")
        self.message.setWordWrap(True)
        self.message.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        bottom.addWidget(self.message, 1)
        self.save_button = QPushButton("Save as a file")
        self.save_button.setObjectName("QuietButton")
        self.save_button.setAutoDefault(False)
        self.save_button.setToolTip(f"Puts it all in one file on your Desktop, to email to {feedback.report.SUPPORT_EMAIL}")
        self.save_button.clicked.connect(self._save)
        self.save_button.hide()
        bottom.addWidget(self.save_button)
        self.send_button = QPushButton("Send")
        self.send_button.setDefault(True)
        self.send_button.setMinimumWidth(76)
        self.send_button.clicked.connect(self._send)
        bottom.addWidget(self.send_button)
        layout.addLayout(bottom)

        self._answer = _Answer(self)
        self._answer.done.connect(self._answered)
        self._kind_changed(kind)
        self.words.setFocus()

    # -- the kind --
    def _kind_changed(self, kind):
        self.words.setPlaceholderText(dict((k, ask) for k, _l, _g, ask in KINDS)[kind])
        self.logs_row.setVisible(kind == "problem")

    # -- pictures --
    def _take_mime(self, mime):
        """A picture (or picture files) pasted or dropped: to the pictures. False when there was none."""
        took = False
        if mime.hasImage():
            took = self.pictures.add(QImage(mime.imageData()))
        elif mime.hasUrls():
            for url in mime.urls():
                if url.isLocalFile():
                    image = QImage(url.toLocalFile())
                    if not image.isNull():
                        took = self.pictures.add(image) or took
        return took

    def _pick_pictures(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Add pictures", "", "Pictures (*.png *.jpg *.jpeg *.gif *.webp *.bmp)")
        for path in files:
            self.pictures.add(QImage(path))

    def keyPressEvent(self, event):
        if event.matches(QKeySequence.Paste):
            from PySide6.QtWidgets import QApplication
            if self._take_mime(QApplication.clipboard().mimeData()):
                return
        super().keyPressEvent(event)

    def dragEnterEvent(self, event):
        if event.mimeData().hasImage() or event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        if self._take_mime(event.mimeData()):
            event.acceptProposedAction()

    # -- sending --
    def _what(self):
        kind = self.kinds.value
        return dict(kind=kind, text=self.words.toPlainText().strip(), email=self.email.text().strip(),
                    images=self.pictures.images(), logs=kind == "problem" and self.logs_box.isChecked())

    def _say(self, text, bad=False):
        from .actions_panel import script_red
        t = self.settings.theme
        self.message.setStyleSheet(f"color: {script_red(t).name() if bad else t['picker_folder']};")
        self.message.setText(text)

    def _send(self):
        if not self.send_button.isEnabled():
            return
        what = self._what()
        if not what["text"]:
            self._say("Write a few words first", True)
            self.words.setFocus()
            return
        self.settings.display["feedback_email"] = what["email"]
        self.send_button.setEnabled(False)
        self._say("Sending…")

        def go():
            try:
                feedback.send(**what)
                self._answer.done.emit(True, "")
            except Exception as e:
                self._answer.done.emit(False, str(e))
        threading.Thread(target=go, daemon=True).start()

    def _answered(self, worked, text):
        try:
            self.send_button.setEnabled(True)
        except RuntimeError:
            return  # (closed meanwhile)
        if worked:
            self._say("Sent. Thank you!")
            self.send_button.setEnabled(False)
            QTimer.singleShot(1100, self.accept)
            return
        self._say(text, True)
        self.save_button.show()

    def _save(self):
        from . import file_manager
        try:
            path = feedback.save(**self._what())
        except OSError as e:
            self._say(f"Couldn't save it: {e}", True)
            return
        file_manager.reveal(path, self.settings.files.get("file_manager", ""))
        self._say(f"Saved as {path} - email it to {feedback.report.SUPPORT_EMAIL}")

