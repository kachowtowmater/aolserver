"""Helpers shared by services."""
from fdo import codec
from fdo.compiler import FORMS as FORMS_DIR, compile_fdo, fdo_text, plain, render  # noqa: F401


def atoms(body: bytes):
    try:
        return codec.decode(body)
    except Exception:
        return []


def de_strings(body: bytes) -> list[str]:
    """Text fields a client form sent (de_data atoms, in order)."""
    return [a.args.rstrip(b"\0").decode("latin1") for a in atoms(body) if a.name == "de_data"]


def gid_arg(raw: bytes) -> str:
    """4-byte GID as sent in de_data/dod_gid -> '40-4408' or '1-0-1329'."""
    t, sub, i = raw[0], raw[1], int.from_bytes(raw[2:4], "big")
    return f"{t}-{sub}-{i}" if t else f"{sub}-{i}"


def alert(link, text: str):
    # raw atom (not FDO source), so plain Latin-1 text -- no \x escapes
    link.send_stream(codec.stream(codec.atom("async_alert", b"\x01" + plain(text).encode("latin1"))))


def name_of(link) -> str:
    return link.session.get("name", "Guest")


def run_bg(work, done):
    """Run blocking work (network) in a thread, then done(result) on the event loop."""
    import asyncio
    import traceback
    loop = asyncio.get_running_loop()
    fut = loop.run_in_executor(None, work)

    def finish(f):
        try:
            done(f.result())
        except Exception:
            traceback.print_exc()
    fut.add_done_callback(finish)


def request(body: bytes) -> dict:
    """Common request fields: response id, GID (4-byte de_data) and text de_data."""
    out = {"response_id": None, "gid": None, "texts": []}
    for a in atoms(body):
        if a.name == "man_set_response_id":
            out["response_id"] = a.args
        elif a.proto == 0 and a.num == 14 and len(a.args) == 3:  # buf_add_atom_data <gid>
            out["gid"] = f"{a.args[0]}-{int.from_bytes(a.args[1:], 'big')}"
        elif a.name == "de_data":
            if len(a.args) == 4 and not all(32 <= c < 127 for c in a.args):
                out["gid"] = gid_arg(a.args)
            else:
                out["texts"].append(a.args.rstrip(b"\0").decode("latin1"))
    if not out["texts"] and body and all(32 <= c < 127 or c in (0, 13) for c in body):
        out["texts"] = [body.strip(b"\0\r").decode("latin1")]
    return out
