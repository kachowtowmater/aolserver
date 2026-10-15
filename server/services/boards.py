"""Message Boards: boards -> topics -> posts, like the boards in every 90s AOL area.

Keyword BOARDS / MESSAGE BOARDS.  zT = create topic, zM = post reply (forms).
"""
from datetime import datetime

from . import screens, store
from .util import name_of, request

BOARDS = ["General Discussion", "Remember the 90s?", "Tech Talk", "News & Politics", "Sports Talk",
          "Movies, TV & Music", "Help & Questions"]
SEED = {"Remember the 90s?": ("What was your first screen name?",
                              "Mine had way too many X's in it.  What was yours, and what did you do online?"),
        "Help & Questions": ("Welcome to the boards!", "Post questions here and other members will help.  "
                             "Use Create Topic to start a new discussion.")}


def _seed():
    for board, (title, body) in SEED.items():
        if not store.topics(board):
            store.new_topic(board, title, "OnlineHost", body)


def _item(link, payload):
    from .areas import _item as item
    return item(link, payload)


def board_list(link, rid=None):
    _seed()
    rows = [(f"{len(store.topics(b))} topics\t{b}", _item(link, ("board", b))) for b in BOARDS]
    link.send_stream(screens.list_window("Message Boards", "Choose a board.  Double-click to see its topics.",
                                         rows, response_id=rid, width=40, window="boards"))


def board(link, name):
    rows = []
    for t in store.topics(name):
        when = datetime.fromtimestamp(t["last"] or t["created"]).strftime("%m/%d/%y")
        rows.append((f"{t['n']} posts\t{when}\t{t['title'][:50]}", _item(link, ("topic", t["id"]))))
    link.send_stream(screens.list_window(
        name, "Posts, latest date and topic.  Double-click a topic to read it.", rows,
        buttons=[("Create Topic", '          sm_send_token_arg <"zA", %d>' % _item(link, ("new_topic", name)))],
        width=56, window="board"))


def topic(link, topic_id):
    t = store.get_topic(topic_id)
    if not t:
        return
    parts = []
    for p in store.posts(topic_id):
        when = datetime.fromtimestamp(p["posted"]).strftime("%a, %b %-d, %Y %-I:%M %p")
        parts += [f"Subject:  {p['subject']}", f"From:  {p['author']}", f"Date:  {when}", "", p["body"], "",
                  "-" * 50, ""]
    link.session["reply_topic"] = topic_id
    link.send_stream(screens.page_window(t["title"], "\r".join(parts),
                                         [("Post a reply to this topic", _item(link, ("reply", topic_id)))],
                                         window="topic", links_title="Respond:"))


def new_topic_form(link, board_name):
    link.session["new_topic_board"] = board_name
    link.send_stream(screens.form_window(f"Create Topic: {board_name}", "Give your topic a subject and write "
                                         "the first message.", [("Subject:", 40, ""), ("Message:", 50, "")],
                                         "Post", "zT", window="compose_post"))


def reply_form(link, topic_id):
    t = store.get_topic(topic_id)
    link.session["reply_topic"] = topic_id
    link.send_stream(screens.form_window(f"Reply: {t['title'][:40]}", "Write your reply.",
                                         [("Subject:", 40, "Re: " + t["title"][:36]), ("Message:", 50, "")],
                                         "Post", "zM", window="compose_post"))


def create_topic(link, stream_id, body):
    subj, msg = (request(body)["texts"] + ["", ""])[:2]
    board_name = link.session.get("new_topic_board")
    if board_name and subj.strip():
        store.new_topic(board_name, subj.strip(), name_of(link), msg.strip())
        link.send_stream(screens.close_window("compose_post"))
        board(link, board_name)


def post_reply(link, stream_id, body):
    subj, msg = (request(body)["texts"] + ["", ""])[:2]
    tid = link.session.get("reply_topic")
    if tid and msg.strip():
        store.reply(tid, name_of(link), subj.strip() or "Re:", msg.strip())
        link.send_stream(screens.close_window("compose_post"))
        topic(link, tid)


TOKENS = {b"zT": create_topic, b"zM": post_reply}
