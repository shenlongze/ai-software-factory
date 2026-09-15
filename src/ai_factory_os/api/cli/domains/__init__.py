"""CLI 域包 —— 按架构域组织命令注册（api/cli/domains）。

为什么要有它（2026-09-15, Founder 追问「cli 有分类么」）:
    CLI 的命令面此前**代码层零分类** —— 现有 factory 入口 91 个命令全平铺在一个
    10,155 行的文件里; 新 CLI 的 91 个 handler 也在单文件里（虽有名名前缀）。
    ⇒ 按「命令 → 域」的注册表（`api/cli/registry.py`, ★ 单一事实源）逐域拆开。

纪律:
  · 每个域一个模块, 只注册**本域**的命令 —— 域归属以 `api/cli/registry.py` 为准
  · 本包只做**参数注册**（parser 形状）; handler 实现仍在 `commands.py`（后续逐域搬）
  · 域清单来自 SSoT `docs/ssot/architecture.md` §二, 不在本包另抄一份

为什么包名是 `domains` 而不是 `commands`:
    `api/cli/commands.py` 已存在（handler 实现）—— 同名包与模块不能并存, 故取 `domains`。
"""
from __future__ import annotations
