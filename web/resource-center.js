import {localeTag} from "./locale.js";

const sections = {
  reports: ["市场报告", "Market reports"],
  updates: ["版本记录", "Product updates"],
  help: ["帮助中心", "Help center"],
  playbooks: ["运营手册", "Research playbooks"],
  tools: ["精选工具", "Featured tools"],
  partners: ["合作与支持", "Partnerships and support"],
};
const t = (zh,en) => localeTag() === "en-US" ? en : zh;
const esc = value => String(value ?? "").replace(/[&<>"']/g, c =>
  ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const route = (view, scope, extra={}) => "#"+view+"?"+new URLSearchParams({...scope,...extra});
const link = (label,url,attrs="") => '<a class="btn" '+attrs+' href="'+esc(url)+'">'+esc(label)+'</a>';
const paragraph = text => "<p>"+esc(text)+"</p>";
const status = '<p role="status"></p>';
const github = "https://github.com/laixi969-coder/tikflowso";
const number = value => value == null ? "—" : new Intl.NumberFormat(localeTag(), {maximumFractionDigits:2}).format(value);

export function downloadMarketReport(data) {
  const metrics = {gmv:t("商品成交额","Product GMV")+" ("+data.currency+")",sales:t("商品销量","Product units sold"),
    views:t("视频与直播观看次数","Video and live views"),creators:t("达人数量","Creators")};
  const covered = t("覆盖天数","Days covered");
  const lines = [t("tikflowso 市场报告","tikflowso market report"),[data.market,data.currency,data.start_date+" — "+data.date].join(" · "),
    t("数据来源","Source")+"  "+data.source+(data.source==="demo" ? " · "+t("合成演示数据","Synthetic demo data") : ""),
    t("品类","Category")+"  "+(data.category||t("全部品类","All categories")),""];
  for (const [key,label] of Object.entries(metrics)) {
    lines.push(label+"  "+number(data.metrics[key+"_exact"] ?? data.metrics[key])+"    "+covered+" "+data.coverage[key]+"/"+data.days);
  }
  if (data.trend.length) {
    lines.push("",[t("日期","Date"),metrics.gmv,metrics.sales,metrics.views].join("\t"));
    for (const day of data.trend) lines.push([day.date,number(day.gmv_exact ?? day.gmv),number(day.sales),number(day.views)].join("\t"));
  } else {
    lines.push("",t("所选期间没有快照。","No snapshots in this period."));
  }
  lines.push("",t("缺少观测值用 — 表示。成交额按来源及市场本币汇总。","Missing observations are shown as —. GMV uses the source records and the market currency."));
  const url = URL.createObjectURL(new Blob([lines.join("\n")+"\n"],{type:"text/plain;charset=utf-8"}));
  const a = document.createElement("a");
  a.href = url; a.download = "tikflowso-"+data.market+"-"+data.date+".txt";
  a.click(); setTimeout(()=>URL.revokeObjectURL(url),1000);
}

const faqs = [
  {question:["图表为空时先检查什么？","Why is my chart empty?"],answer:["确认市场、数据源和截止日，再在资源中心查看最新快照覆盖。导入后台分配给本工作区的来源后，点击「查看导入结果」即可进入对应市场。","Check the market, source and end date, then inspect the latest snapshot coverage. After importing workspace data, use the results link to open the matching market."],action:["查看快照与导入","Open snapshots and imports"],view:"resources",params:{section:"imports"}},
  {question:["为什么成交额环比显示缺失？","Why is period growth missing?"],answer:["先比较相邻两个等长窗口。任一窗口缺少观测日，或前一期成交额为零时，系统无法给出可比较的增长率。下载市场报告可以核对本期覆盖天数。","Growth compares two adjacent windows of equal length. An incomplete window or a zero prior GMV leaves growth unavailable. The market report includes the current coverage counts."],action:["查看市场报告","Open market reports"],view:"resources",params:{section:"reports"}},
  {question:["怎样导出当前筛选结果？","How do I export filtered results?"],answer:["在对象库应用市场、周期、品类和数值区间，点击「导出 CSV」。大榜单可用「后台导出」，然后在导出中心取回文件。导出行数受工作区套餐限制。","Apply a market, date window, category and metric ranges in a library. Download the CSV, or queue a larger export and retrieve it in the export center. Row allowances depend on the workspace plan."],action:["打开商品库","Open product library"],view:"products"},
  {question:["上线后在哪里填写模型 key？","Where do I add model keys after deployment?"],answer:["在账户页登录。通过部署命令显示的一次性绑定码取得平台管理员权限，打开管理员后台，选择供应商、模型并保存密钥，然后运行样例验收。","Sign in and claim platform administration with the one-time code from deployment. In the admin console, select the provider and model, save the key, then run the sample checks."],action:["打开管理员后台","Open admin console"],view:"admin"},
  {question:["在哪里配置浏览器扩展和 API？","Where do I find the extension and API setup?"],answer:["开放平台提供扩展 ZIP、Chrome 安装步骤、只读 API 密钥及 CLI 示例。创建 API 密钥后，将当次显示的值保存到自己的凭据管理器。","The API platform includes the extension ZIP, Chrome setup, read-only keys and CLI examples. Save a newly created key in your credential manager while it is visible."],action:["打开开放平台","Open API platform"],view:"api"},
];
const playbooks = [
  {title:["从周榜筛出可跟进的商品","Build a weekly product shortlist"],steps:[
    ["在热销榜按销量排序，选目标品类；用价格上、下限限定售价。","Sort the product board by sales, select a category and set a price range."],
    ["打开候选商品的标价走势，比较价格变化与销量发生的日期。","Open a candidate’s listed-price history and compare the timing with sales."],
    ["收藏候选，或在详情设置销量提醒。导出同一范围的 CSV 留作本次选品记录。","Save the candidate or set a sales alert. Export the same filtered CSV as a record of the selection."]],
    action:["打开热销商品榜","Open top-selling products"],view:"products",params:{sort:"sales"}},
  {title:["比较达人带货和涨粉","Evaluate creators for outreach"],steps:[
    ["在涨粉榜选定粉丝区间，查看净增粉和覆盖日期。","Start on the follower-growth board. Set a follower range and check growth and source dates."],
    ["打开达人详情，核对成交、关联商品和已记录的受众资料。","Open the profile to check sales, related products and any recorded audience data."],
    ["在合作联系簿登记已授权的邮箱或渠道，写明授权依据后再准备邀约。","Record permitted contact details and their usage rights in the contact book before drafting an invitation."]],
    action:["打开达人涨粉榜","Open follower-growth board"],view:"creators",params:{sort:"follower_growth"}},
  {title:["选择合适的内容研究工具","Choose a content research workflow"],steps:[
    ["寻找选题时，先在话题趋势核对销量、相关视频和采样覆盖。","For topic selection, examine units sold, related videos and sample coverage in trends."],
    ["已有授权素材时，用本机音轨转写获得带时间码的字幕；需要镜头顺序时，选视频拆解。","For licensed footage, use local transcription for timed captions or video breakdown for shot order."],
    ["需要投放或定价决策时，用费用计算器代入实际运费与佣金，核对盈亏平衡售价。","For pricing decisions, enter shipping and commission in the fee calculator and check the break-even price."]],
    action:["打开话题趋势","Open topic trends"],view:"trends",params:{group:"tag"}},
];
const featured = [
  ["费用计算器","Fee calculator","用售价、运费与佣金估算单件利润。","Estimate per-unit profit from price, shipping and commission.","tools",{tool:"calc"}],
  ["视频拆解","Video breakdown","上传授权素材，提取镜头时间点与画面。","Extract shot timings and frames from licensed footage.","tools",{tool:"video"}],
  ["本机音轨转写","Local transcription","从视频或音轨导出带时间码的字幕。","Export timed captions from a video or audio track.","tools",{tool:"transcribe"}],
  ["监控中心","Monitor center","为商品、视频或直播设置阈值提醒。","Set threshold alerts for products, videos or lives.","monitor",{}],
];

function sectionBody(section,scope,category) {
  const to = (label,view,params,attrs) => link(label,route(view,scope,params),attrs);
  if (section === "reports") {
    const dates = new Date(scope.date+"T00:00:00Z");
    dates.setUTCDate(dates.getUTCDate()-Number(scope.days)+1);
    const from = dates.toISOString().slice(0,10);
    return paragraph([scope.market,scope.source,from+" — "+scope.date,category||t("全部品类","All categories")].join(" · "))+
      paragraph(t("报告列出当前期间的成交额、销量、观看次数和达人数，并附各指标覆盖天数和逐日记录。","The report includes GMV, units sold, views and creators, with coverage counts and daily records for the selected window."))+
      '<div class="tf-inline">'+to(t("打开此期间的市场看板","Open dashboard for this period"),"dashboard",category?{category}:{})+
      '<button type="button" class="btn primary" data-resource-report>'+esc(t("下载市场报告","Download market report"))+'</button></div>'+status;
  }
  if (section === "updates") {
    return '<h3>1.4.0</h3>'+paragraph(t("管理员登录支持动态码及恢复码。工作区所有者可设置来源的模型授权、关闭通知、恢复最近删除的记录；大型榜单导出会进入后台。","Admin sign-in supports authenticator and recovery codes. Workspace owners can configure model access, mute alerts and recover recently removed items. Large ranking exports run in the background."))+'<h3>1.3.1</h3>'+paragraph(t("在市场中选择「中国大陆」即可查看抖音电商演示榜单。导入国内数据时填写市场代码 CN，成交额和标价使用人民币元。","Select Mainland China to explore the Douyin demo rankings. Use market code CN and enter GMV and prices in yuan when importing mainland data."))+
      '<h3>1.3</h3>'+paragraph(t("商品库支持三级品类、价格区间和常用筛选，商品详情可逐日查看标价。工作台新增分榜、市场报告和助手会话记录。","Research libraries now support category drill-down, metric ranges and saved filters. Product profiles show daily listed prices. The dashboard adds dedicated rankings, downloadable reports and assistant conversations."))+
      to(t("试用商品筛选","Try product filters"),"products")+to(t("打开市场报告","Open market reports"),"resources",{section:"reports"})+
      '<h3>1.2.0</h3>'+paragraph(t("部署包加入一键部署、升级前备份与恢复。SQLite 数据库和后台供应商配置独立持久保存，安装后可在管理员后台填写 key。","The deployment package introduced one-command installation, pre-upgrade backups and recovery. The SQLite database and provider settings persist independently of the application. Administrators can add keys after installation."))+
      link(t("查看 1.2.0 发布说明","Read 1.2.0 release notes"),github+"/releases/tag/v1.2.0");
  }
  if (section === "help") {
    return '<label>'+esc(t("搜索帮助","Search help"))+' <input type="search" data-help-search></label><div data-help-items>'+
      faqs.map(f=>'<details><summary>'+esc(t(...f.question))+'</summary>'+paragraph(t(...f.answer))+
        to(t(...f.action),f.view,f.params)+'</details>').join("")+'</div><p role="status" data-help-empty hidden>'+
        esc(t("没有匹配的问题。可尝试「导出」「模型」或「数据」。","No matching questions. Try “export”, “model” or “data”."))+'</p>';
  }
  if (section === "playbooks") {
    return playbooks.map((p,i)=>'<details'+(i===0?" open":"")+'><summary>'+esc(t(...p.title))+'</summary><ol class="tf-guide">'+
      p.steps.map(step=>'<li>'+esc(t(...step))+'</li>').join("")+'</ol>'+to(t(...p.action),p.view,p.params)+'</details>').join("");
  }
  if (section === "tools") {
    return featured.map(([zh,en,bodyZh,bodyEn,view,params])=>'<article class="tf-row"><div><b>'+esc(t(zh,en))+'</b>'+
      paragraph(t(bodyZh,bodyEn))+'</div>'+to(t("打开","Open")+" "+t(zh,en),view,params)+'</article>').join("");
  }
  if (section === "partners") {
    return '<h3>'+esc(t("推荐与结算","Referrals and settlements"))+'</h3>'+
      paragraph(t("登录后到合作中心领取推荐码，并查看自己的推荐记录、佣金和账期。","Sign in to get a referral code and review referred activity, commission and statements."))+
      to(t("打开合作中心","Open partnership center"),"tools",{tool:"partners"})+
      '<h3>'+esc(t("合作渠道","Creator contacts"))+'</h3>'+
      paragraph(t("在工作区联系簿中查找已获授权的达人渠道和使用范围。","Find authorized creator contact channels and their permitted use in the workspace contact book."))+
      to(t("打开合作联系簿","Open contact book"),"tools",{tool:"contacts"})+
      '<h3>'+esc(t("产品反馈","Product support"))+'</h3>'+
      paragraph(t("在项目的公开问题区搜索已有问题或提交反馈。提供复现步骤、版本与错误提示，公开内容请省略密钥和私有业务数据。","Search the public project issues or file feedback with the reproduction steps, version and error message. Omit credentials and private business data from a public report."))+
      link(t("打开项目问题区","Open project issues"),github+"/issues")+
      link(t("数据使用、隐私与安全问题报告","Data use, privacy and security reporting"),"/privacy.html");
  }
  return "";
}

class ResourceCenter extends HTMLElement {
  configure(context) {
    this.scope={market:context.market,source:context.source,date:context.date,days:context.days};
    this.context=context;
    this.section=Object.hasOwn(sections,context.params.section) || context.params.section==="support-inbox" ? context.params.section : "";
    this.category=context.params.category||"";
    this.render();
  }
  connectedCallback() { window.addEventListener("tikflowso:locale",this); }
  disconnectedCallback() { window.removeEventListener("tikflowso:locale",this); }
  handleEvent() { this.render(); }
  render() {
    if (!this.scope) return;
    const {scope,section,category}=this;
    const form=this.querySelector("[data-support-form]");
    const draft=form ? Object.fromEntries(new FormData(form)) : {};
    const support=section==="partners" || section==="support-inbox";
    const copy = t("资源中心","Resource center");
    const sectionLink = ([id,label])=>link(t(...label),route("resources",scope,{section:id,...(category?{category}:{})}),
      'data-resource-section="'+id+'"'+(id===section?' aria-current="page"':""));
    this.innerHTML='<section class="panel tf-panel"><h2>'+esc(copy)+'</h2><nav class="tf-inline" aria-label="'+esc(copy)+'">'+
      Object.entries(sections).map(sectionLink).join("")+'</nav>'+
      (section?'<article data-resource-article="'+section+'">'+(section==="support-inbox"?"":"<h3>"+esc(t(...sections[section]))+"</h3>")+
        (support?'<div data-customer-support></div>':"")+sectionBody(section,scope,category)+'</article>':"")+'</section>';
    if (support) renderSupport(this.querySelector('[data-customer-support]'),this.context,scope,draft);
    const search=this.querySelector("[data-help-search]");
    if (search) search.oninput=()=>{
      const query=search.value.trim().toLocaleLowerCase();
      const items=[...this.querySelectorAll("[data-help-items] details")];
      for (const item of items) item.hidden=!item.textContent.toLocaleLowerCase().includes(query);
      this.querySelector("[data-help-empty]").hidden=items.some(item=>!item.hidden);
    };
    const report=this.querySelector("[data-resource-report]");
    if (report) report.onclick=async()=>{
      const message=this.querySelector("[role=status]");
      report.disabled=true; message.textContent=t("正在生成报告…","Generating report…");
      try {
        const response=await fetch("/api/overview?"+new URLSearchParams({...scope,category}));
        const data=await response.json();
        if (!response.ok) throw Error(data.error||t("报告读取失败","Could not load report"));
        if (!report.isConnected) return;
        downloadMarketReport(data);
        message.textContent=t("报告已生成。","Report generated.");
      } catch (error) { message.textContent=error.message; }
      finally { report.disabled=false; }
    };
  }
}

customElements.define("tf-resource-center",ResourceCenter);

async function supportRequest(operator, params={}, data) {
  const url="/api/"+(operator?"admin/":"")+"support?"+new URLSearchParams(params);
  const response=await fetch(url,data===undefined?{}:{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(data)});
  const result=await response.json();
  if (!response.ok) throw Error(result.error || t("暂时无法读取工单。","Could not read support cases."));
  return result;
}
function caseNumber() {
  return Array.from(crypto.getRandomValues(new Uint8Array(16)),b=>b.toString(16).padStart(2,"0")).join("");
}
async function renderSupport(box,context,scope,draft) {
  const operator=context.params.section==="support-inbox";
  const section=operator?"support-inbox":"partners";
  const id=context.params.ticket || "";
  const page=Number(context.params.page)||1;
  const caseLink=(label,params)=>link(label,route("resources",scope,{section,...params}));
  const label=operator?t("支持工单收件箱","Support inbox"):t("联系本站支持","Contact this deployment’s support");
  const head="<h3>"+esc(label)+"</h3>";
  if (context.guest) {
    box.innerHTML=head+paragraph(t("登录后可提交问题，并在此查看部署管理员的回复。","Sign in to send a private support request and read replies from this deployment’s administrator."))+
      link(t("登录或注册","Sign in or register"),route("account",scope));
    return;
  }
  box.innerHTML=head+status;
  try {
    const data=await supportRequest(operator,id?{id}:{page});
    if (!box.isConnected) return;
    const inbox=caseLink(t("返回工单列表","Back to cases"),{});
    const state=r=>r.awaiting_reply?t("待管理员回复","Awaiting support"):t("管理员已回复","Support replied");
    const subject = '<label>'+esc(t("主题","Subject"))+'<input name="subject" required maxlength="120" data-case-subject></label>';
    const form=(newCase)=>'<form class="tf-form" data-support-form><input type="hidden" name="nonce" value="'+caseNumber()+'">'+(newCase?subject:"")+
      '<label>'+esc(newCase?t("问题描述","Describe the issue"):t("回复内容","Message"))+
      '<textarea name="message" required maxlength="4000" rows="4" data-case-message></textarea></label>'+
      '<button class="btn primary" type="submit">'+esc(newCase?t("提交工单","Submit request"):t("发送回复","Send reply"))+
      '</button>'+status+'</form>';
    if (id) {
      box.innerHTML=head+inbox+'<h3 data-source-text>#'+data.id+" · "+esc(data.subject)+'</h3>'+paragraph(state(data))+
        data.messages.map(m=>'<article class="tf-row"><div><b>'+esc(m.is_operator?t("部署管理员","Deployment support"):data.requester)+'</b>'+
          '<p data-source-text style="white-space:pre-wrap">'+esc(m.body)+'</p></div><time>'+
          esc(new Date(m.created*1000).toLocaleString(localeTag()))+'</time></article>').join("")+form(false);
    } else {
      box.innerHTML=head+(operator?"":paragraph(t("问题只对提交人和本站平台管理员可见。在此查看回复或补充情况。","Requests are private to the requester and this deployment’s platform administrators. Return here to read replies or add details."))+form(true))+
        "<h4>"+esc(operator?t("收到的工单","Received cases"):t("我的工单","My cases"))+"</h4>"+
        (data.items.length?data.items.map(r=>'<article class="tf-row">'+caseLink("#"+r.id+" · "+r.subject,{ticket:r.id})+
          '<span>'+esc(state(r))+'</span></article>').join(""):paragraph(t("暂无工单。","No support cases.")))+
        (page>1?caseLink(t("上一页","Previous page"),{page:page-1}):"")+
        (data.more?caseLink(t("下一页","Next page"),{page:page+1}):"");
    }
    const editor=box.querySelector("[data-support-form]");
    if (!editor) return;
    for (const [key,value] of Object.entries(draft||{})) if(editor.elements[key])editor.elements[key].value=value;
    editor.oninput=()=>{editor.elements.nonce.value=caseNumber();};
    editor.onsubmit=async event=>{
      event.preventDefault();
      const btn=editor.querySelector("button");
      if (btn.disabled) return;
      btn.disabled=true;
      try {
        const fields=Object.fromEntries(new FormData(editor));
        const saved=await supportRequest(operator,{}, {...fields,...(id?{id}:{})});
        if (!box.isConnected) return;
        if (!id) location.hash=route("resources",scope,{section,ticket:saved.id});
        else await renderSupport(box,context,scope);
      } catch (error) { editor.querySelector("[role=status]").textContent=error.message; }
      finally { btn.disabled=false; }
    };
  } catch (error) { if(box.isConnected)box.querySelector("[role=status]").textContent=error.message; }
}
