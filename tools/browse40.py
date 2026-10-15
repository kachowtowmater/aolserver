"""Stress AOL 4.0's World Wide Web window on the TEST client and report crashes.

Each round loads sites through the host (keywords), through the address bar (typed + Enter),
and scrolls the page; afterwards it counts Wine Gecko crashes ("page fault"), engines refused
on a second thread ("one thread"), and World Wide Web windows (there should be exactly one).
usage: browse40.py [rounds=3]
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sweep40 as sw  # noqa: E402

NAME = "Tester98"
SITES = ["npr.org", "bbc.com", "yahoo.com", "wikipedia.org", "weather.gov", "espn.com"]


def log_count(word):
    try:
        return sw.CLIENT_LOG.read_text(errors="replace").count(word)
    except OSError:
        return 0


def keyword(word):
    sw.admin(f'__import__("sys").modules["services.areas"].keyword(next(l for l in links if l.session.get("name")=={NAME!r}), 0, '
             f'__import__("fdo.codec",fromlist=["x"]).atom("de_data", {word.encode()!r}))')


def address_bar():
    for line in (sw.wctl("list") or "").splitlines():
        if " Edit " in line and "vis=1" in line:
            return line.split()[0]


def doc_view():
    for line in (sw.wctl("list") or "").splitlines():
        if "Shell DocObject View" in line:
            return line.split()[0]


def main():
    rounds = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    faults0, thread0 = log_count("page fault"), log_count("one thread")
    for r in range(rounds):
        for i, site in enumerate(SITES):
            if i % 2 == 0:
                keyword(site)
            else:
                bar = address_bar()
                if bar:
                    sw.wctl("type", bar, site)
                    time.sleep(1)
                    sw.wctl("enter", bar)
            time.sleep(14)
            view = doc_view()
            if view:
                sw.wctl("wheel", view, "300", "300", "-3")
                time.sleep(2)
            if sw.crashed(faults0):
                print(f"round {r + 1} {site}: CRASH", flush=True)
                sw.restart(NAME)
                faults0 = log_count("page fault")
        windows = (sw.wctl("list") or "").count('"World Wide Web"')
        print(f"round {r + 1}: crashes={log_count('page fault') - faults0} second-thread={log_count('one thread') - thread0} "
              f"browser windows={windows}", flush=True)


if __name__ == "__main__":
    main()
