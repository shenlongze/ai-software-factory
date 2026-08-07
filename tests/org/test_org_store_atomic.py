"""tests/org/test_org_store_atomic.py — 原子写 + 损坏失败安全 (Phase 16A, ADR-0036)。

覆盖: 原子写 (tmp + os.replace, 无 .tmp 残留) / 损坏 JSON → 响亮
CorruptOrgStoreError (绝不静默返回空) / 结构不符 (缺 section) / 单条模型
校验失败 → CorruptOrgStoreError / 六文件损坏互不影响 (一个坏不连坐)。

⚠ mkdir 局部化: 损坏测试需要真实存在的文件 (Path.exists() 为 True 才走
损坏分支), 但共享 org_dir fixture 不能 mkdir — 否则破坏
test_org_store.py::test_dir_created_on_first_write 的逆断言。因此本文件
用类内 autouse fixture 预建目录 (同 tests/intelligence 模式)。
"""

from __future__ import annotations

import json

import pytest

from org.store import CorruptOrgStoreError, OrgStore

from org_helpers import make_company, make_employee


@pytest.fixture
def corrupted_dir(tmp_path) -> object:
    """已存在的 Org 数据空间目录 (损坏测试专用, 类内局部化)。"""
    d = tmp_path / "org"
    d.mkdir(parents=True)
    return d


class TestAtomicWrite:
    def test_no_tmp_files_left(self, org_dir):
        store = OrgStore(org_dir)
        store.save_company(make_company())
        leftovers = [p for p in org_dir.iterdir() if p.name.endswith(".tmp")]
        assert leftovers == []

    def test_json_format(self, org_dir):
        store = OrgStore(org_dir)
        store.save_company(make_company())
        raw = json.loads((org_dir / "companies.json").read_text(encoding="utf-8"))
        assert set(raw) == {"companies"}
        assert "C-1" in raw["companies"]

    def test_write_overwrites_atomically(self, org_dir):
        store = OrgStore(org_dir)
        store.save_company(make_company(name="First"))
        store.save_company(make_company(name="Second"))
        raw = json.loads((org_dir / "companies.json").read_text(encoding="utf-8"))
        assert raw["companies"]["C-1"]["name"] == "Second"


class TestCorruptJson:
    @pytest.fixture(autouse=True)
    def _ensure_dir(self, corrupted_dir):
        return corrupted_dir

    def test_invalid_json_raises(self, corrupted_dir):
        (corrupted_dir / "companies.json").write_text("{not json", encoding="utf-8")
        store = OrgStore(corrupted_dir)
        with pytest.raises(CorruptOrgStoreError):
            store.list_companies()

    def test_missing_section_raises(self, corrupted_dir):
        (corrupted_dir / "companies.json").write_text(
            json.dumps({"other": {}}), encoding="utf-8"
        )
        with pytest.raises(CorruptOrgStoreError):
            OrgStore(corrupted_dir).count_companies()

    def test_wrong_section_type_raises(self, corrupted_dir):
        (corrupted_dir / "companies.json").write_text(
            json.dumps({"companies": []}), encoding="utf-8"
        )
        with pytest.raises(CorruptOrgStoreError):
            OrgStore(corrupted_dir).get_company("C-1")

    def test_validation_failure_raises(self, corrupted_dir):
        (corrupted_dir / "employees.json").write_text(
            json.dumps({"employees": {"E-1": {"id": "E-1"}}}), encoding="utf-8"
        )
        with pytest.raises(CorruptOrgStoreError):
            OrgStore(corrupted_dir).list_employees()

    def test_corruption_error_message_has_path(self, corrupted_dir):
        (corrupted_dir / "companies.json").write_text("x", encoding="utf-8")
        with pytest.raises(CorruptOrgStoreError) as exc:
            OrgStore(corrupted_dir).list_companies()
        assert "companies.json" in str(exc.value)


class TestIsolationBetweenFiles:
    @pytest.fixture(autouse=True)
    def _ensure_dir(self, corrupted_dir):
        return corrupted_dir

    def test_corrupt_company_does_not_affect_employees(self, corrupted_dir):
        (corrupted_dir / "companies.json").write_text("broken", encoding="utf-8")
        store = OrgStore(corrupted_dir)
        store.save_employee(make_employee())  # 写正常子库不受影响
        assert store.get_employee("E-1") is not None
        with pytest.raises(CorruptOrgStoreError):
            store.list_companies()

    def test_corrupt_knowledge_does_not_affect_company(self, corrupted_dir):
        (corrupted_dir / "knowledge.json").write_text("broken", encoding="utf-8")
        store = OrgStore(corrupted_dir)
        store.save_company(make_company())
        assert store.get_company("C-1") is not None
        with pytest.raises(CorruptOrgStoreError):
            store.list_knowledge()

    def test_save_raises_on_corrupt_file(self, corrupted_dir):
        """损坏文件上 save 先读后写 → 响亮 CorruptOrgStoreError (不静默覆盖)。"""
        (corrupted_dir / "companies.json").write_text("broken", encoding="utf-8")
        store = OrgStore(corrupted_dir)
        with pytest.raises(CorruptOrgStoreError):
            store.save_company(make_company())
