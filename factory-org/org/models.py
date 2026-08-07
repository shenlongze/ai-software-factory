"""factory-org/org/models.py — 组织领域模型 (Pydantic v2)。

设计依据 (phase16-organization-model-review.md §2 统一组织模型):
```
Company (parent 支持集团嵌套)
  ├── Department (可选, Solo 扁平 / Enterprise 嵌套)
  │     └── Role (全局 Role 注册表)
  │           └── Employee (Agent)
  │                 └── Capability + Knowledge + Authority + Experience + Performance
```

关键语义 (agent-employee-model.md):
- Capability ≠ Role: Employee.capabilities 是多技能集; Role 决定权限与责任
- Authority 绑定 Role (非 Agent): 默认 deny, 未声明即拒绝; 显式 deny 优先
- Role.authority_policy = Role→Permission 矩阵 (声明式模板), 实例化时物化为
  Authority 记录 (org.authority.granted/denied 可审计)
- Employee.status: active/left (离职生命周期保留记录, 不物理删除)
- KnowledgeItem.company_id: 公司隔离 (A 公司知识 B 公司不可见)

Pydantic v2 陷阱 (backend-developer 经验):
- 容器字段 None 输入 → 默认值必须 mode="before" validator (after 在类型检查后跑)
- 类级常量带注解 = 字段 → 用 ClassVar
- to_dict() 用 model_dump(mode="json") (datetime → ISO 字符串)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


def new_id(prefix: str) -> str:
    """生成带域前缀的唯一 id (如 C-1a2b3c4d)。"""
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def utcnow() -> datetime:
    """UTC 当前时间 (统一存储格式, 与 events 层同语义)。"""
    return datetime.now(timezone.utc)


def _norm_list(v: Any) -> Any:
    """None → [] 归一 (before validator 用: 类型检查前收到原始输入)。"""
    return v if v is not None else []


class _OrgModel(BaseModel):
    """组织模型基类: 严格字段 (extra=forbid) + JSON 友好导出。"""

    model_config = ConfigDict(extra="forbid")

    def to_dict(self) -> dict[str, Any]:
        """JSON 友好 dict (datetime → ISO 字符串, 审计/CLI 输出用)。"""
        return self.model_dump(mode="json")


class EmployeeStatus(str, Enum):
    """员工生命周期状态 (active → left; 离职保留记录, 权限即刻失效)。"""

    ACTIVE = "active"
    LEFT = "left"


class Company(_OrgModel):
    """公司 (组织根; parent_company 支持集团递归嵌套, Phase 21+)。

    knowledge_space: 公司知识空间标识 (默认 = company_id, 知识三层隔离的
    Layer 2 根 — 公司前缀数据空间, knowledge-learning-model.md §1)。
    """

    id: str
    name: str
    template: str = "solo"                    # 模板 id (software_company / solo)
    parent_company: str | None = None         # 集团嵌套 (Phase 21+ 预留)
    departments: list[str] = Field(default_factory=list)  # 部门 id 列表
    knowledge_space: str = ""                 # 空 → 生命周期创建时回填 company_id
    created_at: datetime = Field(default_factory=utcnow)

    @field_validator("departments", mode="before")
    @classmethod
    def _departments_none(cls, v: Any) -> Any:
        return _norm_list(v)


class Department(_OrgModel):
    """部门 (Company 直属子节点; Solo 模板扁平 = 无部门, 角色挂公司级)。"""

    id: str
    company_id: str
    name: str
    created_at: datetime = Field(default_factory=utcnow)


class Role(_OrgModel):
    """职位 (权限与责任的载体; Employee 经 role_ids 引用)。

    authority_policy: Role→Permission 矩阵 {permission: "allow"|"deny"} —
    声明式模板; 未列出的 permission 一律默认 deny (Default Deny 铁律)。
    实例化 (OrgLifecycle.create_role) 时逐条物化为 Authority 记录。
    company_id: 冗余 scoping 字段 (Solo 扁平无部门时 department_id="" 无法
    反查公司 — 公司隔离查询必需)。
    """

    id: str
    company_id: str
    department_id: str = ""                   # "" = company-level (Solo 扁平)
    name: str
    responsibility: str = ""
    authority_policy: dict[str, str] = Field(default_factory=dict)
    human: bool = False                       # True = Human 角色 (CEO, 唯一最终权)
    created_at: datetime = Field(default_factory=utcnow)

    @field_validator("authority_policy", mode="before")
    @classmethod
    def _policy_none(cls, v: Any) -> Any:
        return v if v is not None else {}


class Employee(_OrgModel):
    """员工 (Agent; Capability 多技能集 + Role 定权限, 二者分离)。

    knowledge_scope: 已绑定知识条目 id 列表 (公司知识只读所属公司, 绑定即授权)。
    experience_ref / performance: 经验引用与绩效 (10A experience 回流预留,
    本阶段只记录不消费 — 禁自动分配 Phase 18)。
    """

    id: str
    company_id: str
    name: str
    role_ids: list[str] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)
    knowledge_scope: list[str] = Field(default_factory=list)
    experience_ref: str = ""
    performance: float = 0.0
    status: EmployeeStatus = EmployeeStatus.ACTIVE
    joined_at: datetime = Field(default_factory=utcnow)
    left_at: datetime | None = None

    @field_validator("role_ids", "capabilities", "knowledge_scope", mode="before")
    @classmethod
    def _lists_none(cls, v: Any) -> Any:
        return _norm_list(v)

    @property
    def is_active(self) -> bool:
        """在职判断 (registry 检索只返回 active)。"""
        return self.status == EmployeeStatus.ACTIVE


class Authority(_OrgModel):
    """权限记录 (绑定 Role, 非 Agent; Default Deny: 未声明即拒绝)。

    effect: "allow" | "deny" — 显式 deny 优先于任何 allow (冲突规则:
    高危操作硬拒绝; Developer 无 release.approve 记录 → 默认 deny)。
    """

    id: str
    role_id: str
    permission: str
    effect: str = "allow"                     # "allow" | "deny"

    @field_validator("effect", mode="before")
    @classmethod
    def _effect_normalize(cls, v: Any) -> Any:
        if v is None:
            return "allow"
        low = str(v).strip().lower()
        if low not in ("allow", "deny"):
            raise ValueError(f"effect must be allow|deny, got {v!r}")
        return low


class KnowledgeItem(_OrgModel):
    """企业知识条目 (Knowledge 三层隔离 Layer 2: 公司级, company_id 隔离)。

    version: 知识变更 = 决策 → 版本化 (知识入库需人工确认, 本阶段记录 +
    审计; 重大变更 Approval 属 Phase 17 预留)。
    """

    id: str
    company_id: str
    domain: str
    content: str
    version: int = 1
    created_at: datetime = Field(default_factory=utcnow)
