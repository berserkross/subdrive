/* File response handling shared by the UI and independent stream tests. */
(function (root) {
  "use strict";
  async function readResponse(response, onProgress = () => {}) {
    if (!response.ok) {
      const data = await response.json().catch(() => null);
      const error = new Error(data?.detail?.message || data?.message || `下载失败（HTTP ${response.status}）`);
      error.status = response.status;
      throw error;
    }
    const length = Number(response.headers.get("content-length"));
    const encoding = response.headers.get("content-encoding");
    const total = Number.isFinite(length) && length > 0 && (!encoding || encoding === "identity") ? length : null;
    let loaded = 0;
    onProgress({ loaded, total });
    if (!response.body) throw new Error("浏览器未收到文件内容，请重试");
    const reader = response.body.getReader();
    const chunks = [];
    try {
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        chunks.push(value);
        loaded += value.byteLength;
        onProgress({ loaded, total });
      }
    } catch (error) {
      await reader.cancel().catch(() => {});
      throw error;
    } finally {
      reader.releaseLock();
    }
    if (total !== null && loaded !== total) throw new Error("文件传输不完整，请重新下载");
    return new Blob(chunks, { type: response.headers.get("content-type") || "application/octet-stream" });
  }
  root.SDDownload = { readResponse };
})(globalThis);
