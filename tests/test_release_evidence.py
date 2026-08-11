"""P0-1 发布证据体系测试：Source/Bundle/Provenance 证据 + Ed25519 签名 + release-ready 门禁。"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import release_evidence  # noqa: E402
import sign_release  # noqa: E402
from production_release_gate import run_release_ready  # noqa: E402

GATE_SCRIPT = REPO_ROOT / "scripts" / "production_release_gate.py"


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(["git", "-C", str(repo), *args],
                          capture_output=True, text=True)
    return proc.stdout.strip()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def keys_env(tmp_path, monkeypatch):
    """把 Ed25519 密钥放到仓库外的临时目录，并通过环境变量指向。"""
    keys_dir = tmp_path / "keys"
    keys_dir.mkdir(exist_ok=True)
    priv = str(keys_dir / "private.pem")
    pub = str(keys_dir / "public.pem")
    monkeypatch.setenv(sign_release.ENV_PRIVATE_KEY, priv)
    monkeypatch.setenv(sign_release.ENV_PUBLIC_KEY, pub)
    return {"private": priv, "public": pub}


def _make_repo(tmp_path, commit_evidence: bool, tag: str | None):
    """构造临时 git 仓库并生成三份证据 + Ed25519 签名。

    commit_evidence=False：证据为 git 忽略的生成物（工作区干净、source_commit==HEAD），
    用于证据/签名/门禁测试。
    commit_evidence=True：证据一并提交并打 tag，用于审计可复现性测试。
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "pkg").mkdir()
    (repo / "pkg" / "a.py").write_text("VALUE_A = 1\n", encoding="utf-8")
    (repo / "pkg" / "b.py").write_text("VALUE_B = 2\n", encoding="utf-8")
    (repo / "README.md").write_text("# demo\n", encoding="utf-8")
    if not commit_evidence:
        # 忽略证据/签名/发布产物，使生成后工作区仍保持干净
        (repo / ".gitignore").write_text(
            "SOURCE_MANIFEST.json\nBUNDLE_MANIFEST.json\nPROVENANCE.json\n"
            "*.zip\n*.sig\n*.sha256\n.release_keys/\nreport.json\n",
            encoding="utf-8")
    _git(repo, "init", "-q")
    _git(repo, "add", "-A")
    _git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "seed")

    # 测试报告（pytest 机器可读 JSON；v5.8.1 Commit 15：必须携带 source_commit/
    # package_version/generated_at —— Audit Freshness 门禁要求）
    head = _git(repo, "rev-parse", "HEAD")
    report = repo / "report.json"
    report.write_text(json.dumps({
        "summary": {"passed": 10, "failed": 0, "total": 10},
        "source_commit": head,
        "package_version": "5.6.0",
        "created": "2026-01-01T00:00:00Z",
    }), encoding="utf-8")

    bundle = repo / "aipd-os-5.6.0.zip"
    # 第一轮：生成 SOURCE_MANIFEST / PROVENANCE（无 bundle）
    release_evidence.write_evidence(repo, repo, "5.6.0", None, report)
    # 用仓库内所有非 zip 文件构建发布包（保证解压后 SOURCE_MANIFEST 可复现）
    with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in sorted(repo.rglob("*")):
            if p.is_file() and p.suffix != ".zip" and p.name != bundle.name:
                zf.write(p, arcname=p.relative_to(repo).as_posix())
    # 第二轮：带 bundle 重新生成，写入 BUNDLE_MANIFEST 与带 bundle_hash 的 PROVENANCE
    release_evidence.write_evidence(repo, repo, "5.6.0", bundle, report)

    # Ed25519 签名 bundle
    sign_release.keygen()
    sign_release.sign_file_ed25519(bundle)

    if commit_evidence:
        _git(repo, "add", "-A")
        _git(repo, "-c", "user.email=t@t", "-c", "user.name=t",
             "commit", "-qm", "evidence")
        if tag:
            _git(repo, "tag", tag)
    return repo


@pytest.fixture
def clean_repo(tmp_path, keys_env):
    """干净的临时 git 仓库：证据为 git 忽略的生成物（source_commit==HEAD、工作区干净）。"""
    return _make_repo(tmp_path, commit_evidence=False, tag=None)


# --------------------------------------------------------------------------
# A. 三份证据
# --------------------------------------------------------------------------
def test_three_evidence_files_exist_and_complete(clean_repo):
    for name in ("SOURCE_MANIFEST.json", "BUNDLE_MANIFEST.json", "PROVENANCE.json"):
        assert (clean_repo / name).is_file(), f"missing {name}"

    source = json.loads((clean_repo / "SOURCE_MANIFEST.json").read_text(encoding="utf-8"))
    bundle = json.loads((clean_repo / "BUNDLE_MANIFEST.json").read_text(encoding="utf-8"))
    prov = json.loads((clean_repo / "PROVENANCE.json").read_text(encoding="utf-8"))

    head = _git(clean_repo, "rev-parse", "HEAD")
    assert source["source_commit"] == head
    assert prov["source_commit"] == head

    # 字段完整
    assert isinstance(source["files"], list) and source["files"]
    for f in source["files"]:
        assert {"path", "size", "sha256"} <= set(f)
    assert bundle["bundle_sha256"]
    assert isinstance(bundle["entries"], list) and bundle["entries"]
    for e in bundle["entries"]:
        assert {"path", "size", "sha256"} <= set(e)
    assert prov["build_environment"]["python"]
    assert prov["build_time"]
    assert prov["dependency_lock"] is not None
    assert prov["test_report"]["parsed"] is True
    assert prov["bundle_hash"] == bundle["bundle_sha256"] == _sha256(clean_repo / "aipd-os-5.6.0.zip")

    # 三份证据互不包含自身
    source_paths = {f["path"] for f in source["files"]}
    assert "SOURCE_MANIFEST.json" not in source_paths
    assert "BUNDLE_MANIFEST.json" not in source_paths
    assert "PROVENANCE.json" not in source_paths
    assert "RELEASE_MANIFEST.json" not in source_paths


def test_bundle_sha256_matches_reextract(clean_repo):
    """BUNDLE_MANIFEST 中每个条目的 sha256 与重新解压内容一致。"""
    bundle_manifest = json.loads(
        (clean_repo / "BUNDLE_MANIFEST.json").read_text(encoding="utf-8"))
    with zipfile.ZipFile(clean_repo / "aipd-os-5.6.0.zip") as zf:
        for e in bundle_manifest["entries"]:
            assert hashlib.sha256(zf.read(e["path"])).hexdigest() == e["sha256"], e["path"]


# --------------------------------------------------------------------------
# B. Ed25519 签名
# --------------------------------------------------------------------------
def test_ed25519_keygen_sign_verify_roundtrip(clean_repo, keys_env):
    assert Path(keys_env["private"]).is_file()
    assert Path(keys_env["public"]).is_file()
    data = b"hello ed25519"
    priv = sign_release.load_private_key()
    pub = sign_release.load_public_key()
    sig = sign_release.sign_bytes_ed25519(data, priv)
    assert sig
    assert sign_release.verify_bytes_ed25519(data, sig, pub) is True
    # 篡改后失败
    assert sign_release.verify_bytes_ed25519(b"tampered", sig, pub) is False


def test_ed25519_sign_verify_file_roundtrip(clean_repo):
    target = clean_repo / "pkg" / "a.py"
    info = sign_release.sign_file_ed25519(target)
    assert (clean_repo / "pkg" / "a.py.ed25519.sig").is_file()
    assert sign_release.verify_file_ed25519(target) is True
    # 篡改内容后验签失败
    target.write_bytes(target.read_bytes() + b"tampered")
    assert sign_release.verify_file_ed25519(target) is False


def test_ed25519_sign_errors_when_cryptography_unavailable(monkeypatch, tmp_path):
    target = tmp_path / "f.bin"
    target.write_bytes(b"x")
    # 模拟 cryptography 缺失
    def boom():
        raise RuntimeError("cryptography is not installed")
    monkeypatch.setattr(sign_release, "_ed25519", boom)
    with pytest.raises(RuntimeError):
        sign_release.sign_file_ed25519(target)
    # CLI --sign 返回非零（明确报错，不伪造成功）
    rc = sign_release.main(["--sign", str(target)])
    assert rc == 3


def test_digest_mac_dsig_products_distinct(tmp_path, keys_env):
    """摘要(.sha256) / MAC(.sig) / Ed25519 数字签名(.ed25519.sig) 三者产物区分清楚。"""
    target = tmp_path / "release.bin"
    target.write_bytes(b"cargo" * 10)
    os.environ.setdefault(sign_release.ENV_KEY, "unit-key")
    sign_release.sign_release(str(target))          # MAC -> .sha256 + .sig
    sign_release.keygen()
    sign_release.sign_file_ed25519(target)          # Ed25519 -> .ed25519.sig

    sha_file = tmp_path / "release.bin.sha256"
    mac_file = tmp_path / "release.bin.sig"
    dsig_file = tmp_path / "release.bin.ed25519.sig"
    assert sha_file.is_file()
    assert mac_file.is_file()
    assert dsig_file.is_file()
    # 三个产物内容互不相同（不同机制）
    assert sha_file.read_bytes() != mac_file.read_bytes()
    assert mac_file.read_bytes() != dsig_file.read_bytes()
    # 摘要文本包含 hex 摘要
    assert _sha256(target) in sha_file.read_text(encoding="utf-8")
    # MAC 是十六进制 HMAC；Ed25519 是 Base64 数字签名
    mac = mac_file.read_text(encoding="utf-8").strip()
    assert len(mac) == 64 and all(c in "0123456789abcdef" for c in mac)
    base64.b64decode(dsig_file.read_bytes().strip())


# --------------------------------------------------------------------------
# C. release-ready 门禁
# --------------------------------------------------------------------------
def _run_gate(repo: Path, monkeypatch) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    return subprocess.run(
        [sys.executable, str(GATE_SCRIPT), "--release-ready", "--repo", str(repo)],
        capture_output=True, text=True, env=env,
    )


def test_release_ready_passes_in_clean_workspace(clean_repo):
    r = _run_gate(clean_repo, None)
    out = json.loads(r.stdout)
    assert out["release_ready"] is True, out
    assert all(c["passed"] for c in out["checks"]), out
    assert r.returncode == 0


def test_release_ready_fails_after_tampering_protected_file(clean_repo):
    # 篡改一个被 SOURCE_MANIFEST 保护的文件
    (clean_repo / "pkg" / "a.py").write_text("VALUE_A = 999\n", encoding="utf-8")
    r = _run_gate(clean_repo, None)
    out = json.loads(r.stdout)
    assert out["release_ready"] is False, out
    by_name = {c["check"]: c for c in out["checks"]}
    assert by_name["workspace_clean"]["passed"] is False
    assert by_name["source_manifest_zero_diff"]["passed"] is False
    assert r.returncode == 2


def test_release_ready_function_result(clean_repo):
    """import 层面调用 run_release_ready 结果一致（便于程序化集成）。"""
    result = run_release_ready(clean_repo, None, None)
    assert result["release_ready"] is True


# --------------------------------------------------------------------------
# D. aipd audit 可复现（干净 clone 与解压后的发布包）
# --------------------------------------------------------------------------
def test_audit_reproducible_in_clean_clone(tmp_path, keys_env):
    """干净 clone 中 audit 结果一致：hash 一致、HEAD==最终 tag SHA、hash_mismatch_count=0。"""
    repo = _make_repo(tmp_path, commit_evidence=True, tag="v5.6.0")
    clone = tmp_path / "clone"
    subprocess.run(["git", "clone", "-q", str(repo), str(clone)], check=True)
    from scripts.audit_repo import audit_repo  # noqa: E402
    report = audit_repo(clone)
    sm = report["source_manifest_verification"]
    assert sm["present"] is True
    assert sm["hash_mismatch_count"] == 0
    # HEAD == 最终 tag SHA
    assert report["latest_commit_sha"] == _git(clone, "rev-parse", "HEAD")
    assert _git(clone, "rev-parse", "v5.6.0") == report["latest_commit_sha"]


def test_audit_reproducible_in_unpacked_release(tmp_path, keys_env):
    """解压后的发布包中 audit 结果一致：hash_mismatch_count=0。"""
    repo = _make_repo(tmp_path, commit_evidence=True, tag=None)
    unpack = tmp_path / "unpacked"
    unpack.mkdir()
    with zipfile.ZipFile(repo / "aipd-os-5.6.0.zip") as zf:
        zf.extractall(str(unpack))
    from scripts.audit_repo import audit_repo  # noqa: E402
    report = audit_repo(unpack)  # 无 .git 也应正常返回
    sm = report["source_manifest_verification"]
    assert sm["present"] is True
    assert sm["hash_mismatch_count"] == 0

def test_release_ready_fails_on_stale_test_report(clean_repo):
    """v5.8.1 Commit 15（§38-39）：test_report.source_commit != HEAD → STALE，
    不能作为 release PASS 证据。"""
    prov_path = clean_repo / "PROVENANCE.json"
    prov = json.loads(prov_path.read_text(encoding="utf-8"))
    assert prov["test_report"]["source_commit"]
    prov["test_report"]["source_commit"] = "0" * 40  # 篡改为错误 commit
    prov_path.write_text(json.dumps(prov), encoding="utf-8")
    r = _run_gate(clean_repo, None)
    out = json.loads(r.stdout)
    assert out["release_ready"] is False, out
    by_name = {c["check"]: c for c in out["checks"]}
    assert by_name["test_numbers_from_report"]["passed"] is False
    assert "STALE" in " ".join(by_name["test_numbers_from_report"]["detail"])
