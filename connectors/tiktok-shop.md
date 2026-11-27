# TikTok Shop 卖家商品日表现

## 离线验收

在仓库根目录运行。测试使用 Python 标准库、临时目录、临时 SQLite 和仅监听本机的模拟服务。

```sh
TIKFLOWSO_ENV_FILE=/dev/null python3 -m unittest -v test_tiktok_shop_connector
```

模拟服务执行授权码交换、续期、店铺匹配和两页商品查询。14 个合成统计日每天有两件商品记录，导入的 28 行与单独编写的每日行数、销量和 GMV 核对。另有缺页、币种错误、市场不符、未就绪、重放及回补用例。整个验收使用合成凭据，结果代表连接器契约。

## 授权与输入

连接器只读指定卖家已授权给应用的一个店铺。一个店铺、市场与数据来源对应一个独立交付目录。卖家授权、商户数据和市场排名属于不同的使用范围。本地使用案例不涉及跨店市场排名。[官方卖家授权说明](https://partner.tiktokshop.com/docv2/page/authorization-overview-202407) · [授权店铺接口](https://partner.tiktokshop.com/docv2/page/6507ead7b99d5302be949ba9)

如将来取得授权，将 Partner Center 发给该应用的授权链接、已登记的 HTTPS 回调地址、店铺 ID 与店铺登记时区填入私有配置文件。下列值为格式示例。选择私有目录时让运行账户有写入权限；feed 工作进程只需能读取交付目录。

```json
{
  "source": "ws-1-seller100",
  "market": "US",
  "shop_id": "100",
  "timezone": "America/New_York",
  "start_date": "2025-03-08",
  "directory": "/absolute/path/to/deliveries/seller100",
  "private_dir": "/absolute/path/to/private/seller100",
  "authorization_url": "https://services.us.tiktokshop.com/open/authorize?service_id=YOUR_SERVICE_ID",
  "redirect_uri": "https://your-registered-domain.example/callback",
  "lookback_days": 2
}
```

通过运行环境提供 `TIKTOK_SHOP_APP_KEY`、`TIKTOK_SHOP_APP_SECRET`。下面第一条命令输出一次性授权链接，卖家在官方页面同意后，受信任的回调处理方将完整回调 URL 通过 `TIKTOK_SHOP_CALLBACK_URL` 传给第二条命令。校验包括登记回调地址、十分钟有效的随机 state、卖家身份、授权店铺和市场。私有目录下的 `seller-tokens.json` 使用 0600 权限，保存访问令牌、刷新令牌与绝对过期时间。访问令牌即将过期时自动续期。应用需取得授权店铺查询和 TikTok Shop Analytics 的相应权限。[签名规则](https://partner.tiktokshop.com/docv2/page/sign-your-api-request)

```sh
python3 -m connectors.tiktok_shop --config /absolute/path/to/seller100.json authorize-url
python3 -m connectors.tiktok_shop --config /absolute/path/to/seller100.json authorize
```

## 每日增量与回补

第二条命令显式回补一个区间，包含两端日期。默认同步从配置的起始日开始，到店铺本地昨天，跳过已完成历史日并重查最近 `lookback_days` 个已完成日。服务尚未生成该日期的报表时，命令返回非零；先前完整发布的日期可供正常查询，未完成日期下次继续。请求遇到临时 HTTP 限流或服务错误会有限重试。回补和定时执行共用同一把目录锁。

```sh
python3 -m connectors.tiktok_shop --config /absolute/path/to/seller100.json sync
python3 -m connectors.tiktok_shop --config /absolute/path/to/seller100.json sync --since 2025-03-08 --until 2025-03-21
```

采集查询一次仅覆盖一个店铺当地统计日，使用 `start_date_ge=D` 和 `end_date_lt=D+1`、本币、全部商品状态，逐页核对 `next_page_token`、`total_count`、商品 ID 唯一性及 `latest_available_date`。授权接口核对店铺识别码与市场，时区由运营对照 Seller Center 填写。端点版本为 202605，字段取值如下。[官方商品表现接口](https://partner.tiktokshop.com/docv2/page/get-shop-product-performance-list-202605)

| 日快照 | 来源 |
|---|---|
| `id`、`name` | `products[].id` 的原始文本。指标接口提供商品 ID，榜单以该 ID 作为显示名 |
| `sales` | `total_performance.items_sold`，单位为件 |
| `gmv` | `total_performance.gmv.amount`，验证 `currency` 匹配登记市场，按精确本币金额导入 |
| `orders`、`refund_units` | 上游提供时取 `total_performance.orders`、`refunded_items` |
| `shop_id`、`market`、`date` | 经授权核对的店铺和市场、此次请求的店铺当地统计日 |

每个完整非空日原子发布一个 `YYYY-MM-DD.json` 商品数组，最大 32 MiB。确定无商品的日期仅记入隐藏检查点，避免制造零销量商品。现有 feed 按业务键写入修订和新增商品；若上游回补移除曾发布过的商品，采集器保留原日文件并报告日期和移除数量，由运营核对上游口径。零件销售且保留商品记录的正常日期按原样发布。保持交付目录专用，并将其连同隐藏检查点一起备份。

已配置店铺时，将本条添加到服务的 feeds 配置，并把来源、所属工作区 ID 与目录对应起来。数据文件交给现有 `feeds.py` 完成校验、幂等导入和来源可见性控制。独立真实商户报表是业务对账所需输入，离线验收不产生真实市场数据。

```json
[
  {"id": "seller100", "source": "ws-1-seller100", "owner": 1,
   "directory": "/absolute/path/to/deliveries/seller100", "interval_seconds": 900}
]
```
