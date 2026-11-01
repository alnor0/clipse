#!/usr/bin/env bash
# Clipse installer for Linux - double-click it, or run:  bash install.sh
# Installs into its own folder (~/.clipse/app) using your Python.
# Nothing else on the system is changed (no pipx, no system packages
# beyond the two Qt/Python pieces some distros leave out).
cd "$(dirname "$0")" || exit 1
[ -f pyproject.toml ] || cd ..   # run straight from the project folder, not the download
fail() { echo; echo "Something went wrong: $1"; read -rp "Press Enter to close..."; exit 1; }
has() { command -v "$1" >/dev/null 2>&1; }

pkg_install() {  # pkg_install <apt> <dnf> <pacman> <zypper> - package names per package manager
    if   has apt-get; then sudo apt-get install -y "$1"
    elif has dnf;     then sudo dnf install -y "$2"
    elif has pacman;  then sudo pacman -S --needed --noconfirm "$3"
    elif has zypper;  then sudo zypper install -y "$4"
    else return 1; fi
}

APP="$HOME/.clipse/app"   # the app's own Python environment
BIN="$HOME/.local/bin"             # clipse / -daemon commands
OLD_CLIENT="$BIN/clipse"

echo "== Installing Clipse =="

# Python 3.9 or newer (some distros, e.g. Rocky 8, ship an older python3)
PY=""
for p in python3 python3.13 python3.12 python3.11 python3.10 python3.9; do
    if has "$p" && "$p" -c 'import sys; sys.exit(sys.version_info < (3, 9))' 2>/dev/null; then
        PY="$(command -v "$p")"; break
    fi
done
[ -n "$PY" ] || fail "Python 3.9 or newer is needed - install it with your package manager
(e.g. sudo dnf install python3.11), then run this again."
echo "Using $PY"

# Qt needs libxcb-cursor on X11 desktops (not preinstalled on e.g. Ubuntu/Mint)
if ! ldconfig -p 2>/dev/null | grep -q 'libxcb-cursor\.so\.0'; then
    echo "Installing libxcb-cursor (needed by Qt on X11)..."
    pkg_install libxcb-cursor0 xcb-util-cursor xcb-util-cursor libxcb-cursor0 \
        || echo "  Couldn't install it - if the picker doesn't open, install libxcb-cursor yourself."
fi

# Stop a running copy first, and remove one an older version installed with pipx
# (--shutdown also stops the login helper; versions before 1.31 only know --stop)
for c in "$OLD_CLIENT" "$APP/bin/clipse"; do
    [ -x "$c" ] && { "$c" --shutdown >/dev/null 2>&1 || "$c" --stop >/dev/null 2>&1; }
done
export PIPX_DEFAULT_BACKEND=pip
if has pipx; then pipx uninstall davinci-search >/dev/null 2>&1
else "$PY" -m pipx uninstall davinci-search >/dev/null 2>&1; fi

echo "Installing the app (the first time downloads about 140 MB - give it a minute)..."
if ! "$PY" -m venv --clear "$APP" >/dev/null 2>&1; then
    # Debian / Ubuntu / Mint ship Python's venv module separately
    echo "Installing Python's venv module (you may be asked for your password)..."
    V="$("$PY" -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
    pkg_install "python$V-venv" python3 python python3 || pkg_install python3-venv python3 python python3
    "$PY" -m venv --clear "$APP" || fail "couldn't create the app's Python environment"
fi
PIP=("$APP/bin/python" -m pip --disable-pip-version-check)
"${PIP[@]}" install --quiet --upgrade pip >/dev/null 2>&1
"${PIP[@]}" install --quiet . || fail "couldn't install Clipse (see the messages above)"
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
# Clipse among the apps (the app launcher) - picked, it opens the picker
"$APP/bin/clipse" --app-entry >/dev/null

echo
echo "Done! Next: restart DaVinci Resolve and give the shortcuts keys in"
echo "DaVinci Resolve -> Keyboard Customization (search for \"Clipse\")."
case ":$PATH:" in
    *":$BIN:"*) ;;
    *) echo "(To run clipse in a terminal, add $BIN to your PATH.)" ;;
esac
read -rp "Press Enter to close..."
