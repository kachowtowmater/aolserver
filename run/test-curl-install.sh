#!/bin/bash
# Test that install.sh works when piped through curl (the one-command install).
# Uses a real PTY so the /dev/tty reads in ask() succeed.
# Usage: run/test-curl-install.sh [--local]
#   --local   pipe from the local install.sh instead of fetching from GitHub
set -e
REPO_URL="https://raw.githubusercontent.com/kachowtowmater/aolserver/main/install.sh"
INSTALL_DIR=$(mktemp -d)/aolserver
SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

if [ "$1" = "--local" ]; then
  CMD="cat '$SCRIPT_DIR/install.sh' | AOL_DIR=$INSTALL_DIR bash"
else
  CMD="curl -fsSL $REPO_URL | AOL_DIR=$INSTALL_DIR bash"
fi

python3 -c "
import os, pty, select, sys, time

ANSWERS = [b'\n', b'1\n', b'n\n']  # hostname=default, mail=skip, service=no

pid, fd = pty.fork()
if pid == 0:
    os.execvp('bash', ['bash', '-c', '''$CMD'''])
    sys.exit(1)

output, idx, last = b'', 0, time.time()
try:
    while time.time() - last < 120:
        ready, _, _ = select.select([fd], [], [], 2.0)
        if ready:
            try:
                chunk = os.read(fd, 4096)
            except OSError:
                break
            if not chunk:
                break
            output += chunk
            last = time.time()
            text = chunk.decode('utf-8', errors='replace')
            if idx < len(ANSWERS) and (']:' in text or '[Y/n]' in text):
                time.sleep(0.3)
                os.write(fd, ANSWERS[idx])
                idx += 1
        else:
            r = os.waitpid(pid, os.WNOHANG)
            if r[0] != 0:
                while True:
                    rr, _, _ = select.select([fd], [], [], 0.5)
                    if not rr: break
                    try:
                        c = os.read(fd, 4096)
                        if not c: break
                        output += c
                    except OSError: break
                pid = 0
                break
finally:
    if pid:
        try: os.waitpid(pid, 0)
        except ChildProcessError: pass
    try: os.close(fd)
    except OSError: pass

text = output.decode('utf-8', errors='replace')
checks = [
    ('banner', 'aolserver' in text.lower()),
    ('dependencies', 'Python' in text),
    ('git_clone', 'Done' in text or 'Updating' in text),
    ('hostname_prompt', 'hostname' in text.lower()),
    ('mail_prompt', 'Internet mail' in text or 'mail' in text.lower()),
    ('setup_complete', 'Setup complete' in text),
]
ok = True
for name, passed in checks:
    print(f\"  {'PASS' if passed else 'FAIL'}  {name}\")
    if not passed: ok = False
if ok:
    print('ALL PASS')
else:
    print('FAILED')
    sys.exit(1)
"

rm -rf "$(dirname "$INSTALL_DIR")"
echo "install dir cleaned up"
