"""Sign-on: the Welcome form sends Dd with screen name and password."""
import state
from fdo.codec import atom, gid, stream

from .util import de_strings, render


def sign_on(link, stream_id, body):
    fields = de_strings(body)
    name = (fields[0].strip() if fields else "") or "Guest"
    link.session["name"] = name
    link.session["signed_on"] = __import__("time").time()
    state.ONLINE[name.lower().replace(" ", "")] = link
    # async_online flips every client tool to "online"; 32-296 is the client's
    # own went-online script (Sign Off menu, toolbar, Welcome sound).
    link.send_stream(stream(atom("async_online"), atom("uni_invoke_local", gid("32-296"))))
    link.send_stream(render("welcome", name=name))
    from . import mail
    mail.got_mail(link)


def on_disconnect(link):
    name = link.session.get("name")
    key = name.lower().replace(" ", "") if name else None
    if key and state.ONLINE.get(key) is link:
        del state.ONLINE[key]


TOKENS = {b"Dd": sign_on}
