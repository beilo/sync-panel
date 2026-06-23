# Command Contract

## Providers

Allowed providers:

- `codex`
- `claude`

Do not use `--agent`; it loads `.trellis/agents/<name>.md` and conflicts with this skill's worker-only model.

## Create

```bash
tl channel create <name> --scope project|global --type chat|forum --description TEXT --ephemeral
```

Project scope follows current cwd. Global scope uses shared channel storage.

## Spawn

```bash
tl channel spawn <name> --provider codex|claude --as worker-name --timeout 10m --idle-timeout 5m --max-live-workers 2
```

Workers are idle after spawn until a targeted send arrives.

Use stable worker names:

- `implementer-1` (`claude`)
- `checker-1` (`codex`)
- `checker-2` (`claude`)
- `reviewer-1`
- `verifier-1`
- `reader-1`
- `synthesizer-1`

## Send

```bash
tl channel send <name> --as main --to worker-name --text-file /tmp/prompt.md
```

Long prompts use `--text-file` or `--stdin`, never positional text.

## Wait

```bash
tl channel wait <name> --as main --from worker-a,worker-b --kind done,turn_finished --all --timeout 10m
```

Use `--all` when waiting for multiple workers.

## Inspect

```bash
tl channel messages <name> --raw --last 100
tl channel messages <name> --last 50
```

Raw output is the audit source. Pretty output is only an operator view.

## Kill Finished Worker

```bash
tl channel kill <name> --scope project|global --as worker-name
```

Use this after collecting output from a completed stage in a sequential pipeline. It frees the live-worker budget before spawning the next worker.

## Forum

```bash
tl channel create <board> --type forum --scope global
tl channel post <board> opened --as main --thread finding-1 --title "Finding" --text-file body.md --scope global
tl channel forum <board> --scope global
tl channel thread <board> finding-1 --scope global
```
