"""runtime/adapter.py — RuntimeAdapter 抽象接口 (执行出口协议, 无具体实现)。

设计依据:
- architecture.md §7.1: Runtime Adapter 为唯一执行出口 — core 不直接调用任何
  LLM/Agent 框架; 换 Runtime = 换 Adapter, core 零改动。
- phase4b1-status.md: 本阶段只定义抽象接口 (execute), 不实现任何具体 Runtime
  (hermes/claude_code/mock 等均在后续 Phase)。
- resolve_runtime_id 等派发辅助放在 RuntimeRegistry (需访问注册状态), 见 ADR-0006 决策 6。
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from .models import ExecutionRequest, ExecutionResult


class RuntimeAdapter(ABC):
    """Runtime 适配器抽象接口 — 具体 Runtime (hermes/mock 等) 在 Phase 4B-2+ 实现。

    契约:
    - execute(request) -> ExecutionResult: 同步执行一次请求; 实现方自行处理
      启动外部进程/调用 LLM 等细节, 返回结构化结果 (SUCCESS 带 output /
      FAILED 带 error)。
    - 注册信息 (id/name/type/status) 由 RuntimeRegistry 的 RuntimeInfo 记录,
      本接口不强制暴露 — 注册表与实现解耦。
    """

    @abstractmethod
    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        """执行一次 ExecutionRequest 并返回 ExecutionResult。

        Args:
            request: 执行请求 (含任务/工作流/步骤绑定、目标 agent 与输入载荷)。

        Returns:
            ExecutionResult: status=SUCCESS 且 output 为结构化结果;
            或 status=FAILED 且 error 描述失败原因 (终态校验见模型)。

        Raises:
            实现方自定义异常: 执行器内部错误 (本接口不规定)。
        """
        raise NotImplementedError
