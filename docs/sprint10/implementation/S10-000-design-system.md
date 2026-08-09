# S10-000 — Design System 实现报告

> 任务: S10-000 Design System (先行) | 日期: 2026-08-10 | 状态: 已提交, 等人工审核
> 依据: sprint10-backlog.md S10-000 + ui-information-architecture.md (设计语言) + workspace-architecture.md (组件架构)
> Token 同源: AI 自产 `/tmp/ai-factory-product-ui/uxui.json` design_tokens
> 约束: 只做 Design System, 不实现业务页面; 不破坏 S9 Console; Core/Runtime/Desktop 冻结

## 1. 交付摘要

| 项 | 结果 |
|---|---|
| 设计令牌 | `src/design/tokens.ts` (TS) + `src/design/design.css` (CSS 变量, 同值) |
| 主题切换 | `src/design/theme.tsx` — ThemeProvider/useTheme/ThemeToggle, 默认 light, `<html data-theme>` + localStorage |
| 组件库 | `src/components/ds/` 13 个组件 + 桶导出 index.ts |
| 测试 | `src/test/design-system.test.tsx` — 30 用例 (≥15 达标) |
| vitest | 151 全绿 (S9 121 + 新增 30) |
| tsc | `npx tsc --noEmit` 零错 |
| pytest | 6456 全绿零回归 (本任务不改后端) |
| 集成 | `main.tsx` 挂载 ThemeProvider + design.css (S9 页面零改动) |

## 2. 设计令牌 (Token)

### 2.1 颜色 — 亮/暗双主题

| Token | Light | Dark | 用途 |
|---|---|---|---|
| bg | `#FFFFFF` | `#1E1E1E` | 页面背景 / Modal 底色 |
| surface | `#F5F5F5` | `#252526` | 卡片/侧栏 |
| surface2 | `#EBEBEB` | `#2D2D30` | 悬浮/次级面板 |
| border | `#E0E0E0` | `#3E3E3E` | 边框 |
| text | `#1E1E1E` | `#D4D4D4` | 主文本 |
| textSecondary | `#757575` | `#999999` | 次要文本 |
| primary | `#007ACC` | `#007ACC` | 主色 (两主题一致) |
| primaryHover | `#0062A3` | `#1A8AD4` | 主色悬浮 |
| success | `#4CAF50` | 同 | 成功 |
| error | `#F44336` | 同 | 失败/危险 |
| warning | `#FF9800` | 同 | 警告/待审 |
| info | `#007ACC` | 同 | 运行中 |
| overlay | rgba(0,0,0,.5) | rgba(0,0,0,.55) | Modal 遮罩 |

### 2.2 状态色 — 8 阶段状态 (StatusBadge / Timeline 圆点)

| 状态 | 语义 | 色调 | 色值 | 中文标签 |
|---|---|---|---|---|
| pending | 待执行 | neutral | `#9E9E9E` | 待执行 |
| running | 运行中 | running | `#007ACC` (脉冲动画) | 运行中 |
| waiting_review | 待审核 | warning | `#FF9800` | 待审核 |
| approved | 已批准 | success | `#4CAF50` | 已批准 |
| completed | 已完成 | success | `#4CAF50` | 已完成 |
| failed | 失败 | failed | `#F44336` | 失败 |
| rejected | 已驳回 | failed | `#F44336` | 已驳回 |
| rework | 返工中 | warning | `#FF9800` | 返工中 |

对外字符串兼容: `approval_required`/`awaiting_approval` → warning; `in_progress`/`active` → running; `success`/`done`/`passed` → success; 未知 → neutral。

### 2.3 间距 / 圆角 / 字体 / 阴影

- 间距 (4px 单位): xs 4 / sm 8 / md 16 / lg 24 / xl 32 / xxl 48
- 圆角: sm 4 / md 8 / lg 12 / full 999
- 字号: xs 11 / sm 12 / body 14 / md 16 / lg 18 / title 24
- 字重: regular 400 / medium 500 / bold 700
- 字体: `system-ui, -apple-system, 'Segoe UI', 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif` (中文优先); 等宽 `ui-monospace, SFMono-Regular, Menlo, Consolas, monospace` (代码/diff)
- 阴影: light `0 1px 3px rgba(0,0,0,.12)...` / dark `0 2px 8px rgba(0,0,0,.45)`

### 2.4 Agent 元信息 (AgentAvatar)

| Role | 中文名 | 色 | 图标 |
|---|---|---|---|
| pm | 产品经理 | `#007ACC` | 📋 |
| ux_ui | UX/UI 设计师 | `#9C27B0` | 🎨 |
| architecture | 架构师 | `#FF9800` | 🏗️ |
| developer | 开发工程师 | `#4CAF50` | 💻 |
| tester | 测试工程师 | `#E91E63` | 🧪 |
| release | 发布工程师 | `#607D8B` | 🚀 |

未知角色回退: `#9E9E9E` + 🤖。

### 2.5 工具函数

- `statusTone(status)` / `statusLabel(status)` — 状态 → 色调 / 中文标签
- `agentMeta(role)` — 角色 → {label, color, icon}
- `formatDuration(seconds)` — 42s / 1m 20s / 1h 5m / —
- `formatCost(cost)` — $0.0038 / $12 / —

## 3. 组件清单 (`src/components/ds/`)

| 组件 | 文件 | 说明 |
|---|---|---|
| Button | Button.tsx | primary/secondary/danger/ghost × sm/md + loading (spinner + disabled + aria-busy) |
| Card | Card.tsx | surface/边框/圆角 + 可选 标题/副标题/操作区 |
| Timeline | Timeline.tsx | 垂直时间线容器 + TimelineNode (状态色圆点/标题/时间/内容) |
| StageCard | StageCard.tsx | Agent 头像 + 状态徽章 + 输入/输出/耗时/成本 + 查看详情; `inTimeline` 包 TimelineNode |
| StatusBadge | StatusBadge.tsx | 8 状态 → 语义色 + 中文标签 |
| ArtifactCard | ArtifactCard.tsx | 图标/类型中文/名称/创建者/输入/输出/状态 (6 类产物链) |
| AgentAvatar | AgentAvatar.tsx | 6 Agent 图标色, sm/md/lg |
| Modal | Modal.tsx | 遮罩点击 + Escape 关闭 + footer |
| Input | Input.tsx | label + hint |
| Textarea | Textarea.tsx | label + hint |
| Select | Select.tsx | options + placeholder + onChange(value) |
| Layout | Layout.tsx | 三栏: Explorer 220px / Workspace flex / Panel 360px, 两侧可折叠 |
| — | index.ts | 桶导出 (`import { Button, Layout } from '../components/ds'`) |

### 与 S9 隔离设计 (不破坏现有 Console)

- 全部类名 `ds-*` 前缀 (S9: `.card/.badge/.modal/.btn-*` 等不受影响)
- 全部 CSS 变量 `--ds-*` 命名空间 (S9: `--bg/--panel/--accent` 等不受影响)
- 新组件放 `src/components/ds/` 子目录, 与 S9 `src/components/` 同 basename 组件 (Card) 并存互不引用
- `main.tsx` 仅追加 ThemeProvider 包裹 + design.css import; S9 页面/测试零改动 (App.tsx 未动)
- 默认 light: `:root` 即亮色; S9 自身 `:root` 变量 (暗色) 依然生效, 页面外观不变

## 4. 主题切换

```tsx
// 入口 (main.tsx 已挂载)
import { ThemeProvider } from './design/theme';
<ThemeProvider><App /></ThemeProvider>

// 消费
const { theme, setTheme, toggleTheme } = useTheme();

// 切换按钮
<ThemeToggle />
```

- 默认 light; 持久化 localStorage `factory-theme` (不可用时静默降级, 内存生效)
- 生效方式: `<html data-theme="light|dark">` → design.css `[data-theme='dark']` 覆盖层

## 5. 用法示例

```tsx
import { Button, Card, Layout, Modal, StatusBadge, StageCard, Timeline, ArtifactCard, AgentAvatar, Input, Select } from '../components/ds';

<Layout
  explorer={<ProjectTree />}
  workspace={
    <Timeline>
      <StageCard name="需求分析" agent="pm" status="completed"
        input={['用户需求']} output={['PRD 文档']} durationSec={80} cost={0.0038}
        onViewDetails={() => navigateReview()} inTimeline />
    </Timeline>
  }
  panel={<ArtifactCard type="prd" name="记账 App PRD" createdBy="pm" status="completed" />}
/>
```

## 6. 测试 (30 用例)

| 分组 | 用例数 | 覆盖 |
|---|---|---|
| 设计令牌 | 5 | 双主题色值/状态映射/中文标签/Agent 元信息/scale/格式化 |
| 主题切换 | 3 | 默认 light + data-theme / toggle 切换 / setTheme |
| Button | 4 | variant/loading 禁用/onClick |
| Card | 2 | 标题区/纯内容 |
| StatusBadge | 2 | 色调映射/未知回退 |
| AgentAvatar | 2 | data-role/aria-label/6 角色 |
| Timeline+StageCard | 3 | 节点圆点时间/详情点击/inTimeline 包裹 |
| ArtifactCard | 1 | 中文标签/创建者/输入输出/状态 |
| Modal | 2 | open 控制/遮罩+Escape 关闭 |
| 表单 | 3 | Input/Textarea/Select |
| Layout | 2 | 三栏尺寸/折叠 |

## 7. 验证

```
vitest run       → 151 passed (17 files), 0 failed
npx tsc --noEmit → 0 errors
.venv/bin/pytest -q → 6456 passed, 0 regression (本任务未改后端)
```

## 8. 文件清单

新增:
- `frontend/src/design/tokens.ts`
- `frontend/src/design/theme.tsx`
- `frontend/src/design/design.css`
- `frontend/src/components/ds/` (13 文件: Button/Card/Timeline/StageCard/StatusBadge/ArtifactCard/AgentAvatar/Modal/Input/Textarea/Select/Layout/index)
- `frontend/src/test/design-system.test.tsx`
- `docs/sprint10/implementation/S10-000-design-system.md` (本文件)

修改:
- `frontend/src/main.tsx` (挂载 ThemeProvider + import design.css)

## 9. 后续消费指引 (S10-001+)

- S10-001 Shell: `Layout` (Explorer/Workspace/Panel) + `ThemeToggle` 入 Header
- S10-003 Timeline: `Timeline` + `StageCard inTimeline` + `StatusBadge`
- S10-005 Artifact: `ArtifactCard` + `Card`
- S10-006 Review: `Modal` + `Button` + `Textarea` (意见输入)
- 新页面统一消费 `--ds-*` 变量; 需要新 token 时先在 tokens.ts + design.css 双写
