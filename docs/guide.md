# Clipse guide

## Set up

1. Install Clipse: see the [README](../README.md#install).
2. In Resolve: Preferences › System › General › External scripting using: Local. Restart Resolve.
3. Workspace › Scripts › !Clipse › Clipse - Open opens the picker.
4. Give it a key in Resolve's Keyboard Customization. Search for "Clipse" to find every script that comes with it.

## Find and insert

- Type to search the Media Pool, your macros, nodes, scripts and more. <kbd>Enter</kbd> inserts at the playhead.
- <kbd>Tab</kbd> stages a clip, so several go in at once. <kbd>Ctrl</kbd>+<kbd>Tab</kbd> stages it once more. <kbd>Alt</kbd>+<kbd>Enter</kbd> puts them in as one compound clip.
- Type `:` to pick what to search, like Videos or Scripts.
- <kbd>Ctrl</kbd>+<kbd>I</kbd> opens Insert as: back to back, at every marker or cut, with gaps, and where pictures sit in the frame.
- <kbd>Ctrl</kbd>+<kbd>Enter</kbd> puts clips one after another, <kbd>Alt</kbd>+<kbd>M</kbd> one on every marker.
- <kbd>Ctrl</kbd>+<kbd>K</kbd> opens the Actions: all 23 of the scripts that come with Clipse, and more. <kbd>Ctrl</kbd>+<kbd>H</kbd> opens History, to insert the same thing again.

## Preview

- <kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>P</kbd> opens the preview. <kbd>Ctrl</kbd>+<kbd>Space</kbd> plays, the arrows scrub.
- <kbd>Alt</kbd>+<kbd>I</kbd> and <kbd>Alt</kbd>+<kbd>O</kbd> mark in and out. Only that part goes in.
- <kbd>Ctrl</kbd>+<kbd>L</kbd> finds sounds that sound like the one you're on.

## Sounds and music

- <kbd>Alt</kbd>+<kbd>T</kbd> tags the sound you're on, and <kbd>Alt</kbd>+<kbd>1</kbd>, <kbd>Alt</kbd>+<kbd>2</kbd> and <kbd>Alt</kbd>+<kbd>3</kbd> set its energy, while it plays. Tags are kept in the file (.wav, .mp3, .flac and .mov).
- Type a tag to find its sounds, or `e2` for that energy.
- In Actions, **Mark the beats** and **Mark the bars** put a marker on every beat or bar of the song on the timeline. Bars count four beats.
- **Relink missing clips** in Actions finds offline clips near where they were and points them at their files.

## Make it yours

Settings (<kbd>Ctrl</kbd>+<kbd>,</kbd>) has the themes, the font size and every key of the picker. Drag the picker's edges to size it, and the line between the list and the preview to give either more room. <kbd>Ctrl</kbd> with <kbd>+</kbd> or <kbd>-</kbd> makes everything in it larger or smaller.

On a Mac, <kbd>Ctrl</kbd> is <kbd>Cmd</kbd>.

## Questions

**Is it really free?**
Yes. No trial, no key, no account. The code is here, under the GPL-3.0 license.

**Does it work with the free version of DaVinci Resolve?**
No, you need DaVinci Resolve Studio. The free version doesn't let other apps talk to it.

**Which systems does it run on?**
It's made and tested on Linux. There are Mac (Apple silicon) and Windows versions too, but they aren't tested and may not work.

**Does it need the internet?**
No. It only uses it to check for updates and send crash logs, and you can turn both off in Settings › About.

**Can it mess up my timeline?**
It only adds what you insert. **Undo Clipse's last step** takes back what the app did, and nothing you did yourself.

**Can I give its scripts keyboard shortcuts?**
Yes. They're in Resolve's Workspace › Scripts menu, so you set their shortcuts in Resolve's Keyboard Customization, like any other command.

## If something's wrong

Use Settings › About › Send feedback, or [open an issue](https://github.com/alnor0/clipse/issues).
