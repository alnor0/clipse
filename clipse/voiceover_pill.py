"""A voiceover, from the key in Resolve (Clipse 21 - Record Voiceover) or the Actions panel to the clip on the
timeline: the pill low in the middle of the screen while it records (VoiceoverPill - a count-down, how long, how
loud, and its buttons), and its steps (VoiceoverTake). The recording itself is voiceover.py.

Pressed once it starts - when you speak, after a count-down, or at once (Settings > Scripts) - pressed again it stops
and the take goes on the timeline where the playhead was. While it records the playhead moves along (playhead.py,
2026-10-27: "make the playhead move with the recording") and, with Mute the timeline on, the audio tracks are
switched off ("mute everything that passes") and back as they were after. The pill's buttons (the same day: "an
option to expand the recorder to be able to click pause, restart etc" - buttons, not more scripts: a script's place
in Resolve's menu is for good): Pause / Resume (the take one clip, without the pause; the playhead waits), Restart
(thrown away, from the same spot again), Stop, and the cross (thrown away). The pill never takes the keyboard: the
key stays Resolve's. Nothing is said once a take is on the timeline ("dont give me a message after the insert")."""
import os
import subprocess
import sys
import time

from PySide6.QtCore import QEasingCurve, QObject, QPointF, QPropertyAnimation, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QCursor, QFontMetricsF, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import QWidget

from . import voiceover as vo
from .fonts import at as font_at
from .keycast import place

TICK_MS = 30  # the pill's meter and clock, and the playhead read while following playback
LISTENING = "Speak to start"
COUNTDOWN_SECONDS = 3
BUTTON_WORDS = {"pause": "Pause", "resume": "Resume", "restart": "Restart", "stop": "Stop"}
SAME_WIDTH = {"pause": ("Pause", "Resume"), "resume": ("Pause", "Resume")}  # (paused, the pill doesn't jump)


def _clock(seconds):
    minutes, seconds = divmod(int(seconds), 60)
    return f"{minutes}:{seconds:02d}"


class VoiceoverPill(QWidget):
    """What's going on with the take, small and over Resolve: a dot (red while it records), a few words or the time,
    the microphone's level, the buttons for now, and a cross that throws the take away. Clicks only."""
    clicked = Signal(str)  # a key of BUTTON_WORDS, or "cancel"

    def __init__(self, settings):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
                         | Qt.WindowDoesNotAcceptFocus | Qt.NoDropShadowWindowHint)
        self.settings = settings
        self.setWindowTitle("Clipse voiceover")
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_MacAlwaysShowToolWindow)  # (else hidden on a Mac while Resolve is in front)
        self.setMouseTracking(True)
        self.state = None        # "countdown", "listening" (for your voice), "recording", "paused"
        self.text = ""
        self.buttons = ()        # keys of BUTTON_WORDS, left to right (the cross is always last)
        self.level = 0.0         # 0-1, as shown: quick up, slow down
        self._hover = None
        self._hit = {}           # key -> QRectF
        self._anim = QPropertyAnimation(self, b"windowOpacity", self)
        self._anim.setDuration(140)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)

    def _font(self):
        return font_at(1.0, self.font())

    def _sizes(self):
        fm = QFontMetricsF(self._font())
        return fm, fm.height() + 22

    @staticmethod
    def _button_width(fm, key):
        return max(fm.horizontalAdvance(words) for words in SAME_WIDTH.get(key, (BUTTON_WORDS[key],))) + 20

    def _words_width(self, fm):
        return fm.horizontalAdvance("00:00" if self.state in ("recording", "paused") else self.text)

    def show_state(self, state, text, buttons=()):
        """The pill for `state` with `text` and `buttons` - sized for them, low in the middle of the screen."""
        first = not self.isVisible()
        resized = first or state != self.state or len(buttons) != len(self.buttons)
        self.state, self.text, self.buttons = state, text, tuple(buttons)
        if not resized:
            self.update()
            return
        fm, h = self._sizes()
        width = 18 + 20 + self._words_width(fm) + 18 + 96 + 14 \
            + sum(self._button_width(fm, b) + 6 for b in self.buttons) + (h - 14) + 8
        self.setFixedSize(int(width), int(h))  # (one size at a time: on Sway it floats)
        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        area = screen.availableGeometry()
        if first:
            self.setWindowOpacity(0.0)
            self.show()
        place(self, area.center().x() - self.width() // 2, area.bottom() - self.height() - int(area.height() * 0.08))
        self.raise_()
        if first:
            QTimer.singleShot(40, self._fade_in)
        self.update()

    def _fade_in(self):
        self._anim.stop()
        self._anim.setStartValue(self.windowOpacity())
        self._anim.setEndValue(1.0)
        self._anim.start()

    def set_level(self, peak):
        """The microphone's loudest just now (0-1), on a dB scale from -60."""
        import math
        shown = 0.0 if peak <= 0.001 else max(0.0, min(1.0, (20 * math.log10(peak) + 60) / 60))
        self.level = shown if shown > self.level else self.level * 0.86 + shown * 0.14
        self.update()

    def _under(self, event):
        return next((key for key, r in self._hit.items() if r.contains(event.position())), None)

    def mouseMoveEvent(self, event):
        hover = self._under(event)
        if hover != self._hover:
            self._hover = hover
            self.setCursor(Qt.PointingHandCursor if hover else Qt.ArrowCursor)
            self.update()

    def leaveEvent(self, event):
        self._hover = None
        self.update()

    def mousePressEvent(self, event):
        hit = self._under(event)
        if hit:
            self.clicked.emit(hit)

    def paintEvent(self, event):
        from .actions_panel import script_red
        t = self.settings.theme
        fm, h = self._sizes()
        text_c, muted = QColor(t["picker_text"]), QColor(t["picker_folder"])
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        bg = QColor(t.get("picker_bar_bg", t["picker_bg"]))
        bg.setAlphaF(0.97)
        edge = QColor(text_c)
        edge.setAlphaF(0.14)
        p.setPen(edge)
        p.setBrush(bg)
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        cy = self.height() / 2
        red = script_red(t)
        x = 18.0
        # the dot: red while recording (breathing a little), quiet before and while paused
        p.setPen(Qt.NoPen)
        if self.state == "recording":
            dot = QColor(red)
            dot.setAlphaF(0.65 + 0.35 * abs(((time.monotonic() * 0.8) % 2) - 1))
        else:
            dot = QColor(muted)
        p.setBrush(dot)
        p.drawEllipse(QPointF(x + 5, cy), 4.5, 4.5)
        x += 20
        p.setFont(self._font())
        p.setPen(text_c if self.state == "recording" else muted)
        words = self._words_width(fm)
        p.drawText(QRectF(x, 0, words + 2, self.height()), Qt.AlignLeft | Qt.AlignVCenter, self.text)
        x += words + 18
        # how loud: a thin track, the level in the text's colour - red when it's about to clip
        p.setPen(Qt.NoPen)
        track = QRectF(x, cy - 2.5, 96, 5)
        surface = QColor(text_c)
        surface.setAlphaF(0.1)
        p.setBrush(surface)
        p.drawRoundedRect(track, 2.5, 2.5)
        if self.level > 0.01:
            fill = QColor(red) if self.level > 0.97 else QColor(text_c)
            if self.level <= 0.97:
                fill.setAlphaF(0.6)
            p.setBrush(fill)
            p.drawRoundedRect(QRectF(track.left(), track.top(), max(5.0, track.width() * self.level), 5), 2.5, 2.5)
        x = track.right() + 14
        self._hit = {}
        button_h = fm.height() + 8
        for key in self.buttons:  # soft buttons, as Vicinae's: the text's colour at 7 %, 12 % under the mouse
            words = BUTTON_WORDS[key]
            box = QRectF(x, cy - button_h / 2, self._button_width(fm, key), button_h)
            fill = QColor(text_c)
            fill.setAlphaF(0.12 if self._hover == key else 0.07)
            p.setPen(Qt.NoPen)
            p.setBrush(fill)
            p.drawRoundedRect(box, 6, 6)
            p.setPen(text_c)
            p.drawText(box, Qt.AlignCenter, words)
            self._hit[key] = box
            x = box.right() + 6
        side = h - 14
        box = QRectF(x, cy - side / 2, side, side)
        if self._hover == "cancel":
            fill = QColor(text_c)
            fill.setAlphaF(0.1)
            p.setPen(Qt.NoPen)
            p.setBrush(fill)
            p.drawEllipse(box)
        p.setPen(QPen(text_c if self._hover == "cancel" else muted, 1.4, Qt.SolidLine, Qt.RoundCap))
        k = side * 0.2
        c = box.center()
        p.drawLine(QPointF(c.x() - k, c.y() - k), QPointF(c.x() + k, c.y() + k))
        p.drawLine(QPointF(c.x() - k, c.y() + k), QPointF(c.x() + k, c.y() - k))
        self._hit["cancel"] = box
        p.end()


class VoiceoverTake(QObject):
    """A voiceover: begin() starts it, finish() puts what's recorded on the timeline and ends it, cancel() throws it
    away and ends it. `window` is the picker: Resolve, the settings, placing a clip, Undo, toasts."""
    done = Signal()

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.settings = window.settings
        self.recorder = None
        self.state = None          # "countdown", "listening", "recording", "paused" - None once it's over
        self.frame = None          # where the playhead was: where the take's words go
        self.lead = 0              # frames of sound kept from before that (starting when you speak)
        self.fps = 24.0
        self.drop = False          # a drop-frame timecode
        self.timeline_id = None
        self._go = None            # when the take's sound begins, on time.monotonic()'s clock
        self._pauses = []          # [(paused, resumed or None)] of the take
        self._countdown_end = None
        self._room = None          # the quietest moment heard while listening (dBFS)
        self._muted = []           # audio tracks switched off for the take - switched on again after
        self._mover = None         # playhead.py, running
        self.pill = VoiceoverPill(self.settings)
        self.pill.setFont(window.font())
        self.pill.clicked.connect(self._clicked)
        self._timer = QTimer(self)
        self._timer.setInterval(TICK_MS)
        self._timer.timeout.connect(self._tick)

    @property
    def active(self):
        return self.state is not None

    def _timeline(self):
        project = self.window.resolve.GetProjectManager().GetCurrentProject()
        return project.GetCurrentTimeline() if project else None

    def begin(self):
        """None once it's going, else why it can't."""
        from .timeline_tools import tc_frames
        if not vo.available():
            return "Recording needs the miniaudio library"
        try:
            timeline = self._timeline()
        except Exception:
            timeline = None
        if timeline is None:
            return "Open a timeline first"
        try:
            self.fps = float(timeline.GetSetting("timelineFrameRate") or 24) or 24.0
            timecode = timeline.GetCurrentTimecode()
            self.drop = ";" in (timecode or "")
            self.frame = tc_frames(timecode, self.fps) if timecode else None
        except Exception:
            self.frame = None
        if self.frame is None:  # (the Fusion page can't tell a script where the playhead is)
            return "Voiceover needs the Edit, Cut or Fairlight page"
        self.timeline_id = self.window._timeline_id(timeline)
        tools = self.settings.timeline_tools
        self.recorder = vo.Recorder(tools.get("voice_mic", ""))
        problem = self.recorder.start()
        if problem:
            self.recorder = None
            return problem
        if tools.get("voice_mute", True):
            self._mute(timeline)
        self._start_mover()
        self._start_over()
        self._timer.start()
        print(f"[voiceover] at frame {self.frame} ({tools.get('voice_mic') or 'the system microphone'})")
        return None

    # -- the timeline while it records --

    def _mute(self, timeline):
        """Every audio track that's on switched off for the take (a script can't mute one - only this)."""
        try:
            for index in range(1, int(timeline.GetTrackCount("audio") or 0) + 1):
                if timeline.GetIsTrackEnabled("audio", index) and timeline.SetTrackEnable("audio", index, False):
                    self._muted.append(index)
        except Exception as e:
            print(f"[voiceover] couldn't mute the timeline: {e}")

    def _unmute(self):
        if not self._muted:
            return
        try:
            timeline = self._timeline()
            for index in self._muted:
                timeline.SetTrackEnable("audio", index, True)
        except Exception as e:
            print(f"[voiceover] couldn't switch the audio tracks on again ({self._muted}): {e}")
        self._muted = []

    def _start_mover(self):
        from .launch import command
        try:
            self._mover = subprocess.Popen(command("playhead", windowless=True), stdin=subprocess.PIPE,
                                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, text=True)
        except Exception as e:
            self._mover = None
            print(f"[voiceover] the playhead won't move: {e}")

    def _tell_mover(self, line):
        if self._mover is None:
            return
        try:
            self._mover.stdin.write(line + "\n")
            self._mover.stdin.flush()
        except Exception:
            self._mover = None

    def _move_from(self, moment, take_seconds):
        """The playhead moving on from `moment` (monotonic), at the place `take_seconds` into the take."""
        frame = self.frame - self.lead + int(round(take_seconds * self.fps))
        wall = time.time() - (time.monotonic() - moment)  # (the other program's clock)
        self._tell_mover(f"move {wall:.4f} {frame} {self.fps:g} {int(self.drop)}")

    def _stop_mover(self):
        if self._mover is None:
            return
        self._tell_mover("quit")
        try:
            self._mover.stdin.close()
            self._mover.wait(timeout=2.5)  # (Resolve may keep it waiting for a second)
        except Exception:
            self._mover.kill()
        self._mover = None

    # -- a take --

    def _start_over(self):
        """A new take from the same spot: listening for your voice, counted down, or at once - what came before
        forgotten."""
        now = time.monotonic()
        self.recorder.forget_before(now)
        self._pauses, self.lead, self._room = [], 0, None
        self._tell_mover(f"goto {self.frame} {self.fps:g} {int(self.drop)}")
        start = self.settings.timeline_tools.get("voice_start", "speech")
        if start == "speech":
            self.state = "listening"
            self._show(LISTENING)
        elif start == "countdown":
            self.state = "countdown"
            self._countdown_end = now + COUNTDOWN_SECONDS
            self._show(f"Recording in {COUNTDOWN_SECONDS}")
        else:
            self._record_now(now)

    def _buttons(self):
        if self.state == "recording":
            return ("pause", "restart", "stop")
        if self.state == "paused":
            return ("resume", "restart", "stop")
        return ()

    def _show(self, text):
        self.pill.show_state(self.state, text, self._buttons())

    def _record_now(self, moment, lead_seconds=0.0):
        """Recording from `moment` - and `lead_seconds` before it, kept (heard speaking: the start of the word)."""
        self.lead = min(int(round(lead_seconds * self.fps)), max(0, self.frame - self._timeline_start()))
        self._go = moment - self.lead / self.fps
        self.state = "recording"
        self._move_from(self._go, 0.0)
        self._show(_clock(self._recorded(time.monotonic())))

    def _timeline_start(self):
        try:
            return int(self._timeline().GetStartFrame() or 0)
        except Exception:
            return 0

    def _recorded(self, now):
        """How long the take is so far, pauses left out."""
        paused = sum((resumed or now) - since for since, resumed in self._pauses)
        return max(0.0, now - self._go - paused)

    def _clicked(self, key):
        if key == "cancel":
            return self.cancel()
        if key == "stop":
            return self.finish()
        if key == "restart":
            return self._start_over()
        now = time.monotonic()
        if key == "pause" and self.state == "recording":
            self._pauses.append((now, None))
            self.state = "paused"
            self._tell_mover("hold")
        elif key == "resume" and self.state == "paused":
            self._pauses[-1] = (self._pauses[-1][0], now)
            self.state = "recording"
            self._move_from(now, self._recorded(now))
        self._show(_clock(self._recorded(now)))

    def _tick(self):
        if self.state is None:
            return
        now = time.monotonic()
        self.pill.set_level(self.recorder.level)
        if self.state == "countdown":
            left = self._countdown_end - now
            if left <= 0:
                self._record_now(self._countdown_end)
            else:
                self._show(f"Recording in {int(left) + 1}")
            return
        if self.state == "listening":
            level = self.recorder.loudness(0.1)
            if self.recorder.seconds < 0.15:
                return  # (the first moments: the device settling)
            self._room = level if self._room is None else min(self._room, level)
            if vo.speech_started(level, self._room):
                self._record_now(now, vo.LEAD_SECONDS)
            else:
                self.recorder.forget_before(now - 2.0)
            return
        if self.state in ("recording", "paused"):
            took = self._recorded(now)
            self._show(_clock(took))
            if took >= vo.MAX_SECONDS:
                self.finish()

    def _end(self):
        self._timer.stop()
        self.state = None
        self._stop_mover()
        self._unmute()
        if self.recorder is not None:
            self.recorder.stop()
        self.pill.hide()
        self.pill.deleteLater()
        self.done.emit()

    def cancel(self):
        self._end()  # (the cross says what it does: no word after it)

    def finish(self):
        """Stops: what's recorded - its pauses and quiet ends left out - is saved and goes on the timeline."""
        if self.state is None:
            return
        take = None
        if self.state in ("recording", "paused"):
            import numpy as np
            r, now = self.recorder, time.monotonic()
            spans = vo.kept_spans(self._go, now, self._pauses)
            take = np.concatenate([r.cut(r.index_at(a), r.index_at(b)) for a, b in spans] or [np.zeros(0, np.float32)])
        self._end()
        if take is not None:
            self._place(take, self.frame - self.lead)

    def _place(self, sound, frame):
        """The take - its quiet ends trimmed - saved, and on the timeline at `frame`. Said only when that fails."""
        if len(sound) < vo.RATE * 0.3:
            return
        mic = self.settings.timeline_tools.get("voice_mic") or "the microphone"
        if not float(abs(sound).max()):
            if sys.platform == "darwin":
                return self.window._say(f"No sound came from {mic}", 7000,
                                        steps=("System Settings", "Privacy & Security", "Microphone", "Clipse"))
            return self.window._say(f"No sound came from {mic}", 4000)
        if self.settings.timeline_tools.get("voice_trim", True):
            first, last = vo.trim_silence(sound)
            frame += int(round(first / vo.RATE * self.fps))  # (your words stay where you said them)
            sound = sound[first:last]
        try:
            project = self.window.resolve.GetProjectManager().GetCurrentProject()
            where = vo.folder(self.settings, project.GetName() if project else "")
            path = os.path.join(where, vo.next_name(where))
            vo.write_wav(path, sound)
        except Exception as e:
            print(f"[voiceover] couldn't save the take: {e}")
            return self.window._say("Couldn't save the voiceover")
        print(f"[voiceover] {len(sound) / vo.RATE:.1f} s saved as {path}")
        worked, message = self.window._place_voiceover(path, frame, self.timeline_id)
        print(f"[voiceover] {message}")
        if not worked:  # (on the timeline it's there to see: nothing said - 2026-10-27, "dont give me a message")
            self.window._say(message)
