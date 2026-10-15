"""DKIM (RFC 6376) signing with rsa-sha256, relaxed/relaxed -- pure stdlib, no crypto package.

The key lives in server/var/dkim.json ({"n", "e", "d"} as hex; never in git).  `dns_record()`
gives the TXT record to publish at <selector>._domainkey.<domain>.
RSA here is textbook PKCS#1 v1.5 signing (pow(m, d, n)); it is not constant-time, which is
fine for a hobby mail host signing its own outgoing mail.
"""
import base64
import hashlib
import json
import os
import re
import secrets
from pathlib import Path

KEY = Path(__file__).resolve().parent.parent / "var" / "dkim.json"
SIGNED_HEADERS = ["from", "to", "cc", "subject", "date", "message-id", "reply-to", "mime-version", "content-type"]
_SHA256_INFO = bytes.fromhex("3031300d060960864801650304020105000420")  # DigestInfo prefix


# ---------- keys ----------

def _probable_prime(bits: int) -> int:
    small = [p for p in range(3, 2000, 2) if all(p % q for q in range(3, int(p ** 0.5) + 1, 2))]
    while True:
        n = secrets.randbits(bits) | (1 << (bits - 1)) | (1 << (bits - 2)) | 1
        if any(n % p == 0 for p in small):
            continue
        d, r = n - 1, 0
        while d % 2 == 0:
            d //= 2
            r += 1
        for _ in range(40):  # Miller-Rabin
            x = pow(secrets.randbelow(n - 3) + 2, d, n)
            if x in (1, n - 1):
                continue
            for _ in range(r - 1):
                x = pow(x, 2, n)
                if x == n - 1:
                    break
            else:
                break
        else:
            return n


def generate(bits: int = 2048) -> dict:
    e = 65537
    while True:
        p, q = _probable_prime(bits // 2), _probable_prime(bits // 2)
        phi = (p - 1) * (q - 1)
        if p != q and phi % e and (p * q).bit_length() == bits:
            return {"n": p * q, "e": e, "d": pow(e, -1, phi)}


def load() -> dict | None:
    try:
        k = json.loads(KEY.read_text())
        return {"n": int(k["n"], 16), "e": int(k["e"], 16), "d": int(k["d"], 16)}
    except Exception:
        return None


def ensure_key() -> dict:
    k = load()
    if k:
        return k
    k = generate()
    KEY.parent.mkdir(exist_ok=True)
    fd = os.open(KEY, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump({x: format(k[x], "x") for x in ("n", "e", "d")}, f)
    return k


def _der_int(v: int) -> bytes:
    b = v.to_bytes((v.bit_length() + 8) // 8, "big")  # leading 0 keeps it positive
    return b"\x02" + _der_len(len(b)) + b


def _der_len(n: int) -> bytes:
    if n < 128:
        return bytes([n])
    b = n.to_bytes((n.bit_length() + 7) // 8, "big")
    return bytes([0x80 | len(b)]) + b


def _der_seq(*parts: bytes) -> bytes:
    body = b"".join(parts)
    return b"\x30" + _der_len(len(body)) + body


def public_der(k: dict) -> bytes:
    """SubjectPublicKeyInfo for the RSA key (what DKIM's p= carries)."""
    rsa_pub = _der_seq(_der_int(k["n"]), _der_int(k["e"]))
    alg = _der_seq(bytes.fromhex("06092a864886f70d010101"), b"\x05\x00")  # rsaEncryption, NULL
    bitstr = b"\x03" + _der_len(len(rsa_pub) + 1) + b"\x00" + rsa_pub
    return _der_seq(alg, bitstr)


def dns_record(k: dict) -> str:
    return "v=DKIM1; k=rsa; p=" + base64.b64encode(public_der(k)).decode()


# ---------- canonicalization (relaxed/relaxed) ----------

def _split(msg: bytes) -> tuple[list[tuple[str, bytes]], bytes]:
    msg = re.sub(rb"\r?\n", b"\r\n", msg)
    head, _, body = msg.partition(b"\r\n\r\n")
    headers = []
    for line in head.split(b"\r\n"):
        if line[:1] in (b" ", b"\t") and headers:
            name, value = headers[-1]
            headers[-1] = (name, value + b"\r\n" + line)
        elif b":" in line:
            name, _, value = line.partition(b":")
            headers.append((name.decode("latin1"), value))
    return headers, body


def canon_header(name: str, value: bytes) -> bytes:
    value = re.sub(rb"\r\n", b"", value)
    value = re.sub(rb"[ \t]+", b" ", value).strip()
    return name.strip().lower().encode() + b":" + value


def canon_body(body: bytes) -> bytes:
    lines = [re.sub(rb"[ \t]+", b" ", line).rstrip(b" \t") for line in body.split(b"\r\n")]
    while lines and lines[-1] == b"":
        lines.pop()
    return b"".join(line + b"\r\n" for line in lines)


def _sig_input(headers, signed: list[str], sig_value: bytes) -> bytes:
    by_name: dict[str, list[bytes]] = {}
    for name, value in headers:
        by_name.setdefault(name.lower(), []).append(value)
    out = []
    for h in signed:  # bottom-most instance first (RFC 6376 5.4.2)
        if by_name.get(h):
            out.append(canon_header(h, by_name[h].pop()) + b"\r\n")
    out.append(canon_header("dkim-signature", sig_value))
    return b"".join(out)


def _rsa_sign(k: dict, digest: bytes) -> bytes:
    size = (k["n"].bit_length() + 7) // 8
    t = _SHA256_INFO + digest
    em = b"\x00\x01" + b"\xff" * (size - len(t) - 3) + b"\x00" + t
    return pow(int.from_bytes(em, "big"), k["d"], k["n"]).to_bytes(size, "big")


def sign(msg: bytes, domain: str, selector: str, k: dict | None = None) -> bytes:
    """Return msg with a DKIM-Signature header prepended."""
    k = k or ensure_key()
    headers, body = _split(msg)
    present = {n.lower() for n, _ in headers}
    signed = [h for h in SIGNED_HEADERS if h in present]
    bh = base64.b64encode(hashlib.sha256(canon_body(body)).digest()).decode()
    tags = f"v=1; a=rsa-sha256; c=relaxed/relaxed; d={domain}; s={selector}; h={':'.join(signed)}; bh={bh}; b="
    digest = hashlib.sha256(_sig_input(headers, signed, tags.encode())).digest()
    b = base64.b64encode(_rsa_sign(k, digest)).decode()
    return f"DKIM-Signature: {tags}{b}\r\n".encode() + re.sub(rb"\r?\n", b"\r\n", msg)


def verify(msg: bytes, k: dict) -> bool:
    """Check our own signature (tests / mail-setup --test); `k` needs n and e."""
    headers, body = _split(msg)
    sig = next((v for n, v in headers if n.lower() == "dkim-signature"), None)
    if sig is None:
        return False
    tags = dict(t.strip().split("=", 1) for t in canon_header("x", sig)[2:].decode().split(";") if "=" in t)
    if base64.b64encode(hashlib.sha256(canon_body(body)).digest()).decode() != tags["bh"].replace(" ", ""):
        return False
    rest = [(n, v) for n, v in headers if n.lower() != "dkim-signature"]
    unsigned = re.sub(rb"b=[^;]*$", b"b=", sig.rstrip())
    digest = hashlib.sha256(_sig_input(rest, tags["h"].split(":"), unsigned)).digest()
    s = int.from_bytes(base64.b64decode(tags["b"].replace(" ", "")), "big")
    size = (k["n"].bit_length() + 7) // 8
    return pow(s, k["e"], k["n"]).to_bytes(size, "big").endswith(_SHA256_INFO + digest)
