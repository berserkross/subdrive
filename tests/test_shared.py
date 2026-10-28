"""共享文件夹（D27）测试：公开共享目录能看/能下/能传、配额跟上传者、只能删自己传的。

与 test_smoke.py / test_features.py 一样是 main() 脚本，不是 pytest 用例：
直接 `python test_shared.py`。stub 模式，不接触真实 Seafile。
"""
import os
import sys
import tempfile

# Windows 控制台默认 GBK，最后打印 ✅ 会抛 UnicodeEncodeError 把整轮测试拖成失败退出。
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

tmp = tempfile.mkdtemp(prefix="subdrive-shared-")
os.environ["DATA_DIR"] = tmp
os.environ["SEAFILE_MODE"] = "stub"
os.environ["CALIBRATE_INTERVAL_SECONDS"] = "0"
os.environ["SUBDRIVE_ADMIN_USERNAME"] = "boss"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient

from app.main import app, get_db, _db_lock

PASSED = []


def check(name, cond, extra=""):
    assert cond, f"FAIL: {name} {extra}"
    PASSED.append(name)
    print(f"{len(PASSED):2d}. {name} OK")


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def register(c, admin_token, username, password="sharedpass1"):
    r = c.post("/api/admin/invite-codes", headers=auth(admin_token), json={"note": username})
    code = r.json()["code"]
    r = c.post("/api/auth/register",
               json={"username": username, "password": password, "invite_code": code})
    assert r.status_code == 200, r.text
    return r.json()["token"], r.json()["user"]["id"]


def upload(c, token, path, filename, data, owner=""):
    params = {"path": path}
    if owner:
        params["owner"] = owner
    r = c.post("/api/files/upload", params=params, headers=auth(token),
               files={"file": (filename, data, "application/octet-stream")})
    assert r.status_code == 200, (filename, r.text)
    return r.json()


def used(c, token):
    return c.get("/api/quota", headers=auth(token)).json()["used_bytes"]


def main():
    c = TestClient(app)

    # 第一个注册的是所有者（管理员）
    r = c.post("/api/auth/register", json={"username": "boss", "password": "bosspass1"})
    assert r.status_code == 200, r.text
    boss = r.json()["token"]

    tok_a, a_id = register(c, boss, "alice")   # 共享文件夹创建者（B1：先提升为管理员）
    tok_b, _ = register(c, boss, "bob")        # 被授权成员
    tok_c, _ = register(c, boss, "carol")      # 未授权者

    # B1：只有管理员能创建共享文件夹，S1 全程由 alice 以管理员身份执行
    r = c.post(f"/api/admin/users/{a_id}/admin", headers=auth(boss), json={"is_admin": True})
    assert r.status_code == 200, r.text

    print("\n— S1 创建共享文件夹 —")
    r = c.post("/api/files/mkdir", headers=auth(tok_a), json={"path": "", "name": "公共资料"})
    assert r.status_code == 200, r.text
    r = c.post("/api/files/mkdir", headers=auth(tok_a),
               json={"path": "公共资料", "name": "2026"})
    assert r.status_code == 200, r.text
    upload(c, tok_a, "公共资料/2026", "议程.txt", b"agenda-v1")

    r = c.post("/api/shared/create", headers=auth(tok_a),
               json={"path": "公共资料/2026", "members": ["bob"]})
    check("S1 创建者能共享自己的文件夹", r.status_code == 200, r.text)
    folder_id = r.json()["id"]

    r = c.post("/api/shared/create", headers=auth(tok_c),
               json={"path": "公共资料/2026", "members": []})
    check("S1 非管理员创建共享被拒（403 admin_required）",
          r.status_code == 403 and r.json()["detail"]["error"] == "admin_required", r.text)

    r = c.post("/api/shared/create", headers=auth(tok_a),
               json={"path": "公共资料/2026", "members": []})
    check("S1 同一文件夹不能重复共享（409）", r.status_code == 409, r.text)

    r = c.post("/api/shared/create", headers=auth(tok_a),
               json={"path": "公共资料", "members": ["nobody"]})
    check("S1 不存在的成员被拒（400）", r.status_code == 400, r.text)

    print("\n— S2 授权可见性 —")
    r = c.get("/api/shared/list", headers=auth(tok_b)).json()["folders"]
    check("S2 被授权者能看到这条共享", len(r) == 1 and r[0]["owner"] == "alice"
          and r[0]["path"] == "公共资料/2026" and r[0]["is_mine"] is False, str(r))
    check("S2 被授权者看到名单", r[0]["members"] == ["bob"], str(r))
    r = c.get("/api/shared/list", headers=auth(tok_c)).json()["folders"]
    check("S2 未授权者看不到", r == [], str(r))

    r = c.get("/api/files/list", params={"path": "公共资料/2026", "owner": "alice"},
              headers=auth(tok_b))
    check("S2 被授权者能列共享目录本身", r.status_code == 200, r.text)
    names = [e["name"] for e in r.json()["entries"]]
    check("S2 列目录看到创建者传的文件", "议程.txt" in names, str(names))

    r = c.get("/api/files/list", params={"path": "", "owner": "alice"}, headers=auth(tok_b))
    check("S2 授权只覆盖那一个目录，上级不可见（403）", r.status_code == 403, r.text)

    r = c.get("/api/files/download", params={"path": "公共资料/2026/议程.txt", "owner": "alice"},
              headers=auth(tok_b))
    check("S2 被授权者能下载", r.status_code == 200 and r.content == b"agenda-v1", r.text)

    r = c.get("/api/files/list", params={"path": "", "owner": "alice"}, headers=auth(tok_c))
    check("S2 未授权者访问他人目录被拒（403）", r.status_code == 403, r.text)

    print("\n— S3 往别人的共享目录上传 —")
    a_before = used(c, tok_a)
    r = c.post("/api/shared/create", headers=auth(tok_a),
               json={"path": "公共资料", "members": ["bob"]})
    assert r.status_code == 200, r.text
    outer_id = r.json()["id"]

    size = upload(c, tok_b, "公共资料/2026", "bob的笔记.txt", b"x" * 100,
                  owner="alice")["size"]
    check("S3 上传成功并回报大小", size == 100, str(size))
    check("S3 配额记在被授权者头上", used(c, tok_b) == 100, str(used(c, tok_b)))
    check("S3 创建者的配额不变", used(c, tok_a) == a_before, f"{used(c, tok_a)} != {a_before}")

    r = c.get("/api/files/list", params={"path": "公共资料/2026/bob", "owner": "alice"},
              headers=auth(tok_b))
    check("S3 文件落在上传者自己的同名子目录", r.status_code == 200, r.text)
    names = [e["name"] for e in r.json()["entries"]]
    check("S3 子目录里能看到该文件", "bob的笔记.txt" in names, str(names))

    b_before = used(c, tok_b)
    up = upload(c, tok_b, "公共资料/2026", "bob的笔记.txt", b"x" * 40, owner="alice")
    check("S3 同名覆盖写被标记 replaced", up.get("replaced") is True, str(up))
    check("S3 覆盖写只记增量（100→40，用量 -60）", used(c, tok_b) == b_before - 60,
          f'{used(c, tok_b)} != {b_before - 60}')

    r = c.post("/api/files/upload", params={"path": "公共资料/2026", "owner": "alice"},
               headers=auth(tok_c), files={"file": ("bad.txt", b"nope", "text/plain")})
    check("S3 未授权者不能往共享目录传（403）", r.status_code == 403, r.text)

    print("\n— S3b 建文件夹与上传同一条落点规则 —")
    r = c.post("/api/files/mkdir", headers=auth(tok_b),
               params={"owner": "alice"}, json={"path": "公共资料/2026", "name": "bob的相册"})
    check("S3b 建夹成功并回报落点", r.status_code == 200
          and r.json()["path"] == "公共资料/2026/bob/bob的相册", r.text)
    r = c.get("/api/files/list", params={"path": "公共资料/2026/bob", "owner": "alice"},
              headers=auth(tok_b))
    names = [e["name"] for e in r.json()["entries"]]
    check("S3b 新夹出现在我那一格里", "bob的相册" in names, str(names))
    r = c.get("/api/files/list", params={"path": "公共资料/2026", "owner": "alice"},
              headers=auth(tok_b))
    names = [e["name"] for e in r.json()["entries"]]
    check("S3b 共享目录本体没多出同名夹", "bob的相册" not in names, str(names))
    r = c.post("/api/files/mkdir", headers=auth(tok_c),
               params={"owner": "alice"}, json={"path": "公共资料/2026", "name": "偷偷的"})
    check("S3b 未授权者不能建夹（403）", r.status_code == 403, r.text)
    r = c.post("/api/files/mkdir", headers=auth(tok_b),
               params={"owner": "alice"}, json={"path": "公共资料", "name": "在共享根建"})
    check("S3b 在共享根建夹也落进自己那格", r.status_code == 200
          and r.json()["path"] == "公共资料/bob/在共享根建", r.text)

    print("\n— S4 只能删自己传的 —")
    r = c.post("/api/files/delete", headers=auth(tok_b),
               json={"path": "公共资料/2026/议程.txt"}, params={"owner": "alice"})
    check("S4 不能删别人传的文件（403）", r.status_code == 403, r.text)
    r = c.post("/api/files/delete", headers=auth(tok_b),
               json={"path": "公共资料/2026/bob"}, params={"owner": "alice"})
    check("S4 能删自己上传的文件", r.status_code == 200, r.text)
    check("S4 删完配额回冲", used(c, tok_b) == 0, str(used(c, tok_b)))

    print("\n— S4b 成员能管自己那一格（改名/移动），但那一格本身不许改名 —")
    # S4 已经把 公共资料/2026/bob 整个删掉了，这里用一次上传把那一格重建回来
    upload(c, tok_b, "公共资料/2026", "我的笔记.txt", b"note", owner="alice")
    r = c.post("/api/files/mkdir", headers=auth(tok_b), params={"owner": "alice"},
               json={"path": "公共资料/2026", "name": "子目录"})
    check("S4b 我那一格里能建子目录", r.status_code == 200
          and r.json()["path"] == "公共资料/2026/bob/子目录", r.text)

    r = c.post("/api/files/rename", headers=auth(tok_b), params={"owner": "alice"},
               json={"path": "公共资料/2026/bob/我的笔记.txt", "new_name": "改名后.txt"})
    check("S4b 能给自己那格里的文件改名", r.status_code == 200, r.text)
    r = c.get("/api/files/list", params={"path": "公共资料/2026/bob", "owner": "alice"},
              headers=auth(tok_b))
    names = [e["name"] for e in r.json()["entries"]]
    check("S4b 改名生效", "改名后.txt" in names and "我的笔记.txt" not in names, str(names))

    r = c.post("/api/files/move", headers=auth(tok_b), params={"owner": "alice"},
               json={"path": "公共资料/2026/bob/改名后.txt",
                     "dest_dir": "公共资料/2026/bob/子目录"})
    check("S4b 能把自己那格里的文件移到格内子目录", r.status_code == 200, r.text)
    r = c.get("/api/files/list", params={"path": "公共资料/2026/bob/子目录", "owner": "alice"},
              headers=auth(tok_b))
    names = [e["name"] for e in r.json()["entries"]]
    check("S4b 移动生效", "改名后.txt" in names, str(names))

    r = c.post("/api/files/upload", params={"path": "公共资料/2026/bob/子目录",
                                            "owner": "alice"}, headers=auth(tok_b),
               files={"file": ("深处.txt", b"deep", "text/plain")})
    check("S4b 在自己那格的子目录里上传", r.status_code == 200, r.text)
    r = c.get("/api/files/list", params={"path": "公共资料/2026/bob/子目录",
                                         "owner": "alice"}, headers=auth(tok_b))
    entries = r.json()["entries"]
    check("S4b 上传不再多套一层自己的用户名", r.status_code == 200
          and "深处.txt" in [e["name"] for e in entries]
          and not any(e["type"] == "dir" and e["name"] == "bob" for e in entries),
          str(entries))

    r = c.post("/api/files/mkdir", headers=auth(tok_b), params={"owner": "alice"},
               json={"path": "公共资料/2026/bob/子目录", "name": "更深的"})
    check("S4b 在自己那格的子目录里建夹也不套用户名",
          r.status_code == 200 and r.json()["path"] == "公共资料/2026/bob/子目录/更深的",
          r.text)

    r = c.post("/api/files/rename", headers=auth(tok_b), params={"owner": "alice"},
               json={"path": "公共资料/2026/bob", "new_name": "bob2"})
    check("S4b 不能给自己那一格改名（400 cell_rename）", r.status_code == 400
          and r.json()["detail"]["error"] == "cell_rename", r.text)
    r = c.post("/api/files/move", headers=auth(tok_b), params={"owner": "alice"},
               json={"path": "公共资料/2026/bob", "dest_dir": "公共资料/2026/bob/子目录"})
    check("S4b 不能把自己那一格移走（400 cell_move）", r.status_code == 400
          and r.json()["detail"]["error"] == "cell_move", r.text)

    r = c.post("/api/files/rename", headers=auth(tok_b), params={"owner": "alice"},
               json={"path": "公共资料/2026/议程.txt", "new_name": "议程2.txt"})
    check("S4b 不能给创建者的文件改名（403）", r.status_code == 403, r.text)
    r = c.post("/api/files/move", headers=auth(tok_b), params={"owner": "alice"},
               json={"path": "公共资料/2026/议程.txt", "dest_dir": "公共资料/2026/bob"})
    check("S4b 不能把创建者的文件移走（403）", r.status_code == 403, r.text)

    upload(c, tok_a, "公共资料/2026", "创建者的.txt", b"owner")
    r = c.post("/api/files/rename", headers=auth(tok_a),
               json={"path": "公共资料/2026/创建者的.txt", "new_name": "创建者的-改.txt"})
    check("S4b 创建者改名照旧可用（新判断不误伤本人）", r.status_code == 200, r.text)

    print("\n— S5 共享目录本身的保护 —")
    r = c.post("/api/files/rename", headers=auth(tok_a),
               json={"path": "公共资料/2026", "new_name": "改名了"})
    check("S5 共享目录不许直接改名（400）", r.status_code == 400, r.text)
    r = c.post("/api/files/delete", headers=auth(tok_a), json={"path": "公共资料/2026"})
    check("S5 共享目录不许直接删除（400）", r.status_code == 400, r.text)
    r = c.post("/api/files/delete", headers=auth(tok_a), json={"path": "公共资料"})
    check("S5 共享目录的上级也不许删（400）", r.status_code == 400, r.text)

    print("\n— S6 名单可改、取消共享退回私有 —")
    r = c.post(f"/api/shared/{folder_id}/members", headers=auth(tok_b),
               json={"members": ["bob"]})
    check("S6 非创建者不能改名单（403）", r.status_code == 403, r.text)
    r = c.post(f"/api/shared/{folder_id}/members", headers=auth(tok_a), json={"members": []})
    check("S6 创建者能把名单清空", r.status_code == 200 and r.json()["members"] == [], r.text)
    r = c.get("/api/files/list", params={"path": "公共资料/2026", "owner": "alice"},
              headers=auth(tok_b))
    check("S6 名单清空＝全员可见，被点过名的成员照样能进", r.status_code == 200, r.text)
    r = c.get("/api/files/list", params={"path": "公共资料/2026", "owner": "alice"},
              headers=auth(tok_c))
    check("S6 名单清空后没被点名的人也能进", r.status_code == 200, r.text)

    r = c.post(f"/api/shared/{folder_id}/members", headers=auth(tok_a),
               json={"members": ["bob"]})
    check("S6 名单能再加回来", r.status_code == 200 and r.json()["members"] == ["bob"], r.text)
    r = c.get("/api/files/list", params={"path": "公共资料/2026", "owner": "alice"},
              headers=auth(tok_c))
    check("S6 名单收窄后未点名者立刻失去访问（403）", r.status_code == 403, r.text)

    r = c.delete(f"/api/shared/{folder_id}", headers=auth(tok_a))
    check("S6 取消共享成功", r.status_code == 200, r.text)
    r = c.get("/api/shared/list", headers=auth(tok_b)).json()["folders"]
    check("S6 取消后共享列表里没有了", all(f["id"] != folder_id for f in r), str(r))
    r = c.get("/api/files/list", params={"path": "", "owner": "alice"}, headers=auth(tok_b))
    check("S6 取消后被授权者失去访问（403）", r.status_code == 403, r.text)
    r = c.get("/api/files/list", params={"path": "公共资料/2026"}, headers=auth(tok_a))
    check("S6 文件夹与内容仍归创建者", r.status_code == 200
          and "议程.txt" in [e["name"] for e in r.json()["entries"]], r.text)

    print("\n— S7 审计 —")
    with _db_lock, get_db() as db:
        rows = db.execute("SELECT action, result FROM audit_log WHERE action IN"
                          " ('share','share_members','unshare') ORDER BY id").fetchall()
    actions = [r["action"] for r in rows]
    check("S7 share/share_members/unshare 都进了审计",
          "share" in actions and "share_members" in actions and "unshare" in actions,
          str(actions))
    check("S7 审计里没有 denied 的共享操作", all(r["result"] == "ok" for r in rows), str(rows))

    print("\n— S8 每目录上限：容量 / 成员数（D35）—")
    r = c.post("/api/shared/create", headers=auth(tok_a),
               json={"path": "公共资料/2026", "members": [], "max_bytes": 4096,
                     "max_members": 1})
    check("S8 创建时可以带自定义上限", r.status_code == 200, r.text)
    sid = r.json()["id"]
    mine = [f for f in c.get("/api/shared/list", headers=auth(tok_a)).json()["folders"]
            if f["id"] == sid][0]
    check("S8 列表回显两个上限", mine["max_bytes"] == 4096 and mine["max_members"] == 1,
          str(mine))
    r = c.post("/api/files/upload", params={"path": "公共资料/2026", "owner": "alice"},
               headers=auth(tok_b),
               files={"file": ("big.bin", b"x" * 8192, "application/octet-stream")})
    check("S8 超出共享目录容量被拒（413 shared_full）",
          r.status_code == 413 and r.json()["detail"]["error"] == "shared_full", r.text)
    upload(c, tok_b, "公共资料/2026", "small.bin", b"y" * 100, owner="alice")
    check("S8 容量之内的上传照常成功", True)
    r = c.post(f"/api/shared/{sid}/members", headers=auth(tok_a),
               json={"members": ["bob", "carol"]})
    check("S8 点名超过成员上限被拒（400 too_many_members）", r.status_code == 400, r.text)
    r = c.post(f"/api/shared/{sid}/members", headers=auth(tok_a), json={"members": ["bob"]})
    check("S8 不超过上限的名单照常生效",
          r.status_code == 200 and r.json()["members"] == ["bob"], r.text)
    r = c.patch(f"/api/shared/{sid}", headers=auth(tok_a), json={"max_members": 9999})
    check("S8 抬不过全局硬顶（400 bad_limit）", r.status_code == 400, r.text)
    r = c.patch(f"/api/shared/{sid}", headers=auth(tok_a), json={"max_bytes": 0})
    check("S8 上限不许设成 0（400 bad_limit）", r.status_code == 400, r.text)
    r = c.patch(f"/api/shared/{sid}", headers=auth(tok_b), json={"max_bytes": 1024})
    check("S8 非创建者不能改上限（403）", r.status_code == 403, r.text)
    r = c.patch(f"/api/shared/{sid}", headers=auth(tok_a), json={"max_bytes": 1 << 20})
    check("S8 创建者能把容量上限调大",
          r.status_code == 200 and r.json()["max_bytes"] == 1 << 20, r.text)
    upload(c, tok_b, "公共资料/2026", "ok.bin", b"z" * 8192, owner="alice")
    check("S8 调大之后大一点的文件能进", True)
    r = c.patch(f"/api/shared/{sid}", headers=auth(boss), json={"max_members": 2})
    check("S8 管理员能改别人的共享上限",
          r.status_code == 200 and r.json()["max_members"] == 2, r.text)
    r = c.get("/api/shared/list", headers=auth(tok_b)).json()["folders"]
    check("S8 被授权者也能看到上限", any(f["id"] == sid and f["max_members"] == 2 for f in r),
          str(r))

    print(f"\n全部 {len(PASSED)} 项共享文件夹测试通过 ✅")


if __name__ == "__main__":
    main()
