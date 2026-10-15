#!/bin/bash
# (Re)start the AOL 3.0 client in the ~/.wine-aol prefix.
# AOL_DIAG=1: diagnostics mode (WAOL -D) with the client's debug strings in run/waol.log
W="$HOME/aol-revival/run/wine-aol"
pkill -f "WAOL.EXE" 2>/dev/null; sleep 1
args=() dbg="${WINEDEBUG:-err+all}"
[ -n "$AOL_DIAG" ] && args=(-D) dbg="err+all,+debugstr"
cd "$HOME/.wine-aol/drive_c/aol30" && WINEDEBUG="$dbg" setsid "$W" WAOL.EXE "${args[@]}" > "$HOME/aol-revival/run/waol.log" 2>&1 &
