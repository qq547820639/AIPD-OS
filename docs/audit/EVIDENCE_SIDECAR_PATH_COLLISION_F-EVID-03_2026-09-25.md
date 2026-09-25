# F-EVID-03：证据侧车路径按「干名」拼，同名不同后缀的产物会互相顶掉（发现，未修）

**发现方式**：第 22 片的端到端跑。同一个目录里先出总装 STEP（`assy.step` + 侧车），
再出装配图（`assy.dxf`），然后 `aipd release manifest --assembly-step assy.step` 报

```
[阻断] assembly_step_evidence_incomplete:
       assy.evidence.json 里没有 declared_part_count / parts
```

——它读到的是**那张图的侧车**。STEP 的证据文件被 DXF 覆盖了。

## 一、机制

两个写入方都用同一套「换后缀」的拼法：

- 图纸侧：`release_manifest._evidence_path(dxf)` 与 `write_dxf` 内部一律
  `path.with_suffix(".evidence.json")`；
- 侧车写入：`aipd_os/cad/evidence.py:write_evidence_sidecar()` 同样 `with_suffix`。

`assy.step`.with_suffix(".evidence.json") == `assy.evidence.json` ==
`assy.dxf`.with_suffix(".evidence.json")。**后缀被丢掉，只剩干名** ⇒
任何「同名不同后缀」的一对产物（`bracket.step` / `bracket.dxf`、
`assy.step` / `assy.dxf` / `assy.md`）共享一个侧车路径，后写的赢。

## 二、危害面（为什么不是洁癖）

侧车是这一路唯一的机器可读凭据：球标↔BOM 绑定、尺寸实测值、回读核对结论、哈希。
两份产物抢一个文件 ⇒ 发布证据会拿 A 的凭据给 B 盖章，而且**双方都不知道自己被顶了**
（写入方是无条件覆盖，读取方只看内容像不像）。第 22 片这条 `assembly_step_evidence_incomplete`
算运气好——字段名恰好不重合才被抓住；重合的时候（比如两份都是 DXF 派生）读到的就是一套
自洽但属于别人的证据。

## 三、修法选项（还没定，留给下一片）

1. **侧车名带上原后缀**：`assy.step.evidence.json` / `assy.dxf.evidence.json`。
   根治，但要动的面大：`_evidence_path`、`write_evidence_sidecar`、各 CLI 的读侧、
   `release_manifest` 与门禁里所有按 `.evidence.json` 找文件的地方、以及既有常驻用例
   里的路径断言。**先数清消费方再动**（本仓 `docs/audit/` 下已有 `.evidence.json` 字面量
   出现在 README/SKILL/多份审计里，那些是文档不是代码，得区分开）。
2. **写入方拒绝顶掉别人**：`write_evidence_sidecar` 发现目标已存在且其 `document` 字段
   与本次不同 ⇒ 报错退出。改动小、当场消除静默丢证据，但把「同干名」变成用法限制，
   作者得改产物命名。
3. 两条一起做：先 2 止血（一个写入点 + 一条用例），再 1 根治。

倾向 **3**：止血那条几乎没风险（正常流程里目标不存在或 `document` 相同），
而 1 的收益要给消费方普查开绿灯之后才敢动。

## 四、这一片（第 22 片）里已有的部分防护

读侧不信任侧车的自述。实测这份 DXF 侧车里**没有** `document_sha256`（它带的是 `bytes`），
所以顶掉发生时先撞的是 `assembly_step_evidence_incomplete`（没有 `declared_part_count`/`parts`）
——正是端到端那一次报出来的那条。若哪天两份侧车字段名重合了，还有 `assembly_step_hash_mismatch`
兜着：侧车写的 `document_sha256` 与眼前这份文件实际哈希不等即阻断（**字段缺失也算不等**，
代码里是 `str(evidence.get("document_sha256") or "")` 与真哈希比）。
也就是说真被顶时不会静默过关；但这是**撞上**，不是设计——防护应该建在「两个产物不共用一个
证据文件」上，而不是建在字段名恰好不重合上。
