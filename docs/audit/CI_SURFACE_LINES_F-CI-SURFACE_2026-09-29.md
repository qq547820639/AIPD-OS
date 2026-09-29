# F-CI-SURFACE 第 94 片：CI 命令的**行号**与「门禁被声明为可失败」

量具：`scripts/ci_surface_census.py`（第 91 片立的那把尺）
常驻用例：`tests/test_ci_surface_census.py`（6 条 → **12** 条）
变异电池：`docs/audit/s94/battery94.py`（**13 臂全杀**，控制臂绿，收尾 sha 复原）
量具自测：`python scripts/ci_surface_census.py --self-test`（4 条标记 → **6** 条）
同片顺带修：`scripts/dependency_license_gate.py` 一条 `SIM102`（第 93 片留下的嵌套 if）

> 本文档的**上一版在落盘时被自家补丁脚本写坏了**：脚本里给"新建文件"这条用的是
> `old=""` 的空锚点，守卫循环因为"文件还不存在"跳过它，而写盘循环跑在
> `write_text(DOC)` **之后** ⇒ 对新已存在的文件执行 `s.replace("", DOC)`，
> 把整篇按字符边界插了 3591 份（23MB）。这一版是重写。留这段话在开头的理由：
> "空锚点 + 先建后改"这类自伤只有事后数字才会暴露，而它当时把文档门（census /
> forensic parse / changelog）全数判绿。

## 一、现读分母（四条命令）

```
$ python scripts/ci_surface_census.py --json /tmp/ci94.json
CI 命令 32 条（17 个 job），消费表 32 条
归属：已接住 19 / 免跑有理由 13 / 无人守 0 / 被声明为可失败 0
现状面缺陷 0 条：CI 每条门禁都在本地有归宿
```

```
# 行号与原文互相对账（判据自证，不是"看起来有数"）
命令数 32 | line==0 的条数 0 | 行号处那一行不含该命令起始原文的条数 0
样本：行 208 `python -m pip install --upgrade pip setuptools wheel`
      行 232 `run: python -m pytest tests/test_command_coverage.py ...`
      行  26 `run: python -m pytest tests/ -m "not integration" -q`
```

```
# 软门面：0 是不是"真的没有"——用同一把正则去扫原文，与桶计数对一次
len(hits)=0  continue-on-error=0   （38 个 run 步骤）
```

⇒ 本片**没有活的原告**：行号那一格是把恒 0 的字段换成可指位的数（原来判红只能说
"哪条命令没人守"），`可失败` 那一格是 **fail-closed 的防未来门**。两处都不许写成
"实测抓出的缺陷"，牙齿在 6 条自测标记、12 条常驻用例与 13 臂电池里。

**但电池抓到了一条关于我自己的缺陷**（见 §三第 5 条）：`--emit-register` 整条路
此前没有任何常驻读者，而我补的第一条读者用例是**恒真的**。

## 二、选型（AGENTS.md 第三节；本轮属"影响面明确的局部加宽"，仍给两候选）

| 候选 | 一手出处（本轮真开） | 六维结论 |
|---|---|---|
| actionlint | 经 GitHub 取到 `rhysd/actionlint` 的 README 并读完（MIT；`docs/checks.md` 等文档链接同源列出） | 功能匹配度：**部分**——它查 workflow 语法、`${{ }}` 表达式类型、action 输入输出、脚本注入，并对 `run:` 里的脚本接 shellcheck/pyflakes；报错形状正是 `test.yaml:3:5: … [check]`。它**不查**"这条门在本地有没有读者"（那正是本尺的问题）。License MIT 兼容；维护活跃；安全与质量无疑问；**适配成本＝不可接受**：分发形态是 Go 二进制（`go install` / prebuilt / Docker），装不进 `.venv`，而第 92/93 片已把同一条否决线写死："门依赖未声明的第三方 ⇒ CI 那一侧永远 SKIP"。借的是它的**输出形状**：判据落点写成 `doc:line` |
| PyYAML `compose` + `Mark`（本机 6.0.3） | 本轮实际打开：`.venv/lib/python3.9/site-packages/yaml/__init__.py:51 def compose(stream, Loader=Loader)`、`yaml/error.py:4 class Mark` | 功能匹配度：正对——标量节点自带 `start_mark.line` / `end_mark`；License MIT；PyYAML 本仓 `full` 档已声明、第 91 片那把尺已经在 `import yaml` ⇒ **零新增依赖、零下载**；适配成本最低 ⇒ **选定** |
| ruamel.yaml（round-trip 保留行列标记） | 只作候选列出；**本轮未亲开其官方文档**，不引用其细节，因此不参与六维评分 | 真候选但需新增未声明依赖 ⇒ 与 actionlint 落在同一条否决线上 |

**择一 = 自研薄封装 `_run_marks()` + 用 PyYAML 的标量标记**（不引新依赖）。
决定性理由是本轮实测的两种 YAML 标量形状：块标量 `run: |` 的 `start_mark` 落在**指示行**、
内容从下一行开始；内联 `run: cmd` 的 `start_mark` 就在内容行上。所以定锚法必须是
"从 `start_mark.line` 往后找第一行 strip 后**包含**内容首行的文件行"，而不是 `start+1`。

## 三、这一片实际改的四处（每处都由读数逼出来）

1. `_split_shell()` 返回 `(命令, 起始行偏移, 那一行原文)`：`\` 续行折成一条时偏移取**起始**行
   （指到末尾那行会把人指到参数的续行上），注释行与空行不占命令但**占偏移**。
   第一版我让锚点跳过注释行去找第一条命令——夹具当场把行号整体推后，
   这就是"静默错位"的形状，于是锚点改回标量真正的首行。
2. `_run_marks()` 用 `yaml.compose` 建 `(job, step 序) → 文件行` 映射；
   定不到就不给行号，并由 `ci_commands` 记一条前提诊断 `run_mark_unmatched`（不许静默记 0）。
3. 判据自证关系进常驻用例：`行号处那一行必须包含这条命令的起始原文`——
   行号与内容互相对账，而不是各报各的（钉具体行号会随 workflow 漂，关系不漂）。
4. 新判据 `CI面被声明为可失败`（桶 `soft-declared`）：步骤级 `continue-on-error: true`、
   命令级 `|| true` / `|| :` / `set +e` / `--exit-zero` / `--warn-only` / `--ignore-errors`。
   它与第 91 片立起这把尺的理由同源：`pip-licenses` 只打印、退码恒 0 ⇒ "有门"等于没门；
   这一格把"退码本来会红但被声明可忽略"那种写法也一并拦住。
   真语料 0 命中 ⇒ 常驻用例额外断"0 是真的没有"（同一条正则扫原文，两数同为 0），
   免得判据坏了还读成"很干净"。
5. **`--emit-register` 之前是一个没有读者的出口**，补的读者第一版还是恒真的：
   电池 W12（把 `"line_text_at_emit_time": c["at"]` 换成空串）在 12 条用例全绿的情况下
   **存活**——因为我那条断言写的是 `e["line_text_at_emit_time"] in wf_lines[...]`，
   而 `"" in 任何字符串` 恒真。改成等式（并要求非空）之后 W12 当场被抓住，
   电池从 12/13 变 **13/13**。这条留在这里的形状值得记：
   **包含式断言对"字段被清空"这类变异是天然盲的**；
   而"没有读者"本身也要靠撤销臂才现形——`--emit-register` 在仓库里躺了 3 片，
   `grep` 只有脚本自己提到它。
6. **W13 也翻了同样一次**：臂表原文 `"line": c["line"],` 在靶文件里命中 **2** 次
   （:261 软门、:274 「无人守」）。派单时按"恰好一次"预数的闸门把它拦在一支都没跑（退 7），
   执行方遂把锚点**收窄到软门那一处**继续跑——于是 13/13 的读数里，"无人守"的指位
   其实从没被撤过。本轮把它扩成两处一起撤（`pairs()` 本就支持一支多编辑），
   并给「无人守」补上 `assert unwatched["line"] == 8` 的常驻断言：
   现在 W13 被两条用例各抓一处（13 臂、15 处编辑、13/13 全杀）。
   **教训形状**：锚点命中数不为 1 时，"收窄锚点"是把臂改弱来迁就读数；
   正确动作是**把每一处都撤一遍**，并问"这一处有读者吗"。

## 四、已知边界

1. 命令仍按文本去重 ⇒ `line` 报的是**第一次出现**那一处；同一条命令在 13 个 job 里各有一行，
   册面只钉一个位。要逐 job 指位得把分母从"命令"换成"(job, 命令)"，那是另一次口径改动。
2. 行号只在 `run` 是**字面块或内联标量**时准；`run: >-` 折叠标量会把多行并成一行，
   偏移不再 1:1（本仓 ci.yml 现读 0 处折叠标量）。这一档**已做成常驻用例**：
   喂一个 `run: >-` 折叠标量，`ci_commands` 会给 `run_mark_unmatched` 前提诊断、
   该条 `line` 记 0、`main()` 退 2——不是给一个错行号，也不是静默读成"没有问题"。
   （我第一版拿"带引号的多空格标量"造这一格，结果匹配**成功**：引号标量的值仍逐字包含在
   文件行里，那条用例根本读不到"定不到"这一档。换折叠标量才真造得出来。）
3. `&&` / `for` 复合行**不拆**：粒度保持"一行一条"，因为 GitHub 就是以行为单位跑、
   `set -e` 下任一非零即红——比 runner 更细的粒度会造出 runner 不认的账。
4. 消费表侧没变：`--emit-register` 现在多写 `line_text_at_emit_time` /
   `soft_declared_at_emit_time` 两个取证字段，但对 kind 已是 consumed/ci-only 的条目
   照旧**剥掉** `line_at_emit_time`（防止把一次性行号钉成永久断言）。
5. `scripts/` 整体仍不在 CI 的 ruff 面内（第 93 片 §四.7 那条 643 条现读未清）。
   本片顺带修的 `SIM102` 就是这条缺口自己冒出来的证据：它在许可证门禁里躺了一整片，
   直到本轮专门去扫 `scripts/ci_surface_census.py` 与 `scripts/dependency_license_gate.py` 才现形。

## 五、认证读数（收口时填）

```
（待收口链写入：BIND / GATE / CV / -b 复算 / 全量 collected / 电池 杀-活-注入无效）
```
