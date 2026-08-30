# IntelligenceStrategy Lifecycle (S42)

> 日期: 2026-08-29 | 冻结于 S42

## Lifecycle
复用 Plugin Lifecycle (S31): DISCOVERED→REGISTERED→ENABLED→DISABLED→RETIRED
(不建第二套 Lifecycle)

## 治理
- DISABLED → 执行拒绝 (PermissionError)
- 替换 (learning.v2/healing.alt/optimization.alt) → Core 零修改
- 不能 self-elevate / bypass governance / 改 Evidence history / 直接改 Production
