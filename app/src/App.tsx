import { useEffect, useState, useCallback } from "react";
import {
  api,
  TARGETS,
  type Tree,
  type TreeNode,
  type FileContent,
  type Plan,
  type ApplyOutcome,
  type TargetStatus,
} from "./api";
import { FileTree } from "./components/FileTree";
import { Preview } from "./components/Preview";
import { SyncDialog } from "./components/SyncDialog";
import "./App.css";

export default function App() {
  const [tree, setTree] = useState<Tree | null>(null);
  const [target, setTarget] = useState<string>("codex");
  const [status, setStatus] = useState<TargetStatus | null>(null);
  const [selected, setSelected] = useState<{ which: string; rel: string } | null>(null);
  const [preview, setPreview] = useState<FileContent | null>(null);
  const [plan, setPlan] = useState<Plan | null>(null);
  const [outcome, setOutcome] = useState<ApplyOutcome | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 初次加载文件树
  const loadTree = useCallback(async () => {
    try {
      setTree(await api.getTree());
    } catch (e) {
      setError(String(e));
    }
  }, []);

  useEffect(() => {
    // 首屏必须从 sidecar 拉真实文件树; 这里是异步 IO 入口, 不是派生状态。
    // eslint-disable-next-line react-hooks/set-state-in-effect
    loadTree();
  }, [loadTree]);

  // 切 target -> 拉该 target 状态
  useEffect(() => {
    api
      .targetStatus(target)
      .then(setStatus)
      .catch((e) => setError(String(e)));
  }, [target]);

  // 点文件 -> 读内容预览
  const onSelectFile = useCallback(async (node: TreeNode, rootName: string) => {
    if (node.is_dir) return;
    const which = rootName; // shared-skills | shared-rules
    setSelected({ which, rel: node.rel });
    try {
      setPreview(await api.readFile(which, node.rel));
    } catch (e) {
      setPreview({ path: node.rel, error: String(e) });
    }
  }, []);

  // 点 Sync -> 先算 plan -> 开确认弹窗
  const onSync = useCallback(async () => {
    setBusy(true);
    setError(null);
    setOutcome(null);
    try {
      const p = await api.buildPlan();
      setPlan(p);
      setDialogOpen(true);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }, []);

  // 弹窗确认 -> apply (引擎重算 plan, 防 TOCTOU)
  const onConfirm = useCallback(async () => {
    setBusy(true);
    try {
      const out = await api.applySync();
      setOutcome(out);
      setDialogOpen(false);
      await loadTree();
      setStatus(await api.targetStatus(target));
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }, [loadTree, target]);

  return (
    <div className="app">
      <header className="topbar">
        <h1>AI Workspace 同步面板</h1>
        <button className="sync-btn" onClick={onSync} disabled={busy} data-testid="sync-btn">
          {busy ? "处理中…" : "Sync"}
        </button>
      </header>

      {error && (
        <div className="error-banner" data-testid="error-banner">
          {error}
        </div>
      )}

      <div className="three-pane">
        {/* 区1: target 选择器 */}
        <aside className="pane target-pane">
          <h2>Target</h2>
          <ul className="target-list">
            {TARGETS.map((t) => (
              <li key={t.id}>
                <label className={target === t.id ? "active" : ""}>
                  <input
                    type="radio"
                    name="target"
                    checked={target === t.id}
                    onChange={() => setTarget(t.id)}
                    data-testid={`target-${t.id}`}
                  />
                  {t.label}
                </label>
              </li>
            ))}
          </ul>
          {status && (
            <div className="status-box" data-testid="status-box">
              <div className="status-count">{status.count} 项</div>
            </div>
          )}
        </aside>

        {/* 区2: 文件树 (永远 canonical) */}
        <section className="pane tree-pane">
          <h2>Files (canonical)</h2>
          {tree ? (
            <FileTree tree={tree} selectedRel={selected?.rel} onSelect={onSelectFile} />
          ) : (
            <div className="loading">加载中…</div>
          )}
        </section>

        {/* 区3: 预览 (只读) */}
        <section className="pane preview-pane">
          <h2>Preview</h2>
          <Preview file={preview} />
        </section>
      </div>

      {outcome && <ResultBar outcome={outcome} />}

      {dialogOpen && plan && (
        <SyncDialog
          plan={plan}
          busy={busy}
          onConfirm={onConfirm}
          onCancel={() => setDialogOpen(false)}
        />
      )}
    </div>
  );
}

// 底部结果条 — apply 后展示 SyncResult 概览。
function ResultBar({ outcome }: { outcome: ApplyOutcome }) {
  if (outcome.error) {
    return (
      <div className="result-bar error" data-testid="result-bar">
        执行失败: {outcome.error}
      </div>
    );
  }
  const c = outcome.result?.counts ?? {};
  return (
    <div className="result-bar" data-testid="result-bar">
      执行完成 — 收集 {c.collected ?? 0} · 转换 {c.root_links_converted ?? 0} · 新链 {c.links_created ?? 0} · 修复{" "}
      {c.links_repaired ?? 0} · 已正确 {c.already_correct ?? 0} · 替换 {c.replaced ?? 0} ·
      备份 {c.backups ?? 0} · 错误 {c.errors ?? 0}
    </div>
  );
}
