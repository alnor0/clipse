"""Putting things on the clipboard - on a Mac written out at once, never promised.

Qt on a Mac only promises what it copies: the words are handed over when another app pastes, asked of Clipse's
main thread then. Resolve reads the clipboard whenever it comes to the front, and Clipse's main thread is often
waiting on Resolve (a question asked through its scripting) - so each waited for the other and Resolve hung
(2026-10-23, after copying a piece in Expressions). Written straight to the Mac's pasteboard, nobody waits on us."""
import sys

from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication


def _mac_pasteboard():
    if sys.platform != "darwin" or QGuiApplication.platformName() != "cocoa":
        return None  # (offscreen, as the tests run: Qt's own clipboard)
    try:
        from AppKit import NSPasteboard
    except ImportError:
        return None
    return NSPasteboard.generalPasteboard()


def set_text(text):
    board = _mac_pasteboard()
    if board is not None:
        try:
            from AppKit import NSPasteboardTypeString
            board.clearContents()
            if board.setString_forType_(text, NSPasteboardTypeString):
                return
        except Exception as e:
            print(f"[clipboard] the Mac's pasteboard: {e}")
    QApplication.clipboard().setText(text)


def set_files(paths, data):
    """Files, as a file manager copies them, with their paths as words. `data` is the QMimeData for every other
    system (it says the same the Linux file managers' way)."""
    board = _mac_pasteboard()
    if board is not None:
        try:
            from Foundation import NSURL
            board.clearContents()
            if board.writeObjects_([NSURL.fileURLWithPath_(p) for p in paths] + ["\n".join(paths)]):
                return False
        except Exception as e:
            print(f"[clipboard] the Mac's pasteboard: {e}")
    QApplication.clipboard().setMimeData(data)
    return True  # (Qt holds it: let go of it when the app quits)
