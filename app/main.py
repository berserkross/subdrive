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

from app.paths import USERNAME_RE, PathRejected, full_path, normalize_rel_path, validate_name, validate_username
from app.storage import StorageError, make_storage

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
            """
        )


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


# ------------------------------------------------------------------ files 组

def _user_full(user, rel_raw) -> tuple[str, str]:
    """用户路径 → (规范化相对路径, Seafile 完整路径)；越界在此被 paths 层拦下。"""
    rel = normalize_rel_path(rel_raw)
    return rel, full_path(user["username"], rel)


@app.get("/api/files/list")
def files_list(request: Request, path: str = Query("")):
    user = require_user(request)
    rel, full = _user_full(user, path)
    if rel == "":
        pass  # 根目录即用户自己的文件夹
    entries = storage.list_dir(full)
    return {"path": "/" + rel if rel else "/", "entries": entries}


@app.get("/api/files/detail")
def files_detail(request: Request, path: str = Query("")):
    user = require_user(request)
    rel, full = _user_full(user, path)
    st = storage.stat(full)
    return {"path": "/" + rel if rel else "/", **st}


@app.post("/api/files/mkdir")
def files_mkdir(data: MkdirIn, request: Request):
    user = require_user(request)
    name = validate_name(data.name)
    rel, full = _user_full(user, data.path)
    target = full_path(user["username"], f"{rel}/{name}" if rel else name)
    storage.mkdir(target)
    with _db_lock, get_db() as db:
        audit(db, user["id"], "mkdir", "/" + (f"{rel}/{name}" if rel else name),
              None, client_ip(request), "ok")
    return {"ok": True, "name": name}


@app.post("/api/files/upload")
async def files_upload(request: Request, path: str = Query(""),
                       file: UploadFile = File(...)):
    user = require_user(request)
    rel, full = _user_full(user, path)
    filename = validate_name(file.filename or "")
    ip = client_ip(request)

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
        if used + size > quota:
            Path(tmp.name).unlink(missing_ok=True)
            with _db_lock, get_db() as db:
                audit(db, user["id"], "upload", "/" + (f"{rel}/{filename}" if rel else filename),
                      size, ip, "denied", "超出配额")
            raise err(413, "quota_exceeded", "超出个人配额")

        stored = storage.upload(full, filename, Path(tmp.name))
    finally:
        Path(tmp.name).unlink(missing_ok=True)

    with _db_lock, get_db() as db:
        usage_add(db, user["id"], stored, 1)
        audit(db, user["id"], "upload", "/" + (f"{rel}/{filename}" if rel else filename),
              stored, ip, "ok")
    return {"ok": True, "name": filename, "size": stored}


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
    rel, full = _user_full(user, path)
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
def files_rename(data: RenameIn, request: Request):
    user = require_user(request)
    rel, full = _user_full(user, data.path)
    if rel == "":
        raise err(400, "bad_path", "根文件夹（用户名）禁止改名")
    new_name = validate_name(data.new_name)
    storage.rename(full, new_name)
    with _db_lock, get_db() as db:
        audit(db, user["id"], "rename", "/" + rel, None, client_ip(request), "ok",
              f"-> {new_name}")
    return {"ok": True, "name": new_name}


@app.post("/api/files/move")
def files_move(data: MoveIn, request: Request):
    user = require_user(request)
    rel, full = _user_full(user, data.path)
    if rel == "":
        raise err(400, "bad_path", "根文件夹禁止移动")
    drel, dfull = _user_full(user, data.dest_dir)
    storage.move(full, dfull)
    with _db_lock, get_db() as db:
        audit(db, user["id"], "move", "/" + rel, None, client_ip(request), "ok",
              f"-> /{drel}")
    return {"ok": True}


@app.post("/api/files/delete")
def files_delete(data: DeleteIn, request: Request):
    user = require_user(request)
    rel, full = _user_full(user, data.path)
    if rel == "":
        raise err(400, "bad_path", "根文件夹禁止删除")
    freed, count = storage.path_size(full)  # 先算记账再删
    storage.delete(full)
    with _db_lock, get_db() as db:
        usage_add(db, user["id"], -freed, -count)
        audit(db, user["id"], "delete", "/" + rel, freed, client_ip(request), "ok")
    return {"ok": True, "freed_bytes": freed}


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
