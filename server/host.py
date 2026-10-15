"""Token dispatcher. Hot-reloaded (with services/*) by server.py on change."""
import importlib
import pkgutil

import services

MODULES = []
HANDLERS = {}


def load():
    MODULES.clear()
    HANDLERS.clear()
    for info in pkgutil.iter_modules(services.__path__):
        mod = importlib.import_module(f"services.{info.name}")
        mod = importlib.reload(mod)
        MODULES.append(mod)
        HANDLERS.update(getattr(mod, "TOKENS", {}))


def on_data(link, token: bytes, stream_id: int, body: bytes):
    handler = HANDLERS.get(token)
    if handler:
        handler(link, stream_id, body)
    else:
        print(f"      (no handler for token {token!r})")


def on_disconnect(link):
    for mod in MODULES:
        hook = getattr(mod, "on_disconnect", None)
        if hook:
            hook(link)


load()
