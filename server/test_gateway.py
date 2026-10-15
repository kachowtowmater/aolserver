"""Mail tests: Internet gateway (all modes), built-in SMTP receiver, DKIM, DNS parsing, and
member-to-member mail -- against a temporary database and local stand-in servers.  No real
mail account or network mail is used.   Run:  cd server && python3 test_gateway.py
"""
import asyncio
import os
import email
import email.policy
import smtplib
import socket
import struct
import sys
import tempfile
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from services import dkim, gateway, mail, maildns, smtpd, store  # noqa: E402

TMP = Path(tempfile.mkdtemp(prefix="aolmail-"))
store.DB = TMP / "aol.db"
dkim.KEY = TMP / "dkim.json"
for name in ("Rewind98", "Surfer98", "WebGuy"):
    store.create_account(name, "pw123456")


def use(cfg):
    gateway.config = lambda: cfg


def _smtp_sink(received):
    """One-connection SMTP server that records the DATA lines and envelope."""
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)

    def run():
        c, _ = srv.accept()
        f = c.makefile("rwb")
        f.write(b"220 sink\r\n"); f.flush()
        data = False
        for line in f:
            if data:
                if line == b".\r\n":
                    data = False
                    f.write(b"250 ok\r\n")
                else:
                    received.append(line)
            elif line.upper().startswith(b"DATA"):
                data = True
                f.write(b"354 go\r\n")
            elif line.upper().startswith(b"QUIT"):
                f.write(b"221 bye\r\n"); f.flush(); break
            else:
                if line.upper().startswith((b"MAIL", b"RCPT")):
                    received.append(b"ENVELOPE " + line[:9].upper() + line[9:])
                f.write(b"250 ok\r\n")
            f.flush()
        c.close()
    threading.Thread(target=run, daemon=True).start()
    return srv.getsockname()[1]


def _msg(lines):
    return email.message_from_bytes(b"".join(l for l in lines if not l.startswith(b"ENVELOPE")),
                                    policy=email.policy.default)


# ---------- outbound ----------

def test_send_plus_old_style_config():
    got = []
    port = _smtp_sink(got)
    use({"smtp_host": "127.0.0.1", "smtp_port": port, "starttls": False,
         "user": "aolhost@example.com", "password": ""})
    assert gateway.send("Rewind98", ["friend@example.org"], [], "Hi from 1997", "line1\rline2") is None
    m = _msg(got)
    assert m["From"] == "Rewind98 <aolhost+rewind98@example.com>" and m["To"] == "friend@example.org"
    assert "line2" in m.get_content() and m["Message-ID"] and m["Date"]
    assert b"ENVELOPE MAIL FROM:<aolhost+rewind98@example.com>\r\n" in got


def test_send_catchall_address():
    got = []
    port = _smtp_sink(got)
    use({"mode": "mailbox", "address_style": "catchall", "domain": "my90s.net", "smtp_host": "127.0.0.1",
         "smtp_port": port, "smtp_security": "none", "user": "inbox@my90s.net", "password": ""})
    assert gateway.send("Surfer98", ["pal@example.org"], ["two@example.org"], "yo", "body") is None
    m = _msg(got)
    assert m["From"] == "Surfer98 <surfer98@my90s.net>" and m["Cc"] == "two@example.org"
    assert sum(l.startswith(b"ENVELOPE RCPT") for l in got) == 2


def test_send_domain_relay_dkim_signed():
    got = []
    port = _smtp_sink(got)
    use({"mode": "domain", "domain": "my90s.net", "outbound": "relay", "smtp_host": "127.0.0.1",
         "smtp_port": port, "smtp_security": "none", "listen_port": 0})
    assert gateway.send("Rewind98", ["pal@example.org"], [], "signed", "hello\r\n") is None
    raw = b"".join(l for l in got if not l.startswith(b"ENVELOPE"))
    assert raw.startswith(b"DKIM-Signature: v=1; a=rsa-sha256; c=relaxed/relaxed; d=my90s.net; s=aol;")
    assert dkim.verify(raw, dkim.load()), "relay copy must carry a valid DKIM signature"
    assert b"From: Rewind98 <rewind98@my90s.net>" in raw


def test_dkim_dns_record():
    k = dkim.ensure_key()
    rec = dkim.dns_record(k)
    assert rec.startswith("v=DKIM1; k=rsa; p=MII") and k["n"].bit_length() == 2048
    assert os.name == "nt" or oct(dkim.KEY.stat().st_mode)[-3:] == "600"  # Windows has no Unix modes


def test_send_error_messages():
    use(None)
    assert "not set up" in gateway.send("Rewind98", ["x@example.org"], [], "s", "b")
    use({"mode": "mailbox", "smtp_host": "127.0.0.1", "smtp_port": 1, "smtp_security": "none",
         "user": "a@example.com", "password": ""})
    assert "could not be delivered" in gateway.send("Rewind98", ["x@example.org"], [], "s", "b")


# ---------- inbound: IMAP mailbox ----------

class FakeIMAP:
    messages = {}
    seen = set()

    def __init__(self, *a): pass
    def __enter__(self): return self
    def __exit__(self, *a): pass
    def login(self, *a): pass
    def select(self, *a): pass

    def search(self, *a):
        return "OK", [b" ".join(i for i in self.messages if i not in self.seen)]

    def fetch(self, i, what):
        raw = self.messages[i]
        if "HEADER.FIELDS" in what:
            raw = raw.split(b"\r\n\r\n")[0] + b"\r\n\r\n"
        return "OK", [(i, raw)]

    def store(self, i, *a):
        self.seen.add(i)


def test_poll_plus_leaves_other_mail_unread():
    import imaplib
    imaplib.IMAP4_SSL = FakeIMAP
    FakeIMAP.messages = {
        b"1": b"From: Friend <friend@example.org>\r\nTo: aolhost+rewind98@example.com\r\n"
              b"Subject: Re: Hi\r\n\r\nGot your AOL mail!\r\n",
        b"2": b"From: bank@example.com\r\nTo: aolhost@example.com\r\nSubject: statement\r\n\r\nprivate\r\n",
        b"3": b"From: x@example.com\r\nTo: aolhost+nosuchmember@example.com\r\nSubject: ?\r\n\r\n?\r\n"}
    FakeIMAP.seen = set()
    use({"imap_host": "x", "user": "aolhost@example.com", "password": "p"})
    assert gateway.poll_once() == [("rewind98", "Friend <friend@example.org>")]
    assert FakeIMAP.seen == {b"1"}, "only the gateway's own message may be marked read"
    row = store.mailbox("Rewind98")[0]
    assert row["subject"] == "Re: Hi" and "AOL mail" in row["body"]
    assert not store.mailbox("Friend <friend@example.org>", "sent"), "no junk 'sent' copy for outsiders"


def test_poll_catchall_html_and_attachment():
    import imaplib
    imaplib.IMAP4_SSL = FakeIMAP
    FakeIMAP.messages = {b"9": (
        b"From: Pal <pal@example.org>\r\nTo: Surfer98@My90s.net\r\nSubject: pics\r\nMIME-Version: 1.0\r\n"
        b"Content-Type: multipart/mixed; boundary=XX\r\n\r\n--XX\r\nContent-Type: text/html\r\n\r\n"
        b"<p>Hi&nbsp;there<br>line two</p>\r\n--XX\r\nContent-Type: image/png\r\n"
        b"Content-Disposition: attachment; filename=pic.png\r\n\r\nAAAA\r\n--XX--\r\n")}
    FakeIMAP.seen = set()
    use({"mode": "mailbox", "address_style": "catchall", "domain": "my90s.net", "imap_host": "x",
         "user": "inbox@my90s.net", "password": "p"})
    assert gateway.poll_once() == [("surfer98", "Pal <pal@example.org>")]
    body = store.mailbox("Surfer98")[0]["body"]
    assert "Hi\xa0there\nline two" in body and "pic.png" in body and "<p>" not in body


# ---------- inbound: built-in SMTP receiver ----------

DOMAIN = {"mode": "domain", "domain": "my90s.net", "listen_port": 0, "max_size": 4000,
          "postmaster": "WebGuy", "aliases": {"info": "Surfer98"}}


def _with_receiver(cfg, client):
    """Run the receiver on a spare port; client(port) talks to it from a thread."""
    use(cfg)
    gateway._status()["rate"] = {}

    async def main():
        srv = await asyncio.start_server(lambda r, w: smtpd.session(r, w, cfg), "127.0.0.1", 0, limit=1 << 16)
        port = srv.sockets[0].getsockname()[1]
        try:
            return await asyncio.get_running_loop().run_in_executor(None, client, port)
        finally:
            srv.close()
    return asyncio.run(main())


def test_receiver_delivers_and_refuses_relay():
    def client(port):
        out = {}
        with smtplib.SMTP("127.0.0.1", port) as s:
            code, msg = s.ehlo("mx.example.org")
            out["ehlo"] = msg
            s.mail("pal@example.org")
            out["relay"] = s.rcpt("victim@gmail.com")
            out["unknown"] = s.rcpt("nobody@my90s.net")
            out["ok"] = s.rcpt("Rewind98@my90s.net")
            out["alias"] = s.rcpt("info@my90s.net")
            out["post"] = s.rcpt("postmaster@my90s.net")
            out["data"] = s.data(b"From: Pal <pal@example.org>\r\nTo: rewind98@my90s.net\r\nSubject: hey\r\n\r\n"
                                 b".leading dot line\r\nbye\r\n")
        return out
    out = _with_receiver(DOMAIN, client)
    assert b"SIZE 4000" in out["ehlo"]
    assert out["relay"][0] == 550 and b"Relaying denied" in out["relay"][1]
    assert out["unknown"][0] == 550 and out["ok"][0] == 250 and out["alias"][0] == 250 and out["post"][0] == 250
    assert out["data"][0] == 250
    for who in ("Rewind98", "Surfer98", "WebGuy"):
        row = store.mailbox(who)[0]
        assert row["subject"] == "hey" and ".leading dot line" in row["body"], who


def test_receiver_size_limit_and_sequence():
    def client(port):
        with smtplib.SMTP("127.0.0.1", port) as s:
            s.ehlo()
            early = s.docmd("RCPT TO:<rewind98@my90s.net>")
            s.mail("pal@example.org")
            s.rcpt("rewind98@my90s.net")
            big = s.data(b"Subject: big\r\n\r\n" + b"x" * 5000 + b"\r\n")[0]
            return early, big
    early, big = _with_receiver(DOMAIN, client)
    assert early[0] == 503 and big == 552


def test_receiver_rate_limit():
    def client(port):
        codes = []
        for _ in range(smtpd.CONN_PER_MIN + 2):
            with socket.create_connection(("127.0.0.1", port)) as c:
                codes.append(c.recv(100)[:3])
        return codes
    codes = _with_receiver(DOMAIN, client)
    assert codes[0] == b"220" and codes[-1] == b"421"


def test_receiver_off_in_mailbox_mode():
    def client(port):
        with socket.create_connection(("127.0.0.1", port)) as c:
            return c.recv(100)
    assert _with_receiver({"mode": "mailbox", "user": "a@b.com", "imap_host": "x"}, client).startswith(b"421")


# ---------- DNS ----------

def test_dns_mx_parse():
    q = maildns._qname("my90s.net")
    resp = (struct.pack(">HHHHHH", 7, 0x8180, 1, 2, 0, 0) + q + struct.pack(">HH", 15, 1)
            + b"\xc0\x0c" + struct.pack(">HHIH", 15, 1, 300, 2 + 5) + struct.pack(">H", 20) + b"\x02mx\xc0\x0c"
            + b"\xc0\x0c" + struct.pack(">HHIH", 15, 1, 300, 2 + 6) + struct.pack(">H", 10) + b"\x03mx1\xc0\x0c")
    assert sorted(maildns.parse(resp, 15)) == [(10, "mx1.my90s.net"), (20, "mx.my90s.net")]


# ---------- member mail (what the AOL clients' Send Now does) ----------

class FakeLink:
    def __init__(self, name):
        self.session = {"name": name}
        self.sent = []

    def send_stream(self, data):
        self.sent.append(data)

    def text(self):
        return b"".join(self.sent)


def _send_mail(link, to, cc, subject, text):
    from fdo.codec import atom, stream
    parts = [atom("mip_start_message", b"\0" * 4), atom("mip_text", text.encode("latin1"))]
    for kind, names in ((0, to), (1, cc)):
        for n in names:
            parts += [atom("mip_attr_addressee_type", kind.to_bytes(2, "big")), atom("mip_addressee", n.encode())]
    parts += [atom("mip_subject", subject.encode()), atom("mip_header_complete"), atom("mip_end_message")]
    mail.compose_packet(link, 1, stream(*parts))


def test_member_mail_and_unknown_names():
    import state
    use(None)
    a, b = FakeLink("Rewind98"), FakeLink("Surfer98")
    state.ONLINE.clear()
    state.ONLINE["surfer98"] = b
    _send_mail(a, ["Surfer98", "NoSuchGuy"], [], "Lunch?", "<HTML>see you at<BR>noon&amp;stuff</HTML>")
    assert b"NoSuchGuy is not a known member" in a.text()
    assert b"You've Got Mail" in b.text(), "online recipient hears You've Got Mail"
    row = store.mailbox("Surfer98")[0]
    assert row["subject"] == "Lunch?" and row["body"] == "see you at\nnoon&stuff" and row["sender"] == "Rewind98"
    assert row["recipients"] == "Surfer98, NoSuchGuy"
    assert store.mailbox("Rewind98", "sent")[0]["subject"] == "Lunch?"
    assert not store.mailbox("NoSuchGuy")


def test_member_mail_to_own_domain_address_stays_local():
    use({"mode": "domain", "domain": "my90s.net", "listen_port": 0})
    a = FakeLink("Rewind98")
    _send_mail(a, ["webguy@my90s.net"], [], "local via domain", "hi")
    assert store.mailbox("WebGuy")[0]["subject"] == "local via domain"


def test_internet_mail_without_gateway_says_so():
    use(None)
    a = FakeLink("Rewind98")
    _send_mail(a, ["friend@example.org"], [], "out", "hi")
    assert b"Internet mail is not set up" in a.text()
    assert store.mailbox("Rewind98", "sent")[0]["subject"] == "out"


def test_info_lines():
    use(None)
    assert any("not set up" in l for l in gateway.info_lines())
    use({"mode": "domain", "domain": "my90s.net", "listen_port": 0})
    assert any("yourname@my90s.net" in l for l in gateway.info_lines())


if __name__ == "__main__":
    failed = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print(f"ok    {name}")
            except Exception as e:
                failed += 1
                import traceback
                traceback.print_exc()
                print(f"FAIL  {name}: {e!r}")
    print("all passed" if not failed else f"{failed} failed")
    sys.exit(1 if failed else 0)
