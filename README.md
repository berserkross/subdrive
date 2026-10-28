# SubDrive · 子用户网盘（一期网页端 MVP）

在现有 Seafile（drive.ourmetaverse.cn）之上加一层自研多用户网盘：子用户凭**邀请码**在本系统注册，
登录本客户端后只看到自己那一份空间；文件本体存放于主账号名下的**一个专用资料库**中，
每人一个以其用户名命名的文件夹（子账号在主账号那边的「投影」）。

设计规格：`~/workspace/goals/personal-cloud-drive-build/files/子用户网盘客户端-规格.md`（实现严格对应该规格；
下文「与规格的对应/歧义消解」记录了实现时做的具体决定）。

## 架构速览

```
浏览器（原生 JS 单页，登录/注册、文件浏览、管理员后台）
   │  Bearer session token
FastAPI 后端（本仓库 app/）—— 唯一安全边界
   │  逐请求：验会话 → 路径规范化与前缀锁死（app/paths.py，全系统唯一实现）
   │        → 配额预检 → 审计落库（SQLite：users / invite_codes / sessions / usage_cache / audit_log）
   │  app/storage.py —— 唯一允许碰 Seafile 的模块
   ├─ stub 模式（默认）：本地文件系统假实现 <DATA_DIR>/stub_storage/<repo>/<username>/…
   └─ live 模式：Seafile Web API v2（令牌只从环境变量读）
Seafile 专用库 subdrive（非加密）内：/<username>/ 一人一文件夹
```

- 密码 PBKDF2-SHA256、20 万次迭代、每用户随机盐（沿用 private-chat 约定）；
  session token 256 bit 随机、存 sessions 表、可撤销（禁用用户即删全部 session）。
- 配额双轨（规格 §3）：上传/删除增量记账 + `calibrate` 递归遍历校准（后台线程每小时跑一次，
  管理员可手动触发）；上传前预检，超额直接拒绝。
- 文件传输一期全部经后端**流式转发**（上传先分块落临时文件、全程内存恒定；下载 StreamingResponse），
  上传/下载链接永不下发到客户端（规格 §6）。
- 界面沿用 private-chat v4 设计系统（令牌、圆角、阴影、跟随系统深色模式），
  品牌标记为 Ourmetaverse 极光环（static/logo.png）。截图见 `screenshots/`（登录/文件/后台 × 明暗 + 移动端）。

## 扩展功能（2026-10-22 增补）

### 🔒 加密文件夹（客户端加密，后端只存密文）

- 每个加密文件夹有**独立的文件夹密码**（与登录密码无关）：密钥 = 文件夹密码经 PBKDF2-SHA256
  （210,000 次、每夹随机 16 字节盐）派生；每个文件在**浏览器里**用 Web Crypto AES-256-GCM
  （每文件随机 12 字节 IV）加密后才上传。格式规范见 **[`CRYPTO.md`](CRYPTO.md)**（SDV1），
  网页端与 Flutter 端严格同一格式、互通，并用同一份固定测试向量（`testdata/crypto_vector.json`）跨端验证。
- 后端/Seafile 只存不透明密文 blob（`blobs/<随机id>.enc`）；文件名映射放在加密的清单 `manifest.enc` 里，
  **连文件名对后端都不可见**。服务端可见的元数据只有：blob 的大小与数量（诚实标注，UI 亦有同样文案）。
- 文件夹密码只在内存中，永不发送到服务器、永不持久化；输错密码即清单解密失败（明确报错）；
  **密码遗失不可恢复**（创建对话框原文警告）。加密文件的配额按密文大小计。后端对加密零感知（blobs 是普通文件）。

### 🔗 共享文件夹（多人协作同一目录）

- 任何人都能把自己网盘里的**一个文件夹**变成共享文件夹：创建时选授权成员（用户名列表，留空＝全员）。
  共享后，名单内成员可**查看、下载、上传**；共享文件夹一旦创建即对名单内成员公开，创建者随时可改名单或取消共享
  （取消后内容全部保留，退回私有文件夹）。
- **配额算上传者自己**：A 的共享文件夹里，B 传 1MB 就扣 B 的额度、记在 B 名下，创建者的配额不变。
- **每人一格**：成员在共享目录里的上传/新建一律落进以自己用户名命名的子文件夹
  （`<共享目录>/…/<用户名>/`），所以「能不能删」自然等于「是不是我传的」——只能删自己那一格里的东西。
  创建者的文件成员可读不可删。
- 共享目录**本身及其上级**禁止改名/删除/移动（授权记录按路径前缀存，改名会让权限静默失配）；
  成员在共享目录内也**不能**改名、移动、删除（只上传与下载），需在自己网盘里管理。
- 后端接口：`POST /api/shared/create`、`GET /api/shared/list`、`POST /api/shared/{id}/members`、
  `DELETE /api/shared/{id}`；文件接口带 `?owner=<用户名>` 表示「以共享身份访问他人目录」，
  服务端按 `shared_folders`/`shared_grants` 复核授权（越权 403 并审计）。网页端入口：工具栏下方「共享文件夹」卡片、
  目录行「共享此文件夹 / 管理共享 / 取消共享」、以及浏览他人共享目录顶部的提示条。

### ⚡ 上下行测速

- 登录后可用：`GET /api/speed/download?mb=` 流式生成字节（不落盘）、`POST /api/speed/upload`
  流式接收即丢弃（**不计配额、不存文件**）；上限 50MB（`SPEEDTEST_MAX_BYTES`）、每用户同一时刻只允许一个测速。
- 网页端工具栏「⚡ 测速」面板：10/25/50MB 可选，实时进度，MB/s 与 Mbps 并列；
  stub 模式结果会标注「本地测试链路，不代表真实 Seafile/e2 速度」。

### 👁 文件预览与格式支持

- 网页端直接预览：图片、PDF、视频、音频（带 HTTP Range 分段，可拖动进度条）、
  文本/代码（转义后纯文本渲染，512KB 上限）、Markdown（先转义再渲染，原始 HTML 永不进 DOM，
  链接仅放行 http/https/mailto）；不支持的格式走「下载查看」。
- 下载与预览共用同一条路径安全 + 验权链（`GET /api/files/preview`），支持单段 Range（206/416 语义完整）；
  文件类型图标已扩展（PDF/Office/电子书/压缩包/代码/音视频各自配色）。

### 📱 全平台客户端

- `~/workspace/subdrive-app/`（Flutter，org `cn.ourmetaverse`）：功能与网页端对齐，含加密文件夹的
  SDV1 本地加解密（Dart 与 JS/Python 三方用同一测试向量验证互通）；Material 3、跟随系统深浅色。
  打包在用户 Mac 上进行，见该目录 `BUILD.md`。开发机验证：`flutter analyze` 干净、`flutter test` 5/5。

## 本地运行（stub 模式，不需要真实 Seafile）

```bash
cd ~/workspace/subdrive
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
DATA_DIR=./data SEAFILE_MODE=stub .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8001
# 打开 http://127.0.0.1:8001/
```

- 第一个注册的用户（免邀请码）自动成为管理员（沿用 private-chat 约定），之后注册必须凭邀请码；
  也可用环境变量 `SUBDRIVE_ADMIN_USERNAME` / `SUBDRIVE_ADMIN_PASSWORD` 在首次启动时初始化管理员（部署推荐）。
- 冒烟测试（27 项，全过）：`.venv/bin/python tests/test_smoke.py`
  覆盖邀请码无效/过期/撤销/复用、建夹投影、会话、路径穿越 13 例、跨用户隔离、
  上传下载字节一致、配额拦截与删除释放、校准、禁用即时生效、登录限速、改密码等。
- 功能测试（43 项，全过）：`.venv/bin/python tests/test_features.py`
  覆盖加密文件夹（后端存量无明文文件名/内容、往返字节一致、错密码被拒、密文计配额）、
  测速（需登录、字节数精确、并发 409、不占配额）、预览与 Range（跨用户预览被拦、416、多段回退 200）、管理员提升。
- 共享文件夹测试（54 项，全过）：`.venv/bin/python tests/test_shared.py`
- LiveStorage 协议测试（15 项，全过）：`.venv/bin/python tests/test_storage_live.py`（MockTransport 打桩，不联网）
- JS 密码学测试（10 项，全过）：`node tests/test_crypto.mjs` —— 与 Python/Dart 共验 SDV1 测试向量；
  Flutter 端同向量 5 项见 `~/workspace/subdrive-app/test/crypto_vector_test.dart`。
- 上传计划测试（13 项，全过）：`node tests/test_uploadplan.mjs`

## 环境变量

| 变量 | 默认 | 说明 |
|---|---|---|
| `DATA_DIR` | `./data` | SQLite 与 stub 存储根目录（Docker 里为 `/data`） |
| `SEAFILE_MODE` | `stub` | `stub` / `live` |
| `SEAFILE_BASE_URL` | — | live 必填，如 `https://drive.ourmetaverse.cn` |
| `SEAFILE_API_TOKEN` | — | live 必填。**只经服务器 chmod 600 的 env 文件注入，永不入库/入仓/入聊天** |
| `SEAFILE_REPO_ID` | — | live 必填，专用库的 repo_id |
| `SEAFILE_REPO_NAME` | `subdrive` | 专用库名 |
| `STUB_STORAGE_DIR` | `$DATA_DIR/stub_storage` | stub 模式存储根 |
| `DEFAULT_QUOTA_BYTES` | 20 GiB | 默认个人配额（管理员可按人覆盖） |
| `MAX_FILE_BYTES` | 2 GiB | 单文件上限 |
| `SPEEDTEST_MAX_BYTES` | 50 MiB | 测速单次数据量上限（默认 25MB） |
| `SESSION_TTL_DAYS` | 30 | 会话有效期 |
| `LOGIN_MAX_FAILS` / `LOGIN_LOCK_MINUTES` | 5 / 10 | 登录失败锁定（规格 §7-6） |
| `CALIBRATE_INTERVAL_SECONDS` | 3600 | 用量校准周期，0 = 关闭 |
| `SUBDRIVE_ADMIN_USERNAME/PASSWORD` | — | 首次启动初始化管理员 |

live 模式启动即 `auth/ping` 校验令牌与专用库配置，失败直接停机（fail closed，规格 §7-9）。

## 上线清单（未执行 —— 部署时按此走，助手给命令、用户在 VPS 执行）

- [ ] **硬前置：对象存储套餐升级**（规格 §10；不转，存量满格即全体停摆。供应商与套餐细节内部记录，不公开）
- [ ] 定子域名（规格候选 `files.ourmetaverse.cn` / `pan.ourmetaverse.cn`）并在 Cloudflare 加 A 记录（仅 DNS；服务器 IP 内部记录）
- [ ] 主账号已定为**新建专用服务账号**（拍板记录：爆炸半径只限专用库，占满最后一个免费名额）；
      用它登录后新建**非加密**专用库 `subdrive`，记下 repo_id
- [ ] 为服务账号签发 API Token 并存入密码管理器；**若该账号要开 TOTP，先签发令牌、再开 TOTP**
      （签发 auth-token 时若已开 TOTP 需带 `X-SEAFILE-OTP` 头）
- [ ] 把专用库以「可读写」共享给日常账号（这样日常账号登录即可看见那排投影文件夹，无需换账号）
- [ ] VPS：部署目录 + 数据 volume + `chmod 600` 的 env 文件（令牌只写在这里）；
      `docker compose up -d --build`（compose 默认 stub，上线改 `SEAFILE_MODE=live` 并注入三项 Seafile 变量）
- [ ] 设 `SUBDRIVE_ADMIN_USERNAME/PASSWORD` 初始化本系统管理员（或首注册自动管理员后立即改强密码）
- [ ] Caddy 追加站点块 → `caddy validate` → reload → 外网验证 HTTPS 与登录页
- [ ] 按规格 §8 验收清单 1–10 在真实 Seafile 上自测一轮（stub 已等价覆盖逻辑项；
      第 1/9/10 条须真环境验证：主账号视角建夹、原生使用不受影响、错令牌熔断）
- [ ] 签发第一张正式邀请码

## 与规格的对应 / 歧义消解（实现决定记录）

1. **管理员初始化**：规格 §9-5 说「命令行一次性创建」。实现为环境变量初始化
   （`SUBDRIVE_ADMIN_USERNAME/PASSWORD`，首次启动生效）+ 沿用 private-chat 的
   「首个注册用户免邀请码自动成为管理员」兜底，两者并存；正式部署用前者。
2. **限速落表**：规格 §7-6 要求登录/注册限速但未单列数据表，实现新增 `login_failures` 表
   （scope+ts）承载失败计数，其余五表与规格 §4 字段一致。
3. **邀请码格式**：规格示例 `SD-XXXX-XXXX-XXXX` 且要求 ≥128 bit，实现为 128 bit 随机
   十六进制分 8 组展示（`SD-XXXX-…-XXXX`），熵达标、外观同族。
4. **目录大小**：Seafile 无可靠的单目录大小接口（规格 §3 已注明），故目录 `stat.size=0`，
   递归大小统一走 `path_size`（删除记账与校准共用），不依赖待核实端点。
5. **live 层上传**：按附录 A 走「取 upload-link → POST multipart（parent_dir + file）」；
   下载走「file/?op=download 的 302 → 流式拉取」。live 层未对真实 Seafile 实测
   （本地一律 stub），列入上线清单验收。
6. **路径穿越口径**：含真实 `..` 段/反斜杠/编码变体一律 403 并审计；
   `..;`、`....` 之类只是本人空间内的怪名字（构造上无法逃逸），返回 404 ——
   两类都在冒烟测试的穿越电池里有断言。

## 目录

```
app/main.py      后端全部路由（auth/files/quota/admin）+ 配额/校准/审计/限速
app/paths.py     路径规范化与前缀锁死（全系统唯一实现，规格 §7-1）
app/storage.py   Seafile 适配层（stub / live 双实现）
static/          原生 JS 前端（index.html / style.css / app.js / logo / favicon）
tests/test_smoke.py    冒烟测试 27 项
screenshots/     界面截图（明/暗 × 登录/文件/后台 + 移动端）
Dockerfile / docker-compose.yml / .env.example
```
