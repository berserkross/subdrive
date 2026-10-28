"""SubDrive 浏览器端到端冒烟：真 Chrome 点真页面，打真后端（stub 存储）。

跑法（仓库根目录）：
    .\\.venv\\Scripts\\python.exe tests\\e2e\\test_e2e_browser.py

原则：
- 每一步都是真实点击/输入，不绕过页面；关键结论同时用后端 JSON 交叉验证。
- 自起自停：临时 DATA_DIR + 随机端口，跑完删干净，不碰本机 subdrive.db 与文件。
- 只用系统已装的 Chrome/Edge（channel=chrome，失败退 msedge），不下载 150MB 浏览器。

覆盖：首个用户注册 → 建夹 → 上传 → 重命名 → 删除 → 创建共享文件夹 →
      第二个用户凭邀请码注册 → 看到并进入他人共享目录 → 在他人目录里上传 → 退出登录。
"""
from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

try:
    import httpx
    from playwright.sync_api import sync_playwright
except ImportError as exc:  # pragma: no cover
    print(f"[SKIP] 缺少依赖：{exc}")
    print("      装：.\\.venv\\Scripts\\python.exe -m pip install playwright httpx")
    raise SystemExit(0)

PASSED: list[str] = []
FAILED: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    (PASSED if ok else FAILED).append(name)
    line = f"{'PASS' if ok else 'FAIL'}: {name}"
    if detail and not ok:
        line += f"  [{detail}]"
    print(line, flush=True)
    return ok


def need(name: str, ok: bool, detail: str = "") -> None:
    if not check(name, ok, detail):
        raise AssertionError(name)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def boot_server(base: str, data_dir: Path, port: int) -> subprocess.Popen:
    env = dict(os.environ)
    env.update({
        "DATA_DIR": str(data_dir),
        "SEAFILE_MODE": "stub",
        "PYTHONIOENCODING": "utf-8",
        "CALIBRATE_INTERVAL_SECONDS": "3600",
    })
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1",
         "--port", str(port), "--log-level", "warning"],
        cwd=str(ROOT), env=env, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT,
    )
    deadline = time.time() + 60
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"服务进程提前退出，退出码 {proc.returncode}")
        try:
            if httpx.get(base + "/api/auth/me", timeout=1.0).status_code in (200, 401):
                return proc
        except Exception:
            time.sleep(0.2)
    proc.terminate()
    raise RuntimeError("服务 60 秒内未就绪")


def launch_browser(pw):
    last = None
    for channel in ("chrome", "msedge"):
        try:
            return pw.chromium.launch(channel=channel, headless=True)
        except Exception as exc:  # 本机可能只装了其中一个
            last = exc
    raise RuntimeError(f"Chrome/Edge 都起不来：{last}")


def register(page, base: str, username: str, nickname: str, password: str, invite: str = "") -> None:
    page.goto(base, wait_until="load")
    page.click("#tab-register")
    if invite:
        page.fill("#reg-invite", invite)
    page.fill("#reg-username", username)
    page.fill("#reg-nickname", nickname)
    page.fill("#reg-password", password)
    page.click("#form-register button[type=submit]")
    page.wait_for_selector("#view-drive:not(.hidden)", timeout=15000)


def login(page, base: str, username: str, password: str) -> None:
    page.goto(base, wait_until="load")
    page.fill("#login-username", username)
    page.fill("#login-password", password)
    page.click("#form-login button[type=submit]")
    page.wait_for_selector("#view-drive:not(.hidden)", timeout=15000)


def row(page, name: str):
    return page.locator(f'.row:has(.row-name:text-is("{name}"))')


def wait_row(page, name: str, timeout: int = 20000) -> None:
    page.wait_for_selector(f'.row:has(.row-name:text-is("{name}"))', timeout=timeout)


def wait_row_gone(page, name: str, timeout: int = 20000) -> None:
    page.wait_for_selector(f'.row:has(.row-name:text-is("{name}"))', state="detached", timeout=timeout)


def run() -> int:
    port = free_port()
    base = f"http://127.0.0.1:{port}"
    data_dir = Path(tempfile.mkdtemp(prefix="subdrive-e2e-"))
    work_dir = Path(tempfile.mkdtemp(prefix="subdrive-e2e-files-"))
    proc = None
    browser = None
    try:
        proc = boot_server(base, data_dir, port)
        print(f"服务已起：{base}（DATA_DIR={data_dir}）", flush=True)

        with sync_playwright() as pw:
            browser = launch_browser(pw)
            boss_ctx = browser.new_context(viewport={"width": 1400, "height": 950})
            boss = boss_ctx.new_page()
            errors: list[str] = []
            boss.on("pageerror", lambda e: errors.append(str(e)))

            # ---- 1. 首屏与注册（首个用户免邀请码，且成为管理员）----
            boss.goto(base, wait_until="load")
            need("首页渲染出登录表单", boss.is_visible("#form-login"))
            register(boss, base, "boss", "老板", "bosspass123")
            need("注册后进入网盘视图", boss.is_visible("#view-drive"))
            need("用户名显示为昵称", "老板" in boss.inner_text("#user-name"),
                 boss.inner_text("#user-name"))
            need("首个用户拿到管理员入口", boss.is_visible("#btn-admin"))

            boss_token = boss.evaluate("() => localStorage.getItem('subdrive_token')")
            auth = {"Authorization": f"Bearer {boss_token}"}

            # ---- 2. 新建文件夹 ----
            boss.click("#btn-mkdir")
            boss.fill("#m-name", "docs")
            boss.click("#modal-ok")
            wait_row(boss, "docs")
            check("新建文件夹出现在列表", True)

            # ---- 3. 上传文件 ----
            sample = work_dir / "hello.txt"
            sample.write_text("hello subdrive\n", encoding="utf-8")
            boss.set_input_files("#file-input", str(sample))
            wait_row(boss, "hello.txt", timeout=30000)
            check("上传后文件出现在列表", True)
            quota_after_upload = boss.inner_text("#quota-text")
            check("配额栏显示已用量", "0 B" not in quota_after_upload, quota_after_upload)

            # ---- 4. 重命名 ----
            row(boss, "hello.txt").locator('button[title="重命名"]').click()
            boss.fill("#m-name", "hi.txt")
            boss.click("#modal-ok")
            wait_row(boss, "hi.txt")
            check("重命名后旧名消失新名出现", row(boss, "hello.txt").count() == 0)

            # ---- 4.5 批量操作（行首勾选 → 底部操作条）----
            fa = work_dir / "a.txt"
            fb = work_dir / "b.txt"
            fa.write_text("a\n", encoding="utf-8")
            fb.write_text("b\n", encoding="utf-8")
            boss.set_input_files("#file-input", [str(fa), str(fb)])
            wait_row(boss, "a.txt")
            wait_row(boss, "b.txt")
            row(boss, "a.txt").locator(".row-sel").check()
            row(boss, "b.txt").locator(".row-sel").check()
            need("勾选后底部操作条出现", boss.is_visible("#batch-bar"))
            check("计数显示已选 2 项", "已选 2 项" in boss.inner_text("#batch-count"),
                  boss.inner_text("#batch-count"))
            check("勾选没有触发打开或下载", row(boss, "a.txt").count() == 1)
            check("部分勾选时表头全选为不确定态",
                  boss.evaluate("() => document.querySelector('#sel-all').indeterminate"))
            boss.click("#batch-clear")
            check("取消后操作条收起", not boss.is_visible("#batch-bar"))
            row(boss, "docs").locator(".row-sel").check()
            check("只勾文件夹时下载按钮禁用",
                  boss.evaluate("() => document.querySelector('#batch-download').disabled"))
            boss.click("#batch-clear")
            boss.check("#sel-all")
            total = boss.locator("#file-list .row").count()
            checked = boss.locator("#file-list .row-sel:checked").count()
            check("表头全选勾中所有行", total > 0 and checked == total, f"{checked} / {total}")
            boss.click("#batch-clear")
            row(boss, "a.txt").locator(".row-sel").check()
            row(boss, "b.txt").locator(".row-sel").check()
            boss.click("#batch-move")
            boss.click('#modal-body .folder-pick button[data-dir="docs"]')
            boss.click("#modal-ok")
            wait_row_gone(boss, "a.txt")
            check("批量移动后原目录不再有这两个文件",
                  row(boss, "a.txt").count() == 0 and row(boss, "b.txt").count() == 0)
            boss.locator('.row:has(.row-name:text-is("docs")) .row-name').click()
            wait_row(boss, "a.txt")
            check("批量移动后目标目录出现两个文件",
                  row(boss, "a.txt").count() == 1 and row(boss, "b.txt").count() == 1)
            boss.check("#sel-all")
            boss.click("#batch-delete")
            boss.click("#modal-ok")
            wait_row_gone(boss, "a.txt")
            check("批量删除后目录清空", boss.locator("#file-list .row").count() == 0,
                  f"剩 {boss.locator('#file-list .row').count()} 行")
            boss.locator("#crumbs button").first.click()
            wait_row(boss, "hi.txt")
            check("面包屑能回到根目录", boss.locator('.row:has(.row-name:text-is("docs"))').count() == 1)

            # ---- 5. 创建共享文件夹（名单留空＝全员可见）----
            row(boss, "docs").locator('button[title="共享此文件夹"]').click()
            boss.wait_for_selector("#share-members", timeout=10000)
            boss.click("#modal-ok")
            boss.wait_for_selector("#shared-card:not(.hidden)", timeout=15000)
            check("共享卡出现", boss.is_visible("#shared-card"))
            check("共享卡标明我创建", "我创建" in boss.inner_text("#shared-list"),
                 boss.inner_text("#shared-list"))
            shared = httpx.get(base + "/api/shared/list", headers=auth, timeout=10).json()
            need("后端共享清单含 docs 且 is_mine",
                 any(f["path"] == "docs" and f["is_mine"] for f in shared["folders"]),
                 str(shared))

            # ---- 6. 第二个用户凭邀请码注册 ----
            invite = httpx.post(base + "/api/admin/invite-codes", headers=auth,
                                json={"note": "e2e", "max_uses": 1}, timeout=10).json()
            bob_ctx = browser.new_context(viewport={"width": 1400, "height": 950})
            bob = bob_ctx.new_page()
            bob.on("pageerror", lambda e: errors.append(str(e)))
            register(bob, base, "bob", "小明", "bobpass123", invite=invite["code"])
            check("第二个用户注册成功", bob.is_visible("#view-drive"))
            check("普通用户没有管理员入口", not bob.is_visible("#btn-admin"))

            bob_token = bob.evaluate("() => localStorage.getItem('subdrive_token')")
            bob_auth = {"Authorization": f"Bearer {bob_token}"}

            # ---- 7. bob 在共享卡里看到 boss 的 docs，并进入 ----
            bob.wait_for_selector("#shared-card:not(.hidden)", timeout=15000)
            check("bob 看到 boss 的共享文件夹", "docs" in bob.inner_text("#shared-list"),
                 bob.inner_text("#shared-list"))
            bob.click('#shared-list .shared-item:has-text("docs")')
            bob.wait_for_selector("#foreign-bar:not(.hidden)", timeout=15000)
            check("进入他人目录后共享提示条标出目录主人",
                 "boss" in bob.inner_text("#foreign-owner"), bob.inner_text("#foreign-owner"))
            check("他人目录里没有管理员共享按钮",
                 bob.locator('button[title="共享此文件夹"]').count() == 0)

            # ---- 8. bob 在他人共享目录里上传，落在自己那一格，配额算 bob ----
            boss_used_before = httpx.get(base + "/api/quota", headers=auth, timeout=10).json()["used_bytes"]
            bob_file = work_dir / "bob.txt"
            bob_file.write_text("from bob\n", encoding="utf-8")
            bob.set_input_files("#file-input", str(bob_file))
            wait_row(bob, "bob", timeout=30000)  # 落点是 docs/bob/，页面里出现 bob 这一格
            check("bob 在共享目录里上传后出现自己那一格", True)

            listing = httpx.get(base + "/api/files/list", headers=auth,
                                params={"path": "/docs", "owner": "boss"}, timeout=10).json()
            names = [e["name"] for e in listing.get("entries", [])]
            need("boss 侧能看到 docs/bob 这一格", "bob" in names, str(names))
            inner = httpx.get(base + "/api/files/list", headers=auth,
                             params={"path": "/docs/bob", "owner": "boss"}, timeout=10).json()
            need("bob 的文件落在 docs/bob/bob.txt",
                 [e["name"] for e in inner.get("entries", [])] == ["bob.txt"], str(inner))
            boss_used_after = httpx.get(base + "/api/quota", headers=auth, timeout=10).json()["used_bytes"]
            need("bob 的上传不记在 boss 的配额上", boss_used_after == boss_used_before,
                 f"{boss_used_before} -> {boss_used_after}")
            bob_quota = httpx.get(base + "/api/quota", headers=bob_auth, timeout=10).json()
            need("bob 的上传记在 bob 的配额上", bob_quota["used_bytes"] > 0, str(bob_quota))

            # 自己的目录里看不到 boss 的东西
            bob_home = httpx.get(base + "/api/files/list", headers=bob_auth,
                                 params={"path": "/"}, timeout=10).json()
            need("bob 自己的根目录不含 docs",
                 "docs" not in [e["name"] for e in bob_home.get("entries", [])], str(bob_home))

            # ---- 9. 删除 ----
            boss.goto(base, wait_until="load")
            wait_row(boss, "hi.txt")
            row(boss, "hi.txt").locator('button[title="删除"]').click()
            boss.click("#modal-ok")
            boss.wait_for_selector('.row:has(.row-name:text-is("hi.txt"))', state="detached", timeout=20000)
            check("删除后文件从列表消失", True)

            # ---- 10. 退出登录 ----
            bob.click("#btn-logout")
            bob.wait_for_selector("#view-auth:not(.hidden)", timeout=10000)
            check("退出后回到登录页", bob.is_visible("#view-auth"))
            need("退出后本地令牌已清除",
                 not bob.evaluate("() => localStorage.getItem('subdrive_token')"))

            need("页面没有未捕获的 JS 异常", not errors, "; ".join(errors[:3]))
            try:
                boss_ctx.close()
            except Exception:
                pass
            try:
                bob_ctx.close()
            except Exception:
                pass

        print(f"\n{len(PASSED)} 项通过，{len(FAILED)} 项失败", flush=True)
        return 0 if not FAILED else 1
    finally:
        if browser is not None:
            try:
                browser.close()
            except Exception:
                pass
        if proc is not None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except Exception:
                proc.kill()
        shutil.rmtree(data_dir, ignore_errors=True)
        shutil.rmtree(work_dir, ignore_errors=True)


if __name__ == "__main__":
    try:
        sys.exit(run())
    except AssertionError:
        print(f"\n{len(PASSED)} 项通过，{len(FAILED)} 项失败（中断于首个失败项）", flush=True)
        sys.exit(1)
