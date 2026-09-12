# add_badges_columns.py —— 只跑一次，给 dishes 表加徽章字段
import sqlite3

conn = sqlite3.connect("07.db")
cur = conn.cursor()

columns = [
    ("is_signature", "INTEGER NOT NULL DEFAULT 0"),
    ("is_new",       "INTEGER NOT NULL DEFAULT 0"),
    ("spicy_level",  "INTEGER NOT NULL DEFAULT 0"),
]

for name, definition in columns:
    try:
        cur.execute(f"ALTER TABLE dishes ADD COLUMN {name} {definition}")
        print(f"✓ 已添加 {name}")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e).lower():
            print(f"ℹ {name} 已存在，跳过")
        else:
            print(f"✗ {name} 出错：{e}")

conn.commit()
conn.close()
print("\n完成。")