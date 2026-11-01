<div align="center">
  <img src="clipse/data/icon.png" width="84" alt="">
  <h1>Clipse</h1>
  <p>A quick search for DaVinci Resolve Studio.</p>
  <p>
    <a href="#install">Install</a> &nbsp;·&nbsp;
    <a href="docs/guide.md">Guide</a> &nbsp;·&nbsp;
    <a href="https://github.com/alnor0/clipse/releases">Releases</a>
  </p>
  <img src="docs/media/overview.webp" alt="Clipse open over DaVinci Resolve">
</div>

<br>

Type a few letters, press <kbd>Enter</kbd> and it's on your timeline. Clipse finds your clips, sounds, markers, scripts, macros and Fusion nodes, plays them before you insert them, and lets you decide how they land.

## Install

```sh
curl -fsSL https://downloads.alnor.store/install.sh | sh
```

Clipse needs DaVinci Resolve Studio, with Preferences › System › General › External scripting using set to Local. Then open it from Workspace › Scripts › !Clipse › Clipse - Open, and give it a key in Resolve's Keyboard Customization.

It's made and tested on Linux. [Mac and Windows builds](https://github.com/alnor0/clipse/releases) are made automatically and aren't tested, so they may not work.

## What it does

<details>
<summary><b>Find anything fast.</b> Search everything, or start with a prefix for only scripts, markers or sounds.</summary>
<br>

<kbd>Tab</kbd> picks a few at once, and <kbd>Ctrl</kbd>+<kbd>Tab</kbd> picks the same one twice.

<img src="docs/media/search.webp" alt="Searching for clips, sounds and scripts">

</details>

<details>
<summary><b>See and hear it first.</b> Every clip plays right next to the list.</summary>
<br>

<kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>P</kbd> opens the preview, and with <kbd>Ctrl</kbd>+<kbd>P</kbd> every sound you move to plays by itself. Scrub, loop, and mark in and out before it goes anywhere.

<img src="docs/media/preview.webp" alt="Previewing a video and sounds">

</details>

<details>
<summary><b>Every useful tool in one place.</b> Find what you'd dig through menus for by typing its name.</summary>
<br>

<kbd>Ctrl</kbd>+<kbd>K</kbd> shows them all, and every script can have its own key in Resolve.

<img src="docs/media/actions.webp" alt="The Actions panel">

</details>

<details>
<summary><b>Choose how clips are inserted.</b> One after another, spaced out or on every marker.</summary>
<br>

<kbd>Ctrl</kbd>+<kbd>I</kbd> sets lengths and where pictures sit in the frame, and shows it on a drawing of your timeline first.

<img src="docs/media/insert_as.webp" alt="Insert as, with a drawing of the timeline">

</details>

<details>
<summary><b>Fusion expressions.</b> Ready-made expressions and a cheat sheet, right next to your node.</summary>
<br>

<img src="docs/media/fusion.webp" alt="Fusion expressions">

</details>

<details>
<summary><b>Swap a clip.</b> Click a clip in Resolve and pick the new one. Same spot, same length.</summary>
<br>

<img src="docs/media/swap.webp" alt="Swapping a clip on the timeline">

</details>

<details>
<summary><b>Sounds like this.</b> Found a sound you like? Get the ones that sound like it.</summary>
<br>

<kbd>Ctrl</kbd>+<kbd>L</kbd> finds them.

<img src="docs/media/sounds_like_this.webp" alt="Finding sounds that sound alike">

</details>

<details>
<summary><b>History.</b> Every insert is kept, and an old one comes back set up the same way.</summary>
<br>

<img src="docs/media/history.webp" alt="History of inserts">

</details>

<details>
<summary><b>Make it yours.</b> Pick a theme, drag it to any size, and see what every option does.</summary>
<br>

<img src="docs/media/themes.webp" alt="Changing themes">

<img src="docs/media/settings.webp" alt="Settings">

</details>

## Why I made it

Searching is faster than looking. It's how I get around my computer, with [Vicinae](https://vicinae.com), and DaVinci Resolve didn't have it. So I added it.

Most editors know the names of the sound effects, nodes and macros they use, or at least some part of the name. The slow part is finding them: the right folder, then the right file among hundreds. With Clipse you type what you're after, and it's there.

## More

- [Guide](docs/guide.md): setting up, keys and common questions
- [Contributing](CONTRIBUTING.md): running it from source

**Privacy:** Clipse checks alnor.store for updates and sends crash logs there, which hold clip names. Both can be turned off in Settings › About. Nothing else leaves your computer unless you send feedback.

**License:** [GPL-3.0](LICENSE). Clipse is an independent tool, not affiliated with Blackmagic Design.
