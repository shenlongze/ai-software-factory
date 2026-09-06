# 05 — SINGLE WRITER CONTRACT (P2-C CONTRACT, 2026-09-06)

## 1. 冻结 writer

**ExperienceBridge** (新, P2-C Implementation 建) = canonical writer

```
ExperienceBridge.record(...)
  → ExperienceStore.add (幂等: (source, source_id) 唯一)
```

## 2. 收敛 (现状 → 未来)

| 写入方 | 现状 | 未来 |
|---|---|---|
| ExperienceStore.add | 公开 (任何调) | 仅 ExperienceBridge 调 (store 降内部) |
| AutoLearner (M3) | 直接 extract+add | LEGACY 隔离 (保留旧路径, 不接入新 canonical) |
| finalize_node_run | 不写 exp | 经 ExperienceBridge (P2-C hook, 失败安全) |
| release_truth.execute | 不写 exp | 经 ExperienceBridge (P2-C hook) |
| CLI/API/WebUI | 无写 | 全经 ExperienceBridge |

## 3. 禁止

orchestrator/release/learning/CLI/WebUI 多头直写 exp store。
