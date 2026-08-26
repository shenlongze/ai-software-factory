# S10-125 · C-2 产出物契约引擎接线 — Hermes 提示词（2026-08-26）

> 战役: C-2（docs/产出物契约-平台级.md §8 · 债务清单 C-2）
> 版本: **不 bump 版本文件** — 集成时由 Codex 统一 bump（C-2 与 C-3 合并同一版本, 避免并发版本冲突）
> 交付后: 债务清单 C-2 ✅
> ⚠️ 并行纪律（关键）: 与 Codex 的 WebUI（C-3/W-1）并行 — **共享桥文件只归 Codex 碰**:
>   `fastapi_adapter.py` / `artifact_contract.py`(只可 import, 不可改) / `web/frontend/` /
>   `pyproject.toml` / `CHANGELOG.md` / `docs/FEATURES.md` / 版本断言测试 —— Hermes 全部不碰。
>   工作区若有他人未提交改动, 先 git status 确认, 不覆盖。

---

请作为 Hermes 派发 Sprint 任务给 Codex，遵守既有纪律（pre-flight → plan → dispatch → verify → acceptance → report）。

【任务】S10-125 · C-2 产出物契约引擎接线（平台级, 全部项目）
目标: 所有引擎写产出物只走 `set_artifact`（C-1 已交付: Manifest+历史+追溯+版本信号）

【背景（C-1 已交付, v1.1.109）】
- `factory-console/artifact_contract.py`: `set_artifact(root, project_id, type, data, *,
  raw_text=None, producer="unknown", trace_id=None, file=None)` — 校验→归档旧版到
  history/<名>.v<N>.<ext>→写当前标准文件→更新 artifacts.manifest.json(版本链+producer+
  trace_id+时间戳)→bump 项目版本; `ARTIFACT_SCHEMA` 默认文件名; `read_manifest` /
  `get_artifact_version` / `scan_project` / `validate_*` 已就绪
- 设计稿: docs/产出物契约-平台级.md（Manifest 权威 + 固定文件名默认约定 + 历史不丢）

【现状（实事求是, pre-flight 必须全量核对, 不限于此）】
已知直写产出物文件的引擎点（需枚举补全）:
1. `factory-console/session/change_control.py` — PRD.md 追加 v2 / tasks.json / plan.json /
   execution_plan.json（M3-6 变更回流）
2. 产品管线（product pipeline / PRD 生成）— product.json / PRD.md
3. `factory-console/service.py` — create_project 等落 product.json
4. 编排器 / workflow_runner — engineering.json / plan.json / tasks.json / execution_*
5. `factory-console/memory/extraction.py`（读写 repair_task.json / validation_result.json）
6. 其余未列出的直写点 — pre-flight 全量枚举（grep 各标准文件名写路径）

【设计与实现要求（先出设计文档 docs/sprint10/S10-125-c2-plan.md, 批准后再实现）】
1. **写点全量枚举（pre-flight 必做）**: 列出所有引擎直接写产出物文件的位置
   （文件+行+产出物类型+当前写法: 覆盖写/追加写/JSON dump/模板渲染）
2. **改造原则**: 每个写点改走 `set_artifact`, 传入:
   - `producer`: 引擎标识（product-pipeline / change-control / orchestrator / execution …）
   - `trace_id`: 从 K-4 contextvar 读（`factory-console/trace_context.py`, 无上下文 → None）
   - `file`: 保持现状文件名（默认即可; 若现写位置非默认名, 显式传, 不改变落盘位置）
   - **内容语义零变化**: 写出的文件内容与改造前逐字节一致（除合法 JSON 格式缩进外）;
     JSON 用 data 传对象, markdown 用 raw_text 传全文
3. **追加写场景（如 change_control PRD.md 追加 v2）**: 先读现有全文, 合并新内容后整体
   走 `set_artifact`（归档旧版=含历史, 符合"历史不丢"）; 禁止绕过契约直接 append
4. **读路径不动**: 只改"写"动作; 读（service/retriever/board/intent 等）保持原样
   （契约目标是写统一, 读端 C-3 再接 manifest）
5. **失败安全**: set_artifact 异常不得阻断主流程（引擎照常产出, 契约尽力而为, 同
   C-1 语义）; 但默认路径必须成功（测试断言）
6. **契约自身**: artifact_contract.py 只 import 不改; 需要新增能力（如批量/追加辅助）
   先提给 Codex, 不在本任务直接改
7. **测试**:
   - 每个引擎写点改造后有断言: 写后 manifest 有该类型条目 + 版本 +1 + producer/trace_id
     正确 + history 归档（第二次写）; 内容读取一致
   - 回归: 全量 tests/console + tests/api 0 新增失败（预存失败如 session/LLM 类需
     A/B 隔离确认, 与本任务无关）

【验收】
1. 写点枚举文档（含改造前后对照）✅
2. 全部引擎写点走 set_artifact, 直写点归零（grep 无残留直写标准文件名）✅
3. 契约测试 + 引擎接线测试全过, 回归 0 新增失败 ✅
4. 边界遵守: 未碰 fastapi_adapter / frontend / 版本文件 / artifact_contract 本体 ✅
5. 诚实记录: 无法改造的点（如有）如实标注 + 理由 ✅

【提示】C-1 已提供 `set_artifact` 幂等写 + 历史归档, 本任务重点是"接线"不是"新能力";
遇到契约能力缺口 → 记录给 Codex, 不自行扩契约。
