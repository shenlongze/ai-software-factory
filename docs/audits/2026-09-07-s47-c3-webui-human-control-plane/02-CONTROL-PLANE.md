# 02 — CONTROL PLANE (READ-ONLY)

## 人类控制动作清单
| 动作 | UI | backend | 状态 | 证据 |
|---|---|---|---|---|
| 创建项目 | ✓ | POST /api/projects | REAL | S46/S47 |
| 启动生产 | chat 首消息 (隐式) | chat_route auto-start | REAL (可发现性 P2) | backend: "未启动 → idea 更新 + start"; client.startWorkflow 零调用 |
| 观察实时 | runtime LIVE | SSE events | REAL (C1) | 7928 events |
| Run 下钻 | AfRunDetail | run detail API | REAL (C2) | S46 progress |
| Approve | review | approve ACC | REAL (S47-B) | ACC-* |
| Request Change | review comment | request-change | REAL (S47-B) | CHANGE_REQUESTED |
| Release Gate | review | create release | REAL (S47-B) | GATED |
| Release | review | execute | REAL (S47-B) | RELEASED |
| Delivery 取物 | **✗ 无下载/打开** | 无端点 (dist zip 真实存在) | **GAP P1** | workflow_runs/.../dist/app-1.0.0.zip |
| 取消/Stop run | runtime-sessions cancel (session 域) | 有 | PARTIAL (workflow run cancel 无 UI) | P2 |

## Multi-client boundary (审计 8)
- Web: 全投影 (历轮实证, mock 诚实 is_mock)
- Desktop: src-tauri = Tauri host → factory-runtime CLI → 后端 (无 domain)
- CLI: bin/factory → cli_factory → console services (薄; 无第二 backend)
- Mobile: 不存在
- 无第二执行链 / 无第二真相: ✓ (P0-P2D/S44-S47 全部走 console domain)

## Mock/fallback 风险 (审计 6)
- runtimeClient.getWorkflow/getTimeline/listRuntimes: 真 API 优先; 失败 →
  mock (is_mock=true 诚实) — 但 AfRuntimePage/AfWorkflowPage 直接用
  api.* 真端点, 不走 fallback → 不遮蔽真失败
- backend projectWorkflow: 无运行数据 → mock (is_mock=true) — 空态兜底,
  不冒充
- projectRuns/run detail/ACC/release: 无 mock
- → MOCK_FALLBACK_RISK: 低 (诚实标注; 不遮蔽 backend failure)
