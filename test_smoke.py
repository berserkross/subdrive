"""子用户网盘一期冒烟测试（stub 模式，不接触真实 Seafile）。

覆盖：邀请码注册（无效/过期/撤销/复用）、建夹投影、登录/会话、路径穿越电池、
跨用户隔离、上传→列表→下载字节一致、配额拦截与删除释放、改名/移动、
管理员禁用/启用与邀请码管理、登录限速、改密码、用量校准。
"""
import os
import secrets
import sys
import tempfile
from pathlib import Path

tmp = tempfile.mkdtemp(prefix="subdrive-test-")
os.environ["DATA_DIR"] = tmp
os.environ["SEAFILE_MODE"] = "stub"
os.environ["CALIBRATE_INTERVAL_SECONDS"] = "0"
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi.testclient import TestClient
from app.main import app

PASSED = []


def check(name, cond, extra=""):
    assert cond, f"FAIL: {name} {extra}"
    PASSED.append(name)
    print(f"{len(PASSED):2d}. {name} OK")


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def main():
    c = TestClient(app, raise_server_exceptions=False)
    stub_lib = Path(tmp) / "stub_storage" / "subdrive"

    # 1. 首个用户免邀请码注册 → 管理员，且投影文件夹已建
    r = c.post("/api/auth/register", json={"username": "boss", "password": "adminpass123",
                                           "nickname": "管理员", "invite_code": ""})
    assert r.status_code == 200, r.text
    admin = r.json()
    admin_token = admin["token"]
    check("首用户注册自动管理员", admin["user"]["is_admin"] is True)
    check("管理员投影文件夹已建", (stub_lib / "boss").is_dir())

    # 2. 无效邀请码被拒
    r = c.post("/api/auth/register", json={"username": "alice", "password": "alicepass1",
                                           "invite_code": "SD-DEAD-BEEF"})
    check("无效邀请码被拒", r.status_code == 400 and r.json()["detail"]["error"] == "bad_invite", r.text)

    # 3. 非法用户名被拒（大写/过短/保留字）
    for bad in ("Alice", "ab", "root", "a b c"):
        r = c.post("/api/auth/register", json={"username": bad, "password": "password123",
                                               "invite_code": "whatever"})
        assert r.status_code == 400, (bad, r.text)
    check("非法用户名被拒（大写/过短/保留字/空格）", True)

    # 4. 管理员签发邀请码；过期的码被拒
    r = c.post("/api/admin/invite-codes", headers=auth(admin_token),
               json={"note": "过期测试", "expires_days": -1})
    assert r.status_code == 200, r.text
    expired_code = r.json()["code"]
    r = c.post("/api/auth/register", json={"username": "alice", "password": "alicepass1",
                                           "invite_code": expired_code})
    check("过期邀请码被拒", r.status_code == 400, r.text)

    # 5. 被撤销的码被拒
    r = c.post("/api/admin/invite-codes", headers=auth(admin_token), json={"note": "撤销测试"})
    revoked = r.json()
    c.post(f"/api/admin/invite-codes/{revoked['id']}/revoke", headers=auth(admin_token))
    r = c.post("/api/auth/register", json={"username": "alice", "password": "alicepass1",
                                           "invite_code": revoked["code"]})
    check("撤销邀请码被拒", r.status_code == 400, r.text)

    # 6. 正常邀请码注册 alice，投影文件夹自动创建
    r = c.post("/api/admin/invite-codes", headers=auth(admin_token), json={"note": "给 alice"})
    code_a = r.json()["code"]
    r = c.post("/api/auth/register", json={"username": "alice", "password": "alicepass1",
                                           "nickname": "爱丽丝", "invite_code": code_a})
    assert r.status_code == 200, r.text
    alice_token = r.json()["token"]
    alice_id = r.json()["user"]["id"]
    check("邀请码注册成功", True)
    check("注册即建投影文件夹 /alice", (stub_lib / "alice").is_dir())

    # 7. 同一邀请码复用被拒
    r = c.post("/api/auth/register", json={"username": "alice2", "password": "alicepass1",
                                           "invite_code": code_a})
    check("邀请码复用被拒", r.status_code == 400, r.text)

    # 8. 注册 bob
    r = c.post("/api/admin/invite-codes", headers=auth(admin_token), json={"note": "给 bob"})
    code_b = r.json()["code"]
    r = c.post("/api/auth/register", json={"username": "bob", "password": "bobpass123",
                                           "invite_code": code_b})
    assert r.status_code == 200, r.text
    bob_token = r.json()["token"]
    bob_id = r.json()["user"]["id"]
    check("第二用户注册成功", (stub_lib / "bob").is_dir())

    # 9. 登录/错误密码/会话
    r = c.post("/api/auth/login", json={"username": "alice", "password": "wrong-password"})
    assert r.status_code == 401
    r = c.post("/api/auth/login", json={"username": "alice", "password": "alicepass1"})
    assert r.status_code == 200, r.text
    alice_token2 = r.json()["token"]
    me = c.get("/api/auth/me", headers=auth(alice_token2)).json()
    check("登录与 me", me["username"] == "alice" and me["quota_bytes"] == 20 * 1024 ** 3)
    r = c.post("/api/auth/logout", headers=auth(alice_token2))
    assert r.status_code == 200
    r = c.get("/api/auth/me", headers=auth(alice_token2))
    check("登出后 token 失效", r.status_code == 401)

    # 10. 上传 → 列表 → 下载 字节完全一致
    payload = secrets.token_bytes(100_000)
    r = c.post("/api/files/upload?path=", headers=auth(alice_token),
               files={"file": ("data.bin", payload, "application/octet-stream")})
    assert r.status_code == 200, r.text
    assert r.json()["size"] == len(payload)
    lst = c.get("/api/files/list", params={"path": ""}, headers=auth(alice_token)).json()
    names = [e["name"] for e in lst["entries"]]
    assert names == ["data.bin"], lst
    dl = c.get("/api/files/download", params={"path": "data.bin"}, headers=auth(alice_token))
    assert dl.status_code == 200
    check("上传→列表→下载字节一致", dl.content == payload)

    # 11. 跨用户隔离：bob 看不到、读不到 alice 的文件
    lst_b = c.get("/api/files/list", params={"path": ""}, headers=auth(bob_token)).json()
    assert lst_b["entries"] == [], lst_b
    r = c.get("/api/files/download", params={"path": "data.bin"}, headers=auth(bob_token))
    assert r.status_code == 404, r.status_code
    check("跨用户隔离（列表不可见、下载 404）", True)

    # 12. 路径穿越电池：含真 .. 段/反斜杠的必须 403 拒绝；
    #     "..;"、"...." 这类只是本人空间内的怪名字（无法逃逸），404 亦算安全。
    evil_strict = ["../bob", "/../bob", "..\\bob", "//../bob", "%2e%2e/bob",
                   "%252e%252e/bob", "a/../../bob", "/%2e%2e%2fbob", "/alice/../../bob"]
    for p in evil_strict:
        r = c.get("/api/files/list", params={"path": p}, headers=auth(alice_token))
        assert r.status_code == 403, (p, r.status_code, r.text)
        r = c.get("/api/files/download", params={"path": p + "/data.bin"}, headers=auth(alice_token))
        assert r.status_code in (400, 403), (p, r.status_code)
    evil_loose = ["..;/bob", "....//bob", "/etc/passwd", "C:\\windows"]
    for p in evil_loose:
        r = c.get("/api/files/list", params={"path": p}, headers=auth(alice_token))
        assert r.status_code in (400, 403, 404), (p, r.status_code, r.text)
    check(f"路径穿越电池 {len(evil_strict) + len(evil_loose)} 例无一逃逸", True)

    # 13. 建夹 → 子目录上传/下载 → 改名 → 移动
    r = c.post("/api/files/mkdir", headers=auth(alice_token), json={"path": "", "name": "照片"})
    assert r.status_code == 200, r.text
    r = c.post("/api/files/mkdir", headers=auth(alice_token), json={"path": "", "name": "a/b"})
    assert r.status_code == 403, r.text  # 名称含分隔符被拒
    small = b"hello-subdrive" * 10
    r = c.post("/api/files/upload", params={"path": "照片"}, headers=auth(alice_token),
               files={"file": ("note.txt", small, "text/plain")})
    assert r.status_code == 200, r.text
    dl = c.get("/api/files/download", params={"path": "照片/note.txt"}, headers=auth(alice_token))
    assert dl.content == small
    r = c.post("/api/files/rename", headers=auth(alice_token),
               json={"path": "照片/note.txt", "new_name": "日记.txt"})
    assert r.status_code == 200, r.text
    r = c.post("/api/files/mkdir", headers=auth(alice_token), json={"path": "", "name": "归档"})
    assert r.status_code == 200
    r = c.post("/api/files/move", headers=auth(alice_token),
               json={"path": "照片/日记.txt", "dest_dir": "归档"})
    assert r.status_code == 200, r.text
    lst = c.get("/api/files/list", params={"path": "归档"}, headers=auth(alice_token)).json()
    assert [e["name"] for e in lst["entries"]] == ["日记.txt"], lst
    r = c.post("/api/files/rename", headers=auth(alice_token), json={"path": "", "new_name": "x"})
    assert r.status_code == 400  # 根文件夹禁改名
    check("建夹/子目录传输/改名/移动/根保护", True)

    # 14. 配额：设小配额 → 超额上传被拒 → 删除释放后可再传
    c.post(f"/api/admin/users/{alice_id}/quota", headers=auth(admin_token),
           json={"quota_bytes": 100_140 + 1060})  # 现有 100140 + 恰好再放 1000、拒绝 +600
    big = secrets.token_bytes(1000)
    r = c.post("/api/files/upload", params={"path": ""}, headers=auth(alice_token),
               files={"file": ("q1.bin", big, "application/octet-stream")})
    assert r.status_code == 200, r.text
    r = c.post("/api/files/upload", params={"path": ""}, headers=auth(alice_token),
               files={"file": ("q2.bin", secrets.token_bytes(600), "application/octet-stream")})
    assert r.status_code == 413 and r.json()["detail"]["error"] == "quota_exceeded", r.text
    q = c.get("/api/quota", headers=auth(alice_token)).json()
    assert q["used_bytes"] == 100_000 + len(small) + 1000, q
    r = c.post("/api/files/delete", headers=auth(alice_token), json={"path": "q1.bin"})
    assert r.status_code == 200 and r.json()["freed_bytes"] == 1000, r.text
    r = c.post("/api/files/upload", params={"path": ""}, headers=auth(alice_token),
               files={"file": ("q2.bin", secrets.token_bytes(600), "application/octet-stream")})
    assert r.status_code == 200, r.text
    check("配额拦截 + 删除释放 + 再传成功", True)
    c.post(f"/api/admin/users/{alice_id}/quota", headers=auth(admin_token),
           json={"quota_bytes": None})

    # 15. 校准：绕过后端直接往 stub 文件夹塞文件 → 校准后用量对齐
    rogue = stub_lib / "alice" / "rogue.bin"
    rogue.write_bytes(b"R" * 4321)
    before = c.get("/api/quota", headers=auth(alice_token)).json()["used_bytes"]
    r = c.post(f"/api/admin/users/{alice_id}/recalibrate", headers=auth(admin_token))
    assert r.status_code == 200, r.text
    after = c.get("/api/quota", headers=auth(alice_token)).json()
    assert after["used_bytes"] == before + 4321, (before, after)
    check("用量校准对齐真实占用", True)
    rogue.unlink()

    # 16. 管理员禁用 bob → 现有 token 立即失效、登录被拒；启用后恢复
    r = c.post(f"/api/admin/users/{bob_id}/disable", headers=auth(admin_token))
    assert r.status_code == 200
    r = c.get("/api/files/list", params={"path": ""}, headers=auth(bob_token))
    assert r.status_code in (401, 403), r.status_code
    r = c.post("/api/auth/login", json={"username": "bob", "password": "bobpass123"})
    assert r.status_code == 403, r.text
    assert (stub_lib / "bob").is_dir()  # 文件夹保留
    c.post(f"/api/admin/users/{bob_id}/enable", headers=auth(admin_token))
    r = c.post("/api/auth/login", json={"username": "bob", "password": "bobpass123"})
    assert r.status_code == 200, r.text
    bob_token = r.json()["token"]
    check("禁用即时失效 + 文件夹保留 + 启用恢复", True)

    # 17. 非管理员访问 admin 接口被拒
    r = c.get("/api/admin/users", headers=auth(bob_token))
    check("非管理员访问后台被拒", r.status_code == 403)

    # 18. 登录限速：连续 5 次错密码 → 第 6 次（哪怕密码正确）被锁
    r = c.post("/api/admin/invite-codes", headers=auth(admin_token), json={"note": "给 carol"})
    code_c = r.json()["code"]
    r = c.post("/api/auth/register", json={"username": "carol", "password": "carolpass1",
                                           "invite_code": code_c})
    assert r.status_code == 200, r.text
    for _ in range(5):
        r = c.post("/api/auth/login", json={"username": "carol", "password": "nope-nope"})
        assert r.status_code == 401
    r = c.post("/api/auth/login", json={"username": "carol", "password": "carolpass1"})
    check("登录失败限速锁定", r.status_code == 429, r.text)

    # 19. 改密码：旧密码失效、新密码可用
    r = c.post("/api/auth/login", json={"username": "bob", "password": "bobpass123"})
    bob_t = r.json()["token"]
    r = c.post("/api/auth/change-password", headers=auth(bob_t),
               json={"old_password": "bobpass123", "new_password": "bobnewpass9"})
    assert r.status_code == 200, r.text
    r = c.post("/api/auth/login", json={"username": "bob", "password": "bobpass123"})
    assert r.status_code == 401
    r = c.post("/api/auth/login", json={"username": "bob", "password": "bobnewpass9"})
    assert r.status_code == 200
    check("改密码生效", True)

    # 20. 详情端点
    d = c.get("/api/files/detail", params={"path": "data.bin"}, headers=auth(alice_token)).json()
    check("文件详情", d["type"] == "file" and d["size"] == 100_000)

    print(f"\n全部 {len(PASSED)} 项冒烟测试通过 ✅")


main()
