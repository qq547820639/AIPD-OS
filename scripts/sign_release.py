#!/usr/bin/env python3
"""发布物签名工具（RELEASE_SIGNING.md 的实现）。

计算文件的 SHA-256 摘要，并用 HMAC-SHA256（密钥来自环境变量
``AIPD_RELEASE_SIGNING_KEY``）生成分离式签名文件。

产物：
- ``<file>.sha256``：摘要文本（``<hex>  <filename>``）
- ``<file>.sig``：HMAC-SHA256 签名（十六进制）

无第三方依赖，输出确定。

用法：
    python scripts/sign_release.py <file>            # 生成 .sha256 与 .sig
    python scripts/sign_release.py --verify <file>   # 校验现有签名
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import os
import sys
from pathlib import Path

ENV_KEY = "AIPD_RELEASE_SIGNING_KEY"


def sha256_file(path: Path) -> str:
    """计算文件的 SHA-256 摘要（十六进制）。"""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def sign_bytes(data: bytes, key: str) -> str:
    """用 HMAC-SHA256 对数据签名，返回十六进制签名。"""
    return hmac.new(key.encode("utf-8"), data, hashlib.sha256).hexdigest()


def sign_file(path: Path, key: str) -> str:
    """对文件签名，返回 HMAC-SHA256 十六进制签名。"""
    return sign_bytes(path.read_bytes(), key)


def verify_signature(path: Path, signature_hex: str, key: str) -> bool:
    """校验签名是否匹配（常量时间比较）。"""
    expected = sign_file(path, key)
    return hmac.compare_digest(expected, signature_hex.strip())


def _require_key() -> str:
    key = os.environ.get(ENV_KEY)
    if not key:
        print(f"error: {ENV_KEY} environment variable is not set", file=sys.stderr)
        raise SystemExit(2)
    return key


def sign_release(path_str: str) -> dict:
    """签名一个发布物，返回摘要与签名信息。"""
    path = Path(path_str)
    if not path.is_file():
        raise FileNotFoundError(path_str)
    key = _require_key()
    digest = sha256_file(path)
    sig = sign_file(path, key)
    sha_path = path.with_suffix(path.suffix + ".sha256")
    sha_path.write_text(f"{digest}  {path.name}\n", encoding="utf-8")
    path.with_suffix(path.suffix + ".sig").write_text(sig + "\n", encoding="utf-8")
    return {"file": str(path), "sha256": digest, "signature": sig}


def verify_release(path_str: str) -> bool:
    """校验一个发布物的 .sig 签名。"""
    path = Path(path_str)
    if not path.is_file():
        raise FileNotFoundError(path_str)
    key = _require_key()
    sig_path = path.with_suffix(path.suffix + ".sig")
    if not sig_path.is_file():
        print(f"error: signature file not found: {sig_path}", file=sys.stderr)
        return False
    stored = sig_path.read_text(encoding="utf-8").strip()
    return verify_signature(path, stored, key)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="AIPD-OS 发布物签名工具")
    parser.add_argument("file", help="要签名/校验的文件")
    parser.add_argument("--verify", action="store_true", help="校验已有签名而非生成")
    args = parser.parse_args(argv)

    if args.verify:
        ok = verify_release(args.file)
        print(f"verified: {args.file} -> {'OK' if ok else 'FAILED'}")
        return 0 if ok else 1

    info = sign_release(args.file)
    print(f"signed: {info['file']}")
    print(f"  sha256: {info['sha256']}")
    print(f"  signature: {info['signature']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
