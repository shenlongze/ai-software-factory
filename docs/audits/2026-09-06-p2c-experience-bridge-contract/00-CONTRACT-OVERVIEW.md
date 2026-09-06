# 00 — CONTRACT OVERVIEW (P2-C EXPERIENCE BRIDGE, 2026-09-06)

> 阶段: P2-C Experience Bridge Contract Freeze — 只冻结, 不实施
> 基线: 90caeb91 (P2-A) | 前置: Post-P2A Global Closure (PARTIALLY CLOSED)
> 产出: 本目录 20 份契约文档; 零代码/零数据改动

---

## 1. 核心判定

```
Status: GO (contract 级 — 待人工批准进入 P2-C Implementation)
```

- Experience canonical model 可冻结 (exp-* 保留, 加 provenance FK)
- provenance 可冻结 (Model B — Anchor provenance)
- writer 可冻结 (ExperienceBridge 唯一新写入口; 现有 ExperienceStore.add 收敛)
- trigger 可冻结 (P0 finalize 后 + P2-A RELEASE 后 — 双触发)
- legacy 隔离可冻结 (M3 AutoLearner 提取路径保留 legacy, 新桥独立)
- P0/P1/P2-A boundary 清晰 (consumer-only, 零 authority 修改)

## 2. 契约核心 (见分文档)

- **Experience = 派生 Learning Fact** (非生产第二 SSOT; production 不依赖 exp)
- **Model B Anchor provenance**: exp 存 task_run_id + exs_id + release_id(可选),
  其余经 canonical reverse_trace 获取 (不复制事实)
- **唯一 writer**: ExperienceBridge (新, 收敛 ExperienceStore.add)
- **双 trigger**: finalize_node_run (P0 执行完成) + RELEASE finalization (P2-A)
- **幂等**: (source, source_id) 唯一键
