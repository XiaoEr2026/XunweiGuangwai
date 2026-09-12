# add_announcements_table.py —— 只跑一次，创建 announcements 表
import sqlite3

conn = sqlite3.connect("07.db")
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS announcements (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT NOT NULL,
    content     TEXT,
    level       TEXT NOT NULL DEFAULT 'info',
    is_pinned   INTEGER NOT NULL DEFAULT 0,
    expires_at  TEXT,
    created_at  TEXT DEFAULT (datetime('now', 'localtime'))
)
""")

conn.commit()
conn.close()
print("✓ announcements 表已就绪。")