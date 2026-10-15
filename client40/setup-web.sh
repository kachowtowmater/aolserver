#!/bin/bash
# Make AOL 4.0's own World Wide Web window show 2026 web pages.
#
# AOL 4.0's browser is Wine's IE (Wine Gecko 2.47, a 2016 engine), which breaks on modern sites.
# So its http:// traffic goes through WRP (Web Rendering Proxy): a modern headless Chromium
# loads the real page and hands back a clickable picture of it.  https:// still goes direct
# (WRP can't proxy https), and WRP's pictures link back over http, so browsing stays in WRP.
#
# Steps: build WRP, install the aol-wrp user service, install Wine Gecko, register IE's
# components, point the 32-bit Internet Settings at WRP, patch iwengx32 (patch-iwengx32.sh).
# Needs: chromium, go, ~/.wine-aol4 with AOL 4.0 installed.
set -e
ROOT="$HOME/aol-revival"
WINE="$HOME/.local/opt/wine-oms/bin/wine"
export WINEPREFIX="$HOME/.wine-aol4" WINEDEBUG=-all

# 1. WRP
if [ ! -x "$ROOT/vendor/wrp/wrp" ]; then
  mkdir -p "$ROOT/vendor"
  [ -d "$ROOT/vendor/wrp" ] || git clone -q --depth 1 https://github.com/tenox7/wrp "$ROOT/vendor/wrp"
  (cd "$ROOT/vendor/wrp" && git apply "$ROOT/client40/wrp-nav-timeout.patch" && GOFLAGS=-p=2 go build -o wrp .)
fi
mkdir -p "$HOME/.config/systemd/user"
cp "$ROOT/run/aol-wrp.service" "$HOME/.config/systemd/user/"
systemctl --user daemon-reload
systemctl --user enable --now aol-wrp

# 2. Wine Gecko (the version this Wine expects) + IE components, 32- and 64-bit
GV=2.47.4
mkdir -p "$HOME/.cache/wine"
for a in x86 x86_64; do
  f="$HOME/.cache/wine/wine-gecko-$GV-$a.msi"
  [ -f "$f" ] || curl -sfL -o "$f" "https://dl.winehq.org/wine/wine-gecko/$GV/wine-gecko-$GV-$a.msi"
  [ -d "$WINEPREFIX/drive_c/windows/syswow64/gecko/$GV" ] && [ -d "$WINEPREFIX/drive_c/windows/system32/gecko/$GV" ] \
    || WINEDLLOVERRIDES=mscoree= "$WINE" msiexec /i "Z:${f//\//\\}" /qn
done
for d in mshtml.dll ieframe.dll urlmon.dll shdocvw.dll; do
  "$WINE" regsvr32 /s $d
  "$WINE" 'C:\windows\syswow64\regsvr32.exe' /s $d
done

# 3. Proxy: AOL is 32-bit, and this Wine keeps a separate 32-bit view of these keys
R='HKCU\Software\Microsoft\Windows\CurrentVersion\Internet Settings'
for view in /reg:32 /reg:64; do
  "$WINE" reg add "$R" /v ProxyEnable /t REG_DWORD /d 1 /f $view >/dev/null
  "$WINE" reg add "$R" /v ProxyServer /t REG_SZ /d "http=127.0.0.1:8098" /f $view >/dev/null
  "$WINE" reg add "$R" /v ProxyOverride /t REG_SZ /d "<local>" /f $view >/dev/null
done

# Home page through WRP (Wine's default is https://www.winehq.org, which bypasses WRP)
for view in /reg:32 /reg:64; do
  "$WINE" reg add 'HKCU\Software\Microsoft\Internet Explorer\Main' /v "Start Page" /t REG_SZ /d "http://www.aol.com/" /f $view >/dev/null
done

# Stand-in inetcpl.cpl: AOL's WWW preferences ask it for IE's settings pages, which Wine
# lacks (crashes the client).  run/wine-aol4 sets inetcpl.cpl=n,b so this copy is used.
cp "$ROOT/client40/inetcpl/inetcpl.cpl" "$WINEPREFIX/drive_c/America Online 4.0/inetcpl.cpl"

# 4. AOL's browser engine treats Wine's stubbed FreezeEvents as fatal
"$ROOT/client40/patch-iwengx32.sh"
echo "AOL 4.0 web set up.  Restart the 4.0 client (run/aol4.sh) to pick it up."
