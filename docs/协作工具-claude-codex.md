# 协作工具：Codex 与 Claude Code（2026-11-12 实测）

两个 CLI 都装在这台机器上，定位不同：**看图找 Codex（支持图片），读代码/审文本找 Claude Code（本网关不支持图片）**。

## 一、Codex（视觉评审、代码审阅）

- 安装：`npm i -g @openai/codex` → `codex-cli 0.167.1`
- 认证：已配好，默认 `model: gpt-6-astra`、`sandbox: read-only`、`approval: never`
- 图片：支持（已用它评审界面截图，能正确识别控件与配色）

调用模板（prompt 必须走 stdin）：

```bash
printf '%s' "你是视觉设计评审……只输出 5 条问题，每条给一行可落地的 CSS" \
  | codex exec --skip-git-repo-check \
      -i "E:\\path\\shot-1.png" -i "E:\\path\\shot-2.png"
```

**坑**：`-i/--image <FILE>...` 是可变参数，把 prompt 写在它后面会被当成又一个图片路径，codex 会回
`Reading prompt from stdin / No prompt provided` 并空跑。所以 prompt 一定走管道。

**已用它做过**：评审顶栏 / 主题面板 / 深色整页，5 条意见采纳 3 条（深色辅助文字提亮、用户胶囊过宽、
色板选中环过重），未采纳 2 条（表格行高属整体密度取舍；语言入口那条引用了不存在的类名，属看图臆测）。

## 二、Claude Code（读代码、改代码、文字审）

- 路径：`/c/Users/Ibash/AppData/Roaming/npm/claude`（v2.1.299）
- **必须先把 Git 的 bin 目录放进 PATH**，否则全局 PreToolUse 钩子会因为「找不到 Git Bash」把**所有**工具调用判成 blocking：

```bash
PATH="/d/Program Files/Git/bin:$PATH" claude -p "..." --allowedTools "Read" --max-turns 5
```

报错原文（不给 PATH 时）：

```
PreToolUse hook error: [python3 "<插件目录>/hooks/pretooluse.py"]: failed;
blocking because Git Bash wasn't found and this hook doesn't set "shell" to "powershell",
so only exit code 0 or 2 counts as its verdict.
```

- **不支持图片**：让它 Read PNG 会返回「Unsupported Image」（本网关走 api.deepseek.com，图片块不被接受）。纯文本提示正常。
- 输出里混有网关提示（`[claude-code:unrecognized_model]` 与 auto mode 计费说明），脚本里用 `tail` 截正文。

## 三、怎么分工

| 任务 | 用谁 |
|---|---|
| 看截图找视觉问题 | Codex（`-i` 附图） |
| 审一段代码 / 写重构建议 | Claude Code（`--allowedTools Read`） |
| 让它真的改文件 | 两个都不给写权限，改由主代理落地——避免绕过评审直接改仓库 |

一个实测数据点：同一份「深色模式下辅助文字太暗」的判断，Codex 看完图能直接给到 `--text-2` 这一层；
Claude Code 只能靠人把现象描述成文字再让它推理。所以视觉相关的活优先 Codex。