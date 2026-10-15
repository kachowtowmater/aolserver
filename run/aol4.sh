#!/bin/bash
# (Re)start the AOL 4.0 client in the ~/.wine-aol4 prefix (or $AOL4_PREFIX, e.g. a test copy).
W="$HOME/aol-revival/run/wine-aol4"
WINE_AOL_TOOL=wineserver "$W" -k 2>/dev/null; sleep 1
P="${AOL4_PREFIX:-$HOME/.wine-aol4}"; LOG="$HOME/aol-revival/run/waol4${AOL4_PREFIX:+-$(basename "$AOL4_PREFIX")}.log"
cd "$P/drive_c/America Online 4.0" && setsid "$W" waol.exe > "$LOG" 2>&1 &
