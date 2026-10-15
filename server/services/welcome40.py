"""AOL 4.0's own Welcome screen (client form 32-6442, window 32-30), filled with today's content.

The 4.0 client draws the Welcome window itself and, as it opens, asks the host for the day's
content with K1 17-65227.  The host answers by writing into the window's slots:
   17  top story (under the "Top Story" banner, link on 15/16)
   40  today's date
   20  markets line (picture 19 / title 41-42 go to Personal Finance)
    3  weather (title 21/14)
   24/26/28  three more headlines (bullets 23/25/27)
   30  People Connection caption (picture 29 joins the chat)
The fixed parts (mailbox, Channels, People Connection, AOL Today and the channel buttons on
the right) are the client's own and keep their original actions.
"""
from datetime import datetime

from .util import compile_fdo, fdo_text, run_bg

WINDOW = "32-30"


def open_window(link):
    """Show the client's own Welcome screen; it then asks us (K1 17-65227) for the content."""
    link.send_stream(compile_fdo("uni_start_stream <00x>\n  uni_invoke_local <32-6442>\n  uni_wait_off\n"
                                 "uni_end_stream <00x>"))


def _text(rel, text):
    return (f"  man_set_context_relative <{rel}>\n  man_clear_object\n"
            f'  man_append_data <"{fdo_text(text)}">\n  man_end_data\n  man_end_context\n')


def _link(rel, n):
    return (f"  man_set_context_relative <{rel}>\n  act_replace_select_action\n    <\n"
            f'    uni_start_stream_wait_on <00x>\n    sm_send_token_arg <"zA", {n}>\n    >\n'
            "  man_end_context\n")


def fill(link, rid=None):
    from . import areas, content

    def work():
        heads = content.headlines("top", 8)
        dow = content.quote("^DJI")
        return heads, dow

    def done(result):
        heads, dow = result or ([], None)
        item = areas._item
        parts = [_text(40, datetime.now().strftime("%A, %B %-d"))]
        if heads:
            top = heads[0]
            summary = (top.get("summary") or "")[:110]
            parts += [_text(17, top["title"] + (" -- " + summary if summary else "")[:200])]
            n = item(link, ("article", top))
            parts += [_link(15, n), _link(16, n)]
            for (bullet, view), h in zip(((23, 24), (25, 26), (27, 28)), heads[1:4]):
                n = item(link, ("article", h))
                parts += [_text(view, h["title"][:90]), _link(bullet, n)]
        if dow:
            arrow = "up" if dow["change"] >= 0 else "down"
            parts += [_text(20, f"Dow {arrow} {abs(dow['change']):,.0f} to {dow['price']:,.0f}")]
        fin = item(link, ("area", "finance"))
        parts += [_link(19, fin), _link(41, fin), _link(42, fin)]
        parts += [_text(3, "Today's forecast for your town: Keyword WEATHER")]
        wx = item(link, ("area", "weather"))
        parts += [_link(21, wx), _link(14, wx)]
        parts += [_text(30, "The lobbies are hopping. Chat now in People Connection!")]
        pc = item(link, ("area", "people connection"))
        parts += [_link(29, pc)]
        rid_line = f"  man_set_response_id <{int.from_bytes(rid, 'big')}>\n" if rid else ""
        src = (f"uni_start_stream <00x>\n{rid_line}  man_set_context_globalid <{WINDOW}>\n" + "".join(parts)
               + "  man_end_context\n  man_update_display\n  uni_wait_off\nuni_end_stream <00x>")
        link.send_stream(compile_fdo(src))
    run_bg(work, done)
