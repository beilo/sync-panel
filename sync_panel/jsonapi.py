"""JSON API 层 — 给 React/Tauri UI 用的结构化接口。

引擎逻辑零改动: 这里只做编排 + 序列化。
所有函数返回纯 dict (可直接 json.dumps)。

设计要点:
- 文件树永远只展示 canonical (shared-skills / shared-rules), 不浏览 target。
- read 只允许读 canonical 根内文件 (防 UI 传任意路径越权读系统文件)。
- plan: dry-run, 不写盘; apply: 重新算 plan 再执行 (不信任前端旧 plan, 防 TOCTOU)。
- target status: 从同一份 plan 过滤出该 target 的条目, 不独立浏览 target 目录。
"""

from __future__ import annotations

import os
from pathlib import Path

from .config import Config, SKILL_TOOLS, TOOL_AGENTS, TOOL_CODEX, default_config
from .engine import BackupFailed, SyncEngine
from .model import Plan


# ---------------------------------------------------------------- 文件树

def _tree_node(path: Path, root: Path) -> dict:
    """递归构造文件树节点。symlink 不跟随 (标记 is_link)。

    rel: 相对 root 的路径, 作为 read 的安全标识 (UI 回传它, 不回传绝对路径)。
    """
    is_link = path.is_symlink()
    # is_dir 对指向目录的链接也 True; 但树里链接不展开 (canonical 内不应有链接)
    is_dir = path.is_dir() and not is_link
    node: dict = {
        "name": path.name,
        "rel": str(path.relative_to(root)),
        "is_dir": is_dir,
        "is_link": is_link,
    }
    if is_dir:
        children = []
        for child in sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name)):
            if child.name.startswith("."):
                continue  # dot 条目 out of scope
            children.append(_tree_node(child, root))
        node["children"] = children
    return node


def get_tree(cfg: Config) -> dict:
    """返回 shared-skills + shared-rules 两棵只读树。"""
    roots = []
    for label, root in (("shared-skills", cfg.shared_skills),
                        ("shared-rules", cfg.shared_rules)):
        if root.exists():
            node = _tree_node(root, root)
            node["name"] = label
            roots.append(node)
        else:
            roots.append({"name": label, "rel": "", "is_dir": True,
                         "is_link": False, "children": []})
    return {"roots": roots}


# ---------------------------------------------------------------- 文件预览

class PathDenied(Exception):
    """请求路径越出 canonical 根 — 拒绝读取。"""


def _resolve_within(cfg: Config, which: str, rel: str) -> Path:
    """把 (which, rel) 解析成 canonical 根内的绝对路径, 越界则抛 PathDenied。

    which: 'shared-skills' | 'shared-rules' — 决定根。
    rel: 相对根的路径。realpath 后必须仍在根内 (防 ../ 逃逸 + 符号链接逃逸)。
    """
    roots = {"shared-skills": cfg.shared_skills, "shared-rules": cfg.shared_rules}
    root = roots.get(which)
    if root is None:
        raise PathDenied(f"未知根: {which}")
    candidate = (root / rel)
    real = os.path.realpath(candidate)
    root_real = os.path.realpath(root)
    if real != root_real and not real.startswith(root_real + os.sep):
        raise PathDenied(f"路径越界: {rel}")
    return Path(real)


def read_file(cfg: Config, which: str, rel: str, max_bytes: int = 1_000_000) -> dict:
    """读 canonical 内文件内容 (只读预览)。

    越界抛 PathDenied; 目录/不存在返回 error 字段。
    超过 max_bytes 截断并标记 truncated。
    """
    path = _resolve_within(cfg, which, rel)
    if not path.exists():
        return {"path": str(path), "error": "文件不存在"}
    if path.is_dir():
        return {"path": str(path), "error": "是目录, 非文件"}
    raw = path.read_bytes()
    truncated = len(raw) > max_bytes
    raw = raw[:max_bytes]
    try:
        content = raw.decode("utf-8")
        is_binary = False
    except UnicodeDecodeError:
        content = ""
        is_binary = True
    return {
        "path": str(path),
        "content": content,
        "is_binary": is_binary,
        "truncated": truncated,
        "size": path.stat().st_size,
    }


# ---------------------------------------------------------------- plan / apply

def build_plan_dict(cfg: Config, timestamp: str) -> dict:
    """dry-run plan, 不写盘。含 dst_realpath / overlaps_canonical 标注。"""
    engine = SyncEngine(cfg, timestamp)
    plan = engine.build_plan()
    return plan.to_dict(canonical_root=cfg.workspace)


def apply_sync(cfg: Config, timestamp: str) -> dict:
    """真执行。重新算 plan 再执行 (不信任前端旧 plan, 防 TOCTOU)。

    返回 {plan, result} 或 {error} (备份失败 stop)。
    """
    engine = SyncEngine(cfg, timestamp)
    plan = engine.build_plan()  # 重算, 以当前文件系统为准
    plan_dict = plan.to_dict(canonical_root=cfg.workspace)
    try:
        result = engine.execute(plan, apply=True)
    except BackupFailed as e:
        return {"plan": plan_dict, "error": f"备份失败, 已停止 (未替换任何真实文件): {e}"}
    return {"plan": plan_dict, "result": result.to_dict()}


# ---------------------------------------------------------------- target 状态

AGENT_SKILLS_TARGET = "agent-skills"


def _agent_skill_items(cfg: Config, plan: Plan) -> list[dict]:
    """Agent Skills 视图只展示 ~/.agents/skills; Codex 官方也读取这个位置。"""
    items: list[dict] = []
    for a in plan.actions:
        if a.tool != TOOL_AGENTS:
            continue
        item = a.to_dict(canonical_root=cfg.workspace)
        item["tool"] = AGENT_SKILLS_TARGET
        items.append(item)
    return items


def target_status(cfg: Config, timestamp: str, target: str) -> dict:
    """某 target 的同步状态: 从 plan 过滤条目, 不独立浏览 target 目录。"""
    if target not in (*SKILL_TOOLS, AGENT_SKILLS_TARGET, TOOL_CODEX):
        return {"error": f"未知 target: {target}"}
    engine = SyncEngine(cfg, timestamp)
    plan = engine.build_plan()
    if target == AGENT_SKILLS_TARGET:
        items = _agent_skill_items(cfg, plan)
    else:
        items = [
            a.to_dict(canonical_root=cfg.workspace)
            for a in plan.actions
            if a.tool == target
        ]
    return {"target": target, "items": items, "count": len(items)}
