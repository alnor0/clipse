"""Stays fast with a big project: 5000 clips, typing and opening measured
against a budget (16 ms is one frame - under that feels instant).
python3 tests/test_speed.py"""
import os
import statistics
import time

os.environ["FAKE_CLIPS"] = "5000"
import _setup  # noqa: E402
from clipse import fuzzy  # noqa: E402

w, s, F = _setup.picker()
while w._scan is not None:  # the first read of the Media Pool
    _setup.pump(0.1)
_setup.pump(0.3)
fails = 0


def check(what, ok):
    global fails
    print(("ok   " if ok else "FAIL ") + what)
    fails += not ok


def ms(fn, times=9):
    took = []
    for _ in range(times):
        start = time.perf_counter()
        fn()
        took.append(1000 * (time.perf_counter() - start))
    return statistics.median(took)


check(f"the fake project is big ({len(w.model.clip_rows)} rows)", len(w.model.clip_rows) >= 5000)

# -- the quick "can't match" check never changes an answer --
names = [r.name for r in w.model.clip_rows[::37]] + ["whoosh_dark_02.wav", "Transition Glitch.mov", "Lyd_ø Ä.wav",
                                                      "B-roll", "photo", "", "a", "SFX_034.wav"]
queries = ["b", "br", "bro", "b-roll 0", "roll b", "woosh", "whsooh", "transtion", "dark whoosh", "wsh", "o a",
           "photo 1", "sfx 34", "zzzz", "0", "mp4", "b roll 4999", "glich", "é", "upbeat corp"]
same = all(fuzzy.scorer(q)(n) == fuzzy.smart_score(q, n) for q in queries for n in names)
check(f"searching finds exactly what it found before ({len(queries) * len(names)} pairs)", same)

# -- typing: one letter at a time, words not typed before --
words = iter(f"b-roll {n}" for n in range(4000, 4999, 7))


def type_a_word():
    word = next(words)
    took = []
    for end in range(1, len(word) + 1):
        start = time.perf_counter()
        w.search_edit.setText(word[:end])
        _setup.app.processEvents()
        took.append(1000 * (time.perf_counter() - start))
    return took


keys = [t for _ in range(6) for t in type_a_word()]
typical, slowest = statistics.median(keys), max(keys)
print(f"     a key: typically {typical:.1f} ms, slowest {slowest:.1f} ms")
check("a key press is searched, sorted and on screen within a frame (16 ms)", typical < 16)
check("...and even the slowest one in well under a tenth of a second", slowest < 60)


def nothing():
    w.search_edit.setText("zzzzqq")
    _setup.app.processEvents()
    w.search_edit.setText("zzzzq")
    _setup.app.processEvents()


t = ms(nothing) / 2
print(f"     a key that finds nothing: {t:.1f} ms")
check("a key that finds nothing is quicker still", t < 10)

# -- opening again --
w.search_edit.setText("")


def reopen():
    w.hide()
    _setup.app.processEvents()
    w.open_picker()
    _setup.app.processEvents()


t = ms(reopen)
print(f"     closing and opening: {t:.1f} ms")
check("the picker opens again within a frame (nothing is read or built twice)", t < 16)


def arrow():
    row = min(w.list_view.currentIndex().row() + 1, w.model.rowCount() - 1)
    w.list_view.setCurrentIndex(w.model.index(row, 0))
    _setup.app.processEvents()


t = ms(arrow, 30)
print(f"     arrow down: {t:.1f} ms")
check("moving through the list is immediate", t < 5)

print("\nall good" if not fails else f"\n{fails} FAILED")
raise SystemExit(1 if fails else 0)
