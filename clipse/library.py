"""Title (Text+) and Solid colour at the playhead on a free track (Basics, title:).

Resolve's own way to add one (InsertFusionTitleIntoTimeline, InsertGeneratorIntoTimeline) always cuts it into V1 at
the playhead and pushes everything after it along (21.1.1, 2026-10-20). From the Media Pool it lands on any track -
and a Media Pool clip of either can be made from its name alone: a small bin file (.drb) is written with the clip in
it, Resolve builds the title from its template when it's brought in. The clip is kept in the clipse bin and used again.

The clip's <FieldsBlob> is 4 bytes (2), 4 bytes the length of the rest, 0x80 (the rest not compressed - 0x81: a
zstd frame), then a protobuf: {2: name, 6: 4}, its kind ("Fusion Title", a plain generator its name), {1: frame
rate}, 5: 240, and for a title 6: name, 7: template ("Text+", "Templates/Edit/Titles/Candy").

A plain generator's name Resolve doesn't know CRASHES Resolve when it's placed: only Solid Color is ever made."""
import os
import re
import uuid
import zipfile

from . import stills
from . import paths

TEXT_PLUS = ("title", "Text+", "Text+")
SOLID = ("generator", "Solid Color", "")
_BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "adjustment_clip.drb")  # (its project.xml)


def title(name):
    """Text+, or a title of your own saved in Fusion's Templates/Edit/Titles (Settings > Timeline > Title to add)."""
    return TEXT_PLUS if not name or name == "Text+" else ("title", name, f"Templates/Edit/Titles/{name}")


def clip_name(entry):
    """Its name in the Media Pool, like_this: text_plus, solid_color."""
    return stills.like_this(entry[1].replace("+", " plus")) or "title"


def _pb(field, text):
    raw = text.encode()
    return bytes([field << 3 | 2, len(raw)]) + raw


def _blob(entry):
    kind, name, template = entry
    inner = _pb(2, name) + b"\x30\x04"
    msg = b"\x0a" + bytes([len(inner)]) + inner
    msg += _pb(2, "Fusion Title" if kind == "title" else name)
    msg += bytes.fromhex("1a09090000000000004e40") + b"\x28\xf0\x01"
    if kind == "title":
        msg += _pb(6, name) + _pb(7, template)
    raw = b"\x80" + msg
    return (b"\x00\x00\x00\x02" + len(raw).to_bytes(4, "big") + raw).hex()


def write_bin(path, entry, bin_name="clipse_import"):
    """The bin file with the one clip in it."""
    if entry[0] != "title" and entry != SOLID:
        raise ValueError(f"not a generator Clipse makes: {entry[1]}")  # (an unknown one crashes Resolve)
    with zipfile.ZipFile(_BASE) as z:
        project = z.read("project.xml").decode()
        master = z.read("MediaPool/Master/MpFolder.xml").decode()
    master_id = re.search(r'<Sm2MpFolder DbId="([^"]+)"', master).group(1)
    pool_id = re.search(r"<MediaPool>([^<]+)</MediaPool>", master).group(1)
    folder = str(uuid.uuid4())
    shown = "Fusion Title" if entry[0] == "title" else entry[1]
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<!--DbAppVer="21.1.1.0010" DbPrjVer="17"-->
<Sm2MpFolder DbId="{folder}">
 <FieldsBlob/>
 <Name>{bin_name}</Name>
 <MpFolder>{master_id}</MpFolder>
 <UniqueMediaPoolItemId>{uuid.uuid4()}</UniqueMediaPoolItemId>
 <MediaVec>
  <Element>
   <Sm2MpGenerator DbId="{uuid.uuid4()}">
    <FieldsBlob>{_blob(entry)}</FieldsBlob>
    <Name>{shown}</Name>
    <MpFolder>{folder}</MpFolder>
    <UniqueMediaPoolItemId>{uuid.uuid4()}</UniqueMediaPoolItemId>
    <MarkIn/>
    <MarkInVideo/>
    <MarkInAudio/>
    <MarkOut/>
    <MarkOutVideo/>
    <MarkOutAudio/>
    <CurPlayheadPosition/>
   </Sm2MpGenerator>
  </Element>
 </MediaVec>
 <MediaPool>{pool_id}</MediaPool>
 <Folded>true</Folded>
 <ColorTag>FOLDER_COLOR_NONE</ColorTag>
 <LockSysId/>
 <DbSavedTime>0</DbSavedTime>
</Sm2MpFolder>
"""
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as out:
        out.writestr("project.xml", project)
        out.writestr("MediaPool/Master/MpFolder.xml", master)
        out.writestr(f"MediaPool/Master/000_{bin_name}/MpFolder.xml", xml)


def _find(folder, name, depth=0):
    for clip in folder.GetClipList() or []:
        if clip.GetName() == name:
            return clip
    for sub in (folder.GetSubFolderList() or []) if depth < 3 else []:
        found = _find(sub, name, depth + 1)
        if found is not None:
            return found
    return None


def clip_for(media_pool, entry):
    """(the Media Pool clip for Text+ / Solid colour, None) - the one in the clipse bin, else made from its name and
    brought in - or (None, why)."""
    from . import timeline_tools as tt
    name = clip_name(entry)
    home = stills._named(media_pool.GetRootFolder(), stills.CLIPSE_BIN)
    clip = _find(home, name) if home is not None else None
    if clip is not None:
        return clip, None
    path = paths.cache("library.drb")
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        write_bin(path, entry)
    except (OSError, ValueError) as e:
        return None, f"Couldn't make {entry[1]}: {e}"
    clip = tt._bring_clip(media_pool, path, lambda c: True, entry[1], name)
    if clip is None:
        return None, f"Resolve wouldn't take {entry[1]}."
    return clip, None


def set_words(item, words):
    """What's typed, into the title's first Text+."""
    try:
        comp = item.GetFusionCompByIndex(1)
        tool = next(iter((comp.GetToolList(False, "TextPlus") or {}).values()), None) if comp else None
        if tool is None:
            return False
        tool.SetInput("StyledText", words)
        return True
    except Exception:
        return False
