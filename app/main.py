"""
子用户网盘 · 后端（一期网页端 MVP）

形态见《子用户网盘客户端-规格》：
  - 子用户在本系统凭邀请码注册；每人在 Seafile 专用库里有一个 /<username>/ 文件夹（投影）；
  - 本后端是唯一安全边界：逐请求验身份、验路径（app.paths 唯一实现）、验配额，
    再翻译为 Seafile 适配层调用（app.storage，stub/live 可切换）；
  - 主账号令牌只住服务器环境变量，永不下发。
工程模式沿用 private-chat：FastAPI + SQLite 单文件、PBKDF2-SHA256 20 万次迭代、
sessions 表管登录态、原生 JS 前端由后端同源托管。
"""
import hashlib
import os
import re
import secrets
import sqlite3
import tempfile
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.paths import (USERNAME_RE, PathRejected, full_path, normalize_rel_path,
                       set_current_user, set_granted_prefixes, validate_name,
                       validate_username)
from app.storage import StorageConflict, StorageError, StorageNotFound, make_storage

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("DATA_DIR", BASE_DIR / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = Path(os.environ.get("DB_PATH", DATA_DIR / "subdrive.db"))
STATIC_DIR = BASE_DIR / "static"

PBKDF2_ITERATIONS = 200_000
DEFAULT_QUOTA_BYTES = int(os.environ.get("DEFAULT_QUOTA_BYTES", 20 * 1024 ** 3))
MAX_FILE_BYTES = int(os.environ.get("MAX_FILE_BYTES", 2 * 1024 ** 3))
SESSION_TTL_DAYS = int(os.environ.get("SESSION_TTL_DAYS", "30"))
LOGIN_MAX_FAILS = int(os.environ.get("LOGIN_MAX_FAILS", "5"))
LOGIN_LOCK_MINUTES = int(os.environ.get("LOGIN_LOCK_MINUTES", "10"))
REGISTER_MAX_FAILS_PER_IP = int(os.environ.get("REGISTER_MAX_FAILS_PER_IP", "10"))
CALIBRATE_INTERVAL = int(os.environ.get("CALIBRATE_INTERVAL_SECONDS", "3600"))
SPEEDTEST_MAX_BYTES = int(os.environ.get("SPEEDTEST_MAX_BYTES", 50 * 1024 ** 2))
SPEEDTEST_DEFAULT_BYTES = int(os.environ.get("SPEEDTEST_DEFAULT_BYTES", 25 * 1024 ** 2))
STORAGE_MODE = os.environ.get("SEAFILE_MODE", "stub").lower()

storage = make_storage(DATA_DIR)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def now_dt() -> datetime:
    return datetime.now(timezone.utc)


# ------------------------------------------------------------------ 数据库

_db_lock = threading.Lock()


def get_db() -> sqlite3.Connection:
    # autocommit：避免在 with 块内抛 HTTPException 时把限速计数/审计写入一并回滚
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    with _db_lock, get_db() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                nickname TEXT NOT NULL DEFAULT '',
                password_hash TEXT NOT NULL,
                password_salt TEXT NOT NULL,
                is_admin INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'active',
                quota_bytes INTEGER,
                invite_code_id INTEGER REFERENCES invite_codes(id),
                folder_created INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                last_login_at TEXT
            );
            CREATE TABLE IF NOT EXISTS invite_codes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT UNIQUE NOT NULL,
                created_by INTEGER REFERENCES users(id),
                note TEXT NOT NULL DEFAULT '',
                max_uses INTEGER NOT NULL DEFAULT 1,
                used_count INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'active',
                expires_at TEXT,
                used_by_user_id INTEGER REFERENCES users(id),
                used_at TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                user_agent TEXT NOT NULL DEFAULT '',
                ip TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS usage_cache (
                user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                used_bytes INTEGER NOT NULL DEFAULT 0,
                file_count INTEGER NOT NULL DEFAULT 0,
                dirty INTEGER NOT NULL DEFAULT 0,
                calibrated_at TEXT
            );
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                actor_user_id INTEGER REFERENCES users(id),
                action TEXT NOT NULL,
                target_path TEXT NOT NULL DEFAULT '',
                size_bytes INTEGER,
                ip TEXT NOT NULL DEFAULT '',
                result TEXT NOT NULL DEFAULT 'ok',
                detail TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS login_failures (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scope TEXT NOT NULL,
                ts TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_fail_scope ON login_failures(scope, ts);
            CREATE TABLE IF NOT EXISTS shared_folders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                owner_username TEXT NOT NULL,
                rel_path TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(owner_id, rel_path)
            );
            CREATE TABLE IF NOT EXISTS shared_grants (
                folder_id INTEGER NOT NULL REFERENCES shared_folders(id) ON DELETE CASCADE,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                granted_at TEXT NOT NULL,
                PRIMARY KEY (folder_id, user_id)
            );
            CREATE INDEX IF NOT EXISTS idx_grants_user ON shared_grants(user_id);
            """
        )
        # 轻量迁移：共享文件夹的「每目录上限」两列（SQLite 没有 ADD COLUMN IF NOT EXISTS）
        for col in ("max_bytes", "max_members"):
            try:
                db.execute(f"ALTER TABLE shared_folders ADD COLUMN {col} INTEGER NOT NULL DEFAULT 0")
            except sqlite3.OperationalError:
                pass  # 已经有了


# ------------------------------------------------------------------ 密码/令牌

def hash_password(password: str, salt: str) -> str:
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), PBKDF2_ITERATIONS)
    return dk.hex()


def new_session_token() -> str:
    return secrets.token_urlsafe(32)  # 256 bit


def new_invite_code() -> str:
    raw = secrets.token_hex(16).upper()  # 128 bit
    return "SD-" + "-".join(raw[i:i + 4] for i in range(0, 32, 4))


# ------------------------------------------------------------------ 审计

def audit(db, actor_id, action, target_path="", size=None, ip="", result="ok", detail=""):
    db.execute(
        "INSERT INTO audit_log (ts, actor_user_id, action, target_path, size_bytes, ip, result, detail)"
        " VALUES (?,?,?,?,?,?,?,?)",
        (now_iso(), actor_id, action, target_path, size, ip, result, detail),
    )


# ------------------------------------------------------------------ 限速（规格 §7-6）

def _recent_failures(db, scope: str, minutes: int) -> int:
    since = (now_dt() - timedelta(minutes=minutes)).isoformat()
    row = db.execute(
        "SELECT COUNT(*) AS c FROM login_failures WHERE scope = ? AND ts >= ?",
        (scope, since),
    ).fetchone()
    return row["c"]


def _record_failure(db, scope: str) -> None:
    db.execute("INSERT INTO login_failures (scope, ts) VALUES (?,?)", (scope, now_iso()))


def _clear_failures(db, scope: str) -> None:
    db.execute("DELETE FROM login_failures WHERE scope = ?", (scope,))


def login_locked(db, username: str) -> bool:
    return _recent_failures(db, f"login:{username}", LOGIN_LOCK_MINUTES) >= LOGIN_MAX_FAILS


# ------------------------------------------------------------------ 会话/当前用户

def create_session(db, user_id: int, request: Request) -> str:
    token = new_session_token()
    exp = (now_dt() + timedelta(days=SESSION_TTL_DAYS)).isoformat()
    db.execute(
        "INSERT INTO sessions (token, user_id, created_at, expires_at, last_seen_at, user_agent, ip)"
        " VALUES (?,?,?,?,?,?,?)",
        (token, user_id, now_iso(), exp, now_iso(),
         request.headers.get("user-agent", "")[:200], client_ip(request)),
    )
    return token


def client_ip(request: Request) -> str:
    return request.client.host if request.client else ""


def extract_token(request: Request) -> str:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return request.query_params.get("token", "")


def get_user_by_token(token: str):
    if not token:
        return None
    with _db_lock, get_db() as db:
        row = db.execute(
            "SELECT u.* FROM sessions s JOIN users u ON s.user_id = u.id"
            " WHERE s.token = ? AND s.expires_at > ?",
            (token, now_iso()),
        ).fetchone()
        if row:
            db.execute("UPDATE sessions SET last_seen_at = ? WHERE token = ?", (now_iso(), token))
        return row


def require_user(request: Request):
    user = get_user_by_token(extract_token(request))
    if not user:
        raise HTTPException(401, detail={"error": "unauthorized", "message": "未登录或登录已失效"})
    if user["status"] != "active":
        raise HTTPException(403, detail={"error": "account_disabled", "message": "账号已被禁用"})
    # 供存储层做归属校验：此后所有 full 路径都必须落在 /<该用户名> 下（管理员除外，
    # 校准、代管等操作本来就要跨用户）。
    set_current_user(user["username"], bool(user["is_admin"]))
    # 被授权的他人共享目录：存储层据此放行整棵子树；写权限在路由层再收窄到
    # 「自己的同名子目录」，见 _foreign_target。
    set_granted_prefixes(_granted_prefixes_of(user["id"]))
    return user


def require_admin(request: Request):
    user = require_user(request)
    if not user["is_admin"]:
        raise HTTPException(403, detail={"error": "admin_required", "message": "需要管理员权限"})
    return user


def owner_username() -> str:
    """系统所有者 = 部署引导管理员（SUBDRIVE_ADMIN_USERNAME 环境变量指定的账号）。"""
    return os.environ.get("SUBDRIVE_ADMIN_USERNAME", "").strip()


def is_owner(user) -> bool:
    owner = owner_username()
    return bool(owner) and user["username"] == owner


def user_public(row) -> dict:
    return {
        "id": row["id"],
        "username": row["username"],
        "nickname": row["nickname"] or row["username"],
        "is_admin": bool(row["is_admin"]),
        "is_owner": is_owner(row),
        "status": row["status"],
        "created_at": row["created_at"],
        "last_login_at": row["last_login_at"],
    }


# ------------------------------------------------------------------ 配额

def quota_of(db, user) -> int:
    if user["quota_bytes"] is not None:
        return user["quota_bytes"]
    return DEFAULT_QUOTA_BYTES


def usage_of(db, user_id: int) -> dict:
    row = db.execute("SELECT * FROM usage_cache WHERE user_id = ?", (user_id,)).fetchone()
    if not row:
        return {"used_bytes": 0, "file_count": 0, "calibrated_at": None}
    return {"used_bytes": row["used_bytes"], "file_count": row["file_count"],
            "calibrated_at": row["calibrated_at"]}


def usage_add(db, user_id: int, delta_bytes: int, delta_files: int = 0) -> None:
    db.execute(
        "INSERT INTO usage_cache (user_id, used_bytes, file_count, dirty) VALUES (?,?,?,1)"
        " ON CONFLICT(user_id) DO UPDATE SET used_bytes = MAX(0, used_bytes + ?),"
        " file_count = MAX(0, file_count + ?), dirty = 1",
        (user_id, max(0, delta_bytes), max(0, delta_files), delta_bytes, delta_files),
    )


def calibrate_user(user_id: int) -> dict:
    """校准轨：递归遍历该用户文件夹累加真实用量，覆写缓存（规格 §3 双轨制）。"""
    with _db_lock, get_db() as db:
        user = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if not user:
        raise HTTPException(404, detail={"error": "not_found", "message": "用户不存在"})
    total, count = storage.path_size(full_path(user["username"], ""))
    with _db_lock, get_db() as db:
        db.execute(
            "INSERT INTO usage_cache (user_id, used_bytes, file_count, dirty, calibrated_at)"
            " VALUES (?,?,?,0,?) ON CONFLICT(user_id) DO UPDATE SET used_bytes=?, file_count=?,"
            " dirty=0, calibrated_at=?",
            (user_id, total, count, now_iso(), total, count, now_iso()),
        )
    return {"used_bytes": total, "file_count": count, "calibrated_at": now_iso()}


def _calibration_loop():
    while True:
        time.sleep(CALIBRATE_INTERVAL)
        try:
            with _db_lock, get_db() as db:
                ids = [r["id"] for r in db.execute(
                    "SELECT id FROM users WHERE folder_created = 1").fetchall()]
            for uid in ids:
                try:
                    calibrate_user(uid)
                except Exception:
                    pass
        except Exception:
            pass


# ------------------------------------------------------------------ 应用

app = FastAPI(title="子用户网盘 SubDrive", docs_url=None, redoc_url=None)


@app.exception_handler(StorageError)
async def _storage_error_handler(request: Request, exc: StorageError):
    return JSONResponse(status_code=exc.status,
                        content={"error": exc.code, "message": str(exc)})


@app.exception_handler(PathRejected)
async def _path_error_handler(request: Request, exc: PathRejected):
    return JSONResponse(status_code=403,
                        content={"error": "path_rejected", "message": str(exc)})


def err(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status, detail={"error": code, "message": message})


def _dedup_name(full: str, filename: str) -> str:
    """「两者都保留」：在同一目录里挑一个带 (n) 后缀、当前不存在的名字。

    只改文件名，不碰目录——归属仍由落点规则决定，所以名字变了也不会变成别人的文件。
    """
    stem, dot, ext = filename.rpartition(".")
    if not dot or not stem:  # 没有扩展名，或形如 .env
        stem, ext = filename, ""
    for n in range(2, 1000):
        cand = f"{stem} ({n})" + (f".{ext}" if ext else "")
        try:
            storage.stat(f"{full}/{cand}")
        except StorageNotFound:
            return cand
    raise err(409, "conflict", "同名文件太多，改个名再传")


def bootstrap_admin() -> None:
    """部署初始化管理员（规格 §9-5）：环境变量 SUBDRIVE_ADMIN_USERNAME/PASSWORD。"""
    username = os.environ.get("SUBDRIVE_ADMIN_USERNAME", "").strip()
    password = os.environ.get("SUBDRIVE_ADMIN_PASSWORD", "")
    if not username or not password:
        return
    # 部署管理员由运营者经环境变量指定：只验格式，不受注册保留字名单限制
    # （保留字是防注册者冒用系统名的；曾因此把默认名 admin 静默跳过，导致无人能登录）
    if not USERNAME_RE.match(username):
        print(f"[subdrive] SUBDRIVE_ADMIN_USERNAME 不符合用户名格式，已跳过管理员初始化：{username}")
        return
    with _db_lock, get_db() as db:
        if db.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone():
            return
        salt = secrets.token_hex(16)
        cur = db.execute(
            "INSERT INTO users (username, nickname, password_hash, password_salt, is_admin,"
            " status, folder_created, created_at) VALUES (?,?,?,?,?, 'active', 0, ?)",
            (username, username, hash_password(password, salt), salt, 1, now_iso()),
        )
        uid = cur.lastrowid
        db.execute("INSERT INTO usage_cache (user_id) VALUES (?)", (uid,))
    try:
        storage.ensure_user_folder(username)
        with _db_lock, get_db() as db:
            db.execute("UPDATE users SET folder_created = 1 WHERE id = ?", (uid,))
    except StorageError:
        pass


init_db()
bootstrap_admin()
if CALIBRATE_INTERVAL > 0:
    threading.Thread(target=_calibration_loop, daemon=True).start()


# ------------------------------------------------------------------ 请求体

class RegisterIn(BaseModel):
    invite_code: str = ""
    username: str
    password: str
    nickname: str = ""


class LoginIn(BaseModel):
    username: str
    password: str


class ChangePasswordIn(BaseModel):
    old_password: str
    new_password: str
    revoke_others: bool = True


class MkdirIn(BaseModel):
    path: str = ""
    name: str


class RenameIn(BaseModel):
    path: str
    new_name: str


class MoveIn(BaseModel):
    path: str
    dest_dir: str = ""


class DeleteIn(BaseModel):
    path: str


class InviteCreateIn(BaseModel):
    note: str = ""
    max_uses: int = 1
    expires_days: float | None = 7


class QuotaIn(BaseModel):
    quota_bytes: int | None = None


class AdminFlagIn(BaseModel):
    is_admin: bool


class SharedCreateIn(BaseModel):
    path: str
    members: list[str] = []
    max_bytes: int | None = None    # None/0 = 用全局默认
    max_members: int | None = None


class SharedMembersIn(BaseModel):
    members: list[str] = []


class SharedLimitsIn(BaseModel):
    """改每目录上限（D35）：留 None 的字段不动。"""
    max_bytes: int | None = None
    max_members: int | None = None


# ------------------------------------------------------------------ auth 组

@app.post("/api/auth/register")
def register(data: RegisterIn, request: Request):
    ip = client_ip(request)
    username = (data.username or "").strip()
    # 用户名先过规则（正则+保留字），与路径安全同源
    try:
        validate_username(username)
    except PathRejected as e:
        raise err(400, "bad_username", str(e))
    if len(data.password or "") < 8:
        raise err(400, "weak_password", "密码至少 8 位")
    nickname = (data.nickname or "").strip()[:40]

    with _db_lock, get_db() as db:
        # 首个用户免邀请码自动成为管理员（沿用 private-chat 约定；正式部署走环境变量初始化）
        user_count = db.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
        first_user = user_count == 0
        invite = None
        if not first_user:
            # 邀请码试错限速（§7-6）
            if _recent_failures(db, f"reg:{ip}", 60) >= REGISTER_MAX_FAILS_PER_IP:
                raise err(429, "rate_limited", "尝试过于频繁，请稍后再试")
            code = (data.invite_code or "").strip().upper()
            invite = db.execute("SELECT * FROM invite_codes WHERE code = ?", (code,)).fetchone()
            problem = None
            if not invite:
                problem = "邀请码无效"
            elif invite["status"] == "revoked":
                problem = "邀请码已被撤销"
            elif invite["status"] != "active" or invite["used_count"] >= invite["max_uses"]:
                problem = "邀请码已被使用"
            elif invite["expires_at"] and invite["expires_at"] <= now_iso():
                problem = "邀请码已过期"
            if problem:
                _record_failure(db, f"reg:{ip}")
                audit(db, None, "register", "", None, ip, "denied", problem)
                raise err(400, "bad_invite", problem)
        if db.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone():
            raise err(400, "username_taken", "用户名已被占用")

        salt = secrets.token_hex(16)
        cur = db.execute(
            "INSERT INTO users (username, nickname, password_hash, password_salt, is_admin,"
            " status, invite_code_id, folder_created, created_at) VALUES (?,?,?,?,?,?,?,0,?)",
            (username, nickname, hash_password(data.password, salt), salt,
             1 if first_user else 0, "active", invite["id"] if invite else None, now_iso()),
        )
        user_id = cur.lastrowid
        db.execute("INSERT INTO usage_cache (user_id) VALUES (?)", (user_id,))

    # 建投影文件夹；失败则整体回滚（不建号、不消耗邀请码）
    try:
        if storage.user_folder_exists(username):
            raise StorageConflict("Seafile 侧已存在同名文件夹")
        storage.ensure_user_folder(username)
    except StorageError as e:
        with _db_lock, get_db() as db:
            db.execute("DELETE FROM users WHERE id = ?", (user_id,))
            db.execute("DELETE FROM usage_cache WHERE user_id = ?", (user_id,))
        raise e

    with _db_lock, get_db() as db:
        db.execute("UPDATE users SET folder_created = 1 WHERE id = ?", (user_id,))
        if invite:
            used = invite["used_count"] + 1
            status = "used_up" if used >= invite["max_uses"] else "active"
            db.execute(
                "UPDATE invite_codes SET used_count = ?, status = ?, used_by_user_id = ?,"
                " used_at = ? WHERE id = ?",
                (used, status, user_id, now_iso(), invite["id"]),
            )
        token = create_session(db, user_id, request)
        db.execute("UPDATE users SET last_login_at = ? WHERE id = ?", (now_iso(), user_id))
        audit(db, user_id, "register", f"/{username}", None, ip, "ok",
              "first-admin" if first_user else "invite")
        user = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return {"token": token, "user": user_public(user)}


@app.post("/api/auth/login")
def login(data: LoginIn, request: Request):
    ip = client_ip(request)
    username = (data.username or "").strip()
    with _db_lock, get_db() as db:
        if login_locked(db, username):
            raise err(429, "login_locked", f"失败次数过多，账号锁定 {LOGIN_LOCK_MINUTES} 分钟")
        user = db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        ok = user is not None and secrets.compare_digest(
            hash_password(data.password or "", user["password_salt"]), user["password_hash"])
        if not ok:
            _record_failure(db, f"login:{username}")
            audit(db, user["id"] if user else None, "login", "", None, ip, "denied", "密码错误")
            raise err(401, "bad_credentials", "用户名或密码错误")
        if user["status"] != "active":
            audit(db, user["id"], "login", "", None, ip, "denied", "账号已禁用")
            raise err(403, "account_disabled", "账号已被禁用")
        _clear_failures(db, f"login:{username}")
        token = create_session(db, user["id"], request)
        db.execute("UPDATE users SET last_login_at = ? WHERE id = ?", (now_iso(), user["id"]))
        audit(db, user["id"], "login", "", None, ip, "ok")
    return {"token": token, "user": user_public(user)}


@app.post("/api/auth/logout")
def logout(request: Request):
    token = extract_token(request)
    user = require_user(request)
    with _db_lock, get_db() as db:
        db.execute("DELETE FROM sessions WHERE token = ?", (token,))
        audit(db, user["id"], "logout", "", None, client_ip(request), "ok")
    return {"ok": True}


@app.get("/api/auth/me")
def me(request: Request):
    user = require_user(request)
    with _db_lock, get_db() as db:
        usage = usage_of(db, user["id"])
        out = user_public(user)
        out["quota_bytes"] = quota_of(db, user)
    out["used_bytes"] = usage["used_bytes"]
    out["storage_mode"] = STORAGE_MODE
    return out


@app.post("/api/auth/change-password")
def change_password(data: ChangePasswordIn, request: Request):
    user = require_user(request)
    if len(data.new_password or "") < 8:
        raise err(400, "weak_password", "新密码至少 8 位")
    with _db_lock, get_db() as db:
        row = db.execute("SELECT * FROM users WHERE id = ?", (user["id"],)).fetchone()
        if not secrets.compare_digest(
                hash_password(data.old_password or "", row["password_salt"]), row["password_hash"]):
            audit(db, user["id"], "change_password", "", None, client_ip(request), "denied", "旧密码错误")
            raise err(401, "bad_credentials", "旧密码错误")
        salt = secrets.token_hex(16)
        db.execute("UPDATE users SET password_hash = ?, password_salt = ? WHERE id = ?",
                   (hash_password(data.new_password, salt), salt, user["id"]))
        if data.revoke_others:
            current = extract_token(request)
            db.execute("DELETE FROM sessions WHERE user_id = ? AND token != ?",
                       (user["id"], current))
        audit(db, user["id"], "change_password", "", None, client_ip(request), "ok")
    return {"ok": True}


class NicknameIn(BaseModel):
    nickname: str = ""


@app.post("/api/me/nickname")
def update_nickname(data: NicknameIn, request: Request):
    """改自己的显示名（昵称）：可改、可重名、可清空，清空后回落到用户名。
    username 是登录名与所有路径/授权前缀的锚点（D3/D27），永远不动它。"""
    user = require_user(request)
    nick = (data.nickname or "").strip()[:40]
    with _db_lock, get_db() as db:
        db.execute("UPDATE users SET nickname = ? WHERE id = ?", (nick, user["id"]))
        row = db.execute("SELECT * FROM users WHERE id = ?", (user["id"],)).fetchone()
        out = user_public(row)
        out["quota_bytes"] = quota_of(db, row)
        out["used_bytes"] = usage_of(db, row["id"])["used_bytes"]
    out["storage_mode"] = STORAGE_MODE
    return out


# ------------------------------------------------------------------ 共享文件夹

# 共享文件夹的每目录上限（D35）：库里的 0 表示「用全局默认」；创建者可以往下调，
# 但两者都不能超过这里的全局硬顶——上限是防事故的，不是可以无限抬的旋钮。
MAX_SHARED_MEMBERS = 200
SHARED_MAX_BYTES = int(os.environ.get("SUBDRIVE_SHARED_MAX_BYTES", 2 * 1024 ** 3))
SHARED_MAX_MEMBERS = min(int(os.environ.get("SUBDRIVE_SHARED_MAX_MEMBERS", 20)), MAX_SHARED_MEMBERS)


def _shared_limits(row) -> tuple:
    """→ (容量上限, 成员上限)；库里 0 = 用全局默认。"""
    return (row["max_bytes"] or SHARED_MAX_BYTES, row["max_members"] or SHARED_MAX_MEMBERS)


def _clamp_limits(max_bytes, max_members) -> tuple:
    """把请求里的上限夹进 [1, 全局硬顶]；超硬顶直接拒，不静默截断。"""
    mb = SHARED_MAX_BYTES if max_bytes is None else int(max_bytes)
    mm = SHARED_MAX_MEMBERS if max_members is None else int(max_members)
    if mb < 1 or mm < 1:
        raise err(400, "bad_limit", "上限必须 ≥ 1")
    if mb > SHARED_MAX_BYTES:
        raise err(400, "bad_limit", f"容量上限最大 {SHARED_MAX_BYTES} 字节")
    if mm > SHARED_MAX_MEMBERS:
        raise err(400, "bad_limit", f"成员上限最大 {SHARED_MAX_MEMBERS}")
    return mb, mm


def _shared_of(owner_username: str, rel: str):
    """rel 落在哪个共享目录里（含它自己）；一层套一层时取最深的那层。"""
    with _db_lock, get_db() as db:
        rows = db.execute("SELECT * FROM shared_folders WHERE owner_username = ?",
                          (owner_username,)).fetchall()
    best = None
    for r in rows:
        base = r["rel_path"]
        if rel == base or rel.startswith(base + "/"):
            if best is None or len(base) > len(best["rel_path"]):
                best = r
    return best


def _shared_usage(row) -> tuple:
    try:
        return storage.path_size(full_path(row["owner_username"], row["rel_path"]))
    except StorageError:
        return 0, 0


def _share_roots_of(user_id: int) -> list:
    """当前用户可进入的共享目录（不含自己创建的）：被显式授权的，或名单留空（＝全员）的。

    名单留空必须解释成「全员」而不是「没人」：创建者创建时还没有第二个用户，
    之后再注册的人也得能进；否则 UI 上写着「留空＝全员」，实际谁也进不去。
    """
    with _db_lock, get_db() as db:
        rows = db.execute(
            "SELECT f.owner_username, f.rel_path FROM shared_folders f"
            " WHERE f.owner_id != ? AND ("
            "   NOT EXISTS (SELECT 1 FROM shared_grants g WHERE g.folder_id = f.id)"
            "   OR EXISTS (SELECT 1 FROM shared_grants g2"
            "              WHERE g2.folder_id = f.id AND g2.user_id = ?))"
            " ORDER BY f.owner_username, f.rel_path",
            (user_id, user_id),
        ).fetchall()
    return [{"owner": r["owner_username"], "rel": r["rel_path"]} for r in rows]


def _granted_prefixes_of(user_id: int) -> list:
    return [f"/{s['owner']}/{s['rel']}" for s in _share_roots_of(user_id)]


def _foreign_target(user, owner: str, rel_raw, write: bool) -> str:
    """以 owner 身份解析 rel；越权在此拦下，返回规范化后的 rel。

    自己的目录直接放行。他人的目录：rel 必须落在某个已授权共享目录内；
    write=True 时还要求 rel 里出现一段等于本人用户名 —— 也就是每个人在共享目录里
    只能写自己名下那一格（`<共享目录>/…/<自己的用户名>/`），删除权自然等价于上传权。
    """
    rel = normalize_rel_path(rel_raw)
    if owner == user["username"]:
        return rel
    for share in _share_roots_of(user["id"]):
        if share["owner"] != owner:
            continue
        base = share["rel"]
        if rel != base and not rel.startswith(base + "/"):
            continue
        if write and user["username"] not in rel.split("/"):
            continue
        return rel
    raise err(403, "forbidden", "无权访问该共享目录")


def _target(user, rel_raw, owner_raw=None, write: bool = False):
    """→ (owner, rel, full)。owner 缺省为本人；他人的目录必须带授权。"""
    owner = (owner_raw or "").strip() or user["username"]
    rel = _foreign_target(user, owner, rel_raw, write)
    return owner, rel, full_path(owner, rel)


def _owned_shared_paths(db, user) -> set:
    return {r["rel_path"] for r in db.execute(
        "SELECT rel_path FROM shared_folders WHERE owner_id = ?", (user["id"],)).fetchall()}


def _shadows_shared(db, user, rel: str) -> bool:
    """rel 是某个共享目录本身、或是它的上级 —— 改名/移动会让授权记录静默失配。"""
    return any(p == rel or p.startswith(rel + "/") for p in _owned_shared_paths(db, user))


def _members_of(db, folder_id: int) -> list:
    return [r["username"] for r in db.execute(
        "SELECT u.username FROM shared_grants g JOIN users u ON u.id = g.user_id"
        " WHERE g.folder_id = ? ORDER BY u.username", (folder_id,)).fetchall()]


def _member_views_of(db, folder_id: int) -> list:
    """成员名单的展示形态。授权表里只存用户名，勾选列表看不出「alice 是谁」。"""
    return [{"username": r["username"], "nickname": r["nickname"] or r["username"]}
            for r in db.execute(
                "SELECT u.username, u.nickname FROM shared_grants g JOIN users u ON u.id = g.user_id"
                " WHERE g.folder_id = ? ORDER BY u.nickname, u.username",
                (folder_id,)).fetchall()]


def _folder_or_403(db, folder_id: int, user):
    row = db.execute("SELECT * FROM shared_folders WHERE id = ?", (folder_id,)).fetchone()
    if not row:
        raise err(404, "not_found", "共享文件夹不存在")
    if row["owner_username"] != user["username"] and not user["is_admin"]:
        raise err(403, "forbidden", "只有创建者或管理员能修改共享设置")
    return row


def _resolve_members(db, usernames, owner_username: str, limit=None) -> list:
    ids, seen = [], set()
    for name in usernames or []:
        name = (name or "").strip()
        if not name or name == owner_username or name in seen:
            continue
        seen.add(name)
        row = db.execute("SELECT id, status FROM users WHERE username = ?", (name,)).fetchone()
        if not row:
            raise err(400, "bad_member", f"成员不存在：{name}")
        if row["status"] != "active":
            raise err(400, "bad_member", f"成员已被禁用：{name}")
        ids.append(row["id"])
    cap = MAX_SHARED_MEMBERS if limit is None else min(int(limit), MAX_SHARED_MEMBERS)
    if len(ids) > cap:
        raise err(400, "too_many_members", f"成员上限 {cap}")
    return ids


def _set_members(db, folder_id: int, user_ids) -> None:
    db.execute("DELETE FROM shared_grants WHERE folder_id = ?", (folder_id,))
    for uid in user_ids:
        db.execute("INSERT INTO shared_grants (folder_id, user_id, granted_at) VALUES (?,?,?)",
                   (folder_id, uid, now_iso()))


def _usage_by_member(full_root: str, names: set) -> dict:
    """把共享目录的用量按「目录里出现与成员同名的段」切开，返回 {用户名: (字节, 文件数)}。

    落点规则保证成员的文件必在自己的同名子目录下，所以这条切分是准确的；
    创建者自己的文件落在切不到的其余部分（由调用方用总量相减）。
    """
    out = {n: (0, 0) for n in names}
    stack = [(full_root, None)]
    while stack:
        cur, who = stack.pop()
        try:
            entries = storage.list_dir(cur)
        except StorageError:
            continue
        for e in entries:
            sub = f"{cur}/{e['name']}"
            if e["type"] == "dir":
                stack.append((sub, who or (e["name"] if e["name"] in names else None)))
            elif who:
                b, c = out[who]
                out[who] = (b + e["size"], c + 1)
    return out


# ------------------------------------------------------------------ files 组

def _user_full(user, rel_raw, owner_raw=None, write: bool = False) -> tuple[str, str]:
    """路径 → (规范化相对路径, Seafile 完整路径)；越界在此被 paths 层拦下。

    owner 缺省为本人；指定他人时必须是已授权的共享目录，write=True 时还只能落到
    自己名下那一格（见 _foreign_target）。
    """
    _, rel, full = _target(user, rel_raw, owner_raw, write)
    return rel, full


def _is_own_cell(user, owner_raw, rel: str) -> bool:
    """rel 的最后一段是不是本人用户名 —— 也就是「自己那一格」这个文件夹本身。

    那一格的文件夹名就是归属标记：改名/移走会让随后上传的落点算错，
    所以在共享目录里单独拦一条（owner 是本人时不算，自己的同名文件夹照旧可动）。
    """
    owner = (owner_raw or "").strip() or user["username"]
    return bool(rel) and owner != user["username"] and rel.rsplit("/", 1)[-1] == user["username"]


def _cell_rel(user, owner_name: str, path_raw) -> str:
    """他人共享目录里「我那一格」的落点：已经在自己那一格（含其子目录）就原样返回，
    否则补一层 /<用户名>。上传与建夹共用这条规则。

    判定用「共享根 + 我的用户名」当锚点，而不是「路径里出现过我的用户名」：
    创建者恰好有个与我同名的目录时，后者会把我那一格算错、把文件放到共享根上去。
    write=True 的越权校验照旧由 _foreign_target 复核，不在这里绕过。
    """
    base = _foreign_target(user, owner_name, path_raw, write=False)
    for share in _share_roots_of(user["id"]):
        root = share["rel"]
        if share["owner"] != owner_name or not root:
            continue
        cell = f"{root}/{user['username']}"
        if base == cell or base.startswith(cell + "/"):
            return _foreign_target(user, owner_name, base, write=True)
    return _foreign_target(
        user, owner_name, f"{base}/{user['username']}" if base else user["username"],
        write=True)


@app.get("/api/files/list")
def files_list(request: Request, path: str = Query(""), owner: str = Query("")):
    user = require_user(request)
    rel, full = _user_full(user, path, owner)
    entries = storage.list_dir(full)
    return {"path": "/" + rel if rel else "/", "owner": owner or user["username"],
            "entries": entries}


@app.get("/api/files/detail")
def files_detail(request: Request, path: str = Query(""), owner: str = Query("")):
    user = require_user(request)
    rel, full = _user_full(user, path, owner)
    st = storage.stat(full)
    return {"path": "/" + rel if rel else "/", "owner": owner or user["username"], **st}


@app.post("/api/files/mkdir")
def files_mkdir(data: MkdirIn, request: Request, owner: str = Query("")):
    user = require_user(request)
    name = validate_name(data.name)
    owner_name = (owner or "").strip() or user["username"]
    if owner_name != user["username"]:
        # 与上传同一条落点规则：建夹也强制落进自己那一格
        rel = _cell_rel(user, owner_name, data.path)
    else:
        rel = _user_full(user, data.path)[0]
    rel_new = f"{rel}/{name}" if rel else name
    if owner_name != user["username"]:
        try:
            storage.mkdir(full_path(owner_name, rel))
        except StorageConflict:
            pass
    storage.mkdir(full_path(owner_name, rel_new))
    with _db_lock, get_db() as db:
        audit(db, user["id"], "mkdir", "/" + rel_new, None, client_ip(request), "ok",
              "" if owner_name == user["username"] else f"in {owner_name}")
    return {"ok": True, "name": name, "owner": owner_name, "path": rel_new}


@app.post("/api/files/upload")
async def files_upload(request: Request, path: str = Query(""), owner: str = Query(""),
                       on_conflict: str = Query("overwrite"),
                       expected_old_size: int = Query(-1),
                       file: UploadFile = File(...)):
    user = require_user(request)
    dest_owner = (owner or "").strip() or user["username"]
    if dest_owner != user["username"]:
        # 写别人的共享目录：强制落到自己名下那一格。同名冲突与「只能删自己的」两条
        # 都由这个落点规则保证，不另记文件归属。
        rel = _cell_rel(user, dest_owner, path)
    else:
        rel = normalize_rel_path(path)
    full = full_path(dest_owner, rel)
    filename = validate_name(file.filename or "")
    ip = client_ip(request)
    target_display = "/" + (f"{rel}/{filename}" if rel else filename)

    # 先落临时文件（分块流式，内存恒定），同时计大小、查上限
    tmp = tempfile.NamedTemporaryFile(delete=False, prefix="subdrive-up-")
    size = 0
    try:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > MAX_FILE_BYTES:
                tmp.close()
                Path(tmp.name).unlink(missing_ok=True)
                raise err(413, "file_too_large", f"单文件上限 {MAX_FILE_BYTES} 字节")
            tmp.write(chunk)
        tmp.close()

        with _db_lock, get_db() as db:
            used = usage_of(db, user["id"])["used_bytes"]
            quota = quota_of(db, user)
        # 同名文件是覆盖写（storage.upload 直接 wb），旧大小要先从用量里退掉，
        # 否则每覆盖一次配额就多算一份
        prior = 0
        try:
            old = storage.stat(f"{full}/{filename}")
            if old["type"] == "file":
                prior = old["size"]
        except StorageNotFound:
            prior = 0
        if on_conflict not in ("overwrite", "rename"):
            Path(tmp.name).unlink(missing_ok=True)
            raise err(400, "bad_on_conflict", "on_conflict 只能是 overwrite 或 rename")
        # 前端弹窗给用户看的是「旧文件多大」，那就必须按这个前提写：期间被改过就 409，
        # 不静默覆盖别人的新版本（D34）
        if prior and expected_old_size >= 0 and prior != expected_old_size:
            Path(tmp.name).unlink(missing_ok=True)
            with _db_lock, get_db() as db:
                audit(db, user["id"], "upload", target_display, size, ip, "denied", "覆盖前文件已变化")
            raise err(409, "conflict",
                      f"同名文件已被改动（原 {expected_old_size} 字节，现在 {prior} 字节），请重试")
        if on_conflict == "rename" and prior:
            # 「两者都保留」：同目录里换个不冲突的名字，归属仍由目录决定
            filename = _dedup_name(full, filename)
            prior = 0
        if used - prior + size > quota:
            # 往共享目录里传也算自己的用量：配额始终跟着上传者走（D27）
            Path(tmp.name).unlink(missing_ok=True)
            with _db_lock, get_db() as db:
                audit(db, user["id"], "upload", target_display, size, ip, "denied", "超出配额")
            raise err(413, "quota_exceeded", "超出个人配额")

        # 共享目录的每目录容量上限（D35）：算的是整个目录（所有成员的格子）的占用
        share = _shared_of(dest_owner, rel)
        if share is not None:
            cap_bytes, _ = _shared_limits(share)
            cur_bytes, _ = _shared_usage(share)
            if cur_bytes - prior + size > cap_bytes:
                Path(tmp.name).unlink(missing_ok=True)
                with _db_lock, get_db() as db:
                    audit(db, user["id"], "upload", target_display, size, ip, "denied",
                          "共享目录已满")
                raise err(413, "shared_full",
                          f"共享目录容量上限 {cap_bytes} 字节，已用 {cur_bytes - prior}")

        if dest_owner != user["username"]:
            try:
                storage.mkdir(full)
            except StorageConflict:
                pass
        stored = storage.upload(full, filename, Path(tmp.name))
    finally:
        Path(tmp.name).unlink(missing_ok=True)

    with _db_lock, get_db() as db:
        usage_add(db, user["id"], stored - prior, 0 if prior else 1)
        audit(db, user["id"], "upload", target_display, stored, ip, "ok",
              "" if dest_owner == user["username"] else f"in {dest_owner}")
    return {"ok": True, "name": filename, "size": stored, "owner": dest_owner,
            "replaced": bool(prior)}


# 预览用的 MIME 映射（按扩展名）；未列出的回退 mimetypes，再回退 octet-stream
_PREVIEW_MIME = {
    "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "gif": "image/gif",
    "webp": "image/webp", "svg": "image/svg+xml", "bmp": "image/bmp", "avif": "image/avif",
    "pdf": "application/pdf",
    "mp4": "video/mp4", "webm": "video/webm", "mov": "video/quicktime",
    "mp3": "audio/mpeg", "wav": "audio/wav", "flac": "audio/flac",
    "m4a": "audio/mp4", "ogg": "audio/ogg", "aac": "audio/aac",
    "txt": "text/plain; charset=utf-8", "log": "text/plain; charset=utf-8",
    "md": "text/plain; charset=utf-8", "markdown": "text/plain; charset=utf-8",
    "json": "text/plain; charset=utf-8", "csv": "text/plain; charset=utf-8",
}


def _mime_for(name: str) -> str:
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext in _PREVIEW_MIME:
        return _PREVIEW_MIME[ext]
    import mimetypes

    return mimetypes.guess_type(name)[0] or "application/octet-stream"


def _range_span(header: str | None, size: int):
    """解析单段 Range → (start, end_inclusive)；无 Range 返回 None；不可满足抛 416。"""
    if not header:
        return None
    unit, _, rng = header.partition("=")
    if unit.strip() != "bytes" or "," in rng:
        return None  # 非 bytes 单位/多段：忽略，走 200 全量
    start_s, _, end_s = rng.partition("-")
    try:
        if start_s == "":
            n = int(end_s)
            if n <= 0:
                raise ValueError
            return (max(0, size - n), size - 1)
        start = int(start_s)
        end = int(end_s) if end_s else size - 1
        if start >= size or end < start:
            raise ValueError
        return (start, min(end, size - 1))
    except ValueError:
        raise HTTPException(416, detail={"error": "range_not_satisfiable",
                                         "message": "Range 不可满足"},
                            headers={"Content-Range": f"bytes */{size}"})


def _serve_file(request: Request, inline: bool, action: str):
    """下载/预览共用：同一条路径安全与验权链，支持 HTTP Range（音视频拖动、断点续传）。"""
    user = require_user(request)
    path = request.query_params.get("path", "")
    owner = request.query_params.get("owner", "")
    rel, full = _user_full(user, path, owner)
    if rel == "":
        raise err(400, "bad_path", "不能下载根目录")
    st = storage.stat(full)
    if st["type"] != "file":
        raise err(400, "not_a_file", "目标不是文件")
    size = st["size"]
    name = rel.rsplit("/", 1)[-1]
    span = _range_span(request.headers.get("range"), size)
    with _db_lock, get_db() as db:
        audit(db, user["id"], action, "/" + rel, size, client_ip(request), "ok")
    from urllib.parse import quote

    disposition = "inline" if inline else "attachment"
    headers = {
        "Accept-Ranges": "bytes",
        "Content-Disposition": f"{disposition}; filename*=UTF-8''{quote(name)}",
    }
    media = _mime_for(name) if inline else "application/octet-stream"
    if span is None:
        gen, out_size = storage.download_iter(full)
        headers["Content-Length"] = str(out_size)
        return StreamingResponse(gen, media_type=media, headers=headers)
    start, end = span
    gen, out_size = storage.download_iter(full, start, end - start + 1)
    headers["Content-Length"] = str(out_size)
    headers["Content-Range"] = f"bytes {start}-{end}/{size}"
    return StreamingResponse(gen, status_code=206, media_type=media, headers=headers)


@app.get("/api/files/download")
def files_download(request: Request, path: str = Query(...)):
    return _serve_file(request, inline=False, action="download")


@app.get("/api/files/preview")
def files_preview(request: Request, path: str = Query(...)):
    return _serve_file(request, inline=True, action="preview")


@app.post("/api/files/rename")
def files_rename(data: RenameIn, request: Request, owner: str = Query("")):
    user = require_user(request)
    # write=True：他人目录里只能动自己那一格里的东西（与上传/建夹同一条归属规则）
    rel, full = _user_full(user, data.path, owner, write=True)
    if rel == "":
        raise err(400, "bad_path", "根文件夹（用户名）禁止改名")
    if _is_own_cell(user, owner, rel):
        raise err(400, "cell_rename", "不能改自己那一格的文件夹名：它就是你在共享目录里的归属标记")
    new_name = validate_name(data.new_name)
    with _db_lock, get_db() as db:
        if _shadows_shared(db, user, rel):
            raise err(400, "shared_rename",
                      "这是共享文件夹（或其上级）：请先取消共享再改名，避免授权失配")
    storage.rename(full, new_name)
    with _db_lock, get_db() as db:
        audit(db, user["id"], "rename", "/" + rel, None, client_ip(request), "ok",
              f"-> {new_name}")
    return {"ok": True, "name": new_name}


@app.post("/api/files/move")
def files_move(data: MoveIn, request: Request, owner: str = Query("")):
    user = require_user(request)
    rel, full = _user_full(user, data.path, owner, write=True)
    if rel == "":
        raise err(400, "bad_path", "根文件夹禁止移动")
    if _is_own_cell(user, owner, rel):
        raise err(400, "cell_move", "不能移动自己那一格的文件夹：它就是你在共享目录里的归属标记")
    drel, dfull = _user_full(user, data.dest_dir, owner, write=True)
    with _db_lock, get_db() as db:
        if _shadows_shared(db, user, rel):
            raise err(400, "shared_move",
                      "这是共享文件夹（或其上级）：请先取消共享再移动，避免授权失配")
    storage.move(full, dfull)
    with _db_lock, get_db() as db:
        audit(db, user["id"], "move", "/" + rel, None, client_ip(request), "ok",
              f"-> /{drel}")
    return {"ok": True}


@app.post("/api/files/delete")
def files_delete(data: DeleteIn, request: Request, owner: str = Query("")):
    user = require_user(request)
    rel, full = _user_full(user, data.path, owner, write=True)
    if rel == "":
        raise err(400, "bad_path", "根文件夹禁止删除")
    with _db_lock, get_db() as db:
        if _shadows_shared(db, user, rel):
            raise err(400, "shared_delete",
                      "这是共享文件夹（或其上级）：请用「取消共享」删除，否则其他成员的文件会一起消失")
    freed, count = storage.path_size(full)  # 先算记账再删
    storage.delete(full)
    with _db_lock, get_db() as db:
        usage_add(db, user["id"], -freed, -count)
        audit(db, user["id"], "delete", "/" + rel, freed, client_ip(request), "ok")
    return {"ok": True, "freed_bytes": freed}


# ------------------------------------------------------------------ shared 组

@app.post("/api/shared/create")
def shared_create(data: SharedCreateIn, request: Request):
    # B1：只有管理员能创建共享文件夹（收口「人人可开公开目录」）；管理名单仍见 shared_members
    user = require_admin(request)
    rel, full = _user_full(user, data.path)
    if rel == "":
        raise err(400, "bad_path", "根目录不能设为共享文件夹")
    if storage.stat(full)["type"] != "dir":
        raise err(400, "not_a_dir", "只能共享文件夹")
    with _db_lock, get_db() as db:
        dup = db.execute("SELECT id FROM shared_folders WHERE owner_id = ? AND rel_path = ?",
                         (user["id"], rel)).fetchone()
        if dup:
            raise err(409, "already_shared", "该文件夹已经共享过了")
        mb, mm = _clamp_limits(data.max_bytes, data.max_members)
        ids = _resolve_members(db, data.members, user["username"], mm)
        if len(ids) > mm:
            raise err(400, "too_many_members", f"成员上限 {mm}")
        cur = db.execute(
            "INSERT INTO shared_folders (owner_id, owner_username, rel_path, created_at,"
            " max_bytes, max_members) VALUES (?,?,?,?,?,?)",
            (user["id"], user["username"], rel, now_iso(), mb, mm))
        fid = cur.lastrowid
        _set_members(db, fid, ids)
        audit(db, user["id"], "share", "/" + rel, None, client_ip(request), "ok",
              f"members={len(ids)}")
    return {"ok": True, "id": fid, "path": rel}


@app.get("/api/shared/list")
def shared_list(request: Request):
    user = require_user(request)
    out = []
    with _db_lock, get_db() as db:
        mine = db.execute("SELECT * FROM shared_folders WHERE owner_id = ? ORDER BY rel_path",
                          (user["id"],)).fetchall()
        granted = db.execute(
            "SELECT f.* FROM shared_folders f WHERE f.owner_id != ? AND ("
            "   NOT EXISTS (SELECT 1 FROM shared_grants g WHERE g.folder_id = f.id)"
            "   OR EXISTS (SELECT 1 FROM shared_grants g2"
            "              WHERE g2.folder_id = f.id AND g2.user_id = ?))"
            " ORDER BY f.owner_username, f.rel_path",
            (user["id"], user["id"])).fetchall()
        rows = [(r, True) for r in mine] + [(r, False) for r in granted]
        members = {r["id"]: _members_of(db, r["id"]) for r, _ in rows}
        member_details = {r["id"]: _member_views_of(db, r["id"]) for r, _ in rows}

    for row, is_mine in rows:
        full = full_path(row["owner_username"], row["rel_path"])
        try:
            size, count = storage.path_size(full)
        except StorageError:
            size, count = 0, 0
        item = {
            "id": row["id"],
            "owner": row["owner_username"],
            "path": row["rel_path"],
            "is_mine": is_mine,
            "members": members[row["id"]],
            "member_details": member_details[row["id"]],
            "bytes": size,
            "files": count,
            "max_bytes": _shared_limits(row)[0],
            "max_members": _shared_limits(row)[1],
        }
        if is_mine:
            # 只有创建者看得到「每人占了多少」，这也是删文件夹时回冲的依据
            item["by_member"] = {
                name: {"bytes": b, "files": c}
                for name, (b, c) in _usage_by_member(full, set(members[row["id"]])).items()
            }
        out.append(item)
    # 界面上「留空＝默认多少」要说真话，所以默认值与硬顶随列表一起下发
    return {"folders": out, "defaults": {
        "max_bytes": SHARED_MAX_BYTES,
        "max_members": SHARED_MAX_MEMBERS,
        "hard_members": MAX_SHARED_MEMBERS,
    }}


@app.post("/api/shared/{folder_id}/members")
def shared_set_members(folder_id: int, data: SharedMembersIn, request: Request):
    user = require_user(request)
    with _db_lock, get_db() as db:
        row = _folder_or_403(db, folder_id, user)
        _, mm = _shared_limits(row)
        ids = _resolve_members(db, data.members, row["owner_username"], mm)
        _set_members(db, folder_id, ids)
        names = _members_of(db, folder_id)
        audit(db, user["id"], "share_members", "/" + row["rel_path"], None,
              client_ip(request), "ok", f"members={len(ids)}")
    return {"ok": True, "id": folder_id, "members": names}


@app.patch("/api/shared/{folder_id}")
def shared_limits(folder_id: int, data: SharedLimitsIn, request: Request):
    """改每目录上限（D35）：创建者或管理员，且不能把已有成员挤出上限。"""
    user = require_user(request)
    with _db_lock, get_db() as db:
        row = _folder_or_403(db, folder_id, user)
        cur_mb, cur_mm = _shared_limits(row)
        mb, mm = _clamp_limits(
            cur_mb if data.max_bytes is None else data.max_bytes,
            cur_mm if data.max_members is None else data.max_members)
        have = db.execute("SELECT COUNT(*) AS c FROM shared_grants WHERE folder_id = ?",
                          (folder_id,)).fetchone()["c"]
        if have > mm:
            raise err(400, "too_many_members", f"现有成员 {have} 人，超过要设的上限 {mm}")
        db.execute("UPDATE shared_folders SET max_bytes = ?, max_members = ? WHERE id = ?",
                   (mb, mm, folder_id))
        audit(db, user["id"], "share_limits", "/" + row["rel_path"], None,
              client_ip(request), "ok", f"bytes={mb} members={mm}")
    return {"ok": True, "id": folder_id, "max_bytes": mb, "max_members": mm}


@app.delete("/api/shared/{folder_id}")
def shared_revoke(folder_id: int, request: Request):
    """取消共享：退回私有文件夹，内容全员保留（D27）。"""
    user = require_user(request)
    with _db_lock, get_db() as db:
        row = _folder_or_403(db, folder_id, user)
        db.execute("DELETE FROM shared_grants WHERE folder_id = ?", (folder_id,))
        db.execute("DELETE FROM shared_folders WHERE id = ?", (folder_id,))
        audit(db, user["id"], "unshare", "/" + row["rel_path"], None, client_ip(request), "ok")
    return {"ok": True}


# ------------------------------------------------------------------ quota 组

@app.get("/api/quota")
def quota(request: Request):
    user = require_user(request)
    with _db_lock, get_db() as db:
        usage = usage_of(db, user["id"])
        q = quota_of(db, user)
    return {
        "used_bytes": usage["used_bytes"],
        "quota_bytes": q,
        "file_count": usage["file_count"],
        "calibrated_at": usage["calibrated_at"],
    }


# ------------------------------------------------------------------ 测速组
# 上下行测速：字节只在内存里生成/丢弃——不写存储、不计配额；每用户同时只允许一个测速。

_speed_locks: dict[int, threading.Lock] = {}
_speed_locks_guard = threading.Lock()
_SPEED_BLOCK = bytes(range(256)) * 4096  # 1 MiB 固定图案块，循环发出


def _speed_acquire(user_id: int):
    with _speed_locks_guard:
        lock = _speed_locks.setdefault(user_id, threading.Lock())
    if lock.acquire(blocking=False):
        return lock
    return None


def _speed_size(mb: float | None) -> int:
    if mb is None or mb <= 0:
        return SPEEDTEST_DEFAULT_BYTES
    n = int(mb * 1024 * 1024)
    return max(1024 * 1024, min(n, SPEEDTEST_MAX_BYTES))


@app.get("/api/speed/download")
def speed_download(request: Request, mb: float = Query(None)):
    user = require_user(request)
    n = _speed_size(mb)
    lock = _speed_acquire(user["id"])
    if lock is None:
        raise err(409, "speedtest_busy", "已有测速在进行中，请等它结束")
    with _db_lock, get_db() as db:
        audit(db, user["id"], "speedtest_download", "", n, client_ip(request), "ok")

    def gen():
        try:
            sent = 0
            while sent < n:
                chunk = _SPEED_BLOCK[: min(len(_SPEED_BLOCK), n - sent)]
                sent += len(chunk)
                yield chunk
        finally:
            lock.release()

    return StreamingResponse(
        gen(), media_type="application/octet-stream",
        headers={"Content-Length": str(n), "X-Speedtest-Bytes": str(n),
                 "X-Storage-Mode": STORAGE_MODE, "Cache-Control": "no-store"},
    )


@app.post("/api/speed/upload")
async def speed_upload(request: Request):
    user = require_user(request)
    lock = _speed_acquire(user["id"])
    if lock is None:
        raise err(409, "speedtest_busy", "已有测速在进行中，请等它结束")
    total = 0
    try:
        async for chunk in request.stream():
            total += len(chunk)
            if total > SPEEDTEST_MAX_BYTES:
                raise err(413, "speedtest_too_large",
                          f"测速上传上限 {SPEEDTEST_MAX_BYTES} 字节")
    finally:
        lock.release()
    with _db_lock, get_db() as db:
        audit(db, user["id"], "speedtest_upload", "", total, client_ip(request), "ok")
    return {"received_bytes": total, "stored": False, "mode": STORAGE_MODE}


# ------------------------------------------------------------------ admin 组

def _admin_user_view(db, row) -> dict:
    usage = usage_of(db, row["id"])
    out = user_public(row)
    out["quota_bytes"] = quota_of(db, row)
    out["used_bytes"] = usage["used_bytes"]
    out["file_count"] = usage["file_count"]
    out["invite_code_id"] = row["invite_code_id"]
    out["folder_created"] = bool(row["folder_created"])
    return out


@app.get("/api/admin/users")
def admin_users(request: Request):
    admin = require_admin(request)
    with _db_lock, get_db() as db:
        rows = db.execute("SELECT * FROM users ORDER BY id").fetchall()
        return [_admin_user_view(db, r) for r in rows]


@app.get("/api/users/directory")
def users_directory(request: Request):
    """给授权成员勾选列表用：只回显用户名与昵称，不带配额/用量。
    B1 之后能建共享与改名单的都是管理员，所以这道门跟着管理员走。"""
    require_admin(request)
    with _db_lock, get_db() as db:
        rows = db.execute("SELECT username, nickname, status FROM users ORDER BY username").fetchall()
    return [{"username": r["username"],
             "nickname": r["nickname"] or r["username"],
             "disabled": r["status"] != "active"} for r in rows]


@app.post("/api/admin/users/{user_id}/disable")
def admin_disable(user_id: int, request: Request):
    admin = require_admin(request)
    with _db_lock, get_db() as db:
        target = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if not target:
            raise err(404, "not_found", "用户不存在")
        db.execute("UPDATE users SET status = 'disabled' WHERE id = ?", (user_id,))
        db.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))  # 立即失效
        audit(db, admin["id"], "admin_disable", f"/{target['username']}", None,
              client_ip(request), "ok")
    return {"ok": True}


@app.post("/api/admin/users/{user_id}/enable")
def admin_enable(user_id: int, request: Request):
    admin = require_admin(request)
    with _db_lock, get_db() as db:
        target = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if not target:
            raise err(404, "not_found", "用户不存在")
        db.execute("UPDATE users SET status = 'active' WHERE id = ?", (user_id,))
        audit(db, admin["id"], "admin_enable", f"/{target['username']}", None,
              client_ip(request), "ok")
    return {"ok": True}


@app.post("/api/admin/users/{user_id}/quota")
def admin_set_quota(user_id: int, data: QuotaIn, request: Request):
    admin = require_admin(request)
    with _db_lock, get_db() as db:
        target = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if not target:
            raise err(404, "not_found", "用户不存在")
        db.execute("UPDATE users SET quota_bytes = ? WHERE id = ?",
                   (data.quota_bytes, user_id))
        audit(db, admin["id"], "admin_quota", f"/{target['username']}", None,
              client_ip(request), "ok", f"quota={data.quota_bytes}")
    return {"ok": True}


@app.post("/api/admin/users/{user_id}/admin")
def admin_set_admin(user_id: int, data: AdminFlagIn, request: Request):
    admin = require_admin(request)
    if not is_owner(admin):
        raise err(403, "owner_required", "仅系统所有者可变更管理员")
    with _db_lock, get_db() as db:
        target = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if not target:
            raise err(404, "not_found", "用户不存在")
        if not data.is_admin and is_owner(target):
            raise err(400, "owner_protected", "系统所有者的管理员权限不可取消")
        if not data.is_admin and target["is_admin"]:
            admins = db.execute(
                "SELECT COUNT(*) AS c FROM users WHERE is_admin = 1").fetchone()["c"]
            if admins <= 1:
                raise err(400, "last_admin", "不能取消最后一位管理员的管理员权限")
        db.execute("UPDATE users SET is_admin = ? WHERE id = ?",
                   (1 if data.is_admin else 0, user_id))
        audit(db, admin["id"], "admin_promote" if data.is_admin else "admin_demote",
              f"/{target['username']}", None, client_ip(request), "ok")
    return {"ok": True}


@app.post("/api/admin/users/{user_id}/recalibrate")
def admin_recalibrate(user_id: int, request: Request):
    admin = require_admin(request)
    result = calibrate_user(user_id)
    with _db_lock, get_db() as db:
        audit(db, admin["id"], "admin_recalibrate", "", None, client_ip(request), "ok",
              f"user={user_id}")
    return result


@app.get("/api/admin/invite-codes")
def admin_invites(request: Request):
    admin = require_admin(request)
    with _db_lock, get_db() as db:
        rows = db.execute("SELECT * FROM invite_codes ORDER BY id DESC").fetchall()
        out = []
        for r in rows:
            d = dict(r)
            if d["status"] == "active" and d["expires_at"] and d["expires_at"] <= now_iso():
                d["status"] = "expired"
            out.append(d)
        return out


@app.post("/api/admin/invite-codes")
def admin_create_invite(data: InviteCreateIn, request: Request):
    admin = require_admin(request)
    code = new_invite_code()
    expires = None
    if data.expires_days:
        expires = (now_dt() + timedelta(days=data.expires_days)).isoformat()
    with _db_lock, get_db() as db:
        cur = db.execute(
            "INSERT INTO invite_codes (code, created_by, note, max_uses, expires_at, created_at)"
            " VALUES (?,?,?,?,?,?)",
            (code, admin["id"], data.note.strip()[:100], max(1, data.max_uses), expires, now_iso()),
        )
        audit(db, admin["id"], "admin_invite_create", "", None, client_ip(request), "ok", code[:7] + "…")
        row = db.execute("SELECT * FROM invite_codes WHERE id = ?", (cur.lastrowid,)).fetchone()
    return dict(row)


@app.post("/api/admin/invite-codes/{code_id}/revoke")
def admin_revoke_invite(code_id: int, request: Request):
    admin = require_admin(request)
    with _db_lock, get_db() as db:
        row = db.execute("SELECT * FROM invite_codes WHERE id = ?", (code_id,)).fetchone()
        if not row:
            raise err(404, "not_found", "邀请码不存在")
        db.execute("UPDATE invite_codes SET status = 'revoked' WHERE id = ?", (code_id,))
        audit(db, admin["id"], "admin_invite_revoke", "", None, client_ip(request), "ok")
    return {"ok": True}


@app.get("/api/admin/usage")
def admin_usage(request: Request):
    admin = require_admin(request)
    with _db_lock, get_db() as db:
        rows = db.execute(
            "SELECT u.username, c.used_bytes, c.file_count FROM users u"
            " LEFT JOIN usage_cache c ON c.user_id = u.id ORDER BY u.id").fetchall()
        total = sum(r["used_bytes"] or 0 for r in rows)
    return {"users": [dict(r) for r in rows], "total_used_bytes": total}


# ------------------------------------------------------------------ 静态前端

@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
