import {localMessage, localeTag} from './locale.js';

function evidenceTable(snapshot, esc) {
  const current = snapshot.current, previous = snapshot.previous;
  const complete = [current,previous].every(p => p.covered_days === snapshot.days);
  const dateRange = (start,end) => '<small>' + esc(start + ' – ' + end) + '</small>';
  const numbers = new Intl.NumberFormat(localeTag());
  const currency = new Intl.NumberFormat(localeTag(),{style:'currency', currency:snapshot.currency,
    currencyDisplay:'code', minimumFractionDigits:2, maximumFractionDigits:2});
  const value = (n,monetary) => {
    if (n == null) return '—';
    if (!monetary) return esc(numbers.format(BigInt(n)));
    const [whole,fraction] = String(n).split('.');
    return esc(currency.formatToParts(BigInt(whole)).map(p => p.type==='fraction' ? fraction : p.value).join(''));
  };
  const row = (label,key) => {
    const monetary = key !== 'sales';
    const a = monetary ? current[key] : current.sales_exact;
    const b = monetary ? previous[key] : previous.sales_exact;
    let change = '—';
    if (complete && a != null && b != null) {
      const aa=BigInt(String(a).replace('.','')), bb=BigInt(String(b).replace('.',''));
      if (bb) {
        const delta = aa-bb;
        const tenths = ((delta<0n ? -delta : delta)*1000n+bb/2n)/bb;
        change = (delta<0n ? '−' : delta>0n ? '+' : '')+(tenths/10n)+'.'+(tenths%10n)+'%';
      }
    }
    return '<tr><th>' + localMessage(label) + '</th><td>' + value(a,monetary) + '</td><td>' +
      value(b,monetary) + '</td><td>' + change + '</td></tr>';
  };
  const coverage = p => esc(p.covered_days + '/' + snapshot.days);
  const estimate = current.estimated || previous.estimated ? '<small data-ui-label>含来源估算</small>' : '';
  return '<div class="table-wrap"><table class="records" data-decision-comparison><thead><tr><th>' +
    localMessage('指标') + '</th><th>' + localMessage('本期') + '<br>' + dateRange(snapshot.start_date,snapshot.date) +
    '</th><th>' + localMessage('上期') + '<br>' + dateRange(snapshot.prev_date,snapshot.previous_end) +
    '</th><th>' + localMessage('环比') + '</th></tr></thead><tbody>' + row('销量','sales') + row('成交额','gmv') +
    row('成交均价','avg_price') + '<tr><th>' + localMessage('覆盖天数') + '</th><td>' + coverage(current) +
    '</td><td>' + coverage(previous) + '</td><td>—</td></tr></tbody></table></div>' + estimate +
    (complete ? '' : '<p class="muted" data-ui-label>日快照不完整，环比不可比。</p>');
}

function videoEvidence(s, esc) {
  const label = localMessage('窗口内关联视频');
  const links = s.videos.map(v => {
    const params = new URLSearchParams({source:s.source, market:s.market, date:s.date, days:s.days, kind:'videos', id:v.id});
    return '<li><a data-source-text href="#detail?' + esc(params.toString()) + '">' + esc(v.name) +
      '</a> <small>' + esc(v.first_seen + ' – ' + v.last_seen + ' · ' + v.linked_days + 'd') + '</small></li>';
  });
  return '<details><summary>' + label + ' (' + s.videos.length + '/' + s.video_count + ')</summary>' +
    (links.length ? '<ul>' + links.join('') + '</ul>' : '<p data-ui-label>来源未记录关联视频。</p>') + '</details>';
}

export function decisionForm(data, esc) {
  const s = data.decision_evidence;
  if (!s) return '';
  return '<section class="panel tf-panel" data-decision-panel><h2>选品判断</h2>' +
    evidenceTable(s,esc) + videoEvidence(s,esc) + '<form class="tf-form" id="research-decision">' +
    '<label><span>入选或暂缓的理由</span><textarea required maxlength="1200" rows="2" name="reason">' +
    esc(data.decisionDraft || '') + '</textarea></label><div><button class="btn" type="submit"' +
    (data.decisionPending && data.decisionPending.reason === data.decisionDraft.trim() ? ' disabled' : '') +
    '>保存选品判断</button> ' +
    '<a class="text-link" href="#favorites">查看已保存的判断</a></div><output aria-live="polite" data-ui-label>' +
    (data.decisionSaved ? localMessage('选品判断已保存') : '') + '</output></form></section>';
}

export async function submitDecision(form, data, api, activePage) {
  const s = data.decision_evidence, reason = form.elements.reason.value.trim();
  if (!reason) { form.elements.reason.focus(); return; }
  if (data.decisionRequest?.reason !== reason) {
    const bytes = crypto.getRandomValues(new Uint8Array(16));
    data.decisionRequest = {reason, key:Array.from(bytes, n => n.toString(16).padStart(2,'0')).join('')};
  }
  data.decisionDraft = reason;
  const request = data.decisionRequest;
  if (data.decisionPending === request) return;
  data.decisionPending = request;
  const button = form.querySelector('button');
  button.disabled = true;
  const status = (saved,message) => {
    if (data.decisionRequest !== request || data.decisionDraft.trim() !== reason) return;
    data.decisionSaved = saved;
    if (activePage() === data) {
      const output = document.querySelector('#research-decision output');
      if (output) output.textContent = localMessage(message);
    }
  };
  try {
    await api('research-decisions',{request_key:request.key,source:s.source,market:s.market,
      date:s.date,days:s.days,product:s.product,version:s.version,reason},true);
    status(true,'选品判断已保存');
  } catch (err) {
    status(false,err.message);
  } finally {
    if (data.decisionPending === request) {
      delete data.decisionPending;
      if (activePage() === data) {
        const current = document.querySelector('#research-decision button[type="submit"]');
        if (current) current.disabled = false;
      }
    }
    // A newer request can use the same form after the detail panel redraws.
    if (!data.decisionPending) button.disabled = false;
  }
}

export function decisionHistory(page, esc) {
  if (!page.items.length) return '';
  const rows = page.items.map(row => {
    const s = row.evidence;
    return '<article class="tf-panel" data-decision-record="' + row.id + '"><h3 data-source-text>' + esc(s.name) +
      '</h3><small>' + esc([s.source,s.market,s.product,new Date(row.created*1000).toISOString().slice(0,16)+' UTC'].join(' · ')) +
      '</small><p data-source-text>' + esc(row.reason) + '</p><details><summary>保存时的依据</summary>' +
      evidenceTable(s,esc) + videoEvidence(s,esc) + '<small>' + localMessage('证据版本') + ' ' + esc(s.version.slice(0,12)) +
      '</small> <button class="btn" data-download-decision="' + row.id + '">下载判断依据</button></details>' +
      '<button class="btn" data-compare-decision="' + row.id + '">复核当前数据</button>' +
      '<div aria-live="polite" data-current-decision></div></article>';
  });
  return rows.join('') + (page.next ? '<button class="btn" data-older-decisions="' + page.next + '">更早的判断</button>' : '');
}

export async function reviewDecision(button,get,esc) {
  button.disabled = true;
  try {
    if (button.hasAttribute('data-download-decision')) {
      const id = button.dataset.downloadDecision;
      const stored = await get('research-decisions?saved=1&id='+encodeURIComponent(id));
      const url = URL.createObjectURL(new Blob([JSON.stringify(stored,null,2)],{type:'application/json'}));
      const link = document.createElement('a');
      link.href=url;
      link.download='tikflowso-decision-'+id+'.json';
      link.click();
      setTimeout(()=>URL.revokeObjectURL(url),1000);
      return;
    }
    if (button.hasAttribute('data-older-decisions')) {
      const next = await get('research-decisions?before='+encodeURIComponent(button.dataset.olderDecisions));
      button.insertAdjacentHTML('beforebegin',decisionHistory(next,esc));
      button.remove();
      return;
    }
    const result = await get('research-decisions?id='+encodeURIComponent(button.dataset.compareDecision));
    const message = !result.current ? '当前窗口已无此商品记录。' : result.changed ? '依据已更新' : '与保存时一致';
    button.nextElementSibling.innerHTML = '<p data-ui-label>' + localMessage(message) + '</p>' +
      (result.changed && result.current ? evidenceTable(result.current,esc)+videoEvidence(result.current,esc) : '');
  } catch (err) {
    button.textContent = localMessage(err.message);
  } finally { button.disabled = false; }
}
