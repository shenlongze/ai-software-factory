# S10-007 — 阶段四: 真实用户验收报告（Acceptance Report）

> 日期: 2026-08-10 | 状态: 核心目标达成 (Review gate 缺失已记录) | 证据: /tmp/s10-007-phase4/evidence3/

## 验收方式

模拟无程序经验用户 (Playwright headless 真实浏览器 + 隔离 HOME 干净环境):

```
./factory start (隔离 HOME /tmp/s10-007-phase4/home + key env 注入, 无明文落盘)
  ↓
Welcome 首屏 "你想创建什么软件?" → 输入 "一个简单记账 App" → [开始生产]
  ↓
创建项目 (ledger-app) → [🚀 开始开发] → 真实 Agent 链 (deepseek-v4-pro)
  ↓
等待全链 (729s) → 轮询 run-status/timeline/artifacts
```

## 7 点验证结果

| # | 验证点 | 结论 | 证据 |
|---|--------|------|------|
| 1 | Product Agent 工作 | ✅ | product COMPLETED, calls=1, 40.05s, $0.000858 (真实 LLM usage: prompt 309/completion 1838 tokens) |
| 2 | 需求分析产物 | ✅ | PRODUCT/UXUI/DESIGN artifacts validated (docs/*.json) + idea.md 注册 |
| 3 | Timeline | ✅ | 28 事件 (created→started→stage→completed) + 49 张 UI watch 截图 |
| 4 | Artifact | ✅ | 7 类全部 validated; release zip 实体 (app.js/index.html/style.css/smoke_check.py) |
| 5 | Review gate | ❌ | 一键链无审批门 — 已知契约 (三挡板未接入真实用户流), 功能缺失如实记录 |
| 6 | approve 后继续 | ❌ | 不适用 (无审批门, 同 5) |
| 7 | 最终 release 产物 | ✅ | dist/app-1.0.0.zip (4 文件, 32,439 B), RELEASE artifact validated |

## 真实执行统计

```
6/6 阶段 COMPLETED (product→ux_ui→design→development→testing→release)
7 次真实 LLM 调用 | 76,733 tokens | 费用 $0.028776 | 耗时 729.98s (~12.2min)
```

## 验收中发现并修复的真实缺陷 (干净环境暴露, 开发环境被掩盖)

```
缺陷 #1: git baseline commit 英文环境误判 ("nothing to commit" 在 stdout,
         代码只在 stderr 查) → 链启动即 failed → 已修 (combined stderr+stdout)
缺陷 #2: load_llm_key() 死代码 (start 路径只调 has_llm_key 检查不注入) →
         干净环境 OpenAIProvider 读不到 OPENAI_API_KEY → 已修 (补调用)
```

## 缺失功能 (产品缺陷, 如实记录)

```
1. Review gate 未接入真实用户流 (一键链无审批门) — 用户"关键节点审核"要求未达成
   → 下一步: 真实链插入审批门 (PM/设计/发布门) + Review 中心联动
2. 产物文件系统实体与注册的对应关系待核实 (docs/*.json 注册 validated 但未在 run 树找到实体
   — 可能存 sqlite) — 观察项
3. 开发链写文件未 commit (git status 全 untracked) — 链完成不受影响, 产品观察
```

## 结论

```
✅ 达成 S10-007 完成标准: AI Factory 脱离 Hermes, 在干净环境启动,
   完成一次完整软件生产 Demo (输入需求 → 软件产物)
❌ 未达成: 关键节点人工审核 (Review gate) — 记录为下一步最高优先
```

## 下一步

```
1. 真实链接入审批门 (三挡板: 需求/设计/发布) + Review 中心联动 — P1
2. 产物落盘核实
3. 阶段五: README (3 分钟运行指南)
```
