"""People Connection chat rooms.

Client -> host:  CJ  enter People Connection (we place you in a lobby)
                 Aa  chat line typed in the room window (raw text)
Host -> client (AOLCHAT tool tokens, decoded from AOLCHAT.AOL):
                 AB  <screen name, 10 bytes><sep><text>   chat line
                 CA  <slot><screen name>                   member arrived
                 CB  <slot>                                member left
The room window itself is the client's own form 32-117 with the title preset.
"""
import state
from fdo.codec import atom, stream

from . import art
from .util import compile_fdo, fdo_text, FORMS_DIR, name_of

ROOM_SIZE = 23  # AOL lobbies held 23 people


def _room_of(link):
    return state.ROOMS.get(link.session.get("room"))


def _slot(room, link) -> int:
    return room["slots"][link]


def _send_line(link, who: str, text: str):
    name = who.encode("latin1")[:10].ljust(10, b" ")
    link.send_data_raw(b"AB", name + b"\x00" + text.encode("latin1", "replace") + b"\x00")


def broadcast_line(room, who: str, text: str):
    import time
    room.setdefault("history", []).append((who, text))
    del room["history"][:-40]
    room["last_line"] = time.time()
    for member in room["slots"]:
        _send_line(member, who, text)


def join(link, room_name: str):
    leave(link)
    room = state.ROOMS.setdefault(room_name, {"slots": {}, "next": 1})
    from . import regulars
    regulars.populate(room_name, room)
    regulars.ensure_running()
    slot = room["next"]
    room["next"] += 1
    room["slots"][link] = slot
    link.session["room"] = room_name
    me = name_of(link)
    users = "\n".join(f'  chat_add_user <"{fdo_text(name_of(m))}">' for m in room["slots"])
    form = "43-22783" if art.version(link) == "40" else "32-117"
    src = (FORMS_DIR / "chat_room.fdo").read_text().replace("{{room}}", fdo_text(room_name)).replace(
        "{{users}}", users).replace("{{form}}", form)
    art.ensure_form(link, form)
    link.send_stream(compile_fdo(src))
    for other in room["slots"]:
        if other is not link:
            other.send_data_raw(b"CA", bytes([slot]) + me.encode("latin1") + b"\x00")
    link.send_stream(stream(atom("uni_wait_off")))
    _send_line(link, "OnlineHost", f"*** You are in \"{room_name}\". ***")


def leave(link):
    room = _room_of(link)
    if not room:
        return
    slot = room["slots"].pop(link, None)
    link.session.pop("room", None)
    for other in room["slots"]:
        other.send_data_raw(b"CB", bytes([slot]))


def enter_people_connection(link, stream_id, body):
    n = 1
    while len(state.ROOMS.get(f"Lobby {n}", {}).get("slots", {})) >= ROOM_SIZE:  # regulars count too, like AOL
        n += 1
    join(link, f"Lobby {n}")


def chat_line(link, stream_id, body):
    room = _room_of(link)
    from .util import request
    texts = request(body)["texts"]
    text = (texts[0] if texts else "").strip()
    if room and text:
        broadcast_line(room, name_of(link), text)
        from . import regulars
        regulars.heard(link.session.get("room"), room, name_of(link), text)


def list_rooms(link, stream_id, body):
    """LP: People Connection room list (public rooms + who's in them)."""
    from . import areas, screens
    for name in ("Lobby 1", "Romance", "Thirtysomething", "Nineties Kids", "Tech Talk", "News Talk", "Sports Arena"):
        state.ROOMS.setdefault(name, {"slots": {}, "next": 1})
    rows = [(f"{name:<24}{len(r['slots']):>3}", areas._item(link, ("room", name)))
            for name, r in sorted(state.ROOMS.items(), key=lambda kv: (not kv[0].startswith("Lobby"), kv[0]))]
    link.send_stream(screens.list_window(
        "Public Rooms", "Double-click a room to go there.  Number of people in each room is shown.", rows,
        buttons=[("Create Room", '          sm_send_token_arg <"zA", %d>' % areas._item(link, ("create_room",)))],
        width=34, window="rooms"))


def create_room_form(link):
    from . import screens
    link.send_stream(screens.form_window("Create a Member Room", "Name your room (up to 20 characters).  "
                                         "Anyone can join it from the room list.", [("Room Name:", 20, "")],
                                         "Create", "zC", window="createroom"))


def create_room(link, stream_id, body):
    from .util import request
    name = " ".join((request(body)["texts"] or [""])[0].split())[:20]
    if not name:
        return
    state.ROOMS.setdefault(name, {"slots": {}, "next": 1, "regulars": []})
    join(link, name)


def on_disconnect(link):
    leave(link)


TOKENS = {b"CJ": enter_people_connection, b"Aa": chat_line, b"LP": list_rooms, b"zC": create_room}
