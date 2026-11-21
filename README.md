# tikflowso

面向 TikTok Shop 卖家、达人运营和内容策划的本机电商研究工作台。先阅读[产品需求与验收矩阵](docs/PRD.md)，再查阅[竞品公开证据](docs/对标记录.md)和[数据接入规范](docs/数据接入.md)。

## 一键部署、升级与恢复

在安装了 Python 3.11+、Docker Engine 和 Docker Compose v2.20+ 的 Linux 或 macOS 主机上，从项目目录运行。首次构建需要访问镜像仓库和 PyPI。以下命令使用同一个系统账户。

```sh
python3 deploy.py
```

命令会构建镜像，创建独立持久目录，启动服务，等待健康检查通过，再打印管理入口和一次性绑定码的文件位置。默认访问 [本机工作台](http://127.0.0.1:8765/)；五家供应商 key 初始均为空。部署使用镜像里的应用和独立的服务配置。开发目录的 `.env`、`.data` 和已有工作区都留在原处。

**上线域名**　在已有 HTTPS 反向代理的主机上，可直接以自己的真实域名执行下面的首装命令。代理上游为 `127.0.0.1:8765`，转发时保留浏览器的 Host。云端视频请求最大 48 MiB，启用时把代理请求体上限及读取超时调到能容纳该任务的大小。端口可由 `--port` 指定，部署脚本会记住。域名证书及 DNS 由托管方配置。

```sh
python3 deploy.py --public-url https://research.example.com
```

**持久化**　默认实例目录为 `~/.local/share/tikflowso`，也可在每条命令中用相同的 `--home` 指定位置。其 `data/` 挂载到容器的 `/app/.data`。数据库保存账户、平台角色、业务记录及导出文件；`tikflowso.providers.json` 保存后台模型、key 与提示词；`service.env` 保存部署域名及可选服务配置。后两份文件含明文凭据，使用 0600 权限。后台保存即时生效，手动修改 `service.env` 后执行升级命令生效。

**接入已有工作区**　迁移原来用 `server.py` 启动的实例时，先执行 `python3 manage.py backup-deployment --db .data/tikflowso.sqlite3 --out /绝对路径/迁移备份`，再用下方的 `restore` 命令指定新目录。既有后台配置会随包迁移；原来仅存于开发 `.env` 的字段按需写入新实例的 `data/service.env`。

| 操作 | 在项目目录执行 |
|---|---|
| 升级 | 取得新版代码后运行 `python3 deploy.py upgrade`。先构建，再暂停旧服务、生成升级前备份并启动新镜像；启动失败时，脚本用旧镜像和备份恢复已有容器实例 |
| 在线备份 | `python3 deploy.py backup`。命令打印新目录，位于实例的 `backups/` 下。将整个目录私密复制到备份主机 |
| 校验 | `python3 manage.py verify-deployment --dir /绝对路径/备份目录`。核对 SHA-256、SQLite 完整性、外键、表行数和分市场商品金额 |
| 独立恢复 | `python3 deploy.py restore /绝对路径/备份目录 --home /绝对路径/新实例 --port 8766`。可加 `--public-url` 更改对外地址；验证完成后再切换代理 |
| 暂停 | `python3 deploy.py stop`。数据保留，运行 `python3 deploy.py` 可重新启动 |

恢复包包含数据库、已保存的后台配置及已有的 `service.env`。初始化码仅在尚未绑定管理员的目标上重新生成。模型目录缓存可在后台重新同步；自备转写权重、授权供数文件、通知路由和汇率文件需另外迁移到配置指定的位置。容器内文件路径以 `/app/.data/` 开头。

首次上线后进入 `/#admin`，注册或登录，读取部署命令提示的绑定码文件，绑定平台管理员。保存所选平台的 key 和模型，再执行「测试连接」和「一键样例验收」。逐项结果和报告下载位于「运行记录」。[后台操作](#部署后填写云端密钥) · [发布验收](docs/PRD.md#10-逐项验收记录)

## 开发机启动

项目使用 Python 标准库、SQLite 和原生浏览器 JavaScript，无需安装 npm 或 pip 依赖。开发验收环境为 Python 3.15、SQLite 3.54 和 Chrome。

```sh
cd /Users/caiwenbin/tikflowso
python3 server.py
```

打开 [本地工作台](http://127.0.0.1:8765/)。首次启动会创建 `.data/tikflowso.sqlite3`，载入美国、英国、印度尼西亚和马来西亚共 75 天的合成样例。默认截止日为 2026-11-19。可用 `--db /absolute/path/store.sqlite3 --port 8766` 指定其他数据库和端口。

**五分钟体验**：在市场概览选择美国和近 7 天，从市场排行榜打开一个商品，检查日趋势及关联店铺，加入收藏和监控。进入监控中心设置销量阈值，再去商品榜按当前条件导出 CSV。页面标明来源；授权数据与演示数据分别查询。

右上角可切换中文与 English，浏览器记住语言偏好。切换覆盖研究界面、导入与修订记录、运营工具、后台配置及周报。来源提供的对象名、脚本、评价、用户编辑的提示词和模型输出保留原文。Chrome 扩展按浏览器语言显示中文或英文。

管理员后台的「研究周报」按 UTC 自周一统计至所选日期，分别显示演示和导入来源的活跃工作区、首次完成选品及跨日复访。分母是当周查看过商品榜或详情的工作区。首次完成按同一天、同一来源、市场、截止日及周期内先看榜单和详情、再收藏该商品或导出榜单计入；复访按至少两个 UTC 日期有研究行为计入。首次部署从开始记录之日累计，空分母显示「—」。

## 已实现的工作流

| 场景 | 入口与行为 |
| --- | --- |
| 选品、找店和达人合作 | 五类对象库、细分榜、按名称或 ID 搜索、历史趋势、关联对象、达人画像和授权合作联系簿 |
| 市场与内容研究 | 市场间同窗口本币比较、类目份额、价格带和店铺集中度；话题、音乐、关键词、脚本及代表内容；按窗口保存灵感、查看 28 日覆盖与七日预测 |
| 日常运营 | 工作区收藏、后台大榜单导出、阈值站内信和观测历史、费用与利润计算、授权素材与商品货盘 |
| 内容生产 | 当前市场数据问答；选题、推广脚本、标题、邀约、口播结构、图片去字、本机视频分镜、音轨转写和 SRT 字幕；可选视觉模型翻译图片并导出译图、对视频采样帧做拆解 |
| 团队与开放平台 | 本地注册登录、成员邀请和移除、席位和额度、密钥创建与撤销、版本化 REST、CLI、stdio MCP 和 Chrome 扩展 |
| 商业化 | 可配置的 Stripe 托管结账和客户门户、签名回调、推荐归因、订阅实收及退款冲正、月度佣金申请、跨币种核算、财务审批与争议调整 |

访客拥有独立会话，当前访客注册后会保留其收藏和监控。导入的资料以工作区为界，成员共用研究清单，个人只读密钥依身份访问获准的数据源。导入授权快照、维护合作联系方式、订阅管理与成员管理由工作区所有者操作。批量导出授权合作联系方式需要团队套餐。

## 架构与持久化

```text
浏览器 / Chrome 扩展 / CLI / MCP
              ↓
         同源 HTTP API
              ↓
   分析查询 · 工作区会话与配额 · 创作与计费
              ↓
        SQLite WAL 数据库
              ↑
  浏览器导入 / 本地 CSV、JSON / 授权 HTTPS / 监控推送
```

- `analytics.py` 负责日事实、来源、关系、市场比较和指标；`feeds.py` 处理有授权的文件或 HTTPS 交付。数据以来源、市场、类型、对象、统计日为业务键；实体属性与日指标一同保留，历史分析采用对应窗口的属性。
- `server.py` 提供 HTTP、来源访问校验、导出和后台轮询。每次请求使用独立数据库连接。常规查询、开放 API、问答和 CSV 复用相同的统计函数。
- `workspace.py` 管理 scrypt 密码散列、会话、成员、额度、收藏、监控及历史。令牌只以摘要存储。`contacts.py` 管理工作区授权联系簿。`stream.py` 接收指定来源的带时间戳观测值。
- `studio.py` 提供本地问答、文本模板和可选模型接入。`billing.py` 和 `partnerships.py` 分别负责计费事件、推荐归因与素材清单。
- `insights.py` 负责评价文本分析和趋势回测，`transcription.py` 调用本机音频工具。`export_jobs.py` 处理持久化导出队列，`notifications.py` 保存站内信及分渠道投递记录，`settlement.py` 维护争议、结算快照和审批记录。
- `web/` 包含 UI 及本地静态资源。`extension/` 可在 Chrome 开发者模式中以“加载已解压的扩展程序”安装。在 TikTok 页面点击扩展，即可打开 tikflowso 查询对应标识。
- `cli.py` 通过 HTTP 访问调用者可见的数据，支持包含趋势研究在内的七种分析接口。`python3 cli.py rankings --kind products` 执行榜单查询，`python3 cli.py mcp` 启动 stdio MCP；API 地址和密钥分别通过 `TIKFLOWSO_URL`、`TIKFLOWSO_API_KEY` 设置。

## 数据和服务配置

**授权日数据**：所有者登录后从「使用指南」下载样例并导入 CSV 或 JSON。后台文件交付通过 `TIKFLOWSO_FEEDS` 指向配置文件。Web 导入生成工作区私有来源。命令行导入和定时任务通过运营方指定的来源 ID 决定可见范围。数据表、快照样例、汇率文件、重试和数据修订的规则见[数据接入规范](docs/数据接入.md)。

**时点监控数据**：先在指定授权来源导入对象档案，再配置 `TIKFLOWSO_STREAM_SOURCE` 和 `TIKFLOWSO_STREAM_TOKEN`。向 `POST /api/stream` 提交 JSON，并在请求头传入 `Authorization: Bearer <token>`。来源由服务端配置固定。每次最多 5,000 个观测点，重复的对象、指标与时刻会覆盖。监控中心的“刷新监控记录”可读取最近 60 个观测点；日快照上的阈值与供应商提供的时点值分别显示。

```json
{"points":[{"market":"US","kind":"lives","id":"supplier-live-01","time":"2026-11-20T17:05:00Z","metric":"online_viewers","value":126}]}
```

支持在线人数（直播）、销量、GMV 和观看次数。供应商提供的观测值按原时点展示；累计计数不能直接跨时点求和。没有时点源时仍可跟踪授权日快照。

**云端视觉模型。** 图片翻译和视频镜头分析共用所选供应商的视觉模型和服务端密钥。图片工具生成文字框、原文、译文及 PNG；视频工具在部署主机切镜，把每个选中镜头的前后帧拼图发给模型，取得主体、动作、构图和起止时间。用户登录后提交素材才会调用云端推理。[图片翻译](http://127.0.0.1:8765/#tools?tool=image_translate) · [视频拆解](http://127.0.0.1:8765/#tools?tool=video)

**可选文本模型。** 本机数据库问答与文本模板继续独立工作。如需单独接入生成式文本服务，可配置 `TIKFLOWSO_MODEL_URL`（完整 Chat Completions 端点）、`TIKFLOWSO_MODEL` 和 `TIKFLOWSO_MODEL_KEY`。

**支付和联盟**：设置 `STRIPE_SECRET_KEY`、`STRIPE_WEBHOOK_SECRET`、`STRIPE_PRICE_PRO`、`STRIPE_PRICE_TEAM`、`TIKFLOWSO_PUBLIC_URL`，并启用商户的 Stripe 客户门户。在 Stripe 给 `/api/billing/webhook` 配置 `checkout.session.completed`、`customer.subscription.*`、`invoice.paid`、`charge.succeeded`、`charge.refunded`、`refund.updated`、`charge.dispute.created`、`charge.dispute.updated` 和 `charge.dispute.closed`。佣金比例由 `TIKFLOWSO_AFFILIATE_BPS` 配置，按基点计算，默认 0；受邀用户同意绑定时锁定比例。价格由运营方的循环收费价格决定，收款与测试交易在不同环境核对。实际打款由运营方执行。

### 部署后填写云端密钥

部署后，访问工作台网址的 `/#admin`。本机可直接打开[云端 API 管理后台](http://127.0.0.1:8765/#admin)。图片翻译和视频镜头分析使用云端推理，无需下载视觉模型。

1. 登录你要用于平台管理的工作台账户。首次启动会在数据库旁生成一次性初始化码，默认路径为 `.data/tikflowso.admin-setup.txt`。在后台输入后绑定当前账户，初始化码随即失效。其他工作区的所有者仍使用原有工作区权限。如需恢复管理权限，可在服务器执行 `python3 manage.py grant-admin --db .data/tikflowso.sqlite3 --email 已注册的邮箱`。
2. 在「供应商配置」选择已开通的平台，填写 key 并保存。可分别保存五家的 key，也可只填一家。点击「同步模型」获取该账号可见的最新目录，或点击「同步全部目录」分别刷新五家。目录支持选择视觉模型，也可手填模型 ID 或火山推理接入点。输入类型不明确的模型会标记为待测。
3. 保存模型后点「测试连接」，后台会发送一张英文样图，核对模型识别出的标题。再点「一键样例验收」，逐项查看英文图翻中文、中文图翻英文、空白图、四秒双镜头视频的结果。在「运行记录」可以重看失败原因和下载 JSON 报告。推理使用该标签页的账号和模型，按供应商规则计费。
4. 验收通过后，勾选「将此平台用于工作台视觉任务」并保存，即时切换线上图片和视频工具。需要文本生成时再勾选「同时用于数据问答与文本创作」；问答会向该平台提交问题和相关查询结果。默认可以使用本地数据库问答和创作模板。
5. 在「提示词」选择任务，可编辑、保存或恢复默认指令。九项任务涵盖图片翻译、镜头拆解、研究问答、选题、推广脚本、视频标题、商品标题、达人邀约和口播结构拆解。修改对后续模型请求生效。

后台只显示密钥是否已设置。输入框留空保留原值，「清除密钥」会停用该平台的现有密钥，包括环境变量提供的后备值。配置存于数据库旁的 `*.providers.json`，服务端以文件所有者可读写的权限（0600）保存，内容为明文。部署时将数据库目录挂到持久卷，通过 HTTPS 开放后台，并单独保管和备份此文件。初始默认平台为百炼北京地域。运维也可通过环境变量或 [.env.example](.env.example) 配置默认值；后台保存的覆盖项优先，页面保存后立即生效。

| 平台选择值 | API Base URL | 预填视觉模型 | 服务端密钥 |
|---|---|---|---|
| `bailian` | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen3.7-plus` | `DASHSCOPE_API_KEY` |
| `volcengine` | `https://ark.cn-beijing.volces.com/api/v3` | `doubao-seed-2-0-lite-260215` | `ARK_API_KEY` |
| `openrouter` | `https://openrouter.ai/api/v1` | `qwen/qwen3.7-plus` | `OPENROUTER_API_KEY` |
| `atlas` | `https://api.atlascloud.ai/v1` | `qwen/qwen3.7-plus` | `ATLASCLOUD_API_KEY` |
| `deepseek` | `https://api.deepseek.com` | `deepseek-flash` | `DEEPSEEK_API_KEY` |
| `custom` | `TIKFLOWSO_CUSTOM_BASE_URL` | `TIKFLOWSO_CUSTOM_MODEL` | `TIKFLOWSO_MODEL_KEY` |

供应商密钥独立，服务端只调用所选供应商。账号使用不同地域、业务空间专属域名或火山专属推理接入点时，可覆盖对应的 `TIKFLOWSO_<平台大写>_BASE_URL` 和 `_MODEL`。模型目录列出某个 ID 后，账号能否推理仍取决于权限、余额和服务状态。[百炼视觉模型](https://help.aliyun.com/zh/model-studio/text-generation-model/) · [火山方舟](https://docs.volcengine.com/docs/ark/image-process?lang=en) · [OpenRouter 模型目录](https://openrouter.ai/docs/api/api-reference/models/get-models) · [Atlas Cloud 协议](https://www.atlascloud.ai/docs/llm-protocols) · [DeepSeek 视觉接口](https://api-docs.deepseek.com/guides/vision/)

```sh
python3 connections.py sync --all --public-only
python3 connections.py sync --provider bailian
python3 connections.py models --provider openrouter --limit 10
python3 connections.py test --provider bailian
python3 connections.py check --external
node qa/vision_acceptance.cjs --live
```

第一条命令匿名刷新各家的目录，鉴权网关会标为待填密钥。第二条使用服务端配置刷新指定平台目录，第三条读取上次同步的列表；供应商提供发布日期时按其倒序展示。同步只更新目录，实际推理沿用选定模型。第四条向指定平台发送项目自带的英文样图并核对标题；最后一条使用所选账号实测两张译图和一个视频，均会产生该平台正常的推理用量。测试脚本使用临时工作区，无需登录生产账号。目录缓存在 `.data/vision/catalogs/`。

视频分析需部署主机可调用 FFmpeg 和 ffprobe，支持最多 48 MiB、10 分钟、4K；硬切镜头超过 12 个时等距抽取并显示实际分析数。macOS 可选执行 `mkdir -p .data/vision && swiftc -O native/vision_ocr.swift -o .data/vision/vision-ocr` 启用本机文字定位；其余部署直接由云端模型识别文字和文字框。两种方式均将用户提交的图片发送至所选平台。短暂动作及渐变转场可能漏检。音轨转写使用独立工具。

支付、授权供数、汇率和邮件短信使用模板中的其他字段。Stripe 价格 ID、Webhook 签名、域名、收件地址和供数授权由业务账号提供。连接检查会区分待配置、已验证及失败项。

### 无外部密钥的操作入口

- 在任一对象榜点击「后台导出」。在工具页可查看任务状态、失败原因及已完成的 CSV。离开页面后任务继续，文件保留 7 天，成功生成时扣除导出行数。界面对超过 1,000 行的结果自动使用队列。[后台导出](http://127.0.0.1:8765/#tools?tool=exports)
- 在「趋势研究」选择话题，查看每日覆盖、七日基线和回测误差。点击「收藏此灵感」会保存当时的市场、来源、截止日和周期。在「我的收藏」可按原条件重开。[趋势研究](http://127.0.0.1:8765/#trends)
- 在「视频拆解」上传视频可取得带起止时间的镜头分析。未启用视觉模型的工作台仍提供五帧预览。「本机音轨转写」接受不超过 48 MiB、10 分钟的音视频，生成文本和 SRT。部署镜像内置 FFmpeg 和 CPU 版 whisper.cpp 引擎。启用时将自备的多语 GGML 权重放入实例的 `data/models/whisper.bin`，刷新页面即可转写。原生开发环境也可使用 `ffmpeg`、`whisper-cli` 和 `.data/models/whisper.bin`，或用 `TIKFLOWSO_WHISPER_MODEL` 指定权重路径。[音轨转写](http://127.0.0.1:8765/#tools?tool=transcribe)
- 在开放平台页面下载扩展 ZIP，解压后从 Chrome 扩展管理页加载该目录。[扩展安装包](http://127.0.0.1:8765/downloads/tikflowso-extension.zip)

### 监控通知

为被监控对象设置指标阈值后，可在监控中心进入站内信，查看达到阈值的最新日快照。重复处理同一任务同一天的快照只记一次。没有渠道配置时使用站内信；有配置时由后台按工作区分渠道发送，失败自动重试，最多五次。[监控通知](http://127.0.0.1:8765/#tools?tool=alerts)

如需投递邮件和短信，将 `TIKFLOWSO_ALERT_ROUTES` 指向 JSON 配置文件。顶层键为数字工作区 ID 的字符串。以下为配置格式，地址和环境变量名供替换。邮件使用 SMTP，短信网关接受含 `to`、`text` 的 JSON POST 和 `Idempotency-Key` 请求头。按需只配置一个渠道。

```json
{
  "1": {
    "email": {"host":"smtp.example.com","port":587,"starttls":true,"from":"alerts@example.com","to":"ops@example.com","user":"mailer","password_env":"MAIL_PASSWORD"},
    "sms": {"url":"https://sms.example.com/send","to":"+12025550123","token_env":"SMS_TOKEN"}
  }
}
```

### 结算与素材

在「合作与货盘」选择环境与 UTC 月份。可直接按原币种对账，或指定本地汇率文件覆盖的日期进行折算。提交后，运营方在持有数据库的机器用下列命令查看快照及填写审批结论。若金额或汇率发生变化，重新提交后再审核。审批记录保留经办人与依据。素材条目支持上传最多 12 MiB 的授权附件，在工作区内下载，授权到期后停止提供附件。[合作与货盘](http://127.0.0.1:8765/#tools?tool=partners)

```sh
python3 manage.py settlements --db .data/tikflowso.sqlite3
python3 manage.py settlements --db .data/tikflowso.sqlite3 --id 1
python3 manage.py review --help
python3 manage.py dispute --help
```

对拒付可登记开启、败诉、胜诉及重新开启。签名争议事件可以先于收款到达，核账时按原交易匹配。测试及正式账本分开处理。支付机构侧的争议举证和实际打款需要业务方执行。[Stripe 争议对象](https://docs.stripe.com/api/disputes/object) · [事件目录](https://docs.stripe.com/api/events/types)

## 检查与恢复

```sh
python3 -m unittest discover -v
node qa/browser_acceptance.cjs
python3 qa/load_acceptance.py --seconds 30
python3 manage.py backup --db .data/tikflowso.sqlite3 --out /absolute/path/backup.sqlite3
python3 manage.py verify --db /absolute/path/backup.sqlite3
```

备份通过 SQLite 在线备份接口从一致读事务创建到新文件，并检查表完整性、外键、记录数量及分市场商品金额总和。可使用独立端口执行 `python3 server.py --db /absolute/path/backup.sqlite3 --port 8766` 试恢复。SQLite 备份包含账户、平台管理员、运行记录、授权资料和工作区数据。恢复供应商密钥、模型选择和自定义提示词时，还需将单独备份的 `*.providers.json` 恢复到目标数据库旁，使用相同文件名前缀并保留 0600 权限。

迁移整套后台配置时可以用下面的命令生成一个新的私有目录。目录中包含数据库、已存在的供应商配置和文件哈希清单。将其复制到恢复主机，先核对清单，再用**工作副本**启动。部署主机的环境变量、供数文件、素材处理工具及外部服务权限按目标主机配置。

```sh
python3 manage.py backup-deployment --db .data/tikflowso.sqlite3 --out /absolute/path/backup-directory
python3 manage.py verify-deployment --dir /absolute/path/backup-directory
cp -Rp /absolute/path/backup-directory /absolute/path/recovery-instance
python3 server.py --db /absolute/path/recovery-instance/tikflowso.sqlite3 --port 8766
```

逐项结果、复验环境和负载数字见 [PRD 第 10 节](docs/PRD.md#10-逐项验收记录)。正式上线还需要生产数据授权、供应商和模型实联、支付沙箱交易、对外 HTTPS 托管及生产负载和恢复演练。当前没有实际商业供数、支付订单或经供应商认证的 SLA。
