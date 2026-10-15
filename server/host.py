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
    mods, handlers = [], {}
    for info in pkgutil.iter_modules(services.__path__):
        mod = importlib.import_module(f"services.{info.name}")
        mods.append(mod)
        handlers.update(getattr(mod, "TOKENS", {}))
    MODULES[:] = mods
    HANDLERS.clear()
    HANDLERS.update(handlers)


def on_data(link, token: bytes, stream_id: int, body: bytes):
    handler = HANDLERS.get(token)
    if handler:
        handler(link, stream_id, body)
    else:
        # never leave the client hourglassed waiting for a reply we can't give
        print(f"      (no handler for token {token!r})")
        from fdo.codec import atom, stream
        link.send_stream(stream(atom("uni_wait_off")))


def on_disconnect(link):
    for mod in MODULES:
        hook = getattr(mod, "on_disconnect", None)
        if hook:
            hook(link)


load()
