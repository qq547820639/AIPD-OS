# F-EVID-03：证据侧车路径按「干名」拼，同名不同后缀的产物会互相顶掉（第 23 片已修）

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

## 三、修的是哪一个，以及为什么不是先止血

立案时给了三个选项，实修选了 **1（侧车名带上原后缀）+ 一条守拼法的常驻用例**，
没走「先拒绝顶掉、以后再说」那条止血路。理由是动手前数了一遍消费方：

- 全仓**没有一个跟踪在案的 `.evidence.json` 文件**（`git ls-files | grep -c evidence.json` = 0）
  ⇒ 改拼法不涉及「老侧车读不到」的迁移问题，止血方案要防的那个风险在这里不存在。
- 产品侧只有 **4 个写入点 + 3 个读取点**在拼这个名字，全部改成走一个
  `cad/evidence.sidecar_path()` 即可，规则从此只有一份。
- 测试侧 20 处跟着改（12 个文件，其中 4 处是硬写文件名的字面量，逐条对着产物名改）。
  止血方案反而更贵：它不消除「两个产物不能同干名」这条用法限制，作者还是得改名。

于是新拼法是 `assy.step.evidence.json` / `assy.dxf.evidence.json`——后缀留在名字里，
一个产物一个侧车，谁也不顶谁。**不留兼容分支**（本仓规矩：能直接改就不加向后兼容的壳）。

一处过程教训值得记：批量替换第一次用的是「任意表达式 + `.with_suffix(...)`」的正则，
把 `json.loads(out.with_suffix(".evidence.json").read_text(...))` 这类嵌套调用改成了
语法不通的残骸（`sidecar_path(json.loads(out).read_text(...))`），12 个文件里有 8 处中招。
发现后**整批 revert**，改用「只匹配裸标识符」的严格式，并在写盘前对每个文件 `ast.parse`
一遍才落盘。批量文本改写的底线是**改完必须能被解析**，不是「跑起来大概没事」。

## 四、第 22 片当时已有的部分防护（读侧不信任侧车）

读侧不信任侧车的自述。实测这份 DXF 侧车里**没有** `document_sha256`（它带的是 `bytes`），
所以顶掉发生时先撞的是 `assembly_step_evidence_incomplete`（没有 `declared_part_count`/`parts`）
——正是端到端那一次报出来的那条。若哪天两份侧车字段名重合了，还有 `assembly_step_hash_mismatch`
兜着：侧车写的 `document_sha256` 与眼前这份文件实际哈希不等即阻断（**字段缺失也算不等**，
代码里是 `str(evidence.get("document_sha256") or "")` 与真哈希比）。
也就是说真被顶时不会静默过关；但这是**撞上**，不是设计——防护应该建在「两个产物不共用一个
证据文件」上，而不是建在字段名恰好不重合上。

## 五、常驻用例与电池（第 23 片）

`tests/test_evidence_sidecar_paths.py` 9 条，三组：拼法本身用**字面量**钉住
（`assy.step` ⇒ `assy.step.evidence.json`，不跟着助手函数一起错）、
两个同干名产物各有各的侧车且**哈希各自对得上自己那份**（真导出 + 真出图）、
以及一条「全仓 `src/` 里再不许出现第二处侧车拼法」的 grep 守卫。
最后那条是防复发的：以后谁在别的写入点手写一遍旧式换后缀，常驻用例就红。

变异电池 `/tmp/slice23-mutations.py` **8/8 killed**：拼法退回只留干名（S1）、
读取点自己拼（S2）、图纸/DFM/步骤文档/公共侧车四个写入点各自退回旧写法（S3~S6）、
别处再留一处旧写法（S7，打的是那条 grep 守卫）、
端到端那条读侧被绕开（S8）。S5/S6 特意打在**各自文件的既有用例**上——
证明这次改名不是只有新文件看得见。

## 六、收尾读数（落盘后由量具复算，不是计划）

| 量具 | 读数 |
|---|---|
