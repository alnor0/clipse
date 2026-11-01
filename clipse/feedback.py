"""Send feedback (Settings > About, feedback_dialog.py): a problem or an idea, a few words, pictures, an email to answer
to - and with a problem the logs (report.logs_zip), unless they're left out. Posted to the site's /api/feedback
(tools/site_functions), listed with tools/feedback.py. When that doesn't work it's kept as a zip on the Desktop
instead (save), to email to report.SUPPORT_EMAIL."""
import json
import platform
import urllib.error
import urllib.request
import uuid

from . import __version__, report

SITE = "https://alnor.store"  # (your own domain, never a host's address: every copy keeps calling what it shipped with)

MAX_IMAGES = 5


def system():
    return f"{platform.system()} {platform.release()} ({platform.machine()})"


def _multipart(fields, files):
    """(content type, body) of a form: fields (name, text), files (name, file name, type, bytes)."""
    boundary = uuid.uuid4().hex
    parts = []
    for name, value in fields:
        parts += [f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
                  str(value).encode("utf-8"), b"\r\n"]
    for name, filename, kind, data in files:
        parts += [f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'
                  f"Content-Type: {kind}\r\n\r\n".encode(), data, b"\r\n"]
    parts.append(f"--{boundary}--\r\n".encode())
    return f"multipart/form-data; boundary={boundary}", b"".join(parts)


def send(kind, text, email="", images=(), logs=True):
    """kind "problem" | "idea"; images [(type, bytes)]. Raises with a message to show when it didn't go."""
    fields = [("kind", kind), ("text", text), ("email", email), ("version", __version__), ("system", system())]
    files = [("image", f"picture-{n}.{mime.split('/')[1]}", mime, data)
             for n, (mime, data) in enumerate(images[:MAX_IMAGES], 1)]
    if logs:
        files.append(("logs", "logs.zip", "application/zip", report.logs_zip()))
    post(dict(fields), files)


def post(fields, files):
    """Posts a form to the site's /api/feedback - Send feedback's, and a crash report's (crash_report.py). Raises with
    a message to show when it didn't go."""
    fields = {"version": __version__, "system": system(), **fields}
    content_type, body = _multipart(list(fields.items()), files)
    request = urllib.request.Request(f"{SITE}/api/feedback", data=body, headers={
        "content-type": content_type, "User-Agent": f"clipse/{__version__}"})  # (Cloudflare turns Python's own away)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            answer = json.load(response)
    except urllib.error.HTTPError as e:
        try:
            message = json.load(e).get("error")
        except Exception:
            message = None
        raise RuntimeError(message or f"The site said no ({e.code})") from None
    except (urllib.error.URLError, OSError):
        raise RuntimeError("Couldn't reach alnor.store - are you online?") from None
    if not answer.get("ok"):
        raise RuntimeError(answer.get("error") or "The site said no")


def save(kind, text, email="", images=(), logs=True):
    """Kept as a zip on the Desktop instead - its path."""
    note = f"{'A problem' if kind == 'problem' else 'An idea'}\n\n{text}\n\nEmail: {email}\n"
    extra = [("feedback.txt", note)] + [(f"picture-{n}.{mime.split('/')[1]}", data)
                                        for n, (mime, data) in enumerate(images[:MAX_IMAGES], 1)]
    return report.make(extra=extra, logs=logs)
