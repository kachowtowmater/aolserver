"""Built-in SMTP receiver for gateway mode "domain": screenname@yourdomain lands in AOL mail.

A small RFC 5321 server on asyncio (no packages): EHLO/HELO, optional STARTTLS (when
tls_cert/tls_key are set in gateway.json), MAIL, RCPT, DATA, RSET, NOOP, VRFY, QUIT.
Anti-abuse: only existing members of the configured domain(s) are accepted as recipients
(so it is never an open relay), a size limit, at most 50 recipients per message, per-IP
limits on connections and messages, and idle timeouts.
"""
import asyncio
import email.utils
import re
import socket
import ssl
import sys
import time

MAX_RCPTS = 50
IDLE = 300  # seconds per command
CONN_PER_MIN = 30
MSGS_PER_HOUR = 200
_ADDR = re.compile(rb"^(?:MAIL FROM|RCPT TO):\s*<([^<>]*)>(.*)$", re.I)


def _gw():
    return sys.modules["services.gateway"]


def _allow(ip: str, kind: str, limit: int, window: float) -> bool:
    rate = _gw()._status().setdefault("rate", {})
    now = time.time()
    hits = [t for t in rate.get((ip, kind), []) if now - t < window]
    if len(hits) >= limit:
        rate[(ip, kind)] = hits
        return False
    hits.append(now)
    rate[(ip, kind)] = hits
    if len(rate) > 5000:  # forget idle peers
        for k in [k for k, v in rate.items() if not v or now - v[-1] > 3600]:
            rate.pop(k, None)
    return True


async def session(reader: asyncio.StreamReader, writer: asyncio.StreamWriter, cfg=None):
    gw = _gw()
    cfg = gw.settings(cfg if cfg is not None else gw.config())
    peer = (writer.get_extra_info("peername") or ("?", 0))[0]
    me = (cfg["domains"][0] if cfg and cfg["domains"] else socket.getfqdn())

    async def reply(line: str):
        writer.write(line.encode() + b"\r\n")
        await writer.drain()

    if not cfg or cfg["mode"] != "domain":
        await reply("421 4.3.2 Mail service not available")
        writer.close()
        return
    if not _allow(peer, "conn", CONN_PER_MIN, 60):
        await reply("421 4.7.0 Too many connections, try again later")
        writer.close()
        return
    await reply(f"220 {me} ESMTP America Online mail")
    mail_from, owners, tls = None, [], False
    try:
        while True:
            try:
                line = await asyncio.wait_for(reader.readline(), IDLE)
            except (asyncio.LimitOverrunError, ValueError):
                await reply("500 5.5.2 Line too long")
                continue
            if not line:
                break
            cmd = line.rstrip(b"\r\n")
            verb = cmd[:4].upper()
            if verb in (b"EHLO", b"HELO"):
                mail_from, owners = None, []
                if verb == b"HELO":
                    await reply(f"250 {me}")
                else:
                    ext = [f"SIZE {cfg['max_size']}", "8BITMIME", "PIPELINING", "ENHANCEDSTATUSCODES"]
                    if cfg.get("tls_cert") and not tls:
                        ext.append("STARTTLS")
                    lines = [me] + ext
                    for i, l in enumerate(lines):
                        await reply(("250-" if i < len(lines) - 1 else "250 ") + l)
            elif cmd.upper() == b"STARTTLS" and cfg.get("tls_cert") and not tls:
                await reply("220 2.0.0 Ready to start TLS")
                ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
                ctx.load_cert_chain(cfg["tls_cert"], cfg.get("tls_key"))
                await writer.start_tls(ctx)
                tls, mail_from, owners = True, None, []
            elif verb == b"MAIL":
                m = _ADDR.match(cmd)
                if not m:
                    await reply("501 5.5.4 Syntax: MAIL FROM:<address>")
                    continue
                size = re.search(rb"SIZE=(\d+)", m.group(2), re.I)
                if size and int(size.group(1)) > cfg["max_size"]:
                    await reply("552 5.3.4 Message too big")
                    continue
                mail_from, owners = m.group(1).decode("latin1"), []
                await reply("250 2.1.0 OK")
            elif verb == b"RCPT":
                m = _ADDR.match(cmd)
                if mail_from is None:
                    await reply("503 5.5.1 MAIL first")
                elif not m:
                    await reply("501 5.5.4 Syntax: RCPT TO:<address>")
                elif len(owners) >= MAX_RCPTS:
                    await reply("452 4.5.3 Too many recipients")
                else:
                    addr = m.group(1).decode("latin1")
                    domain = addr.rsplit("@", 1)[-1].lower().strip(".")
                    if "@" not in addr or domain not in cfg["domains"]:
                        await reply("550 5.7.1 Relaying denied")
                        continue
                    k = gw.owner_for(cfg, addr)
                    if not k:
                        await reply("550 5.1.1 No such member here")
                    else:
                        if k not in owners:
                            owners.append(k)
                        await reply("250 2.1.5 OK")
            elif verb == b"DATA":
                if not owners:
                    await reply("503 5.5.1 RCPT first")
                    continue
                if not _allow(peer, "msg", MSGS_PER_HOUR, 3600):
                    await reply("451 4.7.1 Too much mail from you, try again later")
                    continue
                await reply("354 End data with <CR><LF>.<CR><LF>")
                chunks, size, too_big = [], 0, False
                while True:
                    try:
                        dl = await asyncio.wait_for(reader.readline(), IDLE)
                    except (asyncio.LimitOverrunError, ValueError):
                        too_big = True  # absurd line: treat the message as unacceptable
                        continue
                    if not dl:
                        return
                    if dl in (b".\r\n", b".\n"):
                        break
                    if dl.startswith(b"."):
                        dl = dl[1:]  # dot-unstuffing
                    size += len(dl)
                    if size > cfg["max_size"]:
                        too_big = True
                    elif not too_big:
                        chunks.append(dl)
                if too_big:
                    await reply("552 5.3.4 Message too big")
                else:
                    stamp = (f"Received: from {peer} by {me} (AOL Revival) for <{owners[0]}@{cfg['domains'][0]}>; "
                             f"{email.utils.formatdate(localtime=True)}\r\n").encode()
                    raw = stamp + b"".join(chunks)
                    got = await asyncio.get_running_loop().run_in_executor(
                        None, gw.deliver_raw, cfg, raw, list(owners))
                    gw._status()["received"] = gw._status().get("received", 0) + len(got)
                    gw.notify(got)
                    print(f"      mail: received from <{mail_from}> for {', '.join(k for k, _ in got)}")
                    await reply("250 2.0.0 Delivered to AOL mail")
                mail_from, owners = None, []
            elif verb == b"RSET":
                mail_from, owners = None, []
                await reply("250 2.0.0 OK")
            elif verb == b"NOOP":
                await reply("250 2.0.0 OK")
            elif verb == b"VRFY":
                await reply("252 2.5.2 Cannot VRFY user")
            elif verb == b"QUIT":
                await reply("221 2.0.0 Goodbye")
                break
            else:
                await reply("502 5.5.2 Command not recognized")
    except (asyncio.TimeoutError, ConnectionError, ssl.SSLError):
        pass
    finally:
        try:
            writer.close()
        except Exception:
            pass
