"""输入校验工具模块。"""


def validate_email(email: str) -> bool:
    """简单邮箱格式校验。"""
    if not isinstance(email, str) or "@" not in email:
        return False
    local, _, domain = email.partition("@")
    if not local or not domain or "." not in domain:
        return False
    if domain.startswith(".") or domain.endswith("."):
        return False
    return True


def validate_age(age: int) -> bool:
    """年龄校验 (int, 0-150 含边界)。"""
    return isinstance(age, int) and 0 <= age <= 150


def validate_score(score: float) -> bool:
    """成绩校验 (0-100 含边界, 数字字符串也接受)。"""
    try:
        return 0.0 <= float(score) <= 100.0
    except (TypeError, ValueError):
        return False
