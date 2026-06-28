"""JSON API 层测试。

沿用 test_engine 的临时 HOME fixture, 不碰真实 ~。
覆盖: tree 结构 / read 内容 / read 越权防护 / plan 的 dst_realpath+overlap 标注 /
apply 真执行 / target status 过滤。

运行: python -m unittest sync_panel.test_jsonapi
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from sync_panel import jsonapi
from sync_panel.cli import main
from sync_panel.config import default_config


def touch(p: Path, content: str = "") -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    return p


def mkskill(root: Path, name: str, body: str) -> Path:
    d = root / name
    touch(d / "SKILL.md", body)
    return d


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="syncpanel-json-"))
        self.home = self.tmp / "home"
        self.cfg = default_config(self.home)
        self.cfg.shared_skills.mkdir(parents=True, exist_ok=True)
        self.cfg.shared_rules.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


class TestTree(Base):
    def test_tree_lists_canonical(self):
        mkskill(self.cfg.shared_skills, "alpha", "a body")
        touch(self.cfg.shared_rules / "AGENTS.md", "rules")
        tree = jsonapi.get_tree(self.cfg)
        names = {r["name"] for r in tree["roots"]}
        self.assertEqual(names, {"shared-skills", "shared-rules"})
        skills = next(r for r in tree["roots"] if r["name"] == "shared-skills")
        child_names = {c["name"] for c in skills["children"]}
        self.assertIn("alpha", child_names)
        # alpha 是目录, 应有 children
        alpha = next(c for c in skills["children"] if c["name"] == "alpha")
        self.assertTrue(alpha["is_dir"])
        self.assertIn("SKILL.md", {c["name"] for c in alpha["children"]})

    def test_tree_excludes_dot_entries(self):
        mkskill(self.cfg.shared_skills, ".hidden", "x")
        mkskill(self.cfg.shared_skills, "visible", "y")
        tree = jsonapi.get_tree(self.cfg)
        skills = next(r for r in tree["roots"] if r["name"] == "shared-skills")
        child_names = {c["name"] for c in skills["children"]}
        self.assertIn("visible", child_names)
        self.assertNotIn(".hidden", child_names)


class TestRead(Base):
    def test_read_canonical_file(self):
        mkskill(self.cfg.shared_skills, "alpha", "hello world")
        out = jsonapi.read_file(self.cfg, "shared-skills", "alpha/SKILL.md")
        self.assertEqual(out["content"], "hello world")
        self.assertFalse(out["is_binary"])

    def test_read_rejects_escape(self):
        # ../ 逃逸出 canonical 根 -> PathDenied
        touch(self.home / "secret.txt", "TOP SECRET")
        with self.assertRaises(jsonapi.PathDenied):
            jsonapi.read_file(self.cfg, "shared-skills", "../../secret.txt")

    def test_read_rejects_unknown_root(self):
        with self.assertRaises(jsonapi.PathDenied):
            jsonapi.read_file(self.cfg, "etc", "passwd")

    def test_read_missing_file(self):
        out = jsonapi.read_file(self.cfg, "shared-skills", "nope/SKILL.md")
        self.assertIn("error", out)


class TestPlan(Base):
    def test_plan_has_realpath_annotation(self):
        # agents 有真实 skill, canonical 没有 -> plan 含 collect + map 动作
        mkskill(self.cfg.skill_targets["agents"], "foo", "hello")
        d = jsonapi.build_plan_dict(self.cfg, "20260622-201530")
        self.assertIn("actions", d)
        self.assertIn("overlap_count", d)
        for a in d["actions"]:
            # 每个有 dst 的动作都带 realpath 标注键
            self.assertIn("dst_realpath", a)
            self.assertIn("overlaps_canonical", a)

    def test_plan_flags_real_replacement(self):
        # agents 的 skills 下放真实 skill, 同名 canonical 也存在但更旧 -> 不一定 replace
        # 这里造 map 阶段的 REAL-REPLACE: target 是真实目录, canonical 已存在
        mkskill(self.cfg.shared_skills, "foo", "canonical")
        mkskill(self.cfg.skill_targets["agents"], "foo", "real dir at target")
        d = jsonapi.build_plan_dict(self.cfg, "20260622-201530")
        # codex/foo 是真实目录且 canonical 存在 -> 应出现 requires_real_replace
        self.assertTrue(d["has_real_replacements"])
        self.assertGreaterEqual(d["real_replacement_count"], 1)


class TestApply(Base):
    def test_apply_executes_and_links(self):
        mkskill(self.cfg.skill_targets["agents"], "foo", "hello")
        out = jsonapi.apply_sync(self.cfg, "20260622-201530")
        self.assertIn("result", out)
        # canonical 应已收集
        self.assertTrue((self.cfg.shared_skills / "foo" / "SKILL.md").exists())
        # codex target 应已变链接
        entry = self.cfg.skill_targets["agents"] / "foo"
        self.assertTrue(entry.is_symlink())

    def test_apply_idempotent(self):
        mkskill(self.cfg.skill_targets["agents"], "foo", "hello")
        jsonapi.apply_sync(self.cfg, "20260622-201530")
        out2 = jsonapi.apply_sync(self.cfg, "20260622-201531")
        counts = out2["result"]["counts"]
        # 第二次: 无收集/无替换/无备份
        self.assertEqual(counts["collected"], 0)
        self.assertEqual(counts["replaced"], 0)
        self.assertEqual(counts["backups"], 0)


class TestStatus(Base):
    def test_status_filters_by_target(self):
        mkskill(self.cfg.skill_targets["agents"], "foo", "hello")
        out = jsonapi.target_status(self.cfg, "20260622-201530", "agents")
        self.assertEqual(out["target"], "agents")
        self.assertTrue(all(i["tool"] == "agents" for i in out["items"]))

    def test_agent_skills_status_uses_agents_only(self):
        mkskill(self.cfg.shared_skills, "foo", "canonical")
        touch(self.cfg.shared_rules / "AGENTS.md", "rules")
        out = jsonapi.target_status(self.cfg, "20260622-201530", "agent-skills")
        self.assertEqual(out["target"], "agent-skills")
        self.assertEqual(out["count"], 1)
        self.assertEqual(out["items"][0]["name"], "foo")
        self.assertEqual(out["items"][0]["tool"], "agent-skills")
        # rule 不进入 Agent Skills 合并视图, 但仍留在全量 plan 里由同步流程处理。
        self.assertNotIn("AGENTS.md", {i["name"] for i in out["items"]})

    def test_status_unknown_target(self):
        out = jsonapi.target_status(self.cfg, "20260622-201530", "bogus")
        self.assertIn("error", out)


class TestCliJson(Base):
    """通过 cli main 走子命令, 校验 JSON 输出 (UI 实际走这条路)。"""

    def _run(self, *argv):
        import io
        import contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            # --home 是顶层 arg, 必须在子命令前
            rc = main(["--home", str(self.home), *argv])
        return rc, buf.getvalue()

    def test_cli_tree_json(self):
        mkskill(self.cfg.shared_skills, "alpha", "a")
        # 注意: --home 是顶层 arg, 子命令在前
        rc, out = self._run("tree")
        self.assertEqual(rc, 0)
        d = json.loads(out)
        self.assertIn("roots", d)

    def test_cli_read_denied_returns_json_error(self):
        touch(self.home / "secret.txt", "x")
        rc, out = self._run("read", "--which", "shared-skills", "--rel", "../../secret.txt")
        d = json.loads(out)
        self.assertIn("error", d)

    def test_cli_agent_skills_status_json(self):
        mkskill(self.cfg.shared_skills, "alpha", "a")
        rc, out = self._run("status", "--target", "agent-skills")
        self.assertEqual(rc, 0)
        d = json.loads(out)
        self.assertEqual(d["target"], "agent-skills")


if __name__ == "__main__":
    unittest.main()
