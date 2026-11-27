"""Explainable local review labels and weekly baseline forecasts over observed daily facts."""
from collections import Counter
from datetime import timedelta
import re

import analytics

WORDS = {
    "positive": ("喜欢","满意","好用","好看","舒服","耐用","推荐","清晰","方便","优秀","精致","好评","完好","符合预期",
                 "love","loved","great","good","excellent","durable","comfortable","recommend","perfect","easy"),
    "negative": ("失望","难用","难看","破损","坏了","漏水","退货","差评","糟糕","劣质","太贵",
                 "bad","poor","broken","disappointed","terrible","leaks","expensive","uncomfortable","hate"),
}
TOKENS = re.compile("|".join(
    word if not word.isascii() else r"\b"+word+r"\b"
    for word in sorted(sum(WORDS.values(),()),key=len,reverse=True)),re.I)
NEGATION = re.compile(r"(?:不太|不够|没有|不|没|并非|(?:\bnot|\bnever|n't)(?:\s+very)?\s+)$",re.I)


def sentiment(reviews):
    labels=[]
    for review in reviews:
        text=review["text"].casefold()
        signals={"positive":[], "negative":[]}
        for m in TOKENS.finditer(text):
            term=m.group()
            pos=term in WORDS["positive"]
            neg=NEGATION.search(text[:m.start()])
            if neg: pos=not pos
            signals["positive" if pos else "negative"].append((neg.group() if neg else "")+term)
        present=[k for k,words in signals.items() if words]
        label="mixed" if len(present)==2 else present[0] if present else "unknown"
        labels.append({"label":label,"signals":list(dict.fromkeys(signals["positive"]+signals["negative"]))})
    return {"method":"zh-en-lexicon-v1","counts":dict(Counter(r["label"] for r in labels)),"reviews":labels}


def study(db,params):
    scope=analytics.scope_for(db,params)
    group=params.get("group","tag")
    if group not in ("category","tag","music","keyword","script"): raise ValueError("趋势类型无效")
    topic=params.get("topic","")
    end=analytics.iso_day(scope["date"])
    dates=[(end-timedelta(days=i)).isoformat() for i in reversed(range(28))]
    args={**scope,"begin":dates[0],"kind":"products" if group=="category" else "videos","topic":topic}
    condition=f" AND {group}=:topic" if topic else ""
    rows=analytics.sum_rows(db,f"""SELECT date,SUM(gmv_units),SUM(sales),COUNT(DISTINCT id) FROM analytics_daily
                      WHERE source=:source AND market=:market AND kind=:kind AND date BETWEEN :begin AND :date
                      {condition} GROUP BY date ORDER BY date""",args)
    cents = {stamp:amount for stamp,amount,_,_ in rows}
    daily={stamp:{"gmv":amount/100,"sales":sales,"objects":objects,**analytics.exact_amounts(gmv=amount)}
           for stamp,amount,sales,objects in rows}
    missing=[stamp for stamp in dates if stamp not in daily]
    horizon=[]
    mae=None
    if all(stamp in daily for stamp in dates[-14:]):
        comparable = list(zip(dates[-7:], dates[-14:-7]))
        error_cents = analytics.average_cents(sum(abs(cents[a]-cents[b]) for a,b in comparable), 7)
        mae={"gmv":error_cents/100,"sales":round(sum(abs(daily[a]["sales"]-daily[b]["sales"]) for a,b in comparable)/7,2),
             **analytics.exact_amounts(gmv=error_cents)}
        for n,stamp in enumerate(dates[-7:],1):
            horizon.append({"date":(end+timedelta(days=n)).isoformat(),
                            **{k:v for k,v in daily[stamp].items() if k!="objects"}})
    return {**scope,"group":group,"topic":topic,"method":"weekly-naive-v1","sample_start":dates[0],
            "observed_days":len(daily),"missing_dates":missing,"mae":mae,"forecast":horizon,
            "series":[{"date":d,"gmv":None,"sales":None,"objects":None,**daily.get(d,{})} for d in dates]}
