"""文本工具模块。"""

import re


def title_case(text: str) -> str:
    """每个单词首字母大写 (其余小写)。"""
    return " ".join(word.capitalize() for word in text.split())


def slugify(text: str) -> str:
    """转 URL slug: 小写, 非字母数字转连字符, 去首尾连字符。"""
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9\s_-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    return text.strip("-")


def truncate(text: str, max_len: int = 30) -> str:
    """超长截断 (默认 30 字符, 末尾省略号, 总长不超 max_len)。"""
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"


def word_count(text: str) -> int:
    """单词数 (连续非空白片段计数)。"""
    return len(text.split())
