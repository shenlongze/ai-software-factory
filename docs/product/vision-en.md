# Product Vision — AI Workforce Operating System

> **English** · [中文版](./vision-zh.md)

## The Idea in One Sentence

**AI Factory is the AI Workforce Operating System — it manages AI workers,
instead of chatting with AI.**

## From Human-Only to Human-Managed AI

### Traditional software development

```
Human
  ↓
Code
```

### The AI era

```
Human
  ↓
AI Organization        ← AI Factory (the operating system)
  ↓
AI Workers             ← agents with roles, skills, permissions
  ↓
Software Output        ← code, tests, docs, artifacts — all audited
```

Traditional tools put the human in a chat loop with code.
AI Factory puts the human **above** an organization of AI workers —
planning, reviewing, approving, auditing.

## Positioning

> **Devin executes tasks. AI Factory manages AI workers.**

- Devin / Cursor / Claude Code are great **workers**.
- AI Factory is the **operating system** that organizes, governs and audits
  those workers at company scale.

## What AI Factory Provides

| Layer | Capability |
|---|---|
| **Organize** | Agents as employees: roles, skills, teams (org metaphor) |
| **Decide** | AI Router: which model for which task (User > Agent > Project > System > Fallback) |
| **Execute** | Real LLM execution: Task → Agent → LLM → sandbox → artifact |
| **Govern** | Approval gates, permission chains, human in the loop |
| **Audit** | Full event trail: who / what / when / which model / how much |

## Target Users

1. **Developers** — control multiple models, real execution, cost visibility
2. **Startup teams** — one person + AI workforce ships a product
3. **Enterprise AI teams** — governance, compliance, audit at scale

## What We Believe

- **Human in the loop, decision power in humans.** AI proposes, humans approve.
- **Evidence driven.** Every claim must be backed by artifacts and events.
- **Governance is the moat.** Managing AI is the problem; generating text is not.
- **Open core.** Community builds on the shell; enterprise pays for governance.

## Status

- v1.0.0-rc1 — CLI-first MVP: install → init → real LLM execution → artifact
- 8148 tests green · full audit trail · multi-provider router

---

*See [vision-zh.md](./vision-zh.md) for Chinese version.*
