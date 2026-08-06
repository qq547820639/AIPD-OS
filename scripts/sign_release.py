#!/usr/bin/env python3
"""发布物签名工具（RELEASE_SIGNING.md 的实现）。

区分三样东西：
- **摘要（digest）**：文件 SHA-256（``<file>.sha256``）。
- **MAC（HMAC）**：仅内部完整性，用 HMAC-SHA256（密钥来自环境变量
  ``AIPD_RELEASE_SIGNING_KEY``），生成 ``<file>.sig``，标注为 MAC。
- **数字签名**：Ed25519（公开密钥），``<file>.ed25519.sig``，用于对外可验证的非对称验签。

产物：
- ``<file>.sha256``：摘要文本（``<hex>  <filename>``）
- ``<file>.sig``：HMAC-SHA256 签名（MAC，十六进制）
- ``<file>.ed25519.sig``：Ed25519 数字签名（Base64）

依赖：HMAC/SHA-256 仅标准库；Ed25519 需要 ``cryptography``。若 ``cryptography``
不可用，``--sign/--verify`` 会明确报错而不是伪造成功。

用法：
    python scripts/sign_release.py <file>                 # 生成 .sha256 与 .sig（MAC）
    python scripts/sign_release.py --hmac <file>          # 同上，显式标注为 MAC
    python scripts/sign_release.py --keygen               # 生成 Ed25519 密钥对
    python scripts/sign_release.py --sign <file>          # Ed25519 数字签名 -> .ed25519.sig
    python scripts/sign_release.py --verify <file>        # 用公钥验签 .ed25519.sig
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import os
import sys
from pathlib import Path

ENV_KEY = "AIPD_RELEASE_SIGNING_KEY"
ENV_PRIVATE_KEY = "AIPD_RELEASE_PRIVATE_KEY"
ENV_PUBLIC_KEY = "AIPD_RELEASE_PUBLIC_KEY"

_KEY_DIR = Path(__file__).resolve().parent.parent / ".release_keys"
_DEFAULT_PRIVATE = _KEY_DIR / "ed25519_private.pem"
_DEFAULT_PUBLIC = _KEY_DIR / "ed25519_public.pem"


# --------------------------------------------------------------------------
# SHA-256 摘要
# --------------------------------------------------------------------------
def sha256_file(path: Path) -> str:
    """计算文件的 SHA-256 摘要（十六进制）。"""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# --------------------------------------------------------------------------
# MAC（HMAC-SHA256，仅内部完整性）
# --------------------------------------------------------------------------
def sign_bytes(data: bytes, key: str) -> str:
    """用 HMAC-SHA256 对数据签名，返回十六进制 MAC。"""
    return hmac.new(key.encode("utf-8"), data, hashlib.sha256).hexdigest()


def sign_file(path: Path, key: str) -> str:
    """对文件签名，返回 HMAC-SHA256 十六进制 MAC。"""
    return sign_bytes(path.read_bytes(), key)


def verify_signature(path: Path, signature_hex: str, key: str) -> bool:
    """校验 MAC 是否匹配（常量时间比较）。"""
    expected = sign_file(path, key)
    return hmac.compare_digest(expected, signature_hex.strip())


def _require_key() -> str:
    key = os.environ.get(ENV_KEY)
    if not key:
        print(f"error: {ENV_KEY} environment variable is not set", file=sys.stderr)
        raise SystemExit(2)
    return key


def sign_release(path_str: str) -> dict:
    """用 MAC(HMAC-SHA256) 签名一个发布物，返回摘要与 MAC 信息。"""
    path = Path(path_str)
    if not path.is_file():
        raise FileNotFoundError(path_str)
    key = _require_key()
    digest = sha256_file(path)
    sig = sign_file(path, key)
    sha_path = path.with_suffix(path.suffix + ".sha256")
    sha_path.write_text(f"{digest}  {path.name}\n", encoding="utf-8")
    path.with_suffix(path.suffix + ".sig").write_text(sig + "\n", encoding="utf-8")
    return {"file": str(path), "sha256": digest, "signature": sig, "kind": "MAC"}


def verify_release(path_str: str) -> bool:
    """校验一个发布物的 .sig（MAC）签名。"""
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


# --------------------------------------------------------------------------
# Ed25519 公开密钥数字签名（需要 cryptography）
# --------------------------------------------------------------------------
def _ed25519():
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import ed25519
        return serialization, ed25519
    except ImportError as exc:  # pragma: no cover - 依赖缺失时的明确报错
        raise RuntimeError(
            "cryptography is not installed; Ed25519 signing/verification requires "
            "`cryptography`. Please install it (e.g. `.venv/bin/pip install cryptography`) "
            "or use the HMAC/MAC mode instead.") from exc


def _key_paths():
    """返回 (私钥路径, 公钥路径)。环境变量优先，否则用仓库 .release_keys 默认路径。"""
    priv = os.environ.get(ENV_PRIVATE_KEY)
    pub = os.environ.get(ENV_PUBLIC_KEY)
    return Path(priv) if priv else _DEFAULT_PRIVATE, \
        Path(pub) if pub else _DEFAULT_PUBLIC


def generate_ed25519_keypair() -> tuple[bytes, bytes]:
    """生成 Ed25519 密钥对，返回 (private_pem_bytes, public_pem_bytes)。"""
    serialization, ed25519 = _ed25519()
    private_key = ed25519.Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return private_pem, public_pem


def keygen() -> dict:
    """生成并持久化 Ed25519 密钥对，返回结果信息。"""
    priv_path, pub_path = _key_paths()
    private_pem, public_pem = generate_ed25519_keypair()
    priv_path.parent.mkdir(parents=True, exist_ok=True)
    priv_path.write_bytes(private_pem)
    pub_path.write_bytes(public_pem)
    os.chmod(priv_path, 0o600)
    return {"private_key": str(priv_path), "public_key": str(pub_path)}


def load_private_key() -> object:
    """加载 Ed25519 私钥（默认从默认路径或 AIPD_RELEASE_PRIVATE_KEY 指向的文件）。"""
    serialization, _ = _ed25519()
    priv_path, _ = _key_paths()
    if not priv_path.is_file():
        raise FileNotFoundError(
            f"Ed25519 private key not found: {priv_path} "
            f"(run `--keygen` or set {ENV_PRIVATE_KEY} to the key file path)")
    return serialization.load_pem_private_key(priv_path.read_bytes(), password=None)


def load_public_key() -> object:
    """加载 Ed25519 公钥（默认从默认路径或 AIPD_RELEASE_PUBLIC_KEY 指向的文件）。"""
    serialization, _ = _ed25519()
    _, pub_path = _key_paths()
    if not pub_path.is_file():
        raise FileNotFoundError(
            f"Ed25519 public key not found: {pub_path} "
            f"(run `--keygen` or set {ENV_PUBLIC_KEY} to the key file path)")
    return serialization.load_pem_public_key(pub_path.read_bytes())


def sign_bytes_ed25519(data: bytes, private_key) -> bytes:
    """用 Ed25519 对数据签名，返回原始签名字节。"""
    return private_key.sign(data)


def verify_bytes_ed25519(data: bytes, signature: bytes, public_key) -> bool:
    """用 Ed25519 公钥验签，返回是否有效。"""
    try:
        public_key.verify(signature, data)
        return True
    except Exception:
        return False


def sign_file_ed25519(path: Path) -> dict:
    """用 Ed25519 对文件签名，写 ``<file>.ed25519.sig``（Base64）。"""
    if not path.is_file():
        raise FileNotFoundError(path)
    priv = load_private_key()
    sig = sign_bytes_ed25519(path.read_bytes(), priv)
    sig_path = path.with_suffix(path.suffix + ".ed25519.sig")
    sig_path.write_bytes(base64.b64encode(sig) + b"\n")
    return {"file": str(path), "signature_path": str(sig_path),
            "signature": base64.b64encode(sig).decode("ascii"), "kind": "Ed25519"}


def verify_file_ed25519(path: Path) -> bool:
    """用 Ed25519 公钥验签 ``<file>.ed25519.sig``。"""
    if not path.is_file():
        raise FileNotFoundError(path)
    sig_path = path.with_suffix(path.suffix + ".ed25519.sig")
    if not sig_path.is_file():
        print(f"error: Ed25519 signature file not found: {sig_path}", file=sys.stderr)
        return False
    stored = sig_path.read_bytes().strip()
    try:
        sig = base64.b64decode(stored)
    except Exception:
        return False
    pub = load_public_key()
    return verify_bytes_ed25519(path.read_bytes(), sig, pub)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="AIPD-OS 发布物签名工具")
    parser.add_argument("file", nargs="?", help="要签名/校验的文件")
    parser.add_argument("--hmac", action="store_true",
                        help="显式使用 HMAC-SHA256（MAC，仅内部完整性）")
    parser.add_argument("--keygen", action="store_true", help="生成 Ed25519 密钥对")
    parser.add_argument("--sign", action="store_true", help="Ed25519 数字签名（写 .ed25519.sig）")
    parser.add_argument("--verify", action="store_true", help="用公钥验签 Ed25519 签名")
    args = parser.parse_args(argv)

    if args.keygen:
        info = keygen()
        print(f"generated Ed25519 keypair:")
        print(f"  private: {info['private_key']}")
        print(f"  public:  {info['public_key']}")
        return 0

    if args.sign:
        try:
            info = sign_file_ed25519(Path(args.file))
        except RuntimeError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 3
        print(f"signed (Ed25519): {info['file']}")
        print(f"  signature: {info['signature']}")
        return 0

    if args.verify:
        try:
            ok = verify_file_ed25519(Path(args.file))
        except RuntimeError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 3
        print(f"verified: {args.file} -> {'OK' if ok else 'FAILED'}")
        return 0 if ok else 1

    if not args.file:
        parser.error("file argument is required unless --keygen/--sign/--verify")

    # 默认（或显式 --hmac）：MAC（HMAC-SHA256）签名
    info = sign_release(args.file)
    print(f"signed (MAC): {info['file']}")
    print(f"  sha256: {info['sha256']}")
    print(f"  signature: {info['signature']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())