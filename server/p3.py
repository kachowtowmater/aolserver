"""P3 link layer used by the AOL 3.0 client (TCP port 5190).

Frame: [5A][CRC 2B][LEN 2B][TX][RX][TYPE][payload...]
DATA frames carry [TOKEN 2B][STREAM 2B][body...] as payload.
Confirmed against the AOL 3.0 client's AOLP3.AOL (see ../re/NOTES.md):
- LEN = len(payload) + 3; every frame ends with a 0x0D terminator.
- CRC-16/ARC over [LEN .. end of payload], stored big-endian.
- Client->server types carry 0x80; server->client types must not.
- Sequence numbers run 16..127 and wrap; both sides start at 127.
"""
from dataclasses import dataclass

MAGIC = 0x5A
DATA, INIT, ACK, NAK, HBEAT, RESET, RAK, SETUP, ACKNOW = 0x20, 0x23, 0x24, 0x25, 0x26, 0x28, 0x29, 0x2A, 0x2B
TYPE_NAMES = {DATA: "DATA", INIT: "INIT", ACK: "ACK", NAK: "NAK", HBEAT: "HBEAT",
              RESET: "RESET", RAK: "RAK", SETUP: "SETUP", ACKNOW: "ACKNOW"}


def crc16(data: bytes) -> int:
    crc = 0
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc


@dataclass
class Frame:
    tx: int
    rx: int
    type: int
    payload: bytes = b""
    crc_ok: bool = True
    crc_variant: str = ""

    @property
    def name(self) -> str:
        return TYPE_NAMES.get(self.type & 0x7F, f"0x{self.type:02x}")

    @property
    def token(self) -> bytes | None:
        return self.payload[:2] if self.type & 0x7F == DATA and len(self.payload) >= 2 else None

    @property
    def stream(self) -> int | None:
        return int.from_bytes(self.payload[2:4], "big") if self.token and len(self.payload) >= 4 else None


SEQ_MIN, SEQ_MAX = 16, 127
NO_CRC = b"**"
MAX_CLIENT_DATA = 0x77


def next_seq(n: int) -> int:
    return SEQ_MIN if n + 1 > SEQ_MAX else n + 1


def encode(f: Frame, no_crc: bool = False) -> bytes:
    body = (len(f.payload) + 3).to_bytes(2, "big") + bytes([f.tx, f.rx, f.type]) + f.payload
    crc = NO_CRC if no_crc else crc16(body).to_bytes(2, "big")
    return bytes([MAGIC]) + crc + body + b"\x0d"


def try_decode(buf: bytearray) -> tuple[Frame | None, int]:
    """Return (frame, bytes_consumed). (None, 0) means need more data;
    (None, n) means n junk bytes were skipped."""
    if not buf:
        return None, 0
    if buf[0] != MAGIC:
        i = buf.find(MAGIC)
        return None, len(buf) if i < 0 else i
    if len(buf) < 8:
        return None, 0
    total = 5 + int.from_bytes(buf[3:5], "big")
    if len(buf) < total + 1:
        return None, 0
    raw = bytes(buf[:total])
    if raw[1:3] == NO_CRC:  # AOL 4.0 over TCP skips the CRC and sends '**'
        return Frame(raw[5], raw[6], raw[7], raw[8:], crc_ok=True, crc_variant="none"), \
            total + (1 if buf[total] == 0x0D else 0)
    ok = crc16(raw[3:]) == int.from_bytes(raw[1:3], "big")
    f = Frame(raw[5], raw[6], raw[7], raw[8:], crc_ok=ok, crc_variant="arc" if ok else "")
    return f, total + (1 if buf[total] == 0x0D else 0)
