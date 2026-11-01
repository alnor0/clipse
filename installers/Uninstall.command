#!/bin/bash
# Clipse uninstaller for macOS - double-click it.
APP="$HOME/.clipse/app"
BIN="$HOME/.local/bin"
CLIENT=""
for c in "$APP/bin/clipse" "$BIN/clipse"; do
    [ -x "$c" ] && { CLIENT="$c"; break; }
done
if [ -n "$CLIENT" ]; then
    "$CLIENT" --no-autostart >/dev/null 2>&1
    "$CLIENT" --stop >/dev/null 2>&1
    "$CLIENT" --uninstall-resolve-shortcuts
fi
rm -rf "$APP"
rm -f "$BIN/clipse" "$BIN/clipse-daemon"
# a copy an older version installed with pipx
export PIPX_DEFAULT_BACKEND=pip
if command -v pipx >/dev/null 2>&1; then
    pipx uninstall davinci-search >/dev/null 2>&1
else
    for v in /Library/Frameworks/Python.framework/Versions/3.*; do
        "$v/bin/python3" -m pipx uninstall davinci-search >/dev/null 2>&1
    done
fi
echo "Clipse is removed."
read -rp "Also delete your Clipse settings and favourites? [y/N] " a
[[ "$a" =~ ^[Yy] ]] && rm -rf "$HOME/.clipse" "$HOME/Library/Application Support/Clipse" \
    "$HOME/Library/Caches/Clipse" "$HOME/Library/Logs/Clipse" && echo "Settings deleted."
read -rp "Done. Press Enter to close..."
