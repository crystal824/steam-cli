# steam-cli

[![CI](https://github.com/crystal824/steam-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/crystal824/steam-cli/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12-blue)](https://github.com/crystal824/steam-cli)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

**English** → [README.md](README.md)

在终端里搜 Steam 商店、**买前先看口碑**、管理游戏库与愿望单、激活 CDK、发评测、查好友与时长。
工具受一套严格的安全策略约束：绝不碰钱、购买、交易与账号安全设置。

它就是一个普通命令行工具。 [Hermes](https://agentskills.io) 是可选的：单独发布的技能包
（见 [Hermes 技能包](#hermes-技能包)）只是把同样的命令教给 Agent。

## 你需要什么

- **Python ≥ 3.11。**
- 逛商店、查价格、看评测：**什么都不需要**。
- 读取**你自己账号**的数据（游戏库、统计、好友、愿望单）以及任何写操作：需要
  **Steam Web API Key** 与**登录态**——Key 用于授权调用，登录态提供你的 SteamID。
  `steam status` 会告诉你缺什么，报错信息也会直接给出该跑哪条命令。

## 安装

```bash
python -m venv .venv && . .venv/bin/activate   # 或你惯用的环境
pip install .                                  # 从源码目录
steam --help
```

或安装官方发布产物：到[最新 Release](https://github.com/crystal824/steam-cli/releases/latest)
下载 `steam_cli-<版本>-py3-none-any.whl` 后 `pip install`。（**未发布到 PyPI**。）

**装完即用，无需任何额外步骤。** 第三方 `steam` 库的两处已知问题已在包内绕过
（[`src/steam_cli/_compat.py`](src/steam_cli/_compat.py)，登录见
[`src/steam_cli/modern_login.py`](src/steam_cli/modern_login.py)）；
[`patches/`](patches/README.md) 只是留档的原始补丁。

依赖：`typer`、`rich`、`steam`（ValvePython）、`httpx`、`keyring`。

## 30 秒试跑

以下命令都不需要账号、不需要任何凭据：

```bash
steam search black myth            # 多词名称不用加引号
steam app 2358720
steam price 1144200                # 按你所在区域的货币显示
steam review summary 1144200       # 档位 + 正负样本，用于购买决策
steam profile 76561198121699884
```

## 接入你的账号

```bash
steam set-key <你的Key>       # https://steamcommunity.com/dev/apikey —— 只读查询
steam login                   # 仅需一次：输入密码，然后在手机 App 批准或输入验证码
steam status                  # 看当前配了什么、会话是否仍有效
```

会话里带着长期 refresh token，所以**只是过期**时重建即可，不需要密码也不需要 2FA：

```bash
steam refresh --remint
```

`steam logout` 只清会话（**有意保留** refresh token）；`steam revoke-all` 才会抹掉全部凭据。
凭据存于系统 keyring；没有 keyring 的环境回落到 `~/.config/steam-cli/*.secret`（`0600`）。
**账号密码从不保存。**

## 能做什么

| 分类 | 命令 | 需要 |
|---|---|---|
| 登录 | `login` `status` `logout` `set-key` `refresh [--remint]` `revoke-all` | — |
| 自检 | `doctor` | — |
| 商店 | `search` `app` `price` `profile` | — |
| | `news` `radar` | Web API Key（`radar` 还需登录态） |
| 评测 | `review summary` `review list` | — |
| | `review mine` `review post` | 登录态 |
| 游戏库 | `library list` `library has` | Key + 登录态 |
| 愿望单 | `wishlist list` `add` `remove` `on-sale` | Key + 登录态 |
| 好友 | `friends list` `playing` `recently-played` | Key + 登录态 |
| | `friends invite-link` | 登录态（服务端 403，见下） |
| 统计 | `stats summary` `stats game` | Key + 登录态 |
| 成就 | `achievements` | Key + 登录态 |
| 卡密激活 | `activate <cdk> [--batch file]` | 登录态 + 二次确认 |
| 设置 | `config proxy …` `config region …` | — |
| 其它 | `launch` `recommend` | Key + 登录态（`launch` 还需桌面版 Steam） |

**没有 `steam auth …` 这个子命令**——所有命令都在顶层。上游旧文档（以及第三方库自己的
错误文案）里还会写成 `steam auth xxx`，请忽略那个前缀。

任何写操作都可用 `--dry-run` 预览而不真正发出。每条命令的参数见 `steam <命令> --help`。

## 看懂一款游戏的评价现状

`steam review summary <appid|游戏名>` 用来回答"这游戏到底怎么样"——**包括你还没买的游戏**：

- **评分档位**：同时给中文商店档位与 Steam 英文档位（好评如潮 / `Overwhelmingly Positive`、
  褒贬不一 / `Mixed`…），附好评率与评测总数
- **近期口碑**：从最新评测抽样得出
- **提炼素材**：最有帮助的好评与差评各若干条，附票数、语言、该玩家时长

```bash
steam review summary 1144200                     # 正负各 8 条；-s 12 可加量
steam review summary Elden Ring -L schinese      # 只看中文评测
steam review summary 1144200 --json              # 结构化输出，给脚本/Agent 用
```

下面是 `steam review summary 1144200 -s 1 --json` 的**真实输出**（截断；评测数会变化）：

```json
{
  "appid": "1144200",
  "language": "all",
  "overall": {
    "score": 6,
    "label": "多半好评 (Mostly Positive)",
    "positive": 272490,
    "negative": 73463,
    "total": 345953,
    "pct": 78.8
  },
  "recent": {"days": 30, "sampled": 400, "positive": 336, "pct": 84.0, "truncated": true},
  "samples": {
    "positive": [{"votes_up": 63, "language": "russian", "playtime_hours": 33.2, "text": "Ready or Not — это игра, где ты заходишь…"}],
    "negative": []
  }
}
```

人类可读输出的栏目名是中文（总评 / 近期 / 好评样本 / 差评样本），档位写成
`中文档位 (英文档位)`；`--json` 与语言无关。

CLI 本身不做总结——它只把档位、数字和样本交出来。如果由 Agent 来写结论，要求它：报出实际
读到的档位、好评率与样本条数；面向中文用户时跑两遍（`-L all` 与 `-L schinese`），因为两个
口径可能相差整整一档。

## 商店区域与语言

商店请求**跟随你的账号**：国家码取自账号页的 `country_code`（缓存一天），语言由国家推导
（cn→schinese，jp→japanese…）。中文账号拿到的是人民币价和中文商店文案。

```bash
steam status                                     # … Region: cn (schinese) — account
steam config region show                         # 当前用的是什么、来源在哪
steam config region set cn --lang schinese       # 钉住，不再跟随账号
steam config region clear                        # 恢复跟随账号
steam price 1144200 --cc us                      # 临时查其他区域价格
```

`STEAM_CLI_CC` / `STEAM_CLI_LANG` 可在单个 shell 内达到同样效果。

## 安全策略

- **直接拒绝**：购买、支付、交易、修改邮箱/手机、以及任何账号安全设置变更。
- **只有 `activate` 会二次确认**（它自己的提示，或 `--yes` 跳过）。其余写操作——
  `wishlist add/remove`、`review post`——**执行即生效、没有任何提示**，所以务必先确认意图
  （发评测还要先确认文案）。`--dry-run` 可只预览请求而不发出。
- `review post` 发完会回读你的资料页确认（`--verify/--no-verify`，默认开启）——Steam 回
  `{"success": true}` 并不等于评论可见。此外 Steam 要求该产品**至少 5 分钟游玩记录**。
- 登录与激活遇到验证码 / Steam Guard / 2FA 一律交回给你，绝不自动重试或绕过。
- 每次写操作都会追加到 `~/.config/steam-cli/audit.log`（仅本地）。

## 排错速查

| 现象 | 含义 |
|---|---|
| `not_authenticated: not logged in` | 该命令需要登录态（通常还需 Key）：`steam login`（并 `steam set-key <key>`）。 |
| `session_expired` | 免密码重建：`steam refresh --remint`。 |
| `api_key_missing` | `steam set-key <key>` —— https://steamcommunity.com/dev/apikey |
| `network_error` | 本机连不上 Steam，见[代理](#代理)。 |
| `review_rejected` | Steam 的原话（例如游玩时长不足 5 分钟）。 |
| `already_activated` | 该卡密此前已被使用——这是成功而非失败（可用 `tools/check_licenses.py` 验证）。 |
| `friends invite-link` 返回 403 | Valve 改了该接口，本地无法修复。 |
| 中文标题搜不到 | Steam 的中文索引缺部分译名（`二之国` 搜索为空，`Ni no Kuni` 正常）。改用英文原名或 appid。 |

背后的完整来龙去脉（Valve 下/改了哪些接口、每种症状怎么修的）见
[docs/steam-endpoint-changes-2026.md](docs/steam-endpoint-changes-2026.md)。

### 代理

连不上 Steam 时，配置一个作用于**所有**请求的代理：

```bash
steam config proxy set http://user:pass@127.0.0.1:7890   # 完整 URL，或：
steam config proxy set --host 127.0.0.1 --port 7890 --username u --password p
steam config proxy test
steam config proxy show        # 密码打码显示
steam config proxy unset
```

支持的协议：`http`、`https`、`socks4`、`socks5`、`socks5h`（SOCKS 需要
`PySocks`/`socksio`）。

## 仓库结构

| 路径 | 是什么 | 用 CLI 需要它吗 |
|---|---|---|
| `src/steam_cli/` | CLI 本体 | 就是包本身 |
| `skill/steam/` | Hermes 技能包（给 Agent 的说明） | 不需要——仅 Agent 用 |
| `tools/` | 登录/恢复辅助脚本与许可证核验；都是同一套代码的封装 | 不需要 |
| `patches/` | 第三方库的历史补丁，已被 `_compat.py` 取代 | 不需要 |
| `docs/` | 接口变更记录、开发文档、各版本发布说明 | 不需要 |
| `tests/` | 离线测试（107 项） | 不需要 |
| `scripts/`、`Makefile`、`.github/` | 发版工具与 CI | 不需要 |
| `pyproject.toml`、`uv.lock`、`MANIFEST.in`、`cliff.toml` | 打包与 CHANGELOG 生成 | 不需要 |

## Hermes 技能包

面向 Agent 的技能在 [`skill/steam/`](skill/steam)，作为独立产物
`steam-skill-<版本>.tar.gz` 发布。解压到 `~/.hermes/skills/steam/` 即可让 Hermes 获得这些
能力——技能文档里除了同样的命令，还写了 Agent 该遵守的规则：什么时候必须先问、发完要验证
什么、哪些坑已经踩过。

## 参与开发

```bash
pip install -e ".[dev]"
ruff check src tests tools
ruff format --check src tests tools
mypy src
PYTHONPATH=src python3 -m pytest -q
```

这四道门禁就是 CI 跑的内容。只读功能可以放心打真实接口；写操作——尤其是 `activate`——
**绝不**在主账号上运行。提交规范见 [CONTRIBUTING.md](CONTRIBUTING.md)，代码地图、区域机制
与已踩过的坑见 [docs/development.md](docs/development.md)。发布说明按版本放在
[docs/releases/](docs/releases)（格式见[其 README](docs/releases/README.md)）。

## 许可

MIT，见 [LICENSE](LICENSE)。
