#!/usr/bin/env python3
"""Start the aolserver host (and, if it's built, the WRP web renderer) on Windows, macOS or Linux.

  python start.py                 host on :5190 (+ WRP on 127.0.0.1:8098 if vendor/wrp is built)
  python start.py --no-web        host only
  python start.py --web-listen 0.0.0.0:8098   let AOL clients on other machines use this WRP

Needs Python 3.10+.  WRP (optional, for AOL 4.0's World Wide Web window) needs Go to build and
Chrome/Chromium/Edge installed: see SETUP.md.  Ctrl+C stops everything.
For running as a service instead: run/aol-server.service + run/aol-wrp.service (Linux systemd),
run/macos/*.plist (launchd), run/windows/install-tasks.ps1 (Task Scheduler).
"""
import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
EXE = ".exe" if os.name == "nt" else ""
CHROME_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
             "Chrome/140.0.0.0 Safari/537.36")


def find_browser() -> str | None:
    """Chrome-family browser for WRP to drive (it also finds one itself; this just lets us say so)."""
    for name in ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable", "chrome", "msedge"):
        if p := shutil.which(name):
            return p
    for p in (r"C:\Program Files\Google\Chrome\Application\chrome.exe",
              r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
              "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
              "/Applications/Chromium.app/Contents/MacOS/Chromium"):
        if Path(p).exists():
            return p
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--no-web", action="store_true", help="don't start WRP")
    ap.add_argument("--web-listen", default="127.0.0.1:8098")
    args = ap.parse_args()

    procs = []
    wrp = ROOT / "vendor" / "wrp" / f"wrp{EXE}"
    if not args.no_web:
        browser = find_browser()
        if not wrp.exists():
            print("WRP not built (optional): see SETUP.md 'Web pages in AOL 4.0'.  Starting the host only.")
        elif not browser:
            print("WRP needs Chrome, Chromium or Edge installed.  Starting the host only.")
        else:
            profile = ROOT / "run" / "wrp-profile"
            profile.mkdir(parents=True, exist_ok=True)
            cmd = [str(wrp), "-l", args.web_listen, "-b", browser, "-t", "jpg", "-q", "70",
                   "-g", "1024x4000x216", "-ua", CHROME_UA, "-profile", str(profile)]
            procs.append(subprocess.Popen(cmd, cwd=wrp.parent))
            print(f"WRP on {args.web_listen} using {browser}")

    server = subprocess.Popen([sys.executable, "server.py"], cwd=ROOT / "server")
    procs.append(server)
    print("aolserver host on :5190 (admin console 127.0.0.1:5191).  Ctrl+C to stop.")
    try:
        while all(p.poll() is None for p in procs):
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        for p in procs:
            if p.poll() is None:
                p.terminate()
        for p in procs:
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                p.kill()


if __name__ == "__main__":
    main()
