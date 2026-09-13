# add_users_table.py —— 只跑一次，创建 users 表
import sqlite3

conn = sqlite3.connect("07.db")
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    email         TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    nickname      TEXT NOT NULL,
    is_banned     INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT DEFAULT (datetime('now', '+8 hours'))
)
""")

conn.commit()
conn.close()
print("✓ users 表已就绪。")