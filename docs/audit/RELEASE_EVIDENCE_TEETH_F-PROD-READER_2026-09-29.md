# F-PROD-READER 第 97 片：`release_evidence.py` 那四支没人调的分支，与版本号该从哪儿读

日期：2026-09-29。上一片收口提交：`e8dcbcb`。

## 一、这一片问什么

第 96 片排片时我记了一条「`release_evidence.py` 没有常驻读者」。**那条是假的**——
按本仓自己的规矩（否定结论要穷举全部书写形态）一手复算后推翻：
`grep -rl release_evidence tests/` 现读命中 7 个文件，其中
`tests/test_release_evidence.py:17` 就是 `import release_evidence`。
真正的缺口在**函数级**，且逐个名字亲手数过（`grep -rl <名> tests/` 零命中）：
`_build_environment`、`_dependency_lock`、`generate_bundle_manifest`、CLI 的 `--bundle` 旗子。
也就是说：这个发布工具最容易被环境牵着走的那几段，之前只被历轮 `docs/audit/` 里
**没人 collect** 的取证脚本碰过（`pyproject.toml:75` `testpaths = ["tests"]`）。

顺带在补牙过程中撞到一个**今天的活风险**：`_build_environment` 用
`getattr(mod, "__version__", "unknown")` 读版本号，而本机现跑直接吐

```
DeprecationWarning: Accessing jsonschema.__version__ is deprecated and will be
removed in a future release. Use importlib.metadata directly to query for jsonschema's version.
scripts/release_evidence.py:235
```

（一手读数：本机 `jsonschema` 4.25.1，警告文案就是它自己写的。）
将来它移除该属性时，那一格会**静默**变成 `unknown`——在证件里与"这台机器没装"同一种形状。

## 二、技术选型（四段）

### 候选清单

| 方案 | 出处（本轮真实打开） |
| --- | --- |
| A `importlib.metadata.version()` | `https://docs.python.org/3/library/importlib.metadata.html`（抓到的是 3.14.7 那版页面）：模块 **added in Python 3.8**；`version()` 是“the quickest way to get a Distribution Package's version number”；“Raises `PackageNotFoundError` if the named distribution package is not installed”；并且“it supersedes `pkg_resources`”“the now-removed `pkg_resources` package” |
| B `pkg_resources`（setuptools） | 本机现跑 `-W error::DeprecationWarning` 的 `import pkg_resources` ⇒ `ModuleNotFoundError: No module named 'pkg_resources'`（本 venv 里根本没装） |
| C 模块属性 `mod.__version__` | 现行实现（`scripts/release_evidence.py` 第 97 片改动前的 `:235`），运行时已被包自己标为废弃（见 §一 那条警告） |

### 六维对比

- **功能匹配度**：A 直接给"已装发行包的版本"，正是 `build_environment.packages` 要记的事实；
  B 同一问法但语义更宽（还带 resolver）；C 只在"包作者恰好导出这个属性"时成立——
  它读的是**包的内建约定**，不是安装事实。
- **License 兼容性**：A 是 CPython 标准库（随解释器的许可证），零新增依赖；
  B 属 setuptools（MIT），但本机没装；C 零依赖。
- **维护活跃度**：A 在 3.14 文档里是正式、持续维护的入口（“Changed in version 3.10”），
  而 `pkg_resources` 被同一页描述为 **now-removed**；C 的这条路正被包作者自己废弃。
- **安全风险**：A/B 都不引入网络与执行面；C 无新增面。差异不在风险而在**会不会静默降级**。
- **代码质量**：A 的失败模式是显式异常（`PackageNotFoundError`），可分档；
  C 的失败模式是 `getattr(..., "unknown")` 的默认值，把两种不同的"不知道"折成同一个字符串。
- **适配成本**：A 在本机 3.9.6 现读可用（`importlib.metadata.__file__` 指向
  `.../Python3.framework/Versions/3.9/.../importlib/metadata.py`，`version`/`PackageNotFoundError`
  都在）；B 要先加依赖；C 是改都不改。

### 择一决定

**采用 A（成熟方案，零依赖），并把 C 留作回退**：`_pkg_version(pkg)` 先问打包元数据，
`PackageNotFoundError` 时才回退 `__import__(pkg).__version__`，两条路都没有才写
`not-installed`；`unknown` 只留给"导入得到但确实给不出版本"。
不引 B：本机没有 `pkg_resources`，为一个已经在文档里被写成 *now-removed* 的入口加依赖，
方向反了。借了 A 的什么：整个版本来源都换成它的权威 API 与它的显式失败语义。

现读值确认这一步**不改数**（只改来源）：改动前后三格都是
`{'cryptography': '50.0.0', 'aipd_os': '5.6.0', 'jsonschema': '4.25.1'}`，且警告消失。

### 落地处

- 实现：`scripts/release_evidence.py` 新增 `_pkg_version()`，`_build_environment()` 循环体改成一行调用。
- 常驻牙：`tests/test_release_evidence_environment.py`（8 条，含 1 条生产侧对账）。
- 变异电池：`docs/audit/s97/battery97.py`（W0 对照 + 9 支撤销臂）。
- 电池缓存那一格的连带核查：对历轮电池做**静态**普查（`docs/audit/RELEASE_EVIDENCE_TEETH_F-PROD-READER_2026-09-29.md` §四）。

## 三、八条常驻牙各钉什么

| 用例 | 钉的口径 | 为什么不能只钉一极 |
| --- | --- | --- |
| `test_build_environment_header_fields_are_the_host_truth` | 头部四格 == 独立重算的 `platform.*` | 抄实现的断言只证"两处一致"，不证与宿主一致 |
| `test_metadata_wins_and_the_two_missing_shapes_stay_distinct` | 元数据优先；`not-installed` 与 `unknown` 分两档；都不许空串 | 只钉"能读到"抓不到"说谎的属性值赢了元数据"；两档合一会让"没装"与"工具链读不出"同形 |
| `test_dependency_lock_keeps_lockfiles_when_pip_freeze_fails_or_lies` | 抛异常 ⇒ `pip_freeze is None` 且锁文件面照算；退码非 0 ⇒ 不许把垃圾 stdout 记进证件；成功 ⇒ 收去空白正文 | "尽力而为"最容易长成的样子是"失败时把整段信息一起带走" |
| `test_zip_bundle_lists_every_member_with_independently_recomputed_sha` | 逐条 sha 用 `hashlib` 独立重算、`entry_count == len(entries)`、按 path 排序 | 夹具故意**逆序**写入 zip，否则"排序面"那条断言其实在抄 `zipfile` 的插入顺序 |
| `test_non_zip_bundle_degrades_to_exactly_one_self_entry` | 非 zip 退化成"整包自身"一条 | 退化成 0 条时清单看着像合规 |
| `test_bundle_path_is_relative_and_not_tied_to_the_dev_machine` | `bundle_path` 相对、正斜杠、随 `repo_root`/cwd 变 | 这个字段存在的全部意义是可重定位；写成绝对路径不会报错，只会让证件在别的机器上指不到包 |
| `test_bundle_cli_flag_writes_the_bundle_manifest_and_omission_does_not` | `--bundle` 真跑 CLI：给 ⇒ 三件套且 `PROVENANCE.bundle_hash == BUNDLE_MANIFEST.bundle_sha256`；不给 ⇒ 不许凭空多出 BUNDLE | 这条旗子之前从未被任何常驻用例传过（`grep '"--bundle"' tests/` 零命中） |
| `test_provenance_on_disk_carries_a_populated_build_environment` | **已入库**那份 `PROVENANCE.json` 的这几格真有内容，且逐条锁文件 sha 与磁盘独立重算一致 | 前七条都靠桩或临时仓库；这一条钉"生产路径真跑出来过"，二者缺一就是"缝里能跑、产物里没有" |

## 四、电池层普查：哪些历轮读数可能被陈旧字节码遮蔽

第 96 片实测到：`python -m py_compile <靶文件>` 会把**变异体**的字节码落进
`sys.pycache_prefix`，而缓存有效性只看 `(源 mtime 整秒, 源字节数)` ⇒
"同长度编辑 + 同秒还原"之后，每一次 `import` 该文件跑的都是变异体。

普查手法（关键是**不许 import 电池**）：第一版我用
`importlib` 把历轮电池逐个 `exec_module` 来读 `ARMS`——`battery83/84/86` 有**模块级副作用**
（`docs/audit/s84/battery84.py:90` 就是模块顶层的 `print(f"基线 rc={RC0} …")`），
于是那一次普查自己跑了两三轮 pytest。改成纯 `ast.parse` 后逐臂比较
`len(old.encode()) == len(new.encode())`，读数（只列被标的）：

| 电池 | 语法检查 | 可判臂 | 同长度臂 |
| --- | --- | --- | --- |
| `battery89/90/91` | `py_compile` | 15 / 13 / 7 | 0（没有同长度编辑 ⇒ 未被这一格影响） |
| `battery92` | `py_compile` | 7 | 1：`B3-flatten-or-and` |
| `battery93` | `py_compile` | 14 | 1：`Y5-missing-counts-as-checked` |
| `battery94` | `py_compile` | 8 | 2：`W3-continuation-offset-last-line`、`W11-bucket-doesnt-count-soft` |
| `battery96` | 硬化后复跑 | 15 | 2：`Z5`、`Z14`（`Z14` 就是当场逮到的那条；硬化后 15/15 KILLED 才是权威读数） |
| `battery97` | 硬化（一开始就按新形状写） | 9 | 0 |

判据与处置：**只有"用 `py_compile` 且存在同长度编辑"的臂**可能被遮蔽。本片把这 4 支电池的
语法检查换成 `ast.parse`、子进程加 `-B` 与 `PYTHONDONTWRITEBYTECODE=1`、并在开局与每臂复位后
清两份缓存路径，然后**重跑一遍**——重跑读数与留档读数的对照见 §五。

## 五、历轮电池重跑与两处连带发现

硬化后的六支电池**当场重跑**（`-B` + `ast.parse` + 前后清缓存），读数：

| 电池 | 重跑读数 | 与留档读数 |
| --- | --- | --- |
| `battery89` | `RC=7`，2 支锚点作废：`Y11-reverse-arm-reads-state-names`、`Y12-reverse-arm-trusts-delegated` 各命中 0 次 | **不能重放**——靶文件 `scripts/doc_command_census.py` 在第 90 片"识别面加宽"里被改过，那两支臂的锚点所在代码已经不是当初那段。本片该核的是同长度臂，而 s89 现读 0 支同长度臂 ⇒ 它的历史读数不受字节码那一格影响 |
| `battery90` | `KILLED 13 / 13`，无 SURVIVED、无 BAD-ANCHOR | 与留档一致 |
| `battery91` | `RC=7`，2 支锚点作废：`A6-no-continuation-fold`、`A7-block-is-one-command` | 同 s89：靶 `scripts/ci_surface_census.py` 在第 94 片被重写；s91 现读 0 支同长度臂 ⇒ 历史读数不受影响 |
| `battery92` | `KILLED 7 / 7`（含被标出的 `B3-flatten-or-and`） | **被标出的那一臂重跑后仍是 KILLED** ⇒ 留档读数成立 |
| `battery93` | `KILLED 14 / 14`（含 `Y5-missing-counts-as-checked`） | 同上，成立 |
| `battery94` | `KILLED 13 / 13`（含 `W3-continuation-offset-last-line`、`W11-bucket-doesnt-count-soft`） | 同上，成立 |

结论：这一族里**只有第 96 片的 Z14 真的被陈旧字节码遮蔽过**，而它已经在当场被发现后按硬化形状重跑（15/15 KILLED 是权威读数）；
另外四支同长度臂重跑后读数不变。两支老电池因靶代码演进而拒跑（退 7）——这是锚点预数那道闸**设计上的正确行为**，
不去修锚、也不把它的历史读数说成"已重放"。

连带两处：

1. `sys.implementation.cache_tag` 现读 `cpython-39`，八支电池的 `_drop_cache()` 都改成用它拼树内路径
   （原来写死 `.cpython-39.pyc`，换解释器就删不到东西）。探针实测：macOS 把 `sys.pycache_prefix`
   设成 `~/Library/Caches/com.apple.python/<源路径镜像>`，所以**树内 `__pycache__` 那一支在这台机器上
   根本没被写过**（探针现读 `猜测路径存在(树内): False`），真正生效的是 `cache_from_source()` 那一路；
   两条路都留着，因为换环境（无 prefix）时树内那一路才是唯一有效的一路。
2. 派生脚本的**日志基名**是个漏掉的镜像面：`s95`→`s96` 这类替换吃不到 `bind95.log`/`gate95.log`/
   `closeout95.log`（数字前面是 `out`/`bind`/`gate`，不是 `s`）。于是第 96 片跑完，
   `docs/audit/s96/` 里躺着的是**名字叫 95、内容是 96 读数**的三个日志
   （`bind95.log` 首行现读就是那一跑的 `release_evidence.py:235` DeprecationWarning ⇒ 内容确实是本轮）。
   本片把三个基名写进派生的替换表，并给派生脚本加了一条哨兵断言
   `assert "95.log" not in text`，同时在 `SENTINELS` 里钉上 `bind97.log`/`gate97.log`/`closeout97.log`
   三个名字 ⇒ 以后漏掉这一格会在派生阶段就拒写，而不是等到读数对不上。
   s96 那三个文件按原样留着（改名会让"哪个文件是哪一跑"的对账变模糊）。

## 六、认证读数

（由 `docs/audit/s97/closeout97.sh` 回填。）

- 新增常驻：`tests/test_release_evidence_environment.py` 8 条 ⇒ `8 passed`；
  与既有三支同族一起跑 `tests/test_release_evidence*.py tests/test_repo_hygiene.py` ⇒ `50 passed`。
- `ruff check` 与 `mypy` 对新文件各 0 错（`ruff` 顺带报出既有的一处
  `Invalid # noqa directive on scripts/release_evidence.py:268`——`EMPTY_EXCEPT` 不是 ruff 的规则码；
  这一格与"scripts/ 要不要进 CI lint 面"是同一个属主侧待裁项，本片不动它）。
- 电池 `docs/audit/s97/battery97.py`：W0 对照绿、9 支臂各命中 1 次、**KILLED 9/9**、
  收尾 sha 与开局相等（`435a99c194b3`）。
- 版本号来源切换前后现读一致：`{'cryptography': '50.0.0', 'aipd_os': '5.6.0', 'jsonschema': '4.25.1'}`，
  且 DeprecationWarning 消失（改前那条见 §一）。
