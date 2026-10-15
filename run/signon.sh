#!/bin/bash
# Restart the AOL client and press SIGN ON (Welcome screen's third icon).
W="$HOME/aol-revival/run/wine-aol"; T="$HOME/aol-revival/run/tools/wctl.exe"
"$HOME/aol-revival/run/aol.sh"; sleep 14
for i in 1 2 3; do "$W" "$T" click OK >/dev/null 2>&1; done
s=$("$W" "$T" list 2>/dev/null | awk '/"Welcome"/{f=1} f&&/_AOL_Icon/{n++; if(n==3){print $1; exit}}')
"$W" "$T" clickh "$s" >/dev/null 2>&1; sleep 10
"$W" "$T" list 2>/dev/null | grep -E '^[0-9A-F]|AOL Child'
