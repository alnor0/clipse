"""Ctrl + the scroll wheel zooms what's under the mouse, as Ctrl and + / - zoom what has the keyboard (2026-10-22:
"can i have zoom work with ctrl scroll wheel"): the picker, Expressions and the Actions panel by themselves, Insert as,
History and Settings. A drawing with a Ctrl + wheel of its own (Insert as's timeline: closer in) keeps it."""
from PySide6.QtCore import QEvent, QObject, Qt

NOTCH = 120  # one click of a wheel; a touchpad sends many small steps that add up to it


def _target(widget):
    """(what zooms, how) for the widget under the mouse - None when nothing of ours zooms there."""
    from .actions_panel import ActionsPanel
    from .expression_sheet import ExpressionSheet
    from .history_dialog import HistoryDialog
    from .insert_as_dialog import InsertAsDialog
    from .picker_window import PickerWindow
    from .settings_dialog import SettingsDialog
    while widget is not None:
        if getattr(widget, "OWN_CTRL_WHEEL", False):
            return None
        if isinstance(widget, ExpressionSheet):
            return widget.zoom_sheet
        if isinstance(widget, ActionsPanel):
            return widget.zoom_panel
        if isinstance(widget, (InsertAsDialog, HistoryDialog, SettingsDialog, PickerWindow)):
            return widget.zoom_window
        widget = widget.parentWidget()
    return None


class WheelZoom(QObject):
    """Installed on the app: every Ctrl + wheel in its windows comes here first."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._sum = 0

    def eventFilter(self, obj, event):
        if event.type() != QEvent.Wheel:
            return False
        mods = event.modifiers() & ~Qt.KeypadModifier
        if mods != Qt.ControlModifier:
            self._sum = 0
            return False
        from PySide6.QtWidgets import QWidget
        zoom = _target(obj) if isinstance(obj, QWidget) else None
        if zoom is None:
            return False
        delta = event.angleDelta().y() or event.angleDelta().x()
        if (delta > 0) != (self._sum > 0):
            self._sum = 0  # (turned the other way: start counting again)
        self._sum += delta
        while abs(self._sum) >= NOTCH:
            step = 1 if self._sum > 0 else -1
            self._sum -= step * NOTCH
            zoom(step)
        event.accept()
        return True


def install(app):
    """Once, as the app starts."""
    if getattr(app, "_wheel_zoom", None) is None:
        app._wheel_zoom = WheelZoom(app)
        app.installEventFilter(app._wheel_zoom)
