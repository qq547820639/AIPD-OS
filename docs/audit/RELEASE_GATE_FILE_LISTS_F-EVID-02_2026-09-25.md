# F-EVID-02 第 21 片（门禁那一半）：FILE_KEYS 的哈希核对对**数组形状**整条形同虚设

发现的起因不是审代码，是第 20 片收尾后要接着问「总装 STEP 怎么进发布证据」。
顺着这条路读到门禁的 `FILE_KEYS` 那一栏，撞上：**它引用文件存在与哈希，但只认单值，
而模板和生产者写出来的恰恰是数组**。这意味着第 21 片要把总装 STEP 接进去的那道格子，
接的是一道不会开火的判据。所以本片先修判据，接线留到下一片。

## 一、现象与最小复现

`scripts/production_release_gate.py` 自述：

> `# Keys whose value may reference a file path that must exist and hash-match.`

两条使用点：`check_requirement` 的 (b)（逐键，产出 `missing`）与 `file_openable`
（产出 `evidence_checks`）。两处都走 `resolve_path(value)`，而它只认
`dict{path,sha256}` 与非 URL 字符串；数组掉到最后一行返回 `(None, None)`，
两条使用点都 `if not path: continue`。

可这些键**在模板里就是数组**（`assets/templates/production_cad_manifest.json`：
`step_assemblies: []`、`step_parts: []`、`drawings: []`、`cae_reports: []`、
`physical_evidence: []`），`aipd release manifest` 写出的 `evidence.drawings[]`
也是数组（`release_manifest.py:189` 逐张图 `{path, sha256, kind}`）。
⇒ 一份图纸全删、全被改过的包，门禁读成「所有引用文件可打开」。

最小复现（修之前必红，修之后必绿，已常驻）：
`tests/test_production_release_gate_file_lists.py::TestOpenableFiresOnLists`。

## 二、为什么以前没被发现

`tests/test_production_release_gate.py:86` 钉的是 `drawings="missing_drawings.pdf"`——
**字符串**。也就是说这道判据唯一被验过的那条路径恰好是它少数能认的形状；
生产者真正写出来的数组形状一次都没进过用例。`tests/test_release_manifest.py` 里
唯一走到 `file_openable` 的那条（`test_drawing_file_is_referenced_with_a_matching_sha256`）
断言的是 `passed is True`——**在判据根本不跑的情况下它当然绿**。
这条不是假断言（它想说的对生产者也成立），但修完之后它才第一次为正确的理由通过。

## 三、改了什么

`resolve_paths(value)`：数组/元组摊平（递归一层元素，元素仍是 dict/str 两种形状），
单值走原来的 `resolve_path`；不是文件引用（布尔、None、空串、URL）一律空表。
两条使用点都换成逐条核：

- 每一条都要在；缺就报 `{key}: file not found: {path}` / `{key}: not found: {path}`。
- 每条**各自**核哈希，报 `{key}: sha256 mismatch: {path}`（旧文案不带文件名，
  多条时无法指认是哪一条，一并补上）。
- 没写 `sha256` 的条目只核存在，**不判失配也不现场算一个当期望值**——
  现场算等于永不失配。
- 字符串与布尔的旧行为原样（`_find_cad_contract` 仍用单数版，那儿的值是单个引用）。

## 四、常驻用例 11 条（`tests/test_production_release_gate_file_lists.py` 9 + `test_release_manifest.py` 2）

四组：`resolve_paths` 形状（3）、`file_openable` 对数组开火（3）、逐键哈希对数组开火（3）、
旧行为不回退（2）。其中两条打在**真产物**上：用 `build_release_manifest` 出一份文档，
删掉图 ⇒ `file_openable` 点名；改内容 ⇒ `missing` 里出 `C6:drawings: sha256 mismatch`。
门禁是逐级停的（`achieved` 停在没满足的那一级，上面各级的逐键判据不跑），
所以那两条先把与本题无关的 C0..C5 各键填成占位真值，`drawings` 一条不改。

## 五、变异电池（`/tmp/slice21-mutations.py`，8 条全开火）

| # | 注入的坏判据 | 开火 |
|---|---|---|
| G1 | 数组只核第一条 | 两条图只丢第二条 ⇒ 没人红（正是这个形状） |
| G2 | 数组摊平整条关掉（回到修前） | 3 条（含真产物那条） |
| G3 | 哈希拿现场算的值跟自己比 | 3 条 |
| G4 | 没写哈希的条目判失配（反向扩权） | 1 条 |
| G5 | `file_openable` 不再报「没了」 | 2 条 |
| G6 | 逐键判据不再报「没了」 | 1 条 |
| G7 | 布尔证据被当成路径 | 1 条 |
| G8 | 字符串值不再认 | 2 条 |

G4 是特意放的**反向**注入：收紧判据时容易顺手把「没给哈希」也判成错，
那会让 `step_parts: ["part.step"]` 这种合法写法全体失配。一条必须开火、一条必须不开火，
配成对才敢说这次收紧的边界是对的。

## 六、读数的连带影响（都跑过，不是推测）

- 全量 pytest：**1865 passed / 0 failed / 3 skipped**（本片新增 11 条；上一片收尾 1854/0/3）。
  唯一的两红是 `test_packaging.py` 的两条清单锚点自检——改动工作树后必然红，
  收尾重锚即消（与每片同形，不是回归）。
- 收紧之后**没有任何一份现存包判红**：`tests/test_golden_projects_e2e.py`、
  `tests/test_release_manifest.py`、`tests/test_production_release_gate.py`、
  `tests/test_cli.py` 全绿 ⇒ 没有一份包是靠这条空判据蒙过去的（这是好消息，
  也是「以前没人依赖过它」的另一面证据）。
- 能力行 `cad.production_release_gate` 的 `e2e_evidence` 原文列着「hash」，
  这一栏此前对数组是虚的 ⇒ 与散文同批改：写清数组形状现在逐条核，
  并把「哈希核对按级触发」写成明写的 limitation（原来那一栏是 `None`，等于宣称没边界）。

## 七、这一片没做的事

- 没把 `assembly_model` 加进 `REQ['C6']`：总装 STEP 进发布证据是下一片的事，
  而且「是否阻断」是判决，得先有生产者那一格可判。
- 没做「多条 FILE_KEYS 一次报全」之外的表现层改动（`missing` 仍是扁平字符串清单）。
- 递归只摊一层（元素是数组的数组不处理）：模板与生产者都不产生那种形状，
  不为没见到的形状加代码。
