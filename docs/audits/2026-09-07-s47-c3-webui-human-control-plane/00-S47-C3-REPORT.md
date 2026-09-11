# 00 — S47-C3 WebUI Human Control Plane END-TO-END AUDIT (2026-09-07, READ-ONLY)

> HEAD 8be75f88。零代码改动/零 commit/零 push。

## Verdict
WebUI 已具备 **Human Control Plane 主体** (Idea→…→Release 全程可控+可观察),
但 **Delivery 取物断点** (P1) 与若干可追溯/UX 缺口 (P2) 存在。无 P0。

## 5 问答
1. **WebUI 能否定义为 Human Control Plane?** → 大部分是: Project/Conversation
   创建管理真, chat 启动生产 (后端首消息 auto-start), Runtime LIVE (SSE),
   Run Detail (stage/repair/calls), Review (ACC approve/request-change/
   release/delivery 列表) — 真实闭环控制面, 非孤立诊断页 (项目 8 子页共享
   project 壳 + 状态真实联动)。缺口 = Delivery 取物 + Request Change 到新
   run 的编排提示。
2. **普通用户能否从 Idea 走到 Delivery?** → **能走到 RELEASE** (approve →
   release → RELEASED 可见于 review 页), **Delivery 卡在"看到"非"拿到"**:
   artifact ID 列表无下载/路径入口 (P1)。
3. **阻断点**: Delivery 下载/打开最终产物 (dist zip) 无 UI 入口 — 后端
   workflow_runs/{pid}/{R}/dist/app-*.zip 真实存在但无端点/无链接。
4. **后端已有但 UI 未暴露**: dist zip 下载/列表; run→canonical EXS/ver/EVD
   REST (证据链); workflow start 显式按钮 (现 chat auto); Request Change→
   自动 repair run 编排 (workflow start 已备); conversation 进度阶段意图
   映射 (UX 人话)。
5. **下一 Sprint 建议**: **A (Delivery 取物完成闭环)** 优先 —
   薄下载端点 + review delivery 真实 href; 其次 C (canonical 证据下钻)。

## 分类
P0: 无 (无第二 truth/mock 冒充/安全)
P1:
  - DELIVERY: 最终产品无下载/打开入口 (review 只列 artifact id; workspace
    产物面板空态提示) — 核心闭环终点缺失
P2 (backlog, 不执行):
  - TRACEABILITY: run/stage → canonical art/ver/EVD 独立下钻 (C3 backlog;
    release 可见 ID 但不可点)
  - CONTROL_PLANE: Request Change → 自动新 run 编排提示缺; 显式
    "开始生成"按钮 (现依赖 chat 首消息 auto-start, 可发现性弱)
  - OBSERVABILITY: run detail 未嵌 artifact/verification 关联; overview
    无 active-run 醒目卡 (runtime 页有)
  - FAILURE_RECOVERY: repair 轮在 run detail 人话显示 ✓; 失败 run 的
    errors 需进 overview 概要
P3: cosmetic (repair 徽章样式等)

## GAP 清单
CONTROL_PLANE_GAPS: delivery 取物 / request-change→repair 编排提示 /
显式 start 按钮 (P1+P2)
OBSERVABILITY_GAPS: overview active-run 卡; run detail 关联产物 (P2)
TRACEABILITY_GAPS: canonical art/ver/EVD 下钻 REST+UI (P2)
FAILURE_RECOVERY_GAPS: errors 概要进 overview (P2)
HUMAN_INTERVENTION_GAPS: ACC/gate/release 动作存在 (S47-B ✓); 运行上下文
  内干预提示 (P3)
MOCK_FALLBACK_RISKS: runtimeClient/workflow mock = 真 API 优先 + 诚实
  is_mock; 不遮蔽真失败 (通过 — 详见 02)
NAVIGATION_GAPS: 项目 8 子页 + workspace 作用域切换有 shell; delivery 从
  review 页无下一步指引 (P2)
MULTI_CLIENT_BOUNDARY_GAPS: 无 (Web 投影 / Desktop 走 factory-runtime /
  CLI 薄 — 单 backend, 详见 02)
