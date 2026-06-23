import type { Plan, PlanAction } from "../api";

// 动作名 -> 糊弄的中文 (画图程序里随便打的, 不是产品文案)
const KIND_LABEL: Record<string, string> = {
  collect: "收",
  migrate: "搬",
  backup: "备",
  link: "链",
  relink: "修",
  replace: "换",
  skip: "过",
  mkdir: "建",
  convert_root_link: "拆",
  error: "错",
};

interface Props {
  plan: Plan;
  busy: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

export function SyncDialog({ plan, busy, onConfirm, onCancel }: Props) {
  const reals = plan.actions.filter((a) => a.requires_real_replace);
  const overlaps = plan.actions.filter((a) => a.overlaps_canonical && !a.requires_real_replace);
  const needsConfirm = plan.has_real_replacements;

  return (
    <div className="dialog-overlay" data-testid="sync-dialog">
      <div className="dialog">
        <h3>咋回事 {plan.timestamp}</h3>

        <div className="dialog-summary">
          <span>{plan.actions.length} 项</span>
          <span className={reals.length ? "warn" : ""}>
            会覆盖: {plan.real_replacement_count}
          </span>
          {overlaps.length > 0 && (
            <span className="info" data-testid="overlap-info">
              跳过: {overlaps.length}
            </span>
          )}
        </div>

        {needsConfirm && reals.length > 0 && (
          <div className="dialog-reals">
            <h4>这 {reals.length} 个会先备份再换掉:</h4>
            <ul>
              {reals.map((a, i) => (
                <ActionRow key={i} a={a} tone="real" />
              ))}
            </ul>
          </div>
        )}

        {overlaps.length > 0 && (
          <details className="dialog-skipped">
            <summary>
              跳了 {overlaps.length} 项，不用管
            </summary>
            <p>
              这些指向跟仓库是一家的，引擎自己跳了。不用操心。
            </p>
            <ul>
              {overlaps.slice(0, 50).map((a, i) => (
                <ActionRow key={i} a={a} tone="skipped" />
              ))}
            </ul>
          </details>
        )}

        {!needsConfirm && (
          <div className="dialog-safe" data-testid="dialog-safe">
            没啥要换的，安全的。搞不搞？
          </div>
        )}

        <div className="dialog-actions">
          <button onClick={onCancel} disabled={busy} data-testid="cancel-btn">
            算了
          </button>
          <button
            className="confirm-btn"
            onClick={onConfirm}
            disabled={busy}
            data-testid="confirm-btn"
          >
            {busy ? "…" : "搞"}
          </button>
        </div>
      </div>
    </div>
  );
}

function ActionRow({ a, tone }: { a: PlanAction; tone: "real" | "skipped" }) {
  const label = KIND_LABEL[a.kind] || a.kind;
  return (
    <li className={tone === "real" ? "real-replace" : "skipped-link"}>
      [{label}] {a.name}
      <div className="action-paths">
        <div>目标 {a.dst}</div>
        {a.dst_realpath && a.dst_realpath !== a.dst && (
          <div className="realpath">实际 {a.dst_realpath}</div>
        )}
      </div>
    </li>
  );
}
