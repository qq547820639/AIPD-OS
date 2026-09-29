r"""`release_evidence.py` 里那四支"从没被常驻调用过"的分支的常驻牙（第 97 片）。

第 96 片排片时一手数过：`_build_environment`、`_dependency_lock`、
`generate_bundle_manifest`、CLI 的 `--bundle` 旗子在 `tests/` 里**零命中**——
也就是说这个发布工具最容易被环境牵着走的那几段，之前只被历轮 `docs/audit/` 里
没人 collect 的取证脚本碰过。分三组：

① 环境段（1–2 条）：头部四格必须等于**独立重算**的宿主事实；两档缺失必须分别是
   `not-installed`（导入不了）与 `unknown`（导入得到但没有 `__version__`），
   且都不许是空串——空串在 JSON 里与"没填"同形。
② 依赖锁（3 条）：`pip freeze` 是尽力而为，所以失败/非零必须折成 `None`（不是垃圾串），
   而**锁文件清单必须照常算出来**（否则一次 freeze 失败就把整段锁信息带走）。
③ bundle（4–7 条）：zip 逐条 sha 用 `hashlib` 独立重算；非 zip 退化成"整包自身"一条；
   `bundle_path` 必须是相对路径（可重定位性就是这个字段的全部意义）；
   `--bundle` 旗子真跑一遍 CLI，并钉"不给旗子就不写 BUNDLE_MANIFEST"。

第 8 条是生产侧对账：读**已入库的** `PROVENANCE.json`，断那几格真的有内容——
它把"缝里能跑通"与"真产物里确实有"分成两件事，缺前者判据测不到分支，缺后者分支测到了
但生产路径可能从没走过（本仓在这族上已经实测过一次：真跑 CLI 抓出 3 个缺陷）。
"""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import platform
import subprocess
import sys
import zipfile
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import release_evidence as ev  # noqa: E402

ANCHOR = "a" * 40


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fake_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "x.py").write_text("x = 1\n", encoding="utf-8")
    (repo / "pyproject.toml").write_text('[project]\nname = "aipd-os"\nversion = "5.6.0"\n',
                                         encoding="utf-8")
    (repo / "requirements-quality.txt").write_text("pytest==8.0.0\n", encoding="utf-8")
    return repo


def _fake_run(monkeypatch: pytest.MonkeyPatch, *, rc: int = 0, stdout: str = "",
              raises: bool = False) -> int:
    """把 `subprocess.run` 换成可控桩，返回它被调了几次（调用次数本身也是判据的一格）。"""
    calls = {"n": 0}

    def fake(cmd, *a, **kw):                                    # noqa: ANN001, ARG001
        calls["n"] += 1
        if raises:
            raise OSError("没有 pip")
        return subprocess.CompletedProcess(cmd, rc, stdout=stdout, stderr="")

    monkeypatch.setattr(ev.subprocess, "run", fake)
    return calls["n"]


def test_build_environment_header_fields_are_the_host_truth() -> None:
    env = ev._build_environment()
    assert sorted(env) == ["os", "packages", "platform", "python", "python_implementation"]
    # 契约侧独立重算，不抄实现的值
    assert env["python"] == platform.python_version(), env
    assert env["python_implementation"] == platform.python_implementation(), env
    assert env["os"] == f"{platform.system()} {platform.release()}", env
    assert env["platform"] == platform.platform(), env


def test_metadata_wins_and_the_two_missing_shapes_stay_distinct(
        monkeypatch: pytest.MonkeyPatch) -> None:
    """三格各钉一极：元数据命中 ⇒ 用元数据；元数据没有 ⇒ 退回属性；两条都没有 ⇒ 分档。

    少第一极时"属性优先"的写法照绿，而本机 `jsonschema.__version__` 已经在吐
    DeprecationWarning——将来它会静默变 `unknown`，与"这台机器没装"同一种形状。
    `not-installed`（没装）与 `unknown`（装了给不出版本）必须分开：前者是覆盖面缺口，
    后者是工具链问题，下游要做的动作不一样。
    """
    env = ev._build_environment()
    for name, want in (("cryptography", "50.0.0"), ("jsonschema", "4.25.1")):
        assert env["packages"][name] == importlib.metadata.version(name), (name, env)
        assert env["packages"][name] == want, (name, env)      # 现读值也不许漂

    # 元数据命中时，一个说谎的属性值不许赢
    liar = ModuleType("cryptography")
    liar.__version__ = "9.9.9-lie"                              # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "cryptography", liar)
    assert ev._build_environment()["packages"]["cryptography"] == "50.0.0"

    def miss(pkg: str, **_kw: object) -> str:
        raise importlib.metadata.PackageNotFoundError(pkg)

    monkeypatch.setattr(ev.importlib.metadata, "version", miss)
    nometa = ModuleType("jsonschema")                            # 导入得到，但没有 __version__
    monkeypatch.setitem(sys.modules, "jsonschema", nometa)
    monkeypatch.setitem(sys.modules, "cryptography", None)       # 让 import 抛 ImportError
    got = ev._build_environment()["packages"]
    assert got["jsonschema"] == "unknown", got
    assert got["cryptography"] == "not-installed", got
    # 任何一档都不许是空串：空串在 JSON 里与"根本没填这一格"同形
    assert all(str(v or "").strip() for v in got.values()), got


def test_dependency_lock_keeps_lockfiles_when_pip_freeze_fails_or_lies(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _fake_repo(tmp_path)
    lockfile = repo / "requirements-quality.txt"

    _fake_run(monkeypatch, raises=True)
    got = ev._dependency_lock(repo)
    assert got["pip_freeze"] is None, got
    assert got["files"] == {"requirements-quality.txt": _sha(lockfile)}, got

    # 非零退码不许把垃圾 stdout 当锁内容记进去（"失败了但写了点东西"是最难查的一档）
    _fake_run(monkeypatch, rc=1, stdout="Traceback: boom\n")
    got2 = ev._dependency_lock(repo)
    assert got2["pip_freeze"] is None, got2
    assert got2["files"], got2                                  # 锁文件面不许被 freeze 拖走

    _fake_run(monkeypatch, rc=0, stdout="  attrs==26.1.0  \n")
    got3 = ev._dependency_lock(repo)
    assert got3["pip_freeze"] == "attrs==26.1.0", got3          # 成功侧收的是去空白的正文


def _zip(tmp_path: Path) -> Path:
    p = tmp_path / "bundle.zip"
    with zipfile.ZipFile(p, "w") as zf:
        # 故意按**逆序**写入：这样"排序面"那条断言不是白抄 zipfile 的插入顺序
        zf.writestr("sub/b.txt", "BBBB")
        zf.writestr("a.txt", "AAA")
    return p


def test_zip_bundle_lists_every_member_with_independently_recomputed_sha(
        tmp_path: Path) -> None:
    p = _zip(tmp_path)
    doc = ev.generate_bundle_manifest(p, repo_root=tmp_path)
    assert doc["entry_count"] == len(doc["entries"]) == 2, doc
    assert [e["path"] for e in doc["entries"]] == ["a.txt", "sub/b.txt"], doc   # 排序面
    assert doc["entries"][0]["sha256"] == hashlib.sha256(b"AAA").hexdigest(), doc
    assert doc["entries"][1]["sha256"] == hashlib.sha256(b"BBBB").hexdigest(), doc
    assert doc["bundle_sha256"] == _sha(p), doc
    assert doc["bundle_size"] == p.stat().st_size == len(p.read_bytes()), doc


def test_non_zip_bundle_degrades_to_exactly_one_self_entry(tmp_path: Path) -> None:
    """非 zip（tar.gz 这类）退化成"整包自身"一条，而不是静默 0 条 ⇒ 空清单看着像合规。"""
    p = tmp_path / "bundle.tar.gz"
    p.write_bytes(b"\x1f\x8b not really gzip, but definitely not a zip")
    doc = ev.generate_bundle_manifest(p, repo_root=tmp_path)
    assert doc["entry_count"] == 1, doc
    assert doc["entries"] == [{"path": p.name, "size": p.stat().st_size,
                              "sha256": _sha(p)}], doc
    assert not zipfile.is_zipfile(str(p)), "这一条的前提是它确实不是 zip"


def test_bundle_path_is_relative_and_not_tied_to_the_dev_machine(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    p = _zip(tmp_path)
    doc = ev.generate_bundle_manifest(p, repo_root=tmp_path)
    assert doc["bundle_path"] == "bundle.zip", doc
    assert not os.path.isabs(doc["bundle_path"]) and "\\" not in doc["bundle_path"], doc

    # 缺省走 cwd：把 cwd 挪到上一层，同一包就得读成上一层的相对路径
    other = tmp_path / "elsewhere"
    other.mkdir()
    monkeypatch.chdir(other)
    rel = ev.generate_bundle_manifest(p)
    assert rel["bundle_path"] == os.path.relpath(str(p), str(other)).replace(os.sep, "/"), rel
    assert rel["bundle_path"] != doc["bundle_path"], (rel["bundle_path"], doc["bundle_path"])


def test_bundle_cli_flag_writes_the_bundle_manifest_and_omission_does_not(
        tmp_path: Path) -> None:
    """`--bundle` 这条旗子第一次被常驻跑：给了就三件套，不给就不许凭空多出 BUNDLE。"""
    repo = _fake_repo(tmp_path)
    for args in (["init", "-q"], ["config", "user.email", "t@example.invalid"],
                 ["config", "user.name", "t"], ["add", "-A"], ["commit", "-q", "-m", "seed"]):
        subprocess.run(["git", "-C", str(repo), *args], capture_output=True, check=True)
    out = tmp_path / "out"
    p = _zip(tmp_path)
    rc = ev.main(["--repo", str(repo), "--out", str(out), "--version", "5.6.0",
                  "--source-commit", ANCHOR, "--bundle", str(p)])
    assert rc == 0, rc
    bundle_doc = json.loads((out / "BUNDLE_MANIFEST.json").read_text(encoding="utf-8"))
    assert bundle_doc["bundle"] == "bundle.zip", bundle_doc
    prov = json.loads((out / "PROVENANCE.json").read_text(encoding="utf-8"))
    assert prov["bundle_hash"] == bundle_doc["bundle_sha256"], (prov, bundle_doc)

    out2 = tmp_path / "out2"
    rc2 = ev.main(["--repo", str(repo), "--out", str(out2), "--version", "5.6.0",
                   "--source-commit", ANCHOR])
    assert rc2 == 0, rc2
    assert not (out2 / "BUNDLE_MANIFEST.json").exists(), "没给 bundle 就不许写这一件"
    prov2 = json.loads((out2 / "PROVENANCE.json").read_text(encoding="utf-8"))
    assert prov2.get("bundle") in (None, ""), prov2


def test_provenance_on_disk_carries_a_populated_build_environment() -> None:
    """生产侧对账：已入库那份 `PROVENANCE.json` 的这几格必须真有内容。

    上面各条都靠桩或临时仓库；这一条钉的是"真跑出来的产物里也确实有"。
    判据只问形状与非空，不问具体版本号（版本号随环境变，钉死就是自锁）。
    """
    prov = json.loads((ROOT / "PROVENANCE.json").read_text(encoding="utf-8"))
    env = prov["build_environment"]
    assert sorted(env) == ["os", "packages", "platform", "python", "python_implementation"]
    assert all(str(env[k]).strip() for k in
               ("os", "platform", "python", "python_implementation")), env
    assert sorted(env["packages"]) == ["aipd_os", "cryptography", "jsonschema"], env["packages"]
    assert all(str(v).strip() for v in env["packages"].values()), env["packages"]
    lock = prov["dependency_lock"]
    assert isinstance(lock["pip_freeze"], str) and lock["pip_freeze"], type(lock["pip_freeze"])
    assert lock["files"], lock                     # 至少一个 LOCKFILE 的 sha 落在证件里
    for name, sha in lock["files"].items():
        assert sha == _sha(ROOT / name), (name, sha)   # 逐条独立重算：证件里的 sha 说得通
