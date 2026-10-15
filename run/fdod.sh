#!/bin/bash
# AOL's FDO compiler as an HTTP daemon (POST /compile, /decompile) on 127.0.0.1:8099.
cd "$HOME/aol-revival/run/fdotools" && WINEDEBUG=-all exec "$HOME/aol-revival/run/wine-aol" fdo_daemon.exe --port 8099 --quiet
