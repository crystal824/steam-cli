# Steam CLI & Hermes Skill 开发文档

> 目标：为 Hermes Agent 提供一套可调用的 Steam 操作能力，让 Agent 能通过自然语言安全、可控地操作用户 Steam 账号。
> 核心交付物：
> 1. `steam-cli` —— 独立可执行 CLI（Python）
> 2. `steam` Skill —— Hermes 标准 Skill（`~/.hermes/skills/steam/`）
> 3. 安全凭证管理 + 渐进式披露文档

---

## 1. 项目愿景与边界

### 1.1 愿景
Agent 能听懂并执行类似指令：
- 「把用户发来的这串 CDK 激活到我的账号」
- 「帮我搜一下《黑神话：悟空》当前最低价并加愿望单」
- 「看看我库里哪些游戏最近 2 周没玩过」
- 「给《艾尔登法环》写一条推荐评价，语气轻松」
- 「查一下我好友列表里谁在玩同款游戏」
- 「把这款游戏从愿望单移到购物车并提醒我有折扣」
- 「生成一个我的好友快速邀请链接发给朋友」

### 1.2 能力边界（必须遵守）

| 操作类型 | 支持程度 | 说明 |
|---------|---------|------|
| 公共数据查询（搜索、价格、新闻、成就） | 完整 | Steam Web API + 第三方补充 |
| 用户库 / 愿望单 / 好友（读） | 完整 | 需用户 API Key 或登录会话 |
| CDK 激活 | 有限 | 无官方 API，仅通过网页会话模拟完成（非协议层）；用户首次登录并完成 Steam Guard/验证码验证后，由程序维持会话，后续可自动完成，无需重复登录 |
| 好友快速邀请链接（生成 / 刷新） | 有限 | 无官方 API，依赖登录会话调用官方好友页面完成 |
| 写评价 / 加愿望单 / 修改配置 | 有限 | 依赖登录会话 Cookie / 非官方端点 |
| 购买 / 交易 / 修改密码 | **禁止** | 安全红线，Skill 直接拒绝 |
| 启动游戏 | 支持 | `steam://` 协议或 SteamCMD |

**红线原则**：任何涉及真实金钱支付、账号绑定手机/邮箱修改的指令，以及任何可能被 Steam 判定为异常自动化行为（区别于 VAC 反作弊意义上的"作弊"，这里指账号/风控层面的异常操作模式，例如无节制的批量提交）的操作，Skill 必须拒绝或加以限速/确认，并明确告知用户。

---

## 2. 技术选型

| 层级 | 技术 | 理由 |
|------|------|------|
| 语言 | Python 3.11+ | Hermes 生态友好、Steam 库成熟 |
| 官方只读 API | `steam` (ValvePython) 的 `WebAPI` 模块 + dev API key | 官方文档化、稳定，不依赖 gevent |
| 登录与会话 | `steam` (ValvePython) 的 `WebAuth` 模块 + `httpx`（复用会话 cookie 发起请求）+ `beautifulsoup4`（解析必要的网页结构） | CDK 激活、愿望单增删、评价发布、好友邀请链接等功能已定为纯网页会话方案（不做协议层），因此只需要 `WebAuth` 处理登录与 Steam Guard/验证码，不需要引入 `SteamClient`／gevent，避免和 `httpx`/`typer` 的并发模型冲突 |
| CLI 框架 | `typer` + `rich` | 现代、好看、易写子命令 |
| 配置 / 凭证 | `keyring`（存储 session / refresh token 等高敏感数据）+ 本地文件（仅缓存低敏感数据，如 appid 索引） | 高敏感凭证交给操作系统级凭证库（Keychain / Credential Manager / Secret Service），不用自制的"加密 JSON"作为主存储方案 |
| Skill 标准 | agentskills.io / Hermes SKILL.md | 渐进式披露 |

> 说明：本项目不引入 `steam[client]`（gevent 依赖）。当前范围内所有写操作都通过网页会话完成，不需要协议层；若未来确有场景需要协议层能力，再单独评估 gevent 与现有模型的整合方案。

---

## 3. 目录结构（最终交付）

```
steam-cli/                          # 独立 CLI 仓库
├── pyproject.toml
├── MANIFEST.in
├── README.md
├── docs/
│   └── development.md              # 仓库级设计与开发文档
├── scripts/
│   └── build_skill.py               # 构建独立 Skill 归档
├── src/steam_cli/
│   ├── __init__.py
│   ├── main.py                     # typer 入口
│   ├── auth.py                     # 登录 / API Key / 会话管理（基于 WebAuth，不依赖 gevent）
│   ├── client.py                   # 统一封装（WebAPI + 会话请求，非 ValvePython 的 SteamClient 类）
│   ├── commands/
│   │   ├── library.py
│   │   ├── wishlist.py
│   │   ├── store.py
│   │   ├── friends.py              # 含好友列表、在玩查询、邀请链接生成/刷新
│   │   ├── review.py
│   │   ├── activate.py
│   │   ├── stats.py
│   │   └── launch.py
│   └── utils/
│       ├── price.py                # 价格 / 折扣 / 历史最低
│       └── steamdb.py              # 可选第三方价格数据源（见 §9）
├── skill/steam/                    # Skill 源文件，独立于 Python 包发布
└── tests/

~/.hermes/skills/steam/             # 解压 Skill 发布归档后的安装目录
├── SKILL.md                        # 主入口（触发描述 + 核心指令）
├── references/
│   ├── api-map.md                  # 命令 ↔ 能力对照表（含技术分层标注）
│   ├── auth.md                     # 如何获取 API Key / 登录
│   ├── safety.md                   # 安全与拒绝策略
│   └── examples.md                 # 自然语言 → CLI 映射示例
└── scripts/
    └── check_auth.py               # 快速检测凭证是否有效
```

---

## 4. CLI 命令设计（核心接口）

所有命令统一前缀：`steam <subcommand>`。每个小节标注了技术分层，便于评估稳定性与风险：
- **①公开 API**：官方 dev API key，文档化、稳定
- **②会话 API**：需要登录后的会话，接口本身被官方前端使用但不对第三方公开文档化
- **③网页会话模拟**：没有对应 Web API，靠登录会话直接调用网页/表单端点，是本项目中最不稳定、ToS 风险最高的一类

以下写操作均支持 `--dry-run`（只预览将要执行的动作，不实际提交）：`activate`、`wishlist add/remove`、`review post`、`friends invite-link --refresh`。

### 4.1 认证与状态 `[①/②]`
```bash
steam auth login                  # 交互式登录（支持 Steam Guard / 邮箱验证码 / 图形验证码）
steam auth status                 # 当前登录状态 / SteamID / API Key 是否有效
steam auth logout
steam auth set-key <web_api_key>  # 仅设置 Web API Key（只读场景）
steam auth refresh                # 刷新即将过期的会话
steam auth revoke-all             # 紧急撤销：清空本地保存的所有会话/凭证
steam doctor                      # 自检：探测当前依赖的非官方端点是否仍然可用
```

### 4.2 商店与搜索 `[①]`
```bash
steam search "黑神话" [--limit 10] [--type game|dlc|software]
steam app <appid|name>            # 详情（价格、折扣、标签、评测、系统需求）
steam price <appid|name>          # 当前价 + 历史最低（可接 IsThereAnyDeal，见 §9）
steam news <appid> [--count 5]
```

### 4.3 库与愿望单 `[①读 / ②写]`
```bash
steam library list [--recent] [--never-played] [--sort playtime|name|added]
steam library has <appid|name>
steam wishlist list
steam wishlist add <appid|name>       # ② 需要登录会话 access_token
steam wishlist remove <appid|name>    # ② 需要登录会话 access_token
steam wishlist on-sale                # 愿望单里正在打折的
```

### 4.4 CDK / 激活 `[③ 网页会话模拟，无官方 API]`
```bash
steam activate <cdk>              # 激活密钥；首次登录后自动复用会话完成，无需重复登录
steam activate --batch <file>     # 批量激活：默认整批预览 + 一次确认，逐条之间加入节奏间隔
```

### 4.5 评价 `[③ 网页会话模拟，无官方 API]`
```bash
steam review post <appid> --text "..." [--recommend true|false]
steam review list <appid> [--mine]
```

### 4.6 好友与社交 `[①/②读 · ③写]`
```bash
steam friends list [--online]
steam friends playing <appid>          # 正在玩某游戏的好友
steam friends recently-played
steam profile <steamid|vanity>
steam friends invite-link [--refresh]  # 获取当前好友快速邀请链接；--refresh 生成新链接（旧链接立即失效）
```

### 4.7 特色功能（建议优先实现）
```bash
# 1. 智能推荐
steam recommend [--based-on library|wishlist] [--limit 5]

# 2. 游玩统计看板
steam stats summary               # 总时长、最多玩、最近 2 周、从未玩过数量
steam stats game <appid>          # 单游戏成就进度 + 时长

# 3. 折扣雷达
steam radar [--wishlist] [--library-never-played]

# 4. 一键启动
steam launch <appid|name>         # steam://run/<appid>

# 5. 成就猎人助手
steam achievements <appid> [--missing] [--rarity]
```

---

## 5. Hermes Skill 设计要点

### 5.1 SKILL.md 前端描述（触发器）
```yaml
---
name: steam
description: Operate the user's Steam account via steam-cli — activate CD keys, search store, manage wishlist and library, post reviews, check friends and playtime, generate friend invite links, get price history and recommendations. Use when user mentions Steam, game activation, wishlist, library, Steam friends, or game reviews.
---
```

### 5.2 正文核心指令（给 Agent 的）
- 永远先执行 `steam auth status` 确认凭证。
- 所有写操作（activate / wishlist add / review post / friends invite-link --refresh）必须二次确认用户意图（除非用户明确说「直接执行」）；批量操作（activate --batch）需要先展示整批预览，一次性确认，而不是逐条单独打断用户。
- 登录会话对用户全程透明：用户仅需在首次使用时完成一次登录 + Steam Guard/验证码验证，此后由程序自动维持并按需刷新会话；后续 CDK 激活等操作在此基础上自动完成，不需要每次都重新走登录流程。
- 若登录或激活过程中触发验证码或其它异常登录挑战，必须把控制权交还用户，不自动重试、不试图程序化绕过。
- 涉及金钱、交易、账号安全的请求 → 立即拒绝并解释。
- 优先使用 CLI 子命令，不要自己拼 HTTP 请求。
- 输出用简洁表格或列表，方便用户阅读。
- 出错时优先返回结构化错误类型（格式错误 / 已激活 / 区域锁 / 网络问题 / 会话过期等），必要时附带原始 CLI 输出便于调试。

### 5.3 渐进式披露
- Level 0：只有 name + description
- Level 1：SKILL.md 正文（命令清单 + 安全规则）
- Level 2：`references/` 下详细 API 映射与示例

---

## 6. 认证与安全设计

1. **Web API Key**（只读，①层）
   用户去 https://steamcommunity.com/dev/apikey 申请，CLI 用 `keyring` 安全存储。

2. **登录会话**（②③层写操作共用同一套会话）
   - 使用 `steam` 库的 `steam.webauth.WebAuth` 处理登录（用户名密码 + Steam Guard / 邮箱验证码 / 图形验证码），不依赖 `SteamClient`/gevent
   - 登录成功后得到的会话（cookies）复用于 CDK 激活、愿望单增删、评价发布、好友邀请链接生成/刷新等所有网页会话类操作
   - 敏感的 session / refresh 信息通过 `keyring` 交给操作系统凭证库存储；本地文件只保存非敏感缓存
   - 支持 `steam auth refresh`（主动刷新即将过期的会话）与 `steam auth revoke-all`（怀疑凭证泄露时一键清空本地所有会话）
   - 本地维护操作审计日志（时间、命令、目标、结果），仅本地保存，不上传

3. **安全策略（Skill 强制）**
   - 禁止任何「购买」「支付」「修改邮箱/手机」「生成交易报价」指令
   - CDK 格式校验：标准为 3 段 × 5 字符（15 位，如 `XXXXX-XXXXX-XXXXX`，最常见情况），同时兼容 5 段 × 5 字符（25 位）的少数情况；两种格式都不匹配时提示用户核对来源，而不是直接报错拒绝
   - 激活或登录过程中若触发验证码 / 异常登录挑战，交还用户处理，不自动重试或尝试程序化绕过
   - 批量激活（`--batch`）默认要求执行前整批预览确认，逐条之间加入节奏间隔，不允许无间隔连续提交；完整记录每次激活的时间与结果
   - 评价内容长度与敏感词基础过滤
   - 所有写操作默认需要用户明确确认（可通过配置关闭，但批量场景不建议关闭）

---

## 7. 实现优先级（Vibe Coding 顺序）

### Phase 0 – 脚手架（1 天）
- [ ] `typer` 项目骨架 + `pyproject.toml`
- [ ] `steam auth status / set-key`
- [ ] 基础封装（`WebAPI` + `WebAuth`，不引入 gevent）

### Phase 1 – 只读核心（2–3 天）
- [ ] `search` / `app` / `price`
- [ ] `library list` / `has`
- [ ] `wishlist list`
- [ ] `friends list` / `playing`
- [ ] `stats summary`

### Phase 2 – 写操作（2 天，均为网页会话方案，复用同一套登录/会话逻辑）
- [ ] `wishlist add/remove`
- [ ] `activate`（含格式校验、批量预览确认、节奏控制）
- [ ] `review post`（需会话）
- [ ] `friends invite-link`（生成 / `--refresh`）

### Phase 3 – 特色与体验（2 天）
- [ ] 价格历史 / 折扣雷达
- [ ] 推荐引擎（简单协同过滤或标签匹配）
- [ ] `launch`
- [ ] 成就进度

### Phase 4 – Skill 与文档（1 天）
- [ ] 完整 SKILL.md + references
- [ ] 自然语言 → 命令映射示例
- [ ] 安全拒绝用例测试

**测试原则**：只读功能建议用 HTTP 录制/回放的方式跑 CI；写操作（尤其 `activate`）不在 CI 里跑真实调用，使用隔离的测试账号，并将"绝不用主账号做自动化测试"写入贡献指南。

---

## 8. 自然语言映射示例（给 Skill 用）

| 用户说法 | 推荐 CLI |
|---------|---------|
| 「激活这个 CDK：XXXXX-XXXXX-XXXXX」 | `steam activate XXXXX-...` |
| 「帮我搜黑神话悟空」 | `steam search "黑神话：悟空"` |
| 「把艾尔登法环加到愿望单」 | `steam wishlist add 1245620` |
| 「我库里有哪些游戏超过 100 小时」 | `steam library list --sort playtime` 后过滤 |
| 「给博德之门 3 写个好评」 | `steam review post 1086940 --recommend true --text "..."` |
| 「谁在玩双人成行」 | `steam friends playing 1426210` |
| 「愿望单里现在打折的有哪些」 | `steam wishlist on-sale` |
| 「推荐几款我可能喜欢的游戏」 | `steam recommend` |
| 「生成一个好友快速邀请链接」 | `steam friends invite-link` |
| 「给我一个新的邀请链接，旧的作废」 | `steam friends invite-link --refresh` |

---

## 9. 风险与已知限制

1. **CDK 激活 / 评价发布 / 愿望单写操作 / 好友邀请链接均无官方 API**
   这些功能没有对应的公开 Web API，只能靠登录会话调用官方网页背后的端点，本质上是在模拟人类操作，随时可能因页面改版而失效，也存在被 Steam 判定为异常自动化、导致账号被限制的风险（这和 VAC 反作弊封禁是两套不同机制——只有游戏内破坏公平性的修改才会触发 VAC；账号层面的异常操作走的是另一套风控）。

2. **Steam Guard / 二次验证**
   首次登录需要用户手动输入验证码，`WebAuth` 在遇到图形验证码 / 邮箱验证码 / 两步验证时会分别抛出对应异常，CLI 需要分别捕获并友好提示用户输入。

3. **速率限制**
   公共 API 有频率限制，CLI 需做简单缓存与退避；网页会话类操作更要主动限速，避免因短时间大量提交触发风控。

4. **第三方数据源**
   历史最低价建议优先接入 IsThereAnyDeal 面向开发者的官方 API；SteamDB 本身未对外提供正式 API，不建议直接爬取其站点。

5. **法律与 ToS**
   Skill 文档中明确声明：本工具仅供个人账号管理，禁止用于商业自动化或违反 Steam 订阅协议的行为；网页会话类功能属于业界公认的"灰色地带"，风险由使用者自行承担。

---

## 10. 验收标准（Definition of Done）

- [ ] `steam --help` 清晰展示所有子命令
- [ ] 在无 API Key 情况下，公共搜索与价格查询可用
- [ ] 登录后可成功列出库、愿望单、好友
- [ ] 首次登录完成验证后，后续激活 / 愿望单写操作 / 好友邀请链接生成无需重复登录
- [ ] CDK 激活流程完整（成功/失败都有明确反馈，格式校验同时兼容 3×5 与 5×5）
- [ ] 好友快速邀请链接可正常生成与刷新
- [ ] Hermes Skill 能被正确触发，并调用 CLI
- [ ] 安全红线测试全部通过（购买、交易等请求被拒绝）
- [ ] 依赖的非官方端点不可用时，CLI 给出清晰降级提示而非裸抛异常
- [ ] `steam doctor` 可正确探测各非官方端点的可用状态
- [ ] 文档与 `references/` 齐全，新人可独立上手

---

## 11. 后续可扩展方向

- MCP Server 封装（让其他 Agent 也能直接调）
- 多账号 Profile 支持
- Telegram / Discord 网关直接发 CDK 激活
- 与 Hermes 记忆系统联动（记住用户喜欢的游戏标签）
- 自动愿望单监控 + 折扣推送（配合 cron）

---

**文档版本**：v0.2
**变更摘要**：CDK 激活明确为纯网页会话方案（不做协议层），移除 gevent/SteamClient 依赖；新增好友快速邀请链接生成/刷新功能；移除家庭共享/借出状态查询；补充各命令的技术分层标注、CDK 格式校验修正、凭证存储与审计日志、批量操作节奏控制等安全细节。
**适用 Hermes**：v0.15+（agentskills.io 标准）
**维护建议**：把本文件放在 Skill 的 `references/dev-plan.md`，方便后续迭代时 Agent 自己查阅。
