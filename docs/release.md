# 发版与版本号规矩（Founder 定：2026-09-21）

> Founder 原话：**「以后每改一下，都递增最后版本号」**
> 本文是硬规矩；`AGENTS.md` 里挂着入口（进入即读）。

## 一、版本号在哪（改要**三处同步**，少一处就是错 ✗）

| 位置 | 字段 |
|---|---|
| `pyproject.toml` | `version = "X.Y.Z"` |
| `README.md` | 正文里的 `` `vX.Y.Z` `` |
| `CHANGELOG.md` | 新增 `## [vX.Y.Z] — YYYY-MM-DD` 一节 |

（`FEATURES.md` 不含版本号 ✓ 不用改。）

## 二、什么时候递增

**每改一次就递增末尾号**（patch +1）。

- 改代码 / 改界面 / 改判据 ⇒ 同一个提交里把版本号 + CHANGELOG 一起改 ✓
- 只改文档或守卫，也算"改动" ⇒ 同样递增 ✓（Founder 的规矩：不挑）
- 递增**只能往上**（禁止倒退）✓

## 三、发版动作（一条条来，别跳步 ✗）

1. 三处同步版本号 + CHANGELOG 一节（按 `Added / Fixed / Changed / Known gaps` 分组，逐条带证据 ✓）
2. 门禁全绿：`pytest` · `scripts/smoke_chain_links.py`（守卫）· `bash scripts/verify.sh` · `ruff check apps src scripts`
3. 提交 + 打 tag：`git tag -a vX.Y.Z -m "…"` ⇒ `git push origin HEAD:main` + `git push origin vX.Y.Z`
4. **重装**（editable 装的元数据不会自己更新 ✗）：
   `.venv/bin/pip install -e .` + `~/factory-venv/bin/pip install -e .`（你 PATH 上那个）
   ⇒ 用 `factory -v` 复核真的显示新版本号 ✓
5. `gh release create vX.Y.Z --title … --notes-file … --latest`
6. 回报里给：版本号 · tag · Release 链接 · 门禁读数

## 四、守卫

`scripts/smoke_chain_links.py` 的「版本号规矩」一组：
- 版本号在 `pyproject` / `README` / `CHANGELOG` **三处一致** ✓
- 版本号**不低于**最近 tag（防倒退 / 防忘记递增 ✗）
