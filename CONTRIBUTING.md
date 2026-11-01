# Contributing

Bug reports and pull requests are welcome.

Clipse is maintained on Linux. Mac and Windows fixes are welcome, but they can't be tested by the maintainer, so please say how you tried yours.

## Run from source

```sh
git clone https://github.com/alnor0/clipse
cd clipse
python3 -m venv .venv
.venv/bin/pip install -e ".[preview]"
.venv/bin/clipse --open
```

## Tests

Most tests run against a stand-in for Resolve, so Resolve doesn't need to be open. `ffmpeg` and `luajit` are needed for some of them.

```sh
.venv/bin/python tests/test_commands.py     # actions and search order
.venv/bin/python tests/test_insert_as.py    # inserting and presets
.venv/bin/python tests/test_preview.py      # the preview
.venv/bin/python tests/test_sound_tags.py   # tags, energy and beats
.venv/bin/python tests/test_speed.py        # after touching search or the list
```

A key press has to stay within one frame (16 ms), which `test_speed.py` checks.

## Keeping it simple

- Clipse only talks to Resolve through its scripting API. No fake key presses or clicking its interface.
- Before adding a setting, ask whether people would really disagree about it.
- Wording stays short and plain, and doesn't explain what's already obvious.

The code is under GPL-3.0. The pictures and videos in `docs/` only show how Clipse looks.
