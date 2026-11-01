#!/usr/bin/env bash
# Builds Clipse as a compiled program (Nuitka) and packs the download: build/clipse-linux.AppImage (built in a
# container, on this computer or GitHub), build/clipse-mac.dmg, build/clipse-windows.exe (on GitHub's Mac and Windows
# machines - .github/workflows/build.yml; Nuitka builds only for the system it runs on).
# Tried on Linux, 2026-10-16: it starts, connects to Resolve and opens the picker (the owner: "It works").
#   - Nuitka 4.2.2, NOT 4.3: 4.3 corrupts its list of compiled functions in PySide6 apps - a crash as soon as one
#     of our own QWidget classes is made (Nuitka issue #4081, fixed in 4.4).
#   - Python 3.12 (uv's; on Linux the container's), PySide6-Essentials 6.12. About 340 MB, 15 minutes the first time.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# Linux: built inside manylinux_2_34 (AlmaLinux 9's glibc 2.34, pinned), so it runs on every system Resolve does -
# built on Arch the program asked for glibc 2.38 and wouldn't start on Rocky 9, Ubuntu 22.04 or Debian 12. The
# container's Python lives in /opt/python: no folder of this computer gets into the program.
LINUX_IMAGE="quay.io/pypa/manylinux_2_34_x86_64@sha256:3a7a51dd9c82f9e0b81e5cf72fd7e784906d76fcec727dd1645f609c869289fa"
if [ "$(uname -s)" = Linux ] && [ -z "${DS_IN_CONTAINER:-}" ]; then
  mkdir -p "$ROOT/build/container-cache"
  # (as the container's root: Nuitka needs the static libpython, packed in /opt/_internal - what it makes is
  #  handed back to this user at the end)
  exec docker run --rm -v "$ROOT:/src" -v "$ROOT/build/container-cache:/cache" -w /src \
    -e DS_IN_CONTAINER=1 -e GITHUB_ACTIONS="${GITHUB_ACTIONS:-}" -e HOME=/cache -e XDG_CACHE_HOME=/cache -e OUTSIDE_HOME="$HOME" \
    -e HOST_OWNER="$(id -u):$(id -g)" "$LINUX_IMAGE" bash tools/build_compiled.sh
fi
if [ -n "${DS_IN_CONTAINER:-}" ]; then
  trap 'chown -R "$HOST_OWNER" "$ROOT/build"' EXIT
  [ -e /opt/_internal/static-libs-for-embedding-only.tar.xz ] && (cd /opt/_internal && tar xf static-libs-for-embedding-only.tar.xz)
  VENV="$ROOT/build/compile-venv-linux"
  if ! "$VENV/bin/python" -c 1 2>/dev/null; then
    rm -rf "$VENV"
    /opt/python/cp312-cp312/bin/python -m venv "$VENV"
    "$VENV/bin/python" -m pip install -q "nuitka==4.2.2" ordered-set zstandard imageio \
      "PySide6-Essentials==6.12.0" "av>=12" numpy "miniaudio>=1.59"
  fi
else
  VENV="$ROOT/build/compile-venv"
  # Python saves where it's installed, and that's compiled in - so the build's Python lives in a neutral folder,
  # never under the home folder (it put /home/<user> into the program 20 times)
  PYDIR=/tmp/clipse-python
  VPY="$VENV/bin/python"
  case "$(uname -s)" in MINGW*|MSYS*|CYGWIN*) VPY="$VENV/Scripts/python.exe" ;; esac   # (Windows: Git Bash)
  if ! grep -q "^home = $PYDIR/" "$VENV/pyvenv.cfg" 2>/dev/null || ! "$VPY" -c 1 2>/dev/null; then
    rm -rf "$VENV"
    UV_PYTHON_INSTALL_DIR="$PYDIR" uv python install -q 3.12
    UV_PYTHON_INSTALL_DIR="$PYDIR" uv venv -q --managed-python -p 3.12 "$VENV"
    uv pip install -q -p "$VPY" "nuitka==4.2.2" ordered-set zstandard imageio \
      "PySide6-Essentials==6.12.0" "av>=12" numpy "miniaudio>=1.59"
  fi
  # a Mac: PyObjC, the app's way to macOS itself - without it the picker isn't brought to the front, Resolve doesn't
  # get the keyboard back after an insert and nothing shows over a full-screen Resolve (silently: found 2026-10-20,
  # the first .dmg had none)
  if [ "$(uname -s)" = Darwin ] && ! "$VPY" -c "import AppKit, objc" 2>/dev/null; then
    uv pip install -q -p "$VPY" "pyobjc-framework-Cocoa==12.2.2"
  fi
fi
VPY="${VPY:-$VENV/bin/python}"
cd "$ROOT"
# paths as the system's own programs want them (Windows: C:\..., not Git Bash's /c/...)
native() { if command -v cygpath >/dev/null 2>&1; then cygpath -w "$1"; else printf '%s' "$1"; fi; }
OUT="$ROOT/build/compiled"
# Opened by hand it opens the picker (compiled_main.py): a Mac gets a real Clipse.app (in Applications, opened
# once - macOS asks there, not later in the background) with no Dock icon; Windows no console window. Both with the
# app's mark (clipse/data/icon.png - imageio turns it into .icns / .ico). Built on GitHub (.github/workflows/build.yml).
ICON="$(native "$ROOT/clipse/data/icon.png")"
VERSION="$(sed -n 's/^version = "\(.*\)"/\1/p' "$ROOT/pyproject.toml")"
case "$(uname -s)" in
  # (the Mac's bundle id is the login start's name; its version is what a copy opened from the .dmg compares with
  #  the one in Applications - install.mac_version. Without them: "Clipse" and "1.0")
  Darwin) PLATFORM=(--macos-create-app-bundle --macos-app-name="Clipse" --macos-app-mode=ui-element
                    --macos-signed-app-name=store.alnor.clipse --macos-app-version="$VERSION"
                    --include-module=AppKit --include-module=Foundation --include-module=objc
                    --macos-app-icon="$ICON"
                    --macos-app-protected-resource="NSMicrophoneUsageDescription:Clipse records your voiceovers.") ;;
  MINGW*|MSYS*|CYGWIN*) PLATFORM=(--windows-console-mode=disable --windows-icon-from-ico="$ICON"
                                  --windows-product-name=Clipse --windows-company-name=alnor
                                  --windows-file-description=Clipse
                                  --windows-product-version="$VERSION") ;;
  *) PLATFORM=() ;;
esac
# the program's file: clipse.exe on Windows, clipse.bin elsewhere - a file called clipse would collide with the app's
# own folder (clipse/, its data) in the same place
EXE=clipse.bin
case "$(uname -s)" in MINGW*|MSYS*|CYGWIN*) EXE=clipse.exe ;; esac
CPUS="$(nproc 2>/dev/null || getconf _NPROCESSORS_ONLN 2>/dev/null || echo 4)"
# no docstrings (the code's notes) and no paths of this computer in the program: nothing in it leads to who built it
PYTHONPATH="$(native "$ROOT")" "$VPY" -m nuitka --standalone --assume-yes-for-downloads \
  --enable-plugin=pyside6 --include-package=clipse --include-package-data=clipse \
  --include-module=av --include-module=av._cyutil --include-module=miniaudio --include-module=numpy --include-module=runpy \
  --nofollow-import-to=tests --python-flag=no_docstrings --file-reference-choice=runtime --jobs="$CPUS" \
  --output-dir="$(native "$OUT")" --output-filename="$EXE" "${PLATFORM[@]}" "$(native "$ROOT/tools/compiled_main.py")"
MINE="${OUTSIDE_HOME:-$HOME}"  # (in the container: the home folder outside it)
SHIPPED="$OUT/compiled_main.dist"   # (only what ships - Nuitka's own work files beside it name the home folder)
[ "$(uname -s)" = Darwin ] && SHIPPED="$(ls -d "$OUT"/*.app | head -1)"
if [ -z "${GITHUB_ACTIONS:-}" ] && grep -rlF --binary-files=text "$MINE" "$SHIPPED" >/dev/null; then
  echo "Stopped: your home folder ($MINE) is inside the program:" >&2   # (on GitHub the home is its machine's)
  grep -rlF --binary-files=text "$MINE" "$SHIPPED" >&2
  exit 1
fi
if [ -n "${DS_IN_CONTAINER:-}" ]; then  # (it has to start where Resolve does: nothing newer than glibc 2.34)
  NEWEST=$(find "$OUT/compiled_main.dist" -type f \( -name "*.so*" -o -name clipse.bin \) \
    -exec objdump -T {} \; 2>/dev/null | grep -o "GLIBC_2\.[0-9]*" | sort -t. -k2,2n -u | tail -1)
  [ "$NEWEST" = GLIBC_2.34 ] || [ "${NEWEST#GLIBC_2.}" -lt 34 ] || { echo "Stopped: it needs $NEWEST" >&2; exit 1; }
  echo "Needs at most $NEWEST (Rocky 9, Ubuntu 22.04, Debian 12 and newer)"
fi
case "$(uname -s)" in
  Darwin)  # the download: a .dmg with Clipse.app and Applications beside it, to drag it in
    for bundle in "$OUT"/*.app; do   # (the bundle is named after compiled_main.py: in Applications it's the app's name)
      [ "$bundle" = "$OUT/Clipse.app" ] || { rm -rf "$OUT/Clipse.app"; mv "$bundle" "$OUT/Clipse.app"; }
    done
    [ -d "$OUT/Clipse.app/Contents/MacOS/AppKit" ] && [ -d "$OUT/Clipse.app/Contents/MacOS/objc" ] ||
      { echo "Stopped: no PyObjC in Clipse.app (see the Mac's pip install above)" >&2; exit 1; }
    codesign --force --deep --sign - "$OUT/Clipse.app"   # (ad hoc - no Apple account: Apple silicon needs at least this)
    STAGE="$OUT/dmg" && rm -rf "$STAGE" && mkdir -p "$STAGE"
    cp -R "$OUT/Clipse.app" "$STAGE/" && ln -s /Applications "$STAGE/Applications"
    [ "$(uname -m)" = arm64 ] || { echo "Stopped: Clipse is built for Apple silicon Macs only (Intel dropped, 2026-10-23)" >&2; exit 1; }
    DMG="$ROOT/build/clipse-mac.dmg"
    rm -f "$DMG"
    hdiutil create -quiet -volname Clipse -srcfolder "$STAGE" -ov -format UDZO "$DMG"
    PACKED="$DMG"
    echo "Packed $DMG" ;;
  MINGW*|MSYS*|CYGWIN*)  # the download: an installer (Inno Setup - tools/windows/clipse.iss), no admin needed
    ISCC="$(command -v iscc || command -v ISCC || true)"
    [ -n "$ISCC" ] || ISCC="/c/Program Files (x86)/Inno Setup 6/ISCC.exe"
    rm -f "$ROOT/build/clipse-windows.exe"
    MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL="*" "$ISCC" /Q "/DVersion=$(sed -n 's/^version = "\(.*\)"/\1/p' pyproject.toml)" \
      "/DSource=$(native "$OUT/compiled_main.dist")" "/DOut=$(native "$ROOT/build")" "$(native "$ROOT/tools/windows/clipse.iss")"
    PACKED="$ROOT/build/clipse-windows.exe"
    echo "Packed $PACKED" ;;
  Linux)  # the download: one AppImage (it installs itself - clipse/install.py)
    TOOLS="$ROOT/build/appimage-tools"   # the official tool and runtime, pinned
    mkdir -p "$TOOLS"
    [ -x "$TOOLS/appimagetool" ] || { curl -fsSL -o "$TOOLS/appimagetool" \
      https://github.com/AppImage/appimagetool/releases/download/1.9.1/appimagetool-x86_64.AppImage && chmod +x "$TOOLS/appimagetool"; }
    [ -f "$TOOLS/runtime-x86_64" ] || curl -fsSL -o "$TOOLS/runtime-x86_64" \
      https://github.com/AppImage/type2-runtime/releases/download/20251108/runtime-x86_64
    APPDIR="$OUT/AppDir"
    rm -rf "$APPDIR" && mkdir -p "$APPDIR"
    cp -r "$OUT/compiled_main.dist" "$APPDIR/clipse"
    printf '#!/bin/sh\nexec "$(dirname "$(readlink -f "$0")")/clipse/clipse.bin" "$@"\n' > "$APPDIR/AppRun"
    chmod +x "$APPDIR/AppRun"
    printf '[Desktop Entry]\nType=Application\nName=Clipse\nExec=clipse\nIcon=clipse\nTerminal=false\nCategories=AudioVideo;Video;\n' \
      > "$APPDIR/clipse.desktop"
    cp "$ROOT/clipse/data/icon.png" "$APPDIR/clipse.png" && cp "$ROOT/clipse/data/icon.png" "$APPDIR/.DirIcon"
    rm -f "$ROOT/build/clipse-linux.AppImage"
    ARCH=x86_64 "$TOOLS/appimagetool" --appimage-extract-and-run --no-appstream --comp zstd \
      --runtime-file "$TOOLS/runtime-x86_64" "$APPDIR" "$ROOT/build/clipse-linux.AppImage" >/dev/null
    PACKED="$ROOT/build/clipse-linux.AppImage"
    echo "Packed $PACKED" ;;
esac
# what it was built as, beside it: tools/publish_release.py refuses a release of another version
printf '{"version": "%s"}
' "$VERSION" > "$PACKED.info.json"
