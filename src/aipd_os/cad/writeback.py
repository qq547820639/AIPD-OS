"""CAD 变更写回链：把 CAD 变更传播到下游产物。

当 CAD 参数/模型发生变更并生成新版本后，需要把该变更传播到下游产物
（规格 spec、BOM、手册 manual、验证计划 verification plan）：为每个受影响
下游产物推高修订号、写入 ``regeneration_needed`` 标记、记录来源 CAD 修订号，
并更新模型自身的参数与修订号。
"""
from __future__ import annotations

import re
from typing import Any

from aipd_os.cad.evidence import utc_now_iso

# 下游产物键（写回链可传播到的目标）。
DEFAULT_DOWNSTREAM = ['spec', 'bom', 'manual', 'verification_plan']

# 模型键与下游产物键的映射。
_MODEL_KEYS = ('model', 'cad_model')
_DOWNSTREAM_ALIASES = {
    'spec': ('spec', 'specification'),
    'bom': ('bom',),
    'manual': ('manual', 'user_manual'),
    'verification_plan': ('verification_plan', 'verification_plan_evidence'),
}


def _find_key(d: dict[str, Any], candidates) -> str | None:
    for k in candidates:
        if k in d:
            return k
    return None


def _revision_of(record: dict[str, Any]) -> str:
    for cand in ('revision', 'rev', 'version'):
        v = record.get(cand)
        if v:
            return str(v)
    return 'R1'


def _bump_revision(rev: str) -> str:
    """把修订号推高：R1->R2；末尾为数字时加一，否则追加 .1。"""
    m = re.match(r'^(.*?)(\d+)$', rev)
    if m:
        return m.group(1) + str(int(m.group(2)) + 1)
    return f'{rev}.1'


def propagate_cad_change(
    manifest: dict[str, Any],
    edits: dict[str, Any],
    downstream: list[str] | None = None,
    *,
    tool_version: str | None = None,
) -> dict[str, Any]:
    """把一次 CAD 参数变更传播到下游产物，返回更新后的 manifest 深拷贝。

    :param manifest: 工程清单，含模型记录 ``model`` 与下游产物记录
        （spec / bom / manual / verification_plan）。
    :param edits: 本次 CAD 参数变更 {参数名: 新值}。
    :param downstream: 需要传播的下游产物键；缺省为
        ``['spec','bom','manual','verification_plan']``。
    :param tool_version: 触发变更的 CAD 工具版本（写入证据）。
    :return: 更新后的 manifest；每个受影响下游产物修订号 +1、标记
        ``regeneration_needed`` 与来源 CAD 修订号。
    """
    import json
    out: dict[str, Any] = json.loads(json.dumps(manifest))

    model_key = _find_key(out, _MODEL_KEYS) or 'model'
    model = out.setdefault(model_key, {'revision': 'R1', 'parameters': {}})
    if not isinstance(model, dict):
        model = out[model_key] = {'revision': 'R1', 'parameters': {}}

    # 应用参数变更并推高模型修订号。
    params = dict(model.get('parameters') or {})
    params.update({k: v for k, v in edits.items()})
    model['parameters'] = params
    old_rev = _revision_of(model)
    new_rev = _bump_revision(old_rev)
    model['revision'] = new_rev
    model['last_change'] = {
        'edits': dict(edits),
        'timestamp': utc_now_iso(),
        'tool_version': tool_version,
    }

    # 传播到下游产物。
    targets = downstream or DEFAULT_DOWNSTREAM
    for name in targets:
        key = _find_key(out, _DOWNSTREAM_ALIASES.get(name, (name,)))
        if key is None:
            continue
        record = out[key]
        if isinstance(record, dict):
            record['revision'] = _bump_revision(_revision_of(record))
            record['regeneration_needed'] = True
            record['cad_source_revision'] = new_rev
            record['cad_change_timestamp'] = utc_now_iso()

    return out


__all__ = ['propagate_cad_change', 'DEFAULT_DOWNSTREAM', '_bump_revision']
