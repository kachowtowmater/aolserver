"""AOL host: P3 link layer for AOL 3.0 clients on :5190.

Handles the INIT->ACK handshake, heartbeats, sequencing and ACKs, logs every
frame to captures/*.jsonl, and hands DATA tokens to host.py, which is
hot-reloaded whenever it changes on disk.

Admin console on 127.0.0.1:5191 (one Python expression per line, evaluated
with `link` = newest client and fdo.codec helpers in scope), e.g.
    link.send_data(b"AT", 0, stream(atom("async_alert", b"\x01Hi")))
Run: python3 server.py
"""
import asyncio
import importlib
import json
import time
import traceback
from pathlib import Path

import host
import p3
from fdo import codec

LINKS: list["Link"] = []
CHUNK = 900  # atom bytes per DATA packet (client accepts frames up to 0x3fa)
def _mtime():
    here = Path(host.__file__).parent
    return max(p.stat().st_mtime for p in [here / "host.py", here / "fdo" / "compiler.py", *here.glob("services/*.py")])


_host_mtime = _mtime()


def current_host():
    global _host_mtime
    m = _mtime()
    if m != _host_mtime:
        _host_mtime = m
        try:
            importlib.reload(host)
            print("  (host.py reloaded)")
        except Exception:
            traceback.print_exc()
    return host

LOG = Path(__file__).parent / "captures"
LOG.mkdir(exist_ok=True)
ACK_EVERY = 1  # ack each DATA frame until we learn the client's window


class Link:
    def __init__(self, reader, writer):
        self.reader, self.writer = reader, writer
        self.peer = "%s:%d" % writer.get_extra_info("peername")[:2]
        self.tx = self.rx = p3.SEQ_MAX  # last seq we sent / last seq we accepted
        self.session = {}  # per-connection state owned by host.py
        self.no_crc = False  # AOL 4.0 over TCP: once the client sends '**' CRCs, so do we
        self.stream_seq = 0
        self.log = (LOG / f"{time.strftime('%Y%m%d-%H%M%S')}-{self.peer.replace(':', '_')}.jsonl").open("w")

    def record(self, direction, f: p3.Frame, raw: bytes):
        tok = f.token.decode("latin1") if f.token else None
        self.log.write(json.dumps({"t": time.time(), "dir": direction, "type": f.name, "tx": f.tx, "rx": f.rx,
                                   "token": tok, "stream": f.stream, "crc_ok": f.crc_ok, "hex": raw.hex()}) + "\n")
        self.log.flush()
        if f.name in ("ACK", "HBEAT"):
            return
        print(f"  {direction} {f.name:6} tx={f.tx:3} rx={f.rx:3} tok={tok} stream={f.stream}")
        skip = {"aT": 2, "at": 6, "At": 5}.get(tok, 4)
        if tok and len(f.payload) > skip and (direction == "C->S" or tok == "aT"):
            try:
                for a in codec.decode(f.payload[skip:]):
                    print(f"      {a!r}")
            except Exception:
                print(f"      raw {f.payload[4:80].hex(' ')}")

    def send(self, type_: int, payload: bytes = b""):
        if type_ == p3.DATA:
            self.tx = p3.next_seq(self.tx)
        f = p3.Frame(self.tx, self.rx, type_, payload)
        raw = p3.encode(f, no_crc=self.no_crc)
        self.record("S->C", f, raw)
        self.writer.write(raw)

    def send_data_raw(self, token: bytes, body: bytes = b""):
        """DATA packet whose payload is just token + body (no stream id)."""
        self.send(p3.DATA, token + body)

    def send_data(self, token: bytes, stream: int, body: bytes = b""):
        self.send(p3.DATA, token + stream.to_bytes(2, "big") + body)

    def send_stream(self, atoms: bytes):
        """Run an atom stream on the client. 'aT' carries no stream id; the
        2-byte-id 'AT' form is silently ignored by the 3.0 client. Streams too
        big for one packet go out as 'at' chunks sharing a 4-byte stream id."""
        parts = codec.top_level_streams(atoms)
        if len(parts) > 1:  # e.g. close-old-window then open-new: each runs as its own stream
            for part in parts:
                self.send_stream(part)
            return
        if len(atoms) <= CHUNK:
            return self.send(p3.DATA, b"aT" + atoms)
        self.stream_seq += 1
        sid = self.stream_seq.to_bytes(4, "big")
        for chunk in codec.split(atoms, CHUNK):
            self.send(p3.DATA, b"at" + sid + chunk)

    def on_frame(self, f: p3.Frame):
        if f.crc_variant == "none":
            self.no_crc = True
        if not f.crc_ok:
            return self.send(p3.NAK, b"\x01")
        kind = f.type & 0x7F
        if kind == p3.INIT:
            self.send(p3.ACK)  # moves the client from INIT_SENT to CONNECTED
        elif kind == p3.HBEAT:
            self.send(p3.ACK)
        elif kind == p3.DATA:
            if f.tx != p3.next_seq(self.rx):
                return self.send(p3.NAK, b"\x02")
            self.rx = f.tx
            self.send(p3.ACK)
            self.on_data(f)

    def on_data(self, f: p3.Frame):
        try:
            current_host().on_data(self, f.token, f.stream, f.payload[4:])
        except Exception:
            traceback.print_exc()

    async def run(self):
        print(f"[+] {self.peer} connected")
        LINKS.append(self)
        buf = bytearray()
        try:
            while chunk := await self.reader.read(4096):
                buf += chunk
                while True:
                    f, n = p3.try_decode(buf)
                    if n == 0:
                        break
                    raw = bytes(buf[:n])
                    del buf[:n]
                    if f is None:
                        print(f"  skipped {n} non-P3 bytes: {raw[:32].hex()}")
                        continue
                    self.record("C->S", f, raw)
                    self.on_frame(f)
                await self.writer.drain()
        finally:
            print(f"[-] {self.peer} disconnected")
            LINKS.remove(self)
            try:
                current_host().on_disconnect(self)
            except Exception:
                traceback.print_exc()
            self.log.close()
            self.writer.close()


async def admin(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    scope = {k: getattr(codec, k) for k in dir(codec) if not k.startswith("_")}
    while line := (await reader.readline()).decode().strip():
        scope.update(link=LINKS[-1] if LINKS else None, links=LINKS, host=current_host(),
                     by_name=lambda n: next((l for l in LINKS if l.session.get("name", "").lower() == n.lower()), None))
        try:
            out = eval(line, scope)
            for l in LINKS:
                await l.writer.drain()
            writer.write(f"{out!r}\n".encode())
        except Exception as e:
            writer.write(f"error: {e!r}\n".encode())
        await writer.drain()
    writer.close()


async def main(port: int = 5190):
    srv = await asyncio.start_server(lambda r, w: Link(r, w).run(), "0.0.0.0", port)
    adm = await asyncio.start_server(admin, "127.0.0.1", port + 1)
    print(f"AOL host listening on :{port} (admin on 127.0.0.1:{port + 1})")
    current_host().start_services()  # background services (mail gateway) need the running loop
    async with srv, adm:
        await asyncio.gather(srv.serve_forever(), adm.serve_forever())


if __name__ == "__main__":
    import os
    asyncio.run(main(int(os.environ.get("AOL_PORT", "5190"))))  # admin console is AOL_PORT + 1
