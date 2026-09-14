# 铁律（永久生效）

> 权威布局: ADR-0037（根布局定案 = 方案 C，`src/ai_factory_os/`）。
> 本文件是"规则"，不是"状态"；状态看 `docs/ssot/`。

## 铁律 1：新代码只进新地基

任何新功能、新能力、新模块，只能写在 `src/ai_factory_os/` 的七层里：

```
 contracts/       数据契约（dataclass / Enum / Protocol）
 core/            调度 + 事件（零 IO，只许 scheduler + events）
 services/        域逻辑（organization / work / resource / execution / governance / learning）
 plugins/         实现绑定（factories / agents / skills / tools / mcp / models / storage…）
 infrastructure/  技术底座（llm / process / events / git / storage / sandbox / messaging）
 api/             对外接口（REST / 事件桥）
 bootstrap/       装配（唯一允许跨层 wire 的地方）
```

**不许写进 `src/legacy/`。** 那是隔离区，不是开发区。

## 铁律 2：`src/legacy/` 只减不增

旧代码按「重写替换」逐步归位到各层：新层实现 → 等价验证 → 切消费者 → 删旧件。
**不允许在隔离区里新增文件**，也不允许新层依赖隔离区（唯一的例外要写明理由并登记）。

## 铁律 3：根目录只放入口与元数据

```
 代码 → src/      多端 → apps/      文档 → docs/      脚本 → scripts/
 测试 → tests/    构建产物 → 不落盘（运行时目录一律 gitignore）
```

根目录不得出现 `factory-*`、运行时产物（`build/ exec/ projects/ workspace/`）、临时文件。

## 铁律 4：改动前先报告影响面

改什么 / 为什么 / 影响哪些消费者 —— 报告后才动。
批量文件操作（替换、搬迁、删除）必须附**全量验证**（逐模块导入 + 产品命令），不接受抽样。
