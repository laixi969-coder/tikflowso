// Translate only authored interface labels. Entity names, user text, and form values stay in their source language.
import extraCopy from './locale-extra.js';
const preference = 'tikflowso-locale';
let language = 'zh-CN';
try { if (localStorage.getItem(preference) === 'en-US') language = 'en-US'; } catch {}
export const localeTag = () => language;
export function displayDate(value) {
  if (!value) return '';
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return String(value);
  return new Intl.DateTimeFormat(language,{year:'numeric',month:'2-digit',day:'2-digit',timeZone:'UTC'})
    .format(new Date(value+'T00:00:00Z'));
}

// This catalog contains interface copy only. Source-provided labels are never looked up globally.
const catalog = {
  ...extraCopy,
  '本机抽取五个时间点的实际画面。':'Sample five timestamped frames on this device.',
  '已收藏的灵感':'Saved inspiration','收藏此灵感':'Save inspiration',
  '后台导出':'Background exports','查看任务进度，下载完整榜单。':'Track export jobs and download complete rankings.','刷新任务':'Refresh jobs','在任一榜单选择“后台导出”即可创建任务。':'Choose Background exports from a ranking to queue a file.',
  '文件保留 7 天；刷新或离开页面后任务继续。':'Files are kept for 7 days. Jobs continue after you leave the page.',
  '本机音轨转写':'Local audio transcription','识别音轨并导出带时间码的字幕。':'Transcribe a local media file and export timed captions.','语言':'Language','自动识别':'Detect automatically','转写音轨':'Transcribe','音频或视频':'Audio or video',
  '下载 SRT 字幕':'Download SRT captions','FFmpeg + Whisper · 支持含音轨的视频和音频，最大 48 MiB、10 分钟。':'FFmpeg + Whisper · Audio files and videos with sound. Maximum 48 MiB and 10 minutes.',
  '音轨转写待配置。请管理员检查语音识别引擎及本地 Whisper 权重。':'Transcription needs setup. Ask an administrator to check the speech engine and local Whisper weights.',
  '监控通知':'Monitor alerts','查看监控通知 →':'View alerts →','查看阈值提醒和投递状态。':'Read threshold alerts and delivery status.','标为已读':'Mark as read','达到监控阈值的最新快照将出现在这里。':'Recent snapshots that cross a monitor threshold appear here.',
  '趋势预测与采样覆盖':'Forecast and sample coverage','缺失日期':'Missing dates','预测日期':'Forecast date','预估销量':'Forecast units','预估 GMV':'Forecast GMV',
  '测试':'Test','正式':'Live','授权素材':'Licensed asset','商品货盘':'Product catalog','编辑':'Edit','删除':'Delete','付款审批':'Payment review','结算审批':'Settlement review',
  '提交当前账期审批':'Submit period for review','折算汇率日（留空按原币核账）':'FX date (leave blank for original currencies)','附件（素材，可选）':'Asset attachment (optional)','附件授权截止日':'Attachment license expiry',
  '下载扩展 ZIP':'Download extension ZIP','该账期没有已核实的支付或退款。':'No verified payments or refunds for this period.','清单中还没有条目。':'No items in the library yet.',
  '登录后可建立推荐关系、核对佣金，或与团队整理已获授权的素材及货盘。':'Sign in to manage referrals, reconcile commissions, and organize licensed assets and products.',
  '请输入有效的文本字段':'Enter a valid value.','邮箱或密码有误':'Incorrect email or password.','邮箱已被注册':'This email is already registered.',
  '请先注册或登录':'Sign up or sign in first.','密码至少需要 10 个字符':'Use at least 10 characters for your password.','邮箱格式无效':'Enter a valid email.',
  '此数据源属于其他工作区':'This source belongs to another workspace.','当前市场和时间范围内没有此对象':'This item has no observations for this market and period.',
  '账期内没有可核对的流水':'There are no ledger entries for this period.','此账期存在未结争议':'This period has an unresolved dispute.',
  '附件不能为空':'Select a nonempty attachment.','素材使用期限已过':'The asset license has expired.','文件超过大小上限':'The file exceeds the upload limit.',
  '无法解码音轨，请选择含声音的本地音频或视频':'Could not decode audio. Select a local media file with an audio track.',
  '单段音轨时长须大于零且不超过 10 分钟':'Audio duration must be greater than zero and at most ten minutes.',
  '需要工作区所有者权限':'Workspace owner access is required.','当前条件下没有数据':'No data for these filters.',
  '正向':'Positive','负向':'Negative','褒贬并存':'Mixed','未识别倾向':'Unclassified','最近 14 日记录不连续，暂缺预测。':'A forecast requires 14 consecutive observed days.',
  '已读':'Read','站内通知':'Inbox','排队中':'Queued','生成中':'Running','已生成':'Ready','失败':'Failed','授权依据与用途':'License and permitted use',

  '家居生活':'Home & living','数码电子':'Electronics','美妆个护':'Beauty & personal care','运动户外':'Sports & outdoors','服饰配件':'Fashion accessories','文具办公':'Office & stationery',
  '登记和查找已授权的达人合作渠道。':'Record and find licensed creator contact channels.',
  '文件支持 CSV 或 JSON 数组，单批最多 20,000 行。相同市场、对象和日期的快照将更新覆盖。':'Import a CSV file or a JSON array with up to 20,000 rows per batch. Matching market, entity and date keys update existing snapshots.',
  '成交额 / GMV':'Gross merchandise value (GMV)','选择市场内商品日成交额之和，使用市场本币。':'Sum of daily product GMV in the selected market, in local currency.',
  '对比两个相邻等长窗口。基数为零或覆盖不足时显示缺失。':'Compares consecutive periods of equal length. A missing baseline, zero baseline or incomplete coverage produces no percentage.',
  '视频与直播快照中记录的观看次数，未按观众去重。':'Views reported in video and livestream snapshots, including repeat views.',
  '演示来源使用合成日快照。切换数据源可以单独研究授权记录。':'The demo uses synthetic daily snapshots. Select a licensed source to research imported records.',
  '选择市场、来源与研究窗口。':'Select a market, data source and period.','打开商品、店铺或达人榜，按成交或增长排序。':'Open products, shops or creators and sort by sales or growth.',
  '点击对象名称查看趋势与关联内容。':'Open an item to see trends and related content.','收藏候选对象，或为商品、直播、视频开启监控。':'Save candidates or monitor a product, livestream or video.',
  '按当前筛选导出完整结果。':'Export all rows matching the current filters.',
  '使用 Bearer 密钥查询当前账户可访问的数据。HTTP 429 表示月度额度用尽，UTC 下月 1 日重置。':'Use a bearer key to query data available to this account. HTTP 429 indicates the monthly quota was reached. It resets on the first day of the next month (UTC).',
  '参数包括 source、market、date、days。榜单支持 kind、q、category、segment、sort、page、limit。详情传入 kind、id。':'Common parameters are source, market, date and days. Rankings accept kind, q, category, segment, sort, page and limit. Detail queries require kind and id.',
  '在本机设置 TIKFLOWSO_URL 与 TIKFLOWSO_API_KEY。命令行和 stdio MCP 共用只读接口。':'Set TIKFLOWSO_URL and TIKFLOWSO_API_KEY locally. The CLI and stdio MCP share the read-only API.',
  '在 Chrome 扩展程序页启用开发者模式，加载项目中的 extension 文件夹。打开 TikTok 对象页后，点击扩展可在本研究台搜索。':'Enable developer mode in Chrome extensions and load the project extension directory. Open a TikTok page and use the extension to search the workspace.',
  '哪个商品销量最高？':'Which products sell the most?','哪些达人涨粉最快？':'Which creators gain followers fastest?',
   '匹配方式':'Match mode','模糊匹配':'Contains','精确匹配':'Exact match','合作联系簿':'Partnership contacts',
  '合作中心':'Partnership center','登录或注册':'Sign in or register','复制链接':'Copy link','生成我的推荐码':'Create referral code','账期（UTC）':'Period (UTC)','支付环境':'Payment mode','查看账单':'View statement','类型':'Type','名称':'Name','来源链接':'Source link','授权依据或使用范围':'License or permitted use','关联商品 ID（可选）':'Related product ID (optional)','保存条目':'Save item','清空表单':'Clear form','推荐合作':'Referrals','佣金结算单':'Commission statement','素材与货盘':'Assets and catalog','团队清单':'Team list','导出清单 CSV':'Export list as CSV','访':'G',
  '工作空间':'Workspace' ,'工作区':'Workspace','电商数据':'Commerce data','市场研究':'Market research','工具与服务':'Tools & services',
  '市场概览':'Market overview','国家分析':'Markets','商品分析':'Products','店铺分析':'Shops','达人分析':'Creators','视频分析':'Videos','直播分析':'Livestreams',
  '内容趋势':'Content trends','品类分析':'Categories','创作灵感':'Inspiration','我的收藏':'Saved items','监控中心':'Monitoring','运营工具':'Operations tools',
  '开放 API':'Developer API','账户设置':'Account settings','使用指南':'User guide','数据助手':'Data assistant','搜索结果':'Search results','对象详情':'Details',
  '跳到内容':'Skip to content','展开导航':'Open navigation','关闭导航':'Close navigation','搜索工作台':'Search workspace','全站搜索':'Search workspace','搜索':'Search',
  '输入商品、店铺、达人或内容名称':'Enter a product, shop, creator or content name','关闭':'Close','切换数据来源':'Switch data source','数据来源':'Data source','演示数据':'Demo data',
  '访客工作区':'Guest workspace','本地工作空间':'Local workspace','个人工作空间':'Personal workspace','TikTok Shop 数据工作台':'TikTok Shop analytics workspace',
  '美国':'United States','英国':'United Kingdom','印度尼西亚':'Indonesia','马来西亚':'Malaysia','泰国':'Thailand','越南':'Vietnam','菲律宾':'Philippines','新加坡':'Singapore',
  '墨西哥':'Mexico','巴西':'Brazil','西班牙':'Spain','法国':'France','德国':'Germany','意大利':'Italy','日本':'Japan','爱尔兰':'Ireland','中国大陆':'Mainland China',
  '市场':'Market','数据截止日':'End date','统计周期':'Period','单日':'One day','全部市场':'All markets','近 7 天':'Last 7 days','近 14 天':'Last 14 days','近 30 天':'Last 30 days',
  '跟踪 TikTok Shop 的销售表现、品类变化与热门商品。':'Track TikTok Shop sales, category mix and leading products.',
  '跟踪抖音电商的销售表现、品类变化与热门商品。':'Track sales, category mix and leading products on Douyin.',
  '在相同时间窗口内比较各市场的销售规模、商品均价和活跃对象。':'Compare market sales, average prices and active entities over the same period.',
  '发现热销商品，比较成交表现与增长速度。':'Find bestsellers and compare their sales and growth.',
  '研究本地与跨境店铺的销售表现。':'Compare the sales performance of local and cross-border shops.',
  '按成交、观看与粉丝增长寻找合作达人。':'Find potential creator partners by sales, views and follower growth.',
  '比较带货短视频与图文内容的市场表现。':'Compare short videos and image posts by market performance.',
  '查看直播场次的观看与成交表现。':'Review livestream views and sales.',
  '按商品成交额研究品类结构，进入对应商品库。':'Explore category shares and open their product rankings.',
  '从话题、音乐和关键词中发现热门内容。':'Discover popular content through topics, music and keywords.',
  '从脚本和代表内容中寻找下一条创作方向。':'Explore script types and example content for your next creative brief.',
  '商品':'Products','店铺':'Shops','达人':'Creators','视频':'Videos','直播':'Livestreams','排名':'Rank','品类':'Category','对象':'Entity',
  '销量':'Units sold','成交额':'GMV','成交总额':'Total GMV','商品销量':'Units sold','内容观看':'Content views','观看次数':'Views','活跃达人':'Active creators','粉丝数':'Followers',
  '净增粉丝':'Net new followers','成交额增长率':'GMV growth','成交额环比':'GMV change','件':'units','次':'views','人':'creators','较上一周期':'vs. previous period',
  '市场成交走势':'Market performance','趋势指标':'Chart metric','商品 GMV':'Product GMV','品类成交占比':'GMV by category','查看品类分析':'View categories',
  'TOP 5 · 按成交额':'TOP 5 · BY GMV','市场排行榜':'Market rankings','完整榜单':'Full ranking','每日数据 ·':'Daily data ·',
  '全部商品':'All products','全部店铺':'All shops','全部达人':'All creators','全部视频':'All videos','全部直播':'All livestreams',
  '商品数据库':'Product database','店铺数据库':'Shop database','达人数据库':'Creator database','视频数据库':'Video database','直播数据库':'Livestream database',
  '商品信息':'Product','店铺信息':'Shop','达人信息':'Creator','视频信息':'Video','直播信息':'Livestream',
  '热推商品':'Promoted products','新品':'New products','本地店铺':'Local shops','跨境店铺':'Cross-border shops','S 店':'S shops',
  '新锐达人':'Rising creators','成熟达人':'Established creators','黑马达人':'Breakout creators','短视频':'Short videos','图文':'Image posts','直播场次':'Live sessions','回放场次':'Replays',
  '黑马达人要求两期快照完整，本期销量至少 20 件，前期有成交，成交额环比增长至少 15%，期末粉丝少于 20 万。':'Breakout creators have complete data for both periods, at least 20 units sold, prior sales, GMV growth of 15% or more, and fewer than 200,000 followers.',
  '搜索名称或 ID，回车查询':'Search by name or ID, then press Enter','全部品类':'All categories','排序方式':'Sort by','成交额从高到低':'Highest GMV','销量从高到低':'Most units sold',
  '增长率从高到低':'Fastest growth','观看次数从高到低':'Most views','粉丝数从高到低':'Most followers','净增粉从高到低':'Most new followers',
  '导出 CSV':'Export CSV','正在导出…':'Exporting…','榜单已导出':'Ranking exported','导出失败':'Export failed','上一页':'Previous page','下一页':'Next page',
  '更新日期':'Last updated','记录天数':'Days covered','所属分组':'Segment','价格':'Price','话题':'Topics','音乐':'Music','关键词':'Keywords','脚本':'Scripts',
  '对象档案':'Profile','对象 ID':'Entity ID','关联对象':'Related items','每日表现':'Daily performance','加入收藏':'Save item','加入监控':'Monitor','已加入收藏':'Saved','已加入监控':'Monitoring',
  '受众构成':'Audience','达人里程碑':'Creator milestones','商品评价':'Product reviews','直播流量':'Live traffic','市场比较':'Market comparison',
  '成交额（原币）':'GMV (local)','平均成交价':'Average price','覆盖天数':'Days covered','折算成交额 / 汇率日':'Converted GMV / FX date',
  '市场集中度':'Market concentration','商品数':'Products','前三商品 GMV 占比':'Top 3 product share','店铺数':'Shops','前三店铺 GMV 占比':'Top 3 shop share',
  '商品价格带':'Product price bands','占比':'Share','视频数':'Videos','话题排行':'Topic rankings','音乐排行':'Music rankings','关键词排行':'Keyword rankings','脚本排行':'Script rankings','品类排行':'Category rankings',
  '返回排行':'Back to rankings','输入名称或 ID':'Enter a name or ID','搜索范围':'Search scope','全部类型':'All types','全站搜索关键词':'Global search keywords','查看全部':'View all',
  '正在读取数据…':'Loading data…','当前条件下没有数据':'No data matches these filters','所选时间没有趋势记录':'No trend data for this period',
  '所选指标没有可用观测值':'No readings for this metric','当前窗口没有关联记录':'No related items in this period','当前时段没有可比较的市场记录':'No markets to compare in this period',
  '当前没有商品标价':'No product prices available','这个页面不存在':'Page not found','页面未找到':'Page not found','返回工作台':'Back to workspace','重新加载':'Reload','返回概览':'Back to overview',
  '选题灵感':'Video ideas','推广脚本':'Promotional script','视频标题':'Video title','商品标题':'Product title','达人邀约':'Creator outreach','文本脚本拆解':'Script analysis',
  '视频拆解':'Video analysis','图片翻译':'Image translation','图片去字':'Image text removal','费用计算器':'Fee calculator','合作与货盘':'Partnerships & catalog',
  '查询当前市场的成交、销量、观看与增长。':'Query current market sales, views and growth.','从商品或人群出发寻找拍摄角度。':'Find shooting angles for a product or audience.',
  '将商品卖点整理成分镜与时间段。':'Turn product benefits into a timed storyboard.','围绕选题撰写多版短视频标题。':'Draft multiple titles for a short video.',
  '根据提供的规格整理商品名称。':'Build a product title from its specifications.','草拟合作邀请与交付沟通邮件。':'Draft a creator partnership invitation.',
  '从现有口播文字提取结构。':'Extract structure from an existing transcript.','从本地视频抽取关键时间点并分析画面。':'Analyze frames from a local video.',
  '识别图中文字，输出原文和译文。':'Read and translate text in an image.','框选文字，用周围像素填充并下载。':'Select text to remove, then download the result.',
  '按实际费率估算单件利润与盈亏平衡售价。':'Estimate unit profit and break-even price.','整理素材、商品清单与推荐记录。':'Manage assets, product lists and referrals.',
  '登录':'Sign in','登录工作区':'Sign in','注册个人账户':'Create a personal account','显示名称':'Display name','邮箱':'Email','密码':'Password','推荐码（选填）':'Referral code (optional)',
  '我同意将此账户与填写的推荐码关联':'I agree to link this account to the referral code.','创建账户':'Create account','退出登录':'Sign out','本月额度':'Monthly usage',
  '开发者 API 调用':'Developer API calls','生成任务':'Generation jobs','今日导出行数':'Rows exported today','今日详情浏览':'Detail views today','并行监控上限':'Concurrent monitor limit',
  '订阅管理':'Subscription','套餐':'Plan','前往结账':'Checkout','管理账单与订阅':'Manage billing','团队成员':'Team members','移出团队':'Remove member','邀请成员邮箱':'Invitee email',
  '生成邀请码':'Create invite code','退出团队':'Leave team','团队邀请码':'Team invite code','加入团队':'Join team','访问密钥':'Access keys','前往账户':'Open account',
  '密钥用途':'Key label','例如：销售周报':'e.g. Weekly sales report','创建只读密钥':'Create read-only key','数据接口':'Data endpoints','CLI 与 MCP':'CLI and MCP','浏览器扩展':'Browser extension',
  '监控任务':'Monitors','收藏清单':'Saved items','浏览商品':'Browse products','移除':'Remove','监控中':'Monitoring','已结束':'Completed','等待快照':'Waiting for snapshots',
  '提醒阈值':'Alert threshold','仅记录':'Record only','保存阈值':'Save threshold','结束监控':'Stop monitoring','恢复监控':'Resume monitoring','已达阈值':'Threshold reached',
  '刷新监控记录':'Refresh readings','供应商时点观测（UTC）':'Provider observations (UTC)','售价':'Sale price','货品成本':'Cost of goods','履约运费':'Shipping',
  '其他固定费用':'Other fixed costs','平台费率 %':'Platform fee %','达人佣金率 %':'Creator commission %','计算利润':'Calculate profit','选择图片':'Choose image','撤销':'Undo',
  '下载 PNG':'Download PNG','下载译图 PNG':'Download translated PNG','本地文件':'Local file','目标语言':'Target language','口播文字':'Transcript',
  '研究问题或创作素材':'Question or creative brief','例如：当前市场哪些商品销量最高？':'e.g. Which products sell the most in this market?','填写与任务相关的素材…':'Enter your brief…',
  '查询数据':'Run query','生成结果':'Generate','← 所有工具':'← All tools','处理中…':'Processing…','导入授权日快照':'Import licensed snapshots','下载 JSON 示例':'Download JSON sample',
  '登录后导入私有数据':'Sign in to import private data','数据来源标识':'Source ID','日快照文件':'Daily snapshot file','验证并导入':'Validate and import',
  '数据口径':'Metric definitions','操作指南':'How to use','导入记录':'Import history','当前工作区暂无导入批次。':'No imports in this workspace.','查看导入的商品':'View imported products',
  '加载失败':'Loading failed','重试':'Retry','当前使用本地文本模板。':'Using local text templates.','答案使用所选市场和时间窗口。':'Results use the selected market and period.',
  '初始数值仅供试算，可按实际合同修改。':'Replace the example values with your actual costs and fees.',
  '在对象详情页点击「收藏」，即可在这里继续研究。':'Save items from a detail page to continue your research here.',
  '在商品、视频或直播详情页点击「监控」，即可在这里查看最新快照和历史记录。':'Monitor a product, video or livestream from its detail page to see readings here.',
  '请先登录，以便将密钥和月度用量关联到你的账户。':'Sign in to manage access keys and monthly usage.'
};

export function localMessage(value) { return language==='en-US' && typeof value==='string' ? translated(value) : value; }
const byText = new WeakMap();
const byAttr = new WeakMap();
function translated(value) {
  const trimmed=value.trim();
  let result=catalog[trimmed];
  if (!result) {
    const expressions=[
      [/^(\d+) 行$/,m=>m[1]+' rows'],
      [/^已导入 (\d+) 行、(\d+) 个对象。数据截止 ([\d-]+)。$/,m=>'Imported '+m[1]+' rows for '+m[2]+' items through '+m[3]+'.'],
      [/^第 (\d+) 行：(.*)$/,m=>'Row '+m[1]+': '+translated(m[2])],
      [/^(\w+) 的数值或精度无效$/,m=>'Invalid value or precision for '+m[1]],
      [/^缺少 (\w+)$/,m=>'Missing '+m[1]],
      [/^云端 HTTP (\d+) · (.+)$/,m=>'Cloud HTTP '+m[1]+' · '+(catalog[m[2]]||m[2])],
      [/^从已同步目录选择（(\d+)）$/,m=>'Select from synced catalog ('+m[1]+')'],
      [/^正在使用 · (待填密钥|已设密钥)$/,m=>'Active · '+catalog[m[1]]],
      [/^目录更新\s+(.+)$/,m=>'Catalog updated · '+(m[1]==='尚未同步'?'Never':m[1])],
      [/^(.+) · 输入类型待测$/,m=>m[1]+' · Input type unverified'],
      [/^(\d+) \/ (\d+) 个模型目录同步任务已提交。$/,m=>m[1]+' / '+m[2]+' catalog sync jobs submitted.'],
      [/^(.+) · 配置版本 (\d+)$/,m=>m[1]+' · Settings revision '+m[2]],
      [/^已刷新 (\d+) 个模型，当前模型(在目录中。|未列入目录。)$/,m=>m[1]+' models synced. Selected model '+(m[2].startsWith('在')?'listed.':'not listed.')],
      [/^样图首行识别结果\s+(.+)$/,m=>'Recognized first line: '+m[1]],
      [/^(英文商品图 → 中文|中文商品图 → 英文|空白图|双镜头视频) · (通过|失败)$/,m=>catalog[m[1]]+' · '+catalog[m[2]]],
      [/^合作联系簿 · (.+)$/,m=>'Contacts · '+m[1]],
      [/^云端视觉模型 · (.+) · (等待部署时填写密钥|提交后发送图片或镜头采样帧)$/,m=>'Cloud vision · '+m[1]+' · '+(m[2].startsWith('等待')?'Awaiting provider key':'Images or shot samples are sent on submission')],
      [/^云端视觉模型 · (.+)$/,m=>'Cloud vision · '+m[1]],
      [/^(.+) · (工作区所有者|团队成员)$/,m=>m[1]+' · '+catalog[m[2]]],
      [/^下载 CSV · (\d+) 行$/,m=>'Download CSV · '+m[1]+' rows'],
      [/^中英词典与否定规则 · (\d+) 条样本$/,m=>'Chinese/English lexicon and negation rules · '+m[1]+' reviews'],
      [/^已推荐注册 (\d+) 人。新绑定用户的佣金率为 ([0-9.]+)%。$/,m=>m[1]+' referred signups. Commission on new referrals: '+m[2]+'%.'],

      [/^查看 (.+)$/,m=>'View '+m[1]],[/^(\d+) 天$/,m=>m[1]+' days'],[/^成交额 ([A-Z]{3})$/,m=>'GMV '+m[1]],
      [/^共 ([\d,]+) 个(商品|达人|店铺|直播|视频)$/,m=>m[1]+' '+catalog[m[2]].toLowerCase()],
      [/^([\d,]+) 个市场$/,m=>m[1]+' markets'],[/^([\d,]+) 项$/,m=>m[1]+' entries'],
      [/^市场概览 · tikflowso$/,()=> 'Market overview · tikflowso'],
      [/^(监控任务|收藏清单) · (\d+)$/,m=>catalog[m[1]]+' · '+m[2]],
      [/^单件利润测算 · ([A-Z]{3})$/,m=>'Unit economics · '+m[1]],
      [/^每日数据 · ([A-Z]{3})$/,m=>'Daily data · '+m[1]],
      [/^([\d,]+) 款商品 · ([\d.,—]+%?) 成交占比$/,m=>m[1]+' products · '+m[2]+' of GMV'],
      [/^检索(商品|达人|店铺|直播|视频)$/,m=>'Search '+catalog[m[1]].toLowerCase()],
      [/^(成交额|销量|观看次数)逐日走势$/,m=>catalog[m[1]]+' by day'],
      [/^全部市场\s*·\s*(.+)$/,m=>'All markets · '+m[1]],
      [/^(话题|关键词|脚本|音乐) · 关联视频$/,m=>catalog[m[1]]+' · Related videos'],
      [/^历史记录（(\d+)）$/,m=>'History ('+m[1]+')']
    ];
    for (const [pattern,format] of expressions) {
      const match=trimmed.match(pattern);
      if (match) { result=format(match); break; }
    }
  }
  return result ? value.replace(trimmed,result) : value;
}

const controls=[
  '.ca-gate h2,.ca-gate p,.ca-gate label,.ca-gate output,.ca-platforms strong,.ca-platforms span,.ca-editor h2,.ca-editor h3,.ca-editor label,.ca-editor p,.ca-editor summary,.ca-editor figcaption,.ca-editor small,.ca-editor option,.ca-message,.ca-run strong,.ca-run [data-state],.ca-run p,.ca-case b,.ca-muted,.tf-inline label,.tf-monitor summary',
   '#identity[data-guest] .user-info b','#identity[data-guest] .user-info small','#identity[data-guest] .avatar','[data-field="match"] option','.skip','.crumb-root' ,'#crumb','#navigation .nav-label','#navigation .nav-item span','#search-button span',
  '.footer span','#search-dialog label','#search-dialog button','.page-heading h1','.page-heading p','.eyebrow',
  '.scope-fields option','.section-kicker','.kpi-label span','.kpi-label small','.kpi-comparison span:last-child',
  '.chart-foot span','.panel-head h2','.panel-head .text-link','.workspace-content .tabs button','.workspace-content .tabs a',
  '.records th','.count-label','.pagination>span','.rule-note','.detail-stats small','.fact-panel .fact>span','.price-bands span',
  '.tf-form label>span','.tf-dl dt','.tf-dl dd','.tf-guide li','[data-ui-label]','.related-card>span>small','.empty p','.loading','.text-link','[data-field="sort"] option','[data-field="chart"] option','[data-field="search-kind"] option',
  '[data-field="category"] option[value=""]','#source option[value="demo"]','.btn','button.primary','.tf-tools .tf-tool-name',
  '.tf-tools .tf-tool small','.tf-panel h2','.tf-form label','.tf-panel summary','.tf-reading>span','.tf-badge',
  '.tf-form select option','.tf-panel>label','.tf-result.bad','.tf-note','.tf-back','.profile-actions button','.tf-form [type="submit"]','.tf-panel a[href="#account"]',
  '.tf-panel button','#toast'
].join(',');

function renderLabel(node) {
  const current=node.nodeValue;
  const old=byText.get(node);
  const original=old && old.out===current ? old.original : current;
  const out=language==='en-US' ? translated(original) : original;
  if(out!==current) node.nodeValue=out;
  byText.set(node,{original,out});
}
const domainLabels='.category-chip,.category-legend a>span,[data-field="category"] option,.group-link';
function localizeElement(el) {
  if (!el.matches || el.closest('[data-source-text]')) return;
  const section = location.hash.slice(1).split('?')[0];
  const isMarketName = section==='markets' && el.matches('.group-link');
  const demoCategory = document.querySelector('#source')?.value==='demo' && el.matches(domainLabels) &&
    (!el.matches('.group-link') || section==='categories');
  if(el.matches(controls) || isMarketName || demoCategory) {
    const parent=el.parentElement;
    // A topic drill-down and an account profile both have data-supplied titles.
    const isUserTitle=(el.matches('.panel-head h2') && new URLSearchParams(location.hash.split('?')[1]).has('topic')) ||
      (el.matches('.tf-panel h2') && parent?.querySelector('.tf-big'));
    if(!isUserTitle) for(const node of el.childNodes) if(node.nodeType===3) renderLabel(node);
  }
  const tracked=byAttr.get(el)||{};
  for(const name of ['aria-label','title','placeholder','alt']) {
    if(!el.hasAttribute(name)) continue;
    const current=el.getAttribute(name);
    const old=tracked[name];
    const original=old && old.out===current ? old.original : current;
    const out=language==='en-US' ? translated(original) : original;
    if(out!==current) el.setAttribute(name,out);
    tracked[name]={original,out};
  }
  byAttr.set(el,tracked);
}
function apply(root) {
  if(root.nodeType===3) {if(root.parentElement) localizeElement(root.parentElement); return;}
  if(root.nodeType!==1 && root.nodeType!==9) return;
  if(root.nodeType===1) localizeElement(root);
  for(const el of root.querySelectorAll(controls+','+domainLabels+',[aria-label],[title],[placeholder],[alt]'))localizeElement(el);
  const gate=document.querySelector('[data-locale-toggle]');
  if(gate){
    const label=language==='en-US'?'中文':'EN';
    if(gate.textContent!==label) gate.textContent=label;
    gate.setAttribute('aria-label',language==='en-US'?'切换为中文':'Switch to English');
  }
}
function syncTitle(){
  const crumb=document.querySelector('#crumb')?.textContent;
  if(crumb)document.title=crumb+' · tikflowso';
}
function activate(){
  document.documentElement.lang=language;
  apply(document);
  syncTitle();
}
function start(){
  activate();
  const observer=new MutationObserver(changes=>{
    for(const change of changes){
      for(const node of change.addedNodes) apply(node);
      if(change.type==='characterData') apply(change.target);
    }
    syncTitle();
  });
  observer.observe(document.body,{childList:true,subtree:true,characterData:true});
  document.querySelector('[data-locale-toggle]')?.addEventListener('click',()=>{
    language=language==='zh-CN'?'en-US':'zh-CN';
    try{localStorage.setItem(preference,language);}catch{}
    activate();
    window.dispatchEvent(new Event('tikflowso:locale'));
  });
}
if(document.readyState==='loading') document.addEventListener('DOMContentLoaded',start,{once:true});
else start();
