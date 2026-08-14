# S10-037 Task 004 — Git Tag Recommendation

> 日期:2026-08-14 | Sprint: S10-037 | 只输出推荐命令, 不执行(用户指令)
> 原则: 不删除历史 tag v1.0.0-rc1; 新增正式 tag v0.1.0

---

## 推荐命令(用户确认后执行)

```bash
# 1. 打正式版本 tag (指向当前 HEAD e8de138+)
git tag v0.1.0

# 2. 推送 tag 到远端
git push origin v0.1.0

# 3. 验证
git tag -l          # 应同时存在: v0.1.0 + v1.0.0-rc1 (历史保留)
git ls-remote --tags origin
```

## GitHub Release(打 tag 后)

1. Repo → Releases → Draft a new release
2. Choose tag: v0.1.0
3. Title: AI Factory v0.1.0
4. 内容: 粘贴 docs/releases/v0.1.0.md(已就绪: Highlights/Quick Start/Features/Architecture/Tests/Known Limitations)
5. 可选: 上传 wheel 产物(ai_software_factory-0.1.0-py3-none-any.whl)

## 版本关系(最终)

```
v1.0.0-rc1  — 历史 (2026-08-06, 保留不删)
v0.1.0      — 正式首个社区版本 (待打 tag)
```

## 注意事项

- 不执行 git push -f
- 不删除历史 tag/release(用户原则)
- 打 tag 前确认 HEAD 是期望基线(当前 main 已含 S10-036 全部发布准备)

---

> Task 004 完毕 | 推荐: git tag v0.1.0 + git push origin v0.1.0 | 未执行(等用户确认)
