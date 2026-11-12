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
    """用本机已装的 Chrome 驱动（channel 定位，不跑 playwright install、不下载浏览器）。

    想看它自己点：$env:SUBDRIVE_E2E_HEADED='1'
    想指定别的 Chromium 内核：$env:SUBDRIVE_E2E_CHANNEL='msedge'
    """
    headless = os.environ.get("SUBDRIVE_E2E_HEADED", "") == ""
    want = os.environ.get("SUBDRIVE_E2E_CHANNEL", "").strip()
    channels = (want,) if want else ("chrome", "msedge")
    last = None
    for channel in channels:
        try:
            return pw.chromium.launch(channel=channel, headless=headless)
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


def open_side(page):
    """顶栏只剩品牌 + 用户：次级入口都先点开头像侧边栏。"""
    page.click("#user-chip")
    page.wait_for_selector("#side-panel.open", timeout=5000)


def open_nickname(page):
    """改昵称现在住在设置页的「账号与安全」里。"""
    open_side(page)
    page.click("#btn-settings")
    page.wait_for_selector("#view-settings:not(.hidden)", timeout=10000)
    page.click('#set-nav [data-panel="account"]')
    page.click("#set-nickname")
    page.wait_for_selector("#nick-input", timeout=10000)


def back_to_drive(page):
    page.click("#set-back")
    page.wait_for_selector("#view-drive:not(.hidden)", timeout=10000)


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
            open_side(boss)
            need("首个用户拿到管理员入口（侧边栏内）", boss.is_visible("#btn-admin"))
            boss.click("#side-close")

            boss_token = boss.evaluate("() => localStorage.getItem('subdrive_token')")
            auth = {"Authorization": f"Bearer {boss_token}"}

            # ---- 1b. 改名字（点头像/用户名处那个 chip）----
            open_nickname(boss)
            boss.fill("#nick-input", "新老板")
            boss.click("#modal-ok")
            boss.wait_for_selector("#modal-overlay", state="hidden", timeout=10000)
            check("改名字后顶栏立刻更新", "新老板" in boss.inner_text("#user-name"),
                  boss.inner_text("#user-name"))
            back_to_drive(boss)
            me_now = httpx.get(base + "/api/auth/me", headers=auth, timeout=10).json()
            check("后端也记下了新昵称", me_now.get("nickname") == "新老板", str(me_now))
            check("登录名没跟着变", me_now.get("username") == "boss", str(me_now))
            open_nickname(boss)
            boss.fill("#nick-input", "老板")
            boss.click("#modal-ok")
            boss.wait_for_selector("#modal-overlay", state="hidden", timeout=10000)
            back_to_drive(boss)
            check("改回原昵称（后面几步依赖「老板」）",
                  "老板" in boss.inner_text("#user-name"), boss.inner_text("#user-name"))

            # ---- 2. 新建文件夹 ----
            boss.click("#btn-mkdir")
            boss.fill("#m-name", "docs")
            boss.click("#modal-ok")
            wait_row(boss, "docs")
            check("新建文件夹出现在列表", True)

            # ---- 2.1 「＋ 新建」是唯一建夹入口：类型与可见性都在弹窗里 ----
            boss.click("#btn-mkdir")
            need("新建弹窗里有私密/公开可见性选择", boss.is_visible("#m-vis"))
            need("管理员能看到「公开共享」选项",
                 boss.locator('#m-vis .seg-btn[data-vis="shared"]').count() == 1)
            boss.click('#m-kind .seg-btn[data-kind="vault"]')
            need("选加密文件夹时出现密码输入", boss.is_visible("#m-vpass"))
            boss.click('#m-kind .seg-btn[data-kind="plain"]')
            check("切回普通文件夹后密码框收起", not boss.is_visible("#m-vpass"))
            boss.fill("#m-name", "team")
            boss.click('#m-vis .seg-btn[data-vis="shared"]')
            need("选公开共享后出现成员与上限字段",
                 boss.is_visible("#m-mode") and boss.is_visible("#m-cap"))
            boss.click("#modal-ok")
            wait_row(boss, "team")
            boss.wait_for_selector("#shared-card:not(.hidden)", timeout=15000)
            check("弹窗里勾选公开共享即建成共享文件夹",
                  "team" in boss.inner_text("#shared-list"), boss.inner_text("#shared-list"))

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

            # ---- 4.2 同名上传先问一声（替换 / 两者都保留 / 跳过）----
            dup = work_dir / "hi.txt"
            dup.write_text("second version, longer\n", encoding="utf-8")
            boss.set_input_files("#file-input", str(dup))
            boss.wait_for_selector(".conflict-actions", timeout=20000)
            check("同名上传弹出三选一", "两者都保留" in boss.inner_text(".conflict-actions"),
                  boss.inner_text(".conflict-actions"))
            boss.click('.conflict-actions button[data-v="rename"]')
            wait_row(boss, "hi (2).txt")
            check("两者都保留生成 hi (2).txt，原名仍在",
                  row(boss, "hi.txt").count() == 1 and row(boss, "hi (2).txt").count() == 1)
            boss.set_input_files("#file-input", str(dup))
            boss.wait_for_selector(".conflict-actions", timeout=20000)
            boss.click('.conflict-actions button[data-v="overwrite"]')
            boss.wait_for_selector("#modal-overlay", state="hidden", timeout=20000)
            boss.wait_for_timeout(1200)
            check("选替换后没有多出新行",
                  row(boss, "hi.txt").count() == 1 and row(boss, "hi (3).txt").count() == 0)
            boss.set_input_files("#file-input", str(dup))
            boss.wait_for_selector(".conflict-actions", timeout=20000)
            boss.click('.conflict-actions button[data-v="skip"]')
            wait_row(boss, "hi.txt")
            check("选跳过不产生新文件",
                  boss.locator('#file-list .row-name:text-is("hi (3).txt")').count() == 0)

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

            # 目录搜索与筛选只作用于当前列表，失败状态保留重试入口。
            boss.fill("#file-search", "hi (2)")
            need("目录搜索只显示匹配文件", boss.locator("#file-list .row").count() == 1 and row(boss, "hi (2).txt").count() == 1)
            boss.select_option("#file-kind", "dir")
            need("类型筛选有独立无结果态", boss.is_visible("#file-no-matches") and not boss.is_visible("#empty-state"))
            boss.click("#file-clear-filters")
            boss.select_option("#file-sort", "size")
            need("大小排序显示大文件在前",
                 boss.locator('#file-list .row:has(.row-sel) .col-size').evaluate_all(
                     "cells => cells.filter(c=>c.textContent.endsWith(' B')).map(c=>parseFloat(c.textContent)).every((v,i,a)=>!i||a[i-1]>=v)"))
            boss.select_option("#file-sort", "")
            boss.route("**/api/files/list?*", lambda request: request.fulfill(
                status=503, json={"detail":{"error":"seafile_unreachable"}}))
            boss.locator("#crumbs button").first.click()
            boss.wait_for_selector("#list-error:not(.hidden)")
            need("列表失败与空文件夹区分", not boss.is_visible("#empty-state") and boss.is_visible("#list-retry"))
            boss.unroute("**/api/files/list?*")
            boss.click("#list-retry")
            wait_row(boss, "hi.txt")
            need("重试恢复当前目录", not boss.is_visible("#list-error"))
            boss.route("**/api/shared/list", lambda request: request.fulfill(
                status=503, json={"detail":{"error":"seafile_unreachable"}}))
            boss.click('#nav-scope [data-scope="public"]')
            boss.wait_for_selector("#public-error:not(.hidden)")
            need("共享加载失败可重试", boss.is_visible("#public-retry") and not boss.is_visible("#public-empty"))
            boss.unroute("**/api/shared/list")
            boss.click("#public-retry")
            boss.wait_for_selector("#public-list .shared-item")
            boss.click('#nav-scope [data-scope="mine"]')
            wait_row(boss, "hi.txt")

            # 真浏览器队列保留原落点，失败后手动重试。
            held_upload = []
            def hold_upload(request):
                held_upload.append(request)
            boss.route("**/api/files/upload?*", hold_upload)
            boss.evaluate("window.SubDriveUploadTuning.maxConcurrent = 1")
            upload_fixture = {"name":"ux-retry.txt","mimeType":"text/plain","buffer":b"retry example"}
            cancelled_fixture = {"name":"ux-cancel.txt","mimeType":"text/plain","buffer":b"cancel"}
            boss.set_input_files("#file-input", [upload_fixture, cancelled_fixture])
            queued = boss.locator(".upload-item").filter(has_text="ux-cancel.txt")
            queued.get_by_role("button", name="取消上传").click()
            need("排队上传可取消", "已取消上传" in queued.inner_text())
            boss.wait_for_function("uploadInflight === 1")
            if not held_upload:
                boss.locator(".upload-item").filter(has_text="ux-retry.txt").wait_for()
                for _ in range(20):
                    if held_upload: break
                    boss.wait_for_timeout(50)
            need("队列取消不会发出该文件请求", len(held_upload) == 1)
            held_upload[0].fulfill(status=503, json={"detail":{"error":"seafile_unreachable"}})
            failed = boss.locator(".upload-item.failed").filter(has_text="ux-retry.txt")
            failed.wait_for()
            boss.click("#upload-close")
            boss.click("#upload-queue-toggle")
            need("关闭再打开仍可看到失败条目", failed.is_visible())
            boss.unroute("**/api/files/upload?*")
            failed.get_by_role("button", name="重试").click()
            wait_row(boss, "ux-retry.txt")
            need("上传重试成功且取消项未落盘", row(boss, "ux-cancel.txt").count() == 0)
            boss.click("#upload-close")

            row(boss, "ux-retry.txt").locator('button[title="重命名"]').click()
            boss.fill("#m-name", "ux-renamed.txt")
            boss.click("#modal-ok")
            wait_row(boss, "ux-renamed.txt")
            boss.click("#toast-action")
            wait_row(boss, "ux-retry.txt")
            need("重命名通知支持撤销", row(boss, "ux-renamed.txt").count() == 0)
            row(boss, "ux-retry.txt").locator('button[title="移动"]').click()
            boss.click('#modal-body .folder-pick button[data-dir="docs"]')
            boss.click("#modal-ok")
            boss.wait_for_selector("#toast-action:not(.hidden)")
            boss.click("#toast-action")
            wait_row(boss, "ux-retry.txt")
            need("移动通知支持撤销", "已撤销" in boss.inner_text("#toast"))
            boss.click("#toast-close")
            need("通知可主动关闭", not boss.is_visible("#toast"))
            boss.set_viewport_size({"width":390,"height":844})
            item = row(boss, "ux-retry.txt")
            item.locator(".row-more").click()
            need("390px 行菜单可访问", item.locator(".row-action-list.is-open").is_visible())
            boss.keyboard.press("Escape")
            need("移动行菜单 Escape 收起并还焦点", item.locator(".row-more").evaluate("e=>document.activeElement===e"))
            boss.set_viewport_size({"width":1400,"height":950})

            # ---- 5. 创建共享文件夹（名单留空＝全员可见）----
            boss.wait_for_selector(
                '#file-list .row:has(.row-name:text-is("docs")) button[title="共享此文件夹"]',
                timeout=20000)
            row(boss, "docs").locator('button[title="共享此文件夹"]').click()
            boss.wait_for_selector("#s-mode", timeout=10000)
            boss.click("#modal-ok")
            boss.wait_for_selector("#shared-card:not(.hidden)", timeout=15000)
            # 前面已经建过 team，共享卡本来就可见；这里必须等到 docs 自己进列表，
            # 否则紧接着的清单断言会读到「建之前」的数据（曾偶发失败一次）。
            boss.wait_for_selector('#shared-list .shared-item:has-text("docs")', timeout=15000)
            check("共享卡出现", boss.is_visible("#shared-card"))
            check("共享卡标明我创建", "我创建" in boss.inner_text("#shared-list"),
                 boss.inner_text("#shared-list"))
            shared = httpx.get(base + "/api/shared/list", headers=auth, timeout=10).json()
            need("后端共享清单含 docs 且 is_mine",
                 any(f["path"] == "docs" and f["is_mine"] for f in shared["folders"]),
                 str(shared))

            # ---- 5a. 公共区域：切过去看得到，点得进去，面包屑能回来 ----
            boss.click('#nav-scope [data-scope="public"]')
            boss.wait_for_selector("#public-panel:not(.hidden)", timeout=10000)
            check("公共区域列出共享文件夹", "docs" in boss.inner_text("#public-list"),
                  boss.inner_text("#public-list"))
            check("公共区域里文件列表收起", not boss.is_visible("#dropzone"))
            check("公共区域标题栏显示数量", "共享文件夹" in boss.inner_text("#public-count"),
                  boss.inner_text("#public-count"))
            check("公共区域卡片带用量条", boss.locator("#public-list .si-bar").count() >= 1,
                  str(boss.locator("#public-list .si-bar").count()))
            boss.click("#public-list .shared-item")
            boss.wait_for_selector("#dropzone:not(.hidden)", timeout=10000)
            boss.wait_for_function(
                "() => document.querySelector('#crumbs') &&"
                " document.querySelector('#crumbs').textContent.includes('docs')",
                timeout=10000)
            check("面包屑第一格是公共区域",
                  "公共区域" in boss.inner_text("#crumbs"), boss.inner_text("#crumbs"))
            boss.click('#crumbs button:has-text("公共区域")')
            boss.wait_for_selector("#public-panel:not(.hidden)", timeout=10000)
            check("面包屑能回到公共区域", boss.is_visible("#public-panel"))
            boss.click('#nav-scope [data-scope="mine"]')
            boss.wait_for_selector("#dropzone:not(.hidden)", timeout=10000)
            check("切回我的网盘显示文件列表", boss.is_visible("#dropzone"))

            # ---- 5b. 每目录上限（D35）：在「管理共享」里设成员上限 ----
            row(boss, "docs").locator('button[title="管理共享"]').click()
            boss.wait_for_selector("#s-maxmem", timeout=10000)
            boss.fill("#s-maxmem", "1")
            boss.click("#modal-ok")
            boss.wait_for_selector('#shared-list .si-meta:has-text("上限 1")', timeout=15000)
            check("共享卡显示成员上限与用量", "上限 1" in boss.inner_text("#shared-list"),
                  boss.inner_text("#shared-list"))
            shared = httpx.get(base + "/api/shared/list", headers=auth, timeout=10).json()
            docs = [f for f in shared["folders"] if f["path"] == "docs"][0]
            need("后端记下了成员上限", docs["max_members"] == 1, str(docs))

            # ---- 5c. 成员选择器：搜索 / 勾选 / 空名单拦截（GUI 化）----
            row(boss, "docs").locator('button[title="管理共享"]').click()
            boss.wait_for_selector("#s-mode", timeout=10000)
            check("共享弹窗默认是「全部成员」",
                  "selected" in (boss.get_attribute('#s-mode .seg-btn[data-mode="all"]', "class") or ""))
            boss.click('#s-mode .seg-btn[data-mode="some"]')
            check("切到仅指定成员后出现搜索框", boss.is_visible("#s-search"))
            boss.fill("#s-search", "boss")
            boss.wait_for_selector("#s-list .member-item", timeout=5000)
            check("搜索框按昵称/用户名过滤",
                  boss.locator("#s-list .member-item").count() == 1,
                  f"剩 {boss.locator('#s-list .member-item').count()} 项")
            boss.click("#modal-ok")
            check("选了「仅指定成员」却一个没勾会被拦住", boss.is_visible("#modal-overlay"))
            check("拦住时提示写明该怎么办",
                  "一个都没勾" in boss.inner_text("#toast"), boss.inner_text("#toast"))
            disabled_rows = boss.locator("#s-list .member-item input[disabled]").count()
            check("创建者自己那行不可勾选（后端本来就会忽略自己）", disabled_rows == 1,
                  f"disabled 行 {disabled_rows}")
            check("创建者自己点不动，计数仍是 0",
                  "已选 0 人" in boss.inner_text("#s-count"), boss.inner_text("#s-count"))
            boss.click('#s-mode .seg-btn[data-mode="all"]')
            boss.click("#modal-ok")
            boss.wait_for_selector("#modal-overlay", state="hidden", timeout=10000)
            docs = [f for f in httpx.get(base + "/api/shared/list", headers=auth, timeout=10).json()["folders"]
                    if f["path"] == "docs"][0]
            need("改回「全部成员」＝空名单（后端语义：空＝全员）", docs["members"] == [],
                 str(docs) + " | toast=" + boss.inner_text("#toast"))

            # ---- 6. 第二个用户凭邀请码注册 ----
            invite = httpx.post(base + "/api/admin/invite-codes", headers=auth,
                                json={"note": "e2e", "max_uses": 1}, timeout=10).json()
            bob_ctx = browser.new_context(viewport={"width": 1400, "height": 950})
            bob = bob_ctx.new_page()
            bob.on("pageerror", lambda e: errors.append(str(e)))
            register(bob, base, "bob", "小明", "bobpass123", invite=invite["code"])
            check("第二个用户注册成功", bob.is_visible("#view-drive"))
            check("普通用户没有管理员入口", not bob.is_visible("#btn-admin"))
            bob.click("#btn-mkdir")
            need("普通用户的新建弹窗仍可建私密文件夹", bob.is_visible("#m-name"))
            need("普通用户看不到「公开共享」选项（B1 只有管理员能开共享）",
                 bob.locator('#m-vis .seg-btn[data-vis="shared"]').count() == 0)
            bob.click("#modal-cancel")
            bob.wait_for_selector("#modal-overlay", state="hidden", timeout=10000)

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
            open_side(bob)
            bob.click("#btn-logout")
            bob.wait_for_selector("#view-auth:not(.hidden)", timeout=10000)
            check("退出后回到登录页", bob.is_visible("#view-auth"))
            need("退出后本地令牌已清除",
                 not bob.evaluate("() => localStorage.getItem('subdrive_token')"))

            # ---- 11. 中英双语切换（默认中文，切 EN 后整页零中文）----
            # 零 CJK 断言需要 body.innerText 里没有中文用户数据，故另起一个 ASCII 昵称的用户。
            inv2 = httpx.post(base + "/api/admin/invite-codes", headers=auth,
                              json={"note": "e2e-i18n", "max_uses": 1}, timeout=10).json()
            i18n_ctx = browser.new_context(viewport={"width": 1440, "height": 900})
            en_page = i18n_ctx.new_page()
            en_page.on("pageerror", lambda e: errors.append(str(e)))
            register(en_page, base, "emma", "Emma", "emmapass123", invite=inv2["code"])
            need("语言下拉默认是简体且页面是中文",
                 en_page.input_value("#lang-select") == "zh" and "新建" in en_page.inner_text("#btn-mkdir"),
                 en_page.input_value("#lang-select") + " | " + en_page.inner_text("#btn-mkdir"))
            # 三语：下拉直接选「繁體」→「English」。繁体先验「没有简体残留」，再进英文。
            open_side(en_page)
            en_page.select_option("#lang-select", "hant")
            en_page.wait_for_function("() => document.documentElement.lang === 'zh-Hant'", timeout=5000)
            hant_text = en_page.inner_text("body")
            hant_hits = [c for c in "网说设这会个们时后点开关现实应该发" if c in hant_text]
            need("繁中模式：<html lang> 与下拉选中值正确，且无简体残留",
                 en_page.input_value("#lang-select") == "hant" and not hant_hits,
                 "leftover=" + "".join(hant_hits) + " sel=" + en_page.input_value("#lang-select"))
            en_page.select_option("#lang-select", "en")
            en_page.click("#side-close")
            en_page.wait_for_function("() => document.documentElement.lang === 'en'", timeout=5000)
            en_btn = en_page.inner_text("#btn-mkdir")
            en_col = en_page.inner_text(".col-name").strip()
            check("切到 EN 后新建按钮与文件表头变英文", ("New" in en_btn) and en_col == "Name", f"btn={en_btn} col={en_col}")
            # 公共区域也切一遍：EN 下的共享列表 / 空态都在扫描范围内
            en_page.click('#nav-scope [data-scope="public"]')
            en_page.wait_for_selector("#public-panel:not(.hidden)", timeout=10000)
            # 配额、共享列表这些是切换后异步重画的：轮询到整页零 CJK 为止（切换前的旧 toast 已由 setLang 收回）
            # 语言下拉里的选项写的是各语言的自称（简体 / 繁體 / English），不随界面语言翻译，
            # 扫「零 CJK」时按白名单剔除，别把语言名当成漏翻的文案。
            zero_cjk = """() => {
                const cjk = /[\\u4e00-\\u9fff]/;
                const allow = ["简体中文", "繁体中文"];
                let txt = document.body.innerText;
                allow.forEach((w) => { txt = txt.split(w).join(""); });
                if (cjk.test(txt)) return false;
                return ![...document.querySelectorAll("[placeholder],[title]")].some((el) =>
                    cjk.test(el.getAttribute("placeholder") || "") || cjk.test(el.getAttribute("title") || ""));
            }"""
            settled = True
            try:
                en_page.wait_for_function(zero_cjk, timeout=15000)
            except Exception:
                settled = False
            en_pub = en_page.inner_text("#public-panel").strip().replace("\n", " / ")
            scan = en_page.evaluate("""() => {
                const cjk = /[\\u4e00-\\u9fff]/;
                const hits = [];
                const allow = ["简体中文", "繁体中文"];
                let body = document.body.innerText;
                allow.forEach((w) => { body = body.split(w).join(""); });
                if (cjk.test(body)) {
                    document.querySelectorAll("#view-drive *").forEach((el) => {
                        if (el.children.length) return;
                        const t = (el.innerText || "").trim();
                        if (t && cjk.test(t) && hits.length < 12) hits.push("text " + el.tagName + "#" + el.id + "." + el.className + " = " + t);
                    });
                    const bt = body.match(/[\\u4e00-\\u9fff]/g);
                    if (bt && hits.length < 12) hits.push("innerText 剩余字符: " + [...new Set(bt)].join(""));
                }
                document.querySelectorAll("[placeholder]").forEach((el) => {
                    const v = el.getAttribute("placeholder");
                    if (cjk.test(v) && hits.length < 16) hits.push("placeholder " + (el.id || el.tagName) + " = " + v);
                });
                document.querySelectorAll("[title]").forEach((el) => {
                    const v = el.getAttribute("title");
                    if (cjk.test(v) && hits.length < 20) hits.push("title " + (el.id || el.tagName + "." + el.className) + " = " + v);
                });
                return { hits: hits, len: body.length };
            }""")
            print("      公共区域(EN)：" + en_pub[:160], flush=True)
            print("      零 CJK 扫描：innerText " + str(scan["len"]) + " 字符，命中 " + str(len(scan["hits"]))
                  + " 处，异步重画已落地=" + str(settled), flush=True)
            need("EN 模式 body.innerText 与全部 placeholder/title 零 CJK", settled and not scan["hits"],
                 "等待超时（异步区域仍是旧语言）; " + "; ".join(scan["hits"][:6]))
            en_page.click('#nav-scope [data-scope="mine"]')
            open_side(en_page)
            en_page.select_option("#lang-select", "zh")
            en_page.click("#side-close")
            en_page.wait_for_function("() => document.documentElement.lang === 'zh-CN'", timeout=5000)
            check("切回中文后按钮与表头恢复",
                  "新建" in en_page.inner_text("#btn-mkdir") and en_page.inner_text(".col-name").strip() == "名称",
                  en_page.inner_text("#btn-mkdir") + " | " + en_page.inner_text(".col-name"))
            # ---- 11b. 设置页：外观（主题 / 主色 / 语言）----
            theme_attr = "() => document.documentElement.getAttribute('data-theme')"
            bg = "() => getComputedStyle(document.body).backgroundColor"
            accent_var = "() => getComputedStyle(document.documentElement).getPropertyValue('--accent').trim()"

            open_side(en_page)
            en_page.click("#btn-settings")
            en_page.wait_for_selector("#view-settings:not(.hidden)", timeout=10000)
            need("齿轮打开设置页，地址栏落在 #/settings，默认外观分组",
                 en_page.evaluate("() => location.hash") == "#/settings"
                 and en_page.evaluate("() => document.querySelector('.set-main .set-panel:not(.hidden)').dataset.panel") == "appearance")
            need("关于页读得到版本与存储模式",
                 en_page.inner_text("#set-version").strip() != ""
                 and en_page.inner_text("#set-storage-mode").strip() != "",
                 en_page.inner_text("#set-version") + " | " + en_page.inner_text("#set-storage-mode"))

            need("设置页默认跟随系统（不写 data-theme）",
                 en_page.evaluate(theme_attr) is None, str(en_page.evaluate(theme_attr)))
            en_page.click('#set-theme-mode [data-theme-set="light"]')
            en_page.wait_for_timeout(250)
            light_bg = en_page.evaluate(bg)
            need("设置页选浅色：data-theme=light 且背景随之变化",
                 en_page.evaluate(theme_attr) == "light" and light_bg != "rgba(0, 0, 0, 0)", light_bg)
            en_page.click('#set-theme-mode [data-theme-set="dark"]')
            en_page.wait_for_timeout(250)
            dark_bg = en_page.evaluate(bg)
            need("设置页选深色：data-theme=dark 且背景比浅色深",
                 en_page.evaluate(theme_attr) == "dark" and dark_bg != light_bg, light_bg + " -> " + dark_bg)

            en_page.click('#set-accent [data-accent-set="ocean"]')
            need("设置页选主色 ocean：data-accent 与 --accent 同步",
                 en_page.evaluate("() => document.documentElement.getAttribute('data-accent')") == "ocean"
                 and en_page.evaluate(accent_var) == "#79beff", str(en_page.evaluate(accent_var)))
            en_page.evaluate("""() => {
                const el = document.querySelector('#set-accent-color');
                el.value = '#00aa88';
                el.dispatchEvent(new Event('input', { bubbles: true }));
            }""")
            en_page.wait_for_timeout(150)
            need("设置页自选主色（#00aa88）通过 inline 变量生效",
                 en_page.evaluate("() => document.documentElement.getAttribute('data-accent')") == "custom"
                 and en_page.evaluate(accent_var) == "#00aa88", str(en_page.evaluate(accent_var)))

            en_page.reload(wait_until="networkidle")
            en_page.wait_for_selector("#view-settings:not(.hidden)", timeout=15000)
            en_page.wait_for_timeout(300)
            need("刷新后仍在设置页，且深色与自选主色都保持",
                 en_page.evaluate("() => location.hash") == "#/settings"
                 and en_page.evaluate(theme_attr) == "dark"
                 and en_page.evaluate(accent_var) == "#00aa88", str(en_page.evaluate(accent_var)))

            # 上传并发：滑杆改 5，写进 localStorage 与调度钩子
            en_page.click('#set-nav [data-panel="upload"]')
            en_page.fill("#set-concurrency", "5")
            en_page.dispatch_event("#set-concurrency", "input")
            need("上传并发滑杆写进 localStorage 与 SubDriveUploadTuning",
                 en_page.evaluate("() => localStorage.getItem('subdrive_upload_conc')") == "5"
                 and en_page.evaluate("() => window.SubDriveUploadTuning.maxConcurrent") == 5)

            en_page.click('#set-nav [data-panel="about"]')
            need("关于分组可切换",
                 en_page.evaluate("() => document.querySelector('.set-main .set-panel:not(.hidden)').dataset.panel") == "about")

            # 复位：回默认主色 + 跟随系统，再回网盘（先切回外观面板，否则控件是隐藏的）
            en_page.click('#set-nav [data-panel="appearance"]')
            en_page.click('#set-accent [data-accent-set=""]')
            en_page.click('#set-theme-mode [data-theme-set="auto"]')
            en_page.click('#set-back')
            en_page.wait_for_selector("#view-drive:not(.hidden)", timeout=10000)
            need("返回网盘后不再写 data-theme/data-accent",
                 en_page.evaluate(theme_attr) is None
                 and en_page.evaluate("() => document.documentElement.getAttribute('data-accent')") is None
                 and en_page.evaluate(accent_var) == "#5038bd", str(en_page.evaluate(accent_var)))


            # Full-screen free canvas editor through its normal entry point.
            open_side(en_page)
            en_page.click("#btn-settings")
            en_page.select_option("#lang-select-settings", "en")
            en_page.click('#set-nav [data-panel="layout"]')
            en_page.click("#open-block-editor")
            editor = en_page.frame_locator("#full-block-editor")
            editor.locator("#save-editor").wait_for()
            editor.frame_locator("#drive").locator("#dropzone.module").wait_for()
            need("free canvas editor opens", editor.locator("#snap-grid").is_visible())
            need("free canvas snap defaults off", not editor.locator("#snap-grid").is_checked())
            editor.locator("#snap-grid").check()
            editor.locator("#snap-grid").uncheck()
            editor.locator('#layers [data-id="scope"] .layer-name').click()
            editor.locator("#prop-cx").fill("37")
            editor.locator("#prop-cx").press("Tab")
            editor_text = editor.locator("body").inner_text()
            editor_attrs = editor.locator("[title],[placeholder],[aria-label]").evaluate_all(
                "els => els.map(e => [e.title,e.getAttribute('placeholder'),e.getAttribute('aria-label')].join(' ')).join(' ')")
            need("free canvas EN labels zero CJK", not any(0x3400 <= ord(c) <= 0x9fff for c in editor_text + editor_attrs))
            editor.locator("#save-editor").click()
            en_page.wait_for_selector("#full-block-editor", state="detached")
            need("free canvas saves arbitrary coordinate",
                 en_page.evaluate("JSON.parse(localStorage.getItem('subdrive_canvas')).blocks.scope.x") == 37)
            need("free canvas preserves auto theme", en_page.evaluate(theme_attr) is None)
            en_page.reload(wait_until="networkidle")
            en_page.wait_for_selector("#view-settings:not(.hidden)")
            en_page.click('#set-nav [data-panel="layout"]')
            en_page.click("#open-block-editor")
            editor = en_page.frame_locator("#full-block-editor")
            editor.locator("#save-editor").wait_for()
            editor.frame_locator("#drive").locator("#dropzone.module").wait_for()
            editor.locator('#layers [data-id="scope"] .layer-name').click()
            need("free canvas restores saved coordinate", editor.locator("#prop-cx").input_value() == "37")
            editor.locator("#close-editor").click()
            en_page.click("#set-blocks-reset")
            need("free canvas reset clears supplemental storage",
                 en_page.evaluate("localStorage.getItem('subdrive_canvas')") is None)

            i18n_ctx.close()

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
