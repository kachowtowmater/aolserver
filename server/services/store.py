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
