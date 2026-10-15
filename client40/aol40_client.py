#!/usr/bin/env python3
"""Get the original AOL 4.0 for Windows client and point it at an aolserver host.

Runs anywhere Python 3.9+ runs (Windows, macOS, Linux); stdlib only.

  python aol40_client.py fetch                    download + verify the AOL 4.0 CD (archive.org)
                                                 and unpack it to ./aol40-cd  (run SETUP.EXE from there)
  python aol40_client.py configure <AOL dir> [--host aol.example.com] [--port 5190] [--wine]
                                                 point an installed client at your server

`configure` makes the same changes on every platform:
  - csl/tcp.csl  -> "EXTERN CONNECT <host> <port>"   (use a host NAME: the client mangles dotted IPs;
                   for a server on the same machine use localhost)
  - tool/aolsec.aol -> security handshake off (1 byte; the host can't do AOL's RSA handshake)
and with --wine (Linux/macOS, or Windows-on-ARM under Wine) also the two Wine work-arounds:
  - iwengx32.dll  -> AOL's browser engine ignores Wine's stubbed FreezeEvents (else blank/frozen WWW)
  - inetcpl.cpl   -> stand-in so WWW Preferences doesn't abort on Wine's missing IE property pages
Originals are kept next to each file as *.orig; `configure --revert` puts them back.

  python aol40_client.py web --wine-prefix ~/.wine-aol4 [--proxy 127.0.0.1:8098] [--wine wine]
                                                 send AOL 4.0's browser through WRP (Wine clients):
                                                 http via the WRP proxy, home page http://www.aol.com/
On Windows itself AOL 4.0 uses Windows' own IE engine, which copes with much more of the modern
Web, so WRP is optional there (pointing Windows' system proxy at WRP would also affect other apps).
"""
import argparse
import hashlib
import shutil
import struct
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ISO_URL = ("https://archive.org/download/All_New_and_Improved_AOL_Version_4.0_1999/"
           "All%20New%20and%20Improved%20AOL%20Version%204.0%201999.ISO")
ISO_SHA256 = "7780ca46200b990b2106085f7051be786062d2c47c427cbca109e5da021978d2"
ISO_SIZE = 102404096

# (relative path, offset, expected original bytes, patched bytes)
PATCHES = {
    "aolsec": ("tool/aolsec.aol", 0x21ad8, b"\x01", b"\x00"),
    "iwengx32": ("iwengx32.dll", 0x2ed8, b"\x7d", b"\xeb"),
}


# ---------- fetch ----------

def download(dest: Path):
    if dest.exists() and dest.stat().st_size == ISO_SIZE:
        print(f"have {dest}")
    else:
        print(f"downloading AOL 4.0 CD ({ISO_SIZE // 2**20} MB) from archive.org ...")
        tmp = dest.with_suffix(".part")
        with urllib.request.urlopen(ISO_URL, timeout=60) as r, open(tmp, "wb") as f:
            done = 0
            while chunk := r.read(1 << 20):
                f.write(chunk)
                done += len(chunk)
                print(f"\r  {done * 100 // ISO_SIZE}%", end="", flush=True)
        print()
        tmp.replace(dest)
    h = hashlib.sha256(dest.read_bytes()).hexdigest()
    if h != ISO_SHA256:
        sys.exit(f"checksum mismatch for {dest}: {h}")
    print("checksum OK")


def iso_extract(iso: Path, out: Path):
    """Minimal ISO 9660 reader (plain level-1/2 names, which is what this CD uses)."""
    data = iso.read_bytes()
    pvd = data[16 * 2048:17 * 2048]
    if pvd[1:6] != b"CD001":
        sys.exit("not an ISO 9660 image")
    root = pvd[156:156 + 34]

    def walk(extent, size, path: Path):
        path.mkdir(parents=True, exist_ok=True)
        pos, end = extent * 2048, extent * 2048 + size
        while pos < end:
            n = data[pos]
            if n == 0:  # records don't cross sectors: skip to the next one
                pos = (pos // 2048 + 1) * 2048
                continue
            rec = data[pos:pos + n]
            ext, length = struct.unpack_from("<I", rec, 2)[0], struct.unpack_from("<I", rec, 10)[0]
            flags, nlen = rec[25], rec[32]
            name = rec[33:33 + nlen]
            pos += n
            if name in (b"\x00", b"\x01"):
                continue
            name = name.decode("latin1").split(";")[0].rstrip(".")
            if flags & 2:
                walk(ext, length, path / name)
            else:
                (path / name).write_bytes(data[ext * 2048:ext * 2048 + length])

    walk(struct.unpack_from("<I", root, 2)[0], struct.unpack_from("<I", root, 10)[0], out)


def fetch(args):
    iso = Path(args.iso)
    download(iso)
    out = Path(args.out)
    iso_extract(iso, out)
    print(f"unpacked to {out}.  Install with {out / 'SETUP.EXE'} (on Linux/macOS: wine {out / 'SETUP.EXE'}),")
    print("then run:  python aol40_client.py configure '<install folder>' --host <your server>")


# ---------- configure ----------

def patch(aol: Path, key: str, revert: bool):
    rel, off, old, new = PATCHES[key]
    f = aol / rel
    orig = f.with_name(f.name + ".orig")
    if revert:
        if orig.exists():
            shutil.copy2(orig, f)
            print(f"restored {rel}")
        return
    data = bytearray(f.read_bytes())
    if data[off:off + 1] == new:
        print(f"{rel}: already patched")
        return
    if data[off:off + 1] != old:
        sys.exit(f"{rel}: unexpected byte at {off:#x} ({data[off]:#04x}); different client version?")
    if not orig.exists():
        shutil.copy2(f, orig)
    data[off:off + 1] = new
    f.write_bytes(bytes(data))
    print(f"patched {rel}")


def configure(args):
    aol = Path(args.dir)
    if not (aol / "waol.exe").exists():
        sys.exit(f"{aol} doesn't look like an AOL 4.0 install (no waol.exe)")
    csl = aol / "csl" / "tcp.csl"
    orig = csl.with_name("tcp.csl.orig")
    if args.revert:
        if orig.exists():
            shutil.copy2(orig, csl)
            print("restored csl/tcp.csl")
    else:
        if not orig.exists():
            shutil.copy2(csl, orig)
        text = orig.read_bytes().decode("latin1")
        import re
        text = re.sub(r"EXTERN CONNECT \S+ \d+", f"EXTERN CONNECT {args.host} {args.port}", text)
        csl.write_bytes(text.encode("latin1"))
        print(f"csl/tcp.csl -> {args.host}:{args.port}")
    patch(aol, "aolsec", args.revert)
    if args.wine:
        patch(aol, "iwengx32", args.revert)
        stand_in = aol / "inetcpl.cpl"
        if args.revert:
            stand_in.unlink(missing_ok=True)
        else:
            shutil.copy2(HERE / "inetcpl" / "inetcpl.cpl", stand_in)
            print("installed stand-in inetcpl.cpl (also set WINEDLLOVERRIDES=inetcpl.cpl=n,b)")
    if not args.revert:
        print("\nIn AOL: Setup -> 'Add Location' (or edit Home) -> connect via TCP/IP, then sign on.")


def web(args):
    """Point the Wine prefix's IE settings (both registry views: AOL is 32-bit) at WRP."""
    import os
    import subprocess
    env = dict(os.environ, WINEPREFIX=str(Path(args.wine_prefix).expanduser()), WINEDEBUG="-all")
    inet = r"HKCU\Software\Microsoft\Windows\CurrentVersion\Internet Settings"
    main_key = r"HKCU\Software\Microsoft\Internet Explorer\Main"
    values = [(inet, "ProxyEnable", "REG_DWORD", "1"), (inet, "ProxyServer", "REG_SZ", f"http={args.proxy}"),
              (inet, "ProxyOverride", "REG_SZ", "<local>"), (main_key, "Start Page", "REG_SZ", "http://www.aol.com/")]
    for view in ("/reg:32", "/reg:64"):
        for key, name, kind, data in values:
            subprocess.run([args.wine, "reg", "add", key, "/v", name, "/t", kind, "/d", data, "/f", view],
                           env=env, check=True, capture_output=True)
    # crash-safe Wine Gecko settings (no JavaScript JITs under x86 emulation), every installed version
    import glob
    for d in glob.glob(str(Path(args.wine_prefix).expanduser() / "drive_c/windows/*/gecko/*/wine_gecko/defaults/pref")):
        shutil.copy2(HERE / "gecko-aol.js", d)
    print(f"AOL's browser now renders http pages through WRP at {args.proxy} (restart AOL).")
    print("WRP must be running there: python start.py on the server, or on this machine.")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch")
    f.add_argument("--iso", default="aol40.iso")
    f.add_argument("--out", default="aol40-cd")
    c = sub.add_parser("configure")
    c.add_argument("dir")
    c.add_argument("--host", default="localhost")
    c.add_argument("--port", type=int, default=5190)
    c.add_argument("--wine", action="store_true", help="also apply the Wine work-arounds")
    c.add_argument("--revert", action="store_true")
    w = sub.add_parser("web")
    w.add_argument("--wine-prefix", required=True)
    w.add_argument("--proxy", default="127.0.0.1:8098")
    w.add_argument("--wine", default="wine", help="wine command (e.g. a wrapper script)")
    args = ap.parse_args()
    {"fetch": fetch, "configure": configure, "web": web}[args.cmd](args)


if __name__ == "__main__":
    main()
