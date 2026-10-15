"""Dump an AOL 3.0 IDB database (MAIN.IDX): one 'R2D2' record per GID.

Record header (26 bytes, little-endian): R2D2 | gid u32 | len u32 | flags u32 | 6 reserved | self offset u32
GID u32: top byte = type, next byte = subtype, low 16 = id  ('20-0-25' / '32-221').
usage: idb_dump.py MAIN.IDX [gid ...]   (no gid: list all)
"""
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "server"))
from fdo import codec  # noqa: E402


def gid_str(g: int) -> str:
    t, sub, i = g >> 24, (g >> 16) & 0xFF, g & 0xFFFF
    return f"{t}-{sub}-{i}" if t else f"{sub}-{i}"


def records(d: bytes):
    i = d.find(b"R2D2")
    while i >= 0:
        g, n, flags = struct.unpack_from("<III", d, i + 4)
        self_off, = struct.unpack_from("<I", d, i + 22)
        if self_off == i and n < len(d):
            yield g, flags, d[i + 26:i + 26 + n]
        i = d.find(b"R2D2", i + 4)


NESTED = ("act_append_action", "act_replace_action", "act_replace_select_action", "act_set_db_action",
          "uni_start_stream", "act_append_select_action")


def show(atoms, depth):
    for a in atoms:
        if a.name in NESTED and len(a.args) > 2:
            try:
                inner = codec.decode(a.args)
                print("    " * depth + a.name + " {")
                show(inner, depth + 1)
                print("    " * depth + "}")
                continue
            except Exception:
                pass
        print("    " * depth + repr(a))


def main():
    d = Path(sys.argv[1]).read_bytes()
    want = set(sys.argv[2:])
    for g, flags, body in records(d):
        name = gid_str(g)
        if want and name not in want:
            continue
        print(f"== {name}  len={len(body)} flags={flags:08x}")
        if not want:
            continue
        try:
            show(codec.decode(body), 1)
        except Exception as e:
            print("    (not an atom stream:", e, ")", body[:64].hex(" "))


if __name__ == "__main__":
    main()
