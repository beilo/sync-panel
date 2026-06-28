# Changelog

## 2026-06-27

- 发布版本 `v0.1.1`：用于分发包含 Agent Skills 目录调整与新版图标的 macOS 安装包。
- 依据 Codex 官方技能目录语义，`Agent Skills` 改为只维护 `~/.agents/skills`；Codex 直接读取该目录，不再维护 `~/.codex/skills` 入口。
- `rule` 同步逻辑保持不变；Codex 仍只保留 `~/.codex/AGENTS.md` rule 映射。

## 2026-06-23

- Sync 弹窗文案彻底中文化：动作名单字、路径标签短打、确认按钮「搞」/「算了」、标题「咋回事」。

## 2026-06-22

- 接管 Claude resume 卡住后的剩余验证工作。
- 为 Tauri React 前端补齐 e2e 测试依赖: `vitest`, `@testing-library/react`, `@testing-library/user-event`, `jsdom`, `@testing-library/jest-dom`。
- 调整 `app/tsconfig.app.json`, 让前端生产构建排除 `src/test`, 避免 Node/jsdom 测试代码污染浏览器构建。
- 清理 `app/src/test/e2e.test.tsx` 未使用导入, 保持 TypeScript `noUnusedLocals` 约束可过。
- 修正 e2e 对 Sync 弹窗的断言: fixture 中 target 是真实目录, 预期应为替换/重叠警告而非安全提示。
- 调整 ESLint: 忽略 `src-tauri/target` 和 `src-tauri/gen` 构建产物, 并对首屏 sidecar 异步加载加定点 lint 说明。
