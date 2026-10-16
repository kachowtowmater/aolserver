#!/usr/bin/env python3
"""Start the aolserver host on Windows, macOS or Linux.

  python start.py                 host on :5190
  python start.py --no-web        disable the host-side web renderer (AOL_WEBVIEW=0)

Needs Python 3.10+.  The World Wide Web window is rendered server-side by headless Chrome
(Chromium/Chrome/Edge; optional -- without it, web pages are shown as text).
Ctrl+C stops everything.
For running as a service instead: run/aol-server.service (Linux systemd),
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
    ap.add_argument("--no-web", action="store_true", help="disable host-side web rendering (AOL_WEBVIEW=0)")
    args = ap.parse_args()

    env = dict(os.environ)
    if args.no_web:
        env["AOL_WEBVIEW"] = "0"
    elif not find_browser():
        print("No Chrome/Chromium/Edge found: web pages will be shown as text inside AOL.")
        print("Install chromium for full web page rendering.")

    procs = []
    server = subprocess.Popen([sys.executable, "server.py"], cwd=ROOT / "server", env=env)
    procs.append(server)
    port = int(env.get("AOL_PORT", "5190"))
    print(f"aolserver host on :{port} (admin console 127.0.0.1:{port + 1}).  Ctrl+C to stop.")
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
