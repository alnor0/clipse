"""Project check-up: what's wrong in the Media Pool, found from what the
picker already knows about each clip (no extra calls to Resolve).

  missing    the clip's file isn't on disk any more
  duplicate  the same clip is in more than one bin, or two clips are
             copies of the same file
  clipping   the sound is louder than a file can hold, so its tops are
             cut flat (analysed sounds; the same test as the preview's
             dashed red lines - loud alone doesn't count)

Each returns [(clip row index, what's wrong - shown next to the name)].
"""
import hashlib
import os
import re
from collections import defaultdict

_SEQUENCE = re.compile(r"\[\d+-\d+\]|%0?\d*d")  # an image sequence: one "file" standing for many


def _on_disk(path):
    if _SEQUENCE.search(os.path.basename(path)):
        return os.path.isdir(os.path.dirname(path))
    return os.path.exists(path)


def missing(rows):
    out = []
    for i, row in enumerate(rows):
        path = getattr(row, "source", "")
        if path and row.category not in ("bin", "selected") and not _on_disk(path):
            out.append((i, f"not found: {path}"))
    return out


def _fingerprint(path):
    """Size plus the first and last 64 KB - enough to tell copies of a file
    from files that just happen to be the same size, without reading it all."""
    size = os.path.getsize(path)
    digest = hashlib.blake2b(digest_size=12)
    with open(path, "rb") as f:
        digest.update(f.read(65536))
        if size > 131072:
            f.seek(-65536, os.SEEK_END)
            digest.update(f.read(65536))
    return size, digest.hexdigest()


def duplicates(rows, groups):
    """groups: the picker's (name, [(media id, bin, type) ...], category)
    per row - a row with several entries is one clip in several bins."""
    why = {}
    for i, (_name, instances, category) in enumerate(groups):
        if i < len(rows) and category not in ("bin", "selected") and len(instances) > 1:
            bins = sorted({str(folder) for _id, folder, _type in instances})
            why[i] = (f"{len(instances)} times, in {', '.join(bins)}" if len(bins) > 1
                      else f"{len(instances)} times in {bins[0]}")
    by_size = defaultdict(list)
    for i, row in enumerate(rows):
        path = getattr(row, "source", "")
        if not path or row.category in ("bin", "selected") or _SEQUENCE.search(os.path.basename(path)):
            continue
        try:
            by_size[os.path.getsize(path)].append(i)
        except OSError:
            pass
    for size, same_size in by_size.items():
        if len(same_size) < 2 or size == 0:
            continue
        by_content = defaultdict(list)
        for i in same_size:
            try:
                by_content[_fingerprint(rows[i].source)].append(i)
            except OSError:
                pass
        for twins in by_content.values():
            for i in twins:
                others = [rows[j].name for j in twins if j != i]
                if others and i not in why:
                    same_file = all(rows[j].source == rows[i].source for j in twins)
                    why[i] = ("the same file as " if same_file else "a copy of ") + ", ".join(others[:3])
    return sorted(why.items(), key=lambda pair: rows[pair[0]].name.lower())


def clipping(rows):
    out = []
    for i, row in enumerate(rows):
        flat = (getattr(row, "analysis", None) or {}).get("clips") if row.category == "audio" else None
        if isinstance(flat, int) and flat >= 2:  # one pair of samples at the top can be chance
            out.append((i, "clips in one spot" if flat < 20 else "clips a lot" if flat > 2000 else "clips in places"))
    return out
