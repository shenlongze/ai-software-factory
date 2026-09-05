# 06 — LEGACY ISOLATION (P2-A CONTRACT, 2026-09-06)

## 1. 冻结

| 对象 | 分类 | 处置 |
|---|---|---|
| rel-* (0 条真实) | **LEGACY (M3)** | 保留 store/代码; 不迁移不回填不重建 |
| M3 production_run | LEGACY | 隔离 (rel-* 仍可服务 M3 域, 若未来用) |
| M3 evaluation | LEGACY | 隔离 |
| _run_verification (自跑 pytest) | LEGACY 机制 | 新 Release 不用 (ver-* 已承担) |

## 2. 分区存储

releases.json 同时容纳 rel-* (legacy 段) + RELEASE-* (canonical 段)?
→ **否**: 新 RELEASE-* 独立 store 或同文件 id 前缀分区。决策: 同文件但
RELEASE-* 前缀唯一 (rel-* 记录保留原样, 新 create 只产 RELEASE-*) —
最小侵入, 无迁移。list 时按前缀过滤。

## 3. 禁止

migration / backfill / fabricated release / reconstruction —
历史 0 条 rel 无需处理; 未来 M3 若产 rel 保持 M3 语义。
