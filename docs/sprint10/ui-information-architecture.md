# Sprint 10 — UI Information Architecture

> 日期: 2026-08-10 | 状态: 设计 (ONLY DESIGN)
> 目标: 产品工作台页面结构 (参考 AI Factory 自己产出的设计规范: /tmp/ai-factory-product-ui/uxui.json)

## 1. 全局布局 (AppShell)

```
┌────────┬──────────────────────────────────┐
│ 侧边栏  │  顶栏 (项目名/LLM 状态/主题)       │
│ 图标导航 ├──────────────────────────────────┤
│        │  内容区 (路由页面)                 │
│ 工作区  │                                  │
│ 设置    │                                  │
│        ├──────────────────────────────────┤
│        │  状态栏 (运行中任务/成本/事件)       │
└────────┴──────────────────────────────────┘
```

## 2. 页面结构

```
① Dashboard (工作区首页)
   我的项目 (卡片网格: 名称/状态/进度/最近活动)
   + 新建项目按钮
   + 等待审批卡片 (待审批门数)
   + 最近生成结果 (发布包)

② Create Project (新建对话框)
   一句话输入: "开发一个记账 App"
   项目类型: Web App / Mobile App / Desktop App (单选)
   技术偏好: AI 自动 / Flutter / React / Vue
   → 创建后跳转 Workspace

③ Project Workspace (核心页)
   顶部: 项目名 + 状态 + 成本/耗时统计
   中间: 8 阶段管道 (Idea→PRD→UX/UI→Arch→Dev→Test→Release)
         每阶段: Agent 图标 + 状态 (待办/运行/等待审批/完成/失败)
         + 产物链接 + 成本 + 耗时
   点击阶段: 展开详情 (artifact 内容/审批按钮/意见输入)

④ AI Design Review (重点页 — 阶段展开)
   PRD 审核: 市场分析/用户画像/功能列表/MVP 范围 逐节展示
   UI 审核: wireframe ASCII 预览 + 组件卡片
   操作: ✅ 批准 / ✏️ 修改意见 (意见 → gate comment → 下一轮 Agent)

⑤ Build Monitor (运行视图)
   Developer: 生成代码 (patch 摘要/文件清单)
   Tester: 测试运行 (passed/failed/耗时)
   Release: 版本打包 (zip/notes)
   实时: 轮询 2s 刷新 或 SSE 推送

⑥ Artifact Viewer
   6 类产物 (product/ux_ui/design/code/test/release)
   点击查看内容 (JSON/代码预览/zip 下载)

⑦ Settings (LLM 配置)
   Provider 选择 + API Key (密码框 + 加密提示) + 模型选择
   + 测试连接按钮 + 主题切换 (亮/暗)
```

## 3. 路由

```
/                    → Dashboard
/new                 → Create Project
/projects/:id        → Project Workspace
/projects/:id/review → AI Design Review (阶段展开)
/projects/:id/monitor→ Build Monitor
/projects/:id/artifacts → Artifact Viewer
/settings            → Settings
```

## 4. 设计语言（AI Factory 自产 token）

```
极简风 (参考 UX/UI Agent 输出):
  亮/暗双主题 | primary #007ACC | 语义色
  背景 #FFF/#1E1E1E | 间距/圆角统一 | 中文优先
```

## 5. 复用现状

```
现有 Console 页 (S9-002/003): Projects/Workflow/Artifacts/Approval/Review
  → 重构为上述产品布局 (保留数据逻辑, 重排 UI)
  → 新增: Create Project / Build Monitor / Settings / Downloads
```
