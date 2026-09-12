# add_menu_photos_table.py —— 只跑一次，给已有数据库加 menu_photos 表
import sqlite3

conn = sqlite3.connect("07.db")
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS menu_photos (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    filename    TEXT NOT NULL,
    meal        TEXT NOT NULL,
    note        TEXT,
    uploaded_at TEXT DEFAULT (datetime('now', 'localtime')),
    processed   INTEGER NOT NULL DEFAULT 0
)
""")

conn.commit()
conn.close()
print("已添加 menu_photos 表。")