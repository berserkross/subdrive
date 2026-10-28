"""
路径安全 —— 全系统唯一实现（规格 §7 第 1 条：路径穿越防线不许有第二实现）。

所有用户传入的路径都先过这里：
  - 反复 URL 解码（防 %252e%252e 这类双重编码绕过），解码后含 NUL/控制字符即拒绝；
  - 拒绝反斜杠、拒绝任何 `..` 段；
  - 折叠重复 `/` 与 `.` 段；
  - 规范化结果再拼上 `/<username>` 前缀，并断言结果仍在该前缀内。

用户视角路径一律是「相对本人根目录」的路径：""、"/" 表示根目录，
"/照片/2026/" 表示根下的子目录。客户端永远接触不到完整 Seafile 路径。
"""
import re
import urllib.parse
from contextvars import ContextVar

# 当前请求的用户名 + 是否管理员。由 main.require_user 写入，存储层用它做归属校验。
# 不在请求上下文里（脚本、直调测试）时保持 None，存储层退回只校验形状。
_current_user: ContextVar[tuple[str, bool] | None] = ContextVar("sd_current_user", default=None)


def set_current_user(username: str | None, is_admin: bool = False) -> None:
    _current_user.set(None if username is None else (username, is_admin))


def current_user() -> str | None:
    ctx = _current_user.get()
    return None if ctx is None else ctx[0]


def current_is_admin() -> bool:
    ctx = _current_user.get()
    return bool(ctx and ctx[1])

# 与规格 §3 一致：用户名即文件夹名
USERNAME_RE = re.compile(r"^[a-z][a-z0-9_-]{2,23}$")
RESERVED_USERNAMES = {
    "admin", "root", "system", "support", "seafile", "api", "www",
    "mail", "ftp", "null", "undefined", "anonymous", "guest", "public",
}

_MAX_SEGMENT_LEN = 255
_MAX_PATH_LEN = 1024


class PathRejected(ValueError):
    """路径非法/越界 —— 调用方应映射为 403 并写审计。"""


def _fully_unquote(s: str) -> str:
    # 最多解 5 层编码；解不开的原样返回后由后续校验拦截
    for _ in range(5):
        t = urllib.parse.unquote(s)
        if t == s:
            break
        s = t
    return s


def _check_chars(s: str, what: str) -> None:
    for ch in s:
        o = ord(ch)
        if o < 0x20 or o == 0x7F:
            raise PathRejected(f"{what} 包含控制字符")


def normalize_rel_path(raw) -> str:
    """
    把用户传入路径规范化为本人空间内的相对路径：
    返回形如 "" （根）或 "a/b/c"（无首尾斜杠）的字符串。
    任何越界/非法输入抛 PathRejected。
    """
    if raw is None:
        return ""
    if not isinstance(raw, str):
        raise PathRejected("路径类型非法")
    s = _fully_unquote(raw)
    _check_chars(s, "路径")
    if "\\" in s:
        raise PathRejected("路径包含反斜杠")
    if len(s) > _MAX_PATH_LEN:
        raise PathRejected("路径过长")
    parts = []
    for seg in s.split("/"):
        if seg == "" or seg == ".":
            continue
        if seg == "..":
            raise PathRejected("路径包含 ..")
        if seg != seg.rstrip(" ."):
            # Windows 会静默裁掉段尾的空格与点：`a ` 与 `a` 落到同一个文件，
            # `.. ` 又能骗过上面那次精确比对。所以尾随空格/点一律拒。
            raise PathRejected("路径段不得以空格或点结尾")
        _check_chars(seg, "路径段")
        if len(seg) > _MAX_SEGMENT_LEN:
            raise PathRejected("路径段过长")
        parts.append(seg)
    return "/".join(parts)


def full_path(username: str, rel: str) -> str:
    """把规范化后的相对路径拼成 Seafile 侧完整路径，并断言前缀不逃逸。"""
    if not USERNAME_RE.match(username or ""):
        raise PathRejected("用户名非法")
    rel = normalize_rel_path(rel)
    full = f"/{username}" + (f"/{rel}" if rel else "")
    if full != f"/{username}" and not full.startswith(f"/{username}/"):
        raise PathRejected("路径逃逸出用户前缀")
    return full


def validate_name(name) -> str:
    """
    校验单个文件/文件夹名（新建/重命名/上传文件名用）。
    返回清洗后的名字；非法抛 PathRejected。
    """
    if name is None or not isinstance(name, str):
        raise PathRejected("名称非法")
    s = _fully_unquote(name).strip()
    _check_chars(s, "名称")
    if not s:
        raise PathRejected("名称为空")
    if s in (".", ".."):
        raise PathRejected("名称非法")
    if "/" in s or "\\" in s:
        raise PathRejected("名称包含路径分隔符")
    if len(s) > _MAX_SEGMENT_LEN:
        raise PathRejected("名称过长")
    if s.endswith(".") or s.endswith(" "):
        raise PathRejected("名称不能以点或空格结尾")
    return s


def validate_username(username) -> str:
    if not isinstance(username, str) or not USERNAME_RE.match(username):
        raise PathRejected("用户名须为 3–24 字符：小写字母开头，仅小写字母/数字/下划线/连字符")
    if username in RESERVED_USERNAMES:
        raise PathRejected("该用户名为保留字")
    return username
