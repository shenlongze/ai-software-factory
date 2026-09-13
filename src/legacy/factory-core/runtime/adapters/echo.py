"""runtime/adapters/echo.py — EchoRuntimeAdapter: 测试用 mock Runtime (验证执行链路)。

设计依据:
- phase4b2-status.md: EchoRuntimeAdapter (测试用 mock, 验证执行链路) — 行为:
  execute(request) → 输入 echo 到 output, status SUCCESS; 按 input 特殊值返回 FAILED 供测试。
- 无真实 Hermes/LLM 调用 (phase4b2 禁止清单): 纯内存计算, 唯一内置 Runtime。
- 契约遵守 RuntimeAdapter 抽象接口: 仅依赖 runtime.models, 无 registry/store/事件引用
  (ADR-0006 解耦铁律); 返回结果 request_id 必须绑定请求 id (派发层校验)。

特殊分支 (phase4b2-status: "或按 input 特殊值返回 FAILED 供测试"):
- request.input 含真值键 "fail" (如 {"fail": "boom"}) → status=FAILED, error=str(input["fail"]),
  用于失败链路测试 (execution.failed + workflow.failed)。
- 其余输入一律 SUCCESS: output = {"echo": input, "execution_id": ..., "runtime_id": "echo"}。

注册为内置 runtime: id="echo", type="mock" — 实现在本模块 + runtime/adapters/__init__.py
的 BUILTIN_ADAPTERS 映射; 身份记录 (RuntimeInfo) 仍须经 RuntimeRegistry 显式注册
(registry 是注册身份的唯一事实源, 见 ADR-0007 决策 3)。
"""

from __future__ import annotations

from runtime.adapter import RuntimeAdapter
from runtime.models import ExecutionRequest, ExecutionResult, ExecutionStatus


class EchoRuntimeAdapter(RuntimeAdapter):
    """Echo mock Runtime: 输入原样回显到 output, 供派发/执行链路验证。

    - RUNTIME_ID = "echo" / TYPE = "mock": 内置 runtime 身份常量
      (RuntimeInfo 注册时建议使用, 与 BUILTIN_ADAPTERS 键一致)。
    - FAIL_KEY = "fail": input 真值触发 FAILED 分支 (测试失败链路)。
    """

    RUNTIME_ID = "echo"
    TYPE = "mock"
    FAIL_KEY = "fail"

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        """同步执行: 输入 echo 到 output (SUCCESS); input["fail"] 真值 → FAILED。"""
        if request.input.get(self.FAIL_KEY):
            return ExecutionResult(
                id=self._result_id(request.id),
                request_id=request.id,
                status=ExecutionStatus.FAILED,
                error=str(request.input[self.FAIL_KEY]),
            )
        return ExecutionResult(
            id=self._result_id(request.id),
            request_id=request.id,
            status=ExecutionStatus.SUCCESS,
            output={
                "echo": request.input,
                "execution_id": request.id,
                "runtime_id": self.RUNTIME_ID,
            },
        )

    @staticmethod
    def _result_id(execution_id: str) -> str:
        """结果 id 从执行 id 派生 (1:1 确定性, 便于测试断言与审计追踪)。"""
        return f"EXR-{execution_id}"
