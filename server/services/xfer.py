"""File downloads into the AOL 3.0 client (AOLXFER.AOL). Protocol: ../../re/NOTES.md "File transfer".

host  aT  xfer_start_object <0> ... xfer_end_object   -> client shows the Download Manager Save dialog
client eJ 00 <chosen full path>   (ej for a mail attachment; eK = user cancelled)
host  tf  <flags 0x20><size 3B LE><15 x 00><file name>\\x90<done token 2B>\\0
client xG                         (file opened; xA ff = open failed)
host  F7 <data>... F8 <data>      (F8/FF ask for an xG ack, F7 doesn't) ... F9 <last data>
client <done token>               (file closed, File's Done played)

Data bytes '[' (RLE) and ']' (escape) are escaped as ']' + (b ^ 0x55); everything else is literal.
"""
import os
import re
import time

from fdo.codec import atom, stream, u8, u32

from .util import alert

PACKET = 880      # escaped data bytes per packet (frames top out near 0x3fa)
WINDOW = 8        # packets per xG ack
DONE_TOKEN = b"xD"
EPOCH_1980 = 315532800


def _session(link):
    return link.session.get("xfer")


def _safe_name(name: str) -> str:
    base = re.split(r"[\\/]", name)[-1]
    base = re.sub(r"[^A-Za-z0-9._ ()-]", "_", base).strip(" .") or "FILE.BIN"
    if len(base) > 60:
        stem, ext = os.path.splitext(base)
        base = stem[:60 - len(ext)] + ext
    return base


def _cstr(text: str) -> bytes:
    return text.encode("latin1", "replace") + b"\0"


def offer(link, name: str, data: bytes, title: str | None = None, library: str = "AOL Revival",
          created: float | None = None):
    """Offer `data` as a download: the client pops its Save dialog, then pulls the file."""
    if _session(link) and _session(link).get("stage") in ("open", "data"):
        return alert(link, "A file transfer is already in progress.")
    if len(data) >= 1 << 24:  # tf carries the size in 3 bytes
        return alert(link, "That file is too large to download online.")
    name = _safe_name(name)
    rid = (int(time.time() * 10) & 0x7FFFFFFF) or 1  # a fresh id, so the DL manager never says "already downloaded"
    link.session["xfer"] = {"name": name, "data": data, "rid": rid, "stage": "offered", "pos": 0, "t0": time.time()}
    created = int((created or time.time()) - EPOCH_1980)
    link.send_stream(stream(
        atom("uni_wait_off"),
        atom("xfer_start_object", u8(0)),            # 0 = Download Now
        atom("xfer_atr_request_id", u32(rid)),
        atom("xfer_atr_title", _cstr((title or name)[:32])),
        atom("xfer_atr_file_size", u32(len(data))),
        atom("xfer_atr_file_name", _cstr(name)),
        atom("xfer_atr_create_date", u32(max(created, 0))),
        atom("xfer_bool_mail", u8(0)),
        atom("xfer_atr_library", _cstr(library[:19])),
        atom("xfer_end_object"),
    ))
    print(f"      xfer: offered {name} ({len(data)} bytes) rid={rid}")


def _next_packet(x) -> bytes:
    """Escaped bytes for the next packet, advancing x['pos']."""
    data, pos = x["data"], x["pos"]
    out = bytearray()
    while pos < len(data) and len(out) < PACKET:
        b = data[pos]
        out += bytes([0x5D, b ^ 0x55]) if b in (0x5B, 0x5D) else bytes([b])
        pos += 1
    x["pos"] = pos
    return bytes(out)


def _send_window(link, x):
    for i in range(WINDOW):
        body = _next_packet(x)
        if x["pos"] >= len(x["data"]):
            link.send_data_raw(b"F9", body)
            x["stage"] = "sent"
            print(f"      xfer: {x['name']} all {len(x['data'])} bytes sent")
            return
        link.send_data_raw(b"F8" if i == WINDOW - 1 else b"F7", body)


def chosen(link, stream_id, body):
    """eJ/ej: the member picked where to save. Payload: 00 + full DOS path."""
    x = _session(link)
    raw = bytes([(stream_id or 0) & 0xFF]) + body if stream_id is not None else b""
    path = raw.split(b"\0")[0].decode("latin1")
    print(f"      xfer: save to {path!r}")
    if not x or x["stage"] != "offered":
        return
    # 3.0 (eJ) sends the full file path; 4.0 (uJ) sends just the folder
    last = path.replace("/", "\\").rsplit("\\", 1)[-1]
    name = _safe_name(path) if path and "." in last else x["name"]
    x.update(stage="open", saved_as=path or name)
    size = len(x["data"])
    hdr = bytes([0x20]) + size.to_bytes(4, "little")[:3] + bytes(15)  # 0x20 = show the progress dialog
    link.send_data_raw(b"tf", hdr + name.encode("latin1")[:0x50] + b"\x90" + DONE_TOKEN + b"\0")


def cancelled(link, stream_id, body):
    x = link.session.pop("xfer", None)
    print(f"      xfer: cancelled {x and x['name']}")


def go(link, stream_id, body):
    """xG: file is open / window received, send more."""
    x = _session(link)
    if not x or x["stage"] not in ("open", "data"):
        return
    x["stage"] = "data"
    _send_window(link, x)


def failed(link, stream_id, body):
    """xA: client aborted (open/write error or Cancel in the File Transfer dialog)."""
    x = link.session.pop("xfer", None)
    print(f"      xfer: client aborted {x and x['name']} ({body.hex()})")


def done(link, stream_id, body):
    x = link.session.pop("xfer", None)
    if x:
        print(f"      xfer: {x['name']} done in {time.time() - x['t0']:.1f}s -> {x.get('saved_as')}")


def readme(link, stream_id=0, body=b""):
    """Keyword README: a small server-generated text file, to try downloads."""
    from .util import name_of
    text = (f"Welcome to America Online, {name_of(link)}!\r\n\r\n"
            "This file was sent by the AOL revival host using the original\r\n"
            "AOL 3.0 file transfer protocol.  [Brackets] survive the trip.\r\n\r\n"
            f"Sent {time.strftime('%A, %B %d, %Y %I:%M %p')}.\r\n")
    offer(link, "README.TXT", text.encode("latin1"), "Welcome README")


# ---------- Internet Archive (File Search) ----------

MAX_SIZE = 15_000_000  # tf carries the size in 3 bytes (<= 16,777,215)
# what a 1997 member would want to download, best first
PREFERRED = (".zip", ".exe", ".com", ".lzh", ".arj", ".txt", ".doc", ".wri", ".hlp", ".mid", ".wav", ".gif",
             ".bmp", ".jpg", ".pdf", ".mp3")
SKIP = ("_thumb.jpg", "__ia_thumb.jpg", "_meta.xml", "_files.xml", "_reviews.xml", "_meta.sqlite", ".torrent")


def archive_files(ident: str) -> dict | None:
    """{'title', 'files': [{'name', 'size', 'md5'}] best first} -- files small enough to send."""
    import json
    from .content import _get
    meta = json.loads(_get(f"https://archive.org/metadata/{ident}", timeout=15))
    files = []
    for f in meta.get("files", []):
        name, size = f.get("name", ""), int(f.get("size") or 0)
        ext = os.path.splitext(name.lower())[1]
        if not 0 < size <= MAX_SIZE or name.lower().endswith(SKIP) or ext not in PREFERRED:
            continue
        files.append({"name": name, "size": size, "md5": f.get("md5"), "rank": PREFERRED.index(ext),
                      "original": f.get("source") == "original"})
    files.sort(key=lambda f: (f["rank"], not f["original"], f["size"]))
    return {"title": (meta.get("metadata") or {}).get("title", ident), "files": files}


def archive_download(link, ident: str, name: str | None = None):
    """Fetch one file of an Internet Archive item (the best pick when name is None) and offer it."""
    import hashlib
    import urllib.parse
    from .content import _get
    from .util import run_bg

    def work():
        info = archive_files(ident)
        pick = next((f for f in info["files"] if f["name"] == name), None) if name else \
            (info["files"][0] if info["files"] else None)
        if not pick:
            return info, None, None
        data = _get(f"https://archive.org/download/{ident}/{urllib.parse.quote(pick['name'])}", timeout=180)
        if pick.get("md5") and hashlib.md5(data).hexdigest() != pick["md5"]:
            raise IOError(f"md5 mismatch on {pick['name']}")
        return info, pick, data

    def finish(result):
        info, pick, data = result
        if info is None:
            return alert(link, "The file library is temporarily unavailable.  Please try again later.")
        if not pick:
            return alert(link, "Sorry, this item has no file small enough to download.")
        offer(link, pick["name"], data, info["title"], "Internet Archive")

    def guarded():
        try:
            return work()
        except Exception as e:
            print(f"      xfer: archive {ident} failed: {e}")
            return None, None, None
    run_bg(guarded, finish)


def ad_request(link, stream_id, body):
    """aS: AOL 4.0's File Transfer window asking for an ad banner -- show none."""


TOKENS = {b"aS": ad_request, b"uJ": chosen, b"eJ": chosen, b"ej": chosen, b"eK": cancelled, b"xG": go, b"xA": failed, DONE_TOKEN: done}
