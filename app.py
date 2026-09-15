# app.py —— 寻味广外 主程序
import os
import re
import sqlite3
import time
import secrets
from datetime import datetime, timezone, timedelta

# 设置时区为北京时间（PythonAnywhere 服务器默认是 UTC）
# os.environ['TZ'] = 'Asia/Shanghai'
# try:
#     time.tzset()   # Linux/Mac 生效；Windows 会报 AttributeError，已忽略
# except AttributeError:
#     pass

from flask import (
    Flask, render_template, request, redirect, url_for, session,
    g, jsonify, flash
)
from werkzeug.utils import secure_filename

from werkzeug.security import generate_password_hash, check_password_hash   # ← 新增
import openpyxl                                                            # ← 新增

app = Flask(__name__)
app.secret_key = "change-me-to-a-random-string-07-platform"

DB_PATH = "07.db"
UPLOAD_DIR       = os.path.join("static", "uploads")
MENU_PHOTO_DIR   = os.path.join("static", "menu_photos")
DISH_IMAGE_DIR   = os.path.join("static", "dish_images")
ANNOUNCE_IMG_DIR = os.path.join("static", "announcement_images")
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(MENU_PHOTO_DIR, exist_ok=True)
os.makedirs(DISH_IMAGE_DIR, exist_ok=True)
os.makedirs(ANNOUNCE_IMG_DIR, exist_ok=True)

ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp"}

MEALS = ("breakfast", "lunch", "dinner")
MEAL_LABEL = {"breakfast": "早餐", "lunch": "午餐", "dinner": "晚餐"}

SPICY_LABELS = {0: "", 1: "🌶️ 微辣", 2: "🌶️🌶️ 中辣", 3: "🌶️🌶️🌶️ 特辣"}
MOOD_LABELS  = {1: "😞 很不满意", 2: "😕 不太满意", 3: "😐 一般", 4: "😊 满意", 5: "🤩 非常满意"}

ADMIN_PASSWORD = "07CNadmin"
SIGNATURE_MIN_REVIEWS = 5
SIGNATURE_MIN_RATING  = 4.5

FEEDBACK_CATEGORIES = {
    "bug": "🐞 报告问题",
    "suggest": "💡 功能建议",
    "data": "📋 菜品数据有误",
    "other": "📝 其他",
}


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def is_allowed(filename):
    ext = os.path.splitext(filename)[1].lower()
    return ext in ALLOWED_EXT


def is_admin():
    return session.get("is_admin") is True


def save_image(file):
    if not file or not file.filename:
        return None
    if not is_allowed(file.filename):
        return None
    safe = secure_filename(file.filename)
    filename = f"{int(time.time())}_{safe}"
    file.save(os.path.join(DISH_IMAGE_DIR, filename))
    return filename


def parse_badges_from_form():
    is_new = 1 if request.form.get("is_new") == "1" else 0
    try:
        spicy = int(request.form.get("spicy_level", "0"))
    except (TypeError, ValueError):
        spicy = 0
    if spicy not in (0, 1, 2, 3):
        spicy = 0
    return is_new, spicy

WEEKDAY_LABELS = {
    1: "周一",
    2: "周二",
    3: "周三",
    4: "周四",
    5: "周五",
    6: "周六",
    7: "周日",
}


def parse_weekdays_from_form():
    """从表单读 weekdays 复选框，返回排序好的字符串，如 '1,2,3'。
       没选任何 → 返回 '1,2,3,4,5,6,7'（每天）。
    """
    try:
        selected = [int(x) for x in request.form.getlist("weekdays")]
    except (TypeError, ValueError):
        selected = []
    selected = sorted(set(w for w in selected if 1 <= w <= 7))
    if not selected:
        return "1,2,3,4,5,6,7"
    return ",".join(str(w) for w in selected)

# 表头 / 说明行：这些词出现时跳过，不入库
HEADER_KEYWORDS = {
    "星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日", "星期天",
    "周一", "周二", "周三", "周四", "周五", "周六", "周日",
    "餐次", "类别", "早餐", "午餐", "晚餐", "中午", "晚上",
}


def parse_week_columns(text):
    """解析用户从 Excel 粘贴的 7 列内容。
       每行按 Tab 拆，期望得到 7 个字段（周一到周日）。
       每个字段内用 、 , ， 再拆成多道菜。
       返回 (results, skipped)：
         results = [(菜名, weekdays_str), ...]
         skipped = [(原始行, 原因), ...]
    """
    results = []
    skipped = []

    for raw_line in text.splitlines():
        line = raw_line.rstrip("\n").rstrip("\r")
        if not line.strip():
            continue

        # 优先 Tab 拆（Excel 复制的默认分隔）
        parts = line.split("\t")

        # 如果 Tab 拆出来只有 1 段，试试 2 个以上空格
        if len(parts) == 1:
            parts = re.split(r"\s{2,}", line)

        # 如果还是只有 1 段，跳过
        if len(parts) < 2:
            skipped.append((line, "无法拆分（不是 Tab 也不是多空格分隔）"))
            continue

        # 补齐 / 截断到 7 段
        while len(parts) < 7:
            parts.append("")
        parts = parts[:7]

        # 检查这一行是不是"表头行"（7 段全是星期词）
        if all(p.strip() in HEADER_KEYWORDS or not p.strip() for p in parts):
            continue

        # 每段内部再拆（顿号 / 逗号）
        for col_idx, part in enumerate(parts, start=1):
            part = part.strip()
            if not part:
                continue

            # 顿号 / 逗号 / 中英文逗号 拆
            sub_dishes = re.split(r"[、,，]", part)
            for d in sub_dishes:
                d = d.strip()
                if not d:
                    continue
                # 跳过太短的（<=1 字）和表头词
                if len(d) < 2:
                    continue
                if d in HEADER_KEYWORDS:
                    continue
                # 跳过含括号的（如"中点（学生选二）"）
                if "（" in d or "(" in d:
                    continue

                results.append((d, str(col_idx)))

    return results, skipped

def get_client_ip():
    """拿访客 IP（兼容反向代理）"""
    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "")
    return ip.split(",")[0].strip()


def is_ip_banned(ip):
    """检查 IP 是否在黑名单里"""
    conn = get_db()
    row = conn.execute(
        "SELECT 1 FROM ip_blacklist WHERE ip = ?", (ip,)
    ).fetchone()
    conn.close()
    return row is not None

def current_user():
    """返回当前登录的学生对象，未登录返回 None"""
    uid = session.get("user_id")
    if not uid:
        return None
    conn = get_db()
    user = conn.execute(
        "SELECT * FROM users WHERE id = ?", (uid,)
    ).fetchone()
    conn.close()
    return user


def is_logged_in():
    return current_user() is not None

def get_bj_now():
    """拿北京时间（服务器通常是 UTC）"""
    return datetime.now(timezone.utc) + timedelta(hours=8)


def resolve_day_param(day):
    """根据 day 参数决定看周几的菜。
       day: '1'~'7'（周一~周日）或空
       返回 target_weekday（1~7）
    """
    bj = get_bj_now()
    today_weekday = bj.isoweekday()

    if day and day.isdigit() and 1 <= int(day) <= 7:
        return int(day)

    # 默认今天
    return today_weekday

def current_author_name():
    """评论/拼饭显示的名字。
       只认学生账号登录（user_id）。管理员后台登录（无 user_id）不能发言。
    """
    u = current_user()
    if u:
        return u["nickname"]
    return None

def parse_menu_line(line):
    """把 OCR 的一行文字拆成一个或多个 (菜名, 价格)。
       返回列表。两栏菜单可能一行有两道菜。
    """
    s = (line or "").strip()
    if not s:
        return []

    # 去掉开头的序号，如 "1." "2、" "3，"
    s = re.sub(r'^\d+\s*[.、，,。]\s*', '', s)

    # ===== 模式 0：价格在前，"12元鱼香肉丝" 或 "12元 鱼香肉丝" =====
    m = re.match(r'^(\d+(?:\.\d+)?)\s*元\s*(.+)$', s)
    if m:
        name = m.group(2).strip()
        price = m.group(1)
        if name:
            return [(name, price)]

    results = []

    # ===== 模式 A：菜名 + 数字 + 元（支持两栏） =====
    pattern_a = r'([\u4e00-\u9fa5A-Za-z][\u4e00-\u9fa5A-Za-z0-9]*?)\s*(\d+(?:\.\d+)?)\s*元'
    matches = re.findall(pattern_a, s)
    if matches:
        for name, price in matches:
            name = name.strip()
            if name:
                results.append((name, price))
        if results:
            return results

    # ===== 模式 B：菜名 + 空格 + 数字（无"元"） =====
    pattern_b = r'([\u4e00-\u9fa5A-Za-z][\u4e00-\u9fa5A-Za-z0-9]*?)\s+(\d+(?:\.\d+)?)(?:\s|$)'
    matches = re.findall(pattern_b, s)
    if matches:
        for name, price in matches:
            name = name.strip()
            if name:
                results.append((name, price))
        if results:
            return results

    # ===== 模式 C：纯价格行，如 "18" 或 "18元" =====
    m = re.match(r'^(\d+(?:\.\d+)?)\s*元?$', s)
    if m:
        return [('', m.group(1))]

    # 都不匹配：整行当菜名
    return [(s, '')]


# ============================================================
# 访客 ID（cookie 版本，用来做收藏/点赞/评论归属）
# ============================================================

@app.before_request
def ensure_visitor_id():
    # 优先级 1：后台管理员已登录 → "admin"
    if session.get("is_admin") is True:
        g.visitor_id = "admin"
        return

    # 优先级 2：学生已登录 → 检查是不是 staff
    uid = session.get("user_id")
    if uid:
        conn = get_db()
        u = conn.execute(
            "SELECT is_staff FROM users WHERE id = ?", (uid,)
        ).fetchone()
        conn.close()

        if u and u["is_staff"]:
            g.visitor_id = "admin"
        else:
            g.visitor_id = f"u{uid}"
        return

    # 兜底：cookie
    vid = request.cookies.get("visitor_id")
    if not vid or len(vid) < 8:
        vid = secrets.token_urlsafe(16)
        g.new_visitor_id = vid
    g.visitor_id = vid

@app.before_request
def record_visit():
    """记录学生端页面访问。只记 GET，忽略静态文件和管理后台。"""
    # 只记 GET
    if request.method != "GET":
        return

    path = request.path

    # 忽略这些
    if (path.startswith("/static/")
            or path == "/favicon.ico"
            or path.startswith("/admin")
            or path.startswith("/login")
            or path.startswith("/logout")):
        return

    vid = getattr(g, "visitor_id", None)
    if not vid:
        return

    try:
        conn = get_db()
        conn.execute(
            "INSERT INTO page_views (path, visitor_id, ip) "
            "VALUES (?, ?, ?)",
            (path, vid, request.remote_addr or "")
        )
        conn.commit()
        conn.close()
    except Exception:
        # 记录失败不能影响正常访问
        pass

@app.before_request
def require_student_login():
    """学生端所有页面都要求登录。管理员登录状态可以直接看。"""
    path = request.path

    # 1) 静态文件、favicon 放行
    if path.startswith("/static/") or path == "/favicon.ico":
        return

    # 2) 登录/注册/登出/关于 放行
    allowed = (
        "/login",      # 管理员登录
        "/logout",     # 管理员登出
        "/signin",     # 学生登录
        "/signout",    # 学生登出
        "/register",   # 学生注册
        "/about",      # 关于页
    )
    for p in allowed:
        if path == p or path.startswith(p + "/") or path.startswith(p + "?"):
            return

    # 3) 管理员路径放行（它们有 is_admin() 自己控制权限）
    admin_prefixes = (
        "/admin",
        "/menu_upload",
        "/menu_photos",
        "/feedback/list",
        "/dish/new",
    )
    for p in admin_prefixes:
        if path.startswith(p):
            return
    if path.startswith("/dish/") and path.endswith("/edit"):
        return
    if path.startswith("/dish/") and path.endswith("/delete"):
        return
    if path.startswith("/feedback/") and (path.endswith("/done") or path.endswith("/delete")):
        return

    # 4) 已经登录的学生 OR 管理员 → 放行
    if session.get("user_id"):
        return

    if is_admin():
        return

    # 5) 其他情况：跳登录页，登录后回到原页
    return redirect(url_for("signin", next=path))

@app.before_request
def block_banned_from_posting():
    """被禁言的用户能看，但不能发任何内容（所有 POST 请求都拦）"""
    if request.method != "POST":
        return

    # 管理员不受影响
    if is_admin():
        return

    uid = session.get("user_id")
    if not uid:
        return

    conn = get_db()
    u = conn.execute(
        "SELECT is_banned FROM users WHERE id = ?", (uid,)
    ).fetchone()
    conn.close()

    if u and u["is_banned"]:
        flash("你的账号已被禁言，暂时不能发言或互动", "error")
        ref = request.referrer or "/"
        return redirect(ref)

@app.after_request
def set_visitor_cookie(response):
    new_vid = getattr(g, "new_visitor_id", None)
    if new_vid:
        response.set_cookie(
            "visitor_id", new_vid,
            max_age=60 * 60 * 24 * 365 * 2,
            samesite="Lax",
            httponly=False,
        )
    return response


@app.context_processor
def inject_globals():
    path = request.path
    is_admin_page = (
        path.startswith("/admin")
        or path.startswith("/menu_upload")
        or path.startswith("/menu_photos")
        or path.startswith("/feedback/list")
        or path == "/dish/new"
        or (path.startswith("/dish/") and path.endswith("/edit"))
    )

    conn = get_db()

    pending_feedback = 0
    if is_admin():
        try:
            row = conn.execute(
                "SELECT COUNT(*) AS c FROM feedback WHERE status = 'new'"
            ).fetchone()
            pending_feedback = row["c"] if row else 0
        except Exception:
            pending_feedback = 0

    unread_announcements = 0
    unread_announcement_list = []
    vid = getattr(g, "visitor_id", None)
    if vid:
        try:
            row = conn.execute("""
                SELECT COUNT(*) AS c FROM announcements
                WHERE (expires_at IS NULL
                       OR expires_at >= datetime('now', '+8 hours'))
                  AND id NOT IN (
                      SELECT announcement_id FROM announcement_reads
                      WHERE visitor_id = ?
                  )
            """, (vid,)).fetchone()
            unread_announcements = row["c"] if row else 0

            # 弹窗用：未读公告完整列表（含标题、内容、级别）
            rows = conn.execute("""
                SELECT id, title, content, level
                FROM announcements
                WHERE (expires_at IS NULL
                       OR expires_at >= datetime('now', '+8 hours'))
                  AND id NOT IN (
                      SELECT announcement_id FROM announcement_reads
                      WHERE visitor_id = ?
                  )
                ORDER BY is_pinned DESC, id DESC
            """, (vid,)).fetchall()
            unread_announcement_list = [dict(r) for r in rows]
        except Exception:
            unread_announcements = 0
            unread_announcement_list = []

    # 未读的管理员回复（只对学生）—— 注意放在 conn.close() 之前
    unread_replies = 0
    uid = session.get("user_id")
    if uid and not is_admin():
        try:
            row = conn.execute("""
                SELECT COUNT(*) AS c FROM feedback
                WHERE user_id = ?
                  AND reply IS NOT NULL
                  AND reply != ''
                  AND reply_read = 0
            """, (uid,)).fetchone()
            unread_replies = row["c"] if row else 0
        except Exception:
            unread_replies = 0

    conn.close()   # ← 移到这里，所有查询都完了才关

    return {
        "is_admin":              is_admin(),
        "is_admin_page":         is_admin_page,
        "spicy_labels":          SPICY_LABELS,
        "mood_labels":           MOOD_LABELS,
        "pending_feedback":      pending_feedback,
        "unread_announcements":      unread_announcements,
        "unread_announcement_list":  unread_announcement_list,
        "unread_replies":        unread_replies,
        "weekday_labels":        WEEKDAY_LABELS,        # ← 加这一行
        "current_user":          current_user(),
        "is_logged_in":          is_logged_in(),
    }


# ============================================================
# 学生端：首页
# ============================================================

@app.route("/")
def home():
    meal       = request.args.get("meal", "all")
    q          = request.args.get("q", "").strip()
    canteen_id = request.args.get("canteen", "")
    stall_id   = request.args.get("stall", "")
    day        = request.args.get("day", "").strip()
    vid        = g.visitor_id

    # 根据 day 参数决定看周几
    target_weekday = resolve_day_param(day)
    bj = get_bj_now()
    today_weekday = bj.isoweekday()

    conn = get_db()

    announcements = conn.execute("""
        SELECT * FROM announcements
        WHERE expires_at IS NULL
           OR expires_at >= datetime('now', '+8 hours')
        ORDER BY is_pinned DESC, id DESC
        LIMIT 3
    """).fetchall()

    canteens = conn.execute("""
        SELECT c.id, c.name,
               COUNT(DISTINCT s.id) AS stall_count,
               COUNT(d.id)          AS dish_count
        FROM canteens c
        LEFT JOIN stalls s ON s.canteen_id = c.id
        LEFT JOIN dishes d ON d.stall_id   = s.id
        GROUP BY c.id
        ORDER BY c.sort_order, c.id
    """).fetchall()

    all_stalls = conn.execute("""
        SELECT s.id, s.name,
               c.id   AS canteen_id,
               c.name AS canteen_name,
               COUNT(d.id) AS dish_count
        FROM stalls s
        JOIN canteens c ON c.id = s.canteen_id
        LEFT JOIN dishes d ON d.stall_id = s.id
        GROUP BY s.id
        ORDER BY c.sort_order, c.id, s.sort_order, s.id
    """).fetchall()

    where_parts = []
    params = [vid]

    # 按星期几筛（用 ',' 包裹防止 '1' 匹配到 '11'）
    where_parts.append("(',' || d.weekdays || ',') LIKE ?")
    params.append(f"%,{target_weekday},%")

    if meal in MEALS:
        where_parts.append("d.meal = ?")
        params.append(meal)
    else:
        meal = "all"

    if q:
        where_parts.append(
            "(d.name LIKE ? OR d.description LIKE ? OR s.name LIKE ? OR c.name LIKE ?)"
        )
        kw = f"%{q}%"
        params.extend([kw, kw, kw, kw])

    if canteen_id.isdigit():
        where_parts.append("c.id = ?")
        params.append(int(canteen_id))
    else:
        canteen_id = ""

    if stall_id.isdigit():
        where_parts.append("s.id = ?")
        params.append(int(stall_id))
    else:
        stall_id = ""

    where_sql = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""

    dishes = conn.execute(f"""
        SELECT d.id, d.name, d.price, d.description, d.meal, d.image,
               CASE WHEN COUNT(r.id) >= 5 AND AVG(r.rating) >= 4.5
                    THEN 1 ELSE 0 END AS is_signature,
               d.is_new, d.spicy_level,
               s.id AS stall_id, s.name AS stall_name,
               c.id AS canteen_id, c.name AS canteen_name,
               ROUND(AVG(r.rating), 1) AS avg_rating,
               COUNT(r.id)             AS review_count,
               (SELECT COUNT(*) FROM page_views
                WHERE path = '/dish/' || d.id) AS view_count,
               EXISTS(
                   SELECT 1 FROM favorites f
                   WHERE f.dish_id = d.id AND f.visitor_id = ?
               ) AS is_favorited
        FROM dishes d
        JOIN stalls s   ON s.id = d.stall_id
        JOIN canteens c ON c.id = s.canteen_id
        LEFT JOIN reviews r ON r.dish_id = d.id
        {where_sql}
        GROUP BY d.id
        ORDER BY c.sort_order, c.id, s.sort_order, s.id, d.id
    """, params).fetchall()

    conn.close()

    return render_template(
        "menu.html",
        canteens=canteens,
        all_stalls=all_stalls,
        dishes=dishes,
        announcements=announcements,
        current_meal=meal,
        current_canteen=canteen_id,
        current_stall=stall_id,
        current_day=str(target_weekday),   # 链接里用的 day 参数
        target_weekday=target_weekday,
        today_weekday=today_weekday,
        meals=MEALS,
        meal_label=MEAL_LABEL,
        weekday_labels=WEEKDAY_LABELS,
        q=q,
    )


# ============================================================
# 学生端：我的收藏
# ============================================================

@app.route("/my-favorites")
def my_favorites():
    vid = g.visitor_id
    conn = get_db()
    dishes = conn.execute("""
        SELECT d.id, d.name, d.price, d.description, d.meal, d.image,
               CASE WHEN COUNT(r.id) >= 5 AND AVG(r.rating) >= 4.5
                    THEN 1 ELSE 0 END AS is_signature,
               d.is_new, d.spicy_level,
               s.id AS stall_id, s.name AS stall_name,
               c.id AS canteen_id, c.name AS canteen_name,
               ROUND(AVG(r.rating), 1) AS avg_rating,
               COUNT(r.id)             AS review_count,
               (SELECT COUNT(*) FROM page_views
                WHERE path = '/dish/' || d.id) AS view_count,
               1                       AS is_favorited
        FROM favorites f
        JOIN dishes d   ON d.id = f.dish_id
        JOIN stalls s   ON s.id = d.stall_id
        JOIN canteens c ON c.id = s.canteen_id
        LEFT JOIN reviews r ON r.dish_id = d.id
        WHERE f.visitor_id = ?
        GROUP BY d.id
        ORDER BY f.created_at DESC
    """, (vid,)).fetchall()
    conn.close()
    return render_template(
        "my_favorites.html",
        dishes=dishes,
        meal_label=MEAL_LABEL,
    )


# ============================================================
# 收藏切换（AJAX）
# ============================================================

@app.route("/favorite/<int:dish_id>/toggle", methods=["POST"])
def favorite_toggle(dish_id):
    vid = g.visitor_id
    conn = get_db()

    dish = conn.execute(
        "SELECT 1 FROM dishes WHERE id = ?", (dish_id,)
    ).fetchone()
    if not dish:
        conn.close()
        return jsonify({"ok": False, "msg": "菜品不存在"}), 404

    existing = conn.execute(
        "SELECT 1 FROM favorites WHERE visitor_id = ? AND dish_id = ?",
        (vid, dish_id)
    ).fetchone()

    if existing:
        conn.execute(
            "DELETE FROM favorites WHERE visitor_id = ? AND dish_id = ?",
            (vid, dish_id)
        )
        favorited = False
    else:
        conn.execute(
            "INSERT INTO favorites (visitor_id, dish_id) VALUES (?, ?)",
            (vid, dish_id)
        )
        favorited = True

    conn.commit()
    conn.close()
    return jsonify({"ok": True, "favorited": favorited})


# ============================================================
# 评价点赞切换（AJAX）
# ============================================================

@app.route("/review/<int:review_id>/like", methods=["POST"])
def review_like_toggle(review_id):
    vid = g.visitor_id
    conn = get_db()

    review = conn.execute(
        "SELECT 1 FROM reviews WHERE id = ?", (review_id,)
    ).fetchone()
    if not review:
        conn.close()
        return jsonify({"ok": False, "msg": "评价不存在"}), 404

    existing = conn.execute(
        "SELECT 1 FROM review_likes WHERE review_id = ? AND visitor_id = ?",
        (review_id, vid)
    ).fetchone()

    if existing:
        conn.execute(
            "DELETE FROM review_likes WHERE review_id = ? AND visitor_id = ?",
            (review_id, vid)
        )
        liked = False
    else:
        conn.execute(
            "INSERT INTO review_likes (review_id, visitor_id) VALUES (?, ?)",
            (review_id, vid)
        )
        liked = True

    count = conn.execute(
        "SELECT COUNT(*) AS c FROM review_likes WHERE review_id = ?",
        (review_id,)
    ).fetchone()["c"]

    conn.commit()
    conn.close()
    return jsonify({"ok": True, "liked": liked, "count": count})


# ============================================================
# 学生删自己的评论
# ============================================================

@app.route("/review/<int:review_id>/delete-own", methods=["POST"])
def review_delete_own(review_id):
    vid = g.visitor_id
    conn = get_db()

    row = conn.execute(
        "SELECT visitor_id, dish_id FROM reviews WHERE id = ?",
        (review_id,)
    ).fetchone()

    if not row:
        conn.close()
        return "评论不存在", 404

    if not is_admin() and row["visitor_id"] != vid:
        conn.close()
        return "无权删除这条评论", 403

    conn.execute("DELETE FROM review_likes WHERE review_id = ?", (review_id,))
    conn.execute("DELETE FROM reviews WHERE id = ?", (review_id,))
    conn.commit()
    conn.close()

    return redirect(url_for("dish_detail", dish_id=row["dish_id"]))


# ============================================================
# 学生端：楼层 / 窗口
# ============================================================

@app.route("/canteen/<int:canteen_id>")
def canteen_view(canteen_id):
    conn = get_db()
    canteen = conn.execute(
        "SELECT * FROM canteens WHERE id = ?", (canteen_id,)
    ).fetchone()
    if canteen is None:
        conn.close()
        return "楼层不存在", 404

    stalls = conn.execute("""
        SELECT s.id, s.name,
               COUNT(d.id) AS dish_count
        FROM stalls s
        LEFT JOIN dishes d ON d.stall_id = s.id
        WHERE s.canteen_id = ?
        GROUP BY s.id
        ORDER BY s.sort_order, s.id
    """, (canteen_id,)).fetchall()
    conn.close()
    return render_template("canteen.html", canteen=canteen, stalls=stalls)


@app.route("/stall/<int:stall_id>")
def stall_view(stall_id):
    vid = g.visitor_id
    conn = get_db()
    stall = conn.execute("""
        SELECT s.id, s.name, c.id AS canteen_id, c.name AS canteen_name
        FROM stalls s
        JOIN canteens c ON c.id = s.canteen_id
        WHERE s.id = ?
    """, (stall_id,)).fetchone()
    if stall is None:
        conn.close()
        return "窗口不存在", 404

    meal = request.args.get("meal", "all")
    params = [vid, stall_id]
    meal_sql = ""
    if meal in MEALS:
        meal_sql = " AND d.meal = ?"
        params.append(meal)
    else:
        meal = "all"

    dishes = conn.execute(f"""
        SELECT d.id, d.name, d.price, d.description, d.meal, d.image,
               CASE WHEN COUNT(r.id) >= 5 AND AVG(r.rating) >= 4.5
                    THEN 1 ELSE 0 END AS is_signature,
               d.is_new, d.spicy_level,
               ROUND(AVG(r.rating), 1) AS avg_rating,
               COUNT(r.id)             AS review_count,
               (SELECT COUNT(*) FROM page_views
                WHERE path = '/dish/' || d.id) AS view_count,
               EXISTS(
                   SELECT 1 FROM favorites f
                   WHERE f.dish_id = d.id AND f.visitor_id = ?
               ) AS is_favorited
        FROM dishes d
        LEFT JOIN reviews r ON r.dish_id = d.id
        WHERE d.stall_id = ? {meal_sql}
        GROUP BY d.id
        ORDER BY d.id
    """, params).fetchall()
    conn.close()

    return render_template(
        "stall.html",
        stall=stall,
        dishes=dishes,
        current_meal=meal,
        meals=MEALS,
        meal_label=MEAL_LABEL,
    )


# ============================================================
# 学生端：菜品详情 + 发评价 + 点赞排序
# ============================================================

@app.route("/dish/<int:dish_id>", methods=["GET", "POST"])
def dish_detail(dish_id):
    vid = g.visitor_id
    conn = get_db()

    dish = conn.execute("""
        SELECT d.id, d.name, d.price, d.description, d.meal, d.image,
               CASE WHEN COUNT(r.id) >= 5 AND AVG(r.rating) >= 4.5
                    THEN 1 ELSE 0 END AS is_signature,
               d.is_new, d.spicy_level,
               s.id AS stall_id, s.name AS stall_name,
               c.id AS canteen_id, c.name AS canteen_name,
               ROUND(AVG(r.rating), 1) AS avg_rating,
               COUNT(r.id)             AS review_count,
               (SELECT COUNT(*) FROM page_views
                WHERE path = '/dish/' || d.id) AS view_count,
               EXISTS(
                   SELECT 1 FROM favorites f
                   WHERE f.dish_id = d.id AND f.visitor_id = ?
               ) AS is_favorited
        FROM dishes d
        JOIN stalls s   ON s.id = d.stall_id
        JOIN canteens c ON c.id = s.canteen_id
        LEFT JOIN reviews r ON r.dish_id = d.id
        WHERE d.id = ?
        GROUP BY d.id
    """, (vid, dish_id)).fetchone()

    if dish is None:
        conn.close()
        return "菜品不存在", 404

    if request.method == "POST":
        # 黑名单检查
        ip = get_client_ip()
        if is_ip_banned(ip):
            conn.close()
            flash("你的 IP 已被禁止发言，无法提交评价。", "error")
            return redirect(url_for("dish_detail", dish_id=dish_id))

        author  = current_author_name()
        if not author:
            conn.close()
            flash("请先用学生账号登录后再发言", "error")
            return redirect(url_for("signin", next=url_for("dish_detail", dish_id=dish_id)))

        rating  = request.form.get("rating", "0")
        content = request.form.get("content", "").strip()

        # 去重：同一人对同一道菜，24h 内相同内容不重复
        if content:
            dup = conn.execute("""
                SELECT 1 FROM reviews
                WHERE dish_id = ? AND visitor_id = ? AND content = ?
                  AND created_at >= datetime('now', '-1 day', '+8 hours')
            """, (dish_id, vid, content)).fetchone()
            if dup:
                conn.close()
                flash("你今天已经发过相同内容的评价了，请勿重复提交。", "error")
                return redirect(url_for("dish_detail", dish_id=dish_id))

        photo_name = None
        file = request.files.get("photo")
        if file and file.filename and is_allowed(file.filename):
            safe = secure_filename(file.filename)
            photo_name = f"{int(time.time())}_{safe}"
            file.save(os.path.join(UPLOAD_DIR, photo_name))

        if author and content and rating.isdigit():
            conn.execute(
                "INSERT INTO reviews "
                "(dish_id, author, rating, content, photo, visitor_id) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (dish_id, author, int(rating), content, photo_name, vid),
            )
            conn.commit()
        conn.close()
        return redirect(url_for("dish_detail", dish_id=dish_id))

    sort = request.args.get("sort", "helpful")
    if sort == "new":
        order_sql = "r.id DESC"
    else:
        sort = "helpful"
        order_sql = "like_count DESC, r.id DESC"

    reviews = conn.execute(f"""
        SELECT r.id, r.author, r.rating, r.content, r.photo, r.created_at,
               r.visitor_id,
               (SELECT COUNT(*) FROM review_likes rl
                WHERE rl.review_id = r.id) AS like_count,
               EXISTS(
                   SELECT 1 FROM review_likes rl
                   WHERE rl.review_id = r.id AND rl.visitor_id = ?
               ) AS is_liked
        FROM reviews r
        WHERE r.dish_id = ?
        ORDER BY {order_sql}
    """, (vid, dish_id)).fetchall()
    conn.close()
    return render_template(
        "dish.html",
        dish=dish,
        reviews=reviews,
        sort=sort,
        my_visitor_id=vid,
    )


# ============================================================
# 登录 / 登出 / 后台首页 / 关于
# ============================================================

@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        pwd = request.form.get("password", "")
        if pwd == ADMIN_PASSWORD:
            session["is_admin"] = True
            return redirect(url_for("admin"))
        else:
            error = "密码不对"
    return render_template("login.html", error=error)

# ============================================================
# 学生账号系统
# ============================================================

EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')


@app.route("/register", methods=["GET", "POST"])
def register():
    if is_logged_in():
        return redirect(url_for("home"))

    error = None

    if request.method == "POST":
        email    = request.form.get("email", "").strip().lower()
        nickname = request.form.get("nickname", "").strip()
        password = request.form.get("password", "")
        password2 = request.form.get("password2", "")

        if not email or not nickname or not password:
            error = "所有字段都要填"
        elif not EMAIL_RE.match(email):
            error = "邮箱格式不对"
        elif len(nickname) > 20:
            error = "昵称不能超过 20 字"
        elif len(password) < 6:
            error = "密码至少 6 位"
        elif password != password2:
            error = "两次密码不一致"
        else:
            conn = get_db()
            exists = conn.execute(
                "SELECT id FROM users WHERE email = ?", (email,)
            ).fetchone()
            if exists:
                error = "这个邮箱已经注册过了"
                conn.close()
            else:
                conn.execute(
                    "INSERT INTO users (email, password_hash, nickname) "
                    "VALUES (?, ?, ?)",
                    (email, generate_password_hash(password), nickname)
                )
                conn.commit()
                conn.close()
                flash("注册成功，请登录", "success")
                return redirect(url_for("signin"))

    return render_template("register.html", error=error)


@app.route("/signin", methods=["GET", "POST"])
def signin():
    if is_logged_in():
        return redirect(url_for("home"))

    error = None
    next_url = request.args.get("next", "")

    if request.method == "POST":
        email    = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not email or not password:
            error = "邮箱和密码都要填"
        else:
            conn = get_db()
            user = conn.execute(
                "SELECT * FROM users WHERE email = ?", (email,)
            ).fetchone()
            conn.close()

            if not user or not check_password_hash(user["password_hash"], password):
                error = "邮箱或密码不对"
            else:
                session["user_id"] = user["id"]
                if user["is_banned"]:
                    flash(f"欢迎回来，{user['nickname']}。你的账号目前被禁言，不能发言。", "error")
                else:
                    flash(f"欢迎回来，{user['nickname']}", "success")
                if next_url and next_url.startswith("/") and not next_url.startswith("//"):
                    return redirect(next_url)
                return redirect(url_for("home"))

    return render_template("signin.html", error=error, next_url=next_url)


@app.route("/signout")
def signout():
    session.pop("user_id", None)
    flash("已退出登录", "success")
    return redirect(url_for("home"))


@app.route("/logout")
def logout():
    session.pop("is_admin", None)
    return redirect(url_for("home"))


@app.route("/admin")
def admin():
    if not is_admin():
        return redirect(url_for("login"))
    return render_template("admin.html")


@app.route("/about")
def about():
    return render_template("about.html")


# ============================================================
# 公告（学生端）
# ============================================================

@app.route("/announcements")
def announcements_list():
    vid = g.visitor_id
    conn = get_db()

    items = conn.execute("""
        SELECT a.*,
               EXISTS(
                   SELECT 1 FROM announcement_reads ar
                   WHERE ar.announcement_id = a.id AND ar.visitor_id = ?
               ) AS is_read,
               CASE WHEN a.expires_at IS NULL
                     OR a.expires_at >= datetime('now', '+8 hours')
                    THEN 1 ELSE 0 END AS is_active
        FROM announcements a
        ORDER BY a.is_pinned DESC, a.id DESC
    """, (vid,)).fetchall()

    conn.close()
    return render_template("announcements.html", items=items)


@app.route("/announcements/<int:aid>")
def announcement_detail(aid):
    vid = g.visitor_id
    conn = get_db()

    item = conn.execute("""
        SELECT * FROM announcements WHERE id = ?
    """, (aid,)).fetchone()

    if item is None:
        conn.close()
        return "公告不存在", 404

    try:
        conn.execute(
            "INSERT OR IGNORE INTO announcement_reads "
            "(visitor_id, announcement_id) VALUES (?, ?)",
            (vid, aid),
        )
        conn.commit()
    except Exception:
        pass

    conn.close()
    return render_template("announcement_detail.html", item=item)


# ============================================================
# 热门榜单
# ============================================================

@app.route("/hot")
def hot():
    conn = get_db()

    top_rated = conn.execute("""
        SELECT d.id, d.name,
               s.name AS stall_name,
               c.name AS canteen_name,
               ROUND(AVG(r.rating), 1) AS avg_rating,
               COUNT(r.id)             AS review_count
        FROM dishes d
        JOIN stalls s   ON s.id = d.stall_id
        JOIN canteens c ON c.id = s.canteen_id
        LEFT JOIN reviews r ON r.dish_id = d.id
        GROUP BY d.id
        HAVING review_count >= 3
        ORDER BY avg_rating DESC, review_count DESC
        LIMIT 10
    """).fetchall()

    hottest = conn.execute("""
        SELECT d.id, d.name,
               s.name AS stall_name,
               c.name AS canteen_name,
               ROUND(AVG(r.rating), 1) AS avg_rating,
               COUNT(r.id)             AS review_count
        FROM dishes d
        JOIN stalls s   ON s.id = d.stall_id
        JOIN canteens c ON c.id = s.canteen_id
        LEFT JOIN reviews r ON r.dish_id = d.id
        GROUP BY d.id
        HAVING review_count > 0
        ORDER BY review_count DESC, avg_rating DESC
        LIMIT 10
    """).fetchall()

    fav_top = conn.execute("""
        SELECT d.id, d.name,
               s.name AS stall_name,
               c.name AS canteen_name,
               COUNT(f.id) AS fav_count
        FROM dishes d
        JOIN stalls s   ON s.id = d.stall_id
        JOIN canteens c ON c.id = s.canteen_id
        JOIN favorites f ON f.dish_id = d.id
        GROUP BY d.id
        ORDER BY fav_count DESC
        LIMIT 10
    """).fetchall()

    conn.close()

    return render_template(
        "hot.html",
        top_rated=top_rated,
        hottest=hottest,
        fav_top=fav_top,
    )


# ============================================================
# 拼饭广场
# ============================================================

@app.route("/board")
def board():
    vid = g.visitor_id
    conn = get_db()

    posts = conn.execute("""
        SELECT p.id, p.author, p.content, p.when_time, p.contact,
               p.created_at, p.last_reply_at, p.visitor_id,
               s.id AS stall_id, s.name AS stall_name,
               c.name AS canteen_name,
               (SELECT COUNT(*) FROM post_replies pr WHERE pr.post_id = p.id) AS reply_count
        FROM posts p
        LEFT JOIN stalls s   ON s.id = p.stall_id
        LEFT JOIN canteens c ON c.id = s.canteen_id
        ORDER BY p.last_reply_at DESC
        LIMIT 50
    """).fetchall()
    conn.close()
    return render_template("board.html", posts=posts, my_visitor_id=vid)


@app.route("/board/new", methods=["GET", "POST"])
def board_new():
    vid = g.visitor_id
    conn = get_db()
    error = None

    if request.method == "POST":
        ip = get_client_ip()
        if is_ip_banned(ip):
            conn.close()
            flash("你的 IP 已被禁止发言，无法发帖。", "error")
            return redirect(url_for("board"))

        author    = current_author_name()
        if not author:
            conn.close()
            flash("请先用学生账号登录后再发帖", "error")
            return redirect(url_for("signin", next=url_for("board_new")))

        content   = request.form.get("content", "").strip()
        when_time = request.form.get("when_time", "").strip()
        contact   = request.form.get("contact", "").strip()
        stall_id  = request.form.get("stall_id", "")

        if not author or not content:
            error = "昵称和内容不能为空"
        elif len(content) > 500:
            error = "内容过长（最多 500 字）"
        else:
            dup = conn.execute("""
                SELECT 1 FROM posts
                WHERE visitor_id = ? AND content = ?
                  AND created_at >= datetime('now', '-1 day', '+8 hours')
            """, (vid, content)).fetchone()

            recent = conn.execute("""
                SELECT COUNT(*) AS c FROM posts
                WHERE visitor_id = ?
                  AND created_at >= datetime('now', '-10 minutes', '+8 hours')
            """, (vid,)).fetchone()["c"]

            if dup:
                error = "你今天已经发过相同内容的帖子了，请勿重复提交"
            elif recent >= 3:
                error = "发帖太频繁了，请等几分钟再试"
            else:
                stall_val = None
                if stall_id.isdigit():
                    exists = conn.execute(
                        "SELECT id FROM stalls WHERE id = ?", (int(stall_id),)
                    ).fetchone()
                    if exists:
                        stall_val = int(stall_id)

                conn.execute("""
                    INSERT INTO posts
                    (author, content, when_time, contact, stall_id, visitor_id,
                     last_reply_at)
                    VALUES (?, ?, ?, ?, ?, ?, datetime('now', '+8 hours'))
                """, (author, content, when_time or None, contact or None,
                      stall_val, vid))
                conn.commit()
                conn.close()
                return redirect(url_for("board"))

    all_stalls = conn.execute("""
        SELECT s.id, s.name, c.name AS canteen_name
        FROM stalls s
        JOIN canteens c ON c.id = s.canteen_id
        ORDER BY c.sort_order, c.id, s.sort_order, s.id
    """).fetchall()
    conn.close()
    return render_template("board_new.html", all_stalls=all_stalls, error=error)


@app.route("/board/<int:post_id>", methods=["GET", "POST"])
def board_detail(post_id):
    vid = g.visitor_id
    conn = get_db()

    post = conn.execute("""
        SELECT p.*,
               s.name AS stall_name,
               c.id   AS canteen_id,
               c.name AS canteen_name
        FROM posts p
        LEFT JOIN stalls s   ON s.id = p.stall_id
        LEFT JOIN canteens c ON c.id = s.canteen_id
        WHERE p.id = ?
    """, (post_id,)).fetchone()

    if post is None:
        conn.close()
        return "帖子不存在", 404

    if request.method == "POST":
        ip = get_client_ip()
        if is_ip_banned(ip):
            conn.close()
            flash("你的 IP 已被禁止发言，无法回复。", "error")
            return redirect(url_for("board_detail", post_id=post_id))

        author  = current_author_name()
        if not author:
            conn.close()
            flash("请先用学生账号登录后再回复", "error")
            return redirect(url_for("signin", next=url_for("board_detail", post_id=post_id)))

        content = request.form.get("content", "").strip()

        if author and content and len(content) <= 300:
            dup = conn.execute("""
                SELECT 1 FROM post_replies
                WHERE visitor_id = ? AND post_id = ? AND content = ?
                  AND created_at >= datetime('now', '-1 day', '+8 hours')
            """, (vid, post_id, content)).fetchone()

            recent = conn.execute("""
                SELECT COUNT(*) AS c FROM post_replies
                WHERE visitor_id = ? AND post_id = ?
                  AND created_at >= datetime('now', '-1 minute', '+8 hours')
            """, (vid, post_id)).fetchone()["c"]

            if dup:
                flash("你今天已经发过相同内容的回复了，请勿重复提交。", "error")
            elif recent == 0:
                conn.execute("""
                    INSERT INTO post_replies (post_id, author, content, visitor_id)
                    VALUES (?, ?, ?, ?)
                """, (post_id, author, content, vid))
                conn.execute("""
                    UPDATE posts SET last_reply_at = datetime('now', '+8 hours')
                    WHERE id = ?
                """, (post_id,))
                conn.commit()
        conn.close()
        return redirect(url_for("board_detail", post_id=post_id))

    replies = conn.execute("""
        SELECT * FROM post_replies
        WHERE post_id = ?
        ORDER BY id ASC
    """, (post_id,)).fetchall()
    conn.close()

    return render_template(
        "board_detail.html",
        post=post,
        replies=replies,
        my_visitor_id=vid,
    )


@app.route("/board/<int:post_id>/delete-own", methods=["POST"])
def board_post_delete_own(post_id):
    vid = g.visitor_id
    conn = get_db()

    post = conn.execute(
        "SELECT visitor_id FROM posts WHERE id = ?", (post_id,)
    ).fetchone()

    if not post:
        conn.close()
        return "帖子不存在", 404

    if not is_admin() and post["visitor_id"] != vid:
        conn.close()
        return "无权删除", 403

    conn.execute("DELETE FROM post_replies WHERE post_id = ?", (post_id,))
    conn.execute("DELETE FROM posts WHERE id = ?", (post_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("board"))


@app.route("/board/reply/<int:reply_id>/delete-own", methods=["POST"])
def board_reply_delete_own(reply_id):
    vid = g.visitor_id
    conn = get_db()

    reply = conn.execute(
        "SELECT visitor_id, post_id FROM post_replies WHERE id = ?", (reply_id,)
    ).fetchone()

    if not reply:
        conn.close()
        return "回复不存在", 404

    if not is_admin() and reply["visitor_id"] != vid:
        conn.close()
        return "无权删除", 403

    conn.execute("DELETE FROM post_replies WHERE id = ?", (reply_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("board_detail", post_id=reply["post_id"]))


@app.route("/admin/board")
def admin_board():
    if not is_admin():
        return redirect(url_for("login"))

    conn = get_db()
    posts = conn.execute("""
        SELECT p.id, p.author, p.content, p.when_time, p.contact,
               p.created_at,
               s.name AS stall_name,
               c.name AS canteen_name,
               (SELECT COUNT(*) FROM post_replies pr WHERE pr.post_id = p.id) AS reply_count
        FROM posts p
        LEFT JOIN stalls s   ON s.id = p.stall_id
        LEFT JOIN canteens c ON c.id = s.canteen_id
        ORDER BY p.id DESC
        LIMIT 200
    """).fetchall()
    conn.close()
    return render_template("admin_board.html", posts=posts)


@app.route("/board/<int:post_id>/delete", methods=["POST"])
def board_post_delete(post_id):
    if not is_admin():
        return redirect(url_for("login"))

    conn = get_db()
    conn.execute("DELETE FROM post_replies WHERE post_id = ?", (post_id,))
    conn.execute("DELETE FROM posts WHERE id = ?", (post_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("admin_board"))


# ============================================================
# 后台：管理楼层
# ============================================================

@app.route("/admin/canteens", methods=["GET", "POST"])
def admin_canteens():
    if not is_admin():
        return redirect(url_for("login"))

    conn = get_db()

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if name:
            conn.execute(
                "INSERT INTO canteens (name, sort_order) VALUES (?, ?)",
                (name, 0),
            )
            conn.commit()

    canteens = conn.execute("""
        SELECT c.id, c.name,
               COUNT(DISTINCT s.id) AS stall_count,
               COUNT(d.id)          AS dish_count
        FROM canteens c
        LEFT JOIN stalls s ON s.canteen_id = c.id
        LEFT JOIN dishes d ON d.stall_id   = s.id
        GROUP BY c.id
        ORDER BY c.sort_order, c.id
    """).fetchall()
    conn.close()
    return render_template("admin_canteens.html", canteens=canteens)


@app.route("/admin/canteens/<int:cid>/delete", methods=["POST"])
def admin_canteens_delete(cid):
    if not is_admin():
        return redirect(url_for("login"))

    conn = get_db()
    stall_ids = [row["id"] for row in conn.execute(
        "SELECT id FROM stalls WHERE canteen_id = ?", (cid,)
    ).fetchall()]
    for sid in stall_ids:
        dish_ids = [row["id"] for row in conn.execute(
            "SELECT id FROM dishes WHERE stall_id = ?", (sid,)
        ).fetchall()]
        for did in dish_ids:
            review_ids = [r["id"] for r in conn.execute(
                "SELECT id FROM reviews WHERE dish_id = ?", (did,)
            ).fetchall()]
            for rid in review_ids:
                conn.execute("DELETE FROM review_likes WHERE review_id = ?", (rid,))
            conn.execute("DELETE FROM reviews WHERE dish_id = ?", (did,))
            conn.execute("DELETE FROM favorites WHERE dish_id = ?", (did,))
        conn.execute("DELETE FROM dishes WHERE stall_id = ?", (sid,))
    conn.execute("DELETE FROM stalls WHERE canteen_id = ?", (cid,))
    conn.execute("DELETE FROM canteens WHERE id = ?", (cid,))
    conn.commit()
    conn.close()
    return redirect(url_for("admin_canteens"))


# ============================================================
# 后台：管理窗口
# ============================================================

@app.route("/admin/stalls", methods=["GET", "POST"])
def admin_stalls():
    if not is_admin():
        return redirect(url_for("login"))

    conn = get_db()

    if request.method == "POST":
        canteen_id = request.form.get("canteen_id", "")
        name       = request.form.get("name", "").strip()

        if name and canteen_id.isdigit():
            exists = conn.execute(
                "SELECT id FROM canteens WHERE id = ?", (int(canteen_id),)
            ).fetchone()
            if exists:
                conn.execute(
                    "INSERT INTO stalls (canteen_id, name, sort_order) VALUES (?, ?, ?)",
                    (int(canteen_id), name, 0),
                )
                conn.commit()

    canteens = conn.execute(
        "SELECT * FROM canteens ORDER BY sort_order, id"
    ).fetchall()

    stalls = conn.execute("""
        SELECT s.id, s.name, c.name AS canteen_name,
               COUNT(d.id) AS dish_count
        FROM stalls s
        JOIN canteens c ON c.id = s.canteen_id
        LEFT JOIN dishes d ON d.stall_id = s.id
        GROUP BY s.id
        ORDER BY c.sort_order, c.id, s.sort_order, s.id
    """).fetchall()
    conn.close()
    return render_template(
        "admin_stalls.html",
        canteens=canteens,
        stalls=stalls,
    )


@app.route("/admin/stalls/<int:sid>/delete", methods=["POST"])
def admin_stalls_delete(sid):
    if not is_admin():
        return redirect(url_for("login"))

    conn = get_db()
    dish_ids = [row["id"] for row in conn.execute(
        "SELECT id FROM dishes WHERE stall_id = ?", (sid,)
    ).fetchall()]
    for did in dish_ids:
        review_ids = [r["id"] for r in conn.execute(
            "SELECT id FROM reviews WHERE dish_id = ?", (did,)
        ).fetchall()]
        for rid in review_ids:
            conn.execute("DELETE FROM review_likes WHERE review_id = ?", (rid,))
        conn.execute("DELETE FROM reviews WHERE dish_id = ?", (did,))
        conn.execute("DELETE FROM favorites WHERE dish_id = ?", (did,))
    conn.execute("DELETE FROM dishes WHERE stall_id = ?", (sid,))
    conn.execute("DELETE FROM stalls WHERE id = ?", (sid,))
    conn.commit()
    conn.close()
    return redirect(url_for("admin_stalls"))


# ============================================================
# 后台：菜品
# ============================================================

@app.route("/admin/dishes")
def admin_dishes():
    if not is_admin():
        return redirect(url_for("login"))

    conn = get_db()
    dishes = conn.execute("""
        SELECT d.id, d.name, d.price, d.meal, d.stall_id, d.image,
               d.is_new, d.spicy_level,
               s.name AS stall_name,
               c.name AS canteen_name
        FROM dishes d
        JOIN stalls s   ON s.id = d.stall_id
        JOIN canteens c ON c.id = s.canteen_id
        ORDER BY c.sort_order, c.id, s.sort_order, s.id, d.id
    """).fetchall()
    conn.close()

    return render_template(
        "admin_dishes.html",
        dishes=dishes,
        meal_label=MEAL_LABEL,
    )


@app.route("/dish/new", methods=["GET", "POST"])
def dish_new():
    if not is_admin():
        return redirect(url_for("login"))

    conn = get_db()

    if request.method == "POST":
        name        = request.form.get("name", "").strip()
        price       = request.form.get("price", "").strip()
        description = request.form.get("description", "").strip()
        meal        = request.form.get("meal", "lunch")
        stall_id    = request.form.get("stall_id", "")

        if not name or not price or not stall_id.isdigit():
            conn.close()
            return "菜名、价格、窗口为必填项", 400

        try:
            price_val = float(price)
        except ValueError:
            conn.close()
            return "价格必须是数字", 400

        if price_val <= 0:
            conn.close()
            return "价格必须大于 0", 400

        if meal not in MEALS:
            conn.close()
            return "餐次不合法", 400

        exists = conn.execute(
            "SELECT id FROM stalls WHERE id = ?", (int(stall_id),)
        ).fetchone()
        if not exists:
            conn.close()
            return "窗口不存在", 400

        image_name = save_image(request.files.get("image"))
        is_new, spicy = parse_badges_from_form()
        weekdays = parse_weekdays_from_form()

        conn.execute(
            "INSERT INTO dishes "
            "(stall_id, name, price, description, meal, image, "
            " is_signature, is_new, spicy_level, weekdays) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (int(stall_id), name, price_val, description, meal, image_name,
             0, is_new, spicy, weekdays),
        )
        conn.commit()
        conn.close()
        return redirect(url_for("admin_dishes"))

    all_stalls = conn.execute("""
        SELECT s.id, s.name, c.name AS canteen_name
        FROM stalls s
        JOIN canteens c ON c.id = s.canteen_id
        ORDER BY c.sort_order, c.id, s.sort_order, s.id
    """).fetchall()
    conn.close()
    return render_template(
        "dish_new.html",
        meals=MEALS,
        meal_label=MEAL_LABEL,
        all_stalls=all_stalls,
    )


@app.route("/dish/<int:dish_id>/edit", methods=["GET", "POST"])
def dish_edit(dish_id):
    if not is_admin():
        return redirect(url_for("login"))

    conn = get_db()

    if request.method == "POST":
        name        = request.form.get("name", "").strip()
        price       = request.form.get("price", "").strip()
        description = request.form.get("description", "").strip()
        meal        = request.form.get("meal", "lunch")
        stall_id    = request.form.get("stall_id", "")

        if not name or not price or not stall_id.isdigit():
            conn.close()
            return "菜名、价格、窗口为必填项", 400

        try:
            price_val = float(price)
        except ValueError:
            conn.close()
            return "价格必须是数字", 400

        if price_val <= 0:
            conn.close()
            return "价格必须大于 0", 400

        if meal not in MEALS:
            conn.close()
            return "餐次不合法", 400

        exists = conn.execute(
            "SELECT id FROM stalls WHERE id = ?", (int(stall_id),)
        ).fetchone()
        if not exists:
            conn.close()
            return "窗口不存在", 400

        weekdays = parse_weekdays_from_form()
        is_new, spicy = parse_badges_from_form()
        new_image = save_image(request.files.get("image"))
        remove_image = request.form.get("remove_image") == "1"

        if remove_image:
            old = conn.execute(
                "SELECT image FROM dishes WHERE id = ?", (dish_id,)
            ).fetchone()
            if old and old["image"]:
                p = os.path.join(DISH_IMAGE_DIR, old["image"])
                if os.path.exists(p):
                    os.remove(p)
            conn.execute("""
                UPDATE dishes SET stall_id = ?, name = ?, price = ?,
                    description = ?, meal = ?, image = NULL,
                    is_new = ?, spicy_level = ?, weekdays = ?
                WHERE id = ?
            """, (int(stall_id), name, price_val, description, meal,
                  is_new, spicy, weekdays, dish_id))
        elif new_image:
            old = conn.execute(
                "SELECT image FROM dishes WHERE id = ?", (dish_id,)
            ).fetchone()
            if old and old["image"]:
                p = os.path.join(DISH_IMAGE_DIR, old["image"])
                if os.path.exists(p):
                    os.remove(p)
            conn.execute("""
                UPDATE dishes SET stall_id = ?, name = ?, price = ?,
                    description = ?, meal = ?, image = ?,
                    is_new = ?, spicy_level = ?, weekdays = ?
                WHERE id = ?
            """, (int(stall_id), name, price_val, description, meal, new_image,
                  is_new, spicy, weekdays, dish_id))
        else:
            conn.execute("""
                UPDATE dishes SET stall_id = ?, name = ?, price = ?,
                    description = ?, meal = ?,
                    is_new = ?, spicy_level = ?, weekdays = ?
                WHERE id = ?
            """, (int(stall_id), name, price_val, description, meal,
                  is_new, spicy, weekdays, dish_id))

        conn.commit()
        conn.close()
        return redirect(url_for("admin_dishes"))

    dish = conn.execute(
        "SELECT * FROM dishes WHERE id = ?", (dish_id,)
    ).fetchone()
    if dish is None:
        conn.close()
        return "菜品不存在", 404

    all_stalls = conn.execute("""
        SELECT s.id, s.name, c.name AS canteen_name
        FROM stalls s
        JOIN canteens c ON c.id = s.canteen_id
        ORDER BY c.sort_order, c.id, s.sort_order, s.id
    """).fetchall()
    conn.close()
    return render_template(
        "dish_edit.html",
        dish=dish,
        meals=MEALS,
        meal_label=MEAL_LABEL,
        all_stalls=all_stalls,
    )


@app.route("/dish/<int:dish_id>/delete", methods=["POST"])
def dish_delete(dish_id):
    if not is_admin():
        return redirect(url_for("login"))

    conn = get_db()
    row = conn.execute(
        "SELECT image FROM dishes WHERE id = ?", (dish_id,)
    ).fetchone()
    if row and row["image"]:
        p = os.path.join(DISH_IMAGE_DIR, row["image"])
        if os.path.exists(p):
            os.remove(p)

    review_ids = [r["id"] for r in conn.execute(
        "SELECT id FROM reviews WHERE dish_id = ?", (dish_id,)
    ).fetchall()]
    for rid in review_ids:
        conn.execute("DELETE FROM review_likes WHERE review_id = ?", (rid,))

    conn.execute("DELETE FROM reviews WHERE dish_id = ?", (dish_id,))
    conn.execute("DELETE FROM favorites WHERE dish_id = ?", (dish_id,))
    conn.execute("DELETE FROM dishes WHERE id = ?", (dish_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("admin_dishes"))


@app.route("/admin/dishes/bulk", methods=["GET", "POST"])
def admin_dishes_bulk():
    if not is_admin():
        return redirect(url_for("login"))

    conn = get_db()
    report = None

    if request.method == "POST":
        meal     = request.form.get("meal", "lunch")
        stall_id = request.form.get("stall_id", "")
        raw      = request.form.get("bulk_text", "")

        if meal not in MEALS:
            conn.close()
            return "餐次不合法", 400
        if not stall_id.isdigit():
            conn.close()
            return "请选择窗口", 400

        exists = conn.execute(
            "SELECT id FROM stalls WHERE id = ?", (int(stall_id),)
        ).fetchone()
        if not exists:
            conn.close()
            return "窗口不存在", 400

        lines = raw.splitlines()
        ok_names = []
        fail_lines = []

        for line in lines:
            line = line.strip()
            if not line:
                continue

            parts = [p.strip() for p in line.split("|")]
            if len(parts) < 2:
                fail_lines.append((line, "字段不足（至少 菜名 | 价格）"))
                continue

            name      = parts[0]
            price_str = parts[1]
            description = parts[2] if len(parts) >= 3 else ""

            if not name or not price_str:
                fail_lines.append((line, "菜名 / 价格不能为空"))
                continue

            try:
                price_val = float(price_str)
            except ValueError:
                fail_lines.append((line, f"价格不是数字：{price_str}"))
                continue

            if price_val <= 0:
                fail_lines.append((line, "价格必须大于 0"))
                continue

            conn.execute(
                "INSERT INTO dishes (stall_id, name, price, description, meal) "
                "VALUES (?, ?, ?, ?, ?)",
                (int(stall_id), name, price_val, description, meal),
            )
            ok_names.append(name)

        conn.commit()

        report = {
            "ok_count":   len(ok_names),
            "ok_names":   ok_names,
            "fail_count": len(fail_lines),
            "fail_lines": fail_lines,
        }

    all_stalls = conn.execute("""
        SELECT s.id, s.name, c.name AS canteen_name
        FROM stalls s
        JOIN canteens c ON c.id = s.canteen_id
        ORDER BY c.sort_order, c.id, s.sort_order, s.id
    """).fetchall()
    conn.close()

    return render_template(
        "admin_dishes_bulk.html",
        meals=MEALS,
        meal_label=MEAL_LABEL,
        all_stalls=all_stalls,
        report=report,
    )

@app.route("/admin/dishes/excel", methods=["GET", "POST"])
def admin_dishes_excel():
    """Excel 智能导入：从 Excel 粘贴 7 列，自动识别星期"""
    if not is_admin():
        return redirect(url_for("login"))

    conn = get_db()
    all_stalls = conn.execute("""
        SELECT s.id, s.name, c.name AS canteen_name
        FROM stalls s
        JOIN canteens c ON c.id = s.canteen_id
        ORDER BY c.sort_order, c.id, s.sort_order, s.id
    """).fetchall()
    conn.close()

    error = None
    report = None
    bulk_text = ""

    if request.method == "POST":
        bulk_text = request.form.get("bulk_text", "")
        stall_id  = request.form.get("stall_id", "")
        meal      = request.form.get("meal", "lunch")
        price_str = request.form.get("price", "0").strip()

        # 解析价格
        try:
            default_price = float(price_str) if price_str else 0
        except ValueError:
            default_price = 0
        if default_price < 0:
            default_price = 0

        if not bulk_text.strip():
            error = "请先粘贴内容"
        elif not stall_id.isdigit():
            error = "请选择入库窗口"
        elif meal not in MEALS:
            error = "餐次不合法"
        else:
            conn = get_db()
            exists = conn.execute(
                "SELECT id FROM stalls WHERE id = ?", (int(stall_id),)
            ).fetchone()
            if not exists:
                error = "窗口不存在"
                conn.close()
            else:
                pairs, skipped = parse_week_columns(bulk_text)

                ok_list = []
                for name, weekdays in pairs:
                    conn.execute(
                        "INSERT INTO dishes "
                        "(stall_id, name, price, description, meal, weekdays) "
                        "VALUES (?, ?, ?, ?, ?, ?)",
                        (int(stall_id), name, default_price, "", meal, weekdays),
                    )
                    ok_list.append({"name": name, "weekdays": weekdays})

                conn.commit()
                conn.close()

                report = {
                    "ok_count":   len(ok_list),
                    "ok_list":    ok_list,
                    "skip_count": len(skipped),
                    "skip_lines": skipped,
                }

    return render_template(
        "admin_dishes_excel.html",
        all_stalls=all_stalls,
        meals=MEALS,
        meal_label=MEAL_LABEL,
        weekday_labels=WEEKDAY_LABELS,
        error=error,
        report=report,
        bulk_text=bulk_text,
    )

@app.route("/admin/dishes/batch", methods=["GET", "POST"])
def admin_dishes_batch():
    """批量删除菜品"""
    if not is_admin():
        return redirect(url_for("login"))

    conn = get_db()
    all_stalls = conn.execute("""
        SELECT s.id, s.name, c.name AS canteen_name
        FROM stalls s
        JOIN canteens c ON c.id = s.canteen_id
        ORDER BY c.sort_order, c.id, s.sort_order, s.id
    """).fetchall()

    # 处理删除
    if request.method == "POST":
        ids = request.form.getlist("dish_ids")
        deleted = 0
        for did in ids:
            if not did.isdigit():
                continue
            did = int(did)

            # 删图片文件
            row = conn.execute(
                "SELECT image FROM dishes WHERE id = ?", (did,)
            ).fetchone()
            if row and row["image"]:
                p = os.path.join(DISH_IMAGE_DIR, row["image"])
                if os.path.exists(p):
                    os.remove(p)

            # 删评价点赞
            review_ids = [r["id"] for r in conn.execute(
                "SELECT id FROM reviews WHERE dish_id = ?", (did,)
            ).fetchall()]
            for rid in review_ids:
                conn.execute("DELETE FROM review_likes WHERE review_id = ?", (rid,))

            # 删关联数据
            conn.execute("DELETE FROM reviews WHERE dish_id = ?", (did,))
            conn.execute("DELETE FROM favorites WHERE dish_id = ?", (did,))
            conn.execute("DELETE FROM dishes WHERE id = ?", (did,))
            deleted += 1

        conn.commit()
        conn.close()
        flash(f"✓ 已删除 {deleted} 道菜", "success")
        return redirect(url_for("admin_dishes_batch"))

    # GET：显示列表
    stall_id = request.args.get("stall_id", "")
    if stall_id.isdigit():
        dishes = conn.execute("""
            SELECT d.id, d.name, d.price, d.meal,
                   s.name AS stall_name,
                   c.name AS canteen_name
            FROM dishes d
            JOIN stalls s   ON s.id = d.stall_id
            JOIN canteens c ON c.id = s.canteen_id
            WHERE d.stall_id = ?
            ORDER BY d.id DESC
        """, (int(stall_id),)).fetchall()
    else:
        dishes = conn.execute("""
            SELECT d.id, d.name, d.price, d.meal,
                   s.name AS stall_name,
                   c.name AS canteen_name
            FROM dishes d
            JOIN stalls s   ON s.id = d.stall_id
            JOIN canteens c ON c.id = s.canteen_id
            ORDER BY d.id DESC
            LIMIT 500
        """).fetchall()
    conn.close()

    return render_template(
        "admin_dishes_batch.html",
        dishes=dishes,
        all_stalls=all_stalls,
        current_stall=stall_id,
        meal_label=MEAL_LABEL,
    )

# ============================================================
# 反馈（含 IP 记录、限流、去重、黑名单检查）
# ============================================================

@app.route("/feedback", methods=["GET", "POST"])
def feedback():
    submitted = False
    error = None

    if request.method == "POST":
        ip = get_client_ip()

        # 1) 黑名单检查（统一用 helper）
        if is_ip_banned(ip):
            flash("你的 IP 已被禁止提交反馈。如有疑问请联系平台管理员。", "error")
            return redirect(url_for("feedback"))

        conn = get_db()

        category = request.form.get("category", "").strip()
        content  = request.form.get("content", "").strip()
        contact  = request.form.get("contact", "").strip()
        mood_str = request.form.get("mood", "").strip()

        if category not in FEEDBACK_CATEGORIES:
            error = "请选择反馈类型"
        elif not content:
            error = "反馈内容不能为空"
        elif len(content) > 500:
            error = "反馈内容过长（最多 500 字）"
        else:
            recent = conn.execute("""
                SELECT COUNT(*) AS c FROM feedback
                WHERE ip = ? AND created_at >= datetime('now', '-5 minutes', '+8 hours')
            """, (ip,)).fetchone()["c"]

            if recent >= 3:
                error = "提交太频繁了，请等 5 分钟后再试。"
            else:
                dup = conn.execute("""
                    SELECT id FROM feedback
                    WHERE content = ?
                      AND created_at >= datetime('now', '-1 day', '+8 hours')
                    LIMIT 1
                """, (content,)).fetchone()

                if dup:
                    error = "这个内容今天已经被提交过了，请勿重复提交。"
                else:
                    mood = None
                    if mood_str.isdigit():
                        m = int(mood_str)
                        if m in MOOD_LABELS:
                            mood = m

                    conn.execute(
                        "INSERT INTO feedback "
                        "(category, content, contact, mood, ip, user_id) "
                        "VALUES (?, ?, ?, ?, ?, ?)",
                        (category, content, contact or None, mood, ip,
                         session.get("user_id")),
                    )
                    conn.commit()
                    submitted = True

        conn.close()

    return render_template(
        "feedback.html",
        categories=FEEDBACK_CATEGORIES,
        submitted=submitted,
        error=error,
    )

@app.route("/my-feedback")
def my_feedback():
    """学生查看自己提交的反馈 + 管理员回复"""
    uid = session.get("user_id")
    if not uid:
        return redirect(url_for("signin"))

    conn = get_db()

    # 把这个学生所有"已回复"的反馈标记为已读
    conn.execute("""
        UPDATE feedback
        SET reply_read = 1
        WHERE user_id = ?
          AND reply IS NOT NULL
          AND reply != ''
          AND reply_read = 0
    """, (uid,))
    conn.commit()

    items = conn.execute("""
        SELECT * FROM feedback
        WHERE user_id = ?
        ORDER BY id DESC
    """, (uid,)).fetchall()
    conn.close()

    return render_template(
        "my_feedback.html",
        items=items,
        categories=FEEDBACK_CATEGORIES,
    )

@app.route("/feedback/list")
def feedback_list():
    if not is_admin():
        return redirect(url_for("login"))

    conn = get_db()
    items = conn.execute("""
        SELECT * FROM feedback
        ORDER BY
          CASE status WHEN 'new' THEN 0 ELSE 1 END,
          id DESC
    """).fetchall()
    conn.close()

    return render_template(
        "feedback_list.html",
        items=items,
        categories=FEEDBACK_CATEGORIES,
    )


@app.route("/feedback/<int:fid>/done", methods=["POST"])
def feedback_done(fid):
    if not is_admin():
        return redirect(url_for("login"))

    conn = get_db()
    conn.execute("UPDATE feedback SET status = 'done' WHERE id = ?", (fid,))
    conn.commit()
    conn.close()
    return redirect(url_for("feedback_list"))


@app.route("/feedback/<int:fid>/delete", methods=["POST"])
def feedback_delete(fid):
    if not is_admin():
        return redirect(url_for("login"))

    conn = get_db()
    conn.execute("DELETE FROM feedback WHERE id = ?", (fid,))
    conn.commit()
    conn.close()
    return redirect(url_for("feedback_list"))

@app.route("/feedback/<int:fid>/reply", methods=["POST"])
def feedback_reply(fid):
    if not is_admin():
        return redirect(url_for("login"))

    reply = request.form.get("reply", "").strip()
    if not reply:
        flash("回复内容不能为空", "error")
        return redirect(url_for("feedback_list"))

    conn = get_db()
    conn.execute("""
        UPDATE feedback
        SET reply = ?, replied_at = datetime('now', '+8 hours'),
            reply_read = 0
        WHERE id = ?
    """, (reply, fid))
    conn.commit()
    conn.close()

    flash("已回复", "success")
    return redirect(url_for("feedback_list"))

# ============================================================
# 后台：评论管理
# ============================================================

@app.route("/admin/reviews")
def admin_reviews():
    if not is_admin():
        return redirect(url_for("login"))

    dish_id = request.args.get("dish_id", "")

    conn = get_db()

    all_dishes = conn.execute("""
        SELECT d.id, d.name,
               s.name AS stall_name,
               c.name AS canteen_name,
               (SELECT COUNT(*) FROM reviews r WHERE r.dish_id = d.id) AS review_count
        FROM dishes d
        JOIN stalls s   ON s.id = d.stall_id
        JOIN canteens c ON c.id = s.canteen_id
        ORDER BY c.sort_order, c.id, s.sort_order, s.id, d.id
    """).fetchall()

    current_dish = None
    if dish_id.isdigit():
        current_dish = conn.execute("""
            SELECT d.id, d.name,
                   s.name AS stall_name,
                   c.name AS canteen_name
            FROM dishes d
            JOIN stalls s   ON s.id = d.stall_id
            JOIN canteens c ON c.id = s.canteen_id
            WHERE d.id = ?
        """, (int(dish_id),)).fetchone()

    if current_dish:
        reviews = conn.execute("""
            SELECT r.id, r.author, r.rating, r.content, r.photo, r.created_at,
                   d.id AS dish_id, d.name AS dish_name,
                   s.name AS stall_name,
                   c.name AS canteen_name,
                   (SELECT COUNT(*) FROM review_likes rl
                    WHERE rl.review_id = r.id) AS like_count
            FROM reviews r
            JOIN dishes d   ON d.id = r.dish_id
            JOIN stalls s   ON s.id = d.stall_id
            JOIN canteens c ON c.id = s.canteen_id
            WHERE r.dish_id = ?
            ORDER BY r.id DESC
        """, (current_dish["id"],)).fetchall()
    else:
        reviews = conn.execute("""
            SELECT r.id, r.author, r.rating, r.content, r.photo, r.created_at,
                   d.id AS dish_id, d.name AS dish_name,
                   s.name AS stall_name,
                   c.name AS canteen_name,
                   (SELECT COUNT(*) FROM review_likes rl
                    WHERE rl.review_id = r.id) AS like_count
            FROM reviews r
            JOIN dishes d   ON d.id = r.dish_id
            JOIN stalls s   ON s.id = d.stall_id
            JOIN canteens c ON c.id = s.canteen_id
            ORDER BY r.id DESC
            LIMIT 200
        """).fetchall()

    conn.close()

    return render_template(
        "admin_reviews.html",
        all_dishes=all_dishes,
        current_dish=current_dish,
        reviews=reviews,
        dish_id=dish_id,
    )


@app.route("/review/<int:review_id>/delete", methods=["POST"])
def review_delete(review_id):
    if not is_admin():
        return redirect(url_for("login"))

    conn = get_db()
    conn.execute("DELETE FROM review_likes WHERE review_id = ?", (review_id,))
    conn.execute("DELETE FROM reviews WHERE id = ?", (review_id,))
    conn.commit()
    conn.close()

    back = request.form.get("back", "")
    if back:
        return redirect(back)
    return redirect(url_for("admin_reviews"))


# ============================================================
# 后台：IP 黑名单
# ============================================================

@app.route("/admin/blacklist", methods=["GET", "POST"])
def admin_blacklist():
    if not is_admin():
        return redirect(url_for("login"))

    conn = get_db()

    if request.method == "POST":
        ip     = request.form.get("ip", "").strip()
        reason = request.form.get("reason", "").strip()
        if ip:
            try:
                conn.execute(
                    "INSERT INTO ip_blacklist (ip, reason) VALUES (?, ?)",
                    (ip, reason or None),
                )
                conn.commit()
            except sqlite3.IntegrityError:
                pass

    items = conn.execute(
        "SELECT * FROM ip_blacklist ORDER BY id DESC"
    ).fetchall()
    conn.close()

    return render_template("admin_blacklist.html", items=items)


@app.route("/admin/blacklist/<int:bid>/delete", methods=["POST"])
def admin_blacklist_delete(bid):
    if not is_admin():
        return redirect(url_for("login"))

    conn = get_db()
    conn.execute("DELETE FROM ip_blacklist WHERE id = ?", (bid,))
    conn.commit()
    conn.close()
    return redirect(url_for("admin_blacklist"))


@app.route("/admin/blacklist/add", methods=["POST"])
def admin_blacklist_add_from_feedback():
    if not is_admin():
        return redirect(url_for("login"))

    ip     = request.form.get("ip", "").strip()
    reason = request.form.get("reason", "从反馈列表拉黑").strip()

    if ip:
        conn = get_db()
        try:
            conn.execute(
                "INSERT INTO ip_blacklist (ip, reason) VALUES (?, ?)",
                (ip, reason or None),
            )
            conn.commit()
        except sqlite3.IntegrityError:
            pass
        conn.close()

    return redirect(url_for("feedback_list"))


# ============================================================
# 后台：公告管理
# ============================================================

@app.route("/admin/announcements", methods=["GET", "POST"])
def admin_announcements():
    if not is_admin():
        return redirect(url_for("login"))

    conn = get_db()

    if request.method == "POST":
        title      = request.form.get("title", "").strip()
        content    = request.form.get("content", "").strip()
        level      = request.form.get("level", "info")
        is_pinned  = 1 if request.form.get("is_pinned") == "1" else 0
        expires_at = request.form.get("expires_at", "").strip()

        if level not in ("info", "warning", "danger"):
            level = "info"

        if expires_at:
            expires_at = expires_at.replace("T", " ")
            if len(expires_at) == 16:
                expires_at += ":00"
        else:
            expires_at = None

        if title:
            conn.execute(
                "INSERT INTO announcements "
                "(title, content, level, is_pinned, expires_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (title, content or None, level, is_pinned, expires_at),
            )
            conn.commit()

    items = conn.execute("""
        SELECT * FROM announcements
        ORDER BY is_pinned DESC, id DESC
    """).fetchall()
    conn.close()

    return render_template("admin_announcements.html", items=items)


@app.route("/admin/announcements/<int:aid>/delete", methods=["POST"])
def admin_announcements_delete(aid):
    if not is_admin():
        return redirect(url_for("login"))

    conn = get_db()
    conn.execute("DELETE FROM announcements WHERE id = ?", (aid,))
    conn.commit()
    conn.close()
    return redirect(url_for("admin_announcements"))

@app.route("/admin/announcements/upload-image", methods=["POST"])
def admin_announcements_upload_image():
    """公告编辑器里的插图上传接口，返回 {"ok": true, "url": "..."} """
    if not is_admin():
        return jsonify({"ok": False, "msg": "未登录"}), 403

    file = request.files.get("image")
    if not file or not file.filename:
        return jsonify({"ok": False, "msg": "没有选择文件"}), 400
    if not is_allowed(file.filename):
        return jsonify({"ok": False, "msg": "只支持 jpg / png / gif / webp"}), 400

    # 中文文件名会被 secure_filename 清空，兜底成 "image"
    safe = secure_filename(file.filename) or "image"
    filename = f"{int(time.time())}_{secrets.token_hex(4)}_{safe}"
    file.save(os.path.join(ANNOUNCE_IMG_DIR, filename))

    return jsonify({
        "ok": True,
        "url": f"/static/announcement_images/{filename}",
    })

@app.route("/announcements/<int:aid>/read", methods=["POST"])
def announcement_mark_read(aid):
    """弹窗读完时调这个接口，标记为已读"""
    vid = g.visitor_id
    if not vid:
        return jsonify({"ok": False}), 400

    conn = get_db()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO announcement_reads "
            "(visitor_id, announcement_id) VALUES (?, ?)",
            (vid, aid),
        )
        conn.commit()
    except Exception:
        pass
    conn.close()
    return jsonify({"ok": True})

# ============================================================
# 菜单照片
# ============================================================

@app.route("/menu_upload", methods=["GET", "POST"])
def menu_upload():
    if not is_admin():
        return redirect(url_for("login"))

    error = None
    success = False

    if request.method == "POST":
        meal = request.form.get("meal", "lunch")
        note = request.form.get("note", "").strip()
        file = request.files.get("photo")

        if meal not in MEALS:
            error = "餐次不合法"
        elif not file or not file.filename:
            error = "请选择一张照片"
        elif not is_allowed(file.filename):
            error = "只允许 jpg / png / gif / webp 格式"
        else:
            safe = secure_filename(file.filename)
            filename = f"{int(time.time())}_{safe}"
            file.save(os.path.join(MENU_PHOTO_DIR, filename))

            conn = get_db()
            conn.execute(
                "INSERT INTO menu_photos (filename, meal, note) VALUES (?, ?, ?)",
                (filename, meal, note or None),
            )
            conn.commit()
            conn.close()
            success = True

    return render_template(
        "menu_upload.html",
        meals=MEALS,
        meal_label=MEAL_LABEL,
        error=error,
        success=success,
    )


@app.route("/menu_photos")
def menu_photos():
    if not is_admin():
        return redirect(url_for("login"))

    conn = get_db()
    photos = conn.execute(
        "SELECT * FROM menu_photos ORDER BY id DESC"
    ).fetchall()
    conn.close()
    return render_template(
        "menu_photos.html",
        photos=photos,
        meal_label=MEAL_LABEL,
    )


@app.route("/menu_photos/<int:pid>/delete", methods=["POST"])
def menu_photos_delete(pid):
    if not is_admin():
        return redirect(url_for("login"))

    conn = get_db()
    row = conn.execute(
        "SELECT filename FROM menu_photos WHERE id = ?", (pid,)
    ).fetchone()
    if row:
        path = os.path.join(MENU_PHOTO_DIR, row["filename"])
        if os.path.exists(path):
            os.remove(path)
        conn.execute("DELETE FROM menu_photos WHERE id = ?", (pid,))
        conn.commit()
    conn.close()
    return redirect(url_for("menu_photos"))

@app.route("/menu_photos/<int:pid>/ocr")
def menu_photos_ocr(pid):
    """对已上传的菜单照片做 OCR 识别"""
    if not is_admin():
        return redirect(url_for("login"))

    conn = get_db()
    photo = conn.execute(
        "SELECT * FROM menu_photos WHERE id = ?", (pid,)
    ).fetchone()

    all_stalls = conn.execute("""
        SELECT s.id, s.name, c.name AS canteen_name
        FROM stalls s
        JOIN canteens c ON c.id = s.canteen_id
        ORDER BY c.sort_order, c.id, s.sort_order, s.id
    """).fetchall()
    conn.close()

    if not photo:
        return "照片不存在", 404

    image_path = os.path.join(MENU_PHOTO_DIR, photo["filename"])

    try:
        from ocr_helper import ocr_image
    except ImportError as e:
        return f"导入 ocr_helper 失败：{e}"

    ok, result = ocr_image(image_path)

    # 把 OCR 结果拆成 [(菜名, 价格)]
    # 一行可能拆出多个菜（两栏菜单）
    parsed = []
    if ok:
        for line in result:
            items = parse_menu_line(line)
            for name, price in items:
                parsed.append({"name": name, "price": price})

    return render_template(
        "menu_photos_ocr.html",
        photo=photo,
        ok=ok,
        result=result,
        parsed=parsed,
        all_stalls=all_stalls,
        meal_label=MEAL_LABEL,
    )

@app.route("/menu_photos/<int:pid>/ocr/save", methods=["POST"])
def menu_photos_ocr_save(pid):
    """接收编辑后的菜名/价格，批量入库"""
    if not is_admin():
        return redirect(url_for("login"))

    stall_id = request.form.get("stall_id", "")
    if not stall_id.isdigit():
        flash("请选择入库窗口", "error")
        return redirect(url_for("menu_photos_ocr", pid=pid))

    conn = get_db()
    exists = conn.execute(
        "SELECT id FROM stalls WHERE id = ?", (int(stall_id),)
    ).fetchone()
    if not exists:
        conn.close()
        flash("窗口不存在", "error")
        return redirect(url_for("menu_photos_ocr", pid=pid))

    names  = request.form.getlist("name")
    prices = request.form.getlist("price")

    ok_count   = 0
    fail_count = 0

    for raw_name, raw_price in zip(names, prices):
        name      = (raw_name or "").strip()
        price_str = (raw_price or "").strip()

        if not name and not price_str:
            continue

        if not name or not price_str:
            fail_count += 1
            continue

        try:
            price_val = float(price_str)
        except ValueError:
            fail_count += 1
            continue

        if price_val <= 0:
            fail_count += 1
            continue

        conn.execute(
            "INSERT INTO dishes (stall_id, name, price, description, meal) "
            "VALUES (?, ?, ?, ?, ?)",
            (int(stall_id), name, price_val, "", "lunch"),
        )
        ok_count += 1

    conn.commit()
    conn.close()

    if ok_count:
        msg = f"✓ 成功导入 {ok_count} 道菜"
        if fail_count:
            msg += f"，{fail_count} 条格式不对已跳过"
        flash(msg, "success")
    else:
        flash("没有导入任何菜品（检查是否所有行都填了菜名和价格）", "error")

    return redirect(url_for("admin_dishes"))

# ============================================================
# 后台：用户管理
# ============================================================

@app.route("/admin/users")
def admin_users():
    if not is_admin():
        return redirect(url_for("login"))

    conn = get_db()

    users = conn.execute("""
        SELECT u.id, u.email, u.nickname, u.is_banned, u.is_staff, u.created_at,
               (SELECT COUNT(*) FROM reviews r
                WHERE r.visitor_id = 'u' || u.id) AS review_count,
               (SELECT COUNT(*) FROM posts p
                WHERE p.visitor_id = 'u' || u.id) AS post_count,
               (SELECT COUNT(*) FROM feedback f
                WHERE f.contact = u.email) AS feedback_count
        FROM users u
        ORDER BY u.id DESC
        LIMIT 500
    """).fetchall()
    conn.close()

    return render_template("admin_users.html", users=users)


@app.route("/admin/users/<int:uid>/toggle-ban", methods=["POST"])
def admin_users_toggle_ban(uid):
    if not is_admin():
        return redirect(url_for("login"))

    conn = get_db()
    user = conn.execute(
        "SELECT is_banned FROM users WHERE id = ?", (uid,)
    ).fetchone()
    if user:
        new_val = 0 if user["is_banned"] else 1
        conn.execute(
            "UPDATE users SET is_banned = ? WHERE id = ?",
            (new_val, uid)
        )
        conn.commit()
        flash(f"用户已{'禁言' if new_val else '解除禁言'}", "success")
    conn.close()
    return redirect(url_for("admin_users"))

@app.route("/admin/users/<int:uid>/toggle-staff", methods=["POST"])
def admin_users_toggle_staff(uid):
    if not is_admin():
        return redirect(url_for("login"))

    conn = get_db()
    user = conn.execute(
        "SELECT is_staff FROM users WHERE id = ?", (uid,)
    ).fetchone()
    if user:
        new_val = 0 if user["is_staff"] else 1
        conn.execute(
            "UPDATE users SET is_staff = ? WHERE id = ?",
            (new_val, uid)
        )
        conn.commit()
        flash(f"已{'设为管理员' if new_val else '取消管理员'}", "success")
    conn.close()
    return redirect(url_for("admin_users"))

@app.route("/admin/users/<int:uid>/delete", methods=["POST"])
def admin_users_delete(uid):
    if not is_admin():
        return redirect(url_for("login"))

    conn = get_db()

    # 用 visitor_id = "u5" 这种格式找到这个用户发过的内容
    vid = f"u{uid}"

    # 删他的评价 + 点赞
    review_ids = [r["id"] for r in conn.execute(
        "SELECT id FROM reviews WHERE visitor_id = ?", (vid,)
    ).fetchall()]
    for rid in review_ids:
        conn.execute("DELETE FROM review_likes WHERE review_id = ?", (rid,))
    conn.execute("DELETE FROM reviews WHERE visitor_id = ?", (vid,))

    # 删他的拼饭 + 回复
    post_ids = [p["id"] for p in conn.execute(
        "SELECT id FROM posts WHERE visitor_id = ?", (vid,)
    ).fetchall()]
    for pid in post_ids:
        conn.execute("DELETE FROM post_replies WHERE post_id = ?", (pid,))
    conn.execute("DELETE FROM posts WHERE visitor_id = ?", (vid,))
    conn.execute("DELETE FROM post_replies WHERE visitor_id = ?", (vid,))

    # 删收藏 + 评价点赞
    conn.execute("DELETE FROM favorites WHERE visitor_id = ?", (vid,))
    conn.execute("DELETE FROM review_likes WHERE visitor_id = ?", (vid,))

    # 删账号
    conn.execute("DELETE FROM users WHERE id = ?", (uid,))
    conn.commit()
    conn.close()

    flash("用户及其所有内容已删除", "success")
    return redirect(url_for("admin_users"))

# ============================================================
# 数据统计
# ============================================================

@app.route("/admin/stats")
def admin_stats():
    if not is_admin():
        return redirect(url_for("login"))

    conn = get_db()

    dish_count     = conn.execute("SELECT COUNT(*) AS c FROM dishes").fetchone()["c"]
    stall_count    = conn.execute("SELECT COUNT(*) AS c FROM stalls").fetchone()["c"]
    review_count   = conn.execute("SELECT COUNT(*) AS c FROM reviews").fetchone()["c"]
    favorite_count = conn.execute("SELECT COUNT(*) AS c FROM favorites").fetchone()["c"]
    feedback_new   = conn.execute("SELECT COUNT(*) AS c FROM feedback WHERE status='new'").fetchone()["c"]
    feedback_total = conn.execute("SELECT COUNT(*) AS c FROM feedback").fetchone()["c"]

    base_sql = """
        SELECT d.id, d.name, d.meal,
               s.name AS stall_name,
               c.name AS canteen_name,
               ROUND(AVG(r.rating), 1) AS avg_rating,
               COUNT(r.id)             AS review_count
        FROM dishes d
        JOIN stalls s   ON s.id = d.stall_id
        JOIN canteens c ON c.id = s.canteen_id
        LEFT JOIN reviews r ON r.dish_id = d.id
        GROUP BY d.id
        HAVING review_count > 0
    """

    top_rated = conn.execute(
        base_sql + " ORDER BY avg_rating DESC, review_count DESC LIMIT 5"
    ).fetchall()
    worst_rated = conn.execute(
        base_sql + " ORDER BY avg_rating ASC, review_count DESC LIMIT 5"
    ).fetchall()
    hottest = conn.execute(
        base_sql + " ORDER BY review_count DESC, avg_rating DESC LIMIT 5"
    ).fetchall()

    fav_top = conn.execute("""
        SELECT d.id, d.name,
               s.name AS stall_name,
               c.name AS canteen_name,
               COUNT(f.id) AS fav_count
        FROM dishes d
        JOIN stalls s   ON s.id = d.stall_id
        JOIN canteens c ON c.id = s.canteen_id
        JOIN favorites f ON f.dish_id = d.id
        GROUP BY d.id
        ORDER BY fav_count DESC
        LIMIT 5
    """).fetchall()

    # ============== 访问量统计 ==============
    today_views    = conn.execute("""
        SELECT COUNT(*) AS c FROM page_views
        WHERE date(created_at) = date('now', '+8 hours')
    """).fetchone()["c"]

    today_visitors = conn.execute("""
        SELECT COUNT(DISTINCT visitor_id) AS c FROM page_views
        WHERE date(created_at) = date('now', '+8 hours')
    """).fetchone()["c"]

    total_views    = conn.execute(
        "SELECT COUNT(*) AS c FROM page_views"
    ).fetchone()["c"]

    total_visitors = conn.execute(
        "SELECT COUNT(DISTINCT visitor_id) AS c FROM page_views"
    ).fetchone()["c"]

    trend = conn.execute("""
        SELECT date(created_at) AS day,
               COUNT(*) AS views,
               COUNT(DISTINCT visitor_id) AS visitors
        FROM page_views
        WHERE created_at >= datetime('now', '-7 days', '+8 hours')
        GROUP BY date(created_at)
        ORDER BY day DESC
    """).fetchall()

    conn.close()

    return render_template(
        "admin_stats.html",
        dish_count=dish_count,
        stall_count=stall_count,
        review_count=review_count,
        favorite_count=favorite_count,
        feedback_new=feedback_new,
        feedback_total=feedback_total,
        top_rated=top_rated,
        worst_rated=worst_rated,
        hottest=hottest,
        fav_top=fav_top,
        meal_label=MEAL_LABEL,
        today_views=today_views,
        today_visitors=today_visitors,
        total_views=total_views,
        total_visitors=total_visitors,
        trend=trend,
    )


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)  # 部署时不需要这行
    pass