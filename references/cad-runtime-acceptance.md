# CAD运行验收

## 前置检查

```bash
python scripts/runtime_preflight.py --require-cad --json-out runtime_preflight.json
```

要求发现 CAD Skill 的 `SKILL.md` 以及 `scripts/step`、`scripts/inspect`、`scripts/snapshot`。

## 最低运行样例

对真实项目执行至少一次 C0 到 C3：

- 受控 CAD Brief 和 CAD Contract；
- 参数化 Python 源码；
- 实际生成的主 STEP；
- `refs --facts --planes --positioning` 等几何事实；
- 规格驱动的定向测量、对齐和干涉检查；
- 主 STEP 快照及人工/视觉审查记录；
- 修复重跑与回归记录；
- 版本 manifest 与哈希。

缺少任一项时，只能声明“CAD接口就绪”，不能声明“CAD运行链闭合”。
