# demo/repo — BacklogSweeper 演示仓库 (M1b · E3 / M1 闭环)

E3 积压清道夫演示项目: 一个最小 Python 仓库 + `issues.json` issue 清单。

## 快速演示 (无 LLM 也 3/3 确定性修完)

```bash
factory workload backlog --project demo/repo
```

- **ISS-001 (dependency)** — 缺少 `requests` → 确定性追加依赖
- **ISS-002 (dependency)** — 缺少 `httpx` → 确定性追加依赖
- **ISS-003 (dependency)** — 升级 `flask` 到 3.0.0 → 确定性版本升级

三个 issue 全部走确定性依赖修复器 (无 LLM 也真实修复): 每个 issue 在
Sandbox 副本生成可应用 patch + pytest 验证 → 证据包落盘
`projects/demo-repo/evidence/` + pending 审批请求。

## 看证据 + 审批 + 应用 (完整闭环)

```bash
factory evidence list --project demo-repo          # 证据包可见 (show 附审批状态)
factory approval list                              # 待审批列表 (每行附证据包 id)
factory approval decide <id> approve --by <你>     # 审批决策 (approve 后提示下一步)
factory approval apply <id> --project demo/repo    # 应用已批准 patch (落地)
```

## 说明

- 修改只在 Sandbox 副本 (原仓库零影响, 同 `factory repo`); patch 经 Human
  审批后可 `factory approval apply --id <id> --project demo/repo` 应用。
- 非 git 目标被硬拒绝 (应用前须可审计)。
- `demo/repo` 本身不是 git 仓库 (源无需 git; 沙箱自建 git 基线)。
