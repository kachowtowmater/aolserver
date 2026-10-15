"""FDO91 atom stream codec (binary form the AOL client executes).

Byte 0's top 3 bits pick the style (see deceptio.org/re/fdo/decoding-atom-streams):
0 full, 1 length, 2 data, 3 atom, 4 current, 5 zero, 6 one, 7 prefix.
We always *encode* with the full style; *decoding* handles all eight.
"""
import json
from dataclasses import dataclass
from pathlib import Path

_TABLE = json.loads((Path(__file__).parent / "atoms.json").read_text())
BY_NAME = {k: (v["proto"], v["atom"]) for k, v in _TABLE.items()}
BY_NUM = {v: k for k, v in BY_NAME.items()}


@dataclass
class Atom:
    proto: int
    num: int
    args: bytes = b""

    @property
    def name(self) -> str:
        return BY_NUM.get((self.proto, self.num), f"p{self.proto}:a{self.num}")

    def __repr__(self):
        a = self.args
        shown = repr(a.decode("latin1")) if a and all(32 <= c < 127 for c in a) else a.hex(" ")
        return f"{self.name} <{shown}>" if a else self.name


def decode(data: bytes) -> list[Atom]:
    out, i, cur_proto = [], 0, 0
    p_off = a_off = 0
    keep = False
    while i < len(data):
        b = data[i]
        style, low = b >> 5, b & 0x1F
        if style == 7:
            p_off, a_off, keep = (b & 0x18) << 2, (b & 0x06) << 4, bool(b & 1)
            i += 1
            continue
        if style == 0:
            proto, num, flag = low, data[i + 1], data[i + 2]
            if flag & 0x80:
                n = ((flag & 0x7F) << 8) | data[i + 3]
                hdr = 4
            else:
                n, hdr = flag, 3
            args = data[i + hdr:i + hdr + n]
            i += hdr + n
        elif style in (1, 2):
            proto, num, x = low, data[i + 1] & 0x1F, data[i + 1] >> 5
            if style == 1:
                args = data[i + 2:i + 2 + x]
                i += 2 + x
            else:
                args = bytes([x])
                i += 2
        elif style == 4:
            proto, num, n = cur_proto, low, data[i + 1]
            args = data[i + 2:i + 2 + n]
            i += 2 + n
        else:  # 3 atom, 5 zero, 6 one
            proto, num = cur_proto, low
            args = {3: b"", 5: b"\x00", 6: b"\x01"}[style]
            i += 1
        proto |= p_off
        num |= a_off
        if not keep:
            p_off = a_off = 0
        cur_proto = proto
        out.append(Atom(proto, num, bytes(args)))
    return out


def atom(name: str, args: bytes = b"") -> bytes:
    proto, num = BY_NAME[name]
    n = len(args)
    if n < 0x80:
        return bytes([proto, num, n]) + args
    return bytes([proto, num, 0x80 | (n >> 8), n & 0xFF]) + args


def stream(*atoms: bytes) -> bytes:
    return atom("uni_start_stream") + b"".join(atoms) + atom("uni_end_stream")


# argument helpers
def u8(n: int) -> bytes: return bytes([n])
def u16(n: int) -> bytes: return n.to_bytes(2, "big")
def u32(n: int) -> bytes: return n.to_bytes(4, "big")
def s(text: str) -> bytes: return text.encode("latin1")


def gid(text: str) -> bytes:
    """'32-221' -> 3 bytes (type, id16); '20-0-25' -> 4 bytes (type, subtype, id16)."""
    parts = [int(p) for p in text.split("-")]
    if len(parts) == 2:
        return bytes([parts[0]]) + u16(parts[1])
    return bytes([parts[0], parts[1]]) + u16(parts[2])
