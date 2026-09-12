# init_db.py —— 初始化数据库（三层结构：饭堂 → 窗口 → 菜品）
# ⚠️ 跑它会删掉旧的 07.db，所有数据清空重建

import os
import sqlite3

DB_PATH = "07.db"

if os.path.exists(DB_PATH):
    os.remove(DB_PATH)
    print(f"已删除旧的 {DB_PATH}")

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

# ========== 表 1：饭堂楼层 ==========
cur.execute("""
CREATE TABLE canteens (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0
)
""")

# ========== 表 2：窗口 ==========
# canteen_id 指向 canteens.id，表示"这个窗口属于哪个饭堂楼层"
cur.execute("""
CREATE TABLE stalls (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    canteen_id  INTEGER NOT NULL,
    name        TEXT NOT NULL,
    sort_order  INTEGER NOT NULL DEFAULT 0
)
""")

# ========== 表 3：菜品 ==========
# stall_id 指向 stalls.id（替代了原来的 stall 字符串）
# meal 保留（早/午/晚），因为同一个窗口不同餐次卖的菜可能不同
cur.execute("""
CREATE TABLE dishes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    stall_id    INTEGER NOT NULL,
    name        TEXT NOT NULL,
    price       REAL NOT NULL,
    description TEXT,
    meal        TEXT NOT NULL DEFAULT 'lunch'
)
""")

# ========== 表 4：评价 ==========
cur.execute("""
CREATE TABLE reviews (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    dish_id    INTEGER NOT NULL,
    author     TEXT NOT NULL,
    rating     INTEGER NOT NULL,
    content    TEXT,
    photo      TEXT,
    created_at TEXT DEFAULT (datetime('now', '+8 hours'))
)
""")

# ========== 表 5：反馈 ==========
cur.execute("""
CREATE TABLE feedback (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    category   TEXT NOT NULL,
    content    TEXT NOT NULL,
    contact    TEXT,
    status     TEXT NOT NULL DEFAULT 'new',
    created_at TEXT DEFAULT (datetime('now', '+8 hours'))
)
""")

# ========== 表 6：菜单照片 ==========
cur.execute("""
CREATE TABLE menu_photos (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    filename    TEXT NOT NULL,
    meal        TEXT NOT NULL,
    note        TEXT,
    uploaded_at TEXT DEFAULT (datetime('now', '+8 hours')),
    processed   INTEGER NOT NULL DEFAULT 0
)
""")

# ============================================================
# 种子数据
# ============================================================

# ---- 饭堂楼层 ----
canteens = [
    ("一期一楼", 1),
    ("一期二楼", 2),
    ("一期三楼", 3),
    ("二期一楼", 4),
    ("二期二楼", 5),
]
cur.executemany("INSERT INTO canteens (name, sort_order) VALUES (?, ?)", canteens)

# ---- 窗口 ----
# 格式：(canteen_id, 窗口名, sort_order)
# canteen_id 对应上面 canteens 插入的顺序：1=一期一楼, 2=一期二楼, ...
stalls = [
    # 一期一楼
    (1, "川湘风味",   1),
    (1, "面点窗口",   2),
    (1, "烧腊饭",     3),
    # 一期二楼
    (2, "风情水煮",   1),
    (2, "兰州拉面",   2),
    (2, "麻辣香锅",   3),
    # 一期三楼
    (3, "西式简餐",   1),
    # 二期一楼
    (4, "粥粉面",     1),
    # 二期二楼（大众菜）
    (5, "大众菜",     1),
]
cur.executemany(
    "INSERT INTO stalls (canteen_id, name, sort_order) VALUES (?, ?, ?)",
    stalls
)

# ---- 菜品 ----
# 格式：(stall_id, 菜名, 价格, 描述, 餐次)
# stall_id 对应上面 stalls 插入的顺序：1=川湘风味, 2=面点窗口, ...
dishes = [
    (1, "黑椒牛柳饭",   15, "牛柳挺嫩，黑椒味重",     "lunch"),
    (1, "番茄炒蛋盖饭", 12, "家常味道，稳的选择",     "lunch"),
    (1, "宫保鸡丁",     14, "花生脆，鸡丁嫩",         "lunch"),
    (2, "鲜肉包",       3,  "皮薄馅大",              "breakfast"),
    (2, "皮蛋瘦肉粥",   5,  "粥稠，皮蛋足",           "breakfast"),
    (3, "叉烧饭",       16, "叉烧肥瘦相间",           "lunch"),
    (4, "水煮牛肉",     22, "辣度可调，牛肉不少",     "lunch"),
    (4, "水煮鱼片",     20, "麻辣鲜香",              "dinner"),
    (5, "牛肉拉面",     14, "手工拉面，汤底浓",       "lunch"),
    (6, "麻辣香锅",     18, "自选，辣度可调",         "lunch"),
    (7, "意面",         18, "肉酱意面",              "lunch"),
    (8, "瘦肉粥",       6,  "清淡养胃",              "breakfast"),
    (8, "云吞面",       12, "汤清面爽",              "lunch"),
    (9, "素菜",         3,  "每日不同",              "lunch"),
    (9, "荤菜",         8,  "每日不同",              "lunch"),
]
cur.executemany(
    "INSERT INTO dishes (stall_id, name, price, description, meal) VALUES (?, ?, ?, ?, ?)",
    dishes
)

conn.commit()
conn.close()

print(f"✓ 已重建 {DB_PATH}")
print(f"  · 饭堂楼层 {len(canteens)} 个")
print(f"  · 窗口 {len(stalls)} 个")
print(f"  · 菜品 {len(dishes)} 道")
print()
print("下一步：请去后台管理页手动添加你学校的真实窗口和菜品。")