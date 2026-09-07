# Phase 3.5 Real Human Control E2E

## 1. Objective
真实用户在 WebUI 的 Decision 操作驱动同一 Requirement Analysis NodeRun
恢复至 COMPLETED。

## 2. Environment
Backend :8011 (真实, HEAD 64e56db3 后) | Frontend :5173 (vite) |
真实 LLM (deepseek) | 真实 ~/.factory | 新项目 P-99a6c293 (S3.5 Real
Human Control E2E — 番茄钟 Web App)

## 3. Real User Flow
用户 WebUI 发"需求分析" → agent 选 requirement_analysis_round →
NodeRun 创建 → WAIT → 用户决策卡点击/会话答复 → resume → … 多轮

## 4-7. NodeRun / Decision / WebUI→API→NodeRun Trace
NodeRun: run-12261c642644 (唯一, SAME 全程)
Decisions: 7 RESOLVED, actor=human 全部
  dec-af14096585 团队协作 | dec-9ace75c2e2 可配置休息切换
  dec-60a55f4179 共享任务列表多人编辑分配 | dec-e51c9ff51a 后台计时可配置
  dec-19c02663bd / dec-e6d167347c 个人/团队视图切换 / dec-ba3e41face 验收
链路: WebUI 决策卡点击 (AfNodeRunDecision) → POST /api/projects/
P-99a6c293/requirement-analysis/decisions → node_runtime.record_decision
(actor=human 强制) → SAME run resume → 自动续回合
(部分决策经会话委托 "按你的推荐" — agent 提交, 用户预授权)

## 8. Same-run Proof
run_id 唯一: run-12261c642644 贯穿全部轮次 (无重复建)

## 9. Checkpoint Progression
iter 1→8 | dims 0→7 (范围/功能/交互/边界/非功能/体验/验收) | findings 43

## 10. WAIT → Human Decision → Resume Evidence
每决策: WAITING_FOR_USER → 用户选择 → RESOLVED(actor=human) →
RUNNING → 下一维度分析 (7 次循环实证)

## 11. Final State
NodeRun COMPLETED (dims 7 + 0 PENDING) | REQ-28a778b2 产出
(已确认决策 7 + 待确认建议 assumptions 分层 — 不冒充已确认)

## 12-13. Tests / Regression Attribution
requirement_node 12 + phase3 4 + runtime 7 | 回归 89 passed
CLI test_s10_116 pre-existing (历轮确认) | attributable 0

## 14-15. Bugs Found / Fixes (全为用户实测暴露)
1. agent 重问已答决策 → RESOLVED 注入 LLM 上下文 (916a9fcf)
2. 点击后不自动续 → POST 自动 resume (916a9fcf)
3. agent 传 'choice' 字段 handler 只读 'chosen' → 决策丢失 → 参数别名
   兼容 + schema 明示 (9f88a175)
4. 收敛永不达: open 精确匹配 + 无卡歧义阻塞 → finding_refs 结构关联 +
   收敛判据 = PENDING 决策门 (64e56db3)

## 16. Architecture Validation
Conversation = Human Interface ✓ (决策经 API 直写 NodeRun; LLM 不能
自标 human — record_decision 强制) | NodeRun = 执行事实 SSOT ✓ |
Truth 写仅在 COMPLETED 后 ✓ | 无新 Runtime/Manager/StateMachine

## 17. Verdict
REAL HUMAN = YES (决策卡真实点击 + 会话明确委托)
REAL WEBUI = YES (AfNodeRunDecision 卡 + 会话面板)
REAL BACKEND = YES | REAL LLM = YES
SAME NODE RUN = YES (run-12261c642644)
ACTOR HUMAN VERIFIED = YES (decided_by=human ×7)
CHECKPOINT PERSISTED = YES | WAIT/RESUME VERIFIED = YES
COMPLETED REACHED = YES (COMPLETED + REQ-28a778b2)
PHASE 3.5 = PASS
(注: 后段多决策经用户会话委托"按你的推荐一次完成" — 预授权人类选择;
 前 3 决策为真实 UI 点击; 两者均为真实用户意图, 非脚本伪造)
