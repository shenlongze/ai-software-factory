"""tests/intelligence/test_intelligence_store_atomic.py — 原子写 + 损坏失败安全 (Phase 10A-1)。

覆盖: 目录由首次原子写创建 (无预建 mkdir 的逆断言 — mkdir 局部化在损坏测试类
autouse fixture, backend-developer skill 陷阱: 共享目录 fixture 加 mkdir 会破坏
test_dir_created_on_first_write); 无 .tmp 残留; os.replace 原子替换; 损坏文件
(JSON 解析失败/结构不符/模型校验失败/空文件) 响亮报错不静默; 三文件独立损坏。
"""

from __future__ import annotations

import inspect
import json
import os
from pathlib import Path

import pytest

from intelligence.store import (
    CorruptIntelligenceStoreError,
    DecisionStore,
    ExperienceStore,
    IntelligenceStoreError,
    RecommendationStore,
)

from intelligence_helpers import make_decision, make_experience, make_recommendation


class TestAtomicWrite:
    def test_dir_created_on_first_write(self, tmp_path: Path):
        """目录由首次原子写创建 (不预建 — 逆断言与损坏类 mkdir 互斥)。"""
        idir = tmp_path / "factory" / "intelligence"
        assert not idir.exists()
        DecisionStore(idir).save(make_decision())
        assert idir.is_dir()
        assert (idir / "decisions.json").is_file()

    def test_no_tmp_residue_after_save(self, tmp_path: Path):
        idir = tmp_path / "factory" / "intelligence"
        store = DecisionStore(idir)
        for i in range(5):
            store.save(make_decision(decision_id=f"d{i}"))
        tmp_files = [p.name for p in idir.iterdir() if p.name.endswith(".tmp")]
        assert tmp_files == []

    def test_no_tmp_residue_after_upsert(self, tmp_path: Path):
        idir = tmp_path / "factory" / "intelligence"
        store = DecisionStore(idir)
        for _ in range(10):
            store.save(make_decision())  # 同 id 覆盖
        assert [p.name for p in idir.iterdir()] == ["decisions.json"]

    def test_three_stores_no_cross_tmp(self, tmp_path: Path):
        idir = tmp_path / "factory" / "intelligence"
        DecisionStore(idir).save(make_decision())
        RecommendationStore(idir).save(make_recommendation())
        ExperienceStore(idir).save(make_experience())
        assert sorted(p.name for p in idir.iterdir()) == [
            "decisions.json",
            "experiences.json",
            "recommendations.json",
        ]

    def test_uses_os_replace_for_atomicity(self):
        """源码级断言: 原子写 = 临时文件 + os.replace (同 product/providers 模式)。"""
        import intelligence.store as store_module

        src = inspect.getsource(store_module)
        assert "os.replace" in src
        assert ".tmp" in src

    def test_write_is_self_consistent_json(self, tmp_path: Path):
        """落盘文件随时可解析 (原子写不留半成品)。"""
        idir = tmp_path / "factory" / "intelligence"
        store = DecisionStore(idir)
        for i in range(3):
            store.save(make_decision(decision_id=f"d{i}", description=f"v{i}"))
        raw = json.loads((idir / "decisions.json").read_text(encoding="utf-8"))
        assert sorted(raw["decisions"].keys()) == ["d0", "d1", "d2"]

    def test_tmp_naming_includes_pid(self, tmp_path: Path):
        """临时文件名带 pid (多进程共存不冲突, 同 product 模式)。"""
        import intelligence.store as store_module

        src = inspect.getsource(store_module)
        assert ".{self._filename}.{os.getpid()}.tmp" in src


class TestCorruptionDetection:
    """损坏检测只对真实存在的文件生效 → mkdir 局部化在本类 autouse (不破坏
    test_dir_created_on_first_write 的逆断言)。"""

    @pytest.fixture(autouse=True)
    def _prepare_dir(self, tmp_path: Path):
        idir = tmp_path / "factory" / "intelligence"
        idir.mkdir(parents=True, exist_ok=True)
        self.idir = idir
        self.store = DecisionStore(idir)

    def _write(self, content: str, filename: str = "decisions.json") -> Path:
        p = self.idir / filename
        p.write_text(content, encoding="utf-8")
        return p

    def test_corrupt_json_raises(self):
        self._write("{not valid json!!!")
        with pytest.raises(CorruptIntelligenceStoreError):
            self.store.list_all()
        with pytest.raises(CorruptIntelligenceStoreError):
            self.store.count()

    def test_wrong_structure_raises(self):
        self._write("[1, 2, 3]")  # 顶层非 dict
        with pytest.raises(CorruptIntelligenceStoreError):
            self.store.list_all()

    def test_missing_section_raises(self):
        self._write('{"other_section": {}}')
        with pytest.raises(CorruptIntelligenceStoreError):
            self.store.list_all()

    def test_invalid_record_model_raises(self):
        # subject_id 必须为 str → 模型校验失败 → 响亮报错 (不静默跳过)
        self._write('{"decisions": {"d1": {"subject_id": 123}}}')
        with pytest.raises(CorruptIntelligenceStoreError):
            self.store.list_all()

    def test_empty_file_raises(self):
        self._write("")
        with pytest.raises(CorruptIntelligenceStoreError):
            self.store.get("d1")

    def test_error_is_intelligence_store_error(self):
        self._write("###")
        with pytest.raises(IntelligenceStoreError):
            self.store.list_all()

    def test_get_also_detects_corruption(self):
        self._write("{broken")
        with pytest.raises(CorruptIntelligenceStoreError):
            self.store.get("d1")

    def test_recommendation_store_independent_corruption(self, tmp_path: Path):
        """三文件独立: recommendations.json 损坏不影响 decisions.json 读取。"""
        idir = tmp_path / "factory" / "intelligence"
        idir.mkdir(parents=True, exist_ok=True)
        DecisionStore(idir).save(make_decision())
        (idir / "recommendations.json").write_text("[[[", encoding="utf-8")
        # decisions 正常读
        assert DecisionStore(idir).count() == 1
        # recommendations 响亮报错
        with pytest.raises(CorruptIntelligenceStoreError):
            RecommendationStore(idir).list_all()

    def test_experience_store_independent_corruption(self, tmp_path: Path):
        idir = tmp_path / "factory" / "intelligence"
        idir.mkdir(parents=True, exist_ok=True)
        ExperienceStore(idir).save(make_experience())
        (idir / "experiences.json").write_text('{"experiences": {"e1": {"domain": "nope"}}}', encoding="utf-8")
        with pytest.raises(CorruptIntelligenceStoreError):
            ExperienceStore(idir).list_all()
        assert (idir / "experiences.json").exists()  # 损坏不自动清除数据


class TestMissingFileSemantics:
    def test_missing_file_is_empty_not_error(self, tmp_path: Path):
        """文件不存在 = 空库 (首次写前合法状态), 不是损坏。"""
        idir = tmp_path / "factory" / "intelligence"
        assert not idir.exists()
        store = DecisionStore(idir)
        assert store.list_all() == []
        assert store.count() == 0
        assert store.get("d1") is None
