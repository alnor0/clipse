<div align="center">
  <img src="clipse/data/icon.png" width="84" alt="">
  <h1>Clipse</h1>
  <p>A quick search for DaVinci Resolve Studio.</p>
  <p>
    <a href="#install">Install</a> &nbsp;·&nbsp;
    <a href="docs/guide.md">Guide</a> &nbsp;·&nbsp;
    <a href="https://github.com/alnor0/clipse/releases">Releases</a>
  </p>
</div>

https://github.com/user-attachments/assets/36e35f2f-a0fb-41dd-92a2-e0464f6408cd

<br>

Find it, drop it in, keep editing. Type a few letters, press <kbd>Enter</kbd> and it's on your timeline. Clipse finds your clips, sounds, markers, scripts, macros and Fusion nodes, plays them before you insert them, and lets you decide how they land.

Free, with no trial, no key and no account.

## Install

```sh
curl -fsSL https://downloads.alnor.store/install.sh | sh
```

Clipse needs DaVinci Resolve Studio, with Preferences › System › General › External scripting using set to Local. Then open it from Workspace › Scripts › !Clipse › Clipse - Open, and give it a key in Resolve's Keyboard Customization.

It's made and tested on Linux. [Mac and Windows builds](https://github.com/alnor0/clipse/releases) are made automatically and aren't tested, so they may not work.

## What it does

<details>
<summary><b>Find anything fast.</b> Start with a prefix to search only scripts, markers or sounds.</summary>
<br>

Type a few letters, press <kbd>Enter</kbd> and it's on your timeline. Start with a prefix to search only scripts, markers or sounds. <kbd>Tab</kbd> picks a few at once, and <kbd>Ctrl</kbd>+<kbd>Tab</kbd> picks the same one twice.

**Edit page**

https://github.com/user-attachments/assets/945a2c2b-0486-4f40-82d9-14d9b8367030

**Fusion page**

https://github.com/user-attachments/assets/464f7dce-a579-486b-89e7-10ca209ee0eb

</details>

<details>
<summary><b>See and hear it first.</b> Every clip plays right next to the list, sound and all.</summary>
<br>

Every clip plays right next to the list, sound and all, with <kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>P</kbd>. With <kbd>Ctrl</kbd>+<kbd>P</kbd> every sound you move to plays by itself. Scrub through it, loop it, and mark in and out before it goes anywhere.

https://github.com/user-attachments/assets/6ac12cb8-9bc0-4740-8345-0f605c0bcb08

</details>

<details>
<summary><b>Every useful tool in one place.</b> All 23 of my scripts are included.</summary>
<br>

Adjustment clips, markers, grabbing a frame, swapping a clip. All the things you would normally dig through menus for, you find by typing their name. <kbd>Ctrl</kbd>+<kbd>K</kbd> shows them all, and on the Fusion page the Fusion ones.

**All 23** of my scripts come with it, every one of them included in the app, and bindable through Keyboard Customization.

**Edit page**

https://github.com/user-attachments/assets/ace84bb6-4324-4471-9756-358eff01b52e

**Fusion page**

https://github.com/user-attachments/assets/590fcf5d-0cc5-4d5b-bbf2-8406987554d0

</details>

<details>
<summary><b>Choose how clips are inserted.</b> At the playhead, one after another, spaced out or on every marker.</summary>
<br>

At the playhead, one after another, spaced out or on every marker. <kbd>Ctrl</kbd>+<kbd>I</kbd> sets lengths and where pictures sit in the frame, and shows it on a drawing of your timeline first. <kbd>Ctrl</kbd>+<kbd>Enter</kbd> puts clips one after another, <kbd>Alt</kbd>+<kbd>M</kbd> one on every marker.

https://github.com/user-attachments/assets/e85d4c1a-a7e3-47a3-a571-1c6cec33f963

</details>

<details>
<summary><b>Sounds like this.</b> Found a sound you like? Get the ones that sound like it.</summary>
<br>

Found a sound you like? <kbd>Ctrl</kbd>+<kbd>L</kbd> gets the ones that sound like it.

https://github.com/user-attachments/assets/25714ec7-3ce5-4215-a91d-018fd87f0829

</details>

<details>
<summary><b>Fusion expressions.</b> Ready-made expressions and a cheat sheet, right next to your node.</summary>
<br>

https://github.com/user-attachments/assets/e12f5dfb-cb44-48b8-bac3-98c8fb44d8db

</details>

<details>
<summary><b>Swap a clip.</b> Click a clip in Resolve, pick the new one. Same spot, same length.</summary>
<br>

https://github.com/user-attachments/assets/76f2217f-76e9-4ae5-bf31-1d9b1538b2a4

</details>

<details>
<summary><b>History.</b> Every insert is kept. Pick an old one and its clips come back, set up the same way.</summary>
<br>

https://github.com/user-attachments/assets/42437d11-9e78-466d-9f98-b98a5e615d87

</details>

<details>
<summary><b>Settings you can see.</b> Every option shows you what it does. No guessing.</summary>
<br>

https://github.com/user-attachments/assets/a6fab63b-04d3-4dfd-b1e7-17ba5b7c03ff

</details>

<details>
<summary><b>Change how it looks.</b> Pick a theme, and drag it to the size you want.</summary>
<br>

Pick a theme. Drag the edges to make it bigger, and drag the line between the list and the preview to give either one more room. <kbd>Ctrl</kbd> with <kbd>+</kbd> or <kbd>-</kbd> makes everything in it larger or smaller.

https://github.com/user-attachments/assets/14a27aed-6505-406a-a086-f20bd6a9fb5c

</details>

**Also in it:** tag sounds and rate their energy while you listen, switch a song's stems on and off, put markers on a song's beats, relink missing clips, organise a project's bins and clip colours, and record a voiceover. The [guide](docs/guide.md) has how.

## Why I made it

Searching is faster than looking. It's how I get around my computer, with [Vicinae](https://vicinae.com) (Linux) or [Raycast](https://www.raycast.com) (Mac and Windows), and DaVinci Resolve didn't have it. So I added it.

Most editors know the names of the sound effects, nodes and macros they use, me included. Or at least some part of the name. The slow part is finding them: the right folder, then the right file among hundreds. That takes too long, and honestly, it's boring.

With Clipse you type what you're after, from the Media Pool or anywhere else, and it's there. It's an add-on to Resolve, but it doesn't feel like one. It fits right in, it's responsive, and it's satisfying to use.

The source code is free, so you can do what you want with it. Use it, change it, build on it. And if you can see a way to make Clipse better, I'd love to hear it: [suggest an improvement](https://github.com/alnor0/clipse/issues/new) or send a pull request.

## More

- [Guide](docs/guide.md): setting up, keys and common questions
- [Contributing](CONTRIBUTING.md): running it from source

**Privacy:** Clipse checks alnor.store for updates and sends crash logs there, which hold clip names. Both can be turned off in Settings › About. Nothing else leaves your computer unless you send feedback.

**License:** [GPL-3.0](LICENSE). Clipse is an independent tool, not affiliated with Blackmagic Design.
