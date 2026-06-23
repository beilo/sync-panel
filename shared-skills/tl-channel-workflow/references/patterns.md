# Patterns

## Selection

Use channel workflow only when the plan belongs outside the main conversation: multiple workers, adversarial verification, durable forum tracking, or long-running evidence capture. Direct work stays direct.

## Review

Purpose: one worker reviews a bounded artifact.

Flow:

1. Create ephemeral chat channel.
2. Spawn `reviewer-1`.
3. Send scoped prompt to `reviewer-1`.
4. Wait for `done,turn_finished`.
5. Read `messages --raw`.
6. Main session summarizes.

Use for small reviews where independent verification is not worth the cost.

## Dual Verify

Purpose: find claims, then independently verify them.

Flow:

1. `reviewer-1` receives the source scope and returns JSON findings.
2. Harness extracts reviewer output.
3. `verifier-1` receives only the artifact/rubric/finding list, not reviewer identity.
4. Main session reports confirmed, rejected, and needs-human items.

Why: same-context self-review is biased. Verification must use a separate channel worker.

## Implement / Check

Purpose: one worker writes the bounded change, then two independent workers check the resulting diff.

Flow:

1. Create ephemeral chat channel.
2. Spawn `implementer-1` with provider `claude`.
3. Send scoped implementation prompt to `implementer-1`.
4. Wait for `done,turn_finished`.
5. Capture `messages --raw` and `git diff`.
6. Kill `implementer-1` to release live-worker budget.
7. Spawn `checker-1` with provider `codex`.
8. Spawn `checker-2` with provider `claude`.
9. Send original request, implementer output, and diff to both checkers.
10. Wait for both checkers with `--all`.
11. Main session reports implementation summary, checker findings, disagreements, and remaining test gaps.

Safety:

- Requires explicit `--write` and `--yes`.
- `implementer-1` is Claude Code and may write only inside the approved scope.
- `checker-1` and `checker-2` must not modify files.
- The channel may be deleted after success; file changes remain in the workspace.

## Research

Purpose: external or untrusted material, then validation and synthesis.

Flow:

1. `reader-1` reads only and returns sanitized claims.
2. `verifier-1` checks claims against provided evidence/rubric.
3. `synthesizer-1` produces a concise final report from reader/verifier outputs.

Why: reader touches untrusted text; verifier/synthesizer should not receive raw hostile instructions unless needed.

Release each finished worker before spawning the next stage. Trellis keeps completed workers alive while idle, so long sequential pipelines can otherwise exhaust the live-worker budget.

## Forum

Purpose: durable board for issues, findings, or decisions.

Use `--type forum --scope global` for cross-project boards. Threads hold findings or decisions. Prefer `forum`, `thread`, and `context list` commands over direct `events.jsonl` parsing.

## Pipeline Bias

Default to per-item progression. Only use a barrier when the next step needs all results: de-duplication, global comparison, or final synthesis.
