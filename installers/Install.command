#!/bin/bash
# Clipse installer for macOS - double-click it.
# Installs into its own folder (~/.clipse/app) using Python from
# python.org. Nothing else on the Mac is changed.
cd "$(dirname "$0")" || exit 1
[ -f pyproject.toml ] || cd ..   # run straight from the project folder, not the download
fail() { echo; echo "Something went wrong: $1"; read -rp "Press Enter to close..."; exit 1; }

APP="$HOME/.clipse/app"   # the app's own Python environment
BIN="$HOME/.local/bin"             # clipse / -daemon commands
OLD_CLIENT="$BIN/clipse"

echo "== Installing Clipse =="

# Resolve on macOS only runs scripts with Python from python.org
# (Homebrew's or Apple's Python isn't found by Resolve).
PY=""
for v in $(ls -d /Library/Frameworks/Python.framework/Versions/3.* 2>/dev/null | grep -v "t$" | sort -t. -k3 -n -r); do
    if "$v/bin/python3" -c 'import sys; sys.exit(sys.version_info < (3, 9))' 2>/dev/null; then
        PY="$v/bin/python3"; break
    fi
done
if [ -z "$PY" ]; then
    echo "DaVinci Resolve needs Python from python.org to run scripts."
    echo "Opening python.org - download and install the latest Python 3,"
    echo "then double-click Install.command again."
    open "https://www.python.org/downloads/macos/"
    read -rp "Press Enter to close..."; exit 1
fi
echo "Using $PY"

# Stop a running copy first, and remove one an older version installed with pipx
# (--shutdown also stops the login helper; versions before 1.31 only know --stop)
for c in "$OLD_CLIENT" "$APP/bin/clipse"; do
    [ -x "$c" ] && { "$c" --shutdown >/dev/null 2>&1 || "$c" --stop >/dev/null 2>&1; }
done
export PIPX_DEFAULT_BACKEND=pip
if command -v pipx >/dev/null 2>&1; then pipx uninstall davinci-search >/dev/null 2>&1
else "$PY" -m pipx uninstall davinci-search >/dev/null 2>&1; fi

echo "Installing the app (the first time downloads about 140 MB - give it a minute)..."
"$PY" -m venv --clear "$APP" || fail "couldn't create the app's Python environment"
PIP=("$APP/bin/python" -m pip --disable-pip-version-check)
"${PIP[@]}" install --quiet --upgrade pip >/dev/null 2>&1
"${PIP[@]}" install --quiet ".[macos]" || fail "couldn't install Clipse (see the messages above)"
# Previewing sounds and clips (optional - only from ready-made builds)
for extra in miniaudio av numpy; do
    "${PIP[@]}" install --quiet --only-binary=:all: "$extra" >/dev/null 2>&1 \
        || echo "  (couldn't add $extra - previews or sound analysis may be missing, everything else works)"
done

mkdir -p "$BIN"
for cmd in clipse clipse-daemon; do
    ln -sf "$APP/bin/$cmd" "$BIN/$cmd"
done
"$APP/bin/clipse" --install-resolve-shortcuts || fail "couldn't add the Resolve shortcuts"
# Start in the background at login, so the first open is instant (Settings -> General)
"$APP/bin/clipse" --autostart

echo
echo "Done! Next: restart DaVinci Resolve and give the shortcuts keys in"
echo "DaVinci Resolve -> Keyboard Customization (search for \"Clipse\")."
read -rp "Press Enter to close..."
