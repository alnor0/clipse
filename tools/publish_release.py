"""Puts a release on downloads.alnor.store (Cloudflare R2, bucket alnor-downloads): the downloads that are built
(the names download.html links to), install.sh (Linux's terminal line) and clipse.json - the version the app's update check reads
(updater.LATEST_URL). The json goes last, so no app is told about a version before its download is there.

    python3 tools/publish_release.py            uploads what's in build/
    python3 tools/publish_release.py --dry-run  says what it would upload
    ... --run 12345                             GitHub's build run 12345 downloaded into build/ first
                                                (gh run download; each download's .info.json says its version)
    python3 tools/publish_release.py --test     under test/ instead (no app looks there without the test_updates file)
    ... --partial                               without all three downloads (otherwise refused: every copy hears of
                                                the new version, and a system without its download would get the old
                                                one again from the download page)

Needs wrangler logged in (npx wrangler@4.151.1 login, once per computer).
"""
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD = os.path.join(ROOT, "build")
BUCKET = "alnor-downloads"
WRANGLER = ["npx", "--yes", "wrangler@4.151.1"]
DOWNLOADS = ("clipse-linux.AppImage", "clipse-mac.dmg", "clipse-windows.exe")
PAGE = "https://alnor.store/download.html"
UPDATES = {"linux": "clipse-linux.AppImage", "windows": "clipse-windows.exe", "mac": "clipse-mac.dmg"}  # (updater.DOWNLOAD_KINDS)


def version():
    with open(os.path.join(ROOT, "pyproject.toml"), encoding="utf-8") as f:
        mine = re.search(r'^version = "(.+?)"', f.read(), re.M).group(1)
    with open(os.path.join(ROOT, "clipse", "__init__.py"), encoding="utf-8") as f:
        other = re.search(r'__version__ = "(.+?)"', f.read()).group(1)
    if mine != other:
        sys.exit(f"pyproject.toml says {mine}, clipse/__init__.py says {other} - make them the same first.")
    return mine


def put(name, path, dry, cache="public, max-age=300", folder=""):
    print(f"  https://downloads.alnor.store/{folder}{name}  ({os.path.getsize(path) / 1e6:.1f} MB)")
    if not dry:
        subprocess.run(WRANGLER + ["r2", "object", "put", f"{BUCKET}/{folder}{name}", "--file", path, "--remote",
                                   "--cache-control", cache], check=True, cwd=BUILD)


def fetch_run(run):
    """GitHub's build run's downloads (and what each says of itself) into build/, over what's there."""
    import shutil
    import tempfile
    with tempfile.TemporaryDirectory(dir=BUILD) as there:
        subprocess.run(["gh", "run", "download", run, "-D", there], check=True, cwd=ROOT)
        for folder, _dirs, files in os.walk(there):
            for name in files:
                if name.removesuffix(".info.json") in DOWNLOADS:
                    shutil.move(os.path.join(folder, name), os.path.join(BUILD, name))
                    print(f"  from run {run}: {name}")


def check_builds(found, v, release):
    """Every download that says what it was built as (GitHub's do) must be this version."""
    for name in found:
        info = os.path.join(BUILD, name + ".info.json")
        if not os.path.isfile(info):
            continue
        with open(info, encoding="utf-8") as f:
            built = json.load(f)
        if built.get("version") != v:
            sys.exit(f"{name} was built as {built.get('version')}, this is {v} - build it again.")


def main():
    dry = "--dry-run" in sys.argv
    folder = "test/" if "--test" in sys.argv else ""
    if "--run" in sys.argv:
        fetch_run(sys.argv[sys.argv.index("--run") + 1])
    found = [name for name in DOWNLOADS if os.path.isfile(os.path.join(BUILD, name))]
    check_builds(found, version(), release=not folder)
    if not found:
        sys.exit(f"Nothing to upload: none of {', '.join(DOWNLOADS)} is in build/.")
    if len(found) < len(DOWNLOADS) and "--partial" not in sys.argv and not folder and not dry:
        sys.exit("Not all three downloads are in build/ (" + ", ".join(n for n in DOWNLOADS if n not in found) +
                 " missing) - every copy would hear of the new version. Get them from GitHub's build "
                 "(gh run download), or add --partial.")
    v = version()
    print(f"Clipse {v}{' (dry run)' if dry else ''}:")
    for name in found:
        put(name, os.path.join(BUILD, name), dry, folder=folder)
    with open(os.path.join(ROOT, "tools", "release", "install.sh"), encoding="utf-8") as f:  # (the terminal line)
        script = f.read().replace("__APPIMAGE_URL__", f"https://downloads.alnor.store/{folder}clipse-linux.AppImage")
    with open(os.path.join(BUILD, "install.sh"), "w", encoding="utf-8") as f:
        f.write(script)
    put("install.sh", os.path.join(BUILD, "install.sh"), dry, folder=folder)
    latest = os.path.join(BUILD, "clipse.json")
    with open(latest, "w", encoding="utf-8") as f:
        # (<kind>_url: what a copy updates itself from - self_update - with its fingerprint: a download that doesn't
        #  match it is refused. Only the downloads built for this version: one left from before would "update" a
        #  copy to the version it already is, over and over - without it that system gets the download page.)
        import hashlib
        release = {"version": v, "page_url": PAGE}
        for kind, name in UPDATES.items():
            if name in found:
                with open(os.path.join(BUILD, name), "rb") as a:
                    release[f"{kind}_sha256"] = hashlib.file_digest(a, "sha256").hexdigest()
                release[f"{kind}_url"] = f"https://downloads.alnor.store/{folder}{name}"
        json.dump(release, f)
    put("clipse.json", latest, dry, cache="no-cache", folder=folder)
    missing = [name for name in DOWNLOADS if name not in found]
    if missing:
        print("Not built here (the old one stays): " + ", ".join(missing))


if __name__ == "__main__":
    main()
