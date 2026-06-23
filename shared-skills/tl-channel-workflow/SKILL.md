---
name: tl-channel-workflow
description: Run Trellis channel workflows through the local `tl channel` CLI, using only Claude Code or Codex channel workers. Use when the user asks to use tl channel, channel workflow, channel-based implement/check/review/research/verification/forum boards, or explicitly wants worker coordination without platform subagents.
---

# tl-channel-workflow

Use this skill as a tool skill for `tl channel`. It coordinates channel workers through Trellis, not through the host platform's subagent system.

## Hard Rules

- Do not call platform subagents, `multi_agent`, Paseo, tmux agent routing, or other agent-spawn tools while this skill is active.
- Do not create an `agents/` directory in this skill. Use the word `worker`, not `agent`, in new instructions.
- Only create workers with `tl channel spawn --provider claude|codex`.
- Default provider is `codex`; use `claude` only when the user asks for Claude Code or the task needs it.
- Before any command that can spawn workers, show the execution plan and get explicit user approval, unless the user already approved this exact plan or the command is a smoke test that does not spawn workers.
- Require a bounded scope and a concrete deliverable. Do not run broad scans such as home directory, desktop, or whole repo unless the user explicitly confirms that exact scope.
- Default max live workers is 2; never exceed 4 unless the user explicitly asks.
- Use temp prompt files plus `--text-file` for long or mixed Chinese/English prompts.
- Wait for completion with `--kind done,turn_finished`; inspect with `messages --raw`.
- Preserve failed channels for inspection. Clean up only after successful ephemeral runs.
- Implement mode writes files and therefore requires both `--write` and `--yes`.
- In implement mode, `implementer-1` is always Claude Code, `checker-1` is Codex, and `checker-2` is Claude Code.

## Workflow

1. Read the relevant reference:
   - Implement/check, review, or verification: `references/patterns.md`
   - External/web/untrusted input: `references/safety.md`
   - Exact CLI behavior: `references/command-contract.md`
2. Build a plan: channel name, mode, scope, provider, workers, timeout, deliverable.
3. Print the plan and ask for approval.
4. Run the harness with `--yes`:

```bash
python3 /Users/am/ai-workspace/shared-skills/tl-channel-workflow/scripts/tl_channel_workflow.py dual-verify \
  --scope project \
  --prompt-file /tmp/tl-channel-prompt.md \
  --yes
```

5. Summarize confirmed findings and give the raw inspection command if the channel was preserved.

## Harness Commands

```bash
python3 scripts/tl_channel_workflow.py review --prompt-file PROMPT.md
python3 scripts/tl_channel_workflow.py dual-verify --prompt-file PROMPT.md
python3 scripts/tl_channel_workflow.py implement --prompt-file PROMPT.md --write
python3 scripts/tl_channel_workflow.py research --prompt-file PROMPT.md
python3 scripts/tl_channel_workflow.py forum --channel NAME --thread THREAD --title TITLE --text-file BODY.md --yes
python3 scripts/tl_channel_workflow.py inspect --channel NAME --raw
python3 scripts/tl_channel_workflow.py self-test
```

Without `--yes`, worker-spawning commands print a plan and exit before spawning.

## Output Contract

Worker prompts request JSON. Treat invalid JSON as a workflow finding, not as success. Final user output should separate:

- `confirmed`: verified findings or facts.
- `rejected`: reviewer claims the verifier rejected.
- `needs_human`: items that need user judgment.
- `channel`: name and inspect command.

Implement mode additionally reports:

- `implementer`: files changed, checks run, and unresolved questions.
- `checkers`: `checker-1` from Codex and `checker-2` from Claude Code, each reporting approval, findings, and test gaps.
