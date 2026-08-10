# S10-004 — Runtime Workspace（Completion Report）

> 日期: 2026-08-10 | 状态: 完成 (待人工审核) | pytest 6521 + vitest 245 + tsc 零错
> 模式: Runtime Instance (S10-004 调整版 — 非固定 Browser Tab)

## 交付内容

```
1. Runtime Instance 模式 (复用 S10-002 RuntimeInstance, 零重设计):
   id/type(browser|terminal)/project_id/artifact_id/status
   (starting|running|stopped|error)/url|session/created_at

2. 后端 runtimes API (6 端点 + Store 持久化):
   POST/GET /api/projects/{id}/runtimes + GET /api/runtimes/{id}
   + POST /api/runtimes/{id}/start|stop|screenshot
   (404/409/400 语义; RuntimeStateError→409; 原子写 JSON)

3. 前端 Runtime Panel (右侧):
   - Instances 列表 (类型图标/状态徽章/绑定 Artifact/创建时间)
   - [+] → Create Runtime Modal (Browser Runtime / Terminal Runtime)
   - Browser: iframe 沙箱预览 + 工具栏 (刷新/截图/打开新窗口) + 绑定 Artifact
   - Terminal: 终端样式 + mock stream (npm test/build, "演示数据" 标注)
   - 空态 "还没有 Runtime — 点击 + 创建" | REST 轮询 2s

4. Timeline 联动: artifact "查看" → 定位对应 Runtime (高亮) 或提示创建
5. Screenshot 预留: POST screenshot → "已保存截图 artifact" (Loop 后续)
```

## 测试

```
后端 +24 (CRUD/状态机/截图门禁 409/持久化/损坏安全/失败安全)
前端 +32 (List/Create Modal/Browser/Terminal/状态徽章/空态/联动/Screenshot/mock 流/轮询)
共 pytest 6521 (6496+25) + vitest 245 (213+32)
```

## 修复的真实 bug

```
1. service.py 属性遮蔽方法 (_runtime_store 属性 vs 方法同名 → TypeError)
2. events.py: Core 冻结无 org.runtime.* EventType 成员 → record 崩溃
   → 改失败安全跳过 (REST 轮询替代 SSE runtime.*, 诚实标注)
```

## 限制（诚实）

```
1. Core EventType 冻结: org.runtime.* 事件暂不能落库 → Runtime Panel 走 REST 轮询 2s
   (S10-005+ 扩展枚举后自动恢复 SSE 推送 — 事件函数已就绪零改动)
2. Terminal stream 为 mock 演示 (真实 Agent 命令输出 → 后续接入)
3. Screenshot Feedback Loop 未实现 (只预留 screenshot artifact)
4. Browser url 为模板占位 (沙箱静态服务器 → 后续接)
```

## 截图

```
/tmp/s10-004-shots/runtime-workspace.png (1600×950, 三栏 + Runtime Panel)
```

## 下一步 S10-005

```
Artifact Center: 资产库式 6 类产物查看 + Artifact Renderer (wireframe 预览/代码高亮/diff)
```
