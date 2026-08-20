"""demo/repo 测试 (BacklogSweeper 沙箱验证用)。"""

from main import add, sub


def test_add():
    assert add(1, 2) == 3
    assert add(-1, 1) == 0


def test_sub():
    assert sub(5, 3) == 2
