"""agents/skills.py — Skill 辅助: 内置技能目录 (能力描述非执行)。

用途: 测试数据源 / CLI 冒烟演示 / 后续阶段 (Agent 自动调度) 的推荐技能集。
非强制 — Skill 完全由用户自由定义, 内置集只是约定俗成的起点 (KISS)。
"""

from __future__ import annotations

from .models import Skill

BUILTIN_SKILLS: dict[str, dict] = {
    "flutter": {
        "name": "flutter",
        "category": "frontend",
        "description": "Flutter/Dart 跨平台 UI 开发",
        "capabilities": ["widget", "state management", "material design", "dart"],
        "version": "1.0.0",
    },
    "frontend": {
        "name": "frontend",
        "category": "frontend",
        "description": "Web 前端 (HTML/JS/Vue/小程序)",
        "capabilities": ["html", "javascript", "vue", "css"],
        "version": "1.0.0",
    },
    "backend": {
        "name": "backend",
        "category": "backend",
        "description": "后端开发 (Java/Spring Boot/Python/CLI)",
        "capabilities": ["java", "spring boot", "python", "rest api"],
        "version": "1.0.0",
    },
    "testing": {
        "name": "testing",
        "category": "quality",
        "description": "功能/压力/自动化测试",
        "capabilities": ["pytest", "unit test", "regression", "acceptance"],
        "version": "1.0.0",
    },
    "validation": {
        "name": "validation",
        "category": "quality",
        "description": "独立验证 (L1/L2/L3 验证门)",
        "capabilities": ["verification", "acceptance check", "report"],
        "version": "1.0.0",
    },
}


def builtin_skill(skill_id: str) -> Skill | None:
    """按 id 取内置技能; 不存在返回 None。"""
    data = BUILTIN_SKILLS.get(skill_id)
    return Skill(id=skill_id, **data) if data is not None else None


def builtin_skill_ids() -> list[str]:
    """内置技能 id 列表 (排序, 稳定)。"""
    return sorted(BUILTIN_SKILLS)
