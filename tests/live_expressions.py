"""Every piece of the expression cheat sheet, tried in the real Fusion - not the stand-in.

    python3 tests/live_expressions.py        (DaVinci Resolve open - not while you're working in it)

On a scratch timeline ("ds scratch - expressions", left there - delete it when you like): one picture, a Fusion
composition on it, a few nodes to point at, and each piece put on a node as its expression. Fusion works it out
at a frame, and the answer has to be what the piece says it gives. Every piece of the sheet has a case here
(a piece without one fails), the ones in a tile of several each their own. The timeline is switched while it
runs - your page and your timeline are as they were afterwards.
"""
import math
import sys
import time

import _setup  # noqa: F401 (the project on the path)
from clipse import fusion_expressions as fx
from clipse import resolve_client as rc
from clipse import scripts_fusion as sf

NAME = "ds scratch - expressions"
REF, WORDS, BG = "DSRef", "DSWords", "DSBg"   # the nodes a piece points at (NodeName)
# the nodes to point at: DSRef a Transform (Size 1.5, Center 0.3, 0.6), DSWords a Text+ ("Hello"), DSBg a
# Background (red 0.25, green 0.5, blue 0.75, alpha 1)


def near(want, tol=1e-3):
    return lambda got: isinstance(got, (int, float)) and abs(got - want) <= tol * max(1.0, abs(want))


def between(lo, hi, whole=False):
    return lambda got: isinstance(got, (int, float)) and lo <= got <= hi and (not whole or float(got).is_integer())


def cases(c):
    """{sheet code: [(expression, "n" a number / "p" a position / "t" words, frame, what it must give)]}.
    c: the comp's own numbers (start, end, rate, width, height, gstart, gend)."""
    S, E, R, W, H = c["start"], c["end"], c["rate"], c["width"], c["height"]
    rate, width, height = fx._RATE, fx._WIDTH, fx._HEIGHT
    f = 37
    n = REF
    return {
        # Composition
        "time": [("time", "n", f, near(f))],
        "comp.RenderStart": [("comp.RenderStart", "n", f, near(S))],
        "comp.RenderEnd": [("comp.RenderEnd", "n", f, near(E))],
        rate: [(rate, "n", f, near(R))],
        width: [(width, "n", f, near(W))],
        height: [(height, "n", f, near(H))],
        f"{width} / {height}": [(f"{width} / {height}", "n", f, near(W / H))],
        # Time
        "time - comp.RenderStart": [("time - comp.RenderStart", "n", f, near(f - S))],
        "comp.RenderEnd - time": [("comp.RenderEnd - time", "n", f, near(E - f))],
        "(time - comp.RenderStart) / (comp.RenderEnd - comp.RenderStart)":
            [("(time - comp.RenderStart) / (comp.RenderEnd - comp.RenderStart)", "n", f, near((f - S) / (E - S)))],
        f"time / {rate}": [(f"time / {rate}", "n", f, near(f / R))],
        "time * 3": [("time * 3", "n", f, near(f * 3))],
        "time % 30": [("time % 30", "n", f, near(f % 30))],
        "floor(time / 10)": [("floor(time / 10)", "n", f, near(math.floor(f / 10)))],
        "max(0, time - 20)": [("max(0, time - 20)", "n", 10, near(0)), ("max(0, time - 20)", "n", f, near(f - 20))],
        "min(1, time / 15)": [("min(1, time / 15)", "n", 6, near(0.4)), ("min(1, time / 15)", "n", f, near(1))],
        f"max(0, floor(60 - time / {rate}))": [(f"max(0, floor(60 - time / {rate}))", "n", f, near(max(0, math.floor(60 - f / R))))],
        # Waves
        "sin(time / 10)": [("sin(time / 10)", "n", f, near(math.sin(f / 10)))],
        "abs(sin(time / 10))": [("abs(sin(time / 10))", "n", f, near(abs(math.sin(f / 10))))],
        "0.5 + 0.5 * sin(time / 10)": [("0.5 + 0.5 * sin(time / 10)", "n", f, near(0.5 + 0.5 * math.sin(f / 10)))],
        "3 * sin(time / 10)": [("3 * sin(time / 10)", "n", f, near(3 * math.sin(f / 10)))],
        "sin(time / 20)": [("sin(time / 20)", "n", f, near(math.sin(f / 20)))],
        "cos(time / 10)": [("cos(time / 10)", "n", f, near(math.cos(f / 10)))],
        "bmd.noise(time / 20)": [("bmd.noise(time / 20)", "n", f, between(-1, 1))],
        # Easing
        f"1 - cos({fx._U} * pi / 2)": [(f"1 - cos({fx._U} * pi / 2)", "n", f, near(1 - math.cos(f / E * math.pi / 2)))],
        f"sin({fx._U} * pi / 2)": [(f"sin({fx._U} * pi / 2)", "n", f, near(math.sin(f / E * math.pi / 2)))],
        f"(1 - cos({fx._U} * pi)) / 2": [(f"(1 - cos({fx._U} * pi)) / 2", "n", f, near((1 - math.cos(f / E * math.pi)) / 2))],
        f"{fx._U} ^ 3": [(f"{fx._U} ^ 3", "n", f, near((f / E) ** 3))],
        f"1 - (1 - {fx._U}) ^ 3": [(f"1 - (1 - {fx._U}) ^ 3", "n", f, near(1 - (1 - f / E) ** 3))],
        f"1 - 2 ^ (-10 * {fx._U})": [(f"1 - 2 ^ (-10 * {fx._U})", "n", f, near(1 - 2 ** (-10 * f / E)))],
        f"1 + 2.70158 * ({fx._U} - 1) ^ 3 + 1.70158 * ({fx._U} - 1) ^ 2":
            [(f"1 + 2.70158 * ({fx._U} - 1) ^ 3 + 1.70158 * ({fx._U} - 1) ^ 2", "n", f,
              near(1 + 2.70158 * (f / E - 1) ** 3 + 1.70158 * (f / E - 1) ** 2))],
        # Moving
        "Point(cos(time * 0.1) * 0.4 + 0.5, sin(time * 0.1) * 0.4 + 0.5)":
            [("Point(cos(time * 0.1) * 0.4 + 0.5, sin(time * 0.1) * 0.4 + 0.5)", "p", f,
              (math.cos(f * 0.1) * 0.4 + 0.5, math.sin(f * 0.1) * 0.4 + 0.5))],
        "Point(0.5, sin(time * 0.1) * 0.4 + 0.5)": [("Point(0.5, sin(time * 0.1) * 0.4 + 0.5)", "p", f, (0.5, math.sin(f * 0.1) * 0.4 + 0.5))],
        f"time * 360 / {rate}": [(f"time * 360 / {rate}", "n", f, near(f * 360 / R))],
        # Counters
        f'ceil({fx._U} * 100) .. "%"': [(f'ceil({fx._U} * 100) .. "%"', "t", f, f"{math.ceil(f / E * 100)}%")],
        f'"Progress: " .. ceil({fx._U} * 100) .. "%"': [(f'"Progress: " .. ceil({fx._U} * 100) .. "%"', "t", f,
                                                       f"Progress: {math.ceil(f / E * 100)}%")],
        f"ceil(time / {rate})": [(f"ceil(time / {rate})", "n", f, near(math.ceil(f / R)))],
        f"ceil((comp.RenderEnd - time) / {rate})": [(f"ceil((comp.RenderEnd - time) / {rate})", "n", f, near(math.ceil((E - f) / R)))],
        f'"9:" .. string.format("%02d", max(30 - floor(time / {rate}), 0))':
            [(f'"9:" .. string.format("%02d", max(30 - floor(time / {rate}), 0))', "t", f, "9:%02d" % max(30 - math.floor(f / R), 0))],
        # Words, more
        f':_, n = string.gsub({fx.NODE}.StyledText.Value, "\\n", ""); return n + 1':
            [(f':_, n = string.gsub({WORDS}.StyledText.Value, "\\n", ""); return n + 1', "n", 0, near(1)),
             (':_, n = string.gsub("one\\ntwo", "\\n", ""); return n + 1', "n", 0, near(2))],
        f':_, n = string.gsub({fx.NODE}.StyledText.Value, "%S+", ""); return n':
            [(f':_, n = string.gsub({WORDS}.StyledText.Value, "%S+", ""); return n', "n", 0, near(1)),
             (':_, n = string.gsub("two words", "%S+", ""); return n', "n", 0, near(2))],
        f':_, n = string.gsub({fx.NODE}.StyledText.Value, "[AEIOUaeiou]", ""); return n':
            [(f':_, n = string.gsub({WORDS}.StyledText.Value, "[AEIOUaeiou]", ""); return n', "n", 0, near(2))],
        **{p: [(f':_, n = string.gsub("Hello 42!", "{p}", ""); return n', "n", 0, near(k))]
           for p, k in (("%a", 5), ("%d", 2), ("%s", 1), ("%u", 1), ("%l", 4), ("%p", 1))},
        'Text("one\\ntwo")': [('Text("one\\ntwo")', "t", 0, "one\\ntwo")],
        f"Text({fx.NODE}.Font.Value)": [(f"Text({WORDS}.Font.Value)", "t", 0, lambda got: len(str(got)) > 1)],
        # (a clip's file is in its information once its picture has been worked out - always in a comp in use,
        # not in this test's, where nothing is drawn; seen giving the file in Fusion 21.1.1. Here: the information is there)
        'Text(string.match(MediaIn1.Output.Metadata.Filename, "[^/\\\\]+$"))':
            [("Text(type(MediaIn1.Output.Metadata))", "t", f, "table")],
        # Choices, more
        ":if time < 10 then return 0 else return 90 end": [(":if time < 10 then return 0 else return 90 end", "n", 5, near(0)),
                                                          (":if time < 10 then return 0 else return 90 end", "n", f, near(90))],
        "iif(comp.HiQ, 1, 0)": [("iif(comp.HiQ, 1, 0)", "n", 0, between(0, 1, whole=True))],
        # Other nodes, more
        'self:GetSourceTool("Input"):GetValue("Size", time)': [('self:GetSourceTool("Input"):GetValue("Size", time)', "n", f, near(1.5))],
        # Maths
        "min(x, y)": [("min(3, 5)", "n", 0, near(3)), ("min(4, 2, 8)", "n", 0, near(2))],
        "max(x, y)": [("max(3, 5)", "n", 0, near(5))],
        "abs(x)": [("abs(-3)", "n", 0, near(3))],
        "floor(x)": [("floor(2.9)", "n", 0, near(2))],
        "ceil(x)": [("ceil(2.1)", "n", 0, near(3))],
        "floor(x + 0.5)": [("floor(2.5 + 0.5)", "n", 0, near(3)), ("floor(2.4 + 0.5)", "n", 0, near(2))],
        "sqrt(x)": [("sqrt(16)", "n", 0, near(4))],
        "x ^ 2": [("3 ^ 2", "n", 0, near(9))],
        "x % y": [("7 % 3", "n", 0, near(1))],
        "atan2(y, x)": [("atan2(1, 1)", "n", 0, near(math.pi / 4))],
        "deg(x)": [("deg(pi)", "n", 0, near(180))],
        "random(1, 10)": [("random(1, 10)", "n", f, between(1, 10, whole=True))],
        ":randomseed(7); return random()": [(":randomseed(7); return random()", "n", 3, between(0, 1)),
                                             (":randomseed(7); return random()", "n", 90, "same as before")],
        "pi": [("pi", "n", 0, near(math.pi))],
        "iif(time > 30, 1, 0)": [("iif(time > 30, 1, 0)", "n", 20, near(0)), ("iif(time > 30, 1, 0)", "n", f, near(1))],
        "(time > 30 and 1 or 0)": [("(time > 30 and 1 or 0)", "n", 20, near(0)), ("(time > 30 and 1 or 0)", "n", f, near(1))],
        "==": [("iif(3 == 3, 1, 0)", "n", 0, near(1))],
        "~=": [("iif(3 ~= 4, 1, 0)", "n", 0, near(1))],
        "<": [("iif(3 < 4, 1, 0)", "n", 0, near(1))],
        ">": [("iif(3 > 4, 1, 0)", "n", 0, near(0))],
        "<=": [("iif(4 <= 4, 1, 0)", "n", 0, near(1))],
        ">=": [("iif(3 >= 4, 1, 0)", "n", 0, near(0))],
        "iif(x > 0 and y > 0, 1, 0)": [("iif(true and false, 1, 0)", "n", 0, near(0)), ("iif(true or false, 1, 0)", "n", 0, near(1)),
                               ("iif(not false, 1, 0)", "n", 0, near(1))],
        # Other nodes
        "self.Size": [("self.Size", "n", 0, near(1.0))],  # (the probe's own Size: 1, as it comes)
        f"{fx.NODE}.Size": [(f"{n}.Size", "n", 0, near(1.5))],
        f"{fx.NODE}.Center.X": [(f"{n}.Center.X", "n", 0, near(0.3)), (f"{n}.Center.Y", "n", 0, near(0.6))],
        f"Point({fx.NODE}.Center.X, 0.5)": [(f"Point({n}.Center.X, 0.5)", "p", 0, (0.3, 0.5))],
        f'{fx.NODE}:GetValue("Size", time - 5)': [(f'{n}:GetValue("Size", time - 5)', "n", f, near(1.5))],
        f'{fx.NODE}:GetValue("Center", time - 5).X': [(f'{n}:GetValue("Center", time - 5).X', "n", f, near(0.3))],
        f"sqrt(({fx.NODE}.Center.X - 0.5) ^ 2 + ({fx.NODE}.Center.Y - 0.5) ^ 2)":
            [(f"sqrt(({n}.Center.X - 0.5) ^ 2 + ({n}.Center.Y - 0.5) ^ 2)", "n", 0, near(math.hypot(0.2, 0.1)))],
        'Text(string.format("%.2f", x))': [('Text(string.format("%.2f", pi))', "t", 0, "3.14")],
        'Text(string.format("%d:%02d", floor(x / 60), x % 60))':
            [('Text(string.format("%d:%02d", floor(65 / 60), 65 % 60))', "t", 0, "1:05")],
        # Picture size
        f"{fx.NODE}.Output.Width": [(f"{BG}.Output.Width", "n", 0, near(W))],
        f"{fx.NODE}.Output.Height": [(f"{BG}.Output.Height", "n", 0, near(H))],
        f"{fx.NODE}.Output.DataWindow[1]": [(f"{BG}.Output.DataWindow[1]", "n", 0, between(-1, W))],
        f"({fx.NODE}.Output.DataWindow[3] - {fx.NODE}.Output.DataWindow[1]) / {fx.NODE}.Output.Width":
            [(f"({BG}.Output.DataWindow[3] - {BG}.Output.DataWindow[1]) / {BG}.Output.Width", "n", 0, between(0, 1.01))],
        f"({fx.NODE}.Output.DataWindow[4] - {fx.NODE}.Output.DataWindow[2]) / {fx.NODE}.Output.Height":
            [(f"({BG}.Output.DataWindow[4] - {BG}.Output.DataWindow[2]) / {BG}.Output.Height", "n", 0, between(0, 1.01))],
        # Words
        'Text("Hello")': [('Text("Hello")', "t", 0, "Hello")],
        'Text("Frame " .. time)': [('Text("Frame " .. time)', "t", f, f"Frame {f}")],
        f"{fx.NODE}.StyledText.Value": [(f"Text({WORDS}.StyledText.Value)", "t", 0, "Hello")],
        f"Text(string.upper({fx.NODE}.StyledText.Value))": [(f"Text(string.upper({WORDS}.StyledText.Value))", "t", 0, "HELLO")],
        'Text(string.format("%02d", time))': [('Text(string.format("%02d", time))', "t", 7, "07")],
        f"string.len({fx.NODE}.StyledText.Value)": [(f"string.len({WORDS}.StyledText.Value)", "n", 0, near(5))],
        f':_, n = string.gsub({fx.NODE}.StyledText.Value, "%a", ""); return n':
            [(f':_, n = string.gsub({WORDS}.StyledText.Value, "%a", ""); return n', "n", 0, near(5))],
        # (Words, too)
        "string.sub(s, 1, 3)": [('Text(string.sub("Hello", 1, 3))', "t", 0, "Hel")],
        # Dates
        'Text(os.date("%d %B %Y"))': [('Text(os.date("%d %B %Y"))', "t", 0, time.strftime("%d %B %Y"))],
        'Text(os.date("%A"))': [('Text(os.date("%A"))', "t", 0, time.strftime("%A"))],
        'Text(os.date("%H:%M"))': [('Text(os.date("%H"))', "t", 0, time.strftime("%H"))],
        **{code: [(f'Text(os.date("{code}"))', "t", 0, time.strftime(code))]
           for code in ("%d", "%m", "%B", "%b", "%Y", "%y", "%A", "%a", "%H", "%I", "%M", "%p")},
        "%S": [('Text(os.date("%S"))', "t", 0, lambda got: str(got).isdigit() and len(str(got)) == 2)],
    }


def everything(c):
    """{code: [cases]} for the Everything list (fx.EVERYTHING) - the same way."""
    S, E, R, W, H = c["start"], c["end"], c["rate"], c["width"], c["height"]
    n, f = REF, 37
    t = lambda expr, want, frame=0: [(expr, "t", frame, want)]   # noqa: E731 (words)
    num = lambda expr, want, frame=0: [(expr, "n", frame, want if callable(want) else near(want))]  # noqa: E731
    return {
        # Fusion
        "time": num("time", f, f), "self": num("self.Size", 1.0), "comp": num("comp.RenderEnd", E),
        f"{fx.NODE}.Size": num(f"{n}.Size", 1.5), f"{fx.NODE}.Center.X": num(f"{n}.Center.X", 0.3),
        f'{fx.NODE}:GetValue("Size", time - 5)': num(f'{n}:GetValue("Size", time - 5)', 1.5, f),
        f"{fx.NODE}.Output.Width": num(f"{BG}.Output.Width", W),
        f"{fx.NODE}.Output.OriginalWidth": num(f"{BG}.Output.OriginalWidth", W),
        f"{fx.NODE}.Output.XScale": num(f"{BG}.Output.XScale", 1),
        f"{fx.NODE}.Output.Depth": num(f"{BG}.Output.Depth", between(1, 32)),
        f"{fx.NODE}.Output.DataWindow[1]": num(f"{BG}.Output.DataWindow[1]", between(-1, W)),
        "comp.RenderStart": num("comp.RenderStart", S), "comp.RenderEnd": num("comp.RenderEnd", E),
        "comp.GlobalStart": num("comp.GlobalStart", c["gstart"]), "comp.GlobalEnd": num("comp.GlobalEnd", c["gend"]),
        "comp.CurrentTime": num("comp.CurrentTime", between(-1e6, 1e6)),
        fx._RATE: num(fx._RATE, R), fx._WIDTH: num(fx._WIDTH, W), fx._HEIGHT: num(fx._HEIGHT, H),
        "iif(c, x, y)": num("iif(5 > 3, 1, 0)", 1), "Point(x, y)": [("Point(0.2, 0.4)", "p", 0, (0.2, 0.4))],
        'Text("...")': t('Text("Hello")', "Hello"), ":x = 2; return x * 3": num(":x = 2; return x * 3", 6),
        "bmd.noise(x)": num("bmd.noise(1.5)", between(-1, 1)), "print(x)": num(":print(42); return 1", 1),
        # Fusion, more
        "x -- a note": num("time -- a note", f, f),
        "comp.HiQ": t("Text(tostring(comp.HiQ))", lambda got: got in ("true", "false")),
        "comp.Proxy": t("Text(tostring(comp.Proxy))", lambda got: got in ("true", "false")),
        "comp.ProxyScale": num("comp.ProxyScale", between(1, 16)),
        "req:IsQuick()": t("Text(tostring(req:IsQuick()))", lambda got: got in ("true", "false")),
        "req:IsNoMotionBlur()": t("Text(tostring(req:IsNoMotionBlur()))", lambda got: got in ("true", "false")),
        "req:IsInteractive()": t("Text(tostring(req:IsInteractive()))", lambda got: got in ("true", "false")),
        f"{fx.NODE}.Output.Metadata.Filename": [("Text(type(MediaIn1.Output.Metadata))", "t", f, "table")],  # (see above)
        f"{fx.NODE}.Font.Value": t(f"Text({WORDS}.Font.Value)", lambda got: len(str(got)) > 1),
        'self:GetSourceTool("Input")': num('self:GetSourceTool("Input"):GetValue("Size", time)', 1.5),
        ":if c then return x else return y end": num(":if 5 > 3 then return 1 else return 0 end", 1),
        '"\\n"': t('Text("a\\nb")', "a\\nb"),
        # Maths
        "abs(x)": num("abs(-3)", 3), "floor(x)": num("floor(2.9)", 2), "ceil(x)": num("ceil(2.1)", 3),
        "floor(x + 0.5)": num("floor(2.5 + 0.5)", 3), "min(x, y, ...)": num("min(4, 2, 8)", 2),
        "max(x, y, ...)": num("max(4, 2, 8)", 8), "sqrt(x)": num("sqrt(16)", 4), "pow(x, y)": num("pow(2, 3)", 8),
        "exp(x)": num("exp(1)", math.e), "log(x)": num("log(exp(2))", 2), "log10(x)": num("log10(1000)", 3),
        "fmod(x, y)": num("fmod(-7, 3)", -1), "modf(x)": num("modf(2.7)", 2), "frexp(x)": num("frexp(8)", 0.5),
        "ldexp(x, y)": num("ldexp(0.5, 4)", 8), "sin(x)": num("sin(pi / 2)", 1), "cos(x)": num("cos(0)", 1),
        "tan(x)": num("tan(pi / 4)", 1), "asin(x)": num("asin(1)", math.pi / 2), "acos(x)": num("acos(1)", 0),
        "atan(x)": num("atan(1)", math.pi / 4), "atan2(y, x)": num("atan2(1, 1)", math.pi / 4),
        "sinh(x)": num("sinh(1)", math.sinh(1)), "cosh(x)": num("cosh(1)", math.cosh(1)), "tanh(x)": num("tanh(1)", math.tanh(1)),
        "deg(x)": num("deg(pi)", 180), "rad(x)": num("rad(180)", math.pi), "pi": num("pi", math.pi),
        "huge": num("iif(huge > 1e300, 1, 0)", 1), "random()": num("random()", between(0, 1)),
        "random(x)": num("random(6)", between(1, 6, whole=True)), "random(x, y)": num("random(3, 5)", between(3, 5, whole=True)),
        "randomseed(x)": num(":randomseed(3); return random(1, 1000)", between(1, 1000, whole=True)),
        "math.sin(x)": num("math.sin(0)", 0),
        "+": num("2 + 3", 5), "-": num("2 - 3", -1), "*": num("2 * 3", 6), "/": num("3 / 2", 1.5),
        "^": num("2 ^ 3", 8), "%": num("7 % 3", 1),
        # Comparing and choosing
        "==": num("iif(3 == 3, 1, 0)", 1), "~=": num("iif(3 ~= 4, 1, 0)", 1), "<": num("iif(3 < 4, 1, 0)", 1),
        ">": num("iif(3 > 4, 1, 0)", 0), "<=": num("iif(4 <= 4, 1, 0)", 1), ">=": num("iif(3 >= 4, 1, 0)", 0),
        "and": num("iif(true and false, 1, 0)", 0), "or": num("iif(true or false, 1, 0)", 1),
        "not": num("iif(not false, 1, 0)", 1), "c and x or y": num("(5 > 3 and 1 or 0)", 1),
        # Text
        "s .. w": t('Text("Frame " .. 37)', "Frame 37"), "tostring(x)": t("Text(tostring(12))", "12"),
        "tonumber(s)": num('tonumber("12")', 12), "string.len(s)": num('string.len("Hello")', 5),
        "string.upper(s)": t('Text(string.upper("Hello"))', "HELLO"), "string.lower(s)": t('Text(string.lower("HeLLo"))', "hello"),
        "string.sub(s, x, y)": t('Text(string.sub("Hello", 1, 3))', "Hel"), "string.rep(s, x)": t('Text(string.rep("Hi", 3))', "HiHiHi"),
        "string.reverse(s)": t('Text(string.reverse("Hello"))', "olleH"), "string.find(s, w)": num('string.find("Hello", "l")', 3),
        "string.match(s, w)": t('Text(string.match("frame 37", "%d+"))', "37"),
        'string.gsub(s, w, "new")': t('Text((string.gsub("Hello", "l", "x")))', "Hexxo"),
        "string.gmatch(s, w)": num(':local n = 0; for w in string.gmatch("a b c", "%a") do n = n + 1 end; return n', 3),
        "string.format(w, ...)": t('Text(string.format("%02d", 7))', "07"), "string.byte(s)": num('string.byte("A")', 65),
        "string.char(x, ...)": t("Text(string.char(72, 105))", "Hi"), "s:upper()": t('Text(("Hello"):upper())', "HELLO"),
        # Lists
        "{x, y, z}": num(":local t = {4, 5, 6}; return t[3]", 6), "t[1]": num(":local t = {4, 5, 6}; return t[1]", 4),
        "#t": num("#({1, 2, 3})", 3), "table.concat(t, s)": t('Text(table.concat({"a", "b"}, "-"))', "a-b"),
        "table.insert(t, x)": num(":local t = {1}; table.insert(t, 9); return t[2]", 9),
        "table.remove(t)": num(":local t = {1, 9}; return table.remove(t)", 9),
        "table.sort(t)": num(":local t = {3, 1, 2}; table.sort(t); return t[1]", 1),
        "table.unpack(t)": num("select(2, table.unpack({4, 5, 6}))", 5), "table.maxn(t)": num("table.maxn({1, 2, 3})", 3),
        "table.getn(t)": num("table.getn({1, 2, 3})", 3), "table.pack(...)": num("#(table.pack(4, 5))", 2),
        "table.move(t, x, y, z)": num(":local t = table.move({7, 8, 9}, 1, 2, 2); return t[3]", 8),
        "table.foreach(t, f)": num(":local s = 0; table.foreach({1, 2, 3}, function(k, v) s = s + v end); return s", 6),
        "table.foreachi(t, f)": num(":local s = 0; table.foreachi({1, 2, 3}, function(k, v) s = s + v end); return s", 6),
        "select(x, ...)": num('select("#", 1, 2, 3)', 3),
        "pairs(t)": num(":local n = 0; for k, v in pairs({a = 1, b = 2}) do n = n + v end; return n", 3),
        "ipairs(t)": num(":local n = 0; for i, v in ipairs({4, 5}) do n = n + v end; return n", 9),
        "next(t)": num(":local k, v = next({7}); return v", 7),
        # Date and time
        'os.date("%d %B %Y")': t('Text(os.date("%d %B %Y"))', time.strftime("%d %B %Y")),
        "os.time()": t("Text(tostring(os.time()))", lambda got: str(got).isdigit() and abs(int(got) - time.time()) < 120),
        "os.clock()": num("os.clock()", between(0, 1e7)), "os.difftime(x, y)": num("os.difftime(20, 10)", 10),
        'os.getenv("HOME")': t('Text(tostring(os.getenv("HOME") or os.getenv("USERPROFILE")))', lambda got: len(str(got)) > 1),
        # Bits
        "bit.band(x, y)": num("bit.band(12, 10)", 8), "bit.bor(x, y)": num("bit.bor(12, 10)", 14),
        "bit.bxor(x, y)": num("bit.bxor(12, 10)", 6), "bit.bnot(x)": num("bit.bnot(12)", -13),
        "bit.lshift(x, y)": num("bit.lshift(12, 2)", 48), "bit.rshift(x, y)": num("bit.rshift(12, 2)", 3),
        "bit.arshift(x, y)": num("bit.arshift(-12, 2)", -3), "bit.rol(x, y)": num("bit.rol(12, 2)", 48),
        "bit.ror(x, y)": num("bit.ror(48, 2)", 12), "bit.bswap(x)": num("bit.bswap(bit.bswap(12))", 12),
        "bit.tobit(x)": num("bit.tobit(12)", 12), "bit.tohex(x)": t("Text(bit.tohex(255))", "000000ff"),
        # Lua
        "type(x)": t("Text(type(3))", "number"), "pcall(f)": num("pcall(function() return 1 end) and 1 or 0", 1),
        "assert(c, s)": num("assert(5, 'no')", 5), "error(s)": num(':return pcall(error, "x") and 1 or 0', 0),
    }


SETUP = r'''
local function node(kind, name)
    local t = comp:FindTool(name)
    if not t then t = comp:AddTool(kind, -32768, -32768); t:SetAttrs({TOOLS_Name = name}) end
    return t
end
local ref = node("Transform", "DSRef"); ref.Size = 1.5; ref.Center = {0.3, 0.6}
local words = node("TextPlus", "DSWords"); words.StyledText = "Hello"
local bg = node("Background", "DSBg")
bg.TopLeftRed = 0.25; bg.TopLeftGreen = 0.5; bg.TopLeftBlue = 0.75; bg.TopLeftAlpha = 1
local probe = node("Transform", "DSProbe"); node("TextPlus", "DSText")
probe.Input:ConnectTo(ref.Output)  -- (for "the node plugged into this one")

local a = comp:GetAttrs()
comp:SetData("DSLive", table.concat({a.COMPN_RenderStart, a.COMPN_RenderEnd,
    comp:GetPrefs("Comp.FrameFormat.Rate"), comp:GetPrefs("Comp.FrameFormat.Width"),
    comp:GetPrefs("Comp.FrameFormat.Height"), a.COMPN_GlobalStart, a.COMPN_GlobalEnd}, " "))
'''

TRY = r'''
local probe, words = comp:FindTool("DSProbe"), comp:FindTool("DSText")
local out = {}
for i, case in ipairs(CASES) do
    local expr, kind, frame = case[1], case[2], case[3]
    local tool, input = probe, "Angle"
    if kind == "p" then input = "Center" elseif kind == "t" then tool, input = words, "StyledText" end
    local ok, problem = pcall(function() tool[input]:SetExpression(expr) end)
    local v
    if ok then ok, v = pcall(function() return tool:GetInput(input, frame) end) end
    pcall(function() tool[input]:SetExpression(nil) end)
    if type(v) == "table" then v = "P " .. tostring(v[1]) .. " " .. tostring(v[2]) end
    if not ok then v = "ERROR " .. tostring(problem or v) end
    out[#out + 1] = (tostring(v):gsub("\n", "\\n"))  -- (a line break in an answer: written as \n, one line each)
end
comp:SetData("DSLive", table.concat(out, "\n"))
'''


def lua_string(text):
    return "[======[" + text + "]======]"


def main():
    r = rc.connect_to_resolve(timeout=8)
    page = r.GetCurrentPage()
    project = r.GetProjectManager().GetCurrentProject()
    pool = project.GetMediaPool()
    home = project.GetCurrentTimeline()
    timelines = {project.GetTimelineByIndex(i).GetName(): project.GetTimelineByIndex(i)
                 for i in range(1, project.GetTimelineCount() + 1)}
    failed, total = [], 0
    try:
        scratch = timelines.get(NAME) or pool.CreateEmptyTimeline(NAME)
        project.SetCurrentTimeline(scratch)
        items = scratch.GetItemListInTrack("video", 1) or []
        if not items:
            def walk(folder):
                for clip in folder.GetClipList():
                    yield clip
                for sub in folder.GetSubFolderList():
                    yield from walk(sub)
            still = next(clip for clip in walk(pool.GetRootFolder())
                         if rc.is_still_image(clip.GetName(), clip.GetClipProperty("Type")))
            rc.append_clip(pool, still, {"mediaPoolItem": still, "trackIndex": 1, "mediaType": 1}, 0, 120, still=True)
            items = scratch.GetItemListInTrack("video", 1)
        item = items[0]
        comp = item.GetFusionCompByIndex(1) if item.GetFusionCompCount() else item.AddFusionComp()
        numbers = sf.run_lua(comp, SETUP, key="DSLive", wait=8.0)
        start, end, rate, width, height, gstart, gend = (float(v) for v in str(numbers).split())
        c = dict(start=start, end=end, rate=rate, width=width, height=height, gstart=gstart, gend=gend)
        print(f"the comp: frames {start:g}-{end:g}, {rate:g} fps, {width:g} x {height:g}")
        # every piece of the cheat sheet and of Everything has its case - one without fails
        runs = []
        for where, source, table in (("sheet", fx.CHEAT_SHEET, cases(c)), ("everything", fx.EVERYTHING, everything(c))):
            pieces = [code for _g, rows in source for code, _a, _s in rows]
            flat = [piece for code in pieces for piece in (code if isinstance(code, tuple) else (code,))]
            for piece in flat:
                if piece not in table:
                    failed.append((f"{where}: {piece}", "no case to try it with"))
            runs += [(f"{where}: {piece}", case) for piece in flat if piece in table for case in table[piece]]
        lua_cases = "local CASES = {" + ", ".join(
            "{" + lua_string(expr) + ', "' + kind + '", ' + str(frame) + "}" for _p, (expr, kind, frame, _w) in runs) + "}\n"
        answer = sf.run_lua(comp, lua_cases + TRY, key="DSLive", wait=30.0)
        got = str(answer).split("\n") if answer is not None else []
        before = {}
        for (piece, (expr, kind, frame, want)), value in zip(runs, got):
            total += 1
            if kind == "n":
                try:
                    value = float(value)
                except ValueError:
                    pass
            elif kind == "p" and value.startswith("P "):
                value = tuple(float(v) for v in value.split()[1:])
            if want == "same as before":
                good = value == before.get(expr)
            elif callable(want):
                good = want(value)
            elif isinstance(want, tuple):
                good = isinstance(value, tuple) and all(abs(a - b) < 1e-3 for a, b in zip(value, want))
            else:
                good = value == want
            before[expr] = value
            print(("ok   " if good else "FAIL ") + f"{piece:50.50}  {expr}  ->  {value}")
            if not good:
                failed.append((piece, f"{expr} gave {value!r}"))
        if len(got) < len(runs):
            failed.append(("(all)", f"Fusion answered {len(got)} of {len(runs)}"))
    finally:
        project.SetCurrentTimeline(home)
        if r.GetCurrentPage() != page:
            r.OpenPage(page)
    print(f"\n{total} tried, {len(failed)} wrong" + ("" if not failed else ":"))
    for piece, why in failed:
        print(f"   {piece}: {why}")
    print(f'(the scratch timeline "{NAME}" is left in place - delete it when you like)')
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
