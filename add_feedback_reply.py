# add_feedback_reply.py —— 只跑一次，给 feedback 表加字段
import sqlite3

conn = sqlite3.connect("07.db")
cur = conn.cursor()

columns = [
    ("user_id",    "INTEGER"),
    ("reply",      "TEXT"),
    ("replied_at", "TEXT"),
]

for name, definition in columns:
    try:
        cur.execute(f"ALTER TABLE feedback ADD COLUMN {name} {definition}")
        print(f"✓ feedback.{name} 已添加")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e).lower():
            print(f"ℹ feedback.{name} 已存在，跳过")
        else:
            print(f"✗ {name} 出错：{e}")

conn.commit()
conn.close()
print("\n完成。")