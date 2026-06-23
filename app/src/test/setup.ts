// vitest 全局 setup: 把 Tauri 的 invoke mock 成真实调用 PyInstaller sidecar exe。
//
// 思路: UI 调 invoke(cmd, args) -> 这里 spawn 真 sync-panel-cli exe 带对应子命令
// + --home <当前 fixture HOME> -> 收 stdout JSON -> 返回。
// 于是模拟点击驱动的是真 Python 引擎 (隔离 HOME), 端到端无桩。

import { execFileSync } from "node:child_process";
import { existsSync } from "node:fs";
import { join } from "node:path";
import { afterEach, vi } from "vitest";
import "@testing-library/jest-dom/vitest";

// sidecar exe 路径 (PyInstaller 产物)。
const EXE = join(process.cwd(), "..", "dist-cli", "sync-panel-cli");
if (!existsSync(EXE)) {
  throw new Error(`sidecar exe 不存在: ${EXE} — 先跑 PyInstaller 打包`);
}

// 当前测试的 fixture HOME, 由测试用 setTestHome 注入。
let currentHome: string | null = null;
export function setTestHome(home: string) {
  currentHome = home;
}

// 把前端 command 名 + 参数翻译成 CLI argv (与 Rust lib.rs 的映射一致)。
function toArgv(cmd: string, args: Record<string, unknown> = {}): string[] {
  const home = currentHome;
  if (!home) throw new Error("测试未设置 fixture HOME");
  const base = ["--home", home];
  switch (cmd) {
    case "get_tree":
      return [...base, "tree"];
    case "read_file":
      return [...base, "read", "--which", String(args.which), "--rel", String(args.rel)];
    case "build_plan":
      return [...base, "plan"];
    case "apply_sync":
      return [...base, "apply"];
    case "target_status":
      return [...base, "status", "--target", String(args.target)];
    default:
      throw new Error(`未知 command: ${cmd}`);
  }
}

// mock @tauri-apps/api/core 的 invoke。
vi.mock("@tauri-apps/api/core", () => ({
  invoke: async (cmd: string, args?: Record<string, unknown>) => {
    const argv = toArgv(cmd, args);
    const out = execFileSync(EXE, argv, { encoding: "utf-8" });
    return JSON.parse(out);
  },
}));

afterEach(() => {
  currentHome = null;
});
