# Setting up aolserver

Two halves: the **host** (this repo's Python server, runs anywhere) and the **client**
(the original 1998 *AOL 4.0 for Windows*, unmodified except for a few bytes, pointed at
your host). AOL 3.0 works too; 4.0 is the main target.

| | Windows 10/11 | macOS | Linux |
|---|---|---|---|
| Host (`start.py`) | Python 3.10+ | Python 3.10+ | Python 3.10+ |
| Web pages in AOL 4.0 (WRP, optional) | Go + Chrome/Edge | Go + Chrome | Go + Chrome/Chromium |
| AOL 4.0 client | runs natively | under Wine (or CrossOver) | under Wine |

> Status: everything below is used daily on Linux (aarch64, Wine + FEX). The Windows and
> macOS steps use the same scripts but haven't been run on real Windows/Mac hardware yet;
> please report what you hit.

## 1. The host

```sh
git clone git@github.com:kachowtowmater/aolserver.git
cd aolserver
python start.py            # Windows: run\windows\start-server.bat
```

That's the whole host: AOL clients connect to TCP **5190** (open it in your firewall/router
for clients on other machines). Nothing to install: the host uses only Python's standard
library. Data lives in `server/var/` (SQLite: accounts, mail, boards...).

Run it as a service instead:
- **Linux** (systemd user units): `cp run/aol-server.service run/aol-wrp.service ~/.config/systemd/user/ && systemctl --user enable --now aol-server aol-wrp`
- **macOS**: edit `REPO` in `run/macos/com.aolserver.host.plist`, copy it to `~/Library/LaunchAgents/`, `launchctl load` it.
- **Windows**: `powershell -ExecutionPolicy Bypass -File run\windows\install-task.ps1`

Admin console (local only): `run/admin '<python expression>'`, e.g. `run/admin '[l.session["name"] for l in links]'`.

Optional extras:
- **Chat regulars**: the lobby personas talk through any OpenAI-compatible endpoint; set
  `LLM_URL` / `LLM_MODEL` in `server/services/regulars.py` (they fall back to canned lines).
- **Internet mail / your own domain**: `run/mail-setup` (see README "Internet mail").

## 2. Web pages in AOL 4.0 (optional): WRP

AOL 4.0's World Wide Web window is Internet Explorer's engine (on Wine: Wine Gecko, a 2016
engine). To show 2026 sites it goes through **WRP** (Web Rendering Proxy): a headless modern
Chrome loads the page and returns a clickable picture of it.

```sh
git clone --depth 1 https://github.com/tenox7/wrp vendor/wrp
cd vendor/wrp && git apply ../../client40/wrp-nav-timeout.patch && go build -o wrp .   # wrp.exe on Windows
cd ../.. && python start.py      # now also starts WRP on 127.0.0.1:8098
```

`start.py --web-listen 0.0.0.0:8098` lets clients on other machines use it (only do that on
a trusted network: it fetches any URL it's asked for).

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
wine aol40-cd/SETUP.EXE                       # let Wine install Gecko when it asks
python client40/aol40_client.py configure ~/.wine-aol4/drive_c/America\ Online\ 4.0 --host localhost --wine
python client40/aol40_client.py web --wine-prefix ~/.wine-aol4      # if you run WRP
WINEDLLOVERRIDES="mscoree=;inetcpl.cpl=n,b" wine "C:\\America Online 4.0\\waol.exe"
```
`run/wine-aol4` + `run/aol4.sh` are the wrapper/launcher used here (they set those overrides;
`AOL4_PREFIX` picks another prefix). `client40/setup-web.sh` does the WRP + Gecko steps in one go.

### macOS (Wine)
Install Wine (e.g. `brew install --cask --no-quarantine wine-stable`, or use CrossOver), then
follow the Linux steps with the same commands. Apple-silicon Macs need Rosetta 2 installed
(Wine runs the x86 client through it); Intel Macs run it directly.

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

## What's in the repo
- `server/` the host (stdlib Python): `server.py`, `p3.py` link layer, `host.py` dispatcher,
  `services/*` features (hot-reloaded), `fdo/` the client's form language, `forms/` templates,
  `art/` 16k original AOL art records + drawn stand-ins, `data/` client art indexes.
- `client40/` client setup (`aol40_client.py`), Wine work-arounds, WRP patch.
- `re/` protocol notes (`NOTES.md`) and the client's decoded forms (`idb40/`, `idb/`) used by the tools.
- `tools/` checkers, art builders, the bot client.
- `run/` launch wrappers and service files for Linux/macOS/Windows.
