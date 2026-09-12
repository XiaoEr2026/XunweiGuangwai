# add_board_tables.py —— 只跑一次，创建拼饭广场相关表
import sqlite3

conn = sqlite3.connect("07.db")
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS posts (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    author         TEXT NOT NULL,
    content        TEXT NOT NULL,
    when_time      TEXT,
    contact        TEXT,
    stall_id       INTEGER,
    visitor_id     TEXT,
    created_at     TEXT DEFAULT (datetime('now', 'localtime')),
    last_reply_at  TEXT DEFAULT (datetime('now', 'localtime'))
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS post_replies (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id     INTEGER NOT NULL,
    author      TEXT NOT NULL,
    content     TEXT NOT NULL,
    visitor_id  TEXT,
    created_at  TEXT DEFAULT (datetime('now', 'localtime'))
)
""")

conn.commit()
conn.close()
print("✓ posts / post_replies 表已就绪。")