# AGENTS.md

给在本仓库里工作的 AI agent（含 Codex 云端沙箱）的说明。人类读者请看 `README.md`。
本文件每轮对话都会被重复投喂：只写「不看代码就会做错」的事实，别写散文。

## 这是什么

SubDrive —— FastAPI 后端 + 原生 JS 单页前端的多用户网盘。文件本体不落本仓库，
由 `app/storage.py` 转发到 Seafile（`stub` 是本地假实现，`live` 是真实 Web API v2）。
**所有上传/下载都经后端流式转发**，下发到客户端的永远不是直链。

| 路径 | 职责 |
|---|---|
| `app/main.py` | 全部路由：auth / files（含预览、Range）/ quota / admin / speedtest，外加会话、审计、限速、配额校准。1047 行单文件，**没有 router 拆分** |
| `app/paths.py` | 路径规范化与前缀锁死（**全系统唯一实现**）：`normalize_rel_path` / `full_path` / `validate_name` / `validate_username` / `PathRejected` |
| `app/storage.py` | Seafile 适配层，`stub` / `live` 双实现；`StorageError` 家族自带 `code` / `status` |
| `static/` | 前端（`index.html` / `style.css` / `app.js` / `vault.js` / `uploadplan.js`）+ 品牌二进制 `logo.png` / `favicon.png` |
| `test_smoke.py` | 冒烟测试 23 项 |
| `test_features.py` | 功能测试 43 项（F1 加密文件夹 / F2 测速 / F3 预览与 Range / F4 管理员提升） |
| `test_storage_live.py` | `LiveStorage` 请求级回归 15 项（`httpx.MockTransport`，不联网） |
| `test_crypto.mjs` | JS 侧 SDV1 加解密 10 项，与 Python/Dart 共用 `testdata/crypto_vector.json` |
| `test_uploadplan.mjs` | 整文件夹上传的目录计划（`planFolderUpload`）13 项，纯逻辑 |
| `testdata/crypto_vector.json` | SDV1 跨端固定向量，只由 `tools/gen_vector.py` 生成 |
| `tools/gen_vector.py` | 重新生成上面那份向量（`tools/` 下唯一的脚本，不是测试） |
| `CRYPTO.md` | SDV1 加密格式规范（Web / Flutter / Python 三端共用） |
| `docs/` | 本项目的长期记忆：`DECISIONS.md`（已定决策+为什么）/ `DEAD-ENDS.md`（试过并放弃的方案）/ `STATUS.md`（现状+未决问题）。**动手前先读 `docs/STATUS.md` 的「未决问题」，别把已否掉的方案重新提一遍** |
| `scripts/codex-setup.sh` | 云端环境的依赖安装脚本（Codex 环境里设为 setup 脚本） |
| `screenshots/` | README 引用的 13 张界面截图（明/暗 × 登录/文件/后台/测速/保险库/预览 + 移动端） |
| `Dockerfile` / `docker-compose.yml` / `.env.example` | 部署与配置（镜像内监听 8000，compose 把 `127.0.0.1:8001` 映射到容器的 8000） |

## 环境准备

云端沙箱用仓库内脚本，一次装完：

```bash
bash scripts/codex-setup.sh
```

**本机（Windows，就是这台机器）**：venv 已存在于 `.venv\`（Python 3.14），直接用，别重建：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install pytest cryptography
```

POSIX / 云端等价写法：`python3 -m venv .venv` → `.venv/bin/pip install -r requirements.txt pytest cryptography`。

运行时依赖只有 4 个（`fastapi` / `uvicorn[standard]` / `python-multipart` / `httpx`）。
`cryptography` 与 `pytest` 只用于测试与向量生成（`test_features.py`、`tools/gen_vector.py`），
没写进 `requirements.txt`。**按「依赖装在哪个解释器」选写法**：云端全局装好是 `python3 test_smoke.py`，
本机是 `.\.venv\Scripts\python.exe test_smoke.py`。不要写死 `.venv/bin/python` 去跑一个不存在的 venv。

两条本机专有坑：

- **测试不是 pytest 用例**：五个测试都是 `main()` 脚本，`pytest test_smoke.py` 会收集 0 个（exit 5）。
  必须直接 `python test_smoke.py`；装了 pytest 只当顺手工具，别指望 `pytest -q` 跑全套。
- **控制台是 GBK**：先 `$env:PYTHONIOENCODING="utf-8"`。`test_smoke.py` / `test_features.py` 已自带
  `sys.stdout.reconfigure(encoding="utf-8")`，但 `test_storage_live.py` 没有——GBK 下结尾打印
  `✅` 会抛 `UnicodeEncodeError` 并 exit 1（测试其实全过了，骗你失败）。
- Node ≥19（本机 v24，自带 Web Crypto）。两个 `.mjs` 零依赖、无 `package.json`、无构建步骤。

## 运行

本机 PowerShell（stub 模式，不联网）：

```powershell
$env:DATA_DIR=".\data"; $env:SEAFILE_MODE="stub"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

POSIX / 云端等价写法：

```bash
DATA_DIR=./data SEAFILE_MODE=stub .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

打开 `http://127.0.0.1:8001/`：`GET /` 返回 200（`static/index.html`），`GET /api/auth/me` 未登录返回 401。

- **环境变量在 `import app.main` 时固化**：`DATA_DIR` / `DB_PATH` / `SEAFILE_MODE` / 各限额在模块级
  读入并 `mkdir`，`storage` 也在导入时创建。改环境变量必须在启动进程之前，运行中改无效
  （测试正是靠「先设 `DATA_DIR=tempfile.mkdtemp()` 再 import」隔离工作区的）。
- `SEAFILE_MODE=live` 启动即 `auth/ping` 校验令牌，失败直接停机（fail closed）。
- `docs_url=None` / `redoc_url=None` 是故意的：线上不暴露 OpenAPI 文档，别打开。

## 测试（逐文件：命令 + 覆盖范围）

全部在仓库根目录执行。`test_smoke.py` / `test_features.py` 启动即把 `DATA_DIR` 指向
`tempfile.mkdtemp()` 并设 `CALIBRATE_INTERVAL_SECONDS=0`，不污染工作区。

| 命令 | 项数 | 覆盖范围 |
|---|---|---|
| `.\.venv\Scripts\python.exe test_smoke.py` | 23 | 邀请码注册（无效/过期/撤销/复用）、建夹投影、登录与会话、路径穿越电池 14 例、跨用户隔离、上传→列表→下载字节一致、配额拦截与删除释放、改密码、禁用/启用、登录限速、用量校准、文件详情 |
| `.\.venv\Scripts\python.exe test_features.py` | 43 | F1 加密文件夹 10（后端无明文名/明文内容、往返字节一致、错密码被拒、blob 大小=明文+33、密文计配额）；F2 测速 6（需登录、字节数精确、不计配额不落盘、并发 409、锁释放）；F3 预览与 Range 12（类型与 inline、Markdown 以纯文本下发、跨用户被拦、206 闭区间/后缀段/开放段、越界 416、无 Range 回退 200）；F4 管理员 15（`owner_protected` / `owner_required`、被提升者可用会话、审计、404） |
| `.\.venv\Scripts\python.exe test_storage_live.py` | 15 | `LiveStorage` 的 HTTP 形状：删除必须是 `HTTP DELETE`、`p` 参数百分号编码、下载地址 `200+JSON 字符串` 与 `302+Location` 两种形式、Range 分片、全程无 POST、无未命中路由 |
| `node test_crypto.mjs` | 10 | SDV1 向量与自洽：派生密钥一致、文件/清单/校验块可解、错密码必失败、信封 33 字节开销与魔数版本、roundtrip、GCM 拒绝篡改 |
| `node test_uploadplan.mjs` | 13 | `planFolderUpload`：散文件、目录去重、父目录先于子目录、空目录进 `extraDirs`、路径清洗、垃圾输入跳过、`..` 段不被吞 |

改动 SDV1 格式时才需要跑生成器：`.\.venv\Scripts\python.exe tools\gen_vector.py`（会重写
`testdata/crypto_vector.json`，跑完必须让三端测试重新全绿）。

五项全绿才算完成；任一失败就是真失败，不要跳过、不要改断言来凑。没有 CI，这五条就是唯一门禁。

## 代码风格与错误契约（从现有代码归纳，新增代码照做）

- **路径**：用户输入路径一律先过 `app/paths.py`——`_user_full(user, raw)` 里 `normalize_rel_path`
  + `full_path`，名字走 `validate_name`，用户名走 `validate_username`。**不许在别处自己
  `split` / `join` / `os.path` 拼路径**（那是第二实现，必然漏边界）。已知现存例外一处：
  `app/main.py:616` 的 `f"{full}/{name}"`（`name` 先过 `validate_name`，当前不可利用，但别再学）。
  `app/storage.py` 现在有形状体检 `_assert_full_path()`（绝对路径 + 无 `..`/反斜杠/控制字符/
  尾随空格点），stub 与 live 都过；但它**不知道当前用户是谁，挡不住跨用户冒名**。用户隔离
  真正的门只有 `_user_full`（`main.py:587-590`），新增路由必须自己走它。
- **错误形状**：业务错误用 `err(status, code, message)` 抛 `HTTPException`，响应是
  `{"detail": {"error": <snake_case 英文 code>, "message": <中文，给用户看>}}`；存储层与路径异常
  由 app 级 `exception_handler` 返回**扁平** `{"error": ..., "message": ...}`。前端两种都读
  （`detail?.message || data?.message`）——加错误分支别破坏这两层形状。
- **新增接口**：写进 `app/main.py`（当前没有 router 目录，别为一个小接口开新模块）；输入用
  Pydantic 模型，目录不存在的普通错误走 `err(404, "not_found", ...)` 这类既有 code。
- **数据库**：一律 `with _db_lock, get_db() as db:`。`get_db()` 是 `isolation_level=None`（autocommit），
  所以写操作必须持 `_db_lock`；schema 全在 `init_db()` 的 `CREATE TABLE IF NOT EXISTS` 里。
- **审计**：任何改文件、改配额、改权限的写操作都要 `audit(db, user_id, action, path, size, ip, result)`
  留痕，`result` 用 `ok` / `denied`，否则后台查不到。
- **命名**：函数与变量 snake_case；模块私有 helper 前缀下划线（`_user_full`、`_range_span`、
  `_db_lock`、`_PREVIEW_MIME`）；Pydantic 输入模型 PascalCase + `In` 后缀（`MkdirIn`）；
  分区注释 `# ---------- 名称`；docstring/注释中文，解释「为什么」。
- **前端**：原生 JS 经典脚本（`<script src>` 直出，**没有 ESM、没有打包、没有 npm**）。
  `vault.js` 暴露 `globalThis.SDVault`、`uploadplan.js` 暴露 `globalThis.SubDriveUpload`，
  正是为了让 Node 测试 `eval()` 它们——改成模块会同时打断 `index.html` 和两个 `.mjs` 测试。
  渲染用户内容只许 `textContent` 或转义后写入；Markdown 先转义再渲染，原始 HTML 永不进 DOM，
  链接只放行 `http/https/mailto`。
- **依赖**：不新增。`httpx` 在 live 模式里延迟 `import`。
- **编码**：源码与文案 UTF-8，界面中文；文件 LF（`.gitattributes` 的 `* text=auto`）。

## 硬性约定

1. **秘密只从环境变量读**，永不写进代码、仓库、日志、测试固件。`.env` 已在 `.gitignore` 里，
   变量清单见 `.env.example`。细节见下节「密钥纪律」。
2. **路径安全只允许改 `app/paths.py`**。其它模块不得自行拼接或规范化用户输入路径
   （规格 §7-1：这条防线不许有第二实现）。改动后必须让 `test_smoke.py` 的穿越电池保持全绿
   ——**现状是 17 例**（`evil_strict` 13 例必须 403 + `evil_loose` 4 例 404 亦可；含尾随空格/
   点的 `..`、NUL、超长段等形态，项数会打印在结果里，改动后对一遍）。**加规则必须同时加用例**，
   否则下一个人重构时会把这条防线悄悄改回去。
3. **默认 `SEAFILE_MODE=stub`**：本地与 CI 一律不联网，任何改动不得让 stub 路径依赖真实 Seafile。
4. 文本一律 UTF-8，界面文案中文。文件内容与文件名保持 ASCII 路径（云端跨平台安全）。
5. 加密文件夹的格式受 `CRYPTO.md`（SDV1）约束，改格式必须同步 `test_crypto.mjs`、
   `testdata/crypto_vector.json`、`static/vault.js`、`tools/gen_vector.py` 与 Flutter 端，
   否则跨端不互通。
6. 运行时数据只写 `DATA_DIR`（默认 `./data`，已忽略），不要往仓库目录写别的。

## 密钥纪律

- 键名可以从 `.env.example`、`README.md` 变量表、代码里的 `os.environ.get` 核对；
  **值永不打印、永不回显、永不入仓、永不贴进聊天、永不写进测试固件**。
- 只有 `.env.example` 入仓（`.gitignore` 忽略 `.env` 与 `.env.*`）。服务器上令牌只经 `chmod 600`
  的 env 文件注入；`docker-compose.yml` 里明确写着不要把令牌写进该文件。
- live 模式三件套 `SEAFILE_BASE_URL` / `SEAFILE_API_TOKEN` / `SEAFILE_REPO_ID` 缺一即启动
  `RuntimeError`，`ping` 失败即停机（fail closed）。另可选 `SEAFILE_REPO_NAME`。
- 账户侧：`SUBDRIVE_ADMIN_USERNAME` + `SUBDRIVE_ADMIN_PASSWORD` 仅在首次启动且该用户不存在时建号；
  引导失败只打印用户名，不打印口令。
- 审计表与 stdout 只允许 username / path / size / ip / action，令牌、口令、文件内容一律不许进。
- 代码里可读但 `.env.example` 尚未列出的：`DB_PATH`、`REGISTER_MAX_FAILS_PER_IP`、
  `SPEEDTEST_DEFAULT_BYTES`（改默认值时顺手补进 `.env.example`）。

## 禁区（没有明确指令不许碰）

| 路径 | 为什么 |
|---|---|
| `.env`、任何真实令牌 / base url / repo_id | 未入仓的机密，只在服务器 env 文件里 |
| `data/`、`*.db`、`*.db-wal`、`.venv/`、`__pycache__/`、`.pytest_cache/` | 运行时产物与本地环境，不入仓、不当固件 |
| `screenshots/**`（13 张 PNG，合计 2.1 MB） | README 引用的发布截图，重生成会整批改二进制 |
| `static/logo.png`、`static/favicon.png` | 品牌资产（697 KB / 154 KB 二进制） |
| `testdata/crypto_vector.json` | SDV1 固定向量，只能由 `tools/gen_vector.py` 重生成 |
| `CRYPTO.md` + `static/vault.js` + `test_crypto.mjs` + `tools/gen_vector.py` | SDV1 四件套，改一处即改四处（外加 Flutter 端） |
| `Dockerfile`、`docker-compose.yml`、`scripts/codex-setup.sh` | 部署与云端环境配置 |
| `.gitattributes`、`.gitignore` | 行尾归一化与忽略规则，动了会污染全仓 diff |

- git：`status` / `log` / `diff` / `show` 等只读命令随便用。**本地 `commit` 允许**，但只在五条测试
  全绿之后、且一次只提交你确实改过的文件（先 `git status --short` 核对，别 `git add -A`）。
  **`push` / `pull` / `rebase` / 任何重写历史的操作一律等人来做**——什么时候上线是人的决定。
- 运行、测试、调试只允许往 `DATA_DIR` 及其临时目录写，别在仓库根留下 `data/` 或临时上传文件。

## 已知空白（改到相关处顺手补，别假装有）

- **没有数据库迁移**：schema 全在 `init_db()` 的 `CREATE TABLE IF NOT EXISTS` 里，没有版本号也没有
  migration 目录，老库加字段只能手工迁移。动表前先想清楚线上已有数据。
- **没有 API 契约文档**：`/docs` 被显式关闭，错误码与响应形状只能读代码（见「错误形状」）。
  新增或改动接口时，至少在上面的「代码风格与错误契约」里补一行。

## 验收命令（一次改动「算通过」的标准）

仓库根目录、PowerShell：

```powershell
$env:PYTHONIOENCODING="utf-8"
.\.venv\Scripts\python.exe test_smoke.py         # 23 项，exit 0
.\.venv\Scripts\python.exe test_features.py      # 43 项，exit 0
.\.venv\Scripts\python.exe test_storage_live.py  # 15 项，exit 0
node test_crypto.mjs                             # 10 项，exit 0
node test_uploadplan.mjs                         # 13 项，exit 0
```

- 五条全 exit 0 且项数对得上才算通过；没有 CI，这就是唯一门禁。
- 动过 `app/main.py` 或 `static/` 再加一条：起服务后 `GET /` 得 200、`GET /api/auth/me` 未登录得 401。
- 收尾 `git status --short` 只应看到你打算改的文件（`data/`、`__pycache__/` 等不应出现）。
