"""AOL 4.0's own Welcome screen (client form 32-6442, window 32-30), filled with today's content.

The window is the client's own form, sent by the host from forms/welcome40.fdo (the form's
source with two changes so it draws when the host sends it: the "Display Channels at Sign On"
check at the top is done here instead, and the window is built at top level -- the original
builds inside context 53 and leaves the display update to its caller).  As it opens it asks the
host for the day's content with K1 17-65227; the host answers by writing into its slots:
   17  "on AOL Today" feature (bullet 15 / banner 16)        40  today's date
   20  "Your Weather" (picture 19 / heading 41-42)
    3  "Top News Story" (bullet 21 / heading 14)
   24/26/28  more headlines (bullets 23/25/27)               30  caption by picture 29 (chat)
Everything else (Mailbox, AOL Channels, People Connection, the AOL Today note and the buttons
on the right) is the client's own art and actions.
"""
from datetime import datetime

from .util import fmt_time, compile_fdo, fdo_text, run_bg

WINDOW = "32-30"


def open_window(link):
    """Channels (4.0's "Display Channels at Sign On" default) with the Welcome screen on top;
    the Welcome screen then asks us (K1 17-65227) for the content."""
    from .util import render
    link.send_stream(compile_fdo("uni_start_stream <00x>\n  uni_invoke_local <32-5483>\n"
                                 "uni_end_stream <00x>"))
    link.send_stream(render("welcome40", title=f"Welcome, {link.session.get('name', '')}!"))


def _text(rel, text):
    return (f"  man_set_context_relative <{rel}>\n  man_clear_object\n"
            f'  man_append_data <"{fdo_text(text)}">\n  man_end_data\n  man_end_context\n')


def _link(rel, n):
    return (f"  man_set_context_relative <{rel}>\n  act_replace_select_action\n    <\n"
            f'    uni_start_stream_wait_on <00x>\n    sm_send_token_arg <"zA", {n}>\n    >\n'
            "  man_end_context\n")


def _short(text, n):
    """Cut at a word boundary so the small text boxes end cleanly."""
    return text if len(text) <= n else text[:n].rsplit(" ", 1)[0] + "..."


def fill(link, rid=None):
    from . import areas, content

    def work():
        return content.headlines("top", 8), content.headlines("entertainment", 3), content.quote("^DJI")

    def done(result):
        heads, feature, dow = result or ([], [], None)
        item = areas._item
        parts = [_text(40, fmt_time(datetime.now(), "%a, %b %-d"))]
        if feature:  # "on AOL Today": something fun from entertainment/tech
            f = feature[0]
            n = item(link, ("article", f))
            parts += [_text(17, _short(f["title"], 90)), _link(15, n), _link(16, n)]
        if heads:
            top = heads[0]
            n = item(link, ("article", top))
            parts += [_text(3, _short(top["title"], 50)), _link(21, n), _link(14, n)]
            for (bullet, view), h in zip(((23, 24), (25, 26), (27, 28)), heads[1:4]):
                n = item(link, ("article", h))
                parts += [_text(view, _short(h["title"], 70)), _link(bullet, n)]
        parts += [_text(20, "Your town's forecast")]
        wx = item(link, ("area", "weather"))
        parts += [_link(19, wx), _link(41, wx), _link(42, wx)]
        chat = "Chat now in People Connection!"
        if dow:
            chat = f"Dow {'up' if dow['change'] >= 0 else 'down'} {abs(dow['change']):,.0f}.  " + chat
        parts += [_text(30, chat)]
        pc = item(link, ("area", "people connection"))
        parts += [_link(29, pc)]
        rid_line = f"  man_set_response_id <{int.from_bytes(rid, 'big')}>\n" if rid else ""
        src = (f"uni_start_stream <00x>\n{rid_line}  man_set_context_globalid <{WINDOW}>\n" + "".join(parts)
               + "  man_end_context\n  man_update_display\n  uni_wait_off\nuni_end_stream <00x>")
        link.send_stream(compile_fdo(src))
    run_bg(work, done)
