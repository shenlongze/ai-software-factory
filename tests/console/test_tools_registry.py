"""tests/console/test_tools_registry.py — U-1 统一工具注册表 (v1.1.168)。

Founder: 工具要和 CLI/WebUI 连接 — 39 内置工具统一注册 (唯一事实源)。
覆盖 (factory_console.tools.registry):
- 39 工具全量注册 (设计7/开发11/测试7/部署5/运维9)
- 每工具元数据齐全 (id/name/stage/status/desc/keywords)
- list_tools 按阶段过滤; get_tool; summary (implemented/planned)
- 四端入口标注 (cli/api/intent 至少一类; planned 允许全 None)
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
for _p in (_ROOT, _ROOT / "factory-core"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_P) if (_P := _p) else _p)  # noqa: F841

_reg = importlib.import_module("factory_console.tools.registry")


class TestToolRegistry:
    def test_39_tools_all_registered(self):
        tools = _reg.list_tools()
        assert len(tools) == 39

    def test_stage_distribution(self):
        s = _reg.summary()
        assert s["by_stage"] == {"设计": 7, "开发": 11, "测试": 7, "部署": 5, "运维": 9}

    def test_metadata_complete(self):
        for t in _reg.list_tools():
            assert t["id"] and t["name"] and t["stage"] and t["desc"]
            assert t["status"] in ("implemented", "planned")
            assert isinstance(t["keywords"], list)

    def test_implemented_have_entry(self):
        # implemented 工具必须有至少一类入口 (cli/api/intent)
        for t in _reg.list_tools():
            if t["status"] == "implemented":
                assert t["cli"] or t["api"] or t["intent"] or t["fn"], t["id"]

    def test_get_and_filter(self):
        assert _reg.get_tool("code_exec")["name"] == "代码生成/执行"
        assert _reg.get_tool("nope") is None
        assert len(_reg.list_tools("设计")) == 7
        assert all(t["stage"] == "设计" for t in _reg.list_tools("设计"))
