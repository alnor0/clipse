"""Hover explanations for every setting.

apply_help(root) walks a dialog after it's built and gives each setting
(label, checkbox, and the field next to it) a tooltip explaining what it
does — looked up by the setting's visible text, so new settings only need
an entry here. Called from settings_dialog.restrict_tab_to_inputs, which
every dialog already runs after (re)building its widgets.
"""
from PySide6.QtWidgets import QCheckBox, QFormLayout, QLabel, QWidget


HELP = {
    # -- Organise (organise_page.py)
    "Template": "Organise project goes by the template whose bins the project has most of.",
    "Clip colours": "Every clip in the open project gets its colour again, one you coloured by hand too. Nothing is "
                    "moved.",
    "Fusion compositions": "Its colour goes before its bin's.",
    "Compound clips": "Its colour goes before its bin's.",
    "Adjustment clips": "Its colour goes before its bin's.",
    # -- General
    "Show inserted clips in the Media Pool": "When a clip is inserted, also jump to it in the Media Pool.",
    "Insert the highlighted row with staged clips": "When you have staged clips (Tab) and press "
                                                          "Enter, the highlighted row is inserted too.",
    "Include sub-bins": "Inserting a bin also inserts the clips in the bins inside it.",
    "Bin name at the right edge": "The bin's name at the very right of each row, after the star and the other "
                                     "symbols.",
    "Start when you log in": "A tiny helper starts when you "
        "log in and waits for DaVinci Resolve - nothing else. When Resolve opens it starts the picker's "
        "service and reads your project's Media Pool ahead of time, so the first shortcut press opens "
        "everything at once. Off: the first press starts it (a few seconds).",
    "Show timecode": "The preview's time and in/out "
        "marks in hours:minutes:seconds:frames, counted from the clip's own start timecode - the same "
        "numbers Resolve shows for it.",
    "Sound while scrubbing": "Scrubbing with sound, like in Resolve: moving the mouse across "
        "a video - or dragging along the bar or a sound's waveform while it's paused - plays a short piece of "
        "the sound from just there. Slowly, you hear it in little steps; fast, a blur of what's passing. Good "
        "for finding a word, a hit or a beat. Uses the listening volume. Clips over 20 minutes stay silent.",
    "Space plays": "When the Space key plays instead of writing a space. When I'm in the list: in the search, "
        "Space writes a space. Once you move down into the rows (arrow keys, or a click on a row) Space plays "
        "what's highlighted, and the left and right arrows move a second through it. Typing a letter, or "
        "clicking the search, takes you back to searching. With nothing typed, or the mouse on the preview, "
        "Space always plays. Always: every Space plays, and Shift+Space writes a space. Never: only Ctrl+Space.",
    "What Space does": "Short clips start over, long ones pause: a sound effect plays from the start every time "
        "you press Space - handy when listening through them - while music or a long take pauses and carries on. "
        "Or always one of the two. Hold Space on a short sound and it fires over and over. Ctrl+Space is "
        "always play / pause.",
    "Short clips are under": "Clips shorter than this start over on Space; longer ones pause. For What Space "
        "does set to Short clips start over, long ones pause.",
    "Scrub with the mouse": "Hover scrub: with a video in the preview, the "
        "mouse's place across the picture shows that moment of the clip - left edge the start, right edge "
        "the end. Only the picture changes: where it plays stays put, and it carries on when the mouse "
        "leaves. Click to play from the moment you're looking at.",
    "Trim silence when inserting sounds": "A sound effect that starts with half a "
        "second of nothing lands late. With this on, inserting a sound skips the silence before it and "
        "after it (a few milliseconds are kept so nothing is cut off). Marked in/out always wins.",
    # -- General: no-prefix view
    "Media Pool clips": "Show your Media Pool clips when nothing (no prefix) is typed, on this page.",
    "Search keywords, comments and clip colours":
        "Also finds clips by the keywords, comments, description and clip colour set in Resolve's "
        "Metadata panel - typing 'whoosh dark' finds a clip tagged whoosh and dark whatever its file "
        "name. Press Ctrl+R after changing tags in Resolve. Off makes rescans of very big Media Pools faster.",
    "Show clip colours":
        "The clip colour set in Resolve (right-click a clip \u203a Clip Color) as a small dot before the bin "
        "name. Press Ctrl+R after changing colours in Resolve.",
    "Check for updates":
        "Asks alnor.store once a day, and when About opens. Nothing else is sent. "
        "A dot on Settings in the picker's bottom bar means there is a newer Clipse.",
    "Send crash reports":
        "When Clipse crashes, its log of that run goes to alnor.store the next time it starts, so the crash can be "
        "fixed. The log has clip names in it; your home folder's name is left out, and your settings stay here. "
        "Shutting down the computer isn't a crash.",
    "Esc clears the search first":
        "On: when something is typed in the search, Esc first empties it, and the next Esc closes.",
    "Close the picker when you click outside it":
        "Off: the picker stays open while you click around in Resolve - press the Search key or click "
        "it to type again. On: clicking anywhere else closes it.",
    "Type where the mouse is":
        "After clicking in Resolve (the Media Pool, the timeline), move the mouse back onto the picker - or "
        "Settings, Insert as, History, the preview - and after a moment it takes the keyboard again, "
        "so you can type straight away. Not while a mouse button is held (dragging in Resolve). On Wayland "
        "your window manager decides about focus.",
    "Stay above Resolve only":
        "On: the picker, its preview and Settings stay above Resolve, but when you switch to another app "
        "they step back like normal windows (and stay on Resolve's desktop/Space). Off: they float above "
        "everything, on every Space. (macOS and Windows; on Linux your window manager decides.)",
    "Open where it was last moved":
        "Drag the picker by any empty spot (the bottom bar, the edges) to put it where you like; it opens "
        "there again next time. Off: it always opens in the middle of the screen. (On Wayland the window "
        "manager decides where windows go - use a window rule.)",
    "Esc closes the preview too":
        "On: one Esc closes everything. Off: the first Esc closes the preview window, the next one "
        "closes the picker.",
    # -- General: listen
    "Volume": "How loud sounds play when you listen to them in the picker.",
    "Preview window": "Next to it: the window grows by the preview. In its space: the window stays, the list makes "
                      "room and has it back when the preview closes. The gap between them is the slider (0: one card, "
                      "a line between); drag the line in the picker to change their widths. A window of its own: "
                      "a normal window you can drag anywhere - another screen, a corner - and it opens there again "
                      "next time. (On Wayland, where apps can't place their own windows, use a window rule for the "
                      "title \"Clipse preview\".)",
    "Open the preview with the picker":
        "On: the preview is there every time the picker opens, showing the highlighted clip - no need to "
        "press the preview key first. They close together as always. The first clip waits on its first "
        "frame, so the picker never opens with sound; it plays as soon as you move to a clip or press play. "
        "Also in the preview's options (the three dots).",
    "Autoplay":
        "On: a video starts playing as soon as it shows in the preview window. Off: it waits on the "
        "first frame until you press play (Ctrl+Space by default). Also in the preview's bottom bar.",
    "Loop":
        "On: the preview starts over when the clip ends. Off: it plays once and stops on the last frame. "
        "Also in the preview's bottom bar.",
    "Guess energy": "Songs you haven't given an energy show Clipse's guess, from their tempo, how much happens in them, "
                    "how bright and how punchy they are - after Analyse sounds. The bars are outlined, so a guess "
                    "can't be taken for your own. Searching e1, e2 or e3 finds guesses too.",
    "Show BPM on music": "The tempo of each music clip, small after its name (128 BPM) - after "
                                   "Analyse sounds. Search it too: m: 120, m: calm, m: a minor.",
    "Show clip info under the preview": "The details of the highlighted clip under the preview picture. Also "
                                        "Info in the preview's bottom bar, or Ctrl+D. Right-click the info "
                                        "to choose its lines.",
    "Analyse new sounds automatically":
        "Off (recommended): sounds are only analysed when you press Analyse sounds, so opening the picker "
        "never does extra work. On: sounds that are new since last time are analysed in the background "
        "each time the picker opens.",
    "Music is at least": "Audio shorter than this counts as a sound effect, unless its name, bin or keywords "
                         "say it's music.",
    "Put it on the timeline":
        "Grab Frame always adds the frame to the \"frame_grabs\" bin (in the \"clipse\" bin). On: it also goes on "
        "the timeline at the playhead, on the first free track - a freeze frame.",
    "Command": "Leave empty to use your system's file manager. Or type the program to use, "
                            "e.g. thunar, nautilus, dolphin --select {file} or explorer - {folder} and {file} "
                            "are filled in (with neither, the folder is added at the end).",
    "Sort results by": "Best match: the closest name first (an exact name always wins). Most used "
                               "first: what you insert most, then best match. Name: A to Z.",
    "With nothing typed": "Recently added: what came into the Media Pool last. Recently used: what you inserted "
                          "last. Most used first: what you insert most.",
    "Layout": "How Tidy Fusion Nodes lines up the node editor. Lines: each line of nodes left to "
                     "right, what joins it right above the node it goes into (masks right below). Top to bottom: "
                     "the same, running down, with what joins beside it. MediaOut stays where it is; notes, "
                     "underlays and the inside of a group are left alone.",
    "Tidy up after every insert": "After each node, macro or clip the picker puts into a composition, the node "
        "editor is tidied the same way - mostly it's just the new node that goes into place. Undo takes it back "
        "together with the insert.",
    "Spoken language": "The language Resolve listens for when it writes subtitles from the speech (> subtitles). "
        "Work it out from the speech is fine for one language; choose it yourself when Resolve guesses wrong.",
    "Lines on screen": "One line at a time: short subtitles that change often - good for vertical videos. "
        "Two lines: fewer, longer subtitles, the way films show them.",
    "Longest line": "How many characters a line may have before the subtitle is split. Lower means shorter "
        "subtitles that change more often (42 is the usual; about 20 suits vertical videos).",
    "Gap between subtitles": "Frames left empty between one subtitle and the next, so they don't run into each other.",
    "Made for": "Resolve's own rules for timing and length. Normal suits most videos; Teletext and Netflix follow "
        "those broadcasters' rules (shorter lines, stricter timing).",
    "Default title": "What title: in the picker adds (type title: then your text, Enter). Text+ by default, "
                    "or the exact name of one of your own saved titles from the Effects library - the text "
                    "goes into its first Text+.",
    # -- General: adjustment clip
    "Clip name": "Exact name of the adjustment clip in your Media Pool that the Adjustment "
                            "Clip scripts place. It can be in any bin. Left as \"adjustment_clip\", a project "
                            "that has none gets one by itself (in the \"clipse\" bin) - nothing to set up. "
                            "Put the name of your own here to use that one instead.",
    "Clip length": "How long Adjustment Clip at Playhead makes it - and the other two when there's no clip under "
                   "the playhead to match.",
    "Composition name": "Exact name of the empty Fusion composition in your Media Pool that the Fusion "
                          "Composition scripts place. It can be in any bin. Left as \"fusion_composition\", any "
                          "Fusion composition in the Media Pool will do - and a project that has none gets one by "
                          "itself (in the \"clipse\" bin). Put the name of your own here to use that one.",
    "Composition length": "How long Fusion Composition at Playhead makes it - and the other two when there's no "
                          "clip under the playhead to match.",
    # -- Appearance
    "Font": "Font used in the picker. Leave as is for the system font.",
    "Font size": "Text size in the picker. Press Enter to apply.",
    "Scale": "Scales everything in the picker up or down (e.g. 1.25 for high-resolution screens).",
    "Keep staged clips when the picker closes":
        "On: clips you staged with Tab stay staged when you close the picker (Esc or the open key), so you "
        "can check the timeline and come back. They're cleared once inserted.",
}

# The Actions panel: what each action does - said when the mouse rests on its tile (an Insert as preset says
# what it does by itself: presets.summary)
# what a sound's energy means (Tags' E1, E2, E3 under the mouse): how much of the viewer's attention the music takes
ENERGY_LEVELS = {
    1: "Calm: it stays in the background. You'd hardly notice it under someone talking.",
    2: "Moving: it has drive and you notice it, but a voice still leads over it.",
    3: "Intense: it takes over. It's hard to talk over, so it's for moments the music carries.",
}

ACTIONS = {
    "Restart Clipse": "Stops Clipse and starts it again.",
    "Quit Clipse": "Stops Clipse until a Resolve key or Resolve itself starts it again.",
    "Picture only": "Inserts the picture without its sound.",
    "Sound only": "Inserts the sound without its picture.",
    "As compound clip": "Inserts the clips, then puts them together in one compound clip.",
    "Grab frame": "Saves the frame under the playhead as a still and puts it on the timeline.",
    "Record voiceover": "Records your microphone and puts the take on the timeline at the playhead.",
    "Undo Clipse\u2019s last step": "Takes back the last thing Clipse did.",
    "Favourite": "Stars the clip. Favourites come first.",
    "Show in Media Pool": "Selects the clip in its bin.",
    "Show in file manager": "Opens the folder the file is in.",
    "Swap clip": "Puts another clip in place of the one under the playhead.",
    "Sounds like this": "Finds the sounds that sound like this one.",
    "Tags": "Sets this sound's energy and tags while you listen. They're kept in the file.",
    "Relink missing clips": "Finds this project's offline clips near where they were and points them at their files.",
    "Mark the beats": "A marker on every beat of the song on the timeline.",
    "Mark the bars": "A marker on every bar of the song on the timeline, counting four beats to a bar.",
    "Next use of clip": "Jumps to the next place this clip is used.",
    "Previous use of clip": "Jumps to the previous place this clip is used.",
    "Adjustment clip over clip": "An adjustment clip over the clip under the playhead.",
    "Adjustment clip over footage": "An adjustment clip over the footage under the playhead, past other adjustment clips.",
    "Adjustment clip at playhead": "An adjustment clip at the playhead.",
    "Fusion composition over clip": "An empty Fusion composition over the clip under the playhead.",
    "Fusion composition over footage": "An empty Fusion composition over the footage under the playhead.",
    "Fusion composition at playhead": "An empty Fusion composition at the playhead.",
    "Switch timeline\u2026": "Opens another timeline.",
    "Remove empty tracks": "Removes every track with nothing on it.",
    "Copy markers": "Copies the markers' times and notes as text, to paste into ChatGPT or a script.",
    "Copy timeline": "Copies every clip, marker and what's said on this timeline as text with times, to paste into "
                     "a chat assistant.",
    "Copy project": "Copies the whole project as text with times: its settings, the Media Pool, and every "
                    "timeline's clips, markers and what's said.",
    "Copy transcript": "Copies what's said, with times, from the subtitles (Timeline \u203a Create Subtitles from Audio "
                       "in Resolve makes them). They can stay switched off.",
    "Render\u2026": "Renders the timeline with one of your presets.",
    "Switch project\u2026": "Opens another project.",
    "Project templates\u2026": "Sets this project up from a template.",
    "Project check-up": "Finds missing files, duplicates and clipping sounds.",
    "Organise project": "Puts loose clips in the template's bins and colours clips by what they are.",
    "Add marker": "Places a marker at the playhead and asks what it's for - or opens the one there.",
    "Hide - show markers": "Takes every marker off the timeline and keeps them; again puts them back.",
    "Stretch marker to clips": "Stretches the marker at the playhead over the selected clips (or the clip under the "
                           "playhead).",
    "Tidy up nodes": "Lines the nodes up in clean rows.",
    "Pull node out": "Takes the selected node out of its chain.",
    "Node off / on": "Switches the selected node off or on.",
    "Before / after": "Switches every effect off to see the clip as it came in, and back on.",
    "Step back": "Moves the playhead a few frames back.",
    "Step forward": "Moves the playhead a few frames forward.",
    "Copy node name": "Copies the selected node's name, for an expression.",
    "Animate\u2026": "Ready-made moves in and out for the selected node.",
}

SHORT = {
    # the grey line under a setting's name - one line, only what its name doesn't say ("": none)
    "Open where it was last moved": "",
    "Analyse new sounds automatically": "",
    "Put it on the timeline": "At the playhead, on the first free track.",
    "Composition name": "",
    "Show clip colours": "As a dot before the bin.",
    "Clip name": "",
    "Centre the view after tidying": "The zoom stays.",
    "Sound while scrubbing": "",
    "Spoken language": "What Resolve listens for.",
    "Lines on screen": "One short line, or two like in films.",
    "Longest line": "Shorter lines: subtitles change more often.",
    "Gap between subtitles": "Empty frames between one and the next.",
    "Made for": "Resolve's rules for timing and length.",
    "Open the preview with the picker": "",
    "Short clips are under": "",
    "Search keywords, comments and clip colours": "",
    "Keep staged clips when the picker closes": "",
    "Stay above Resolve only": "Not above your other apps.",
    "Type where the mouse is": "No click needed.",
    "Scrub with the mouse": "",
    "Show timecode": "01:00:12:14 instead of 0:12.",
    "Corners": "",
    "Bin name at the right edge": "",
    "Include sub-bins": "Inserting a bin also inserts the bins inside it.",
    "Show inserted clips in the Media Pool": "",
    "Insert the highlighted row with staged clips": "",
    "Close the picker when you click outside it": "",
    "Esc clears the search first": "",
    "Esc closes the preview too": "",
    "Start when you log in": "So the picker opens instantly.",
    "Sort results by": "",
    "With nothing typed": "",
    "Font": "",
    "Font size": "",
    "Scale": "",
    "Check for updates": "Once a day, from alnor.store.",
    "Send crash reports": "",
    "Autoplay": "",
    "Loop": "",
    "Space plays": "",
    "What Space does": "",
    "Volume": "",
    "Show clip info under the preview": "",
    "Show BPM on music": "After Analyse sounds.",
    "Guess energy": "Outlined bars on songs you haven't rated.",
    "Trim silence when inserting sounds": "",
    "Music is at least": "Shorter sounds are sound effects, unless named or tagged as music.",
    "Default title": "What title: adds in the picker.",
    "Tidy up after every insert": "",
    "Ask before adding a node for an expression": "When nothing is selected.",
    "Saved in": "A folder for each project inside it.",
    "Clip length": "",
    "Composition length": "",
    "Layout": "",
    "Command": "",
    # Settings > Scripts: each script of Clipse's, by its name in Resolve's menu
    "Swap Clip": "Puts another clip in place of the one under the playhead.",
    "Undo Last Action": "Takes back the last thing Clipse did.",
    "Grab Frame": "Saves the frame under the playhead as a still.",
    "Record Voiceover": "Records your microphone and puts the take on the timeline. Press it again to stop.",
    "Organise Project": "Puts loose clips in the template's bins and colours clips by what they are.",
    "Add Marker": "Places a marker at the playhead and asks what it's for - or opens the one there.",
    "Hide - Show Markers": "Takes every marker off the timeline and keeps them; again puts them back.",
    "Stretch Marker to Clips": "Stretches the marker at the playhead over the selected clips, or the clip under the "
                           "playhead.",
    "Microphone": "",
    "Start": "",
    "Mute the timeline": "",
    "Trim silence": "At the start and end.",
    "Next Use of Clip": "Jumps to the next place this clip is used.",
    "Previous Use of Clip": "Jumps to the previous place this clip is used.",
    "Adjustment Clip Over Clip": "An adjustment clip over the clip under the playhead, as long as it.",
    "Adjustment Clip Over Footage": "An adjustment clip over the footage under the playhead, past other adjustment clips.",
    "Adjustment Clip at Playhead": "An adjustment clip at the playhead.",
    "Fusion Composition Over Clip": "An empty Fusion composition over the clip under the playhead, as long as it.",
    "Fusion Composition Over Footage": "An empty Fusion composition over the footage under the playhead.",
    "Fusion Composition at Playhead": "An empty Fusion composition at the playhead.",
    "Step Back": "Moves the playhead back.",
    "Step Forward": "Moves the playhead forward.",
    "Tidy Fusion Nodes": "Lines the nodes up in clean rows.",
    "Pull Out Fusion Node": "Takes the selected node out of its chain.",
    "Copy Node Name": "Copies the selected node's name, for an expression.",
    "Fusion Node Off - On": "Switches the selected node off or on.",
    "Fusion Before - After": "Every effect off to see the clip as it came in, and back on.",
    "Open": "Opens the picker.",
    "Restart": "Stops Clipse and starts it again.",
    "Quit": "Stops Clipse until a Resolve key or Resolve itself starts it again.",
    "Back by": "",
    "Forward by": "",
}

_COLOR_HELP = "Click the swatch to pick a colour."
_ICON_HELP = ("The symbol in the tag for this kind of row. Leave it empty to use the built-in symbol, "
              "or type any character or emoji to use that instead.")


def _tip(text, resettable=True):
    return text  # (how to reset - double-click the name, the arrow in a field - isn't said: people know)


def _field_widgets(item):
    if item is None:
        return []
    if item.widget() is not None:
        return [item.widget()]
    layout = item.layout()
    if layout is None:
        return []
    return [layout.itemAt(i).widget() for i in range(layout.count()) if layout.itemAt(i).widget()]


def apply_help(root: QWidget):
    # Rows in form layouts: tooltip on the label and on its field(s)
    for form in root.findChildren(QFormLayout):
        for row in range(form.rowCount()):
            label_item = form.itemAt(row, QFormLayout.LabelRole)
            field_item = form.itemAt(row, QFormLayout.FieldRole)
            label = label_item.widget() if label_item else None
            if not isinstance(label, QLabel):
                continue
            text = label.text().strip()
            fields = _field_widgets(field_item)
            kinds = ["QKeySequenceEdit" if type(w).__name__ in ("KeyEdit", "KeyField") else type(w).__name__
                     for w in fields]
            if text in HELP:
                tip = _tip(HELP[text])
            elif "ColorSwatchButton" in kinds:
                tip = _tip(f"{text} colour. {_COLOR_HELP}")
            elif "QLineEdit" in kinds and "QKeySequenceEdit" in kinds:  # Search Prefixes tab
                tip = _tip(f"Prefixes that search only {text.lower()} - type one followed by a colon, "
                           f"e.g. 'a:'. Separate several with commas.\n"
                           f"Right box (optional): a key that jumps straight to this search; press it "
                           f"again to go back.")
            elif kinds.count("QKeySequenceEdit") == 2:  # Keybindings tab
                tip = _tip(f"Key for: {text}.\nClick a box and press the new key (the x on the right clears it). Left = main key, "
                           f"right = optional second key. Only active while the picker is open.")
            else:
                continue
            label.setToolTip(tip)
            for w in _field_widgets(field_item):
                w.setToolTip(tip)
    # Checkboxes that are their own label
    for cb in root.findChildren(QCheckBox):
        text = cb.text().strip()
        if text in HELP:
            cb.setToolTip(_tip(HELP[text], resettable=type(cb).__name__ == "ResettableCheckBox"))
    # Icon fields (label + small text box side by side, not in a form)
    for label in root.findChildren(QLabel):
        if type(label).__name__ == "ResettableLabel" and not label.toolTip().startswith(
                tuple(v[:20] for v in HELP.values())):
            parent_box = label.parentWidget()
            if parent_box is not None and "icons" in getattr(parent_box, "title", lambda: "")().lower():
                label.setToolTip(_tip(_ICON_HELP))
