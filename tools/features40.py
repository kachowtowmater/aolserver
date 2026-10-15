"""Use AOL 4.0's interactive features the way a member does, on the TEST client.

Each check opens a feature the way its button does, types into the real window's fields
(wctl settext), presses the window's own button (wctl click <label>), then verifies both ends:
  server end - the request the client sent (token + the text typed) and no server error;
  client end - the window the answer opened (or the line that appeared) in the client.
usage: features40.py [--only name]     (test client signed on as Tester98, see sweep40.py)
"""
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sweep40 as sw  # noqa: E402

NAME = "Tester98"


def listing():
    return sw.wctl("list") or ""


def child_block(title_part):
    """Controls of the newest visible AOL child window whose title contains title_part."""
    blocks = re.split(r"(?m)^(?=    \S+ AOL Child )", listing())
    hits = [b for b in blocks if b.startswith("    ") and "AOL Child" in b.splitlines()[0]
            and title_part.lower() in b.splitlines()[0].lower()]
    return hits[0] if hits else ""


def edits(block):
    return [l.split()[0] for l in block.splitlines() if re.search(r"_AOL_Edit|RICHCNTL", l) and "vis=1" in l]


def server_since(start):
    return sw.LOG.read_bytes()[start:].decode("latin1", "replace")


def act(action):
    sw.run_action(NAME, action)


def fill_and_press(title, values, button, wait=8):
    """Type values into the window's visible edit fields, press its button, return log text."""
    start = sw.LOG.stat().st_size
    blk = child_block(title)
    if not blk:
        return None, f"no '{title}' window"
    fields = edits(blk)
    for h, v in zip(fields, values):
        sw.wctl("settext", h, v)
    sw.wctl("click", button)
    time.sleep(wait)
    return server_since(start), ""


def errors(log):
    out = []
    if "Traceback" in log:
        out.append("server error: " + log.split("Traceback")[1].strip().splitlines()[-1][:100])
    out += [f"server ignored {t}" for t in re.findall(r"no handler for token (b'..')", log)]
    return out


# ---------- checks: each returns a list of problems ([] = works) ----------

def check_quote():
    act('sm_send_k1 <8-63415>'); time.sleep(5)            # Personal Finance
    n = sw.admin(f'next(l for l in links if l.session.get("name")=={NAME!r}).session.get("item_seq",0)')
    act(f'sm_send_token_arg <"zA", {n}>'); time.sleep(4)   # its "Stock Quotes" button
    log, err = fill_and_press("Stock Quotes", ["AAPL"], "Get Quote")
    if err:
        return [err]
    win = child_block("Quote: AAPL")
    return errors(log) + ([] if "tok=zQ" in log and win else ["no quote window for AAPL"])


def check_weather():
    act('sm_send_k1 <17-64133>'); time.sleep(5)
    log, err = fill_and_press("Weather", ["Seattle"], "Get Forecast", wait=10)
    if err:
        return [err]
    return errors(log) + ([] if child_block("Weather: Seattle") else ["no forecast window"])


def check_chat():
    act('sm_send_token_raw <"CJ">'); time.sleep(8)
    blk = child_block("Lobby")
    if not blk:
        return ["no lobby window"]
    start = sw.LOG.stat().st_size
    edit = [l.split()[0] for l in blk.splitlines() if "_AOL_Edit" in l and "vis=1" in l]
    send = [l.split()[0] for l in blk.splitlines() if "_AOL_Icon" in l and "vis=1" in l]
    if not edit:
        return ["no chat input box"]
    sw.wctl("settext", edit[-1], "hey all, testing from Tester98")
    sw.wctl("enter", edit[-1])
    time.sleep(12)
    log = server_since(start)
    sent = "testing from Tester98" in log
    return errors(log) + ([] if sent else ["chat line didn't reach the server"])


def check_im():
    act("uni_invoke_no_context <32-225>"); time.sleep(4)   # Send Instant Message
    start = sw.LOG.stat().st_size
    blk = child_block("Send Instant Message")
    if not blk:
        return ["no Send IM window"]
    f = edits(blk)
    if len(f) < 2:
        return ["IM window has no To/message fields"]
    sw.wctl("settext", f[0], "PoetGirl22")
    sw.wctl("settext", f[1], "hi poetgirl, what are you reading?")
    lines = blk.splitlines()
    rich = next(i for i, l in enumerate(lines) if "RICHCNTL" in l)
    send = [l.split()[0] for l in lines[rich:] if "_AOL_Icon" in l and "vis=1" in l]  # Send, Available?
    sw.wctl("clickh", send[0])
    time.sleep(25)
    log = server_since(start)
    got = child_block("PoetGirl22")
    return errors(log) + ([] if "iS fields" in log else ["IM didn't reach the server"]) + \
        ([] if got else ["no reply window from PoetGirl22"])


def check_boards():
    act('sm_send_k1 <4-12887>'); time.sleep(5)            # Newsgroups -> Message Boards
    return errors(server_since(0)[-4000:]) + ([] if child_block("Message Boards") or child_block("Boards") else ["no boards window"])


def check_web_keyword():
    start = sw.LOG.stat().st_size
    sw.admin(f'__import__("sys").modules["services.areas"].keyword(next(l for l in links if l.session.get("name")=={NAME!r}), 0, __import__("fdo.codec",fromlist=["x"]).atom("de_data", b"npr.org"))')
    time.sleep(20)
    log = server_since(start)
    return errors(log) + ([] if "www_browse" in log and child_block("World Wide Web") else ["browser didn't open npr.org"])


def check_member_directory():
    act('sm_send_k1 <17-61845>'); time.sleep(4)
    log, err = fill_and_press("Member Directory", ["Rewind98"], "Search")
    if err:
        return [err]
    return errors(log) + ([] if "tok=zD" in log else ["search didn't reach the server"])


def check_file_search():
    act('sm_send_k1 <8-11975>'); time.sleep(4)
    log, err = fill_and_press("File Search", ["doom shareware"], "List Files", wait=20)
    if err:
        return [err]
    return errors(log) + ([] if "tok=zF" in log else ["file search didn't reach the server"])


CHECKS = {"quote": check_quote, "weather": check_weather, "chat": check_chat, "im": check_im,
          "boards": check_boards, "web": check_web_keyword, "directory": check_member_directory,
          "files": check_file_search}


def main():
    only = sys.argv[sys.argv.index("--only") + 1] if "--only" in sys.argv else ""
    results = {}
    for name, fn in CHECKS.items():
        if only and only != name:
            continue
        sw.wctl("dismiss"); sw.wctl("closeall")
        f0 = sw.faults()
        try:
            problems = fn()
        except Exception as e:  # a broken check shouldn't stop the rest
            problems = [f"check failed: {e}"]
        if sw.crashed(f0):
            problems.append("CLIENT CRASHED")
            sw.restart(NAME)
        results[name] = problems
        print(("OK " if not problems else "BAD"), f"{name:10}", problems, flush=True)
    bad = [k for k, v in results.items() if v]
    print(f"\n{len(results) - len(bad)} ok, {len(bad)} with problems")


if __name__ == "__main__":
    main()
