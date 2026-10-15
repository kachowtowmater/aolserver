"""Build the golden corpus for the pure-Python FDO compiler and check it against AOL's own.

The corpus is every FDO source the server can send (its form templates and the screens.py
window builders, driven with awkward text: quotes, CR/LF, long text, Latin-1, curly quotes)
plus every client form decompiled from the 3.0 and 4.0 databases (re/idb*/fdo).

    fdo_corpus.py build    compile everything with Ada32 (the fdod daemon on :8099 must be up)
                           and write server/fdo/golden/{server.json,forms.json}
    fdo_corpus.py check    compare the Python compiler against the golden files (no Wine needed;
                           server/test_fdo_compiler.py runs this)
"""
import glob
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server"))
GOLDEN = ROOT / "server" / "fdo" / "golden"

SAMPLE_TEXT = [
    "Hello", "", 'He said "hi" <b> & back\\slash', "Line one\r\nLine two\nthree\rfour",
    "Café ‘smart’ “quotes” — dash… ™", "x" * 450,
    "Tab\there", "Ctrl\x01char", "© 1997 America Online", "12345678901234567890",
]


def server_sources() -> list[str]:
    """Run the server's window builders and templates, recording the FDO each would compile."""
    import fdo.compiler as compiler
    seen: list[str] = []

    def record(source):
        if source not in seen:
            seen.append(source)
        return b""
    real = compiler.compile_fdo
    compiler.compile_fdo = record
    try:
        import importlib
        for m in ("services.util", "services.screens"):
            if m in sys.modules:
                importlib.reload(sys.modules[m])
        from services import screens, util
        util.compile_fdo = screens.compile_fdo = record
        items = [("First item", 1), ("Second \"quoted\" item", 2), ("x" * 120, 250)]
        buttons = [("OK", '          sm_send_token_arg <"zA", 7>'), ("Cancel", "          uni_invoke_local <32-5483>")]
        for t in SAMPLE_TEXT:
            screens.list_window(t or "Title", t, items, buttons, art="1-0-24836", response_id=b"\x00\x00\x00\x11", window="w1")
            screens.list_window(t or "Title", t, [], (), width=40)
            screens.text_window(t or "Title", t, response_id=b"\x00\x00\x01\x00", window="w2", width=56, height=12)
            screens.input_window("Weather", "City:", "Get Forecast", "zW", t, window="w3")
            screens.input_window("Keyword", "Word:", "Go", "Kk")
            screens.page_window(t or "Page", t, items, window="w4")
            screens.form_window("Sign Up", t, [("Screen Name:", 12, ""), ("Password:", 12, ""), ("Note:", 30, t)], "Continue", "zS", window="w5")
            screens.welcome_window(t or "Surfer98", 3, items)
            screens.welcome_window("Rewind98", 0, [])
            screens.close_window(t or "w6")
        # templates in server/forms, rendered the way the services fill them in
        for t in SAMPLE_TEXT[:6]:
            for form in ("im", "im40"):
                src = (util.FORMS_DIR / f"{form}.fdo").read_text()
                vals = {"gid": "50-0-3", "sender": "Rewind98", "partner": "Surfer98", "text": t}
                record(_fill(src, vals, util.fdo_text))
            users = "\n".join(f'  chat_add_user <"{util.fdo_text(n)}">' for n in ("kewlguy97", t[:10] or "x"))
            for form in ("32-117", "43-22783"):
                src = (util.FORMS_DIR / "chat_room.fdo").read_text().replace("{{room}}", util.fdo_text(t or "Lobby 1")).replace(
                    "{{users}}", users).replace("{{form}}", form).replace("{{gid}}", screens.window_gid("chatroom"))
                record(src)
            welcome = (util.FORMS_DIR / "welcome.fdo").read_text()
            import re
            record(re.sub(r"\{\{(\w+)\}\}", lambda m: util.fdo_text(t or "Rewind98"), welcome))
            record(f'uni_start_stream <00x>\n  www_browse <"{util.fdo_text("http://news.yahoo.com/" + t[:40])}">\n'
                   "  uni_wait_off\nuni_end_stream <00x>")
    finally:
        compiler.compile_fdo = real
    return seen


def _fill(src, vals, esc):
    import re
    return re.sub(r"\{\{(\w+)\}\}", lambda m: esc(vals[m.group(1)]), src)


def form_files() -> list[Path]:
    return sorted(glob.glob(str(ROOT / "re" / "idb40" / "fdo" / "*.fdo")) + glob.glob(str(ROOT / "re" / "idb" / "fdo" / "*.fdo")))


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def build():
    import urllib.request

    def ada(src):
        req = urllib.request.Request("http://127.0.0.1:8099/compile", data=src.encode("latin1", "replace"))
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read() or None
        except urllib.error.HTTPError:
            return None
    GOLDEN.mkdir(parents=True, exist_ok=True)
    server = []
    for src in server_sources():
        out = ada(src)
        if out is None:
            print("Ada rejected a server source:\n" + src[:300])
            continue
        server.append({"source": src, "hex": out.hex()})
    (GOLDEN / "server.json").write_text(json.dumps(server, indent=0))
    forms = {}
    for f in form_files():
        out = ada(Path(f).read_text(encoding="latin1"))
        if out is not None:
            forms[str(Path(f).relative_to(ROOT))] = {"sha256": sha(out), "len": len(out)}
    (GOLDEN / "forms.json").write_text(json.dumps(forms, indent=0, sort_keys=True))
    print(f"golden: {len(server)} server sources, {len(forms)} client forms")


def check(verbose=True) -> tuple[int, list[str]]:
    from fdo.pycompiler import CompileError, compile_source
    failures, total = [], 0
    for case in json.loads((GOLDEN / "server.json").read_text()):
        total += 1
        try:
            out = compile_source(case["source"])
        except CompileError as e:
            out = str(e).encode()
        if out.hex() != case["hex"]:
            failures.append("server source: " + case["source"][:120].replace("\n", " | "))
    for path, want in json.loads((GOLDEN / "forms.json").read_text()).items():
        total += 1
        try:
            out = compile_source((ROOT / path).read_text(encoding="latin1"))
        except CompileError as e:
            failures.append(f"{path}: {e}")
            continue
        if sha(out) != want["sha256"]:
            failures.append(f"{path}: bytes differ ({len(out)} vs {want['len']})")
    if verbose:
        print(f"{total - len(failures)}/{total} identical to Ada32")
        for f in failures[:20]:
            print("  ", f)
    return total, failures


if __name__ == "__main__":
    {"build": build, "check": check}[sys.argv[1] if len(sys.argv) > 1 else "check"]()
