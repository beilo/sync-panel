"""Plan / 动作 / 结果 数据模型。

sync 先生成 Plan (一组 PlanAction), 再执行。dry-run 只打印 Plan。
真实执行后产生 SyncResult。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class ActionKind(str, Enum):
    """单条计划动作类型。"""

    COLLECT = "collect"          # 把 target 内容复制进 canonical (canonical 不存在)
    MIGRATE = "migrate"          # 较新版本迁移进 canonical, 旧 canonical 备份
    BACKUP = "backup"            # 备份将被替换的真实文件/目录
    LINK = "link"               # 创建 symlink: target -> canonical
    RELINK = "relink"           # 替换错误/损坏的 symlink
    REPLACE = "replace"         # 备份后用 symlink 替换真实文件/目录
    SKIP_SYNCED = "skip"        # 已是正确链接, 跳过
    MKDIR = "mkdir"             # 创建缺失的固定目录
    CONVERT_ROOT_LINK = "convert_root_link"  # 整目录链接拆成逐项链接
    ERROR = "error"             # 需人工处理的错误


# 哪些动作会触及"真实文件/目录" (需要确认 + 必须先备份成功)
DESTRUCTIVE = frozenset({ActionKind.REPLACE, ActionKind.MIGRATE, ActionKind.CONVERT_ROOT_LINK})


@dataclass
class PlanAction:
    """一条计划动作。

    src/dst 含义随 kind 变化, message 给人读。
    requires_real_replace=True 表示会替换一个真实 (非链接) 文件/目录。
    """

    kind: ActionKind
    name: str                       # skill 名 / rule 文件名, 供分组展示
    tool: str | None                # 归属工具 (备份分组用)
    src: Path | None = None
    dst: Path | None = None
    backup_path: Path | None = None
    message: str = ""
    requires_real_replace: bool = False

    def describe(self) -> str:
        arrow = ""
        if self.src and self.dst:
            arrow = f"  {self.src} -> {self.dst}"
        elif self.dst:
            arrow = f"  {self.dst}"
        flag = " [REAL-REPLACE]" if self.requires_real_replace else ""
        return f"[{self.kind.value}] {self.name}{flag}{arrow} {self.message}".rstrip()

    def to_dict(self, canonical_root: Path | None = None) -> dict:
        """序列化给 UI。

        显式暴露 dst 的 realpath (事故教训: dry-run 文本没暴露 target 解析到
        canonical 自身的重叠)。overlaps_canonical=True 表示该 target resolve 后
        落在 canonical 根内 — UI 应标红告警, 此类条目执行会自指环。
        """
        dst_realpath = None
        overlaps_canonical = False
        if self.dst is not None:
            # 不跟随到不存在路径报错: 用 realpath (不存在时返回规范化路径本身)
            dst_realpath = os.path.realpath(self.dst)
            if canonical_root is not None:
                root_real = os.path.realpath(canonical_root)
                overlaps_canonical = (
                    dst_realpath == root_real
                    or dst_realpath.startswith(root_real + os.sep)
                )
        return {
            "kind": self.kind.value,
            "name": self.name,
            "tool": self.tool,
            "src": str(self.src) if self.src else None,
            "dst": str(self.dst) if self.dst else None,
            "dst_realpath": dst_realpath,
            "overlaps_canonical": overlaps_canonical,
            "backup_path": str(self.backup_path) if self.backup_path else None,
            "message": self.message,
            "requires_real_replace": self.requires_real_replace,
        }


@dataclass
class Plan:
    """整次 sync 的计划。collect 在前, map 在后。"""

    timestamp: str
    actions: list[PlanAction] = field(default_factory=list)

    def add(self, action: PlanAction) -> None:
        self.actions.append(action)

    @property
    def real_replacements(self) -> list[PlanAction]:
        return [a for a in self.actions if a.requires_real_replace]

    @property
    def has_real_replacements(self) -> bool:
        return bool(self.real_replacements)

    def of_kind(self, *kinds: ActionKind) -> list[PlanAction]:
        ks = set(kinds)
        return [a for a in self.actions if a.kind in ks]

    def to_dict(self, canonical_root: Path | None = None) -> dict:
        return {
            "timestamp": self.timestamp,
            "actions": [a.to_dict(canonical_root) for a in self.actions],
            "has_real_replacements": self.has_real_replacements,
            "real_replacement_count": len(self.real_replacements),
            # 重叠 canonical 的 target 数量 (事故防护指标)
            "overlap_count": sum(
                1 for a in self.actions
                if a.to_dict(canonical_root)["overlaps_canonical"]
            ),
        }


@dataclass
class SyncResult:
    """执行后的汇总结果。"""

    timestamp: str
    collected: list[PlanAction] = field(default_factory=list)
    migrated: list[PlanAction] = field(default_factory=list)
    links_created: list[PlanAction] = field(default_factory=list)
    links_repaired: list[PlanAction] = field(default_factory=list)
    already_correct: list[PlanAction] = field(default_factory=list)
    backups: list[PlanAction] = field(default_factory=list)
    replaced: list[PlanAction] = field(default_factory=list)
    root_links_converted: list[PlanAction] = field(default_factory=list)
    errors: list[PlanAction] = field(default_factory=list)

    def summary_lines(self) -> list[str]:
        return [
            f"已收集 (collected):     {len(self.collected)}",
            f"已迁移较新版本 (migrated): {len(self.migrated)}",
            f"整目录链接已转换 (root converted): {len(self.root_links_converted)}",
            f"新建链接 (links created):  {len(self.links_created)}",
            f"修复链接 (links repaired): {len(self.links_repaired)}",
            f"已正确链接 (already ok):   {len(self.already_correct)}",
            f"备份 (backups):           {len(self.backups)}",
            f"替换旧版/真实文件 (replaced): {len(self.replaced)}",
            f"错误 (errors):            {len(self.errors)}",
        ]

    def to_dict(self) -> dict:
        """序列化给 UI。counts 供概览, errors 给明细 (需人工处理)。"""
        return {
            "timestamp": self.timestamp,
            "counts": {
                "collected": len(self.collected),
                "migrated": len(self.migrated),
                "root_links_converted": len(self.root_links_converted),
                "links_created": len(self.links_created),
                "links_repaired": len(self.links_repaired),
                "already_correct": len(self.already_correct),
                "backups": len(self.backups),
                "replaced": len(self.replaced),
                "errors": len(self.errors),
            },
            "errors": [a.to_dict() for a in self.errors],
            "backups": [a.to_dict() for a in self.backups],
        }
