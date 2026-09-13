# add_reply_read.py —— 只跑一次，给 feedback 表加 reply_read 字段
import sqlite3

conn = sqlite3.connect("07.db")
cur = conn.cursor()

try:
    cur.execute("ALTER TABLE feedback ADD COLUMN reply_read INTEGER NOT NULL DEFAULT 0")
    print("✓ feedback.reply_read 已添加")
except sqlite3.OperationalError as e:
    if "duplicate column name" in str(e).lower():
        print("ℹ feedback.reply_read 已存在，跳过")
    else:
        print(f"✗ 出错：{e}")

conn.commit()
conn.close()
print("完成。")