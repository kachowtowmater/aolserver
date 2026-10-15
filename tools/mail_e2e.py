"""End-to-end member mail check against the running host, over the real P3/FDO protocol.

Two bot members sign on; A sends mail (3.0-style, and 4.0-style rich text split across two
packets in one large atom) to B plus a name that doesn't exist; B must hear "You've Got
Mail", see it in New Mail (eL; and 4.0's m7, which fills the client's own mailbox list), open it, then find it in Old Mail; A must find
it in Sent Mail.  The bots and their mail are removed afterwards.
usage: python3 tools/mail_e2e.py        (host on 127.0.0.1:5190, admin console on :5191)
"""
import socket
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server"))
sys.path.insert(0, str(ROOT / "tools"))
from botclient import Bot  # noqa: E402
from fdo.codec import atom, stream  # noqa: E402

A, B, PW = "MailBotA", "MailBotB", "e2epass77"
SUBJ = f"E2E {int(time.time()) % 100000}"
OK = True


def check(cond, what):
    global OK
    OK &= bool(cond)
    print(("PASS  " if cond else "FAIL  ") + what)


def admin(expr: str) -> str:
    with socket.create_connection(("127.0.0.1", 5191)) as s:
        s.sendall(expr.encode() + b"\n")
        s.shutdown(socket.SHUT_WR)
        return s.makefile().read().strip()


def seen(bot, needle: bytes, since: int = 0) -> bool:
    return any(needle in p for _, p in bot.frames[since:])


def item_for(name: str, kind: str, value) -> int | None:
    out = admin(f'[n for n, p in by_name("{name}").session.get("items", {{}}).items() '
                f'if p[0] == "{kind}" and p[1] == {value!r}]')
    nums = [int(x) for x in out.strip("[]").split(",") if x.strip().isdigit()]
    return nums[-1] if nums else None


def cleanup():
    db = sqlite3.connect(ROOT / "server" / "var" / "aol.db")
    with db:
        db.execute("DELETE FROM mail WHERE owner IN (?,?)", (A.lower(), B.lower()))
        db.execute("DELETE FROM account WHERE key IN (?,?)", (A.lower(), B.lower()))
        db.execute("DELETE FROM buddy WHERE owner IN (?,?)", (A.lower(), B.lower()))


def main():
    cleanup()
    a, b = Bot(A), Bot(B)
    for bot in (a, b):
        bot.quiet = True
        bot.sign_on(PW)
    a.pump(3)
    b.pump(3)
    check(admin(f'by_name("{A}") is not None and by_name("{B}") is not None') == "True", "both bots signed on")

    # 3.0-style send: two m4 streams (text, then header)
    mark = len(b.frames)
    a.data(b"m4", stream(atom("mip_start_message", b"\0" * 4), atom("mip_text", b"Hello from bot A\rsecond line")))
    a.data(b"m4", stream(atom("mip_attr_addressee_type", b"\0\0"), atom("mip_addressee", B.encode()),
                         atom("mip_attr_addressee_type", b"\0\0"), atom("mip_addressee", b"NoSuchGuy9"),
                         atom("mip_subject", SUBJ.encode()), atom("mip_header_complete"), atom("mip_end_message")))
    a.pump(2)
    b.pump(2)
    check(seen(b, b"You've Got Mail", mark), "B hears You've Got Mail while online")
    check(seen(a, b"NoSuchGuy9 is not a known member"), "A is told NoSuchGuy9 is not a member")

    # 4.0-style send: rich text in a large atom split over two packets of one stream
    whole = stream(atom("mip_start_message", b"\0" * 4), atom("uni_start_large_atom", bytes([17, 11])),
                   atom("uni_large_atom_segment", b"<HTML><FONT SIZE=3>rich part one, "),
                   atom("uni_end_large_atom", b"part two<BR>done</HTML>"),
                   atom("mip_attr_addressee_type", b"\0\0"), atom("mip_addressee", B.encode()),
                   atom("mip_subject", (SUBJ + " rich").encode()), atom("mip_header_complete"),
                   atom("mip_end_message"))
    cut = whole.index(atom("uni_end_large_atom", b"part two<BR>done</HTML>"))
    a.data(b"m4", whole[:cut], stream_id=77)
    a.data(b"m4", whole[cut:], stream_id=77)
    a.pump(2)
    b.pump(1)

    # New Mail: toolbar eL (3.0) and m7 (4.0 Read Mail)
    for tok in (b"eL", b"m7"):
        mark = len(b.frames)
        b.data(tok, stream(atom("uni_start_stream"), atom("uni_end_stream")))
        b.pump(2)
        title = b"New Mail" if tok == b"eL" else b"%newmail"  # 4.0: the client's own Online Mailbox list
        check(seen(b, SUBJ.encode(), mark) and seen(b, title, mark), f"{tok.decode()} lists the new mail")
    rows = admin(f'[ (r["id"], r["subject"], r["body"]) for r in __import__("services.store",fromlist=["x"])'
                 f'.mailbox("{B}") ]')
    check("rich part one, part two\\ndone" in rows, "4.0 rich text arrives as plain text (split packets joined)")

    # open the 3.0 message
    mid = admin(f'[r["id"] for r in __import__("services.store",fromlist=["x"]).mailbox("{B}") '
                f'if r["subject"] == "{SUBJ}"][0]')
    n = item_for(B, "mail", int(mid))
    mark = len(b.frames)
    b.data(b"zA", stream(atom("de_data", int(n).to_bytes(4, "big"))))
    b.pump(2)
    check(seen(b, b"Hello from bot A", mark) and seen(b, f"From:  {A}".encode(), mark), "B opens and reads it")
    mark = len(b.frames)
    b.data(b"eO", stream(atom("uni_start_stream"), atom("uni_end_stream")))
    b.pump(2)
    check(seen(b, SUBJ.encode(), mark) and seen(b, b"Mail You've Read", mark), "it moved to Old Mail")
    mark = len(a.frames)
    a.data(b"oL", stream(atom("uni_start_stream"), atom("uni_end_stream")))
    a.pump(2)
    check(seen(a, SUBJ.encode(), mark) and seen(a, b"Mail You've Sent", mark), "A finds it in Sent Mail")

    # mail to someone offline is waiting (and announced) at sign-on
    b.sock.close()
    time.sleep(1)
    a.data(b"m4", stream(atom("mip_start_message", b"\0" * 4), atom("mip_text", b"while you were out"),
                         atom("mip_attr_addressee_type", b"\0\0"), atom("mip_addressee", B.encode()),
                         atom("mip_subject", b"offline note"), atom("mip_header_complete"), atom("mip_end_message")))
    a.pump(2)
    b2 = Bot(B)
    b2.quiet = True
    b2.sign_on(PW)
    b2.pump(5)
    check(seen(b2, b"You've Got Mail") and seen(b2, b"new message"), "mail sent while offline is announced at sign-on")
    a.sock.close()
    b2.sock.close()
    cleanup()
    print("ALL PASS" if OK else "SOME CHECKS FAILED")
    sys.exit(0 if OK else 1)


if __name__ == "__main__":
    main()
