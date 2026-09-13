# steam-cli

[![CI](https://github.com/crystal824/steam-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/crystal824/steam-cli/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12-blue)](https://github.com/crystal824/steam-cli)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

**English** → [README.md](README.md)

给 [Hermes](https://agentskills.io) Agent 使用的 Steam 命令行工具：安全、可控。

它让 Agent 用自然语言操作 Steam 账号——搜商店、买前先看口碑、管理库和愿望单、激活 CDK、
发评测、查好友与时长——同时受一套严格的安全策略约束，绝不碰钱和账号安全设置。

## 能做什么

| 分类 | 命令 | 需要的凭据 |
|---|---|---|
| 登录 | `login` `status` `logout` `set-key` `refresh` `revoke-all` | — |
| 自检 | `doctor` | — |
| 商店 | `search` `app` `price` `news` `radar` `profile` | `news`/`radar` 需 Web API Key |
| 评测 | `review summary` `review list` `review mine` `review post` | `mine`/`post` 需登录态 |
| 游戏库 | `library list` `library has` | Web API Key |
| 愿望单 | `wishlist list` `add` `remove` `on-sale` | 读取需 Key，增删需登录态 |
| 卡密激活 | `activate <cdk> [--batch file]` | 登录态 + 二次确认 |
| 好友 | `friends list` `playing` `recently-played` `invite-link` | Key；`invite-link` 需登录态 |
| 统计 | `stats summary` `stats game` | Web API Key |
| 成就 | `achievements` | Key + 登录态 |
| 设置 | `config proxy …` `config region …` | — |
| 其它 | `launch` `recommend` | `recommend` 需 Key |

「Key」指 Steam Web API Key（只读，`steam set-key` 设置）；「登录态」指 `steam login` 建立的会话，
凡是要写数据的操作都需要它。用 `steam status` 看当前配了什么。商店查询（`search`、`app`、
`price`、`profile`、`review summary`、`review list`）**不需要任何凭据**。

**没有 `steam auth …` 这个子命令**——上游文档早于当前 CLI，上表所有命令都在顶层。

## 安装

从源码：

```bash
pip install .
steam --help
```

或直接装发布产物：到 [最新 Release](https://github.com/crystal824/steam-cli/releases/latest)
下载 `steam_cli-<版本>-py3-none-any.whl` 再 `pip install`。（**未发布到 PyPI**。）

需要 Python ≥ 3.11。依赖：`typer`、`rich`、`steam`（ValvePython）、`httpx`、`keyring`。

## 快速上手

```bash
# 商店查询不需要凭据
steam search "黑神话" --limit 5
steam app 2358720
steam price 2358720                       # 按你账号所在区域显示价格与货币

# 买前先看口碑（同样不需要凭据）
steam review summary 1144200

# 读取账号数据需要 Web API Key
steam set-key <你的Key>                    # https://steamcommunity.com/dev/apikey
steam library list --sort playtime
steam wishlist on-sale

# 任何写操作都需要登录态
steam login                               # Steam Guard / 验证码，只需一次
steam activate XXXXX-XXXXX-XXXXX
steam review post 2807960 --text "就冲能把墙拆了直接冲进去这点就值。"

# 可选：历史最低价需要 IsThereAnyDeal 开发者 Key
export STEAM_CLI_ITAD_KEY=<itad_key>
steam price 2358720
```

## 看懂一款游戏的评价现状

`steam review summary <appid|游戏名>` 用来回答「这游戏到底怎么样」——**包括你还没买的游戏**，
所以它能直接支撑购买建议：

- **评分档位**：同时给 Steam 英文档位和中文商店档位（`Overwhelmingly Positive`/好评如潮、
  `Mixed`/褒贬不一…），附好评率与评测总数
- **近期口碑**：Steam 已废弃 `day_range` 参数（传了也只会返回全时段数据），所以近期数据由客户端
  抽样最新评测得出，窗口内评测过多时会标注「未全量」
- **提炼素材**：最有帮助的好评与差评各若干条，附票数、语言、该玩家时长

```bash
steam review summary 1144200                     # 正负各 8 条；-s 12 可加量
steam review summary "Elden Ring" -L schinese    # 只看中文评测
steam review summary 1144200 --json              # 结构化输出，给 Agent 用
```

下面 `steam review summary 1144200 -s 1 --json` 的**真实输出**（截断；评测数会随新评测变化）：

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

人类可读输出的栏目名是中文（总评/近期/好评样本/差评样本），档位则写成
`中文档位 (英文档位)` 的形式；`--json` 输出与语言无关。

CLI 本身不做总结——它只把档位、数字和样本交出来，「好在哪/不好在哪」由 Agent 写。写的时候有两条
纪律：**报出你实际看到的数字**（档位、好评率、读了多少条样本），以及**面向中文用户要跑两遍**
（`-L all` 和 `-L schinese`）——两个口径可能相差整整一档（二之国系列和《严阵以待》都是这样）。

## 商店区域与语言

商店请求**跟随你的账号**：国家码从账号页的 `country_code` 读取（缓存一天），语言由国家推导
（cn→schinese，jp→japanese…）。中文账号拿到的是人民币价和中文商店文案，而不是过去写死的美元与英文。

```bash
steam status                                     # … Region: cn (schinese) — account
steam config region show                         # 当前用的是什么、来源在哪
steam config region set cn --lang schinese       # 钉住，不再跟随账号
steam config region clear                        # 恢复跟随账号
steam price 1144200 --cc us                      # 临时查其他区域价格
```

`STEAM_CLI_CC` / `STEAM_CLI_LANG` 可在单个 shell 内达到同样效果。

## 凭据

- `steam set-key <Key>`：存一个 Web API Key，用于只读的账号数据查询。
- `steam login`：走 Steam 当前登录流程（RSA 密钥交换、`IAuthenticationService`、手机 App 批准或
  Steam Guard 验证码），同时保存会话与**长期 refresh token**——之后重新认证不需要密码，也不需要 2FA。
- 凭据存进系统 keyring；没有 keyring 的环境（比如无头 NAS）回落到
  `~/.config/steam-cli/*.secret`，权限 `0600`。**账号密码从不保存**。
- `steam logout` 清除会话；`steam revoke-all` 抹掉全部本地凭据。
- 所有写操作都会追加到 `~/.config/steam-cli/audit.log`。

## 安全策略

- **直接拒绝**：购买、支付、交易、修改邮箱/手机、以及任何账号安全设置变更。
- **只有 `activate` 会二次确认**（它自己的确认提示，或 `--yes` 跳过）。其余写操作——
  `wishlist add/remove`、`review post`——**执行即生效、没有任何提示**，所以调用方必须先拿到用户的
  意图（发评测还要先拿到文案）。`--dry-run` 可以只预览请求而不发出。
- `review post` 发完会回读你的资料页确认（`--verify/--no-verify`，默认开启）——因为 Steam 返回
  `{"success": true}` 并不等于评论真的可见。
- 登录与激活遇到验证码 / Steam Guard / 2FA 一律交回用户，绝不自动重试或绕过。
- 发评测要求该产品至少有 5 分钟游玩记录；这是 Steam 的服务端规则，CLI 会把它原样抛成结构化的
  `review_rejected` 错误。

## 与 Steam 之间的三层通道

- **① 官方 Web API**——用 Key 访问：游戏库、好友、统计、新闻、成就。
- **② 会话 API**——需要登录态的读取：愿望单、你自己的评测。
- **③ Web 会话模拟**——没有公开 API，所以直接调用官方网页前端调用的接口：CDK 激活、愿望单增删、
  发布评测、好友邀请链接。最不稳定、也最涉及 ToS；接口随时可能变。

`steam doctor` 会逐个探测这三层依赖的接口。

## 与 2026 年 Steam 现状的兼容性

Valve 陆续下线和改写了本 CLI 早期依赖的一批接口。那些失败看起来都像「凭据不对」，实际是接口已死；
改了什么、症状长什么样、修在哪里，都记在
[docs/steam-endpoint-changes-2026.md](docs/steam-endpoint-changes-2026.md)。先知道这几条：

- **`steam review post` 曾经什么都发不出去却报成功**——它把请求发到了一个社区*页面*上，而且只检查
  HTTP 200。现在改用商店前端真正调用的 `friends/recommendgame`，并解析 JSON 响应：被拒绝会抛成
  结构化的 `review_rejected`，返回非 JSON 则抛 `network_error`，不再有假成功。
- **登录流程重写过**——单靠 `steam login` 会「成功」但实际上没认证任何东西。
  `tools/steam_modern_login.py` 实现当前流程，`tools/steam_remint_session.py` 用已存的 refresh token
  免密码免 2FA 重新铸造会话。
- **验证激活**用 `tools/check_licenses.py`：`GetOwnedGames` 不带获取时间戳，账号许可证页面上的
  日期与方式（Retail = 卡密）才是唯一凭据。
- `steam friends invite-link` 返回 **403**——Valve 改了该接口，本地无法修复。
- 安装的 `steam` 库有两处需要本地补丁，见 [`patches/`](patches/README.md)。
- 中文商店搜索找不到所有译名（社区索引会把「黑神话」解析成无关山寨，把「二之国」解析成空）。
  CJK 标题会改走简体中文商店搜索；连它也搜不到时，用英文原名或直接给 appid。

## 开发

```bash
pip install -e ".[dev]"     # 或 uv sync（uv.lock 锁定版本）
pre-commit install

ruff check src tests tools
ruff format --check src tests tools
mypy src
PYTHONPATH=src python3 -m pytest -q
```

这四道门禁就是 CI 跑的内容（v0.2.5 时 87 项测试全过）。`make test`、`make build`、
`make build-skill` 是常用命令的封装。

测试原则：只读功能可以放心打真实接口；写操作——尤其是 `activate`——**绝不**在主账号上运行。
用单独的测试账号，CI 里优先用 HTTP 录制/回放。

## 发版

```bash
python -m pip install build twine
python -m build --outdir dist/python
python scripts/build_skill.py --output-dir dist/skill
python -m twine check dist/python/*
```

每次发版产出两个产物：Python 包（只含 `src/` 运行时代码）和 Hermes 技能包
（`steam-skill-<版本>.tar.gz`）。发布流程：在 `docs/releases/<tag>.md` 写发布说明
（**中文在前、英文在后**），在 `pyproject.toml` 与 `uv.lock` **两处**都升版本号，推 `main`，
再推 tag。CI 会校验 tag 与 `pyproject.toml` 一致、构建两个产物、用你写的说明发布 Release，
并把重新生成的 `CHANGELOG.md` 提交回 `main`。细节见
[docs/releases/README.md](docs/releases/README.md) 与 [CONTRIBUTING.md](CONTRIBUTING.md)。

## Hermes 技能包

面向 Agent 的技能在 [`skill/steam/`](skill/steam)，作为独立产物
`steam-skill-<版本>.tar.gz` 发布。解压到 `~/.hermes/skills/steam/` 即可让 Hermes 获得这些能力——
技能文档里除了同样的命令，还写了 Agent 该遵守的规则：什么时候必须先问、发完要验证什么、哪些坑
已经踩过。

## 许可

MIT，见 [LICENSE](LICENSE)。
