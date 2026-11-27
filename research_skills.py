"""Bounded, bilingual research recipes over the selected workspace's snapshots."""
import json
import re
from urllib.parse import urlencode

import analytics
from insights import sentiment


GROUPS = {
    "market": ("市场研究", "Market research"),
    "creator": ("达人分析", "Creator analysis"),
    "content": ("内容营销", "Content marketing"),
    "operations": ("运营策略", "Operations strategy"),
}

# group, source object, ranking metric, display names, editable starting questions
SKILLS = {
    "opportunity": ("market", "products", "sales", "需求与新品机会", "Unmet needs and product opportunities",
                    "比较热销商品的价格与销量，提出一个可以用访谈检验的新品假设。", "Compare product prices and units sold, then propose a new product hypothesis to test in interviews."),
    "trending": ("market", "products", "sales", "热门商品与带货潜力", "Trending products and creator sales",
                 "筛选热销商品，用关联达人和内容验证带货线索。", "Find bestsellers and examine linked creators and content for sales leads."),
    "growth": ("market", "products", "growth", "高增长商品与需求验证", "High-growth products and demand validation",
               "比较相邻周期的成交额，列出需要独立渠道复核的增长候选。", "Compare GMV across periods and shortlist growing products for independent demand validation."),
    "creator_growth": ("creator", "creators", "follower_growth", "涨粉达人与选品策略", "Fast-growing creators and product strategy",
                      "找出净增粉丝领先的达人，查看其关联商品和视频的内容形式。", "Find creators gaining followers and inspect the products and video formats they feature."),
    "creator_fit": ("creator", "creators", "sales", "新品合作达人筛选", "Creator selection for a launch",
                   "按每千次观看对应的销量筛选合作候选，列出询价和试投条件。", "Shortlist creators by units per thousand views and prepare a quote request and pilot."),
    "interest": ("creator", "creators", "sales", "评论反馈与购买兴趣", "Comment feedback and purchase interest",
                "分析我提供的评论，区分购买意向、疑问和情绪；没有评论时查看关联商品评价。", "Separate purchase signals, questions and sentiment in my pasted comments, or examine linked product reviews."),
    "video_script": ("content", "products", "sales", "15 秒带货视频脚本", "15-second product video script",
                    "为候选商品写 15 秒脚本，包含开场三秒、分镜、口播和配乐提示。", "Draft a 15-second product video with a three-second hook, timed shots, voiceover and music cues."),
    "image_prompts": ("content", "products", "sales", "商品系列图提示词", "Product image series prompts",
                      "为商品写四组主图提示词，覆盖白底、细节、场景和尺寸展示。", "Write four image prompts covering a packshot, detail, use scene and scale reference."),
    "community": ("content", "products", "sales", "社区推广短文", "Community promotion copy",
                  "撰写社区推广短文，包含互动问题、可核实的商品信息和行动提示。", "Write a short community post with a question, a verifiable product detail and a call to action."),
    "shop_plan": ("operations", "shops", "sales", "店铺全周期运营计划", "Full-cycle shop plan",
                  "根据店铺与商品记录，制定选品、发布、引流和转化复盘计划。", "Use shop and product records to plan assortment, publishing, traffic and conversion checks."),
    "channel_plan": ("operations", "videos", "views", "多平台引流方案", "Cross-platform traffic plan",
                     "从当前视频出发，为 TikTok、Instagram 与 Facebook 设计引流和归因试验。", "Design a TikTok, Instagram and Facebook traffic and attribution experiment starting from a recorded video."),
    "creator_matrix": ("operations", "creators", "sales", "达人营销组合", "Influencer marketing matrix",
                       "对比达人，分配试投职责，规划谈判、内容共创和成交追踪。", "Compare creators and plan pilot roles, negotiations, co-creation and sales tracking."),
}


def catalog():
    return {"groups":[{"id":k,"zh":v[0],"en":v[1]} for k,v in GROUPS.items()],
            "items":[{"id":k,"group":g,"kind":kind,"title":{"zh":zh,"en":en},
                      "prompt":{"zh":qzh,"en":qen}} for k,(g,kind,_,zh,en,qzh,qen) in SKILLS.items()]}


def option(data, key, limit):
    value = data.get(key, "")
    if not isinstance(value, str) or len(value) > limit:
        raise ValueError(f"Invalid {key} (max {limit})")
    return value.strip()


def number(value):
    if value is None:
        return "—"
    return format(value, ",.2f").rstrip("0").rstrip(".")


def analyze(db, data, scope, english):
    t = lambda zh,en: en if english else zh
    key = data["skill"]
    if not isinstance(key,str) or key not in SKILLS:
        raise ValueError("未知研究模板 / Unknown research template")
    _, kind, sort, zh, en, default_zh, default_en = SKILLS[key]
    focus = option(data, "focus", 150)
    comments = option(data, "comments", 6000)
    resolved = analytics.scope_for(db,scope)
    shared = {key:resolved[key] for key in ("source","market","date","days")}
    rows = analytics.rows_for(db,resolved)
    candidates = [r for r in rows if r["kind"] == kind]
    matches = candidates
    if focus:
        by_id = [r for r in candidates if r["id"] == focus]
        matches = by_id or [r for r in candidates if any(focus.casefold() in str(r.get(k) or "").casefold()
                                                         for k in ("id","name","subtitle","category"))]
    elif data["text"] not in (default_zh,default_en):
        # An edited brief may name several records. Match complete IDs/names;
        # ordinary words in the rest of the brief are not a search filter.
        brief = data["text"].casefold()
        def named(label):
            label=label.casefold()
            if len(label)<2 or label not in brief:
                return False
            if label.isascii():
                return bool(re.search(r"(?<![a-z0-9_])"+re.escape(label)+r"(?![a-z0-9_])",brief))
            return True
        mentioned = [r for r in candidates if named(r["name"]) or named(r["id"])]
        if mentioned:
            matches = mentioned
    if key == "creator_fit":
        complete_views = {row[0] for row in db.execute("""SELECT id FROM analytics_daily WHERE
            source=:source AND market=:market AND kind='creators' AND date BETWEEN :start_date AND :date
            GROUP BY id HAVING COUNT(views)=COUNT(*) AND SUM(views)>0""",resolved)}
        shortlist = sorted((r for r in matches if r["id"] in complete_views),
                           key=lambda r:(-r["sales"]/r["views"],-r["sales"],r["id"]))[:3]
    else:
        shortlist = analytics.leaderboard(matches,kind,{"sort":sort},limit=3)
        shortlist = [r for r in shortlist if r[sort] is not None and
                     (key not in ("growth","creator_growth") or r[sort] > 0)]
    head = f"{t(zh,en)} · {resolved['source']} · {resolved['market']} · {resolved['start_date']} – {resolved['date']}"
    if shared["source"] == "demo":
        head += t(" · 合成演示数据"," · synthetic demo data")
    if not shortlist:
        if key == "interest" and comments:
            return head+"\n\n"+comment_report(comments.splitlines(), True, t), []
        return head+"\n\n"+t("符合筛选且指标可比较的记录为零。请修改对象筛选、来源或时间。","No qualifying records with comparable measurements. Change the focus, source or dates."), []
    refs = {}
    def cite(row):
        label = row["name"]
        href = "#detail?"+urlencode({**shared,"kind":row["kind"],"id":row["id"]})
        refs[href] = {"label":label,"href":href}
        return label

    currency = resolved["currency"]
    lines = [head,"",t("窗口内记录","Window observations")]
    for row in shortlist:
        columns = [(t("销量","units sold"),number(row["sales"])),("GMV",number(row["gmv"])+" "+currency)]
        if row["gmv_estimated"]:
            columns[1] = (t("含估算 GMV","GMV incl. estimates"),columns[1][1])
        if key in ("growth","trending") and row["growth"] is not None:
            columns.append((t("GMV 环比","GMV change"),number(row["growth"])+"%"))
        if kind == "products" and row["price"] is not None:
            columns.append((t("期末标价","closing price"),number(row["price"])+" "+currency))
        if kind == "creators" and row["follower_growth"] is not None:
            columns.append((t("净增粉丝","net new followers"),number(row["follower_growth"])))
        if kind in ("videos","creators") and row["views"] is not None:
            columns.append((t("观看","views"),number(row["views"])))
        if key == "creator_fit":
            columns.append((t("每千次观看销量","units / 1,000 views"),number(1000*row["sales"]/row["views"])))
        lines.append(cite(row)+" · "+" · ".join(f"{k} {v}" for k,v in columns)+
                     f" · {row['covered_days']}/{resolved['days']} "+t("天有快照","days observed"))

    lead = shortlist[0]
    name = lead["name"]
    related = analytics.related_to(lead,rows,db,resolved)
    def linked(target, count=2):
        return sorted((r for r in related if r["kind"] == target),key=lambda r:(-r["sales"],r["id"]))[:count]
    def relation(target):
        selected = linked(target)
        return "、".join(cite(r) for r in selected) or t("未记录","unrecorded")
    lines.append("")
    if key == "opportunity":
        priced=[r["price"] for r in shortlist if r["price"] is not None]
        if priced:
            span=f"{number(min(priced))}–{number(max(priced))} {currency}"
            lines.append(t(f"候选商品的期末标价范围 · {span}（{len(priced)} 款有标价）。",
                           f"Closing price range for the shortlist · {span} ({len(priced)} priced items)."))
        lines.append(t(f"新品假设 · 选取 {name} 作为访谈参照，请买家演示最麻烦的一步。按问题归类，再用两版样品验证最常见问题。销量是选样依据，未满足需求尚待访谈确认。",
                       f"Product hypothesis · Use {name} as the interview reference. Ask buyers to demonstrate their hardest step, group recurring problems, then test two prototypes against the most frequent problem. Sales guide sampling; unmet demand still needs buyer interviews."))
    elif key == "trending":
        creators, videos = relation("creators"),relation("videos")
        lines.append(t(f"{name} 的关联达人 · {creators}\n关联内容 · {videos}\n试投 · 联系关联达人，给新脚本分配独立链接，再与同商品原内容比较销量。",
                       f"Creators linked to {name} · {creators}\nLinked videos · {videos}\nPilot · Contact a linked creator and assign a unique link to a new script. Compare units sold against existing content for the same product."))
    elif key == "growth":
        lines.append(t(f"验证 {name} · 以等长前窗为基线，复查成交增长是否持续。补入独立渠道同款、同市场、同日期的销量后再验证外部需求。当前证据不含 Amazon 销量。",
                       f"Validate {name} · Recheck growth against the equal-length prior window in the next period. Match independent channel data by SKU, market and dates before drawing a cross-platform conclusion. No Amazon sales are present in these observations."))
    elif key == "creator_growth":
        products, videos = relation("products"), linked("videos")
        lines.append(t(f"{name} 的关联商品 · {products}",f"Products linked to {name} · {products}"))
        for video in videos:
            lines.append(cite(video)+" · "+(video["script"] or t("脚本类型未记录","script format unrecorded")))
        lines.append(t("复核 · 选一条关联视频复盘前三秒与商品出镜安排，再测试另一种开场；粉丝增长的具体来源待验证。",
                       "Review the first three seconds and product placement in one linked video, then test a different opening. Attribution of follower growth needs a separate test."))
    elif key == "creator_fit":
        lines.append(t(f"询价单 · 向 {name} 索取固定费、佣金率、样品及使用权报价。每千观看销量用于选取测试对象，实际获客成本须用谈妥费用与追踪订单计算。",
                       f"Quote request · Ask {name} for the fixed fee, commission, sample and usage rights. Units per thousand views guide the shortlist. Calculate actual acquisition cost from negotiated spend and tracked orders."))
    elif key == "interest":
        if comments:
            lines.append(comment_report(comments.splitlines(),True,t))
        else:
            reviews=[]
            for product in linked("products"):
                raw=db.execute("SELECT profile_json FROM analytics_daily WHERE source=? AND market=? AND kind='products' AND id=? AND date=?",
                               (resolved["source"],resolved["market"],product["id"],product["updated_at"])).fetchone()
                if raw and raw[0]:
                    product_reviews=json.loads(raw[0]).get("reviews",[])
                    if product_reviews:
                        cite(product)
                        reviews.extend(r["text"] for r in product_reviews)
            lines.append(comment_report(reviews,False,t))
    elif key == "video_script":
        lines.append(t(f"15 秒拍摄稿 · {name}\n0–3 秒｜商品特写。口播「想看 {name} 的细节吗？」第一拍切入轻快的授权音乐。\n3–9 秒｜手部展示实物，转动给镜头看，口播「先看这里，再看另一面。」音乐压低。\n9–12 秒｜停在实物标示上，按标签念出一条已核对的规格。\n12–15 秒｜定格商品全貌，口播「想看我测试哪一步？留言告诉我。」",
                       f"15-second shooting draft · {name}\n0–3 s | Product close-up. Say “Want a closer look at {name}?” Cut on the first beat of licensed upbeat music.\n3–9 s | Turn the real item in hand. Say “First this detail, then the other side.” Lower the music.\n9–12 s | Hold on its label and read one verified specification.\n12–15 s | Frame the whole item. Say “What should I test next? Tell me in the comments.”"))
    elif key == "image_prompts":
        lines.append(t(f"系列图拍摄提示词 · 以 {name} 的授权实物图为参考，四图保持同款、颜色和标识。\n1. 白底主图，正面三分之四机位，柔和阴影。\n2. 微距细节，侧光突出参考图确有的纹理。\n3. 使用场景，手部操作并留出文字区。\n4. 尺寸图，正侧双视图，用实测值后期标注。",
                       f"Image series · Use a licensed reference of {name}; preserve the exact item, color and marks in all four frames.\n1. White-background packshot, three-quarter front angle, soft shadow.\n2. Macro detail, raking light, texture visible in the reference.\n3. In-use context, hands operating the real item, room for copy.\n4. Size reference, front and side views, add measured dimensions in post."))
    elif key == "community":
        lines.append(t(f"社区短文草稿\n「你挑选 {name} 时最想先看什么？我们准备拍一段实物展示，近看细节，再回答大家关心的问题。你更想看哪一步？留言投票，或点商品页核对规格。」",
                       f"Community post draft\n“What would you check first on {name}? We’re filming a close-up of the real item and taking questions. Vote for the detail you want to see, or open the product page to check its specifications.”"))
    elif key == "shop_plan":
        products=relation("products")
        lines.append(t(f"店铺试行计划 · {name}\n选品：核实关联货盘（{products}）的库存与毛利，选一款试销。\n发布：先排两条不同开场的展示视频，保持价格一致。\n引流：分别分配追踪链接。\n复盘：按内容核对观看、成交、退款与履约；缺少字段时向店铺索取再扩量。",
                       f"Pilot for {name}\nAssortment: verify stock and margin for the linked assortment ({products}) and choose one pilot SKU.\nPublishing: schedule two demos with different hooks at the same price.\nTraffic: assign a separate tracking link to each.\nReview: reconcile views, orders, refunds and fulfillment by content. Obtain missing values before scaling."))
    elif key == "channel_plan":
        lines.append(t(f"渠道试验 · 以 {name} 为 TikTok 素材参照。剪一版 Instagram Reel，再把常见问题整理成 Facebook 社群帖。三个入口使用独立来源标记、同一落地页和商品；一周后按访问、复访和成交对账。其他平台的实际流量需另行接入。",
                       f"Channel pilot · Use {name} as the TikTok creative reference. Adapt a cut for Instagram Reels and a Q&A post for Facebook. Use distinct source tags and the same landing page and SKU. Reconcile visits, returning visitors and orders after one week. Traffic for the other platforms requires separate measurement."))
    elif key == "creator_matrix":
        roles=[t("首发演示","launch demo"),t("使用场景对照","use-case comparison"),t("答疑跟进","follow-up Q&A")]
        lines.extend(f"{cite(r)} · {role}" for r,role in zip(shortlist,roles))
        lines.append(t("谈判与复盘 · 分别协商样品、稿酬、佣金及素材使用期。每人交付一个开场和一条专属链接，按实际订单与费用对账，再决定续约。",
                       "Negotiation and review · Agree samples, fees, commission and usage term separately. Ask each creator for a hook and assign a unique link. Reconcile actual orders and fees before renewal."))
    return "\n".join(lines), list(refs.values())


BUY_SIGNAL = re.compile(r"哪里买|怎么买|想买|下单|链接|where (?:can i |to )?buy|buying|want to buy|order link|link please",re.I)


def comment_report(samples,pasted,t):
    texts=[str(s).strip() for s in samples if str(s).strip()]
    if not texts:
        return t("没有可用评论样本。可在模板中粘贴一行一条的已授权评论。","No comment samples are available. Paste authorized comments on separate lines in the template.")
    counts=sentiment([{"text":s} for s in texts])["counts"]
    buying=sum(bool(BUY_SIGNAL.search(s)) for s in texts)
    questions=sum(any(c in s for c in ("?","？")) for s in texts)
    title=t("粘贴的评论","Pasted comments") if pasted else t("关联商品评价（独立于达人评论）","Linked product reviews (separate from creator comments)")
    return (f"{title} · {len(texts)}\n"+
            t(f"含购买表达 {buying}，含问号 {questions}。词典情绪：正向 {counts.get('positive',0)}，负向 {counts.get('negative',0)}，混合 {counts.get('mixed',0)}，未识别 {counts.get('unknown',0)}。",
              f"Purchase-language matches {buying}, questions marked with ? {questions}. Lexicon sentiment: positive {counts.get('positive',0)}, negative {counts.get('negative',0)}, mixed {counts.get('mixed',0)}, unclassified {counts.get('unknown',0)}.")+
            "\n"+t("样本摘录","Sample excerpts")+"\n"+"\n".join("• "+s[:180] for s in texts[:3])+"\n"+
            t("购买表达需以实际下单复核。","Check expressed interest against actual orders."))
