"""Macro & comp previews: what's inside a .setting / .comp file, drawn as
a small node graph with a line in plain words under it.

Read straight from the file - no Fusion, no rendering - so it shows the
moment you move to a macro. Fusion files are Lua tables; this reads just
enough of that format to find the nodes and how they're connected, what
is animated, what the macro needs, and the controls it shows.

What's drawn is not Fusion's own layout (macros are often saved as one
long row that can't be read at this size): the main line runs left to
right and wraps onto the next row when it's long; side branches sit
under it. Keyframe curves, paths and shakes aren't nodes - a node they
move gets a small diamond instead. Wire elbows (PipeRouter) are left out.
A picture with the macro's name next to it (half_screen.png beside
half_screen.setting) is shown above the nodes.
"""
import os
import re

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QImage, QPainterPath, QPen

MAX_BYTES = 4 * 1024 * 1024
_cache = {}  # path -> (mtime, graph)

_TOKEN = re.compile(r"""
    (?P<ws>\s+|--\[(?P<eq>=*)\[.*?\](?P=eq)\]|--[^\n]*)
  | (?P<long>\[(?P<leq>=*)\[.*?\](?P=leq)\])
  | (?P<str>"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')
  | (?P<num>-?(?:0x[0-9a-fA-F]+|\d+\.?\d*(?:[eE][-+]?\d+)?|\.\d+(?:[eE][-+]?\d+)?))
  | (?P<name>[A-Za-z_][\w.]*)
  | (?P<sym>[{}\[\]=,;()])
""", re.S | re.X)


def _tokens(text):
    pos, n = 0, len(text)
    while pos < n:
        m = _TOKEN.match(text, pos)
        if m is None:
            pos += 1  # something we don't need (operators in expressions) - skip it
            continue
        pos = m.end()
        kind = m.lastgroup
        if kind in ("ws", "eq", "leq"):
            continue
        if kind == "str":
            yield "str", m.group()[1:-1]
        elif kind == "long":
            yield "str", ""
        elif kind == "num":
            try:
                yield "num", float(int(m.group(), 16) if m.group().lower().startswith(("0x", "-0x")) else m.group())
            except ValueError:
                yield "num", 0.0
        elif kind == "name":
            yield "name", m.group()
        else:
            yield "sym", m.group()


class _Parser:
    def __init__(self, text):
        self.toks = list(_tokens(text))
        self.i = 0

    def peek(self, k=0):
        j = self.i + k
        return self.toks[j] if j < len(self.toks) else ("eof", None)

    def take(self):
        tok = self.peek()
        self.i += 1
        return tok

    def value(self):
        kind, val = self.peek()
        if kind == "sym" and val == "{":
            return self.table()
        if kind in ("str", "num"):
            self.take()
            return val
        if kind == "name":
            self.take()
            if val in ("true", "false"):
                return val == "true"
            if val == "nil":
                return None
            if self.peek() == ("sym", "("):  # ordered() / Type() - skip the call's arguments
                depth = 0
                while True:
                    k, v = self.take()
                    if k == "eof":
                        break
                    if (k, v) == ("sym", "("):
                        depth += 1
                    elif (k, v) == ("sym", ")"):
                        depth -= 1
                        if depth == 0:
                            break
            if self.peek() == ("sym", "{"):  # Type { ... }
                table = self.table()
                if isinstance(table, dict):
                    table.setdefault("__type", val)
                return table
            if self.peek()[0] == "str":  # Type "string"
                return self.take()[1]
            return {"__type": val}
        self.take()
        return None

    def table(self):
        self.take()  # {
        out, items = {}, []
        while True:
            kind, val = self.peek()
            if kind == "eof":
                break
            if (kind, val) == ("sym", "}"):
                self.take()
                break
            if (kind, val) in (("sym", ","), ("sym", ";")):
                self.take()
                continue
            if kind == "name" and self.peek(1) == ("sym", "="):
                self.take()
                self.take()
                out[val] = self.value()
            elif (kind, val) == ("sym", "["):
                self.take()
                key = self.value()
                if self.peek() == ("sym", "]"):
                    self.take()
                if self.peek() == ("sym", "="):
                    self.take()
                out[str(key)] = self.value()
            else:
                items.append(self.value())
        if items:
            out["_list"] = items
        return out


_GROUPS = ("MacroOperator", "GroupOperator")


def _pos(tool):
    info = tool.get("ViewInfo")
    if isinstance(info, dict):
        pos = info.get("Pos")
        if isinstance(pos, dict) and len(pos.get("_list", [])) >= 2:
            x, y = pos["_list"][:2]
            if isinstance(x, (int, float)) and isinstance(y, (int, float)):
                return float(x), float(y)
    return None


# Not nodes: they sit on a node's setting and move it. kind -> what to call it
_MODIFIERS = {"BezierSpline": "keyframes", "PolyPath": "a path", "XYPath": "a path", "Path": "a path",
              "Shake": "shake", "Perturb": "shake", "AudioDisplay": "sound", "Expression": "expressions",
              "Calculation": "expressions", "Offset": "", "Vector": "", "PolylineStroke": "", "PublishNumber": "",
              "PublishPoint": "", "GradientColorModifier": "", "Probe": "", "FromTo": "", "CoordTransformPosition": ""}
_MAIN_INPUTS = ("Input", "Background", "Foreground", "Source", "Image", "EffectMask")
_PICTURES = (".png", ".jpg", ".jpeg", ".webp", ".gif")
_NAMES = {"TextPlus": "Text+", "BrightnessContrast": "Brightness", "ChannelBoolean": "Booleans", "ErodeDilate": "Erode",
          "FastNoise": "Fast Noise", "ColorCorrector": "Colour", "MediaIn": "Clip in", "MediaOut": "Out",
          "RectangleMask": "Rectangle", "EllipseMask": "Ellipse", "PolylineMask": "Polygon", "BSplineMask": "B-Spline"}


def _words(camel):
    """"MosaicBlur" -> "Mosaic Blur"."""
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", " ", camel).strip()


def _kind_name(kind):
    short = kind.rsplit(".", 1)[-1] if kind.startswith("ofx.") else kind
    return _NAMES.get(short) or _words(short)


def label(name, kind):
    """What to write on a node: the name you gave it - or, when it still has
    the one Fusion made up ("Transform4_1"), what kind of node it is."""
    base = re.sub(r"[_\d]+$", "", name)
    short = kind.rsplit(".", 1)[-1] if kind.startswith("ofx.") else kind
    if not base or not kind or short.lower().startswith(base.lower()) or base.lower().startswith(short.lower()):
        return _kind_name(kind) if kind else name
    return name


def _tools_of(table):
    tools = table.get("Tools") if isinstance(table, dict) else None
    if not isinstance(tools, dict):
        return {}
    return {k: v for k, v in tools.items() if isinstance(v, dict) and k != "_list"}


def _value(tool, input_name):
    inp = (tool.get("Inputs") or {}).get(input_name) if isinstance(tool.get("Inputs"), dict) else None
    return inp.get("Value") if isinstance(inp, dict) else None


def parse(text):
    """What's in the file: {"nodes": [(name, kind, None)], "edges": [(from, to, input)], "kind": "macro" /
    "group" / "comp", "controls": [names], "animated": {node: {"keyframes", "shake" ...}}, "pictures": how
    many pictures it takes in, "plugins": [names], "fonts": [names], "texts": [what its Text+ nodes say],
    "files": how many files on disk it needs, "labels": {node: what to write on it}} - or None."""
    try:
        root = _Parser(text).value()
    except RecursionError:
        return None
    tools = _tools_of(root)
    if not tools:
        return None
    kind, controls, pictures = "comp", [], 0
    groups = [t for t in tools.values() if t.get("__type") in _GROUPS and isinstance(t.get("Tools"), dict)]
    feeds = {}  # node inside -> the macro's picture inputs that go into it
    outs = []   # the nodes inside whose picture is the macro's output (its MainOutputs)
    if len(groups) == 1 and all(t is groups[0] or t.get("__type") in _MODIFIERS for t in tools.values()):
        group = groups[0]  # a macro: one group (keyframe curves may have been saved beside it)
        kind = "macro" if group.get("__type") == "MacroOperator" else "group"
        inputs = group.get("Inputs") if isinstance(group.get("Inputs"), dict) else {}
        for key, inp in inputs.items():
            if not isinstance(inp, dict) or key == "_list" or inp.get("__type") != "InstanceInput":
                continue
            if key.startswith("MainInput") or inp.get("Source") in ("EffectMask",):
                pictures += 1
                feeds.setdefault(inp.get("SourceOp"), []).append(key)
                continue
            shown = inp.get("Name") or _words(re.sub(r"Clone$", "", str(inp.get("Source") or key)))
            if isinstance(shown, str) and shown not in controls:
                controls.append(shown)
        outputs = group.get("Outputs") if isinstance(group.get("Outputs"), dict) else {}
        for key in sorted(k for k in outputs if str(k).startswith("MainOutput")):
            out = outputs[key]
            if isinstance(out, dict) and isinstance(out.get("SourceOp"), str):
                outs.append(out["SourceOp"])
                break   # (the main output: further ones are extras, not where the picture leaves)
        outside = {k: v for k, v in tools.items() if v is not group}
        tools = dict(outside, **_tools_of(group))

    any_placed = any(_pos(t) is not None for t in tools.values())

    def is_modifier(tool):
        kind_ = str(tool.get("__type", ""))
        return kind_ in _MODIFIERS or (any_placed and _pos(tool) is None and kind_ not in _GROUPS)

    modifiers = {name for name, tool in tools.items() if is_modifier(tool)}
    routers = {name for name, tool in tools.items() if tool.get("__type") == "PipeRouter"}

    def sources(name, seen=()):
        """(node it comes from, input) for everything wired into `name`."""
        tool = tools[name]
        inputs = tool.get("Inputs") if isinstance(tool.get("Inputs"), dict) else {}
        for in_name, inp in inputs.items():
            if isinstance(inp, dict) and isinstance(inp.get("SourceOp"), str) and inp["SourceOp"] in tools:
                yield inp["SourceOp"], in_name

    def moved_by(name, seen):
        """The kinds of animation behind a modifier (a path has keyframes under it ...)."""
        kinds = set()
        if name in seen:
            return kinds
        what = _MODIFIERS.get(str(tools[name].get("__type", "")), "")
        if what:
            kinds.add(what)
        for src, _in in sources(name):
            if src in modifiers:
                kinds |= moved_by(src, seen + (name,))
        return kinds

    def real_source(name, seen=()):
        """Through wire elbows to the node the picture really comes from."""
        while name in routers and name not in seen:
            seen += (name,)
            nxt = next((src for src, _in in sources(name) if src not in modifiers), None)
            if nxt is None:
                return None
            name = nxt
        return name

    nodes, edges, animated = [], [], {}
    plugins, fonts, texts, files = [], [], [], 0
    for name, tool in tools.items():
        if name in modifiers or name in routers:
            continue
        kind_ = str(tool.get("__type", ""))
        nodes.append((name, kind_, None))
        inputs = tool.get("Inputs") if isinstance(tool.get("Inputs"), dict) else {}
        for in_name, inp in inputs.items():
            if isinstance(inp, dict) and isinstance(inp.get("Expression"), str) and inp["Expression"].strip():
                animated.setdefault(name, set()).add("expressions")
        for src, in_name in sources(name):
            if src in modifiers:
                kinds = moved_by(src, ())
                if kinds:
                    animated.setdefault(name, set()).update(kinds)
                continue
            origin = real_source(src)
            if origin is not None and origin != name:
                edges.append((origin, name, in_name))
        if kind_.startswith("ofx."):
            shown = _kind_name(kind_)
            if shown not in plugins:
                plugins.append(shown)
        if kind_ in ("TextPlus", "Text3D"):
            font, said = _value(tool, "Font"), _value(tool, "StyledText")
            if isinstance(font, str) and font and font not in fonts:
                fonts.append(font)
            if isinstance(said, str) and said.strip():
                texts.append(" ".join(said.replace("\\n", " ").split()))
        if kind_ == "Loader":
            files += 1
    # the macro's input and output through wire elbows too: your clip may go into one first
    after = {}   # a wire elbow -> what it feeds
    for name in tools:
        if name in modifiers:
            continue
        for src, _in in sources(name):
            if src in routers:
                after.setdefault(src, []).append(name)

    def fed(name, seen=()):
        if name not in routers:
            return [name] if name in tools and name not in modifiers else []
        if name in seen:
            return []
        return [n for nxt in after.get(name, []) for n in fed(nxt, seen + (name,))]
    resolved = {}
    for node, keys in feeds.items():
        for target in fed(node):
            resolved.setdefault(target, []).extend(keys)
    feeds = resolved
    outs = [real_source(n) for n in outs if n in tools]
    outs = [n for n in outs if n is not None]
    return {"nodes": nodes, "edges": edges, "controls": controls, "kind": kind, "animated": animated,
            "pictures": pictures, "feeds": feeds, "outs": outs, "plugins": plugins, "fonts": fonts, "texts": texts, "files": files,
            "labels": {name: label(name, kind_) for name, kind_, _p in nodes}}


def load(path):
    """The graph of a .setting / .comp file (cached until the file changes), or None."""
    try:
        st = os.stat(path)
    except OSError:
        return None
    hit = _cache.get(path)
    if hit and hit[0] == st.st_mtime:
        return hit[1]
    if st.st_size > MAX_BYTES:
        return None
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            graph = parse(f.read())
        if graph is None or not graph["nodes"]:
            print(f"[preview] no nodes found in {os.path.basename(path)}")
        if graph is not None:  # a picture of what it does, if you put one next to it
            stem = os.path.splitext(path)[0]
            graph["picture"] = next((stem + ext for ext in _PICTURES if os.path.exists(stem + ext)), None)
    except Exception as e:  # never let an odd file break the preview
        print(f"[preview] couldn't read {os.path.basename(path)}: {e}")
        graph = None
    _cache[path] = (st.st_mtime, graph)
    return graph


def describe(graph):
    """What it is, in a line: "17 nodes · keyframes, shake · goes on a clip · Mosaic Blur"."""
    if not graph:
        return ""
    n = len(graph["nodes"])
    parts = [f"{n} node{'s' if n != 1 else ''}"]
    moves = []
    for kinds in (graph.get("animated") or {}).values():
        for kind in sorted(kinds):
            if kind not in moves:
                moves.append(kind)
    order = ["keyframes", "a path", "shake", "expressions", "sound"]
    moves.sort(key=lambda k: order.index(k) if k in order else 9)
    if moves:
        parts.append("animated: " + ", ".join("follows the sound" if m == "sound" else m for m in moves))
    if graph.get("kind") != "comp":
        takes = graph.get("pictures", 0)
        parts.append("goes on a clip" if takes == 1 else f"takes {takes} pictures" if takes else "makes its own picture")
    plugins = graph.get("plugins") or []
    if plugins:
        parts.append(", ".join(plugins[:2]) + (f" +{len(plugins) - 2}" if len(plugins) > 2 else ""))
    fonts = graph.get("fonts") or []
    if fonts:
        parts.append("font: " + ", ".join(fonts[:2]))
    if graph.get("files"):
        parts.append(f"needs {graph['files']} file{'s' if graph['files'] != 1 else ''} on disk")
    return "  ·  ".join(parts)


# -- drawing --
_GENERATORS = ("Background", "TextPlus", "Text3D", "FastNoise", "Plasma", "Loader", "MediaIn", "DayNight")
_MASKS = ("Polygon", "Ellipse", "Rectangle", "BSpline", "Mask", "Wand", "Triangle", "Ranges")
_MERGES = ("Merge", "Dissolve", "ChannelBoolean", "MultiMerge", "Merge3D")
_TRANSFORMS = ("Transform", "DVE", "Resize", "Scale", "Crop", "LetterBox", "CornerPositioner", "Camera3D")
_INPUT_ORDER = ("Background", "Input", "Source", "Image", "Foreground")  # which wire is the main line


def arrange(graph, max_columns):
    """Where each node goes: {name: (column, row, band)}. The main line - the
    longest way through to the end - is row 0, left to right; what feeds
    into it sits in the rows under it, one column before where it joins.
    A line longer than max_columns carries on in the next band below."""
    names = [n for n, _k, _p in graph["nodes"]]
    known = set(names)
    edges = [(a, b, i) for a, b, i in graph["edges"] if a in known and b in known and a != b]
    into, out_of = {n: [] for n in names}, {n: [] for n in names}
    for a, b, i in edges:
        into[b].append((a, i))
        out_of[a].append(b)
    depth = {n: 0 for n in names}
    for _ in range(len(names) + 1):  # the longest way to each node (a loop in the file just stops counting)
        changed = False
        for a, b, _i in edges:
            if depth[b] < depth[a] + 1 <= len(names):
                depth[b] = depth[a] + 1
                changed = True
        if not changed:
            break
    if not names:
        return {}
    end = max(names, key=lambda n: (not out_of[n], depth[n]))
    main, at = [end], end
    while into[at]:
        def rank(pair):
            src, inp = pair
            return (depth[src], -(_INPUT_ORDER.index(inp) if inp in _INPUT_ORDER else 9))
        at = max(into[at], key=rank)[0]
        if at in main:
            break
        main.append(at)
    on_main = set(main)
    # a side branch sits just before the node it feeds, not far off to the left
    for _ in range(len(names)):
        moved = False
        for n in names:
            if n in on_main or not out_of[n]:
                continue
            want = min(depth[b] for b in out_of[n]) - 1
            if want > depth[n]:
                depth[n] = want
                moved = True
        if not moved:
            break
    row, taken = {n: 0 for n in main}, {(depth[n], 0) for n in main}
    for n in sorted((n for n in names if n not in on_main), key=lambda n: (-depth[n], names.index(n))):
        nexts = [row[b] for b in out_of[n] if b in row]
        r = max(1, min(nexts) if nexts else 1)
        while (depth[n], r) in taken:
            r += 1
        row[n] = r
        taken.add((depth[n], r))
    columns = max(depth.values()) + 1
    bands = -(-columns // max(1, max_columns))
    per_band = -(-columns // bands)
    return {n: (depth[n] % per_band, row[n], depth[n] // per_band) for n in names}


IN, OUT = "\x00in", "\x00out"   # the drawing's own ends (never a node's name in a file)


def _with_out(graph):
    """The graph with where the picture comes out drawn as a box of its own, wired in like a node: "Out" from the
    node the macro's main output is (2026-10-17: it wasn't clear where the clip goes in and where it comes
    out - where it goes in is placed by draw, right before the node it feeds). A composition has its own MediaOut."""
    names = {n for n, _k, _p in graph["nodes"]}
    outs = [n for n in (graph.get("outs") or []) if n in names]
    if not outs:
        return graph
    labels = dict(graph.get("labels") or {}, **{OUT: "Out"})
    return dict(graph, nodes=list(graph["nodes"]) + [(OUT, OUT, None)], edges=list(graph["edges"]) + [(outs[0], OUT, "Input")],
                labels=labels)


_pictures = {}  # path -> (mtime, QImage)


def _picture(path):
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return None
    hit = _pictures.get(path)
    if hit is None or hit[0] != mtime:
        image = QImage(path)
        _pictures[path] = hit = (mtime, None if image.isNull() else image)
    return hit[1]


def draw(p, area, graph, settings, font):
    """Paints `graph` into `area` (QRectF) with QPainter `p`."""
    t = settings.theme
    nodes = graph["nodes"]
    small = QFont(font)
    small.setPointSizeF(max(7.5, font.pointSizeF() * 0.82) if font.pointSizeF() > 0 else 9.0)
    fm = QFontMetricsF(small)
    muted, text_color = QColor(t["picker_folder"]), QColor(t["picker_text"])
    accent = QColor(t.get("picker_accent", t["picker_text"]))

    # under the nodes: what it is in a line, then what it says / the controls you get
    lines = [describe(graph)] if nodes else []
    said = graph.get("texts") or []
    controls = graph.get("controls") or []
    if said:
        lines.append("Says  " + "  ·  ".join(f"“{s}”" for s in said[:3]))
    if controls:
        lines.append("Controls  " + "  ·  ".join(controls))
    if graph.get("note"):
        lines.append(graph["note"])
    lines = [line for line in lines if line][:3]
    footer = fm.height() * 1.45 * len(lines) + (6 if lines else 0)
    inner = area.adjusted(14, 12, -14, -10 - footer)
    p.setFont(small)
    for k, line in enumerate(lines):
        p.setPen(text_color if k == 0 else muted)
        p.drawText(QRectF(area.left() + 14, inner.bottom() + 8 + k * fm.height() * 1.45, area.width() - 28, fm.height() * 1.45),
                   Qt.AlignLeft | Qt.AlignVCenter, fm.elidedText(line, Qt.ElideRight, area.width() - 28))

    image = _picture(graph["picture"]) if graph.get("picture") else None
    if image is not None and inner.height() > 120:  # what it looks like, above how it's made
        room = QRectF(inner.left(), inner.top(), inner.width(), inner.height() * 0.56)
        scale = min(room.width() / image.width(), room.height() / image.height())
        w, h = image.width() * scale, image.height() * scale
        target = QRectF(room.center().x() - w / 2, room.top(), w, h)
        clip = QPainterPath()
        clip.addRoundedRect(target, 6, 6)
        p.save()
        p.setClipPath(clip)
        p.drawImage(target, image)
        p.restore()
        inner.setTop(target.bottom() + 10)

    if not nodes:
        p.setPen(muted)
        p.drawText(inner, Qt.AlignCenter, "No nodes inside")
        return
    graph = _with_out(graph)
    nodes = graph["nodes"]
    node_h = fm.height() + 8
    cell_w = 86.0
    place = arrange(graph, max(2, int(inner.width() // cell_w)) - (1 if graph.get("feeds") else 0))
    keys = sorted({k for ks in (graph.get("feeds") or {}).values() for k in ks})
    taken = set(place.values())
    gutter = 0
    ends_in = []   # (end, the node it feeds)
    wires = []   # (end, the node it feeds) - one box per input, a wire to each node it goes into
    for k, key in enumerate(keys):
        targets = sorted((n for n, ks in (graph.get("feeds") or {}).items() if key in ks and n in place),
                         key=lambda n: (place[n][2], place[n][0], place[n][1]))
        if not targets:
            continue
        node = targets[0]   # (the box sits by the first of them)
        col, row, band = place[node]
        end = f"{IN}{k}"
        # its wire must not run under other nodes: the free cell just left of the node, or left of it a row or
        # few below; a node starting its row gets the edge column; else a new row on top of the band for it
        free = next(((col - 1, r, band) for r in range(row, row + 4) if col > 0 and (col - 1, r, band) not in taken),
                    None)
        if free is None and col == 0:
            spot = row
            while (-1, spot, band) in taken:
                spot += 1
            free, gutter = (-1, spot, band), 1
        if free is None:
            for n, (c, r, b) in list(place.items()):
                if b == band:
                    place[n] = (c, r + 1, b)
            taken = set(place.values())
            free = (col - 1, 0, band)
        place[end] = free
        taken.add(free)
        ends_in.append((end, node, "Clip in" if len(keys) == 1 else f"In {k + 1}"))
        wires += [(end, n) for n in targets]
    if ends_in:
        nodes = [(end, IN, None) for end, _n, _l in ends_in] + list(nodes)
        graph = dict(graph, nodes=nodes, edges=list(graph["edges"]) + [(end, node, "Input") for end, node in wires],
                     labels=dict(graph.get("labels") or {}, **{end: label for end, _n, label in ends_in}))
    per_band = max(c for c, _r, _b in place.values()) + 1 + gutter
    bands = max(b for _c, _r, b in place.values()) + 1
    rows = [max(r for _c, r, b in place.values() if b == band) + 1 for band in range(bands)]
    cell_w = min(150.0, inner.width() / per_band)
    row_h, band_gap = node_h + 12.0, 16.0
    height = sum(rows) * row_h + (bands - 1) * band_gap
    squeeze = min(1.0, inner.height() / height) if height > 0 else 1.0
    if squeeze < 1.0:  # tall: the rows close up first, then everything is drawn smaller
        row_h = max(node_h + 3.0, row_h * squeeze)
        band_gap = max(8.0, band_gap * squeeze)
        height = sum(rows) * row_h + (bands - 1) * band_gap
        squeeze = min(1.0, inner.height() / height)
    p.save()
    if squeeze < 1.0:
        p.translate(inner.center().x(), inner.top())
        p.scale(squeeze, squeeze)
        p.translate(-inner.center().x(), -inner.top())
    band_top, y = [], inner.top() + max(0.0, (inner.height() / squeeze - height) / 2)
    for band in range(bands):
        band_top.append(y)
        y += rows[band] * row_h + band_gap
    left = inner.center().x() - per_band * cell_w / 2 + gutter * cell_w   # (column -1: the edge column)
    width = cell_w - 12.0
    centre = {n: QPointF(left + (c + 0.5) * cell_w, band_top[b] + (r + 0.5) * row_h) for n, (c, r, b) in place.items()}

    # the wires first, under the nodes: from a node's right side into the next one's left
    line = QColor(muted)
    line.setAlphaF(0.75)
    for a, b, inp in graph["edges"]:
        if a not in centre or b not in centre:
            continue
        pa = QPointF(centre[a].x() + width / 2, centre[a].y())
        pb = QPointF(centre[b].x() - width / 2, centre[b].y())
        wraps = place[a][2] != place[b][2]
        pen = QPen(line, 1.3)
        if "mask" in inp.lower():
            pen.setStyle(Qt.DashLine)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        path = QPainterPath(pa)
        if pb.x() > pa.x() + 4:
            dx = (pb.x() - pa.x()) * 0.5
            path.cubicTo(QPointF(pa.x() + dx, pa.y()), QPointF(pb.x() - dx, pb.y()), pb)
        else:
            # On to the next band (or back to an earlier column): out to the right, down into the
            # space between the rows, along it, and in from the left. Wires going the same way
            # share that space, so a long macro reads as one line that carries on underneath.
            if wraps:
                lane = band_top[place[b][2]] - band_gap / 2
            else:
                lane = (pa.y() + pb.y()) / 2 if abs(pa.y() - pb.y()) > node_h else pa.y() + row_h / 2
            out_x, in_x, r = pa.x() + 9, pb.x() - 9, 5.0
            down = 1 if lane > pa.y() else -1
            into = 1 if pb.y() > lane else -1
            path.lineTo(out_x - r, pa.y())
            path.quadTo(QPointF(out_x, pa.y()), QPointF(out_x, pa.y() + down * r))
            path.lineTo(out_x, lane - down * r)
            path.quadTo(QPointF(out_x, lane), QPointF(out_x - r, lane))
            path.lineTo(in_x + r, lane)
            path.quadTo(QPointF(in_x, lane), QPointF(in_x, lane + into * r))
            path.lineTo(in_x, pb.y() - into * r)
            path.quadTo(QPointF(in_x, pb.y()), QPointF(in_x + r, pb.y()))
            path.lineTo(pb)
        p.drawPath(path)
        head = QPainterPath()  # a small arrow head: which way it flows
        head.moveTo(pb)
        head.lineTo(pb.x() - 5, pb.y() - 3)
        head.lineTo(pb.x() - 5, pb.y() + 3)
        head.closeSubpath()
        p.setPen(Qt.NoPen)
        p.setBrush(line)
        p.drawPath(head)

    def tint(kind):
        if kind.startswith(_GENERATORS):
            return settings.icon_color("macro")
        if kind.startswith(_MASKS):
            return settings.icon_color("adjustment")
        if kind.startswith(_MERGES):
            return settings.icon_color("video")
        if kind.startswith(_TRANSFORMS):
            return settings.icon_color("image")
        return settings.icon_color("node")

    labels = graph.get("labels") or {}
    animated = graph.get("animated") or {}
    p.setFont(small)
    for name, kind, _p in nodes:
        c = centre[name]
        rect = QRectF(c.x() - width / 2, c.y() - node_h / 2, width, node_h)
        if kind in (IN, OUT):  # an end: an outlined capsule in the accent colour, narrower than a node
            end = QRectF(c.x() - min(width, 64) / 2, rect.top(), min(width, 64), node_h)
            if kind == IN:
                end.moveRight(rect.right())
            else:
                end.moveLeft(rect.left())
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(t["picker_bg"]))
            p.drawRoundedRect(end, node_h / 2, node_h / 2)
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(accent, 1.4))
            p.drawRoundedRect(end, node_h / 2, node_h / 2)
            p.setPen(accent)
            p.drawText(end, Qt.AlignCenter, labels.get(name, ""))
            continue
        color = QColor(tint(kind)) if kind else QColor(muted)  # "" = a stand-in node
        fill = QColor(color)
        fill.setAlphaF(0.22)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(t["picker_bg"]))
        p.drawRoundedRect(rect, 5, 5)
        p.setBrush(fill)
        p.setPen(QPen(color, 1))
        p.drawRoundedRect(rect, 5, 5)
        p.setPen(text_color)
        shown = labels.get(name, name)
        p.drawText(rect.adjusted(5, 0, -5, 0), Qt.AlignCenter, fm.elidedText(shown, Qt.ElideRight, width - 10))
        if animated.get(name):  # something moves it: a keyframe diamond on its corner
            d, corner = 4.0, QPointF(rect.right() - 2, rect.top() + 1)
            diamond = QPainterPath()
            diamond.moveTo(corner.x(), corner.y() - d)
            diamond.lineTo(corner.x() + d, corner.y())
            diamond.lineTo(corner.x(), corner.y() + d)
            diamond.lineTo(corner.x() - d, corner.y())
            diamond.closeSubpath()
            p.setPen(QPen(QColor(t["picker_bg"]), 1.2))
            p.setBrush(accent)
            p.drawPath(diamond)
    p.restore()


def summary(graph):
    """"6 nodes · 4 controls" for the info line."""
    if not graph:
        return ""
    n = len(graph["nodes"])
    c = len(graph.get("controls") or [])
    parts = [f"{n} node{'s' if n != 1 else ''}"]
    if graph.get("animated"):
        parts.append("animated")
    if c:
        parts.append(f"{c} control{'s' if c != 1 else ''}")
    return "  ·  ".join(parts)
