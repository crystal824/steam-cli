# 开发日志

记录尚未进入 `CHANGELOG.md` / `docs/releases/` 的本地改动与审计结论。正式发版时，把本文件对应条目整理进 `docs/releases/<tag>.md`，并由 git-cliff 再生成 `CHANGELOG.md`。

## 2026-09-14

基于远程 `main` @ `ef9e573`（v0.2.7）本地审计与修复。**尚未提交、尚未发版。**

### 审计结论（修复前）

- 四道门禁：ruff / format / mypy 通过；pytest 在 Windows 上 1 失败。
- **P0**：愿望单读取迁移不完整——`wishlist.py` 已用 `IWishlistService/GetWishlist`，但 `radar`、`recommend --based-on wishlist`、`doctor` 探针仍打已退役的 `wishlistdata`（恒 302）。
- **P1**：`test_log_audit_…permissions` 在 Windows 失败（`os.open` 的 Unix mode 被忽略，实际 `0o666`）。
- **P2**：User-Agent 硬编码 `steam-cli/0.1`（9 处）；`_owned_games` 在 library / stats / recommend 三份拷贝。
- **P3**：`_raise_for_result` 未用参数、`library --sort added` 语义不符、`friends playing` 不支持多词、文档版本漂移、Makefile 用 `python3`。

### 已修复

| 类别 | 变更 |
|---|---|
| 愿望单 | 新增 `wishlist.wishlist_appids()`；`radar` / `recommend` / `doctor` 全部改走 `IWishlistService` |
| 测试 | 审计权限断言仅在 POSIX 检查；新增 `test_wishlist_appids_uses_iwishlistservice` |
| UA | `USER_AGENT = f"steam-cli/{__version__}"`（`__init__.py`），client / price / store / recommend / region / wishlist 统一引用 |
| 共享逻辑 | `client.owned_games()` 收口 library / stats / recommend |
| 多词参数 | `wishlist add/remove`、`launch`、`stats game`、`achievements`、`review post/list`、`store news` 均改为 `list[str] + join_terms` |
| 排序 | `library --sort added` → `last-played`；Skill 文档同步 |
| revoke-all | 连 refresh token 与 proxy 一并清除（新增 `auth.clear_refresh_token()`） |
| 杂项 | 删除 `region.language()` 死代码（读从不写的 `"lang"` 缓存键）；`_raise_for_result` 去掉未用 `key`；`friends playing` 支持多词；Makefile / README 用 `python`；`docs/development.md` 版本改为 v0.2.7 |

### 验证

```text
ruff check / ruff format / mypy → 通过
pytest → 108 passed（含新增 wishlist 测试）
```

### 改动规模

26 个文件，约 +179 / −179（相对 `ef9e573`）。工作区已清理 `*.egg-info`、`.mypy_cache`、`.pytest_cache`、`.ruff_cache`（均在 `.gitignore` 内）。

### 遗留 / 已知缺口（项目原有，未在本轮处理）

- `steam friends invite-link` 服务端 403
- `achievements` 显示 API 名而非本地化显示名
- `review summary` 人类可读输出标签固定中文
- `radar` / `wishlist on-sale` 逐条查价，偏慢
- Windows 上 `*.secret` / `audit.log` 依赖 ACL，而非代码中的 `0o600`

### 下一步建议

1. 自检后提交（建议拆成：wishlist 迁移、UA/共享、多词参数、revoke-all/杂项，或合成一次 chore/fix 提交）
2. 若发版：写 `docs/releases/v0.2.8.md`，同步 bump `pyproject.toml` + `uv.lock`，再 tag
