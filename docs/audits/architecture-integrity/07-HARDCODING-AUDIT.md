# 07 — Hardcoding Audit
- Tool schema+desc+handler 硬编码 agent_loop (35): P1 (偏离1)
- Tool description 含业务语义: "审批后/已消费/幂等/引导 plan_development": P1 (偏离3)
- 维度/策略 (govern prompt 13 relation、分析维度建议、guide 文案) 内联:
  部分 = LLM 引导合理; 部分 = 业务策略应代码化
- 状态表/转换: 各域 truth 模块内 (正常)
- slug 函数双口径 (service._confirm_slug vs org.space._slugify): P2
