

# ── 搬迁过渡：装载旧名→新路径的别名桥（详见 compat_aliases.py）──
# 放在包 __init__ 里 → 任何入口（bin/factory · console script · 测试）
# 只要 import 了本包，旧名就已可解析。搬迁完成后本段可删。
try:
    from ai_factory_os.compat_aliases import install as _install_aliases
    _install_aliases()
except Exception:  # noqa: BLE001
    pass
