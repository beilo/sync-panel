"""Sync 引擎: 两阶段 collect -> map。

Plan 与执行分离:
- build_plan(): 只读扫描, 生成 Plan, 绝不写盘。
- execute(): 按 Plan 真正写盘 (apply=True), 否则 dry-run。

设计关键规则:
- correct symlink 视为已同步, 不当作 source, 不参与 latest 比较。
- latest 由最新 mtime 决定 (目录取内部最新)。
- incorrect symlink 若指向存在内容, 该内容参与比较, 较新则迁移进 canonical 并备份旧 canonical;
  随后修复链接。不扫描其同级目录。
- broken symlink 不跟随, 计划里报告, map 阶段修复。
- 替换真实文件/目录前必须先备份成功, 备份失败则 stop。
- 幂等: 重复运行不重复建链/不覆盖备份/不产生多余改动。
"""

from __future__ import annotations

import os
from pathlib import Path

from . import fsutil
from .config import Config
from .model import ActionKind, Plan, PlanAction, SyncResult


class BackupFailed(Exception):
    """备份失败 — 触发 stop, 不得继续替换真实文件。"""


class SyncEngine:
    def __init__(self, config: Config, timestamp: str):
        # timestamp 由调用方传入 (设计要求时间戳分组备份), 形如 20260622-201530
        self.cfg = config
        self.ts = timestamp

    # ---------------------------------------------------------------- 计划

    def build_plan(self) -> Plan:
        plan = Plan(timestamp=self.ts)
        self._plan_skills(plan)
        self._plan_rules(plan)
        return plan

    # ---- skills ----

    def _skill_target_is_canonical(self, tool: str) -> bool:
        """该 skill target 目录本身是否已是 canonical 根 (整目录级已同步)。

        例如 .agents/skills 是指向 shared-skills 的符号链接 -> 两者 resolve 同路径。
        此时逐条 map 会把 canonical 自己删掉再链向自己 (自指环)。
        必须整体跳过这种 target: 既不取它做源, 也不在它下面建逐条链接。
        """
        import os
        root = self.cfg.skill_targets[tool]
        if not root.exists():
            return False
        return os.path.realpath(root) == os.path.realpath(self.cfg.shared_skills)

    def _plan_skills(self, plan: Plan) -> None:
        cfg = self.cfg
        # 枚举所有 skill 名: canonical 已有的 + 各 target 里的真实/错链条目
        names = self._skill_names()
        # 目录级已同步的 target -> 计划转换为逐项链接目录
        convert_tools = {t for t in cfg.skill_targets if self._skill_target_is_canonical(t)}

        # 先为每个需转换的 tool 添加 CONVERT_ROOT_LINK 动作
        for tool in sorted(convert_tools):
            root = cfg.skill_targets[tool]
            plan.add(PlanAction(
                kind=ActionKind.CONVERT_ROOT_LINK,
                name=f".{tool}/skills",
                tool=tool,
                dst=root,
                message=f"整目录链接 -> 逐项链接目录 (unlink + mkdir + 逐项 ln)",
                requires_real_replace=True,
            ))

        for name in sorted(names):
            canonical = cfg.shared_skills / name
            # 收集该 skill 名在各 target 的候选源 (排除 correct link)
            candidates = self._skill_candidates(name)
            # canonical 此刻是否存在, 或本次计划会创建/迁移它 ->
            # map 阶段据此判断能否建链 (plan 阶段 canonical 尚未真正落盘)
            canonical_will_exist = canonical.exists()

            # ---- collect / migrate 决策 ----
            if not canonical.exists():
                # canonical 不存在: 取候选里 mtime 最新的复制进来
                best = self._pick_latest(candidates)
                if best is not None:
                    tool, src = best
                    plan.add(PlanAction(
                        kind=ActionKind.COLLECT, name=name, tool=tool, src=src,
                        dst=canonical, message="canonical 不存在, 收集最新版本",
                    ))
                    canonical_will_exist = True
            else:
                # canonical 已存在: 看有没有更新的候选 -> 迁移
                best = self._pick_latest(candidates)
                if best is not None:
                    tool, src = best
                    if fsutil.newest_mtime(src) > fsutil.newest_mtime(canonical):
                        bkp = cfg.backup_dir(self.ts, "_canonical") / "skills" / name
                        plan.add(PlanAction(
                            kind=ActionKind.MIGRATE, name=name, tool=tool, src=src,
                            dst=canonical, backup_path=bkp,
                            message="发现更新版本, 迁移进 canonical 并备份旧 canonical",
                            requires_real_replace=True,
                        ))

            # ---- map: 各 target 链接回 canonical ----
            for tool in cfg.skill_targets:
                entry = cfg.skill_targets[tool] / name
                if tool in convert_tools:
                    # 该 target 正在从整目录链接转换为逐项链接目录
                    # 转换后条目尚不存在, plan LINK (force, 因为 plan 时 entry
                    # 经 symlink 解析到 canonical 自身, 走 _plan_map_entry 会误判为 REPLACE)
                    if canonical_will_exist:
                        plan.add(PlanAction(
                            kind=ActionKind.LINK, name=name, tool=tool,
                            src=canonical, dst=entry,
                            message="转换后逐项建链",
                        ))
                else:
                    self._plan_map_entry(plan, name, tool, entry, canonical,
                                         kind="skills", canonical_will_exist=canonical_will_exist)

    def _skill_names(self) -> set[str]:
        """所有需处理的 skill 名集合。

        排除规则:
        - dot 前缀条目 (设计要求)。
        - 非目录条目: skill 必须是目录, 散文件 (如 wechat.zip) 不算 skill。
          注意 symlink 指向目录也算 (incorrect/correct link 仍是 skill 条目)。
        """
        cfg = self.cfg
        names: set[str] = set()
        if cfg.shared_skills.exists():
            for p in cfg.shared_skills.iterdir():
                if p.name.startswith(".") or not p.is_dir():
                    continue
                names.add(p.name)
        for tool, root in cfg.skill_targets.items():
            if not root.exists():
                continue
            if self._skill_target_is_canonical(tool):
                continue  # 该 target 即 canonical 根, 其条目就是 canonical 自身, 不重复枚举
            for p in root.iterdir():
                if p.name.startswith("."):
                    continue
                # is_dir() 对指向目录的 symlink 也返回 True; 散文件/断链被排除
                if not p.is_dir():
                    continue
                names.add(p.name)
        return names
        return names

    def _skill_candidates(self, name: str) -> list[tuple[str, Path]]:
        """返回 [(tool, 源路径)] 参与 latest 比较的候选。

        排除 correct link (已同步, 非 source)。
        incorrect link 若指向存在内容, 用其指向内容作为源。
        broken link 不作候选。
        真实文件/目录直接作为源。
        canonical 自身由调用处单独参与比较, 这里不含。
        """
        cfg = self.cfg
        out: list[tuple[str, Path]] = []
        canonical = cfg.shared_skills / name
        for tool, root in cfg.skill_targets.items():
            if self._skill_target_is_canonical(tool):
                continue  # target 即 canonical 根, 其条目就是 canonical, 不作独立源
            entry = root / name
            if not entry.exists() and not entry.is_symlink():
                continue
            if fsutil.is_correct_link(entry, canonical):
                continue  # 已同步, 跳过
            if entry.is_symlink():
                tgt = fsutil.link_target(entry)
                if tgt is None or not tgt.exists():
                    continue  # broken link, 不作候选 (map 阶段修复)
                if not fsutil.has_content(tgt):
                    continue  # 空内容不参与 latest 比较, 防覆盖
                out.append((tool, tgt))  # incorrect link -> 用指向内容
            else:
                if not fsutil.has_content(entry):
                    continue  # 空内容不参与 latest 比较, 防覆盖
                out.append((tool, entry))  # 真实文件/目录
        return out

    def _pick_latest(self, candidates: list[tuple[str, Path]]) -> tuple[str, Path] | None:
        """候选里取 mtime 最新的。空则 None。"""
        best: tuple[str, Path] | None = None
        best_m = -1.0
        for tool, src in candidates:
            m = fsutil.newest_mtime(src)
            if m > best_m:
                best_m = m
                best = (tool, src)
        return best

    # ---- rules ----

    def _plan_rules(self, plan: Plan) -> None:
        cfg = self.cfg
        # 跟踪计划后将存在的 canonical rule (已存在 或 本次会被初始化/迁移)
        will_exist: set[Path] = {
            rm.canonical for rm in cfg.rule_mappings if rm.canonical.exists()
        }
        # collect: 只从 initializes=True 的源初始化 canonical
        for rm in cfg.rule_mappings:
            name = rm.canonical.name
            if rm.initializes and not rm.canonical.exists():
                # 用有效源 (排除 correct link / broken / 空内容) 初始化
                src = self._rule_source(rm)
                if src is not None:
                    plan.add(PlanAction(
                        kind=ActionKind.COLLECT, name=name, tool=rm.tool,
                        src=src, dst=rm.canonical,
                        message="canonical rule 不存在, 从源初始化",
                    ))
                    will_exist.add(rm.canonical)

        # collect: initializes 源里若有更新真实内容 -> 迁移
        for rm in cfg.rule_mappings:
            if not rm.initializes or not rm.canonical.exists():
                continue
            if fsutil.is_correct_link(rm.target, rm.canonical):
                continue
            src = self._rule_source(rm)
            if src is None:
                continue
            if fsutil.newest_mtime(src) > fsutil.newest_mtime(rm.canonical):
                bkp = cfg.backup_dir(self.ts, "_canonical") / "rules" / rm.canonical.name
                plan.add(PlanAction(
                    kind=ActionKind.MIGRATE, name=rm.canonical.name, tool=rm.tool,
                    src=src, dst=rm.canonical, backup_path=bkp,
                    message="rule 源更新, 迁移进 canonical 并备份旧 canonical",
                    requires_real_replace=True,
                ))

        # map: 每个 rule target 链接回 canonical
        for rm in cfg.rule_mappings:
            self._plan_map_entry(
                plan, rm.canonical.name, rm.tool, rm.target, rm.canonical, kind="rules",
                canonical_will_exist=rm.canonical in will_exist,
            )

    def _rule_source(self, rm) -> Path | None:
        """rule target 的有效源: 真实文件直接用; incorrect link 用指向内容; broken/correct/空 不用。

        空内容 (0字节) 不作源 -> 防止空文件靠 mtime 覆盖有内容的 canonical。
        """
        if not rm.target.exists() and not rm.target.is_symlink():
            return None
        if fsutil.is_correct_link(rm.target, rm.canonical):
            return None
        if rm.target.is_symlink():
            tgt = fsutil.link_target(rm.target)
            src = tgt if (tgt and tgt.exists()) else None
        else:
            src = rm.target
        if src is None or not fsutil.has_content(src):
            return None
        return src

    # ---- 通用 map 计划 ----

    def _plan_map_entry(
        self, plan: Plan, name: str, tool: str | None,
        entry: Path, canonical: Path, kind: str, canonical_will_exist: bool,
    ) -> None:
        """为单个 target 条目生成 map 动作。

        canonical 既不存在、本次也不会创建时不建链 (没有可指向的真相), 跳过。
        """
        if not canonical_will_exist:
            return

        if fsutil.is_correct_link(entry, canonical):
            plan.add(PlanAction(
                kind=ActionKind.SKIP_SYNCED, name=name, tool=tool, dst=entry,
                message="已是正确链接",
            ))
            return

        if entry.is_symlink():
            if fsutil.is_broken_link(entry):
                old = fsutil.link_target(entry)
                plan.add(PlanAction(
                    kind=ActionKind.RELINK, name=name, tool=tool,
                    src=canonical, dst=entry,
                    message=f"损坏链接 (原指向 {old}), 修复",
                ))
            else:
                old = fsutil.link_target(entry)
                plan.add(PlanAction(
                    kind=ActionKind.RELINK, name=name, tool=tool,
                    src=canonical, dst=entry,
                    message=f"错误链接 (原指向 {old}), 修复",
                ))
            return

        if not entry.exists():
            plan.add(PlanAction(
                kind=ActionKind.LINK, name=name, tool=tool,
                src=canonical, dst=entry, message="缺失, 创建链接",
            ))
            return

        # 真实文件/目录 -> 备份后替换
        bkp = self.cfg.backup_dir(self.ts, tool or "_unknown") / kind / name
        plan.add(PlanAction(
            kind=ActionKind.REPLACE, name=name, tool=tool,
            src=canonical, dst=entry, backup_path=bkp,
            message="真实文件/目录, 备份后替换为链接",
            requires_real_replace=True,
        ))

    # ---------------------------------------------------------------- 执行

    def execute(self, plan: Plan, apply: bool) -> SyncResult:
        """按 plan 执行。apply=False 为 dry-run (不写盘)。

        替换真实文件/目录前必须备份成功, 否则抛 BackupFailed 并 stop。
        """
        result = SyncResult(timestamp=self.ts)
        for a in plan.actions:
            try:
                self._exec_one(a, apply, result)
            except BackupFailed:
                raise
            except OSError as e:
                err = PlanAction(
                    kind=ActionKind.ERROR, name=a.name, tool=a.tool, dst=a.dst,
                    message=f"{a.kind.value} 失败: {e}",
                )
                result.errors.append(err)
        return result

    def _exec_one(self, a: PlanAction, apply: bool, result: SyncResult) -> None:
        k = a.kind
        if k == ActionKind.COLLECT:
            fsutil.copy_into(a.src, a.dst, apply)
            result.collected.append(a)

        elif k == ActionKind.MIGRATE:
            # 先备份旧 canonical, 再覆盖
            self._safe_backup(a, apply, result)
            fsutil.copy_into(a.src, a.dst, apply)
            result.migrated.append(a)

        elif k == ActionKind.CONVERT_ROOT_LINK:
            # unlink 整目录链接, 创建真实空目录 (逐项 LINK 随后填充)
            fsutil.convert_root_to_dir(a.dst, apply)
            result.root_links_converted.append(a)

        elif k == ActionKind.LINK:
            fsutil.make_symlink(a.dst, a.src, apply)
            result.links_created.append(a)

        elif k == ActionKind.RELINK:
            fsutil.make_symlink(a.dst, a.src, apply)
            result.links_repaired.append(a)

        elif k == ActionKind.REPLACE:
            # 先备份真实文件, 成功后替换为链接
            self._safe_backup(a, apply, result)
            fsutil.make_symlink(a.dst, a.src, apply)
            result.replaced.append(a)

        elif k == ActionKind.SKIP_SYNCED:
            result.already_correct.append(a)

        elif k == ActionKind.ERROR:
            result.errors.append(a)

    def _safe_backup(self, a: PlanAction, apply: bool, result: SyncResult) -> None:
        """备份, 失败则抛 BackupFailed (停止, 不替换真实文件)。

        两种场景备份对象都是 a.dst 处的现有内容:
        MIGRATE 备份旧 canonical; REPLACE 备份 target 真实文件。
        """
        src = a.dst
        try:
            fsutil.backup(src, a.backup_path, apply)
        except OSError as e:
            raise BackupFailed(f"备份失败 {src} -> {a.backup_path}: {e}") from e
        # 记录一条备份动作
        result.backups.append(PlanAction(
            kind=ActionKind.BACKUP, name=a.name, tool=a.tool,
            src=src, dst=a.backup_path, message="已备份",
        ))
