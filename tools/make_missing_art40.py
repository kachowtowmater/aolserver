"""Stand-in art for every picture an AOL 4.0 client form uses that neither the client's own
database nor the harvested CD art has (AOL's host used to send these on demand).

A form that asks the host for missing art stalls until it arrives, so the server preloads
all of these at sign-on (services/art.py preload).  Each stand-in is drawn at the size the
form gives it: a labelled 4.0-style button when the form names it (mat_art_hint_title),
otherwise a plain panel in the window colour so it doesn't stand out.
usage: make_missing_art40.py   (needs ImageMagick; skips art that already exists)
"""
import glob
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from make_chat40_art import CREAM, art_record, button, magick  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server"))
from services import art  # noqa: E402


FORM_DIRS = {"30": "re/idb/fdo", "40": "re/idb40/fdo"}


def referenced(version):
    """Every art id the client's own forms use that its database doesn't hold."""
    refs = set()
    for f in glob.glob(str(ROOT / FORM_DIRS[version] / "*.fdo")):
        refs |= set(re.findall(r"mat_art_id <(\d+-\d+-\d+)>", open(f, errors="replace").read()))
    return sorted(refs - art.LOCAL[version])


def wanted(version="40"):
    """art id -> (label, width, height) for art the forms use but nobody has."""
    local = art.LOCAL[version]
    out = {}
    for f in sorted(glob.glob(str(ROOT / FORM_DIRS[version] / "*.fdo"))):
        lines = open(f, errors="replace").read().splitlines()
        for i, line in enumerate(lines):
            m = re.search(r"mat_art_id <(\d+-\d+-\d+)>", line)
            if not m or m.group(1) in local or m.group(1) in out or (art.ART / f"{m.group(1)}.bin").exists():
                continue
            ctx = "\n".join(lines[max(0, i - 25):i + 3])
            title = re.findall(r'mat_art_hint_title <"([^"]*)">', ctx)
            w = re.findall(r"mat_precise_width <(\d+)>", ctx)
            h = re.findall(r"mat_precise_height <(\d+)>", ctx)
            out[m.group(1)] = (title[-1] if title else "", int(w[-1]) if w else 48, int(h[-1]) if h else 48)
    return out


def main():
    for version in FORM_DIRS:
        for name, (label, w, h) in wanted(version).items():
            w, h = max(8, min(w, 400)), max(8, min(h, 300))
            gif = button(label, w, h) if label else magick("-size", f"{w}x{h}", f"xc:{CREAM}")
            (art.ART / f"{name}.bin").write_bytes(art_record(gif, 5))
            print(version, name, label or "(panel)", f"{w}x{h}")
    # the list services/art.py preloads at sign-on
    out = ROOT / "server" / "data" / "preload_art.json"
    out.write_text(json.dumps({v: referenced(v) for v in FORM_DIRS}, indent=0))
    print("wrote", out)


if __name__ == "__main__":
    main()
