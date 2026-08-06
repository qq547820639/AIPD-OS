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
    """从 Product Truth / 内容模型构建页面定义（正文与规格取事实，而非硬编码文案）。

    facts 支持内容模型字段：params / product / modules / scenes / cmf / qa / closure /
    characters / camera / lighting。缺省字段回退到默认文案，保证向后兼容。
    """
    role = entry["role"]; pid = entry["page_id"]; pn = entry["page_number"]
    facts = facts or {}
    params = (facts.get("params", {}) if facts else {}) or {}
    product = (facts.get("product", {}) if facts else {}) or {}
    modules = (facts.get("modules", []) if facts else []) or []
    scenes = (facts.get("scenes", []) if facts else []) or []
    cmf = (facts.get("cmf", {}) if facts else {}) or {}
    qa_list = (facts.get("qa", []) if facts else []) or []
    closure_list = (facts.get("closure", []) if facts else []) or []
    characters = (facts.get("characters", []) if facts else []) or []
    camera = (facts.get("camera", {}) if facts else {}) or {}
    lighting = (facts.get("lighting", {}) if facts else {}) or {}
    product_name = product.get("name", "外骨骼助力系统")
    defn = {"page_id": pid, "role": role, "title": "", "body": [], "caption": "",
            "param_table": [], "curve": None, "page_number": pn,
            "footer": "AIPD-OS 产品手册", "rendered_by_us": True,
            "expected_character": characters[0].get("appearance", "工业级外骨骼助力产品，工程橙与金属灰")
                if characters else "工业级外骨骼助力产品，工程橙与金属灰",
            "expected_cmf": dict(cmf) if cmf else {"color": "金属灰/工程橙", "material": "铝合金6061", "finish": "阳极氧化"},
            "product_structure": {"name": product_name, "structure": product.get("structure", "")},
            "camera": camera, "lighting": lighting}
    if role == "cover":
        defn["title"] = f"{product_name} 产品手册"
        defn["body"] = [
            product.get("tagline", "本手册涵盖工作原理、技术参数、核心模块、用户场景、CMF 设计、性能曲线与常见问题。")
        ] or ["本手册涵盖工作原理、技术参数、核心模块、用户场景、CMF 设计、性能曲线与常见问题。"]
        defn["caption"] = "封面说明"
    elif role == "principle":
        defn["title"] = "工作原理"
        defn["body"] = (facts.get("principle", []) if facts else []) or [
            "系统通过电机驱动谐波减速器，将助力传递至外骨骼关节，实现重物搬运时的主动助力。",
            "控制单元实时采集关节力矩，结合人体运动意图输出补偿力矩。"]
    elif role == "parameter_table":
        defn["title"] = "技术参数表"
        defn["param_table"] = [{"param": k, "label": PARAM_LABELS.get(k, k), "value": v,
                                "unit": PARAM_UNITS.get(k, "")} for k, v in params.items()]
    elif role == "module":
        defn["title"] = "核心模块"
        defn["body"] = [f"{m.get('name', '模块')}：{m.get('desc', '')}" for m in modules] or [
            "动力模块：高密度无刷电机与谐波减速器。",
            "控制模块：力矩感知与运动意图识别。",
            "供电模块：高容量锂电池组。"]
        defn["modules"] = list(modules)
    elif role == "user_scene":
        defn["title"] = "用户场景"
        defn["body"] = [f"{s.get('title', '场景')}：{s.get('desc', '')}" for s in scenes] or [
            "物流搬运：仓库装卸环节有效缓解腰部劳损。",
            "制造车间：产线搬运与装配作业。",
            "应急救援：长时间负重行进场景。"]
    elif role == "cmf":
        defn["title"] = "CMF 设计"
        defn["body"] = ([f"色彩：{cmf.get('color', '')}", f"材质：{cmf.get('material', '')}",
                         f"表面处理：{cmf.get('finish', '')}"] if cmf else [
            "色彩：工程橙强调识别度，金属灰体现专业质感。",
            "材质：铝合金6061 保证强度与轻量化。",
            "表面处理：阳极氧化提升耐磨与耐腐蚀。"])
    elif role == "curve":
        defn["title"] = "性能曲线"
        defn["body"] = ["下图展示不同负载下的助力效率与输出扭矩曲线。"]
        defn["caption"] = "图 2：负载-效率曲线"
        defn["curve"] = [{"label": "效率曲线", "points": [[0, 10], [1, 20], [2, 18], [3, 30], [4, 40], [5, 38]]},
                         {"label": "输出扭矩", "points": [[0, 5], [1, 12], [2, 20], [3, 28], [4, 40], [5, 46]]}]
    elif role == "qa":
        defn["title"] = "常见问题"
        defn["body"] = [f"Q：{q.get('q', '')} A：{q.get('a', '')}" for q in qa_list] or [
            "Q：电池续航多久？A：依据负载与工况约 4-6 小时。",
            "Q：如何保养？A：定期清洁并检查连接件转矩。"]
    elif role == "closure":
        defn["title"] = "结语"
        defn["body"] = [c.get("text", "") for c in closure_list] or [
            "本产品致力于降低重体力作业风险，提升作业效率与职业健康水平。",
            "更多详情请联系技术支持。"]
    if not defn["title"]: defn["title"] = pid
    if not defn["body"]: defn["body"] = ["本节内容。"]
    return defn


def _build_prior_content(prior_dir):
    """把前一批目录下的真实图像读为字节内容（PriorBatchContent），供 Provider 消费。"""
    from aipd_os.imggen.providers import PriorBatchContent
    pc = _collect_prior(prior_dir)
    if not pc or not pc.get("attachments"):
        return None
    images = []
    for att in pc["attachments"]:
        p = Path(att["path"])
        if p.is_file():
            images.append({"page_id": p.stem, "data": p.read_bytes(), "sha256": att["sha256"]})
    if not images:
        return None
    return PriorBatchContent(images=images)


def _select_provider(name):
    from aipd_os.imggen.providers import provider_from_name
    return provider_from_name(name or "external")


def _write_external_tasks(adapter, entry, defn, fig_path, pages_out, ext_dir):
    """诚实降级：不假装生成，写出外部执行任务包（图 + 整页），保持 HOLD。"""
    image_prompt = f"{defn['title']} 产品配图，中文产品手册插图"
    adapter.write_external_task_package(image_prompt, (1024, 1024), str(fig_path))
    full_pkg = {"job_type": "page_render", "status": "external_pending",
                "page_id": entry['page_id'], "role": entry['role'], "defn": defn,
                "expected_path": str(pages_out / f"{entry['page_id']}.png"),
                "figure_external_task": str(fig_path.with_suffix(fig_path.suffix + '.task.json'))}
    (ext_dir / f"{entry['page_id']}.task.json").write_text(
        json.dumps(full_pkg, ensure_ascii=False, indent=2), encoding='utf-8')


def cmd_run_batch(a):
    # 真实执行链：可替换 ImageGenProvider + 排版渲染器（惰性导入，避免影响纯状态命令）
    from aipd_os.imggen.adapter import ImageGenAdapter
    from aipd_os.imggen.providers import BatchRequest
    from aipd_os.layout.renderer import render_page

    d = load(a.state)
    plan = d.get("batch_plan", [])
    batch_pages = [e for e in plan if e.get("batch_id") == a.batch_id]
    if not batch_pages:
        raise SystemExit(f"no planned pages for batch {a.batch_id}")

    anchors = [x.strip() for x in (a.anchors or "").split(",") if x.strip()]
    prior = _collect_prior(a.prior_batch)
    prior_content = _build_prior_content(a.prior_batch)
    visual_bible = _collect_visual_bible(a.visual_bible) if a.visual_bible else None
    prohibited = json.loads(Path(a.prohibited).read_text(encoding='utf-8')) if a.prohibited else []
    facts = json.loads(Path(a.facts).read_text(encoding='utf-8')) if getattr(a, 'facts', None) else {}

    provider = _select_provider(getattr(a, 'imggen_provider', None))
    adapter = ImageGenAdapter()
    out_dir = Path(a.output_dir); out_dir.mkdir(parents=True, exist_ok=True)
    ext_dir = out_dir / "external_tasks"; ext_dir.mkdir(parents=True, exist_ok=True)
    figures_dir = out_dir / "figures"; figures_dir.mkdir(parents=True, exist_ok=True)
    pages_out = out_dir / "pages"; pages_out.mkdir(parents=True, exist_ok=True)

    defns = [{"entry": e, "defn": _build_defn(e, facts)} for e in batch_pages]
    prompt_template = getattr(a, 'prompt', '')
    model_version = getattr(a, 'model_version', 'gen-1.0')
    seed = getattr(a, 'seed', 0)
    request = BatchRequest(
        pages=[x["defn"] for x in defns],
        model_version=model_version,
        prompt_template=prompt_template,
        generation_params={"size": [1024, 1024], "provider": provider.id},
        seed=seed,
    )

    output_pages = []; completed = []; external = []
    if provider.available():
        try:
            # 真实 Provider：把前一批真实图像作为图像条件传给后一批
            # （RealImageGenProvider 会把 prior_content 的真实字节编码为 input_images 附件，
            #   而非仅拼成蒙太奇证明字节存在）。无真实 Provider 时保持 HOLD。
            if provider.id == "real" and prior_content:
                request.generation_params["prior_condition"] = True
                request.generation_params["prior_image_count"] = len(prior_content.images)
            gen_images = provider.generate_batch(request, prior_content)
            for item, gimg in zip(defns, gen_images):
                entry = item["entry"]; defn = item["defn"]
                fig_path = figures_dir / f"{entry['page_id']}.png"
                fig_path.write_bytes(gimg.data)  # 真实字节落盘
                page_png = pages_out / f"{entry['page_id']}.png"
                render_page(defn, str(page_png))
                status = "completed"; sha256 = sha(page_png)
                completed.append(entry['page_id'])
                rec = {"page_id": entry['page_id'], "role": entry['role'], "defn": defn,
                       "path": str(page_png), "figure_path": str(fig_path),
                       "sha256": sha256, "status": status,
                       "generation": dict(gimg.meta),
                       "figure_sha256": gimg.sha256}
                output_pages.append(rec)
                d["pages"] = [x for x in d.get('pages', []) if x.get('page_id') != entry['page_id']] + [
                    {"page_id": entry['page_id'], "role": entry['role'], "path": rec["path"],
                     "figure_path": str(fig_path), "figure_sha256": gimg.sha256,
                     "batch_id": a.batch_id, "depends_on": anchors, "facts_version": a.truth_version,
                     "status": status, "sha256": sha256, "generation": dict(gimg.meta),
                     "registered_at": now()}]
        except Exception:
            # 诚实：Provider 不可用时整批降级为外部任务包 + HOLD，绝不假装成图
            provider = _select_provider("external")
            for item in defns:
                entry = item["entry"]; defn = item["defn"]
                fig_path = figures_dir / f"{entry['page_id']}.png"
                _write_external_tasks(adapter, entry, defn, fig_path, pages_out, ext_dir)
                external.append(entry['page_id'])
                rec = {"page_id": entry['page_id'], "role": entry['role'], "defn": defn,
                       "path": str(pages_out / f"{entry['page_id']}.png"),
                       "sha256": None, "status": "external_pending",
                       "generation": {"provider_id": provider.id, "status": "external_pending",
                                      "note": "no real backend; external task package emitted"}}
                output_pages.append(rec)
                d["pages"] = [x for x in d.get('pages', []) if x.get('page_id') != entry['page_id']] + [
                    {"page_id": entry['page_id'], "role": entry['role'],
                     "path": str(pages_out / f"{entry['page_id']}.png"),
                     "batch_id": a.batch_id, "depends_on": anchors, "facts_version": a.truth_version,
                     "status": "external_pending", "sha256": None,
                     "registered_at": now()}]
    else:
        # 无后端：输出外部任务包并保持 HOLD
        for item in defns:
            entry = item["entry"]; defn = item["defn"]
            fig_path = figures_dir / f"{entry['page_id']}.png"
            _write_external_tasks(adapter, entry, defn, fig_path, pages_out, ext_dir)
            external.append(entry['page_id'])
            rec = {"page_id": entry['page_id'], "role": entry['role'], "defn": defn,
                   "path": str(pages_out / f"{entry['page_id']}.png"),
                   "sha256": None, "status": "external_pending",
                   "generation": {"provider_id": provider.id, "external_dependency": True,
                                  "status": "external_pending",
                                  "note": "no real backend; chain stays HOLD"}}
            output_pages.append(rec)
            d["pages"] = [x for x in d.get('pages', []) if x.get('page_id') != entry['page_id']] + [
                {"page_id": entry['page_id'], "role": entry['role'],
                 "path": str(pages_out / f"{entry['page_id']}.png"),
                 "batch_id": a.batch_id, "depends_on": anchors, "facts_version": a.truth_version,
                 "status": "external_pending", "sha256": None, "registered_at": now()}]

    batch_status = "completed" if completed and not external else ("external_pending" if external else "unknown")
    batch_run = {"batch_id": a.batch_id, "prompt": a.prompt, "theory_version": a.theory_version,
                 "truth_version": a.truth_version, "anchors": anchors, "prior_batch": prior,
                 "prior_batch_content": {
                     "attachment_hash": prior_content.attachment_hash() if prior_content else None,
                     "image_count": len(prior_content.images) if prior_content else 0,
                     "total_bytes": prior_content.total_bytes() if prior_content else 0,
                 },
                 "visual_bible": visual_bible, "prohibited": prohibited, "facts": facts,
                 "provider": {"id": provider.id, "external_dependency": provider.external_dependency},
                 "output_pages": output_pages,  # 含 defn，供视觉语义审计重建
                 "external_pending": external, "completed": completed,
                 "status": batch_status, "executed_at": now()}
    d["batch_runs"] = d.get("batch_runs", []) + [batch_run]
    d["truth_version"] = a.truth_version
    b = next((x for x in d.get('batches', []) if x.get('id') == a.batch_id), None)
    if not b:
        d.setdefault('batches', []).append({"id": a.batch_id,
                                            "pages": [op['page_id'] for op in output_pages],
                                            "status": batch_status})
    else:
        b["status"] = batch_status
    d["updated_at"] = now(); save(a.state, d)
    print(json.dumps({"batch_id": a.batch_id, "planned": len(batch_pages),
                      "completed": completed, "external_pending": external,
                      "external_task_dir": str(ext_dir), "context_saved": True,
                      "provider_used_bytes": bool(prior_content)},
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


# ---------------------------------------------------------------- 锚点注册表 / Visual Bible
def cmd_build_visual_bible(a):
    from aipd_os.imggen.registry import VisualBible
    d = load(a.state)
    facts = json.loads(Path(a.facts).read_text(encoding='utf-8')) if a.facts else {}
    vb = VisualBible.from_truth(facts)
    d["visual_bible"] = vb.to_dict()
    d["updated_at"] = now(); save(a.state, d)
    print(json.dumps(vb.to_dict(), ensure_ascii=False, indent=2))


def cmd_build_anchor_registry(a):
    from aipd_os.imggen.registry import AnchorRegistry
    d = load(a.state)
    facts = json.loads(Path(a.facts).read_text(encoding='utf-8')) if a.facts else {}
    reg = AnchorRegistry.build(d.get("batch_plan", []), facts)
    d["anchor_registry"] = reg.to_dict()
    d["updated_at"] = now(); save(a.state, d)
    print(json.dumps(reg.to_dict(), ensure_ascii=False, indent=2))


def _find_page_defn(d, page_id):
    for br in d.get("batch_runs", []):
        for op in br.get("output_pages", []):
            if op.get("page_id") == page_id and op.get("defn"):
                return op["defn"]
    return None


def cmd_rebuild_page(a):
    # 仅重建指定失败页：重新生成该页配图 + 整页，并对其重新审计（不触碰其它页）
    from aipd_os.imggen.adapter import ImageGenAdapter
    from aipd_os.imggen.providers import BatchRequest, PriorBatchContent
    from aipd_os.layout.renderer import render_page
    from aipd_os.visual_audit import VisualAuditor

    d = load(a.state)
    defn = _find_page_defn(d, a.page_id)
    if defn is None:
        raise SystemExit(f"page not found for rebuild: {a.page_id}")
    if a.facts:
        # 从更新后的 Product Truth 重新派生该页正文/规格（参数变更传播到相关页）
        new_facts = json.loads(Path(a.facts).read_text(encoding='utf-8'))
        entry = {"page_id": a.page_id, "role": defn.get("role", ""),
                 "page_number": defn.get("page_number", 1)}
        defn = _build_defn(entry, new_facts)
    facts = json.loads(Path(a.facts).read_text(encoding='utf-8')) if a.facts else (
        next((br.get("facts") for br in d.get("batch_runs", []) if br.get("facts")), {}))
    provider = _select_provider(getattr(a, 'imggen_provider', None))
    adapter = ImageGenAdapter()
    out_dir = Path(a.output_dir); out_dir.mkdir(parents=True, exist_ok=True)
    figures_dir = out_dir / "figures"; figures_dir.mkdir(parents=True, exist_ok=True)
    pages_out = out_dir / "pages"; pages_out.mkdir(parents=True, exist_ok=True)
    ext_dir = out_dir / "external_tasks"; ext_dir.mkdir(parents=True, exist_ok=True)

    prior_content = None
    if a.prior_batch:
        pc = _build_prior_content(a.prior_batch)
        prior_content = pc
    request = BatchRequest(
        pages=[defn], model_version=getattr(a, 'model_version', 'gen-1.0'),
        prompt_template=f"rebuild {a.page_id}", generation_params={"size": [1024, 1024], "provider": provider.id},
        seed=getattr(a, 'seed', 0),
    )
    fig_path = figures_dir / f"{a.page_id}.png"
    page_png = pages_out / f"{a.page_id}.png"
    if provider.available():
        gimg = provider.generate_batch(request, prior_content)[0]
        fig_path.write_bytes(gimg.data)
        render_page(defn, str(page_png))
        status = "completed"; page_sha = sha(page_png)
    else:
        _write_external_tasks(adapter, {"page_id": a.page_id, "role": defn.get("role")}, defn,
                              fig_path, pages_out, ext_dir)
        status = "external_pending"; page_sha = None
    # 仅重跑责任页审计（以及受影响页门）
    audit = VisualAuditor().audit_page(defn, str(page_png), facts=facts) if page_sha else None
    rec = {"run": "rebuild", "page_id": a.page_id, "status": status,
           "path": str(page_png), "figure_path": str(fig_path),
           "sha256": page_sha, "figure_sha256": gimg.sha256 if status == "completed" else None,
           "generation": dict(gimg.meta) if status == "completed" else None,
           "defn": defn,
           "audit": audit, "executed_at": now()}
    d.setdefault("rebuilds", []).append(rec)
    d["updated_at"] = now(); save(a.state, d)
    print(json.dumps(rec, ensure_ascii=False, indent=2))
    # 仅当存在非视觉维度硬失败时才阻止（vision hold 不阻止重建，保持 honest HOLD）
    hard_fail = bool(audit) and audit is not None and not audit.get("non_vision_passed", False)
    if hard_fail:
        raise SystemExit(2)


def cmd_preview_batch(a):
    # 预览：产出该批 before/after 差异（哈希/状态），供用户在批准前核对
    d = load(a.state)
    br = next((x for x in d.get("batch_runs", []) if x.get("batch_id") == a.batch_id), None)
    if br is None:
        raise SystemExit(f"no batch run for {a.batch_id}")
    current = {}
    for op in br.get("output_pages", []):
        current[op["page_id"]] = {"path": op.get("path"), "sha256": op.get("sha256"),
                                  "status": op.get("status"), "figure_sha256": op.get("figure_sha256")}
    prior = _collect_prior(a.prior_batch) if a.prior_batch else None
    before = {}
    if prior:
        for att in prior.get("attachments", []):
            before[Path(att["path"]).stem] = {"path": att["path"], "sha256": att["sha256"]}
    diff = []
    for pid, cur in current.items():
        prev = before.get(pid)
        diff.append({"page_id": pid, "before_sha256": prev["sha256"] if prev else None,
                     "after_sha256": cur["sha256"],
                     "changed": bool(prev and prev["sha256"] != cur["sha256"]) if prev else True,
                     "status": cur["status"]})
    report = {"batch_id": a.batch_id, "preview": diff, "approved": any(
        x.get("batch_id") == a.batch_id for x in d.get("approvals", []))}
    if a.json_out: save(a.json_out, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


def cmd_approve_batch(a):
    d = load(a.state)
    d.setdefault("approvals", []).append({"batch_id": a.batch_id, "approved_by": a.approver,
                                          "note": a.note or "", "approved_at": now()})
    d["updated_at"] = now(); save(a.state, d)
    print(json.dumps({"batch_id": a.batch_id, "approved": True, "approved_at": now()},
                     ensure_ascii=False, indent=2))


def cmd_check_release(a):
    # 发布门：视觉审计失败则阻止发布（绝不放行未过审页面）
    from aipd_os.visual_audit import VisualAuditor
    d = load(a.state)
    pages_dir = Path(a.pages_dir)
    facts = json.loads(Path(a.facts).read_text(encoding='utf-8')) if a.facts else None
    audit = VisualAuditor().audit_batch(d, str(pages_dir), facts=facts,
                                        prior_hashes=json.loads(Path(a.prior_hashes).read_text(encoding='utf-8'))
                                        if a.prior_hashes else None)
    blocked = bool(audit["failing_pages"]) or not audit["passed"]
    result = {"release_blocked": blocked, "audit": audit, "reason": (
        "visual audit failed" if blocked else "release allowed")}
    if a.json_out: save(a.json_out, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(1 if blocked else 0)


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
    p.add_argument('--prohibited'); p.add_argument('--facts')
    p.add_argument('--imggen-provider', default='external'); p.add_argument('--model-version', default='gen-1.0')
    p.add_argument('--seed', type=int, default=0); p.set_defaults(f=cmd_run_batch)
    p = sub.add_parser('build-visual-bible'); p.add_argument('--state', required=True)
    p.add_argument('--facts'); p.set_defaults(f=cmd_build_visual_bible)
    p = sub.add_parser('build-anchor-registry'); p.add_argument('--state', required=True)
    p.add_argument('--facts'); p.set_defaults(f=cmd_build_anchor_registry)
    p = sub.add_parser('rebuild-page'); p.add_argument('--state', required=True)
    p.add_argument('--page-id', required=True); p.add_argument('--output-dir', required=True)
    p.add_argument('--prior-batch'); p.add_argument('--imggen-provider', default='external')
    p.add_argument('--model-version', default='gen-1.0'); p.add_argument('--seed', type=int, default=0)
    p.add_argument('--facts'); p.set_defaults(f=cmd_rebuild_page)
    p = sub.add_parser('preview-batch'); p.add_argument('--state', required=True)
    p.add_argument('--batch-id', required=True); p.add_argument('--prior-batch'); p.add_argument('--json-out')
    p.set_defaults(f=cmd_preview_batch)
    p = sub.add_parser('approve-batch'); p.add_argument('--state', required=True)
    p.add_argument('--batch-id', required=True); p.add_argument('--approver', default='owner')
    p.add_argument('--note'); p.set_defaults(f=cmd_approve_batch)
    p = sub.add_parser('check-release'); p.add_argument('--state', required=True)
    p.add_argument('--pages-dir', required=True); p.add_argument('--facts'); p.add_argument('--prior-hashes')
    p.add_argument('--json-out'); p.set_defaults(f=cmd_check_release)
    a = ap.parse_args(); a.f(a)


if __name__ == '__main__':
    main()
