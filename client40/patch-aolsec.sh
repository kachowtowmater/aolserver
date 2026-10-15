#!/bin/bash
# AOL 4.0 aolsec.aol "security off" patch.
# aolsec's StartAolSession (msg 0x37/0, fn 0x62f016c4) checks the global at VA 0x62f236d8
# (.data, file offset 0x21ad8, shipped = 1). When 0 it skips the Wh/Wk handshake and
# broadcasts notify 0x50 (sign-on may proceed) -- the same path the server-signed "Ws"
# security-switch token takes. Patch: that dword 01 -> 00.
#   usage: patch-aolsec.sh          apply (original kept in run/disabled-tools-40/aolsec.aol.orig)
#          patch-aolsec.sh revert   restore the original
set -e
R="$HOME/aol-revival"; T="$R/disc/aol40-installed/tool/aolsec.aol"; O="$R/run/disabled-tools-40/aolsec.aol.orig"
if [ "$1" = revert ]; then cp -p "$O" "$T"; echo reverted; exit; fi
[ -f "$O" ] || cp -p "$T" "$O"
cp "$O" "$R/client40/aolsec.aol.patched"
printf '\x00' | dd of="$R/client40/aolsec.aol.patched" bs=1 seek=$((0x21ad8)) conv=notrunc 2>/dev/null
cp "$R/client40/aolsec.aol.patched" "$T"; echo patched
