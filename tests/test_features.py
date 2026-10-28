"""子用户网盘 · 新功能测试（F1 加密文件夹 / F2 测速 / F3 预览与 Range / F4 管理员提升与取消）。

在 stub 模式下运行，不接触真实 Seafile。原 23 项冒烟在 test_smoke.py，保持独立。
F1 部分把测试自身当作第二个 SDV1 客户端实现（Python cryptography），
与网页端 vault.js 互为交叉验证；格式见 CRYPTO.md。
"""
import hashlib
import json
import os
import secrets
import sys
import tempfile
from pathlib import Path

# Windows 控制台默认 GBK，最后打印 ✅ 会抛 UnicodeEncodeError 把整轮测试拖成失败退出。
# 统一走 UTF-8 输出（Linux 沙箱下是无操作）。
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

tmp = tempfile.mkdtemp(prefix="subdrive-features-")
os.environ["DATA_DIR"] = tmp
os.environ["SEAFILE_MODE"] = "stub"
os.environ["CALIBRATE_INTERVAL_SECONDS"] = "0"
# 测试环境的所有者（只设用户名、不设密码 → bootstrap 不预建号，boss 仍走首用户注册）
os.environ["SUBDRIVE_ADMIN_USERNAME"] = "boss"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from fastapi.testclient import TestClient
from app.main import app, get_db, _db_lock

PASSED = []


def check(name, cond, extra=""):
    assert cond, f"FAIL: {name} {extra}"
    PASSED.append(name)
    print(f"{len(PASSED):2d}. {name} OK")


def auth(token):
    return {"Authorization": f"Bearer {token}"}


# ---------------- SDV1 参考客户端（与 tools/gen_vector.py 同格式） ----------------

def derive_key(password: str, salt: bytes, iterations: int) -> bytes:
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=iterations)
    return kdf.derive(password.encode("utf-8"))


def envelope(key: bytes, plaintext: bytes) -> bytes:
    iv = secrets.token_bytes(12)
    return b"SDV1" + bytes([1]) + iv + AESGCM(key).encrypt(iv, plaintext, None)


def open_envelope(key: bytes, blob: bytes) -> bytes:
    assert blob[:4] == b"SDV1" and blob[4] == 1
    return AESGCM(key).decrypt(blob[5:17], blob[17:], None)


CHECK_PT = b"SUBDRIVE-VAULT-CHECK-v1"


def make_descriptor(password: str, iterations: int = 210_000) -> tuple[bytes, bytes]:
    salt = secrets.token_bytes(16)
    key = derive_key(password, salt, iterations)
    import base64
    desc = {
        "format": "subdrive-vault", "version": 1,
        "kdf": {"algo": "PBKDF2-SHA256", "iterations": iterations,
                "salt": base64.b64encode(salt).decode()},
        "check": base64.b64encode(envelope(key, CHECK_PT)).decode(),
        "created_at": "2026-10-22T00:00:00+00:00",
    }
    return json.dumps(desc).encode(), key


def upload_bytes(c, token, dir_path, filename, data: bytes):
    r = c.post("/api/files/upload", params={"path": dir_path}, headers=auth(token),
               files={"file": (filename, data, "application/octet-stream")})
    assert r.status_code == 200, (filename, r.text)
    return r.json()["size"]


def download_bytes(c, token, path) -> bytes:
    r = c.get("/api/files/download", params={"path": path}, headers=auth(token))
    assert r.status_code == 200, (path, r.text)
    return r.content


def f1_encrypted_folders(c, admin_token, stub_lib):
    print("\n— F1 加密文件夹 —")
    # 注册 vault 用户
    r = c.post("/api/admin/invite-codes", headers=auth(admin_token), json={"note": "vault"})
    code = r.json()["code"]
    r = c.post("/api/auth/register", json={"username": "vaultuser", "password": "vaultpass1",
                                           "invite_code": code})
    assert r.status_code == 200, r.text
    tok = r.json()["token"]
    uid = r.json()["user"]["id"]

    folder_pw = "folder-secret-42"
    desc_bytes, key = make_descriptor(folder_pw)
    r = c.post("/api/files/mkdir", headers=auth(tok), json={"path": "", "name": "保险箱"})
    assert r.status_code == 200, r.text
    s_desc = upload_bytes(c, tok, "保险箱", ".sdvault.json", desc_bytes)
    r = c.post("/api/files/mkdir", headers=auth(tok), json={"path": "保险箱", "name": "blobs"})
    assert r.status_code == 200, r.text
    manifest = {"version": 1, "files": []}
    s_man0 = upload_bytes(c, tok, "保险箱", "manifest.enc",
                          envelope(key, json.dumps(manifest).encode()))

    # 加密一个含醒目标记的文件（文件名与内容都必须在后端不可见）
    secret_name = "绝密计划-Ω.txt"
    secret_body = ("绝密内容 TOP-SECRET " + secrets.token_hex(24)).encode()
    blob_id = secrets.token_hex(16)
    blob = envelope(key, secret_body)
    s_blob = upload_bytes(c, tok, "保险箱/blobs", blob_id + ".enc", blob)
    assert s_blob == len(secret_body) + 33
    manifest["files"].append({"id": blob_id, "name": secret_name, "size": len(secret_body),
                               "mime": "text/plain", "added_at": "2026-10-22T00:00:00+00:00"})
    s_man = upload_bytes(c, tok, "保险箱", "manifest.enc",
                         envelope(key, json.dumps(manifest, ensure_ascii=False).encode()))
    # 清单被覆盖写：用量应按最终一份计（stub 覆盖语义）——删除旧账以实测为准，见配额断言

    # 往返：下载 blob → 解密 → 字节一致；清单解密得到显示名
    got = download_bytes(c, tok, f"保险箱/blobs/{blob_id}.enc")
    check("F1 密文往返解密字节一致", open_envelope(key, got) == secret_body)
    man_pt = open_envelope(key, download_bytes(c, tok, "保险箱/manifest.enc"))
    man = json.loads(man_pt)
    check("F1 清单含显示名映射", man["files"][0]["name"] == secret_name
          and man["files"][0]["id"] == blob_id)

    # 错误密码：派生密钥不同，解 check 与文件都失败
    import base64
    desc = json.loads(desc_bytes)
    wrong_key = derive_key("wrong-password", base64.b64decode(desc["kdf"]["salt"]),
                           desc["kdf"]["iterations"])
    failed = False
    try:
        open_envelope(wrong_key, base64.b64decode(desc["check"]))
    except InvalidTag:
        failed = True
    check("F1 错误密码被拒绝（check 解密失败）", failed)
    failed2 = False
    try:
        open_envelope(wrong_key, got)
    except InvalidTag:
        failed2 = True
    check("F1 错误密码解不开文件", failed2)

    # 后端存储零明文：扫描 stub 里该用户全部文件内容与文件名
    user_dir = stub_lib / "vaultuser"
    all_bytes = b""
    names = []
    for p in user_dir.rglob("*"):
        names.append(p.name)
        if p.is_file():
            all_bytes += p.read_bytes()
    check("F1 后端无明文内容", secret_body not in all_bytes
          and "绝密内容".encode() not in all_bytes and b"TOP-SECRET" not in all_bytes)
    check("F1 后端无明文文件名", all(secret_name not in n and "绝密" not in n for n in names),
          str(names))
    stored_blob = user_dir / "保险箱" / "blobs" / (blob_id + ".enc")
    check("F1 blob 以不透明名存储且大小=明文+33", stored_blob.is_file()
          and stored_blob.stat().st_size == len(secret_body) + 33)

    # 配额按密文计：覆盖写只记增量（旧版本先退再记新大小，否则每覆盖一次配额就多算一份，
    # D27 之后共享目录里的文件也这样记），校准轨对齐磁盘真实占用
    q = c.get("/api/quota", headers=auth(tok)).json()
    incremental = s_desc + s_man + s_blob
    check("F1 配额按密文大小记账（增量轨，覆盖写不重复计）", q["used_bytes"] == incremental,
          f'{q["used_bytes"]} != {incremental}')
    r = c.post(f"/api/admin/users/{uid}/recalibrate", headers=auth(admin_token))
    assert r.status_code == 200, r.text
    expected = s_desc + s_man + s_blob
    check("F1 校准后用量=密文真实占用", r.json()["used_bytes"] == expected,
          f'{r.json()["used_bytes"]} != {expected}')
    # 把配额压到当前真实用量 +8 字节，再传一个 64 字节 blob 必须被拒
    c.post(f"/api/admin/users/{uid}/quota", headers=auth(admin_token),
           json={"quota_bytes": expected + 8})
    r = c.post("/api/files/upload", params={"path": "保险箱/blobs"}, headers=auth(tok),
               files={"file": ("deadbeef.enc", b"X" * 64, "application/octet-stream")})
    check("F1 配额对密文同样执法", r.status_code == 413, r.text)
    c.post(f"/api/admin/users/{uid}/quota", headers=auth(admin_token),
           json={"quota_bytes": None})
    return tok, uid


def f2_speedtest(c, admin_token, stub_lib):
    print("\n— F2 上下行测速 —")
    r = c.post("/api/admin/invite-codes", headers=auth(admin_token), json={"note": "speed"})
    code = r.json()["code"]
    r = c.post("/api/auth/register", json={"username": "speedy", "password": "speedpass1",
                                           "invite_code": code})
    assert r.status_code == 200, r.text
    tok = r.json()["token"]

    # 未登录不可测速
    r = c.get("/api/speed/download", params={"mb": 1})
    a = r.status_code
    r = c.post("/api/speed/upload", content=b"x" * 1024)
    check("F2 测速端点要求登录", a == 401 and r.status_code == 401, f"{a}/{r.status_code}")

    # 下载：字节数精确
    r = c.get("/api/speed/download", params={"mb": 2}, headers=auth(tok))
    assert r.status_code == 200, r.text
    check("F2 下载测速字节数精确", len(r.content) == 2 * 1024 * 1024
          and r.headers.get("x-speedtest-bytes") == str(2 * 1024 * 1024),
          r.headers.get("x-speedtest-bytes"))

    # 上传：全量接收、不落盘、不计配额
    before_q = c.get("/api/quota", headers=auth(tok)).json()
    files_before = sorted(p.name for p in (stub_lib / "speedy").rglob("*"))
    payload = secrets.token_bytes(1_500_000)
    r = c.post("/api/speed/upload", headers={**auth(tok), "Content-Type": "application/octet-stream"},
               content=payload)
    assert r.status_code == 200, r.text
    after_q = c.get("/api/quota", headers=auth(tok)).json()
    files_after = sorted(p.name for p in (stub_lib / "speedy").rglob("*"))
    check("F2 上传测速全量接收", r.json()["received_bytes"] == len(payload)
          and r.json()["stored"] is False, r.text)
    check("F2 上传测速不计配额不落盘", after_q == before_q and files_after == files_before,
          f"{before_q} -> {after_q}")

    # 并发限制：一路下载流挂住时，第二路（上传）必须 409；结束后恢复
    import threading
    started = threading.Event()
    release = threading.Event()
    stream_result = {}

    def hold_stream():
        try:
            with c.stream("GET", "/api/speed/download?mb=50", headers=auth(tok)) as resp:
                stream_result["status"] = resp.status_code
                for chunk in resp.iter_bytes():
                    if chunk:
                        started.set()
                        release.wait(timeout=15)
        except Exception as e:  # pragma: no cover
            stream_result["error"] = str(e)

    th = threading.Thread(target=hold_stream, daemon=True)
    th.start()
    assert started.wait(timeout=15), "下载流未能启动"
    r = c.post("/api/speed/upload", headers=auth(tok), content=b"y" * 4096)
    busy_ok = r.status_code == 409
    release.set()
    th.join(timeout=20)
    check("F2 同一用户并发测速被拒 409", busy_ok and stream_result.get("status") == 200,
          f"busy={r.status_code} stream={stream_result}")
    r = c.post("/api/speed/upload", headers=auth(tok), content=b"z" * 2048)
    check("F2 测速结束后锁释放", r.status_code == 200
          and r.json()["received_bytes"] == 2048, r.text)


def f3_previews(c, admin_token, stub_lib):
    print("\n— F3 预览与 Range —")
    r = c.post("/api/admin/invite-codes", headers=auth(admin_token), json={"note": "viewer"})
    code = r.json()["code"]
    r = c.post("/api/auth/register", json={"username": "viewer", "password": "viewerpass1",
                                           "invite_code": code})
    assert r.status_code == 200, r.text
    tok = r.json()["token"]

    png = b"\x89PNG\r\n\x1a\n" + secrets.token_bytes(200)
    pdf = b"%PDF-1.4\n" + secrets.token_bytes(120)
    txt = "纯文本预览 · hello preview\n第二行".encode()
    md = "# 标题\n\n- 列表项\n\n<script>alert(1)</script>\n".encode()
    mp3 = b"\xff\xfb" + secrets.token_bytes(400)
    payload = bytes(range(256)) * 4  # 1024 字节确定性内容，供 Range 切片比对
    for name, data in [("photo.png", png), ("report.pdf", pdf), ("note.txt", txt),
                       ("readme.md", md), ("song.mp3", mp3), ("data.bin", payload)]:
        upload_bytes(c, tok, "", name, data)

    # 预览端点要求登录
    r = c.get("/api/files/preview", params={"path": "note.txt"})
    check("F3 预览要求登录", r.status_code == 401, str(r.status_code))

    # 内容类型与 inline
    r = c.get("/api/files/preview", params={"path": "note.txt"}, headers=auth(tok))
    ct_ok = r.headers.get("content-type", "").startswith("text/plain")
    cd_ok = r.headers.get("content-disposition", "").startswith("inline")
    check("F3 文本预览类型与 inline", r.status_code == 200 and ct_ok and cd_ok
          and r.content == txt, r.headers.get("content-type"))
    r = c.get("/api/files/preview", params={"path": "photo.png"}, headers=auth(tok))
    check("F3 图片预览类型", r.headers.get("content-type") == "image/png" and r.content == png)
    r = c.get("/api/files/preview", params={"path": "report.pdf"}, headers=auth(tok))
    check("F3 PDF 预览类型", r.headers.get("content-type") == "application/pdf" and r.content == pdf)
    r = c.get("/api/files/preview", params={"path": "readme.md"}, headers=auth(tok))
    check("F3 Markdown 以纯文本下发（客户端转义渲染）",
          r.headers.get("content-type", "").startswith("text/plain") and r.content == md)

    # 跨用户预览：mallory 的命名空间里没有这些文件 → 404，预览不是隔离漏洞
    r = c.post("/api/admin/invite-codes", headers=auth(admin_token), json={"note": "mallory"})
    code = r.json()["code"]
    r = c.post("/api/auth/register", json={"username": "mallory", "password": "mallorypass1",
                                           "invite_code": code})
    assert r.status_code == 200, r.text
    mtok = r.json()["token"]
    r = c.get("/api/files/preview", params={"path": "note.txt"}, headers=auth(mtok))
    r2 = c.get("/api/files/preview", params={"path": "../viewer/note.txt"}, headers=auth(mtok))
    check("F3 跨用户预览被拦（404/403）", r.status_code == 404 and r2.status_code in (400, 403),
          f"{r.status_code}/{r2.status_code}")

    # Range：下载端点
    def ranged(path_tok, path, range_header, endpoint="download"):
        return c.get(f"/api/files/{endpoint}", params={"path": path},
                     headers={**auth(path_tok), "Range": range_header})
    r = ranged(tok, "data.bin", "bytes=10-19")
    check("F3 Range 闭区间 206+切片正确", r.status_code == 206
          and r.content == payload[10:20]
          and r.headers.get("content-range") == "bytes 10-19/1024",
          f"{r.status_code} {r.headers.get('content-range')}")
    r = ranged(tok, "data.bin", "bytes=-25")
    check("F3 Range 后缀段", r.status_code == 206 and r.content == payload[-25:])
    r = ranged(tok, "data.bin", "bytes=1000-")
    check("F3 Range 开放段", r.status_code == 206 and r.content == payload[1000:])
    r = ranged(tok, "data.bin", "bytes=5000-6000")
    check("F3 Range 越界 416", r.status_code == 416
          and r.headers.get("content-range") == "bytes */1024", str(r.status_code))
    r = c.get("/api/files/download", params={"path": "data.bin"}, headers=auth(tok))
    check("F3 无 Range 全量 200 不回归", r.status_code == 200 and r.content == payload
          and r.headers.get("accept-ranges") == "bytes")
    # Range：预览端点（音视频拖动走这条）
    r = ranged(tok, "song.mp3", "bytes=0-9", endpoint="preview")
    check("F3 预览 Range 206+切片正确", r.status_code == 206 and r.content == mp3[:10]
          and r.headers.get("content-range") == f"bytes 0-9/{len(mp3)}",
          f"{r.status_code} {r.headers.get('content-range')}")


# ---------------- F4：管理后台「设为管理员 / 取消管理员」 ----------------

def f4_admin_promote(c, admin_token, stub_lib):
    def users_by_name(tok):
        r = c.get("/api/admin/users", headers=auth(tok))
        assert r.status_code == 200, r.text
        return {u["username"]: u for u in r.json()}

    boss = users_by_name(admin_token)["boss"]
    boss_id = boss["id"]
    check("F4 所有者标记正确（boss=is_owner）", boss["is_owner"] is True)

    r = c.post("/api/admin/invite-codes", headers=auth(admin_token), json={"note": "dave"})
    code = r.json()["code"]
    r = c.post("/api/auth/register", json={"username": "dave", "password": "davepass123",
                                           "invite_code": code})
    assert r.status_code == 200, r.text
    dtok = r.json()["token"]
    dave_id = r.json()["user"]["id"]
    check("F4 新用户默认非管理员且非所有者",
          r.json()["user"]["is_admin"] is False and r.json()["user"]["is_owner"] is False)

    # 非管理员调用 → 403 admin_required
    r = c.post(f"/api/admin/users/{dave_id}/admin", headers=auth(dtok),
               json={"is_admin": True})
    check("F4 非管理员调用设管理员接口被拒 403",
          r.status_code == 403 and r.json()["detail"]["error"] == "admin_required", r.text)

    # 所有者提升：标记翻转 + 被提升者立刻获得后台访问权
    r = c.post(f"/api/admin/users/{dave_id}/admin", headers=auth(admin_token),
               json={"is_admin": True})
    check("F4 所有者提升普通用户为管理员",
          r.status_code == 200 and r.json().get("ok") is True, r.text)
    check("F4 用户列表中管理员标记已翻转", users_by_name(admin_token)["dave"]["is_admin"] is True)
    r = c.get("/api/admin/users", headers=auth(dtok))
    check("F4 被提升者可用自己的会话访问后台", r.status_code == 200, r.text)

    # 非所有者管理员无权变更管理员：提升他人 → 403 owner_required
    r = c.post("/api/admin/invite-codes", headers=auth(admin_token), json={"note": "erin"})
    code = r.json()["code"]
    r = c.post("/api/auth/register", json={"username": "erin", "password": "erinpass123",
                                           "invite_code": code})
    assert r.status_code == 200, r.text
    erin_id = r.json()["user"]["id"]
    r = c.post(f"/api/admin/users/{erin_id}/admin", headers=auth(dtok),
               json={"is_admin": True})
    check("F4 非所有者管理员提升他人被拒 403（owner_required）",
          r.status_code == 403 and r.json()["detail"]["error"] == "owner_required"
          and "仅系统所有者可变更管理员" in r.json()["detail"]["message"], r.text)

    # 非所有者管理员试图取消所有者 → 同样被拒
    r = c.post(f"/api/admin/users/{boss_id}/admin", headers=auth(dtok),
               json={"is_admin": False})
    check("F4 非所有者管理员取消所有者被拒 403（owner_required）",
          r.status_code == 403 and r.json()["detail"]["error"] == "owner_required", r.text)

    # 所有者本人的管理员权限不可取消（自取消也被拒），且状态不变
    r = c.post(f"/api/admin/users/{boss_id}/admin", headers=auth(admin_token),
               json={"is_admin": False})
    check("F4 所有者自取消被拒（owner_protected）",
          r.status_code == 400 and r.json()["detail"]["error"] == "owner_protected"
          and "系统所有者" in r.json()["detail"]["message"], r.text)
    check("F4 被拒后所有者仍是管理员", users_by_name(admin_token)["boss"]["is_admin"] is True)

    # 所有者取消唯一的其他管理员：允许（所有者恒为管理员，系统不会无管理员）
    r = c.post(f"/api/admin/users/{dave_id}/admin", headers=auth(admin_token),
               json={"is_admin": False})
    check("F4 所有者可取消唯一的其他管理员", r.status_code == 200, r.text)
    check("F4 取消后对方失去后台访问权",
          users_by_name(admin_token)["dave"]["is_admin"] is False
          and c.get("/api/admin/users", headers=auth(dtok)).status_code == 403)

    # 目标不存在 → 404
    r = c.post("/api/admin/users/999999/admin", headers=auth(admin_token),
               json={"is_admin": True})
    check("F4 目标用户不存在 404",
          r.status_code == 404 and r.json()["detail"]["error"] == "not_found", r.text)

    # 审计：至此所有者完成的变更应有 admin_promote ×1、admin_demote ×1，被拒尝试不写 ok 记录
    with _db_lock, get_db() as db:
        rows = db.execute(
            "SELECT action, actor_user_id FROM audit_log"
            " WHERE action IN ('admin_promote', 'admin_demote') AND result = 'ok'"
            " ORDER BY id").fetchall()
    actions = [row["action"] for row in rows]
    check("F4 所有者的提升/取消均写入审计日志",
          actions == ["admin_promote", "admin_demote"]
          and all(row["actor_user_id"] == boss_id for row in rows),
          str(actions))

    # 收尾：所有者再次提升 dave，恢复双管理员格局
    r = c.post(f"/api/admin/users/{dave_id}/admin", headers=auth(admin_token),
               json={"is_admin": True})
    check("F4 可再次提升恢复管理员", r.status_code == 200
          and users_by_name(admin_token)["dave"]["is_admin"] is True, r.text)


def main():
    c = TestClient(app, raise_server_exceptions=False)
    stub_lib = Path(tmp) / "stub_storage" / "subdrive"
    r = c.post("/api/auth/register", json={"username": "boss", "password": "adminpass123",
                                           "invite_code": ""})
    assert r.status_code == 200, r.text
    admin_token = r.json()["token"]

    f1_encrypted_folders(c, admin_token, stub_lib)
    f2_speedtest(c, admin_token, stub_lib)
    f3_previews(c, admin_token, stub_lib)
    f4_admin_promote(c, admin_token, stub_lib)

    print(f"\n全部 {len(PASSED)} 项功能测试通过 ✅")


main()
