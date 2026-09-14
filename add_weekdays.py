# add_weekdays.py —— 只跑一次，给 dishes 表加 weekdays 字段
import sqlite3

conn = sqlite3.connect("07.db")
cur = conn.cursor()

try:
    cur.execute("""
        ALTER TABLE dishes
        ADD COLUMN weekdays TEXT NOT NULL DEFAULT '1,2,3,4,5,6,7'
    """)
    conn.commit()
    print("✓ dishes.weekdays 已添加（默认 1,2,3,4,5,6,7 = 每天）")
except sqlite3.OperationalError as e:
    if "duplicate column name" in str(e).lower():
        print("ℹ dishes.weekdays 已存在，跳过")
    else:
        print(f"✗ 出错：{e}")

conn.close()