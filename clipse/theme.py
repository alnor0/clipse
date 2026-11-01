"""Turns a Settings object's color values into a Qt stylesheet, and a
small hex-blend helper (used for the fake "selection opacity" — same
trick as the Tk version, just applied via QSS/paint instead of tag
backgrounds)."""


def blend_hex(base_hex: str, tint_hex: str, amount: float) -> str:
    amount = max(0.0, min(1.0, amount))
    base_hex, tint_hex = base_hex.lstrip("#"), tint_hex.lstrip("#")
    base_rgb = tuple(int(base_hex[i:i + 2], 16) for i in (0, 2, 4))
    tint_rgb = tuple(int(tint_hex[i:i + 2], 16) for i in (0, 2, 4))
    blended = tuple(round(b + (t - b) * amount) for b, t in zip(base_rgb, tint_rgb))
    return "#{:02x}{:02x}{:02x}".format(*blended)


SELECTION_OPACITY = 0.4


def _chevron_file(colour):
    """A small down chevron in `colour`, as a PNG a stylesheet can point at (a Settings dropdown's arrow).
    Made once per colour, in the temp folder; "" if it can't be."""
    import os
    import tempfile
    path = os.path.join(tempfile.gettempdir(), f"clipse_chevron_{colour.lstrip('#')}.png")
    if os.path.exists(path):
        return path.replace("\\", "/")
    try:
        from PySide6.QtCore import QPointF, Qt
        from PySide6.QtGui import QColor, QImage, QPainter, QPen
        img = QImage(24, 24, QImage.Format_ARGB32)
        img.fill(Qt.transparent)
        p = QPainter(img)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(QColor(colour), 2.4, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.drawPolyline([QPointF(6.5, 9.5), QPointF(12, 15), QPointF(17.5, 9.5)])
        p.end()
        return path.replace("\\", "/") if img.save(path) else ""
    except Exception:
        return ""


def window_sheet(settings, name) -> str:
    """A window's own stylesheet with every word in it at that window's zoom (fonts.window_zoom: "settings",
    "insert_as").
    With the app's stylesheet on, a font set on a window never reached its labels - only a stylesheet does. A
    window's own sheet wins over the app's whatever the selector, so the titles' sizes are said again here."""
    from .fonts import HERO, TITLE, base_points, rel
    step = rel(settings, name)

    def size(k):
        return f"{base_points(settings) * k * step:.2f}pt"
    return f"""
    QWidget {{ font-size: {size(1.0)}; }}
    QLabel#SettingsTitle {{ font-size: {size(1.0)}; font-weight: 600; }}
    QLabel#AboutTitle {{ font-size: {size(HERO)}; font-weight: 600; }}
    QLabel#DialogTitle {{ font-size: {size(TITLE)}; font-weight: 600; }}
    QLabel#AboutName {{ font-size: {size(TITLE)}; font-weight: 700; }}
    QPushButton#NavArrow {{ font-size: {size(HERO)}; }}
    """


def settings_sheet(settings) -> str:
    return window_sheet(settings, "settings")


def build_stylesheet(settings) -> str:
    t = settings.theme
    d = settings.display
    select_bg = blend_hex(t["picker_bg"], t["picker_select_bg"], SELECTION_OPACITY)
    from . import look
    r_control, r_tile, r_card = (round(look.radius(settings, k)) for k in ("control", "tile", "card"))  # (3 corners)
    accent = t.get("picker_accent", t["color_video"])
    from . import drag_spinbox
    drag_spinbox.ACCENT = accent  # (a number field's lit edge while it's dragged)
    bar = t.get("picker_bar_bg", t["picker_bg"])
    # Insert as, History, Settings: a shade lifted from the picker, with an edge - over the picker they're
    # told apart at a glance (they were the same colour as it)
    dialog_bg = blend_hex(t["picker_bg"], t["picker_text"], 0.03)
    dialog_edge = blend_hex(t["picker_bg"], t["picker_text"], 0.2)
    from .settings import is_light
    light = is_light(t["picker_bg"])
    if light:  # on a light page a card is lighter than it, not darker
        card = blend_hex(dialog_bg, "#ffffff", 0.4)
    else:
        card = blend_hex(dialog_bg, t["picker_text"], 0.05)
    card_line = blend_hex(dialog_bg, t["picker_text"], 0.09)
    # Settings like Vicinae's: a dark card needs no edge (a light one keeps a faint one, or it melts into the page);
    # the sidebar's search is a shade deeper than the sidebar, with no edge either
    card_edge = card_line if light else card
    field_deep = blend_hex(bar, t["picker_text"], 0.06) if light else blend_hex(bar, "#000000", 0.22)
    # ...and in a dialog (History): a shade deeper than the dialog itself, not than the sidebar
    dialog_field = blend_hex(dialog_bg, t["picker_text"], 0.06) if light else blend_hex(dialog_bg, "#000000", 0.16)
    button = blend_hex(card, t["picker_text"], 0.1)  # (a button shows on a card in every theme)
    hover = blend_hex(t["picker_bg"], t["picker_text"], 0.06)

    from .fonts import HERO, TINY, TITLE, base_points, rel
    SETTINGS = rel(settings, "settings")  # (the titles only Settings has, at its zoom)

    def size(step):  # a font-size on the one scale (fonts.py)
        return f"{base_points(settings) * step:.2f}pt"

    def soft(alpha):  # the text's colour, see-through: a button reads the same on any surface (Vicinae's)
        h = t["picker_text"].lstrip("#")
        return f"rgba({int(h[0:2], 16)}, {int(h[2:4], 16)}, {int(h[4:6], 16)}, {alpha})"

    # chosen text in a field: the accent, softened - the list's selection colour was nearly a card's own, and in
    # Insert as a field's text chosen by a click didn't show (2026-10-21: "the highlight is not visible")
    a = accent.lstrip("#")
    text_select = f"rgba({int(a[0:2], 16)}, {int(a[2:4], 16)}, {int(a[4:6], 16)}, 0.5)"
    return f"""
    QWidget#PickerRoot {{
        background: transparent;
    }}
    QLineEdit#PickerSearch {{
        background: transparent;
        border: none;
        padding: 0;
        color: {t['picker_input_text']};
        selection-background-color: {select_bg};
    }}
    QListView#PickerList {{
        background: transparent;
        border: none;
        outline: 0;
    }}
    QLabel#PickerCount, QLabel#FooterHint {{
        color: {t['picker_folder']};
        background: transparent;
    }}
    QLineEdit {{
        background: {t['picker_bg']};
        color: {t['picker_input_text']};
        border: 1px solid {t['picker_border']};
        border-radius: {r_control}px;
        padding: 5px 8px;
        selection-background-color: {text_select};
        selection-color: {t['picker_input_text']};
    }}
    QListView {{
        background: {t['picker_bg']};
        color: {t['picker_text']};
        border: 1px solid {t['picker_border']};
        outline: 0;
    }}
    QListView::item {{
        padding: {d['row_spacing']}px 4px;
    }}
    QListView::item:selected {{
        background: {select_bg};
        color: {t['picker_text']};
    }}
    QLabel#FooterLink {{
        color: {t['picker_folder']};
        background: transparent;
    }}
    QLabel#FooterLink:hover {{
        color: {t['picker_text']};
    }}
    QLabel#FolderText {{
        color: {t['picker_folder']};
    }}
    QDialog {{
        background: {t['picker_bg']};
        color: {t['picker_text']};
    }}
    QTabWidget::pane {{
        background: {t['picker_bg']};
        color: {t['picker_text']};
        border: 1px solid {t['picker_border']};
        border-radius: {r_control}px;
        top: -1px;
    }}
    QDialog#AppDialog {{
        background: {dialog_bg};
        border: 1px solid {dialog_edge};
    }}
    QDialog#AppDialog QWidget#SettingsPage {{
        background: {dialog_bg};
    }}
    /* Sections are flat: a heading and a hairline, no boxes inside boxes */
    QGroupBox {{
        background: transparent;
        border: none;
        border-top: 1px solid {t['picker_border']};
        margin-top: 22px;
        padding-top: 10px;
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        left: 0px;
        padding: 0 0 4px 0;
        color: {t['picker_text']};
        font-weight: 600;
    }}
    QWidget#SettingsSidebar {{
        background: {bar};
        border-right: 1px solid {t['picker_border']};
    }}
    QLineEdit#SettingsSearch, QLineEdit#DialogSearch {{
        padding: 7px 8px 7px 4px;
        border-radius: {r_control}px;
        background: {field_deep};
        border: 1px solid {field_deep};
    }}
    QLineEdit#DialogSearch {{
        background: {dialog_field};
        border: 1px solid {dialog_field};
    }}
    QLineEdit#SettingsSearch:focus, QLineEdit#DialogSearch:focus {{
        border: 1px solid {card_line};
    }}
    QListWidget#SettingsNav {{
        background: transparent;
        border: none;
        padding: 2px 0;
        outline: 0;
        color: {t['picker_text']};
    }}
    QListWidget#SettingsNav::item {{
        padding: 6px 10px;
        margin: 1px 0;
        border-radius: {r_control}px;
    }}
    QFrame#SettingsCard {{
        background: {card};
        border: 1px solid {card_edge};
        border-radius: {r_card}px;
    }}
    QFrame#SettingsHairline {{
        background: {card_line};
        border: none;
    }}
    QLabel#SectionTitle {{
        color: {t['picker_folder']};
        font-weight: 600;
        padding-left: 2px;
    }}
    QWidget#SettingRow {{
        background: transparent;
    }}
    QFrame#NavPill {{
        background: {card};
        border: 1px solid {card_edge};
        border-radius: {r_control}px;
    }}
    QPushButton#NavArrow {{
        background: transparent;
        border: none;
        border-radius: {r_control}px;
        color: {t['picker_text']};
        font-size: {size(HERO * SETTINGS)};
        padding: 0 0 2px 0;
    }}
    QPushButton#NavArrow:hover {{
        background: {button};
    }}
    QPushButton#NavArrow:disabled {{
        color: {t['picker_border']};
        background: transparent;
    }}
    QLabel#SettingsTitle {{
        font-size: {size(SETTINGS)};
        font-weight: 600;
        color: {t['picker_text']};
    }}
    /* Reset page, Clear: a soft fill you can see at rest (bare text was too faint to find), the text a touch
       quieter than a main button's */
    QPushButton#QuietButton {{
        background: {soft(0.06)};
        border: none;
        border-radius: {r_control}px;
        padding: 5px 12px;
        color: {blend_hex(t['picker_text'], t['picker_bg'], 0.18)};
    }}
    QPushButton#QuietButton:hover {{
        background: {soft(0.11)};
        color: {t['picker_text']};
    }}
    QPushButton#QuietButton:disabled {{
        background: {soft(0.03)};
        color: {t['picker_folder']};
    }}
    QPushButton#SearchResult {{
        background: transparent;
        border: none;
        border-radius: {r_tile}px;
        text-align: left;
    }}
    QPushButton#SearchResult:hover {{
        background: {hover};
    }}
    /* Settings > Organise: the template's bins (organise_page.py) - rows like the sidebar's, a clip colour beside each */
    QTreeWidget#OrganiseBins {{
        background: transparent;
        border: none;
        outline: 0;
        color: {t['picker_text']};
    }}
    QTreeWidget#OrganiseBins::item {{
        padding: 3px 4px;
        border-radius: {r_control}px;
    }}
    QTreeWidget#OrganiseBins::item:hover {{
        background: {soft(0.05)};
    }}
    QTreeWidget#OrganiseBins::item:selected {{
        background: {t['picker_select_bg']};
        color: {t['picker_text']};
    }}
    QPushButton#ColourButton {{
        background: transparent;
        border: none;
        border-radius: {r_control}px;
        padding: 4px 8px;
        text-align: left;
        color: {t['picker_text']};
    }}
    QPushButton#ColourButton:hover {{
        background: {soft(0.08)};
    }}
    QPushButton#ColourButton:disabled {{
        color: {t['picker_folder']};
    }}
    /* About's column, like Vicinae's: the text's colour at 7 % (12 % under the mouse), no edge, radius 6 */
    QPushButton#AboutButton {{
        background: {soft(0.07)};
        border: none;
        border-radius: {r_control}px;
        padding: 0 14px;
        color: {t['picker_text']};
    }}
    QPushButton#AboutButton:hover {{
        background: {soft(0.12)};
    }}
    QPushButton#AboutButton:disabled {{
        background: {soft(0.04)};
        color: {t['picker_folder']};
    }}
    QLabel#AboutTitle {{
        font-size: {size(HERO * SETTINGS)};
        font-weight: 600;
        color: {t['picker_text']};
    }}
    QLabel#AboutName {{
        font-size: {size(TITLE)};
        font-weight: 700;
        color: {t['picker_text']};
    }}
    QListWidget#SettingsNav::item:hover {{
        color: {t['picker_text']};
    }}
    QListWidget#SettingsNav::item:selected {{
        background: {t['picker_select_bg']};
        color: {t['picker_text']};
    }}
    QTabWidget#SettingsPages::pane {{
        border: none;
        background: transparent;
    }}
    QScrollArea#SettingsScroll, QScrollArea#SettingsScroll > QWidget > QWidget {{
        background: {dialog_bg};
        border: none;
    }}
    /* slim scroll bar for the Settings pages (and History's list) */
    QScrollArea#SettingsScroll QScrollBar:vertical, QListWidget#HistoryList QScrollBar:vertical {{
        background: transparent;
        width: 8px;
        margin: 2px 0 2px 0;
    }}
    QScrollArea#SettingsScroll QScrollBar::handle:vertical, QListWidget#HistoryList QScrollBar::handle:vertical {{
        background: {t['picker_border']};
        border-radius: 4px;
        min-height: 30px;
    }}
    QScrollArea#SettingsScroll QScrollBar::handle:vertical:hover,
    QListWidget#HistoryList QScrollBar::handle:vertical:hover {{
        background: {t['picker_folder']};
    }}
    QScrollArea#SettingsScroll QScrollBar::add-line:vertical,
    QScrollArea#SettingsScroll QScrollBar::sub-line:vertical,
    QScrollArea#SettingsScroll QScrollBar::add-page:vertical,
    QScrollArea#SettingsScroll QScrollBar::sub-page:vertical,
    QListWidget#HistoryList QScrollBar::add-line:vertical, QListWidget#HistoryList QScrollBar::sub-line:vertical,
    QListWidget#HistoryList QScrollBar::add-page:vertical, QListWidget#HistoryList QScrollBar::sub-page:vertical {{
        height: 0; background: transparent;
    }}
    QLabel#DialogTitle {{
        font-size: {size(TITLE)};
        font-weight: 600;
        color: {t['picker_text']};
    }}
    QPushButton:default {{
        background: {accent};
        color: {t['picker_bg']};
        font-weight: 600;
    }}
    QTabBar::tab {{
        background: {t['picker_bg']};
        color: {t['picker_folder']};
        padding: 6px 14px;
        border: 1px solid transparent;
        border-bottom: none;
        border-top-left-radius: {r_control}px;
        border-top-right-radius: {r_control}px;
    }}
    QTabBar::tab:selected {{
        color: {t['picker_text']};
        border: 1px solid {t['picker_border']};
        border-bottom: 1px solid {t['picker_bg']};
        background: {t['picker_bg']};
    }}
    QCheckBox, QLabel, QGroupBox {{
        color: {t['picker_text']};
    }}
    QCheckBox::indicator {{
        width: 15px;
        height: 15px;
        border: 1px solid {t['picker_folder']};
        border-radius: 3px;
        background: {t.get('picker_bar_bg', t['picker_bg'])};
    }}
    QCheckBox::indicator:checked {{
        background: {accent};
        border: 1px solid {accent};
    }}
    QAbstractSpinBox, QKeySequenceEdit, QLineEdit, QPlainTextEdit {{
        background: {bar};
        color: {t['picker_input_text']};
        border: 1px solid {t['picker_border']};
        border-radius: {r_control}px;
    }}
    QAbstractSpinBox {{
        padding: 6px 8px;
        selection-background-color: {text_select};
        selection-color: {t['picker_input_text']};
    }}
    QPlainTextEdit {{
        padding: 6px 6px;
        selection-background-color: {text_select};
        selection-color: {t['picker_input_text']};
    }}
    /* Spin boxes have no arrow buttons here. Once a spin box gets a
       border from a stylesheet, Qt still reserves room for those hidden
       buttons and shrinks the number field inside to 1px wide - the box
       looks empty and can't be typed in. Giving the buttons zero size
       fixes that. */
    QAbstractSpinBox::up-button, QAbstractSpinBox::down-button {{
        subcontrol-origin: border;
        width: 0px;
        height: 0px;
        border: none;
    }}
    /* The number field inside a spin box is itself a QLineEdit - keep the
       general QLineEdit rule (padding + border) off it. */
    QAbstractSpinBox QLineEdit {{
        background: transparent;
        border: none;
        padding: 0;
        margin: 0;
    }}
    QComboBox {{
        combobox-popup: 0;
        background: {bar};
        color: {t['picker_input_text']};
        border: 1px solid {t['picker_border']};
        border-radius: {r_control}px;
        padding: 4px 8px;
    }}
    /* The drop-down list. Its container frame and scroll arrows are
       styled too - left alone they show as white bars above and below. */
    /* in a Settings card: rounded and outlined, the card showing through (Vicinae's) */
    QFrame#SettingsCard QComboBox, QFrame#SettingsCard QAbstractSpinBox, QFrame#SettingsCard QKeySequenceEdit,
    QFrame#SettingsCard QLineEdit {{
        background: transparent;
        border: 1px solid {card_line};
        border-radius: {r_control}px;
    }}
    QFrame#SettingsCard QComboBox {{
        padding: 5px 10px;
    }}
    QFrame#SettingsCard QComboBox::drop-down {{
        border: none;
        width: 26px;
    }}
    QFrame#SettingsCard QComboBox::down-arrow {{
        image: url("{_chevron_file(t['picker_folder'])}");
        width: 12px;
        height: 12px;
    }}
    QFrame#SettingsCard QAbstractSpinBox QLineEdit {{
        border: none;
    }}
    QComboBoxPrivateContainer {{
        background: {t['picker_bg']};
        border: 1px solid {t['picker_border']};
        padding: 0;
        margin: 0;
    }}
    QComboBox QAbstractItemView {{
        background: {t['picker_bg']};
        color: {t['picker_text']};
        border: 1px solid {t['picker_border']};
        outline: 0;
        padding: 2px 0;
        selection-background-color: {select_bg};
        selection-color: {t['picker_text']};
    }}
    QComboBox QAbstractItemView::item {{
        padding: 4px 8px;
        min-height: 18px;
    }}
    QComboBoxMenuScroller {{
        background: {t['picker_bg']};
    }}
    QPushButton {{
        background: {soft(0.07)};
        color: {t['picker_text']};
        border: none;
        border-radius: {r_control}px;
        padding: 6px 12px;
    }}
    QPushButton#IconButton {{
        background: transparent;
        padding: 0;
    }}
    QPushButton#IconButton:hover {{
        background: {button};
    }}
    QPushButton:hover {{
        background: {soft(0.12)};
    }}
    QMenu {{
        background: {t['picker_bg']};
        color: {t['picker_text']};
        border: 1px solid {t['picker_border']};
        border-radius: {r_control}px;
        padding: 6px 0px;
    }}
    QMenu::item {{
        padding: 5px 28px 5px 16px;
        background: transparent;
    }}
    QMenu::item:selected {{
        background: {t['picker_select_bg']};
    }}
    QMenu::item:disabled {{
        color: {t['picker_folder']};
        font-size: {size(TINY)};
        padding-top: 7px;
    }}
    QMenu::separator {{
        height: 1px;
        background: {t['picker_border']};
        margin: 5px 10px;
    }}
    QPushButton#LinkButton {{
        background: transparent;
        color: {accent};
        padding: 2px 0px;
    }}
    QPushButton#LinkButton:hover {{
        background: transparent;
        text-decoration: underline;
    }}
    QToolTip {{
        background: {t['picker_bg']};
        color: {t['picker_text']};
        border: 1px solid {t['picker_border']};
        padding: 5px 8px;
    }}
    """
