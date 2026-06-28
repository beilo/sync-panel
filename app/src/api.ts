// 前端 -> Tauri command 封装层。
// 所有数据来自 sidecar (PyInstaller 打包的 Python 引擎), 经 Rust 转发为 JSON。

import { invoke } from "@tauri-apps/api/core";

// ---- 类型 (对应 jsonapi.py 输出结构) ----

export interface TreeNode {
  name: string;
  rel: string;
  is_dir: boolean;
  is_link: boolean;
  children?: TreeNode[];
}

export interface Tree {
  roots: TreeNode[];
}

export interface FileContent {
  path: string;
  content?: string;
  is_binary?: boolean;
  truncated?: boolean;
  size?: number;
  error?: string;
}

export interface PlanAction {
  kind: string;
  name: string;
  tool: string | null;
  src: string | null;
  dst: string | null;
  dst_realpath: string | null;
  overlaps_canonical: boolean;
  backup_path: string | null;
  message: string;
  requires_real_replace: boolean;
}

export interface Plan {
  timestamp: string;
  actions: PlanAction[];
  has_real_replacements: boolean;
  real_replacement_count: number;
  overlap_count: number;
}

export interface SyncResult {
  timestamp: string;
  counts: Record<string, number>;
  errors: PlanAction[];
  backups: PlanAction[];
}

export interface ApplyOutcome {
  plan: Plan;
  result?: SyncResult;
  error?: string;
}

export interface TargetStatus {
  target: string;
  items: PlanAction[];
  count: number;
  error?: string;
}

// ---- command 封装 ----

export const api = {
  getTree: () => invoke<Tree>("get_tree"),
  readFile: (which: string, rel: string) =>
    invoke<FileContent>("read_file", { which, rel }),
  buildPlan: () => invoke<Plan>("build_plan"),
  applySync: () => invoke<ApplyOutcome>("apply_sync"),
  targetStatus: (target: string) =>
    invoke<TargetStatus>("target_status", { target }),
};

// 展示 target 与真实同步 target 解耦: Codex 官方读取 ~/.agents/skills, 所以 Agent Skills 只维护这一处。
export const TARGETS = [
  { id: "agent-skills", label: "Agent Skills" },
  { id: "claude-code", label: "Claude Code" },
] as const;
