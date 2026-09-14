"""providers/provider.py — ProviderAdapter 抽象接口 (统一智能出口协议, 无具体实现)。

设计依据:
- phase8-plan.md §Q3: 统一智能接口 — 不绑定具体 API (OpenAI/Claude/Gemini 差异
  由各 Adapter 自行映射); Runtime 经 ProviderRegistry 解析 Provider → 调统一接口,
  不直接接触 API 差异。
- 与 runtime/adapter.py (RuntimeAdapter 执行出口) 对称: Runtime = 执行机制;
  Provider = 智能来源 (phase8-plan §Q1)。Hermes 双角色并存 (phase8-plan §Q4):
  HermesRuntimeAdapter (执行) 零改动, HermesProviderAdapter (智能) 纯新增。

契约:
- generate(request) -> ProviderResponse: 单轮生成 (一次 prompt → 完整文本)。
- chat(request) -> ProviderResponse: 多轮对话 (messages + system → 完整文本)。
- stream(request) -> Iterator[ProviderResponse]: 流式生成 — 逐块产出
  (每块 content 为增量片段, 消费方拼接); 失败时产出含 error 的单块 (稳定响应,
  不抛异常, 同 HermesRuntimeAdapter 失败处理哲学)。
- 注册信息 (id/type/能力声明) 由 ProviderRegistry 的 ProviderDefinition 记录,
  本接口只要求 PROVIDER_ID/PROVIDER_TYPE 类常量 (与 BUILTIN_PROVIDER_ADAPTERS 键一致)。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterator

from .models import ProviderRequest, ProviderResponse


class ProviderAdapter(ABC):
    """Provider 适配器抽象接口 — 具体 Provider (hermes/openai/claude/local) 后续实现。

    子类必须:
    - 覆盖 PROVIDER_ID (与 BUILTIN_PROVIDER_ADAPTERS 键一致) 与 PROVIDER_TYPE
      (cloud/local/agent, 与 ProviderDefinition.type 对齐)。
    - 实现 generate/chat/stream 三个方法 (统一 I/O 契约)。
    - 失败处理: 返回 ProviderResponse(error=...) 而非抛异常 (稳定响应); 意外
      异常由上层防御 (同 ADR-0007 决策 4 哲学)。
    """

    PROVIDER_ID: str = ""       # 子类覆盖: provider id (如 "hermes")
    PROVIDER_TYPE: str = "cloud"  # 子类覆盖: cloud/local/agent

    @abstractmethod
    def generate(self, request: ProviderRequest) -> ProviderResponse:
        """单轮生成: request.prompt (或 messages 末条) → ProviderResponse。

        Args:
            request: 统一请求 (prompt/messages/system/model/temperature/metadata)。

        Returns:
            ProviderResponse: 成功 content 非空; 失败 error 非空 (不抛异常)。
        """
        raise NotImplementedError

    @abstractmethod
    def chat(self, request: ProviderRequest) -> ProviderResponse:
        """多轮对话: request.messages + system → ProviderResponse (同 generate 契约)。

        实现方可自行决定 system 注入方式 (首条消息/前缀行); 本接口不规定格式。
        """
        raise NotImplementedError

    @abstractmethod
    def stream(self, request: ProviderRequest) -> Iterator[ProviderResponse]:
        """流式生成: 逐块 yield ProviderResponse (content 为增量片段)。

        消费方拼接全部块的 content 得到完整输出; 失败时 yield 含 error 的单块
        (不抛异常)。生成器自身终结 = 流结束。
        """
        raise NotImplementedError
