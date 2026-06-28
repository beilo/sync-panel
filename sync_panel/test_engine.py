"""Sync 引擎测试。

全部在临时目录构造假 HOME, 不碰真实 ~。
覆盖: collect 复制 / latest 比较 / 备份 / map 建链 / 幂等第二次无变更 /
incorrect symlink 比较修复 / broken link 修复 / dot 前缀排除 / map-only rule。

运行: python -m pytest sync_panel/test_engine.py -v
或:   python sync_panel/test_engine.py
"""

from __future__ import annotations

import os
import shutil
import tempfile
import time
import unittest
from pathlib import Path

from sync_panel.config import default_config
from sync_panel.engine import SyncEngine
from sync_panel.model import ActionKind
from sync_panel import fsutil


def touch(p: Path, content: str = "", mtime: float | None = None) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    if mtime is not None:
        os.utime(p, (mtime, mtime))
    return p


def mkskill(root: Path, name: str, body: str, mtime: float | None = None) -> Path:
    """造一个目录式 skill: <root>/<name>/SKILL.md"""
    d = root / name
    touch(d / "SKILL.md", body, mtime)
    return d


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="syncpanel-test-"))
        self.home = self.tmp / "home"
        self.cfg = default_config(self.home)
        # 预建 workspace 骨架
        self.cfg.shared_skills.mkdir(parents=True, exist_ok=True)
        self.cfg.shared_rules.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def engine(self, ts="20260622-201530"):
        return SyncEngine(self.cfg, ts)

    def run_sync(self, ts="20260622-201530"):
        eng = self.engine(ts)
        plan = eng.build_plan()
        result = eng.execute(plan, apply=True)
        return plan, result


class TestCollect(Base):
    def test_collect_when_canonical_missing(self):
        # agents 有个真实 skill, canonical 没有 -> 应收集
        mkskill(self.cfg.skill_targets["agents"], "foo", "hello")
        plan, result = self.run_sync()
        self.assertTrue((self.cfg.shared_skills / "foo" / "SKILL.md").exists())
        self.assertEqual(
            (self.cfg.shared_skills / "foo" / "SKILL.md").read_text(), "hello")
        kinds = {a.kind for a in plan.actions if a.name == "foo"}
        self.assertIn(ActionKind.COLLECT, kinds)

    def test_latest_version_wins(self):
        # 三个 target 同名 skill, mtime 不同 -> 最新进 canonical
        t = time.time()
        mkskill(self.cfg.skill_targets["agents"], "bar", "old", mtime=t - 100)
        mkskill(self.cfg.skill_targets["claude-code"], "bar", "newest", mtime=t)
        mkskill(self.cfg.skill_targets["agents"], "bar", "mid", mtime=t - 50)
        self.run_sync()
        self.assertEqual(
            (self.cfg.shared_skills / "bar" / "SKILL.md").read_text(), "newest")

    def test_dot_prefixed_excluded(self):
        # dot 前缀 skill 不收集
        mkskill(self.cfg.skill_targets["agents"], ".hidden", "secret")
        self.run_sync()
        self.assertFalse((self.cfg.shared_skills / ".hidden").exists())

    def test_migrate_newer_backs_up_old_canonical(self):
        # canonical 已存在旧版, target 有更新真实版 -> 迁移 + 备份旧 canonical
        t = time.time()
        mkskill(self.cfg.shared_skills, "baz", "old-canon", mtime=t - 100)
        mkskill(self.cfg.skill_targets["agents"], "baz", "new-target", mtime=t)
        plan, result = self.run_sync()
        self.assertEqual(
            (self.cfg.shared_skills / "baz" / "SKILL.md").read_text(), "new-target")
        # 备份里应有旧 canonical 内容
        self.assertTrue(result.backups, "应产生备份")
        self.assertTrue(result.migrated, "应有迁移动作")


class TestMap(Base):
    def test_link_created_for_canonical(self):
        # canonical 有 skill, target 缺 -> 建链
        mkskill(self.cfg.shared_skills, "qux", "x")
        self.run_sync()
        for tool, root in self.cfg.skill_targets.items():
            entry = root / "qux"
            self.assertTrue(entry.is_symlink(), f"{tool} 应建链")
            self.assertEqual((entry / "SKILL.md").read_text(), "x")

    def test_real_dir_backed_up_then_replaced(self):
        # canonical 有, target 是真实目录 -> 备份后替换为链接
        mkskill(self.cfg.shared_skills, "rr", "canon")
        mkskill(self.cfg.skill_targets["agents"], "rr", "real-target")
        plan, result = self.run_sync()
        entry = self.cfg.skill_targets["agents"] / "rr"
        self.assertTrue(entry.is_symlink(), "真实目录应被替换为链接")
        self.assertTrue(result.backups or result.replaced)
        # 备份里能找到 real-target 内容
        found = list(self.cfg.backups_root.rglob("SKILL.md"))
        self.assertTrue(any(p.read_text() == "real-target" for p in found),
                        "备份应含被替换的真实内容")


class TestIdempotency(Base):
    def test_second_run_no_changes(self):
        mkskill(self.cfg.skill_targets["agents"], "idem", "v1")
        self.run_sync(ts="20260622-201530")
        # 第二次跑: 计划应全是 skip, 无 collect/migrate/replace/link
        eng = self.engine(ts="20260622-202020")
        plan2 = eng.build_plan()
        bad = [a for a in plan2.actions
               if a.kind not in (ActionKind.SKIP_SYNCED,)]
        self.assertEqual(bad, [], f"第二次应全 skip, 但有: {[a.describe() for a in bad]}")
        # 无新备份目录 (第二次时间戳目录不应被创建)
        self.assertFalse((self.cfg.backups_root / "20260622-202020").exists())


class TestSymlinkRepair(Base):
    def test_incorrect_symlink_with_newer_target_migrates(self):
        # target 是指向别处的错误链接, 指向内容更新 -> 比较后迁移再修复
        t = time.time()
        mkskill(self.cfg.shared_skills, "sk", "old-canon", mtime=t - 100)
        # 别处的真实更新内容
        elsewhere = self.tmp / "elsewhere" / "sk"
        touch(elsewhere / "SKILL.md", "newer-elsewhere", mtime=t)
        # agents/skills/sk -> 指向 elsewhere (错误链接)
        entry = self.cfg.skill_targets["agents"] / "sk"
        entry.parent.mkdir(parents=True, exist_ok=True)
        entry.symlink_to(elsewhere)

        plan, result = self.run_sync()
        # 更新内容应迁入 canonical
        self.assertEqual(
            (self.cfg.shared_skills / "sk" / "SKILL.md").read_text(), "newer-elsewhere")
        # 链接被修复指向 canonical
        self.assertTrue(entry.is_symlink())
        self.assertEqual(os.path.normpath(os.path.realpath(entry)),
                         os.path.normpath((self.cfg.shared_skills / "sk").resolve().as_posix()))

    def test_broken_symlink_repaired(self):
        # canonical 有, target 是断链 -> 修复指向 canonical
        mkskill(self.cfg.shared_skills, "bk", "canon")
        entry = self.cfg.skill_targets["agents"] / "bk"
        entry.parent.mkdir(parents=True, exist_ok=True)
        entry.symlink_to(self.tmp / "nonexistent")
        self.assertTrue(entry.is_symlink() and not entry.exists())  # 断链
        plan, result = self.run_sync()
        self.assertTrue(entry.exists(), "修复后应可用")
        self.assertEqual((entry / "SKILL.md").read_text(), "canon")


class TestRules(Base):
    def test_collect_rule_from_real_file_and_map_all(self):
        # .codex/AGENTS.md 真实文件 -> 初始化 canonical AGENTS.md
        touch(self.home / ".codex" / "AGENTS.md", "agents-rule")
        # .claude/CLAUDE.md 真实文件 -> 初始化 canonical CLAUDE.md
        touch(self.home / ".claude" / "CLAUDE.md", "claude-rule")
        self.run_sync()
        self.assertEqual((self.cfg.shared_rules / "AGENTS.md").read_text(), "agents-rule")
        self.assertEqual((self.cfg.shared_rules / "CLAUDE.md").read_text(), "claude-rule")
        # 三个 rule target 都应是链接回 canonical
        for rm in self.cfg.rule_mappings:
            self.assertTrue(rm.target.is_symlink(), f"{rm.target} 应建链")

    def test_map_only_rule_does_not_initialize(self):
        # 只有 .claude/AGENTS.md (map-only) 存在, 不应初始化 canonical AGENTS.md
        touch(self.home / ".claude" / "AGENTS.md", "should-not-init")
        self.run_sync()
        # canonical AGENTS.md 不应被这个 map-only 源创建
        self.assertFalse((self.cfg.shared_rules / "AGENTS.md").exists(),
                         "map-only 源不应初始化 canonical")

    def test_empty_source_does_not_overwrite_canonical(self):
        # canonical AGENTS.md 有内容; .codex/AGENTS.md 是空文件且 mtime 更新
        # -> 空源不参与比较, canonical 内容保留, target 转链
        t = time.time()
        touch(self.cfg.shared_rules / "AGENTS.md", "real-content", mtime=t - 100)
        touch(self.home / ".codex" / "AGENTS.md", "", mtime=t)  # 0 字节, 更新
        plan, result = self.run_sync()
        self.assertEqual((self.cfg.shared_rules / "AGENTS.md").read_text(),
                         "real-content", "空源不应覆盖 canonical")
        self.assertEqual(result.migrated, [], "空源不应触发迁移")
        self.assertTrue((self.home / ".codex" / "AGENTS.md").is_symlink(),
                        "空 target 应被转为链接")


class TestNonDirSkill(Base):
    def test_loose_file_not_treated_as_skill(self):
        # .agents/skills/foo.zip 散文件 -> 不收集/不映射/不动
        zip_path = self.cfg.skill_targets["agents"] / "foo.zip"
        zip_path.parent.mkdir(parents=True, exist_ok=True)
        zip_path.write_text("PK-binary")
        self.run_sync()
        self.assertFalse((self.cfg.shared_skills / "foo.zip").exists(),
                         "散文件不应被收集进 canonical")
        # 原文件保持不动 (仍是真实文件, 非链接)
        self.assertTrue(zip_path.is_file() and not zip_path.is_symlink(),
                        "散文件应原封不动")
        self.assertEqual(zip_path.read_text(), "PK-binary")

    def test_empty_skill_dir_not_overwrite_canonical(self):
        # canonical 有内容 skill; target 同名是空目录且 mtime 更新 -> 不覆盖
        t = time.time()
        mkskill(self.cfg.shared_skills, "es", "canon-body", mtime=t - 100)
        empty = self.cfg.skill_targets["agents"] / "es"
        empty.mkdir(parents=True)
        os.utime(empty, (t, t))  # 空目录, 更新 mtime
        plan, result = self.run_sync()
        self.assertEqual(
            (self.cfg.shared_skills / "es" / "SKILL.md").read_text(), "canon-body",
            "空目录不应覆盖 canonical")
        self.assertEqual(result.migrated, [], "空目录不应触发迁移")


class TestTargetIsCanonical(Base):
    """target skills 目录本身就是指向 canonical 的链接 (如真实环境的 .agents/skills)。

    回归: 早期 bug 把 canonical 自己删掉再链向自己 -> 自指环, 内容全毁。
    修复: 检测到整目录链接 -> 转换为逐项链接目录。
    """

    def _make_agents_skills_whole_link(self):
        """把 .agents/skills 做成指向 shared-skills 的整体链接 (模拟当前真实环境)。"""
        agents_skills = self.cfg.skill_targets["agents"]
        agents_skills.parent.mkdir(parents=True, exist_ok=True)
        if agents_skills.exists() or agents_skills.is_symlink():
            if agents_skills.is_dir() and not agents_skills.is_symlink():
                agents_skills.rmdir()
            else:
                agents_skills.unlink()
        agents_skills.symlink_to(self.cfg.shared_skills)

    def test_whole_dir_link_is_converted_to_per_item_links(self):
        """整目录链接 -> 逐项链接目录。"""
        # canonical 有 3 个真实 skill
        mkskill(self.cfg.shared_skills, "alpha", "alpha-body")
        mkskill(self.cfg.shared_skills, "beta", "beta-body")
        mkskill(self.cfg.shared_skills, "gamma", "gamma-body")
        self._make_agents_skills_whole_link()

        plan, result = self.run_sync()

        # 验证计划含 CONVERT_ROOT_LINK
        convert_actions = [a for a in plan.actions
                           if a.kind == ActionKind.CONVERT_ROOT_LINK]
        self.assertEqual(len(convert_actions), 1,
                         "应有一个 CONVERT_ROOT_LINK 动作")
        self.assertEqual(convert_actions[0].tool, "agents")

        # 验证计划含 agents 的 LINK 动作 (每个 skill 一个)
        agents_link_actions = [a for a in plan.actions
                               if a.kind == ActionKind.LINK and a.tool == "agents"]
        self.assertEqual(len(agents_link_actions), 3,
                         f"agents 应有 3 个 LINK 动作, 实际: {[a.name for a in agents_link_actions]}")

        # 验证执行后: agents/skills 是真实目录
        agents_skills = self.cfg.skill_targets["agents"]
        self.assertTrue(agents_skills.is_dir(),
                        "apply 后 .agents/skills 应为真实目录")
        self.assertFalse(agents_skills.is_symlink(),
                         "apply 后 .agents/skills 不应仍是链接")

        # 验证执行后: 内部每个 skill 是指向 canonical 的链接
        expected = {"alpha": "alpha-body", "beta": "beta-body", "gamma": "gamma-body"}
        for name, body in expected.items():
            entry = agents_skills / name
            self.assertTrue(entry.is_symlink(),
                            f".agents/skills/{name} 应为 symlink")
            self.assertTrue(fsutil.is_correct_link(entry, self.cfg.shared_skills / name),
                            f".agents/skills/{name} 应指向 canonical")
            self.assertEqual((entry / "SKILL.md").read_text(), body)

        # 验证 canonical 内容完好 (防自指环回归)
        canon = self.cfg.shared_skills
        self.assertFalse(canon.is_symlink(), "canonical 不应被改成链接")
        for name in ("alpha", "beta", "gamma"):
            self.assertTrue((canon / name).is_dir(),
                            f"canonical/{name} 应仍是真实目录")

        # 验证结果含 root_links_converted
        self.assertEqual(len(result.root_links_converted), 1)

    def test_whole_dir_link_idempotent_after_conversion(self):
        """转换后第二次 run: 不再产生 CONVERT_ROOT_LINK, agents 条目全 skip。"""
        mkskill(self.cfg.shared_skills, "alpha", "a-body")
        self._make_agents_skills_whole_link()
        self.run_sync(ts="20260622-201530")

        # 第二次 run
        eng = self.engine(ts="20260622-202020")
        plan2 = eng.build_plan()
        convert_actions = [a for a in plan2.actions
                           if a.kind == ActionKind.CONVERT_ROOT_LINK]
        self.assertEqual(convert_actions, [],
                         "转换后第二次 run 不应再有 CONVERT_ROOT_LINK")

        # agents 条目应全是 SKIP_SYNCED
        agents_actions = [a for a in plan2.actions if a.tool == "agents"]
        self.assertTrue(all(a.kind == ActionKind.SKIP_SYNCED for a in agents_actions),
                        f"agents 条目应全 skip, 实际: {[a.describe() for a in agents_actions]}")

    def test_canonical_content_preserved_during_conversion(self):
        """转换过程中 canonical 内容不动 (shared-skills 不动)。"""
        mkskill(self.cfg.shared_skills, "keep", "precious-data")
        self._make_agents_skills_whole_link()
        self.run_sync()
        # shared-skills 内容必须完好
        self.assertEqual(
            (self.cfg.shared_skills / "keep" / "SKILL.md").read_text(),
            "precious-data",
            "canonical 内容必须在转换后完好无损")
        # shared-skills 自身仍是真实目录
        self.assertTrue(self.cfg.shared_skills.is_dir()
                        and not self.cfg.shared_skills.is_symlink())


if __name__ == "__main__":
    unittest.main(verbosity=2)
