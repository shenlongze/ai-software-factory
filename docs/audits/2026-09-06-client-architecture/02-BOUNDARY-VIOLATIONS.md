# 02 — BOUNDARY VIOLATIONS (2026-09-06, READ-ONLY)

## P0 边界违规: 无
- 无第二套 Backend / Runtime / Orchestrator / Production Truth (P0-P2D
  单 SSOT 已验; M3 legacy 隔离)
- WebUI 无业务真相 (全 projection); Desktop Rust 无 domain; CLI 无第二业务层

## P1/P2 结构问题
| ID | 问题 | 证据 | 类别 | 建议 |
|---|---|---|---|---|
| S-1 | desktop/ui = frontend build 产物副本入库且未 gitignore | ui/assets/index-Cy5_vISn.js == frontend/dist 同 hash; .gitignore 只 ignore frontend/dist | Duplicate build artifact | desktop/ui 加 .gitignore (构建时生成) 或 desktop 构建脚本从 frontend/dist 拷贝 |
| S-2 | 顶层运行时残留 $SMOKE_ROOT/ + exec/checkpoints.json | $SMOKE_ROOT 字面目录 (shell 展开失败); exec/ 非包仅 1 json | Junk/residual | 清理 (审计后单独决策) |
| S-3 | Web 前端物理嵌 backend 发行版 | factory-console/web/frontend 在 console 包内, 单进程部署 | 现状约束 (非违规) | 记录; 未来拆 client 时移 apps/web (见 03) |
| S-4 | factory_console/ 顶层别名桩 (294b py + 636b cli) | S10-031 连字符包 import 修复 | Design shim | 保留 (必须) — 勿当重复删 |
| S-5 | frontend mock/ 目录存在 | 仅测试 + runtimeClient 诚实 fallback (is_mock=true) | Mock/Demo | 保留诚实标注; 后端补齐后移除 fallback (既有 backlog) |
| S-6 | examples/, projects/, workspace/ 顶层数据目录语义模糊 | 混合示例/数据 | Org | 后续归类 docs/数据根 |

## 分类: Legacy / Dead / Mock
- Legacy (隔离保留): factory-org M3 workflow/project_run/rel-*; demo/;
  unused/; exec checkpoints M3
- Dead 候选 (审计后决策): $SMOKE_ROOT/, 顶层 exec/checkpoints.json
- Mock: frontend mock/ (诚实标注) — 非生产冒充

## DEFERRED (本审计不修)
- 任何 Runtime/Workforce/MCP/Learning/SRE/Production Core 重构
