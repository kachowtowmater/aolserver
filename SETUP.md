# Setting up aolserver

**Linux / macOS:** `curl -fsSL https://raw.githubusercontent.com/kachowtowmater/aolserver/main/install.sh | bash`

**Windows (PowerShell):** `git clone https://github.com/kachowtowmater/aolserver.git && cd aolserver && powershell -ExecutionPolicy Bypass -File install.ps1`

Two halves: the **host** (this repo's Python server, runs on any modern OS) and the **client**
(the original 1998 *AOL 4.0 for Windows*, unmodified except for a few bytes, pointed at
your host). AOL 3.0 works too; 4.0 is the main target.

| | Windows 10/11 | Windows 98/XP/2000 | macOS | Linux |
|---|---|---|---|---|
| Host (`start.py`) | Python 3.10+ | no (run host elsewhere) | Python 3.10+ | Python 3.10+ |
| Web pages in AOL (optional) | Chrome/Edge | n/a | Chrome/Chromium | Chrome/Chromium |
| AOL 4.0 client | runs natively | **runs natively** | under Wine (or CrossOver) | under Wine |

> Old Windows (98/XP/2000) machines run the AOL 4.0 client as it was designed — no Wine, no
> patches.  The server needs Python 3.10+, so host it on a modern machine on your LAN and
> point the old Windows client at it.

## 1. The host

```sh
git clone https://github.com/kachowtowmater/aolserver.git
cd aolserver
python start.py            # or: run\windows\start-server.bat on Windows
```

That's the whole host: AOL clients connect to TCP **5190** (open it in your firewall/router
for clients on other machines). Nothing to install: the host uses only Python's standard
library. Data lives in `server/var/` (SQLite: accounts, mail, boards...).

Run it as a service instead:
- **Linux** (systemd user units): `cp run/aol-server.service ~/.config/systemd/user/ && systemctl --user enable --now aol-server`
- **macOS**: edit `REPO` in `run/macos/com.aolserver.host.plist`, copy it to `~/Library/LaunchAgents/`, `launchctl load` it.
- **Windows**: `powershell -ExecutionPolicy Bypass -File run\windows\install-task.ps1` (or the full wizard: `powershell -ExecutionPolicy Bypass -File install.ps1`)

Admin console (local only): `run/admin '<python expression>'`, e.g. `run/admin '[l.session["name"] for l in links]'`.

Optional extras:
- **Chat regulars**: the lobby personas talk through any OpenAI-compatible endpoint; set
  `LLM_URL` / `LLM_MODEL` in `server/services/regulars.py` (they fall back to canned lines).
- **Internet mail / your own domain**: `run/mail-setup` (see README "Internet mail").

## 2. Web pages in AOL (optional)

The World Wide Web window is rendered server-side: the host runs a headless Chrome/Chromium,
screenshots each page, and sends it to the client as a clickable picture with Back, Forward,
Reload, Home, Page Up/Down and an address bar.

Install Chrome or Chromium on the host machine; the server finds it automatically.
Without a browser installed, web pages are shown as text (links still work).
Set `AOL_WEBVIEW=0` to disable the host-side renderer and use the client's own browser
(Wine Gecko under Wine, IE under Windows).

## 3. The AOL 4.0 client

```sh
python client40/aol40_client.py fetch     # downloads the AOL 4.0 CD from archive.org, checks it, unpacks ./aol40-cd
```

### Windows 10/11
1. Run `aol40-cd\SETUP.EXE` (if it refuses, Properties > Compatibility > Windows 98/ME).
   Decline the Internet Explorer 4 / extras offers.
2. `python client40\aol40_client.py configure "C:\America Online 4.0" --host <your host name>`
3. Start AOL, choose **Setup**, and make the location connect by **TCP/IP** (not modem).
4. Sign on with *New User* to create a screen name.

### Linux (Wine)
```sh
export WINEPREFIX=~/.wine-aol4
wine aol40-cd/SETUP.EXE
python client40/aol40_client.py configure ~/.wine-aol4/drive_c/America\ Online\ 4.0 --host localhost --wine
WINEDLLOVERRIDES="mscoree=;inetcpl.cpl=n,b" wine "C:\\America Online 4.0\\waol.exe"
```
`run/wine-aol4` + `run/aol4.sh` are the wrapper/launcher used here (they set those overrides;
`AOL4_PREFIX` picks another prefix).

### macOS (Wine)
Install Wine (e.g. `brew install --cask --no-quarantine wine-stable`, or use CrossOver), then
follow the Linux steps with the same commands. Apple-silicon Macs need Rosetta 2 installed
(Wine runs the x86 client through it); Intel Macs run it directly.

### Old Windows (98 / ME / 2000 / XP)
AOL 4.0 was made for Windows 98 — it runs natively with no emulation, no patches, no
compatibility settings. This is the authentic experience.

1. Get the AOL 4.0 CD image (`aol40_client.py fetch` on a modern machine, then copy the
   `aol40-cd` folder to the old PC — via USB, SMB, burned CD, etc.).
2. Run `SETUP.EXE` from the CD. Decline the Internet Explorer 4 / extras offers.
3. Edit `C:\America Online 4.0\csl\TCP.CSL` in Notepad: find the line with
   `AmericaOnline.aol.com` and replace it with the IP or hostname of the machine running the
   server (e.g. `192.168.1.50`). Save.
4. Start AOL, go to **Setup**, make the location connect by **TCP/IP** (not modem).
5. Sign on with *New User* to create a screen name.

> The `configure` script needs Python 3, which old Windows doesn't have. Editing TCP.CSL by
> hand is all you need — `configure` does the same thing plus disables the RSA handshake
> (the client tolerates the missing handshake and falls through to sign-on).

### Notes
- Use a host **name** in `--host` (the client mangles dotted IP addresses): `localhost`,
  a LAN name, or a DNS name.
- `configure --revert` (with the same flags) restores the original client files.
- What `configure` changes and why is documented at the top of `client40/aol40_client.py`.

## 4. Checking it works

With a client signed on as a throwaway screen name (here `Tester98`, in a separate Wine
prefix so it never disturbs a real user):
- `python tools/sweep40.py` presses every button the client's menus, toolbar, Channels and
  Welcome screens offer and reports any that stall, alert, crash or go unanswered.
- `python tools/areas40.py` opens every host area and follows its first link.
- `python tools/mail_e2e.py` exercises member mail end to end; `python server/test_*.py` are
  the offline tests.

## 5. Let friends connect

Friends only need the AOL 4.0 client pointed at your server — they don't run the host.

**Same LAN:** give them your machine's LAN hostname or address for `--host`.

**Over the Internet:**
- **Easiest:** put the server on a cheap VPS (any $5/mo box — the host is pure stdlib Python,
  needs almost no resources), open port 5190, and give friends the IP or hostname.
- **Tailscale:** invite friends to your tailnet. They use your Tailscale machine name as
  `--host` — no port forwarding, no firewall changes.
- **Port forward:** forward TCP 5190 on your router to the machine running the host.

Use a hostname, not a dotted IP (`192.168...`), because the AOL client mangles raw IPs in
some places. A free dynamic-DNS name (e.g. `*.duckdns.org`) works fine.

**What friends do:**
```sh
git clone https://github.com/kachowtowmater/aolserver.git
cd aolserver
python client40/aol40_client.py fetch
```
Then follow the client setup (section 3) with `--host <your server's hostname>`.
On first sign-on, choose *New User* to create a screen name on your server.

## What's in the repo
- `server/` the host (stdlib Python): `server.py`, `p3.py` link layer, `host.py` dispatcher,
  `services/*` features (hot-reloaded), `fdo/` the client's form language, `forms/` templates,
  `art/` 16k original AOL art records + drawn stand-ins, `data/` client art indexes.
- `client40/` client setup (`aol40_client.py`) and Wine work-arounds.
- `re/` protocol notes (`NOTES.md`) and the client's decoded forms (`idb40/`, `idb/`) used by the tools.
- `tools/` checkers, art builders, the bot client.
- `run/` launch wrappers and service files for Linux/macOS/Windows.
