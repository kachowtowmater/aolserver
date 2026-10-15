"""Draw the AOL 4.0 chat room art that only AOL's host ever had (form 43-22783).

The client's own form names each picture (mat_art_hint_title) and its size; we draw them in
the 4.0 room's look -- grey bevelled buttons with white bold text on the cream window --
and store them as GIF art records next to the harvested originals.
usage: make_chat40_art.py   (needs ImageMagick's `magick`)
"""
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server"))
from services.art import art_record  # noqa: E402

FONT = "/usr/share/fonts/liberation/LiberationSans-Bold.ttf"
CREAM, GREY, DARK, LIGHT = "#F6F2EA", "#7B7B7B", "#202020", "#B8B8B8"

BUTTONS = {  # art id -> (label, width, height)
    "1-1-50131": ("Private Chat", 116, 12),
    "1-1-50130": ("Notify AOL", 116, 12),
    "1-1-50128": ("Chat Prefs", 116, 12),
    "1-1-50129": ("AOL Live", 150, 24),
}


def magick(*args) -> bytes:
    with tempfile.NamedTemporaryFile(suffix=".gif") as f:
        subprocess.run(["magick", *args, "-colors", "32", f"GIF87:{f.name}"], check=True)
        return Path(f.name).read_bytes()


def button(label, w, h) -> bytes:
    size = min(max(9, h - 3), 14)
    return magick("-size", f"{w}x{h}", f"xc:{CREAM}",
                  "-fill", DARK, "-draw", f"rectangle 1,1 {w - 1},{h - 1}",
                  "-fill", GREY, "-draw", f"rectangle 0,0 {w - 2},{h - 2}",
                  "-fill", LIGHT, "-draw", f"line 0,0 {w - 2},0", "-draw", f"line 0,0 0,{h - 2}",
                  "-font", FONT, "-pointsize", str(size), "-fill", "white", "-gravity", "center",
                  "-annotate", "+0+0", label)


def label(text, w, h) -> bytes:
    # the client draws a 2-colour (1-bit) GIF as a mask, so keep the anti-aliased edges:
    # they give the palette enough colours to be shown as a picture
    return magick("-size", f"{w}x{h}", f"xc:{CREAM}", "-font", FONT, "-pointsize", str(h - 7),
                  "-fill", "#000040", "-gravity", "west", "-annotate", "+2+0", text)


def live_banner(w, h) -> bytes:
    return magick("-size", f"{w}x{h}", "gradient:#3262C7-#1A2F70",
                  "-fill", DARK, "-draw", f"rectangle 0,{h - 2} {w},{h}",
                  "-font", FONT, "-fill", "#FFD200", "-gravity", "north", "-pointsize", "22",
                  "-annotate", "+0+6", "AOL Live!",
                  "-fill", "white", "-pointsize", "11", "-annotate", "+0+36", "Tonight's events")


def main():
    out = ROOT / "server" / "art"
    arts = {k: button(*v) for k, v in BUTTONS.items()}
    arts["1-1-50762"] = label("People Here:", 110, 20)
    arts["1-1-50127"] = live_banner(118, 63)
    for name, gif in arts.items():
        (out / f"{name}.bin").write_bytes(art_record(gif, 5))
        print(name, len(gif))


if __name__ == "__main__":
    main()
