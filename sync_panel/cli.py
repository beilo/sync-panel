"""CLI 入口: 生成 plan -> 展示 -> (确认) -> 执行。

用法:
  python -m sync_panel.cli                 # dry-run, 只打印 plan
  python -m sync_panel.cli --apply         # 真执行 (替换真实文件需确认)
  python -m sync_panel.cli --apply --yes   # 真执行, 跳过交互确认
  python -m sync_panel.cli --home /tmp/x   # 用指定 HOME (测试/演练)

默认 dry-run。设计要求: 若 plan 会替换任何真实文件/目录, 执行前必须展示受影响路径并确认。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from .config import default_config
from .engine import BackupFailed, SyncEngine
from . import jsonapi
from .model import ActionKind, Plan, SyncResult


def _timestamp() -> str:
    # 形如 20260622-201530
    return time.strftime("%Y%m%d-%H%M%S", time.localtime())


def print_plan(plan: Plan) -> None:
    print(f"\n=== Sync Plan ({plan.timestamp}) ===")
    if not plan.actions:
        print("  (无动作 — 已全部同步)")
        return
    # 按工具分组打印
    for a in plan.actions:
        print("  " + a.describe())

    reals = plan.real_replacements
    if reals:
        print(f"\n  ⚠ 将替换 {len(reals)} 个真实文件/目录 (会先备份):")
        for a in reals:
            print(f"      - {a.dst}")


def print_result(result: SyncResult, applied: bool) -> None:
    head = "执行结果" if applied else "Dry-run 预览结果"
    print(f"\n=== {head} ===")
    for line in result.summary_lines():
        print("  " + line)
    if result.errors:
        print("\n  错误明细:")
        for e in result.errors:
            print(f"    - {e.describe()}")


def confirm(prompt: str) -> bool:
    try:
        ans = input(f"{prompt} [y/N] ").strip().lower()
    except EOFError:
        return False
    return ans in ("y", "yes")


def _emit(obj) -> int:
    """打印 JSON 到 stdout (UI 解析用)。"""
    json.dump(obj, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


def _run_json(args) -> int:
    """JSON 子命令分发 — 给 React/Tauri UI。每次调用出一次 JSON 即退出。"""
    home = Path(args.home).expanduser() if args.home else None
    cfg = default_config(home)
    ts = _timestamp()
    cmd = args.json_cmd

    if cmd == "tree":
        return _emit(jsonapi.get_tree(cfg))
    if cmd == "read":
        try:
            return _emit(jsonapi.read_file(cfg, args.which, args.rel))
        except jsonapi.PathDenied as e:
            return _emit({"error": str(e)})
    if cmd == "plan":
        return _emit(jsonapi.build_plan_dict(cfg, ts))
    if cmd == "apply":
        return _emit(jsonapi.apply_sync(cfg, ts))
    if cmd == "status":
        return _emit(jsonapi.target_status(cfg, ts, args.target))
    return _emit({"error": f"未知子命令: {cmd}"})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AI Workspace 同步面板 (CLI)")
    parser.add_argument("--apply", action="store_true", help="真正执行 (默认 dry-run)")
    parser.add_argument("--yes", action="store_true", help="跳过交互确认")
    parser.add_argument("--home", type=str, default=None, help="覆盖 HOME 路径 (测试/演练)")

    # JSON 子命令 (UI 用); 无子命令时走原文本 CLI
    sub = parser.add_subparsers(dest="json_cmd")
    sub.add_parser("tree", help="输出 canonical 文件树 JSON")
    p_read = sub.add_parser("read", help="读 canonical 文件内容 JSON")
    p_read.add_argument("--which", required=True, choices=["shared-skills", "shared-rules"])
    p_read.add_argument("--rel", required=True, help="相对根的路径")
    sub.add_parser("plan", help="输出 dry-run plan JSON")
    sub.add_parser("apply", help="真执行并输出结果 JSON")
    p_status = sub.add_parser("status", help="输出某 target 状态 JSON")
    # agent-skills 是 UI 视图; codex 只保留 rule 状态调试, 不再管理 ~/.codex/skills。
    p_status.add_argument("--target", required=True, choices=["agent-skills", "codex", "claude-code", "agents"])

    args = parser.parse_args(argv)

    if args.json_cmd:
        return _run_json(args)

    home = Path(args.home).expanduser() if args.home else None
    cfg = default_config(home)
    engine = SyncEngine(cfg, _timestamp())

    plan = engine.build_plan()
    print_plan(plan)

    if not args.apply:
        # dry-run: 模拟执行得到预览汇总, 不写盘
        result = engine.execute(plan, apply=False)
        print_result(result, applied=False)
        print("\n(dry-run — 未改动文件系统。加 --apply 真执行。)")
        return 0

    # --apply: 若有真实替换, 需确认
    if plan.has_real_replacements and not args.yes:
        if not confirm("以上真实文件/目录将被备份后替换, 确认继续?"):
            print("已取消。")
            return 1

    try:
        result = engine.execute(plan, apply=True)
    except BackupFailed as e:
        print(f"\n✗ 备份失败, 已停止 (未替换任何真实文件): {e}", file=sys.stderr)
        return 2

    print_result(result, applied=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
