"""Tiny DNS client (stdlib only): MX lookups for direct delivery, TXT/A for mail-setup checks."""
import random
import re
import socket
import struct

TYPES = {"A": 1, "MX": 15, "TXT": 16}


def nameservers() -> list[str]:
    try:
        found = re.findall(r"^\s*nameserver\s+(\S+)", open("/etc/resolv.conf").read(), re.M)
    except OSError:
        found = []
    return found or ["1.1.1.1"]


def _qname(name: str) -> bytes:
    return b"".join(bytes([len(p)]) + p.encode("idna") for p in name.rstrip(".").split(".")) + b"\0"


def _read_name(msg: bytes, i: int) -> tuple[str, int]:
    labels, end, jumps = [], None, 0
    while True:
        n = msg[i]
        if n & 0xC0 == 0xC0:  # compression pointer
            if end is None:
                end = i + 2
            i = ((n & 0x3F) << 8) | msg[i + 1]
            jumps += 1
            if jumps > 20:
                raise ValueError("dns: pointer loop")
            continue
        if n == 0:
            return ".".join(labels), (end if end is not None else i + 1)
        labels.append(msg[i + 1:i + 1 + n].decode("latin1"))
        i += 1 + n


def parse(msg: bytes, qtype: int) -> list:
    _, flags, qd, an = struct.unpack(">HHHH", msg[:8])
    if flags & 0xF == 3:  # NXDOMAIN
        return []
    i = 12
    for _ in range(qd):
        _, i = _read_name(msg, i)
        i += 4
    out = []
    for _ in range(an):
        _, i = _read_name(msg, i)
        rtype, _, _, rdlen = struct.unpack(">HHIH", msg[i:i + 10])
        i += 10
        rdata = msg[i:i + rdlen]
        if rtype == qtype == 15:
            out.append((struct.unpack(">H", rdata[:2])[0], _read_name(msg, i + 2)[0]))
        elif rtype == qtype == 16:
            parts, j = [], 0
            while j < len(rdata):
                parts.append(rdata[j + 1:j + 1 + rdata[j]].decode("latin1"))
                j += 1 + rdata[j]
            out.append("".join(parts))
        elif rtype == qtype == 1:
            out.append(socket.inet_ntoa(rdata))
        i += rdlen
    return out


def query(name: str, kind: str, timeout: float = 4.0) -> list:
    qtype = TYPES[kind]
    qid = random.randrange(65536)
    packet = struct.pack(">HHHHHH", qid, 0x0100, 1, 0, 0, 0) + _qname(name) + struct.pack(">HH", qtype, 1)
    for ns in nameservers():
        try:
            with socket.socket(socket.AF_INET6 if ":" in ns else socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.settimeout(timeout)
                s.sendto(packet, (ns, 53))
                msg, _ = s.recvfrom(4096)
            if struct.unpack(">H", msg[:2])[0] == qid:
                return parse(msg, qtype)
        except OSError:
            continue
    raise OSError(f"no DNS answer for {name} {kind}")


def mx_hosts(domain: str) -> list[str]:
    """MX hosts by preference; falls back to the domain itself (RFC 5321 implicit MX)."""
    try:
        rows = query(domain, "MX")
    except OSError:
        rows = []
    hosts = [h for _, h in sorted(rows) if h]
    return hosts or [domain]
