"""Record Voiceover (voiceover.py, voiceover_pill.py): following playback, trimming the quiet, the takes' files and
names, a take's steps - when you speak, pause, restart, the playhead moving, the timeline muted - and the script in Resolve's menu. No microphone
or Resolve needed. python3 tests/test_voiceover.py"""
import os
import sys
import tempfile
import wave

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import numpy as np

import _setup  # (first: a throwaway HOME - the takes are written into it)
from clipse import client, launch, resolve_shortcuts as rs, voiceover as vo
from clipse.settings import RESOLVE_KEYED

fails = 0


def check(what, ok):
    global fails
    print(("ok   " if ok else "FAIL ") + what)
    fails += not ok


# -- hearing you start --
check("his room isn't speech (-58 dB)", not vo.speech_started(-58, -60))
check("his voice is (-30 dB)", vo.speech_started(-30, -60))
check("a loud room needs a voice well over it", not vo.speech_started(-35, -45) and vo.speech_started(-28, -45))

# -- trimming the quiet --
rate = vo.RATE
rng = np.random.default_rng(2)
take = (rng.standard_normal(rate * 3) * 0.002).astype(np.float32)  # a quiet room, 3 s
take[rate:2 * rate] += (np.sin(np.arange(rate) * 2 * np.pi * 220 / rate) * 0.3).astype(np.float32)  # words 1-2 s
first, end = vo.trim_silence(take)
check("the quiet before the words goes, a little kept", abs(first / rate - 0.85) < 0.06)
check("the quiet after them too", abs(end / rate - 2.15) < 0.06)
room = (rng.standard_normal(rate * 3) * 0.0012).astype(np.float32)  # his room: -58 dB, with clicks to -53
room[::4800] = 0.03
room[rate:int(1.6 * rate)] += (np.sin(np.arange(int(0.6 * rate)) * 2 * np.pi * 180 / rate) * 0.05).astype(np.float32)
first, end = vo.trim_silence(room)
check("a room's clicks aren't words (2026-10-27: it kept a second of his room)",
      abs(first / rate - 0.85) < 0.06 and abs(end / rate - 1.75) < 0.06)
check("all quiet: nothing cut", vo.trim_silence(take[:rate // 2]) == (0, rate // 2))

# -- the files --
with tempfile.TemporaryDirectory() as where:
    check("the first take is voiceover_01", vo.next_name(where) == "voiceover_01.wav")
    for name in ("voiceover_01.wav", "voiceover_07.wav", "notes.txt"):
        open(os.path.join(where, name), "w").close()
    check("the next is after the highest", vo.next_name(where) == "voiceover_08.wav")
    path = os.path.join(where, "sub", "voiceover_08.wav")
    vo.write_wav(path, np.array([0.0, 0.5, -1.0, 2.0], np.float32))
    with wave.open(path) as f:
        data = f.readframes(4)
        check("a 24-bit mono 48 kHz WAV", (f.getnchannels(), f.getsampwidth(), f.getframerate()) == (1, 3, 48000))
    samples = [int.from_bytes(data[i:i + 3], "little", signed=True) for i in range(0, 12, 3)]
    check("its samples, a loud one held at full", samples == [0, 4194304, -8388607, 8388607])


class _Settings:
    files = {"voice_folder": ""}


check("in Music/Clipse/<project>", vo.folder(_Settings, "My: project") == os.path.join(vo.DEFAULT_FOLDER, "My_ project"))

# -- what's kept while waiting, and cut --
r = vo.Recorder()
r._t0 = 0.0
for n in range(10):  # ten 0.1 s chunks, each its number
    r._chunks.append(np.full(rate // 10, n, np.float32))
    r._count += rate // 10
r.forget_before(0.35)
check("waiting, the start is forgotten", r._dropped == 3 * rate // 10)
cut = r.cut(r.index_at(0.5), r.index_at(0.7))
check("a moment on the clock is its place in the take", len(cut) == rate // 5 and cut[0] == 5 and cut[-1] == 6)

# -- pauses --
check("a take without its pauses", vo.kept_spans(0, 10, [(2, 3), (5, 7)]) == [(0, 2), (3, 5), (7, 10)])
check("...one still paused when it stops", vo.kept_spans(0, 10, [(4, None)]) == [(0, 4)])
check("...and none", vo.kept_spans(1, 4, []) == [(1, 4)])

# -- the script --
check("in Resolve's menu as Clipse 21", rs.menu_name("Record Voiceover") == "Clipse 21 - Record Voiceover")
check("its action is keyed there", RESOLVE_KEYED["Record voiceover"] == rs.menu_name("Record Voiceover"))
check("the playhead's mover is a part of its own", launch.command("playhead")[-1] in ("clipse.playhead", "--playhead"))
check("clipse voice record sends it", client.build_message(["voice", "record"]) == b"VOICE:record")
check("(and clipse swap clip, which had no prefix)", client.build_message(["swap", "clip"]) == b"SWAP:clip")

# -- a take's steps, against a stand-in microphone, Resolve and picker --
import time  # noqa: E402

from clipse import voiceover_pill as vp  # noqa: E402
from clipse.settings import Settings  # noqa: E402
from clipse.timeline_tools import frames_tc  # noqa: E402


class _Mic:  # every moment a sample - loud while `speaking` - no device
    level = 0.5
    speaking = True

    def __init__(self, mic=""):
        self.began = time.monotonic()

    def start(self):
        return None

    @property
    def seconds(self):
        return time.monotonic() - self.began

    def loudness(self, _seconds):
        return -25.0 if _Mic.speaking else -60.0

    def index_at(self, moment):
        return int(round(moment * vo.RATE))

    def forget_before(self, moment):
        pass

    def cut(self, start=None, end=None):
        return np.full(max(0, end - start), 0.3, np.float32)

    def stop(self):
        pass


class _Timeline:
    def __init__(self):
        self.playhead = 86400 + 1000  # (01:00:00:00 + 1000 frames, at 24)
        self.playing_from = None      # (time it started, frame) while it plays

    def frame(self):
        if self.playing_from is None:
            return self.playhead
        since, start = self.playing_from
        return start + int((time.monotonic() - since) * 24)

    def GetSetting(self, _key):
        return "24"

    def GetCurrentTimecode(self):
        return frames_tc(self.frame(), 24)

    def SetCurrentTimecode(self, timecode):
        self.put_back = timecode  # (the test only looks that it was put back)
        return True

    def GetUniqueId(self):
        return "tl"

    def GetStartFrame(self):
        return 86400

    tracks = {1: True, 2: False, 3: True}  # A2 was off already

    def GetTrackCount(self, _kind):
        return len(self.tracks)

    def GetIsTrackEnabled(self, _kind, index):
        return self.tracks[index]

    def SetTrackEnable(self, _kind, index, on):
        self.tracks[index] = on
        return True


class _Resolve:
    def __init__(self, timeline):
        project = type("P", (), {"GetCurrentTimeline": lambda _s: timeline, "GetName": lambda _s: "Test"})()
        manager = type("M", (), {"GetCurrentProject": lambda _s: project})()
        self.GetProjectManager = lambda: manager


class _Picker(vp.QObject):
    def __init__(self, timeline):
        super().__init__()
        self.settings = Settings()
        self.resolve = _Resolve(timeline)
        self.placed, self.said = [], []

    def font(self):
        return _setup.app.font()

    def _timeline_id(self, timeline):
        return timeline.GetUniqueId()

    def _say(self, text, *a, **k):
        self.said.append(text)

    def _place_voiceover(self, path, frame, _timeline_id):
        with wave.open(path) as f:
            self.placed.append((frame, f.getnframes() / f.getframerate()))
        return True, "Voiceover on A3"


vp.vo.Recorder = _Mic
told = []  # what the playhead's mover was told: its word and frame
vp.VoiceoverTake._start_mover = lambda self: setattr(self, "_mover", None)
vp.VoiceoverTake._tell_mover = lambda self, line: told.append(
    " ".join({"move": lambda w: [w[0], w[2]], "goto": lambda w: w[:2]}.get(line.split()[0], lambda w: w[:1])(line.split())))
tl = _Timeline()
w = _Picker(tl)
w.settings.timeline_tools.update(voice_start="now", voice_trim=False, voice_mute=True)
take = vp.VoiceoverTake(w)
check("at once: it records straight away", take.begin() is None and take.state == "recording")
check("...Pause, Restart, Stop and the cross on the pill", take.pill.buttons == ("pause", "restart", "stop"))
check("...the timeline muted: the audio tracks that were on are off", tl.tracks == {1: False, 2: False, 3: False})
check("...and the playhead moves from where it was", told[-1] == "move 87400")
_setup.pump(0.4)
take._clicked("pause")
check("paused: Resume in place of Pause, the playhead waits", take.state == "paused"
      and take.pill.buttons[0] == "resume" and told[-1] == "hold")
_setup.pump(0.5)
take._clicked("resume")
check("...and moves on from where the take is", told[-1] in ("move " + str(87400 + n) for n in (9, 10, 11)))
_setup.pump(0.4)
take.finish()
check("stopped, one take, where the playhead was", len(w.placed) == 1 and w.placed[0][0] == 86400 + 1000)
check("...as long as it recorded, the pause left out", abs(w.placed[0][1] - 0.8) < 0.1)
check("...nothing said after it", w.said == [] and not take.active)
check("...the tracks as they were (A2 still off)", tl.tracks == {1: True, 2: False, 3: True})

take = vp.VoiceoverTake(w)
take.begin()
_setup.pump(0.6)
take._clicked("restart")
check("Restart: the playhead back to the start", told[-2] == "goto 87400" and told[-1] == "move 87400")
_setup.pump(0.3)
take.finish()
check("...and what came before thrown away", abs(w.placed[-1][1] - 0.3) < 0.1)

take = vp.VoiceoverTake(w)
take.begin()
_setup.pump(0.3)
take._clicked("cancel")
check("the cross: nothing placed, nothing said, the tracks back", len(w.placed) == 2 and w.said == []
      and not take.active and tl.tracks == {1: True, 2: False, 3: True})

w.settings.timeline_tools["voice_start"] = "speech"
_Mic.speaking = False
take = vp.VoiceoverTake(w)
take.begin()
_setup.pump(0.5)
check("when you speak: it listens, the cross only, the playhead still", take.state == "listening"
      and take.pill.buttons == () and not told[-1].startswith("move"))
_Mic.speaking = True
_setup.pump(0.1)
check("...records once you're heard", take.state == "recording")
check("...a moment from before kept: the take starts that much earlier",
      take.lead == round(vo.LEAD_SECONDS * 24) and told[-1] == "move " + str(87400 - take.lead))
_setup.pump(0.5)
take.finish()
check("...and lands that much before the playhead, the words on it",
      w.placed[-1][0] == 86400 + 1000 - take.lead and abs(w.placed[-1][1] - (0.5 + vo.LEAD_SECONDS)) < 0.12)

print("\nall good" if not fails else f"\n{fails} failed")
sys.exit(1 if fails else 0)
