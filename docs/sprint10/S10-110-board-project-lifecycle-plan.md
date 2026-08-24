# S10-110 Sprint 规格 — Board 单项目管理视图（全生命周期）

> 状态: 待开工 · 版本目标: v1.1.49 (若 T9 字段错位修复未先落地则 v1.1.48) · 2026-08-24
> 来源: Founder 讨论 — "项目之间隔离, 不同时展示, select 切换; 单项目管理视图;
>        全生命周期到部署/运维/更新; 先只读"

## 0. 背景与目标

Board 现有主线面板是 **AI Factory 自身开发进度**（M1-M7/P0）。Founder 要的是
**单项目管理视图**：一次只看一个产品项目，展示该项目的**全生命周期进度**。

**核心原则（Founder 确认）**:
- 项目**隔离**：同一时刻只显示一个项目，绝不跨项目聚合/兜底
- **select 切换**：列出项目名供选择，不并排展示
- **全生命周期**：发现→确认→PRD→工程→开发→测试→验收→交付→部署→运维→更新（11 段）
- **只读**：本次不做任何操作（启动/继续/审批/标记）

## 1. 规格

### 1.1 生命周期阶段定义（11 段, 权威常量）
```
PROJECT_LIFECYCLE_STAGES = [
  ("discovery", "发现"), ("confirm", "确认"), ("prd", "PRD"),
  ("engineering", "工程"), ("development", "开发"), ("testing", "测试"),
  ("acceptance", "验收"), ("delivery", "交付"), ("deploy", "部署"),
  ("operations", "运维"), ("update", "更新"),
]
```

### 1.2 阶段完成映射（确定性, 可断言）
| 阶段 | 完成判定（现有数据） |
|---|---|
| 发现 | `projects/<slug>/product.json` 存在 |
| 确认 | 同上（product.json 落盘 = 已确认） |
| PRD | `PRD.md` 存在 |
| 工程 | `engineering.json` 存在 |
| 开发 | `tasks.json` 存在（任务拆分完成） |
| 测试 | `validation_result.json` 存在 |
| 验收 | product.json `status == "user_acceptance"` |
| 交付/部署/运维/更新 | **占位**（无数据源, 显示"未开始"） |

### 1.3 单项目视图内容
```
📌 当前项目: <名> (<slug>)    [select 切换见 1.4]
🌱 全生命周期: [发现✓ 确认✓ PRD✓ 工程✓ 开发● 测试○ ... 更新○]
   当前卡点: <当前未完成阶段>
📄 文档产物: PRD✅ 工程✅ 任务✅ 验证✅/—
📊 任务进度: ✅x ⬜y (pct%) · 最近更新: <mtime>
```

### 1.4 select 切换
- `/board project`（无参）→ 列出所有项目（slug + 名 + 状态 + 更新时间）
- `/board project <slug>` → 显示该项目单项目视图
- 无显式项目/不存在的 slug → **空态提示**（"未选择项目 / 项目不存在 — 用 /board project 查看列表"），**绝不猜项目/扫描兜底**

### 1.5 入口
- 会话: `/board project [slug]`
- Web: `/api/board?view=project&project=<slug>`（导航 tab 加"项目管理"）
- 隔离: 只读 `projects/<slug>/` 目录该项目的文件; 不聚合其他项目

## 2. 范围声明（硬边界）

- ✅ 只改: `board.py`（新增 render_project_lifecycle/render_project_lifecycle_html/list_projects）
  + `commands.py`（BoardCommand 加 project 子命令）+ `fastapi_adapter.py`（view=project）
  + 契约测试 + 版本同步
- ❌ 不做: 项目操作（启动/继续/审批/标记）、多项目并排看板、组织分组（公司/部门/行业）、
  Dashboard 实时聚合、SSE 推送
- ❌ 不影响: 主线面板（/board 默认行为逐字节不变）、graph/chain/timeline/report、T9 字段错位修复
- 统一修改: 实现 + 契约测试 + CHANGELOG + 版本断言 + FEATURES.md 同 Sprint

## 3. Codex Scope

1. `board.py`: `PROJECT_LIFECYCLE_STAGES` 常量 + `_project_stage_status(workspace, slug)` +
   `list_projects(workspace)` + `render_project_lifecycle(workspace, slug)` +
   `render_project_lifecycle_html(workspace, slug)` + Web 导航 tab 集成
2. `commands.py`: BoardCommand 加 `project` 子命令（无参=列表 / 有参=单项目视图; 空态提示）
3. `fastapi_adapter.py`: `/api/board` 支持 `view=project`（+ project 参数）
4. 契约测试: 生命周期映射 / select 列表 / 空态不猜项目 / 隔离只读 / 主线面板零变化 / 兼容

## 4. 验收标准（独立验证）

1. `/board project` 无参 → 项目列表（slug/名/状态/时间）, 20 项目全列出
2. `/board project P-e023a04c` → 11 段生命周期 + 文档产物 + 任务进度 + 更新时间
3. 阶段判定正确: 墨笺(P-e023a04c) → 发现✓确认✓PRD✓ 工程○开发○…（手算对照）
4. 无显式项目 → 空态提示（不猜项目/不扫描兜底）
5. 不存在的 slug → "项目不存在"提示
6. Web `/api/board?view=project&project=<slug>` HTML 可渲染
7. 主线面板 /board 默认行为零变化
8. 只读验证: 跑完视图后各项目文件 mtime 不变
9. 全量回归 0 新增失败 · 版本同步（pyproject/断言/CHANGELOG/FEATURES）

## 5. 边界与后续（backlog）

- 阶段 8-11（交付/部署/运维/更新）真实数据源: 待部署/运维功能落地后填充
- 项目操作（继续开发/审批）: 后续 Sprint
- 组织分组（行业/公司/部门 §8.3）: 多项目管理时再做
- Dashboard 实时聚合 / SSE 推送: 独立 Sprint
