"""Change Set 7 Manual 外骨骼默认事实隔离测试（P0-11）。

覆盖：
- 空 facts 跑 plan-batches + run-batch（provider external）→ 每个 defn 含
  ``truth_gaps``、无「外骨骼」字样、curve 页 curve 为 None；
- 带完整 facts 跑 → 正文来自 facts、无 TBD 标记（回归）；
- validate() 结构性校验仍通过。
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANUAL = ROOT / "scripts" / "manual_chain.py"

# 完整产品事实：覆盖 _build_defn 的全部内容字段。
FULL_FACTS = {
    "product": {"name": "智能护理床", "tagline": "为长期照护场景设计的智能护理床。"},
    "params": {"peak_torque": 120, "weight": 8.5},
    "principle": ["系统通过电动推杆调节背部与腿部角度。"],
    "modules": [{"name": "电动推杆", "desc": "无刷电机驱动"}],
    "scenes": [{"title": "居家照护", "desc": "辅助老人起身"}],
    "cmf": {"color": "白色", "material": "ABS", "finish": "哑光"},
    "qa": [{"q": "承重多少", "a": "150kg"}],
    "closure": [{"text": "感谢选择我们的产品。"}],
    "characters": [{"appearance": "白色护理床"}],
    "curve": [{"label": "负载曲线", "points": [[0, 1], [1, 2]]}],
}

ALL_ROLES = {
    "cover", "principle", "parameter_table", "module", "user_scene",
    "cmf", "curve", "qa", "closure",
}


def _load_module():
    """惰性导入 scripts/manual_chain.py（顶层有 print 副作用，仅取函数）。"""
    import importlib.util

    spec = importlib.util.spec_from_file_location("manual_chain_honesty", MANUAL)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["manual_chain_honesty"] = mod
    spec.loader.exec_module(mod)
    return mod


def _cli(cwd: Path, *args: str) -> str:
    r = subprocess.run(
        [sys.executable, str(MANUAL), *args],
        capture_output=True, text=True, cwd=str(cwd),
    )
    assert r.returncode == 0, f"cli failed: {args}\nstdout={r.stdout}\nstderr={r.stderr}"
    return r.stdout


def _build_state(tmp_path, facts_path=None):
    """init + plan-batches + 逐批 run-batch；返回 (state 路径, 全部 defn 列表)。"""
    state = tmp_path / "state.json"
    _cli(tmp_path, "init", "--state", str(state), "--project-id", "honesty",
         "--minimum-pages", "10")
    _cli(tmp_path, "plan-batches", "--state", str(state), "--minimum-pages", "10")
    plan = json.loads(state.read_text(encoding="utf-8"))["batch_plan"]
    batches = sorted({e["batch_id"] for e in plan}, key=lambda s: int(s.split("_")[1]))
    for bid in batches:
        args = ["run-batch", "--state", str(state), "--batch-id", bid,
                "--prompt", f"honesty {bid}", "--theory-version", "T1",
                "--truth-version", "PT-1", "--anchors", "auto",
                "--output-dir", str(tmp_path / f"out_{bid}")]
        if facts_path is not None:
            args += ["--facts", str(facts_path)]
        _cli(tmp_path, *args)
    data = json.loads(state.read_text(encoding="utf-8"))
    defns = [op["defn"] for br in data["batch_runs"] for op in br["output_pages"]]
    return state, data, defns


def _defn_text(defn) -> str:
    return json.dumps(defn, ensure_ascii=False)


# ---------------------------------------------------------------------------
# 1) 空 facts → 显式 TBD、无外骨骼默认事实、curve=None
# ---------------------------------------------------------------------------
def test_empty_facts_produce_tbd_not_exoskeleton(tmp_path):
    state, data, defns = _build_state(tmp_path)
    assert defns, "run-batch 应产出至少一个页面 defn"
    for defn in defns:
        # 每个 defn 都带 truth_gaps 审计字段
        assert "truth_gaps" in defn
        assert isinstance(defn["truth_gaps"], list)
        text = _defn_text(defn)
        # 绝不出现「外骨骼」等硬编码 demo 产品事实
        assert "外骨骼" not in text, text
    # curve 页：curve 必须为 None（删除伪造数据点）
    curve = [d for d in defns if d["role"] == "curve"]
    assert curve and all(d["curve"] is None for d in curve)
    # cover 默认 product_name 为 TBD
    cover = next(d for d in defns if d["role"] == "cover")
    assert "未指定（TBD）" in _defn_text(cover) or "TBD" in _defn_text(cover)


# ---------------------------------------------------------------------------
# 2) 空 facts 时 truth_gaps 非空且覆盖缺字段
# ---------------------------------------------------------------------------
def test_empty_facts_truth_gaps_listed():
    mc = _load_module()
    gaps_union = set()
    for role in ALL_ROLES:
        defn = mc._build_defn({"page_id": f"p_{role}", "role": role,
                               "page_number": 1}, {})
        gaps_union.update(defn["truth_gaps"])
    # 核心内容字段缺失必须被标记
    for field in ("product.name", "principle", "modules", "scenes", "cmf",
                  "qa", "closure", "characters", "curve", "params"):
        assert field in gaps_union, f"truth_gaps 应包含 {field}"


# ---------------------------------------------------------------------------
# 3) 带完整 facts → 正文来自 facts、无 TBD（回归）
# ---------------------------------------------------------------------------
def test_full_facts_use_facts_not_tbd():
    mc = _load_module()
    for role in ALL_ROLES:
        defn = mc._build_defn({"page_id": f"p_{role}", "role": role,
                               "page_number": 1}, FULL_FACTS)
        assert "TBD" not in _defn_text(defn), role
        assert defn["truth_gaps"] == [], role
        body = "\n".join(defn.get("body") or []) + _defn_text(defn.get("param_table", []))
        if role == "cover":
            assert "智能护理床" in _defn_text(defn)
        elif role == "principle":
            assert "电动推杆" in body
        elif role == "parameter_table":
            assert any(r["param"] == "peak_torque" for r in defn["param_table"])
        elif role == "module":
            assert "电动推杆" in body
        elif role == "user_scene":
            assert "居家照护" in body
        elif role == "cmf":
            assert "白色" in body
            assert defn["expected_cmf"] == FULL_FACTS["cmf"]
        elif role == "curve":
            assert defn["curve"] is not None
        elif role == "qa":
            assert "承重多少" in body
        elif role == "closure":
            assert "感谢选择我们的产品" in body


def test_full_facts_via_cli(tmp_path):
    facts_path = tmp_path / "facts.json"
    facts_path.write_text(json.dumps(FULL_FACTS, ensure_ascii=False), encoding="utf-8")
    state, data, defns = _build_state(tmp_path, facts_path=facts_path)
    for defn in defns:
        assert "TBD" not in _defn_text(defn), defn["page_id"]
        assert "外骨骼" not in _defn_text(defn)


# ---------------------------------------------------------------------------
# 4) validate() 结构性校验仍通过
# ---------------------------------------------------------------------------
def test_validate_passes_after_honesty_batch(tmp_path):
    # 单批状态（无后续批 → 无 batch continuity 要求），验证结构性校验仍通过。
    state = tmp_path / "state.json"
    _cli(tmp_path, "init", "--state", str(state), "--project-id", "honesty",
         "--minimum-pages", "10")
    _cli(tmp_path, "plan-batches", "--state", str(state), "--minimum-pages", "10")
    _cli(tmp_path, "run-batch", "--state", str(state), "--batch-id", "batch_1",
         "--prompt", "honesty", "--theory-version", "T1",
         "--truth-version", "PT-1", "--anchors", "auto",
         "--output-dir", str(tmp_path / "out"))
    data = json.loads(state.read_text(encoding="utf-8"))
    mc = _load_module()
    result = mc.validate(data)
    assert result["passed"] is True, result["errors"]
    assert result["page_count"] >= 1
