# 14 — P0 / P1 / P2-A BOUNDARY (P2-C CONTRACT, 2026-09-06)

## 硬门槛: P2-C consume-only

| 域 | 修改 | hook 方式 |
|---|---|---|
| P0 (node_runtime/verification/evidence/artifact/external) | **零修改** | finalize 后 hook 在**调用侧**或读 EXS/ver store (不碰 finalize 内部 authority) |
| P1 (product_truth) | 零修改 | reverse_trace 只读 |
| P2-A (release_truth) | 零修改 | execute 后由调用侧/独立 listener 触发 bridge (不写 release_truth 内部) |

## 实施注意 (未来)

finalize hook 若需在 finalize_node_run 内加 bridge 调用 = P0 文件改动?
→ **避免**: bridge 由 agent_loop 调用侧 (finalize 后) 或独立
  finalize-observer 触发 — 保持 P0 生产文件零 diff (C13 zero-diff)。
  release bridge 同理 (release_truth.execute 返回后调用侧触发)。

## 禁止

ExperienceBridge 不得改 P0/P1/P2-A authority / 不得被 production 依赖。
