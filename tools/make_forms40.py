"""Build the AOL 4.0 client forms the host pushes at sign-on (server/forms/*40.fdo) from the
client's own forms (re/idb40/fdo), so the World Wide Web goes through the host.

The client's own browser window is Internet Explorer's engine; under Wine that is Wine Gecko,
which only works on the first thread that used it (AOL runs each browser window on its own
thread) and crashes navigating inside a window under x86 emulation.  The host draws the Web
itself instead (services/webview.py), so every place the client would open its IE window now
hands the address to the host:
  addr40   41-19051  address bar / Go: the typed text goes to the host as a keyword (Kk),
                     exactly like the Keyword window -- a URL opens in the host's Web window
  menu40   41-27066  toolbar menus: Go to the Web just asks the host (f1 32-4724)
  nav40    41-18931  toolbar Back/Reload/Stop/Home with no browser on top: home via the host
  wwwhost40 32-4705  the IE window itself, replaced: it never builds a window, it hands the
                     address it was opened with (variable 310, set by the client's native
                     www_browse -- the address bar's URL path) to the host as a keyword, or asks
                     for Go to the Web when there is none
  www40    32-4705   with AOL_WEBVIEW=0 instead: the real IE window, but one fixed window
                     (global id 32-4705, no close box) so a second Gecko thread never starts
The Welcome screen template (forms/welcome40.fdo) gets the Go to the Web change too.
usage: make_forms40.py
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "re" / "idb40" / "fdo"
OUT = ROOT / "server" / "forms"

SEND_A = """buf_start_buffer <token_header | stream_id_header | host_bound | start_stream_header | end_stream_trailer | response_id_header>
buf_set_token <"Kk">
var_string_get <A>
uni_use_last_atom_string <buf_add_atom_pointer>
buf_close_buffer"""


def indent(block: str, ind: str) -> str:
    return "".join(f"{ind}{l}\n" for l in block.splitlines())


def www40():
    s = (SRC / "32-4705.fdo").read_text()
    return s.replace("    mat_bool_auto_closeable <no>\n",
                     "    mat_bool_auto_closeable <no>\n    mat_bool_non_closeable <yes>\n"
                     "    mat_object_id <32-4705>\n", 1)


def wwwhost40():
    """The World Wide Web window's form, reduced to: hand its address to the host."""
    return """uni_start_stream <00x>
  man_set_context_globalid <1>
  var_string_null <A>
  var_lookup_by_id <A, 310>
  var_string_null <B>
  var_string_save <B, 310>
  man_end_context
  if_stra_neq_null_then <1, 2>
""" + indent(SEND_A, "    ") + """  uni_sync_skip <1>
    sm_send_f1 <32-4724>
  uni_sync_skip <2>
  uni_wait_off
uni_end_stream <00x>
"""


def addr40():
    """Both the 'load in the browser on top' and the 'open a browser' branches send A to the host."""
    s = (SRC / "41-19051.fdo").read_text()
    pat = re.compile(r"(?m)^( *)var_string_get <A>\n *uni_use_last_atom_string <www_(?:browse|load_url)>\n")
    s, n = pat.subn(lambda m: indent(SEND_A, m.group(1)), s)
    assert n >= 3, n
    return s


def drop_browse(text: str) -> str:
    """Go to the Web: keep the f1 to the host, drop the client's own www_browse."""
    out, n = re.subn(r'(?m)^ *www_browse <"[^"]*">\n', "", text)
    assert n >= 1
    return out


def nav40():
    s = (SRC / "41-18931.fdo").read_text()
    s, n = re.subn(r"(?m)^( *)www_browse\n", lambda m: f"{m.group(1)}sm_send_f1 <32-4724>\n", s)
    assert n == 1, n
    return s


def main():
    (OUT / "www40.fdo").write_text(www40())
    (OUT / "wwwhost40.fdo").write_text(wwwhost40())
    (OUT / "addr40.fdo").write_text(addr40())
    (OUT / "menu40.fdo").write_text(drop_browse((SRC / "41-27066.fdo").read_text()))
    (OUT / "nav40.fdo").write_text(nav40())
    w = OUT / "welcome40.fdo"
    text = w.read_text()
    # undo an earlier "reuse the IE window" rewrite of Go to the Web, then drop the browse
    text = re.sub(r"(?ms)^( *)man_preset_gid <32-4705>\n.*?^ *uni_sync_skip <120>\n( *www_browse <\"[^\"]*\">\n) *uni_sync_skip <121>\n",
                  lambda m: m.group(2), text)
    if 'www_browse <"' in text:
        text = drop_browse(text)
    w.write_text(text)
    print("wrote www40, wwwhost40, addr40, menu40, nav40 (+ welcome40 Go to the Web)")


if __name__ == "__main__":
    main()
