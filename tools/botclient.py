"""Minimal scripted AOL 3.0 client for testing the host (speaks P3 like AOLP3.AOL).

usage: botclient.py NAME [command ...]      commands run in order:
  join            send CJ (People Connection)
  say:TEXT        send Aa chat line
  wait:SECONDS    sleep while printing what the host sends
  tok:XX:HEX      raw DATA token with hex body
"""
import socket
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "server"))
import p3  # noqa: E402
from fdo import codec  # noqa: E402


class Bot:
    def __init__(self, name, host="127.0.0.1", port=5190):
        self.name, self.tx, self.buf = name, p3.SEQ_MAX, bytearray()
        self.frames = []  # (token, payload) the host sent, for scripted checks
        self.quiet = False
        self.sock = socket.create_connection((host, port))
        self.sock.settimeout(0.2)
        self.raw(p3.INIT, 127, b"\x00" * 4)
        self.pump(1)

    def raw(self, type_, tx, payload=b""):
        self.sock.sendall(p3.encode(p3.Frame(tx, 127, type_ | 0x80, payload)))

    def data(self, token: bytes, body: bytes = b"", stream_id: int = 1):
        self.tx = p3.next_seq(self.tx)
        self.raw(p3.DATA, self.tx, token + stream_id.to_bytes(2, "big") + body)

    def sign_on(self, password: str = "botpass1"):
        self.data(b"Dd", codec.stream(codec.atom("de_data", self.name.encode()),
                                      codec.atom("de_data", password.encode())))

    def pump(self, seconds):
        end = time.time() + seconds
        while time.time() < end:
            try:
                chunk = self.sock.recv(4096)
                if not chunk:
                    print(f"[{self.name}] disconnected")
                    return
                self.buf += chunk
            except socket.timeout:
                continue
            while True:
                f, n = p3.try_decode(self.buf)
                if n == 0:
                    break
                del self.buf[:n]
                if f and f.token:
                    self.frames.append((f.token, bytes(f.payload)))
                    if not self.quiet:
                        print(f"[{self.name}] <- {f.token.decode('latin1')} {f.payload[2:80]!r}")


def main():
    bot = Bot(sys.argv[1])
    bot.sign_on()
    bot.pump(1)
    for cmd in sys.argv[2:]:
        kind, _, arg = cmd.partition(":")
        if kind == "join":
            bot.data(b"CJ")
        elif kind == "say":
            bot.data(b"Aa", arg.encode() + b"\x00", stream_id=0)
        elif kind == "tok":
            tok, _, hexbody = arg.partition(":")
            bot.data(tok.encode(), bytes.fromhex(hexbody))
        elif kind == "wait":
            bot.pump(float(arg))
            continue
        bot.pump(1)


if __name__ == "__main__":
    main()
