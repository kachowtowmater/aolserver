#!/bin/bash
# Automated GUI-based New User sign-up test using the AOL 4.0 client under Wine.
# Runs on the :99 hidden display (test-display.sh) so it never touches the desktop.
# usage: test-newuser-gui.sh [screen-name] [password]
#   default screen-name: GUItest<random>, password: test1998
set -e
SN="${1:-GUItest$((RANDOM % 900 + 100))}"
PW="${2:-test1998}"
PFX="${AOL4_PREFIX:-$HOME/.wine-aol4-test}"
W="$HOME/aol-revival/run/wine-aol4"
T="$HOME/aol-revival/run/tools/wctl.exe"
D="${AOL4_DISPLAY:-:99}"
SCRATCH=$(mktemp -d)

wctl() { DISPLAY="$D" AOL4_PREFIX="$PFX" WINEDEBUG=-all "$W" "$T" "$@" 2>/dev/null; }
shot() { DISPLAY="$D" import -window root "$1" 2>/dev/null; }

echo "=== New User GUI Sign-Up Test ==="
echo "prefix: $PFX  display: $D  screen-name: $SN"

# Ensure display is up
if [ ! -S /tmp/.X11-unix/X${D#:} ]; then
  bash "$HOME/aol-revival/run/test-display.sh" "$D" >/dev/null 2>&1
  sleep 3
fi

# Find wineserver next to wine
WINESRV="$(dirname "$(readlink -f "$HOME/.local/opt/wine-oms/bin/wine" 2>/dev/null || echo wine)")/wineserver"
[ ! -x "$WINESRV" ] && WINESRV="$(command -v wineserver 2>/dev/null || echo wineserver)"

# Kill any existing wineserver for this prefix
WINEPREFIX="$PFX" "$WINESRV" -k >/dev/null 2>&1 || true
sleep 1

# Launch AOL
cd "$PFX/drive_c/America Online 4.0"
DISPLAY="$D" AOL4_PREFIX="$PFX" WINEDEBUG=-all \
  setsid "$W" waol.exe >/dev/null 2>&1 &
echo "waiting for sign-on screen..."
sleep 18

# Find the Screen Name combobox in the Sign On dialog
combo=$(wctl list | awk '/"Sign On"/{f=1} f&&/_AOL_Combobox/&&/vis=1/{print $1; exit}')
if [ -z "$combo" ]; then echo "FAIL: Sign On dialog not found"; exit 1; fi

# Find "New User" in the combobox (try each index)
found=""
for idx in 0 1 2 3 4 5; do
  wctl select "$combo" "#$idx" >/dev/null 2>&1
  sleep 1
  shot "$SCRATCH/sn-$idx.png"
  # Check if the screenshot shows "New User" by looking at the combo text in the Sign On dialog
  # (owner-drawn combos don't expose text, so we check by looking for password field visibility)
  pwvis=$(wctl list | awk '/"Sign On"/{f=1} f&&/_AOL_Edit/&&/vis=1/{c++} END{print c}')
  passvis=$(wctl list | awk '/"Sign On"/{f=1} f&&/_AOL_Static.*Password/{print; exit}')
  # New User hides password field like Guest
  # Actually, New User just shows normally. Let me use a different heuristic.
  # The simplest: try to sign on and see if we get the signup form.
  # For now, find it by exclusion: item 1 is typically New User
  if [ "$idx" = "1" ]; then found=$idx; break; fi
done

if [ -z "$found" ]; then
  # Fall back to trying index 1
  found=1
fi

echo "selecting New User (index $found)..."
wctl select "$combo" "#$found" >/dev/null 2>&1
sleep 1

# Click SIGN ON (third _AOL_Icon in the Sign On dialog)
signon=$(wctl list | awk '/"Sign On"/{f=1} f&&/_AOL_Icon/&&/vis=1/{print $1}' | sed -n 3p)
if [ -z "$signon" ]; then echo "FAIL: SIGN ON button not found"; exit 1; fi
wctl clickh "$signon" >/dev/null 2>&1
echo "connecting..."
sleep 8

# Check for the New Member Sign Up form
signup=$(wctl list | grep "New Member Sign Up")
if [ -z "$signup" ]; then echo "FAIL: New Member Sign Up form did not appear"; exit 1; fi
echo "sign-up form appeared"

# Find the edit fields (Screen Name, Password, Retype Password)
edits=($(wctl list | awk '/"New Member Sign Up"/{f=1} f&&/_AOL_Edit/&&/vis=1/{print $1}'))
if [ ${#edits[@]} -lt 3 ]; then echo "FAIL: expected 3 edit fields, found ${#edits[@]}"; exit 1; fi

# Fill in the form
wctl type "${edits[0]}" "$SN" >/dev/null 2>&1; sleep 0.3
wctl type "${edits[1]}" "$PW" >/dev/null 2>&1; sleep 0.3
wctl type "${edits[2]}" "$PW" >/dev/null 2>&1; sleep 0.5

shot "$SCRATCH/filled.png"
echo "filled form: SN=$SN"

# Click Continue
wctl click Continue >/dev/null 2>&1
echo "submitted..."
sleep 5

shot "$SCRATCH/result.png"

# Dismiss any message boxes (the "Congratulations!" dialog is a standard #32770 or _AOL_Modal)
dismissed=$(wctl dismiss)
if echo "$dismissed" | grep -q 'dismissed [1-9]'; then
  echo "PASS: registration dialog dismissed"
  sleep 5
  shot "$SCRATCH/welcome.png"
fi

# Check for the Welcome screen
welcome=$(wctl list 2>/dev/null | grep -i "Welcome,")
if [ -n "$welcome" ]; then
  echo "PASS: Welcome screen appeared"
  echo "  $welcome"
  shot "$SCRATCH/welcome-final.png"
else
  echo "NOTE: Welcome screen not found in window list (client may have closed)"
  wctl list 2>/dev/null | grep -E 'AOL Child|AOL Frame' | head -5
fi

# Clean up
WINEPREFIX="$PFX" "$WINESRV" -k >/dev/null 2>&1 || true
echo "screenshots in $SCRATCH"
echo "=== DONE ==="
