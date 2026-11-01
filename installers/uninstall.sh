#!/usr/bin/env bash
# Clipse uninstaller for Linux - double-click it, or run:  bash uninstall.sh
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
rm -f "${XDG_DATA_HOME:-$HOME/.local/share}/applications/clipse.desktop"  # (its place among the apps)
# a copy an older version installed with pipx
export PIPX_DEFAULT_BACKEND=pip
if command -v pipx >/dev/null 2>&1; then pipx uninstall davinci-search >/dev/null 2>&1
else python3 -m pipx uninstall davinci-search >/dev/null 2>&1; fi
echo "Clipse is removed."
read -rp "Also delete your Clipse settings and favourites? [y/N] " a
[[ "$a" =~ ^[Yy] ]] && rm -rf "$HOME/.clipse" "${XDG_CONFIG_HOME:-$HOME/.config}/clipse" \
    "${XDG_CACHE_HOME:-$HOME/.cache}/clipse" "${XDG_STATE_HOME:-$HOME/.local/state}/clipse" \
    "${XDG_DATA_HOME:-$HOME/.local/share}/clipse" && echo "Settings deleted."
read -rp "Done. Press Enter to close..."
