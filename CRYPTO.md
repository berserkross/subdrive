# SubDrive 加密文件夹 · 密码学格式（SDV1）

> 本文件是 SubDrive「加密文件夹」的**跨平台格式规范**：网页端（Web Crypto）与
> Flutter 端（`package:cryptography`）必须逐字节实现同一格式，才能互解对方写入的数据。
> 参考实现：`tools/gen_vector.py`（Python `cryptography`）；固定测试向量：
> `testdata/crypto_vector.json`（两端测试都必须用它验证，见 §7）。

## 1. 总体形态

- 加密文件夹是用户空间里的一个**普通文件夹**，其内部文件布局见 §2。加密/解密
  **只发生在客户端**；后端与 Seafile 只经手密文 blob（普通文件），对格式无感知。
- 每个加密文件夹有**独立的文件夹密码**（与登录密码无关）。密钥由文件夹密码经
  PBKDF2 派生（§3），只存在于客户端内存：不发送给服务器、不落盘持久化。
- 服务器侧可见的元数据仅有：blob 的**大小与数量**、文件夹本身的名字与位置、
  描述文件中的盐与迭代次数（公开参数）。**文件名与文件内容不可见。**
- **文件夹密码丢失不可恢复**：没有任何一方持有密钥或后门，数据将永久无法解密。

## 2. 文件夹布局

```
<加密文件夹>/
├── .sdvault.json      描述文件（明文 JSON，见 §5）
├── manifest.enc       清单 blob（SDV1 信封，见 §4；明文结构见 §6）
└── blobs/
    └── <id>.enc       每个文件一个 blob；id = 16 字节随机的 32 位小写十六进制
```

- 除上述保留名外，加密文件夹内不放其他文件；客户端以外的工具往里写文件，后果自负。
- 删除单个文件 = 删除对应 blob 并改写 `manifest.enc`；删除整个加密文件夹 =
  按普通文件夹递归删除（后端无感知）。

## 3. 密钥派生（KDF）

| 参数 | 值 |
|---|---|
| 算法 | PBKDF2-HMAC-SHA256 |
| 口令输入 | 文件夹密码的 **UTF-8** 编码（不做 Unicode 规范化） |
| 盐 | 每文件夹随机 **16 字节**，创建时生成，存于描述文件（base64） |
| 迭代次数 | **210000**（存于描述文件；解密时以描述文件中的值为准） |
| 输出 | **32 字节**，直接用作 AES-256 密钥 |

## 4. 加密信封（SDV1 blob 格式）

所有密文对象（校验块、清单、每个文件）都用同一信封：

```
偏移  长度  内容
0     4     魔数 ASCII "SDV1"（0x53 0x44 0x56 0x31）
4     1     格式版本 = 0x01
5     12    IV / nonce（每次加密随机生成，绝不复用）
17    N+16  AES-256-GCM 密文 || 16 字节认证标签（tag 附于密文尾部）
```

- 算法：AES-256-GCM，密钥为 §3 派生密钥，**无附加数据（AAD = 空）**。
- Web Crypto 的 `subtle.encrypt({name:"AES-GCM", iv}, …)` 输出正是「密文‖tag」，
  与上表一致；`package:cryptography` 的 `AesGcm.with256bits()` 把密文与 MAC
  分开返回，拼接顺序为 `cipherText || mac` 后再写入信封。
- 密文总长 = 明文长 + 33（信封头 17 + tag 16）。
- 解密失败（密码错误、数据被篡改、魔数/版本不符）一律视为**密码错误或数据损坏**，
  客户端给出明确错误，不得静默产出空数据。

## 5. 描述文件 `.sdvault.json`（明文 JSON，UTF-8）

```json
{
  "format": "subdrive-vault",
  "version": 1,
  "kdf": {"algo": "PBKDF2-SHA256", "iterations": 210000, "salt": "<base64 16 字节>"},
  "check": "<base64：一个 SDV1 信封，明文为 ASCII 常量 SUBDRIVE-VAULT-CHECK-v1>",
  "created_at": "<ISO 8601>"
}
```

- `check` 用于在**不读取清单**的前提下快速校验密码是否正确：派生密钥解开 `check`
  且明文等于常量 ⇒ 密码正确。
- 描述文件不含任何文件名/内容信息；盐与校验块泄露不降低安全性（PBKDF2 + 随机盐）。

## 6. 清单 `manifest.enc`（明文结构）

明文为 UTF-8 JSON（序列化时键顺序与空白不作要求，解析按 JSON 语义）：

```json
{
  "version": 1,
  "files": [
    {"id": "<32 位小写十六进制>", "name": "<显示名>", "size": 12345,
     "mime": "text/plain", "added_at": "<ISO 8601>"}
  ]
}
```

- `size` 为**明文**字节数（密文长 = size + 33）。
- 每次增删文件后整表重加密写回（清单规模下成本可忽略）。
- 写入顺序防丢：先上传新 blob 成功，再改写清单；删文件则先改写清单，再删 blob
  （宁可留下孤儿 blob，不可让清单指向不存在的 blob）。

## 7. 固定测试向量（两端必验）

`testdata/crypto_vector.json`，由 `tools/gen_vector.py` 生成（参数：密码
`correct horse battery staple`、盐 `00 01 … 0f`、迭代 210000、三个固定 IV）。
两端测试必须断言：

1. 由密码+盐派生的密钥 hex == 向量 `derived_key_hex`；
2. 解开向量 `file.blob_b64` == 向量 `file.plaintext_b64`；
3. 解开向量 `manifest.blob_b64` 的 UTF-8 文本解析出的 JSON 与向量内清单一致；
4. 解开向量 `check.blob_b64` == ASCII `SUBDRIVE-VAULT-CHECK-v1`；
5. 错误密码派生出的密钥解任一 blob 必须失败。

JS 验证：`node test_crypto.mjs`；Dart 验证：subdrive-app 的 `test/crypto_vector_test.dart`。

## 8. 平台实现要点

- **Web（Web Crypto）**：`importKey("raw", utf8(password), "PBKDF2")` →
  `deriveKey({name:"PBKDF2", salt, iterations, hash:"SHA-256"}, …, {name:"AES-GCM", length:256})`；
  大文件在内存中整体加解密（浏览器端一期可接受，已知限制见 README）。
- **Dart（`package:cryptography`）**：`Pbkdf2(macAlgorithm: Hmac.sha256(), iterations: …, bits: 256)`
  派生；`AesGcm.with256bits()` 加解密，注意 nonce 12 字节、MAC 拼接顺序（见 §4）。
- **Python（参考实现）**：`cryptography` 的 `PBKDF2HMAC` + `AESGCM`（其 encrypt 输出同为密文‖tag）。
