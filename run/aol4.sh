#!/bin/bash
# (Re)start the AOL 4.0 client in the ~/.wine-aol4 prefix (or $AOL4_PREFIX, e.g. a test copy).
W="$HOME/aol-revival/run/wine-aol4"
WINE_AOL_TOOL=wineserver "$W" -k 2>/dev/null; sleep 1
# AOL4_DISPLAY=:99 runs the client inside that X display (e.g. a rootful Xwayland parked on a
# hidden workspace: run/test-display.sh) -- invisible to whoever uses the desktop, yet screenshot-able.
if [ -n "$AOL4_DISPLAY" ]; then export DISPLAY="$AOL4_DISPLAY"; unset WAYLAND_DISPLAY; fi
P="${AOL4_PREFIX:-$HOME/.wine-aol4}"; LOG="$HOME/aol-revival/run/waol4${AOL4_PREFIX:+-$(basename "$AOL4_PREFIX")}.log"
cd "$P/drive_c/America Online 4.0" && setsid "$W" waol.exe > "$LOG" 2>&1 &
# A test copy (AOL4_PREFIX set) goes to workspace 10 (the laptop screen) so it never covers the
# real client: wait for its window, then move it there without following.
if [ -n "$AOL4_PREFIX" ] && [ -z "$AOL4_DISPLAY" ] && command -v hyprctl >/dev/null; then
  (for i in $(seq 60); do
     sleep 1
     A=$(hyprctl clients -j | python3 -c '
import json,sys,os
pre=os.environ["AOL4_PREFIX"]
for c in json.load(sys.stdin):
    if c["class"]=="waol.exe":
        try: env=open("/proc/%d/environ" % c["pid"],"rb").read()
        except OSError: continue
        if pre.encode() in env: print(c["address"], c["workspace"]["name"])' | head -1)
     case "$A" in
       *" 10") break ;;  # already there
       ?*) hyprctl dispatch "hl.dsp.window.move({window = \"address:${A% *}\", workspace = \"10\", follow = false})"; break ;;
     esac
   done) >/dev/null 2>&1 </dev/null &
fi
