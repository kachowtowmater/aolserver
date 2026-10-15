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

## Sign-on, accounts, sign-off (2026-10-15)
- Dd = Welcome form: de_data screen name, de_data password. "New User" -> sign-up form.
- 3.0 has no async_storename (async atoms stop at 39). Screen-name list = IDB record
  20-0-16: count, then <name padded to 10>\0<10 digits>\0 per entry; host rewrites it.
- Sign Off menu sends pE; host shows the client's Goodbye form 32-5438.
  `**` with data "DISCONNECT" makes AOLASYNC stop P3 (ToolSendMsg 1,0x23,4).
- KNOWN ISSUE: after sign-off, SIGN ON AGAIN in the same process never opens a new
  TCP connection (shows "Checking password..." forever) under Wine; exit + relaunch works.

## Chat / IM / mail / areas
- AOLCHAT tokens: AB <name:10><sep><text> line, CA <slot><name> arrive, CB <slot> leave.
- Aa (chat send) and iS (IM) are de_data streams. IM window = client form 32-223 (object id 223).
- Mail send: m4 MIP streams; reply mip_header_accepted + mip_message_accepted.
  Feeding mip_display_mail_form a synthetic message crashes WAOL -- don't.
- K1 from toolbar carries uni_data <3-byte gid>; f1/k1 carry de_data <4-byte gid>.
- Text in views: CR LF (client drops the byte after a bare CR).
