"""LiveStorage 线上存储适配 · 请求级回归测试（httpx MockTransport，不接触真实 Seafile）。

覆盖重点：delete() 必须对 file/dir URL 发 HTTP DELETE —— Seafile api2 没有
POST operation=delete 这种形式（POST 只支持 mkdir/rename/move/copy），
误用 POST 时线上删除恒回 "Seafile 返回 400"。本测试抓全部请求断言方法与
p 参数的百分号编码，防该回归复发。

另覆盖 download_iter() 的下载地址解析：Seafile 的 file/?op=download
实测回 HTTP 200 + JSON 字符串正文（非 302），旧代码只认 Location 头，
导致全部下载恒报“Seafile 未返回下载地址”502（2026-10-26 线上事故）。
302 + Location 的旧形式也须继续兼容；Range 分片下载一并覆盖。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import httpx

from app.storage import LiveStorage

PASSED = []


def check(name, cond, extra=""):
    assert cond, f"FAIL: {name} {extra}"
    PASSED.append(name)
    print(f"{len(PASSED):2d}. {name} OK")


REPO = "repo-123"
FILE_FULL = "/alice/照片 1.jpg"  # 含中文与空格，专为验证 p 参数百分号编码
FILE_302 = "/alice/other.bin"  # 下载地址走 302 + Location 的旧形式
DIR_FULL = "/alice/photos"
FILE_BYTES = b"0123456789AB"
FILE_URL = "https://seafile.example.test/seafhttp/files/abc123/file.bin"

seen = []       # 全部请求（httpx.Request）
unmatched = []  # 未命中任何路由的请求


def handler(request: httpx.Request) -> httpx.Response:
    seen.append(request)
    path = request.url.path
    p = request.url.params.get("p")
    if request.method == "GET" and path == f"/api2/repos/{REPO}/file/detail/":
        if p == FILE_FULL:
            return httpx.Response(200, json={"size": 12, "mtime": 1700000000})
        return httpx.Response(404, json={})
    if request.method == "GET" and path == f"/api2/repos/{REPO}/dir/":
        if p == "/alice":
            return httpx.Response(200, json=[
                {"name": "照片 1.jpg", "type": "file", "size": 12, "mtime": 1700000000},
                {"name": "photos", "type": "dir", "size": 0, "mtime": 1700000000},
            ])
        return httpx.Response(404, json={})
    if request.method == "DELETE" and path in (f"/api2/repos/{REPO}/file/", f"/api2/repos/{REPO}/dir/"):
        return httpx.Response(200, text="success")
    if request.method == "GET" and path == f"/api2/repos/{REPO}/file/":
        # 下载地址接口：实测回 200 + JSON 字符串；旧形式是 302 + Location
        if request.url.params.get("op") == "download" and p == FILE_FULL:
            return httpx.Response(200, json=FILE_URL)
        if request.url.params.get("op") == "download" and p == FILE_302:
            return httpx.Response(302, headers={"Location": FILE_URL})
        return httpx.Response(404, json={})
    if request.method == "GET" and path.startswith("/seafhttp/files/"):
        rng = request.headers.get("range", "")
        if rng.startswith("bytes="):
            spec = rng[len("bytes="):]
            start_s, _, end_s = spec.partition("-")
            start = int(start_s) if start_s else 0
            end = int(end_s) if end_s else len(FILE_BYTES) - 1
            chunk = FILE_BYTES[start:end + 1]
            return httpx.Response(206, content=chunk,
                                  headers={"content-length": str(len(chunk)),
                                           "content-range": f"bytes {start}-{end}/{len(FILE_BYTES)}"})
        return httpx.Response(200, content=FILE_BYTES,
                              headers={"content-length": str(len(FILE_BYTES))})
    unmatched.append(request)
    return httpx.Response(404, json={})


class _HttpxShim:
    """让 LiveStorage._req 造出的 Client 全部走同一个 MockTransport。"""

    Timeout = httpx.Timeout

    def __init__(self, transport):
        self._transport = transport

    def Client(self, **kw):
        return httpx.Client(transport=self._transport, timeout=kw.get("timeout"))


def main():
    storage = LiveStorage("https://seafile.example.test", "test-token", REPO)
    storage._httpx = _HttpxShim(httpx.MockTransport(handler))

    # 1. 删文件：恰好一个 DELETE，命中 file 端点，p 为原路径且已百分号编码
    storage.delete(FILE_FULL)
    deletes = [r for r in seen if r.method == "DELETE"]
    check("删文件发出且仅发一个 DELETE", len(deletes) == 1, f"seen={[r.method for r in seen]}")
    d = deletes[0]
    check("DELETE 命中 file 端点", d.url.path == f"/api2/repos/{REPO}/file/", str(d.url))
    check("p 参数解码后等于原路径", d.url.params.get("p") == FILE_FULL, str(d.url))
    raw_q = str(d.url).split("?", 1)[1]
    check("p 参数在原始 URL 中已百分号编码",
          "%E7%85%A7%E7%89%87" in raw_q and "%20" in raw_q, raw_q)
    check("DELETE 带 Token 鉴权头", d.headers.get("Authorization") == "Token test-token")

    # 2. 删目录：DELETE 命中 dir 端点
    seen.clear()
    storage.delete(DIR_FULL)
    deletes = [r for r in seen if r.method == "DELETE"]
    check("删目录发出且仅发一个 DELETE", len(deletes) == 1, f"seen={[r.method for r in seen]}")
    check("DELETE 命中 dir 端点", deletes[0].url.path == f"/api2/repos/{REPO}/dir/", str(deletes[0].url))
    check("目录 p 参数正确", deletes[0].url.params.get("p") == DIR_FULL)

    # 3. 全程没有任何 POST（POST operation=delete 的旧写法不得复发）
    check("全程无 POST 请求", not any(r.method == "POST" for r in seen))
    check("无未命中路由的请求", not unmatched,
          f"{[(r.method, str(r.url)) for r in unmatched]}")

    # 4. 下载：api2 回 200 + JSON 字符串（实测行为），应正常拉流
    seen.clear()
    gen, size = storage.download_iter(FILE_FULL)
    body = b"".join(gen)
    check("下载 200+JSON 取到下载地址并拉流", body == FILE_BYTES and size == len(FILE_BYTES),
          f"body={body!r} size={size}")
    check("下载请求了 download-link 端点",
          any(r.method == "GET" and r.url.path == f"/api2/repos/{REPO}/file/"
              and r.url.params.get("op") == "download" for r in seen))

    # 5. 下载：302 + Location（旧行为）仍兼容
    seen.clear()
    gen, size = storage.download_iter(FILE_302)
    body = b"".join(gen)
    check("下载 302+Location 仍兼容", body == FILE_BYTES and size == len(FILE_BYTES),
          f"body={body!r} size={size}")

    # 6. 下载 Range：只要 [4, 8) 区间
    seen.clear()
    gen, size = storage.download_iter(FILE_FULL, start=4, length=4)
    body = b"".join(gen)
    check("下载 Range 只取目标区间", body == b"4567" and size == 4,
          f"body={body!r} size={size}")
    check("下载全程无未命中路由", not unmatched,
          f"{[(r.method, str(r.url)) for r in unmatched]}")

    print(f"\n全部 {len(PASSED)} 项 LiveStorage 测试通过 ✅")


if __name__ == "__main__":
    main()
