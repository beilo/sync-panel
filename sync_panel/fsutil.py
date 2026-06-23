"""文件系统辅助。

集中处理 symlink 判定、mtime 比较、复制、备份。
全部接受一个 `apply: bool` —— dry-run 时不真正写盘, 只返回将发生的事实判断。
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path


def is_symlink(p: Path) -> bool:
    return p.is_symlink()


def link_target(p: Path) -> Path | None:
    """返回 symlink 指向的绝对路径 (未必存在)。非链接返回 None。"""
    if not p.is_symlink():
        return None
    raw = Path(os.readlink(p))
    if not raw.is_absolute():
        raw = (p.parent / raw)
    # 不 resolve() 全链, 只规范化, 避免跟随到不存在路径报错
    return Path(os.path.normpath(raw))


def is_correct_link(p: Path, canonical: Path) -> bool:
    """p 是否已是指向 canonical 的正确 symlink。

    用 realpath 规范化两边: 跟随父目录中的符号链接 (如 macOS 的 /tmp -> /private/tmp),
    保证 link_target 与 canonical 在同一坐标系比较。
    """
    if not p.is_symlink():
        return False
    raw = Path(os.readlink(p))
    if not raw.is_absolute():
        raw = p.parent / raw
    left = os.path.realpath(raw)
    right = os.path.realpath(canonical)
    return left == right


def is_broken_link(p: Path) -> bool:
    """损坏 symlink: 是链接但指向不存在。"""
    return p.is_symlink() and not p.exists()


def has_content(p: Path) -> bool:
    """p 是否有实质内容。

    用于 latest 比较: 空内容不应靠 mtime 覆盖有内容的 canonical (防数据丢失)。
    - 不存在 -> False
    - 文件: 大小 > 0
    - 目录: 内部存在任一非空文件
    """
    if not p.exists():
        return False
    if p.is_file():
        return p.stat().st_size > 0
    for root, _dirs, files in os.walk(p):
        for f in files:
            try:
                if (Path(root) / f).stat().st_size > 0:
                    return True
            except OSError:
                continue
    return False


def newest_mtime(p: Path) -> float:
    """文件取自身 mtime; 目录取内部所有文件最新 mtime。

    设计: "对目录 skill, latest 由内部任一文件最新 mtime 决定"。
    空目录/不存在返回 -1。
    """
    if not p.exists():
        return -1.0
    if p.is_file():
        return p.stat().st_mtime
    newest = -1.0
    for root, _dirs, files in os.walk(p):
        for f in files:
            try:
                m = (Path(root) / f).stat().st_mtime
            except OSError:
                continue
            if m > newest:
                newest = m
    # 目录内没有文件时, 退回目录自身 mtime
    if newest < 0:
        newest = p.stat().st_mtime
    return newest


def copy_into(src: Path, dst: Path, apply: bool) -> None:
    """复制 src 到 dst (文件或目录)。dst 父目录自动建。覆盖已存在 dst。"""
    if not apply:
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.is_dir():
        if dst.exists() or dst.is_symlink():
            _remove(dst)
        shutil.copytree(src, dst, symlinks=True)
    else:
        if dst.exists() or dst.is_symlink():
            _remove(dst)
        shutil.copy2(src, dst)


def backup(src: Path, backup_path: Path, apply: bool) -> None:
    """把 src 备份到 backup_path。失败抛异常 (调用方据此 stop)。"""
    if not apply:
        return
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    if src.is_dir() and not src.is_symlink():
        shutil.copytree(src, backup_path, symlinks=True)
    else:
        # 文件 / 链接: 复制内容 (链接则复制其指向的真实内容, 用 copy2 跟随)
        shutil.copy2(src, backup_path, follow_symlinks=True)


def make_symlink(target: Path, canonical: Path, apply: bool) -> None:
    """创建 symlink target -> canonical。先移除已存在 target。"""
    if not apply:
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() or target.is_symlink():
        _remove(target)
    target.symlink_to(canonical)


def convert_root_to_dir(path: Path, apply: bool) -> None:
    """整目录链接 -> 真实空目录。

    移除 path 处的 symlink (或目录), 创建同名的真实空目录。
    逐项建链由后续 LINK 动作完成。
    """
    if not apply:
        return
    if path.is_symlink():
        path.unlink()
    elif path.is_dir():
        # 安全: 仅在 path 本身是 symlink 目标时进入此分支 (不应发生)
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def _remove(p: Path) -> None:
    """删除文件/链接/目录。链接只删链接本身不动指向。"""
    if p.is_symlink() or p.is_file():
        p.unlink()
    elif p.is_dir():
        shutil.rmtree(p)
