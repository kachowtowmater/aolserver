#!/bin/bash
# (Re)start the AOL 3.0 client in the ~/.wine-aol prefix (other prefixes' clients are left alone).
W="$HOME/aol-revival/run/wine-aol"
for p in $(pgrep -x WAOL.EXE); do
  tr '\0' '\n' < /proc/$p/environ 2>/dev/null | grep -qx "WINEPREFIX=$HOME/.wine-aol" && kill "$p"
done
sleep 1
cd "$HOME/.wine-aol/drive_c/aol30" && setsid "$W" WAOL.EXE > "$HOME/aol-revival/run/waol.log" 2>&1 &
