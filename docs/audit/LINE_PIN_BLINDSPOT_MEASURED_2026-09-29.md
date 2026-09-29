# 行钉的静默漂移：第 102 片量的三个分母（2026-09-29）

这片偿 lint 债时把 26 个 `scripts/*.py` 的行结构改了（import 排序 + 拆一行多 import）。
按记忆里那条"改任何被别处按行号引用的文件之前，先把引用换成符号锚点"（第 84 片）去查账，
发现现有尺子查不出这类错位，于是先把分母量出来。**本文只记录读数与形状，不改判据。**

## 一、现有尺子在这件事上能看见什么

`scripts/doc_reference_census.py` 对 `file:NNN` 只有一条行号判据：`line > 文件行数`（`line_beyond_eof`）。
它的作用域里 `HISTORY = ("CHANGELOG.md", "docs/audit")` 这两类**只计数不判红**。
⇒ 两条推论：① 文件变长时行号仍"合法"，内容已经不是那一处 ⇒ 静默；
② 仓库里绝大多数行钉住在 `docs/audit/**`（历史取证件），本来就落在不判红的档里。

## 二、三个现算读数（先给"我自己那把临时尺"的更正，再给权威读数）

**第一版这张表写错过一格，按权威尺改回来了**：我一开始用自写的 `rglob(basename)` 匹配去数 live 面，
得到"live 面 0 处"，并且把 `docs/architecture/truth_architecture.md:164` 的 `state/db.py:1073`
读成"越界"。跑仓里那把同一问法的既有量具（`python scripts/doc_reference_census.py --json …`）现读：
live 面的裸行钉是 **11 处**，且 11 条**全部 `resolved`**——`state/db.py` 由量具解析到
`src/aipd_os/state/db.py`（真有 1073 行以上），是我按 basename 的 `rglob` 撞到了另一个同名文件。
⇒ 同一条规矩第二次生效：**借判据要连它的解析面一起借**，自写简版匹配会把"我算错了"读成"语料有缺陷"。

| 问的东西 | 权威读数（`doc_reference_census.py` 自报） | 量法 |
| --- | --- | --- |
| 全语料的行钉引用分档 | `line_beyond_eof` 10 处、`missing` 290、`elided` 89、`external` 177；**现状面缺陷 0 条**，**历史面缺陷 246 条（只报不判）** | 跑该量具 `--json docs/audit/s102/drc.json` |
| live 面（`LIVE` = README/SKILL + `LIVE_DIRS` = `docs/architecture`、`docs/contracts`、`references`）里的裸行钉 | **11 处**，全在 `docs/architecture/truth_architecture.md`，逐条 `resolved` | 用量具自己的 `_is_live()` 划面，再按 `(\S+):(\d+)` 取 |
| history 面（`CHANGELOG.md` + `docs/audit/**`）里的裸行钉 | **974 处**（语料共 212 个文档：live 47 / history 161 / 其余 4） | 同上，用 `_is_history()` |
| 指向本片改过的 28 个 `scripts/*.py` 的行钉 | **67 处全在 history 面**（越界 9 / 行号仍在文件行数内 58），live 面 0 处 | 对改动集按 basename 归并 |
| JSON 台账（含 `CI_SURFACE_REGISTER.json` 的 `cited_by`）里指向这批文件的行钉 | **0 处** | 对 `*.json` 同法匹配（排除 `report-*`、`releases/`、`.venv`） |
| 抽样：历史钉已经漂了多远 | `docs/audit/v5.4/phase4-manual-chain-audit.md:59-63` 钉 `manual_chain.py:146/147/130-137`，`grep -n` 现读真身在 `:193` / `:195` / `:134` ⇒ **约 47 行**，四轮门禁全绿 | 逐条 grep 符号名 |

## 三、由此定下的下一刀形状（第 103 片入口，任务 #32）

原设想"让 census 去核对行号处的内容"，在量完分母之后**不是首选**：
它要判红的对象 974 处里绝大多数落在历史证据文件里，而那些行号记录的是**当时**的盘——
按新判据会把它们集体判红（现状已经是"历史面 246 条只报不判"），或逼我改写取证件原文（更糟）。

改成两件事，成本与牙都由上表的分母定住：

1. **live 面立棘轮：不许写裸行钉**。判据吃 `_is_live()` 那 47 个文档，
   出现 `file.py:NNN` ⇒ 判红并要求改成符号锚（`file.py::函数名`）。
   **这一刀不是零成本，也不是橡皮章**：今天有 **11 条真原告**（`docs/architecture/truth_architecture.md`，
   逐条 `resolved` 但形状脆弱），要先把这 11 处换成符号锚——`docs/architecture/**` **参与发布哈希**，
   所以这 11 处改写必须赶在该片最后一次 `release_evidence.py` 之前定稿。
   反证极（证明这条闸有牙）：在临时语料的 live 形状文档里塞一行 `x.py:1` 必须开火，
   在 history 形状文档里塞同样的行必须沉默。
2. **history 面继续只报，但把"漂"这件事报出来**：新增聚合档 `line-pin-drift`，
   逐条比对"文档说的行号"与"该句符号锚现在所在行"，**只报计数与前 N 条样例**（974 处不能刷屏），
   进 `--json` 的 `buckets` 与那行自报。这样"漂了 47 行"以后由尺子说，而不是靠我手 grep 撞见。

两条都要配常驻用例两极（live 开火 / history 沉默）与电池收回臂，
且 `doc_reference_census` 的**归属档数与措辞是三处镜像**（`REGISTER_RULE` 被逐字抄进登记册、
README 面 ⑤ 那段、`entry_points()` docstring 与 `--self-test` 期望），改档数必须同批改并重跑
`--emit-register`——见项目记忆里的镜像清单与第 89/90 片那两条账。

## 四、本片为什么不顺手做

第 102 片的认证那一跑正在飞，而 `doc_reference_census.py` 与 `tests/test_doc_reference_census.py`
都在被哈希的面上（`scripts/`、`tests/`）——动它们等于作废那一跑（第 84 片实测烧过 10 分钟）。
读数与形状先落在这里，判据本身按上面两条在下一片立。
