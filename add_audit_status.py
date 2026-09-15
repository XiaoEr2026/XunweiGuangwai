# add_audit_status.py —— 只跑一次，给 posts / reviews / post_replies 加 status 字段
import sqlite3

conn = sqlite3.connect("07.db")
cur = conn.cursor()

targets = [
    ("posts",        "TEXT NOT NULL DEFAULT 'approved'"),
    ("reviews",      "TEXT NOT NULL DEFAULT 'approved'"),
    ("post_replies", "TEXT NOT NULL DEFAULT 'approved'"),
]

for table, definition in targets:
    try:
        cur.execute(f"ALTER TABLE {table} ADD COLUMN status {definition}")
        print(f"✓ {table}.status 已添加（老数据默认 approved）")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e).lower():
            print(f"ℹ {table}.status 已存在，跳过")
        else:
            print(f"✗ {table} 出错：{e}")

conn.commit()
conn.close()
print("完成。")