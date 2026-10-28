"use strict";
/* ================= SubDrive 加密文件夹 · 客户端密码学（SDV1） =================
 * 格式规范见 CRYPTO.md。本文件只依赖 globalThis.crypto（Web Crypto）：
 * 浏览器与 Node ≥19 均可直接加载（Node 测试见 tests/test_crypto.mjs）。
 * 原则：密钥只进内存（CryptoKey / Uint8Array），永不发送、永不持久化。 */
const SDVault = (() => {
  const MAGIC = new Uint8Array([0x53, 0x44, 0x56, 0x31]); // "SDV1"
  const VERSION = 1;
  const HEADER_LEN = 17; // magic 4 + version 1 + iv 12
  const TAG_LEN = 16;
  const CHECK_PLAINTEXT = "SUBDRIVE-VAULT-CHECK-v1";
  const DEFAULT_ITERATIONS = 210000;

  const subtle = globalThis.crypto.subtle;
  const enc = new TextEncoder();
  const dec = new TextDecoder();

  function b64encode(bytes) {
    let s = "";
    for (let i = 0; i < bytes.length; i += 0x8000) {
      s += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
    }
    return btoa(s);
  }
  function b64decode(str) {
    const bin = atob(str);
    const out = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
    return out;
  }
  function randomBytes(n) {
    const b = new Uint8Array(n);
    globalThis.crypto.getRandomValues(b);
    return b;
  }
  function randomId() {
    return [...randomBytes(16)].map((x) => x.toString(16).padStart(2, "0")).join("");
  }

  /* ---- KDF：PBKDF2-HMAC-SHA256 → AES-256-GCM CryptoKey ---- */
  async function deriveKey(password, saltBytes, iterations) {
    const base = await subtle.importKey("raw", enc.encode(password), "PBKDF2", false, ["deriveKey", "deriveBits"]);
    return subtle.deriveKey(
      { name: "PBKDF2", salt: saltBytes, iterations, hash: "SHA-256" },
      base,
      { name: "AES-GCM", length: 256 },
      true, // 可导出：仅供测试向量校验密钥 hex，业务代码不导出
      ["encrypt", "decrypt"]
    );
  }
  async function deriveKeyHex(password, saltBytes, iterations) {
    const base = await subtle.importKey("raw", enc.encode(password), "PBKDF2", false, ["deriveBits"]);
    const bits = await subtle.deriveBits(
      { name: "PBKDF2", salt: saltBytes, iterations, hash: "SHA-256" }, base, 256);
    return [...new Uint8Array(bits)].map((x) => x.toString(16).padStart(2, "0")).join("");
  }

  /* ---- SDV1 信封 ---- */
  async function encryptBlob(key, plaintextBytes) {
    const iv = randomBytes(12);
    const ct = new Uint8Array(await subtle.encrypt({ name: "AES-GCM", iv }, key, plaintextBytes));
    const out = new Uint8Array(HEADER_LEN + ct.length);
    out.set(MAGIC, 0);
    out[4] = VERSION;
    out.set(iv, 5);
    out.set(ct, HEADER_LEN);
    return out;
  }
  async function decryptBlob(key, blobBytes) {
    const bytes = blobBytes instanceof Uint8Array ? blobBytes : new Uint8Array(blobBytes);
    if (bytes.length < HEADER_LEN + TAG_LEN) throw new Error("密文过短，数据已损坏");
    for (let i = 0; i < 4; i++) {
      if (bytes[i] !== MAGIC[i]) throw new Error("不是 SDV1 加密数据");
    }
    if (bytes[4] !== VERSION) throw new Error(`不支持的加密格式版本 ${bytes[4]}`);
    const iv = bytes.subarray(5, 17);
    const ct = bytes.subarray(HEADER_LEN);
    // subtle.decrypt 在 tag 校验失败时抛 OperationError —— 密码错误或数据被篡改
    const pt = await subtle.decrypt({ name: "AES-GCM", iv }, key, ct);
    return new Uint8Array(pt);
  }

  /* ---- 描述文件 ---- */
  async function createDescriptor(password) {
    const salt = randomBytes(16);
    const iterations = DEFAULT_ITERATIONS;
    const key = await deriveKey(password, salt, iterations);
    const checkBlob = await encryptBlob(key, enc.encode(CHECK_PLAINTEXT));
    const descriptor = {
      format: "subdrive-vault",
      version: 1,
      kdf: { algo: "PBKDF2-SHA256", iterations, salt: b64encode(salt) },
      check: b64encode(checkBlob),
      created_at: new Date().toISOString(),
    };
    return { descriptor, key };
  }
  function parseDescriptor(jsonText) {
    const d = JSON.parse(jsonText);
    if (!d || d.format !== "subdrive-vault" || d.version !== 1) {
      throw new Error("不是 SubDrive 加密文件夹");
    }
    if (!d.kdf || d.kdf.algo !== "PBKDF2-SHA256") throw new Error("不支持的密钥派生算法");
    return d;
  }
  /* 用密码打开描述文件：成功返回 CryptoKey；密码错误抛错（check 解密/比对失败）。 */
  async function unlockWithPassword(descriptor, password) {
    const salt = b64decode(descriptor.kdf.salt);
    const key = await deriveKey(password, salt, descriptor.kdf.iterations);
    let plain;
    try {
      plain = await decryptBlob(key, b64decode(descriptor.check));
    } catch {
      throw new Error("文件夹密码错误");
    }
    if (dec.decode(plain) !== CHECK_PLAINTEXT) throw new Error("文件夹密码错误");
    return key;
  }

  /* ---- 清单 ---- */
  function emptyManifest() {
    return { version: 1, files: [] };
  }
  function serializeManifest(manifest) {
    return enc.encode(JSON.stringify(manifest));
  }
  function parseManifest(bytes) {
    const m = JSON.parse(dec.decode(bytes));
    if (!m || m.version !== 1 || !Array.isArray(m.files)) throw new Error("清单格式损坏");
    return m;
  }

  return {
    MAGIC, VERSION, HEADER_LEN, CHECK_PLAINTEXT, DEFAULT_ITERATIONS,
    b64encode, b64decode, randomBytes, randomId,
    deriveKey, deriveKeyHex, encryptBlob, decryptBlob,
    createDescriptor, parseDescriptor, unlockWithPassword,
    emptyManifest, serializeManifest, parseManifest,
  };
})();

if (typeof window !== "undefined") window.SDVault = SDVault;
if (typeof globalThis !== "undefined") globalThis.SDVault = SDVault;
