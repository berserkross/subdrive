/* 整文件夹上传 · 目录计划纯逻辑验证（Node ≥19，无外部依赖）。
 * 运行：node test_uploadplan.mjs
 * 覆盖 planFolderUpload：散文件、单层/嵌套目录、跨文件目录去重与父先于子、
 * 空目录（extraDirs）、路径清洗、垃圾输入跳过、ref 透传。 */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
// uploadplan.js 是经典脚本（浏览器以 <script> 加载），读入并在当前全局求值（同 test_crypto.mjs）
eval(readFileSync(join(here, "..", "static", "uploadplan.js"), "utf8"));
const plan = globalThis.SubDriveUpload.planFolderUpload;

let passed = 0;
function check(name, cond, extra = "") {
  if (!cond) throw new Error(`FAIL: ${name} ${extra}`);
  passed++;
  console.log(`${passed}. ${name} OK`);
}
const eq = (a, b) => JSON.stringify(a) === JSON.stringify(b);
const F = (relPath, ref) => ({ relPath, ref });

// 1. 散文件：无目录，dirRel 为 ""
{
  const p = plan([F("a.txt", 1), F("b.jpg", 2)]);
  check("散文件不建目录", eq(p.dirs, []));
  check("散文件 dirRel 为空、name 正确", eq(p.files.map((f) => [f.name, f.dirRel]), [["a.txt", ""], ["b.jpg", ""]]));
  check("ref 原样透传", p.files[0].ref === 1 && p.files[1].ref === 2);
}

// 2. 单层文件夹：目录只建一次，两个文件共用
{
  const p = plan([F("photos/1.jpg"), F("photos/2.jpg")]);
  check("单层目录去重", eq(p.dirs, ["photos"]));
  check("文件 dirRel 指向该目录", p.files.every((f) => f.dirRel === "photos"));
}

// 3. 嵌套：父目录恒在子目录之前
{
  const p = plan([F("a/b/c/f.txt"), F("a/b/g.txt"), F("a/h.txt")]);
  check("嵌套目录父先于子", eq(p.dirs, ["a", "a/b", "a/b/c"]), JSON.stringify(p.dirs));
  check("各文件 dirRel 正确", eq(p.files.map((f) => f.dirRel), ["a/b/c", "a/b", "a"]));
}

// 4. extraDirs：空文件夹也要建出来（含其父链）
{
  const p = plan([F("x/1.txt")], ["empty/sub"]);
  check("空目录进入计划", p.dirs.includes("empty") && p.dirs.includes("empty/sub"), JSON.stringify(p.dirs));
  check("空目录父先于子", p.dirs.indexOf("empty") < p.dirs.indexOf("empty/sub"));
}

// 5. 路径清洗：首尾斜杠、重复斜杠、"." 段被折叠
{
  const p = plan([F("/x//y.txt"), F("./z.txt")]);
  check("清洗后目录与文件名正确", eq(p.dirs, ["x"]) && p.files[0].relPath === "x/y.txt" && p.files[1].relPath === "z.txt",
    JSON.stringify(p));
}

// 6. 垃圾输入跳过而不是崩溃
{
  const p = plan([F(""), F("/"), null, undefined, F("ok.txt")]);
  check("空/非法条目被跳过", p.files.length === 1 && p.files[0].name === "ok.txt");
  check("空计划不抛错", eq(plan([]), { dirs: [], files: [] }) && eq(plan(), { dirs: [], files: [] }));
}

// 7. 后端会拒绝的段名（".."）原样保留在计划里，留给调用方逐文件呈现错误
{
  const p = plan([F("../evil.txt")]);
  check('".." 段不被前端吞掉', p.files.length === 1 && p.files[0].dirRel === "..", JSON.stringify(p.files));
}

console.log(`\n全部 ${passed} 项上传计划测试通过 ✅`);
