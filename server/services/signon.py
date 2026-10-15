"""Sign-on, new-member registration, and screen-name accounts.

Dd carries the Welcome form: screen name (de_data 1) and password (de_data 2).
  * "New User" -> online with the New Member sign-up form (token zS); on
    success we async_storename/async_storepassword so the name shows up in the
    client's own Select Screen Name list next time, and switch the session.
  * a known name must give its password; "Guest" sign-ons send name+password too.
"""
import re
import time

import state
from fdo.codec import atom, gid, stream

from . import screens, store
from .util import alert, de_strings, render, request

NEW_USER = "new user"
NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9 ]{2,9}$")


STOCK_NAMES = [(b"New User", b"5555555555"), (b"Guest", b"7777777777"), (b"New Local#", b"5555555550")]


def store_screen_name(link, name: str):
    """The 3.0 client has no async_storename (atoms stop at 39); its Select Screen
    Name list is IDB record 20-0-16: count, then per name <name:10>\0<10 digits>\0.
    Rewrite it with the new name first, followed by the stock entries."""
    entries = [(name.encode("latin1"), b"%010d" % (int(time.time()) % 10**10))] + STOCK_NAMES
    rec = bytes([len(entries)]) + b"".join(n.ljust(10) + b"\0" + d + b"\0" for n, d in entries)
    link.send_stream(stream(atom("idb_start_obj", b"b"), atom("idb_atr_globalid", bytes([20, 0, 0, 16])),
                            atom("idb_append_data", rec), atom("idb_end_obj"), atom("uni_wait_off")))


def go_online(link, name: str):
    link.session["name"] = name
    link.session["signed_on"] = time.time()
    state.ONLINE[store.key(name)] = link
    from . import buddy, gateway
    gateway.ensure_polling()
    if name.lower() != NEW_USER:
        buddy.announce(name, True)
    link.send_stream(stream(atom("async_online"), atom("uni_invoke_local", gid("32-296"))))
    if name.lower() != NEW_USER:
        from . import art, compat40
        art.preload(link)
        if art.version(link) == "40":
            compat40.sign_on_forms(link)


def sign_on(link, stream_id, body):
    fields = de_strings(body)
    name = (fields[0].strip() if fields else "") or "Guest"
    password = fields[1].strip() if len(fields) > 1 else ""
    if name.lower() == NEW_USER:
        go_online(link, "New User")
        return new_member_form(link)
    acct = store.account(name)
    if acct and not store.check_password(name, password):
        alert(link, "Incorrect password.  Please check your password and try again.")
        return link.send_stream(stream(atom("async_force_off")))
    if not acct:
        if not password or not NAME_RE.match(name):
            alert(link, f'The screen name "{name}" is not registered.  Sign on as New User to create one.')
            return link.send_stream(stream(atom("async_force_off")))
        store.create_account(name, password)
    if store.key(name) in state.ONLINE and state.ONLINE[store.key(name)] is not link:
        old = state.ONLINE[store.key(name)]
        alert(old, "You have been signed off because this screen name signed on from another computer.")
        old.writer.close()
    store.touch(name)
    go_online(link, acct["name"] if acct else name)
    welcome(link)


def welcome(link):
    from . import areas, art, content, mail
    from .util import run_bg
    if art.version(link) == "40":  # 4.0's own Welcome screen; it asks us for today's content
        from . import welcome40
        welcome40.open_window(link)
        return mail.got_mail(link)

    def done(heads):
        rows = [(h["title"], areas._item(link, ("article", h))) for h in (heads or [])[:6]]
        art.ensure_art(link, ["1-0-24836"])
        link.send_stream(screens.welcome_window(link.session["name"], store.unread(link.session["name"]), rows))
        mail.got_mail(link)
    run_bg(lambda: content.headlines("top", 6), done)


def new_member_form(link, problem: str = ""):
    intro = (problem + "  " if problem else "") + ("Welcome to America Online!  Choose a screen name (3 to 10 letters "
             "and numbers, starting with a letter) and a password of at least 4 characters.")
    link.send_stream(screens.form_window("New Member Sign Up", intro,
                                         [("Screen Name:", 12, ""), ("Password:", 12, ""), ("Retype Password:", 12, "")],
                                         "Continue", "zS", window="signup"))


def register(link, stream_id, body):
    vals = (request(body)["texts"] + ["", "", ""])[:3]
    name, pw, pw2 = vals[0].strip(), vals[1].strip(), vals[2].strip()
    if not NAME_RE.match(name):
        return new_member_form(link, f'"{name}" is not a valid screen name.')
    if name.lower() in (NEW_USER, "guest", "onlinehost") or store.account(name):
        return new_member_form(link, f'Sorry, the screen name "{name}" is already taken.')
    if len(pw) < 4 or pw != pw2:
        return new_member_form(link, "Your passwords did not match (or were shorter than 4 characters).")
    store.create_account(name, pw)
    state.ONLINE.pop(store.key(link.session.get("name", "")), None)
    store_screen_name(link, name)
    go_online(link, name)
    link.send_stream(screens.close_window("signup"))
    alert(link, f'Congratulations!  "{name}" is now your screen name.  It will appear in the Select Screen Name '
                "list on the Welcome screen next time you sign on.")
    welcome(link)


def sign_off(link, stream_id, body):
    """pE (Sign Off menu). XS is AOLASYNC's host-initiated sign-off: it broadcasts the
    offline notification (which hangs up through the client's own path, so SIGN ON AGAIN
    works), opens the Goodbye form 32-5438 and shows our message if non-empty."""
    from . import art
    art.ensure_form(link, "32-5438")
    link.send_data_raw(b"XS", b"\0")


def on_disconnect(link):
    name = link.session.get("name")
    if name and state.ONLINE.get(store.key(name)) is link:
        del state.ONLINE[store.key(name)]
        from . import buddy
        buddy.announce(name, False)


TOKENS = {b"Dd": sign_on, b"zS": register, b"pE": sign_off}
