// Deterministic factual checks. Reference identity and answer text are inspected independently.
const numeric = /-?\d+(?:,\d{3})*(?:\.\d+)?/g;
const values = s => [...s.matchAll(numeric)].map(m => Number(m[0].replaceAll(',','')));
const escapeRE = s => s.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
const moneyCodes = /\b[A-Z]{3}\b/g;
const currencies = new Set(Intl.supportedValuesOf('currency'));
const missing = /no comparable|insufficient|lack|unavailable|no .{0,30}(data|snapshot|record|baseline)|not enough|cannot .{0,30}(compar|calculat)|缺少|不足|未.{0,8}(记录|提供)|没有|不可比|无法/iu;
const amount = '(-?\\d+(?:,\\d{3})*(?:\\.\\d+)?(?:e[+-]?\\d+)?)';
const magnitude = '(?:\\s*(thousand\\b|million\\b|billion\\b|[kmb]\\b|[千万亿]))?';
const unit = '(?:USD|GBP|CNY|RMB|美元|英镑|人民币|元|[$£¥￥])';
const scales = {thousand:1000,million:1e6,billion:1e9,k:1000,m:1e6,b:1e9,'千':1000,'万':1e4,'亿':1e8};
const amountValue = (value,scale) => Number(value.replaceAll(',',''))*(scales[scale?.toLowerCase()]||1);

function checks(output, vars) {
  const answer = typeof output === 'string' ? JSON.parse(output) : output;
  const {truth:t, scope:s, language} = vars;
  const failures=[];
  const check=(valid,reason)=>{ if(!valid) failures.push(reason); };
  if(t.type==='denied') {
    check(answer.status===403 && !answer.result && !(answer.references||[]).length,'private source must return HTTP 403 with no answer or citations');
    const body = JSON.stringify(answer).toLowerCase();
    check((t.privateMarkers||[]).every(marker=>!body.includes(String(marker).toLowerCase())),
      'private source fact leaked in denial body');
    return failures;
  }
  if(answer.status!==200) return ['Unexpected HTTP '+answer.status];
  const text=answer.result||'', refs=answer.references||[];
  check(Object.keys(s).every(k=>String(answer.scope?.[k])===String(s[k])),'wrong effective research scope');
  check(vars.candidate ? /^(Model · database query|模型 · 数据库查询)$/.test(answer.mode) :
    ['数据库查询','Database query'].includes(answer.mode),'wrong inference mode or candidate fell back to local');
  check(language==='zh-CN'?/[\u3400-\u9fff]/u.test(text):/[a-z]{3}/iu.test(text)&&!/[\u3400-\u9fff]/u.test(text),'requested answer language absent');

  const target=(href,label,isBody=false)=>{
    try{
      const hash=new URL(href,'http://local.invalid').hash;
      const [path,query]=hash.split('?'), params=new URLSearchParams(query);
      const keys=t.type==='ranking'?[...Object.keys(s),'kind','id']:Object.keys(s);
      if([...params.keys()].some(key=>!keys.includes(key)||params.getAll(key).length!==1))return false;
      const validScope=Object.entries(s).every(([k,v])=>params.getAll(k).length===1 && params.get(k)===String(v));
      const validRoute=t.type==='overview'?path==='#dashboard':t.type==='ranking'&&path==='#detail'&&
        params.get('kind')===t.kind&&t.rows.some(r=>r.id===params.get('id')&&(isBody||r.label===label));
      return href.startsWith('#') && validScope && validRoute;
    }catch{return false;}
  };
  check(Array.isArray(refs),'invalid references');
  for(const ref of refs)check(target(ref.href,ref.label),'wrong citation source, scope, route, label or object');
  const inline = /#[a-z][a-z0-9_-]*\?[^\s\])>，。；]+/gi;
  for(const m of text.matchAll(inline))check(target(m[0].replaceAll('&amp;','&'),'',true),'wrong inline citation');
  check(!/https?:\/\//i.test(text),'external link presented in a closed-source answer');
  const prose=text.replace(inline,'');
  const withoutWindow=s=>s.replace(/\d{4}-\d{2}-\d{2}/g,'').replace(/\d+\s*[- ]?\s*(?:days?\b|天)/giu,'');
  const dates=prose.match(/\d{4}-\d{2}-\d{2}/g)||[];
  const start=new Date(s.date+'T00:00:00Z');start.setUTCDate(start.getUTCDate()-s.days+1);
  check(dates.every(d=>[s.date,start.toISOString().slice(0,10)].includes(d)),'claim about a date outside the requested window');
  if(t.type!=='empty'){
    const markets={US:/\bUS\b|United States|美国/iu,GB:/\b(?:GB|UK)\b|United Kingdom|英国/iu,CN:/\bCN\b|China|中国/iu};
    check(markets[s.market].test(prose) && Object.entries(markets).every(([m,re])=>m===s.market||!re.test(prose)),'incorrect/missing stated market');
    check(dates.includes(s.date),'missing stated cutoff date');
    check(new RegExp('(?:^|[^0-9])'+s.days+'\\s*[- ]?\\s*(?:days?|天)','iu').test(prose)||
      (s.days>1&&dates.includes(start.toISOString().slice(0,10))),'missing/incorrect period length');
  }
  const numbers=values(prose.replace(/\d{4}-\d{2}-\d{2}/g,'').replace(/^\s*\d+[.)、]\s*/gm,''));
  const allowed=new Set([s.days]);
  const codes=(prose.match(moneyCodes)||[]).filter(x=>currencies.has(x));
  const currency=t.currency||({US:'USD',GB:'GBP',CN:'CNY'})[s.market];
  check(codes.every(x=>x===currency),'wrong currency');
  for(const [symbol,code] of [['$','USD'],['£','GBP'],['¥','CNY'],['￥','CNY']])
    if(prose.includes(symbol))check(code===currency,'wrong currency symbol');
  const expectedAmounts = t.type==='overview'?[t.gmv]:t.type==='ranking'&&t.metric==='gmv'?t.rows.map(r=>r.value):[];
  // Test both "USD 12" and "12 USD". A following comma belongs to the next independent clause.
  const decorated=[...prose.matchAll(new RegExp(unit+'\\s*'+amount+magnitude+'|'+amount+magnitude+'\\s*'+unit,'gi'))];
  check(decorated.every(m=>expectedAmounts.includes(amountValue(m[1]??m[3],m[2]??m[4]))),'invented monetary amount');
  const gmvClaims=[...prose.matchAll(new RegExp('(?:GMV|成交额)\\s*(?:为|是|of|is|was|[:：=])?\\s*'+amount+magnitude,'gi'))];
  check(gmvClaims.every(m=>expectedAmounts.includes(amountValue(m[1],m[2]))),'unsupported GMV claim');
  for(const [name,code] of [['美元','USD'],['英镑','GBP'],['人民币','CNY'],['RMB','CNY']])
    if(prose.includes(name))check(currency===code,'wrong named currency');
  check(!/[零〇一二两三四五六七八九十百千万亿点]+(?:美元|英镑|人民币|元)/u.test(prose.replace(/\d\s*[千万亿](?=元)/gu,'')),
    'monetary claim written in Chinese numerals needs review');
  if(t.type==='empty'){
    check(missing.test(prose),'did not explain the data gap');
    check(refs.length===0,'missing evidence must not produce citations');
    check(values(withoutWindow(prose)).length===0,'missing observations reported as a numeric measurement');
  }else if(t.type==='overview'){
    allowed.add(t.gmv);allowed.add(t.units);
    check(refs.length===1,'missing or duplicated market citation');
    check(codes.includes(currency)||prose.includes(({USD:'$',GBP:'£',CNY:'¥'})[currency]),'missing currency unit');
    check(numbers.includes(t.gmv) && numbers.includes(t.units),'missing ledger GMV or units');
    const unitsText = [...prose.matchAll(/(-?\d[\d,]*(?:\.\d+)?)\s*(?:units(?: sold)?|件)|(?:销量(?:为|是)?|units sold)\s*[:：]?\s*(-?\d[\d,]*(?:\.\d+)?)/gi)];
    check(unitsText.length>0 && unitsText.every(m=>Number((m[1]??m[2]).replaceAll(',',''))===t.units),
      'missing or contradictory units sold');
    check(decorated.length>0,'GMV must carry native currency');
  }else if(t.type==='ranking'){
    check(refs.length===t.rows.length,'incorrect citation count');
    const metrics={gmv:/\bGMV\b|成交额|gross merchandise value/i,sales:/\b(?:units|sales)\b|销量|件数|售出/i,
      views:/\bviews?\b|播放|观看/i,growth:/growth|change|增长|环比/i};
    check(metrics[t.metric].test(prose),'ranking metric is absent or incorrect');
    const numbered=[...prose.matchAll(/^\s*(\d+)[.)、]\s*([^\n]*)/gm)];
    if(numbered.length)check(numbered.length===t.rows.length && numbered.every((m,i)=>
      Number(m[1])===i+1 && m[2].includes(t.rows[i].label)),'unsupported rows or incorrect explicit ranks');
    if(t.metric==='gmv')check(codes.includes(currency)||prose.includes(({USD:'$',GBP:'£',CNY:'¥'})[currency]),'missing ranking currency');
    let previous=-1;
    for(const [index,r] of t.rows.entries()){
      allowed.add(r.value);
      // The stated value must accompany the right entity, not merely appear in the answer.
      const at=prose.indexOf(r.label);
      check(at>previous && at>=0,'incorrect or omitted ranking order: '+r.label);
      previous=at;
      if(refs[index])check(refs[index].label===r.label,'reference order differs from ground truth');
      const next=prose.slice(at+r.label.length).split(/\n|[;；]/)[0];
      const prefix=next.split(new RegExp(t.rows.filter(x=>x!==r).map(x=>escapeRE(x.label)).join('|')||'(?!)'))[0];
      const observed=values(withoutWindow(prefix));
      check(observed.length>0 && observed.every(value=>value===r.value),'missing or conflicting metric for '+r.label);
    }
  }
  check(numbers.every(n=>allowed.has(n)),'unsupported numeric fact in answer');
  return failures;
}

module.exports=(output,context)=>{
  try {
    const failures=checks(output,context.vars);
    return {pass:!failures.length,score:failures.length?0:1,reason:failures.join(' / ')||'Scoped ledger and citations match'};
  }catch(err){return {pass:false,score:0,reason:'Malformed answer: '+err.message};}
};
module.exports.checks=checks;
