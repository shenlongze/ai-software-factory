# Sprint 10 — UI 信息架构: 三栏工作台

> 日期: 2026-08-10 | 状态: 设计 (ONLY DESIGN)
> 参考: Cursor/TRAE/Windsurf 布局 + Figma Review 交互 + DevTools

## 1. 页面路由

```
/                     → Workspace Home (Dashboard: 我的项目/新建/待审批/最近)
/projects/:id         → Project Workspace (三栏: Timeline 核心)
/projects/:id/review  → Review 页 (阶段审核)
/settings             → Settings (LLM 配置/主题)
/projects             → Projects 列表 (Explorer 主导航)
```

## 2. Factory Explorer (左侧)

```
主导航 (图标+文字):
  Home / Projects / Tasks / Agents / Skills / Templates / Artifacts / Settings

Project Tree (选中项目后展开):
  Ledger App
  ├─ Product        (PRD artifact)
  ├─ UX/UI          (设计 + 预览)
  ├─ Architecture   (设计文档)
  ├─ Code           (文件树 + diff)
  ├─ Test           (测试报告)
  └─ Release        (版本包)
  每节点: 状态色点 (待办/运行/待审/完成/失败) + 点击跳对应产物
```

## 3. AI Workspace (中间 — Agent Timeline)

```
顶部: 项目名 + 阶段进度条 + 成本/耗时
主体: 时间线事件流 (从上到下, 新事件追加, SSE 实时)
  每节点渲染 (按事件类型):
  ┌─ user:     用户输入 (聊天气泡风格, 但只读记录)
  ├─ stage:    "PM Agent 正在分析需求" [Running spinner]
  ├─ artifact: "生成 Product Artifact" [查看] [打开设计] 按钮
  ├─ review:   "等待你审核: PRD" [去审核] 按钮 (高亮)
  ├─ diff:     Developer 修改: 文件清单 + 展开 diff
  └─ error:    失败 + 原因 (红色)
底部: 输入框 (继续任务/新需求) — 可选 (一期只读时间线 + 按钮)
```

## 4. Factory Panel (右侧 4 Tabs)

```
① Browser Tab (默认)
   iframe: 沙箱运行 URL (AI 生成软件真实页面)
   工具栏: 刷新 / 截图 / 新窗口打开
   空态: "选择已生成代码的项目 → 预览运行" 

② Task Tab
   Workflow 8 阶段表:
   PM ✅ / UX/UI ✅ / Architecture 🟡 / Developer ⭕ / Tester ⭕ / Release ⭕
   每阶段: 状态 + 耗时 + 成本 + 产物链接
   底部: 总进度 / 总成本 / 总耗时

③ Artifact Tab
   6 类产物列表 (product/ux_ui/design/code/test/release)
   点击: 内容预览 (JSON 格式化 / 代码高亮 / zip 下载)
   分类筛选 + 搜索

④ Review Tab
   待审清单 (审批门):
   [PRD 需求审核] [UX/UI 设计审核] [架构审核] [发布审核]
   点击进入 Review 页:
   - 内容展示 (PRD 节 / wireframe 预览 / 浏览器预览)
   - 意见输入框
   - 按钮: [重新设计] [批准继续]
```

## 5. Review 页 (审核闭环)

```
布局 (左内容右操作):
  左: 审核对象
    PRD: 市场/画像/功能/MVP 逐节
    UX/UI: Wireframe 预览 (L1) + Token 主题 (L2) + 真实浏览器 (L3)
    代码: diff + 文件树
  右: 审核操作
    意见 textarea (可选)
    [重新设计] → reject + comment → Agent 重做
    [批准继续] → approve → 下一阶段
历史: 该阶段历史审批记录 (谁/何时/意见)
```

## 6. Settings

```
LLM: Provider/模型/API Key (密码框 + 加密说明 + 测试连接)
主题: 亮/暗 (design_tokens 应用)
偏好: 语言 (中文默认) / 通知
```

## 7. 设计语言

```
极简风 (UX/UI Agent 自产 token):
  三栏布局 (Explorer 220px / Workspace flex / Panel 360px, 可折叠)
  亮/暗双主题 | primary #007ACC | 状态色 (运行蓝/完成绿/失败红/待审橙)
  中文优先 | 间距/圆角统一 | 等宽字体 (代码/diff)
```

## 8. 状态机 (每阶段)

```
pending → running → waiting_review → (approved → completed | rejected → rework)
失败: failed + reason → [重试] [改意见]
```
