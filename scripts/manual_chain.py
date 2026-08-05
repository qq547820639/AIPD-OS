#!/usr/bin/env python3
"""连续附件产品手册执行链（v5.0）。

状态注册与校验：init / add-prompt / register-page / lock-anchor / validate / status。
真实批次执行：plan-batches（生成 >=N 页批次计划）、run-batch（真实驱动图像适配器+排版渲染器，
保存完整批次上下文到 batch_runs；图像后端不可用时诚实生成外部任务包并标记 external_pending）。
"""
import argparse, json, hashlib, os, sys
from pathlib import Path
from datetime import datetime, timezone

# 允许独立运行 / 被测试子进程调用时导入 src 下的 aipd_os 包
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))


def now(): return datetime.now(timezone.utc).isoformat()
def load(p): return json.loads(Path(p).read_text(encoding='utf-8'))
def save(p, d):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    Path(p).write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding='utf-8')


def sha(path):
    p = Path(path)
    if not p.exists() or not p.is_file(): return None
    h = hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda: f.read(1024 * 1024), b''): h.update(b)
    return h.hexdigest()


# ---------------------------------------------------------------- 状态命令
def cmd_init(a):
    d = {"schema_version": "1.0", "project_id": a.project_id, "phase": "theory_ingested",
         "minimum_pages": a.minimum_pages, "source_materials": [], "prompts": [], "pages": [],
         "anchors": [], "batches": [], "batch_plan": [], "batch_runs": [],
         "visual_bible": None, "design_intent_package": None, "facts_version": None,
         "created_at": now(), "updated_at": now()}
    save(a.state, d); print(json.dumps(d, ensure_ascii=False, indent=2))


def cmd_add_prompt(a):
    d = load(a.state); ins = a.input or []; outs = a.output or []
    item = {"id": a.prompt_id, "purpose": a.purpose, "instruction": a.instruction,
            "inputs": ins, "outputs": outs, "status": a.status, "created_at": now()}
    d["prompts"] = [x for x in d["prompts"] if x.get("id") != a.prompt_id] + [item]
    d["updated_at"] = now(); save(a.state, d); print(json.dumps(item, ensure_ascii=False, indent=2))


def cmd_register_page(a):
    d = load(a.state)
    item = {"page_id": a.page_id, "role": a.role, "path": a.path, "batch_id": a.batch_id,
            "depends_on": a.depends_on or [], "facts_version": a.facts_version,
            "status": a.status, "sha256": sha(a.path), "registered_at": now()}
    d["pages"] = [x for x in d["pages"] if x.get("page_id") != a.page_id] + [item]
    batch = next((x for x in d["batches"] if x.get("id") == a.batch_id), None)
    if not batch:
        d["batches"].append({"id": a.batch_id, "pages": [a.page_id], "status": "in_progress"})
    elif a.page_id not in batch["pages"]:
        batch["pages"].append(a.page_id)
    d["updated_at"] = now(); save(a.state, d); print(json.dumps(item, ensure_ascii=False, indent=2))


def cmd_lock_anchor(a):
    d = load(a.state)
    ids = {x.get('page_id') for x in d['pages']}
    if a.page_id not in ids: raise SystemExit(f'page not registered: {a.page_id}')
    if a.page_id not in d['anchors']: d['anchors'].append(a.page_id)
    d['phase'] = 'anchors_locked'; d['updated_at'] = now(); save(a.state, d); print(a.page_id)


# ---------------------------------------------------------------- 批次计划
PLAN_ROLES = [
    ("cover", "cover"), ("principle", "principle"), ("parameter_table", "parameter_table"),
    ("module_main", "module"), ("module_drive", "module"), ("user_scene", "user_scene"),
    ("user_scene_2", "user_scene"), ("cmf", "cmf"), ("curve", "curve"),
    ("qa", "qa"), ("closure", "closure"), ("principle_2", "principle"),
]


def build_plan(minimum_pages):
    """生成 >=max(minimum_pages,10) 页的批次计划，每 4 页一批。"""
    n = max(minimum_pages, 10)
    entries = [{"page_id": pid, "role": role} for pid, role in PLAN_ROLES]
    i = 0
    while len(entries) < n:
        if i % 2 == 0:
            entries.append({"page_id": f"module_extra_{i}", "role": "module"})
        else:
            entries.append({"page_id": f"user_scene_extra_{i}", "role": "user_scene"})
        i += 1
    for idx, e in enumerate(entries):
        e["page_number"] = idx + 1
        e["batch_id"] = f"batch_{idx // 4 + 1}"
    return entries


def cmd_plan_batches(a):
    d = load(a.state)
    plan = build_plan(a.minimum_pages)
    d["batch_plan"] = plan
    d["minimum_pages"] = a.minimum_pages
    if not any(x.get('purpose') == 'plan' for x in d.get('prompts', [])):
        d["prompts"].append({"id": "plan-default", "purpose": "plan",
                             "instruction": f"plan a manual with >= {a.minimum_pages} pages",
                             "inputs": [], "outputs": ["plan"], "status": "completed", "created_at": now()})
    d["updated_at"] = now(); save(a.state, d)
    ids = sorted({e['batch_id'] for e in plan})
    print(json.dumps({"page_count": len(plan), "batches": ids},
                     ensure_ascii=False, indent=2))


# ---------------------------------------------------------------- 批次执行
PARAM_LABELS = {"peak_torque": "峰值扭矩", "weight": "整机重量", "battery_capacity": "电池容量",
                "max_speed": "最大速度", "input_voltage": "输入电压", "max_load": "最大载荷"}
PARAM_UNITS = {"peak_torque": "N·m", "weight": "kg", "battery_capacity": "Wh",
               "max_speed": "km/h", "input_voltage": "V", "max_load": "kg"}


def _collect_prior(pdir):
    if not pdir: return None
    p = Path(pdir)
    if not p.exists() or not p.is_dir(): return None
    out = []
    for f in sorted(list(p.glob("*.png")) + list(p.glob("*.jpg")) + list(p.glob("*.jpeg"))):
        out.append({"path": str(f), "sha256": sha(f)})
    return {"dir": str(p), "attachments": out}


def _collect_visual_bible(vdir):
    if not vdir: return None
    p = Path(vdir)
    if p.is_file():
        return json.loads(p.read_text(encoding='utf-8'))
    if p.is_dir():
        return {"dir": str(p), "files": [str(f) for f in sorted(p.rglob("*")) if f.is_file()]}
    return None


def _build_defn(entry, facts):
    role = entry["role"]; pid = entry["page_id"]; pn = entry["page_number"]
    params = ((facts or {}).get("params", {}) if facts else {}) or {}
    defn = {"page_id": pid, "role": role, "title": "", "body": [], "caption": "",
            "param_table": [], "curve": None, "page_number": pn,
            "footer": "AIPD-OS 产品手册", "rendered_by_us": True,
            "expected_character": "工业级外骨骼助力产品，工程橙与金属灰",
            "expected_cmf": {"color": "金属灰/工程橙", "material": "铝合金6061", "finish": "阳极氧化"}}
    if role == "cover":
        defn["title"] = "外骨骼助力系统 产品手册"
        defn["body"] = ["本手册涵盖工作原理、技术参数、核心模块、用户场景、CMF 设计、性能曲线与常见问题。"]
        defn["caption"] = "封面说明"
    elif role == "principle":
        defn["title"] = "工作原理"
        defn["body"] = ["系统通过电机驱动谐波减速器，将助力传递至外骨骼关节，实现重物搬运时的主动助力。",
                        "控制单元实时采集关节力矩，结合人体运动意图输出补偿力矩。"]
    elif role == "parameter_table":
        defn["title"] = "技术参数表"
        defn["param_table"] = [{"param": k, "label": PARAM_LABELS.get(k, k), "value": v,
                                "unit": PARAM_UNITS.get(k, "")} for k, v in params.items()]
    elif role == "module":
        defn["title"] = "核心模块"
        defn["body"] = ["动力模块：高密度无刷电机与谐波减速器。",
                        "控制模块：力矩感知与运动意图识别。",
                        "供电模块：高容量锂电池组。"]
    elif role == "user_scene":
        defn["title"] = "用户场景"
        defn["body"] = ["物流搬运：仓库装卸环节有效缓解腰部劳损。",
                        "制造车间：产线搬运与装配作业。",
                        "应急救援：长时间负重行进场景。"]
    elif role == "cmf":
        defn["title"] = "CMF 设计"
        defn["body"] = ["色彩：工程橙强调识别度，金属灰体现专业质感。",
                        "材质：铝合金6061 保证强度与轻量化。",
                        "表面处理：阳极氧化提升耐磨与耐腐蚀。"]
    elif role == "curve":
        defn["title"] = "性能曲线"
        defn["body"] = ["下图展示不同负载下的助力效率与输出扭矩曲线。"]
        defn["caption"] = "图 2：负载-效率曲线"
        defn["curve"] = [{"label": "效率曲线", "points": [[0, 10], [1, 20], [2, 18], [3, 30], [4, 40], [5, 38]]},
                         {"label": "输出扭矩", "points": [[0, 5], [1, 12], [2, 20], [3, 28], [4, 40], [5, 46]]}]
    elif role == "qa":
        defn["title"] = "常见问题"
        defn["body"] = ["Q：电池续航多久？A：依据负载与工况约 4-6 小时。",
                        "Q：如何保养？A：定期清洁并检查连接件转矩。"]
    elif role == "closure":
        defn["title"] = "结语"
        defn["body"] = ["本产品致力于降低重体力作业风险，提升作业效率与职业健康水平。",
                        "更多详情请联系技术支持。"]
    if not defn["title"]: defn["title"] = pid
    if not defn["body"]: defn["body"] = ["本节内容。"]
    return defn


def cmd_run_batch(a):
    # 真实执行链：图像适配器 + 排版渲染器（惰性导入，避免影响纯状态命令）
    from aipd_os.imggen.adapter import ImageGenAdapter
    from aipd_os.layout.renderer import render_page

    d = load(a.state)
    plan = d.get("batch_plan", [])
    batch_pages = [e for e in plan if e.get("batch_id") == a.batch_id]
    if not batch_pages:
        raise SystemExit(f"no planned pages for batch {a.batch_id}")

    anchors = [x.strip() for x in (a.anchors or "").split(",") if x.strip()]
    prior = _collect_prior(a.prior_batch)
    visual_bible = _collect_visual_bible(a.visual_bible) if a.visual_bible else None
    prohibited = json.loads(Path(a.prohibited).read_text(encoding='utf-8')) if a.prohibited else []
    facts = json.loads(Path(a.facts).read_text(encoding='utf-8')) if getattr(a, 'facts', None) else {}

    adapter = ImageGenAdapter()
    out_dir = Path(a.output_dir); out_dir.mkdir(parents=True, exist_ok=True)
    ext_dir = out_dir / "external_tasks"; ext_dir.mkdir(parents=True, exist_ok=True)
    figures_dir = out_dir / "figures"
    pages_out = out_dir / "pages"; pages_out.mkdir(parents=True, exist_ok=True)

    output_pages = []; completed = []; external = []
    for entry in batch_pages:
        defn = _build_defn(entry, facts)
        image_prompt = f"{defn['title']} 产品配图，中文产品手册插图"
        fig_path = figures_dir / f"{entry['page_id']}.png"
        status = "external_pending"; sha256 = None; page_png = None
        if adapter.available():
            try:
                adapter.generate(image_prompt, (1024, 1024), str(fig_path))
                page_png = pages_out / f"{entry['page_id']}.png"
                render_page(defn, str(page_png))
                status = "completed"; sha256 = sha(page_png); completed.append(entry['page_id'])
            except Exception:
                status = "external_pending"
        if status == "external_pending":
            # 诚实：不假装生成，写出外部执行任务包（图 + 整页）
            adapter.write_external_task_package(image_prompt, (1024, 1024), str(fig_path))
            full_pkg = {"job_type": "page_render", "status": "external_pending",
                        "page_id": entry['page_id'], "role": entry['role'], "defn": defn,
                        "expected_path": str(pages_out / f"{entry['page_id']}.png"),
                        "figure_external_task": str(fig_path.with_suffix(fig_path.suffix + '.task.json'))}
            (ext_dir / f"{entry['page_id']}.task.json").write_text(
                json.dumps(full_pkg, ensure_ascii=False, indent=2), encoding='utf-8')
            external.append(entry['page_id'])
        rec = {"page_id": entry['page_id'], "role": entry['role'], "defn": defn,
               "path": str(pages_out / f"{entry['page_id']}.png"),
               "sha256": sha256, "status": status}
        output_pages.append(rec)
        d["pages"] = [x for x in d.get('pages', []) if x.get('page_id') != entry['page_id']] + [
            {"page_id": entry['page_id'], "role": entry['role'], "path": rec["path"],
             "batch_id": a.batch_id, "depends_on": anchors, "facts_version": a.truth_version,
             "status": status, "sha256": sha256, "registered_at": now()}]

    batch_run = {"batch_id": a.batch_id, "prompt": a.prompt, "theory_version": a.theory_version,
                 "truth_version": a.truth_version, "anchors": anchors, "prior_batch": prior,
                 "visual_bible": visual_bible, "prohibited": prohibited, "facts": facts,
                 "output_pages": output_pages,  # 含 defn，供视觉语义审计重建
                 "external_pending": external, "completed": completed, "executed_at": now()}
    d["batch_runs"] = d.get("batch_runs", []) + [batch_run]
    d["truth_version"] = a.truth_version
    b = next((x for x in d.get('batches', []) if x.get('id') == a.batch_id), None)
    if not b:
        d.setdefault('batches', []).append({"id": a.batch_id,
                                            "pages": [op['page_id'] for op in output_pages],
                                            "status": status})
    else:
        b["status"] = status
    d["updated_at"] = now(); save(a.state, d)
    print(json.dumps({"batch_id": a.batch_id, "planned": len(batch_pages),
                      "completed": completed, "external_pending": external,
                      "external_task_dir": str(ext_dir), "context_saved": True},
                     ensure_ascii=False, indent=2))


# ---------------------------------------------------------------- 校验
def _batch_continuity_ok(d):
    brs = d.get('batch_runs', [])
    if len(brs) <= 1: return True
    return all(br.get('prior_batch') for br in brs[1:])


def validate(d):
    errors = []; warnings = []
    prompt_ids = [x.get('id') for x in d.get('prompts', [])]
    if len(prompt_ids) != len(set(prompt_ids)): errors.append('duplicate prompt id')
    page_ids = [x.get('page_id') for x in d.get('pages', [])]
    if len(page_ids) != len(set(page_ids)): errors.append('duplicate page id')
    known = set(page_ids)
    for a in d.get('anchors', []):
        if a not in known: errors.append(f'anchor page not registered: {a}')
    paths = {str(x.get('path')) for x in d.get('pages', []) if x.get('path')}
    for p in d.get('pages', []):
        for dep in p.get('depends_on', []):
            if dep not in known and dep not in paths:
                warnings.append(f"page {p.get('page_id')} dependency not registered: {dep}")
    purposes = {x.get('purpose') for x in d.get('prompts', [])}
    if 'plan' not in purposes: errors.append('planning prompt missing')
    if d.get('phase') in {'anchors_locked', 'extension', 'manual_complete', 'design_intent_frozen'} and not d.get('anchors'):
        errors.append('anchors required for current phase')
    if d.get('phase') in {'manual_complete', 'design_intent_frozen'} and len(d.get('pages', [])) < int(d.get('minimum_pages', 1)):
        errors.append('page count below minimum')
    registered_paths = {x.get('path') for x in d.get('pages', []) if x.get('path')}
    anchor_paths = {x.get('path') for x in d.get('pages', []) if x.get('page_id') in set(d.get('anchors', []))}
    for p in d.get('prompts', []):
        if p.get('purpose') in {'extension_batch', 'extend', 'extension'}:
            if not set(p.get('inputs', [])) & (registered_paths | anchor_paths):
                errors.append(f"extension prompt {p.get('id')} does not include prior page attachment")
    # 批次连续性：非首批需携带上一批附件
    if d.get('batch_runs') and not _batch_continuity_ok(d):
        errors.append('batch continuity broken: a non-first batch lacks prior_batch attachments')
    return {"passed": not errors, "errors": errors, "warnings": warnings,
            "page_count": len(page_ids), "anchor_count": len(d.get('anchors', [])),
            "prompt_count": len(prompt_ids), "phase": d.get('phase'),
            "batch_count": len(d.get('batch_runs', [])), "batch_continuity_ok": _batch_continuity_ok(d)}


def cmd_validate(a):
    r = validate(load(a.state))
    if a.json_out: save(a.json_out, r)
    print(json.dumps(r, ensure_ascii=False, indent=2)); raise SystemExit(0 if r['passed'] else 2)


def cmd_status(a):
    d = load(a.state); r = validate(d); r['project_id'] = d.get('project_id')
    r['next_action'] = ('plan' if not d.get('prompts') else
                        ('generate_anchors' if not d.get('anchors') else
                         ('extend_batches' if len(d.get('pages', [])) < d.get('minimum_pages', 10)
                          else 'assemble_and_freeze_design_intent')))
    print(json.dumps(r, ensure_ascii=False, indent=2))


def main():
    ap = argparse.ArgumentParser(); sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('init'); p.add_argument('--state', required=True)
    p.add_argument('--project-id', required=True); p.add_argument('--minimum-pages', type=int, default=10)
    p.set_defaults(f=cmd_init)
    p = sub.add_parser('add-prompt'); p.add_argument('--state', required=True)
    p.add_argument('--prompt-id', required=True); p.add_argument('--purpose', required=True)
    p.add_argument('--instruction', required=True); p.add_argument('--input', action='append')
    p.add_argument('--output', action='append'); p.add_argument('--status', default='completed')
    p.set_defaults(f=cmd_add_prompt)
    p = sub.add_parser('register-page'); p.add_argument('--state', required=True)
    p.add_argument('--page-id', required=True); p.add_argument('--role', required=True)
    p.add_argument('--path', required=True); p.add_argument('--batch-id', required=True)
    p.add_argument('--depends-on', action='append'); p.add_argument('--facts-version')
    p.add_argument('--status', default='completed'); p.set_defaults(f=cmd_register_page)
    p = sub.add_parser('lock-anchor'); p.add_argument('--state', required=True)
    p.add_argument('--page-id', required=True); p.set_defaults(f=cmd_lock_anchor)
    p = sub.add_parser('validate'); p.add_argument('--state', required=True); p.add_argument('--json-out')
    p.set_defaults(f=cmd_validate)
    p = sub.add_parser('status'); p.add_argument('--state', required=True); p.set_defaults(f=cmd_status)
    p = sub.add_parser('plan-batches'); p.add_argument('--state', required=True)
    p.add_argument('--minimum-pages', type=int, default=10); p.set_defaults(f=cmd_plan_batches)
    p = sub.add_parser('run-batch'); p.add_argument('--state', required=True)
    p.add_argument('--batch-id', required=True); p.add_argument('--prompt', required=True)
    p.add_argument('--theory-version', required=True); p.add_argument('--truth-version', required=True)
    p.add_argument('--anchors', required=True); p.add_argument('--prior-batch')
    p.add_argument('--output-dir', required=True); p.add_argument('--visual-bible')
    p.add_argument('--prohibited'); p.add_argument('--facts'); p.set_defaults(f=cmd_run_batch)
    a = ap.parse_args(); a.f(a)


if __name__ == '__main__':
    main()
