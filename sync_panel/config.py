"""固定路径配置。

设计要求路径全部固定 (fixed)。这里把它们集中成一个可注入的 Config,
真实运行用 default_config(), 测试时用临时目录构造, 避免碰到真实 HOME。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


# 工具标识 — 也用作 backup 分组名 (codex / claude-code / agents)
TOOL_CODEX = "codex"
TOOL_CLAUDE = "claude-code"
TOOL_AGENTS = "agents"

# 三个 skill target 工具顺序固定, latest-version 比较时也按此顺序遍历
SKILL_TOOLS = (TOOL_CODEX, TOOL_CLAUDE, TOOL_AGENTS)


@dataclass(frozen=True)
class RuleMapping:
    """一条 rule 映射: target 文件 -> canonical 文件。

    initializes: 该 target 是否在 collect 阶段用来初始化 canonical 内容。
    设计里 .claude/AGENTS.md 是 map-only (initializes=False)。
    tool: 备份分组归属 (None 表示不产生 rule 备份分组, 如 map-only 项)。
    """

    target: Path
    canonical: Path
    initializes: bool
    tool: str | None


@dataclass(frozen=True)
class Config:
    workspace: Path                     # /Users/am/ai-workspace
    shared_skills: Path                 # canonical skills 根
    shared_rules: Path                  # canonical rules 根
    backups_root: Path                  # .sync-backups 根
    # 工具名 -> 该工具的 skills 目录 (固定路径)
    skill_targets: dict[str, Path]
    # rule 映射表
    rule_mappings: tuple[RuleMapping, ...]

    def backup_dir(self, timestamp: str, tool: str) -> Path:
        """某次 sync、某工具的备份根目录: .sync-backups/<ts>/<tool>/"""
        return self.backups_root / timestamp / tool


def default_config(home: Path | None = None) -> Config:
    """真实环境配置。home 默认 ~ , 测试可传临时目录。"""
    home = home or Path.home()
    workspace = home / "ai-workspace"
    shared_skills = workspace / "shared-skills"
    shared_rules = workspace / "shared-rules"

    canonical_claude = shared_rules / "CLAUDE.md"
    canonical_agents = shared_rules / "AGENTS.md"

    rule_mappings = (
        # .claude/CLAUDE.md <-> shared-rules/CLAUDE.md (初始化 canonical)
        RuleMapping(
            target=home / ".claude" / "CLAUDE.md",
            canonical=canonical_claude,
            initializes=True,
            tool=TOOL_CLAUDE,
        ),
        # .codex/AGENTS.md <-> shared-rules/AGENTS.md (初始化 canonical)
        RuleMapping(
            target=home / ".codex" / "AGENTS.md",
            canonical=canonical_agents,
            initializes=True,
            tool=TOOL_CODEX,
        ),
        # .claude/AGENTS.md -> shared-rules/AGENTS.md (map-only, 不初始化)
        RuleMapping(
            target=home / ".claude" / "AGENTS.md",
            canonical=canonical_agents,
            initializes=False,
            tool=None,
        ),
    )

    return Config(
        workspace=workspace,
        shared_skills=shared_skills,
        shared_rules=shared_rules,
        backups_root=workspace / ".sync-backups",
        skill_targets={
            TOOL_CODEX: home / ".codex" / "skills",
            TOOL_CLAUDE: home / ".claude" / "skills",
            TOOL_AGENTS: home / ".agents" / "skills",
        },
        rule_mappings=rule_mappings,
    )
