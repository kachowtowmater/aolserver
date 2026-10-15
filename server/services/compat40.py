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


TOKENS = {
    b"t1": areas.by_gid,          # 4.0 'go to area by GID'
    b"AE": chat.chat_line,        # 4.0 chat send from some room forms
    b"ir": report,
    b"id": member_info,
    b"L&": chat.list_rooms,       # room lists (member rooms / categories)
    b"LB": chat.list_rooms,
    b"cH": chat_help,
}
