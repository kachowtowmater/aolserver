"""Open every host area from the AOL 4.0 TEST client and follow the first link in each.

For each area the host serves (services/areas.py GID_AREAS), the client is told to send the
same K1 request its button sends; we check a window came back and the server logged no
error, then have the client click the first entry in that window (zA) and check again.
Server end: the log.  Client end: the windows that actually exist in the client.
usage: areas40.py [--only substring]      (test client signed on as Tester98)
"""
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sweep40 as sw  # noqa: E402  (shares the test-client plumbing)

NAME = "Tester98"


def item_seq() -> int:
    """The host numbers each clickable entry it sends (1..250, wrapping): the last one used."""
    out = sw.admin(f'next(l for l in links if l.session.get("name")=={NAME!r}).session.get("item_seq", 0)')
    return int(out) if out.isdigit() else 0


def windows():
    return re.findall(r'AOL Child\s+vis=1.*"(.*)"', sw.wctl("list") or "")


def step(action):
    start, f0 = sw.LOG.stat().st_size, sw.faults()
    sw.run_action(NAME, action)
    time.sleep(5)
    new = sw.LOG.read_bytes()[start:].decode("latin1", "replace")
    problems = sw.judge(new, sw.wctl("list"))
    problems += [f"unmapped: {u}" for u in re.findall(r"UNMAPPED (.*)", new)]
    if sw.crashed(f0):
        problems.append("CLIENT CRASHED")
        sw.restart(NAME)
    return problems, new


def main():
    sys.path.insert(0, str(sw.ROOT / "server"))
    from services import areas
    only = sys.argv[sys.argv.index("--only") + 1] if "--only" in sys.argv else ""
    first_gid = {}
    for g, a in areas.GID_AREAS.items():
        if g and a not in first_gid.values() and a not in ("browser", "welcome content"):
            first_gid[g] = a
    results = []
    for gid, area in first_gid.items():
        if only not in area:
            continue
        sw.wctl("dismiss"); sw.wctl("closeall")
        before = item_seq()
        problems, _ = step(f"sm_send_k1 <{gid}>")
        opened = windows()
        if not opened and not problems:
            problems.append("no window opened")
        after = item_seq()
        followed = ""
        if after != before:
            n = before % 250 + 1  # first entry this window added
            p2, _ = step(f'sm_send_token_arg <"zA", {n}>')
            followed = f"item {n} -> {windows()[:2]}"
            problems += [f"(link) {p}" for p in p2]
        status = "OK " if not problems else "BAD"
        print(f"{status} {area:22} {gid:9} opened={opened[:2]} {followed} {problems}", flush=True)
        results.append({"area": area, "gid": gid, "opened": opened, "followed": followed, "problems": problems})
    out = sw.ROOT / "run" / "areas40.json"
    out.write_text(json.dumps(results, indent=1))
    bad = [r for r in results if r["problems"]]
    print(f"\n{len(results) - len(bad)} ok, {len(bad)} with problems -> {out}")


if __name__ == "__main__":
    main()
