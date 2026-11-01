"""Organise project (organise.py) against the fake Resolve: which template it goes by, where loose clips go, the
colours - and what it leaves alone. python3 tests/test_organise.py"""
import os

import _setup  # noqa: F401  (the throwaway HOME and the fake Resolve)
import DaVinciResolveScript as F
from clipse import organise, paths, project_templates as pt

fails = 0


def check(what, ok):
    global fails
    print(("ok   " if ok else "FAIL ") + what)
    fails += not ok


def log():
    return open(F.LOG).read() if os.path.exists(F.LOG) else ""


def bin_of(name):
    for path, folder in organise._project_bins(F.ROOT).items():
        if any(c.GetName() == name for c in folder.GetClipList()):
            return path
    return "(Master)" if any(c.GetName() == name for c in F.ROOT.GetClipList()) else None


resolve = F.scriptapp("Resolve")

# -- no template's bins in the project: it says so, and does nothing --
worked, said = organise.organise(resolve)
check("no template's bins: it asks for a template first", not worked and "tpl:" in said)

# -- a template of your own: bins, and a folder of yours that goes in overlays --
overlays_folder = "/home/me/library/vfx/generated"
paths.write_json(pt._file("mine"), {"name": "mine", "bins": [
    ["01_a-roll", []], ["02_b-roll", [["screen", []], ["footage", []]]], ["03_graphics", [["images", []], ["overlays", []]]],
    ["04_audio", [["music", []], ["sfx", []]]], ["05_fusion", []], ["06_timelines", []]],
    "organise": {"places": {"folders": {overlays_folder: "03_graphics/overlays"}}}})
F.ROOT.subs.append(F.Folder("02_b-roll", [F.MPI("broll take.mp4", "bt1", "Video")]))
F.ROOT.c += [F.MPI("Fusion Composition", "fc1", "Fusion Composition"), F.MPI("stopwatch.mov", "sw1", "Video"),
             F.MPI("hand picked.png", "hp1", "Still")]
F.FILES["stopwatch.mov"] = overlays_folder + "/stopwatch.mov"
F.ROOT.c[-1].colour = "Lime"  # (a colour given by hand, one the template doesn't use)
name, _template = organise.best_template(F.Project())
check("goes by the template whose bins the project has", name == "mine")

adj, comp, photo = F.Item("Adjustment Clip", 0, 30), F.Item("Fusion Composition", 30, 60), F.Item("photo_1.jpg", 60, 90)
comp.comps = 1
photo.mpi = next(c for c in F.ROOT.c if c.GetName() == "photo_1.jpg")
F.TRACKS[("video", 1)] = [adj, comp, photo]
F.TRACKS[("audio", 1)] = [F.Item("whoosh.wav", 0, 30)]

worked, said = organise.organise(resolve)
print("    " + said)
have = organise._project_bins(F.ROOT)
check("the template's missing bins are added", all(p in have for p in ("01_a-roll", "03_graphics/overlays", "06_timelines")))
check("stills go in images", bin_of("photo_1.jpg") == "03_graphics/images" and bin_of("hand picked.png") == "03_graphics/images")
check("a Fusion composition goes in fusion", bin_of("Fusion Composition") == "05_fusion")
check("a file from your folder goes where its rule says", bin_of("stopwatch.mov") == "03_graphics/overlays")
check("footage no folder rule claims stays in Master for you", bin_of("av.mp4") == "(Master)")
check("sound effects go in sfx (short, or a word like ambience)",
      bin_of("whoosh.wav") == "04_audio/sfx" and bin_of("rain ambience.wav") == "04_audio/sfx")
check("a long sound that says nothing is music", bin_of("untitled_01.wav") == "04_audio/music")
check("a sound already in a bin stays", bin_of("Upbeat Corporate.wav") == "Music")
check("a clip already in a bin isn't moved", bin_of("broll take.mp4") == "02_b-roll")
pool = {c.GetName(): c for f in [F.ROOT] + list(have.values()) for c in f.GetClipList()}
check("stills are navy, b-roll orange, overlays pink",
      pool["photo_1.jpg"].GetClipColor() == "Navy" and pool["broll take.mp4"].GetClipColor() == "Orange"
      and pool["stopwatch.mov"].GetClipColor() == "Pink")
check("a colour given by hand is kept", pool["hand picked.png"].GetClipColor() == "Lime")
check("footage and sound keep Resolve's own (no colour, or theirs)",
      pool["av.mp4"].GetClipColor() == "Blue" and pool["Upbeat Corporate.wav"].GetClipColor() == "")
check("a Fusion composition in the Media Pool isn't asked (Resolve never keeps it)",
      "POOLCOLOUR Fusion Composition" not in log())
check("on the timeline: a still navy; an adjustment clip and a composition keep Resolve's own",
      adj.GetClipColor() == "" and comp.GetClipColor() == "" and photo.GetClipColor() == "Navy")
check("audio tracks are left alone", F.TRACKS[("audio", 1)][0].GetClipColor() == "")
check("it says what it did", worked and "mine" in said and "sorted" in said and "coloured" in said)

worked, said = organise.organise(resolve)
check("again: all in order", worked and said.endswith("all in order"))

# -- a pattern beats its folder; ~ is home --
places = {"kinds": {}, "folders": {"~/gen": "overlays", "~/gen/*_broll_*": "b-roll/screen"}}
home = os.path.expanduser("~")
check("a file matching a pattern goes where the pattern says",
      organise.place_for("video", home + "/gen/2026_broll_research.mp4", places) == "b-roll/screen")
check("the rest of that folder goes where the folder says",
      organise.place_for("video", home + "/gen/2026_stopwatch.mov", places) == "overlays")

# -- Subfolders: each file into a bin named after its folder, inside the rule's bin --
places = {"kinds": {}, "folders": {"~/sfx": "04_audio/sfx", "~/gen/*_broll_*": "b-roll/screen"},
          "split": ["~/sfx", "~/gen/*_broll_*"]}
check("a file in a folder of the rule's folder: that folder's bin, inside",
      organise.place_for("sfx", home + "/sfx/_collections/whoosh/fast.wav", places) == "04_audio/sfx/whoosh"
      and organise.place_for("sfx", home + "/sfx/ambient/rain.wav", places) == "04_audio/sfx/ambient")
check("...one straight in the rule's folder: the rule's bin",
      organise.place_for("sfx", home + "/sfx/pop.wav", places) == "04_audio/sfx")
check("...a pattern: only below where it starts",
      organise.place_for("video", home + "/gen/2026_broll_a.mp4", places) == "b-roll/screen")
check("...without it the bin as it is",
      organise.place_for("sfx", home + "/sfx/ambient/rain.wav", dict(places, split=[])) == "04_audio/sfx")

# -- a built-in template: rules made from its bins --
rules = organise.rules(pt.BUILTIN["Tutorial / screen recording"])
check("a built-in template's stills go in its stills bin", rules["places"]["kinds"].get("still") == "04_graphics/stills")
check("a template saying nothing: footage and sound get no colour",
      not {"video", "music", "sfx"} & set(rules["colours"]["kinds"]))

# -- updating a template from the project keeps its organise --
pt.save_current(resolve, "mine")
check("updated from the project: its folder rule stays",
      pt.saved_templates()["mine"].get("organise", {}).get("places", {}).get("folders") == {overlays_folder: "03_graphics/overlays"})

# -- a bin renamed or taken away takes its rules with it --
own = organise.editable(pt.saved_templates()["mine"])
organise.bin_moved(own, "03_graphics", "03_pictures")
check("renamed: the kinds and folders inside it follow",
      own["places"]["kinds"]["still"] == "03_pictures/images"
      and own["places"]["folders"][overlays_folder] == "03_pictures/overlays")
organise.bin_moved(own, "03_pictures/overlays", None)
check("taken away: its folders' rules go", overlays_folder not in own["places"]["folders"])
organise.bin_moved(own, "03_pictures", None)
check("taken away: a kind going there stays in Master", own["places"]["kinds"]["still"] == "")
check("a bin with no colour of its own: the kind's counts",
      organise.colour_for("still", "02_b-roll", {"kinds": {"still": "Navy"}, "bins": {"02_b-roll": ""}}) == "Navy")

# -- Resolve copying instead of moving (2026-10-30, the owner's run): no duplicates left, every clip still sorted --
F.ROOT.c += [F.MPI(f"grab_{n}.png", f"gr{n}", "Still") for n in range(3)]
for n in range(3):
    F.FILES[f"grab_{n}.png"] = f"/home/me/grabs/grab_{n}.png"
F.COPY_ON_MOVE[0] = 1
worked, said = organise.organise(resolve)
print("    " + said)
images = organise._project_bins(F.ROOT)["03_graphics/images"]
grabs = [c.GetName() for c in images.GetClipList() if c.GetName().startswith("grab_")]
check("Resolve copied: the copies go, ours are moved one at a time",
      sorted(grabs) == ["grab_0.png", "grab_1.png", "grab_2.png"]
      and not any(c.GetName().startswith("grab_") for c in F.ROOT.GetClipList())
      and all(c.GetMediaId().startswith("gr") and "-copy" not in c.GetMediaId()
              for c in images.GetClipList() if c.GetName().startswith("grab_")))
check("...and it says 3 sorted", worked and "3 clips sorted" in said and "wouldn't move" not in said)
organise.RETRY_AFTER = (0, 0)  # (no waiting in the test)
F.ROOT.c += [F.MPI("stuck.png", "st1", "Still")]
F.FILES["stuck.png"] = "/home/me/grabs/stuck.png"
_real_move = F.Pool.MoveClips
F.Pool.MoveClips = lambda self, clips, folder: (F.COPY_ON_MOVE.__setitem__(0, 1), _real_move(self, clips * 2, folder))[1] \
    if any(c.GetName() == "stuck.png" for c in clips) else _real_move(self, clips, folder)
worked, said = organise.organise(resolve)
F.Pool.MoveClips = _real_move
check("copied even alone: it stays in Master, no copy left, and it's said",
      [c.GetName() for c in F.ROOT.GetClipList()].count("stuck.png") == 1
      and not any(c.GetName() == "stuck.png" for c in images.GetClipList()) and "1 Resolve wouldn't move" in said)

F.ROOT.c += [F.MPI("busy.png", "bz1", "Still")]
F.FILES["busy.png"] = "/home/me/grabs/busy.png"
tries = [0]

def _busy_move(self, clips, folder):  # (copied the first three times - Resolve still busy with it - then moved)
    if any(c.GetName() == "busy.png" for c in clips) and tries[0] < 3:
        tries[0] += 1
        F.COPY_ON_MOVE[0] = 1
        return _real_move(self, clips * 2, folder)
    return _real_move(self, clips, folder)
F.Pool.MoveClips = _busy_move
worked, said = organise.organise(resolve)
F.Pool.MoveClips = _real_move
check("copied for a moment: tried again a little later, then it moves",
      any(c.GetName() == "busy.png" for c in images.GetClipList()) and tries[0] == 3
      and not any(c.GetName() == "busy.png" for c in F.ROOT.GetClipList())
      and [c.GetName() for c in images.GetClipList()].count("busy.png") == 1)

# -- a colour changed in the template: clips in the old one change too, one given by hand stays --
lime_by_hand = next(c for c in images.GetClipList() if c.GetName() == "hand picked.png")
mine = pt.saved_templates()["mine"]
own = organise.editable(mine)
own["colours"]["kinds"]["still"] = "Blue"
own["colours"]["was"] = ["Purple"]
mine["organise"] = own
paths.write_json(pt._file("mine"), mine)
purple = next(c for c in images.GetClipList() if c.GetName().startswith("grab_"))
purple.SetClipColor("Purple")
organise.organise(resolve)
check("changed Navy to Blue: the stills in Navy are Blue now", photo.GetClipColor() == "Blue"
      and next(c for c in images.GetClipList() if c.GetName() == "photo_1.jpg").GetClipColor() == "Blue")
check("...one in a colour it gave before (\"was\") too", purple.GetClipColor() == "Blue")
check("...one given by hand stays", lime_by_hand.GetClipColor() == "Lime")

# -- a colour changed in the template file itself (nothing remembered in it): what Organise gave a clip is its own --
mine = pt.saved_templates()["mine"]
mine["organise"]["colours"]["kinds"]["still"] = "Violet"
paths.write_json(pt._file("mine"), mine)
organise.organise(resolve)  # (Blue -> Violet: Blue is in "was"? no - only what it gave each clip says so)
mine["organise"]["colours"]["kinds"]["still"] = "Apricot"
mine["organise"]["colours"]["was"] = []
paths.write_json(pt._file("mine"), mine)
organise.organise(resolve)
check("changed in the file twice: the clips follow (what Organise gave each one)",
      photo.GetClipColor() == "Apricot" and purple.GetClipColor() == "Apricot")
check("...the one given by hand still stays", lime_by_hand.GetClipColor() == "Lime")

# -- Recolour all clips: one coloured by hand gets the template's too; nothing moves --
loose_before = [c.GetName() for c in F.ROOT.GetClipList()]
worked, said = organise.organise(resolve, colours=True)
check("Recolour all: one coloured by hand gets the template's colour", lime_by_hand.GetClipColor() == "Apricot")
check("...nothing is moved", [c.GetName() for c in F.ROOT.GetClipList()] == loose_before and said.startswith("Recoloured"))
adj.SetClipColor("Tan")
mine = pt.saved_templates()["mine"]
mine["organise"]["colours"]["kinds"]["adjustment"] = ""
paths.write_json(pt._file("mine"), mine)
organise.organise(resolve, colours=True)
check("...a kind the template gives no colour any more loses Organise's", adj.GetClipColor() == "")
footage = F.TRACKS[("audio", 1)][0]
check("...footage it never coloured is left as it is", footage.GetClipColor() == "")

# -- just what Clipse has made (a grab, a clip placed): only those coloured, nothing sorted --
F.ROOT.c += [F.MPI("new_grab.png", "ng1", "Still"), F.MPI("loose.png", "lo1", "Still")]
new_grab = F.ROOT.c[-2]
grab_item = F.Item("new_grab.png", 90, 120, new_grab)
placed = F.Item("Adjustment Clip", 120, 150)
F.TRACKS[("video", 2)] = [grab_item, placed]
organise.organise(resolve, only={organise._key(new_grab), organise._key(placed)})
check("only what was made: the grab and its timeline clip, the clip placed",
      new_grab.GetClipColor() == "Apricot" and grab_item.GetClipColor() == "Apricot" and placed.GetClipColor() == "")
check("...nothing else coloured or sorted", any(c.GetName() == "loose.png" for c in F.ROOT.GetClipList())
      and next(c for c in F.ROOT.GetClipList() if c.GetName() == "loose.png").GetClipColor() == ""
      and any(c.GetName() == "new_grab.png" for c in F.ROOT.GetClipList()))
check("keys: a Media Pool clip by its media id, a timeline clip by its own", organise._key(new_grab) == "m:ng1"
      and organise._key(placed).startswith("t:item-"))

# -- coloured here and now (colour_now): a new grab in its bin, a clip placed on the timeline --
F.ROOT.c += [F.MPI("now_grab.png", "nw1", "Still")]
now_grab = F.ROOT.c[-1]
now_item = F.Item("now_grab.png", 150, 180, now_grab)
comp_now = F.Item("Fusion Composition", 180, 210)
comp_now.comps = 1
F.TRACKS[("video", 2)] += [now_item, comp_now]
organise.colour_now(resolve, [now_grab, comp_now])
check("colour_now: the new still gets its colour at once, the composition keeps Resolve's",
      now_grab.GetClipColor() == "Apricot" and comp_now.GetClipColor() == "")

# -- Settings > Organise: what's changed there is the template's --
from PySide6.QtCore import Qt
from clipse.settings import Settings
from clipse.settings_dialog import SettingsDialog
settings = Settings()
settings.load()
dialog = SettingsDialog(settings)
dialog._show_page([t for t, _i, _b in dialog.PAGES].index("Organise"))
_setup.pump(0.05)
page = dialog._organise_page
page._choose("mine")
check("the page shows the template's bins", "04_audio/sfx" in page._bins() and page.bin_tree.topLevelItemCount() == len(page.tree))
item = next(i for i in page._items() if i.data(0, Qt.UserRole) == "04_audio")
item.setText(0, "04_sound")
_setup.pump(0.05)
saved = pt.saved_templates()["mine"]
check("a bin renamed there is saved, with its kinds", "04_sound/sfx" in organise.bin_paths(saved["bins"])
      and saved["organise"]["places"]["kinds"]["sfx"] == "04_sound/sfx")
before = page.own["colours"]["kinds"]["still"]
page._kind_colour("still", "Purple")
check("a colour changed there is remembered as one it gave",
      before in pt.saved_templates()["mine"]["organise"]["colours"]["was"])
page._kind_colour("video", "Blue")
page._kind_place("video", "01_a-roll")
page.bin_tree.setCurrentItem(next(i for i in page._items() if i.data(0, Qt.UserRole) == "02_b-roll"))
page._add_bin(inside=True)
saved = pt.saved_templates()["mine"]
check("a kind's place and colour are saved", saved["organise"]["places"]["kinds"]["video"] == "01_a-roll"
      and saved["organise"]["colours"]["kinds"]["video"] == "Blue")
check("a bin added inside another", "02_b-roll/new_bin" in organise.bin_paths(saved["bins"]))
page.bin_tree.setCurrentItem(next(i for i in page._items() if i.data(0, Qt.UserRole) == "02_b-roll/new_bin"))
page._remove_bin()
page._bin_colour("02_b-roll/screen", "Lime")
page._folder_place(overlays_folder, "02_b-roll/screen")
_setup.pump(0.05)
saved = pt.saved_templates()["mine"]
check("removed, a bin colour, a folder's bin: saved", "02_b-roll/new_bin" not in organise.bin_paths(saved["bins"])
      and saved["organise"]["colours"]["bins"]["02_b-roll/screen"] == "Lime"
      and saved["organise"]["places"]["folders"][overlays_folder] == "02_b-roll/screen")
page._folder_split(overlays_folder, True)
saved = pt.saved_templates()["mine"]
check("Subfolders switched on there is saved", saved["organise"]["places"]["split"] == [overlays_folder])
page._folder_renamed(overlays_folder, "/home/me/overlays")
_setup.pump(0.05)
saved = pt.saved_templates()["mine"]
check("...renamed, the folder keeps it", saved["organise"]["places"]["split"] == ["/home/me/overlays"])
page._remove_folder("/home/me/overlays")
_setup.pump(0.05)
check("...removed, it goes", pt.saved_templates()["mine"]["organise"]["places"]["split"] == [])
page._choose("YouTube video")
page._kind_colour("music", "Green")
check("a built-in changed there is saved as yours", pt.saved_templates().get("YouTube video", {}).get("organise",
      {}).get("colours", {}).get("kinds", {}).get("music") == "Green")
page._remove_template()
check("Reset takes yours away: the built-in is back", "YouTube video" not in pt.saved_templates()
      and page.name == "YouTube video")
dialog.close()

print(f"\n{'all good' if not fails else f'{fails} failed'}")
raise SystemExit(1 if fails else 0)
