"""Download one archive.org item's disk images into disc/harvest/<item>/, extract (bsdtar;
raw 2352-byte CD sectors are converted first), run harvest_art.py, keep only the IDX files.
usage: python3 -I harvest_ia_item.py ITEM_ID [file-regex]"""
import json, os, re, shutil, subprocess, sys, urllib.parse
from pathlib import Path

ROOT = Path.home() / "aol-revival"
HARV = ROOT / "tools" / "harvest_art.py"
LOG = ROOT / "disc" / "harvest" / "items.log"
MAXB = 700 * 1024 * 1024
WANT = re.compile(r"\.(iso|img|ima|imz|vfd|dsk|bin|zip|7z|rar|exe|idx|cdr|nrg|mdf|toast|dmg)$", re.I)
IMG = re.compile(r"\.(iso|img|bin|cdr|nrg|mdf|toast|zip|7z|rar|imz)$", re.I)


def log(msg):
    print(msg, flush=True)
    with open(LOG, "a") as f:
        f.write(msg + "\n")


def harvest(item, paths, keep, all_=False):
    cmd = ["python3", "-I", str(HARV), "--item", item, "--keep", str(keep)] + (["--all"] if all_ else []) + [str(p) for p in paths]
    r = subprocess.run(cmd, capture_output=True, text=True, cwd="/")
    out = (r.stdout + r.stderr).strip()
    print(out)
    return out


SYNC = b"\x00" + b"\xff" * 10 + b"\x00"


def raw_to_iso(src):
    """Convert a raw 2352-byte-sector CD image (.bin) to a 2048-byte ISO next to it."""
    with open(src, "rb") as f:
        head = f.read(2352)
        if len(head) < 2352 or head[:12] != SYNC or os.path.getsize(src) % 2352:
            return None
        f.seek(16 * 2352)            # volume descriptor sector decides mode
        pvd = f.read(2352)
        off = 16 if pvd[15] == 1 else 24
        dst = Path(str(src) + ".iso")
        f.seek(0)
        with open(dst, "wb") as o:
            while sec := f.read(2352):
                o.write(sec[off:off + 2048])
    return dst


def extract(src, dst):
    dst.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(["bsdtar", "-xf", str(src), "-C", str(dst), "--no-same-owner", "--no-same-permissions"],
                       capture_output=True, text=True, cwd="/")
    subprocess.run(["chmod", "-R", "u+rwX", str(dst)], cwd="/")
    n = sum(1 for _ in dst.rglob("*"))
    return r.returncode == 0 and n > 0, r.stderr.strip()[:200], n


def main():
    item = sys.argv[1]
    pat = re.compile(sys.argv[2], re.I) if len(sys.argv) > 2 else None
    base = ROOT / "disc" / "harvest" / item
    base.mkdir(parents=True, exist_ok=True)
    keep = base / "idx"
    md = json.loads(subprocess.run(["curl", "-sL", "--max-time", "60", f"https://archive.org/metadata/{item}"],
                                   capture_output=True, cwd="/").stdout or b"{}")
    files = [f for f in md.get("files", []) if WANT.search(f["name"]) and f.get("source") != "derivative"]
    if pat:
        files = [f for f in files if pat.search(f["name"])]
    log(f"== {item}: {len(files)} candidate files")
    for f in files:
        size = int(f.get("size", 0) or 0)
        name = f["name"]
        if size > MAXB:
            log(f"  skip {name} ({size} bytes > 700MB)")
            continue
        dl = base / "dl"
        dl.mkdir(exist_ok=True)
        local = dl / Path(name).name
        url = f"https://archive.org/download/{item}/" + urllib.parse.quote(name)
        r = subprocess.run(["curl", "-sSL", "--fail", "--retry", "3", "--max-time", "3600", "-o", str(local), url],
                           capture_output=True, text=True, cwd="/")
        if r.returncode:
            log(f"  download failed {name}: {r.stderr.strip()[:200]}")
            continue
        if re.search(r"\.(bin|iso|img|cdr)$", name, re.I):
            iso = raw_to_iso(local)
            if iso:
                local.unlink()
                local = iso
        ex = base / "ex" / Path(name).name
        outs = []
        if IMG.search(name):
            ok, err, n = extract(local, ex)
            if ok:
                # one more level: images/archives inside the archive
                for inner in list(ex.rglob("*")):
                    if inner.is_file() and IMG.search(inner.name) and inner.stat().st_size <= MAXB:
                        ok2, err2, n2 = extract(inner, inner.with_name(inner.name + ".x"))
                        if ok2:
                            inner.unlink()
                outs.append(harvest(item, [ex], keep))
            else:
                log(f"  bsdtar failed on {name}: {err}")
        if not any("art records" in o for o in outs):
            # raw scan (floppy images, unrecognised images, bare installers)
            outs.append(harvest(item, [local], keep, all_=True))
        recs = [l for l in "\n".join(outs).splitlines() if "art records" in l]
        log(f"  {name} ({size}): " + ("; ".join(l.replace(str(base) + "/", "") for l in recs) or "no art records found"))
        if ex.exists():
            for idx in ex.rglob("*"):
                if idx.is_file() and idx.suffix.upper() == ".IDX" and b"R2D2" in idx.read_bytes()[:1 << 20]:
                    keep.mkdir(exist_ok=True)
                    shutil.copy2(idx, keep / (idx.parent.name + "_" + idx.name))
            shutil.rmtree(base / "ex", ignore_errors=True)
        local.unlink(missing_ok=True)
    shutil.rmtree(base / "dl", ignore_errors=True)
    tot = subprocess.run(["bash", "-c", f"tail -n +2 {ROOT}/server/art/SOURCES.tsv | wc -l"], capture_output=True, text=True).stdout.strip()
    log(f"  total art GIDs now {tot}")


if __name__ == "__main__":
    main()
