#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""文档事实检查：README / AGENTS 里写下的事实必须能从仓库现状验证。

检查项：
  1. 「测试脚本 + N 项」的声明等于该脚本里 check(...) 调用的实际条数
     （e2e 的项数受浏览器分支影响，运行输出为准，不静态断言）。
  2. 「文件 + N 行」的声明等于文件实际行数。
  3. 反引号引用以及命令里出现的仓库内路径真实存在。
  4. 仓库已有 CI 时，文档里不得再写「没有 CI」。

只检查静态可判定的事实；运行时输出、真实 Seafile 环境不在此脚本范围内。

用法：python scripts/check_docs.py
失败返回 1，并把每条不一致打印到 stderr；CI 在测试之前执行。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

# Windows 控制台默认 GBK，中文输出会乱码；统一走 UTF-8（Linux 下是无操作）。
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
DOCS = ("README.md", "AGENTS.md")
PATH_PREFIXES = (
    "app/",
    "static/",
    "tests/",
    "docs/",
    "tools/",
    "testdata/",
    "screenshots/",
    "scripts/",
)
TOP_FILES = {
    "README.md",
    "AGENTS.md",
    "CRYPTO.md",
    "LICENSE",
    "Dockerfile",
    "docker-compose.yml",
    ".env.example",
    "requirements.txt",
}
SKIP_PREFIXES = ("data/", "dist/", "build/", ".venv/", "~", "%")

problems: list[str] = []


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def fail(msg: str) -> None:
    problems.append(msg)


def count_checks(rel: str) -> int:
    text = (ROOT / rel).read_text(encoding="utf-8")
    return len(re.findall(r"^\s*check\(", text, re.M))


def check_counts() -> None:
    for doc in DOCS:
        for line in read(doc).splitlines():
            numbers = re.findall(r"(\d+)\s*项", line)
            scripts = re.findall(r"(tests/[\w/.-]+\.(?:py|mjs))", line)
            if len(numbers) != 1 or len(scripts) != 1:
                continue
            rel = scripts[0]
            if rel.startswith("tests/e2e/"):
                continue  # 浏览器分支会增减项数，以脚本运行输出为准
            actual = count_checks(rel)
            if int(numbers[0]) != actual:
                fail(f"{doc} 声明 {rel} 有 {numbers[0]} 项，实际 {actual} 条 check(...)")


def check_line_counts() -> None:
    for doc in DOCS:
        for line in read(doc).splitlines():
            if "上限" in line:
                continue
            numbers = re.findall(r"(\d+)\s*行", line)
            paths = re.findall(r"`([\w./\\-]+\.(?:py|js|mjs|md|html))`", line)
            if len(numbers) != 1 or len(paths) != 1:
                continue
            path = paths[0].replace("\\", "/")
            target = ROOT / path
            if path.startswith(SKIP_PREFIXES) or not target.is_file():
                continue
            actual = sum(1 for _ in target.open(encoding="utf-8", errors="replace"))
            if actual != int(numbers[0]):
                fail(f"{doc} 声明 {path} 有 {numbers[0]} 行，实际 {actual} 行")


def check_paths() -> None:
    for doc in DOCS:
        for token in re.findall(r"`([^`\n]+)`", read(doc)):
            path = token.replace("\\", "/").strip()
            path = re.sub(r":\d+$", "", path)  # 允许 `app/main.py:616` 这种带行号的引用
            if path.startswith(SKIP_PREFIXES) or any(c in path for c in "*<>{}|"):
                continue
            if not (path.startswith(PATH_PREFIXES) or path in TOP_FILES):
                continue
            if not (ROOT / path).exists():
                fail(f"{doc} 引用了不存在的路径：{token}")


def check_commands() -> None:
    for doc in DOCS:
        for block in re.findall(r"```[a-zA-Z0-9]*\n(.*?)```", read(doc), re.S):
            for token in re.findall(r"[\w./\\-]+\.(?:py|mjs|js|sh|md|json)", block):
                path = token.replace("\\", "/")
                if path.startswith(SKIP_PREFIXES) or any(c in path for c in "*<>$%{}"):
                    continue
                if "/" in path:
                    if not path.startswith(PATH_PREFIXES):
                        continue
                elif path not in {
                    "requirements.txt",
                    "docker-compose.yml",
                    "Dockerfile",
                }:
                    continue
                if not (ROOT / path).exists():
                    fail(f"{doc} 命令里引用了不存在的文件：{token}")


def check_ci_claims() -> None:
    has_ci = (ROOT / ".github/workflows").is_dir() and any(
        (ROOT / ".github/workflows").glob("*.yml")
    )
    if not has_ci:
        return
    for doc in DOCS:
        for phrase in ("没有 CI", "无 CI"):
            if phrase in read(doc):
                fail(f"{doc} 仍写着「{phrase}」，但仓库已有 .github/workflows/")


def main() -> int:
    check_counts()
    check_line_counts()
    check_paths()
    check_commands()
    check_ci_claims()

    if problems:
        print(f"文档一致性检查失败（{len(problems)} 项）：", file=sys.stderr)
        for item in problems:
            print(f"  - {item}", file=sys.stderr)
        return 1

    print("文档一致性检查通过。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
