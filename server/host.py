"""Token dispatcher. Hot-reloaded (with services/*) by server.py on change."""
import importlib
import pkgutil
import sys

import services

MODULES = []
HANDLERS = {}


def load():
    """(Re)import every service fresh, then swap the handler table in one go,
    so a broken edit never leaves a half-loaded host."""
    import fdo.compiler
    importlib.reload(fdo.compiler)  # escaping/compile helpers change often
    for name in [m for m in sys.modules if m.startswith("services.")]:
        del sys.modules[name]
        # `from . import x` reads the package attribute first, so drop that too
        services.__dict__.pop(name.split(".", 1)[1], None)
    mods, handlers = [], {}
    for info in pkgutil.iter_modules(services.__path__):
        mod = importlib.import_module(f"services.{info.name}")
        mods.append(mod)
        handlers.update(getattr(mod, "TOKENS", {}))
    MODULES[:] = mods
    HANDLERS.clear()
    HANDLERS.update(handlers)


PRE_SIGNON = {b"Dd", b"zS", b"fh", b"Wh"}


def on_data(link, token: bytes, stream_id: int, body: bytes):
    if token not in PRE_SIGNON and "name" not in link.session:
        print(f"      (ignoring {token!r} before sign-on)")
        return
    body = _reassemble(link, token, stream_id, body)
    if body is None:
        return
    handler = HANDLERS.get(token)
    if handler:
        handler(link, stream_id, body)
    else:
        # never leave the client hourglassed waiting for a reply we can't give
        print(f"      (no handler for token {token!r})")
        from fdo.codec import atom, stream
        link.send_stream(stream(atom("uni_wait_off")))


def _reassemble(link, token: bytes, stream_id: int, body: bytes):
    """AOL 4.0 splits a long stream (an IM, a mail) over several packets with the same token and
    stream id: hold the pieces until the one carrying uni_end_stream arrives, then hand on the whole."""
    from fdo import codec
    parts = link.session.setdefault("partial", {})
    key = (token, stream_id)
    try:
        names = [a.name for a in codec.decode(body)]
    except Exception:
        names = []
    if key in parts:
        parts[key] += body
        if "uni_end_stream" not in names:
            return None
        return parts.pop(key)
    if names and names[0] == "uni_start_stream" and "uni_end_stream" not in names and stream_id:
        parts[key] = body
        return None
    return body


def on_disconnect(link):
    for mod in MODULES:
        hook = getattr(mod, "on_disconnect", None)
        if hook:
            hook(link)


load()
