"""
Seafile 适配层（规格 §2/§5）：全系统唯一允许与 Seafile 打交道的模块。

两种实现，由 SEAFILE_MODE 环境变量切换：
  - stub（默认）：本地文件系统假实现，布局 <STUB_ROOT>/<repo_name>/<username>/…，
    供本地开发与全部自动化测试使用，绝不接触真实 Seafile。
  - live：按规格附录 A 调用 Seafile Web API v2；base url 与 API Token
    只从环境变量读（SEAFILE_BASE_URL / SEAFILE_API_TOKEN），代码与仓库内无任何凭证。

路径参数约定：本层只接受「完整 Seafile 路径」（如 /alice/照片/a.jpg），
由调用方经 app.paths.full_path() 拼出；本层再做最后一道前缀断言。
"""
import os
import shutil
import time
from pathlib import Path, PurePosixPath

from .paths import USERNAME_RE

CHUNK = 1024 * 1024


class StorageError(Exception):
    def __init__(self, message="存储层错误", code="storage_error", status=502):
        super().__init__(message)
        self.code = code
        self.status = status


class StorageNotFound(StorageError):
    def __init__(self, message="文件或文件夹不存在"):
        super().__init__(message, code="not_found", status=404)


class StorageAuthError(StorageError):
    """Seafile 401：令牌失效 —— 规格 §7 第 9 条，全局熔断、fail closed。"""

    def __init__(self, message="Seafile 令牌失效，后端已熔断"):
        super().__init__(message, code="seafile_auth_failed", status=503)


class StorageConflict(StorageError):
    def __init__(self, message="同名文件或文件夹已存在"):
        super().__init__(message, code="conflict", status=409)


def _mtime_iso(ts: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime(ts))


def _assert_full_path(full: str) -> None:
    """完整 Seafile 路径的形状体检，stub 与 live 共用。

    存储层不知道「当前用户是谁」，所以这里只挡「形状非法」与「首段不是合法用户名
    形态」；真正的用户隔离仍由 `app.paths.full_path()` 负责。但这层必须存在：live
    侧原来零校验，`../bob/a.jpg` 会被原样拼进请求 URL 发给真实 Seafile。
    """
    if not isinstance(full, str) or not full.startswith("/"):
        raise StorageError("路径必须以 / 开头", code="path_rejected", status=403)
    segs = full.split("/")[1:]
    if not segs or not segs[0]:
        raise StorageError("路径缺少用户前缀", code="path_rejected", status=403)
    if not USERNAME_RE.match(segs[0]):
        raise StorageError("首段不是合法用户名", code="path_rejected", status=403)
    for seg in segs:
        if seg in ("", ".", "..") or seg != seg.rstrip(" ."):
            raise StorageError("非法路径", code="path_rejected", status=403)
        if "\\" in seg or any(ord(c) < 0x20 or ord(c) == 0x7F for c in seg):
            raise StorageError("路径包含非法字符", code="path_rejected", status=403)


# ------------------------------------------------------------------ 基类

class BaseStorage:
    repo_name = "subdrive"

    def ensure_user_folder(self, username: str) -> None:
        raise NotImplementedError

    def user_folder_exists(self, username: str) -> bool:
        raise NotImplementedError

    def list_dir(self, full: str) -> list:
        """返回 [{name, type: 'dir'|'file', size, mtime}]，按 目录在前+名称 排序。"""
        raise NotImplementedError

    def mkdir(self, full: str) -> None:
        raise NotImplementedError

    def upload(self, dir_full: str, filename: str, src_path: Path) -> int:
        """把本地临时文件 src_path 以 filename 存入 dir_full，返回字节数。"""
        raise NotImplementedError

    def download_iter(self, full: str, start: int = 0, length: int | None = None):
        """返回 (chunk_iterator, size_bytes)；start/length 给定时只读该字节区间（Range）。"""
        raise NotImplementedError

    def stat(self, full: str) -> dict:
        """{type, size, mtime}；目录 size 为 0（递归大小走 path_size）。"""
        raise NotImplementedError

    def rename(self, full: str, new_name: str) -> None:
        raise NotImplementedError

    def move(self, src_full: str, dst_dir_full: str) -> None:
        raise NotImplementedError

    def delete(self, full: str) -> None:
        raise NotImplementedError

    def path_size(self, full: str):
        """递归统计：(total_bytes, file_count)。校准与删除记账共用。"""
        total = 0
        count = 0
        st = self.stat(full)
        if st["type"] == "file":
            return st["size"], 1
        for entry in self.list_dir(full):
            child = full.rstrip("/") + "/" + entry["name"]
            if entry["type"] == "file":
                total += entry["size"]
                count += 1
            else:
                b, c = self.path_size(child)
                total += b
                count += c
        return total, count


# ------------------------------------------------------------------ stub

class StubStorage(BaseStorage):
    """本地文件系统假 Seafile：<root>/<repo>/<username>/…"""

    def __init__(self, root: Path, repo_name: str = "subdrive"):
        self.root = Path(root)
        self.repo_name = repo_name
        self.repo_dir = self.root / repo_name
        self.repo_dir.mkdir(parents=True, exist_ok=True)

    def _resolve(self, full: str) -> Path:
        # full 形如 /alice/a/b —— 逐段拼接并断言不逃出 repo 目录
        _assert_full_path(full)
        parts = [p for p in PurePosixPath(full).parts if p not in ("/",)]
        p = self.repo_dir
        for part in parts:
            if part in ("", ".", ".."):
                raise StorageError("非法路径", code="path_rejected", status=403)
            p = p / part
        rp = p.resolve()
        if rp != self.repo_dir.resolve() and self.repo_dir.resolve() not in rp.parents:
            raise StorageError("路径越界", code="path_rejected", status=403)
        return p

    def ensure_user_folder(self, username: str) -> None:
        (self.repo_dir / username).mkdir(parents=True, exist_ok=True)

    def user_folder_exists(self, username: str) -> bool:
        return (self.repo_dir / username).is_dir()

    def list_dir(self, full: str) -> list:
        p = self._resolve(full)
        if not p.exists():
            raise StorageNotFound()
        if not p.is_dir():
            raise StorageError("不是文件夹", code="not_a_dir", status=400)
        out = []
        for child in p.iterdir():
            st = child.stat()
            out.append({
                "name": child.name,
                "type": "dir" if child.is_dir() else "file",
                "size": 0 if child.is_dir() else st.st_size,
                "mtime": _mtime_iso(st.st_mtime),
            })
        out.sort(key=lambda e: (0 if e["type"] == "dir" else 1, e["name"].lower()))
        return out

    def mkdir(self, full: str) -> None:
        p = self._resolve(full)
        if p.exists():
            raise StorageConflict()
        if not p.parent.is_dir():
            raise StorageNotFound("父目录不存在")
        p.mkdir()

    def upload(self, dir_full: str, filename: str, src_path: Path) -> int:
        d = self._resolve(dir_full)
        if not d.is_dir():
            raise StorageNotFound("目标目录不存在")
        dst = d / filename
        if dst.is_dir():
            raise StorageConflict("同名文件夹已存在")
        size = 0
        with open(src_path, "rb") as fin, open(dst, "wb") as fout:
            while True:
                chunk = fin.read(CHUNK)
                if not chunk:
                    break
                fout.write(chunk)
                size += len(chunk)
        return size

    def download_iter(self, full: str, start: int = 0, length: int | None = None):
        p = self._resolve(full)
        if not p.exists() or p.is_dir():
            raise StorageNotFound()
        total = p.stat().st_size
        if start < 0 or start > total:
            raise StorageError("Range 起点越界", code="range_error", status=416)
        size = total - start if length is None else min(length, total - start)

        def gen():
            with open(p, "rb") as f:
                f.seek(start)
                remaining = size
                while remaining > 0:
                    chunk = f.read(min(CHUNK, remaining))
                    if not chunk:
                        break
                    remaining -= len(chunk)
                    yield chunk

        return gen(), size

    def stat(self, full: str) -> dict:
        p = self._resolve(full)
        if not p.exists():
            raise StorageNotFound()
        st = p.stat()
        return {
            "type": "dir" if p.is_dir() else "file",
            "size": 0 if p.is_dir() else st.st_size,
            "mtime": _mtime_iso(st.st_mtime),
        }

    def rename(self, full: str, new_name: str) -> None:
        p = self._resolve(full)
        if not p.exists():
            raise StorageNotFound()
        dst = p.parent / new_name
        if dst.exists():
            raise StorageConflict()
        p.rename(dst)

    def move(self, src_full: str, dst_dir_full: str) -> None:
        src = self._resolve(src_full)
        dst_dir = self._resolve(dst_dir_full)
        if not src.exists():
            raise StorageNotFound()
        if not dst_dir.is_dir():
            raise StorageNotFound("目标目录不存在")
        dst = dst_dir / src.name
        if dst.exists():
            raise StorageConflict()
        if src.is_dir() and (dst == src or src in dst.parents):
            raise StorageError("不能把文件夹移动到它自己里面", code="invalid_move", status=400)
        shutil.move(str(src), str(dst))

    def delete(self, full: str) -> None:
        p = self._resolve(full)
        if not p.exists():
            raise StorageNotFound()
        if p.is_dir():
            shutil.rmtree(p)
        else:
            p.unlink()


# ------------------------------------------------------------------ live

class LiveStorage(BaseStorage):
    """真实 Seafile Web API v2 适配（规格附录 A）。本地测试不启用。"""

    def __init__(self, base_url: str, token: str, repo_id: str, repo_name: str = "subdrive"):
        import httpx  # 延迟导入：stub 模式不需要

        self._httpx = httpx
        self.base = base_url.rstrip("/")
        self.token = token
        self.repo_id = repo_id
        self.repo_name = repo_name

    # -- 基础请求 --
    def _req(self, method: str, path: str, **kw):
        headers = kw.pop("headers", {})
        headers["Authorization"] = f"Token {self.token}"
        try:
            with self._httpx.Client(timeout=self._httpx.Timeout(60.0, read=None)) as client:
                resp = client.request(method, self.base + path, headers=headers, **kw)
        except Exception as exc:  # 网络层失败
            raise StorageError(f"Seafile 不可达：{exc}", code="seafile_unreachable", status=503)
        if resp.status_code == 401:
            raise StorageAuthError()
        if resp.status_code == 404:
            raise StorageNotFound()
        if resp.status_code >= 400:
            raise StorageError(f"Seafile 返回 {resp.status_code}", status=502)
        return resp

    def ping(self) -> bool:
        resp = self._req("GET", "/api2/auth/ping/")
        _d = resp.json()
        return _d == "Authorized" or (isinstance(_d, dict) and _d.get("detail") == "Authorized")

    # -- 目录/文件 --
    def _dir_url(self, full: str) -> str:
        from urllib.parse import quote

        _assert_full_path(full)
        return f"/api2/repos/{self.repo_id}/dir/?p={quote(full)}"

    def _file_url(self, full: str) -> str:
        from urllib.parse import quote

        _assert_full_path(full)
        return f"/api2/repos/{self.repo_id}/file/?p={quote(full)}"

    def list_dir(self, full: str) -> list:
        resp = self._req("GET", self._dir_url(full))
        out = []
        for e in resp.json():
            out.append({
                "name": e["name"],
                "type": "dir" if e["type"] == "dir" else "file",
                "size": 0 if e["type"] == "dir" else int(e.get("size", 0)),
                "mtime": _mtime_iso(e.get("mtime", 0)) if isinstance(e.get("mtime"), (int, float)) else str(e.get("mtime", "")),
            })
        out.sort(key=lambda x: (0 if x["type"] == "dir" else 1, x["name"].lower()))
        return out

    def ensure_user_folder(self, username: str) -> None:
        try:
            self.stat(f"/{username}")
            return
        except StorageNotFound:
            pass
        self._req("POST", self._dir_url(f"/{username}"), data={"operation": "mkdir"})

    def user_folder_exists(self, username: str) -> bool:
        try:
            return self.stat(f"/{username}")["type"] == "dir"
        except StorageNotFound:
            return False

    def mkdir(self, full: str) -> None:
        self._req("POST", self._dir_url(full), data={"operation": "mkdir"})

    def upload(self, dir_full: str, filename: str, src_path: Path) -> int:
        from urllib.parse import quote

        resp = self._req("GET", f"/api2/repos/{self.repo_id}/upload-link/?p={quote(dir_full)}")
        upload_url = resp.json()  # 返回 URL 字符串（可能是相对路径）
        if isinstance(upload_url, str) and upload_url.startswith("/"):
            upload_url = self.base + upload_url
        size = Path(src_path).stat().st_size
        headers = {"Authorization": f"Token {self.token}"}
        try:
            with open(src_path, "rb") as f, self._httpx.Client(timeout=self._httpx.Timeout(60.0, read=None)) as client:
                r = client.post(upload_url, headers=headers,
                                data={"parent_dir": dir_full},
                                files={"file": (filename, f)})
        except Exception as exc:
            raise StorageError(f"上传转发失败：{exc}", code="seafile_unreachable", status=503)
        if r.status_code == 401:
            raise StorageAuthError()
        if r.status_code >= 400:
            raise StorageError(f"Seafile 上传返回 {r.status_code}", status=502)
        return size

    def download_iter(self, full: str, start: int = 0, length: int | None = None):
        from urllib.parse import quote

        resp = self._req("GET", f"/api2/repos/{self.repo_id}/file/?p={quote(full)}&op=download",
                         follow_redirects=False)
        # Seafile 的下载地址有两种返回形式（2026-10-26 实测本服是第一种）：
        # ① HTTP 200 + JSON 字符串正文（与 upload-link 一致）；
        # ② 302 + Location 头。两种都接受；都没有才报 502。
        # 教训：旧代码只认 302，导致全部下载恒报“Seafile 未返回下载地址”502。
        location = resp.headers.get("location") or resp.headers.get("Location")
        if not location and resp.status_code == 200:
            try:
                body = resp.json()
            except Exception:
                body = None
            if isinstance(body, str) and body.strip():
                location = body.strip()
        if not location:
            raise StorageError("Seafile 未返回下载地址", status=502)
        if location.startswith("/"):
            location = self.base + location
        client = self._httpx.Client(timeout=self._httpx.Timeout(60.0, read=None))
        headers = {}
        if start or length is not None:
            end = "" if length is None else str(start + length - 1)
            headers["Range"] = f"bytes={start}-{end}"
        req = client.build_request("GET", location, headers=headers)
        r = client.send(req, stream=True, follow_redirects=True)
        if r.status_code == 401:
            client.close()
            raise StorageAuthError()
        if r.status_code >= 400:
            client.close()
            raise StorageError(f"下载返回 {r.status_code}", status=502)
        # 若文件服务器忽略 Range 回了 200 全量，则在转发流里手动跳过/截断到目标区间
        skip = start if (start and r.status_code == 200) else 0
        cap = length if (r.status_code == 200) else None
        size = int(r.headers.get("content-length", 0))
        if r.status_code == 200 and (skip or cap is not None):
            total = size
            size = total - skip if cap is None else min(cap, total - skip)

        def gen():
            try:
                skipped = 0
                emitted = 0
                for chunk in r.iter_bytes(CHUNK):
                    if skip and skipped < skip:
                        take = skip - skipped
                        if len(chunk) <= take:
                            skipped += len(chunk)
                            continue
                        chunk = chunk[take:]
                        skipped = skip
                    if cap is not None:
                        if emitted >= cap:
                            break
                        chunk = chunk[: cap - emitted]
                    emitted += len(chunk)
                    yield chunk
            finally:
                r.close()
                client.close()

        return gen(), size

    def stat(self, full: str) -> dict:
        from urllib.parse import quote

        # 先按文件查，再按目录查
        try:
            resp = self._req("GET", f"/api2/repos/{self.repo_id}/file/detail/?p={quote(full)}")
            d = resp.json()
            return {"type": "file", "size": int(d.get("size", 0)), "mtime": str(d.get("mtime", ""))}
        except StorageNotFound:
            pass
        parent, _, name = full.rstrip("/").rpartition("/")
        parent = parent or "/"
        for e in self.list_dir(parent):
            if e["name"] == name:
                return {"type": e["type"], "size": e["size"], "mtime": e["mtime"]}
        raise StorageNotFound()

    def rename(self, full: str, new_name: str) -> None:
        st = self.stat(full)
        url = self._file_url(full) if st["type"] == "file" else self._dir_url(full)
        self._req("POST", url, data={"operation": "rename", "newname": new_name})

    def move(self, src_full: str, dst_dir_full: str) -> None:
        st = self.stat(src_full)
        url = self._file_url(src_full) if st["type"] == "file" else self._dir_url(src_full)
        self._req("POST", url, data={"operation": "move", "dst_repo": self.repo_id, "dst_dir": dst_dir_full})

    def delete(self, full: str) -> None:
        st = self.stat(full)
        url = self._file_url(full) if st["type"] == "file" else self._dir_url(full)
        # Seafile api2 的删除没有 POST operation 形式（POST 只支持 mkdir/rename/
        # move/copy），文档化的删法就是对同一 file/dir URL 发 HTTP DELETE；
        # 曾误用 POST operation=delete，线上删除恒回 400。
        self._req("DELETE", url)


# ------------------------------------------------------------------ 工厂

def make_storage(data_dir: Path) -> BaseStorage:
    mode = os.environ.get("SEAFILE_MODE", "stub").lower()
    repo_name = os.environ.get("SEAFILE_REPO_NAME", "subdrive")
    if mode == "live":
        base = os.environ.get("SEAFILE_BASE_URL", "")
        token = os.environ.get("SEAFILE_API_TOKEN", "")
        repo_id = os.environ.get("SEAFILE_REPO_ID", "")
        if not base or not token or not repo_id:
            raise RuntimeError("live 模式必须设置 SEAFILE_BASE_URL / SEAFILE_API_TOKEN / SEAFILE_REPO_ID")
        storage = LiveStorage(base, token, repo_id, repo_name)
        storage.ping()  # 启动即验令牌，失败停机（fail closed）
        return storage
    stub_root = Path(os.environ.get("STUB_STORAGE_DIR", data_dir / "stub_storage"))
    return StubStorage(stub_root, repo_name)
