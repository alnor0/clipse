"""A sound's tags, kept inside the file (2026-11-01, "allow me to set the energy while i listen. And allow tagging as
well"): the fields sound-library tools read as keywords, so they survive copies and backups, and the same file can be
tagged by other tools.

    WAV   RIFF LIST/INFO "IKEY"
    MP3   ID3v2 TXXX "Keywords"
    FLAC  Vorbis comment KEYWORDS
    MOV   QuickTime metadata com.apple.quicktime.keywords

Resolve doesn't read these fields (its Keywords stay empty, 21.1.1), so Clipse reads them itself. Energy is a tag too:
e1, e2 or e3, one to a file.

Only the tags change, and a tag never touches the sound: the new file is written beside the old one, everything else
compared byte for byte, the tags read back, and only then swapped in under the same name (Resolve finds media by path),
with its old modified time (waveform thumbnails and caches go by it). A .mov's sound can be many GB and its index sits
at the end, so the sound isn't rewritten at all: the new index is added after the old one, checked, and 4 bytes switch
the old one off. The file is valid at every step, and grows by the size of its index. A file that looks unusual in any
way is left alone, with a ValueError saying so.

Written by hand, so tagging needs nothing installed."""
import hashlib
import os
import re
import shutil
import struct
import threading

from . import paths

CACHE_FILE = paths.cache("file_tags.json")
MAX_ENTRIES = 20000
EXTS = (".wav", ".mp3", ".flac", ".mov")
ENERGY = re.compile(r"e[1-3]", re.I)
_CHUNK = 1 << 20


def can_tag(path):
    return bool(path) and os.path.splitext(path)[1].lower() in EXTS


def split_tags(text):
    out = []
    for tag in re.split(r"[;,\x00]", text or ""):
        tag = tag.strip()
        if tag and tag not in out:
            out.append(tag)
    return out


def energy_of(tags):
    """1-3 from a file's tags, 0 for none."""
    return next((int(tag[1]) for tag in tags or () if ENERGY.fullmatch(tag)), 0)


def with_energy(tags, level):
    """The tags with this energy in place of any other (a file has one). 0 takes it away."""
    kept = [tag for tag in tags if not ENERGY.fullmatch(tag)]
    return kept + [f"e{level}"] if level else kept


# -- WAV ---------------------------------------------------------------------
def _wav_chunks(f, size, strict=False):
    """(id, where its contents start, their size) of each chunk. strict: a file whose sizes don't add up is refused
    (never rewritten) instead of read around."""
    f.seek(0)
    head = f.read(12)
    if len(head) < 12 or head[:4] != b"RIFF" or head[8:12] != b"WAVE":
        raise ValueError("not a WAV file Clipse can tag")
    pos = 12
    while pos + 8 <= size:
        f.seek(pos)
        cid, csize = struct.unpack("<4sI", f.read(8))
        start = pos + 8
        if start + csize > size:
            if strict:
                raise ValueError("this WAV looks damaged or unusual, so it was left alone")
            csize = size - start
        yield cid, start, csize
        pos = start + csize + (csize & 1)
    if strict and size - pos > 1:
        raise ValueError("this WAV looks damaged or unusual, so it was left alone")


def _is_info(f, start, csize):
    f.seek(start)
    return csize >= 4 and f.read(4) == b"INFO"


def _info_items(data):
    items, pos = [], 0
    while pos + 8 <= len(data):
        sid, ssz = struct.unpack("<4sI", data[pos:pos + 8])
        items.append((sid, data[pos + 8:pos + 8 + ssz]))
        pos += 8 + ssz + (ssz & 1)
    return items


def _wav_read(path):
    size = os.path.getsize(path)
    with open(path, "rb") as f:
        for cid, start, csize in _wav_chunks(f, size):
            if cid == b"LIST" and _is_info(f, start, csize):
                f.seek(start + 4)
                for sid, value in _info_items(f.read(csize - 4)):
                    if sid == b"IKEY":
                        return split_tags(value.decode("utf-8", "replace"))
                return []
    return []


def _copy(src, dst, start, count):
    src.seek(start)
    while count > 0:
        block = src.read(min(_CHUNK, count))
        if not block:
            raise ValueError("the file ended early, so it was left alone")
        dst.write(block)
        count -= len(block)


def _wav_write(path, tmp, tags):
    size = os.path.getsize(path)
    with open(path, "rb") as f, open(tmp, "wb") as out:
        out.write(b"RIFF\0\0\0\0WAVE")

        def write_info(items):
            if items:
                body = b"INFO" + b"".join(struct.pack("<4sI", sid, len(value)) + value + (b"\0" if len(value) & 1 else b"")
                                          for sid, value in items)
                out.write(struct.pack("<4sI", b"LIST", len(body)) + body)

        def new_items(old):
            items = [(sid, value) for sid, value in old if sid != b"IKEY"]
            return items + [(b"IKEY", "; ".join(tags).encode("utf-8") + b"\0")] if tags else items

        done = False
        for cid, start, csize in _wav_chunks(f, size, strict=True):
            if cid == b"LIST" and not done and _is_info(f, start, csize):
                f.seek(start + 4)
                write_info(new_items(_info_items(f.read(csize - 4))))
                done = True
                continue
            out.write(struct.pack("<4sI", cid, csize))
            _copy(f, out, start, csize)
            if csize & 1:
                out.write(b"\0")
        if not done:
            write_info(new_items([]))
        total = out.tell()
        if total > 0xFFFFFFFF:
            raise ValueError("this WAV is too long to tag")
        out.seek(4)
        out.write(struct.pack("<I", total - 8))


def _wav_print(path):
    size = os.path.getsize(path)
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        info = True
        for cid, start, csize in _wav_chunks(f, size):
            if cid == b"LIST" and info and _is_info(f, start, csize):
                info = False
                continue
            digest.update(cid)
            _hash(f, digest, start, csize)
    return digest.digest()


def _hash(f, digest, start, count):
    f.seek(start)
    while count > 0:
        block = f.read(min(_CHUNK, count))
        if not block:
            break
        digest.update(block)
        count -= len(block)


# -- MP3 (ID3v2.3 / 2.4) -----------------------------------------------------
def _synchsafe(raw):
    return (raw[0] & 0x7F) << 21 | (raw[1] & 0x7F) << 14 | (raw[2] & 0x7F) << 7 | (raw[3] & 0x7F)


def _to_synchsafe(n):
    return bytes(((n >> 21) & 0x7F, (n >> 14) & 0x7F, (n >> 7) & 0x7F, n & 0x7F))


def _id3_size(f):
    """(whole tag's size including its header, major version, flags) - (0, 0, 0) with no tag."""
    f.seek(0)
    head = f.read(10)
    if len(head) < 10 or head[:3] != b"ID3" or any(b & 0x80 for b in head[6:10]):
        return 0, 0, 0
    return 10 + _synchsafe(head[6:10]), head[3], head[5]


def _id3_frames(body, major):
    """[(id, flags, contents)] of a tag's frames, or None when they can't be walked to the end."""
    for synchsafe in ((True, False) if major == 4 else (False,)):  # (some programs write 2.4 with plain sizes)
        frames, pos = [], 0
        while pos + 10 <= len(body) and body[pos] != 0:
            fid = body[pos:pos + 4]
            if not re.fullmatch(rb"[A-Z0-9]{4}", fid):
                frames = None
                break
            size = _synchsafe(body[pos + 4:pos + 8]) if synchsafe else struct.unpack(">I", body[pos + 4:pos + 8])[0]
            if pos + 10 + size > len(body):
                frames = None
                break
            frames.append((fid, body[pos + 8:pos + 10], body[pos + 10:pos + 10 + size]))
            pos += 10 + size
        if frames is not None:
            return frames
    return None


def _id3_body(f, major, flags, total):
    f.seek(10)
    body = f.read(total - 10)
    if flags & 0x40 and len(body) >= 4:  # an extended header (nothing in it is kept)
        size = _synchsafe(body[:4]) if major == 4 else struct.unpack(">I", body[:4])[0] + 4
        body = body[size:]
    return body


_ENCODINGS = {0: "latin-1", 1: "utf-16", 2: "utf-16-be", 3: "utf-8"}


def _txxx_parts(contents):
    """(description, value) of a TXXX frame's contents."""
    if not contents or contents[0] not in _ENCODINGS:
        return "", ""
    encoding = _ENCODINGS[contents[0]]
    text = contents[1:].decode(encoding, "replace")
    description, _, value = text.partition("\x00")
    return description.lstrip("﻿"), value.replace("﻿", "")


def _mp3_read(path):
    with open(path, "rb") as f:
        total, major, flags = _id3_size(f)
        if not total or major not in (3, 4):
            return []
        body = _id3_body(f, major, flags, total)
    if flags & 0x80 and major == 3:
        body = body.replace(b"\xff\x00", b"\xff")
    tags = []
    for fid, _flags, contents in _id3_frames(body, major) or ():
        if fid == b"TXXX":
            description, value = _txxx_parts(contents)
            if description.lower() == "keywords":
                tags += split_tags(value)
    return list(dict.fromkeys(tags))


def _mp3_write(path, tmp, tags):
    size = os.path.getsize(path)
    with open(path, "rb") as f, open(tmp, "wb") as out:
        total, major, flags = _id3_size(f)
        if total and (major not in (3, 4) or flags & 0x80 or flags & 0x10):
            raise ValueError("this MP3's tag is an unusual kind, so it was left alone")
        major = major or 4
        frames = _id3_frames(_id3_body(f, major, flags, total), major) if total else []
        if frames is None:
            raise ValueError("this MP3's tag looks damaged, so it was left alone")
        kept = [frame for frame in frames if not (frame[0] == b"TXXX" and _txxx_parts(frame[2])[0].lower() == "keywords")]
        if tags:
            text = "; ".join(tags)
            # (2.3 knows no UTF-8: UTF-16 with its mark, as every program reads)
            contents = (b"\x03Keywords\x00" + text.encode("utf-8") if major == 4
                        else b"\x01" + "Keywords\x00".encode("utf-16") + text.encode("utf-16"))
            kept.append((b"TXXX", b"\0\0", contents))
        body = b""
        for fid, frame_flags, contents in kept:
            length = _to_synchsafe(len(contents)) if major == 4 else struct.pack(">I", len(contents))
            body += fid + length + frame_flags + contents
        room = max(0, total - 10 - len(body)) or 1024  # (the padding it had, or some for next time)
        out.write(b"ID3" + bytes((major, 0, 0)) + _to_synchsafe(len(body) + room) + body + b"\0" * room)
        _copy(f, out, total, size - total)


def _mp3_print(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        total = _id3_size(f)[0]
        _hash(f, digest, total, os.path.getsize(path) - total)
    return digest.digest()


# -- FLAC --------------------------------------------------------------------
def _flac_blocks(f):
    """[(type, its contents)] and where the sound starts."""
    f.seek(0)
    if f.read(4) != b"fLaC":
        raise ValueError("not a FLAC file Clipse can tag")
    blocks = []
    while True:
        head = f.read(4)
        if len(head) < 4:
            raise ValueError("this FLAC looks damaged, so it was left alone")
        contents = f.read(int.from_bytes(head[1:4], "big"))
        blocks.append((head[0] & 0x7F, contents))
        if head[0] & 0x80:
            return blocks, f.tell()


def _vorbis_parts(block):
    vendor_size = struct.unpack("<I", block[:4])[0]
    vendor = block[4:4 + vendor_size]
    pos = 4 + vendor_size
    count = struct.unpack("<I", block[pos:pos + 4])[0]
    pos += 4
    comments = []
    for _ in range(count):
        size = struct.unpack("<I", block[pos:pos + 4])[0]
        comments.append(block[pos + 4:pos + 4 + size])
        pos += 4 + size
    return vendor, comments


def _flac_read(path):
    with open(path, "rb") as f:
        blocks, _start = _flac_blocks(f)
    tags = []
    for kind, contents in blocks:
        if kind == 4:
            for comment in _vorbis_parts(contents)[1]:
                key, _, value = comment.partition(b"=")
                if key.upper() == b"KEYWORDS":
                    tags += split_tags(value.decode("utf-8", "replace"))
    return list(dict.fromkeys(tags))


def _flac_write(path, tmp, tags):
    size = os.path.getsize(path)
    with open(path, "rb") as f, open(tmp, "wb") as out:
        blocks, start = _flac_blocks(f)
        if not blocks or blocks[0][0] != 0:
            raise ValueError("this FLAC looks damaged, so it was left alone")
        vendor, comments = b"Clipse", []
        for kind, contents in blocks:
            if kind == 4:
                vendor, comments = _vorbis_parts(contents)
                break
        comments = [c for c in comments if c.partition(b"=")[0].upper() != b"KEYWORDS"]
        if tags:
            comments.append(b"KEYWORDS=" + "; ".join(tags).encode("utf-8"))
        vorbis = struct.pack("<I", len(vendor)) + vendor + struct.pack("<I", len(comments)) \
            + b"".join(struct.pack("<I", len(c)) + c for c in comments)
        kept = [b for b in blocks if b[0] != 4]
        kept.insert(1, (4, vorbis))
        out.write(b"fLaC")
        for i, (kind, contents) in enumerate(kept):
            if len(contents) >= 1 << 24:
                raise ValueError("this FLAC's tags are too long")
            out.write(bytes((kind | (0x80 if i == len(kept) - 1 else 0),)) + len(contents).to_bytes(3, "big") + contents)
        _copy(f, out, start, size - start)


def _flac_print(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        blocks, start = _flac_blocks(f)
        digest.update(blocks[0][1])  # (STREAMINFO: what the sound is)
        _hash(f, digest, start, os.path.getsize(path) - start)
    return digest.digest()


# -- MOV ---------------------------------------------------------------------
_MOV_KEY = b"com.apple.quicktime.keywords"


def _mov_boxes(f, start, end):
    pos = start
    while pos + 8 <= end:
        f.seek(pos)
        size, kind = struct.unpack(">I4s", f.read(8))
        if size == 1:
            size = struct.unpack(">Q", f.read(8))[0]
        elif size == 0:
            size = end - pos
        if size < 8 or pos + size > end:
            raise ValueError("this file looks damaged or unusual, so it was left alone")
        yield kind, pos, size
        pos += size


def _mov_index(f, size):
    boxes = list(_mov_boxes(f, 0, size))
    moovs = [b for b in boxes if b[0] == b"moov"]
    if len(moovs) != 1 or boxes[-1][0] != b"moov":
        raise ValueError("this .mov has its index in the middle, so it was left alone")
    return moovs[0][1], moovs[0][2]


def _mov_children(f, offset, size):
    out = []
    for kind, pos, whole in _mov_boxes(f, offset + 8, offset + size):
        f.seek(pos)
        out.append((kind, f.read(whole)))
    return out


def _mov_meta(tags):
    def box(kind, payload):
        return struct.pack(">I4s", len(payload) + 8, kind) + payload
    hdlr = box(b"hdlr", b"\0" * 8 + b"mdta" + b"\0" * 13)
    keys = box(b"keys", struct.pack(">II", 0, 1) + box(b"mdta", _MOV_KEY))
    data = box(b"data", struct.pack(">II", 1, 0) + "; ".join(tags).encode("utf-8"))
    item = struct.pack(">I", len(data) + 8) + struct.pack(">I", 1) + data
    return box(b"meta", hdlr + keys + box(b"ilst", item))


def _mov_keywords(blob):
    body = blob[8:]
    if body[4:8] != b"hdlr":  # (the ISO form has 4 more bytes up front)
        body = body[4:]
    items, pos = {}, 0
    while pos + 8 <= len(body):
        size, kind = struct.unpack(">I4s", body[pos:pos + 8])
        if size < 8:
            break
        items[kind] = body[pos + 8:pos + size]
        pos += size
    keys, pos, raw = [], 8, items.get(b"keys", b"")
    while pos + 8 <= len(raw):
        size = struct.unpack(">I", raw[pos:pos + 4])[0]
        if size < 8:
            break
        keys.append(raw[pos + 8:pos + size])
        pos += size
    if _MOV_KEY not in keys:
        return []
    want, ilst, pos = keys.index(_MOV_KEY) + 1, items.get(b"ilst", b""), 0
    while pos + 8 <= len(ilst):
        size, index = struct.unpack(">II", ilst[pos:pos + 8])
        if size < 8:
            break
        if index == want:
            return split_tags(ilst[pos + 8 + 16:pos + size].decode("utf-8", "replace"))
        pos += size
    return []


def _mov_read(path):
    with open(path, "rb") as f:
        offset, size = _mov_index(f, os.path.getsize(path))
        for kind, blob in _mov_children(f, offset, size):
            if kind == b"meta":
                return _mov_keywords(blob)
    return []


def _mov_write(path, tags):
    st = os.stat(path)
    with open(path, "r+b") as f:
        offset, size = _mov_index(f, st.st_size)
        old = _mov_children(f, offset, size)
        if not any(kind == b"trak" for kind, _blob in old):
            raise ValueError("this .mov has no tracks, so it was left alone")
        kept = [child for child in old if child[0] != b"meta"]
        parts = b"".join(blob for _kind, blob in kept) + (_mov_meta(tags) if tags else b"")
        new = struct.pack(">I4s", len(parts) + 8, b"moov") + parts
        # the new index goes after the old one, which stays the live one until the new one is checked
        f.seek(st.st_size)
        f.write(new)
        f.flush()
        os.fsync(f.fileno())
        check = _mov_children(f, st.st_size, len(new))
        if [c for c in check if c[0] != b"meta"] != kept \
                or ([_mov_keywords(blob) for kind, blob in check if kind == b"meta"] or [[]])[0] != tags:
            f.truncate(st.st_size)
            raise ValueError("the tags didn't read back, so the file was left as it was")
        f.seek(offset + 4)  # 4 bytes switch the old index off: the file is valid before and after
        f.write(b"free")
        f.flush()
        os.fsync(f.fileno())
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns))


_READ = {".wav": _wav_read, ".mp3": _mp3_read, ".flac": _flac_read, ".mov": _mov_read}
_WRITE = {".wav": _wav_write, ".mp3": _mp3_write, ".flac": _flac_write}
_PRINT = {".wav": _wav_print, ".mp3": _mp3_print, ".flac": _flac_print}


def read(path):
    """The file's tags, read now. [] when it has none, or can't be read."""
    extension = os.path.splitext(path or "")[1].lower()
    if extension not in _READ:
        return []
    try:
        return _READ[extension](path)
    except (OSError, ValueError, struct.error, IndexError):
        return []


def write(path, tags):
    """Puts these tags in the file. A link is followed: the real file is what changes. Raises OSError or ValueError,
    the file as it was."""
    real = os.path.realpath(path)
    extension = os.path.splitext(real)[1].lower()
    if extension not in _READ:
        raise ValueError(f"Clipse can't tag {extension or 'this kind of'} files")
    tags = list(dict.fromkeys(tag.strip() for tag in tags if tag.strip()))
    if _READ[extension](real) == tags:
        return
    if extension == ".mov":
        _mov_write(real, tags)
    else:
        folder, base = os.path.split(real)
        tmp = os.path.join(folder, f".{base}.clipse.tmp")
        try:
            _WRITE[extension](real, tmp, tags)
            if _PRINT[extension](tmp) != _PRINT[extension](real):
                raise ValueError("the sound would have changed, so the file was left alone")
            if _READ[extension](tmp) != tags:
                raise ValueError("the tags didn't read back, so the file was left alone")
            st = os.stat(real)
            shutil.copymode(real, tmp)
            if hasattr(os, "listxattr"):
                for name in os.listxattr(real):
                    os.setxattr(tmp, name, os.getxattr(real, name))
            os.replace(tmp, real)
            os.utime(real, ns=(st.st_atime_ns, st.st_mtime_ns))
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)
    with _lock:
        _known()[path] = [_stamp(path), tags]
        _state["dirty"] = True


# -- what's known already, so opening the picker reads nothing --------------
_lock = threading.Lock()
_state = {"known": None, "dirty": False}


def _known():
    if _state["known"] is None:
        loaded = paths.read_json(CACHE_FILE, {})
        _state["known"] = loaded if isinstance(loaded, dict) else {}
    return _state["known"]


def _stamp(path):
    """What changes when the tags do. A tag keeps the file's modified time, and e1 -> e2 its size: the change time and
    the file number are what tell. (A file tagged by another tool too.)"""
    try:
        st = os.stat(path)
    except OSError:
        return None
    return f"{st.st_ino}|{st.st_size}|{st.st_mtime_ns}|{st.st_ctime_ns}"


def known(path):
    """The tags last seen for this file - nothing read from the disk. [] when there's none."""
    with _lock:
        hit = _known().get(path)
    return list(hit[1]) if hit else []


def fresh(path):
    """The file's tags, read only when it has changed since they were last seen. For the background."""
    stamp = _stamp(path)
    if stamp is None:
        return known(path)
    with _lock:
        hit = _known().get(path)
    if hit and hit[0] == stamp:
        return list(hit[1])
    tags = read(path)
    with _lock:
        _known()[path] = [stamp, tags]
        _state["dirty"] = True
    return tags


def save():
    """What's known, kept for the next start - when anything changed."""
    with _lock:
        if not _state["dirty"]:
            return
        known_now = _known()
        while len(known_now) > MAX_ENTRIES:
            del known_now[next(iter(known_now))]
        _state["dirty"] = False
        snapshot = dict(known_now)
    try:
        paths.write_json(CACHE_FILE, snapshot)
    except OSError as e:
        print(f"[tags] couldn't keep what's known: {e}")


# -- after tagging ---------------------------------------------------------
def after_tagging(changed):
    """A program of your own, run after tags change: the file `after_tagging` in the settings folder, given the files
    changed (like git's hooks - for a tool that goes by the same tags). No such file, nothing happens. Not in Settings,
    and not in a saved setup: a file from someone else can't start anything."""
    import subprocess
    hook = paths.config("after_tagging")
    if not changed or os.name == "nt" or not os.access(hook, os.X_OK):
        return
    try:
        subprocess.Popen([hook, *changed], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError as e:
        print(f"[tags] after_tagging didn't start: {e}")
