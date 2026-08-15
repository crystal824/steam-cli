# Contributing

感谢你愿意帮助改进 steam-cli！

## 开发环境

```bash
pip install -e ".[dev]"     # 安装项目 + 测试/检查依赖
pip install pre-commit      # 提交前检查工具
pre-commit install          # 注册 git 提交钩子
```

本地检查（与 CI 完全一致）：

```bash
ruff check src tests        # 代码规范
ruff format --check src tests
mypy src                    # 类型检查
pytest -q                   # 测试
```

## 发布

版本号以 `pyproject.toml` 为唯一来源。发布前递进版本号并创建对应的
`v<version>` 标签。发布构建会生成独立的 Python 包和 Hermes Skill 归档：

```bash
python -m pip install build twine
make release-check
```

产物位于 `dist/python/` 和 `dist/skill/`，不要将构建产物提交到 Git。
如果要同步发布到 PyPI，需要先配置 PyPI Trusted Publisher，再将仓库变量
`PUBLISH_PYPI` 设置为 `true`。

## 提交规范

提交信息使用 [Conventional Commits](https://www.conventionalcommits.org/)，类型前缀：

| 前缀 | 用途 |
|------|------|
| `feat:` | 新功能 |
| `fix:` | 修 bug |
| `docs:` | 文档 |
| `refactor:` | 重构（不改行为） |
| `test:` | 测试 |
| `chore:` | 杂项（CI、构建、配置） |

CHANGELOG.md 由 git-cliff 从提交历史自动生成（`make changelog`），**没有类型前缀的提交会从 changelog 中丢失**，请务必规范。

## ⚠️ 测试红线（必须遵守）

- **绝不用主账号（或任何真实常用账号）运行写操作测试**：`activate`、`wishlist add/remove`、`review post`、`friends invite-link --refresh`。
- 写操作测试一律使用**隔离的测试账号**。
- 只读功能优先用 HTTP 录制/回放方式测试（`respx`），CI 中不发起真实网络请求。
- 现有测试全部离线可跑（不依赖网络）。

## 分支与提交流程

1. 从 `main` 开分支：`git checkout -b feat/my-feature`
2. 提交时通过 `pre-commit` 检查
3. 推送分支并提交 Pull Request
4. 本地/CI 全绿后合并
