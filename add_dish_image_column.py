# add_dish_image_column.py —— 只跑一次，给 dishes 表加 image 字段
import sqlite3

conn = sqlite3.connect("07.db")
cur = conn.cursor()

try:
    cur.execute("""
        ALTER TABLE dishes
        ADD COLUMN image TEXT
    """)
    conn.commit()
    print("✓ 已添加 image 字段。")
except sqlite3.OperationalError as e:
    if "duplicate column name" in str(e).lower():
        print("ℹ 已经添加过 image 字段，跳过。")
    else:
        print(f"✗ 出错：{e}")

conn.close()