"""Press every button AOL 4.0 offers and report the ones that stall, fail or lock up.

Collects each action from the client's own menus/toolbar/Channels/Welcome forms (re/idb40/fdo):
host requests (sm_send_k1/f1, K1/f1 token args, raw tokens) and local windows
(uni_invoke_no_context/local).  For each one the live, signed-on 4.0 client is told to run
that action exactly as its button would (via the admin console), then we look at what
happened: art the window had to ask for (DOD = a stalled window), "not available" alerts,
tokens the server ignored, server tracebacks, a client that stops answering, or a crash.
Windows it opened are closed before the next one.

Runs against the TEST client (AOL4_PREFIX, default ~/.wine-aol4-test, signed on as Tester98)
so it never disturbs someone using the real one.
usage: sweep40.py [screen name=Tester98] [--only substring]
"""
import glob
import json
import re
import subprocess
import sys
import os
import time
from pathlib import Path

os.environ.setdefault("AOL4_PREFIX", str(Path.home() / ".wine-aol4-test"))
PASSWORD = os.environ.get("AOL4_PASSWORD", "test1998")

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "run" / "server.log"
WINE, WCTL = str(ROOT / "run" / "wine-aol4"), str(ROOT / "run" / "tools" / "wctl.exe")
ENTRY_FORMS = ["41-*", "32-5483", "32-6442", "32-6585", "32-4628", "32-30", "32-4705", "32-278"]

ACTION = re.compile(r'(sm_send_(?:k1|f1) <[\d-]+>|sm_send_token_arg <"\w\w", [\d-]+>|sm_send_token_raw <"\w\w">|'
                    r'sm_send_token_arg <"\w\w">|uni_invoke_(?:no_context|local) <[\d-]+>)')
LABEL = re.compile(r'<(?:trigger|dss_list|ornament|ind_group), "([^"]+)">|mat_art_hint_title <"([^"]+)">')
SKIP = {'sm_send_token_raw <"pE">', 'sm_send_token_raw <"XS">'}  # sign off / exit


def actions():
    seen, out = set(), []
    files = sorted({f for pat in ENTRY_FORMS for f in glob.glob(str(ROOT / "re/idb40/fdo" / f"{pat}.fdo"))})
    for f in files:
        label = ""
        for line in open(f, errors="replace"):
            m = LABEL.search(line)
            if m:
                label = m.group(1) or m.group(2)
            for a in ACTION.findall(line):
                if a in seen or a in SKIP or "<0>" in a:
                    continue
                seen.add(a)
                out.append((Path(f).stem, label.replace("\r", " "), a))
    return out


def admin(expr):
    return subprocess.run([str(ROOT / "run" / "admin"), expr], capture_output=True, text=True, timeout=30).stdout.strip()


def wctl(*args, timeout=15):
    try:
        return subprocess.run([WINE, WCTL, *args], capture_output=True, timeout=timeout).stdout.decode("latin1")
    except subprocess.TimeoutExpired:
        return None


def run_action(name, action):
    fdo = f"uni_start_stream <00x>\\n  {action}\\nuni_end_stream <00x>".replace('"', '\\"')
    return admin(f'next(l for l in links if l.session.get("name")=={name!r}).send_stream('
                 f'__import__("services.util",fromlist=["x"]).compile_fdo("{fdo}"))')


def judge(new_log, listing):
    problems = []
    problems += [f"stalled on art {g}" for g in re.findall(r"DOD for (\S+)", new_log)]
    if "async_alert" in new_log:
        alerts = re.findall(r"async_alert <([0-9a-f ]+)>", new_log)
        for a in alerts:
            text = bytes.fromhex(a.replace(" ", ""))[1:].decode("latin1", "replace")
            problems.append(f"alert: {text[:70]}")
    problems += [f"server ignored {t}" for t in re.findall(r"no handler for token (b'..')", new_log)]
    if "Traceback" in new_log:
        problems.append("server error: " + new_log.split("Traceback")[1].strip().splitlines()[-1][:100])
    if listing is None:
        problems.append("CLIENT NOT RESPONDING")
    return problems


def name_link_missing(name="Tester98") -> bool:
    """The test client crashed or hung if its session is gone from the server."""
    return name not in admin('[l.session.get("name") for l in links]')


CLIENT_LOG = ROOT / "run" / f"waol4-{Path(os.environ['AOL4_PREFIX']).name}.log"


def faults() -> int:
    try:
        return CLIENT_LOG.read_text(errors="replace").count("page fault")
    except OSError:
        return 0


def crashed(before: int = 0) -> bool:
    return name_link_missing() or faults() > before


def restart(name):
    for pid in subprocess.run(["pgrep", "-x", "winedbg.exe"], capture_output=True, text=True).stdout.split():
        subprocess.run(["kill", pid])
    try:
        subprocess.run([str(ROOT / "run" / "signon4.sh"), "0", PASSWORD], capture_output=True, timeout=300)
    except subprocess.TimeoutExpired:
        print("  (test client restart slow; carrying on)", flush=True)
    time.sleep(8)  # art preload


def main():
    name = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else "Tester98"
    only = sys.argv[sys.argv.index("--only") + 1] if "--only" in sys.argv else ""
    results = []
    todo = [a for a in actions() if only in " ".join(a)]
    print(f"{len(todo)} actions")
    for form, label, action in todo:
        start, f0 = LOG.stat().st_size, faults()
        run_action(name, action)
        time.sleep(5)
        new = LOG.read_bytes()[start:].decode("latin1", "replace")
        listing = wctl("list")
        problems = judge(new, listing)
        opened = re.findall(r'AOL Child\s+vis=1.*"(.*)"', listing or "")
        boxes = [l for l in (listing or "").splitlines() if not l.startswith(" ") and "AOL Frame25" not in l and l.strip()]
        errors = [b for b in boxes if "#32770" in b or "Wine" in b]  # message boxes, crash dialogs
        if errors:
            problems.append("error box: " + "; ".join(re.sub(r"^\S+\s+", "", b)[:60] for b in errors))
        opened += [re.sub(r"^\S+\s+\S+\s+", "", b).split("[")[0].strip() for b in boxes if b not in errors]
        wctl("dismiss")
        for b in boxes:
            wctl("close", b.split()[0])
        wctl("closeall")
        if crashed(f0):
            problems.append("CLIENT CRASHED")
            restart(name)
        status = "OK " if not problems else "BAD"
        print(f"{status} {form:9} {label[:28]:28} {action[:46]:46} opened={opened[:2]} {problems}", flush=True)
        results.append((form, label, action, problems))
    out = ROOT / "run" / "sweep40.json"
    out.write_text(json.dumps(results, indent=1))
    bad = [r for r in results if r[3]]
    print(f"\n{len(results) - len(bad)} ok, {len(bad)} with problems -> {out}")


if __name__ == "__main__":
    main()
