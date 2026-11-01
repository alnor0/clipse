"""The connection check window: each step with a tick or a cross and,
for anything wrong, exactly what to do about it. Shown when the service
can't connect to Resolve, and from Settings -> General."""
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QWidget, QApplication)

from . import clipboard, diagnose


class ConnectionCheckDialog(QDialog):
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("Clipse - connection check")
        self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        self.setMinimumWidth(520)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(12)
        title = QLabel("Connection check")
        title.setObjectName("DialogTitle")
        layout.addWidget(title)
        self.rows = QWidget()
        self.rows_layout = QVBoxLayout(self.rows)
        self.rows_layout.setContentsMargins(0, 0, 0, 0)
        self.rows_layout.setSpacing(10)
        layout.addWidget(self.rows)
        self.summary = QLabel("")
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        buttons = QHBoxLayout()
        self.copy_button = QPushButton("Copy report")
        self.copy_button.setToolTip("Copies the results - handy when asking for help")
        self.copy_button.clicked.connect(self._copy)
        again = QPushButton("Check again")
        again.clicked.connect(self.run)
        close = QPushButton("Close")
        close.setDefault(True)
        close.clicked.connect(self.accept)
        buttons.addWidget(self.copy_button)
        buttons.addStretch()
        buttons.addWidget(again)
        buttons.addWidget(close)
        layout.addLayout(buttons)
        self.checks = []
        self.run()

    def run(self):
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            self.checks = diagnose.run_checks()
        finally:
            QApplication.restoreOverrideCursor()
        old = self.rows
        self.rows = QWidget()
        self.rows_layout = QVBoxLayout(self.rows)
        self.rows_layout.setContentsMargins(0, 0, 0, 0)
        self.rows_layout.setSpacing(10)
        self.layout().replaceWidget(old, self.rows)
        old.hide()
        old.deleteLater()
        t = self.settings.theme
        colors = {"ok": t.get("color_audio", "#3ee08f"), "fail": t.get("color_macro", "#ff5f6d"),
                  "warn": t.get("favorite_marker_color", "#e5c07b"), "skip": t["picker_folder"]}
        for status, title, detail in self.checks:
            row = QWidget()
            h = QHBoxLayout(row)
            h.setContentsMargins(0, 0, 0, 0)
            h.setSpacing(10)
            mark = QLabel(diagnose.MARKS[status])
            mark.setFixedWidth(16)
            mark.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
            mark.setStyleSheet(f"color: {colors[status]}; font-weight: 600;")
            h.addWidget(mark)
            text = QLabel()
            text.setWordWrap(True)
            text.setTextInteractionFlags(Qt.TextSelectableByMouse)
            body = f"{_escape(title)}"
            if detail and status != "ok":
                muted = QColor(t["picker_folder"]).name()
                body += f"<br><span style='color:{muted}'>{_escape(detail).replace(chr(10), '<br>')}</span>"
            text.setText(body)
            h.addWidget(text, 1)
            self.rows_layout.addWidget(row)
        self.summary.setText("Everything looks good." if diagnose.all_good(self.checks) else
                             "Fix the ✗ steps, then press Check again.")
        self._fit_height()
        QTimer.singleShot(0, self._fit_height)  # once the wrapped text has its final size

    def _fit_height(self):
        self.layout().activate()
        self.resize(self.width(), self.layout().totalHeightForWidth(self.width()))

    def _copy(self):
        clipboard.set_text(diagnose.report(self.checks))
        self.copy_button.setText("Copied")


def _escape(text):
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def show_connection_check(settings=None):
    """Standalone (the service couldn't connect): a QApplication of its own if needed."""
    import sys
    from .settings import Settings
    from .theme import build_stylesheet
    app = QApplication.instance() or QApplication(sys.argv[:1])
    if settings is None:
        settings = Settings()
        settings.load()
    try:
        from .fonts import apply_ui_font
        app.setFont(apply_ui_font(app.font(), settings))
    except Exception:
        pass
    app.setStyleSheet(build_stylesheet(settings))
    dialog = ConnectionCheckDialog(settings)
    if sys.platform == "darwin":
        try:
            from .daemon import hide_dock_icon_macos
            hide_dock_icon_macos()
            from AppKit import NSApp
            NSApp.activateIgnoringOtherApps_(True)
        except Exception:
            pass
    dialog.exec()
    return app
