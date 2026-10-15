"""Instant Messages.

Client -> host:  iS  send an IM (To + message from form 32-225, or the
                     Respond box of the received-IM window 32-223)
                 iO  "Available?" -- is the screen name online?
Host -> client:  the client's own "Instant Message Received" form 32-223,
                 one window per conversation (man_preset_gid gives each
                 conversation its own global ID so later IMs append to it).
"""
import state

from .util import alert, atoms, name_of, render


def _fields(body: bytes) -> list[str]:
    """iS carries raw de_get_data text fields; tolerate both atom and raw forms."""
    parsed = [a.args for a in atoms(body) if a.name == "de_data"]
    if parsed:
        return [p.rstrip(b"\0").decode("latin1") for p in parsed]
    return [p.decode("latin1") for p in body.replace(b"\r", b"\0").split(b"\0") if p.strip()]


def _conversation_gid(recipient_link, sender: str) -> str:
    convs = recipient_link.session.setdefault("im_windows", {})
    if sender.lower() not in convs:
        convs[sender.lower()] = 1 + len(convs)
    return f"50-0-{convs[sender.lower()]}"


def deliver(sender: str, recipient: str, text: str) -> bool:
    target = state.ONLINE.get(recipient.lower().replace(" ", ""))
    if not target:
        return False
    target.send_stream(_im_stream(target, sender, text))
    return True


def _im_stream(link, sender, text, partner=None):
    """`partner` picks the conversation window (defaults to the sender's)."""
    from . import art
    form = "im40" if art.version(link) == "40" else "im"
    if form == "im":  # 3.0 shows 4.0's HTML IMs as plain text
        import re
        text = re.sub(r"<[^>]*>", "", text).replace("\x7f", " ")
    partner = partner or sender
    return render(form, gid=_conversation_gid(link, partner), sender=sender, partner=partner, text=text)


def send_im(link, stream_id, body):
    fields = _fields(body)
    print(f"      iS fields: {fields!r}")
    if len(fields) < 2:
        return
    to, text = fields[0].strip(), fields[-1]
    me = name_of(link)
    from . import regulars
    regular = regulars.regular_named(to)
    if regular and not state.ONLINE.get(to.lower().replace(" ", "")):
        link.send_stream(_im_stream(link, me, text, partner=regular))
        return regulars.im_to_regular(link, regular, text)
    if not deliver(me, to, text):
        alert(link, f"{to} is not currently signed on.")
        return
    # echo into the sender's own conversation window, like AOL 3.0
    deliver_to_self = state.ONLINE.get(me.lower().replace(" ", ""))
    if deliver_to_self is link:
        link.send_stream(_im_stream(link, me, text, partner=to))


def available(link, stream_id, body):
    fields = _fields(body)
    who = fields[0].strip() if fields else ""
    from . import regulars
    online = who.lower().replace(" ", "") in state.ONLINE or bool(regulars.regular_named(who))
    alert(link, f"{who} is online and able to receive Instant Messages." if online
          else f"{who} is not currently signed on.")


TOKENS = {b"iS": send_im, b"iO": available, b"is": send_im}  # 'is' = AOL 4.0
