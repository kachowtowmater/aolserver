#!/bin/bash
# AOL 4.0 iwengx32.dll (the "World Wide Web" window's IE host) patch for Wine.
# After CoCreateInstance(CLSID_WebBrowser) the setup routine (0x638039ed) ends with
# IOleControl::FreezeEvents(FALSE) and fails the whole browser if that returns an error.
# Wine's ieframe stubs FreezeEvents with E_NOTIMPL, so AOL destroyed the control before it
# ever navigated (blank, unresponsive window). Patch: the `jge` after that call at
# VA 0x63803ad8 (file offset 0x2ed8, 7D 24) becomes `jmp` (EB 24) -- the result is ignored.
#   usage: patch-iwengx32.sh          apply (original kept in run/disabled-tools-40/iwengx32.dll.orig)
#          patch-iwengx32.sh revert   restore the original
set -e
R="$HOME/aol-revival"; T="$HOME/.wine-aol4/drive_c/America Online 4.0/iwengx32.dll"
O="$R/run/disabled-tools-40/iwengx32.dll.orig"; P="$R/client40/iwengx32.dll.patched"
if [ "$1" = revert ]; then cp -p "$O" "$T"; echo reverted; exit; fi
[ -f "$O" ] || cp -p "$T" "$O"
cp "$O" "$P"
[ "$(od -An -tx1 -j $((0x2ed8)) -N2 "$P" | tr -d ' ')" = 7d24 ] || { echo "unexpected bytes; not patching"; exit 1; }
printf '\xeb' | dd of="$P" bs=1 seek=$((0x2ed8)) conv=notrunc 2>/dev/null
cp "$P" "$T"; echo patched
