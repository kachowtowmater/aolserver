"""Members menu: profiles (ji get, jr edit), Locate Member Online (Ln), Member Directory."""
import state

from . import screens, store
from .util import alert, name_of, request, run_bg


def get_profile(link, stream_id, body):
    who = (request(body)["texts"] or [body.decode("latin1", "replace")])[0].strip()
    regular = _regular_profile(who)
    p = store.get_profile(who)
    if not (p or regular or store.account(who)):
        return alert(link, f"{who} is not a member, or does not have a profile.")
    rows = regular or ([(lbl, p[f] or "") for lbl, f in zip(store.PROFILE_LABELS, store.PROFILE_FIELDS)] if p else [])
    text = f"Screen Name:  {who}\r" + "\r".join(f"{lbl}:  {v}" for lbl, v in rows if v)
    if not rows:
        text += "\r(No profile information.)"
    link.send_stream(screens.text_window("Member Profile", text, width=52, height=12))


def _regular_profile(who):
    from . import regulars
    for name, persona in regulars.PERSONAS.items():
        if name.lower() == who.lower().replace(" ", ""):
            return [("Hobbies", persona), ("Location", "People Connection"), ("Quote", "brb!")]
    return None


def edit_profile(link, stream_id, body):
    p = store.get_profile(name_of(link))
    fields = [(lbl + ":", 30, (p[f] if p else "") or "") for lbl, f in zip(store.PROFILE_LABELS, store.PROFILE_FIELDS)]
    link.send_stream(screens.form_window("Edit Your Online Profile",
                                         "Your profile lets other members learn about you.", fields, "Update", "zP"))


def save_profile(link, stream_id, body):
    store.set_profile(name_of(link), request(body)["texts"])
    alert(link, "Your profile has been updated.")


def locate(link, stream_id, body):
    who = (request(body)["texts"] or [""])[0].strip()
    target = state.ONLINE.get(store.key(who))
    if not target:
        from . import regulars
        for room_name, room in state.ROOMS.items():
            if any(m.session.get("name", "").lower() == who.lower() for m in room["slots"]):
                return alert(link, f'{who} is online and in the chat room "{room_name}".')
        return alert(link, f"{who} is not currently signed on.")
    room = target.session.get("room")
    alert(link, f'{who} is online and in the chat room "{room}".' if room else f"{who} is online, but not in a chat room.")


def directory(link, rid=None):
    link.send_stream(screens.input_window("Member Directory", "Search for:", "Search", "zD",
                                          "Find members by screen name, hobbies, location or occupation.",
                                          response_id=rid))


def search_directory(link, stream_id, body):
    from .areas import _item
    q = (request(body)["texts"] or [""])[0].strip()
    rows = store.search_profiles(q)
    entries = [(f"{r['name']:<12} {(r['location'] or '')[:20]:<20} {(r['hobbies'] or '')[:30]}",
                _item(link, ("profile", r["name"]))) for r in rows]
    link.send_stream(screens.list_window(f"Member Directory: {q}", f"{len(entries)} members found.", entries, width=60))


TOKENS = {b"ji": get_profile, b"jr": edit_profile, b"zP": save_profile, b"Ln": locate, b"zD": search_directory}
