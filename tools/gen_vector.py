"""生成 SubDrive 加密文件夹（SDV1 格式）的固定测试向量。

向量写入 testdata/crypto_vector.json，供 JS（Web Crypto）与 Dart（package:cryptography）
两端测试共同验证：同一密码 + 同一盐 → 同一派生密钥；同一信封字节 → 解出同一明文。
格式定义见 CRYPTO.md。本脚本是该格式的参考实现（Python cryptography）。
"""
import base64
import hashlib
import json
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

MAGIC = b"SDV1"
VERSION = 1
CHECK_PLAINTEXT = b"SUBDRIVE-VAULT-CHECK-v1"

PASSWORD = "correct horse battery staple"
SALT = bytes(range(0x00, 0x10))            # 00 01 ... 0f
ITERATIONS = 210_000
FILE_ID = "0123456789abcdeffedcba9876543210"
FILE_NAME = "向量测试.txt"
FILE_MIME = "text/plain"
FILE_ADDED_AT = "2026-01-01T00:00:00.000Z"
FILE_PLAINTEXT = "SubDrive 加密测试向量 — hello vault!\n".encode("utf-8")
IV_CHECK = bytes(range(0x20, 0x2C))        # 20 ... 2b
IV_FILE = bytes(range(0x10, 0x1C))         # 10 ... 1b
IV_MANIFEST = bytes(range(0x30, 0x3C))     # 30 ... 3b


def derive_key(password: str, salt: bytes, iterations: int) -> bytes:
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=iterations)
    return kdf.derive(password.encode("utf-8"))


def envelope(key: bytes, iv: bytes, plaintext: bytes) -> bytes:
    ct = AESGCM(key).encrypt(iv, plaintext, None)  # 输出 = 密文 || 16B tag（与 Web Crypto 一致）
    return MAGIC + bytes([VERSION]) + iv + ct


def main() -> None:
    key = derive_key(PASSWORD, SALT, ITERATIONS)
    # 与 hashlib 的独立实现交叉验证一次
    assert hashlib.pbkdf2_hmac("sha256", PASSWORD.encode(), SALT, ITERATIONS, 32) == key

    manifest = {
        "version": 1,
        "files": [{
            "id": FILE_ID,
            "name": FILE_NAME,
            "size": len(FILE_PLAINTEXT),
            "mime": FILE_MIME,
            "added_at": FILE_ADDED_AT,
        }],
    }
    manifest_pt = json.dumps(manifest, ensure_ascii=False, separators=(",", ":")).encode("utf-8")

    vector = {
        "comment": "SDV1 fixed test vector — see CRYPTO.md. All binary values base64 unless suffixed _hex.",
        "password": PASSWORD,
        "kdf": {"algo": "PBKDF2-SHA256", "iterations": ITERATIONS,
                "salt_b64": base64.b64encode(SALT).decode()},
        "derived_key_hex": key.hex(),
        "check": {"iv_b64": base64.b64encode(IV_CHECK).decode(),
                  "plaintext_ascii": CHECK_PLAINTEXT.decode(),
                  "blob_b64": base64.b64encode(envelope(key, IV_CHECK, CHECK_PLAINTEXT)).decode()},
        "file": {"id": FILE_ID, "name": FILE_NAME, "mime": FILE_MIME,
                 "plaintext_b64": base64.b64encode(FILE_PLAINTEXT).decode(),
                 "iv_b64": base64.b64encode(IV_FILE).decode(),
                 "blob_b64": base64.b64encode(envelope(key, IV_FILE, FILE_PLAINTEXT)).decode()},
        "manifest": {"plaintext_utf8": manifest_pt.decode("utf-8"),
                     "iv_b64": base64.b64encode(IV_MANIFEST).decode(),
                     "blob_b64": base64.b64encode(envelope(key, IV_MANIFEST, manifest_pt)).decode()},
    }
    out = Path(__file__).resolve().parent.parent / "testdata" / "crypto_vector.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(vector, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out}")
    print(f"derived_key_hex = {key.hex()}")
    print(f"file blob = {len(base64.b64decode(vector['file']['blob_b64']))} bytes "
          f"(plaintext {len(FILE_PLAINTEXT)} + overhead 33)")


if __name__ == "__main__":
    main()
