# F-C6 第 31 片：G 表只许有一个来源（声明 50 项、门只要求 40 项）

## 一、这一格以前为什么是假的

`scripts/quality_gate.py:20` 的注释写着

> `# Kept dependency-free: requirements mirror assets/templates/gate_requirements.yaml.`

**这句话今天被证伪**（2026-09-25 现算，正向对照能命中 ⇒ 探针不是空转）：

| 读数 | 值 |
| --- | --- |
| YAML 声明的交付物类型 | **50** |
| 脚本内联 `REQ` 强制的 | **40** |
| 声明了但门不要求 | **10**（`cad_bom_mapping` `cad_contract` `cad_inspection_report` `cad_l1_functional_layout` `cad_l4_dfm_drawings` `cad_l5_release_package` `cad_parametric_source` `cad_primary_step` `cad_snapshot_packet` `evt_cad_configuration`） |
| 门要求但没声明 | **0**（漂移是单边的：只有「声明了不要求」这一侧） |
| `requires_owner_approval` 轴 | 两份**一致**（G2/G5/G6/G7/G8/G9）⇒ 漂的只有交付物轴 |
| 谁解析那份 YAML | **没有人**。`grep -rl gate_requirements` 全仓只命中 `quality_gate.py`，而命中的是**那句注释**；没有任何 `yaml.safe_load` |

⇒ 手抄表在漂，声明文件是死文件。这类「登记说 A、执行是 B」不能靠再加注释修，只能**取消副本**。

## 二、修法与三个决定

1. **权威改成读出来的**：新模块 `src/aipd_os/gate_requirements.py` 用 `yaml.safe_load`
   读 `assets/templates/gate_requirements.yaml`（`pyyaml` 是 `pyproject.toml` 的**核心**依赖，
   本机 6.0.3，零新依赖）。`quality_gate.py` 的 `REQ`/`OWNER` 都由它派生，脚本里
   不再出现任何 `'G3': [...]` 字面表（常驻用例用正则钉住这条）。
   **决定：不引入第二个依赖**——`gate_requirements.yaml` 只有 `required_deliverables`
   与 `requires_owner_approval` 两种键，`safe_load` 足够；不需要 schema 化的声明文件。
2. **读不到就拒绝判决**：YAML 缺失/解析失败/顶层不是映射 ⇒ `_tables()` 报非 ok，
   门打 `{"ok": false, "error": "gate requirements unreadable: …", "source": …}` 并退 **3**；
   表在**每次运行**时现读（不是 import 期缓存），否则「YAML 修好了」和「YAML 坏了」
   这两种情况都读不出差别。反证注入 I2（改回读缓存）由这条用例抓住。
3. **不能要求的要具名，不许静默掉出去**：`UNPRODUCED` 逐项写理由（那 9 项今天没有任何
   代码产出这一类型的交付物；直接接成硬要求 = G3-G8 永久红 = 训练人忽略门）。
   常驻用例钉 **`声明 − 强制 == UNPRODUCED` 且逐项等于那 9 个名字**：
   加第 10 项不归类即判红；从 `UNPRODUCED` 删一项则它自动升进强制集（也有用例钉住）。
   今天升进强制集的是 **`cad_contract`**：它有 `assets/schemas/cad_contract.schema.json`、
   有模板，而且 `production_release_gate` 的 `schema_valid` 真在核它——不是凭名字像就收。

顺带的连锁：`cad_contract` 有同名契约 ⇒ 它同时进了**形状门**那一侧
（第 30 片的 `contracted_types()` 是现算的，不用改代码）。

## 三、「九项没有产者」这句话自己是探针读出来的，而它第一次读错了

`producer_literals()` 在 `src/ scripts/ state_service/ assets/templates/ references/`
里找类型名字面量。第一版**把本模块自己也算进被扫文本**——而九个名字正好写在
`UNPRODUCED` 的键与理由里 ⇒ 九个负向读数全被点亮，"零命中"变成假阴性。
这就是第 30 片记下的「量具不进自己的分母」的**第四个面**，而且是被自己新写的用例当场抓住的：

- 修一：排除 `gate_requirements.py` 自身；
- 修二：名单改为**从声明文件现取**（不再从 `UNPRODUCED` 取名字去反查 `UNPRODUCED`）；
- 正向对照常驻：`project_brief`（→ `scripts/lifecycle_gate.py`）与
  `cad_contract`（→ `src/aipd_os/execution/execution_router.py`）必须探得到；
  这条判据的天花板也写明：字面量只能证明「提过这个名字」，不能证明真产了它。

另有一条**删掉的装饰判据**：`unclassified()`（既没进强制集又没具名的项）在当前实现下
恒为空——`enforced_table()` 丢的恰好就是 `UNPRODUCED`。留着它只会让人以为有一格在守。
删除它，换成两条**真行为**用例：加声明 ⇒ 自动成要求；删豁免 ⇒ 自动升进强制集。

## 四、端到端实测（真子进程、G3）

```
[缺 cad_contract]        rc=1 pass=False  missing=['cad_contract']  shapes=[]
                         enforced_counts={'declared': 6, 'enforced': 5}
                         declared_unenforced=['cad_l1_functional_layout']
[补齐 cad_contract]      rc=0 pass=True   missing=[]  shapes=[]        （must-not-fire 一侧）
[标完成但不填 path]      rc=1 pass=False  missing=[]
                         shapes=[('cad_contract', 'path_missing')]
```

三条一起才算数：只测第一条会分不清「真在要求」还是「永久红灯」；
第三条是第 30 片形状门的连锁，说明**收紧一项会同时收紧两个轴**。

## 五、这一片没做的事

1. 那 9 项 CAD 阶梯交付物**仍然没有产者**。要让它们进硬门，得先决定每一项由哪个
   现有能力产出并以什么 `path` 登记——那是属主裁决（与 C6 那 15 项的处置同一层），
   本片只保证「不具名不许掉出去」。
2. **G 表之外还有两处手抄**：`experience/intent_engine.py`、`experience/impact_analysis.py`、
   `experience/project_summary.py` 各有一份 `G0..G9 → 中文名`（`_MILESTONE_CN` / `GATE_NAMES`），
   实测已漂：G0「概念验证」vs「项目启动与概念验证」等 5 格措辞不同。
   这里**没有**强行统一：短标签与长描述可能是刻意的两种用途，统一方向需要属主拍；
   登记为待裁项而不是顺手改（顺手改会动到用户可见文案）。
3. `scripts/selftest_quality.py`、`scripts/e2e_acceptance.py`、`scripts/selftest_v4.py`
   今天仍不被 CI 或任何用例调用（`grep -rl` 只命中 evals 产物与自身）——**门没人跑**这一族
   还开着；`quality_gate.py` 与 `outcome_acceptance.py` 从第 30 片起有常驻用例（子进程真跑）。
4. 门的 `--root` 仍是单根（一次只能指一个项目目录）。

## 六、收口读数

（全量、电池、门与重锚见下方补记。）
