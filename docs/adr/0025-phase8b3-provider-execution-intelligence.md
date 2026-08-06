# ADR-0025 — Phase 8B-3: Provider Execution Intelligence

> 日期: 2026-08-06 | 状态: Accepted

## 背景

Provider 从声明能力扩展为经验积累: Capability + Cost + Performance + Experience。

## 决策

### 1. Usage 自动接入 Execution 生命周期
ProviderCarrierAdapter (集成层) 执行后自动记录 ProviderUsage (execution_id/task_id/provider_id/model_id/estimated_cost/duration/success); opt-in (usage_store=None → 零落库零事件, 8B-1 单元语义恢复); 事件序: selected → started → completed|failed → usage.recorded (终态后追加)。

### 2. Declared vs Actual 区分
CapabilityProfile = 静态声明 (不覆盖); PerformanceStats = 从 usage 聚合 (success_rate/failure_rate/avg_duration/total_cost/execution_count + provider/model/version/period 维度); declared_vs_actual() 计算 gap。

### 3. 三分数推荐
RecommendationScore = 0.4·capability + 0.3·cost + 0.3·performance; 无 usage → performance 中性 0.5 (8B-2 兼容); 只推荐不自动切换。

### 4. Human Feedback 接口预留
ProviderFeedback (rating 1-5/approved/comment) + FeedbackStore + provider.feedback.created; 暂不实现 UI。

### 5. 收尾裁定
7 失败修复: 2 实现 bug (PerformanceStats 别名同步 model_validator; feedback bool 拒绝 mode="before") + 5 测试 bug。事件链断言最小化更新 (usage.recorded 终态后)。

## 验证

- pytest 2883 全绿 (2744 + 139)
- 冒烟: execution run --provider → usage.recorded → usage count=1 → stats 聚合正确
- Core 零修改
