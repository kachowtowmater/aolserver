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

## File transfer (downloads, AOLXFER.AOL) -- 2026-10-15, verified end to end
Implemented in server/services/xfer.py. AOLXFER registers a catch-all token handler
(0x10001138) and atom protocol 7 (0x100015b2). Client->host packets are raw tokens
(ToolSendMsg 1,0x23,6), no stream id. Sequence for one "Download Now":
1. host `aT` stream: `xfer_start_object <0>` (0 = now, 1 = Download Later), `xfer_atr_request_id <u32>`,
   `xfer_atr_title <str\0, max 0x21>`, `xfer_atr_file_size <u32>`, `xfer_atr_file_name <str\0>`,
   `xfer_atr_create_date <u32 secs since 1980>`, `xfer_bool_mail <0>`, `xfer_atr_library <str\0, max 0x14>`,
   `xfer_end_object`. Ints are big-endian. end_object -> 0x100023bb -> 0x10002462: DL-manager db
   check by request id ("You have already downloaded this file" if reused -- use fresh ids),
   then the "Download Manager" Save As dialog (default dir C:\aol30\download\).
   Same can be started by tokens `tj`/`ti` (0x10005de3 record: [0] mail, [1..3] id, ...) -- unused.
2. client `eJ` 00 <chosen full DOS path> (`ej` when xfer_bool_mail was set; `eK` alone = Cancel).
   The path's first byte lands in our "stream id" field: path = stream_id&0xff + body.
3. host `tf` (0x10003130): [0] flags (0x20 = show File Transfer progress dialog, 0x80 = upload),
   [1..3] file size, 3 bytes LITTLE-endian (progress %), [4] 0, [5] must not be F7 (F7 + [6..7]=0x0187
   strips a 32-byte header from the first block), [6..0x12] 0, [0x13..] file name (client keeps
   only the part after the last '\' and writes it into the dir picked in step 2), then
   `\x90` + 2-byte token + `\0`: the client sends that 2-byte token when the file is finished
   (we use `xD`). Without \x90 it sends garbage bytes [0x12..0x13] as a token. Name+\x90 must sit
   within 0x57 bytes. `tT` = same with an extra byte at [1] (everything shifted by 1).
4. client `xG` = file opened, send data (`xA` ff = open failed; `xA` fd/ff also = user cancelled
   mid-transfer after "Are you sure...").
5. host data packets, payload = token + data (no length/offset fields):
   `F7` write, no reply; `F8` or `FF` write, then client replies `xG` (flow control / window);
   `F9` last packet: write (may be empty), close file, play "File's Done", show
   "<title> has been transferred.", send the \x90 token from tf. No `fX` needed for downloads
   (`fX` is the upload/batch "File transfer complete." path).
   Data decoding (0x10004458): `]` (0x5D) = escape, next byte ^ 0x55; `[` (0x5B) = RLE: pops the
   last 2 bytes written <b><n> and writes b (n+1) times. So literal 0x5B/0x5D must go as
   5D 0E / 5D 08; all other bytes are literal. The tool's data length counts one byte more than
   the token body (its write loop runs len-1 times), so send no padding.
   Data packets without an active transfer -> "No File Transfer in Progress, Rejecting Packet...".
- We send 880-byte (escaped) packets in windows of 8 (7x F7 + F8, wait for xG): 1.5 MB in ~15 s
  under Wine; sha1 of a small text file full of brackets, a 1.5 MB all-bytes test blob and an archive.org .zip all match.
- File Search (areas.py): result -> description window listing the item's files <= 2 MB
  (archive.org/metadata) + "Download Now" (best pick: zip/exe/com/... original, md5-checked).
