# AOL 3.0 client RE notes

Source: US disc PA1097R23 (archive.org), `AOL95/SETUP95.EXE` carved with
`tools/carve_zips.py` -> `disc/client/`. Decompile: `codemap decompile
disc/client/AOLP3.AOL -o re/codemap/aolp3.c`.

## Connection
- `TCP.CCL`: `NetConnect 1 5190 10 AmericaOnline.aol.com` -> redirect that
  hostname (hosts file) or edit TCP.CCL to reach our server.

## P3 link layer (AOLP3.AOL, 23 KB)
- Build fn 0x100024d0: `5A | CRC(BE) | LEN(BE) | TX | RX | TYPE|0x80 | payload | 0D`
- LEN = payload + 3. CRC = CRC-16/ARC (table @0x10007098) over buf[3 .. 8+payload).
- Receive dispatch 0x10001da6: index = type - 0x20, no 0x80 mask, so the server
  sends bare types. Handled: DATA 20, ACK 24, NAK 25, HBEAT 26, RESET 28 (ignored),
  RAK 29, ACKNOW 2B. Anything else -> "Got unexpected packet type".
- State 0x10005114: 0 INIT_SENT, 1 CONNECTED, 2 game/exit, 3 ?.
  ACK while INIT_SENT -> CONNECTED + posts msg 0xff01/0x12 (link up).
  RAK with payload[0]==1 -> back to INIT_SENT (re-init); ==2 -> CONNECTED.
- Seq 16..127 wrapping (min @0x1000601c, max @0x10006020); tx and rx both start at 127.
  DATA must carry tx == next(last rx) else NAK code 2. Client DATA payload <= 0x77.
- INIT packet body comes from the IDB (MAIN.IDX) via SUPERSUB!IDB_Get.

## Next
- Decompile AOL.EXE / AOLATOM / AOLMAN to map sign-on DATA tokens.
- Extract MAIN.IDX records (built-in FDO forms, INIT packet).
