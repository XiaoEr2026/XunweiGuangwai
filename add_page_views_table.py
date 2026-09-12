# add_page_views_table.py —— 只跑一次，记录页面访问
import sqlite3

conn = sqlite3.connect("07.db")
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS page_views (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    path        TEXT NOT NULL,
    visitor_id  TEXT,
    ip          TEXT,
    created_at  TEXT DEFAULT (datetime('now', '+8 hours'))
)
""")

cur.execute("CREATE INDEX IF NOT EXISTS idx_views_time ON page_views(created_at)")
cur.execute("CREATE INDEX IF NOT EXISTS idx_views_vid  ON page_views(visitor_id)")

conn.commit()
conn.close()
print("✓ page_views 表已就绪。")