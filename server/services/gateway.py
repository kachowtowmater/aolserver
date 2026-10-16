"""Internet mail gateway: AOL mail <-> real e-mail (like AOL's own Internet gateway).

Whoever hosts this server picks one of two setups with `run/mail-setup` (it writes
server/var/gateway.json, mode 600, never in git; changes are picked up within seconds):

mode "mailbox" -- borrow an existing mail account (Gmail, Fastmail, iCloud, your ISP...)
    Out: SMTP through the provider, From "ScreenName <address>".
    In:  the server polls the account over IMAP and files each message in the member's mailbox.
    address_style "plus":     you+screenname@provider.com  (needs plus-addressing; Gmail/Fastmail/iCloud)
    address_style "catchall": screenname@yourdomain.com    (a domain whose catch-all lands in that mailbox)

mode "domain" -- this server IS the mail server for your domain: screenname@yourdomain.com
    In:  built-in SMTP receiver (services/smtpd.py) on listen_port; point your MX record here.
         Only members of your own domain(s) are accepted -- never an open relay.
    Out: outbound "relay" -- through a smarthost with login (recommended: home IPs are blocked
         on port 25 and flagged as spam), or outbound "direct" -- straight to each recipient's
         MX.  Outgoing mail is DKIM-signed (services/dkim.py) unless "dkim": false.

Keys: mode, domain, domains[], address_style, user, password, imap_host, imap_port, imap_ssl,
smtp_host, smtp_port, smtp_security ("starttls"|"ssl"|"none"), smtp_user, smtp_password,
outbound, listen_host, listen_port, max_size, dkim, dkim_selector, postmaster, aliases{},
poll_seconds.  Old-style files ({smtp_host, imap_host, user, password, starttls}) still work.
"""
import asyncio
import email
import email.policy
import email.utils
import html
import imaplib
import json
import re
import smtplib
import socket
import ssl
import sys
import time
from email.message import EmailMessage
from pathlib import Path

import state

CONF = Path(__file__).resolve().parent.parent / "var" / "gateway.json"
MAX_BODY = 60_000  # characters kept of an incoming message's text
MAILER = "America Online 4.0 (revived 2026)"


def _status() -> dict:
    return state.__dict__.setdefault("MAIL", {"listener": None, "listen": None, "last_poll": 0,
                                               "poll_error": None, "received": 0, "rate": {}})


# ---------- configuration ----------

def config():
    """The raw gateway.json, or None when outside mail is off."""
    try:
        cfg = json.loads(CONF.read_text())
    except Exception:
        return None
    return cfg if cfg and not cfg.get("disabled") else None


def settings(cfg=None) -> dict | None:
    """config() with defaults filled in and old-style files upgraded."""
    cfg = dict(cfg if cfg is not None else (config() or {}))
    if not cfg:
        return None
    mode = cfg.get("mode") or ("domain" if cfg.get("listen_port") and not cfg.get("imap_host") else "mailbox")
    cfg["mode"] = mode
    if "smtp_security" not in cfg:
        port = cfg.get("smtp_port", 587)
        cfg["smtp_security"] = "ssl" if port == 465 else ("starttls" if cfg.get("starttls", True) else "none")
    cfg.setdefault("smtp_port", {"ssl": 465, "starttls": 587, "none": 25}[cfg["smtp_security"]])
    cfg.setdefault("smtp_user", cfg.get("user", ""))
    cfg.setdefault("smtp_password", cfg.get("password", ""))
    cfg.setdefault("imap_ssl", True)
    cfg.setdefault("imap_port", 993 if cfg["imap_ssl"] else 143)
    cfg.setdefault("poll_seconds", 120)
    if mode == "mailbox":
        cfg.setdefault("address_style", "plus")
        if not cfg.get("domain") and "@" in cfg.get("user", ""):
            cfg["domain"] = cfg["user"].split("@")[1]
    else:
        cfg.setdefault("outbound", "relay" if cfg.get("smtp_host") else "direct")
        cfg.setdefault("listen_host", "0.0.0.0")
        cfg.setdefault("listen_port", 25)
        cfg.setdefault("dkim", True)
        cfg.setdefault("dkim_selector", "aol")
    cfg.setdefault("max_size", 10 * 1024 * 1024)
    domains = cfg.get("domains") or ([cfg["domain"]] if cfg.get("domain") else [])
    cfg["domains"] = [d.lower().strip(".") for d in domains]
    cfg.setdefault("aliases", {})
    return cfg


def enabled() -> bool:
    return settings() is not None


def is_internet(addr: str) -> bool:
    return "@" in addr and "." in addr.split("@")[-1]


def _key(name: str) -> str:
    return name.lower().replace(" ", "")


def member_address(cfg, screen_name: str) -> str:
    """The Internet address a member's mail goes out from (and replies come back to)."""
    cfg = settings(cfg)
    sn = _key(screen_name)
    if cfg["mode"] == "mailbox" and cfg.get("address_style", "plus") == "plus":
        local, domain = cfg["user"].split("@")
        return f"{local}+{sn}@{domain}"
    return f"{sn}@{cfg['domains'][0]}"


def owner_for(cfg, addr: str) -> str | None:
    """Which member an incoming address belongs to (screen-name key), or None.  Checks the
    account exists; aliases ({"webmaster": "Rewind98"}) and postmaster/abuse also map."""
    from . import store
    cfg = settings(cfg)
    m = re.match(r"^\s*<?([^<>@\s]+)@([^<>@\s]+?)>?\s*$", addr or "")
    if not m:
        return None
    local, domain = m.group(1).lower(), m.group(2).lower().strip(".")
    if cfg["mode"] == "mailbox" and cfg.get("address_style", "plus") == "plus":
        box_local, box_domain = cfg["user"].lower().split("@")
        if domain != box_domain or not local.startswith(box_local + "+"):
            return None
        local = local[len(box_local) + 1:]
    elif domain not in cfg["domains"]:
        return None
    aliases = {k.lower(): v for k, v in cfg.get("aliases", {}).items()}
    if cfg.get("postmaster"):
        aliases.setdefault("postmaster", cfg["postmaster"])
        aliases.setdefault("abuse", cfg["postmaster"])
    name = aliases.get(local, local)
    acct = store.account(name)
    return _key(name) if acct else None


# ---------- outbound ----------

def build_message(cfg, sender: str, to: list[str], cc: list[str], subject: str, body: str) -> EmailMessage:
    cfg = settings(cfg)
    addr = member_address(cfg, sender)
    msg = EmailMessage()
    msg["From"] = email.utils.formataddr((sender, addr))
    msg["To"] = ", ".join(to)
    if cc:
        msg["Cc"] = ", ".join(cc)
    msg["Subject"] = subject
    msg["Date"] = email.utils.formatdate(localtime=True)
    msg["Message-ID"] = email.utils.make_msgid(domain=addr.split("@")[1])
    msg["X-Mailer"] = MAILER
    msg.set_content(body.replace("\r\n", "\n").replace("\r", "\n"))
    return msg


def _smtp_login(cfg, host=None, port=None, timeout=30):
    """Open an SMTP session per smtp_security, logged in when a password is set."""
    host, port = host or cfg["smtp_host"], port or cfg["smtp_port"]
    ctx = ssl.create_default_context()
    if cfg["smtp_security"] == "ssl":
        s = smtplib.SMTP_SSL(host, port, timeout=timeout, context=ctx)
    else:
        s = smtplib.SMTP(host, port, timeout=timeout)
        if cfg["smtp_security"] == "starttls":
            s.starttls(context=ctx)
    if cfg.get("smtp_password"):
        s.login(cfg["smtp_user"], cfg["smtp_password"])
    return s


def _send_direct(cfg, raw: bytes, mail_from: str, rcpts: list[str]) -> list[str]:
    """Deliver straight to each domain's MX. Returns the recipients that failed."""
    from . import maildns
    failed, by_domain = [], {}
    for r in rcpts:
        by_domain.setdefault(r.rsplit("@", 1)[1].lower(), []).append(r)
    helo = cfg["domains"][0] if cfg["domains"] else socket.getfqdn()
    for domain, group in by_domain.items():
        for mx in maildns.mx_hosts(domain):
            try:
                with smtplib.SMTP(mx, 25, timeout=30, local_hostname=helo) as s:
                    s.ehlo()
                    if s.has_extn("starttls"):
                        s.starttls(context=ssl.create_default_context())
                        s.ehlo()
                    refused = s.sendmail(mail_from, group, raw)
                failed += list(refused)
                break
            except (OSError, smtplib.SMTPException):
                continue
        else:
            failed += group
    return failed


def send(sender: str, to: list[str], cc: list[str], subject: str, body: str) -> str | None:
    """Blocking (call from run_bg). Returns an error string, or None on success."""
    cfg = settings(config())
    if not cfg:
        return "Internet mail is not set up on this host yet."
    msg = build_message(cfg, sender, to, cc, subject, body)
    mail_from = member_address(cfg, sender)
    raw = msg.as_bytes(policy=email.policy.SMTP)
    if cfg["mode"] == "domain" and cfg.get("dkim"):
        from . import dkim
        raw = dkim.sign(raw, cfg["domains"][0], cfg["dkim_selector"])
    rcpts = [email.utils.parseaddr(a)[1] for a in to + cc]
    try:
        if cfg["mode"] == "domain" and cfg.get("outbound") == "direct":
            failed = _send_direct(cfg, raw, mail_from, rcpts)
            if failed:
                return f"Internet mail could not be delivered to {', '.join(failed)}."
            return None
        with _smtp_login(cfg) as s:
            s.sendmail(mail_from, rcpts, raw)
    except smtplib.SMTPAuthenticationError:
        return "Internet mail could not be sent: the host's mail login was refused."
    except smtplib.SMTPRecipientsRefused as e:
        return f"Internet mail could not be delivered to {', '.join(e.recipients)}."
    except Exception as e:
        return f"Internet mail could not be delivered ({e.__class__.__name__})."
    return None


# ---------- inbound ----------

def html_to_text(text: str) -> str:
    text = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", text)
    text = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</tr>|</h\d>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text).replace("\x7f", "")
    return re.sub(r"\n{3,}", "\n\n", re.sub(r"[ \t]+\n", "\n", text)).strip()


def plain_body(m) -> str:
    part = m.get_body(preferencelist=("plain", "html"))
    try:
        text = part.get_content() if part is not None else ""
    except Exception:
        text = ""
    if part is not None and part.get_content_type() == "text/html":
        text = html_to_text(text)
    names = [p.get_filename() for p in m.iter_attachments() if p.get_filename()]
    if names:
        text += "\n\n[Attachments not delivered to AOL: " + ", ".join(names) + "]"
    return text.strip()[:MAX_BODY]


def deliver_raw(cfg, raw: bytes, owners: list[str] | None = None) -> list[tuple[str, str]]:
    """File one Internet message in the members' mailboxes. `owners` comes from SMTP RCPT;
    without it (IMAP) the members are found from To/Cc/Delivered-To. Returns [(key, sender)]."""
    from . import store
    m = email.message_from_bytes(raw, policy=email.policy.default)
    if owners is None:
        heads = []
        for h in ("To", "Cc", "Delivered-To", "X-Original-To", "Envelope-To"):
            heads += [str(v) for v in m.get_all(h, [])]
        owners = []
        for _, addr in email.utils.getaddresses(heads):
            k = owner_for(cfg, addr)
            if k and k not in owners:
                owners.append(k)
    name, addr = email.utils.parseaddr(str(m.get("From", "")))
    sender = (f"{name} <{addr}>" if name and addr else addr or name or "Internet")[:80]
    subject, body = str(m.get("Subject", "") or "(no subject)"), plain_body(m)
    to, cc = str(m.get("To", ""))[:200], str(m.get("Cc", ""))[:200]
    for k in owners:
        store.deliver_incoming(k, sender, to, cc, subject, body)
    return [(k, sender) for k in owners]


def notify(delivered):
    """'You've Got Mail' for members who are online right now (call on the event loop)."""
    mail = sys.modules.get("services.mail")
    for k, _ in delivered:
        link = state.ONLINE.get(k)
        if link and mail:
            mail.got_mail(link)


def _imap(cfg):
    cls = imaplib.IMAP4_SSL if cfg.get("imap_ssl", True) else imaplib.IMAP4
    im = cls(cfg["imap_host"], cfg["imap_port"])
    im.login(cfg["user"], cfg["password"])
    return im


def poll_once(cfg=None):
    """Blocking: file unseen gateway mail from the IMAP mailbox. Messages addressed to nobody
    here are left untouched (unread), so the mailbox can also be someone's own."""
    cfg = settings(cfg if cfg is not None else config())
    if not cfg or cfg["mode"] != "mailbox" or not cfg.get("imap_host"):
        return []
    delivered = []
    with _imap(cfg) as im:
        im.select("INBOX")
        _, ids = im.search(None, "UNSEEN")
        for i in ids[0].split():
            _, data = im.fetch(i, "(BODY.PEEK[HEADER.FIELDS (TO CC DELIVERED-TO X-ORIGINAL-TO ENVELOPE-TO)])")
            heads = email.message_from_bytes(data[0][1], policy=email.policy.default)
            addrs = []
            for h in ("To", "Cc", "Delivered-To", "X-Original-To", "Envelope-To"):
                addrs += [a for _, a in email.utils.getaddresses([str(v) for v in heads.get_all(h, [])])]
            if not any(owner_for(cfg, a) for a in addrs):
                continue
            _, data = im.fetch(i, "(BODY.PEEK[])")
            got = deliver_raw(cfg, data[0][1])
            if got:
                im.store(i, "+FLAGS", "\\Seen")
                delivered += got
    return delivered


# ---------- status (AOL's Internet Mail window, mail-setup) ----------

def info_lines(screen_name: str = "") -> list[str]:
    cfg = settings()
    if not cfg:
        return ["Mail between members works right now: just address it to a screen name.", "",
                "Internet mail (name@domain.com) is not set up on this host.  "
                "The host's operator can turn it on with run/mail-setup."]
    addr = member_address(cfg, screen_name) if screen_name else member_address(cfg, "YourName")
    lines = ["You can send and receive Internet mail!", "",
             "To send: address your mail to anyone's Internet address, like friend@example.com.",
             f"To receive: give people your Internet address.  Yours is {addr}.", ""]
    st = _status()
    if cfg["mode"] == "domain":
        listening = st.get("listener") is not None
        lines.append(f"This host receives mail for {', '.join(cfg['domains'])} itself"
                     + ("." if listening else " (the mail receiver is not running right now)."))
    else:
        lines.append("Incoming Internet mail is checked every few minutes.")
        if st.get("poll_error"):
            lines.append("(The last check for new Internet mail failed; the host's operator has been told.)")
    return lines


# ---------- background service ----------

async def _listen(cfg):
    st = _status()
    want = (cfg["listen_host"], int(cfg["listen_port"]))
    if st.get("listener") is not None and st.get("listen") == want:
        return
    await _stop_listener()

    async def handle(reader, writer):
        smtpd = sys.modules.get("services.smtpd")  # always the newest code
        if smtpd:
            await smtpd.session(reader, writer)
        else:
            writer.close()
    try:
        st["listener"] = await asyncio.start_server(handle, *want, limit=1 << 16)
        st["listen"] = want
        st.pop("listen_error", None)
        print(f"      mail: receiving SMTP for {', '.join(cfg['domains'])} on {want[0]}:{want[1]}")
    except OSError as e:
        if st.get("listen_error") != str(e):
            print(f"      mail: cannot listen on {want[0]}:{want[1]}: {e}")
        st["listen_error"] = str(e)


async def _stop_listener():
    st = _status()
    srv = st.get("listener")
    if srv is not None:
        srv.close()
        st["listener"] = st["listen"] = None
        print("      mail: SMTP receiver stopped")


async def tick():
    """One supervisor step: follow gateway.json (no restart needed)."""
    cfg = settings()
    st = _status()
    if cfg and cfg["mode"] == "domain" and int(cfg.get("listen_port") or 0):
        await _listen(cfg)
    else:
        await _stop_listener()
    if cfg and cfg["mode"] == "mailbox" and cfg.get("imap_host") \
            and time.time() - st.get("last_poll", 0) >= cfg["poll_seconds"]:
        st["last_poll"] = time.time()
        try:
            got = await asyncio.get_running_loop().run_in_executor(None, poll_once, cfg)
            st["poll_error"] = None
            st["received"] += len(got)
            notify(got)
        except Exception as e:
            st["poll_error"] = f"{e.__class__.__name__}: {e}"
            print(f"      mail: IMAP check failed: {st['poll_error']}")


async def _supervise():
    while True:
        try:
            mod = sys.modules.get("services.gateway")
            if mod:
                await mod.tick()
        except Exception as e:
            print(f"      mail supervisor: {e!r}")
        await asyncio.sleep(5)


def start():
    """Called by host.py whenever services load (server start and every hot reload)."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    t = state.__dict__.get("MAIL_TASK")
    if t is None or t.done():
        state.MAIL_TASK = loop.create_task(_supervise())


ensure_polling = start  # older name, still called at sign-on
