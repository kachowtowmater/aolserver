# aolserver

A from-scratch host for the original **AOL 3.0 for Windows 95** client. AOL's
real servers were never released, so this one is rebuilt by reverse-engineering
the client from its 1997 install CD.

## Status
- [x] P3 link layer: framing, CRC-16/ARC, sequencing, INIT -> ACK handshake
- [x] Real client runs on Linux/aarch64 (Wine + FEX) and connects
- [ ] Sign-on (`Dd`) -> Welcome screen
- [ ] Forms (FDO atom streams), keywords, chat, IM, mail

## Layout
- `server/` Python asyncio host on TCP 5190 (`python3 server.py`); `test_p3.py`
- `re/NOTES.md` protocol facts confirmed from the client binaries
- `tools/carve_zips.py` extracts the client files from the CD installer
- `run/wine-aol` Wine wrapper for the `~/.wine-aol` prefix
- `run/tools/wctl.c` drives the client's dialogs from the shell
  (build: `aarch64-w64-mingw32-clang -O1 -o wctl.exe wctl.c -luser32`)

## Running the client
1. Get the AOL 3.0 CD (archive.org item
   `Proven_Faster_Internet_Experience_AOL_Version_3.0_PA1097R23`) and run
   `AOL95/SETUP95.EXE` with the Wine version set to `win95`.
2. Move `tool/AOLSOCK.AOL` out of the install (it needs a Win95 VxD).
3. In `ccl/TCP.CCL`, change `AmericaOnline.aol.com` to the server address.
4. Setup -> Edit Location -> Network: TCP/IP, then Sign On.

## References
- WireTap / AtomForge: https://github.com/iconidentify (protocol tools)
- FDO91 docs: http://koin.org/files/aol.aim/aol/fdo/manuals/
