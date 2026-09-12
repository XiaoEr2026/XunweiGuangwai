# add_review_visitor_id.py —— 只跑一次，给 reviews 表加 visitor_id 字段
import sqlite3

conn = sqlite3.connect("07.db")
cur = conn.cursor()

try:
    cur.execute("ALTER TABLE reviews ADD COLUMN visitor_id TEXT")
    conn.commit()
    print("✓ reviews.visitor_id 字段已添加。")
    print("  已有的老评论该字段为空，无法被学生自己删除。")
except sqlite3.OperationalError as e:
    if "duplicate column name" in str(e).lower():
        print("ℹ reviews.visitor_id 已存在，跳过。")
    else:
        print(f"✗ 出错：{e}")

conn.close()