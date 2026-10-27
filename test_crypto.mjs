/* SDV1 加密格式 · JS 端向量验证（Node ≥19，自带 Web Crypto）。
 * 运行：node test_crypto.mjs
 * 断言 CRYPTO.md §7 的五条：派生密钥一致、文件/清单/校验块可解、错误密码必失败，
 * 外加一轮随机 IV 的加解密 roundtrip。 */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
// vault.js 是经典脚本（浏览器以 <script> 加载），这里读入并在当前全局求值
eval(readFileSync(join(here, "static", "vault.js"), "utf8"));
const V = globalThis.SDVault;
const vector = JSON.parse(readFileSync(join(here, "testdata", "crypto_vector.json"), "utf8"));

let passed = 0;
function check(name, cond, extra = "") {
  if (!cond) throw new Error(`FAIL: ${name} ${extra}`);
  passed++;
  console.log(`${passed}. ${name} OK`);
}
const eqBytes = (a, b) => a.length === b.length && a.every((x, i) => x === b[i]);

const salt = V.b64decode(vector.kdf.salt_b64);
const iterations = vector.kdf.iterations;

// 1. 派生密钥 hex 与向量一致
const hex = await V.deriveKeyHex(vector.password, salt, iterations);
check("派生密钥与向量一致", hex === vector.derived_key_hex, hex);

const key = await V.deriveKey(vector.password, salt, iterations);

// 2. 文件 blob 解密 == 明文
const filePt = await V.decryptBlob(key, V.b64decode(vector.file.blob_b64));
check("文件 blob 解密与向量一致", eqBytes(filePt, V.b64decode(vector.file.plaintext_b64)));

// 3. 清单 blob 解密并解析 == 向量清单
const manPt = await V.decryptBlob(key, V.b64decode(vector.manifest.blob_b64));
const man = V.parseManifest(manPt);
const expectMan = JSON.parse(vector.manifest.plaintext_utf8);
check("清单 blob 解密与向量一致", JSON.stringify(man) === JSON.stringify(expectMan));

// 4. check 块解开 == 常量
const checkKey = await V.unlockWithPassword(
  { format: "subdrive-vault", version: 1, kdf: { algo: "PBKDF2-SHA256", iterations, salt: vector.kdf.salt_b64 }, check: vector.check.blob_b64 },
  vector.password);
check("描述文件 check 校验通过", !!checkKey);

// 5. 错误密码必失败
let wrongFailed = false;
try {
  const badKey = await V.deriveKey("wrong password", salt, iterations);
  await V.decryptBlob(badKey, V.b64decode(vector.file.blob_b64));
} catch { wrongFailed = true; }
check("错误密码解密失败", wrongFailed);

let wrongUnlock = false;
try {
  await V.unlockWithPassword(
    { format: "subdrive-vault", version: 1, kdf: { algo: "PBKDF2-SHA256", iterations, salt: vector.kdf.salt_b64 }, check: vector.check.blob_b64 },
    "wrong password");
} catch { wrongUnlock = true; }
check("错误密码打不开描述文件", wrongUnlock);

// 6. 随机 IV roundtrip + 信封结构（魔数/版本/开销 33 字节）
const data = new TextEncoder().encode("roundtrip 往返测试 · 12345");
const blob = await V.encryptBlob(key, data);
check("信封开销为 33 字节", blob.length === data.length + 33);
check("信封魔数与版本", blob[0] === 0x53 && blob[1] === 0x44 && blob[2] === 0x56 && blob[3] === 0x31 && blob[4] === 1);
const back = await V.decryptBlob(key, blob);
check("加解密 roundtrip 字节一致", eqBytes(back, data));

// 7. 篡改密文必失败（GCM tag）
const tampered = blob.slice();
tampered[tampered.length - 1] ^= 0xff;
let tamperFailed = false;
try { await V.decryptBlob(key, tampered); } catch { tamperFailed = true; }
check("篡改密文被 GCM 拒绝", tamperFailed);

console.log(`\n全部 ${passed} 项 JS 密码学测试通过 ✅`);
