"""The compiled app's one program (tools/build_compiled.sh): with
--service, the service; --client, the client; --watcher, the watcher that starts the service when Resolve opens; --playhead, what moves the playhead with a voiceover; --organise, Organise project; --beats, Mark the beats;
--install, Linux's terminal line (it installs itself and sets up, no picker); nothing, Clipse opened by
hand: it sets itself up the first time and opens the picker (clipse/launch.py says which to start). DS_PROBE=<file.py> runs that uncompiled script inside the compiled app instead (to
find a problem step by step without compiling again - that's how Nuitka 4.3's crash was found)."""
import os
import sys

if __name__ == "__main__":
    probe = os.environ.get("DS_PROBE")
    if probe:
        import runpy
        runpy.run_path(probe, run_name="__main__")
    elif len(sys.argv) > 1 and sys.argv[1] == "--service":
        del sys.argv[1]
        from clipse.daemon import main
        main()
    elif len(sys.argv) > 1 and sys.argv[1] == "--client":
        del sys.argv[1]
        from clipse.client import main
        main()
    elif len(sys.argv) > 1 and sys.argv[1] == "--watcher":  # (started at login: starts the service with Resolve)
        del sys.argv[1]
        from clipse.watcher import main
        main()
    elif len(sys.argv) > 1 and sys.argv[1] == "--playhead":  # (a voiceover's: moves the playhead while it records)
        del sys.argv[1]
        from clipse.playhead import main
        main()
    elif len(sys.argv) > 1 and sys.argv[1] == "--organise":  # (Organise project: sorts and colours the project)
        del sys.argv[1]
        from clipse.organise import main
        main()
    elif len(sys.argv) > 1 and sys.argv[1] == "--beats":  # (Mark the beats: Resolve can take a second for each marker)
        del sys.argv[1]
        from clipse.beats import main
        main()
    elif len(sys.argv) > 1 and sys.argv[1] == "--install":  # (Linux's terminal line, install.sh: set up, no picker)
        del sys.argv[1:]
        from clipse.client import open_app
        open_app(picker=False)
    else:  # opened by hand - a double-click, Applications, the Start menu, the app launcher: the picker
        del sys.argv[1:]  # (macOS may hand an opened app a -psn_... of its own)
        from clipse.client import open_app
        open_app()
