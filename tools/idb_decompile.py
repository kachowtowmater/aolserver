"""Decompile every atom-stream record in an IDB to FDO source via the FDO daemon.

usage: idb_decompile.py MAIN.IDX OUTDIR [daemon_url]
"""
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from idb_dump import gid_str, records  # noqa: E402

src, out = Path(sys.argv[1]), Path(sys.argv[2])
url = sys.argv[3] if len(sys.argv) > 3 else "http://127.0.0.1:8099"
out.mkdir(parents=True, exist_ok=True)
ok = bad = 0
for g, flags, body in records(src.read_bytes()):
    name = gid_str(g)
    if name.startswith("1-0-"):  # artwork
        continue
    req = urllib.request.Request(url + "/decompile", data=body, headers={"Content-Type": "application/octet-stream"})
    try:
        text = urllib.request.urlopen(req, timeout=30).read().decode("latin1")
        (out / f"{name}.fdo").write_text(text)
        ok += 1
    except Exception as e:
        bad += 1
        (out / f"{name}.err").write_text(str(e))
print(ok, "decompiled,", bad, "failed")
