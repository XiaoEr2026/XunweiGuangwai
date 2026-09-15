# add_notifications_table.py —— 只跑一次，创建 notifications 表
import sqlite3

conn = sqlite3.connect("07.db")
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS notifications (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL,
    type       TEXT NOT NULL,
    title      TEXT NOT NULL,
    content    TEXT,
    link       TEXT,
    is_read    INTEGER NOT NULL DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now', '+8 hours'))
)
""")
cur.execute("CREATE INDEX IF NOT EXISTS idx_notif_user ON notifications(user_id)")
cur.execute("CREATE INDEX IF NOT EXISTS idx_notif_read ON notifications(user_id, is_read)")

conn.commit()
conn.close()
print("✓ notifications 表已就绪")