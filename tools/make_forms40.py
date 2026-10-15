"""Build the AOL 4.0 client forms the host pushes at sign-on (server/forms/*40.fdo) from the
client's own forms (re/idb40/fdo), with the changes the Wine browser needs.

Wine Gecko only works on the first thread that used it, and AOL runs every World Wide Web
window on its own thread: a second browser window stays blank.  So under Wine there must be
exactly one browser window, reused for every page:
  www40   32-4705  World Wide Web window: a fixed global id (32-4705) so it can be found, and
                   no close box (closing it would kill the engine for the rest of the session)
  addr40  41-19051 address bar / Go: load into the browser window if it exists, else open it
  menu40  41-27066 toolbar menus (Internet > Go to the Web): same
The Welcome screen template (forms/welcome40.fdo) gets the same change for its Go to the Web.
usage: make_forms40.py
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "re" / "idb40" / "fdo"
OUT = ROOT / "server" / "forms"


def reuse(url_lines: str, browse_line: str, label: int, indent: str) -> str:
    """FDO: load the URL in the existing browser window (32-4705) if there is one, else open one.
    man_preset_gid succeeds (and sets context) when the window exists."""
    i = indent
    return (f"{i}man_preset_gid <32-4705>\n"
            f"{i}if_last_return_true_then <{label}, {label + 1}>\n"
            f"{i}  man_end_context\n"
            f"{i}  man_set_context_globalid <32-4705>\n"
            f"{i}  man_make_focus\n"
            f"{i}  man_set_context_relative <1>\n"
            + "".join(f"{i}  {l}\n" for l in url_lines.replace("www_browse", "www_load_url").splitlines())
            + f"{i}  man_end_context\n"
            f"{i}  man_update_display\n"
            f"{i}  man_end_context\n"
            f"{i}uni_sync_skip <{label}>\n"
            f"{i}{browse_line}\n"
            f"{i}uni_sync_skip <{label + 1}>\n")


def www40():
    s = (SRC / "32-4705.fdo").read_text()
    return s.replace("    mat_bool_auto_closeable <no>\n",
                     "    mat_bool_auto_closeable <no>\n    mat_bool_non_closeable <yes>\n"
                     "    mat_object_id <32-4705>\n", 1)


def addr40():
    s = (SRC / "41-19051.fdo").read_text()
    for n, label in ((0, 120), (1, 122)):
        m = list(re.finditer(r"(?m)^( *)var_string_get <A>\n *uni_use_last_atom_string <www_browse>\n", s))[n]
        ind = m.group(1)
        s = s[:m.start()] + reuse("var_string_get <A>\nuni_use_last_atom_string <www_browse>",
                                  "var_string_get <A>\n" + ind + "uni_use_last_atom_string <www_browse>",
                                  label, ind) + s[m.end():]
    return s


def fixed_url(text: str, label: int) -> str:
    m = re.search(r'(?m)^( *)www_browse <"([^"]+)">\n', text)
    ind, url = m.group(1), m.group(2)
    return text[:m.start()] + reuse(f'www_browse <"{url}">', f'www_browse <"{url}">', label, ind) + text[m.end():]


def main():
    (OUT / "www40.fdo").write_text(www40())
    (OUT / "addr40.fdo").write_text(addr40())
    (OUT / "menu40.fdo").write_text(fixed_url((SRC / "41-27066.fdo").read_text(), 120))
    w = OUT / "welcome40.fdo"
    if "<32-4705>" not in w.read_text():
        w.write_text(fixed_url(w.read_text(), 120))
    print("wrote www40, addr40, menu40 (+ welcome40 Go to the Web)")


if __name__ == "__main__":
    main()
