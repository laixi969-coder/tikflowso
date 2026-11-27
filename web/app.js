import { translateText } from "./text-translation.js";
import { decisionForm, submitDecision } from "./research-decisions.js";
import { renderTools } from "./tools.js";
import { askOnBoard, boardAssistant } from "./board-chat.js";
import { downloadMarketReport } from "./resource-center.js";
import { localeTag, displayDate, localMessage } from "./locale.js";
import { adaptIdea, conditionLabels, referenceDraft, renderReferences } from "./filming.js";

const icons = {
  dashboard:
    '<rect x="3" y="3" width="7" height="8" rx="1.5"/><rect x="14" y="3" width="7" height="5" rx="1.5"/><rect x="3" y="15" width="7" height="6" rx="1.5"/><rect x="14" y="12" width="7" height="9" rx="1.5"/>',
  products:
    '<path d="m3.5 7 8.5-4 8.5 4v10L12 21l-8.5-4zM3.5 7l8.5 4 8.5-4M12 11v10M8 5l8 4"/>',
  shops:
    '<path d="M4 10v10h16V10M3 10l2-6h14l2 6M3 10a3 3 0 0 0 5 2 3 3 0 0 0 4 0 3 3 0 0 0 4 0 3 3 0 0 0 5-2M9 20v-6h6v6"/>',
  creators:
    '<circle cx="9" cy="8" r="3"/><path d="M3 20v-2a6 6 0 0 1 12 0v2M16 5a3 3 0 0 1 0 6m2 3a5 5 0 0 1 3 5"/>',
  videos:
    '<rect x="3" y="4" width="18" height="16" rx="3"/><path d="m10 8 6 4-6 4z"/>',
  lives:
    '<path d="M4 6a9 9 0 0 0 0 12m16-12a9 9 0 0 1 0 12M8 8a6 6 0 0 0 0 8m8-8a6 6 0 0 1 0 8"/><circle cx="12" cy="12" r="1.6"/>',
  trends: '<path d="M3 17l6-6 4 4 8-10m-6 0h6v6"/>',
  categories:
    '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/>',
  inspiration:
    '<path d="M8 16c0-2-3-3-3-7a7 7 0 1 1 14 0c0 4-3 5-3 7zM9 20h6"/>',
  tools:
    '<rect x="3" y="7" width="18" height="14" rx="2"/><path d="M8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2M3 12a23 23 0 0 0 18 0M10 13h4"/>',
  favorites: '<path d="M5 4h14v17l-7-4-7 4z"/>',
  monitor: '<path d="M3 6h18v12H3zM7 12h3l2-4 2 7 2-3h2M9 21h6"/>',
  api: '<path d="m8 6-6 6 6 6m8-12 6 6-6 6m-3-15-2 18"/>',
  resources:
    '<path d="M3 4h5c2 0 4 2 4 3 0-1 2-3 4-3h5v15h-5c-2 0-3 1-4 2-1-1-2-2-4-2H3zM12 7v13"/>',
  account:
    '<circle cx="12" cy="8" r="4"/><path d="M4 21v-2a8 8 0 0 1 16 0v2"/>',
  search: '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/>',
  agent:
    '<path d="m12 2 2.1 6.9L21 11l-6.9 2.2L12 20l-2.2-6.8L3 11l6.8-2.1zM20 16v5m-2.5-2.5h5"/>',
  arrow: '<path d="M4 12h15m-6-6 6 6-6 6"/>',
  chevron: '<path d="m8 10 4 4 4-4"/>',
  next: '<path d="m9 6 6 6-6 6"/>',
  back: '<path d="m14 6-6 6 6 6"/>',
  calendar:
    '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M7 3v4m10-4v4M3 10h18"/>',
  money:
    '<rect x="2.5" y="5" width="19" height="14" rx="2"/><circle cx="12" cy="12" r="3"/><path d="M6 12h.1m11.8 0h.1"/>',
  cart: '<path d="M2 4h3l3 12h10l3-9H6M9 20h.1M18 20h.1"/>',
  eye: '<path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7z"/><circle cx="12" cy="12" r="3"/>',
  download: '<path d="M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5"/>',
  globe:
    '<circle cx="12" cy="12" r="9"/><ellipse cx="12" cy="12" rx="4" ry="9"/><path d="M3 12h18"/>',
  menu: '<path d="M3 6h18M3 12h18M3 18h18"/>',
  detail: '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/>',
};
const icon = (name, size = 18) =>
  '<svg aria-hidden="true" width="' +
  size +
  '" height="' +
  size +
  '" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round">' +
  (icons[name] || (name==="plans" ? icons.account : "")) +
  "</svg>";
const esc = (v) =>
  String(v ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const kinds = {
  products: "商品",
  shops: "店铺",
  creators: "达人",
  videos: "视频",
  lives: "直播",
};
const names = {
  dashboard: "市场概览",
  markets: "国家分析",
  products: "商品分析",
  shops: "店铺分析",
  creators: "达人分析",
  videos: "视频分析",
  lives: "直播分析",
  trends: "内容趋势",
  categories: "品类分析",
  inspiration: "创作灵感",
  favorites: "我的收藏",
  monitor: "监控中心",
  tools: "运营工具",
  creative: "AI 创作工具",
  api: "开放 API",
  plans: "套餐与额度",
  account: "账户设置",
  admin: "管理员后台",
  resources: "使用指南",
  agent: "数据助手",
  search: "搜索结果",
  detail: "对象详情",
};
const navGroups = [
  ["工作空间", ["dashboard", "favorites", "monitor"]],
  ["电商数据", ["products", "shops", "creators", "videos", "lives"]],
  ["市场研究", ["markets", "categories", "trends", "inspiration"]],
  ["工具与服务", ["creative", "tools", "agent", "api", "resources", "plans"]],
];
const metricNames = {
  price: "商品标价",
  gmv: "成交额",
  sales: "销量",
  views: "观看次数",
  creators: "活跃达人",
  followers: "粉丝数",
  follower_growth: "净增粉丝",
  growth: "成交额增长率",
};
const segmentOptions = {
  products: { promoted: "热推商品", new: "新品" },
  shops: { local: "本地店铺", crossborder: "跨境店铺", s: "S 店" },
  creators: {
    rising: "新锐达人",
    established: "成熟达人",
    breakout: "黑马达人",
  },
  videos: { video: "短视频", image: "图文" },
  lives: { live: "直播场次", replay: "回放场次" },
};
const colorScale = [
  "#195f49",
  "#7b9b68",
  "#afe277",
  "#e8c46e",
  "#c2cbba",
  "#abbcc4",
];
const imageKeys = new Set([
  "serum",
  "headphones",
  "bottle",
  "lamp",
  "bag",
  "lip",
  "cup",
  "planner",
]);
const currencySymbol = { USD: "$", GBP: "£", IDR: "Rp", MYR: "RM", EUR: "€", CNY: "¥" };
const compact = (v, precision = 1) =>
  v == null
    ? "—"
    : new Intl.NumberFormat(localeTag(), {
        notation: "compact",
        maximumFractionDigits: precision,
      }).format(v);
const number = (v) =>
  v == null
    ? "—"
    : new Intl.NumberFormat(localeTag(), { maximumFractionDigits: 2 }).format(v);
const money = (v, c, short = true) =>
  v == null
    ? "—"
    : (currencySymbol[c] || c + " ") + (short ? compact(v, 2) : number(v));
const metricMoney = (row, key, currency, short = true) =>
  row[key + "_exact"] == null ? money(row[key], currency, short) : money(row[key + "_exact"], currency, false);
const dateText = displayDate;
const scope = { market: "US", days: 7, source: "demo", date: "" };
try {
  Object.assign(
    scope,
    JSON.parse(localStorage.getItem("tikflowso-scope") || "{}"),
  );
} catch {}
let meta = {},
  current,
  renderId = 0,
  chartMetric = "gmv",
  toastTimer;
const $ = (s) => document.querySelector(s);
function href(view, params = {}) {
  const q = new URLSearchParams(
    Object.entries(params).filter(
      ([, v]) => v !== null && v !== undefined && v !== "",
    ),
  );
  return "#" + view + (q.size ? "?" + q : "");
}
function route() {
  const [view = "dashboard", query = ""] = location.hash.slice(1).split("?");
  return {
    view: view || "dashboard",
    params: Object.fromEntries(new URLSearchParams(query)),
  };
}
function change(params) {
  const merged = { ...current.params, ...params };
  location.hash = href(current.view, merged);
}
function persist() {
  try {
    localStorage.setItem("tikflowso-scope", JSON.stringify(scope));
  } catch {}
}
function toast(message) {
  $("#toast").textContent = message;
  $("#toast").classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => $("#toast").classList.remove("show"), 2800);
}
async function api(path, params = {}, post = false) {
  const opts = post
    ? {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(params),
      }
    : {};
  const q = post
    ? ""
    : new URLSearchParams(
        Object.entries(params).filter(
          ([, v]) => v !== undefined && v !== null && v !== "",
        ),
      ).toString();
  const res = await fetch("/api/" + path + (q ? "?" + q : ""), opts),
    body = await res.json();
  if (!res.ok)
    throw Object.assign(new Error(
      typeof body.error === "string"
        ? body.error
        : body.message || "请求失败（" + res.status + "）",
    ),{status:res.status});
  return body;
}
function showEmpty(message = "当前条件下没有数据") {
  return (
    '<div class="empty">' +
    icon("search", 26) +
    "<p>" +
    esc(message) +
    "</p></div>"
  );
}
function selectOptions(options, value) {
  return Object.entries(options)
    .map(
      ([key, name]) =>
        '<option value="' +
        esc(key) +
        '" ' +
        (String(value) === key ? "selected" : "") +
        ">" +
        esc(name) +
        "</option>",
    )
    .join("");
}
function optionField(label, id, options, value) {
  return (
    '<label class="compact-select" title="' +
    esc(label) +
    '"><select aria-label="' +
    esc(label) +
    '" data-field="' +
    id +
    '">' +
    selectOptions(options, value) +
    "</select>" +
    icon("chevron", 14) +
    "</label>"
  );
}
function scopeParams() {
  return {
    market: scope.market,
    source: scope.source,
    days: scope.days,
    date: scope.date,
  };
}
function updateScope(field, value) {
  scope[field] = field === "days" ? Number(value) : value;
  if (field === "source" || field === "market") scope.date = "";
  persist();
  const p = { ...current.params };
  delete p.market;
  delete p.source;
  delete p.date;
  delete p.days;
  delete p.page;
  if (current.view === "dashboard" && (field === "market" || field === "source")) delete p.category;
  if (current.view === "inspiration" && (field === "market" || field === "source")) delete p.product_id;
  if (current.view === "detail" && (field === "source" || field === "market")) {
    location.hash = href(kinds[p.kind] ? p.kind : "dashboard");
    return;
  }
  if (href(current.view, p) !== location.hash && location.hash) {
    location.hash = href(current.view, p);
  } else render();
}
function scopeFields() {
  const markets = Object.fromEntries(
    (meta.markets || []).map((m) => [m.code, m.name]),
  );
  if (!markets[scope.market]) markets[scope.market]=scope.market;
  return (
    '<div class="scope-fields">' +
    (current?.view === "markets"
      ? ""
      : '<label class="market-control">' +
        icon("globe", 16) +
        '<select aria-label="市场" data-scope="market">' +
        selectOptions(markets, scope.market) +
        "</select>" +
        icon("chevron", 13) +
        "</label>") +
    '<div class="date-control"><label title="数据截止日">' +
    icon("calendar", 16) +
    '<input type="date" aria-label="数据截止日" data-scope="date" value="' +
    esc(scope.date || meta.date || "") +
    '"></label><span class="date-divider"></span><select aria-label="统计周期" data-scope="days">' +
    selectOptions(
      { [scope.days]:scope.days+" 天",1:"单日",7:"近 7 天",14:"近 14 天",30:"近 30 天",90:"90 天",365:"365 天" },
      scope.days,
    ) +
    "</select>" +
    icon("chevron", 13) +
    "</div></div>"
  );
}
function nav() {
  $("#navigation").innerHTML = navGroups
    .map(
      ([label, items]) =>
        '<div class="nav-group"><div class="nav-label">' +
        label +
        "</div>" +
        items
          .map(
            (k) =>
              '<a href="#' +
              k +
              '" class="nav-item" data-nav="' +
              k +
              '">' +
              icon(({markets:"globe",creative:"inspiration",plans:"money"})[k] || k, 17) +
              "<span>" +
              names[k] +
              "</span></a>",
          )
          .join("") +
        "</div>",
    )
    .join("");
  $("#menu-btn").innerHTML = icon("menu");
  $("#search-button").innerHTML =
    icon("search", 16) + "<span>搜索工作台</span><kbd>⌘ K</kbd>";
}
async function identity() {
  let u = { name: "访客工作区", guest: true };
  try {
    u = await api("me");
  } catch {}
  const adminLink=document.querySelector('#navigation [data-nav="admin"]');
  if(u.platform_admin&&!adminLink){
    $("#navigation").insertAdjacentHTML("beforeend",'<a href="#admin" class="nav-item" data-nav="admin">'+icon("account",17)+'<span>管理员后台</span></a>');
    if(current)markActive(current.view,current.params);
  }else if(!u.platform_admin&&adminLink)adminLink.remove();
  $("#identity").toggleAttribute("data-guest", Boolean(u.guest));
  $("#identity").innerHTML =
    '<span class="avatar">' +
    esc(u.guest ? "访" : Array.from(u.name || "用")[0]) +
    '</span><span class="user-info"><b>' +
    esc(u.guest ? "访客工作区" : u.name) +
    "</b><small>" +
    esc(u.guest ? "本地工作空间" : u.email || "个人工作空间") +
    "</small></span>" +
    icon("next", 14);
}
function sourceUI() {
  const src = Object.fromEntries(
    (meta.sources || []).map((s) => [s.id, s.name]),
  );
  $("#source").innerHTML = selectOptions(src, scope.source);
}
function heading(view) {
  const description = {
    markets: "在相同时间窗口内比较各市场的销售规模、商品均价和活跃对象。",
    dashboard: scope.market === "CN"
      ? "跟踪抖音电商的销售表现、品类变化与热门商品。"
      : "跟踪 TikTok Shop 的销售表现、品类变化与热门商品。",
    products: "发现热销商品，比较成交表现与增长速度。",
    shops: "研究本地与跨境店铺的销售表现。",
    creators: "按成交、观看与粉丝增长寻找合作达人。",
    videos: "比较带货短视频与图文内容的市场表现。",
    lives: "查看直播场次的观看与成交表现。",
    categories: "按商品成交额研究品类结构，进入对应商品库。",
    trends: "从话题、音乐和关键词中发现热门内容。",
    inspiration: "选一个想拍的商品，看看第一句怎么说、镜头怎么拍。",
  };
  const usesScope = !["account", "admin", "favorites", "monitor", "api", "resources", "plans"].includes(view);
  return (
    '<div class="page-heading"><div>' + (usesScope ? '<div class="eyebrow"><i></i>' +
    esc(
      (view === "markets"
        ? "全部市场"
        : scope.market + "  /  " + (meta.currency || "")) +
        "   ·   " +
        dateText(meta.date),
    ) +
    (meta.includes_estimates&&view!=="markets"?' · <span data-ui-label>含来源估算</span>':'')+
    "</div>" : "") + "<h1>" +
    esc(names[view] || "页面未找到") +
    "</h1>" +
    (description[view] ? "<p>" + description[view] + "</p>" : "") +
    "</div>" +
    (usesScope ? scopeFields() : "") +
    "</div>"
  );
}
function delta(n) {
  if (n == null) return '<span class="neutral">—</span>';
  if (n === 0) return '<span class="flat">0%</span>';
  return (
    '<span class="delta ' +
    (n < 0 ? "negative" : "") +
    '">' +
    (n < 0 ? "↘" : "↗") +
    " " +
    number(Math.abs(Number(n)).toFixed(1)) +
    "%</span>"
  );
}
function thumb(row) {
  const key = row.image_key;
  if (scope.source === "demo" && row.kind === "products" && imageKeys.has(key))
    return (
      '<span class="thumb"><img loading="lazy" alt="" src="/assets/' +
      key +
      '.webp"></span>'
    );
  const i =
    Math.abs([...String(row.id)].reduce((n, c) => n + c.charCodeAt(0), 0)) % 5;
  return (
    '<span class="thumb avatar-thumb tone-' +
    i +
    '">' +
    (row.kind === "creators"
      ? esc(
          String(row.name)
            .split(/\s+/)
            .map((s) => s[0])
            .slice(0, 2)
            .join(""),
        )
      : icon(row.kind, 20)) +
    "</span>"
  );
}
function detailHref(row) {
  return esc(
    href("detail", {
      kind: row.kind,
      id: row.id,
      ...scopeParams(),
      date: scope.date || meta.date,
    }),
  );
}
function translateName(row) {
  return row.kind === "products" ? '<button type="button" class="name-translation" data-ui-label data-translate-name="'+esc(row.name)+'">翻译名称</button>' : "";
}
function recordList(rows, currency, kind) {
  if (!rows?.length) return showEmpty();
  const selectedSort = current?.params.sort || "";
  const extra = ["followers", "follower_growth", "views"].includes(selectedSort)
    ? selectedSort
    : kind === "creators"
      ? "followers"
      : null;
  return (
    '<div class="table-wrap"><table class="records"><thead><tr><th>排名</th><th>' +
    esc(kinds[kind] || "对象") +
    '信息</th><th>品类</th><th class="num">成交额 <small>' +
    esc(currency) +
    '</small></th><th class="num">' +
    (extra ? metricNames[extra] : "销量") +
    '</th><th class="num">成交额环比</th><th></th></tr></thead><tbody>' +
    rows
      .map(
        (r, i) =>
          '<tr><td><span class="rank ' +
          (Number(r.rank || i + 1) <= 3 ? "top" : "") +
          '">' +
          String(r.rank || i + 1).padStart(2, "0") +
          '</span></td><td><a class="record" href="' +
          detailHref(r) +
          '">' +
          thumb(r) +
          "<span><b>" +
          esc(r.name) +
          "</b><small>" +
          esc(r.subtitle || r.id) +
          '</small></span></a>'+translateName(r)+'</td><td><span class="category-chip">' +
          esc(r.category || "—") +
          '</span></td><td class="num"><b>' +
          metricMoney(r, "gmv", currency) +
          (r.gmv_estimated?' <small data-ui-label>含来源估算</small>':'')+
          '</b></td><td class="num">' +
          number(extra ? r[extra] : r.sales) +
          '</td><td class="num">' +
          delta(r.growth) +
          '</td><td><a class="row-go" href="' +
          detailHref(r) +
          '" aria-label="查看 ' +
          esc(r.name) +
          '">' +
          icon("next", 15) +
          "</a></td></tr>",
      )
      .join("") +
    "</tbody></table></div>"
  );
}
function chart(data, metric, currency) {
  const observed = data.filter(point => point[metric] != null);
  if (!observed.length) return showEmpty("所选指标没有可用观测值");
  const small = window.matchMedia("(max-width:600px)").matches;
  const width = small ? 360 : 640, height = 151;
  const left = small ? 47 : 58, right = 15, top = 12, floor = height - 24;
  const oneDay = 86_400_000;
  const start = Date.parse(meta.start_date || data[0].date);
  const end = Date.parse(meta.date || data.at(-1).date);
  const values = observed.map(point => Number(point[metric]));
  const low = Math.min(...values), high = Math.max(...values);
  const targetStep = Math.max(high - low, Math.abs(high) * .07, 1) / 3;
  const magnitude = 10 ** Math.floor(Math.log10(targetStep));
  const step = [1, 2, 2.5, 5, 10].find(size => size * magnitude >= targetStep) * magnitude;
  const min = Math.max(0, Math.floor((low - step * .25) / step) * step);
  const max = Math.max(min + 3 * step, Math.ceil((high + step * .25) / step) * step);
  const xFor = time => left + (width-left-right) * (end === start ? .5 : (time-start)/(end-start));
  const yFor = value => top + (floor-top) * (1-(value-min)/(max-min));
  const fmt = value => ["gmv","price"].includes(metric) ? money(value, currency) : compact(value);
  const points = observed.map(point => ({
    x:xFor(Date.parse(point.date)), y:yFor(point[metric]), date:point.date, label:point[metric+"_exact"] == null ? fmt(point[metric]) : money(point[metric+"_exact"], currency, false)
  }));
  const segments = [];
  for (const point of points) {
    const previous = segments.at(-1)?.at(-1);
    if (!previous || Date.parse(point.date)-Date.parse(previous.date)>oneDay) segments.push([]);
    segments.at(-1).push(point);
  }
  const paths = segments.map(segment => {
    const first=segment[0], last=segment.at(-1);
    const path = segment.reduce((d,p,i) => {
      if (!i) return 'M'+p.x+' '+p.y;
      const before=segment[i-1], middle=(before.x+p.x)/2;
      return d+' C'+middle+' '+before.y+' '+middle+' '+p.y+' '+p.x+' '+p.y;
    }, '');
    return '<path d="'+path+' L'+last.x+' '+floor+' L'+first.x+' '+floor+' Z" fill="url(#fillplot)"/>'+
           '<path d="'+path+'" stroke="#c2f18c" stroke-width="3" fill="none"/>';
  }).join('');
  const horizontal = Array.from({length:Math.round((max-min)/step)+1},(_,i)=>{
    const value=max-i*step,y=yFor(value);
    return '<line x1="'+left+'" x2="'+(width-right)+'" y1="'+y+'" y2="'+y+'" stroke="currentColor" stroke-opacity=".18" stroke-dasharray="3 5"/>'+
           '<text x="'+(left-10)+'" y="'+(y+3)+'" text-anchor="end">'+esc(fmt(value))+'</text>';
  }).join('');
  const dayCount=Math.round((end-start)/oneDay)+1, divisions=Math.min(small?4:6,dayCount);
  const dates=Array.from({length:divisions},(_,i)=>{
    const day=start+Math.round(i*(dayCount-1)/Math.max(1,divisions-1))*oneDay;
    return '<text x="'+xFor(day)+'" y="'+(height-2)+'" text-anchor="middle">'+new Date(day).toISOString().slice(5,10).replace('-','/')+'</text>';
  }).join('');
  const marks=points.map(p=>'<g><circle cx="'+p.x+'" cy="'+p.y+'" r="'+(points.length<=14?3.2:1.4)+'" fill="#c7f599" stroke="#245845"/>'+
      '<circle class="chart-target" cx="'+p.x+'" cy="'+p.y+'" r="9"><title>'+esc(p.date+' · '+p.label)+'</title></circle></g>').join('');
  return '<svg class="plot" viewBox="0 0 '+width+' '+height+'" role="img" aria-label="'+esc(metricNames[metric])+'逐日走势"><defs><linearGradient id="fillplot" x1="0" x2="0" y1="0" y2="1"><stop offset="0%" stop-color="#c4f495" stop-opacity=".38"/><stop offset="100%" stop-color="#c4f495" stop-opacity=".015"/></linearGradient></defs>'+horizontal+paths+marks+dates+'</svg>';
}
function chartPanel(rows, currency, title = "市场成交走势", includePrice = false) {
  const options = {gmv:"GMV",sales:"销量",views:"观看次数"};
  if (includePrice) options.price=metricNames.price;
  const active = Object.hasOwn(options,chartMetric) ? chartMetric : "gmv";
  return (
    '<section class="chart-card"><div class="panel-head"><div><span class="section-kicker">每日数据 · ' +
    esc(currency) +
    "</span><h2>" +
    esc(title) +
    '</h2></div><div class="chart-metrics">' +
    optionField(
      "趋势指标",
      "chart",
      options,
      active,
    ) +
    "</div></div>" +
    chart(rows || [], active, currency) +
    '<div class="chart-foot"><span><i></i>' +
    esc(metricNames[active]) +
    "</span><span>" +
    esc(
      rows?.length
        ? dateText(rows[0].date) + " — " + dateText(rows.at(-1).date)
        : "",
    ) +
    "</span></div></section>"
  );
}
function categoryPanel(items) {
  const rows = (items || []).filter((r) => r.gmv > 0);
  return (
    '<section class="panel category-panel"><div class="panel-head"><div><span class="section-kicker">商品 GMV</span><h2>品类成交占比</h2></div><a class="iconbutton" href="#categories" aria-label="查看品类分析">' +
    icon("arrow", 17) +
    "</a></div>" +
    (rows.length
      ? '<div class="stacked">' +
        rows
          .map(
            (r, i) =>
              '<span style="width:' +
              Number(r.share) +
              "%;background:" +
              colorScale[i % 6] +
              '"></span>',
          )
          .join("") +
        '</div><div class="category-legend">' +
        rows
          .slice(0, 6)
          .map(
            (r, i) =>
              '<a href="' +
              esc(href("products", { category: r.name })) +
              '"><i style="background:' +
              colorScale[i % 6] +
              '"></i><span>' +
              esc(r.name) +
              "</span><b>" +
              number(Number(r.share).toFixed(1)) +
              "%</b></a>",
          )
          .join("") +
        "</div>"
      : showEmpty()) +
    "</section>"
  );
}
function kpi(metrics, changes, currency) {
  const keys = [
    ["gmv", "成交总额", "GMV", "money"],
    ["sales", "商品销量", "件", "cart"],
    ["views", "内容观看", "次", "eye"],
    ["creators", "活跃达人", "人", "creators"],
  ];
  return (
    '<div class="kpi-grid">' +
    keys
      .map(
        ([k, title, unit, img]) =>
          '<div class="kpi"><div class="kpi-label">' +
          icon(img, 17) +
          "<span>" +
          title +
          "</span><small>" +
          esc(k === "gmv" ? currency : unit) +
          '</small></div><div class="kpi-value">' +
          (k === "gmv" ? metricMoney(metrics,k,currency) : compact(metrics[k], 2)) +
          '</div><div class="kpi-comparison">' +
          delta(changes?.[k]) +
          "<span>较上一周期</span></div></div>",
      )
      .join("") +
    "</div>"
  );
}
function boardLink(view, params = {}) {
  return esc(href(view, {...scopeParams(), date:scope.date || meta.date, ...params}));
}
function resourceLinks() {
  const entries=[["市场报告","reports"],["版本更新","updates"],["帮助中心","help"],["运营指南","playbooks"],["推荐与佣金","partners"]];
  $("#resource-links").innerHTML=entries.map(([label,section])=>'<a data-ui-label href="'+boardLink("resources",{section})+'">'+esc(localMessage(label))+'</a>').join("")+
    '<a data-ui-label href="'+boardLink("tools",{tool:"alerts"})+'">'+esc(localMessage("监控通知"))+'</a>';
}
function boardDiscovery() {
  const groups = [
    ["creators","找达人",[["带货达人","creators",{sort:"sales"}],["涨粉达人","creators",{sort:"follower_growth"}],["黑马达人","creators",{segment:"breakout",sort:"growth"}]]],
    ["products","找商品",[["热销商品","products",{sort:"sales"}],["热推商品","products",{segment:"promoted"}],["品类分析","categories",{}]]],
    ["shops","找店铺",[["本地店铺","shops",{segment:"local",sort:"sales"}],["跨境店铺","shops",{segment:"crossborder",sort:"sales"}],["S 店","shops",{segment:"s"}]]],
    ["videos","找内容",[["带货视频","videos",{sort:"sales"}],["图文","videos",{segment:"image",sort:"sales"}],["视频拆解","tools",{tool:"video"}]]]
  ];
  return '<div class="board-entry">'+searchForm("", "creators", "broad")+
    boardAssistant({...scopeParams(),date:scope.date || meta.date},{esc,href,t:localMessage,icon})+'</div>'+
    '<div class="board-shortcuts">'+groups.map(([kind,title,links])=>
      '<section class="panel"><a class="board-group" href="'+boardLink(kind)+'">'+icon(kind,18)+'<span data-ui-label>'+title+'</span></a>'+
      links.map(([label,view,params])=>'<a class="board-shortcut" data-ui-label href="'+boardLink(view,params)+'">'+label+'</a>').join("")+
      '</section>').join("")+'</div>';
}
function boardRanking(board, currency) {
  const growth = board.sort === "follower_growth";
  const list = boardLink(board.kind, {sort:board.sort,segment:board.segment});
  return '<section class="panel board-ranking"><div class="panel-head"><h2>'+esc(board.title)+
    '</h2><div class="tf-inline">'+(board.kind==="products"&&board.items.length?'<button class="btn" type="button" data-translate-board>翻译商品名称</button>':'')+
    '<a class="text-link" href="'+list+'">完整榜单 '+icon("arrow",14)+'</a></div></div>'+
    (board.items.length ? '<div class="table-wrap"><table class="records"><thead><tr><th>排名</th><th>'+kinds[board.kind]+
    '</th><th class="num">'+(growth?"净增粉丝":"销量")+'</th><th class="num">'+(growth?"粉丝数":"GMV · "+esc(currency))+'</th></tr></thead><tbody>'+
    board.items.map(r=>'<tr><td><span class="rank'+(r.rank<=3?' top':'')+'">'+r.rank+'</span></td><td><a class="record" href="'+detailHref(r)+'">'+
      thumb(r)+'<b>'+esc(r.name)+'</b></a>'+translateName(r)+'</td><td class="num">'+number(growth?r.follower_growth:r.sales)+'</td><td class="num">'+
      (growth?number(r.followers):metricMoney(r,"gmv",currency)+(r.gmv_estimated?' <small data-ui-label>含来源估算</small>':''))+'</td></tr>').join("")+
    '</tbody></table></div>':showEmpty())+'</section>';
}
const liveTime = value => value ? new Date(value).toISOString().slice(0,19).replace("T"," ") : "—";
function onlineViewers(room) {
  const t = key=>esc(localMessage(key));
  const series = room.series;
  if (!series.length) return '<p class="muted">'+t("没有在线人数观测")+'</p>';
  const start = Date.parse(series[0].time), span = Date.parse(series.at(-1).time)-start;
  const max = Math.max(1,...series.map(point=>point.value));
  const points = series.map(point=>({...point,x:46+(span ? (Date.parse(point.time)-start)/span : .5)*330,y:92-point.value/max*78}));
  const label = t(room.series_basis==="session"?"本场在线人数":"窗口内在线人数");
  return '<figure class="live-viewers"><figcaption>'+label+' · '+
    t(room.series_source==="stream"?"供应商时点观测":"来源日快照")+' · UTC</figcaption>'+
    '<svg viewBox="0 0 395 105" role="img" aria-label="'+label+'"><text x="39" y="18" text-anchor="end">'+compact(max)+'</text>'+
    '<text x="39" y="95" text-anchor="end">0</text><path d="M46 14 V92 H376" stroke="currentColor" opacity=".35" fill="none"/>'+
    (points.length>1?'<polyline points="'+points.map(p=>p.x+','+p.y).join(' ')+'" fill="none" stroke="currentColor" stroke-width="1.5"/>':'')+
    points.map(p=>'<circle cx="'+p.x+'" cy="'+p.y+'" r="3" fill="currentColor"><title>'+liveTime(p.time)+' UTC · '+number(p.value)+'</title></circle>').join('')+
    '</svg><div><time>'+liveTime(series[0].time)+'</time><time>'+liveTime(series.at(-1).time)+'</time></div></figure>'+
    '<details class="live-series-values"><summary>'+t("查看时点明细")+' ('+series.length+')</summary>'+
    points.map(p=>'<div><time>'+liveTime(p.time)+' UTC</time><b>'+number(p.value)+'</b></div>').join('')+'</details>';
}
function boardLive(data) {
  const t = key=>esc(localMessage(key)), preview = data.live_preview, room = preview.room;
  const heading = '<div class="panel-head"><h2>'+t("直播分析")+'</h2><a class="text-link" href="'+boardLink("lives",{sort:"gmv"})+'">'+t("完整榜单")+'</a></div>';
  if (!room) return '<section class="panel board-live">'+heading+showEmpty("所选市场与日期没有直播场次")+'</section>';
  const link = (kind,item) => item.name ? '<a class="text-link" href="'+detailHref({kind,id:item.id})+'">'+esc(item.name)+'</a>' : esc(item.id);
  const list = '<div class="live-picker"><h3>'+t("直播间排行")+'</h3><small>'+t("按周期成交额排序")+' · '+esc(data.currency)+'</small>'+
    '<table><thead><tr>'+["直播间","周期成交额","本场成交额","本场进场人次"].map(s=>'<th>'+t(s)+'</th>').join('')+'</tr></thead><tbody>'+
    preview.rooms.map(r=>'<tr><td><button type="button" data-board-room="'+esc(r.id)+'" aria-pressed="'+(r.id===room.id)+'"><small>'+
      number(r.rank)+'</small> '+esc(r.name)+'</button></td><td>'+money(r.period_gmv,data.currency)+(r.period_estimated?' <small>'+t("含来源估算")+'</small>':'')+
      '</td><td>'+money(r.session_gmv,data.currency)+'</td><td>'+number(r.enter_count)+'</td></tr>').join('')+'</tbody></table></div>';
  const facts = [["本场成交额",money(room.gmv,data.currency,false)],["本场进场人次",number(room.enter_count)],
    ["直播品类",esc(room.category || "—")],["关联达人",room.creator?link("creators",room.creator):"—"],
    ["开播时间（UTC）",liveTime(room.start_at)],["结束时间（UTC）",liveTime(room.end_at)]];
  const products = room.products.length ? '<ol class="live-products">'+room.products.map(p=>'<li>'+
    link("products",p)+' <b>'+number(p.sales)+'</b></li>').join('')+'</ol>' : '<p class="muted">'+t("没有本场商品销量记录")+'</p>'+
    (room.daily_links.length?'<details><summary>'+t("当日快照关联商品")+'</summary>'+room.daily_links.map(p=>link("products",p)).join(' · ')+'</details>':'');
  return '<section class="panel board-live">'+heading+'<div class="board-live-layout">'+list+
    '<section class="live-preview" aria-live="polite" data-preview-room="'+esc(room.id)+'"><header><div><small>'+
    esc(data.source==="demo"?localMessage("演示数据"):data.source)+' · '+esc(data.market)+' · '+esc(room.day)+'</small><h3>'+esc(room.name)+
    '</h3></div><a class="text-link" data-live-detail href="'+detailHref({kind:"lives",id:room.id})+'">'+t("查看场次详情")+'</a></header>'+
    '<dl>'+facts.map(([name,value])=>'<div><dt>'+t(name)+'</dt><dd>'+value+'</dd></div>').join('')+'</dl>'+
    '<h4>'+t("在线人数观测")+'</h4>'+onlineViewers(room)+'<h4>'+t("本场销量前三商品")+'</h4>'+products+
    '<h4>'+t("相似直播场次")+'</h4>'+(room.similar.length?room.similar.map(r=>link("lives",r)).join(' · '):
      '<p class="muted">'+t("所选周期没有同类场次")+'</p>')+'</section></div><output role="status"></output></section>';
}
async function selectBoardRoom(button) {
  const root=button.closest(".board-live"), id=button.dataset.boardRoom, currentPage=cachedPage;
  if (root.dataset.loading===id || (!root.dataset.loading && currentPage.live_preview.room.id===id)) return;
  root.dataset.loading=id;
  const request=Symbol();
  root.liveRequest=request;
  const output=root.querySelector("output");
  output.textContent=localMessage("正在加载场次…");
  try {
    const data=await api("overview",{...scopeParams(),date:currentPage.date,live_only:1,room:id});
    if (!root.isConnected || root.liveRequest!==request || currentPage!==cachedPage) return;
    currentPage.live_preview=data.live_preview;
    root.outerHTML=boardLive(currentPage);
    current.params={...current.params,...scopeParams(),date:currentPage.date,room:data.live_preview.room?.id};
    history.replaceState(null,"",href("dashboard",current.params));
    document.querySelector('.board-live [aria-pressed="true"]')?.focus({preventScroll:true});
  } catch(error) {
    if (root.isConnected && root.liveRequest===request) { delete root.dataset.loading; output.textContent=localMessage(error.message); }
  }
}
function overview(data) {
  const categories = {"":"全部品类",...Object.fromEntries(meta.categories.map(c=>[c,c]))};
  if (data.category) categories[data.category] = data.category;
  return boardDiscovery()+
    '<div class="panel-head board-category"><h2 data-ui-label>品类看板</h2>'+optionField("品类","category",categories,data.category)+'<button class="btn" data-market-report>下载市场报告</button></div>'+
    kpi(data.metrics, data.changes, data.currency)+
    '<dl class="board-activity">'+[["有销量商品",number(data.activity.active_products)],["有销量店铺",number(data.activity.active_shops)],
      ["成交均价",metricMoney(data.activity,"avg_price",data.currency,false)]].map(([label,value])=>'<div><dt data-ui-label>'+label+'</dt><dd>'+value+'</dd></div>').join("")+'</dl>'+
    '<div class="dashboard-charts">'+chartPanel(data.trend,data.currency,data.category || "市场成交走势")+
    categoryPanel(data.categories)+'</div>'+boardLive(data)+'<div class="panel-head board-category"><h2>市场排行榜</h2><time>'+esc(dateText(data.date))+'</time></div><div class="board-list">'+data.boards.map(board=>boardRanking(board,data.currency)).join("")+
    '</div><a class="text-link" href="'+boardLink("tools",{tool:"partners"})+'">推荐与佣金 '+icon("arrow",14)+'</a>';
}
function metricRanges(kind) {
  const fields = {gmv:"周期成交额", sales:"周期销量"};
  if (kind === "products") fields.price = "期末标价";
  if (kind === "creators") fields.followers = "期末粉丝数";
  if (["videos","lives","creators"].includes(kind)) fields.views = "周期观看次数";
  return fields;
}
function rankingRanges(kind, params) {
  const bounds = {};
  for (const metric of Object.keys(metricRanges(kind))) {
    for (const edge of ["min","max"]) {
      const key = edge+"_"+metric;
      if (params[key] !== undefined && params[key] !== "") bounds[key]=params[key];
    }
  }
  return bounds;
}
function researchFilters(kind, data, params, presets) {
  const active=Object.keys(rankingRanges(kind,params)).length>0;
  const fields=Object.entries(metricRanges(kind)).map(([metric,label])=>{
    const monetary=["gmv","price"].includes(metric);
    const unit=monetary?" ("+esc(data.currency)+")":"";
    const inputs=["min","max"].map((edge)=>{
      const name=edge+"_"+metric;
      const hint=localMessage(edge==="min"?"最低":"最高");
      return '<input type="number" min="0" step="'+(monetary?'0.01':'1')+'" name="'+name+
        '" aria-label="'+esc(localMessage(label)+" "+hint)+'" placeholder="'+esc(hint)+'" value="'+esc(params[name]||"")+'">';
    }).join(" – ");
    return '<fieldset class="range-pair"><legend>'+esc(localMessage(label))+unit+'</legend><span>'+inputs+'</span></fieldset>';
  }).join("");
  return '<details class="research-filters"'+(active?' open':'')+'><summary data-ui-label>数值区间与常用筛选</summary>'+
    '<form id="ranking-ranges">'+fields+'<button class="btn">应用区间</button><button class="btn" type="button" data-reset-ranges>清除区间</button></form>'+
    '<form id="ranking-preset"><input name="name" required maxlength="60" placeholder="筛选方案名称" aria-label="筛选方案名称">'+
    '<button class="btn">保存当前已应用条件</button></form>'+
    presets.map(row=>'<div class="tf-inline"><a class="text-link" href="'+esc(href(kind,row.params))+'">'+esc(row.name)+
      '</a><button class="btn" type="button" data-delete-preset="'+esc(row.name)+'">删除方案</button></div>').join("")+
    '</details>';
}
function libraryCategories(values, selected = "") {
  const delimiter = " > ";
  const paths = new Set(values);
  if (selected) paths.add(selected);
  if (![...paths].some(path => path.includes(delimiter))) {
    const options = {"":"全部品类", ...Object.fromEntries([...paths].map(name => [name, name]))};
    return optionField("品类", "category", options, selected);
  }
  const split = path => {
    const [first, second, ...rest] = path.split(delimiter);
    return [first, second, rest.join(delimiter)].filter(Boolean);
  };
  const selectedLevels = split(selected);
  const pathsByLevel = [...paths].map(split);
  let html = "";
  for (const [depth, label] of ["一级品类", "二级品类", "三级品类"].entries()) {
    if (depth > selectedLevels.length) break;
    const branch = selectedLevels.slice(0, depth);
    const children = pathsByLevel.filter(parts => parts.length > depth
      && branch.every((value, i) => value === parts[i]));
    if (!children.length) break;
    const choices = children.map(parts => [parts.slice(0, depth + 1).join(delimiter), parts[depth]]);
    const parent = branch.join(delimiter);
    html += optionField(label, "category",
      {[parent]: depth ? "全部子类" : "全部品类", ...Object.fromEntries(choices)},
      selectedLevels.slice(0, depth + 1).join(delimiter));
  }
  return html;
}
function productReconciliation(report) {
  if (!report) return "";
  const en = localeTag() === "en-US";
  const t = (zh, english) => en ? english : zh;
  const labels = {matched:t("相符","matched"), missing:t("缺交","missing delivery"),
    mismatch:t("有差异","mismatch"), unverified:t("未核验","unverified")};
  const c = report.counts;
  const scopes = [...new Set(report.days.map(day => day.shop_scope).filter(Boolean))];
  const scopeLabel = scopes.join(" / ") || (report.source === "demo"
    ? t("合成演示数据","synthetic demo data") : t("本窗口暂无店铺范围声明","no shop scope declared in this window"));
  const summary = Object.entries(labels).map(([key,label]) => en ? c[key]+" "+label : label+" "+c[key]+" 天").join(" · ");
  const display = value => value ? [...(value.display_counts || [value.product_rows, value.sales]), value.gmv].join(" / ") : "—";
  const rows = report.days.map(day => '<tr><td>'+esc(day.date)+'</td><td>'+esc(labels[day.status])+'</td><td>'+
    esc(day.shop_scope || "—")+'</td><td>'+esc(display(day.expected))+'</td><td>'+esc(display(day.actual))+'</td></tr>').join("");
  return '<details data-source-reconciliation data-matched="'+c.matched+'" data-missing="'+c.missing+
    '" data-mismatch="'+c.mismatch+'" data-unverified="'+c.unverified+'"><summary><strong>'+t("商品日对账","Daily product reconciliation")+
    '</strong> · <span data-source-text>'+esc(report.source)+' · '+esc(scopeLabel)+'</span> · '+esc(summary)+'</summary>'+
    '<p>'+t("核对当前来源和市场的全部商品，数值依次为商品行数 / 销量 / GMV","All products in this source and market. Values are product rows / units sold / GMV")+
    ' ('+esc(report.currency)+')</p><div class="table-wrap"><table><thead><tr>'+
    [t("统计日","Date"),t("核对状态","Result"),t("店铺范围","Declared scope"),t("商户基准","Merchant control"),t("已入库","Recorded")].map(label=>'<th>'+label+'</th>').join("")+
    '</tr></thead><tbody data-source-text>'+rows+'</tbody></table></div></details>';
}
function library(view, data, p, presets) {
  const sorts = {
    gmv: "成交额从高到低",
    sales: "销量从高到低",
    growth: "增长率从高到低",
  };
  if (["videos", "lives", "creators"].includes(view))
    sorts.views = "观看次数从高到低";
  if (view === "creators")
    Object.assign(sorts, {
      followers: "粉丝数从高到低",
      follower_growth: "净增粉从高到低",
    });
  const pages = Math.max(1, Math.ceil(data.total / data.limit));
  return (
    '<section class="panel library"><div class="panel-head"><div><span class="section-kicker">' +
    esc(
      data.market +
        " · " +
        dateText(data.start_date) +
        " — " +
        dateText(data.date),
    ) +
    "</span><h2>" +
    kinds[view] +
    '数据库</h2></div><div class="tf-inline"><button class="btn" data-queue-export>后台导出</button> <button class="btn" data-export>' +
    icon("download", 15) +
    '导出 CSV</button></div></div><div class="tabs segment-tabs">' +
    Object.entries({ "": "全部" + kinds[view], ...segmentOptions[view] })
      .map(
        ([key, name]) =>
          '<button data-segment="' +
          key +
          '" class="' +
          ((p.segment || "") === key ? "active" : "") +
          '">' +
          name +
          "</button>",
      )
      .join("") +
    '</div><div class="list-controls"><form id="list-search" class="inline-search">' +
    icon("search", 16) +
    '<input type="search" name="q" aria-label="检索' +
    kinds[view] +
    '" placeholder="搜索名称或 ID，回车查询" value="' +
    esc(p.q || "") +
    '" maxlength="150"></form>' +
    matchControl(p.match) +
    libraryCategories(meta.categories_by_kind?.[view] || meta.categories || [], p.category) +
    optionField(
      "排序方式",
      "sort",
      sorts,
      p.sort || (p.segment === "breakout" ? "growth" : "gmv"),
    ) +
    "</div>" +
    productReconciliation(data.reconciliation) + researchFilters(view,data,p,presets) +
    (p.segment === "breakout"
      ? '<p class="rule-note">黑马达人要求两期快照完整，本期销量至少 20 件，前期有成交，成交额环比增长至少 15%，期末粉丝少于 20 万。<small> v1</small></p>'
      : p.segment==="promoted"?'<p class="rule-note">热推使用来源在窗口末次快照中提供的推广标记，按所选指标排序。</p>':"") +
    recordList(data.items, data.currency, view) +
    '<div class="pagination"><span>共 ' +
    number(data.total) +
    " 个" +
    kinds[view] +
    '</span><div><button class="iconbutton" data-page="' +
    (data.page - 1) +
    '" ' +
    (data.page <= 1 ? "disabled" : "") +
    ' aria-label="上一页">' +
    icon("back", 15) +
    "</button><b>" +
    data.page +
    "</b><span>/ " +
    pages +
    '</span><button class="iconbutton" data-page="' +
    (data.page + 1) +
    '" ' +
    (data.page >= pages ? "disabled" : "") +
    ' aria-label="下一页">' +
    icon("next", 15) +
    "</button></div></div></section>"
  );
}
function relatedCards(rows) {
  if (!rows?.length) return showEmpty("当前窗口没有关联记录");
  return (
    '<div class="related-grid">' +
    rows
      .map(
        (r) =>
          '<a class="related-card" href="' +
          detailHref(r) +
          '">' +
          thumb(r) +
          "<span><small>" +
          esc(kinds[r.kind] || r.kind) +
          "</small><b>" +
          esc(r.name) +
          "</b></span>" +
          icon("next", 14) +
          "</a>",
      )
      .join("") +
    "</div>"
  );
}
function livePanels(data) {
  const analysis = data.live_analysis;
  if (!analysis) return "";
  const section = (heading,body) => '<section class="panel live-analysis"><div class="panel-head"><h2>'+esc(localMessage(heading))+
    '</h2></div><div class="panel-body">'+body+'</div></section>';
  const period = [data.source,data.market,data.start_date,data.date].map(esc).join(' · ');
  const productRows = analysis.products.map(item=>{
    const name = item.name ? '<a class="text-link" href="'+detailHref({kind:"products",id:item.id})+'">'+esc(item.name)+'</a>' : esc(item.id);
    return '<tr><td>'+name+'</td><td>'+esc(item.first_seen)+' — '+esc(item.last_seen)+'</td><td class="num">'+number(item.days)+
      '</td><td class="num">'+number(item.sales)+'</td><td class="num">'+metricMoney(item,"gmv",data.currency,false)+'</td></tr>';
  });
  const table = (headers,rows) => '<div class="table-wrap"><table class="records"><thead><tr>'+
    headers.map(label=>'<th>'+esc(localMessage(label))+'</th>').join('')+'</tr></thead><tbody>'+rows.join('')+'</tbody></table></div>';
  const points = analysis.points || [];
  const observed = points.map(p=>'<tr><td>'+esc(p.stamp.slice(0,19).replace("T"," "))+'</td><td>'+
    esc(localMessage(p.metric==="online_viewers"?"在线人数":metricNames[p.metric]))+'</td><td class="num">'+
    (p.metric==="gmv"?money(p.value,data.currency,false):number(p.value))+'</td></tr>');
  return section("直播商品分析",'<p class="muted">'+esc(localMessage("日快照中的商品关联与归属指标"))+' · '+period+'</p>'+
    (productRows.length?table(["商品","关联日期","关联天数","商品归属销量","商品归属成交额"],productRows):showEmpty("所选周期没有商品关联记录")))+
    section("相似直播场次",'<p class="muted">'+esc(localMessage("同市场、同类目，按周期成交额排序"))+
      ' · '+esc(data.item.category || "—")+'</p>'+(analysis.similar.length?relatedCards(analysis.similar):showEmpty("所选周期没有同类场次")))+
    section("供应商时点观测",'<p class="muted">'+esc(localMessage("按 UTC 展示窗口内最近 60 条观测"))+' · '+period+'</p>'+
      (observed.length?table(["观测时间（UTC）","指标","观测值"],observed):showEmpty("所选周期没有供应商时点观测")));
}
function details(data) {
  const r = data.item;
  return (
    '<section class="panel profile"><div class="profile-head">' +
    thumb(r) +
    '<div><span class="detail-meta">' +
    '<span data-ui-label>' + esc(kinds[r.kind]) + "</span> · " +
    '<span class="category-chip">' + esc(r.category || "未分类") + "</span>" +
    "</span><h2>" +
    esc(r.name) +
    "</h2>" + translateName(r) + "<p>" +
    esc(r.subtitle || r.id) +
    '</p></div><div class="profile-actions"><button class="btn" data-save>' +
    icon("favorites", 15) +
    "加入收藏</button>" +
    (r.kind === "products" ? '<a class="btn" data-product-inspiration href="' + esc(href("inspiration", {
      source:data.source, market:data.market, days:data.days, date:data.date, product_id:r.id
    })) + '">为这个商品找灵感</a>' : '') +
    (r.kind === "creators" ? '<a class="btn" href="' + esc(href("tools", { tool: "contacts", id: r.id, ...scopeParams(), date: data.date })) + '">' + icon("creators", 15) + '合作联系簿</a>' : '') +
    (["products", "videos", "lives"].includes(r.kind)
      ? '<button class="primary" data-monitor>' +
        icon("monitor", 15) +
        "加入监控</button>"
      : "") +
    '</div></div><div class="detail-stats">' +
    [
      ["成交额", money(data.decision_evidence?.current.gmv ?? r.gmv_exact ?? r.gmv, data.currency, false)],
      ["销量", number(data.decision_evidence?.current.sales_exact ?? r.sales)],
      ["观看次数", number(r.views)],
      ["成交额环比", delta(r.growth)],
    ]
      .map(
        ([l, v]) =>
          "<div><small>" + l + "</small><strong>" + v + "</strong></div>",
      )
      .join("") +
    '</div></section>' + decisionForm(data,esc) + '<div class="detail-charts">' +
    chartPanel(data.trend, data.currency, "每日表现", data.item.kind==="products") +
    '<section class="panel fact-panel"><div class="panel-head"><h2>对象档案</h2></div>' +
    [
      ["对象 ID", r.id],
      ["市场", data.market],
      ["更新日期", dateText(r.updated_at)],
      ["记录天数", r.covered_days + " 天"],
      ["订单数",r.orders==null?'':String(r.orders)],
      ["退款件数",r.refund_units==null?'':String(r.refund_units)],
      ["成交额口径",r.gmv_estimated?localMessage("含来源估算"):""],
      ["所属分组", segmentOptions[r.kind]?.[r.segment] || r.segment],
      ["价格", r.price == null ? "" : metricMoney(r, "price", data.currency, false)],
      ["话题", r.tag],
      ["音乐", r.music],
      ["关键词", r.keyword],
    ]
      .filter(([, v]) => v)
      .map(
        ([k, v]) =>
          '<div class="fact"><span>' + k + "</span><b" + ((k === "记录天数" || (k === "所属分组" && segmentOptions[r.kind]?.[r.segment])) ? " data-ui-label" : "") + ">" + esc(v) + "</b></div>",
      )
      .join("") +
    '</section></div><section class="panel"><div class="panel-head"><h2>关联对象</h2></div>' +
    relatedCards(data.live_analysis ? data.related.filter(row=>row.kind!=="products") : data.related) +
    "</section>" +
    livePanels(data) +
    profileDetails(r)
  );
}
function marketsTable(data) {
  if (!data?.items?.length)
    return (
      '<section class="panel">' +
      showEmpty("当前时段没有可比较的市场记录") +
      "</section>"
    );
  const hasFx = data.items.some((r) => r.gmv_converted != null);
  return (
    '<section class="panel"><div class="panel-head"><div><span class="section-kicker">' +
    esc(dateText(data.start_date) + " — " + dateText(data.date)) +
    '</span><h2>市场比较</h2></div><span class="count-label">' +
    data.items.length +
    ' 个市场</span></div><div class="table-wrap"><table class="records"><thead><tr><th>市场</th><th class="num">成交额（原币）</th><th class="num">平均成交价</th><th class="num">销量</th><th class="num">商品</th><th class="num">店铺</th><th class="num">达人</th><th class="num">覆盖天数</th>' +
    (hasFx ? '<th class="num">折算成交额 / 汇率日</th>' : "") +
    "</tr></thead><tbody>" +
    data.items
      .map(
        (r) =>
          '<tr><td><a class="group-link" href="' +
          esc(
            href("products", {
              market: r.market,
              source: data.source,
              date: data.date,
              days: data.days,
            }),
          ) +
          '">' +
          esc(r.name) +
          " <small>" +
          esc(r.market) +
          '</small></a></td><td class="num"><b>' +
          metricMoney(r, "gmv", r.currency) +
          (r.includes_estimates?' <small data-ui-label>含来源估算</small>':'')+
          "</b> <small>" +
          esc(r.currency) +
          '</small></td><td class="num">' +
          metricMoney(r, "avg_price", r.currency, false) +
          '</td><td class="num">' +
          number(r.sales) +
          '</td><td class="num">' +
          number(r.product_count) +
          '</td><td class="num">' +
          number(r.shop_count) +
          '</td><td class="num">' +
          number(r.creator_count) +
          '</td><td class="num">' +
          number(r.covered_days) +
          "</td>" +
          (hasFx
            ? '<td class="num">' +
              (r.gmv_converted == null
                ? "—"
                : money(r.gmv_converted, r.base_currency) +
                  " " +
                  esc(r.base_currency) +
                  "<br><small>" +
                  esc(r.fx_date || "") +
                  "</small>") +
              "</td>"
            : "") +
          "</tr>",
      )
      .join("") +
    "</tbody></table></div></section>"
  );
}
function marketStructure(d) {
  const c = d.concentration || {},
    bands = d.price_bands || [];
  const ratio = (v) => (v == null ? "—" : number(v) + "%");
  return (
    '<section class="panel"><div class="panel-head"><h2>市场集中度</h2></div><div class="detail-stats">' +
    [
      ["商品数", number(c.product_count)],
      ["前三商品 GMV 占比", ratio(c.top3_share)],
      ["店铺数", number(c.shop_count)],
      ["前三店铺 GMV 占比", ratio(c.shop_top3_share)],
    ]
      .map(
        ([k, v]) =>
          "<div><small>" + k + "</small><strong>" + v + "</strong></div>",
      )
      .join("") +
    '</div></section><section class="panel"><div class="panel-head"><h2>商品价格带</h2><span class="count-label">' +
    esc(d.currency) +
    "</span></div>" +
    (bands.length
      ? '<div class="price-bands">' +
        bands
          .map(
            (b) =>
              "<div><strong>" +
              metricMoney(b,"min",d.currency,false) +
              " – " +
              metricMoney(b,"max",d.currency,false) +
              "</strong><span>" +
              number(b.count) +
              " 款商品 · " +
              ratio(b.share) +
              ' 成交占比</span><progress max="100" value="' +
              Number(b.share || 0) +
              '"></progress></div>',
          )
          .join("") +
        "</div>"
      : showEmpty("当前没有商品标价")) +
    "</section>"
  );
}
function reviewLabel(row,index) {
  const review=row.review_sentiment?.reviews[index];
  if (!review) return "";
  const names={positive:"正向",negative:"负向",mixed:"褒贬并存",unknown:"未识别倾向"};
  return '<small>'+esc(localMessage(names[review.label]))+(review.signals.length?' · '+esc(review.signals.join("、")):'')+'</small>';
}
function profileDetails(row) {
  const p = row.profile || {},
    traffic = p.live_traffic || {};
  const section = (title, body) =>
    '<section class="panel profile-more"><div class="panel-head"><h2>' +
    title +
    '</h2></div><div class="panel-body">' +
    body +
    "</div></section>";
  const facts = (rows) =>
    rows
      .map(
        ([label, value]) =>
          '<div class="fact"><span>' +
          esc(label) +
          "</span><b>" +
          esc(value) +
          "</b></div>",
      )
      .join("");
  let html = "";
  if (p.audience?.length)
    html += section(
      "受众构成",
      facts(p.audience.map((a) => [a.name, number(a.share) + "%"])),
    );
  if (p.milestones?.length)
    html += section(
      "达人里程碑",
      facts(p.milestones.map((m) => [m.date, m.label])),
    );
  if (p.reviews?.length)
    html += section(
      "商品评价",
      '<p data-ui-label class="muted">中英词典与否定规则 · '+p.reviews.length+' 条样本</p>'+
      '<p>'+Object.entries(row.review_sentiment?.counts||{}).map(([key,n])=>esc(localMessage(({positive:'正向',negative:'负向',mixed:'褒贬并存',unknown:'未识别倾向'})[key]))+' '+number(n)).join(' · ')+'</p>'+p.reviews
        .map(
          (r,i) =>
            '<article class="review"><small>' +
            esc(r.date) +
            " · " +
            number(r.rating) +
            " / 5</small><p>" +
            esc(r.text) +
            "</p>"+reviewLabel(row,i)+"</article>",
        )
        .join(""),
    );
  if (Object.keys(traffic).length)
    html += section(
      "直播流量",
      '<p class="muted">'+esc(localMessage("来源日快照"))+' · '+esc(dateText(row.updated_at))+'</p>'+facts([
        [localMessage("在线峰值"), number(traffic.peak_viewers)],
        [
          localMessage("平均观看时长"),
          traffic.avg_watch_seconds == null
            ? "—"
            : number(traffic.avg_watch_seconds) + (localeTag()==='en-US'?" s":" 秒"),
        ],
        ...(traffic.sources || []).map((e) => [e.name, number(e.share) + "%"]),
      ]),
    );
  return html;
}
const trendLabels = {
  tag: "话题",
  music: "音乐",
  keyword: "关键词",
  script: "脚本",
  category: "品类",
};
function ideaConditions(idea) {
  const key = JSON.stringify([idea.topic, idea.subject]);
  const stored = history.state?.filming?.[key] || [];
  return Object.keys(conditionLabels).filter(k => stored.includes(k));
}

function shootableDraft(idea) {
  const selected = ideaConditions(idea);
  return {...adaptIdea(idea, selected, localeTag() === "en-US"), selected};
}

function shotList(idea) {
  return [["第一镜", idea.first], ["接着拍", idea.action], ["收尾画面", idea.reveal]].map(([label, shot]) =>
    '<li><strong>' + esc(localMessage(label)) + '</strong><span>' + esc(shot) + '</span></li>').join("");
}

function opening(idea) {
  return '<small>' + esc(localMessage(idea.selected.includes("faceless") ? "开场字幕" : "开场口播")) + '</small>' + esc(idea.hook);
}

function filmingConditions(draft) {
  return '<fieldset><legend>' + esc(localMessage("选择拍摄条件，可多选")) + '</legend>' +
    Object.entries(conditionLabels).map(([key, label]) => '<label><input type="checkbox" data-idea-condition="' + key + '"' +
      (draft.selected.includes(key) ? ' checked' : '') + '>' + esc(localMessage(label)) + '</label>').join("") + '</fieldset>';
}

async function loadDailyReferences(panel, page, params, id) {
  const en = localeTag() === "en-US";
  try {
    const result = await api("inspiration/videos", {...params, tz: Intl.DateTimeFormat().resolvedOptions().timeZone});
    if (id !== renderId) return;
    const offset = page.cards.length;
    const items = result.items.map((row, i) => {
      const idea = referenceDraft(row, en);
      page.cards.push(idea);
      const draft = shootableDraft(idea);
      return '<article class="daily-reference" data-idea-index="' + (offset + i) + '"><small data-source-text>' +
        esc(row.subject) + ' · ' + (row.match === 'name' ? (en ? 'Name or model in title' : '标题含商品名或型号') : (en ? 'Related product' : '同类参考')) +
        '</small><h3><a data-source-text href="' + esc(row.url) + '" target="_blank" rel="noopener noreferrer">' + esc(row.title) +
        ' ↗</a></h3><small data-source-text>' + esc([row.platform, row.author, row.published].filter(Boolean).join(' · ')) + '</small>' +
        '<p>' + esc(idea.title) + '</p><details class="idea-adapt"' + (draft.selected.length ? ' open' : '') + '><summary>' + esc(localMessage("按我的条件改拍")) + '</summary>' +
        filmingConditions(draft) + '<blockquote>' + opening(draft) + '</blockquote><ol class="idea-shots" aria-live="polite">' + shotList(draft) +
        '</ol><button class="btn" data-copy-idea="' + (offset + i) + '">' + esc(localMessage("复制拍摄稿")) + '</button></details></article>';
    });
    const status = en ? items.length + ' videos · ' + result.day : result.day + ' · ' + items.length + ' 条原片';
    const shortage = items.length >= result.target ? '' : result.incomplete_search
      ? (en ? 'Some sources are temporarily unavailable. Reopen in a few minutes to retry.' : '部分搜索暂时失败，几分钟后重新打开可补查。')
      : (en ? 'These are all the matching videos found. Try a product type or another name to broaden the search.' : '这次只找到这些相关原片。可用商品通用名或别称再找一次。');
    panel.querySelector('[data-daily-status]').textContent = status;
    panel.querySelector('[data-daily-list]').innerHTML = (shortage ? '<p class="idea-empty">' + esc(shortage) + '</p>' : '') +
      '<div class="daily-videos">' + items.join('') + '</div>';
  } catch {
    if (id === renderId) panel.querySelector('[data-daily-status]').textContent = en ? 'Video search unavailable. Reload to retry.' : '视频检索暂时不可用，可刷新重试。';
  }
}

function productVideoPanel(data, windowParams) {
  if (!data.product) return '';
  const en = localeTag() === "en-US";
  const videos = data.linked_videos.map(v => {
    const evidence = en ? v.linked_days + ' linked day(s)' : '关联 ' + v.linked_days + ' 天';
    return '<a class="related-card" data-video-id="' + esc(v.id) + '" href="' +
      esc(href("detail", {...windowParams, kind:"videos", id:v.id})) + '">' + thumb(v) +
      '<span><b data-source-text>' + esc(v.name) + '</b><small>' + esc(evidence + ' · ' + v.first_seen + ' – ' + v.last_seen) +
      '</small></span>' + icon("next", 14) + '</a>';
  });
  return '<section class="panel" data-product-videos><div class="panel-head"><h2>' +
    (en ? 'Videos linked to this product' : '这个商品的关联视频') + '</h2></div><div class="panel-body">' +
    (videos.length ? '<p class="muted">' + (en ? 'Links come from daily video records. Video detail metrics cover the whole video.' :
      '此处展示视频日快照记录的商品关联。视频详情中的成交额与销量为整条视频的指标。') +
      '</p><div class="related-grid">' + videos.join('') + '</div>' :
      '<p class="muted">' + (en ? 'No video in this source and period records a link to this product.' :
        '当前来源和日期范围内没有记录与这个商品关联的视频。') + '</p>') + '</div></section>';
}

function inspirationBoard(data) {
  const t = localMessage;
  const subject = data.subject;
  const en = localeTag() === "en-US";
  const windowParams = {source:data.source, market:data.market, date:data.date, days:data.days};
  const cards = data.cards.map((idea, index) => {
    const product = idea.product
      ? '<a class="idea-product" href="' + detailHref(idea.product) + '">' + thumb(idea.product) + '<span data-source-text>' + esc(idea.subject) + '</span></a>'
      : '<span class="idea-product" data-source-text>' + esc(idea.subject) + '</span>';
    const draft = shootableDraft(idea);
    const adapt = idea.topic ? '<details class="idea-adapt"' + (draft.selected.length ? ' open' : '') + '><summary>' +
      esc(t("按我的条件改拍")) + '</summary>' + filmingConditions(draft) + '</details>' : '';
    return '<article class="panel idea-card" data-idea-index="' + index + '">' + product + '<h3>' + esc(idea.title) +
      '</h3><p class="idea-viewer">' + esc(t("拍给谁看")) + ' · ' + esc(idea.viewer) + '</p>' +
      '<blockquote>' + opening(draft) + '</blockquote>' +
      renderReferences(idea.references, localeTag() === "en-US", esc) + adapt +
      '<ol class="idea-shots" aria-live="polite">' + shotList(draft) +
      '</ol><button type="button" class="btn" data-copy-idea="' + index + '">' + esc(t("复制拍摄稿")) + '</button></article>';
  }).join("");
  const options = data.products.map(p => '<option value="' + esc(p.name) + '"></option>').join("");
  return '<form class="panel idea-search" id="idea-search"><label for="idea-subject">' +
    esc(t("你想拍什么商品？")) + '</label><div><input id="idea-subject" name="subject" list="idea-products" required maxlength="1500" value="' +
    esc(subject) + '" placeholder="' + esc(t("输入商品名称或型号")) + '"><datalist id="idea-products">' + options +
    '</datalist><button class="primary">' + esc(t("看选题")) + '</button></div></form>' +
    (data.products.length ? '<nav class="reference-topics" aria-label="' + esc(t("本期商品")) + '"><strong>' + esc(t("本期商品")) + '</strong>' +
    data.products.slice(0, 6).map(({name,id}) => '<a class="btn" data-source-text href="' + esc(href("inspiration", {...windowParams, product_id:id})) + '">' + esc(name) + '</a>').join("") + '</nav>' : '') +
    productVideoPanel(data, windowParams) +
    (subject || (data.source === "demo" && data.products.length) ? '<section class="panel daily-shelf" data-daily><div class="idea-heading"><h2>' +
      esc(t("今日视频参考")) + '</h2><small data-daily-status role="status">' +
      (data.source === "demo" ? esc(t("正在查找相关原片…")) : (en ? 'Search term sent to Dailymotion and, when needed, MyMemory' :
        '搜索词将发给 Dailymotion，需翻译时也会发给 MyMemory') + ' · ' + esc(subject)) + '</small></div>' +
      (data.source === "demo" ? '' : '<button type="button" class="btn" data-public-video-search>' +
        (en ? 'Search public videos with this term' : '用这个词搜索公开视频') + '</button>') + '<div data-daily-list></div></section>' : '') +
    '<section><div class="idea-heading"><h2>' + esc(t(subject ? "这个商品可以这样拍" : "本期商品可以这样拍")) + '</h2>' +
    (subject ? '<a class="text-link" href="' + esc(href("inspiration", windowParams)) + '">' + esc(t("看本期选题")) + '</a>' : '') +
    '</div>' + (!subject && !data.products.length ? '<p class="idea-empty">' + esc(t("本期没有商品记录。输入你想拍的商品，就可以查找原片和选题。")) + '</p>' : '') +
    '<div class="idea-grid">' + cards + '</div>' +
    '</section><a class="text-link idea-research" href="' + esc(href("trends", {...windowParams, group:"script"})) + '">' +
    esc(t("查看脚本排行与代表视频")) + icon("arrow",14) + '</a>';
}

async function copyIdea(button, idea) {
  const fields = [["拍给谁看", "viewer"], [idea.selected.includes("faceless") ? "开场字幕" : "开场口播", "hook"], ["第一镜", "first"], ["接着拍", "action"], ["收尾画面", "reveal"]];
  const conditions = idea.selected.map(k => localMessage(conditionLabels[k])).join(" · ");
  const source = idea.references?.[0];
  const draft = [idea.title, idea.subject, conditions, ...fields.map(([label,key]) => localMessage(label) + " · " + idea[key]),
    source && (localeTag() === "en-US" ? "Reference video" : "参考原片") + " · " + source.author + " · " + source.url].filter(Boolean).join("\n");
  try {
    await navigator.clipboard.writeText(draft);
    toast(localMessage("拍摄稿已复制"));
  } catch {
    let field = button.parentElement.querySelector("textarea");
    if (!field) {
      field = document.createElement("textarea");
      field.readOnly = true;
      field.rows = 6;
      field.setAttribute("aria-label",localMessage("拍摄稿"));
      button.after(field);
    }
    field.value = draft;
    field.select();
    toast(localMessage("请复制已选中的拍摄稿"));
  }
}
function trends(view, data, p) {
  const gr = data.group,
    rows = data.items || [],
    kind = gr === "category" ? "products" : "videos";
  const tabs =
    view === "trends"
      ? '<div class="tabs">' +
        ["tag", "music", "keyword", "script"]
          .map(
            (k) =>
              '<a class="' +
              (k === gr ? "active" : "") +
              '" href="' +
              esc(href(view, { group: k })) +
              '">' +
              trendLabels[k] +
              "</a>",
          )
          .join("") +
        "</div>"
      : "";
  return (
    '<section class="panel"><div class="panel-head"><div><span class="section-kicker">' +
    esc(
      data.market +
        " · " +
        dateText(data.start_date) +
        " — " +
        dateText(data.date),
    ) +
    "</span><h2>" +
    trendLabels[gr] +
    '排行</h2></div><span class="count-label">' +
    number(rows.length) +
    " 项</span></div>" +
    tabs +
    (rows.length
      ? '<div class="table-wrap"><table class="records"><thead><tr><th>排名</th><th>' +
        trendLabels[gr] +
        '</th><th class="num">成交额 ' +
        esc(data.currency) +
        '</th><th class="num">销量</th><th class="num">' +
        kinds[kind] +
        '数</th><th class="num">占比</th></tr></thead><tbody>' +
        rows
          .map(
            (r, i) =>
              '<tr><td><span class="rank ' +
              (i < 3 ? "top" : "") +
              '">' +
              String(i + 1).padStart(2, "0") +
              '</span></td><td><a class="group-link" href="' +
              esc(
                gr === "category"
                  ? href("products", { category: r.name })
                  : href(view, { group: gr, topic: r.name }),
              ) +
              '">' +
              esc(r.name) +
              '</a></td><td class="num"><b>' +
              metricMoney(r, "gmv", data.currency) +
              (r.includes_estimates?' <small data-ui-label>含来源估算</small>':'')+
              '</b></td><td class="num">' +
              number(r.sales) +
              '</td><td class="num">' +
              number(r.count) +
              '</td><td class="num">' +
              (r.share == null ? "—" : number(r.share) + "%") +
              "</td></tr>",
          )
          .join("") +
        "</tbody></table></div>"
      : showEmpty()) +
    "</section>"
  );
}
async function trendView(view, p) {
  const group =
      view === "categories"
        ? "category"
        : view === "inspiration"
          ? "script"
          : p.group || "tag",
    s = scopeParams();
  const [data,study] = await Promise.all([
    api("trends",{...s,group}),api("trend-study",{...s,group,topic:p.topic||""})
  ]);
  const caption=study.forecast.length
    ? "未来 7 日沿用上周同曜日的观测值。最近 7 日回测平均绝对误差："+metricMoney(study.mae,"gmv",study.currency,false)+" / "+number(study.mae.sales)+" 件。"
    : "最近 14 日记录不连续，暂缺预测。";
  const english=localeTag()==="en-US";
  const method=english?(study.forecast.length?"Next 7 days use the last observed value for the same weekday. Previous 7-day backtest MAE: "+metricMoney(study.mae,"gmv",study.currency,false)+" / "+number(study.mae.sales)+" units.":localMessage(caption)):caption;
  const outlook='<section class="panel"><div class="panel-head"><h2>趋势预测与采样覆盖</h2></div><div class="panel-body">'+
    '<p>'+esc(study.topic||(english?"Market total":"所选市场整体"))+' · '+esc(study.sample_start)+' — '+esc(study.date)+(english?' · Observed ':' · 已观测 ')+study.observed_days+(english?'/28 days</p>':'/28 天</p>')+
    '<p>'+esc(method)+'</p>'+(study.missing_dates.length?'<details><summary data-ui-label>缺失日期</summary>'+esc(study.missing_dates.join("、"))+'</details>':'')+
    (study.forecast.length?'<div class="table-wrap"><table class="records"><thead><tr><th>预测日期</th><th>预估 GMV</th><th>预估销量</th></tr></thead><tbody>'+study.forecast.map(r=>'<tr><td>'+esc(r.date)+'</td><td>'+metricMoney(r,"gmv",study.currency,false)+'</td><td>'+number(r.sales)+'</td></tr>').join('')+'</tbody></table></div>':'')+'</div></section>';
  if (!p.topic || view === "categories")
    return (
      (view === "categories" ? marketStructure(data) : "") +
      trends(view, data, p)+outlook
    );
  const selected = data.items.find((x) => x.name === p.topic)?.examples || [];
  return (
    '<section class="panel"><div class="panel-head"><div><span class="section-kicker">' +
    trendLabels[group] +
    " · 关联视频</span><h2>" +
    esc(p.topic) +
    '</h2></div><button class="btn" data-save-topic>收藏此灵感</button><a class="text-link" href="' +
    esc(href(view === "inspiration" ? "trends" : view, { ...s, date: data.date, group })) +
    '">返回排行</a></div>' +
    relatedCards(selected) +
    "</section>"+outlook
  );
}
function matchControl(value) {
  return optionField("匹配方式","match",{broad:"模糊匹配",exact:"精确匹配"},value||"broad");
}
function searchForm(q, kind, match) {
  return (
    '<section class="panel search-panel"><form id="search-page"><label class="inline-search">' +
    icon("search", 18) +
    '<input aria-label="全站搜索关键词" name="q" value="' +
    esc(q) +
    '" placeholder="输入名称或 ID" required></label>' +
    optionField(
      "搜索范围",
      "search-kind",
      { "": "全部类型", ...kinds },
      kind || "",
    ) +
    matchControl(match) +
    '<button type="button" class="btn" data-translate-query>翻译搜索词</button><button class="primary">搜索</button></form></section>'
  );
}
async function searched(p) {
  let html = searchForm(p.q || "", p.kind, p.match);
  if (!p.q) return html;
  const groups = p.kind && kinds[p.kind] ? [p.kind] : Object.keys(kinds);
  const data = await Promise.all(
    groups.map((kind) =>
      api("rankings", { ...scopeParams(), kind, q: p.q, match: p.match||"broad", limit: 5 }),
    ),
  );
  let any = false;
  data.forEach((a, i) => {
    if (!a.total) return;
    any = true;
    const kind = groups[i];
    html +=
      '<section class="panel search-result"><div class="panel-head"><h2>' +
      kinds[kind] +
      " <small>" +
      number(a.total) +
      '</small></h2><a class="text-link" href="' +
      esc(href(kind, { q: p.q, match:p.match })) +
      '">查看全部 ' +
      icon("arrow", 14) +
      "</a></div>" +
      recordList(a.items, a.currency, kind) +
      "</section>";
  });
  return (
    html +
    (any
      ? ""
      : '<section class="panel">' +
        showEmpty("没有找到与“" + p.q + "”匹配的对象") +
        "</section>")
  );
}
let cachedPage = null;
function markActive(view, p) {
  const active = view === "detail" ? p.kind : view;
  document.querySelectorAll("[data-nav]").forEach((n) => {
    n.classList.toggle("active", n.dataset.nav === active);
    if (n.dataset.nav === active) n.setAttribute("aria-current", "page");
    else n.removeAttribute("aria-current");
  });
}
async function render() {
  const id = ++renderId;
  current = route();
  const { view, params: p } = current;
  cachedPage = null;
  document.body.classList.remove("nav-open");
  syncNavigation();
  markActive(view, p);
  $("#crumb").textContent = names[view] || "页面未找到";
  document.title = (names[view] || "页面") + " · tikflowso";
  if (p.market || p.source || p.date || p.days) {
    if (
      (p.source && p.source !== scope.source) ||
      (p.market && p.market !== scope.market)
    )
      scope.date = "";
    if (p.market) scope.market = p.market;
    if (p.source) scope.source = p.source;
    if (/^\d{4}-\d{2}-\d{2}$/.test(p.date || "")) scope.date = p.date;
    if (Number.isInteger(Number(p.days)) && +p.days>=1 && +p.days<=366) scope.days=Number(p.days);
    persist();
  }
  const mount = document.createElement("div");
  mount.className = "page";
  mount.innerHTML = '<div class="loading">正在读取数据…</div>';
  $("#app").replaceChildren(mount);
  try {
    if (!names[view]) {
      mount.innerHTML =
        '<section class="panel">' +
        showEmpty("这个页面不存在") +
        '<a class="btn" href="#dashboard">返回工作台</a></section>';
      return;
    }
    let fresh;
    try {
      fresh = await api("meta", scopeParams());
    } catch (e) {
      if (id !== renderId) return;
      if (p.source || ![400,403,404].includes(e.status) || (scope.source === "demo" && scope.market === "US" && !scope.date))
        throw e;
      Object.assign(scope, { market: "US", source: "demo", date: "", days: 7 });
      persist();
      fresh = await api("meta", scopeParams());
    }
    if (id !== renderId) return;
    if (
      !p.market && fresh.markets.length &&
      !fresh.markets.some((m) => m.code === scope.market)
    ) {
      scope.market = fresh.markets[0].code;
      scope.date = "";
      persist();
      fresh = await api("meta", scopeParams());
    }
    if (id !== renderId) return;
    meta = fresh;
    resourceLinks();
    sourceUI();
    mount.innerHTML =
      heading(view) +
      '<div class="workspace-content"><div class="loading">正在读取数据…</div></div>';
    const content = mount.querySelector(".workspace-content");
    if (
      [
        "tools",
        "creative",
        "agent",
        "monitor",
        "favorites",
        "account",
        "admin",
        "api",
        "resources",
        "plans",
      ].includes(view)
    ) {
      content.innerHTML = "";
      await renderTools(content, {
        view,
        ...scopeParams(),
        date: scope.date || meta.date,
        meta,
        params: p,
        refresh: () => {
          identity();
          render();
        },
      });
      return;
    }
    let html, data;
    if (view === "dashboard") {
      data = await api("overview", {...scopeParams(),board:1,category:p.category,room:p.room});
      html = overview(data);
    } else if (view === "markets") {
      data = await api("markets", {
        ...scopeParams(),
        date: scope.date || meta.date,
      });
      html = marketsTable(data);
    } else if (kinds[view]) {
      const [ranked,presets] = await Promise.all([api("rankings", {
        ...scopeParams(),
        ...rankingRanges(view,p),
        kind: view,
        q: p.q,
        match: p.match||"broad",
        sort: p.sort,
        category: p.category,
        segment: p.segment,
        page: p.page || 1,
        limit: 10,
      }), api("ranking-presets",{kind:view})]);
      data=ranked;
      html = library(view, data, p, presets.items);
    } else if (view === "detail") {
      data = await api("detail", { ...scopeParams(), kind: p.kind, id: p.id });
      html = details(data);
    } else if (view === "search") html = await searched(p);
    else if (view === "inspiration" && !p.topic) {
      data = await api("inspiration", {...scopeParams(), product_id:p.product_id, subject:p.subject, locale:localeTag()});
      html = inspirationBoard(data);
    } else html = await trendView(view, p);
    if (id !== renderId) return;
    content.innerHTML = html;
    cachedPage = data;
    const daily = content.querySelector('[data-daily]');
    if (daily && data.source === "demo") void loadDailyReferences(daily, data, {...scopeParams(), subject:data.subject}, id);
  } catch (e) {
    if (id !== renderId) return;
    mount.innerHTML =
      heading(view) +
      '<section class="panel error">' +
      showEmpty(e.message || "数据加载失败") +
      '<div class="error-actions"><button data-retry class="btn">重新加载</button><a class="text-link" href="#dashboard">返回概览</a></div></section>';
  }
}
async function mutatePreset(name,remove) {
  const routeAtClick=location.hash;
  try {
    await api("ranking-presets",{kind:current.view,name,remove,params:{...current.params,...scopeParams(),date:scope.date||meta.date}},true);
    if (routeAtClick===location.hash) {
      await render();
      const filters=document.querySelector(".research-filters");
      if (filters) filters.open=true;
    }
  } catch(err) {toast(err.message);}
}
async function queueExport(button) {
  button.disabled=true;
  const request_key=button.dataset.requestKey || crypto.randomUUID();
  button.dataset.requestKey=request_key;
  try {
    await api("exports",{params:{...current.params,...scopeParams(),kind:current.view},request_key},true);
    location.hash="#tools?tool=exports";
  } catch(e) {toast(e.message);button.disabled=false;}
}
async function exportRows(button) {
  const { view, params: p } = current;
  const scopeAtClick = scopeParams();
  button.disabled = true;
  button.textContent = "正在导出…";
  try {
    const q = new URLSearchParams({ ...p, ...scopeAtClick, kind: view });
    if (!q.get("date")) q.delete("date");
    const response = await fetch("/api/export?" + q);
    if(response.status===202){location.hash="#tools?tool=exports";return;}
    if (!response.ok) {
      const body = await response.json();
      throw Error(body.error || "导出失败");
    }
    const url = URL.createObjectURL(await response.blob());
    const a = document.createElement("a");
    a.href = url;
    a.download =
      "tikflowso-" +
      view +
      "-" +
      scopeAtClick.market +
      "-" +
      (scopeAtClick.date || meta.date) +
      ".csv";
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    toast("榜单已导出");
  } catch (e) {
    toast(e.message);
  } finally {
    button.disabled = false;
    button.innerHTML = icon("download", 15) + "导出 CSV";
  }
}
async function saveItem(button, monitor) {
  const r = cachedPage?.item;
  if (!r) return;
  button.disabled = true;
  try {
    await api(
      monitor ? "monitors" : "favorites",
      { ...scopeParams(),date:cachedPage.date||scope.date, kind:r.kind, id:r.id },
      true,
    );
    button.textContent = monitor ? "已加入监控" : "已加入收藏";
    toast(button.textContent);
  } catch (e) {
    button.disabled = false;
    toast(e.message);
  }
}
function openSearch() {
  const d = $("#search-dialog");
  $("#search-options").innerHTML=optionField("搜索范围","search-kind",{"":"全部类型",...kinds},current.params.kind||"")+
    matchControl(current.params.match);
  if (!d.open) d.showModal();
  $("#query").focus();
}
document.querySelector(".skip").onclick = (e) => {
  e.preventDefault();
  $("#main-content").focus();
};
nav();
identity();
$("#source").addEventListener("change", (e) =>
  updateScope("source", e.target.value),
);
const mobileNavigation=window.matchMedia("(max-width:780px)");
try {document.body.classList.toggle("nav-collapsed",localStorage.getItem("tikflowso-nav-collapsed")==="true");} catch {}
function syncNavigation(){
  const expanded=mobileNavigation.matches?document.body.classList.contains("nav-open"):!document.body.classList.contains("nav-collapsed");
  const label=localMessage(expanded?"收起导航":"展开导航");
  $("#menu-btn").setAttribute("aria-expanded",String(expanded));
  $("#menu-btn").setAttribute("aria-label",label);
  $("#menu-btn").title=label;
  $("#sidebar").inert=!expanded;
}
$("#menu-btn").onclick = () => {
  if(mobileNavigation.matches)document.body.classList.toggle("nav-open");
  else{
    const collapsed=document.body.classList.toggle("nav-collapsed");
    try{localStorage.setItem("tikflowso-nav-collapsed",String(collapsed));}catch{}
  }
  syncNavigation();
};
$("#veil").onclick = () => {document.body.classList.remove("nav-open");syncNavigation();};
mobileNavigation.addEventListener("change",syncNavigation);
syncNavigation();
$("#search-button").onclick = openSearch;
$("#close-search").onclick = () => $("#search-dialog").close();
$("#global-search").onsubmit = (e) => {
  e.preventDefault();
  const q = $("#query").value.trim();
  if (!q) return;
  $("#search-dialog").close();
  const dialog=$("#search-dialog");
  location.hash = href("search", {...scopeParams(),q,kind:dialog.querySelector('[data-field="search-kind"]').value,
    match:dialog.querySelector('[data-field="match"]').value});
};
document.addEventListener("keydown", (e) => {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
    e.preventDefault();
    openSearch();
  }
  if (e.key === "Escape") {
    if ($("#search-dialog").open) $("#search-dialog").close();
    document.body.classList.remove("nav-open");
    syncNavigation();
  }
});
$("#app").addEventListener("change", (e) => {
  const t = e.target;
  if (t.hasAttribute("data-idea-condition")) {
    const card = t.closest("[data-idea-index]");
    const idea = cachedPage.cards[Number(card.dataset.ideaIndex)];
    const key = JSON.stringify([idea.topic, idea.subject]);
    const selected = Array.from(card.querySelectorAll("[data-idea-condition]:checked"), el => el.dataset.ideaCondition);
    history.replaceState({...history.state, filming: {...history.state?.filming, [key]: selected}}, "");
    const draft = shootableDraft(idea);
    card.querySelector("blockquote").innerHTML = opening(draft);
    card.querySelector(".idea-shots").innerHTML = shotList(draft);
    card.querySelector("textarea")?.remove();
    return;
  }
  if (t.dataset.scope) {
    updateScope(t.dataset.scope, t.value);
    return;
  }
  const f = t.dataset.field;
  if (f === "chart" && cachedPage) {
    chartMetric = t.value;
    $(".workspace-content").innerHTML =
      current.view === "detail" ? details(cachedPage) : overview(cachedPage);
  } else if (f === "match" && current.view !== "dashboard") {
    const search = document.querySelector(current.view === 'search' ? '#search-page [name=q]' : '#list-search [name=q]');
    change({match:t.value,q:search?.value.trim()||'',page:1});
  } else if (f === "category" || f === "sort") {
    change({ [f]: t.value, page: 1 });
  } else if (f === "search-kind" && current.params.q) {
    change({ kind: t.value });
  }
});
$("#app").addEventListener("input", (e) => {
  if (e.target.form?.id === "research-decision" && cachedPage) {
    cachedPage.decisionDraft = e.target.value;
    cachedPage.decisionSaved = false;
    e.target.form.querySelector("output").textContent = "";
  }
});
$("#app").addEventListener("submit", (e) => {
  const f = e.target;
  if (f.id === "research-decision") {
    e.preventDefault();
    void submitDecision(f,cachedPage,api,()=>cachedPage);
  } else if (f.id === "ranking-ranges") {
    e.preventDefault();
    for (const metric of Object.keys(metricRanges(current.view))) {
      const min=f.elements["min_"+metric], max=f.elements["max_"+metric];
      if (min.value && max.value && min.valueAsNumber > max.valueAsNumber) {
        toast(localMessage("下限不能大于上限")); return;
      }
    }
    change({...Object.fromEntries(new FormData(f)),page:1});
  } else if (f.id === "ranking-preset") {
    e.preventDefault();
    mutatePreset(f.elements.name.value.trim(),false);
  } else if (f.id === "list-search") {
    e.preventDefault();
    change({ q: f.elements.q.value.trim(), page: 1 });
  } else if (f.id === "idea-search") {
    e.preventDefault();
    const subject = f.elements.subject.value.trim();
    if (subject) change({ subject, product_id:null });
    else f.elements.subject.focus();
  } else if (f.id === "board-question") {
    e.preventDefault();
    askOnBoard(f,{...scopeParams(),date:scope.date || meta.date},{esc,href,t:localMessage,icon,api});
  } else if (f.id === "search-page") {
    e.preventDefault();
    location.hash = href("search", {
      ...scopeParams(),date:scope.date || meta.date,
      q: f.elements.q.value.trim(),
      kind: f.querySelector('[data-field="search-kind"]').value,
      match: f.querySelector('[data-field="match"]').value,
    });
  }
});
$("#app").addEventListener("click", (e) => {
  const t = e.target.closest("button");
  if (!t) return;
  if (t.hasAttribute("data-public-video-search")) {
    const panel = t.closest("[data-daily]");
    t.remove();
    panel.querySelector("[data-daily-status]").textContent = localMessage("正在查找相关原片…");
    void loadDailyReferences(panel, cachedPage, {...scopeParams(), subject:cachedPage.subject, external_search:"1"}, renderId);
    return;
  }
  if (t.hasAttribute("data-copy-idea")) {
    const idea = cachedPage?.cards?.[Number(t.dataset.copyIdea)];
    if (idea) copyIdea(t, shootableDraft(idea));
    return;
  }
  if (t.hasAttribute("data-board-room")) { selectBoardRoom(t); return; }
  if (t.hasAttribute("data-translate-board")) {
    const names = Array.from(t.closest(".board-ranking").querySelectorAll("[data-translate-name]"),button=>button.dataset.translateName);
    translateText(api,names.join("\n"),scopeParams());
    return;
  }
  if (t.hasAttribute("data-translate-query") || t.hasAttribute("data-translate-name")) {
    const field = t.hasAttribute("data-translate-query") ? t.form.elements.q : null;
    const source = field ? field.value.trim() : t.dataset.translateName;
    if (!source) { field?.focus(); return; }
    translateText(api, source, scopeParams(), field ? translation => {
      field.value = translation;
      field.form.requestSubmit();
    } : null);
    return;
  }
  if (t.hasAttribute("data-segment"))
    change({
      segment: t.dataset.segment,
      sort: t.dataset.segment === "breakout" ? "growth" : current.params.sort,
      page: 1,
    });
  else if (t.hasAttribute("data-reset-ranges")) {
    change({...Object.fromEntries(Object.keys(rankingRanges(current.view,current.params)).map(k=>[k,""])),page:1});
    document.querySelector("#ranking-ranges")?.querySelectorAll("input").forEach(input=>input.value="");
  }
  else if (t.hasAttribute("data-delete-preset")) mutatePreset(t.dataset.deletePreset,true);
  else if (t.dataset.page) change({ page: t.dataset.page });
  else if (t.hasAttribute("data-retry")) render();
  else if (t.hasAttribute("data-queue-export") || (t.hasAttribute("data-export") && cachedPage?.total>1000)) queueExport(t);
  else if (t.hasAttribute("data-market-report") && current.view==="dashboard" && cachedPage) downloadMarketReport(cachedPage);
  else if (t.hasAttribute("data-export")) exportRows(t);
  else if (t.hasAttribute("data-save-topic")) {
    t.disabled=true;
    api("saved-topics",{...scopeParams(),date:scope.date||meta.date,topic:current.params.topic,
      group:current.view==="inspiration"?"script":current.params.group||"tag"},true)
      .then(()=>{t.textContent=localMessage("已加入收藏");toast(t.textContent);})
      .catch(err=>{t.disabled=false;toast(err.message);});
  }
  else if (t.hasAttribute("data-save")) saveItem(t, false);
  else if (t.hasAttribute("data-monitor")) saveItem(t, true);
});
window.matchMedia("(max-width:600px)").addEventListener("change", () => {
  if (cachedPage && current?.view === "dashboard")
    $(".workspace-content").innerHTML = overview(cachedPage);
  else if (cachedPage && current?.view === "detail")
    $(".workspace-content").innerHTML = details(cachedPage);
});
window.addEventListener("tikflowso:locale", async () => {
  syncNavigation();
  if(meta.date)resourceLinks();
  const liveForms = ["tools","creative","agent","monitor","favorites","account","admin","api","resources"];
  if (!current || !meta.date) return;
  if (liveForms.includes(current.view)) {
    // Keep active file uploads, unsent inputs, and edited media mounted.
    const header = document.querySelector(".page-heading");
    if (header) header.outerHTML = heading(current.view);
    return;
  }
  const oldRoute = location.hash;
  const draftSelector = current.view === "inspiration" ? "#idea-subject" : ".workspace-content input[name=q]";
  const draft = document.querySelector(draftSelector)?.value;
  await render();
  const field = document.querySelector(draftSelector);
  if (location.hash === oldRoute && field && draft !== undefined) field.value = draft;
});
window.addEventListener("hashchange", () => {
  window.scrollTo(0, 0);
  render();
});
render();
