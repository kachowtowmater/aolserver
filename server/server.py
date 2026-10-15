"""Stage 2 AOL host: P3 link layer for AOL 3.0 clients on :5190.

Handles the INIT->ACK handshake, heartbeats, sequencing and ACKs, and logs
every frame (both directions) to captures/*.jsonl for the next stage.
Run: python3 server.py
"""
import asyncio
import json
import time
from pathlib import Path

import p3

LOG = Path(__file__).parent / "captures"
LOG.mkdir(exist_ok=True)
ACK_EVERY = 1  # ack each DATA frame until we learn the client's window


class Link:
    def __init__(self, reader, writer):
        self.reader, self.writer = reader, writer
        self.peer = "%s:%d" % writer.get_extra_info("peername")[:2]
        self.tx = self.rx = p3.SEQ_MAX  # last seq we sent / last seq we accepted
        self.log = (LOG / f"{time.strftime('%Y%m%d-%H%M%S')}-{self.peer.replace(':', '_')}.jsonl").open("w")

    def record(self, direction, f: p3.Frame, raw: bytes):
        tok = f.token.decode("latin1") if f.token else None
        self.log.write(json.dumps({"t": time.time(), "dir": direction, "type": f.name, "tx": f.tx, "rx": f.rx,
                                   "token": tok, "stream": f.stream, "crc_ok": f.crc_ok, "hex": raw.hex()}) + "\n")
        self.log.flush()
        print(f"  {direction} {f.name:6} tx={f.tx:3} rx={f.rx:3} tok={tok} crc={'ok' if f.crc_ok else 'BAD'} "
              f"{f.payload[4 if tok else 0:40]!r}")

    def send(self, type_: int, payload: bytes = b""):
        if type_ == p3.DATA:
            self.tx = p3.next_seq(self.tx)
        f = p3.Frame(self.tx, self.rx, type_, payload)
        raw = p3.encode(f)
        self.record("S->C", f, raw)
        self.writer.write(raw)

    def send_data(self, token: bytes, stream: int, body: bytes = b""):
        self.send(p3.DATA, token + stream.to_bytes(2, "big") + body)

    def on_frame(self, f: p3.Frame):
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
        pass  # stage 3: sign-on tokens go here

    async def run(self):
        print(f"[+] {self.peer} connected")
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
            self.log.close()
            self.writer.close()


async def main(port: int = 5190):
    srv = await asyncio.start_server(lambda r, w: Link(r, w).run(), "0.0.0.0", port)
    print(f"AOL host listening on :{port}")
    async with srv:
        await srv.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
