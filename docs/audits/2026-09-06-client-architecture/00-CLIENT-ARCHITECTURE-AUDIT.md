# 00 — CLIENT ARCHITECTURE AUDIT (2026-09-06, READ-ONLY)

> 基于真实代码扫描 (HEAD 503d3828)。目标: Multi-Client + Single Backend +
> Single Domain Truth 产品化。

## Executive Verdict

AI Factory 当前 = **单一 Python 发行版 (pyproject package-dir 命名空间拼接
factory-core/factory-console/factory-exec/factory-org) + 独立 factory-runtime
发行版 + desktop/ Tauri launcher 壳 + 内嵌 Web build 产物副本**。

**边界现状健康**: WebUI 无业务真相 (全经 api/client fetch); Desktop Rust 无
domain 逻辑 (纯 runtime 子进程宿主); CLI 薄包装调 console services; domain
truth 单 SSOT (P0-P2D 已验)。无第二套 Backend/Runtime/Orchestrator。

**主要结构问题**: ① desktop/ui = frontend build 产物副本但未 gitignore
(构建产物入库) ② 顶层运行时残留 ($SMOKE_ROOT/, exec/checkpoints.json) ③
Web 前端物理嵌于 backend 发行版 (factory-console/web/frontend), 与后端
单进程共部署 — 是现状也是约束 ④ 无顶层入口归位 (apps/clients 不存在)。

## Q1-Q27 摘要
1. 真实入口: Web (factory-console/web/frontend React/Vite)、Desktop
   (desktop/ Tauri 壳)、CLI (bin/factory → factory-console/cli_factory)、
   API (factory-console/web/backend/fastapi_adapter.py, 374 路由)
2. WebUI: factory-console/web/frontend (非顶层)
3. Desktop: desktop/ (src-tauri Rust + src/ui 原生 launcher + ui/ build 副本)
4. CLI: factory-console/cli_factory.py + bin/factory 薄包装
5. Mobile: 不存在 (零 mobile 代码) — 不创建空目录
6. 统一到 apps/? 现阶段不需要 (仅 1 富客户端 + 1 壳 + 1 CLI)
7. 若未来归位: **apps/ > clients/** (入口 = 可部署产品入口; backend console
   是共享内核非 client)
8. 理由: 见 03 报告
9-12. Backend/Domain/Runtime/Shared contracts 位置: 见 01/03
13-17. 需移动/不能移动/legacy/dead/boundary: 见 02
18. WebUI 独立真相: **无** (全投影; mock 仅诚实 fallback is_mock=true)
19-21. 多套 Backend/Runtime/Orchestrator: **无** (单 fastapi/单 workflow/单 domain)
22. Desktop 复用 Web: 未来应经 "Tauri Host → 内嵌 Web (复用同一 build)" —
    现 desktop/ui 已拷 frontend build (同 hash), 机制雏形在
23. Mobile 未来边界: Flutter → API → Backend (禁本地生产逻辑)
24. CLI 正确边界: 薄参数解析 → console service (已是); 禁第二业务后端
25. Monorepo tooling: **不需要** (单 pyproject 已拼接全部 python; 无多包
    独立发布诉求除 factory-runtime)
26. 推荐目标结构: 见 03
27. 低风险迁移: 见 04

## 关键结论
- 无需大爆炸重构。真实工作 = ① gitignore desktop/ui (或改为构建时生成)
  ② 清运行时残留 ③ 未来第二富客户端落地时再建顶层 apps/。
