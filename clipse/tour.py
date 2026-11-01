"""The first-run tour: five short cards over the picker, each pointing at
the part it's about - search, insert, preview, actions, shortcuts. About
half a minute; Enter or a click for the next card, Esc to skip.

Shown the first time the picker opens (Settings -> About can
show it again), and from Actions -> Take the tour. The keys shown are the
ones you have set."""
from PySide6.QtCore import QEasingCurve, QRectF, Qt, QVariantAnimation
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget
from .fonts import SMALL, at as font_at  # (the one scale of sizes)


class Tour(QWidget):
    def __init__(self, picker):
        super().__init__(picker)
        self.picker = picker
        self.settings = picker.settings
        self.step = 0
        self.hide()
        self._fade = 1.0
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(180)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.valueChanged.connect(self._on_fade)

    def _steps(self):
        p = self.picker
        key = p._key_text
        return [
            (p.search_area, "Type to find anything",
             "Part of a name is enough - and words in keywords and comments. "
             "m: finds music, sfx: sound effects, > every action."),
            (p.list_view, "Enter puts it on the timeline",
             f"At the playhead, on the first free track. {key('toggle_staged')} stages a few to insert "
             "together; Undo Clipse\u2019s last step in Actions takes the last insert back."),
            (p.preview_button, "Look and listen first",
             f"{key('preview')} opens the preview next to the list, {key('play_pause')} plays. "
             f"{key('mark_in')} and {key('mark_out')} mark the part you want."),
            (p.actions_link, "Everything else is in Actions",
             f"{key('show_actions')} opens them - grab a frame, switch timeline or project, the check-up, "
             "Fusion tools. Type to narrow them down."),
            (p.settings_link, "Your keys",
             f"Settings ({key('toggle_settings')}) \u203a Keybindings has every key - and the rest of Settings "
             "how everything looks."),
        ]

    # -- showing --
    def start(self):
        self.step = 0
        self.setGeometry(self.picker.picker_column.geometry())
        self.raise_()
        self.show()
        self._anim.start()

    def finish(self):
        self.hide()
        self.settings.general["tour_done"] = True
        self.settings.save()
        self.picker.search_edit.setFocus()

    def go(self, delta):
        target = self.step + delta
        if target >= len(self._steps()):
            self.finish()
            return
        self.step = max(0, target)
        self._anim.stop()
        self._anim.start()

    def _on_fade(self, value):
        self._fade = float(value)
        self.update()

    def handle_key(self, event):
        k = event.key()
        if k == Qt.Key_Escape:
            self.finish()
        elif k in (Qt.Key_Left, Qt.Key_Backspace, Qt.Key_Up):
            self.go(-1)
        else:
            self.go(1)  # Enter, Space, arrows - anything moves on
        return True

    def mousePressEvent(self, event):
        self.go(-1 if event.button() == Qt.RightButton else 1)

    # -- drawing --
    def _target_rect(self, widget):
        if widget is None or not widget.isVisible():
            return None
        top_left = widget.mapTo(self.picker, widget.rect().topLeft()) - self.pos()
        rect = QRectF(top_left.x(), top_left.y(), widget.width(), widget.height()).adjusted(-6, -5, 6, 5)
        return rect.intersected(QRectF(self.rect()).adjusted(2, 2, -2, -2))

    def paintEvent(self, event):
        t = self.settings.theme
        steps = self._steps()
        widget, title, text = steps[min(self.step, len(steps) - 1)]
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        whole = QRectF(self.rect())
        spot = self._target_rect(widget)

        # the room dims, except where the card points
        scrim = QPainterPath()
        radius = max(4.0, self.settings.display.get("corner_radius", 6))
        scrim.addRoundedRect(whole, radius, radius)
        if spot is not None:
            hole = QPainterPath()
            hole.addRoundedRect(spot, radius, radius)
            scrim = scrim.subtracted(hole)
        dim = QColor(t["picker_bg"])
        dim.setAlphaF(0.78)
        p.fillPath(scrim, dim)
        if spot is not None:
            ring = QColor(t.get("picker_accent", t["picker_text"]))
            ring.setAlphaF(0.85 * self._fade)
            p.setPen(QPen(ring, 1.5))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(spot, radius, radius)

        # the card: under the spot if there's room, else above it
        base = QFont(self.picker.list_view.font())  # in step with the list's text size
        head = font_at(1.0, base, QFont.DemiBold)
        body = font_at(SMALL, base, QFont.Normal)
        hfm, bfm = QFontMetricsF(head), QFontMetricsF(body)
        card_w = min(whole.width() - 32, 440.0)
        pad = 16.0
        text_rect = bfm.boundingRect(QRectF(0, 0, card_w - 2 * pad, 1000), Qt.TextWordWrap, text)
        card_h = pad + hfm.height() + 6 + text_rect.height() + 14 + bfm.height() + pad
        x = whole.center().x() - card_w / 2
        if spot is not None and spot.bottom() + 14 + card_h <= whole.bottom() - 8:
            y = spot.bottom() + 14
        elif spot is not None and spot.top() - 14 - card_h >= whole.top() + 8:
            y = spot.top() - 14 - card_h
        else:
            y = whole.center().y() - card_h / 2
        y += (1.0 - self._fade) * 6  # a small rise as it appears
        card = QRectF(x, y, card_w, card_h)
        p.setOpacity(self._fade)
        p.setPen(QPen(QColor(t["picker_border"]), 1.0))
        p.setBrush(QColor(t.get("picker_bar_bg", t["picker_bg"])))
        p.drawRoundedRect(card, radius + 2, radius + 2)
        p.setFont(head)
        p.setPen(QColor(t["picker_text"]))
        p.drawText(QRectF(x + pad, y + pad, card_w - 2 * pad, hfm.height()), Qt.AlignLeft | Qt.AlignVCenter, title)
        p.setFont(body)
        p.setPen(QColor(t["picker_folder"]))
        p.drawText(QRectF(x + pad, y + pad + hfm.height() + 6, card_w - 2 * pad, text_rect.height()),
                   Qt.TextWordWrap, text)
        # step dots, and what moves on
        dots_y = card.bottom() - pad - bfm.height() / 2
        accent = QColor(t.get("picker_accent", t["picker_text"]))
        off = QColor(t["picker_border"])
        p.setPen(Qt.NoPen)
        for i in range(len(steps)):
            p.setBrush(accent if i == self.step else off)
            w = 14.0 if i == self.step else 6.0
            left = x + pad + sum((14.0 if j == self.step else 6.0) + 5 for j in range(i))
            p.drawRoundedRect(QRectF(left, dots_y - 3, w, 6), 3, 3)
        hint = "Enter: done" if self.step == len(steps) - 1 else "Enter: next   Esc: skip"
        p.setPen(QColor(t["picker_folder"]))
        p.drawText(QRectF(x + pad, card.bottom() - pad - bfm.height(), card_w - 2 * pad, bfm.height()),
                   Qt.AlignRight | Qt.AlignVCenter, hint)
        p.end()
