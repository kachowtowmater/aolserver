"""AOL 4.0 (and some 3.0 menu) tokens that map onto existing features."""
import os

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


# The World Wide Web goes through the host (services/webview.py draws it in an AOL window): the
# client's address bar, Go to the Web and toolbar Home are pushed at sign-on in versions that hand
# the address to the host instead of opening the client's own IE window (tools/make_forms40.py).
# Under Wine that IE window is Wine Gecko, which only works on its first thread and crashes
# navigating under x86 emulation.  With AOL_WEBVIEW=0 the IE window is used again; Wine clients
# then also get a single, non-closeable IE window (AOL_WINE_BROWSER_FIX=0 turns that off too).
WINE_BROWSER_FIX = os.environ.get("AOL_WINE_BROWSER_FIX", "1") != "0"


def push_form(link, gid_bytes: bytes, fdo_name: str):
    """Store a form in the client's database (as AOL's host did for form updates)."""
    from fdo.codec import atom, stream
    from .util import render
    rec = render(fdo_name)
    link.send_stream(stream(atom("idb_start_obj", b"a"), atom("idb_atr_globalid", gid_bytes),
                            *[atom("idb_append_data", rec[i:i + 900]) for i in range(0, len(rec), 900)],
                            atom("idb_end_obj")))


def sign_on_forms(link):
    """tools/make_forms40.py builds these from the client's own forms."""
    def gid_bytes(name):  # form ids are two-part: type-id
        t, i = (int(p) for p in name.split("-"))
        return bytes([0, t]) + i.to_bytes(2, "big")
    from . import webview
    forms = [("41-19051", "addr40"), ("41-27066", "menu40"), ("41-18931", "nav40")]
    if webview.ENABLED:
        forms.append(("32-4705", "wwwhost40"))  # the IE window never opens: its address goes to us
    elif WINE_BROWSER_FIX:
        forms.append(("32-4705", "www40"))
    for gid, form in forms:
        push_form(link, gid_bytes(gid), form)


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
