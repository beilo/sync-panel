// 测试 fixture: 造隔离假 HOME, 让真 sidecar (PyInstaller exe) 在其上跑。
// 不碰真实 ~。每个测试用独立临时目录。

import { mkdtempSync, mkdirSync, writeFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

export interface Fixture {
  home: string;
  cleanup: () => void;
}

// 造一个目录式 skill: <root>/<name>/SKILL.md
function mkskill(root: string, name: string, body: string) {
  const d = join(root, name);
  mkdirSync(d, { recursive: true });
  writeFileSync(join(d, "SKILL.md"), body);
}

// 造一个全新的假 HOME:
// - .codex/skills 下有真实 skill "alpha"
// - .claude/skills 下有真实 skill "beta"
// - ai-workspace/shared-skills 已有 canonical "gamma"
// 这样 plan 会产生 collect(alpha/beta) + map(建链), 但无 real-replace 冲突。
export function makeFixture(): Fixture {
  const home = mkdtempSync(join(tmpdir(), "syncpanel-e2e-"));
  const ws = join(home, "ai-workspace");
  mkdirSync(join(ws, "shared-skills"), { recursive: true });
  mkdirSync(join(ws, "shared-rules"), { recursive: true });

  mkskill(join(home, ".codex", "skills"), "alpha", "alpha body");
  mkskill(join(home, ".claude", "skills"), "beta", "beta body");
  mkskill(join(ws, "shared-skills"), "gamma", "gamma canonical");
  writeFileSync(join(ws, "shared-rules", "AGENTS.md"), "# canonical rules\n");

  return {
    home,
    cleanup: () => rmSync(home, { recursive: true, force: true }),
  };
}
