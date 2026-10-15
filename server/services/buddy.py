"""Buddy List: who's online, updated live, with the 4.0 buddy-in/out sounds.

Opened by keyword BUDDY or AOL 4.0's menu (k1 17-22746 view, 17-21293 setup).
Window entries send zA items; Setup sends zB (add) / zX (remove).
"""
from fdo.codec import atom, stream

import state

from . import screens, store
from .util import name_of, request


def _online(name: str) -> bool:
    from . import regulars
    return store.key(name) in state.ONLINE or name in regulars.PERSONAS


def show(link, rid=None, refresh=False):
    from .areas import _item
    me = name_of(link)
    names = store.buddies(me)
    on = [n for n in names if _online(n)]
    if refresh and not link.session.get("buddy_open"):
        return
    link.session["buddy_open"] = True
    rows = [(n, _item(link, ("buddy", n))) for n in on]
    intro = f"Buddies ({len(on)}/{len(names)}) online.  Double-click a buddy to send an Instant Message."
    if not names:
        intro = "Your Buddy List is empty.  Click Setup to add the screen names of your friends."
    buttons = [("Setup", '          sm_send_token_arg <"zA", %d>' % _item(link, ("buddy_setup",)))]
    link.send_stream(screens.list_window("Buddy List Online", intro, rows, buttons, response_id=rid, width=24,
                                         window="buddylist"))


def setup(link, rid=None):
    names = store.buddies(name_of(link))
    link.send_stream(screens.form_window(
        "Buddy List Setup", "Your buddies: " + (", ".join(names) or "(none)") +
        ".  Type a screen name and click Add Buddy.", [("Screen Name:", 14, "")], "Add Buddy", "zB",
        response_id=rid, window="buddysetup"))


def add(link, stream_id, body):
    who = (request(body)["texts"] or [""])[0].strip()
    if who:
        store.add_buddy(name_of(link), who)
    setup(link)
    show(link, refresh=True)


def buddy_im(link, name: str):
    """Double-click: open the client's own Send Instant Message form, To: preset."""
    link.send_stream(stream(atom("uni_invoke_no_context", bytes([0x20, 0x00, 0xe1])), atom("uni_wait_off")))


def announce(name: str, online: bool):
    """Tell everyone who has `name` on their list; play buddyin/buddyout (4.0 ships the WAVs)."""
    for owner in store.watchers(name):
        link = state.ONLINE.get(owner)
        if link and link.session.get("name", "").lower() != name.lower():
            link.send_stream(stream(atom("async_playsound_dammit", b"buddyin.wav" if online else b"buddyout.wav")))
            show(link, refresh=True)


TOKENS = {b"zB": add}
