"""AOL 4.0's own Online Mailbox (form 41-5271), filled by the host like the real one.

Read Mail (mip_action_command 0x1d) opens the client's mailbox, whose New/Old/Sent Mail tabs ask
for their lists with m7 / m9 / m8.  The host answers with an lm_ list (FDO91 manual, appendix A,
example 2) whose lm_attr_list_type picks the client folder the mip tool fills: 2 = %newmail,
3 = %oldmail, 4 = %outmail.  Each entry: id + date (lm_add_entry_date_time, AOL time = seconds
since 1980) + tab + sender/recipients + tab + subject.  The folder is cleared first
(morg_obj_destroy_children), as the form's own close action does.
  m3  open a message (mip_preset_message_id): answered with a mip_start_message stream, which the
      client shows in its own Read Mail window (Next/Prev just send m3 for the neighbour)
  m2  status changes: mip_preset_message_id + mip_change_message_status (2 keep as new, 4 delete,
      6 delete sent, 7 ignore)
  oS  Status of a sent message;  oR  Unsend (only while unread)
AOL 3.0 keeps the host-built mail windows (services/mail.py).
"""
from . import screens, store
from .util import alert, atoms, compile_fdo, fdo_text, name_of


AOL_EPOCH = 315532800  # the client counts host time stamps from 1980-01-01


def aol_date(unix_ts, flags=0x10) -> str:
    """lm_add_entry_date_time's 5-byte form: display flags (0x10 = date only) + time stamp."""
    raw = bytes([flags]) + int(unix_ts - AOL_EPOCH).to_bytes(4, "big")
    return ", ".join(f"{b:02x}x" for b in raw)


LISTS = {"new": (2, "%newmail"), "old": (3, "%oldmail"), "sent": (4, "%outmail")}


def send_list(link, folder):
    """Fill one of the mailbox's lists: clear the client's folder, then the host list."""
    kind, path = LISTS[folder]
    rows = store.mailbox(name_of(link), folder)
    lines = ["uni_start_stream <00x>", f'  morg_obj_set_context <"{path}">', "  morg_obj_destroy_children",
             "  morg_obj_end_context", "  lm_start_list", f"  lm_attr_list_type <{kind}>"]
    for r in rows:
        who = r["recipients"] if folder == "sent" else r["sender"]
        lines += ['  lm_start_list_entry <"">', f"  lm_attr_list_entry_id <{r['id']}>",
                  f"  lm_add_entry_date_time <{aol_date(r['sent'])}>", "  lm_add_entry_tab",
                  f'  lm_add_entry_text <"{fdo_text(who[:30])}">', "  lm_add_entry_tab",
                  f'  lm_add_entry_text <"{fdo_text(r["subject"][:60])}">', "  lm_end_list_entry"]
    lines += ["  lm_end_list", "uni_end_stream <00x>"]
    print(f"      mailbox40 {folder} list -> {len(rows)} entries")
    link.send_stream(compile_fdo("\n".join(lines)))


def open_mailbox(link):
    """Open 4.0's own Online Mailbox, exactly as its Read Mail button does."""
    link.send_stream(compile_fdo("uni_start_stream <00x>\n  mip_action_command <1dx>\n  uni_wait_off\n"
                                 "uni_end_stream <00x>"))


def m7(link, stream_id, body):
    send_list(link, "new")


def m9(link, stream_id, body):
    send_list(link, "old")


def m8(link, stream_id, body):
    send_list(link, "sent")


def _mid(body) -> int | None:
    for a in atoms(body):
        if a.name == "mip_preset_message_id" and a.args:
            return int.from_bytes(a.args, "big")
    return None


def m3(link, stream_id, body):
    """m3: open a message from the mailbox (mip_preset_message_id): the host sends the message
    as MIP atoms and the client shows it in its own Read Mail window."""
    mid = _mid(body)
    m = store.get(mid) if mid else None
    if not m or m["owner"] != store.key(name_of(link)):
        return link.send_stream(compile_fdo("uni_start_stream <00x>\n  uni_wait_off\nuni_end_stream <00x>"))
    lines = ["uni_start_stream <00x>", "  mip_start_message", "  mip_attr_message_type <0>",
             f"  mip_message_id <{m['id']}>", f"  mip_message_date <{aol_date(m['sent'], 0x11)}>",
             f'  mip_author <"{fdo_text(m["sender"])}">', "  mip_attr_addressee_type <0>"]
    lines += [f'  mip_addressee <"{fdo_text(a.strip())}">' for a in m["recipients"].split(",") if a.strip()]
    if m["cc"]:
        lines.append("  mip_attr_addressee_type <1>")
        lines += [f'  mip_addressee <"{fdo_text(a.strip())}">' for a in m["cc"].split(",") if a.strip()]
    lines.append(f'  mip_subject <"{fdo_text(m["subject"] or "")}">')
    body_text = (m["body"] or "").replace("\r\n", "\n").replace("\r", "\n")
    for i in range(0, len(body_text), 200):
        lines.append(f'  mip_text <"{fdo_text(body_text[i:i + 200].replace(chr(10), chr(13)))}">')
    lines += ["  mip_end_message", "uni_end_stream <00x>"]
    link.send_stream(compile_fdo("\n".join(lines)))
    if m["folder"] == "new":
        store.mark_read(m["id"])


# mip_change_message_status values the 41-5271 form sends (m2)
KEEP_AS_NEW, DELETE, DELETE_SENT, IGNORE = 2, 4, 6, 7


def m2(link, stream_id, body):
    """m2: status changes from the mailbox (Keep As New, Ignore, Delete), one message id each."""
    me = store.key(name_of(link))
    mid = None
    for a in atoms(body):
        if a.name == "mip_preset_message_id":
            mid = int.from_bytes(a.args, "big")
        elif a.name == "mip_change_message_status" and mid is not None:
            status = int.from_bytes(a.args, "big")
            m = store.get(mid)
            if m and m["owner"] == me:
                if status in (DELETE, DELETE_SENT):
                    store.delete_mail(mid)
                elif status == KEEP_AS_NEW:
                    store.keep_as_new(mid)
                elif status == IGNORE:
                    store.mark_read(mid)
            print(f"      mailbox40 m2 message {mid} status {status}")
            mid = None


def _id_from(body) -> int | None:
    vals = [a.args for a in atoms(body) if a.args and a.name not in ("uni_start_stream", "uni_end_stream")]
    raw = vals[-1] if vals else body.strip(b"\0")
    return int.from_bytes(raw[-4:], "big") if raw else None


def status(link, stream_id, body):
    """oS: the Status button on a sent message: who has read it."""
    mid = _id_from(body)
    m = store.get(mid) if mid else None
    if not m or m["owner"] != store.key(name_of(link)):
        return alert(link, "Status is only available for mail you've sent.")
    rows = store.read_status(mid)
    if not rows:
        return alert(link, "This message was sent to the Internet; no read status is available.")
    lines = [f"{owner}: {'read' if read else 'not yet read'}" for owner, read in rows]
    link.send_stream(screens.text_window(f"Status: {m['subject'][:40]}", "\r".join(lines), width=44, height=8))


def unsend(link, stream_id, body):
    """oR: Unsend a sent message, if nobody has read it yet."""
    mid = _id_from(body)
    m = store.get(mid) if mid else None
    if not m or m["owner"] != store.key(name_of(link)) or m["folder"] != "sent":
        return alert(link, "Only mail you've sent can be unsent.")
    if any(read for _, read in store.read_status(mid)):
        return alert(link, "This message has already been read and can't be unsent.")
    store.unsend(mid)
    alert(link, "Your message has been unsent.")
    send_list(link, "sent")


TOKENS = {b"m7": m7, b"m9": m9, b"m8": m8, b"m3": m3, b"m2": m2, b"oS": status, b"oR": unsend}
