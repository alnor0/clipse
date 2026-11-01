"""Expressions for Fusion: small pieces of code that move things by
themselves - no keyframes. A setting with an expression works itself out
on every frame: "the angle is 8 times the sine of the time" swings for as
long as the clip lasts, and still fits when you make the clip longer.

In the picker: x: (or the Fusion page's list). Enter copies the code and
puts it where it belongs (TARGETS): on the selected node when that's the
right kind - a Transform or Merge for moving, a Merge for fading, a Text+
for words - otherwise on a new node of the right kind, added after the
selected one (or, with nothing selected, at the end of the comp - asked
first, Settings -> Timeline).

Each has a plain name, what it does, which numbers to change - and the
same sum in Python (`sample`), so the preview can play what it does
without Fusion. Written from Fusion's expression rules; not yet run in
Fusion - a wrong one says so in Fusion's console and changes nothing.

In an expression:  time = the frame now;  comp.RenderStart / comp.RenderEnd
= the clip's first and last frame;  sin cos abs floor ceil min max work as
in maths;  iif(test, a, b) = a if the test is true, else b;  Point(x, y) is
a position (0.5, 0.5 = the middle);  Text("...") is words;  ".." joins words;
another node's setting is NodeName.Setting (Transform1.Size)."""
import math

FPS = 30.0        # only for the preview's drawing
START, END = 0.0, 120.0


def _stopwatch(seconds):
    """00:12.34 - as the stopwatch's code writes it."""
    return f"{int(seconds // 60):02d}:{seconds % 60:05.2f}"


def _along(t):
    """How far through the clip, 0 to 1."""
    return (t - START) / (END - START)


# Where an expression belongs. what it is -> (the setting on a node that already has it, the kinds of
# node that count, the node to add otherwise, the setting on that new node, settings to fix on it,
# how the list says it)
TARGETS = {
    "position": ("Center", ("Transform", "Merge"), "Transform", "Center", {}, "Transform › Center"),
    "rotation": ("Angle", ("Transform", "Merge"), "Transform", "Angle", {}, "Transform › Angle"),
    "size": ("Size", ("Transform", "Merge"), "Transform", "Size", {}, "Transform › Size"),
    # a Merge's Blend fades what's on top; anything else is faded by a Brightness Contrast on its alpha
    "fade": ("Blend", ("Merge",), "BrightnessContrast", "Gain", {"Alpha": 1}, "Merge › Blend"),
    "words": ("StyledText", ("TextPlus",), "TextPlus", "StyledText", {}, "Text+ › Styled Text"),
}
_NODE_NAMES = {"Transform": "Transform", "Merge": "Merge", "BrightnessContrast": "Brightness Contrast", "TextPlus": "Text+"}


def P(name, label, default, low, high, whole=False):
    """A number in an expression you can set: a slider in the preview, and on the node.
    low / high: as far as the slider goes - kept close around `default`, so the whole of it is
    useful (a number can still be typed past the ends on the node). whole: frames - no fractions."""
    return {"id": name, "label": label, "default": default, "low": low, "high": high, "whole": whole}


def slider_share(param, value):
    """Where a number sits on its slider in the preview, 0 to 1. The number it comes with is
    always in the middle: the left half goes down to `low`, the right half up to `high` - so
    there's as much room to make a wiggle slower as to make it faster."""
    low, default, high = param["low"], param["default"], param["high"]
    value = max(low, min(high, value))
    if not low < default < high:
        return (value - low) / ((high - low) or 1)
    if value <= default:
        return 0.5 * (value - low) / (default - low)
    return 0.5 + 0.5 * (value - default) / (high - default)


def slider_value(param, share):
    """The number at `share` of the way along the slider (see slider_share), rounded to something tidy."""
    low, default, high = param["low"], param["default"], param["high"]
    share = max(0.0, min(1.0, share))
    if not low < default < high:
        value, span = low + (high - low) * share, high - low
    elif share <= 0.5:
        value, span = low + (default - low) * share * 2, default - low
    else:
        value, span = default + (high - default) * (share - 0.5) * 2, high - default
    if param.get("whole"):
        return float(round(value))
    step = 10.0 ** math.floor(math.log10(span / 40.0)) if span > 0 else 0.01
    return max(low, min(high, round(round(value / step) * step, 6)))


def _entry(key, group, name, target, template, about, params, sample, copy_only=False, any_number=True):
    """template: the code with {a slider's id} where its number goes. sample: the same sum in
    Python - sample(frame, **the sliders' numbers). copy_only: names another node (or is a
    building block), so it's copied for you to paste rather than put on a node."""
    entry = {"key": key, "group": group, "name": name, "target": target, "template": template, "about": about,
             "params": params, "sample": sample, "copy_only": copy_only}
    entry["code"] = code(entry)  # as it comes, with every slider where it starts
    entry["change"] = ("Sliders: " + ", ".join(p["label"].lower() for p in params)) if params else "Nothing to set."
    return entry


def defaults(entry):
    return {p["id"]: p["default"] for p in entry["params"]}


def _number(value):
    text = f"{float(value):.4f}".rstrip("0").rstrip(".")
    return text if text not in ("", "-0") else "0"


def code(entry, values=None):
    """The expression with the sliders' numbers written in."""
    numbers = dict(defaults(entry), **(values or {}))
    return entry["template"].format(**{k: _number(v) for k, v in numbers.items()})


def code_parts(entry, values=None):
    """The code as code() writes it, and what in it is yours to change: [(start, end, slider id)] for every
    slider's number, [(start, end, None)] for the node a Follow expression reads (NAMES_A_NODE)."""
    import string
    numbers = dict(defaults(entry), **(values or {}))
    text, spans = "", []
    for literal, field, _spec, _conv in string.Formatter().parse(entry["template"]):
        text += literal
        if field is not None:
            number = _number(numbers[field])
            spans.append((len(text), len(text) + len(number), field))
            text += number
    at = text.find(NAMES_A_NODE)
    while at >= 0:
        spans.append((at, at + len(NAMES_A_NODE), None))
        at = text.find(NAMES_A_NODE, at + 1)
    return text, sorted(spans)


def code_lines(text, per_line):
    """The code cut into lines of at most per_line letters (it's drawn in a code font, every letter as wide),
    never inside a number or a name - "0.⏎12", "Transform⏎1" - unless one is longer than a line: [(start, end)].
    A space at a cut stays at the end of the line before."""
    word = lambda c: c.isalnum() or c in "_."
    lines, at = [], 0
    while len(text) - at > per_line:
        end = at + per_line
        cut = next((j for j in range(end, at, -1) if not (word(text[j - 1]) and word(text[j]))), None)
        if cut is not None:
            end = cut + (text[cut] == " ")
        lines.append((at, end))
        at = end
    lines.append((at, len(text)))
    return lines


def control_id(entry, param):
    """The name of a slider on the node: "WigglePositionFar"."""
    return "".join(part.title() for part in entry["key"].split("_")) + param["id"].title()


def control_code(entry):
    """The expression with the node's own sliders in place of the numbers."""
    return entry["template"].format(**{p["id"]: control_id(entry, p) for p in entry["params"]})


_FPS = 'comp:GetPrefs("Comp.FrameFormat.Rate")'
_SINCE = "(time - comp.RenderStart)"
_THROUGH = "((time - comp.RenderStart) / (comp.RenderEnd - comp.RenderStart))"

LIBRARY = [
    # -- moving --
    _entry("wiggle_position", "Move", "Wiggle the position", "position",
           "Point(0.5 + {far}*sin(time*{fast}) + {far}*0.66*sin(time*{fast}*2.35), "
           "0.5 + {far}*cos(time*{fast}*0.87) + {far}*0.66*sin(time*{fast}*1.9))",
           "Drifts around its place like a hand-held camera, never quite the same twice.",
           [P("far", "How far", 0.012, 0.0, 0.05), P("fast", "How fast", 0.12, 0.02, 0.4)],
           lambda t, far, fast: (0.5 + far * math.sin(t * fast) + far * 0.66 * math.sin(t * fast * 2.35),
                                 0.5 + far * math.cos(t * fast * 0.87) + far * 0.66 * math.sin(t * fast * 1.9))),
    _entry("wiggle_rotation", "Move", "Wiggle the rotation", "rotation",
           "{degrees}*sin(time*{fast}) + {degrees}*0.6*sin(time*{fast}*2.44)",
           "Tilts a little to and fro, unevenly.",
           [P("degrees", "Degrees", 2.0, 0.0, 10.0), P("fast", "How fast", 0.12, 0.02, 0.4)],
           lambda t, degrees, fast: degrees * math.sin(t * fast) + degrees * 0.6 * math.sin(t * fast * 2.44)),
    _entry("float", "Move", "Float up and down", "position",
           "Point(0.5, 0.5 + {far}*sin(time/{slow}))",
           "Rises and sinks gently, like something on water.",
           [P("far", "How far", 0.02, 0.0, 0.1), P("slow", "How slow", 12.0, 3.0, 40.0)],
           lambda t, far, slow: (0.5, 0.5 + far * math.sin(t / slow))),
    _entry("bounce", "Move", "Bounce on the spot", "position",
           "Point(0.5, 0.5 + {high}*abs(sin(time/{slow})))",
           "Hops up and lands, over and over.",
           [P("high", "How high", 0.06, 0.0, 0.25), P("slow", "How slow", 8.0, 2.0, 25.0)],
           lambda t, high, slow: (0.5, 0.5 + high * abs(math.sin(t / slow)))),
    _entry("swing", "Move", "Swing like a sign", "rotation",
           "{degrees}*sin(time/{slow})", "Swings left and right around its middle.",
           [P("degrees", "Degrees", 8.0, 0.0, 30.0), P("slow", "How slow", 10.0, 3.0, 40.0)],
           lambda t, degrees, slow: degrees * math.sin(t / slow)),
    _entry("spin", "Move", "Spin steadily", "rotation",
           f"-{_SINCE} * {{speed}}", "Turns round and round at one speed (a minus number turns the other way).",
           [P("speed", "Degrees a frame", 3.0, -12.0, 12.0)],
           lambda t, speed: -(t - START) * speed),
    _entry("pulse", "Move", "Pulse the size", "size",
           "1 + {much}*sin(time/{slow})", "Grows and shrinks a little, like a heartbeat.",
           [P("much", "How much", 0.05, 0.0, 0.25), P("slow", "How slow", 5.0, 1.5, 25.0)],
           lambda t, much, slow: 1 + much * math.sin(t / slow)),
    _entry("zoom_slowly", "Move", "Zoom in slowly, the whole clip", "size",
           f"{{start}} + {{much}} * {_THROUGH}",
           "Creeps closer from the first frame to the last - however long the clip is. A minus number pulls back.",
           [P("much", "How much closer", 0.12, -0.3, 0.5), P("start", "Size at the start", 1.0, 0.5, 2.0)],
           lambda t, much, start: start + much * _along(t)),
    _entry("drift", "Move", "Drift sideways, the whole clip", "position",
           f"Point(0.5 - {{far}}/2 + {{far}} * {_THROUGH}, 0.5 - {{up}}/2 + {{up}} * {_THROUGH})",
           "Slides slowly across its place over the whole clip - to the left with a minus number, and up or down too.",
           [P("far", "How far across", 0.1, -0.4, 0.4), P("up", "How far up", 0.0, -0.3, 0.3)],
           lambda t, far, up: (0.5 - far / 2 + far * _along(t), 0.5 - up / 2 + up * _along(t))),
    _entry("shake_settle", "Move", "Shake, then settle", "position",
           f"Point(0.5 + {{hard}}*sin(time*{{fast}})*max(0, 1 - {_SINCE}/{{frames}}), "
           f"0.5 + {{hard}}*cos(time*{{fast}}*1.21)*max(0, 1 - {_SINCE}/{{frames}}))",
           "A hit: shakes hard at the start, then calms down.",
           [P("hard", "How hard", 0.03, 0.0, 0.12), P("frames", "Frames until calm", 30.0, 5.0, 90.0, whole=True),
            P("fast", "How fast", 1.9, 0.5, 3.0)],
           lambda t, hard, frames, fast: (0.5 + hard * math.sin(t * fast) * max(0, 1 - (t - START) / frames),
                                          0.5 + hard * math.cos(t * fast * 1.21) * max(0, 1 - (t - START) / frames))),
    # -- fading (a Merge's Blend fades what's on top) --
    _entry("fade_in", "Fade", "Fade in at the start", "fade",
           f"min(1, {_SINCE} / {{frames}})", "Comes in over the first frames of the clip.",
           [P("frames", "Frames", 15.0, 1.0, 60.0, whole=True)],
           lambda t, frames: min(1, (t - START) / frames)),
    _entry("fade_out", "Fade", "Fade out at the end", "fade",
           "min(1, (comp.RenderEnd - time) / {frames})",
           "Goes out over the last frames - also after you trim the clip.",
           [P("frames", "Frames", 15.0, 1.0, 60.0, whole=True)],
           lambda t, frames: min(1, (END - t) / frames)),
    _entry("fade_in_out", "Fade", "Fade in and out", "fade",
           f"min(1, {_SINCE} / {{frames_in}}, (comp.RenderEnd - time) / {{frames_out}})",
           "In at the start, out at the end, whatever the clip's length.",
           [P("frames_in", "Frames in", 15.0, 1.0, 60.0, whole=True), P("frames_out", "Frames out", 15.0, 1.0, 60.0, whole=True)],
           lambda t, frames_in, frames_out: min(1, (t - START) / frames_in, (END - t) / frames_out)),
    _entry("blink", "Fade", "Blink on and off", "fade",
           "iif(floor(time / {frames}) % 2 == 0, 1, 0)", "There, gone, there, gone.",
           [P("frames", "Frames each", 15.0, 1.0, 45.0, whole=True)],
           lambda t, frames: 1 if math.floor(t / frames) % 2 == 0 else 0),
    _entry("flicker", "Fade", "Flicker like a bad lamp", "fade",
           "1 - {deep} + {deep}*sin(time*7.3*{fast})*sin(time*3.1*{fast})",
           "Unsteady light: dips and comes back at random-looking moments.",
           [P("deep", "How deep", 0.25, 0.0, 0.5), P("fast", "How fast", 1.0, 0.1, 3.0)],
           lambda t, deep, fast: 1 - deep + deep * math.sin(t * 7.3 * fast) * math.sin(t * 3.1 * fast)),
    _entry("breathe", "Fade", "Breathe", "fade",
           "{dimmest} + (1 - {dimmest})*(0.5 + 0.5*sin(time/{slow}))", "A slow, soft glow up and down.",
           [P("dimmest", "Its dimmest", 0.6, 0.0, 1.0), P("slow", "How slow", 14.0, 4.0, 45.0)],
           lambda t, dimmest, slow: dimmest + (1 - dimmest) * (0.5 + 0.5 * math.sin(t / slow))),
    # -- words (on a Text+: its text) --
    _entry("frame_number", "Words", "Show the frame number", "words",
           'Text("Frame " .. time)', "The text counts the frames as they go by.", [],
           lambda t: f"Frame {int(t)}"),
    _entry("timer", "Words", "A running timer", "words",
           f'Text(string.format("%02d:%02d", floor({_SINCE} / {_FPS} / 60), floor({_SINCE} / {_FPS}) % 60))',
           "Minutes and seconds since the clip began: 00:00, 00:01, 00:02 ...", [],
           lambda t: f"{int((t - START) / FPS // 60):02d}:{int((t - START) / FPS) % 60:02d}"),
    # (short enough to read and change by hand - no slider for the decimals: no decimals is the timer above)
    _entry("stopwatch", "Words", "A stopwatch", "words",
           f'Text(string.format("%02d:%05.2f", floor({_SINCE} / {_FPS} / 60), {_SINCE} / {_FPS} % 60))',
           "Minutes, seconds and hundredths since the clip began: 00:00.00, 00:00.03, 00:00.07 ...", [],
           lambda t: _stopwatch((t - START) / FPS)),
    _entry("countdown_clock", "Words", "A countdown clock", "words",
           f'Text(string.format("%02d:%05.2f", floor((comp.RenderEnd - time) / {_FPS} / 60), '
           f'(comp.RenderEnd - time) / {_FPS} % 60))',
           "Minutes, seconds and hundredths left, down to 00:00.00 on the clip's last frame.", [],
           lambda t: _stopwatch((END - t) / FPS)),
    _entry("countdown", "Words", "Count down the seconds left", "words",
           f'Text(string.format("%d", ceil((comp.RenderEnd - time) / {_FPS})))',
           "3, 2, 1 ... reaches 0 exactly when the clip ends.", [],
           lambda t: str(math.ceil((END - t) / FPS))),
    _entry("count_up", "Words", "Count up to a number", "words",
           f'Text(string.format("%d", {{start}} + ({{to}} - {{start}}) * {_THROUGH}))',
           "A number that runs up over the clip - or down, with the larger number first.",
           [P("start", "From", 0.0, 0.0, 300.0, whole=True), P("to", "Up to", 100.0, 0.0, 300.0, whole=True)],
           lambda t, start, to: str(int(start + (to - start) * _along(t)))),
    _entry("date", "Words", "Today's date", "words",
           'Text(os.date("%d %B %Y"))', "The date of the day you render, written out.", [],
           lambda t: "13 October 2026"),
    # -- time: numbers that come from the clock, to build anything with --
    _entry("frames_since", "Time", "Frames since the clip began", None,
           _SINCE, "0 on the clip's first frame, then 1, 2, 3 ... The start of most time sums.", [],
           lambda t: t - START, copy_only=True),
    _entry("seconds_since", "Time", "Seconds since the clip began", None,
           f"{_SINCE} / {_FPS}", "The same in seconds, whatever the frame rate.", [],
           lambda t: (t - START) / FPS, copy_only=True),
    _entry("through", "Time", "How far through the clip", None,
           _THROUGH, "0 at the start, 1 at the end, 0.5 half way - and still right after a trim.", [],
           lambda t: _along(t), copy_only=True),
    _entry("frames_left", "Time", "Frames left", None,
           "(comp.RenderEnd - time)", "Counts down to 0 on the last frame: for things that happen at the end.", [],
           lambda t: END - t, copy_only=True),
    _entry("wait_then_go", "Time", "Wait, then start counting", None,
           f"max(0, {_SINCE} - {{wait}})", "Stays 0 for a while, then counts frames: a delayed start.",
           [P("wait", "Frames to wait", 30.0, 0.0, 90.0, whole=True)],
           lambda t, wait: max(0, (t - START) - wait), copy_only=True),
    _entry("ramp", "Time", "0 to 1 over some frames, then stay", None,
           f"min(1, {_SINCE} / {{frames}})", "A straight climb from 0 to 1, then it holds at 1.",
           [P("frames", "Frames", 30.0, 1.0, 90.0, whole=True)],
           lambda t, frames: min(1, (t - START) / frames), copy_only=True),
    _entry("ease", "Time", "0 to 1, starting and stopping softly", None,
           f"(1 - cos(min(1, {_SINCE} / {{frames}}) * pi)) / 2",
           "The same climb with soft ends - what makes a move feel made by hand.",
           [P("frames", "Frames", 30.0, 1.0, 90.0, whole=True)],
           lambda t, frames: (1 - math.cos(min(1, (t - START) / frames) * math.pi)) / 2, copy_only=True),
    _entry("loop", "Time", "0 to 1, over and over", None,
           "(time % {frames}) / {frames}", "Climbs from 0 to 1, then starts again.",
           [P("frames", "Frames a round", 30.0, 2.0, 90.0, whole=True)],
           lambda t, frames: (t % frames) / frames, copy_only=True),
    _entry("ping_pong", "Time", "There and back", None,
           "abs(((time / {frames}) % 2) - 1)", "Goes 1 to 0 and back to 1, turning round at each end.",
           [P("frames", "Frames each way", 30.0, 2.0, 90.0, whole=True)],
           lambda t, frames: abs(((t / frames) % 2) - 1), copy_only=True),
    _entry("steps", "Time", "Held for a few frames at a time", None,
           "floor(time / {hold}) * {hold}",
           "Time that jumps on every few frames instead of running: the stop-motion feel. Use it in place of time.",
           [P("hold", "Frames held", 4.0, 1.0, 12.0, whole=True)],
           lambda t, hold: math.floor(t / hold) * hold, copy_only=True),
    _entry("random_steps", "Time", "A new random number now and then", None,
           "(sin(floor(time / {hold}) * 12.9898) * 43758.5453) % 1",
           "Between 0 and 1, changing every few frames - the same every time you render.",
           [P("hold", "Frames each lasts", 6.0, 1.0, 24.0, whole=True)],
           lambda t, hold: (math.sin(math.floor(t / hold) * 12.9898) * 43758.5453) % 1, copy_only=True),
    # -- tied to another node: copy, then put your node's name in --
    _entry("follow", "Follow", "Follow another node's position", "position",
           "Transform1.Center", "Goes wherever the other node goes.", [],
           lambda t: (0.5 + 0.2 * math.sin(t / 20), 0.5), copy_only=True),
    _entry("echo", "Follow", "Follow another node, a moment late", "position",
           "Transform1.Center[time - {late}]",
           "Where the other node was a few frames ago: a trail, an echo. [time - 5] reads any setting in the past.",
           [P("late", "Frames late", 5.0, 0.0, 20.0, whole=True)],
           lambda t, late: (0.5 + 0.2 * math.sin((t - late) / 20), 0.5), copy_only=True),
    _entry("mirror", "Follow", "Mirror another node", "position",
           "Point(1 - Transform1.Center.X, Transform1.Center.Y)", "Moves the opposite way, left to right.", [],
           lambda t: (0.5 - 0.2 * math.sin(t / 20), 0.5), copy_only=True),
    _entry("parallax", "Follow", "Move part of the way another node moves", "position",
           "Point(0.5 + (Transform1.Center.X - 0.5) * {share}, 0.5 + (Transform1.Center.Y - 0.5) * {share})",
           "Depth: a layer behind moves less than the one in front.",
           [P("share", "How much of it", 0.5, 0.0, 1.5)],
           lambda t, share: (0.5 + 0.2 * math.sin(t / 20) * share, 0.5), copy_only=True),
    _entry("half_size", "Follow", "A share of another node's size", "size",
           "Transform1.Size * {share}", "Always that much of the other node's size, whatever you set there.",
           [P("share", "How much of it", 0.5, 0.0, 1.5)],
           lambda t, share: share * (1 + 0.3 * math.sin(t / 15)), copy_only=True),
]

# Other words people look for them by (the group's name finds its expressions too: x: time)
KEYWORDS = {
    "wiggle_position": "shake camera handheld jitter noise random", "wiggle_rotation": "shake tilt jitter random",
    "float": "hover bob wave", "bounce": "hop jump", "swing": "pendulum rock sway", "spin": "rotate turn",
    "pulse": "heartbeat scale beat throb", "zoom_slowly": "ken burns push in scale", "drift": "pan slide",
    "shake_settle": "impact hit earthquake decay", "fade_in": "opacity appear", "fade_out": "opacity disappear",
    "fade_in_out": "opacity", "blink": "flash strobe", "flicker": "light lamp neon", "breathe": "glow pulse",
    "frame_number": "counter", "timer": "clock seconds minutes", "stopwatch": "clock timer seconds hundredths decimals race lap",
    "countdown_clock": "timer clock seconds left remaining hundredths decimals", "countdown": "clock seconds timer",
    "count_up": "counter number percent", "date": "today calendar",
    "frames_since": "start offset", "seconds_since": "clock", "through": "progress percent normalised 0 1",
    "frames_left": "end remaining", "wait_then_go": "delay hold offset later", "ramp": "linear progress",
    "ease": "easing smooth soft in out curve", "loop": "repeat cycle", "ping_pong": "back forth bounce repeat",
    "steps": "stop motion posterize stutter hold frames", "random_steps": "noise jitter",
    "follow": "link connect parent", "echo": "delay trail lag offset past", "mirror": "flip opposite",
    "parallax": "depth layers", "half_size": "link scale",
}


def search_words(entry):
    return f"{entry['group']} {KEYWORDS.get(entry['key'], '')} expression".lower()


# What you can write in an expression - the cheat sheet (x: then its row, or > expression cheat sheet):
# [(group, [(the code, what it gives, what to draw beside it)])]. NODE stands for a node's name: the
# sheet writes the node selected in Fusion there (sheet_code).
# What to draw: None; a few words - what it comes to in the sample clip (4 seconds, 1920 x 1080, 30
# frames a second); or (sum, sum to compare with or None, (lowest, highest) or None) - the same sum
# in Python, drawn as a small curve over the sample clip, the one it's compared with faint behind it.
NODE = "NodeName"
_RATE = 'comp:GetPrefs("Comp.FrameFormat.Rate")'
_WIDTH, _HEIGHT = 'comp:GetPrefs("Comp.FrameFormat.Width")', 'comp:GetPrefs("Comp.FrameFormat.Height")'
_sin, _line = math.sin, (lambda t: t)


_U = "(time / comp.RenderEnd)"  # 0 at the start of the clip, 1 at its end
_ramp = lambda t: t / END  # noqa: E731 (what an easing curve is drawn against)


def _noise(t):
    return 1 + math.floor(((math.sin(math.floor(t / 4) * 12.9898) * 43758.5453) % 1) * 10)


CHEAT_SHEET = [
    ("Composition", [
        ("time", "The frame now.", (_line, None, None)),
        ("comp.RenderStart", "The clip's first frame.", "0"),
        ("comp.RenderEnd", "The clip's last frame.", "119"),
        (_RATE, "Frames a second.", "30"),
        (_WIDTH, "The picture's width, in pixels.", "1920"),
        (_HEIGHT, "The picture's height, in pixels.", "1080"),
        (f"{_WIDTH} / {_HEIGHT}", "The picture's shape: 1.78 when it's 16:9.", "1.78"),
    ]),
    ("Time", [
        ("time - comp.RenderStart", "Frames since the clip began.", (_line, None, None)),
        ("comp.RenderEnd - time", "Frames left.", (lambda t: END - t, None, None)),
        ("(time - comp.RenderStart) / (comp.RenderEnd - comp.RenderStart)",
         "How far through the clip: 0 at the start, 1 at the end.", "0 → 1"),
        (f"time / {_RATE}", "Seconds, whatever the frame rate.", "0 → 4"),
        ("time * 3", "Time running three times as fast. time / 3: three times slower.", (lambda t: t * 3, _line, None)),
        ("time % 30", "Counts 0 to 29, then starts over.", (lambda t: t % 30, None, None)),
        ("floor(time / 10)", "Goes up by one every 10 frames.", (lambda t: math.floor(t / 10), None, None)),
        ("max(0, time - 20)", "Nothing for 20 frames, then counts.", (lambda t: max(0, t - 20), _line, None)),
        ("min(1, time / 15)", "0 to 1 over 15 frames, then stays at 1.", (lambda t: min(1, t / 15), None, (0, 1.25))),
        (f"max(0, floor(60 - time / {_RATE}))", "A countdown from 60 seconds, stopping at 0.", "60, 59, 58 ..."),
    ]),
    ("Waves", [
        ("sin(time / 10)", "Swings between -1 and 1.", (lambda t: _sin(t / 10), None, (-1.2, 1.2))),
        ("abs(sin(time / 10))", "Bounces between 0 and 1.", (lambda t: abs(_sin(t / 10)), lambda t: _sin(t / 10), (-1.2, 1.2))),
        ("0.5 + 0.5 * sin(time / 10)", "Glides between 0 and 1.", (lambda t: 0.5 + 0.5 * _sin(t / 10), None, (-0.2, 1.2))),
        ("3 * sin(time / 10)", "The number in front: how far it swings.",
         (lambda t: 3 * _sin(t / 10), lambda t: _sin(t / 10), (-3.4, 3.4))),
        ("sin(time / 20)", "A bigger number under time: slower.", (lambda t: _sin(t / 20), lambda t: _sin(t / 10), (-1.2, 1.2))),
        ("cos(time / 10)", "The same swing, a quarter turn ahead. sin for one side and cos for the other draws a circle.",
         (lambda t: math.cos(t / 10), lambda t: _sin(t / 10), (-1.2, 1.2))),
        ("bmd.noise(time / 20)", "A smooth, random wobble between -1 and 1 - Fusion's own noise.",
         (lambda t: 0.6 * _sin(t / 13) + 0.4 * _sin(t / 7.3 + 1.7), None, (-1.2, 1.2))),
    ]),
    # from 0 at the start of the clip to 1 at its end, the way it eases (* 100, or a distance, after it)
    ("Easing", [
        (f"1 - cos({_U} * pi / 2)", "Eases in: starts slow, speeds up.",
         (lambda t: 1 - math.cos(t / END * math.pi / 2), _ramp, (0, 1))),
        (f"sin({_U} * pi / 2)", "Eases out: starts fast, settles.", (lambda t: math.sin(t / END * math.pi / 2), _ramp, (0, 1))),
        (f"(1 - cos({_U} * pi)) / 2", "Eases in and out.", (lambda t: (1 - math.cos(t / END * math.pi)) / 2, _ramp, (0, 1))),
        (f"{_U} ^ 3", "Eases in, harder.", (lambda t: (t / END) ** 3, _ramp, (0, 1))),
        (f"1 - (1 - {_U}) ^ 3", "Eases out, harder.", (lambda t: 1 - (1 - t / END) ** 3, _ramp, (0, 1))),
        (f"1 - 2 ^ (-10 * {_U})", "Shoots out and stops dead.", (lambda t: 1 - 2 ** (-10 * t / END), _ramp, (0, 1))),
        (f"1 + 2.70158 * ({_U} - 1) ^ 3 + 1.70158 * ({_U} - 1) ^ 2", "Goes a little past, then back - an overshoot.",
         (lambda t: 1 + 2.70158 * (t / END - 1) ** 3 + 1.70158 * (t / END - 1) ** 2, _ramp, (0, 1.15))),
    ]),
    ("Moving", [
        ("Point(cos(time * 0.1) * 0.4 + 0.5, sin(time * 0.1) * 0.4 + 0.5)", "Round in a circle - for a Center.", None),
        ("Point(0.5, sin(time * 0.1) * 0.4 + 0.5)", "Bobs up and down.", None),
        (f"time * 360 / {_RATE}", "One full turn a second - for an Angle. -time turns the other way.", None),
    ]),
    ("Counters", [
        (f'ceil({_U} * 100) .. "%"', "How far through the clip, as words: 0% to 100%.", "40%"),
        (f'"Progress: " .. ceil({_U} * 100) .. "%"', "...with words in front.", "Progress: 40%"),
        (f"ceil(time / {_RATE})", "Counts the seconds up.", "2"),
        (f"ceil((comp.RenderEnd - time) / {_RATE})", "Counts the seconds left down.", "3"),
        (f'"9:" .. string.format("%02d", max(30 - floor(time / {_RATE}), 0))', "A clock that runs down from 9:30.",
         "9:28"),
    ]),
    ("Maths", [
        ("min(x, y)", "The smaller of the two (or of as many as you give it).",
         (lambda t: min(_sin(t / 10), 0.3), lambda t: _sin(t / 10), (-1.2, 1.2))),
        ("max(x, y)", "The larger.", (lambda t: max(_sin(t / 10), 0.3), lambda t: _sin(t / 10), (-1.2, 1.2))),
        ("abs(x)", "Never below zero.", (lambda t: abs(_sin(t / 10)), lambda t: _sin(t / 10), (-1.2, 1.2))),
        ("floor(x)", "Rounds down.", (lambda t: math.floor(t / 24), lambda t: t / 24, None)),
        ("ceil(x)", "Rounds up.", (lambda t: math.ceil(t / 24), lambda t: t / 24, None)),
        ("floor(x + 0.5)", "Rounds to the nearest whole number.", (lambda t: math.floor(t / 24 + 0.5), lambda t: t / 24, None)),
        ("sqrt(x)", "The square root.", (lambda t: math.sqrt(t / END), lambda t: t / END, None)),
        ("x ^ 2", "To the power of 2.", (lambda t: (t / END) ** 2, lambda t: t / END, None)),
        ("x % y", "What's left after dividing.", (lambda t: t % 40, None, None)),
        ("random(1, 10)", "A whole number from 1 to 10, a new one each frame.", (_noise, None, (0, 11))),
        (":randomseed(7); return random()", "The same random number on every frame - another seed, another number.",
         "0.60 every frame"),
        ("atan2(y, x)", "The angle towards a point, in radians - to point at something.", "atan2(1, 1) = 0.785"),
        ("deg(x)", "Radians into degrees.", "deg(pi) = 180"),
        ("pi", "3.14159...", "3.14159"),
    ]),
    ("Choices", [
        ("iif(time > 30, 1, 0)", "One thing or the other: 1 after frame 30, 0 before.",
         (lambda t: 1 if t > 30 else 0, None, (-0.25, 1.25))),
        ("(time > 30 and 1 or 0)", "The same, written the short way.", (lambda t: 1 if t > 30 else 0, None, (-0.25, 1.25))),
        # several small pieces under one heading: each its own box, copied by itself
        (("==", "~=", "<", ">", "<=", ">="), "Equal, not equal, smaller, larger, at most, at least.", None),
        ("iif(x > 0 and y > 0, 1, 0)", "and: both must be true. or: either. not: the opposite.", None),
        (":if time < 10 then return 0 else return 90 end", "If, then, else - written out (a colon first).", None),
        ("iif(comp.HiQ, 1, 0)", "1 with HiQ on, 0 with it off - on a heavy node's Blend: off while you work.", None),
    ]),
    ("Other nodes", [
        ("self.Size", "A setting of the same node the expression is on.", None),
        (f"{NODE}.Size", "Another node's setting.", None),
        (f"{NODE}.Center.X", "One side of a position. .Y is the other.", None),
        (f"Point({NODE}.Center.X, 0.5)", "A position made of two numbers (0.5, 0.5 is the middle).", None),
        (f'{NODE}:GetValue("Size", time - 5)', "A setting at another moment, the long way.", None),
        (f'{NODE}:GetValue("Center", time - 5).X', "One side of a position at another moment.", None),
        ('self:GetSourceTool("Input"):GetValue("Size", time)', "A setting of the node plugged into this one.", None),
        (f"sqrt(({NODE}.Center.X - 0.5) ^ 2 + ({NODE}.Center.Y - 0.5) ^ 2)", "How far a node's centre is from the middle.",
         None),
    ]),
    ("Picture size", [
        (f"{NODE}.Output.Width", "The width of a node's picture, in pixels.", "1920"),
        (f"{NODE}.Output.Height", "Its height, in pixels.", "1080"),
        (f"{NODE}.Output.DataWindow[1]", "The left edge of what is really drawn, in pixels. [2] bottom, [3] right, [4] top.", None),
        (f"({NODE}.Output.DataWindow[3] - {NODE}.Output.DataWindow[1]) / {NODE}.Output.Width",
         "How wide what's drawn is, 0 to 1 - for a box that fits its text.", "0.42"),
        (f"({NODE}.Output.DataWindow[4] - {NODE}.Output.DataWindow[2]) / {NODE}.Output.Height",
         "How tall what's drawn is, 0 to 1.", "0.08"),
    ]),
    ("Words", [
        ('Text("Hello")', "Words, for a Text+.", "Hello"),
        ('Text("Frame " .. time)', "Two dots join words and numbers.", "Frame 37"),
        (f"{NODE}.StyledText.Value", "The words of another Text+.", None),
        (f"Text(string.upper({NODE}.StyledText.Value))", "Another Text+'s words, in capitals.", "HELLO"),
        ('Text(string.format("%02d", time))', "A number with a zero in front when it's short.", "07"),
        ('Text(string.format("%.2f", x))', "A number with two decimals.", "3.14"),
        ('Text(string.format("%d:%02d", floor(x / 60), x % 60))', "Seconds as minutes and seconds.", "1:05"),
        ("string.sub(s, 1, 3)", "A part of the words: from the 1st to the 3rd letter.", "Hel"),
        (f':_, n = string.gsub({NODE}.StyledText.Value, "\\n", ""); return n + 1', "How many lines a Text+ has.", "2"),
        (f':_, n = string.gsub({NODE}.StyledText.Value, "%S+", ""); return n', "How many words.", "2"),
        (f':_, n = string.gsub({NODE}.StyledText.Value, "[AEIOUaeiou]", ""); return n', "How many vowels.", "3"),
        (("%a", "%d", "%s", "%u", "%l", "%p"), "What to count instead: letters, digits, spaces, capitals, small letters, "
         "punctuation.", None),
        ('Text("one\\ntwo")', "Two lines: \\n starts a new one.", None),
        (f"Text({NODE}.Font.Value)", "The font a Text+ uses (.Style.Value: its style).", "Open Sans"),
        ('Text(string.match(MediaIn1.Output.Metadata.Filename, "[^/\\\\]+$"))', "The clip's file name.", "clip.mp4"),
        (f"string.len({NODE}.StyledText.Value)", "How many characters a Text+ has.", "5"),
        (f':_, n = string.gsub({NODE}.StyledText.Value, "%a", ""); return n',
         "How many letters, not counting spaces. A colon first lets an expression take several steps.", "5"),
    ]),
    ("Dates", [
        ('Text(os.date("%d %B %Y"))', "The date on the day you render.", "13 October 2026"),
        ('Text(os.date("%A"))', "The weekday.", "Tuesday"),
        ('Text(os.date("%H:%M"))', "The clock.", "14:05"),
        (("%d", "%m", "%B", "%b", "%Y", "%y"), "Day, month as a number, its name, its short name, year, short year.", None),
        (("%A", "%a", "%H", "%I", "%M", "%S", "%p"), "Weekday, short weekday, hour (24), hour (12), minute, second, am / pm.", None),
    ]),
]


def sheet_curve(show, count=72):
    """([the sum's values], [the compared one's values] or None, lowest, highest) over the sample clip."""
    fn, ref, limits = show
    frames = [START + (END - START) * k / (count - 1) for k in range(count)]
    values = [float(fn(t)) for t in frames]
    behind = [float(ref(t)) for t in frames] if ref else None
    lo, hi = limits or (min(values + (behind or [])), max(values + (behind or [])))
    return values, behind, lo, (hi if hi > lo else lo + 1)


def sheet_code(code, node=""):
    """A cheat sheet line with the node's name written in."""
    return code.replace(NODE, node) if node else code


SHEET_ROW = "cheat_sheet"  # the row in the x: list that shows it

BY_KEY = {entry["key"]: entry for entry in LIBRARY}
GROUPS = {"Move": "moves it", "Fade": "fades it", "Words": "writes text", "Time": "a number from the clock",
          "Follow": "ties it to another node"}


def label(entry):
    return f"Expression: {entry['name']}"


BY_LABEL = {label(entry): entry for entry in LIBRARY}


def where(entry):
    """Which setting it goes on, the way Fusion's Inspector names it: "Transform > Center"."""
    target = TARGETS.get(entry["target"])
    if entry["copy_only"]:
        return "Copies the code" + (f" (for a {entry['target']})" if target else " (for any number)")
    return target[5]


def goes_on(entry):
    """The same, said in full - for the preview."""
    if entry["copy_only"]:
        if entry["target"]:
            return (f"On the Fusion page: Enter, then click the node to follow - its name is written in, and the "
                    f"code is copied to paste on the node that should follow. Meant for {TARGETS[entry['target']][5]}.")
        return "Copied for you to paste on any setting that is a number (right-click the setting > Expression)."
    setting, kinds, new_node, new_setting, _fixed, _short = TARGETS[entry["target"]]
    have = " or ".join(_NODE_NAMES[k] for k in kinds)
    other = f"a new {_NODE_NAMES[new_node]}" + (f"'s {new_setting}" if new_setting != setting else "")
    return f"Goes on: {setting} of the selected {have} - or {other}, added for it."


def value_at(entry, frame, values=None):
    """What the expression gives on `frame`, with the sliders at `values`."""
    return entry["sample"](frame, **dict(defaults(entry), **(values or {})))


def samples(entry, count=96, values=None):
    """What it does over a 4 second clip: numbers, (x, y) positions, or a few strings."""
    out = [value_at(entry, START + (END - START) * i / (count - 1), values) for i in range(count)]
    if isinstance(out[0], str):
        return [out[0], out[count // 3], out[2 * count // 3], out[-1]]
    return out


# Which node would it go on?  "has <name>" - the selected node is the right kind;
# "other <name>" - something else is selected; "none <name>" - nothing is (name: the node before MediaOut).
_LOOK_LUA = r"""
local INPUT, KINDS = %s, %s
local tool = comp.ActiveTool
if not tool then
    for _, t in pairs(comp:GetToolList(true)) do tool = t break end
end
local result
if tool then
    local attrs = tool:GetAttrs()
    local right = false
    for _, kind in ipairs(KINDS) do if attrs.TOOLS_RegID == kind then right = true end end
    result = ((right and tool[INPUT]) and "has " or "other ") .. attrs.TOOLS_Name
else
    local before = ""
    for _, t in pairs(comp:GetToolList(false)) do
        if t:GetAttrs().TOOLS_RegID == "MediaOut" then
            local inp = t:FindMainInput(1)
            local out = inp and inp:GetConnectedOutput()
            if out then before = out:GetTool():GetAttrs().TOOLS_Name end
        end
    end
    result = "none " .. before
end
comp:SetData("ClipseResult", result)
"""

_APPLY_LUA = r"""
local INPUT, PLAIN, WITH_SLIDERS, FIXED, SLIDERS = %s, %s, %s, %s, %s
local function run()
    local tool = comp.ActiveTool
    if not tool then return "no node" end
    for name, value in pairs(FIXED) do tool[name] = value end
    if not tool[INPUT] then return "no input " .. tool:GetAttrs().TOOLS_Name end
    -- Sliders for its numbers, on the node itself (the Inspector's Controls page): the
    -- expression then reads them by name, so it can be tuned there afterwards. If Fusion
    -- won't make them, the numbers are simply written into the code instead.
    local code, made = PLAIN, false
    if #SLIDERS > 0 then
        made = pcall(function()
            local controls = tool.UserControls or {}
            for _, c in ipairs(SLIDERS) do
                controls[c.id] = {LINKS_Name = c.label, LINKID_DataType = "Number", INPID_InputControl = "SliderControl",
                                  INP_Default = c.value, INP_MinScale = c.low, INP_MaxScale = c.high,
                                  INP_Integer = c.whole, ICS_ControlPage = "Controls"}
            end
            tool.UserControls = controls
            tool = tool:Refresh()
            for _, c in ipairs(SLIDERS) do
                if tool[c.id] == nil then error("no slider " .. c.id) end
            end
        end)
        if made then code = WITH_SLIDERS else tool = comp.ActiveTool or tool end
    end
    tool[INPUT]:SetExpression(code)
    return (made and "sliders " or "ok ") .. tool:GetAttrs().TOOLS_Name
end
local ok, result = pcall(run)
comp:SetData("ClipseResult", ok and result or ("error: " .. tostring(result)))
"""


def look(comp, entry):
    """("has" / "other" / "none", the node's name) - see _LOOK_LUA."""
    setting, kinds = TARGETS[entry["target"]][:2]
    from .scripts_fusion import run_lua
    answer = run_lua(comp, _LOOK_LUA % (f'"{setting}"', "{" + ", ".join(f'"{k}"' for k in kinds) + "}"))
    state, _sep, name = str(answer or "none ").partition(" ")
    return (state if state in ("has", "other", "none") else "none"), name


def _lua_text(text):
    return "[==[" + text + "]==]"


def _put(comp, setting, plain, fixed, sliders=(), with_sliders=""):
    """sliders: [(id, label, value, low, high, whole numbers only)] to make on the node, and the code that reads them."""
    table = "{" + ", ".join(f"{k} = {v}" for k, v in fixed.items()) + "}"
    made = "{" + ", ".join(f"{{id = {_lua_text(i)}, label = {_lua_text(label)}, value = {_number(value)}, "
                            f"low = {_number(low)}, high = {_number(high)}, whole = {'true' if whole else 'false'}}}"
                            for i, label, value, low, high, *rest in sliders for whole in [bool(rest and rest[0])]) + "}"
    from .scripts_fusion import run_lua
    return str(run_lua(comp, _APPLY_LUA % (f'"{setting}"', _lua_text(plain), _lua_text(with_sliders or plain), table, made)) or "")


def apply_comp(comp, key, add_tool=None, values=None, sliders=True):
    """Puts the expression where it belongs in `comp` (see TARGETS), with the
    numbers at `values` - as sliders on the node when `sliders` (else written
    into the code). (worked, message)"""
    from . import scripts_fusion
    entry = BY_KEY[key]
    plain = code(entry, values)
    if entry["copy_only"]:
        return False, "Copied - paste it on a setting (right-click \u203a Expression)"
    add_tool = add_tool or scripts_fusion.add_tool_after_selected
    setting, _kinds, new_node, new_setting, fixed, _short = TARGETS[entry["target"]]
    numbers = dict(defaults(entry), **(values or {}))
    made = [(control_id(entry, p), f"{entry['name']}: {p['label'].lower()}", numbers[p["id"]],
             min(p["low"], numbers[p["id"]]), max(p["high"], numbers[p["id"]]), p.get("whole", False))
            for p in entry["params"]] if sliders else []
    title = label(entry)
    comp.StartUndo(title)
    try:
        state, name = look(comp, entry)
        if state == "has":
            result = _put(comp, setting, plain, {}, made, control_code(entry))
            where_to = f"on {name}'s {setting}"
        else:
            added = add_tool(comp, new_node, title, undo=False)  # after the selected node, or before MediaOut
            if added == "unknown tool" or str(added or "").startswith("error:"):
                return False, f"Copied the code - Fusion couldn't add a {_NODE_NAMES[new_node]} for it"
            result = _put(comp, new_setting, plain, fixed, made, control_code(entry))
            where_to = f"on a new {_NODE_NAMES[new_node]}" + (f" after {name}" if name else "") + f" ({new_setting})"
    finally:
        comp.EndUndo(True)
    if result.startswith(("ok ", "sliders ")):
        extra = " - its sliders are on the node's Controls page" if result.startswith("sliders ") else ""
        return True, f"{entry['name']}: {where_to}{extra}"
    print(f"[expression] {title}: {result}")
    return False, "Copied the code - Fusion wouldn't take it on that node"


def _comp(resolve):
    try:
        return resolve.Fusion().GetCurrentComp() if resolve.GetCurrentPage() == "fusion" else None
    except Exception:
        return None


def plan(resolve, key):
    """What Enter would do right now, before doing it: (state, node name).
    "away": not on the Fusion page; "copy": only copies; else as look()."""
    entry = BY_KEY[key]
    if entry["copy_only"]:
        return "copy", ""
    comp = _comp(resolve)
    if comp is None:
        return "away", ""
    try:
        return look(comp, entry)
    except Exception as e:
        print(f"[expression] couldn't look at the composition: {e}")
        return "away", ""


def new_node_name(entry):
    return _NODE_NAMES[TARGETS[entry["target"]][2]] if entry["target"] else ""


def apply(resolve, key, values=None, sliders=True):
    comp = _comp(resolve)
    if comp is None:
        return False, "Copied the code - on the Fusion page, right-click a setting \u203a Expression and paste it"
    return apply_comp(comp, key, values=values, sliders=sliders)


# Nothing selected - so that the next click on a node is a change, even on the one that was selected.
_DESELECT_LUA = r"""
pcall(function()
    local flow = comp.CurrentFrame and comp.CurrentFrame.FlowView
    if flow then flow:Select() end
end)
pcall(function() comp:SetActiveTool() end)
"""


def clear_selection(resolve):
    """Deselects every node in the open composition (for picking one by a click). Not seen in
    Fusion yet: where it does nothing, a click on another node is still noticed."""
    comp = _comp(resolve)
    if comp is not None:
        try:
            from .scripts_fusion import run_lua
            run_lua(comp, _DESELECT_LUA, wait=1.0)
        except Exception as e:
            print(f"[expression] couldn't clear the selection: {e}")


NAMES_A_NODE = "Transform1"  # in the library's Follow expressions: the node to follow goes here


def with_node(text, node):
    """A library expression's code with the node to follow written in."""
    return text.replace(NAMES_A_NODE, node) if node else text


def selected_node_now(resolve):
    """The selected node's name ("" when there is none, or Resolve isn't on the Fusion page) -
    asked from Python with no script run in Fusion, so it's quick enough to ask a few times a
    second: the cheat sheet follows the node you click."""
    comp = _comp(resolve)
    if comp is None:
        return ""
    try:
        tool = getattr(comp, "ActiveTool", None) or next(iter((comp.GetToolList(True) or {}).values()), None)
        return str((tool.GetAttrs() or {}).get("TOOLS_Name") or "") if tool else ""
    except Exception:
        return ""


# The name of the selected node, to write in an expression (Transform1.Center).
_NAME_LUA = r"""
local tool = comp.ActiveTool
if not tool then
    for _, t in pairs(comp:GetToolList(true)) do tool = t break end
end
comp:SetData("ClipseResult", tool and tool:GetAttrs().TOOLS_Name or "")
"""


def selected_node_name(resolve):
    """(the selected node's name or "", what to say when there is none)."""
    comp = _comp(resolve)
    if comp is None:
        return "", "Node names are copied on the Fusion page"
    try:
        from .scripts_fusion import run_lua
        name = str(run_lua(comp, _NAME_LUA) or "")
    except Exception as e:
        return "", f"Couldn't reach Fusion: {e}"
    return name, "" if name else "Select a node in Fusion first"


# -- Everything: every function and value a Fusion expression can use, each one tried in Fusion
# (tests/live_expressions.py). Found by asking Fusion itself what an expression can reach (2026-10-14): of its
# 6,835 names these are the ones meant for expressions - the rest is Fusion's own insides (window parts, file
# formats, constants) or changes files and the system (io, os.remove, os.execute ...), and the vector types
# (Vector2, Vector3, Matrix4) crashed Resolve 21.1.1 when an expression made one. Not here: dist and
# getr / getg / getb / geta (older Fusions had them - 21.1.1 doesn't), NodeName.Size[time] (gives nothing).
EVERYTHING = [
    ("Fusion", [
        ("time", "The frame being worked out.", "37"),
        ("self", "The node the expression is on: self.Size, self.Center ...", None),
        ("comp", "The composition: comp.RenderStart, comp.RenderEnd ...", None),
        (f"{NODE}.Size", "A setting of another node, by its name.", "1.5"),
        (f"{NODE}.Center.X", "One side of a position - .Y is the other.", "0.3"),
        (f'{NODE}:GetValue("Size", time - 5)', "A setting at another frame.", "1.5"),
        (f"{NODE}.Output.Width", "A node's picture: its width in pixels - .Height its height.", "1920"),
        (f"{NODE}.Output.OriginalWidth", "...its width as it really is (without a proxy).", "1920"),
        (f"{NODE}.Output.XScale", "...the shape of its pixels: 1 when they're square.", "1"),
        (f"{NODE}.Output.Depth", "...how much colour it holds: 8, 16 or 32 bits.", "8"),
        (f"{NODE}.Output.DataWindow[1]", "...where its picture's area begins (2 bottom, 3 right, 4 top).", None),
        ("comp.RenderStart", "The first frame.", "0"),
        ("comp.RenderEnd", "The last frame.", "119"),
        ("comp.GlobalStart", "The comp's very first frame.", "0"),
        ("comp.GlobalEnd", "...and its very last.", "119"),
        ("comp.CurrentTime", "The frame the playhead is on (time: the one being worked out).", "0"),
        (_RATE, "Frames a second.", "30"),
        (_WIDTH, "The comp's width.", "1920"),
        (_HEIGHT, "The comp's height.", "1080"),
        ("iif(c, x, y)", "x when c is true, y when it isn't.", "iif(5 > 3, 1, 0) = 1"),
        ("Point(x, y)", "A position made of two numbers - for a Center or a Pivot.", None),
        ('Text("...")', "Words - for a Text+.", None),
        (":x = 2; return x * 3", "A colon first: an expression of several steps, the last says return.", "6"),
        ("bmd.noise(x)", "Smooth noise between -1 and 1: time / 20 for a slow wobble. Up to three numbers.", "-0.07"),
        ("print(x)", "Shows x in Fusion's console - to see what's going on.", None),
        ("x -- a note", "Everything after -- is a note to yourself; Fusion skips it.", None),
        ("comp.HiQ", "true when HiQ is on.", "true"),
        ("comp.Proxy", "true when proxy is on.", "false"),
        ("comp.ProxyScale", "How far proxy scales the picture down.", "1"),
        ("req:IsQuick()", "true when the node is worked out without HiQ.", "false"),
        ("req:IsNoMotionBlur()", "true when it's worked out without motion blur.", "false"),
        ("req:IsInteractive()", "true while you work - false in a render.", "true"),
        (f"{NODE}.Output.Metadata.Filename", "The file a MediaIn or Loader shows.", None),
        (f"{NODE}.Font.Value", "A setting's value where it isn't a number - a font, a style ...", "Open Sans"),
        ('self:GetSourceTool("Input")', "The node plugged into this one's Input.", None),
        (":if c then return x else return y end", "If, then, else - written out.", None),
    ]),
    ("Maths", [
        ("abs(x)", "Without its minus sign.", "abs(-3) = 3"),
        ("floor(x)", "Down to a whole number.", "floor(2.9) = 2"),
        ("ceil(x)", "Up to a whole number.", "ceil(2.1) = 3"),
        ("floor(x + 0.5)", "To the nearest whole number.", "floor(2.5 + 0.5) = 3"),
        ("min(x, y, ...)", "The smallest.", "min(4, 2, 8) = 2"),
        ("max(x, y, ...)", "The largest.", "max(4, 2, 8) = 8"),
        ("sqrt(x)", "The square root.", "sqrt(16) = 4"),
        ("pow(x, y)", "x to the power of y - the same as x ^ y.", "pow(2, 3) = 8"),
        ("exp(x)", "e to the power of x.", "exp(1) = 2.718"),
        ("log(x)", "The natural logarithm.", "log(exp(2)) = 2"),
        ("log10(x)", "How many tens: 1 for 10, 3 for 1000.", "log10(1000) = 3"),
        ("fmod(x, y)", "What's left after dividing, with x's sign.", "fmod(-7, 3) = -1"),
        ("modf(x)", "The whole part.", "modf(2.7) = 2"),
        ("frexp(x)", "x as a fraction times a power of 2 - the fraction.", "frexp(8) = 0.5"),
        ("ldexp(x, y)", "x times 2 to the power of y.", "ldexp(0.5, 4) = 8"),
        ("sin(x)", "The sine - swings between -1 and 1.", "sin(pi / 2) = 1"),
        ("cos(x)", "The cosine.", "cos(0) = 1"),
        ("tan(x)", "The tangent.", "tan(pi / 4) = 1"),
        ("asin(x)", "The angle for a sine, in radians.", "asin(1) = 1.571"),
        ("acos(x)", "The angle for a cosine.", "acos(1) = 0"),
        ("atan(x)", "The angle for a tangent.", "atan(1) = 0.785"),
        ("atan2(y, x)", "The angle towards a point - to point at something.", "atan2(1, 1) = 0.785"),
        ("sinh(x)", "The hyperbolic sine.", "sinh(1) = 1.175"),
        ("cosh(x)", "The hyperbolic cosine.", "cosh(1) = 1.543"),
        ("tanh(x)", "The hyperbolic tangent: a soft S from -1 to 1.", "tanh(1) = 0.762"),
        ("deg(x)", "Radians into degrees.", "deg(pi) = 180"),
        ("rad(x)", "Degrees into radians.", "rad(180) = 3.142"),
        ("pi", "3.14159...", "3.14159"),
        ("huge", "Larger than any number - for comparing.", "huge > 1e300"),
        ("random()", "From 0 to 1, a new one each frame.", None),
        ("random(x)", "A whole number from 1 to x.", None),
        ("random(x, y)", "A whole number from x to y.", None),
        ("randomseed(x)", "Picks which random numbers come: the same seed, the same numbers.", None),
        ("math.sin(x)", "Every one of these also as math.something - the same function.", "math.sin(0) = 0"),
        (("+", "-", "*", "/", "^", "%"), "Add, take away, times, divide, to the power of, left after dividing.", None),
    ]),
    ("Comparing and choosing", [
        (("==", "~=", "<", ">", "<=", ">="), "Equal, not equal, smaller, larger, at most, at least.", None),
        (("and", "or", "not"), "Both, either, the opposite.", None),
        ("c and x or y", "x when c is true, else y - the short way of iif.", "(5 > 3 and 1 or 0) = 1"),
    ]),
    ("Text", [
        ("s .. w", "Joins words and numbers.", '"Frame " .. 37'),
        ('"\\n"', "A new line, inside words.", None),
        ("tostring(x)", "A number as words.", '"12"'),
        ("tonumber(s)", "Words as a number.", "12"),
        ("string.len(s)", "How many characters.", "5"),
        ("string.upper(s)", "In capitals.", "HELLO"),
        ("string.lower(s)", "In small letters.", "hello"),
        ("string.sub(s, x, y)", "A part: from the x-th to the y-th character.", "Hel"),
        ("string.rep(s, x)", "x times over.", "HiHiHi"),
        ("string.reverse(s)", "Back to front.", "olleH"),
        ("string.find(s, w)", "Where w is in s, counting from 1.", "3"),
        ("string.match(s, w)", "The part of s that matches w - %d+ is a number.", "37"),
        ('string.gsub(s, w, "new")', "s with every w changed into the words after it.", "Hexxo"),
        ("string.gmatch(s, w)", "Each part that matches, one after another (for a loop).", None),
        ("string.format(w, ...)", "Numbers into words the way w says: %d whole, %.2f two decimals, %02d 07.", "07"),
        ("string.byte(s)", "A character's number.", "65"),
        ("string.char(x, ...)", "Characters from their numbers.", "Hi"),
        ("s:upper()", "Every string. something also as s:something().", "HELLO"),
    ]),
    ("Lists", [
        ("{x, y, z}", "A list.", None),
        ("t[1]", "Its first item.", None),
        ("#t", "How many items.", "3"),
        ("table.concat(t, s)", "The items joined into words, s between them.", "a-b"),
        ("table.insert(t, x)", "Adds x at the end.", None),
        ("table.remove(t)", "Takes the last one off.", None),
        ("table.sort(t)", "Puts it in order.", None),
        ("table.unpack(t)", "The items one by one - unpack(t) too.", None),
        ("table.maxn(t)", "The highest number used for an item.", "3"),
        ("table.getn(t)", "How many items - the old way.", "3"),
        ("table.pack(...)", "A list of what's given.", None),
        ("table.move(t, x, y, z)", "Copies items x to y of a list to place z.", None),
        ("table.foreach(t, f)", "f on every item - the old way.", None),
        ("table.foreachi(t, f)", "...on every numbered item.", None),
        ("select(x, ...)", "From the x-th value on - '#' for how many.", "3"),
        (("pairs(t)", "ipairs(t)", "next(t)"), "Every item one after another, for a loop.", None),
    ]),
    ("Date and time", [
        ('os.date("%d %B %Y")', "The date, the way the letters say.", "13 October 2026"),
        ("os.time()", "Seconds since 1970.", None),
        ("os.clock()", "Seconds of work Resolve has done.", None),
        ("os.difftime(x, y)", "Seconds from y to x.", "10"),
        ('os.getenv("HOME")', "A setting of the computer.", "/home/you"),
    ]),
    ("Bits", [
        ("bit.band(x, y)", "Bits in both.", "8"),
        ("bit.bor(x, y)", "Bits in either.", "14"),
        ("bit.bxor(x, y)", "Bits in one, not both.", "6"),
        ("bit.bnot(x)", "Every bit turned over.", "-13"),
        ("bit.lshift(x, y)", "Bits y places to the left: x times 2^y.", "48"),
        ("bit.rshift(x, y)", "...to the right.", "3"),
        ("bit.arshift(x, y)", "...to the right, keeping a minus sign.", "-3"),
        ("bit.rol(x, y)", "Bits turned round to the left.", "48"),
        ("bit.ror(x, y)", "...to the right.", None),
        ("bit.bswap(x)", "Its bytes in reverse order.", None),
        ("bit.tobit(x)", "As a 32-bit whole number.", "12"),
        ("bit.tohex(x)", "As hexadecimal.", "000000ff"),
    ]),
    ("Lua", [
        ("type(x)", "What x is: number, string, table ...", '"number"'),
        ("pcall(f)", "Runs f - and carries on if it goes wrong.", None),
        ("assert(c, s)", "Stops with s when c isn't true.", None),
        ("error(s)", "Stops with s.", None),
    ]),
]
