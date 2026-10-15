"""Compile FDO91 source with AOL's own compiler (Ada32.dll) via the FDO daemon.

The daemon is run/fdod.sh (fdo_daemon.exe under Wine) on 127.0.0.1:8099.
Forms live in server/forms/*.fdo; {{var}} placeholders are filled with
FDO-safe text before compiling. Results are cached by source text.
"""
import functools
import re
import urllib.request
from pathlib import Path

DAEMON = "http://127.0.0.1:8099"
FORMS = Path(__file__).resolve().parent.parent / "forms"


class CompileError(Exception):
    pass


@functools.lru_cache(maxsize=512)
def compile_fdo(source: str) -> bytes:
    req = urllib.request.Request(DAEMON + "/compile", data=source.encode("latin1"),
                                 headers={"Content-Type": "text/plain"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            data = r.read()
    except urllib.error.HTTPError as e:
        raise CompileError(e.read().decode("latin1", "replace")) from None
    if not data:
        raise CompileError("empty output")
    return data


def fdo_text(value) -> str:
    """Make a value safe inside an FDO "string" (no quotes / angle brackets)."""
    return re.sub(r'["<>\r\n]', " ", str(value))


def render(form: str, **values) -> bytes:
    src = (FORMS / f"{form}.fdo").read_text()
    src = re.sub(r"\{\{(\w+)\}\}", lambda m: fdo_text(values[m.group(1)]), src)
    return compile_fdo(src)
