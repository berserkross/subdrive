"use strict";
/* 整文件夹上传的「相对路径 → 目录计划」纯逻辑（无 DOM 依赖，浏览器与 Node 测试共用）。
 *
 * 输入：
 *   items     [{ relPath, ref }] —— relPath 形如 "照片/2026/a.jpg"（正斜杠分隔，
 *             首段即被选/被拖入的文件夹名）；ref 为调用方不透明引用（浏览器端放 File 对象）。
 *   extraDirs [ "空文件夹/子目录" ] —— 只有目录、没有文件的相对路径（拖放空文件夹时才有；
 *             文件选择器的 webkitdirectory 给不出空目录，故选择器路径恒为空数组）。
 * 输出 { dirs, files }：
 *   dirs  —— 需要确保存在的目录（相对基准目录），去重且父目录恒排在子目录之前；
 *   files —— [{ relPath, name, dirRel, ref }]，dirRel 为该文件的目标目录
 *            （相对基准目录，"" 表示基准目录本身），name 为末段文件名。
 * 本函数只做结构拆分，不做合法性判断：后端会拒绝的段名（如 ".."）原样保留在计划里，
 * 由调用方在建目录/上传时按文件逐个呈现后端错误，绝不在此崩溃。 */
function planFolderUpload(items, extraDirs = []) {
  const cleanSegs = (relPath) => String(relPath || "")
    .replace(/\\/g, "/")
    .split("/")
    .filter((s) => s !== "" && s !== ".");
  const dirs = [];
  const seen = new Set();
  const addDirChain = (dirSegs) => {
    for (let i = 1; i <= dirSegs.length; i++) {
      const d = dirSegs.slice(0, i).join("/");
      if (!seen.has(d)) { seen.add(d); dirs.push(d); }
    }
  };
  for (const d of extraDirs || []) addDirChain(cleanSegs(d));
  const files = [];
  for (const it of items || []) {
    if (!it) continue;
    const segs = cleanSegs(it.relPath);
    if (!segs.length) continue;
    const dirSegs = segs.slice(0, -1);
    addDirChain(dirSegs);
    files.push({
      relPath: segs.join("/"),
      name: segs[segs.length - 1],
      dirRel: dirSegs.join("/"),
      ref: it.ref,
    });
  }
  return { dirs, files };
}

globalThis.SubDriveUpload = { planFolderUpload };
