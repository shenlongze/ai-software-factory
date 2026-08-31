# S31-001.5 — Long-running Run Architecture Record

> 日期: 2026-08-31 | 真实案例记录 (非设计稿)

## 核心事实

**Run 生命周期独立于 Browser / SSE / Watcher 生命周期。**

```
真实案例: Run R1788175174725 (台球记分 MVP 设计链)

时间线:
  11:19:49  Run 启动 (POST /api/projects/P-69c4f155/start)
            status=running, stage=product (WF-DESIGN, product-manager)
            calls=1, tokens=1639, cost=$0.000644
  ...       watcher (60×10s=10min) 超时退出
  ...       Run 继续后台执行
  至今       status=running (Browser/SSE/Watcher 全断开, Run 不受影响)
```

## 架构结论

### 三个生命周期必须分离

```
Request lifecycle (HTTP/SSE 连接)     — 秒级, 可断
Watcher lifecycle (观察/轮询)          — 分钟级, 可超时
Production Run lifecycle (真实执行)    — 分钟~小时级, 独立持久化
```

### Run 是持久化 Production Fact

```
Browser CLOSED → Session 仍在 → Run 仍在 → Agent 继续 → Artifact 产生 → Verification 运行
Browser REOPEN → Session reload → Run state restored → "任务已完成"
```

### Watcher timeout ≠ Run timeout

- Watcher 退出只是"观察者离开", 不是"任务失败"
- UI 不得把 watcher timeout 显示成 Run failed

## 对 UI 的要求 (S31-002 起)

1. Run 状态卡显示**真实持久状态** (来自 /api/sessions/{id}/runs), 非前端猜测
2. 刷新/重连后从后端恢复 Run state
3. 长任务期间 UI 显示"运行中" (真实 status=running), 永不显示超时/失败
4. 用户重新打开 → 看到 Run 最终结果 (completed/failed 由后端事实决定)

## 对 Runtime 的后续要求 (P1, 不阻塞 S31)

- Run 应有持久 execution state (progress.json 已有, 需完整化)
- event/polling/subscription 让任何 client 可重连
- 不修改 Run lifecycle 迎合 watcher

## 本案例价值

R1788175174725 证明: **AI Factory 的 Run 已脱离 Web 请求生命周期, 可长时间自主运行。**
这是 AI Work OS 的核心特性, 保留作为长期生产证据。
