# steam-cli 开发文档

面向贡献者与维护者。写的是**当前实现**（v0.2.5）的形态，不是最初的设计稿。

相关文档：
[README](../README.md)（用户向）·
[steam-endpoint-changes-2026](steam-endpoint-changes-2026.md)（Steam 侧发生过什么变化、怎么修的）·
[skill/steam/SKILL.md](../skill/steam/SKILL.md)（给 Agent 的规则）·
[CONTRIBUTING](../CONTRIBUTING.md)（提交规范与测试红线）

## 1. 定位与边界

一句话：让 Agent 用自然语言安全地操作 Steam 账号。

必须遵守的边界：

- **不碰**资金、支付、交易、账号安全设置——这类请求直接拒绝，也不许用"手写 HTTP"绕过。
- 写操作必须有用户的明确意图；CLI 自身只在 `activate` 上弹确认，其余靠调用方自律。
- 网页会话模拟层（见 §3 的 ③）只保证"尽量可用 + 失败可见"，接口随时可能变。

## 2. 代码结构

```
src/steam_cli/
├── main.py            # typer 入口：顶层命令注册 + SteamError 统一渲染
├── auth.py            # keyring/回退存储、会话、cookie_value()、审计日志
├── region.py          # 账号区域与语言解析（country_code → cc/lang，缓存 1 天）
├── client.py          # WebAPI 封装 + appid/名称解析（含 CJK 特例）
├── errors.py          # 结构化错误类型（main 据此输出 `code: message`）
├── commands/          # 一命令一模块，各自 register(app)
│   ├── store.py library.py wishlist.py friends.py stats.py
│   ├── activate.py review.py achievements.py recommend.py launch.py
│   └── config.py      # 代理 + 区域设置
└── utils/
    ├── doctor.py      # 端点探针（按区域发请求）
    └── price.py       # 现价 + ITAD 史低（country 跟随区域）
tests/                 # 全部离线：pytest + FakeResponse/FakeClient/monkeypatch
tools/                 # 命令面之外的一次性脚本（现代登录 / 重铸会话 / 许可证核验）
skill/steam/           # 随版本单独发布的 Hermes 技能包
patches/               # 第三方库（steam 1.4.4）补丁
```

## 3. 三层通道与代码映射

| 层 | 含义 | 代表命令 | 代码位置 |
|---|---|---|---|
| ① 官方 Web API | 用 Web API Key，只读、稳定 | `library` `friends` `stats` `news` `achievements` | `client.SteamClient` |
| ② 会话 API | 需要登录态 | 愿望单读取、`review mine` | `auth.require_session()` + `auth.cookie_value()` |
| ③ 网页会话模拟 | 无公开 API，直接调用官方前端调用的接口 | `activate`、愿望单增删、`review post`、`friends invite-link` | 各命令模块内部 |

新增功能前先判断它属于哪一层：③ 层必须**失败可诊断**（抛结构化错误），绝不允许"看起来成功"。

## 4. 区域与语言

- 唯一入口是 `region.py`。任何商店请求都走 `region.store_params({...})`，**不要写死 `cc`/`l`**。
- 解析顺序：显式覆盖（`STEAM_CLI_CC`/`STEAM_CLI_LANG`、`steam config region`）→ 账号页 `country_code`（缓存一天）→ `us`/`english`。
- **不要"省略 cc 让 Steam 自己判"**：实测不可靠——带会话时同一参数对不同 appid 会给出不同货币，加个 `filters` 又会变。
- 覆盖途径：单次调用（`--cc`/`--lang`）、单个 shell（环境变量）、长期（`steam config region set`）。

## 5. 新增一个命令

1. 在 `commands/` 加模块或给现有模块加 `@app.command()`；帮助文本写清**需要哪一档凭据**。
2. 错误一律抛 `errors.py` 的结构化类型，`main.py` 会渲染成 `code: message`。
3. 网络失败要能区分：`network_error` / `session_expired` / `api_key_missing` / `not_authenticated` / 业务拒绝（如 `review_rejected`）。
4. 写离线测试（`FakeResponse`/`FakeClient` 或 monkeypatch `httpx.Client`），**不打真实网络**。
5. 同步四处文档：`README.md`、`README.zh-CN.md`、`skill/steam/SKILL.md`（命令清单）、`skill/steam/references/api-map.md`（分层表）；涉及 Steam 接口变化再补 `docs/steam-endpoint-changes-2026.md`。
6. 四道门禁全绿后提交。

## 6. 测试与门禁

```bash
ruff check src tests tools
ruff format --check src tests tools
mypy src
PYTHONPATH=src python3 -m pytest -q
```

CI 跑的就是这四道（见 `.github/workflows/ci.yml`），另加产物构建校验。

- 测试全部离线可跑；只读功能可以手工对真实接口验证，但 CI 不发起真实请求。
- 写操作（尤其 `activate`）**绝不用主账号测**，用隔离账号；线上验证以单次人工执行为主。

## 7. 发版流程

1. 写发布说明 `docs/releases/<tag>.md`——**中文在前、英文在后**。
2. `pyproject.toml` 与 `uv.lock` **两处**版本号一起改。
3. 推 `main`，再打 tag（`vX.Y.Z`）并推送。
4. CI 校验 tag 与 `pyproject.toml` 一致 → 构建 wheel/sdist 与技能包 → 用发布说明发布 Release → 把重新生成的 `CHANGELOG.md` 提交回 `main`。

细节见 [docs/releases/README.md](releases/README.md)。

## 8. 维护手册：Steam 变了怎么办

- 症状分类与修法集中在 [steam-endpoint-changes-2026.md](steam-endpoint-changes-2026.md)：登录、CDK 激活、愿望单、评价、区域……
- 判断"接口死了还是参数错了"：先看响应的 `content-type`（返回 HTML 说明打到的是页面，不是接口）和 JSON 里的 `success` / `strError`。
- 结论要落进文档（带上实测命令），并在 `skill/steam/SKILL.md` 里留下给 Agent 的规则——否则下次还会踩。

### 两个已经踩过的通用陷阱（2026-09-13）

1. **做"是否登录"探针必须跟随跳转。** 商店对 `/account/` 的首次请求经常回 302 到自身（引导 cookie），
   只看 `allow_redirects=False` 的 200 会把**健康会话判成过期**——`steam status` 曾因此长期误报，
   还白白触发过一次"重新登录"。现统一走 `auth.probe_authed()`：跟随跳转 + 落地页不得是 `/login/`。
2. **凡是用 HTML 解析的页面都要显式 `?l=english`。** 重铸会话后 Steam 会按账号写入
   `Steam_Language`，个人页随之变成中文（推荐/发布于/小时/可见性），按英文正则写的解析器会静默
   解析成空字段（`steam review mine` 就中过一次）。评价的"推荐/不推荐"另用
   `icon_thumbsUp/Down` 图标判定，与语言无关。

## 9. 已知缺口

- `steam friends invite-link` 服务端 403，本地无法修复。
- `steam achievements` 打印成就的 API 名而非显示名（未 join `GetSchemaForGame`）。
- `review summary` 的人类可读输出标签目前固定中文（档位为「中文档位 (English band)」），`--json` 与语言无关。
