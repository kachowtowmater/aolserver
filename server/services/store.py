"""Persistent storage (SQLite in server/var/aol.db): accounts and mail."""
import sqlite3
import time
from pathlib import Path

DB = Path(__file__).resolve().parent.parent / "var" / "aol.db"


def db():
    DB.parent.mkdir(exist_ok=True)  # server/var isn't in git: a fresh checkout starts empty
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    con.executescript("""
    CREATE TABLE IF NOT EXISTS mail(
        id INTEGER PRIMARY KEY, owner TEXT, sender TEXT, recipients TEXT, cc TEXT,
        subject TEXT, body TEXT, sent REAL, read INTEGER DEFAULT 0, folder TEXT DEFAULT 'new');
    CREATE INDEX IF NOT EXISTS mail_owner ON mail(owner, folder);
    CREATE TABLE IF NOT EXISTS account(
        key TEXT PRIMARY KEY, name TEXT, pwhash TEXT, created REAL, last_on REAL);
    CREATE TABLE IF NOT EXISTS topic(id INTEGER PRIMARY KEY, board TEXT, title TEXT, author TEXT, created REAL);
    CREATE TABLE IF NOT EXISTS post(id INTEGER PRIMARY KEY, topic INTEGER, author TEXT, subject TEXT,
                                    body TEXT, posted REAL);
    CREATE TABLE IF NOT EXISTS holding(owner TEXT, symbol TEXT, shares REAL, PRIMARY KEY(owner, symbol));
    CREATE TABLE IF NOT EXISTS buddy(owner TEXT, buddy TEXT, PRIMARY KEY(owner, buddy));
    CREATE TABLE IF NOT EXISTS profile(
        key TEXT PRIMARY KEY, realname TEXT, location TEXT, birthday TEXT, sex TEXT,
        marital TEXT, hobbies TEXT, computers TEXT, occupation TEXT, quote TEXT);
    """)
    return con


def key(name: str) -> str:
    return name.lower().replace(" ", "")


def deliver(sender, to: list[str], cc: list[str], subject, body, local: list[str] | None = None) -> list[str]:
    """Store one copy per member recipient plus the sender's 'Mail You've Sent'. `to`/`cc` are
    the headers as addressed (may include Internet addresses); `local` (default: every name in
    to+cc) are the members who get a copy. Returns their keys."""
    now = time.time()
    with db() as con:
        owners = []
        for r in (to + cc if local is None else local):
            if r.strip() and key(r) not in owners:
                con.execute("INSERT INTO mail(owner,sender,recipients,cc,subject,body,sent) VALUES(?,?,?,?,?,?,?)",
                            (key(r), sender, ", ".join(to), ", ".join(cc), subject, body, now))
                owners.append(key(r))
        con.execute("INSERT INTO mail(owner,sender,recipients,cc,subject,body,sent,read,folder) "
                    "VALUES(?,?,?,?,?,?,?,1,'sent')", (key(sender), sender, ", ".join(to), ", ".join(cc),
                                                        subject, body, now))
    return owners


def deliver_incoming(owner: str, sender: str, to: str, cc: str, subject: str, body: str) -> str:
    """Mail from outside AOL (the Internet gateway): one copy in the member's New Mail, no
    'sent' copy for the outside sender.  Returns the owner key."""
    with db() as con:
        con.execute("INSERT INTO mail(owner,sender,recipients,cc,subject,body,sent) VALUES(?,?,?,?,?,?,?)",
                    (key(owner), sender, to, cc, subject, body, time.time()))
    return key(owner)


def mailbox(owner: str, folder: str = "new"):
    with db() as con:
        return con.execute("SELECT * FROM mail WHERE owner=? AND folder=? ORDER BY sent DESC",
                           (key(owner), folder)).fetchall()


def unread(owner: str) -> int:
    with db() as con:
        return con.execute("SELECT count(*) FROM mail WHERE owner=? AND folder='new' AND read=0",
                           (key(owner),)).fetchone()[0]


def get(mid: int):
    with db() as con:
        return con.execute("SELECT * FROM mail WHERE id=?", (mid,)).fetchone()


def mark_read(mid: int):
    with db() as con:
        con.execute("UPDATE mail SET read=1, folder='old' WHERE id=?", (mid,))


def keep_as_new(mid: int):
    with db() as con:
        con.execute("UPDATE mail SET read=0, folder='new' WHERE id=? AND folder!='sent'", (mid,))


def delete_mail(mid: int):
    with db() as con:
        con.execute("DELETE FROM mail WHERE id=?", (mid,))


def unsend(sent_mid: int) -> int:
    """Take back a sent message from recipients who haven't read it yet; returns how many."""
    with db() as con:
        m = con.execute("SELECT * FROM mail WHERE id=?", (sent_mid,)).fetchone()
        if not m:
            return 0
        n = con.execute("DELETE FROM mail WHERE sender=? AND subject=? AND sent=? AND folder='new' AND id!=?",
                        (m["sender"], m["subject"], m["sent"], sent_mid)).rowcount
        con.execute("DELETE FROM mail WHERE id=?", (sent_mid,))
        return n


def read_status(sent_mid: int) -> list[tuple[str, bool]]:
    """For a sent message: each recipient copy's owner and whether it's been read."""
    with db() as con:
        m = con.execute("SELECT * FROM mail WHERE id=?", (sent_mid,)).fetchone()
        if not m:
            return []
        rows = con.execute("SELECT owner, read FROM mail WHERE sender=? AND subject=? AND sent=? AND id!=?",
                           (m["sender"], m["subject"], m["sent"], sent_mid)).fetchall()
        return [(r["owner"], bool(r["read"])) for r in rows]


def _hash(name: str, pw: str) -> str:
    import hashlib
    return hashlib.pbkdf2_hmac("sha256", pw.encode(), key(name).encode(), 100_000).hex()


def account(name: str):
    with db() as con:
        return con.execute("SELECT * FROM account WHERE key=?", (key(name),)).fetchone()


def create_account(name: str, pw: str):
    with db() as con:
        con.execute("INSERT INTO account(key,name,pwhash,created) VALUES(?,?,?,?)",
                    (key(name), name, _hash(name, pw), time.time()))


def check_password(name: str, pw: str) -> bool:
    a = account(name)
    return bool(a) and a["pwhash"] == _hash(name, pw)


def touch(name: str):
    with db() as con:
        con.execute("UPDATE account SET last_on=? WHERE key=?", (time.time(), key(name)))


PROFILE_FIELDS = ["realname", "location", "birthday", "sex", "marital", "hobbies", "computers", "occupation", "quote"]
PROFILE_LABELS = ["Member Name", "Location", "Birthday", "Sex", "Marital Status", "Hobbies", "Computers",
                  "Occupation", "Quote"]


def get_profile(name: str):
    with db() as con:
        return con.execute("SELECT * FROM profile WHERE key=?", (key(name),)).fetchone()


def set_profile(name: str, values: list[str]):
    vals = (values + [""] * 9)[:9]
    with db() as con:
        con.execute(f"INSERT OR REPLACE INTO profile(key,{','.join(PROFILE_FIELDS)}) VALUES(?,{','.join('?'*9)})",
                    (key(name), *vals))


def search_profiles(q: str):
    like = f"%{q.lower()}%"
    with db() as con:
        return con.execute("SELECT a.name, p.* FROM account a LEFT JOIN profile p ON p.key=a.key WHERE "
                           "lower(a.name) LIKE ? OR lower(coalesce(p.hobbies,'')) LIKE ? OR "
                           "lower(coalesce(p.location,'')) LIKE ? OR lower(coalesce(p.occupation,'')) LIKE ? "
                           "ORDER BY a.name LIMIT 50", (like,) * 4).fetchall()


def buddies(owner: str) -> list[str]:
    with db() as con:
        return [r[0] for r in con.execute("SELECT buddy FROM buddy WHERE owner=? ORDER BY lower(buddy)", (key(owner),))]


def add_buddy(owner: str, name: str):
    with db() as con:
        con.execute("INSERT OR IGNORE INTO buddy(owner,buddy) VALUES(?,?)", (key(owner), name))


def remove_buddy(owner: str, name: str):
    with db() as con:
        con.execute("DELETE FROM buddy WHERE owner=? AND lower(buddy)=?", (key(owner), name.lower()))


def watchers(name: str) -> list[str]:
    """Owners whose Buddy List includes `name`."""
    with db() as con:
        return [r[0] for r in con.execute("SELECT owner FROM buddy WHERE lower(buddy)=?", (name.lower(),))]


def topics(board: str):
    with db() as con:
        return con.execute("SELECT t.*, count(p.id) n, max(p.posted) last FROM topic t LEFT JOIN post p ON "
                           "p.topic=t.id WHERE board=? GROUP BY t.id ORDER BY last DESC", (board,)).fetchall()


def posts(topic_id: int):
    with db() as con:
        return con.execute("SELECT * FROM post WHERE topic=? ORDER BY posted", (topic_id,)).fetchall()


def get_topic(topic_id: int):
    with db() as con:
        return con.execute("SELECT * FROM topic WHERE id=?", (topic_id,)).fetchone()


def new_topic(board, title, author, body) -> int:
    with db() as con:
        cur = con.execute("INSERT INTO topic(board,title,author,created) VALUES(?,?,?,?)",
                          (board, title, author, time.time()))
        con.execute("INSERT INTO post(topic,author,subject,body,posted) VALUES(?,?,?,?,?)",
                    (cur.lastrowid, author, title, body, time.time()))
        return cur.lastrowid


def reply(topic_id, author, subject, body):
    with db() as con:
        con.execute("INSERT INTO post(topic,author,subject,body,posted) VALUES(?,?,?,?,?)",
                    (topic_id, author, subject, body, time.time()))


def holdings(owner: str):
    with db() as con:
        return con.execute("SELECT symbol, shares FROM holding WHERE owner=? ORDER BY symbol", (key(owner),)).fetchall()


def set_holding(owner: str, symbol: str, shares: float):
    with db() as con:
        if shares:
            con.execute("INSERT OR REPLACE INTO holding(owner,symbol,shares) VALUES(?,?,?)", (key(owner), symbol, shares))
        else:
            con.execute("DELETE FROM holding WHERE owner=? AND symbol=?", (key(owner), symbol))
