# S34 — Conversation-First Production Reality & Context Integrity 审计

> 日期: 2026-08-31 | 依据: 真实代码 + API + 存储 + 浏览器行为

## P0-1 Current Context 唯一性 — PARTIAL

```
✅ session.project_id 唯一来源 (console_sessions.json, 23/51 会话)
✅ project_id 全部在 org 或 project_ 前缀 (无孤儿)
❌ 公司级会话 (project_id=None): AI 猜当前项目
   真实案例: "我要一个飞机大战的web" (公司级)
   → AI 说"当前项目是 P-f848f51d" (猜的! 错!)
   → 项目关联错误

结论: context resolver 缺"无项目时明确询问/新建"逻辑
```

## P0-2 Project Identity Integrity — BROKEN

```
Case A "P-f848f51d 是什么项目":
  ✅ 识别 ID → project_list/project_status → 真实回答
  ⚠️ 但 name 漂移: org=日记 / project.json=小鹏日记 / API=日记
Case B "项目列表":
  ✅ project_list 工具 (不再 bash 扫)
Case C "我的飞机大战呢":
  ❌ 飞机大战从未正确创建/关联
  根因: 公司级会话 AI 猜 P-f848f51d → 初始化失败 → 项目意图丢失
```

## P0-3 Project Name/Description/Intent 一致性 — BROKEN

```
漂移 3 处:
  P-5be3a04a: org lifecycle=idea vs project.json status=development
  P-f848f51d: org name=日记 vs project.json name=小鹏日记
  P-f848f51d: org lifecycle=idea vs project.json status=development

org/projects.json = name SSOT (S34-003B 定) 但 project.json 不同步
```

## P0-5 Tool Protocol 泄漏 — PARTIAL

```
✅ 历史 27 条已清 (migration)
❌ 新增 5 条 (15:59-16:17 UTC):
  根因: send_message 落库前未清洗 reply (v1/回退路径)
  → 出口防线缺失 (stream v3 有, send_message 无)
```

## P0-6 Tool Selection Integrity — PARTIAL

```
bash_exec 88 次 (最高频) vs project_list 8 次
根因: 工具 schema 描述引导不足, 复杂任务 AI 倾向 bash
✅ project_list 已建 (项目列表走 API)
⚠️ 仍需: project_get (单项目查询) + 工具选择强化
```

## P0-8 Project Switching — 待测

## P0-9 Conversation Continuity — 待测

## P0-10 Browser Lifecycle — 待测

## Failure Matrix

```
P0:
  F1: 公司级会话 AI 猜项目 (无 context 询问) — P0-1
  F2: 飞机大战项目意图丢失 (创建未关联) — P0-2
  F3: project.json ↔ org 漂移 (name/status) — P0-3
  F4: send_message 落库未清洗 (5 条新泄漏) — P0-5
P1:
  F5: bash_exec 高频 (工具选择引导)
P2:
  F6: Search/Delete 缺失
```
