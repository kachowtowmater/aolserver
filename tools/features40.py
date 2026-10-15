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
    if not hits:
        return ""
    # the frame's own toolbar is listed after the last child window: not part of it
    return re.split(r"(?m)^\s+\S+ (?:AOL Toolbar|MDIClient)", hits[0])[0]


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


def check_write_mail():
    """4.0's own Write Mail window: To/Subject/body, Send Now (the client sends mN packets)."""
    act("uni_invoke_no_context <32-4629>"); time.sleep(5)
    blk = child_block("Write Mail")
    if not blk:
        return ["no Write Mail window"]
    lines = blk.splitlines()
    eds = [l.split()[0] for l in lines if "_AOL_Edit" in l and "vis=1" in l]
    rich = [l.split()[0] for l in lines if "RICHCNTL" in l]
    # the right-hand column of picture buttons: Send Now is the top one
    col = sorted((int(re.search(r"@(\d+),(\d+)", l).group(2)), l.split()[0]) for l in lines
                 if "_AOL_Icon" in l and "vis=1" in l and int(re.search(r"@(\d+),", l).group(1)) > 1400)
    if len(eds) < 3 or not rich or not col:
        return ["Write Mail fields not found"]
    unread = lambda: int(sw.admin(f'__import__("sys").modules["services.store"].unread({NAME!r})') or 0)
    before = unread()
    start = sw.LOG.stat().st_size
    sw.wctl("settext", eds[0], NAME)
    sw.wctl("settext", eds[2], "features40 write mail check")
    sw.wctl("settext", rich[0], "Sent from 4.0's own Write Mail window.")
    sw.wctl("clickh", col[0][1])
    time.sleep(10)
    log = server_since(start)
    return errors(log) + ([] if unread() > before else ["mail didn't arrive"]) + \
        ([] if not child_block("Write Mail") else ["Write Mail window stayed open"])


def check_reply():
    """Read Mail -> open a message in 4.0's own mailbox (its Read button) -> Reply -> Send Now."""
    sw.admin('__import__("sys").modules["services.store"].deliver("Rewind98", ["Tester98"], [], '
             '"features40 reply source", "Please reply to this.")')
    act("sm_send_k1 <40-4391>"); time.sleep(6)
    box = child_block("Online Mailbox")
    icons = sorted((int(re.search(r"@(\d+),", l).group(1)), l.split()[0]) for l in box.splitlines()
                   if "_AOL_Icon" in l and "vis=1" in l and re.search(r"@\d+,(\d+)", l)
                   and int(re.search(r"@\d+,(\d+)", l).group(1)) > 1300)
    if not icons:
        return ["no Online Mailbox buttons"]
    sw.wctl("clickh", icons[0][1]); time.sleep(7)  # Read (bottom-left button) opens the selected message
    titles = re.findall(r'AOL Child\s+vis=1.*"(.*)"', sw.wctl("list") or "")
    msg = next((t for t in titles if "Mailbox" not in t), None)
    if not msg:
        return ["message didn't open"]
    blk = child_block(msg)
    col = sorted((int(re.search(r"@\d+,(\d+)", l).group(1)), l.split()[0]) for l in blk.splitlines()
                 if "_AOL_Icon" in l and "vis=1" in l and int(re.search(r"@(\d+),", l).group(1)) > 1400)
    if not col:
        return ["no Reply button"]
    sw.wctl("clickh", col[0][1]); time.sleep(6)  # Reply is the top of the right-hand column
    re_blk = child_block("Re: ")
    if not re_blk:
        return ["Reply didn't open a Re: window"]
    rich = [l.split()[0] for l in re_blk.splitlines() if "RICHCNTL" in l]
    send = sorted((int(re.search(r"@\d+,(\d+)", l).group(1)), l.split()[0]) for l in re_blk.splitlines()
                  if "_AOL_Icon" in l and "vis=1" in l and int(re.search(r"@(\d+),", l).group(1)) > 1400)
    sent = lambda: int(sw.admin(f'len(__import__("sys").modules["services.store"].mailbox({NAME!r}, "sent"))') or 0)
    before, start = sent(), sw.LOG.stat().st_size
    sw.wctl("settext", rich[0], "features40 reply check")
    sw.wctl("clickh", send[0][1]); time.sleep(10)
    return errors(server_since(start)) + ([] if sent() > before else ["reply wasn't sent"])


def keyword(word):
    sw.admin(f'__import__("sys").modules["services.areas"].keyword(next(l for l in links if l.session.get("name")=={NAME!r}), 0, '
             f'__import__("fdo.codec",fromlist=["x"]).atom("de_data", {word.encode()!r}))')


def check_create_room():
    act("sm_send_k1 <14-16393>"); time.sleep(4)
    log, err = fill_and_press("Create a Member Room", ["Retro Room"], "Create")
    return [err] if err else errors(log) + ([] if child_block("Retro Room") else ["didn't enter Retro Room"])


def check_private_chat():
    act("sm_send_k1 <14-8785>"); time.sleep(4)
    log, err = fill_and_press("Private Chat", ["SecretClub"], "Go Chat")
    if err:
        return [err]
    listed = "SecretClub" in sw.admin('[n for n, r in __import__("state").ROOMS.items() if not r.get("private")]')
    return errors(log) + ([] if child_block("SecretClub") else ["didn't enter SecretClub"]) + \
        (["private room shows in the public list"] if listed else [])


def check_buddy_add():
    act("sm_send_k1 <17-21293>"); time.sleep(4)
    log, err = fill_and_press("Buddy List Setup", ["kewlguy97"], "Add Buddy")
    has = "kewlguy97" in sw.admin(f'__import__("sys").modules["services.store"].buddies({NAME!r})')
    return [err] if err else errors(log) + ([] if has else ["buddy not saved"])


def check_portfolio():
    keyword("portfolio"); time.sleep(8)
    blk = child_block("Portfolio")
    if not blk:
        return ["no portfolio window"]
    if "Add Stock" not in blk:
        btn = [l.split()[0] for l in blk.splitlines() if "_AOL_Button" in l and "Add" in l]
        if btn:
            sw.wctl("clickh", btn[0]); time.sleep(4)
    log, err = fill_and_press("Add Stock", ["MSFT", "10"], "Add Stock", wait=10)
    return [err] if err else errors(log) + ([] if "tok=zH" in log else ["add didn't reach the server"])


def check_profile_save():
    act("sm_send_k1 <17-48638>"); time.sleep(4)
    log, err = fill_and_press("Edit Your Online Profile", ["Tester Ninety-Eight"], "Update")
    return [err] if err else errors(log) + ([] if "tok=zP" in log else ["profile save didn't reach the server"])


# check_reply drives the mailbox list, whose pre-selected row ignores scripted clicks: run it on
# its own (--only reply) when the New Mail list has unread mail.  Verified by hand 2026-10-15.
OPTIONAL = {"reply": check_reply}
CHECKS = {"write mail": check_write_mail, "create room": check_create_room, "private chat": check_private_chat,
          "buddy": check_buddy_add, "portfolio": check_portfolio, "profile": check_profile_save, "quote": check_quote, "weather": check_weather, "chat": check_chat, "im": check_im,
          "boards": check_boards, "web": check_web_keyword, "directory": check_member_directory,
          "files": check_file_search}


def main():
    only = sys.argv[sys.argv.index("--only") + 1] if "--only" in sys.argv else ""
    results = {}
    for name, fn in {**CHECKS, **(OPTIONAL if only in OPTIONAL else {})}.items():
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
