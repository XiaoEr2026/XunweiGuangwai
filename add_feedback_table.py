# add_feedback_table.py —— 只跑一次，给已有数据库加 feedback 表
import sqlite3

conn = sqlite3.connect("07.db")
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS feedback (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    category   TEXT NOT NULL,
    content    TEXT NOT NULL,
    contact    TEXT,
    status     TEXT NOT NULL DEFAULT 'new',
    created_at TEXT DEFAULT (datetime('now', '+8 hours'))
)
""")

conn.commit()
conn.close()
print("已添加 feedback 表。")