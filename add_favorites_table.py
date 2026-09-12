# add_favorites_table.py —— 只跑一次，创建 favorites 表
import sqlite3

conn = sqlite3.connect("07.db")
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS favorites (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    visitor_id  TEXT NOT NULL,
    dish_id     INTEGER NOT NULL,
    created_at  TEXT DEFAULT (datetime('now', '+8 hours')),
    UNIQUE(visitor_id, dish_id)
)
""")

conn.commit()
conn.close()
print("✓ favorites 表已就绪。")