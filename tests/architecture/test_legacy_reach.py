"""可达性工具的正确性守卫（工具曾出过三次错，必须锁死）。

被测对象：scripts/legacy_reach.py（作为 CLI 契约测试，不做内部导入）

锁定的三条回归：
    ① 相对 import 必须解析（factory-console 的 `from .x import y`）
       —— 否则活代码被误判为死（cli_factory.py 出边曾从 55 塌成 2）
    ② 字符串动态加载必须解析（importlib.import_module("...")）
       —— kernel/node/patch_filter 就是这样被加载的
    ③ 拼接式动态加载必须发现（__import__(f"factory_console.{mod}") 与
       经本地辅助函数 _console_import("api") 的转发）
       —— 漏了它，factory-console/api 整层会被当成"没人用"

并且：工具**绝不产出「可删」结论**。
"""
from __future__ import annotations

import json
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "scripts" / "legacy_reach.py"

CATEGORIES = ("live", "test_only", "unverified")

# 已知真活（被生产入口间接使用）。任一条被归入"未证实"即视为回归。
KNOWN_LIVE = (
    "factory-console/cli_factory.py",                   # CLI 入口
    "factory-console/web/backend/fastapi_adapter.py",   # Web 入口
    "factory-console/session/delivery.py",              # 经相对 import 被拉起（回归点①）
    "kernel/node/patch_filter.py",                      # 经字符串动态加载（回归点②）
    "kernel/governance/contracts.py",                   # 被 services/approval_runtime 使用
    "factory-core/agents/models.py",                    # 经 sys.path 根解析
)


@lru_cache(maxsize=1)
def _analyse() -> dict:
    """跑一次即可（扫描 ~4s，缓存后各测试共用）。"""
    proc = subprocess.run([sys.executable, str(TOOL), "--json"],
                          cwd=ROOT, capture_output=True, text=True, check=True)
    return json.loads(proc.stdout)


def test_tool_runs_and_partitions_are_disjoint() -> None:
    data = _analyse()
    sets = [set(data["paths"][k]) for k in CATEGORIES]
    assert not sets[0] & sets[1]
    assert not sets[0] & sets[2]
    assert not sets[1] & sets[2]
    assert data["totals"]["files"] == sum(len(s) for s in sets)


def test_never_claims_deletable() -> None:
    """绝不产出「可删」结论 —— 曾因动态加载盲区把 44 个活文件误判为可删。"""
    data = _analyse()
    assert "dead" not in data, "不得出现 dead 类目"
    assert "dead" not in data["paths"], "不得出现 dead 类目"


def test_known_live_files_are_not_misjudged() -> None:
    paths = _analyse()["paths"]
    for rel in KNOWN_LIVE:
        assert rel not in paths["unverified"], f"{rel} 被归入「未证实」（回归）"
        assert rel in paths["live"], f"{rel} 应在 live"


def test_computed_dynamic_imports_are_detected() -> None:
    """拼接式动态加载必须被发现（回归点③）。

    语料：factory-console 里 `__import__(f"factory_console.{mod}")` 与
    `_console_import("api")` → 受影响模块绝不可归为"没人用"。
    """
    data = _analyse()
    assert "factory_console." in data["dynamic_prefixes"], "未发现拼接前缀"
    assert data["dynamic_targets"], "未提取到本地辅助函数的字面量调用点"
    assert data["unverified_shadowed"]["files"] > 0, "受动态影响的文件必须被标出"


def test_entry_points_exist() -> None:
    data = _analyse()
    assert data["entries"], "必须声明活入口"
    for rel in data["entries"]:
        assert (ROOT / rel).exists(), f"入口不存在: {rel}"


def test_counts_are_internally_consistent() -> None:
    data = _analyse()
    for key in ("totals", *CATEGORIES):
        assert data[key]["files"] > 0, key
        assert data[key]["lines"] > 0, key
    assert data["totals"]["files"] == sum(data[k]["files"] for k in CATEGORIES)


def test_tools_agree_on_legacy_file_count() -> None:
    """两个工具必须对「旧代码文件数」给同一答案。

    回归：可达性工具曾把旧分区里嵌的 tests/ 误算进来（factory-runtime/tests/），
    与台账扫描器差 1 个文件 —— 台账数字对不上，等于台账不可信。
    """
    baseline = json.loads((ROOT / "tests" / "architecture" / "legacy_baseline.json")
                          .read_text(encoding="utf-8"))
    assert len(baseline["files"]) == _analyse()["totals"]["files"]


def test_blind_spot_is_reported_not_hidden() -> None:
    """未解析的动态目标与已知盲区必须被报出来 —— 宁可承认盲区，不假装精确。"""
    data = _analyse()
    assert isinstance(data["unresolved_dynamic"], list)
    assert isinstance(data["dynamic_calls"], int)
    assert len(data["blind_spots"]) == 4


def test_non_python_consumers_are_detected() -> None:
    """非 Python 载体的引用必须被发现。

    回归：factory-runtime 只被 Python 当【子进程 CLI】调用（消费者是 Rust 桌面应用），
    任何基于 import 的分析都看不见它 —— 我曾据此判它「0 活引用、可删」。
    现在靠名称引用扫描兜住：desktop/package.json 等必须被点名。
    """
    data = _analyse()
    ext = data["external_references"]
    assert "factory-runtime" in ext, "factory-runtime 未被点名（回归）"
    assert any("desktop" in f for f in ext["factory-runtime"]), \
        f"未发现 desktop 的引用: {ext['factory-runtime']}"


def test_self_references_are_not_reported() -> None:
    """本工具自己的产物不算「被消费」（否则 kernel/services 会被自家基线文件误报）。"""
    ext = _analyse()["external_references"]
    for name, files in ext.items():
        for f in files:
            assert not f.startswith("tests/architecture/"), f"{name} 被自家基线文件误报: {f}"
            assert not f.startswith("scripts/"), f"{name} 被自家脚本误报: {f}"
