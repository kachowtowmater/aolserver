# aolserver

A from-scratch host for the original **AOL 3.0 for Windows 95** client. AOL's
real servers were never released, so this one is rebuilt by reverse-engineering
the client from its 1997 install CD.

## Status
Works with the real **AOL 3.0** (1996-98) and **AOL 4.0** (1998-99) Windows clients.
- [x] P3 link layer (CRC-16/ARC; 4.0's '**' no-CRC TCP mode), sequencing, handshake
- [x] Sign-on, New Member sign-up, screen names + passwords, Goodbye/sign-off
- [x] Welcome screen with mail + today's top news
- [x] People Connection: lobbies, room list, Center Stage, LLM-driven chat regulars
- [x] Instant Messages (3.0 and 4.0 windows), Buddy List with live buddy in/out
- [x] E-mail: send, New/Old/Sent mailboxes, You've Got Mail
- [x] Keywords + every Channels/toolbar area with live 2026 content: news,
      quotes, weather, the Web (as text), Wikipedia, files (Internet Archive), deals
- [x] Profiles, Locate Member, Member Directory, Message Boards, Stock Portfolios
- [x] File downloads (3.0): File Search -> Internet Archive -> the client's own Download Manager
- [x] 16k original AOL art records harvested from 73 AOL CD images
- [ ] 3.0: SIGN ON AGAIN after sign-off doesn't reconnect (exit + relaunch works)

## Layout
- `server/` Python asyncio host on TCP 5190 (`python3 server.py`); `test_p3.py`
- `re/NOTES.md` protocol facts confirmed from the client binaries
- `tools/carve_zips.py` extracts the client files from the CD installer
- `run/wine-aol` Wine wrapper for the `~/.wine-aol` prefix
- `run/tools/wctl.c` drives the client's dialogs from the shell
  (build: `aarch64-w64-mingw32-clang -O1 -o wctl.exe wctl.c -luser32`)

## AOL 4.0
Install from the 4.0 CD into its own prefix (`run/wine-aol4`), set `csl/tcp.csl`
to `EXTERN CONNECT localhost 5190` (a dotted IP gets mangled), Expert Setup ->
TCP/IP, and run `client40/patch-aolsec.sh` (turns off the RSA session handshake
that only AOL's servers could answer).

## Running the 3.0 client
1. Get the AOL 3.0 CD (archive.org item
   `Proven_Faster_Internet_Experience_AOL_Version_3.0_PA1097R23`) and run
   `AOL95/SETUP95.EXE` with the Wine version set to `win95`.
2. Move `tool/AOLSOCK.AOL` out of the install (it needs a Win95 VxD).
3. In `ccl/TCP.CCL`, change `AmericaOnline.aol.com` to the server address.
4. Setup -> Edit Location -> Network: TCP/IP, then Sign On.

## References
- WireTap / AtomForge: https://github.com/iconidentify (protocol tools)
- FDO91 docs: http://koin.org/files/aol.aim/aol/fdo/manuals/
