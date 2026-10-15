"""E-mail.

Client -> host:  m4  Compose Mail's Send: a MIP stream (mip_start_message,
                     mip_text..., mip_addressee with mip_attr_addressee_type
                     0=To 1=CC, mip_subject, mip_header_complete, mip_end_message)
                     possibly split over several m4 packets.
                 eL  Read New Mail (toolbar).
Host -> client:  mip_header_accepted / mip_message_accepted finish a send (the
                 client then shows its own confirmation if that pref is on);
                 mailbox and messages use AOL-style windows built here.
"""
import re
from datetime import datetime

import state
from fdo.codec import atom, stream

from . import screens, store
from .util import alert, atoms, name_of, request


def _body_text(parts: list[str]) -> str:
    """Compose text as typed: AOL 4.0 sends rich text as HTML, 3.0 plain text."""
    text = "".join(parts)
    if text.lstrip()[:6].upper() == "<HTML>" or re.search(r"(?i)<br>|<font", text):
        from .gateway import html_to_text
        text = html_to_text(text)
    return text


def _flush_draft(link):
    d = link.session.pop("draft", None)
    if not d:
        return
    sender = name_of(link)
    from . import gateway
    from .util import run_bg
    cfg = gateway.settings()
    body = _body_text(d["text"])
    to = [r.strip() for r in d["to"] if r.strip()]
    cc = [r.strip() for r in d["cc"] if r.strip()]
    members, internet, unknown = [], [], []
    for r in to + cc:
        if gateway.is_internet(r):
            k = gateway.owner_for(cfg, r) if cfg else None  # name@our-own-domain is a member
            (members if k else internet).append(k or r)
        elif store.account(r):
            members.append(r)
        else:
            unknown.append(r)
    owners = store.deliver(sender, to, cc, d["subject"], body, local=members)
    link.send_stream(stream(atom("mip_header_accepted"), atom("mip_message_accepted"), atom("uni_wait_off")))
    if internet:
        def sent(err):
            if err:
                alert(link, err + "  Your message to " + ", ".join(internet) + " was not sent.")
        if cfg:
            net_to = [r for r in to if r in internet]
            net_cc = [r for r in cc if r in internet]
            run_bg(lambda: gateway.send(sender, net_to or net_cc, net_cc if net_to else [], d["subject"], body), sent)
        else:
            sent("Internet mail is not set up on this host.")
    if unknown:
        alert(link, f"{', '.join(unknown)} {'is' if len(unknown) == 1 else 'are'} not "
                    f"{'a known member' if len(unknown) == 1 else 'known members'}; "
                    "your message was not delivered there.")
    for k in owners:
        target = state.ONLINE.get(k)
        if target:
            got_mail(target)


def compose_packet(link, stream_id, body):
    d = link.session.setdefault("draft", {"to": [], "cc": [], "subject": "", "text": []})
    kind = 0
    for a in atoms(body):
        if a.name == "mip_text":
            d["text"].append(a.args.decode("latin1"))
        elif a.name == "mip_attr_addressee_type":
            kind = int.from_bytes(a.args, "big")
        elif a.name == "mip_addressee":
            (d["cc"] if kind == 1 else d["to"]).append(a.args.rstrip(b"\0").decode("latin1"))
        elif a.name == "mip_subject":
            d["subject"] = a.args.rstrip(b"\0").decode("latin1")
        elif a.name == "mip_end_message":
            _flush_draft(link)


def got_mail(link):
    """'You've got mail!' -- the client's own Welcome-sound atom plus the alert."""
    n = store.unread(name_of(link))
    if n:
        link.send_stream(stream(atom("async_playsound_dammit", b"You've Got Mail")))


def _items(link):
    from .areas import _item
    return _item


def read_new_mail(link, stream_id, body=b"", folder="new"):
    from . import art
    if art.version(link) == "40":  # 4.0 has its own Online Mailbox (services/mailbox40.py fills it)
        from . import mailbox40
        return mailbox40.open_mailbox(link)
    rows = store.mailbox(name_of(link), folder)
    item = _items(link)
    title = {"new": "New Mail", "old": "Mail You've Read", "sent": "Mail You've Sent"}[folder]
    if not rows and folder == "new":
        link.send_stream(stream(atom("uni_wait_off")))
        return alert(link, "You have no new mail.")
    def who(r):
        n = (r["recipients"] if folder == "sent" else r["sender"])[:16]
        return n + ("\t" if len(n) < 8 else "")  # second tab keeps short names in the column

    entries = [(f"{datetime.fromtimestamp(r['sent']).strftime('%m/%d/%y')}\t{who(r)}\t{r['subject'][:44]}",
                item(link, ("mail", r["id"]))) for r in rows]
    buttons = [("Old Mail", '          sm_send_token_arg <"zA", %d>' % item(link, ("mailbox", "old"))),
               ("Sent Mail", '          sm_send_token_arg <"zA", %d>' % item(link, ("mailbox", "sent")))]
    link.send_stream(screens.list_window(f"{name_of(link)}'s {title}",
                                         f"{len(rows)} message{'s' if len(rows) != 1 else ''}.  "
                                         "Double-click a message to read it.", entries, buttons, width=60))


def open_message(link, mid: int):
    m = store.get(mid)
    if not m or m["owner"] != store.key(name_of(link)):
        return link.send_stream(stream(atom("uni_wait_off")))
    when = datetime.fromtimestamp(m["sent"]).strftime("%a, %b %-d, %Y %-I:%M:%S %p")
    head = [f"Subj:  {m['subject']}", f"Date:  {when}", f"From:  {m['sender']}", f"To:    {m['recipients']}"]
    if m["cc"]:
        head.append(f"CC:    {m['cc']}")
    link.send_stream(screens.text_window(m["subject"] or "(no subject)", "\r".join(head) + "\r\r" + m["body"],
                                         width=62, height=16))
    if m["folder"] == "new":
        store.mark_read(mid)


TOKENS = {b"m4": compose_packet, b"eL": read_new_mail, b"eO": lambda link, sid, body: read_new_mail(link, sid, body, "old"),
          b"oL": lambda link, sid, body: read_new_mail(link, sid, body, "sent")}
