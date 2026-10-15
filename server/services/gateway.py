"""Internet mail gateway: AOL mail <-> real e-mail (like AOL's own gateway).

Configure server/var/gateway.json (not in git):
  {"smtp_host": "smtp.gmail.com", "smtp_port": 587, "imap_host": "imap.gmail.com",
   "user": "you@gmail.com", "password": "<app password>"}
Outbound: mail addressed to name@domain is sent as "ScreenName <you+screenname@gmail.com>".
Inbound: messages to you+screenname@... are polled by IMAP and delivered to that member.
"""
import email
import email.policy
import imaplib
import json
import re
import smtplib
import time
from email.message import EmailMessage
from pathlib import Path

import state

CONF = Path(__file__).resolve().parent.parent / "var" / "gateway.json"
POLL_SECONDS = 120


def config():
    try:
        return json.loads(CONF.read_text())
    except Exception:
        return None


def is_internet(addr: str) -> bool:
    return "@" in addr and "." in addr.split("@")[-1]


def member_address(cfg, screen_name: str) -> str:
    local, domain = cfg["user"].split("@")
    return f"{local}+{screen_name.lower().replace(' ', '')}@{domain}"


def send(sender: str, to: list[str], cc: list[str], subject: str, body: str) -> str | None:
    """Blocking (call from run_bg). Returns an error string, or None on success."""
    cfg = config()
    if not cfg:
        return "Internet mail is not set up on this host yet."
    msg = EmailMessage()
    msg["From"] = f"{sender} <{member_address(cfg, sender)}>"
    msg["To"] = ", ".join(to)
    if cc:
        msg["Cc"] = ", ".join(cc)
    msg["Subject"] = subject
    msg["X-Mailer"] = "America Online 3.0 (revived 2026)"
    msg.set_content(body.replace("\r\n", "\n").replace("\r", "\n"))
    try:
        with smtplib.SMTP(cfg["smtp_host"], cfg.get("smtp_port", 587), timeout=30) as s:
            s.starttls()
            s.login(cfg["user"], cfg["password"])
            s.send_message(msg)
    except Exception as e:
        return f"Internet mail could not be delivered ({e.__class__.__name__})."
    return None


def _plain_body(m) -> str:
    part = m.get_body(preferencelist=("plain", "html"))
    text = part.get_content() if part else ""
    if part is not None and part.get_content_type() == "text/html":
        text = re.sub(r"<[^>]+>", " ", text)
    return text.strip()


def poll_once():
    """Blocking: fetch unseen gateway mail, deliver to members. Returns [(screen key, sender)]."""
    from . import store
    cfg = config()
    if not cfg or not cfg.get("imap_host"):
        return []
    local = cfg["user"].split("@")[0].lower()
    delivered = []
    with imaplib.IMAP4_SSL(cfg["imap_host"]) as im:
        im.login(cfg["user"], cfg["password"])
        im.select("INBOX")
        _, ids = im.search(None, "UNSEEN")
        for i in ids[0].split():
            _, data = im.fetch(i, "(RFC822)")
            m = email.message_from_bytes(data[0][1], policy=email.policy.default)
            targets = re.findall(rf"{re.escape(local)}\+([a-z0-9]+)@", " ".join(
                str(m.get(h, "")) for h in ("To", "Cc", "Delivered-To")).lower())
            if not targets:
                continue
            sender = str(m.get("From", "Internet"))[:60]
            for t in set(targets):
                if store.account(t):
                    store.deliver(sender, [t], [], str(m.get("Subject", "(no subject)")), _plain_body(m))
                    delivered.append((t, sender))
    return delivered


async def _poll_loop():
    import asyncio
    import sys
    while True:
        await asyncio.sleep(POLL_SECONDS)
        mod = sys.modules.get("services.gateway")
        if not mod or not mod.config():
            continue
        try:
            got = await asyncio.get_running_loop().run_in_executor(None, mod.poll_once)
        except Exception as e:
            print(f"      gateway poll failed: {e}")
            continue
        mail = sys.modules.get("services.mail")
        for key, sender in got:
            link = state.ONLINE.get(key)
            if link and mail:
                mail.got_mail(link)


def ensure_polling():
    import asyncio
    t = state.__dict__.get("GATEWAY_TASK")
    if t is None or t.done():
        state.GATEWAY_TASK = asyncio.get_running_loop().create_task(_poll_loop())
