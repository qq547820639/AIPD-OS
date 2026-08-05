# CAD插件安装与发现

Codex 0.142.0 或更新版本：

```bash
codex plugin marketplace add earthtojake/text-to-cad
codex plugin add cad@text-to-cad
```

安装后启动新会话。若采用直接 Skill 安装，可将 CAD Skill 放在仓库或用户级 `.agents/skills/cad/`，并通过 `AIPD_CAD_SKILL_DIR` 显式指定路径。

安装完成后必须运行 `runtime_preflight.py`；不要仅凭安装命令返回成功就假定工具可用。
