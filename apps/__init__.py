"""apps —— 消费者层（cli / web / desktop / mobile）, 独立于 src/。

SSoT §一: **`apps/` 独立于 `src/`**（cli / web / desktop / mobile 作为消费者, 不进包内）。
R7: `apps/*` 不许出现在 `src/` 内 —— 反之亦然: 消费者住这里, 不嵌进 `ai_factory_os`。

补记（2026-09-15）: CLI 原先住在 `src/ai_factory_os/api/cli/` —— 违反上面这条
（消费者嵌进了包内）。本次搬到 `apps/cli/`, 位置归正。
"""
from __future__ import annotations
