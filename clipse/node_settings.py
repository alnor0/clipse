"""The node in the preview while Expressions is open: the node the pieces point at, with what each of its
settings is called - the name an expression uses, which isn't always the one in the Inspector ("Blending 1"
is Overlap1) - and its value now. A click copies it ready to write (Merge1.Size, Text1.StyledText.Value); a
position has X and Y to copy by themselves.

Asked of Fusion from Python, no script run (read only): the list of settings once per node (Text+ has 309,
30 ms), the values a few times a second (5 ms)."""
import re
import time

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPen

from .glyphs import draw_glyph
from .fonts import SMALL, TINY, TITLE, at as font_at  # (the one scale of sizes)

KINDS = {"Number": "number", "Point": "point", "Text": "text"}
_NOT_SETTINGS = ("SeparatorControl", "SpacerControl", "NestControl", "LabelControl", "ButtonControl")
_PAGE_NAMES = {"Common": "Settings"}  # (what the Inspector calls the tab)
_FROM_COMMON = ("Blend",)  # the Settings tab is mostly how it's worked out - only these are for expressions
_TABS = re.compile(r"Tab\d+(Position|Alignment)$")  # a Text+'s eight tab stops: never what an expression is for
ROW_H = 26.0
COPIED_SECONDS = 1.4


def _comp(resolve):
    try:
        return resolve.Fusion().GetCurrentComp() if resolve.GetCurrentPage() == "fusion" else None
    except Exception:
        return None


def read(resolve, name):
    """{"name", "kind", "pages": [(tab, [{"id", "label", "kind"}])]} of the node called `name`, or a word for
    why there's none: "away" (not on the Fusion page), "missing" (no node by that name)."""
    comp = _comp(resolve)
    if comp is None:
        return "away"
    try:
        tool = comp.FindTool(name) if name else None
        if not tool:
            return "missing"
        inputs = tool.GetInputList() or {}
        pages = {}
        for key in sorted(inputs, key=float):
            attrs = inputs[key].GetAttrs() or {}
            kind = KINDS.get(attrs.get("INPS_DataType"))
            ident, page = attrs.get("INPS_ID") or "", attrs.get("INPS_ICS_ControlPage") or ""
            if not kind or attrs.get("INPB_Passive") or not attrs.get("INPB_External") \
                    or (attrs.get("INPI_IC_ControlPage") or 0) < 0 or attrs.get("INPID_InputControl") in _NOT_SETTINGS \
                    or ident.startswith("Gamut.") or ident.endswith("Clone") or _TABS.match(ident) or not page \
                    or (page == "Common" and ident not in _FROM_COMMON):
                continue
            # in the Inspector's order: the node's own tabs, then Image (a Text+'s size), then Settings
            order = {"Common": 10 ** 6, "Image": 10 ** 6 - 1}.get(page, attrs.get("INPI_IC_ControlPage") or 0)
            pages.setdefault((order, page), []).append(
                {"id": ident, "label": attrs.get("INPS_Name") or ident, "kind": kind})
        return {"name": name, "kind": str((tool.GetAttrs() or {}).get("TOOLS_RegID") or ""),
                "pages": [(_PAGE_NAMES.get(page, page), rows) for (_o, page), rows in sorted(pages.items())]}
    except Exception as e:
        print(f"[node settings] couldn't read {name}: {e}")
        return "missing"


def names_in_order(resolve):
    """The open composition's nodes as the node editor lays them out: left to right, then top to bottom - for
    flipping through them (the arrows by the node's name). A node with no place in the node view (a MediaIn's
    Left / Right sound) isn't one. 1 ms for a few nodes, read only."""
    from .fusion_graph import _MODIFIERS
    comp = _comp(resolve)
    if comp is None:
        return []
    try:
        flow = comp.CurrentFrame.FlowView
    except Exception:
        flow = None
    found = []
    try:
        for tool in (comp.GetToolList(False) or {}).values():
            attrs = tool.GetAttrs() or {}
            name, kind = str(attrs.get("TOOLS_Name") or ""), str(attrs.get("TOOLS_RegID") or "")
            if not name or kind in _MODIFIERS:
                continue
            try:
                place = flow.GetPosTable(tool) if flow is not None else None
            except Exception:
                place = None
            if flow is not None and not place:
                continue
            found.append(((round(float(place[1]), 1), float(place[2])) if place else (0.0, 0.0), name))
    except Exception as e:
        print(f"[node settings] couldn't list the nodes: {e}")
        return []
    return [name for _place, name in sorted(found, key=lambda pn: pn[0])]


def _number(value):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return str(value)
    return str(int(value)) if value.is_integer() else f"{value:.3f}".rstrip("0").rstrip(".")


def values(resolve, node):
    """{id: the value now, as words} of the settings in `node` (from read())."""
    comp = _comp(resolve)
    if comp is None or not isinstance(node, dict):
        return {}
    try:
        tool, now = comp.FindTool(node["name"]), comp.CurrentTime
        if not tool:
            return {}
        out = {}
        for _page, rows in node["pages"]:
            for row in rows:
                try:
                    value = tool[row["id"]][now]
                except Exception:
                    continue
                if row["kind"] == "point" and isinstance(value, dict):
                    out[row["id"]] = f"{_number(value.get(1, 0))}, {_number(value.get(2, 0))}"
                elif row["kind"] == "text":
                    out[row["id"]] = " ".join(str(value or "").split())
                else:
                    out[row["id"]] = _number(value)
        return out
    except Exception:
        return {}


def code(node, row, part=""):
    """What a click copies: the setting as an expression writes it."""
    tail = ".Value" if row["kind"] == "text" else f".{part}" if part else ""
    return f"{node['name']}.{row['id']}{tail}"


class NodeView:
    """What the preview draws and does while it shows a node (PreviewCanvas.node_view)."""

    def __init__(self, node, values=None):
        self.node = node          # read(), or "away" / "missing" / "" (no node in the field)
        self.values = values or {}
        self.scroll = 0.0
        self.mouse = QPointF(-1, -1)
        self.copied = (None, 0.0)  # (what was copied, when)
        self._spots = []  # [(rect, text a click copies)], as painted
        self._flips = []  # [(rect, -1 / +1)]: the previous / next node arrows, as painted
        self._room = 0.0  # how far the list can scroll

    def same_node(self, name):
        return isinstance(self.node, dict) and self.node["name"] == name

    def wheel(self, dy):
        self.scroll = max(0.0, min(self._room, self.scroll - dy))

    def flip_at(self, pos):
        """-1 / +1 on the previous / next node arrow, else None."""
        return next((step for rect, step in self._flips if rect.contains(pos)), None)

    def _paint_flips(self, p, area, top, height, colour, bright):
        """Two small chevrons in the top right corner - previous and next node, quiet until the mouse is on one."""
        self._flips = []
        side = 22.0
        right = area.right() - 10
        for step in (1, -1):
            rect = QRectF(right - side, top + (height - side) / 2, side, side)
            right -= side + 2
            over = rect.contains(self.mouse)
            if over:
                soft = QColor(bright)
                soft.setAlphaF(0.08)
                p.setPen(Qt.NoPen)
                p.setBrush(soft)
                p.drawRoundedRect(rect, 6, 6)
            c, w = rect.center(), 3.0
            p.setPen(QPen(bright if over else colour, 1.4, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            p.setBrush(Qt.NoBrush)
            p.drawPolyline([QPointF(c.x() - w * step / 1.6, c.y() - w * 1.3), QPointF(c.x() + w * step / 1.6, c.y()),
                            QPointF(c.x() - w * step / 1.6, c.y() + w * 1.3)])
            self._flips.append((rect, step))

    def hit(self, pos):
        return next((text for rect, text in reversed(self._spots) if rect.contains(pos)), None)

    def click(self, pos):
        text = self.hit(pos)
        if text:
            self.copied = (text, time.monotonic())
        return text

    def paint(self, p, area, settings, font):
        t = settings.theme
        text_c, muted, accent = QColor(t["picker_text"]), QColor(t["picker_folder"]), QColor(t["picker_accent"])
        quiet = QColor(t["picker_border"])
        title_f, text_f, mono_f = font_at(TITLE, font, QFont.DemiBold), font_at(SMALL, font), font_at(SMALL, font)
        head_f = font_at(TINY, font)
        from .fonts import mono_families
        mono_f.setFamilies(mono_families())
        for tag in ("calt", "liga"):
            mono_f.setFeature(QFont.Tag(tag), 0)
        head_f.setWeight(QFont.DemiBold)
        head_f.setCapitalization(QFont.AllUppercase)
        head_f.setLetterSpacing(QFont.PercentageSpacing, 112)
        self._spots = []
        node = self.node
        pad = 16.0
        tfm = QFontMetricsF(title_f)
        if node != "away":  # (off the Fusion page there are no nodes to go through)
            self._paint_flips(p, area, area.top() + pad - 2, tfm.height() + 4, muted, text_c)
        else:
            self._flips = []
        if not isinstance(node, dict):  # nothing to show: the node symbol and a word
            draw_glyph(p, "x_nodes", QPointF(area.center().x(), area.center().y() - 18), 30, muted)
            p.setFont(text_f)
            p.setPen(muted)
            p.drawText(QRectF(area.left(), area.center().y() + 4, area.width(), 24), Qt.AlignHCenter | Qt.AlignTop,
                       {"away": "Nodes are on the Fusion page", "missing": "No node by that name"}.get(
                           node, "No node selected"))
            return
        xfm, mfm, hfm = (QFontMetricsF(f) for f in (text_f, mono_f, head_f))
        row_h = max(ROW_H, round(mfm.height() + 10))
        just = self.copied[0] if time.monotonic() - self.copied[1] < COPIED_SECONDS else None
        # the node: its name (a click copies it) and what kind it is
        top = area.top() + pad
        p.setFont(title_f)
        p.setPen(accent if just == node["name"] else text_c)
        name_w = tfm.horizontalAdvance(node["name"])
        p.drawText(QPointF(area.left() + pad, top + tfm.ascent()), node["name"])
        self._spots.append((QRectF(area.left() + pad - 4, top - 2, name_w + 8, tfm.height() + 4), node["name"]))
        p.setFont(text_f)
        p.setPen(accent if just == node["name"] else muted)
        p.drawText(QPointF(area.left() + pad + name_w + 10, top + tfm.ascent()),
                   "Copied" if just == node["name"] else node["kind"])
        list_top = top + tfm.height() + 12
        view = QRectF(area.left(), list_top, area.width(), area.bottom() - list_top - 6)
        rows_h = sum(hfm.height() + 18 + len(rows) * row_h for _page, rows in node["pages"])
        self._room = max(0.0, rows_h - view.height() + 8)
        self.scroll = min(self.scroll, self._room)
        p.save()
        p.setClipRect(view)
        y = list_top - self.scroll
        right = area.right() - pad
        soft = QColor(text_c)
        soft.setAlphaF(0.07)
        chip = QColor(text_c)
        chip.setAlphaF(0.12)
        for page, rows in node["pages"]:
            mid = y + 8 + hfm.height() / 2
            p.setFont(head_f)
            p.setPen(muted)
            p.drawText(QPointF(area.left() + pad, y + 8 + hfm.ascent()), page)
            p.setPen(QPen(quiet, 1))
            p.drawLine(QPointF(area.left() + pad + hfm.horizontalAdvance(page.upper()) + 12, mid + 0.5),
                       QPointF(right, mid + 0.5))
            y += hfm.height() + 18
            for row in rows:
                rect = QRectF(area.left() + 6, y, area.width() - 12, row_h)
                if view.intersects(rect):
                    whole = code(node, row)
                    over = rect.contains(self.mouse) and view.contains(self.mouse)
                    if over:
                        p.setPen(Qt.NoPen)
                        p.setBrush(soft)
                        p.drawRoundedRect(rect, 6, 6)
                    base = y + (row_h + mfm.ascent() - mfm.descent()) / 2
                    done = just is not None and just in (whole, code(node, row, "X"), code(node, row, "Y"))
                    # a position: X and Y at the right end, to copy by themselves
                    end = right
                    if row["kind"] == "point":
                        for part in ("Y", "X"):
                            part_w = mfm.horizontalAdvance(part) + 12
                            spot = QRectF(end - part_w, y + 4, part_w, row_h - 8)
                            p.setPen(Qt.NoPen)
                            p.setBrush(chip if spot.contains(self.mouse) else soft)
                            p.drawRoundedRect(spot, 4, 4)
                            p.setFont(mono_f)
                            p.setPen(accent if just == code(node, row, part) else text_c)
                            p.drawText(spot, Qt.AlignCenter, part)
                            self._spots.append((spot.intersected(view), code(node, row, part)))
                            end -= part_w + 4
                        end -= 6
                    # the name an expression uses first - it's what you write; its value now at the right (or
                    # Copied); the Inspector's name between them when it isn't the same, as far as there's room
                    left = area.left() + pad
                    value = "Copied" if done else self.values.get(row["id"], "")
                    value_fm = xfm if done else mfm
                    value_w = min(value_fm.horizontalAdvance(value), (end - left) * 0.5)
                    shown = row["id"]  # (a text's copy has .Value after it)
                    id_w = min(mfm.horizontalAdvance(shown), end - left - value_w - 10)
                    p.setFont(mono_f)
                    p.setPen(accent if done else text_c)
                    p.drawText(QPointF(left, base), mfm.elidedText(shown, Qt.ElideRight, id_w))
                    label_w = end - value_w - 14 - (left + id_w + 10)
                    if label_w > 24 and row["label"].replace(" ", "").lower() != row["id"].lower():
                        p.setFont(text_f)
                        p.setPen(muted)
                        p.drawText(QRectF(left + id_w + 10, y, label_w, row_h), Qt.AlignLeft | Qt.AlignVCenter,
                                   xfm.elidedText(row["label"], Qt.ElideRight, label_w))
                    p.setFont(text_f if done else mono_f)
                    p.setPen(accent if done else muted)
                    p.drawText(QRectF(end - value_w, y, value_w, row_h), Qt.AlignRight | Qt.AlignVCenter,
                               value_fm.elidedText(value, Qt.ElideRight, value_w))
                    self._spots.insert(0, (rect.intersected(view), whole))  # (the X / Y on it come first)
                y += row_h
        p.restore()
