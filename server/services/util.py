"""Helpers shared by services."""
from fdo import codec
from fdo.compiler import FORMS as FORMS_DIR, compile_fdo, fdo_text, render  # noqa: F401


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
    link.send_stream(codec.stream(codec.atom("async_alert", b"\x01" + fdo_text(text).encode("latin1"))))


def name_of(link) -> str:
    return link.session.get("name", "Guest")
