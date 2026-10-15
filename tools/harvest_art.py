"""Harvest AOL art records (type-1 GIDs) from AOL client databases into server/art/.

usage: python3 -I harvest_art.py [--item NAME] [--keep DIR] PATH [PATH ...]

PATH may be an IDX file (MAIN.IDX, ART5.IDX, ...), an installer/blob that embeds
zip entries (AOL DynaZip SETUP95.EXE etc.), or a directory (walked recursively).
Embedded *.IDX zip entries are carved out in memory (validated by CRC); with
--keep they are also saved under DIR for later re-harvesting.

Each art body is written to server/art/<gid>.bin.  The first copy found wins
unless a later one is larger.  Provenance goes to server/art/SOURCES.tsv:
gid, item, size, image type, file.

Pure stdlib; treats every input as untrusted data (never executed).
"""
import argparse
import os
import struct
import sys
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ART = ROOT / "server" / "art"
SOURCES = ART / "SOURCES.tsv"
HDR = "gid\titem\tsize\timage\tfile\n"
MAX_SCAN = 800 * 1024 * 1024        # never slurp anything bigger than this
NESTED_EXT = (".EXE", ".ZIP", ".DLL", ".CAB", ".IDX", ".AOL")


def gid_str(g: int) -> str:
    t, sub, i = g >> 24, (g >> 16) & 0xFF, g & 0xFFFF
    return f"{t}-{sub}-{i}" if t else f"{sub}-{i}"


def records(d: bytes):
    """Yield (gid, flags, body) for every self-consistent R2D2 record."""
    i = d.find(b"R2D2")
    while i >= 0:
        if i + 26 <= len(d):
            g, n, flags = struct.unpack_from("<III", d, i + 4)
            self_off, = struct.unpack_from("<I", d, i + 22)
            if self_off == i and i + 26 + n <= len(d):
                yield g, flags, d[i + 26:i + 26 + n]
        i = d.find(b"R2D2", i + 4)


def image_type(body: bytes) -> str:
    best = None
    for sig, name in ((b"GIF89a", "gif"), (b"GIF87a", "gif"), (b"\xff\xd8\xff", "jpeg"),
                      (b"JFIF", "jpeg"), (b"BM", "bmp"), (b"\x89PNG", "png")):
        k = body.find(sig, 0, 512)
        if sig == b"BM" and k >= 0:
            # require a plausible BITMAPFILEHEADER/INFOHEADER after "BM"
            ok = False
            while k >= 0 and not ok:
                if k + 18 <= len(body) and struct.unpack_from("<I", body, k + 14)[0] in (12, 40, 108, 124):
                    ok = True
                else:
                    k = body.find(sig, k + 1, 512)
        if k >= 0 and (best is None or k < best[0]):
            best = (k, name)
    if best:
        return best[1]
    k = body.find(b"JG", 0, 128)            # Johnson-Grace ART (AOL's compressed art format)
    if k >= 0 and k + 4 <= len(body) and body[k + 3] == 0x0E:
        return "jg-art"
    for k in range(0, 64, 2):           # headerless DIB: BITMAPINFOHEADER after the AOL art header
        if k + 16 <= len(body) and struct.unpack_from("<I", body, k)[0] == 40:
            planes, bpp = struct.unpack_from("<HH", body, k + 12)
            if planes == 1 and bpp in (1, 4, 8, 16, 24, 32):
                return "dib"
    return "unknown"


def zip_entries(d: bytes, depth=0):
    """Carve zip local-file entries from a blob. Validates each header by CRC and
    advances only 4 bytes past a bad one (garbage 'PK\\3\\4' inside code is common)."""
    i = 0
    while (i := d.find(b"PK\x03\x04", i)) >= 0:
        if i + 30 > len(d):
            break
        ver, flag, meth, t, dt, crc, csz, usz, nl, xl = struct.unpack_from("<HHHHHIIIHH", d, i + 4)
        start = i + 30 + nl + xl
        if meth not in (0, 8) or flag & 1 or not 0 < nl < 260 or start + csz > len(d) or usz > MAX_SCAN:
            i += 4
            continue
        name = d[i + 30:i + 30 + nl].decode("latin1").replace("\\", "/")
        if flag & 8:                    # sizes in data descriptor: not used by AOL installers
            i += 4
            continue
        data = d[start:start + csz]
        try:
            raw = data if meth == 0 else zlib.decompress(data, -15)
        except zlib.error:
            i += 4
            continue
        if zlib.crc32(raw) != crc or len(raw) != usz:
            i += 4
            continue
        yield name, raw
        if depth < 2 and name.upper().endswith(NESTED_EXT) and b"PK\x03\x04" in raw:
            for n2, r2 in zip_entries(raw, depth + 1):
                yield f"{name}!{n2}", r2
        i = start + csz


class Store:
    def __init__(self):
        ART.mkdir(parents=True, exist_ok=True)
        self.rows = {}
        if SOURCES.exists():
            for line in SOURCES.read_text().splitlines()[1:]:
                f = line.split("\t")
                if len(f) >= 4:
                    self.rows[f[0]] = f + [""] * (5 - len(f))
        self.new = self.bigger = 0

    def add(self, gid, body, item, fname):
        size = len(body)
        cur = self.rows.get(gid)
        if cur and int(cur[2]) >= size:
            return
        (ART / f"{gid}.bin").write_bytes(body)
        if cur:
            self.bigger += 1
        else:
            self.new += 1
        self.rows[gid] = [gid, item, str(size), image_type(body), fname]

    def save(self):
        def key(g):
            return tuple(int(x) for x in g.split("-"))
        tmp = SOURCES.with_suffix(".tmp")
        with open(tmp, "w") as f:
            f.write(HDR)
            for g in sorted(self.rows, key=key):
                f.write("\t".join(self.rows[g]) + "\n")
        os.replace(tmp, SOURCES)


def harvest_blob(store, d, item, fname, keep):
    n = 0
    if b"R2D2" in d:
        for g, flags, body in records(d):
            if g >> 24 == 1 and body:
                store.add(gid_str(g), body, item, fname)
                n += 1
    if b"PK\x03\x04" in d:
        for name, raw in zip_entries(d):
            if not name.upper().endswith(".IDX") or b"R2D2" not in raw:
                continue
            if keep:
                dst = Path(keep) / (Path(fname).name + "!" + name.replace("/", "_").replace("!", "_"))
                dst.parent.mkdir(parents=True, exist_ok=True)
                dst.write_bytes(raw)
            n += harvest_blob(store, raw, item, f"{fname}!{name}", None)
    return n


def walk(paths):
    for p in map(Path, paths):
        if p.is_dir():
            for q in sorted(p.rglob("*")):
                if q.is_file() and not q.is_symlink():
                    yield q
        elif p.is_file():
            yield p


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--item", help="source item name (default: first path component name)")
    ap.add_argument("--keep", help="directory to save IDX files carved out of installers")
    ap.add_argument("--all", action="store_true", help="scan every file, not just IDX/EXE/ZIP/...")
    ap.add_argument("paths", nargs="+")
    a = ap.parse_args()
    store = Store()
    item = a.item or Path(a.paths[0]).resolve().name
    for f in walk(a.paths):
        up = f.name.upper()
        if not a.all and not up.endswith(NESTED_EXT + (".IMA", ".BIN", ".DAT")) and not up.startswith("SETUP"):
            continue
        if f.stat().st_size > MAX_SCAN:
            continue
        d = f.read_bytes()
        n = harvest_blob(store, d, item, str(f).replace(str(Path.home()), "~", 1), a.keep)
        del d
        if n:
            print(f"{f}: {n} art records", file=sys.stderr)
    store.save()
    print(f"{item}: +{store.new} new, {store.bigger} replaced by larger; total {len(store.rows)} art GIDs")


if __name__ == "__main__":
    main()
