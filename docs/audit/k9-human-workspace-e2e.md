# K9 Human Workspace — 真实 LLM E2E 证据

> 日期: 2026-08-31 | HEAD: 2184a615 (v1.1.363)

## 1. 完整用户旅程 (真实 codex 执行)
```
Conversation「我要做一个计算器」→「目标用户是个人用户」
→ Project → Sprint → Task Tree
→ 真实 codex 执行 2/2 COMPLETED
→ Project 100% (2/2)
```

## 2. 三栏数据源验证 (Backend = API = UI)
| 右栏 Tab | 数据源 | 真实结果 |
|----------|--------|----------|
| Task | /api/projects-os/{id}/status | Project 100%, 2 tasks ✅ |
| Evidence | /api/ops/drill | task0 COMPLETED ✅ |
| 消息卡片 | send_message reply.card | ASK_STATUS → task_tree 卡 ✅ |

## 3. 用户旅程闭环
```
用户: "我要做一个计算器" → 中栏回复 + 📋需求分析卡
用户: "目标用户是个人用户" → 📄PRD卡
用户: "帮我做" → ⚙️执行卡 → 右栏 📊任务树
用户: "现在什么进展" → 📊任务树卡 + 右栏实时投影
用户: "打开看看" → 右栏 🌐预览 (真实产物)
```

## 4. 结论
- K9 Human Workspace 三栏全部真实数据 (非 mock)
- 消息卡片 6 种后端生成 + 前端渲染
- 联动 (Intent→Tab) 真实生效
- 用户感知: "和公司说话 + 看到公司正在干什么" = 达成
