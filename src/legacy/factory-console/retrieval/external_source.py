"""factory-console/retrieval/external_source.py — M5-3 外挂适配器接口
(S10-123)。

ExternalKnowledgeSource Protocol + MockExternalSource (确定性) + 注册表 +
配置 providers.external_rag — 企业 Postgres/向量库/知识库 BYO 接入点 (接口先行)。

- register_external_source(source) / get_external_sources() / clear_external_sources()
- configured_external_sources(config) — 读 config providers.external_rag (缺省空,
  未配置 → 空不崩); 只返回已注册且名称命中的源
- 复用 RetrievalSource.EXTERNAL_RAG (models.py 预留挂点) — 注册语义同源
- 真实接入 (Postgres/向量库) 未做 — 接口 + Mock 就绪, 诚实标注

设计: docs/sprint10/S10-123-k6-rag-plan.md §1.2
边界:
- 纯标准库 (dataclasses/typing), 零新依赖
- 确定性: MockExternalSource 同输入同输出
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from .models import RetrievalSource

__all__ = [
    "ExternalKnowledgeSource",
    "MockExternalSource",
    "register_external_source",
    "get_external_sources",
    "clear_external_sources",
    "configured_external_sources",
]


@runtime_checkable
class ExternalKnowledgeSource(Protocol):
    """外挂知识源协议 (M5-3): name + search + ping。

    search(query, top_k) -> list[dict]: 每条 {content, source, score}
    ping() -> bool: 连通性探测 (未接入/故障 → False, 失败安全)
    """

    name: str

    def search(self, query: str, top_k: int) -> list[dict[str, Any]]: ...

    def ping(self) -> bool: ...


#: 外部源注册表 (进程内单例; 线程安全 — API/CLI 并发读)
_registry: dict[str, ExternalKnowledgeSource] = {}
_registry_lock = threading.Lock()


def register_external_source(source: Any) -> None:
    """注册外部知识源 (按 name 去重, 后注册覆盖)。"""
    name = str(getattr(source, "name", "") or "")
    if not name:
        return
    with _registry_lock:
        _registry[name] = source


def get_external_sources() -> list[Any]:
    """已注册外部源列表 (按 name 排序 — 确定性)。"""
    with _registry_lock:
        return [src for _, src in sorted(_registry.items(), key=lambda kv: kv[0])]


def clear_external_sources() -> None:
    """清空注册表 (测试隔离用)。"""
    with _registry_lock:
        _registry.clear()


def configured_external_sources(config: Any = None) -> list[Any]:
    """按配置 providers.external_rag 过滤已注册源 (缺省空 → 空不崩)。

    config: ConfigProvider (get(section, key)) 或任何有 get(section, key, default)
    的对象; None → 空。配置值: list[str] 源名 (逗号分隔字符串也兼容)。
    未配置 providers.external_rag → [] (不崩, 接口就绪状态)。
    """
    if config is None:
        return []
    try:
        raw = config.get("providers", "external_rag", None)
    except Exception:  # noqa: BLE001 — 失败安全
        return []
    names: list[str] = []
    if isinstance(raw, str):
        names = [n.strip() for n in raw.split(",") if n.strip()]
    elif isinstance(raw, (list, tuple)):
        names = [str(n).strip() for n in raw if str(n).strip()]
    if not names:
        return []
    by_name = {str(getattr(src, "name", "") or ""): src for src in get_external_sources()}
    return [by_name[n] for n in names if n in by_name]


# ================================================================== Mock (确定性)


@dataclass
class MockExternalSource:
    """确定性 Mock 外部知识源 (可跑可断言; 真实接入待后续, 诚实标注)。

    corpus: {关键词: 内容} 命中表 (同输入同输出);
    search: 返回 corpus 中 query 包含关键词 或 关键词包含 query 的条目;
    ping: alive (默认 True; False 模拟故障 — 失败安全不崩)。
    """

    name: str = "mock"
    corpus: dict[str, str] = field(default_factory=dict)
    alive: bool = True
    base_score: float = 0.9

    def search(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        """确定性搜索: corpus 键与 query 互含 → 命中 (score=base_score)。"""
        q = str(query or "")
        hits: list[dict[str, Any]] = []
        for i, (key, content) in enumerate(sorted(self.corpus.items())):
            if not (key in q or q in key):
                continue
            hits.append({
                "content": str(content),
                "source": key,
                "score": float(self.base_score),
            })
        return hits[: max(0, int(top_k or 0))]

    def ping(self) -> bool:
        """连通性探测 (alive=False → False, 失败安全)。"""
        return bool(self.alive)


#: 外部源检索动作源头 (models.py EXTERNAL_RAG 预留挂点 — 注册语义复用)
def _external_rag_source_type() -> RetrievalSource:
    """EXTERNAL_RAG 来源标识 (M5-3 挂点: 编排/去重可引用)。"""
    return RetrievalSource.EXTERNAL_RAG
