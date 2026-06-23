// 端到端模拟点击测试。
//
// 全链路: 渲染真 App -> mock 的 invoke 实际 spawn PyInstaller sidecar (真 Python 引擎)
// 跑在隔离 fixture HOME 上。覆盖设计文档三区 + Sync 流程的验收点。
//
// 这不是桩测试: 点击触发的是真引擎的真文件系统操作 (在临时 HOME 内)。

import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { existsSync, lstatSync } from "node:fs";
import { join } from "node:path";
import App from "../App";
import { makeFixture, type Fixture } from "./fixture";
import { setTestHome } from "./setup";

let fx: Fixture;

beforeEach(() => {
  fx = makeFixture();
  setTestHome(fx.home);
});

afterEach(() => {
  fx.cleanup();
});

describe("三区 UI 端到端 (真 sidecar)", () => {
  it("加载后展示文件树, 含 canonical skill gamma", async () => {
    render(<App />);
    // 文件树异步加载
    await waitFor(() => expect(screen.getByTestId("file-tree")).toBeInTheDocument());
    // canonical 的 gamma skill 应出现
    await waitFor(() => expect(screen.getByText("gamma")).toBeInTheDocument());
    // 两棵根都在
    expect(screen.getByText("shared-skills")).toBeInTheDocument();
    expect(screen.getByText("shared-rules")).toBeInTheDocument();
  });

  it("三个 target 都可选, 切换触发状态加载", async () => {
    const user = userEvent.setup();
    render(<App />);
    await waitFor(() => screen.getByTestId("file-tree"));

    expect(screen.getByTestId("target-codex")).toBeInTheDocument();
    expect(screen.getByTestId("target-claude-code")).toBeInTheDocument();
    expect(screen.getByTestId("target-agents")).toBeInTheDocument();

    // 点 claude-code -> 状态框刷新
    await user.click(screen.getByTestId("target-claude-code"));
    await waitFor(() => expect(screen.getByTestId("status-box")).toBeInTheDocument());
  });

  it("点击文件 -> 预览区显示 canonical 内容", async () => {
    const user = userEvent.setup();
    render(<App />);
    await waitFor(() => screen.getByText("gamma"));

    // 展开 gamma 目录
    await user.click(screen.getByText("gamma"));
    // 点 SKILL.md
    await waitFor(() => screen.getByText("SKILL.md"));
    await user.click(screen.getByText("SKILL.md"));

    // 预览展示真实内容 "gamma canonical"
    await waitFor(() =>
      expect(screen.getByTestId("preview-content")).toHaveTextContent("gamma canonical")
    );
  });

  it("Sync 全流程: 点 Sync -> 弹计划 -> 确认 -> 真执行建链", async () => {
    const user = userEvent.setup();
    render(<App />);
    await waitFor(() => screen.getByText("gamma"));

    // 执行前: codex/alpha 是真实目录, 非链接
    const alphaEntry = join(fx.home, ".codex", "skills", "alpha");
    expect(lstatSync(alphaEntry).isSymbolicLink()).toBe(false);

    // 点 Sync -> 弹窗
    await user.click(screen.getByTestId("sync-btn"));
    await waitFor(() => expect(screen.getByTestId("sync-dialog")).toBeInTheDocument());

    // fixture 故意放真实 target 目录: 真实替换要突出; 内部重叠项只作为自动跳过信息。
    expect(screen.getByText(/会覆盖: 2/)).toBeInTheDocument();
    expect(screen.getByTestId("overlap-info")).toBeInTheDocument();

    // 确认执行
    await user.click(screen.getByTestId("confirm-btn"));

    // 结果条出现
    await waitFor(() => expect(screen.getByTestId("result-bar")).toBeInTheDocument(), {
      timeout: 20000,
    });

    // 真文件系统已变: canonical 收集到 alpha, codex/alpha 变链接
    expect(existsSync(join(fx.home, "ai-workspace", "shared-skills", "alpha", "SKILL.md"))).toBe(true);
    expect(lstatSync(alphaEntry).isSymbolicLink()).toBe(true);
  });

  it("read 越权被引擎拒绝 (UI 不崩, 显示错误)", async () => {
    // 直接验 api 层: 越权路径返回 error JSON, UI 的 Preview 会显示
    // (通过真 sidecar)
    const { api } = await import("../api");
    const out = await api.readFile("shared-skills", "../../../../etc/hosts");
    expect(out.error).toBeTruthy();
  });
});
