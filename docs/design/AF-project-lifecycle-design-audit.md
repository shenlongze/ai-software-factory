# AF Project Lifecycle Design Audit

> 日期: 2026-08-11 | 作者: Orchestrator (审计) | 状态: 待确认后实施 (AF-CORE-001)
> 基线: 49a3d2e (pytest 6674 / vitest 305)

## 一、当前设计 (实测代码)

### 1.1 Project 创建流程

```
前端 (WorkspaceView): 输入想法 → [分析需求] → AI 理解卡片 (suggest) → [确认创建]
  → POST /api/projects {idea, name?} (name = 用户确认的名称)
后端 (api/projects.py create_project):
  → service.create_project → org ProjectLifecycle.create_project
  → org/projects.json 落一条 Project 记录 {id: P-xxx, name, goal, lifecycle: "idea"}
  → 立即返回正式项目 (带名称, lifecycle=idea)
```

### 1.2 Project 数据模型 (org/projects.py Project)

```
字段: id / name / user_id / goal / lifecycle / repo_path / language /
      framework / build_command / test_command / project_type /
      analysis_ref / baseline_ref / snapshot_ref / created_at / updated_at
存储: <root>/org/projects.json (集中式 _SectionStore, id 索引)
状态机 (ProjectState): IDEA → ACTIVE → MAINTAINED → ARCHIVED
  PROJECT_TRANSITIONS: idea→(active,archived) ...
```

### 1.3 运行目录 (workflow_runner._run_dirs)

```
<root>/workflow_runs/{project_id}/{run_id}/
  app/    (代码 — 每 run 独立临时沙箱)
  dist/   (发布产物 zip)
  progress.json / report.json
→ 代码放临时 run 目录, 不属于项目生命周期目录
```

### 1.4 API 清单

```
POST /api/projects/suggest  {idea} → {suggested_name, slug, summary, questions, ai_generated}
POST /api/projects          {idea, name?, project_type?, tech?} → 创建正式项目 (lifecycle=idea)
POST /api/projects/{id}/start   → 真实 Agent 链 (product→...→release)
POST /api/projects/{id}/chat    → 持续开发对话
GET  /api/projects/{id}/run-status | timeline | artifacts
PATCH/DELETE /api/projects/{id}
```

### 1.5 前端 Welcome

```
输入想法 → [分析需求] → AI 理解卡片 (名称可编辑 + 摘要 + 澄清问题)
  → [确认创建] → 创建正式项目 → 进入工作台
✓ 已有: AI 沟通环节 (suggest) — 用户确认后才创建
✗ 缺失: Draft 阶段 (unnamed-project-XXX → DISCOVERY → 确认 → 命名)
```

## 二、存在问题 (与目标模型偏差)

| # | 偏差 | 影响 |
|---|------|------|
| 1 | **无 Draft 概念**: 创建即正式命名 (ledger-app), 无 unnamed-project-001 阶段 | 用户没确认名称前已"定名"; 无法反悔 |
| 2 | **状态机缺 Discovery/Confirmed**: 只有 idea→active→maintained→archived; 无 DISCOVERY→CONFIRMED→DEVELOPMENT→RELEASE | 无法表达"需求澄清中/已确认/生产中/已发布" |
| 3 | **无产品沟通持久化**: suggest 是一次性响应, 澄清问题不落库、无 discovery 记录 | 用户确认后丢失"为什么叫这个名/答了什么" |
| 4 | **无项目目录结构**: 只有 org/projects.json 记录 + workflow_runs 临时沙箱; 无 idea/discovery/space/knowledge/artifacts 目录 | 产物/需求文档无固定家; 代码与项目生命周期解耦 |
| 5 | **workspace 无 index**: 项目列表 = org/projects.json 全部; 无"已确认项目"与"draft"区分视图 | 前端无法区分 draft/正式 |

## 三、目标模型 (用户定义)

```
AI Factory → Workspace (容器) → Project (生命周期主体)
  Project:
    Idea          (conversation.json + idea.md)
    Discovery     (AI 产品经理沟通: 方向/痛点/画像/场景/功能/MVP/使用方式/商业)
                  → product-definition.md → 用户确认
    Definition    (确认: 产品名称/定位/价值/用户/功能/边界)
    Project Space (requirements/design/development/testing/release/)
    AI Team Execution
    Knowledge / Artifacts / History

状态机: IDEA → DISCOVERY → CONFIRMED → DEVELOPMENT → RELEASE
创建: 输入想法 → unnamed-project-001 (DISCOVERY) → AI 沟通 → 用户确认
      → 正式命名 (rename 目录 + 索引/引用更新)
```

## 四、修改方案 (AF-CORE-001)

### Task 1: Domain Model (org/projects.py)
```
- ProjectState 扩展: IDEA → DISCOVERY → CONFIRMED → DEVELOPMENT → RELEASE
  (保留 ACTIVE/MAINTAINED/ARCHIVED 兼容旧数据 — 受控转换表扩展, 不删旧值)
- PROJECT_TRANSITIONS 更新: idea→(discovery,archived) / discovery→(confirmed,archived)
  / confirmed→(development,archived) / development→(release,archived) / release→(archived)
- Project 字段扩展 (带默认值, 零破坏):
  - status_meta: {discovery: {questions:[], answers:{}, product_definition_ref}, ...} (或轻量字段)
  - draft: bool (默认 False — 旧数据兼容)
```

### Task 2: 项目目录结构 (新 ProjectStore 布局)
```
<root>/workspace/projects/{project_slug}/
  project.json          (Project 记录镜像 — 生命周期主体)
  idea/conversation.json + idea.md
  discovery/product-definition.md (AI 沟通产物)
  space/{requirements,design,development,testing,release}/
  knowledge/  artifacts/
```
```
迁移: org/projects.json (索引) → 每项目目录; 或双写:
  方案 A (推荐): workspace/projects/{id}/project.json 为信源 + org/projects.json
    保留为索引 (读兼容); 新项目走目录, 旧项目懒迁移 (读取时回填目录)
  方案 B: 全量迁移脚本 (一次性搬移 + 索引重建) — 风险高 (用户已有项目)
推荐 A (零破坏, 新老共存)
```

### Task 3: 创建流程改造
```
POST /api/projects (改造):
  输入 {idea} → 创建 Draft: id=unnamed-project-{seq} 或 {draft-id},
  lifecycle=discovery, name="unnamed-project-XXX", draft=true
  → 返回 {project_id, name: unnamed..., lifecycle: discovery}
POST /api/projects/{id}/discovery/answer {question, answer} (AI 持续沟通记录)
POST /api/projects/{id}/confirm {name} → 正式命名:
  1. 校验 name 唯一/合法
  2. rename 目录 (unnamed→scorepocket) + 更新 project.json/索引/产物/历史引用
  3. lifecycle: discovery → confirmed
  4. 返回 {project_id, name: scorepocket, lifecycle: confirmed}
POST /api/projects/suggest 保留 (AI 提议名称/理解/问题 — 作为 discovery 沟通起点)
```

### Task 4: 前端改造 (Welcome)
```
输入想法 → [创建草稿] → 进入 Draft 工作台 (DISCOVERY 状态可见)
  → AI 理解卡片 (suggest) + 澄清问题逐条问答
  → 用户确认名称 (可编辑) → [确认并命名] → 正式项目 (confirmed) → 生产空间
旧"确认创建"按钮 → 改名"确认并命名" (语义: 确认=命名+进入开发)
```

### Task 5: 兼容与数据迁移
```
- 旧项目 (ledger-app×4, markpad 等 lifecycle=idea/active):
  → 读取兼容 (org/projects.json 仍可读) + 懒迁移 (首次访问创建目录镜像)
  → 前端旧项目显示"正式项目" (draft=false), 不受影响
- API 兼容: POST /api/projects {idea, name} 旧调用 → 直接 confirmed (跳 discovery,
  向后兼容); 新调用 {idea} 无 name → draft (discovery)
- 测试: 场景1 (draft+discovery+AI 提问) / 场景2 (确认命名 scorepocket + 目录/索引
  正确) / 场景3 (既有项目 MarkPad/AI Factory/TimeOn 不受影响)
```

## 五、验收标准映射

```
场景1: "做一个台球计分 App" → draft (unnamed-project-XXX, DISCOVERY) + AI 提问 ✅
场景2: 确认名称 ScorePocket → 目录 scorepocket/ + 索引正确 ✅
场景3: 既有项目 (MarkPad/AI Factory/TimeOn) 不受影响 ✅
原则: 不 mock 绕过; 先建正确模型再改代码
```

## 六、风险

```
- 目录迁移兼容 (方案 A 双写) — 需仔细处理索引与目录的一致性
- 状态机扩展对旧数据 (lifecycle=idea/active) 的读取 — 枚举扩展需宽容解析
- 前端改动面大 (Welcome/项目树/Draft 视图) — 建议 Task 拆分独立提交
```

## 七、实施顺序 (确认后)

```
Task 1 Domain Model (状态机+字段) → Task 2 目录结构 → Task 3 创建流程
→ Task 4 前端 → Task 5 兼容迁移 → 场景验收 1/2/3 → commit 每 Task
```
