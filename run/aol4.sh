#!/bin/bash
# (Re)start the AOL 4.0 client in the ~/.wine-aol4 prefix.
W="$HOME/aol-revival/run/wine-aol4"
WINE_AOL_TOOL=wineserver "$W" -k 2>/dev/null; sleep 1
cd "$HOME/.wine-aol4/drive_c/America Online 4.0" && setsid "$W" waol.exe > "$HOME/aol-revival/run/waol4.log" 2>&1 &
