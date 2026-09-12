# add_feedback_ip_and_blacklist.py —— 只跑一次
# 给 feedback 表加 ip 字段，并新建 ip_blacklist 表
import sqlite3

conn = sqlite3.connect("07.db")
cur = conn.cursor()

try:
    cur.execute("ALTER TABLE feedback ADD COLUMN ip TEXT")
    print("✓ feedback.ip 字段已添加")
except sqlite3.OperationalError as e:
    if "duplicate column name" in str(e).lower():
        print("ℹ feedback.ip 已存在，跳过")
    else:
        print(f"✗ feedback.ip 出错：{e}")

cur.execute("""
CREATE TABLE IF NOT EXISTS ip_blacklist (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    ip         TEXT NOT NULL UNIQUE,
    reason     TEXT,
    created_at TEXT DEFAULT (datetime('now', '+8 hours'))
)
""")
print("✓ ip_blacklist 表已就绪")

conn.commit()
conn.close()
print("\n完成。")