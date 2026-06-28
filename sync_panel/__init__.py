"""AI Workspace 同步面板 — 核心 sync 引擎。

设计文档: docs/superpowers/specs/2026-06-22-ai-workspace-sync-panel-design.md

把 /Users/am/ai-workspace 作为全局 skills/rules 的唯一真相源,
再用 symlink 映射 Claude Code 与通用 Agent Skills；Codex skills 直接复用 ~/.agents/skills。
"""

from .config import Config, default_config
from .engine import SyncEngine
from .model import Plan, PlanAction, SyncResult

__all__ = [
    "Config",
    "default_config",
    "SyncEngine",
    "Plan",
    "PlanAction",
    "SyncResult",
]
