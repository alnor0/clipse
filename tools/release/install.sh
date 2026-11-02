#!/bin/sh
# Clipse for Linux: curl -fsSL https://github.com/alnor0/clipse/releases/latest/download/install.sh | sh
# Downloads the app and runs it with --install: it installs itself in ~/.local/share/clipse (no password)
# and sets up Resolve's scripts - a tick for each. Updates and Uninstall are in the app (Settings).
set -eu
URL="https://github.com/alnor0/clipse/releases/latest/download/clipse-linux.AppImage"
printf '\n  \033[1mClipse\033[0m\n\n'
# An AppImage runs through FUSE - Resolve starts the installed one that way too, so it has to be there
has_fuse() { [ -e /dev/fuse ] && { command -v fusermount3 || command -v fusermount; } >/dev/null 2>&1; }
if ! has_fuse; then
  printf '  Clipse needs FUSE. Install the fuse3 package, then run this again:\n'
  printf '    Ubuntu, Debian:  sudo apt install fuse3\n    Fedora, Rocky:   sudo dnf install fuse3\n'
  printf '    Arch:            sudo pacman -S fuse3\n\n'
  exit 1
fi
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
curl -fL --progress-bar -o "$work/clipse.AppImage" "$URL"
chmod +x "$work/clipse.AppImage"
printf '  \033[32m\342\234\223\033[0m Downloaded\n'
"$work/clipse.AppImage" --install
printf '\n  In DaVinci Resolve: Workspace > Scripts > Clipse - Open\n\n'
