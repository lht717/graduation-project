import asyncio
import json
import queue
import hashlib
import base64
import secrets
import threading
from typing import Dict, List
from pathlib import Path
from datetime import datetime, timezone
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import uvicorn
from fastapi.middleware.cors import CORSMiddleware


BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
MODELS_DIR = BASE_DIR / "models"
MODELS_DIR.mkdir(exist_ok=True)

app = FastAPI()


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)



app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ================= CARLA 仿真模块（已拆分，可选加载） =================
# CARLA / ONNX / 相机 / 推理 / 模型 API / 驾驶 WebSocket 都在 carla_runtime.py。
# 即使没有启动 CARLA 服务（或环境缺少 carla / numpy / cv2 / onnxruntime），
# 本文件中的用户、认证、私信、实验数据等业务接口仍可正常启动与编辑。
import os

if os.environ.get("FUSIONLAB_DISABLE_CARLA", "").lower() in ("1", "true", "yes", "on"):
    print("[CARLA] 已通过 FUSIONLAB_DISABLE_CARLA 禁用，仅运行业务后端（用户/私信/实验数据）")
else:
    try:
        from carla_runtime import router as carla_router
        app.include_router(carla_router)
        print("[CARLA] 仿真模块已加载（/api/models、/ws）")
    except Exception as exc:
        print(f"[CARLA] 仿真模块未加载（业务后端不受影响）: {exc}")

# ================= 用户与私信存储（MySQL） =================
import pymysql

data_lock = threading.Lock()

DB_CONFIG = {
    "host": "127.0.0.1",
    "port": 3306,
    "user": "root",
    "password": os.environ.get("FUSIONLAB_DB_PASSWORD", "123456"),
    "database": "fusionlab",
    "charset": "utf8mb4",
}


def _now_iso():
    return datetime.now(timezone.utc).astimezone().isoformat()


def _hash_password(password: str) -> str:
    # 演示用加盐哈希；生产环境建议换用 bcrypt/argon2
    salt = "fusionlab"
    return hashlib.sha256((salt + password).encode("utf-8")).hexdigest()


def _safe_username(username: str) -> str:
    name = (username or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="账号不能为空")
    return name


def _db_conn():
    return pymysql.connect(**DB_CONFIG, cursorclass=pymysql.cursors.DictCursor, autocommit=False)


def _ensure_user_status_column() -> None:
    conn = _db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SHOW COLUMNS FROM users LIKE 'is_active'")
            if not cur.fetchone():
                cur.execute(
                    "ALTER TABLE users ADD COLUMN is_active TINYINT(1) NOT NULL DEFAULT 1"
                )
        conn.commit()
    finally:
        conn.close()


_ensure_user_status_column()


def _public_user(user: dict) -> dict:
    is_admin = user.get("role") == "admin"
    return {
        "username": user["username"],
        "account_id": user.get("account_id", user["username"]),
        "display_name": user.get("display_name", user["username"]),
        "role": "admin" if is_admin else "user",
        "role_name": user.get("role_name", "管理员" if is_admin else "普通用户"),
        "is_active": bool(user.get("is_active", True)),
        "registered_at": user.get("registered_at", ""),
        "avatar": user.get("avatar", ""),
        "class_name": user.get("class_name", ""),
    }


def load_users() -> list:
    conn = _db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT username, account_id, display_name, role, role_name, is_active, password_hash, registered_at, avatar, class_name FROM users")
            return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def save_users(users: list) -> None:
    conn = _db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM users")
            for u in users:
                cur.execute(
                    "INSERT INTO users (username, account_id, display_name, role, role_name, is_active, password_hash, registered_at, avatar, class_name) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (u["username"], u.get("account_id", u["username"]), u["display_name"],
                     u.get("role", "user"), u.get("role_name", "普通用户"), 1 if u.get("is_active", True) else 0,
                     u["password_hash"], u.get("registered_at", ""), u.get("avatar", ""),
                     u.get("class_name", "")),
                )
        conn.commit()
    finally:
        conn.close()


def load_messages() -> list:
    conn = _db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id, subject, sender, sender_username, recipient, recipient_username, content, created_at FROM messages")
            return [
                {
                    "id": f"msg-{r['id']}",
                    "subject": r["subject"],
                    "sender": r["sender"],
                    "sender_username": r["sender_username"],
                    "recipient": r["recipient"],
                    "recipient_username": r["recipient_username"],
                    "content": r["content"],
                    "created_at": r["created_at"],
                }
                for r in cur.fetchall()
            ]
    finally:
        conn.close()


def save_messages(messages: list) -> None:
    conn = _db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM messages")
            for m in messages:
                mid = int(str(m["id"]).split("-")[-1])
                cur.execute(
                    "INSERT INTO messages (id, subject, sender, sender_username, recipient, recipient_username, content, created_at) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                    (mid, m["subject"], m["sender"], m["sender_username"], m["recipient"],
                     m["recipient_username"], m["content"], m["created_at"]),
                )
        conn.commit()
    finally:
        conn.close()


# 启动时从 MySQL 加载；首次运行自动预置管理员和演示用户
users = load_users()
if not users:
    users = [
        {
            "username": "admin", "account_id": "20240000",
            "display_name": "系统管理员", "role": "admin", "role_name": "管理员",
            "is_active": True,
            "password_hash": _hash_password("admin123"),
            "registered_at": "2024-06-01T10:00:00+08:00",
            "avatar": "/static/avatar_default.png",
            "class_name": "",
        },
        {
            "username": "demo", "account_id": "20240001",
            "display_name": "演示用户", "role": "user", "role_name": "普通用户",
            "is_active": True,
            "password_hash": _hash_password("fusionlab"),
            "registered_at": "2025-01-15T08:30:00+08:00",
            "avatar": "/static/avatar_default.png",
            "class_name": "计算机2401班",
        },
    ]
    save_users(users)

messages = load_messages()
next_message_id = max([int(m["id"].split("-")[-1]) for m in messages], default=0) + 1

# 登录会话：token -> username（重启后需重新登录）
# 注意：命名用 auth_sessions，避免与上方 CARLA 驾驶会话 sessions(Dict[int, ClientSession]) 冲突
auth_sessions: Dict[str, str] = {}


def _current_user(request: Request) -> dict:
    auth = request.headers.get("Authorization", "")
    token = auth[7:].strip() if auth.startswith("Bearer ") else ""
    username = auth_sessions.get(token)
    if not username:
        raise HTTPException(status_code=401, detail="请先登录")
    for user in users:
        if user["username"] == username:
            if not user.get("is_active", True):
                raise HTTPException(status_code=403, detail="账号已停用")
            return user
    raise HTTPException(status_code=401, detail="会话已失效，请重新登录")


def _admin_only(request: Request) -> dict:
    user = _current_user(request)
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user


# ---------- 认证 API ----------
@app.post("/api/auth/login")
async def login(request: Request):
    body = await request.json()
    username = _safe_username(body.get("username", ""))
    password = str(body.get("password", ""))
    if not password:
        raise HTTPException(status_code=400, detail="请输入账号和密码")
    user = next((u for u in users if u["username"] == username), None)
    if not user or user["password_hash"] != _hash_password(password):
        raise HTTPException(status_code=401, detail="账号或密码错误")
    if not user.get("is_active", True):
        raise HTTPException(status_code=403, detail="账号已停用，请联系管理员")
    token = secrets.token_hex(16)
    with data_lock:
        auth_sessions[token] = user["username"]
    return {"authenticated": True, "user": _public_user(user), "token": token}


@app.get("/api/auth/me")
async def auth_me(request: Request):
    try:
        user = _current_user(request)
    except HTTPException:
        return {"authenticated": False, "user": None}
    return {"authenticated": True, "user": _public_user(user)}


@app.post("/api/auth/logout")
async def logout(request: Request):
    auth = request.headers.get("Authorization", "")
    token = auth[7:].strip() if auth.startswith("Bearer ") else ""
    with data_lock:
        auth_sessions.pop(token, None)
    return {"success": True}


# ---------- 个人资料 API ----------
@app.post("/api/users/me/display-name")
async def update_display_name(request: Request):
    user = _current_user(request)
    body = await request.json()
    display_name = str(body.get("display_name", "")).strip()
    if not display_name:
        raise HTTPException(status_code=400, detail="自定义名称不能为空")
    if len(display_name) > 40:
        raise HTTPException(status_code=400, detail="自定义名称不能超过 40 字")
    with data_lock:
        user["display_name"] = display_name
        save_users(users)
    return {"user": _public_user(user), "message": "自定义名称修改成功"}


@app.post("/api/users/me/avatar")
async def update_avatar(request: Request):
    """更新当前用户头像。支持 data:image/... base64 图片（保存为 static/avatars/<username>.png），或 /static/、http(s) 图片地址。"""
    user = _current_user(request)
    body = await request.json()
    data = str(body.get("avatar", "") or body.get("image", "")).strip()
    if not data:
        raise HTTPException(status_code=400, detail="请提供头像图片")
    if data.startswith("data:image/"):
        try:
            _header, b64 = data.split(",", 1)
            raw = base64.b64decode(b64)
        except Exception:
            raise HTTPException(status_code=400, detail="图片数据无效")
        if len(raw) > 2 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="图片不能超过 2MB")
        avatar_dir = STATIC_DIR / "avatars"
        avatar_dir.mkdir(exist_ok=True)
        filename = f"{user['username']}.png"
        (avatar_dir / filename).write_bytes(raw)
        url = f"/static/avatars/{filename}"
    else:
        url = data
        if not (url.startswith("/static/") or url.startswith("http://") or url.startswith("https://")):
            raise HTTPException(status_code=400, detail="头像地址不合法")
    if len(url) > 255:
        raise HTTPException(status_code=400, detail="头像地址过长")
    with data_lock:
        user["avatar"] = url
        save_users(users)
    return {"user": _public_user(user), "message": "头像已更新"}


@app.post("/api/users/me/password")
async def change_password(request: Request):
    user = _current_user(request)
    body = await request.json()
    current_password = str(body.get("current_password", ""))
    new_password = str(body.get("new_password", ""))
    if not current_password or not new_password:
        raise HTTPException(status_code=400, detail="请填写当前密码和新密码")
    if len(new_password) < 8:
        raise HTTPException(status_code=400, detail="新密码至少需要 8 位")
    if user["password_hash"] != _hash_password(current_password):
        raise HTTPException(status_code=400, detail="当前密码不正确")
    with data_lock:
        user["password_hash"] = _hash_password(new_password)
        save_users(users)
    return {"message": "密码修改成功"}


# ---------- 管理员用户管理 API ----------
@app.get("/api/admin/users")
async def admin_list_users(request: Request):
    _admin_only(request)
    with data_lock:
        return {"users": [_public_user(u) for u in users]}


@app.post("/api/admin/users")
async def admin_create_user(request: Request):
    _admin_only(request)
    body = await request.json()
    username = _safe_username(body.get("username", ""))
    display_name = str(body.get("display_name", "")).strip()
    password = str(body.get("password", ""))
    class_name = str(body.get("class_name", "") or "").strip()[:64]
    if not username.isdigit():
        raise HTTPException(status_code=400, detail="账号（学号）必须为数字")
    if not display_name:
        raise HTTPException(status_code=400, detail="请输入自定义名称")
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="初始密码至少需要 8 位")
    with data_lock:
        if any(u["username"] == username for u in users):
            raise HTTPException(status_code=409, detail="该账号已存在")
        new_user = {
            "username": username,
            "account_id": username,
            "display_name": display_name,
            "role": "user",
            "role_name": "普通用户",
            "is_active": True,
            "password_hash": _hash_password(password),
            "registered_at": _now_iso(),
            "avatar": "/static/avatar_default.png",
            "class_name": class_name,
        }
        users.append(new_user)
        save_users(users)
    return {"user": _public_user(new_user), "message": "用户创建成功"}


@app.post("/api/admin/users/password/reset")
async def admin_reset_password(request: Request):
    _admin_only(request)
    body = await request.json()
    username = _safe_username(body.get("username", ""))
    return {"message": f"已提交 {username} 的密码重置请求"}


@app.put("/api/admin/users/{username}/password")
async def admin_set_password(username: str, request: Request):
    _admin_only(request)
    body = await request.json()
    new_password = str(body.get("new_password", ""))
    if len(new_password) < 8:
        raise HTTPException(status_code=400, detail="新密码至少需要 8 位")
    with data_lock:
        for user in users:
            if user["username"] == username:
                user["password_hash"] = _hash_password(new_password)
                save_users(users)
                return {"message": "用户密码修改成功"}
    raise HTTPException(status_code=404, detail="用户不存在")


@app.patch("/api/admin/users/{username}")
async def admin_update_user(username: str, request: Request):
    _admin_only(request)
    body = await request.json()
    display_name = str(body.get("display_name", "") or "").strip()
    class_given = "class_name" in body
    class_name = str(body.get("class_name", "") or "").strip()[:64]
    if not display_name and not class_given:
        raise HTTPException(status_code=400, detail="请至少提供自定义名称或班级")
    if len(display_name) > 40:
        raise HTTPException(status_code=400, detail="自定义名称不能超过 40 个字")
    with data_lock:
        for user in users:
            if user["username"] == username:
                if display_name:
                    user["display_name"] = display_name
                if class_given:
                    user["class_name"] = class_name
                save_users(users)
                return {"user": _public_user(user), "message": "用户信息已更新"}
    raise HTTPException(status_code=404, detail="用户不存在")


@app.put("/api/admin/users/{username}/role")
async def admin_promote_user(username: str, request: Request):
    _admin_only(request)
    with data_lock:
        user = next((item for item in users if item["username"] == username), None)
        if not user:
            raise HTTPException(status_code=404, detail="用户不存在")
        if user["role"] == "admin":
            raise HTTPException(status_code=400, detail="该账号已经是管理员")
        previous_role = user["role"]
        previous_role_name = user.get("role_name")
        user["role"] = "admin"
        user["role_name"] = "管理员"
        try:
            save_users(users)
        except Exception:
            user["role"] = previous_role
            user["role_name"] = previous_role_name
            raise
        return {"user": _public_user(user), "message": "用户已提升为管理员"}


@app.put("/api/admin/users/{username}/status")
async def admin_set_user_status(username: str, request: Request):
    acting_user = _admin_only(request)
    body = await request.json()
    is_active = body.get("is_active")
    if not isinstance(is_active, bool):
        raise HTTPException(status_code=400, detail="账号状态必须为布尔值")
    with data_lock:
        target = next((item for item in users if item["username"] == username), None)
        if not target:
            raise HTTPException(status_code=404, detail="用户不存在")
        if target["role"] != "admin":
            raise HTTPException(status_code=400, detail="该操作仅适用于管理员账号")
        if not is_active:
            if acting_user["username"] == username:
                raise HTTPException(status_code=400, detail="不能停用当前登录的管理员账号")
            active_admins = [
                item for item in users
                if item["role"] == "admin" and item.get("is_active", True)
            ]
            if len(active_admins) <= 1:
                raise HTTPException(status_code=400, detail="不能停用最后一位启用中的管理员")
        previous_status = target.get("is_active", True)
        target["is_active"] = is_active
        try:
            save_users(users)
        except Exception:
            target["is_active"] = previous_status
            raise
        return {
            "user": _public_user(target),
            "message": "管理员账号已启用" if is_active else "管理员账号已停用",
        }


@app.delete("/api/admin/users/{username}")
async def admin_delete_user(username: str, request: Request):
    _admin_only(request)
    with data_lock:
        for i, user in enumerate(users):
            if user["username"] == username:
                if user["role"] == "admin":
                    raise HTTPException(status_code=400, detail="不能删除管理员账号")
                users.pop(i)
                save_users(users)
                # 同步清理该用户相关的私信
                messages[:] = [m for m in messages
                                if m["sender_username"] != username and m["recipient_username"] != username]
                save_messages(messages)
                return {"success": True, "message": "用户已删除"}
    raise HTTPException(status_code=404, detail="用户不存在")


# ---------- 班级管理 API（管理员增删改查） ----------
CLASS_COLUMNS = ("name", "grade", "student_count", "sort_order", "created_at", "remark")


def _ensure_class_table() -> None:
    conn = _db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """CREATE TABLE IF NOT EXISTS classes (
                    id BIGINT NOT NULL AUTO_INCREMENT,
                    name VARCHAR(128) NOT NULL,
                    grade VARCHAR(32) NOT NULL,
                    student_count INT NOT NULL DEFAULT 0,
                    sort_order INT NOT NULL DEFAULT 0,
                    created_at VARCHAR(64) NOT NULL DEFAULT '',
                    remark VARCHAR(500) NOT NULL DEFAULT '',
                    PRIMARY KEY (id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"""
            )
        conn.commit()
    finally:
        conn.close()


_ensure_class_table()


def _sync_class_student_counts(cur) -> None:
    """把班级人数同步为学生表中的真实人数（管理员账号不计入）。

    班级人数属于派生数据，统一以 users 表为准，避免新增/删除/导入学生后
    班级管理页仍显示手工填写的旧值。
    """
    cur.execute(
        "UPDATE classes c SET c.student_count = ("
        "  SELECT COUNT(*) FROM users u "
        "  WHERE u.class_name = c.name AND COALESCE(u.role, '') <> 'admin'"
        ")"
    )


def _ensure_classes_from_users(cur) -> None:
    """把学生表中出现、但 classes 表还没有的班级自动补建。

    覆盖所有创建/编辑学生的入口（页面手动新增、批量导入、直接调用 API）：
    只要读取班级列表，缺失班级就会补齐，人数随后由
    _sync_class_student_counts 统一统计。年级默认「未设置」，可在班级管理页修改。
    """
    cur.execute(
        "SELECT DISTINCT u.class_name FROM users u "
        "WHERE COALESCE(u.class_name, '') <> '' AND COALESCE(u.role, '') <> 'admin' "
        "AND NOT EXISTS (SELECT 1 FROM classes c WHERE c.name = u.class_name)"
    )
    missing = [
        row["class_name"].strip()
        for row in cur.fetchall()
        if (row["class_name"] or "").strip()
    ]
    if not missing:
        return
    cur.execute("SELECT COALESCE(MAX(sort_order), 0) AS max_sort FROM classes")
    next_sort = int(list(cur.fetchone().values())[0] or 0)
    for name in missing:
        next_sort += 1
        cur.execute(
            "INSERT INTO classes (name, grade, student_count, sort_order, created_at, remark) "
            "VALUES (%s, %s, 0, %s, %s, %s)",
            (name, "未设置", next_sort, _now_iso(), "创建学生时自动补建"),
        )


def _class_public(row: dict) -> dict:
    return {
        "id": int(row["id"]),
        "name": row["name"] or "",
        "grade": row["grade"] or "",
        "student_count": int(row["student_count"] or 0),
        "sort_order": int(row["sort_order"] or 0),
        "created_at": row["created_at"] or "",
        "remark": row["remark"] or "",
    }


def _class_values(body: dict, base: dict = None) -> dict:
    source = dict(base or {})
    source.update(body or {})

    def nonnegative_int(key: str) -> int:
        try:
            value = int(source.get(key) or 0)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail=f"{key} 必须为整数")
        if value < 0:
            raise HTTPException(status_code=400, detail=f"{key} 不能小于 0")
        return value

    return {
        "name": str(source.get("name") or "").strip(),
        "grade": str(source.get("grade") or "").strip(),
        "student_count": nonnegative_int("student_count"),
        "sort_order": nonnegative_int("sort_order"),
        "created_at": str(source.get("created_at") or _now_iso()).strip(),
        "remark": str(source.get("remark") or "").strip(),
    }


def _class_by_id(cur, class_id: int) -> dict:
    cur.execute(
        f"SELECT {', '.join(CLASS_COLUMNS)}, id FROM classes WHERE id = %s",
        (class_id,),
    )
    return cur.fetchone()


@app.get("/api/admin/classes")
async def admin_list_classes(request: Request, keyword: str = "", grade: str = ""):
    _admin_only(request)
    clauses = []
    params = []
    if keyword.strip():
        clauses.append("name LIKE %s")
        params.append(f"%{keyword.strip()}%")
    if grade.strip():
        clauses.append("grade LIKE %s")
        params.append(f"%{grade.strip()}%")
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    conn = _db_conn()
    try:
        with conn.cursor() as cur:
            _ensure_classes_from_users(cur)
            _sync_class_student_counts(cur)
            cur.execute(
                f"SELECT {', '.join(CLASS_COLUMNS)}, id FROM classes {where} ORDER BY sort_order ASC, id DESC",
                params,
            )
            classes = [_class_public(row) for row in cur.fetchall()]
        conn.commit()
        return {"classes": classes}
    finally:
        conn.close()


@app.post("/api/admin/classes")
async def admin_create_class(request: Request):
    _admin_only(request)
    values = _class_values(await request.json())
    if not values["name"] or not values["grade"]:
        raise HTTPException(status_code=400, detail="班级名称和年级不能为空")
    if len(values["name"]) > 128 or len(values["grade"]) > 32 or len(values["remark"]) > 500:
        raise HTTPException(status_code=400, detail="班级字段长度超出限制")
    conn = _db_conn()
    try:
        with conn.cursor() as cur:
            placeholders = ", ".join(["%s"] * len(CLASS_COLUMNS))
            cur.execute(
                f"INSERT INTO classes ({', '.join(CLASS_COLUMNS)}) VALUES ({placeholders})",
                tuple(values[column] for column in CLASS_COLUMNS),
            )
            class_id = cur.lastrowid
            _sync_class_student_counts(cur)
            row = _class_by_id(cur, class_id)
        conn.commit()
    finally:
        conn.close()
    return {"class": _class_public(row), "message": "班级已新增"}


@app.put("/api/admin/classes/{class_id}")
async def admin_update_class(class_id: int, request: Request):
    _admin_only(request)
    body = await request.json()
    message = "班级信息已更新"
    conn = _db_conn()
    try:
        # 改名要同时改 users 表和内存缓存；与用户相关接口共用 data_lock，
        # 避免 save_users() 用旧缓存把刚改好的所属班级覆盖回数据库。
        with data_lock:
            with conn.cursor() as cur:
                row = _class_by_id(cur, class_id)
                if not row:
                    raise HTTPException(status_code=404, detail="班级不存在")
                old_name = row["name"] or ""
                values = _class_values(body, _class_public(row))
                if not values["name"] or not values["grade"]:
                    raise HTTPException(status_code=400, detail="班级名称和年级不能为空")
                if len(values["name"]) > 128 or len(values["grade"]) > 32 or len(values["remark"]) > 500:
                    raise HTTPException(status_code=400, detail="班级字段长度超出限制")
                new_name = values["name"]
                renamed_count = 0
                if new_name != old_name:
                    cur.execute(
                        "SELECT id FROM classes WHERE name = %s AND id <> %s",
                        (new_name, class_id),
                    )
                    if cur.fetchone():
                        raise HTTPException(status_code=400, detail="班级名称已存在")
                assignments = ", ".join(f"{column} = %s" for column in CLASS_COLUMNS)
                cur.execute(
                    f"UPDATE classes SET {assignments} WHERE id = %s",
                    tuple(values[column] for column in CLASS_COLUMNS) + (class_id,),
                )
                if new_name != old_name:
                    renamed_count = cur.execute(
                        "UPDATE users SET class_name = %s WHERE class_name = %s",
                        (new_name, old_name),
                    )
                _sync_class_student_counts(cur)
                updated = _class_by_id(cur, class_id)
            conn.commit()
            if new_name != old_name:
                for user in users:
                    if (user.get("class_name") or "") == old_name:
                        user["class_name"] = new_name
                message = f"班级信息已更新，已同步 {renamed_count} 个账号的所属班级"
    finally:
        conn.close()
    return {"class": _class_public(updated), "message": message}


@app.delete("/api/admin/classes/{class_id}")
async def admin_delete_class(class_id: int, request: Request):
    _admin_only(request)
    conn = _db_conn()
    try:
        with conn.cursor() as cur:
            if not _class_by_id(cur, class_id):
                raise HTTPException(status_code=404, detail="班级不存在")
            cur.execute("DELETE FROM classes WHERE id = %s", (class_id,))
        conn.commit()
    finally:
        conn.close()
    return {"success": True, "message": "班级已删除"}


# ---------- 实验类型管理 API（管理员增删改查） ----------
EXPERIMENT_TYPE_COLUMNS = ("name", "sort_order", "created_at", "remark")

# 与「实验中心」页展示的三个实验保持一致，数据库为空时自动补齐
DEFAULT_EXPERIMENT_TYPES = (
    ("智能汽车视觉感知实验", 1, "CARLA 城市道路 · UFLD 车道线检测 · YOLO 目标检测 · 自动驾驶状态监控"),
    ("仓储 AGV 实验", 2, "仓储物流 AGV 场景，后续场景适配阶段开放"),
    ("巡检机器人实验", 3, "巡检机器人场景，机器人仿真适配完成后开放"),
)


def _ensure_experiment_type_table() -> None:
    conn = _db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """CREATE TABLE IF NOT EXISTS experiment_types (
                    id BIGINT NOT NULL AUTO_INCREMENT,
                    name VARCHAR(128) NOT NULL,
                    sort_order INT NOT NULL DEFAULT 0,
                    created_at VARCHAR(64) NOT NULL DEFAULT '',
                    remark VARCHAR(500) NOT NULL DEFAULT '',
                    PRIMARY KEY (id),
                    UNIQUE KEY uk_experiment_type_name (name)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"""
            )
            cur.execute("SELECT COUNT(*) AS total FROM experiment_types")
            if int(cur.fetchone()["total"] or 0) == 0:
                cur.executemany(
                    "INSERT INTO experiment_types (name, sort_order, created_at, remark) "
                    "VALUES (%s, %s, %s, %s)",
                    [(name, order, _now_iso(), remark) for name, order, remark in DEFAULT_EXPERIMENT_TYPES],
                )
        conn.commit()
    finally:
        conn.close()


_ensure_experiment_type_table()


def _experiment_type_public(row: dict) -> dict:
    return {
        "id": int(row["id"]),
        "name": row["name"] or "",
        "sort_order": int(row["sort_order"] or 0),
        "created_at": row["created_at"] or "",
        "remark": row["remark"] or "",
    }


def _experiment_type_values(body: dict, base: dict = None) -> dict:
    source = dict(base or {})
    source.update(body or {})
    try:
        sort_order = int(source.get("sort_order") or 0)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="排序必须为整数")
    if sort_order < 0:
        raise HTTPException(status_code=400, detail="排序不能小于 0")
    return {
        "name": str(source.get("name") or "").strip(),
        "sort_order": sort_order,
        "created_at": str(source.get("created_at") or _now_iso()).strip(),
        "remark": str(source.get("remark") or "").strip(),
    }


def _experiment_type_by_id(cur, type_id: int) -> dict:
    cur.execute(
        f"SELECT {', '.join(EXPERIMENT_TYPE_COLUMNS)}, id FROM experiment_types WHERE id = %s",
        (type_id,),
    )
    return cur.fetchone()


def _validate_experiment_type(values: dict) -> None:
    if not values["name"]:
        raise HTTPException(status_code=400, detail="实验类型名称不能为空")
    if len(values["name"]) > 128:
        raise HTTPException(status_code=400, detail="实验类型名称不能超过 128 个字符")
    if len(values["remark"]) > 500:
        raise HTTPException(status_code=400, detail="备注不能超过 500 个字符")


def _assert_type_name_available(cur, name: str, exclude_id: int = 0) -> None:
    cur.execute(
        "SELECT id FROM experiment_types WHERE name = %s AND id <> %s",
        (name, exclude_id),
    )
    if cur.fetchone():
        raise HTTPException(status_code=400, detail=f"实验类型“{name}”已存在")


@app.get("/api/experiment-types")
async def list_experiment_types(request: Request):
    """实验中心页读取实验类型卡片：与「实验类型」管理页共用同一张表。"""
    _current_user(request)
    conn = _db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT {', '.join(EXPERIMENT_TYPE_COLUMNS)}, id FROM experiment_types "
                "ORDER BY sort_order ASC, id ASC"
            )
            rows = cur.fetchall()
            return {"experiment_types": [_experiment_type_public(row) for row in rows]}
    finally:
        conn.close()


@app.get("/api/admin/experiment-types")
async def admin_list_experiment_types(request: Request):
    _admin_only(request)
    conn = _db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT {', '.join(EXPERIMENT_TYPE_COLUMNS)}, id FROM experiment_types "
                "ORDER BY sort_order ASC, id ASC"
            )
            rows = cur.fetchall()
            return {"experiment_types": [_experiment_type_public(row) for row in rows]}
    finally:
        conn.close()


@app.post("/api/admin/experiment-types")
async def admin_create_experiment_type(request: Request):
    _admin_only(request)
    values = _experiment_type_values(await request.json())
    _validate_experiment_type(values)
    conn = _db_conn()
    try:
        with conn.cursor() as cur:
            _assert_type_name_available(cur, values["name"])
            placeholders = ", ".join(["%s"] * len(EXPERIMENT_TYPE_COLUMNS))
            cur.execute(
                f"INSERT INTO experiment_types ({', '.join(EXPERIMENT_TYPE_COLUMNS)}) "
                f"VALUES ({placeholders})",
                tuple(values[column] for column in EXPERIMENT_TYPE_COLUMNS),
            )
            row = _experiment_type_by_id(cur, cur.lastrowid)
        conn.commit()
    finally:
        conn.close()
    return {"experiment_type": _experiment_type_public(row), "message": "实验类型已新增"}


@app.put("/api/admin/experiment-types/{type_id}")
async def admin_update_experiment_type(type_id: int, request: Request):
    _admin_only(request)
    body = await request.json()
    conn = _db_conn()
    try:
        with conn.cursor() as cur:
            row = _experiment_type_by_id(cur, type_id)
            if not row:
                raise HTTPException(status_code=404, detail="实验类型不存在")
            values = _experiment_type_values(body, _experiment_type_public(row))
            _validate_experiment_type(values)
            _assert_type_name_available(cur, values["name"], type_id)
            assignments = ", ".join(f"{column} = %s" for column in EXPERIMENT_TYPE_COLUMNS)
            cur.execute(
                f"UPDATE experiment_types SET {assignments} WHERE id = %s",
                tuple(values[column] for column in EXPERIMENT_TYPE_COLUMNS) + (type_id,),
            )
            updated = _experiment_type_by_id(cur, type_id)
        conn.commit()
    finally:
        conn.close()
    return {"experiment_type": _experiment_type_public(updated), "message": "实验类型已更新"}


@app.delete("/api/admin/experiment-types/{type_id}")
async def admin_delete_experiment_type(type_id: int, request: Request):
    _admin_only(request)
    conn = _db_conn()
    try:
        with conn.cursor() as cur:
            row = _experiment_type_by_id(cur, type_id)
            if not row:
                raise HTTPException(status_code=404, detail="实验类型不存在")
            cur.execute("DELETE FROM experiment_types WHERE id = %s", (type_id,))
        conn.commit()
    finally:
        conn.close()
    return {"success": True, "message": "实验类型已删除"}


# ---------- 实验数据管理 API（管理员增删改查） ----------
EXPERIMENT_COLUMNS = (
    "name", "experiment_type", "operator_name", "operator_username", "description",
    "duration_seconds", "speed", "acceleration",
    "throttle", "yaw", "front_fps", "created_at", "is_active",
)


def _experiment_public(row: dict) -> dict:
    return {
        "id": int(row["id"]),
        "name": row["name"] or "",
        "experiment_type": row.get("experiment_type") or "",
        "operator_name": row.get("operator_name") or "",
        "operator_username": row.get("operator_username") or "",
        "description": row.get("description") or "",
        "duration_seconds": int(row["duration_seconds"] or 0),
        "speed": float(row["speed"] or 0),
        "acceleration": float(row["acceleration"] or 0),
        "throttle": float(row["throttle"] or 0),
        "yaw": float(row["yaw"] or 0),
        "front_fps": float(row["front_fps"] or 0),
        "created_at": row["created_at"] or "",
        "is_active": bool(row.get("is_active", 0)),
    }


def _experiment_values(body: dict, base: dict = None) -> dict:
    """把请求体合并到 base（更新场景），并做类型清洗。"""
    source = dict(base or {})
    source.update(body or {})

    def _str(key, default=""):
        value = source.get(key, default)
        return str(value).strip() if value is not None else default

    def _int(key):
        try:
            return max(0, int(source.get(key) or 0))
        except (TypeError, ValueError):
            return 0

    def _float(key):
        try:
            return float(source.get(key) or 0)
        except (TypeError, ValueError):
            return 0.0

    return {
        "name": _str("name"),
        "experiment_type": _str("experiment_type"),
        "operator_name": _str("operator_name"),
        "operator_username": _str("operator_username"),
        "description": _str("description"),
        "duration_seconds": _int("duration_seconds"),
        "speed": _float("speed"),
        "acceleration": _float("acceleration"),
        "throttle": _float("throttle"),
        "yaw": _float("yaw"),
        "front_fps": _float("front_fps"),
        "created_at": _str("created_at") or (base or {}).get("created_at") or _now_iso(),
        "is_active": 1 if source.get("is_active") else 0,
    }


def _experiment_by_id(cur, exp_id: int) -> dict:
    cur.execute(
        f"SELECT {', '.join(EXPERIMENT_COLUMNS)}, id FROM experiments WHERE id = %s",
        (exp_id,),
    )
    return cur.fetchone()


def _ensure_experiment_status_column() -> None:
    conn = _db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SHOW COLUMNS FROM experiments LIKE 'is_active'")
            if not cur.fetchone():
                cur.execute(
                    "ALTER TABLE experiments ADD COLUMN is_active TINYINT(1) NOT NULL DEFAULT 0"
                )
        conn.commit()
    finally:
        conn.close()


def _ensure_experiment_type_column() -> None:
    conn = _db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SHOW COLUMNS FROM experiments LIKE 'experiment_type'")
            if not cur.fetchone():
                cur.execute(
                    "ALTER TABLE experiments ADD COLUMN experiment_type VARCHAR(64) NOT NULL DEFAULT ''"
                )
        conn.commit()
    finally:
        conn.close()


def _ensure_experiment_description_column() -> None:
    conn = _db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SHOW COLUMNS FROM experiments LIKE 'description'")
            if not cur.fetchone():
                cur.execute(
                    "ALTER TABLE experiments ADD COLUMN description VARCHAR(2000) NOT NULL DEFAULT ''"
                )
        conn.commit()
    finally:
        conn.close()


def _ensure_experiment_operator_name_column() -> None:
    conn = _db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SHOW COLUMNS FROM experiments LIKE 'operator_name'")
            if not cur.fetchone():
                cur.execute(
                    "ALTER TABLE experiments ADD COLUMN operator_name VARCHAR(64) NOT NULL DEFAULT ''"
                )
            cur.execute("SHOW COLUMNS FROM experiments LIKE 'student_name'")
            if cur.fetchone():
                cur.execute(
                    "UPDATE experiments SET operator_name = student_name "
                    "WHERE operator_name = '' AND student_name <> ''"
                )
        conn.commit()
    finally:
        conn.close()


def _ensure_experiment_operator_username_column() -> None:
    conn = _db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SHOW COLUMNS FROM experiments LIKE 'operator_username'")
            if not cur.fetchone():
                cur.execute(
                    "ALTER TABLE experiments ADD COLUMN operator_username VARCHAR(64) NOT NULL DEFAULT ''"
                )
            operator_owners = {}
            ambiguous_names = set()
            for account in users:
                username = account["username"]
                for operator_name in {
                    username,
                    str(account.get("display_name") or "").strip(),
                }:
                    if not operator_name:
                        continue
                    owner = operator_owners.get(operator_name)
                    if owner and owner != username:
                        ambiguous_names.add(operator_name)
                    else:
                        operator_owners[operator_name] = username
            for operator_name, username in operator_owners.items():
                if operator_name in ambiguous_names:
                    continue
                cur.execute(
                    "UPDATE experiments SET operator_username = %s "
                    "WHERE operator_username = '' AND operator_name = %s",
                    (username, operator_name),
                )
        conn.commit()
    finally:
        conn.close()


_ensure_experiment_status_column()
_ensure_experiment_type_column()
_ensure_experiment_description_column()
_ensure_experiment_operator_name_column()
_ensure_experiment_operator_username_column()


@app.get("/api/admin/experiments")
async def admin_list_experiments(request: Request, keyword: str = "", experiment_type: str = ""):
    _admin_only(request)
    conn = _db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT DISTINCT experiment_type FROM experiments "
                "WHERE TRIM(experiment_type) <> '' ORDER BY experiment_type"
            )
            used_types = [row["experiment_type"] for row in cur.fetchall()]
            # 实验类型以下拉列表形式提供给「新增/编辑实验」使用：
            # 优先使用「实验类型管理」中维护的类型，再补充实验记录中已出现但未维护的类型。
            cur.execute("SELECT name FROM experiment_types ORDER BY sort_order ASC, id ASC")
            experiment_types = [row["name"] for row in cur.fetchall()]
            for used_type in used_types:
                if used_type not in experiment_types:
                    experiment_types.append(used_type)
            sql = f"SELECT {', '.join(EXPERIMENT_COLUMNS)}, id FROM experiments WHERE 1=1"
            params = []
            if keyword:
                sql += " AND name LIKE %s"
                params.append(f"%{keyword}%")
            if experiment_type:
                sql += " AND experiment_type = %s"
                params.append(experiment_type)
            sql += " ORDER BY id DESC"
            cur.execute(sql, params)
            return {
                "experiments": [_experiment_public(row) for row in cur.fetchall()],
                "experiment_types": experiment_types,
            }
    finally:
        conn.close()


@app.get("/api/users/me/experiments")
async def user_experiment_summary(request: Request):
    user = _current_user(request)
    conn = _db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) AS experiment_count, "
                "COALESCE(SUM(duration_seconds), 0) AS total_duration_seconds "
                "FROM experiments WHERE operator_username = %s",
                (user["username"],),
            )
            summary = cur.fetchone()
            cur.execute(
                "SELECT DISTINCT experiment_type FROM experiments "
                "WHERE operator_username = %s AND TRIM(experiment_type) <> '' "
                "ORDER BY experiment_type",
                (user["username"],),
            )
            experiment_types = [row["experiment_type"] for row in cur.fetchall()]
            cur.execute(
                "SELECT id, name, experiment_type, duration_seconds, created_at, is_active "
                "FROM experiments WHERE operator_username = %s ORDER BY id DESC LIMIT 5",
                (user["username"],),
            )
            experiments = [
                {
                    "id": int(row["id"]),
                    "name": row["name"] or "",
                    "experiment_type": row["experiment_type"] or "",
                    "duration_seconds": int(row["duration_seconds"] or 0),
                    "created_at": row["created_at"] or "",
                    "is_active": bool(row.get("is_active", 0)),
                }
                for row in cur.fetchall()
            ]
            return {
                "experiments": experiments,
                "experiment_types": experiment_types,
                "experiment_count": int(summary["experiment_count"] or 0),
                "total_duration_seconds": int(summary["total_duration_seconds"] or 0),
            }
    finally:
        conn.close()


@app.post("/api/admin/experiments")
async def admin_create_experiment(request: Request):
    _admin_only(request)
    body = await request.json()
    values = _experiment_values(body)
    if not values["name"]:
        raise HTTPException(status_code=400, detail="实验名称不能为空")
    if not values["experiment_type"]:
        raise HTTPException(status_code=400, detail="实验类型不能为空")
    if len(values["experiment_type"]) > 64:
        raise HTTPException(status_code=400, detail="实验类型不能超过 64 个字符")
    if not values["description"]:
        raise HTTPException(status_code=400, detail="实验简介不能为空")
    if len(values["description"]) > 2000:
        raise HTTPException(status_code=400, detail="实验简介不能超过 2000 字")
    conn = _db_conn()
    try:
        with conn.cursor() as cur:
            placeholders = ", ".join(["%s"] * len(EXPERIMENT_COLUMNS))
            cur.execute(
                f"INSERT INTO experiments ({', '.join(EXPERIMENT_COLUMNS)}) VALUES ({placeholders})",
                tuple(values[column] for column in EXPERIMENT_COLUMNS),
            )
            exp_id = cur.lastrowid
            row = _experiment_by_id(cur, exp_id)
        conn.commit()
    finally:
        conn.close()
    return {"experiment": _experiment_public(row), "message": "实验数据已新增"}


@app.post("/api/experiments")
async def save_experiment_record(request: Request):
    """实验结束后保存运行记录：登录用户（普通用户/管理员）均可写入。

    请求体字段：name、duration_seconds、speed、acceleration、throttle、yaw、front_fps。
    name 为空时按「用户名 + 时间」自动生成。
    """
    user = _current_user(request)
    body = await request.json()
    values = _experiment_values(body)
    values["operator_name"] = str(user.get("display_name") or user["username"]).strip()
    values["operator_username"] = user["username"]
    if not values["name"]:
        values["name"] = f"{user.get('display_name') or user['username']} 的实验 {_now_iso()[:19].replace('T', ' ')}"
    values["is_active"] = 1
    conn = _db_conn()
    try:
        with conn.cursor() as cur:
            placeholders = ", ".join(["%s"] * len(EXPERIMENT_COLUMNS))
            cur.execute(
                f"INSERT INTO experiments ({', '.join(EXPERIMENT_COLUMNS)}) VALUES ({placeholders})",
                tuple(values[column] for column in EXPERIMENT_COLUMNS),
            )
            exp_id = cur.lastrowid
            row = _experiment_by_id(cur, exp_id)
        conn.commit()
    finally:
        conn.close()
    return {"experiment": _experiment_public(row), "message": "实验记录已保存"}


@app.put("/api/admin/experiments/{exp_id}")
async def admin_update_experiment(exp_id: int, request: Request):
    _admin_only(request)
    body = await request.json()
    conn = _db_conn()
    try:
        with conn.cursor() as cur:
            row = _experiment_by_id(cur, exp_id)
            if not row:
                raise HTTPException(status_code=404, detail="实验记录不存在")
            values = _experiment_values(body, _experiment_public(row))
            if not values["name"]:
                raise HTTPException(status_code=400, detail="实验名称不能为空")
            if not values["experiment_type"]:
                raise HTTPException(status_code=400, detail="实验类型不能为空")
            if len(values["experiment_type"]) > 64:
                raise HTTPException(status_code=400, detail="实验类型不能超过 64 个字符")
            if not values["description"]:
                raise HTTPException(status_code=400, detail="实验简介不能为空")
            if len(values["description"]) > 2000:
                raise HTTPException(status_code=400, detail="实验简介不能超过 2000 字")
            assignments = ", ".join(f"{column} = %s" for column in EXPERIMENT_COLUMNS)
            cur.execute(
                f"UPDATE experiments SET {assignments} WHERE id = %s",
                tuple(values[column] for column in EXPERIMENT_COLUMNS) + (exp_id,),
            )
            updated = _experiment_by_id(cur, exp_id)
        conn.commit()
    finally:
        conn.close()
    return {"experiment": _experiment_public(updated), "message": "实验数据已更新"}


@app.delete("/api/admin/experiments/{exp_id}")
async def admin_delete_experiment(exp_id: int, request: Request):
    _admin_only(request)
    conn = _db_conn()
    try:
        with conn.cursor() as cur:
            row = _experiment_by_id(cur, exp_id)
            if not row:
                raise HTTPException(status_code=404, detail="实验记录不存在")
            cur.execute("DELETE FROM experiments WHERE id = %s", (exp_id,))
        conn.commit()
    finally:
        conn.close()
    return {"success": True, "message": "实验记录已删除"}


@app.put("/api/admin/experiments/{exp_id}/status")
async def admin_set_experiment_status(exp_id: int, request: Request):
    _admin_only(request)
    body = await request.json()
    is_active = bool(body.get("is_active"))
    conn = _db_conn()
    try:
        with conn.cursor() as cur:
            row = _experiment_by_id(cur, exp_id)
            if not row:
                raise HTTPException(status_code=404, detail="实验记录不存在")
            cur.execute(
                "UPDATE experiments SET is_active = %s WHERE id = %s",
                (1 if is_active else 0, exp_id),
            )
            updated = _experiment_by_id(cur, exp_id)
        conn.commit()
    finally:
        conn.close()
    return {
        "experiment": _experiment_public(updated),
        "message": "实验已启用" if is_active else "实验已停用",
    }


# ---------- 私信 API ----------
@app.get("/api/messages")
async def list_messages(request: Request):
    user = _current_user(request)
    is_admin = user["role"] == "admin"
    with data_lock:
        my_messages = [
            m for m in messages
            if m["sender_username"] == user["username"] or m["recipient_username"] == user["username"]
        ]
        if not is_admin:
            # 普通用户只可见与管理员的消息（用户之间不可对话、不可见）
            my_messages = [
                m for m in my_messages
                if m["sender_username"] == "admin" or m["recipient_username"] == "admin"
            ]
        available_recipients = []
        if is_admin:
            available_recipients = [
                {"username": u["username"], "display_name": u["display_name"]}
                for u in users if u["role"] != "admin"
            ]
        return {"messages": my_messages, "available_recipients": available_recipients}


@app.post("/api/messages")
async def send_message(request: Request):
    global next_message_id
    user = _current_user(request)
    body = await request.json()
    recipient = str(body.get("recipient", body.get("recipient_username", ""))).strip()
    content = str(body.get("content", "")).strip()
    if not recipient or not content:
        raise HTTPException(status_code=400, detail="请填写收件人和消息内容")
    if len(content) > 2000:
        raise HTTPException(status_code=400, detail="消息内容不能超过 2000 字")
    recipient_user = next((u for u in users if u["username"] == recipient), None)
    if not recipient_user:
        raise HTTPException(status_code=404, detail="收件人不存在")
    if user["role"] == "admin" and recipient_user["role"] != "user":
        raise HTTPException(status_code=400, detail="管理员只能向普通用户发送私信")
    if user["role"] != "admin" and recipient_user["username"] != "admin":
        raise HTTPException(status_code=403, detail="普通用户只能向管理员发送私信")
    message = {
        "id": f"msg-{next_message_id}",
        "subject": str(body.get("subject", "用户与管理员私信" if user["role"] != "admin" else "管理员私信")).strip(),
        "sender": user["display_name"],
        "sender_username": user["username"],
        "recipient": recipient_user["display_name"],
        "recipient_username": recipient_user["username"],
        "content": content,
        "created_at": _now_iso(),
    }
    with data_lock:
        next_message_id += 1
        messages.append(message)
        save_messages(messages)
    return {"message": message}


# ---------- 静态文件服务 ----------
@app.get("/")
async def get():
    return FileResponse(str(STATIC_DIR / "index.html"), headers={"Cache-Control": "no-store, no-cache, must-revalidate"})

# 将 static 目录挂载到根路径：前端用相对路径引用 /js/*、/config.js 等资源，
# 需以 static 作为 web 根；已注册的 /api/* 与 /ws 路由优先级更高，不受影响。
app.mount("/", StaticFiles(directory=str(STATIC_DIR)), name="static-root")

if __name__ == "__main__":
    # 使用 8080 端口，避免与 CARLA Traffic Manager 默认 8000 冲突
    uvicorn.run(app, host="0.0.0.0", port=8080)