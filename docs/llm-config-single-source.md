# LLM 配置：单源（Single Source of Truth）设计与改法

> **Founder 定的原则（原话 ✓）**：
> 「上面分层没有问题，但是**底层 OS 应该只有一套配置**，
>   上层的应该是**加载过去的**，**用户不能、也不用单独配置**。」
>
> 本文 = 按此原则的现状核对 + 改法规格。**只读产出（未改代码 ✗）。**

---

## 1. 现状核对：同一件事有三处可配（✗ 违反原则）

| # | 位置 | 存什么 | 谁在用 | 问题 |
|---|---|---|---|---|
| ① | `config.py` `PROVIDER_DEFAULTS` | 硬编码默认 `model="deepseek-v4-pro"` ✗ | `config.get_llm()` | **自带一套默认** ✗ |
| ② | `providers.json` | provider 的 `models[]` / `enabled` / `api_key_ref` | `llm_control`（LLM 控制面） | **真正发请求用它**（`model_id = pc.models[0]`）✓ |
| ③ | `models.json` | 模型元数据 + `suggest()` 候选 | `model_catalog`（Router 预留） | **只登记了 chat/reasoner，没有 v4-pro** ✗ |

**症状（实测 ✓）**：`factory config show` 报 `model=deepseek-v4-pro`，
而实际发请求用的是 `deepseek-chat`，模型目录里根本没有 `v4-pro`。
⇒ 三处各说各的；**用户要在哪配？答：不知道 ✗** —— 这就是 Founder 说的"不能也不用单独配置"的反面。

## 2. 原则落地：一条权威 + 其余全是投影

```
                ┌─────────────────────────────────────────┐
                │  唯一权威（OS 底层）                    │
                │  ~/.factory/providers.json              │
                │  · provider: id/enabled/models[]/       │
                │    base_url/api_key_ref(env:VAR ✓)      │
                └───────────────┬─────────────────────────┘
                                │  只读投影（load，不复制 ✗）
        ┌───────────────────────┼───────────────────────┐
        ▼                       ▼                       ▼
  config.get_llm()        llm_control            model_catalog
  运行时取用 ✓             生命周期管理 ✓          模型元数据（只读视图 ✓）
```

**为什么权威选 `providers.json`（而不是 config.json）**：
- API key 引用（`env:VAR`）只在这里 ✓（红线：明文 key 永不落盘 ✓）
- provider 的 `enabled`（启停）只在这里 ✓
- `llm_control` 的 D4 已把它排在 `config.json` 之后作为覆盖层 ✓
- **③ models.json 保持独立**：它是**模型元数据目录**（能力/费率），
  但不是"当前选哪个"的权威 —— **"当前选择"必须只有一处** ✓

## 3. 改法（三刀，每刀可验证 ✓）

| 刀 | 改什么 | 判据（怎么验） |
|---|---|---|
| **L1** | `config.get_llm()` 的 `model` 不再用硬编码默认 ✗ → **改为从权威读取**；读不到才回落 | 改 `providers.json` 的 `models[]` → `config show` 的 model **跟着变** ✓ |
| **L2** | 加**一致性校验**：权威里的每个 `models[]` 条目**必须存在于 `models.json`**；不存在 → **响亮警告**（不静默 ✗） | 造一个假模型 → 必须报警 ✓；真模型 → 静默通过 ✓ |
| **L3** | **用户入口收敛**：只保留 `factory llm`（+ init 向导）写权威；`config.json` **不再接受 llm.\***（已有红线 ✓ 保持） | `factory config set llm.model x` → 已被拒 ✓（现状即如此 ✓）；`factory config show` 的 model **只读**投影自权威 ✓ |

```
L1 之后：用户在【一处】配置 ✓（factory llm / init 向导）
        所有入口（config show / llm list / provider / 执行时）读到【同一个值】✓
```

## 4. 验收（Founder 的标准 ✓）

1. **同一个值** ✓：`factory llm show deepseek` 与 `factory config show` 的 model **逐字相同**
2. **只配一次** ✓：改一处 → 所有入口同步变（不需要用户改第二个地方）
3. **一致性有守** ✓：权威里出现目录中没有的模型 → **响亮报警** ✓（不静默 ✗）
4. **负例必测** ✓：故意写个假模型 → 必须报警（当前的 v4-pro 就是活样本 ✓）

## 5. 诚实边界

- `models.json` **保留** ✓（它是元数据，不是"当前选择"✗）——**但"当前选择"只有一处** ✓
- 费率/能力等元数据仍归 `models.json` ✓，**不搬进 providers.json** ✗（那是两件事）
- 本改法**不改执行链** ✓，只收敛"默认值来源 + 一致性校验" ✓ → 风险低 ✓
