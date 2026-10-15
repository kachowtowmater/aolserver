"""Art for the client: preload what a form needs, and answer DOD (fh) requests.

The 3.0 client renders a form, hits a missing mat_art_id, sends `fh` and stalls
the form until the art shows up -- and we have not found a reply that resumes a
stalled form. So we never let it stall: before opening a form we push every art
record it references that the client lacks (idb_start_obj/idb_append_data/
idb_end_obj stores straight into the client's MAIN.IDX).

Art sources, in order: server/art/<gid>.bin (original AOL art harvested from
AOL CDs by tools/harvest_art.py), else a generated placeholder button.
"""
import json
from pathlib import Path

from fdo.codec import atom, stream

from . import gif
from .util import atoms, gid_arg

HERE = Path(__file__).resolve().parent.parent
ART = HERE / "art"
_CLIENTS = {v: json.loads((HERE / "data" / f).read_text())
            for v, f in (("30", "client_art.json"), ("40", "client_art40.json"))}
LOCAL = {v: set(c["local_art"]) for v, c in _CLIENTS.items()}
FORM = {v: c["forms"] for v, c in _CLIENTS.items()}


def version(link) -> str:
    """'40' for AOL 4.0 (sends '**' instead of CRCs over TCP), else '30'."""
    return "40" if getattr(link, "no_crc", False) else "30"
CHUNK = 700


def gid_bytes(name: str) -> bytes:
    t, sub, i = (int(p) for p in name.split("-"))
    return bytes([t, sub]) + i.to_bytes(2, "big")


def art_record(image: bytes, fmt: int) -> bytes:
    """Wrap a GIF (fmt 5) or BMP (fmt 2) in the AOL art header (40 bytes)."""
    total = 40 + len(image)
    head = (b"\x01\x00\x01\x00\x01\x00" + (total - 4).to_bytes(4, "little") + b"\x01\x00\x00\x00"
            + bytes([fmt, 2]) + bytes(6) + len(image).to_bytes(4, "little") + (0x24).to_bytes(4, "little")
            + bytes(6) + b"\x80\x00\x00\x00")
    return head + image


def record_for(name: str) -> bytes:
    path = ART / f"{name}.bin"
    if path.exists():
        return path.read_bytes()
    return art_record(gif.placeholder(), 5)


def push(link, name: str):
    data = record_for(name)
    parts = [atom("idb_start_obj", b"p"), atom("idb_atr_globalid", gid_bytes(name))]
    parts += [atom("idb_append_data", data[i:i + CHUNK]) for i in range(0, len(data), CHUNK)]
    parts.append(atom("idb_end_obj"))
    link.send_stream(stream(*parts))
    link.session.setdefault("art_sent", set()).add(name)


def ensure_art(link, gids):
    sent = link.session.setdefault("art_sent", set())
    local = LOCAL[version(link)]
    for name in gids:
        if name and name not in local and name not in sent:
            push(link, name)


def ensure_form(link, form_gid: str):
    """Push the art a local client form references before it is invoked."""
    ensure_art(link, FORM[version(link)].get(form_gid, []))


def dod_request(link, stream_id, body):
    req = {a.name: a.args for a in atoms(body)}
    raw = req.get("dod_gid", b"")
    if len(raw) == 4:
        name = gid_arg(raw)
        print(f"      DOD for {name} (form will stay stalled; preload it next time)")
        push(link, name)


TOKENS = {b"fh": dod_request}
