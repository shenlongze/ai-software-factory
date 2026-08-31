# S34-P0-FIX — Conversation Context Integrity & Project Truth 修复报告

> 日期: 2026-08-31 | 依据: 真实代码 + API + 存储 + E2E 实测

## 1. Root Cause

```
F1 猜项目: _repo_fact 在 company scope (project_id="") 时兜底
           /Users/Shared/work/ai-software-factory → AI 误认为有"当前项目"
F2 意图丢失: agent 工具面无 create_project → "做飞机大战"被错误
           关联到最近项目 (P-f848f51d 日记)
F3 漂移: org/projects.json (SSOT) 与 projects/{id}/project.json 双写
         name/status 不一致 (5 处真实漂移)
```

## 2. Architecture Change

```
F1: _repo_fact company scope → 明确"公司级会话无当前项目"引导
F2: create_project 工具 (工具面 schema + dispatch) → 真实注册项目
F3: project_ssot.py (org = SSOT, project.json = 缓存, 幂等对齐)
    + POST /api/projects/ssot-align + GET /api/projects/ssot-drift
```

## 3. Context Resolution Contract

```
company scope:   active_project_id = null (绝不猜)
project scope:   session.project_id = P-xxx (默认继续)
明确引用:        "修改 P-5be3a04a" → project_resolution (真实查询)
```

## 4. Project SSOT Contract

```
org/projects.json = 唯一可变真相 (name/status/stage/goal)
projects/{id}/project.json = 缓存投影 (启动对齐, 只读)
API/UI/AI 回答 = projection (读 org)
```

## 5. Intent → Project Contract

```
"我要做飞机大战" (company)
  → intent: create_project
  → 先确认需求 (不猜项目)
  → create_project(name, goal) → 真实 org 注册 → 返回 project_id
  → 后续 "我的飞机大战呢" → project_list 查 → ID 定位
```

## 6. Migration

```
SSOT 对齐执行: 5 处漂移修正
  P-2f622bdf: P-2f622bdf → 旅行记账
  P-94ec0742: P-94ec0742 → 命令行记账
  P-e023a04c: P-e023a04c → 墨笺
  P-f848f51d: 小鹏日记 → 日记
  ai-factory-self: ai-factory-self → AI Factory 自身
对齐后漂移: 0 (8 项目)
历史 session/run 未动 (只改 name/status 缓存字段)
```

## 7. Tests

```
✅ 后端: 1148 passed + 6 skipped
✅ 专项: 25/25 (含 +3: company 无项目 / SSOT 对齐幂等 / 无漂移)
✅ 前端: 517/518 (af-todo-tree 历史漂移)
✅ tsc | build: PASS
```

## 8. Browser E2E

```
✅ 浏览器: 项目列表 13 个, P-f848f51d=日记 正确 (SSOT 对齐后)
✅ company 会话: "我要一个飞机大战的web"
   → project_list 查 + 确认需求 + 创建 (不猜 P-f848f51d)
✅ 创建: P-b0adfaa6 飞机大战 (org 真实注册)
✅ "我的飞机大战呢" → "找到了,ID 是 P-b0adfaa6" (真实 ID 定位)
```

## 9. Before / After

```
Before: "我要一个飞机大战web" → "当前项目是 P-f848f51d, 在这里做" (错)
        "我的飞机大战呢" → 找不到 / 回答"日记" (错)
        project.json 与 org 漂移 5 处
After:  "我要一个飞机大战web" → 查清单+确认+创建 P-b0adfaa6 (对)
        "我的飞机大战呢" → 定位 P-b0adfaa6 飞机大战 (对)
        漂移 0
```

## 10. Remaining P1/P2

```
P1: 30+ 轮长会话 / budget 配置 / SSE reconnect UI
P2: Search / Delete / 累计成本面板
```

## 11. Git Commit

```
8765b5cb fix(S34-P0): F1 不猜项目 + F2 create_project 工具 + F3 SSOT 对齐
git clean
```

## 12. Final Verdict

```
P0-1 Context Resolution: VERIFIED (company 不猜项目, 实测)
P0-2 Intent Preservation: VERIFIED (创建→ID 关联→可定位, 实测)
P0-3 Project SSOT: VERIFIED (5 处漂移对齐 → 0)
P0-4 Leakage: VERIFIED (send_message 落库清洗, 存储 0)
Conversation as Single Entry: REAL (真实 E2E 全通过)
```
