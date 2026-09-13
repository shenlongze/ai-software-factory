"""core — 平台本体（只依赖 contracts）。

两段：
    scheduler   调度器 —— 只回答一个问题：现在，下一个该是谁
    events      事实源 —— 追加不可变，链式哈希

core 纪律（由 tests/architecture 强制）：
    · 只 import contracts（+ 标准库）
    · 不出现任何具体业务领域的词汇（清单见铁律 R12）
    · 总行数 ≤ 3000
    · 不执行、不调模型、不写结果、不做证据判定
"""
