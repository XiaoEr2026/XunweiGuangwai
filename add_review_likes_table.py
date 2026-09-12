# add_review_likes_table.py —— 只跑一次，创建 review_likes 表
import sqlite3

conn = sqlite3.connect("07.db")
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS review_likes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    review_id   INTEGER NOT NULL,
    visitor_id  TEXT NOT NULL,
    created_at  TEXT DEFAULT (datetime('now', '+8 hours')),
    UNIQUE(review_id, visitor_id)
)
""")

conn.commit()
conn.close()
print("✓ review_likes 表已就绪。")