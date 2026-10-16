#!/bin/bash
# A private X display (:99, 1600x1100) for the AOL test client: rootful Xwayland parked on a
# hidden Hyprland workspace (10).  Screenshot with:  DISPLAY=:99 import -window root shot.png
D=${1:-:99}
if [ ! -S /tmp/.X11-unix/X${D#:} ]; then
  setsid Xwayland "$D" -geometry 1600x1100 -noreset >/dev/null 2>&1 &
  sleep 3
fi
if command -v hyprctl >/dev/null; then
  pid=$(pgrep -f "Xwayland $D" | head -1)
  hyprctl dispatch "hl.dsp.window.move({window = \"pid:$pid\", workspace = \"10\", follow = false})" >/dev/null
  hyprctl dispatch "hl.dsp.window.float({window = \"pid:$pid\"})" >/dev/null
  hyprctl dispatch "hl.dsp.window.resize({window = \"pid:$pid\", x = 1600, y = 1100})" >/dev/null
fi
echo "test display $D ready"
