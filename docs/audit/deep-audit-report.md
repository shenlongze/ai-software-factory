# 《项目深度审计与诊断报告》

> 日期: 2026-08-31 | 审计者: 首席架构师 + 安全审计专家 (Hermes)
> 方法: SOP 全量扫描 (tsc/pytest/build/API对账/状态追踪/质量排查), 全部以真实代码为准
> 基线: 前端 747/748 测试 + tsc PASS + build PASS; 后端 1117 passed + 6 skipped + py_compile PASS

---

## 1. 总体健康度评分

```
总体健康度: 32 / 100

维度评分:
  契约一致性:    78/100  (27 前端 API 全部匹配后端, 无 404; 字段级基本对齐)
  状态管理:      35/100  (双会话系统并存, 组件间状态断裂)
  代码质量:      40/100  (静默失败/死代码/硬编码, 但无密钥泄漏)
  数据持久化:    55/100  (关联字段存在, 但核心实体生产数据为 0)
  架构清晰度:    20/100  (死代码 14K+ 行, God Object, 双包名)
  产品可用性:    10/100  (生产数据 0 会话/0 任务/0 需求, 闭环从未走通)
```

**核心结论**: 这是一个**契约层基本健康、但产品层从未真实运转**的系统。
代码"零件"能编译、能测试(测试环境),但核心业务(会话→任务→执行→落地)
在生产数据里一个实体都没有。架构上存在大量死代码与未接线能力。

---

## 2. 致命/高风险问题列表

### 🔴 P0-1: 核心业务闭环从未真实发生 (架构级)
- **现象**: 生产数据 (`/Users/agentdev/.factory`) conv=0, task=0, req=0, 仅 2 project + 4 审批
- **根因**: 前端三栏只消费 27/313 API; 执行链 (`runtime/execute`/`trigger_work`/`task_tree`) 前端未调用; 75 个 patch 生成但 workspace 落地代码 = 0
- **影响**: 用户无法通过对话驱动任何真实工作; 产品 = 空壳

### 🔴 P0-2: 会话理解 = 关键词正则 (非真实对话)
- **文件**: `factory-console/conversation_os.py:39-45` (INTENT_PATTERNS)
- **现象**: "这软件给谁用" → DISCUSS (错); "现在干嘛呢" → DISCUSS (错)
- **根因**: 纯正则匹配关键词, 非 LLM 语义理解
- **用户实测**: "我有哪些项目" 被回复成 "聊聊「」目标用户是谁"

### 🔴 P0-3: 双会话系统并存 (状态断裂)
- **文件**: `ConversationContext.tsx` (旧 `/api/sessions`) vs `AfConversationCenter.tsx` (新 `/api/conversations`)
- **现象**: 两个会话系统独立 state, 左栏 Context 与中栏 Center 可能显示不同会话
- **根因**: K6-K9 迭代新增新系统, 旧系统未摘除
- **已部分修复**: workspaceConversationId 桥接 (v1.1.364), 但旧系统仍在

### 🟡 P1-1: 静默失败 (异常被吞)
- **文件**: `BrowserWorkspace.tsx:109,117,121` (3 处 `.catch(() => {})`), `ConversationContext.tsx:169`
- **现象**: API 失败无任何反馈, 用户看到空态但不知为何
- **缓解**: BrowserWorkspace 为死代码 (外部引用 0), 影响有限

### 🟡 P1-2: 硬编码开发 URL
- **文件**: `AfBrandHeader.tsx:36` `href="http://127.0.0.1:8011/api/board"`
- **现象**: 部署到非本机环境会失效
- **建议**: 从配置/env 读取

### 🟡 P1-3: 未处理 Promise (fire-and-forget)
- **文件**: `AfContextNav.tsx:31`, `AfSidebar.tsx:76,102,137`, `AfWorkspace.tsx:54`
- **现象**: `.then()` 无 `.catch()`, 失败时未处理 rejection
- **影响**: 组件可能静默不更新, console 有 unhandled rejection

### 🟡 P1-4: 前端死组件
- **文件**: `BrowserWorkspace.tsx` (0 引用), `AfCompanyHome.tsx` (0), `AfMonitorPage.tsx` (0), `AfSidebar.tsx` (1, 仅注释), `AfConversationPanel.tsx` (2, 回退路径)
- **影响**: 维护负担 + 误导 (看似有用实则死)

### 🟡 P1-5: AfContextNav 无三态 (loading/error/empty)
- **文件**: `AfContextNav.tsx` (三态处理 0 次)
- **现象**: 左栏加载失败时静默显示空, 无错误提示

### 🟢 P2-1: God Object
- **文件**: `cli_factory.py` 8145 行, `service.py` 4911 行
- **建议**: 拆分 (但非紧急, 功能正常)

### 🟢 P2-2: 后端死模块 (API 层未引用但全局有引用)
- learning_engine_v2 (15 引用) / llm_router (5) / artifact_lifecycle (14) / agent_kernel (9)
- 非完全死代码, 但大量能力未进产品路径

### 🟢 P2-3: 双包名混乱
- `factory_console/` (别名) vs `factory-console/` (源码), editable finder 复杂
- 曾导致 factory start 后端加载旧代码

---

## 3. 契约/数据流断层清单 (前端 vs 后端)

| 前端组件 | 调用的 API | 后端存在 | 契约匹配 | 缺口 |
|---------|-----------|---------|---------|------|
| AfConversationCenter | conversations/create/get/sendMessage | ✅ | ✅ | 无执行链 |
| AfWorkspace | artifactContent/osProjectStatus/opsDrill | ✅ | ✅ | 无任务树/执行 |
| AfContextNav | conversations/opsOverview/osProjects | ✅ | ✅ | 无三态 |
| AfMessageCard | osDecideApproval | ✅ | ✅ | 无执行触发 |
| **(未接)** | /api/runtime/execute | ✅ 存在 | — | 🔴 主链 API 未用 |
| **(未接)** | /api/tasks/ (task-tree) | ✅ 存在 | — | 🔴 任务树未用 |
| **(未接)** | trigger_work (对话触发) | ✅ 存在 | — | 🔴 对话→执行断 |

**前端请求路径 27 个全部能匹配后端 (无 404)。** 断裂不在"路径", 在"能力未接"。

---

## 4. 重构/修复优先级路线图

### P0 (必须立即修复 — 产品成立的前提)
```
P0-1 会话 LLM 化: conversation_os 理解/回复 → LLM (语义 + 说人话), 保留规则 fallback
P0-2 执行闭环: 对话 → 建项目 → 拆任务 → 真实执行 → 结果回对话
P0-3 代码落地: 执行结果真实写盘 (patch apply 闭环)
P0-4 统一会话系统: 摘除旧 /api/sessions 路径 (AfConversationPanel/Context 旧逻辑)
```

### P1 (重要 — 质量与可信)
```
P1-1 静默失败修复: 所有 .catch(() => {}) 加错误提示
P1-2 硬编码 URL: AfBrandHeader 从 config 读取
P1-3 未处理 Promise: 补 .catch
P1-4 前端死组件: 删除 BrowserWorkspace/AfCompanyHome/AfMonitorPage; AfSidebar 摘除
P1-5 AfContextNav 三态: 加 loading/error/empty
P1-6 factory start 加载旧代码: 修路径解析
```

### P2 (后续 — 整洁与健康)
```
P2-1 God Object 拆分: cli_factory(8145)/service(4911)
P2-2 死模块决策: learning_engine_v2 等 15+ 模块冻结或接线
P2-3 双包名统一: factory_console vs factory-console
P2-4 文档重建: 828 份过期文档以代码为准重写
P2-5 326 未推送提交
```

---

## 5. 附录: 审计探针输出 (关键凭据)

```
[基线] 前端: 747/748 + tsc 0 + build PASS
[基线] 后端: 1117 passed + 6 skipped + py_compile 0
[API] 前端调用 27 路径 / 后端 313 端点 → 全部匹配, 无 404
[死代码] BrowserWorkspace 外部引用 0 / AfCompanyHome 0 / AfMonitorPage 0
[硬编码] AfBrandHeader.tsx:36 → http://127.0.0.1:8011/api/board
[静默] BrowserWorkspace.tsx:109,117,121 → .catch(() => {})
[生产数据] conv=0 task=0 req=0 project=2 approval=4 workspace_code=0
[执行链] 75 patch 生成, 0 落地
```
