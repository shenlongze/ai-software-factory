# Sprint 10 — User Flow: 普通用户完整使用流程

> 日期: 2026-08-10 | 状态: 设计 (ONLY DESIGN)

## 1. 主流程（30 分钟出一个 App 的第一版）

```
用户: 打开 AI Factory (CLI: factory start → 浏览器打开, 或直接 Web 访问)
  ↓
① 输入: "开发一个记账 App" (一句话)
  ↓
② AI Factory: PM Agent 工作 (市场/画像/功能/MVP) → PRD Review
  ↓
③ 用户: 审核 PRD (看市场分析/功能列表/MVP 范围) → ✅ 批准 / ✏️ 修改意见
  ↓
④ AI Factory: UX/UI Agent 设计 (页面/wireframe/风格) → 设计 Review
  ↓
⑤ 用户: 看 UI 原型 (wireframe 可视化) → ✅ 批准 / ✏️ 意见
  ↓
⑥ AI Factory: Architect → Developer (写代码) → Tester (测试) → Release (打包)
    (Build Monitor: 每阶段状态/成本/耗时实时看)
  ↓
⑦ 用户: 收到发布产物 → 下载 (zip/安装包) → ✅ 完成
```

## 2. 审批点（用户只做决定）

```
审批门 1 (PRD): 功能范围对吗? MVP 边界对吗?
审批门 2 (设计): 界面风格对吗? 页面结构对吗?
审批门 3 (发布): 测试通过了, 可以打包交付吗?

每个门: 批准 / 拒绝+意见 (意见自动进下一轮 Agent 输入)
```

## 3. 修改反馈循环

```
用户审 PRD 说 "加个预算功能" 
  → 意见进 gate comment → PM Agent 重做 PRD (带意见)
  → 用户再审 → 批准 → 继续
```

## 4. 用户场景矩阵

```
场景 A (普通用户): 一句话 → 全链自动 → 下载 (审批门把关)
场景 B (开发者): CLI: factory task create → 精确控制
场景 C (维护者): 已有项目 (DevToolBox/MarkPad) → 注册 → 修 bug → 发布
```

## 5. 失败路径

```
Agent 卡住/产出不合格 → 阶段 FAILED → 用户看到原因 + 重试/改意见
LLM 不可用 → 明确提示配置 LLM (设置页)
无网络/断点 → 本地沙箱+事件日志, 恢复后续跑
```
