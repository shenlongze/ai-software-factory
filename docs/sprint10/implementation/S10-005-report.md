# S10-005 — Artifact Center（Completion Report）

> 日期: 2026-08-10 | 状态: 完成 (待人工审核) | vitest 257 + tsc 零错 + pytest 6531

## 交付内容

```
1. Artifact Center 视图 (FactoryPanel Artifact Tab + hash 直链 #/workspace?panel=artifact):
   - Artifact List: ref/id/类型标签/状态徽章/阶段/版本/时间
   - 类型过滤 (product/ux_ui/design/code/test/release + 全部)
   - 状态徽章 (validated 已验证/pending 待验证/failed 失败 — artifactStatusLabel)
   - 空态 "暂无产物 — 等待 AI 生成" + mock fallback "演示数据" 诚实标注

2. Detail Viewer 类型化渲染 (复用 S9-003 ReviewSections):
   - product: market_analysis/user_persona/user_journey/feature_list/mvp_scope/user_stories
   - ux_ui: wireframe ASCII → Screen Card (parseWireframeScreens: 屏幕名/ASCII 预览/组件/交互动作)
   - design: system_architecture/technical_stack/api_design/task_breakdown
   - code: 文件列表 + diff 预览 (metadata.changes; 缺失 → GET /content 兜底)
   - test: passed/failed 统计徽章 + bugs 列表
   - release: 版本/构建/包文件/下载 (content 端点)/部署信息
   - 未知类型: GenericReview JSON 兜底

3. Timeline 联动: artifact 节点 "查看" → Artifact Tab 激活 + 打开产物详情 (focus 优先)

4. API 复用: GET /api/artifacts (列表, S9) + GET /api/artifacts/{id} (详情, S9-003)
   + GET /api/artifacts/{id}/content (新增: 路径穿越防护 + 404 语义 + 失败安全)
```

## 测试

```
后端 +10 (content 端点: 读取/404/越界拒绝/审计 — tests/console 306 全绿)
前端 +12 (artifact-center.test.tsx: List/过滤/状态/6 类详情渲染/未知兜底/mock/空态)
共 vitest 257 (245+12) + pytest 6531 (6521+10)
修复: api 导出断言 +2, EventStore API 断言, stub 顺序, 渲染格式对齐
```

## 修复的真实问题

```
1. api/__init__ 未导出 get_artifact_content (4 HTTP 测试挂) → 补导出
2. 测试用不存在的 EventStore.iter_all → query_events (真实 API)
3. S10-004 联动测试 → S10-005 新行为 (artifact → Artifact Center)
```

## 截图

```
/tmp/s10-005-shots/artifact-center.png (1600×950, Artifact Tab 渲染)
```

## 下一步 S10-006

```
Review Workflow: Review Tab 待审清单 + Review 页 (需求/UI/架构/发布 4 审核闭环)
```

## 限制（诚实）

```
1. wireframe 预览: 组件需字符串数组 (UX/UI Agent 输出 {tag} 对象需规范化 — 记录)
2. Code diff: metadata.changes 文本展示 (完整 diff viewer 后续)
3. Release 下载: content 端点指向 (真实 zip 下载端点后续)
```
