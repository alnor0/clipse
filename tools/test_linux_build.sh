#!/usr/bin/env bash
# Starts the built AppImage (build/clipse-linux.AppImage) on the oldest systems it's meant for - Rocky 9
# (what Blackmagic names for Resolve), Ubuntu 22.04, Debian 12 - and the newest, Arch and Fedora, each in a container with the libraries a desktop has,
# and runs tools/linux_selfcheck.py inside it. Run it before every Linux release.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
[ -f "$ROOT/build/clipse-linux.AppImage" ] || { echo "Build it first: tools/build_compiled.sh" >&2; exit 1; }
status=0
for image in rockylinux:9 ubuntu:22.04 debian:12 archlinux:latest fedora:latest; do
  out=$(docker run --rm -v "$ROOT/build:/b:ro" -v "$ROOT/tools:/t:ro" -e APPIMAGE_EXTRACT_AND_RUN=1 -e LANG=C.UTF-8 \
      -e DS_PROBE=/t/linux_selfcheck.py "$image" sh -c '
      if command -v pacman >/dev/null; then
        pacman -Sy --noconfirm --needed libglvnd libxkbcommon fontconfig dbus glib2 >/dev/null 2>&1
      elif command -v dnf >/dev/null; then
        dnf -q -y install libglvnd-egl libglvnd-glx libxkbcommon fontconfig dbus-libs glib2 >/dev/null 2>&1
      else
        apt-get -qq update >/dev/null && DEBIAN_FRONTEND=noninteractive apt-get -qq -y install libegl1 libgl1 \
          libxkbcommon0 libfontconfig1 libdbus-1-3 libglib2.0-0 >/dev/null 2>&1
      fi
      cp /b/clipse-linux.AppImage /tmp/app && /tmp/app' 2>&1 | grep -v "^qt\." || true)
  line=$(printf '%s\n' "$out" | grep -E "^(WORKS|FAILED)" | head -1)
  if [ "${line%% *}" = WORKS ]; then
    printf '%-14s %s\n' "$image" "$line"
  else
    printf '%-14s DOESN\x27T START:\n%s\n' "$image" "$(printf '%s\n' "$out" | tail -6)"
    status=1
  fi
done
exit $status
