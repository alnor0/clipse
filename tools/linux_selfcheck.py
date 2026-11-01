"""Run inside the built AppImage (DS_PROBE) by tools/test_linux_build.sh: every part of the app loads, and Qt,
video (PyAV), sound (miniaudio) and numpy work - what a missing compiled module would break (av._cyutil was)."""
import os
import pkgutil
import importlib

os.environ["QT_QPA_PLATFORM"] = "offscreen"
import clipse
from clipse import __version__

failed = []
for m in pkgutil.iter_modules(clipse.__path__):
    try:
        importlib.import_module(f"clipse.{m.name}")
    except Exception as e:
        failed.append(f"{m.name}: {e!r}"[:160])

from PySide6.QtWidgets import QApplication, QLabel
app = QApplication([])
label = QLabel("Clipse")
label.show()
app.processEvents()

import av
import miniaudio
import numpy
import io
buffer = io.BytesIO()
with av.open(buffer, "w", format="wav") as out:  # (a sound made and read back: PyAV's own code runs)
    stream = out.add_stream("pcm_s16le", rate=8000)
    frame = av.AudioFrame.from_ndarray(numpy.zeros((1, 800), dtype=numpy.int16), format="s16", layout="mono")
    frame.rate = 8000
    for packet in stream.encode(frame):
        out.mux(packet)
    for packet in stream.encode(None):
        out.mux(packet)
buffer.seek(0)
with av.open(buffer) as back:
    frames = sum(f.samples for f in back.decode(audio=0))
decoded = miniaudio.decode(buffer.getvalue(), nchannels=1, sample_rate=8000)

if failed:
    print("FAILED parts:", *failed, sep="\n  ")
    raise SystemExit(1)
print(f"WORKS {__version__}: every part loads, Qt shows a window, PyAV wrote and read {frames} samples, "
      f"miniaudio decoded {len(decoded.samples)}")
