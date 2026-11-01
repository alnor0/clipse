#!/usr/bin/env bash
# Builds the zip viewers download: build/clipse.zip
# (the app, the installers, READMEs for each system). Run from anywhere.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/build/clipse"
rm -rf "$ROOT/build" && mkdir -p "$OUT"
cp -r "$ROOT/clipse" "$OUT/"
find "$OUT" -name __pycache__ -prune -exec rm -rf {} +
cp "$ROOT/pyproject.toml" "$OUT/"
cp "$ROOT"/installers/* "$OUT/"
for f in "$OUT"/*.bat; do  # Windows wants CRLF line endings in .bat files
  python3 - "$f" <<'PY'
import sys
p = sys.argv[1]
t = open(p, newline="").read().replace("\r\n", "\n").replace("\n", "\r\n")
open(p, "w", newline="").write(t)
PY
done
python3 "$ROOT/tools/make_readmes.py"
(cd "$ROOT/build" && zip -qr -X clipse.zip clipse)
echo "Built $ROOT/build/clipse.zip (version $(python3 -c "import re;print(re.search(r'version = \"(.+?)\"', open('$ROOT/pyproject.toml').read()).group(1))"))"
