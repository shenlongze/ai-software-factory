"""factory-console/session/product.py — ProductIntent 模型 (S10-050 P0)。

产品级意图模型: 回答 "用户想创造什么" (vs IntentObject 回答 "用户想执行什么")。
生命周期: draft → confirmed → project_created (产品确认后经 create_product action
桥接 Project: product.json 落盘)。

设计: docs/sprint10/S10-050-product-manager-design.md §2.1 / §2.6

组件:
- ProductIntent — name/problem/user/platform/core_features/status/raw/session_id
  - REQUIRED_FIELDS: 必填字段 (problem/user/core_features — 缺任一 → DISCOVERY 追问)
  - is_complete() / missing_fields() (中文字段名 — 追问消息直接可用)
  - to_dict() / from_dict() / to_summary() (确认消息用)
- generate_temp_product_name() — "未命名产品-<ts>" 临时名 (name 缺省生成)
- parse_core_features() — 核心功能文本 → list[str] (、/逗号/空格分隔)

边界:
- 纯标准库零依赖; 不 import 其它 session 模块 (供 context/actions/conversation 引用,
  无循环导入)
- 只建模, 不执行业务 (创建逻辑在 actions.create_product)
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Optional

#: 必填字段 (缺失 → DISCOVERY 追问; 设计 §2.1)
REQUIRED_FIELDS: tuple[str, ...] = ("problem", "user", "core_features")

#: 字段 → 中文名 (missing_fields / 追问消息用, 设计 §2.3 口径)
FIELD_LABELS: dict[str, str] = {
    "problem": "产品解决什么问题",
    "user": "目标用户",
    "core_features": "核心功能",
    "name": "产品名称",
    "platform": "运行平台",
}

#: 追问问题模板 (DISCOVERY 多轮 — 缺什么问什么, 不静默)
FIELD_QUESTIONS: dict[str, str] = {
    "problem": "这个产品解决什么问题?",
    "user": "目标用户是谁?",
    "core_features": "核心功能有哪些? (用逗号或顿号分隔)",
    "platform": "运行平台是什么? (如 mobile/web/desktop, 可不填)",
}

#: 核心功能分隔符 (中文顿号/逗号/分号/空白)
_FEATURE_SEPARATORS = "、,，;；/ \t\n"


@dataclass
class ProductIntent:
    """产品级意图 (设计 §2.1): 用户想创造什么的结构化资产。

    name: 产品名 (缺省 → 临时名 "未命名产品-<ts>")
    problem: 产品解决什么问题 (必填)
    user: 目标用户 (必填)
    platform: 运行平台 (可选: mobile/web/desktop)
    core_features: 核心功能列表 (必填)
    status: draft → confirmed → project_created (生命周期)
    raw: 原始输入 (审计)
    session_id: 来源会话 (审计)
    """

    name: Optional[str] = None
    problem: Optional[str] = None
    user: Optional[str] = None
    platform: Optional[str] = None
    core_features: list[str] = field(default_factory=list)
    status: str = "draft"
    raw: str = ""
    session_id: Optional[str] = None

    #: 必填字段 (问题/用户/核心功能 — 缺任一不算完整产品)
    REQUIRED_FIELDS: tuple[str, ...] = REQUIRED_FIELDS

    def _has_value(self, field_name: str) -> bool:
        """字段是否有值: core_features 非空列表; 其余非 None/非空串。"""
        value = getattr(self, field_name)
        if field_name == "core_features":
            return bool(value)
        return value not in (None, "")

    def missing_fields(self) -> list[str]:
        """缺失的必填字段 (中文字段名 — 追问/错误消息直接可用)。"""
        return [
            FIELD_LABELS.get(name, name)
            for name in self.REQUIRED_FIELDS
            if not self._has_value(name)
        ]

    def is_complete(self) -> bool:
        """必填字段是否齐全 (problem/user/core_features)。"""
        return not self.missing_fields()

    def to_dict(self) -> dict[str, Any]:
        """序列化视图 (product.json 落盘 + 审计)。"""
        return {
            "name": self.name,
            "problem": self.problem,
            "user": self.user,
            "platform": self.platform,
            "core_features": list(self.core_features),
            "status": self.status,
            "raw": self.raw,
            "session_id": self.session_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProductIntent":
        """反序列化 (product.json 读取 / 测试构造)。"""
        data = data or {}
        features = data.get("core_features") or []
        if isinstance(features, str):
            features = parse_core_features(features)
        return cls(
            name=data.get("name"),
            problem=data.get("problem"),
            user=data.get("user"),
            platform=data.get("platform"),
            core_features=list(features),
            status=data.get("status") or "draft",
            raw=data.get("raw") or "",
            session_id=data.get("session_id"),
        )

    def to_summary(self) -> str:
        """产品摘要 (PRODUCT_CONFIRMATION 确认消息, 设计 §2.3 [4])。"""
        lines = [
            f"产品: {self.name or '(未命名)'}",
            f"问题: {self.problem or '(未填写)'}",
            f"目标用户: {self.user or '(未填写)'}",
            f"核心功能: {', '.join(self.core_features) if self.core_features else '(未填写)'}",
        ]
        if self.platform:
            lines.append(f"运行平台: {self.platform}")
        return "\n".join(lines)

    def to_json(self) -> str:
        """JSON 序列化 (product.json 落盘内容)。"""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2) + "\n"


def generate_temp_product_name(ts: Optional[int] = None) -> str:
    """临时产品名 "未命名产品-<ts>" (name 缺省生成, 设计 §2.1)。

    ts 可注入 (测试确定性); 缺省 int(time.time())。
    """
    return f"未命名产品-{int(ts) if ts is not None else int(time.time())}"


def parse_core_features(text: Any) -> list[str]:
    """核心功能文本 → list[str] (顿号/逗号/分号/空白分隔, 去空白去空项)。

    已为 list → 原样规范化返回 (失败安全, 不抛)。
    """
    if isinstance(text, list):
        return [str(item).strip() for item in text if str(item).strip()]
    if text is None:
        return []
    raw = str(text)
    normalized = raw.replace("，", ",").replace("、", ",").replace("；", ",")
    return [part.strip() for part in normalized.split(",") if part.strip()]
