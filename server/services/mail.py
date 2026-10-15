"""E-mail (stub until the mailbox is built): eL = Read New Mail."""
from fdo.codec import atom, stream

from .util import alert


def read_new_mail(link, stream_id, body):
    link.send_stream(stream(atom("uni_wait_off")))
    alert(link, "You have no new mail.")


TOKENS = {b"eL": read_new_mail}
