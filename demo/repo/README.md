# demo/repo — BacklogSweeper 演示仓库 (M1b · E3)

E3 积压清道夫演示项目: 一个最小 Python 仓库 + `issues.json` issue 清单。

## 快速演示 (无 LLM 也能真实修一个 issue)

```bash
factory workload backlog --project demo/repo
```

- **ISS-001 (dependency)** — 确定性真实修复: 分析 `requirements.txt` 缺失
  `requests` → 生成可应用 patch → Sandbox 副本应用 + pytest 验证 →
  证据包落盘 `projects/demo-repo/evidence/` + pending 审批请求。
- **ISS-002 (feature) / ISS-003 (bug)** — 需 LLM 生成 patch; 无 LLM Provider
  时诚实 skipped (不伪造)。配置 LLM 后自动修复。

## 看证据 + 审批

```bash
factory evidence list --project demo-repo          # 证据包可见
factory approval list                              # 待审批列表
factory approval decide <id> approve --by <你>     # 审批决策 (复用 ApprovalGate)
```

## 说明

- 修改只在 Sandbox 副本 (原仓库零影响, 同 `factory repo`); patch 经 Human
  审批后可 `factory-exec approval apply --id <id> --project demo/repo` 应用。
- `demo/repo` 本身不是 git 仓库 (源无需 git; 沙箱自建 git 基线)。
