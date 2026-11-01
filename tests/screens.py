"""Renders Settings pages and the Insert as dialog to PNGs in build/screens -
to look at a UI change without Resolve.  python3 tests/screens.py"""
import _setup
from clipse.settings import Settings
from clipse.theme import build_stylesheet
from clipse.settings_dialog import SettingsDialog
from clipse.insert_as_dialog import InsertAsDialog

out = _setup.ROOT / "build" / "screens"
out.mkdir(parents=True, exist_ok=True)
s = Settings()
s.load()
from clipse.fonts import apply_ui_font
_setup.app.setFont(apply_ui_font(_setup.app.font(), s))  # (as the service does)
_setup.app.setStyleSheet(build_stylesheet(s))
d = SettingsDialog(s)
d.resize(1000, 760)
d.show()
d._build_rest(all_now=True)
for i, (title, _icon, _b) in enumerate(d.PAGES):
    d._show_page(i)
    _setup.pump(0.05)
    d.grab().save(str(out / f"settings_{title.replace(' ', '_')}.png"))
ia = InsertAsDialog(s, sample=[("still", 150, "a"), ("still", 150, "b"), ("audio", 60, "whoosh")],
                    markers={"Blue": 5, "Red": 2, "Green": 1})
ia.resize(820, 900)
ia.show()
for pid in ("normal",):
    ia._pick(pid)
    ia.grid.settle()  # the still drawing, not a moment of its animation
    _setup.pump(0.05)
    ia.scroll.widget().grab().save(str(out / f"insert_as_{pid}.png"))
print(f"saved to {out}")
