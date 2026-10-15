"""Service logic: what the host does with each DATA token from the client.

Hot-reloaded by server.py on change. `link` is the server.Link for the
connection; keep per-connection state in link.session.
"""
from fdo.codec import atom, gid, s, stream, u8, u16, u32  # noqa: F401
from fdo.compiler import render


def on_data(link, token: bytes, stream_id: int, body: bytes):
    handler = HANDLERS.get(token)
    if handler:
        handler(link, stream_id, body)
    else:
        print(f"      (no handler for token {token!r})")


def screen_name(body: bytes) -> str:
    """First de_data in the sign-on form stream is the screen name."""
    from fdo import codec
    for a in codec.decode(body):
        if a.name == "de_data":
            return a.args.decode("latin1").strip()
    return "Guest"


def sign_on(link, stream_id, body):
    """Dd: the Welcome form's screen name (and password) - accept everyone for now.

    Success = tell every client tool we're online (async_online, which the FDO
    manual says belongs on the Welcome form) and run the client's own
    "went online" script 32-296 (enables Sign Off, toolbar, Welcome sound).
    """
    name = link.session["name"] = screen_name(body)
    link.send_stream(stream(
        atom("async_online"),
        atom("uni_invoke_local", gid("32-296")),
    ))
    link.send_stream(render("welcome", name=name))


HANDLERS = {
    b"Dd": sign_on,
}
