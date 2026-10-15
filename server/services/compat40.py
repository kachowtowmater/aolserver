"""AOL 4.0 (and some 3.0 menu) tokens that map onto existing features."""
from . import areas, chat, members
from .util import alert, request


def report(link, stream_id, body):
    """ir: the IM window's 'Notify AOL' button."""
    alert(link, "Thank you.  Your report has been sent to AOL's Community Action Team.")


def member_info(link, stream_id, body):
    """id: double-click on a name in a chat room's people list."""
    members.get_profile(link, stream_id, body)


def chat_help(link, stream_id, body):
    areas.info_area(link, "aol live")


def no_reply(link, stream_id, body):
    """Requests the client fires and forgets (it never waits on an answer)."""


def fetch_form(link, stream_id, body):
    """f2: the client was told to open a form it doesn't have (one AOL's host used to send on
    demand).  The body is the form's global id -- 4 bytes, or just its 2-byte number for the
    40-/32- forms 4.0's menus name: open what we have for it."""
    from .util import gid_arg
    from fdo.codec import atom, stream
    if len(body) >= 4:
        gid = gid_arg(body[:4])
    else:
        n = str(int.from_bytes(body[:2], "big")) if len(body) == 2 else "?"
        gid = next((g for g in areas.GID_AREAS if g.rsplit("-", 1)[-1] == n), n)
    print(f"      f2 form request {gid} ({body.hex(' ')})")
    area = areas.GID_AREAS.get(gid)
    if area:
        return areas.open_area(link, area)
    areas._note_unmapped("form", gid)
    areas.open_area(link, "what's hot")


TOKENS = {
    b"f2": fetch_form,
    b"p#": no_reply,              # Mail Preferences: fetch host-side mail settings (none kept)
    b"t1": areas.by_gid,          # 4.0 'go to area by GID'
    b"AE": chat.chat_line,        # 4.0 chat send from some room forms
    b"ir": report,
    b"id": member_info,
    b"L&": chat.list_rooms,       # room lists (member rooms / categories)
    b"LB": chat.list_rooms,
    b"cH": chat_help,
}
