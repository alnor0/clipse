"""The app's mark (picked 2026-10-18 from samples, the owner's own drawing): two clips leaning forward, the second a
step ahead - the top one light grey, the bottom one a darker grey. Every place that shows the mark draws it from here:
Settings > About, the start-up card (paint), the app icon (data/icon.svg / icon.png, written by
svg - tools/make_logo.py) and the website (tools/make_site.py)."""

LIGHT = "#aeaeb2"   # the top clip
DARK = "#6e6e73"    # the bottom clip
TILE = "#1d1d1f"    # the app icon's tile

# the two clips, as drawn (2000 x 2000), each a parallelogram: top-left, top-right, bottom-right, bottom-left
_TOP = ((315, 321), (1515, 321), (1316, 941), (117, 941))
_BOTTOM = ((614, 991), (1814, 991), (1616, 1610), (417, 1610))


def shapes(x, y, size, fill=0.78):
    """The two clips as point lists, the mark `fill` of a `size` square at (x, y), centred."""
    xs = [p[0] for p in _TOP + _BOTTOM]
    ys = [p[1] for p in _TOP + _BOTTOM]
    k = size * fill / max(max(xs) - min(xs), max(ys) - min(ys))
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    return [[(x + size / 2 + (px - cx) * k, y + size / 2 + (py - cy) * k) for px, py in clip]
            for clip in (_TOP, _BOTTOM)]


def paint(p, x, y, size, fill=0.78):
    """Draws the mark with QPainter `p` into the square at (x, y)."""
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QColor, QPolygonF
    p.save()
    p.setPen(Qt.NoPen)
    for clip, colour in zip(shapes(x, y, size, fill), (LIGHT, DARK)):
        p.setBrush(QColor(colour))
        p.drawPolygon(QPolygonF([QPointF(px, py) for px, py in clip]))
    p.restore()


def svg_parts(size, fill=0.78):
    """The two clips as SVG polygons in a `size` square."""
    return "".join(f'<polygon points="{" ".join(f"{px:.2f},{py:.2f}" for px, py in clip)}" fill="{colour}"/>'
                   for clip, colour in zip(shapes(0, 0, size, fill), (LIGHT, DARK)))


def svg(size=1024, tile=True):
    """The mark as an SVG file's text - on the app icon's rounded tile, or on nothing."""
    back = f'<rect width="{size}" height="{size}" rx="{size * 0.225:.1f}" fill="{TILE}"/>' if tile else ""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size} {size}" width="{size}" height="{size}">'
            f'{back}{svg_parts(size, 0.64 if tile else 0.9)}</svg>\n')
