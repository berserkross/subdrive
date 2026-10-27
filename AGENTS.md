# AGENTS.md

给在本仓库里工作的 AI agent（含 Codex 云端沙箱）的说明。人类读者请看 `README.md`。

## 这是什么

SubDrive —— FastAPI 后端 + 原生 JS 单页前端的多用户网盘。文件本体不落本仓库，
由 `app/storage.py` 转发到 Seafile（`stub` 模式是本地假实现）。**所有上传/下载都经后端流式转发**，
下发到客户端的永远不是直链。

| 路径 | 职责 |
|---|---|
| `app/main.py` | 全部路由：auth / files / quota / admin，外加会话、审计、限速、配额校准 |
| `app/paths.py` | 路径规范化与前缀锁死（**全系统唯一实现**） |
| `app/storage.py` | Seafile 适配层，`stub` / `live` 双实现 |
| `static/` | 前端（`index.html` / `style.css` / `app.js` / `vault.js` / `uploadplan.js`） |
| `test_smoke.py` | 冒烟测试 23 项 |
| `test_features.py` | 功能测试 43 项（含加密文件夹、测速、预览与 Range、管理员提升） |
| `test_crypto.mjs` | JS 侧 SDV1 加解密 10 项，与 Python/Dart 共用 `testdata/crypto_vector.json` |
| `scripts/codex-setup.sh` | 云端环境的依赖安装脚本（Codex 环境里设为 setup 脚本） |

## 环境准备

云端沙箱用仓库内脚本，一次装完：

```bash
bash scripts/codex-setup.sh
```

本机开发则建虚拟环境：

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt pytest cryptography
```

`cryptography` 只被 `test_features.py` 用来做独立于后端实现的 AES-GCM 对照，
没写进 `requirements.txt`（运行时不依赖它）。跑测试前必须装。

**下面的命令按「依赖装在哪个解释器里」选写法**：云端全局装好就是 `python3 test_smoke.py`；
本机 venv 则是 `.venv/bin/python test_smoke.py`（Windows 为 `.venv\Scripts\python.exe`）。
不要写死 `.venv/bin/python` 去跑一个不存在的 venv。

## 运行

```bash
DATA_DIR=./data SEAFILE_MODE=stub python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

打开 `http://127.0.0.1:8001/`。stub 模式不需要真实 Seafile，也不联网。

## 测试

```bash
python3 test_smoke.py      # 23 项
python3 test_features.py   # 43 项
node test_crypto.mjs       # 10 项
```

三个都必须全绿才算完成；任一失败就是真失败，不要跳过或改断言来凑。
两个 Python 测试都在启动时把 `DATA_DIR` 指向 `tempfile.mkdtemp()`，
不会污染仓库工作区。

## 硬性约定

1. **秘密只从环境变量读**，永不写进代码、仓库、日志、测试固件：
   `SEAFILE_API_TOKEN`、`SUBDRIVE_ADMIN_PASSWORD`。`.env` 已在 `.gitignore` 里，
   变量清单见 `.env.example`。
2. **路径安全只允许改 `app/paths.py`**。其它模块不得自行拼接或规范化用户输入路径
   （规格 §7-1：这条防线不许有第二实现）。改动后必须让 `test_smoke.py` 的 13 例穿越电池保持全绿。
3. **默认 `SEAFILE_MODE=stub`**：本地与 CI 一律不联网，任何改动不得让 stub 路径依赖真实 Seafile。
4. 文本一律 UTF-8，界面文案中文。文件内容与文件名保持 ASCII 路径（云端跨平台安全）。
5. 加密文件夹的格式受 `CRYPTO.md`（SDV1）约束，改格式必须同步 `test_crypto.mjs`、
   `testdata/crypto_vector.json` 与 Flutter 端，否则跨端不互通。
6. 运行时数据只写 `DATA_DIR`（默认 `./data`，已忽略），不要往仓库目录写别的。
