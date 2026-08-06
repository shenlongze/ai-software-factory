# ADR-0021 — Phase 7: Project Understanding Layer

> 日期: 2026-08-06 | 状态: Accepted

## 背景

让 Factory 理解任何项目当前状态 (任意阶段接入的第一步)。Extension 模块, Core 零修改。

## 决策

### 1. understanding 为独立 Extension
factory-core/understanding/ 独立目录 (models/analyzers/service/events), 独立数据空间, 独立测试 (151 tests), 删除不影响 Core (Composable Capability Architecture 约束)。

### 2. 10 阶段注册表 + 7 Artifact 注册化
STAGES = IDEA/RESEARCH/PRD/UI_DESIGN/ARCHITECTURE/DEVELOPMENT/TESTING/RELEASE/PRODUCTION/OPERATION (可扩展); ARTIFACT_DETECTORS = PRD/UI_DESIGN/ARCHITECTURE/SOURCE_CODE/TEST/DEPLOYMENT/OPERATION (注册化检测器, doc_patterns + code_patterns 三态匹配)。

### 3. 规则分析, 禁 LLM 写死
阶段识别按 artifact 组合链推断 (无产物→IDEA; +源码→DEVELOPMENT; +tests→TESTING; +部署→PRODUCTION; +运维→OPERATION); confidence = min(0.95, 0.5 + 0.1×支持证据数); evidence 列出依据。未来 LLM 经 Provider 抽象 (Phase 8)。

### 4. 结构化建议
NextAction = {action, reason, risk, approval_required}; PRD/UI/部署缺失 → approval_required=true (Approval Gate 接口预留)。

### 5. Event
understanding.started/completed/failed/viewed (经 EventLogger, 枚举扩展)。

### 6. CLI + Dashboard
factory understand <path> [--json|--stage]; Dashboard Understanding View (17 视图, include_understanding 默认关零回归)。

### 7. 收尾裁定
12 处测试期望修正 (confidence 公式/非 7 产物/--json 键位/部署文档识别) — understanding 实现零 bug。

## 验证

- pytest 2310 全绿 (2159 + 151)
- markpad 冒烟: PRODUCTION (0.95), 证据完整 (PRD/UI/ARCH/SOURCE/TEST)
- 零 Core 修改
