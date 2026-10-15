#!/bin/bash
# Restart the AOL 4.0 client and sign on.  usage: signon4.sh [screen-name-index password]
W="$HOME/aol-revival/run/wine-aol4"; T="$HOME/aol-revival/run/tools/wctl.exe"
"$HOME/aol-revival/run/aol4.sh"; sleep 18
for i in 1 2 3; do "$W" "$T" click OK >/dev/null 2>&1; done
if [ -n "$1" ]; then
  c=$("$W" "$T" list 2>/dev/null | awk '/"Sign On"/{f=1} f&&/_AOL_Combobox/&&/vis=1/{print $1; exit}')
  "$W" "$T" select "$c" "#$1" >/dev/null 2>&1; sleep 1
  e=$("$W" "$T" list 2>/dev/null | awk '/"Sign On"/{f=1} f&&/_AOL_Edit/&&/vis=1/{print $1; exit}')
  [ -n "$2" ] && "$W" "$T" settext "$e" "$2" >/dev/null 2>&1
fi
s=$("$W" "$T" list 2>/dev/null | awk '/"Sign On"/{f=1} f&&/_AOL_Icon/&&/vis=1/{print $1}' | sed -n 3p)
"$W" "$T" clickh "$s" >/dev/null 2>&1; sleep 15
"$W" "$T" list 2>/dev/null | grep -E 'AOL Child' | head -3
