"""run/mail-setup: turn on Internet mail for this AOL host (writes server/var/gateway.json).

  mail-setup                 interactive setup (pick a provider, or host your own domain)
  mail-setup --test          check logins/DNS/ports for real -- never sends any mail
  mail-setup --show          print the current setup (passwords hidden)
  mail-setup --dns           print the DNS records to create (domain mode)
  mail-setup --off | --on    pause / resume outside mail without losing the settings
Non-interactive:  mail-setup --preset gmail --user you@gmail.com --password-stdin
                  mail-setup --mode domain --domain my90s.net --listen-port 2525 \\
                             --outbound relay --smtp-host smtp.example.net --smtp-user u --password-stdin
The running server picks up changes within a few seconds; no restart needed.
"""
import argparse
import getpass
import imaplib
import json
import os
import smtplib
import socket
import ssl
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from services import dkim, gateway, maildns  # noqa: E402

# AOL_MAIL_CONF / AOL_DKIM_KEY point the tool at other files (for trying it out safely)
if os.environ.get("AOL_MAIL_CONF"):
    gateway.CONF = Path(os.environ["AOL_MAIL_CONF"])
if os.environ.get("AOL_DKIM_KEY"):
    dkim.KEY = Path(os.environ["AOL_DKIM_KEY"])
CONF = gateway.CONF

PRESETS = {
    "gmail": {"name": "Gmail", "smtp_host": "smtp.gmail.com", "smtp_port": 587, "smtp_security": "starttls",
              "imap_host": "imap.gmail.com", "plus": True,
              "note": "Needs 2-Step Verification and an App Password (myaccount.google.com > Security > "
                      "App passwords). Your normal Google password will not work."},
    "fastmail": {"name": "Fastmail", "smtp_host": "smtp.fastmail.com", "smtp_port": 465, "smtp_security": "ssl",
                 "imap_host": "imap.fastmail.com", "plus": True,
                 "note": "Make an app password under Settings > Privacy & Security > Integrations."},
    "icloud": {"name": "iCloud Mail", "smtp_host": "smtp.mail.me.com", "smtp_port": 587,
               "smtp_security": "starttls", "imap_host": "imap.mail.me.com", "plus": None,
               "note": "Needs an app-specific password (account.apple.com > Sign-In and Security). "
                       "Plus-addressing on iCloud is not verified; if replies don't arrive, use a custom "
                       "domain with catch-all instead."},
    "yahoo": {"name": "Yahoo / AOL Mail", "smtp_host": "smtp.mail.yahoo.com", "smtp_port": 465,
              "smtp_security": "ssl", "imap_host": "imap.mail.yahoo.com", "plus": False,
              "note": "Needs an app password. Yahoo has no plus-addressing, so use it only with a custom "
                      "domain whose catch-all delivers to this mailbox."},
    "other": {"name": "Other (any IMAP + SMTP provider)", "plus": None, "note": ""},
}
NO_GO = ("Outlook.com / Hotmail / Microsoft 365 need OAuth sign-in, which this host doesn't do. "
         "Pick another provider, or host your own domain.")


# ---------- file ----------

def load() -> dict:
    try:
        return json.loads(CONF.read_text())
    except Exception:
        return {}


def save(cfg: dict):
    CONF.parent.mkdir(exist_ok=True)
    tmp = CONF.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(cfg, f, indent=2)
    os.chmod(tmp, 0o600)
    tmp.replace(CONF)
    print(f"Saved {CONF} (readable only by you). The AOL server picks it up within a few seconds.")


def masked(cfg: dict) -> dict:
    return {k: ("********" if "password" in k and v else v) for k, v in cfg.items()}


# ---------- prompts ----------

def ask(prompt, default=None, choices=None):
    while True:
        hint = f" [{default}]" if default not in (None, "") else ""
        v = input(f"{prompt}{hint}: ").strip() or (str(default) if default is not None else "")
        if not choices or v in choices:
            return v
        print(f"  Please answer one of: {', '.join(choices)}")


def ask_password(prompt):
    while True:
        p = getpass.getpass(f"{prompt}: ").replace(" ", "")  # app passwords are shown with spaces
        if p:
            return p


def wizard() -> dict:
    print(__doc__.split("\n\n")[0].strip(), "\n")
    print("How should Internet mail work?\n"
          "  1) Use a mail account I already have (Gmail, Fastmail, iCloud, Yahoo, other)\n"
          "     Members get you+screenname@provider.com; this host checks the mailbox every 2 minutes.\n"
          "  2) Host my own domain: members get screenname@mydomain.com, received right here.\n"
          "     Needs a domain you control, DNS access, and TCP port 25 reachable from the Internet.\n"
          "  (Outlook/Hotmail can't be used: " + NO_GO.split(", which")[0].split("need ")[1] + " is not supported.)")
    if ask("Choose", "1", ["1", "2"]) == "2":
        return wizard_domain()
    names = list(PRESETS)
    for i, k in enumerate(names, 1):
        print(f"  {i}) {PRESETS[k]['name']}")
    p = PRESETS[names[int(ask("Provider", "1", [str(i) for i in range(1, len(names) + 1)])) - 1]]
    if p["note"]:
        print("\n" + p["note"] + "\n")
    cfg = {"mode": "mailbox"}
    cfg["user"] = ask("Mailbox address (the account's e-mail)")
    if "outlook." in cfg["user"] or "hotmail." in cfg["user"] or "live.com" in cfg["user"]:
        sys.exit(NO_GO)
    cfg["password"] = ask_password("App password")
    cfg["smtp_host"] = p.get("smtp_host") or ask("SMTP server (outgoing)")
    cfg["smtp_security"] = p.get("smtp_security") or ask("SMTP security", "starttls", ["starttls", "ssl", "none"])
    cfg["smtp_port"] = int(p.get("smtp_port") or ask("SMTP port", {"ssl": 465, "starttls": 587, "none": 25}[
        cfg["smtp_security"]]))
    cfg["imap_host"] = p.get("imap_host") or ask("IMAP server (incoming)")
    print("\nMember addresses:\n"
          f"  plus      {cfg['user'].split('@')[0]}+screenname@{cfg['user'].split('@')[1]}  (needs plus-addressing)\n"
          "  catchall  screenname@yourdomain.com  (you own a domain whose catch-all lands in this mailbox)")
    style = ask("Address style", "plus" if p["plus"] is not False else "catchall", ["plus", "catchall"])
    cfg["address_style"] = style
    if style == "catchall":
        cfg["domain"] = ask("Your domain (e.g. my90s.net)").lower()
    return cfg


def wizard_domain() -> dict:
    cfg = {"mode": "domain"}
    cfg["domain"] = ask("Your domain (members become screenname@this)").lower().strip(".")
    print("\nIncoming mail arrives on TCP port 25. Programs that aren't root can't listen on 25, so the\n"
          "usual setup is: listen on 2525 here and have your router forward Internet port 25 -> 2525.\n"
          "(Or allow it: sudo sysctl -w net.ipv4.ip_unprivileged_port_start=25, then use 25.)")
    cfg["listen_port"] = int(ask("Listen port", 2525))
    cfg["postmaster"] = ask("Screen name that receives postmaster@/abuse@ mail", "")
    if not cfg["postmaster"]:
        cfg.pop("postmaster")
    print("\nSending mail out:\n"
          "  relay   through an SMTP service with a login (recommended -- home Internet connections are\n"
          "          blocked on port 25 and their mail is treated as spam; e.g. your ISP, SMTP2GO, Mailgun,\n"
          "          Brevo, Amazon SES, or a Gmail/Fastmail account)\n"
          "  direct  straight to each recipient's mail server (needs a static IP with reverse DNS and\n"
          "          outgoing port 25 open)")
    cfg["outbound"] = ask("Outbound", "relay", ["relay", "direct"])
    if cfg["outbound"] == "relay":
        cfg["smtp_host"] = ask("Relay SMTP server")
        cfg["smtp_security"] = ask("Relay security", "starttls", ["starttls", "ssl", "none"])
        cfg["smtp_port"] = int(ask("Relay port", {"ssl": 465, "starttls": 587, "none": 25}[cfg["smtp_security"]]))
        cfg["smtp_user"] = ask("Relay login (user name)")
        cfg["smtp_password"] = ask_password("Relay password")
    cfg["dkim"] = True
    return cfg


# ---------- DNS records ----------

def dns_text(cfg: dict) -> str:
    s = gateway.settings(cfg)
    if s["mode"] != "domain":
        if s.get("address_style") == "catchall":
            return (f"Point {s['domains'][0]}'s mail at your provider (its MX records) and turn on catch-all "
                    f"delivery to {s['user']}. Follow your provider's custom-domain guide for SPF/DKIM.")
        return "Mailbox mode with plus-addressing needs no DNS changes."
    d = s["domains"][0]
    k = dkim.ensure_key()
    spf = (f"v=spf1 mx include:<your relay's SPF domain> ~all" if s["outbound"] == "relay"
           else "v=spf1 mx ~all")
    txt = dkim.dns_record(k)
    chunks = " ".join(f'"{txt[i:i + 250]}"' for i in range(0, len(txt), 250))
    rows = [(f"mail.{d}.", "A", "<this host's public IPv4 address>"), (f"{d}.", "MX", f"10 mail.{d}."),
            (f"{d}.", "TXT", f'"{spf}"'), (f"{s['dkim_selector']}._domainkey.{d}.", "TXT", chunks),
            (f"_dmarc.{d}.", "TXT", f'"v=DMARC1; p=none; rua=mailto:postmaster@{d}"')]
    w = max(len(r[0]) for r in rows)
    return "\n".join([
        f"Create these DNS records for {d} (at your domain registrar / DNS host):",
        "",
        *(f"  {name:<{w}}  {kind:<4} {value}" for name, kind, value in rows),
        "",
        f"Router: forward TCP port 25 (Internet) -> this machine, port {s['listen_port']}.",
        "Also ask your ISP / host to set reverse DNS (PTR) for your IP to mail." + d + " if you send direct.",
        ("Relay: check your relay's docs for the exact SPF include (e.g. include:mailgun.org)."
         if s["outbound"] == "relay" else
         "Direct sending: most home ISPs block outgoing port 25; --test checks this."),
    ])


# ---------- tests (no mail is ever sent) ----------

def _ok(cond, what, detail=""):
    print(("  OK    " if cond else "  FAIL  ") + what + (f" -- {detail}" if detail else ""))
    return bool(cond)


def test(cfg: dict) -> bool:
    s = gateway.settings(cfg)
    if not s:
        print("Internet mail is not set up (run mail-setup).")
        return False
    good = True
    print(f"Mode: {s['mode']}, addresses like {gateway.member_address(s, 'YourName')}")

    # --- local checks (everything this host controls) ---
    print("\n  Local checks (this host):")
    if s["mode"] == "mailbox" or s.get("outbound") == "relay":
        try:
            with gateway._smtp_login(s, timeout=20) as smtp:
                smtp.noop()
            good &= _ok(True, f"SMTP login to {s['smtp_host']}:{s['smtp_port']}")
        except smtplib.SMTPAuthenticationError as e:
            good &= _ok(False, "SMTP login", f"refused: {e.smtp_error.decode(errors='replace')[:120]}")
        except Exception as e:
            good &= _ok(False, f"SMTP connection to {s.get('smtp_host')}", repr(e))
    if s["mode"] == "mailbox":
        try:
            with gateway._imap(s) as im:
                _, n = im.select("INBOX", readonly=True)
            good &= _ok(True, f"IMAP login to {s['imap_host']}", f"{n[0].decode()} messages in INBOX")
        except imaplib.IMAP4.error as e:
            good &= _ok(False, "IMAP login", str(e)[:120])
        except Exception as e:
            good &= _ok(False, f"IMAP connection to {s.get('imap_host')}", repr(e))
        return good

    d = s["domains"][0]
    try:
        with socket.create_connection(("127.0.0.1", s["listen_port"]), timeout=5) as c:
            banner = c.recv(200)
            c.sendall(b"QUIT\r\n")
        good &= _ok(banner.startswith(b"220"), f"SMTP receiver on port {s['listen_port']}")
    except OSError as e:
        good &= _ok(False, f"SMTP receiver on port {s['listen_port']}",
                    f"{e} (is aol-server running? it starts the receiver within 5 s of saving)")
    k = dkim.ensure_key()
    good &= _ok(k and k["n"].bit_length() == 2048, "DKIM key (2048-bit RSA)")
    msg = gateway.build_message(s, "TestUser", ["test@example.com"], [], "DKIM check", "test")
    raw = msg.as_bytes()
    if s.get("dkim"):
        signed = dkim.sign(raw, d, s["dkim_selector"], k)
        good &= _ok(dkim.verify(signed, k), "DKIM sign-then-verify")
    good &= _ok(gateway.member_address(s, "TestUser") == f"testuser@{d}", "address generation")
    store = sys.modules.get("services.store")
    if store and store.account("TestUser"):
        good &= _ok(gateway.owner_for(s, f"testuser@{d}") == "testuser", "inbound routing")

    # --- DNS checks (need records published at your registrar) ---
    print("\n  DNS checks (your domain's records):")
    dns_ok = True
    try:
        mx = maildns.query(d, "MX")
        dns_ok &= _ok(bool(mx), f"MX record for {d}",
                       ", ".join(h for _, h in sorted(mx)) if mx else "not found -- see --dns")
        for _, host in sorted(mx)[:1]:
            ips = maildns.query(host, "A")
            _ok(bool(ips), f"A record for {host}", ", ".join(ips) or "not found")
        txts = maildns.query(d, "TXT")
        dns_ok &= _ok(any(t.startswith("v=spf1") for t in txts), f"SPF record for {d}")
        dk = maildns.query(f"{s['dkim_selector']}._domainkey.{d}", "TXT")
        dns_ok &= _ok(any(dkim.dns_record(k).split("p=")[1] in t.replace(" ", "") for t in dk),
                      "DKIM record matches this host's key")
        _ok(any(t.startswith("v=DMARC1") for t in maildns.query(f"_dmarc.{d}", "TXT")),
            "DMARC record (optional)")
    except OSError as e:
        dns_ok &= _ok(False, "DNS lookups", str(e))
    if not dns_ok:
        print("\n  DNS records not found. If you just created them, allow up to 48 hours for propagation.")
        print(f"  Run: {sys.argv[0]} --dns   to see the records to create.")

    # --- network checks (outbound reachability) ---
    if s.get("outbound") == "direct":
        print("\n  Network checks:")
        try:
            with socket.create_connection((maildns.mx_hosts("gmail.com")[0], 25), timeout=8) as c:
                ok = c.recv(100).startswith(b"220")
                c.sendall(b"QUIT\r\n")
            good &= _ok(ok, "outgoing port 25 (connected to Gmail's MX, sent nothing)")
        except OSError as e:
            good &= _ok(False, "outgoing port 25",
                        f"blocked? {e} -- switch to a relay (mail-setup, option 1)")

    local_pass = good
    print(f"\n  Local: {'ALL OK' if local_pass else 'ISSUES FOUND'}"
          f"   DNS: {'OK' if dns_ok else 'records missing (see --dns)'}")
    if local_pass and not dns_ok:
        print("  The server code is ready. Create the DNS records above and re-run --test.")
    print(f"\n  From outside, also verify port 25 reaches this host (e.g. an online SMTP check tool"
          f"\n  pointed at mail.{d}).")
    return good


# ---------- main ----------

def main():
    ap = argparse.ArgumentParser(description="Set up Internet mail for the AOL host.",
                                 formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    ap.add_argument("--test", action="store_true")
    ap.add_argument("--show", action="store_true")
    ap.add_argument("--dns", action="store_true")
    ap.add_argument("--off", action="store_true")
    ap.add_argument("--on", action="store_true")
    ap.add_argument("--preset", choices=[k for k in PRESETS if k != "other"])
    ap.add_argument("--mode", choices=["mailbox", "domain"])
    for opt in ("user", "domain", "imap-host", "smtp-host", "smtp-user", "outbound", "address-style",
                "smtp-security", "postmaster"):
        ap.add_argument(f"--{opt}")
    ap.add_argument("--smtp-port", type=int)
    ap.add_argument("--listen-port", type=int)
    ap.add_argument("--password-stdin", action="store_true", help="read the password from standard input")
    a = ap.parse_args()

    cfg = load()
    if a.show:
        print(json.dumps(masked(cfg), indent=2) if cfg else "Internet mail is not set up.")
        return
    if a.off or a.on:
        if not cfg:
            sys.exit("Nothing to turn on/off yet: run mail-setup first.")
        cfg["disabled"] = bool(a.off)
        save(cfg)
        return
    if a.dns:
        print(dns_text(cfg) if cfg else "Run mail-setup first.")
        return
    if a.test:
        sys.exit(0 if test(cfg) else 1)

    if a.preset or a.mode:  # non-interactive
        cfg = {"mode": a.mode or "mailbox"}
        if a.preset:
            p = PRESETS[a.preset]
            cfg.update({k: p[k] for k in ("smtp_host", "smtp_port", "smtp_security", "imap_host")})
            cfg["address_style"] = "plus" if p["plus"] is not False else "catchall"
        for opt in ("user", "domain", "imap_host", "smtp_host", "smtp_user", "outbound", "address_style",
                    "smtp_security", "postmaster", "smtp_port", "listen_port"):
            v = getattr(a, opt)
            if v is not None:
                cfg[opt] = v
        if a.password_stdin:
            pw = sys.stdin.readline().strip().replace(" ", "")
            cfg["password" if cfg["mode"] == "mailbox" else "smtp_password"] = pw
        if cfg["mode"] == "domain":
            cfg.setdefault("listen_port", 2525)
            cfg["dkim"] = True
        if not gateway.settings(cfg) or (cfg["mode"] == "mailbox" and "@" not in cfg.get("user", "")) or \
                (cfg["mode"] == "domain" and not cfg.get("domain")):
            sys.exit("Incomplete: mailbox mode needs --user (and a preset or hosts); domain mode needs --domain.")
    else:
        cfg = wizard()
    save(cfg)
    if cfg["mode"] == "domain":
        dkim.ensure_key()
        print("\n" + dns_text(cfg))
    print("\nNext: run/mail-setup --test   (checks logins/DNS without sending any mail)")


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        sys.exit("\nCancelled; nothing changed.")
