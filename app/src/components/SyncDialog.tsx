import type { Plan, PlanAction } from "../api";

// Sync 确认弹窗。展示 plan, 列出将替换的真实文件/目录。
// 设计要求: 若 plan 替换任何真实文件/目录, 必须展示受影响路径并要求确认。
// 事故防护: 每条显式列 dst_realpath, 重叠 canonical 的条目标红 (执行会自指环)。

interface Props {
  plan: Plan;
  busy: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

export function SyncDialog({ plan, busy, onConfirm, onCancel }: Props) {
  const reals = plan.actions.filter((a) => a.requires_real_replace);
  const overlaps = plan.actions.filter((a) => a.overlaps_canonical);
  // 设计: 无真实替换时可直接执行不需二次确认; 但 UI 统一走弹窗便于审阅。
  const needsConfirm = plan.has_real_replacements;

  return (
    <div className="dialog-overlay" data-testid="sync-dialog">
      <div className="dialog">
        <h3>同步计划 ({plan.timestamp})</h3>

        <div className="dialog-summary">
          <span>共 {plan.actions.length} 项动作</span>
          <span className={reals.length ? "warn" : ""}>
            将替换真实文件/目录: {plan.real_replacement_count}
          </span>
          {plan.overlap_count > 0 && (
            <span className="danger" data-testid="overlap-warn">
              ⚠ {plan.overlap_count} 项 target 解析落在 canonical 内
            </span>
          )}
        </div>

        {needsConfirm && reals.length > 0 && (
          <div className="dialog-reals">
            <h4>以下真实文件/目录将被备份后替换:</h4>
            <ul>
              {reals.map((a, i) => (
                <ActionRow key={i} a={a} />
              ))}
            </ul>
          </div>
        )}

        {overlaps.length > 0 && (
          <details className="dialog-overlaps">
            <summary className="danger">
              重叠 canonical 的条目 ({overlaps.length}) — 已被引擎跳过, 仅供审阅
            </summary>
            <ul>
              {overlaps.slice(0, 50).map((a, i) => (
                <ActionRow key={i} a={a} />
              ))}
            </ul>
          </details>
        )}

        {!needsConfirm && (
          <div className="dialog-safe" data-testid="dialog-safe">
            无真实文件将被替换 — 仅建链/修链/已同步。可安全执行。
          </div>
        )}

        <div className="dialog-actions">
          <button onClick={onCancel} disabled={busy} data-testid="cancel-btn">
            取消
          </button>
          <button
            className="confirm-btn"
            onClick={onConfirm}
            disabled={busy}
            data-testid="confirm-btn"
          >
            {busy ? "执行中…" : needsConfirm ? "确认并执行" : "执行"}
          </button>
        </div>
      </div>
    </div>
  );
}

function ActionRow({ a }: { a: PlanAction }) {
  return (
    <li className={a.overlaps_canonical ? "danger" : ""}>
      <code>[{a.kind}]</code> {a.name}
      <div className="action-paths">
        <div>dst: {a.dst}</div>
        {a.dst_realpath && a.dst_realpath !== a.dst && (
          <div className="realpath">realpath: {a.dst_realpath}</div>
        )}
      </div>
    </li>
  );
}
