# 铁律（永久生效）

## 铁律 1：factory-core 冻结
factory-core 只修 bug，不加功能，不重构。
任何"顺手优化 factory-core"的提议 → 拒绝。

## 铁律 2：新功能只用新骨架
任何新功能、新能力、新模块，只能写在：
  kernel/  services/  extensions/  projections/
不许写进 factory-core / factory-exec / factory-org。

## 铁律 3：factory-core 的改动需审批
任何对 factory-core 的改动（含修 bug）必须先报告：
  改什么 / 为什么 / 影响哪些消费者
经 Founder 批准后才能动。
