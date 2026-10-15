"""Persistent storage (SQLite in server/var/aol.db): accounts and mail."""
import sqlite3
import time
from pathlib import Path

DB = Path(__file__).resolve().parent.parent / "var" / "aol.db"


def db():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    con.executescript("""
    CREATE TABLE IF NOT EXISTS mail(
        id INTEGER PRIMARY KEY, owner TEXT, sender TEXT, recipients TEXT, cc TEXT,
        subject TEXT, body TEXT, sent REAL, read INTEGER DEFAULT 0, folder TEXT DEFAULT 'new');
    CREATE INDEX IF NOT EXISTS mail_owner ON mail(owner, folder);
    CREATE TABLE IF NOT EXISTS account(
        key TEXT PRIMARY KEY, name TEXT, pwhash TEXT, created REAL, last_on REAL);
    CREATE TABLE IF NOT EXISTS buddy(owner TEXT, buddy TEXT, PRIMARY KEY(owner, buddy));
    CREATE TABLE IF NOT EXISTS profile(
        key TEXT PRIMARY KEY, realname TEXT, location TEXT, birthday TEXT, sex TEXT,
        marital TEXT, hobbies TEXT, computers TEXT, occupation TEXT, quote TEXT);
    """)
    return con


def key(name: str) -> str:
    return name.lower().replace(" ", "")


def deliver(sender, to: list[str], cc: list[str], subject, body) -> list[str]:
    """Store one copy per recipient plus the sender's 'Mail You've Sent'. Returns recipient keys."""
    now = time.time()
    with db() as con:
        owners = []
        for r in to + cc:
            if r.strip():
                con.execute("INSERT INTO mail(owner,sender,recipients,cc,subject,body,sent) VALUES(?,?,?,?,?,?,?)",
                            (key(r), sender, ", ".join(to), ", ".join(cc), subject, body, now))
                owners.append(key(r))
        con.execute("INSERT INTO mail(owner,sender,recipients,cc,subject,body,sent,read,folder) "
                    "VALUES(?,?,?,?,?,?,?,1,'sent')", (key(sender), sender, ", ".join(to), ", ".join(cc),
                                                        subject, body, now))
    return owners


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
