# Quick Start — AI Software Factory (5 minutes)

> v1.0.0-rc1 · CLI First · Local deployment · Full audit trail

## What you'll do in 5 minutes

1. Install
2. Initialize (`factory init`)
3. Configure your LLM
4. Diagnose (`factory doctor`)
5. Create a project
6. Run your first AI task (`factory run`)
7. View the artifact

---

## 1. Install

```bash
# Option A — from source (currently recommended)
git clone https://github.com/shenlongze/ai-software-factory.git
cd ai-software-factory
bash scripts/setup.sh          # creates .venv, installs deps, smoke-checks

# Option B — pip (coming soon)
# pip install ai-software-factory
```

After install, the `factory` command is available:

```bash
./bin/factory --help
```

## 2. Initialize

```bash
factory init --non-interactive --provider deepseek
```

This creates your workspace (`~/.factory/`) with agents, skills, projects and
provider directories, then writes `providers.json` with your chosen provider.

> `providers.json` stores only a **reference** to your API key
> (`api_key_ref: "env:DEEPSEEK_API_KEY"`) — never the key itself.

## 3. Configure your LLM

AI Factory never stores plaintext keys. Set your key in the environment:

```bash
export DEEPSEEK_API_KEY="sk-..."   # DeepSeek example
```

Supported providers (in `providers.json`): `deepseek`, `openai`, `anthropic`,
`ollama` (local, no key needed).

## 4. Diagnose

```bash
factory doctor
```

Checks environment, provider, model catalog, runtime and router —
each with PASS / WARN / FAIL and a fix hint.

```bash
factory doctor --json   # machine-readable for CI
```

## 5. Create a project

```bash
factory project create --repo-path /path/to/your/code --name my-project
factory project list
```

Or use the isolated demo workspace:

```bash
factory demo init
factory demo status
```

## 6. Run your first AI task

```bash
mkdir -p /tmp/todo-app && echo "print('hello')" > /tmp/todo-app/main.py

factory run \
  --project /tmp/todo-app \
  --task E2-001 \
  --agent backend-1
```

This triggers the real execution chain:
Task → Agent → LLM (via the Router's decision) → sandbox → artifact.
The LLM call is **real** (DeepSeek/OpenAI/your provider) — not demo data.

## 7. View the artifact

```bash
factory run-status --id <result-id>
```

The run prints its `result_id` (e.g. `EXS-...`). The status shows:

```
status      success
artifact    patch     ~/.factory/exec/patches/EXS-....patch
artifact    report    ~/.factory/exec/EXS-....report.md
usage       {'prompt_tokens': ..., 'completion_tokens': ..., 'estimated_cost_usd': ...}
```

Every step is audited — inspect events with:

```bash
factory audit
```

---

## What you should see

- **Real LLM execution** — not mocked output
- **Approval gate** — AI output waits for human approval
- **Full audit** — who / what / when / which model / how much it cost

## Troubleshooting

| Problem | Fix |
|---|---|
| `factory doctor` warns about provider key | `export DEEPSEEK_API_KEY=...` then re-run |
| `factory run` says provider not found | `factory config check` — verify `providers.json` |
| Want a different model per task | Configure `agent.yaml` / `project.yaml` (Router rules) |

## Next steps

- `factory demo init` — isolated demo workspace
- `factory service list` — backend / frontend / runtime status
- `factory start` — launch backend + frontend
- Docs: [vision](./product/vision-en.md) · [development](../../docs/development.md)

---

*Command names verified against v1.0.0-rc1.*
