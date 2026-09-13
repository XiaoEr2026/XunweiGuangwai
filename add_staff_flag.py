# add_staff_flag.py —— 只跑一次，给 users 表加 is_staff 字段
import sqlite3

conn = sqlite3.connect("07.db")
cur = conn.cursor()

try:
    cur.execute("ALTER TABLE users ADD COLUMN is_staff INTEGER NOT NULL DEFAULT 0")
    print("✓ users.is_staff 已添加")
except sqlite3.OperationalError as e:
    if "duplicate column name" in str(e).lower():
        print("ℹ users.is_staff 已存在，跳过")
    else:
        print(f"✗ 出错：{e}")

conn.commit()
conn.close()
print("完成。")