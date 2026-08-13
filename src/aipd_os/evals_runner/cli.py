"""评估 CLI。

用法：
    python -m aipd_os.evals_runner.cli run --evals evals/evals.json \
        --provider fake --out <dir> [--version 5.0.0] [--threshold 0.1] [--baseline <dir>]

``--provider fake`` 使用确定性脚本化假实现；``--provider model`` 使用真实模型端点
（需配置 AIPD_EVAL_MODEL_ENDPOINT）。提供 ``--baseline`` 时按分数下降阈值做回归门禁，
若任一 case 下降超过 ``--threshold`` 则以非零退出码结束。
"""

from __future__ import annotations

import argparse
import sys

from aipd_os import __version__ as _PKG_VERSION
from aipd_os.evals_runner.completion import EnvCompletionProvider
from aipd_os.evals_runner.registry import load_cases
from aipd_os.evals_runner.runner import EvalRunner, build_report
from aipd_os.evals_runner.versioning import (
    load_baseline,
    save_eval_report,
    should_block_release,
)


def _make_provider(provider: str):
    if provider in ("model", "real-model"):
        return EnvCompletionProvider()
    if provider in ("fake", "deterministic-fixture", "contract-test"):
        return None  # EvalRunner 默认构造 RecordedCompletionProvider（deterministic-fixture）
    if provider == "pure-contract":
        raise SystemExit("pure-contract 由实际应用代码驱动，不通过对话 provider 运行")
    raise SystemExit(
        f"未知 provider: {provider}（可选 fake / deterministic-fixture / contract-test "
        "/ model / real-model / pure-contract，其中 fake 为 deterministic-fixture 的别名）"
    )


def _print_report(report: dict) -> None:
    summary = report.get("summary", {})
    mb = summary.get("model_behavior", {})
    fb = summary.get("fixture_behavior", {})
    print(f"评估版本: {report.get('version')}  模型: {report.get('model_version')}")
    print(
        f"总计 {summary.get('passed', 0)}/{summary.get('total', 0)}  外部/跳过 "
        f"{summary.get('external', 0)}"
    )
    print(
        f"  模型行为通过率: {mb.get('passed', 0)}/{mb.get('total', 0)} "
        f"({mb.get('pass_rate', 0.0)})  [排除夹具]"
    )
    print(
        f"  夹具(contract-test)通过率: {fb.get('passed', 0)}/{fb.get('total', 0)} "
        f"({fb.get('pass_rate', 0.0)})  [仅供夹具回归，非真实模型通过率]"
    )
    for r in report.get("results", []):
        flag = "PASS" if r.get("passed") else "FAIL"
        ext = " [external]" if "external" in r.get("failure_type", []) else ""
        cat = r.get("provider_category", "?")
        print(f"  [{flag}]{ext} {r['case_id']}  cat={cat} score={r['score']}  "
              f"grader={r.get('grader')}  {r.get('failure_type')}")


def cmd_run(args: argparse.Namespace) -> int:
    cases = load_cases(args.evals)
    provider = _make_provider(args.provider)
    runner = EvalRunner(provider=provider, version=args.version)
    results = runner.run(cases, out_dir=args.out, report_version=args.version)
    report = build_report(results, version=args.version)
    save_eval_report(report, args.out, version=args.version)
    _print_report(report)

    if args.baseline:
        baseline = load_baseline(args.baseline, args.version)
        gate = should_block_release(report, baseline, threshold=args.threshold)
        print(f"回归门禁: {gate['reason']}")
        if gate["blocked"]:
            print(f"阻塞发布：{gate['reason']}")
            return 1
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aipd_os.evals_runner.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("run", help="运行行为评估")
    p.add_argument("--evals", required=True, help="evals/evals.json 路径")
    p.add_argument(
        "--provider",
        choices=["fake", "deterministic-fixture", "contract-test",
                 "model", "real-model", "pure-contract"],
        default="fake",
        help="fake/deterministic-fixture/contract-test 为夹具；model/real-model 为真实端点",
    )
    p.add_argument("--out", required=True, help="报告输出目录")
    p.add_argument("--version", default=_PKG_VERSION, help="评估版本号")
    p.add_argument("--threshold", type=float, default=0.1, help="允许的最大分数下降")
    p.add_argument("--baseline", default=None, help="基线目录（用于回归门禁）")
    p.set_defaults(func=cmd_run)
    return parser


def main(argv: list | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
