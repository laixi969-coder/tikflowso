import { renderTools } from "./tools.js";
import { localeTag, displayDate, localMessage } from "./locale.js";

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
  (icons[name] || "") +
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
  api: "开放 API",
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
  ["工具与服务", ["agent", "tools", "api", "resources"]],
];
const metricNames = {
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
const currencySymbol = { USD: "$", GBP: "£", IDR: "Rp", MYR: "RM", EUR: "€" };
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
  overviewTab = "products",
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
              icon(k === "markets" ? "globe" : k, 17) +
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
    dashboard: "跟踪 TikTok Shop 的销售表现、品类变化与热门商品。",
    products: "发现热销商品，比较成交表现与增长速度。",
    shops: "研究本地与跨境店铺的销售表现。",
    creators: "按成交、观看与粉丝增长寻找合作达人。",
    videos: "比较带货短视频与图文内容的市场表现。",
    lives: "查看直播场次的观看与成交表现。",
    categories: "按商品成交额研究品类结构，进入对应商品库。",
    trends: "从话题、音乐和关键词中发现热门内容。",
    inspiration: "从脚本和代表内容中寻找下一条创作方向。",
  };
  const usesScope = !["account", "admin", "favorites", "monitor", "api", "resources"].includes(view);
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
          '</small></span></a></td><td><span class="category-chip">' +
          esc(r.category || "—") +
          '</span></td><td class="num"><b>' +
          money(r.gmv, currency) +
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
  const fmt = value => metric === "gmv" ? money(value, currency) : compact(value);
  const points = observed.map(point => ({
    x:xFor(Date.parse(point.date)), y:yFor(point[metric]), date:point.date, value:point[metric]
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
      '<circle class="chart-target" cx="'+p.x+'" cy="'+p.y+'" r="9"><title>'+esc(p.date+' · '+fmt(p.value))+'</title></circle></g>').join('');
  return '<svg class="plot" viewBox="0 0 '+width+' '+height+'" role="img" aria-label="'+esc(metricNames[metric])+'逐日走势"><defs><linearGradient id="fillplot" x1="0" x2="0" y1="0" y2="1"><stop offset="0%" stop-color="#c4f495" stop-opacity=".38"/><stop offset="100%" stop-color="#c4f495" stop-opacity=".015"/></linearGradient></defs>'+horizontal+paths+marks+dates+'</svg>';
}
function chartPanel(rows, currency, title = "市场成交走势") {
  return (
    '<section class="chart-card"><div class="panel-head"><div><span class="section-kicker">每日数据 · ' +
    esc(currency) +
    "</span><h2>" +
    title +
    '</h2></div><div class="chart-metrics">' +
    optionField(
      "趋势指标",
      "chart",
      { gmv: "GMV", sales: "销量", views: "观看次数" },
      chartMetric,
    ) +
    "</div></div>" +
    chart(rows || [], chartMetric, currency) +
    '<div class="chart-foot"><span><i></i>' +
    esc(metricNames[chartMetric]) +
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
          (k === "gmv" ? money(metrics[k], currency) : compact(metrics[k], 2)) +
          '</div><div class="kpi-comparison">' +
          delta(changes?.[k]) +
          "<span>较上一周期</span></div></div>",
      )
      .join("") +
    "</div>"
  );
}
function overview(data) {
  const rows = data.rankings[overviewTab] || [];
  return (
    kpi(data.metrics, data.changes, data.currency) +
    '<div class="dashboard-charts">' +
    chartPanel(data.trend, data.currency) +
    categoryPanel(data.categories) +
    '</div><section class="panel leaderboard"><div class="panel-head"><div><span class="section-kicker">TOP 5 · 按成交额</span><h2>市场排行榜</h2></div><a href="#' +
    overviewTab +
    '" class="text-link">完整榜单 ' +
    icon("arrow", 15) +
    '</a></div><div class="tabs">' +
    Object.entries(kinds)
      .map(
        ([k, n]) =>
          '<button data-rank="' +
          k +
          '" aria-pressed="' +
          (k === overviewTab) +
          '" class="' +
          (k === overviewTab ? "active" : "") +
          '">' +
          n +
          "</button>",
      )
      .join("") +
    "</div>" +
    recordList(rows, data.currency, overviewTab) +
    "</section>"
  );
}
function library(view, data, p) {
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
    optionField(
      "品类",
      "category",
      {
        "": "全部品类",
        ...Object.fromEntries((meta.categories || []).map((c) => [c, c])),
      },
      p.category || "",
    ) +
    optionField(
      "排序方式",
      "sort",
      sorts,
      p.sort || (p.segment === "breakout" ? "growth" : "gmv"),
    ) +
    "</div>" +
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
    "</h2><p>" +
    esc(r.subtitle || r.id) +
    '</p></div><div class="profile-actions"><button class="btn" data-save>' +
    icon("favorites", 15) +
    "加入收藏</button>" +
    (r.kind === "creators" ? '<a class="btn" href="' + esc(href("tools", { tool: "contacts", id: r.id, ...scopeParams(), date: data.date })) + '">' + icon("creators", 15) + '合作联系簿</a>' : '') +
    (["products", "videos", "lives"].includes(r.kind)
      ? '<button class="primary" data-monitor>' +
        icon("monitor", 15) +
        "加入监控</button>"
      : "") +
    '</div></div><div class="detail-stats">' +
    [
      ["成交额", money(r.gmv, data.currency, false)],
      ["销量", number(r.sales)],
      ["观看次数", number(r.views)],
      ["成交额环比", delta(r.growth)],
    ]
      .map(
        ([l, v]) =>
          "<div><small>" + l + "</small><strong>" + v + "</strong></div>",
      )
      .join("") +
    '</div></section><div class="detail-charts">' +
    chartPanel(data.trend, data.currency, "每日表现") +
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
      ["价格", r.price == null ? "" : money(r.price, data.currency, false)],
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
    relatedCards(data.related) +
    "</section>" +
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
          money(r.gmv, r.currency) +
          (r.includes_estimates?' <small data-ui-label>含来源估算</small>':'')+
          "</b> <small>" +
          esc(r.currency) +
          '</small></td><td class="num">' +
          money(r.avg_price, r.currency, false) +
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
              money(b.min, d.currency, false) +
              " – " +
              money(b.max, d.currency, false) +
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
      facts([
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
              money(r.gmv, data.currency) +
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
    ? "未来 7 日沿用上周同曜日的观测值。最近 7 日回测平均绝对误差："+money(study.mae.gmv,study.currency,false)+" / "+number(study.mae.sales)+" 件。"
    : "最近 14 日记录不连续，暂缺预测。";
  const english=localeTag()==="en-US";
  const method=english?(study.forecast.length?"Next 7 days use the last observed value for the same weekday. Previous 7-day backtest MAE: "+money(study.mae.gmv,study.currency,false)+" / "+number(study.mae.sales)+" units.":localMessage(caption)):caption;
  const outlook='<section class="panel"><div class="panel-head"><h2>趋势预测与采样覆盖</h2></div><div class="panel-body">'+
    '<p>'+esc(study.topic||(english?"Market total":"所选市场整体"))+' · '+esc(study.sample_start)+' — '+esc(study.date)+(english?' · Observed ':' · 已观测 ')+study.observed_days+(english?'/28 days</p>':'/28 天</p>')+
    '<p>'+esc(method)+'</p>'+(study.missing_dates.length?'<details><summary data-ui-label>缺失日期</summary>'+esc(study.missing_dates.join("、"))+'</details>':'')+
    (study.forecast.length?'<div class="table-wrap"><table class="records"><thead><tr><th>预测日期</th><th>预估 GMV</th><th>预估销量</th></tr></thead><tbody>'+study.forecast.map(r=>'<tr><td>'+esc(r.date)+'</td><td>'+money(r.gmv,study.currency,false)+'</td><td>'+number(r.sales)+'</td></tr>').join('')+'</tbody></table></div>':'')+'</div></section>';
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
    esc(href(view, { group })) +
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
    '<button class="primary">搜索</button></form></section>'
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
    sourceUI();
    mount.innerHTML =
      heading(view) +
      '<div class="workspace-content"><div class="loading">正在读取数据…</div></div>';
    const content = mount.querySelector(".workspace-content");
    if (
      [
        "tools",
        "agent",
        "monitor",
        "favorites",
        "account",
        "admin",
        "api",
        "resources",
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
      data = await api("overview", scopeParams());
      html = overview(data);
    } else if (view === "markets") {
      data = await api("markets", {
        ...scopeParams(),
        date: scope.date || meta.date,
      });
      html = marketsTable(data);
    } else if (kinds[view]) {
      data = await api("rankings", {
        ...scopeParams(),
        kind: view,
        q: p.q,
        match: p.match||"broad",
        sort: p.sort,
        category: p.category,
        segment: p.segment,
        page: p.page || 1,
        limit: 10,
      });
      html = library(view, data, p);
    } else if (view === "detail") {
      data = await api("detail", { ...scopeParams(), kind: p.kind, id: p.id });
      html = details(data);
    } else if (view === "search") html = await searched(p);
    else html = await trendView(view, p);
    if (id !== renderId) return;
    content.innerHTML = html;
    cachedPage = data;
  } catch (e) {
    if (id !== renderId) return;
    mount.innerHTML =
      heading(view) +
      '<section class="panel error">' +
      showEmpty(e.message || "数据加载失败") +
      '<div class="error-actions"><button data-retry class="btn">重新加载</button><a class="text-link" href="#dashboard">返回概览</a></div></section>';
  }
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
$("#menu-btn").onclick = () => document.body.classList.toggle("nav-open");
$("#veil").onclick = () => document.body.classList.remove("nav-open");
$("#search-button").onclick = openSearch;
$("#close-search").onclick = () => $("#search-dialog").close();
$("#global-search").onsubmit = (e) => {
  e.preventDefault();
  const q = $("#query").value.trim();
  if (!q) return;
  $("#search-dialog").close();
  location.hash = href("search", { q });
};
document.addEventListener("keydown", (e) => {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
    e.preventDefault();
    openSearch();
  }
  if (e.key === "Escape") document.body.classList.remove("nav-open");
});
$("#app").addEventListener("change", (e) => {
  const t = e.target;
  if (t.dataset.scope) {
    updateScope(t.dataset.scope, t.value);
    return;
  }
  const f = t.dataset.field;
  if (f === "chart" && cachedPage) {
    chartMetric = t.value;
    $(".workspace-content").innerHTML =
      current.view === "detail" ? details(cachedPage) : overview(cachedPage);
  } else if (f === "match") {
    const search = document.querySelector(current.view === 'search' ? '#search-page [name=q]' : '#list-search [name=q]');
    change({match:t.value,q:search?.value.trim()||'',page:1});
  } else if (f === "category" || f === "sort") {
    change({ [f]: t.value, page: 1 });
  } else if (f === "search-kind" && current.params.q) {
    change({ kind: t.value });
  }
});
$("#app").addEventListener("submit", (e) => {
  const f = e.target;
  if (f.id === "list-search") {
    e.preventDefault();
    change({ q: f.elements.q.value.trim(), page: 1 });
  } else if (f.id === "search-page") {
    e.preventDefault();
    location.hash = href("search", {
      q: f.elements.q.value.trim(),
      kind: f.querySelector('[data-field="search-kind"]').value,
      match: f.querySelector('[data-field="match"]').value,
    });
  }
});
$("#app").addEventListener("click", (e) => {
  const t = e.target.closest("button");
  if (!t) return;
  if (t.hasAttribute("data-rank") && cachedPage) {
    overviewTab = t.dataset.rank;
    $(".workspace-content").innerHTML = overview(cachedPage);
  } else if (t.hasAttribute("data-segment"))
    change({
      segment: t.dataset.segment,
      sort: t.dataset.segment === "breakout" ? "growth" : current.params.sort,
      page: 1,
    });
  else if (t.dataset.page) change({ page: t.dataset.page });
  else if (t.hasAttribute("data-retry")) render();
  else if (t.hasAttribute("data-queue-export") || (t.hasAttribute("data-export") && cachedPage?.total>1000)) queueExport(t);
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
  const liveForms = ["tools","agent","monitor","favorites","account","admin","api","resources"];
  if (!current || !meta.date) return;
  if (liveForms.includes(current.view)) {
    // Keep active file uploads, unsent inputs, and edited media mounted.
    const header = document.querySelector(".page-heading");
    if (header) header.outerHTML = heading(current.view);
    return;
  }
  const oldRoute = location.hash;
  const draft = document.querySelector(".workspace-content input[name=q]")?.value;
  await render();
  const field = document.querySelector(".workspace-content input[name=q]");
  if (location.hash === oldRoute && field && draft !== undefined) field.value = draft;
});
window.addEventListener("hashchange", () => {
  window.scrollTo(0, 0);
  render();
});
render();
