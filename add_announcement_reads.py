# add_announcement_reads.py —— 只跑一次，记录"谁读过哪些公告"
import sqlite3

conn = sqlite3.connect("07.db")
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS announcement_reads (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    visitor_id      TEXT NOT NULL,
    announcement_id INTEGER NOT NULL,
    read_at         TEXT DEFAULT (datetime('now', '+8 hours')),
    UNIQUE(visitor_id, announcement_id)
)
""")

conn.commit()
conn.close()
print("✓ announcement_reads 表已就绪。")