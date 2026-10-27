#!/usr/bin/env bash
# Codex 云端环境的 setup 脚本：agent 开始工作前预装依赖。
#
# 云端沙箱是一次性容器、agent 阶段默认断网，所以依赖必须装好在这里。
# 直接装进系统 python（不建 venv），避免 agent 阶段 PATH 里找不到 .venv/bin。
#
# 用法：Codex 环境配置里把 setup 脚本填成 `bash scripts/codex-setup.sh`
set -euo pipefail

python3 -m pip install --quiet -r requirements.txt
python3 -m pip install --quiet pytest cryptography

# 自检：装了但导不进来等于没装，早失败早发现
python3 - <<'PY'
import fastapi, uvicorn, httpx, multipart, cryptography
print("deps ok:", fastapi.__version__, uvicorn.__version__, httpx.__version__)
PY

node --version
