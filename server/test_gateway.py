"""Gateway tests against a local SMTP sink and a fake IMAP inbox (no real account needed)."""
import email
import socket
import threading

from services import gateway


def _smtp_sink(received):
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
                f.write(b"250 ok\r\n")
            f.flush()
        c.close()
    threading.Thread(target=run, daemon=True).start()
    return srv.getsockname()[1]


def test_send(monkeypatch=None):
    got = []
    port = _smtp_sink(got)
    gateway.config = lambda: {"smtp_host": "127.0.0.1", "smtp_port": port, "starttls": False,
                              "user": "aolhost@example.com", "password": ""}
    assert gateway.send("Rewind98", ["friend@example.org"], [], "Hi from 1997", "line1\rline2") is None
    msg = email.message_from_bytes(b"".join(got))
    assert msg["From"] == "Rewind98 <aolhost+rewind98@example.com>" and msg["To"] == "friend@example.org"
    assert "line2" in msg.get_payload()


def test_poll(tmp_db=None):
    raw = (b"From: Friend <friend@example.org>\r\nTo: aolhost+rewind98@example.com\r\n"
           b"Subject: Re: Hi\r\n\r\nGot your AOL mail!\r\n")

    class FakeIMAP:
        def __init__(self, *a): pass
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def login(self, *a): pass
        def select(self, *a): pass
        def search(self, *a): return "OK", [b"1"]
        def fetch(self, *a): return "OK", [(b"1", raw)]
    import imaplib
    imaplib.IMAP4_SSL = FakeIMAP
    delivered = []
    from services import store
    store.account = lambda n: n == "rewind98"
    store.deliver = lambda sender, to, cc, subj, body: delivered.append((sender, to, subj, body))
    gateway.config = lambda: {"imap_host": "x", "user": "aolhost@example.com", "password": "p"}
    assert gateway.poll_once() == [("rewind98", "Friend <friend@example.org>")]
    assert delivered[0][1] == ["rewind98"] and delivered[0][2] == "Re: Hi" and "AOL mail" in delivered[0][3]


if __name__ == "__main__":
    test_send(); print("send ok")
    test_poll(); print("poll ok")
