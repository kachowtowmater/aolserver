# aolserver

A from-scratch host for the original **AOL 4.0** (and 3.0) for Windows clients. AOL's
real servers were never released, so this one is rebuilt by reverse-engineering
the client from its 1997 install CD.

## Quick start

**Linux / macOS:**
```sh
curl -fsSL https://raw.githubusercontent.com/kachowtowmater/aolserver/main/install.sh | bash
```

**Windows (PowerShell):**
```powershell
git clone https://github.com/kachowtowmater/aolserver.git
cd aolserver
powershell -ExecutionPolicy Bypass -File install.ps1
```

**Or clone and run manually (any OS):**
```sh
git clone https://github.com/kachowtowmater/aolserver.git
cd aolserver
python start.py
```

## Status
Works with the real **AOL 3.0** (1996-98) and **AOL 4.0** (1998-99) Windows clients.
- [x] P3 link layer (CRC-16/ARC; 4.0's '**' no-CRC TCP mode), sequencing, handshake
- [x] Sign-on, New Member sign-up, screen names + passwords, Goodbye/sign-off
- [x] Welcome screen with mail + today's top news
- [x] People Connection: lobbies, room list, Center Stage, LLM-driven chat regulars
- [x] Instant Messages (3.0 and 4.0 windows), Buddy List with live buddy in/out
- [x] E-mail: send, New/Old/Sent mailboxes, You've Got Mail
- [x] Internet mail: `run/mail-setup` — host your own domain (`screenname@yourdomain.com`)
      or use Gmail/Fastmail/iCloud (see "Internet mail" below)
- [x] World Wide Web: headless Chrome renders pages as clickable pictures inside the AOL window,
      with Back/Forward/Reload/Home, an address bar and page scrolling
- [x] Keywords + every Channels/toolbar area with live 2026 content: news,
      quotes, weather, Wikipedia, files (Internet Archive), deals
- [x] Profiles, Locate Member, Member Directory, Message Boards, Stock Portfolios
- [x] File downloads (3.0 + 4.0, up to 15 MB): File Search -> Internet Archive -> the client's own Download Manager
- [x] 16k original AOL art records harvested from 73 AOL CD images
- [x] Sign Off -> Goodbye -> SIGN ON AGAIN (host answers pE with XS, the real host sign-off)

## Layout
- `server/` Python asyncio host on TCP 5190 (`python3 server.py`); `test_p3.py`
- `re/NOTES.md` protocol facts confirmed from the client binaries
- `tools/carve_zips.py` extracts the client files from the CD installer
- `run/wine-aol` Wine wrapper for the `~/.wine-aol` prefix
- `run/tools/wctl.c` drives the client's dialogs from the shell
  (build: `aarch64-w64-mingw32-clang -O1 -o wctl.exe wctl.c -luser32`)

## Internet mail
Mail between members always works. To let members mail the rest of the world, whoever
hosts the server runs **`run/mail-setup`** (interactive) and then `run/mail-setup --test`.
It writes `server/var/gateway.json` (mode 600, never committed); the running server picks
it up within seconds, no restart. `--show`, `--dns`, `--off`/`--on` are also there.

**Option 1 -- use a mail account you already have** (`mode: mailbox`). Outgoing mail goes
through the provider's SMTP; incoming mail is fetched over IMAP every 2 minutes, and mail
for nobody here is left untouched/unread.
- Members get `you+screenname@provider.com` (plus-addressing), or `screenname@yourdomain.com`
  if you own a domain whose catch-all lands in that mailbox (`address_style: catchall`).
- Works with: Gmail (2-Step Verification + App Password), Fastmail (app password),
  iCloud (app-specific password; plus-addressing unverified), Yahoo/AOL Mail (app password,
  catch-all domain only -- no plus-addressing), any other IMAP+SMTP host.
- Not supported: Outlook.com/Hotmail/Microsoft 365 -- they require OAuth sign-in.
- Best practice: a fresh account just for the server, not your personal inbox.

**Option 2 -- host your own domain** (`mode: domain`): members are `screenname@yourdomain.com`
and the server receives that mail itself (built-in SMTP receiver, `server/services/smtpd.py`).
- You need: a domain, access to its DNS, and Internet port 25 reaching this machine. Non-root
  programs can't listen on 25: listen on 2525 and forward router port 25 -> 2525 (or
  `sudo sysctl -w net.ipv4.ip_unprivileged_port_start=25`).
- `run/mail-setup --dns` prints the records: `A` for mail.yourdomain, `MX`, SPF `TXT`,
  DKIM `TXT` (key generated in `server/var/dkim.json`), and a DMARC suggestion.
- Sending out: **relay** through an SMTP service with a login (recommended -- home IPs are
  blocked on port 25 and flagged as spam; e.g. your ISP, SMTP2GO, Mailgun, Brevo, Amazon SES,
  or a Gmail/Fastmail account), or **direct** to each recipient's mail server (needs a static
  IP with reverse DNS and outbound 25 open; `--test` checks that). Outgoing mail is
  DKIM-signed either way.
- The receiver only accepts existing screen names at your domain(s) (never an open relay),
  plus `postmaster@`/`abuse@` and any `aliases` you map to a screen name; it limits message
  size, recipients per message, and connections/messages per IP. Optional STARTTLS: set
  `tls_cert`/`tls_key` in gateway.json.

Tests: `cd server && python3 test_gateway.py` (local stand-ins, no real mail);
`python3 tools/mail_e2e.py` checks member mail end to end against the running host.

## AOL 4.0
**Full setup for Windows, macOS and Linux is in [SETUP.md](SETUP.md).** In short:
`python start.py` runs the host (stdlib Python, no Wine: forms are compiled by
`server/fdo/pycompiler.py`, byte-identical to AOL's own Ada32 compiler), and
`python client40/aol40_client.py fetch` / `configure <AOL dir> --host <name>` gets the
original 4.0 client from archive.org and points it at your host (sets `csl/tcp.csl` --
use a host name, a dotted IP gets mangled -- and turns off the RSA session handshake that
only AOL's servers could answer). The World Wide Web window is rendered server-side by
headless Chrome, see SETUP.md.

**Old Windows (98/XP/2000):** The AOL 4.0 client runs natively — no Wine, no patches.
Just run SETUP.EXE from the CD, point the TCP.CCL at your server, and sign on. See SETUP.md.

## Running the 3.0 client
1. Get the AOL 3.0 CD (archive.org item
   `Proven_Faster_Internet_Experience_AOL_Version_3.0_PA1097R23`) and run
   `AOL95/SETUP95.EXE` with the Wine version set to `win95`.
2. Move `tool/AOLSOCK.AOL` out of the install (it needs a Win95 VxD).
3. In `ccl/TCP.CCL`, change `AmericaOnline.aol.com` to the server address.
4. Setup -> Edit Location -> Network: TCP/IP, then Sign On.

## Let friends connect
Friends don't need the repo or the server — just the AOL 4.0 client pointed at your host.

1. **On a modern machine (Windows/macOS/Linux):** `python client40/aol40_client.py fetch`
   grabs the client from archive.org, then `configure <AOL dir> --host <your-hostname>`
   points it at your server. See SETUP.md for the full steps.
2. **On the same LAN:** use your LAN hostname or IP as `--host`.
3. **Over the internet:** put the server on a VPS with port 5190 open, or use
   [Tailscale](https://tailscale.com/) (invite them to your tailnet — they connect by
   machine name, no port forwarding needed), or port-forward 5190 on your router.

The AOL client mangles dotted IP addresses, so use a hostname when possible (a free
`*.duckdns.org` works if you don't have a domain).

## Known issues (AOL 4.0)
- World Wide Web: pages are rendered server-side as pictures, so typing into a site's own
  search or login boxes doesn't work; use the AOL address bar or Keyword (Ctrl+K) instead.
  Sites that block headless Chrome show an error.
- Features that only existed on AOL's servers and have no 2026 equivalent show an
  explanation window (Pager, Reminder Service) or today's headlines; anything a button asks
  for that the host doesn't know is logged to `run/unmapped.log`.

## References
- WireTap / AtomForge: https://github.com/iconidentify (protocol tools)
- FDO91 docs: http://koin.org/files/aol.aim/aol/fdo/manuals/
