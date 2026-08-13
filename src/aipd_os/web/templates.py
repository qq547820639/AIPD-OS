"""Owner Web Console HTML 渲染。

只依赖标准库（``html``）。所有页面均为响应式 + 无障碍：
  - ``<meta name="viewport">`` 保证窄屏适配；
  - 语义标签（header/nav/main/section/footer）；
  - ``aria-label`` / ``tabindex`` / 可见焦点样式；
  - 键盘可操作（导航为真实链接，动作按钮带 ``tabindex``）。
数据一律来自 :class:`~aipd_os.web.views.WebConsole`，与 JSON API 共用同一业务服务。
"""
from __future__ import annotations

import html
from typing import Any

from .views import WebConsole

NAV_ITEMS = [
    ("/onboarding", "首次使用向导"),
    ("/overview", "项目总览"),
    ("/decisions", "决策中心"),
    ("/artifacts", "制品中心"),
    ("/run", "运行控制"),
    ("/external-wait", "外部等待中心"),
]

_CSS = """
:root{--bg:#f6f7f9;--card:#ffffff;--ink:#1a1d21;--muted:#6b7280;--line:#e5e7eb;
--accent:#2563eb;--ok:#16a34a;--warn:#d97706;--bad:#dc2626;}
*{box-sizing:border-box}
body{margin:0;font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;
background:var(--bg);color:var(--ink);line-height:1.6}
a{color:var(--accent);text-decoration:none}
header.top{background:#111827;color:#fff;padding:12px 20px}
header.top .brand{font-weight:700;font-size:18px}
nav{display:flex;flex-wrap:wrap;gap:4px;background:#1f2937;padding:6px 12px}
nav a{color:#d1d5db;padding:6px 10px;border-radius:6px}
nav a:hover,nav a[aria-current="page"]{background:#374151;color:#fff}
main{max-width:960px;margin:0 auto;padding:20px;display:flex;flex-direction:column;gap:16px}
section.card{background:var(--card);border:1px solid var(--line);border-radius:10px;
padding:16px;box-shadow:0 1px 2px rgba(0,0,0,.04)}
section.card h2{margin:0 0 8px;font-size:16px}
h1{font-size:22px;margin:0}
.muted{color:var(--muted);font-size:14px}
.badge{display:inline-block;padding:2px 8px;border-radius:999px;font-size:12px}
.badge.ok{background:#dcfce7;color:var(--ok)}
.badge.warn{background:#fef3c7;color:var(--warn)}
.badge.bad{background:#fee2e2;color:var(--bad)}
.badge.ext{background:#e0e7ff;color:var(--accent)}
ul{list-style:none;padding:0;margin:8px 0}
li{padding:4px 0;border-bottom:1px dashed var(--line)}
li:last-child{border-bottom:none}
button,.btn{display:inline-block;background:var(--accent);color:#fff;border:none;
border-radius:8px;padding:8px 14px;font-size:14px;cursor:pointer;margin:4px 4px 0 0}
button:focus-visible,.btn:focus-visible,a:focus-visible{outline:3px solid #93c5fd;
outline-offset:2px}
/* 可访问性：跳转链接聚焦时回到视口内（键盘用户可见、可操作） */
a.skip{position:absolute;left:-9999px;top:0}
a.skip:focus{left:8px;top:8px;background:#fff;color:var(--ink);z-index:100;
padding:8px 12px;border-radius:6px;outline:3px solid #93c5fd}
button.secondary{background:#374151}
button.danger{background:var(--bad)}
table{width:100%;border-collapse:collapse;font-size:14px}
th,td{text-align:left;padding:8px;border-bottom:1px solid var(--line)}
footer{text-align:center;color:var(--muted);padding:16px;font-size:12px}
@media (max-width:640px){
 nav a{flex:1 1 45%;text-align:center}
 main{padding:12px}
 h1{font-size:19px}
 table{font-size:12px}
}
"""


def _e(value: Any) -> str:
    """转义单个值，None → 空串；非字符串转字符串。"""
    if value is None:
        return ""
    return html.escape(str(value))


def _badge(status: str, text: str) -> str:
    cls = {"ok": "ok", "done": "ok", "released": "ok", "completed": "ok",
           "推进中": "ok", "已完成": "ok", "已发布": "ok",
           "external_dependency": "ext", "partial": "warn", "in_progress": "warn",
           "待重做": "warn", "proposed": "warn", "open": "warn",
           "fail": "bad", "blocked_external": "bad", "等待外部": "bad",
           "failed": "bad", "未闭环": "bad"}.get(str(status).lower(), "ext")
    return f'<span class="badge {cls}">{_e(text)}</span>'


def render_page(title: str, active: str, body: str) -> str:
    def _nav_link(path: str, label: str) -> str:
        current = ' aria-current="page"' if path == active else ""
        return f'<a href="{path}"{current}>{_e(label)}</a>'
    nav = "".join(_nav_link(path, label) for path, label in NAV_ITEMS)
    return ("<!DOCTYPE html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
            f"<title>{_e(title)} · AIPD-OS Owner</title>"
            f"<style>{_CSS}</style></head><body>"
            f'<a class="skip" href="#main">'
            f'<span>跳到主要内容</span></a>'
            '<header class="top"><span class="brand">AIPD-OS · 所有者控制台</span></header>'
            f'<nav aria-label="主导航">{nav}</nav>'
            f'<main id="main">{body}</main>'
            "<footer>本地运行 · 数据保存在本机 · 未经授权不暴露内部代号</footer>"
            "</body></html>")


# ---------------------------------------------------------------- 首次使用向导
def render_onboarding(console: WebConsole) -> str:
    data = console.onboarding_center()
    parts: list[str] = ['<h1>首次使用向导</h1>']

    if not data["has_project"]:
        parts.append('<section class="card" aria-label="创建或导入项目">'
                     '<h2>创建 / 导入项目</h2>'
                     '<p class="muted">还没有项目。请先创建项目，或从内置示例导入一个。</p>'
                     '<form method="post" action="/api/onboarding/create">'
                     '<label for="onb_name">项目名称</label> '
                     '<input id="onb_name" name="name" required > '
                     '<label for="onb_goal">目标</label> '
                     '<input id="onb_goal" name="goal" required > '
                     '<button type="submit" >创建项目</button></form>'
                     '<form method="post" action="/api/onboarding/import">'
                     '<button type="submit" class="secondary" >导入示例项目</button>'
                     '</form></section>')
    else:
        parts.append('<section class="card" aria-label="项目就绪">'
                     '<h2>项目就绪</h2><p class="muted">已存在项目，可前往'
                     '<a href="/overview">项目总览</a>。</p></section>')

    parts.append('<section class="card" aria-label="环境检测"><h2>环境检测</h2><ul>')
    for c in data["checks"]:
        label = {"ok": "正常", "fail": "失败", "external_dependency": "待配置"}.get(c["status"], c["status"])  # noqa: E501
        parts.append(f'<li>{_e(c["name"])} {_badge(c["status"], label)} '
                     f'<span class="muted">{_e(c["detail"])}</span>')
        if c.get("fixable"):
            parts.append(f'<form method="post" action="/api/onboarding/fix">'
                         f'<input type="hidden" name="name" value="{_e(c["name"])}">'
                         f'<button type="submit" >一键修复</button></form>')
    parts.append('</ul></section>')

    creds = data.get("needs_credentials") or []
    if creds:
        parts.append('<section class="card" aria-label="Provider 配置"><h2>Provider 配置</h2><ul>')
        for p in data.get("providers", []):
            parts.append(f'<li>{_e(p["name"])} <code>{_e(p["env"])}</code> '
                         f'<span class="muted">{_e(p["guide"])}</span></li>')
        parts.append('</ul>'
                     '<p class="muted">以上需凭据的外部能力未配置时，系统如实标记为'
                     '外部依赖，绝不伪造结果。</p></section>')

    return render_page("首次使用向导", "/onboarding", "\n".join(parts))


# ---------------------------------------------------------------- 项目总览
def render_overview(console: WebConsole) -> str:
    data = console.overview()
    rows = [
        ("当前目标", data["current_goal"]),
        ("当前阶段", data["current_phase"]),
        ("健康状况", data["health"]),
        ("已完成", data["completed"] if data["completed"] else "暂无"),
        ("还缺什么", data["gaps"] if data["gaps"] else "暂无"),
        ("最大风险", data["top_risk"] if data["top_risk"] else "暂无"),
        ("下一个里程碑", data["next_milestone"] if data["next_milestone"] else "暂无"),
        ("成本约束", data["cost"]),
        ("时间预估", data["time_estimate"]),
        ("下一步", data["next_step"]),
    ]
    body = ['<h1>项目总览</h1>',
            f'<p class="muted">项目：{_e(data["project_name"])} '
            f'（编号 {_e(data["project_ref"])}）</p>']
    for label, value in rows:
        body.append(f'<section class="card" aria-label="{_e(label)}">'
                    f'<h2>{_e(label)}</h2><p>{_e(value)}</p></section>')
    return render_page("项目总览", "/overview", "\n".join(body))


# ---------------------------------------------------------------- 决策中心
def render_decisions(console: WebConsole) -> str:
    data = console.decision_center()
    body = ['<h1>决策中心</h1>']
    if not data.get("has_decision"):
        body.append('<section class="card" aria-label="暂无决策">'
                    '<h2>当前没有待您决策的事项</h2>'
                    '<p class="muted">系统会继续推进，遇到需要您拍板的决策会在此出现。</p>'
                    '</section>')
        return render_page("决策中心", "/decisions", "\n".join(body))

    body.append(f'<section class="card" aria-label="当前决策事项">'
                f'<h2>{_e(data["display_id"])} · {_e(data["topic"])}</h2>'
                f'<p><strong>AI 建议：</strong>{_e(data["ai_recommendation"])}</p></section>')

    body.append('<section class="card" aria-label="可选方案">'
                '<h2>可选方案</h2><table><thead><tr><th>方案</th><th>影响</th></tr></thead><tbody>')
    impacts = data.get("impacts") or {}
    for option in data.get("options") or []:
        imp = impacts.get(option, {}) if isinstance(impacts, dict) else {}
        body.append(
            f'<tr><td>{_e(option)}</td><td>'
            f'成本:{_e(imp.get("cost", "-"))} / 性能:{_e(imp.get("performance", "-"))} / '
            f'时间:{_e(imp.get("time", "-"))} / 安全:{_e(imp.get("safety", "-"))}</td></tr>')
    body.append('</tbody></table>'
                '<form method="post" action="/api/decisions/approve">'
                f'<input type="hidden" name="ref" value="{_e(data["ref"])}">'
                '<button type="submit" >批准（按 AI 建议）</button></form></section>')

    body.append(f'<section class="card" aria-label="批准后系统行为">'
                f'<h2>批准后将自动执行</h2><p>{_e(data["after_approval"])}</p></section>')

    evidence = data.get("evidence") or []
    if evidence:
        body.append('<section class="card" aria-label="决策证据"><h2>证据</h2><ul>')
        for e in evidence:
            body.append(f'<li><strong>{_e(e.get("title"))}</strong>'
                        f'<br><span class="muted">{_e(e.get("summary"))}</span></li>')
        body.append('</ul></section>')
    return render_page("决策中心", "/decisions", "\n".join(body))


# ---------------------------------------------------------------- 制品中心
def render_artifacts(console: WebConsole) -> str:
    data = console.artifact_center()
    body = ['<h1>制品中心</h1>']
    artifacts = data.get("artifacts") or []
    if not artifacts:
        body.append('<section class="card" aria-label="暂无制品">'
                    '<h2>暂无制品</h2><p class="muted">项目推进后生成的交付物会在此展示。</p>'
                    '</section>')
    else:
        body.append('<section class="card" aria-label="制品列表">'
                    '<h2>制品列表</h2><table><thead><tr>'
                    '<th>编号</th><th>类型</th><th>状态</th><th>版本</th><th>操作</th>'
                    '</tr></thead><tbody>')
        for a in artifacts:
            body.append(f'<tr><td>{_e(a["display_id"])}</td>'
                        f'<td>{_e(a["type"])}</td>'
                        f'<td>{_badge(a["status_raw"], a["status"])}</td>'
                        f'<td>{_e(a["version"])}</td>'
                        f'<td><form method="post" action="/api/artifacts/approve">'
                        f'<input type="hidden" name="ref" value="{_e(a["ref"])}">'
                        f'<button type="submit" class="secondary" >批准</button></form>'
                        f'<form method="post" action="/api/artifacts/reject">'
                        f'<input type="hidden" name="ref" value="{_e(a["ref"])}">'
                        f'<button type="submit" class="danger" >退回</button></form>'
                        f'<form method="post" action="/api/artifacts/rework">'
                        f'<input type="hidden" name="ref" value="{_e(a["ref"])}">'
                        f'<button type="submit" >局部返工</button></form></td></tr>')
        body.append('</tbody></table></section>')

    if data.get("cad_versions"):
        body.append(f'<section class="card" aria-label="CAD 版本历史"><h2>CAD 版本历史</h2>'
                    f'<p class="muted">{_e(len(data["cad_versions"]))} 个版本的几何变更记录。</p></section>')  # noqa: E501
    if data.get("bom_diffs"):
        body.append(f'<section class="card" aria-label="BOM 差异"><h2>BOM 差异</h2>'
                    f'<p class="muted">{_e(len(data["bom_diffs"]))} 项物料清单变更。</p></section>')
    if data.get("parameter_diffs"):
        body.append(f'<section class="card" aria-label="参数差异"><h2>参数差异</h2>'
                    f'<p class="muted">{_e(len(data["parameter_diffs"]))} 项参数变更。</p></section>')  # noqa: E501
    return render_page("制品中心", "/artifacts", "\n".join(body))


# ---------------------------------------------------------------- 运行控制
def render_run(console: WebConsole) -> str:
    data = console.run_control()
    state_cn = {"idle": "空闲", "running": "运行中", "paused": "已暂停",
                "cancelled": "已取消", "done": "已完成", "needs_approval": "待批准",
                "needs_clarification": "待澄清", "failed": "失败"}.get(
        data["state"], data["state"])
    cls = {"done": "ok", "running": "warn", "paused": "warn", "idle": "ext"}.get(
        data["state"], "bad")
    body = ['<h1>运行控制</h1>',
            f'<section class="card" aria-label="运行状态"><h2>当前状态</h2>'
            f'<p>{_badge(cls, state_cn)} '
            f'<span class="muted">尝试次数 {_e(data["attempts"])}</span></p>'
            f'<p class="muted">心跳：{_e(data["heartbeat_at"] or "—")}</p>'
            f'<p class="muted">失败原因：{_e(data["failure_reason"] or "无")}</p></section>']

    body.append('<section class="card" aria-label="发起运行">'
                '<h2>发起运行</h2>'
                '<form method="post" action="/api/run/start">'
                '<label for="run_intent">一句自然语言指令</label> '
                '<input id="run_intent" name="intent" required > '
                '<button type="submit" >开始</button></form></section>')

    actions = [
        ("/api/run/pause", "暂停", "secondary"),
        ("/api/run/resume", "恢复", "secondary"),
        ("/api/run/cancel", "取消", "danger"),
        ("/api/run/retry", "重试", ""),
    ]
    body.append('<section class="card" aria-label="控制操作"><h2>控制操作</h2>'
                + "".join(
                    f'<form method="post" action="{url}" style="display:inline">'
                    f'<button type="submit" class="{cls2}" >{label}</button></form>'
                    for url, label, cls2 in actions)
                + '</section>')

    events = data.get("events") or []
    if events:
        body.append('<section class="card" aria-label="进度事件"><h2>进度事件</h2><ul>')
        for ev in events:
            body.append(f'<li><strong>{_e(ev.get("step"))}</strong> '
                        f'<span class="muted">{_e(ev.get("message"))}</span></li>')
        body.append('</ul></section>')
    return render_page("运行控制", "/run", "\n".join(body))


# ---------------------------------------------------------------- 外部等待中心
def render_external_wait(console: WebConsole) -> str:
    data = console.external_wait_center()
    body = ['<h1>外部等待中心</h1>',
            f'<section class="card" aria-label="等待概览"><h2>等待概览</h2>'
            f'<p>{_e(data["summary"])}</p></section>']
    items = data.get("items") or []
    if not items:
        body.append('<section class="card" aria-label="无外部等待">'
                    '<h2>当前没有外部等待事项</h2></section>')
    else:
        body.append('<section class="card" aria-label="外部事项列表"><h2>外部事项</h2><ul>')
        for it in items:
            body.append(f'<li><strong>{_e(it["display_id"])}</strong> '
                        f'{_e(it["what"])}<br>'
                        f'<span class="muted">责任方：{_e(it["who"])} · '
                        f'{_e(it["needs_upload"])} · {_e(it["deadline"])}</span>')
        body.append('</ul></section>')
    return render_page("外部等待中心", "/external-wait", "\n".join(body))


# 各中心渲染函数注册表（供 server 路由复用）
RENDERERS = {
    "onboarding": render_onboarding,
    "overview": render_overview,
    "decisions": render_decisions,
    "artifacts": render_artifacts,
    "run": render_run,
    "external-wait": render_external_wait,
}

__all__ = ["render_page", "render_onboarding", "render_overview",
           "render_decisions", "render_artifacts", "render_run",
           "render_external_wait", "RENDERERS"]
