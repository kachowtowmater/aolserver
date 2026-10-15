"""Compile FDO91 source to the atom stream the AOL client runs.

By default this is fdo/pycompiler.py, a pure-Python compiler that produces the same bytes
as AOL's own compiler (Ada32.dll) -- checked against it on every client form and every
window the server builds (tools/fdo_corpus.py, server/test_fdo_compiler.py).  So the server
needs no Wine and runs on Windows, macOS and Linux.

AOL_FDO_DAEMON=1 compiles with the real Ada32 instead, through run/fdod.sh (fdo_daemon.exe
under Wine on 127.0.0.1:8099); AOL_FDO_DAEMON=verify uses Python but logs any difference
from Ada32.  Forms live in server/forms/*.fdo; {{var}} placeholders are filled with
FDO-safe text before compiling.  Results are cached by source text.
"""
import functools
import os
import re
import urllib.request
from pathlib import Path

from . import pycompiler
from .pycompiler import CompileError  # noqa: F401  (callers catch it from here)

DAEMON = "http://127.0.0.1:8099"
FORMS = Path(__file__).resolve().parent.parent / "forms"
MODE = os.environ.get("AOL_FDO_DAEMON", "").lower()   # "", "1" (Ada32 via Wine) or "verify"


def compile_with_daemon(source: str) -> bytes:
    req = urllib.request.Request(DAEMON + "/compile", data=source.encode("latin1", "replace"),
                                 headers={"Content-Type": "text/plain"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            data = r.read()
    except urllib.error.HTTPError as e:
        raise CompileError(e.read().decode("latin1", "replace")) from None
    if not data:
        raise CompileError("empty output")
    return data


@functools.lru_cache(maxsize=512)
def compile_fdo(source: str) -> bytes:
    if MODE in ("1", "yes", "true"):
        return compile_with_daemon(source)
    data = pycompiler.compile_source(source)
    if MODE == "verify":
        try:
            ada = compile_with_daemon(source)
            if ada != data:
                print(f"      FDO compiler differs from Ada32 ({len(data)} vs {len(ada)} bytes):\n{source[:400]}")
        except Exception as e:  # daemon down: Python output stands
            print(f"      FDO verify skipped: {e}")
    return data


ASCII = str.maketrans({"\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"', "\u2013": "-",
                       "\u2014": "--", "\u2026": "...", "\u00a0": " ", "\u2022": "*", "\u2122": "(TM)"})


def plain(value) -> str:
    """Modern text -> what a 1997 Win95 client can show (Latin-1)."""
    text = str(value).translate(ASCII)
    return text.encode("latin1", "replace").decode("latin1")


def fdo_text(value) -> str:
    """Escape a value for use inside an FDO "string" (\\xNN escapes, like AOL's own forms)."""
    out = []
    for ch in plain(value):
        if ch in '"<>\\' or ord(ch) < 32 and ch != "\r":
            out.append(f"\\x{ord(ch):02x}")
        elif ch == "\r":
            out.append("\\x0d")
        else:
            out.append(ch)
    return "".join(out)


def render(form: str, **values) -> bytes:
    src = (FORMS / f"{form}.fdo").read_text()
    src = re.sub(r"\{\{(\w+)\}\}", lambda m: fdo_text(values[m.group(1)]), src)
    return compile_fdo(src)
