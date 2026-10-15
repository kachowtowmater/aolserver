"""Regenerate server/fdo/atom_args.json: how AOL's compiler encodes each atom's arguments.

Compiles every decompiled client form (re/idb*/fdo) with the real Ada32 compiler (the fdod
daemon on 127.0.0.1:8099 must be running: run/fdod.sh), lines the output atoms up with the
source atoms (recursing into nested action streams), and learns
  - the byte value of every enum word per atom and argument position (center_center, arial,
    ind_group, ...), probing Ada with single-word variants where a word only ever appears
    next to other unknown words;
  - number arguments that Ada writes at a fixed width (the rest are minimal big-endian).
Then run tools/fdo_corpus.py build/check to confirm the Python compiler matches Ada exactly.
usage: learn_fdo_args.py
"""
import glob
import json
import sys
import urllib.request
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server"))
from fdo import codec, fdoparse  # noqa: E402

FLAGS = {n: v.get("flags") for n, v in json.loads((ROOT / "server/fdo/atoms.json").read_text()).items()}
VARS = {c: i for i, c in enumerate("ABCDEFGHIJKLMNOPQRSTUVWXYZ")}
NUM_WIDTH = {("mat_size", 2): 2}       # found by inspection: a 3rd size argument is always 2 bytes
_cache: dict[str, bytes | None] = {}


def ada(src: str):
    if src not in _cache:
        req = urllib.request.Request("http://127.0.0.1:8099/compile", data=src.encode("latin1", "replace"))
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                _cache[src] = r.read() or None
        except urllib.error.HTTPError:
            _cache[src] = None
    return _cache[src]


def full_decode(data: bytes):
    """Ada only writes full-style atoms (with an optional protocol prefix byte)."""
    out, i = [], 0
    while i < len(data):
        b, off = data[i], 0
        if b >> 5 == 7:
            off, i = (b & 0x18) << 2, i + 1
            b = data[i]
        if b >> 5:
            raise ValueError(f"style {b >> 5} at {i}")
        n, h = (data[i + 2], 3) if not data[i + 2] & 0x80 else (((data[i + 2] & 0x7F) << 8) | data[i + 3], 4)
        out.append(((b & 0x1F) | off, data[i + 1], data[i + h:i + h + n]))
        i += h + n
    return out


def collect():
    samples = defaultdict(list)    # atom -> [(args as [(kind, text)], arg bytes)]

    def align(src_atoms, data):
        dec = full_decode(data)
        if len(dec) != len(src_atoms):
            raise ValueError("atom count")
        for s, (proto, num, args) in zip(src_atoms, dec):
            if FLAGS.get(s.name) == 6 and s.args and s.args[0] and s.args[0][0].kind == "word":
                align([a for t in s.args for a in fdoparse.parse_tokens_as_stream(t)], args)
                continue
            samples[s.name].append(([[(t.kind, t.text) for t in a] for a in s.args], args))

    for f in sorted(glob.glob(str(ROOT / "re/idb40/fdo/*.fdo")) + glob.glob(str(ROOT / "re/idb/fdo/*.fdo"))):
        src = Path(f).read_text(encoding="latin1")
        out = ada(src)
        if out is None:
            continue
        try:
            align(fdoparse.parse(src), out)
        except (ValueError, fdoparse.ParseError):
            continue   # art records the decompiler misread as forms
    return samples


def number(t, width=None):
    v = min(int(t), 0x7FFFFFFF)
    v &= 0xFFFFFFFF
    return v.to_bytes(width or max(1, (v.bit_length() + 7) // 8), "big")


def main():
    samples = collect()
    words = defaultdict(dict)

    def word(atom, i, w):
        if (i, w) in words[atom]:
            return words[atom][(i, w)]
        for (_, ww), v in words[atom].items():
            if ww == w:
                return v
        if w in codec.BY_NAME and FLAGS.get(atom) in (12, 18):
            return bytes(codec.BY_NAME[w])
        if w in VARS and FLAGS.get(atom) in (15, 16, 17):
            return bytes([VARS[w]])
        return None

    def arg(atom, i, a):
        if not a:
            return b""
        if len(a) == 1:
            k, t = a[0]
            return {"hex": lambda: bytes([int(t[:-1], 16)]), "num": lambda: number(t, NUM_WIDTH.get((atom, i))),
                    "gid": lambda: number(sum(int(x) << s for x, s in zip(t.split("-")[::-1], (0, 16, 24)))),
                    "str": lambda: fdoparse.unescape(t[1:-1]), "raw": lambda: t.encode("latin1"),
                    "word": lambda: word(atom, i, t)}[k]()
        if any(t == "|" for _, t in a):
            vals = [word(atom, i, t) if k == "word" else number(t) for k, t in a if k != "punct"]
            if None in vals:
                return None
            x = 0
            for v in vals:
                x |= int.from_bytes(v, "big")
            return x.to_bytes(max(len(v) for v in vals), "big")
        return None

    def probe(atom, i, args, w):
        parts = [w if j == i else " ".join(t for _, t in a) for j, a in enumerate(args)]
        out = ada(f"uni_start_stream <00x>\n  {atom} <{', '.join(parts)}>\nuni_end_stream <00x>")
        if not out or out[4] >> 5 == 7 or out[6] & 0x80:
            return None
        data = out[7:-4]
        pre = [arg(atom, j, args[j]) for j in range(i)]
        suf = [arg(atom, j, args[j]) for j in range(i + 1, len(args))]
        if None in pre + suf:
            return None
        pre, suf = b"".join(pre), b"".join(suf)
        if not data.startswith(pre) or not data.endswith(suf):
            return None
        return data[len(pre):len(data) - len(suf)]

    for _ in range(6):
        learned = 0
        for atom, ss in samples.items():
            for args, b in ss:
                enc = [arg(atom, i, a) for i, a in enumerate(args)]
                unk = [i for i, e in enumerate(enc) if e is None]
                for i in unk:
                    for k, t in args[i]:
                        if k != "word" or word(atom, i, t) is not None:
                            continue
                        v = probe(atom, i, args, t) if len(args[i]) > 1 or len(unk) > 1 else None
                        if v is None and len(unk) == 1 and len(args[i]) == 1:
                            pre, suf = b"".join(enc[:i]), b"".join(enc[i + 1:])
                            if b.startswith(pre) and b.endswith(suf):
                                v = b[len(pre):len(b) - len(suf)]
                        if v is not None:
                            words[atom][(i, t)] = v
                            learned += 1
        if not learned:
            break
    out = {"words": {a: {f"{p}:{w}": v.hex() for (p, w), v in sorted(d.items())} for a, d in sorted(words.items()) if d},
           "num_width": {f"{a}:{p}": w for (a, p), w in NUM_WIDTH.items()}}
    (ROOT / "server/fdo/atom_args.json").write_text(json.dumps(out, indent=0, sort_keys=True))
    print(f"{sum(len(d) for d in words.values())} words for {len(out['words'])} atoms")


if __name__ == "__main__":
    main()
