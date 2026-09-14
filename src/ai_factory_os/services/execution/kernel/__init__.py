"""factory-exec — AI Software Factory 执行扩展 (Phase A, 真实 LLM Developer Agent 最小闭环)。

独立 Extension 包 (factory-exec/exec/ — 测试/CLI 把 factory-exec/ 目录挂到
sys.path 后以 `exec` 导入; 目录名含连字符, 包名 `exec` 合法, 非 Python 关键字
模块冲突 — 无 stdlib/第三方顶层模块名为 exec)。

范围 (docs/architecture/phase-a-execution-mvp-design.md 冻结边界):
- ExecutionRequest / AgentRuntime / ProviderInterface + 1 真实 Adapter
  (Anthropic, httpx, 无 key 清晰 ProviderError)
- Developer Agent MVP (prompt 组装 → Provider → patch 解析 → 报告)
- Sandbox MVP (临时目录项目副本 + git 追踪 + patch 导出; 沙箱铁律:
  Agent 不直接改用户环境, 副本 + patch)
- Validation 最小 (语法检查/简单测试命令) + ApprovalGate (应用 patch 前必批)
- Experience 记录 (复用 10A-4 ExperienceStore, 零新模型)
- org.execution.* 事件链 (requested/started/completed/failed/approved/applied)

禁止 (设计 §1): 企业治理完整 / 多 Agent 协作 / Communication 完整 /
自动 Planning / ERP — 本包只做单 Developer Agent 最小执行闭环。

Removal Isolation: factory-core 零顶层 imports 本包 (CLI 延迟导入, 缺包 →
rc 7 响亮配置缺口); 本包依赖 factory-core events/intelligence 层
(Extension 依赖 Core, 反向不成立)。

顶层 __init__ 故意不 import 子模块 (延迟加载): `import exec` 零副作用。
"""

__version__ = "0.1.0"
