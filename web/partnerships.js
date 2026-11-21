import { localMessage } from "./locale.js";
const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, c => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
})[c]);

async function request(endpoint, payload) {
  const options = payload === undefined ? {} : {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)
  };
  const response = await fetch('/api/partners' + endpoint, options);
  const result = await response.json();
  if (!response.ok) throw Error(result.error || '未能读取合作工作区');
  return result;
}

function csvDownload(name, headers, rows) {
  const cell = value => {
    let text = String(value ?? '');
    if (typeof value === 'string' && /^[\s]*[=+@-]/.test(text)) text = "'" + text;
    return '"' + text.replaceAll('"', '""') + '"';
  };
  const text = [headers, ...rows].map(row => row.map(cell).join(',')).join('\r\n');
  const href = URL.createObjectURL(new Blob(['\uFEFF' + text], {type: 'text/csv;charset=utf-8'}));
  const a = document.createElement('a');
  a.href = href;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(href), 1000);
}

const panel = (label, content) => '<section class="panel tf-panel"><h2>' + label + '</h2>' + content + '</section>';
const btn = (label, action) => '<button type="button" class="btn" data-action="' + action + '">' + label + '</button>';
const note = text => '<p class="muted tf-note">' + text + '</p>';
const input = (label, key, attrs = '') => '<label>' + label + '<input name="' + key + '" ' + attrs + '></label>';
const unit = (value, currency) => {
  // Stripe charges use minor units. Its compatibility exceptions store whole-unit amounts in hundreds.
  const decimals = ['BIF','CLP','DJF','GNF','JPY','KMF','KRW','MGA','PYG','RWF','UGX','VND','VUV','XAF','XOF','XPF'].includes(currency.toUpperCase()) ? 0 : 2;
  const multiplier = ['ISK','UGX'].includes(currency.toUpperCase()) ? 100 : 10 ** decimals;
  if (['BHD','JOD','KWD','OMR','TND'].includes(currency.toUpperCase())) return (value / 1000).toFixed(3) + ' ' + currency.toUpperCase();
  return (value / multiplier).toFixed(decimals) + ' ' + currency.toUpperCase();
};

export async function renderPartnerships(container) {
  const me = await (await fetch('/api/me')).json();
  if (me.guest) {
    container.innerHTML = panel('合作中心', note('登录后可建立推荐关系、核对佣金，或与团队整理已获授权的素材及货盘。') + '<a class="btn" href="#account">登录或注册</a>');
    return;
  }
  const month = new Date().toISOString().slice(0, 7);
  const [profile, library, initial, approvals] = await Promise.all([request(''), request('/library'), request('/statement?mode=test&month=' + month),request('/reviews')]);
  const link = new URL('/', location.origin);
  if (profile.code) {
    link.searchParams.set('ref', profile.code);
    link.hash = 'account';
  }
  const referral = profile.code
    ? '<label>推荐注册链接<input name="referral" readonly value="' + escapeHtml(link.href) + '"></label>' + btn('复制链接', 'copy')
    : btn('生成我的推荐码', 'code');
  const statement = '<form data-statement class="tf-form"><div class="tf-fields">' +
    '<label>账期（UTC）<input type="month" name="month" value="' + month + '" required></label>' +
    '<label>支付环境<select name="mode"><option value="test">测试</option><option value="live">正式</option></select></label></div>' +
    '<button class="btn">查看账单</button></form><div data-entries></div>';
  const editor = '<form data-editor class="tf-form"><input type="hidden" name="id">' +
    '<div class="tf-fields"><label>类型<select name="kind"><option value="asset">授权素材</option><option value="product">商品货盘</option></select></label>' +
    input('名称', 'name', 'required maxlength="160"') + '</div>' +
    input('来源链接', 'url', 'required type="url" placeholder="https://"') +
    input('授权依据或使用范围', 'rights', 'required maxlength="500" placeholder="例如：品牌授权本月用于短视频"') +
    input('关联商品 ID（可选）', 'product_id', 'maxlength="160"') +
    input('自定义品类','category','maxlength="120"')+
    input('附件（素材，可选）','attachment','type="file"') +input('附件授权截止日','expires','type="date"') +
    '<div class="tf-inline"><button class="btn primary">保存条目</button>' + btn('清空表单', 'clear') + '</div></form>';
  container.innerHTML = '<a class="tf-back" href="#tools">← 运营工具</a><div class="tf-grid">' +
    panel('推荐合作', note('已推荐注册 ' + profile.referred + ' 人。新绑定用户的佣金率为 ' + (profile.bps / 100).toFixed(2) + '%。') +
      '<div class="tf-form">' + referral + '</div>') + panel('佣金结算单', statement) +
    panel('结算审批', '<label>折算汇率日（留空按原币核账）<input type="date" data-fx-day></label>'+btn('提交当前账期审批','review')+'<div data-approvals></div>')+
    panel('素材与货盘', editor) + panel('团队清单','<label>按名称、品类或商品 ID 筛选<input type="search" data-library-filter></label>'+btn('导出清单 CSV', 'exportLibrary') + '<div data-list></div>') +
    '</div><output class="tf-result" aria-live="polite"></output>';
  const output = container.querySelector('output');
  const list = container.querySelector('[data-list]');
  const form = container.querySelector('[data-editor]');
  let items = library.items;
  let current = initial;
  let requestNumber = 0;

  const showReviews=rows=>{
    container.querySelector('[data-approvals]').innerHTML=rows.map(r=>'<div class="tf-reading"><span>#'+r.id+' · '+escapeHtml(r.mode)+' · '+escapeHtml(r.month)+'</span><b>'+escapeHtml(r.status)+'</b><span>'+escapeHtml([r.converted,r.currency,r.reason].filter(Boolean).join(' '))+'</span></div>').join('');
  };
  showReviews(approvals.items);
  const filter=container.querySelector('[data-library-filter]');
  const visibleItems=()=>items.filter(r=>[r.name,r.category,r.product_id].some(field=>(field||'').toLowerCase().includes(filter.value.trim().toLowerCase())));
  filter.oninput=showList;
  function showList() {
    const visible=visibleItems();
    list.innerHTML = visible.length ? visible.map(r => '<article class="tf-row"><div><small><span data-ui-label>' +
      (r.kind === 'asset' ? '授权素材' : '商品货盘') + '</span> ' + escapeHtml([r.category,r.product_id].filter(Boolean).join(' · ')) + '</small><a class="tf-entity" target="_blank" rel="noopener noreferrer" href="' +
      escapeHtml(r.url) + '">' + escapeHtml(r.name) + '</a><p>' + escapeHtml(r.rights) +
      '</p>'+(r.filename?'<a href="/api/partners/asset?id='+r.id+'" download>下载附件 · '+escapeHtml(r.filename)+'</a>':'')+'</div><div class="tf-inline"><button class="btn" data-edit="' + r.id + '">编辑</button><button class="btn" data-remove="' +
      r.id + '">删除</button></div></article>').join('') : note(items.length?'没有符合筛选条件的条目。':'清单中还没有条目。');
  }
  function showStatement() {
    const summary = Object.entries(current.totals).map(([currency, t]) =>
      '<p>净成交 ' + escapeHtml(unit(t.amount, currency)) + ' · 应计佣金 <b>' + escapeHtml(unit(t.commission, currency)) + '</b></p>').join('');
    const entries = current.items.map(r => '<div class="tf-reading"><span>' + (r.entry.startsWith('dispute:')?'争议冲正':r.amount<0?'退款冲正':'支付入账') +
      '<small> · ' + new Date(r.occurred * 1000).toISOString().slice(0,10) + '</small><br><small>' + escapeHtml(r.entry) + '</small></span>' +
      '<b>' + escapeHtml(unit(r.commission, r.currency)) + '</b></div>').join('');
    const cases=(current.disputes||[]).map(d=>'<p>争议 '+escapeHtml(d.case_id)+' · '+escapeHtml(d.status)+' · '+escapeHtml(d.reason)+'</p>').join('');
    container.querySelector('[data-entries]').innerHTML = cases+summary + entries + (entries ? btn('导出明细 CSV', 'exportStatement') : note('该账期没有已核实的支付或退款。'));
  }
  showList();
  showStatement();
  container.querySelector('[data-statement]').onsubmit = async e => {
    e.preventDefault();
    const version = ++requestNumber;
    try {
      const data = await request('/statement?' + new URLSearchParams(new FormData(e.target)));
      if (version === requestNumber) { current = data; showStatement(); }
    } catch (err) { output.textContent = localMessage(err.message); }
  };
  form.onsubmit = async e => {
    e.preventDefault();
    const values = Object.fromEntries(new FormData(form));
    if (!values.id) delete values.id;
    const submit = form.querySelector('button:not([type])');
    submit.disabled = true;
    try {
      const file=values.attachment,expires=values.expires;
      if(file?.size>12*1024*1024)throw Error('附件上限 12 MiB');
      if(file?.size && values.kind!=='asset')throw Error('请将条目类型设为授权素材');
      delete values.attachment;
      if(file?.size)delete values.expires;
      const saved=await request('/library', values);
      form.elements.namedItem('id').value=saved.id;
      if(file?.size){
        const res=await fetch('/api/partners/asset?'+new URLSearchParams({id:saved.id,name:file.name,expires}),{method:'POST',headers:{'Content-Type':'application/octet-stream'},body:file});
        if(!res.ok)throw Error((await res.json()).error);
      }
      items = (await request('/library')).items;
      form.reset();
      showList();
      output.textContent = '条目已保存。';
    } catch (err) { output.textContent = localMessage(err.message); }
    finally { submit.disabled = false; }
  };
  container.onclick = async e => {
    const b = e.target.closest('button');
    if (!b) return;
    try {
      if (b.dataset.edit) {
        const row = items.find(x => x.id === Number(b.dataset.edit));
        for (const key of ['id', 'kind', 'name', 'url', 'rights', 'product_id','category','expires']) form.elements.namedItem(key).value = row[key]||'';
        form.elements.namedItem('name').focus();
      } else if (b.dataset.remove && window.confirm(localMessage('从团队清单中删除这个条目？'))) {
        await request('/library', {action: 'remove', id: Number(b.dataset.remove)});
        items = (await request('/library')).items;
        if (form.elements.namedItem('id').value === b.dataset.remove) form.reset();
        showList();
      } else {
        switch (b.dataset.action) {
          case 'review': {
            const entry=await request('/reviews',{mode:current.mode,month:current.month,fx_date:container.querySelector('[data-fx-day]').value});
            showReviews((await request('/reviews')).items);output.textContent='结算申请 #'+entry.id;break;
          }
          case 'clear': form.reset(); break;
          case 'code': await request('/code', {}); await renderPartnerships(container); break;
          case 'copy': await navigator.clipboard.writeText(link.href); output.textContent = '推荐链接已复制。'; break;
          case 'exportLibrary':
            csvDownload('tikflowso-library.csv', ['类型','名称','来源链接','授权范围','商品ID','品类'].map(localMessage), visibleItems().map(r => [r.kind,r.name,r.url,r.rights,r.product_id,r.category]));
            break;
          case 'exportStatement': {
            const fields = ['invoice','charge','entry','currency','amount','bps','commission','occurred'];
            csvDownload('tikflowso-' + current.mode + '-' + current.month + '.csv',
              ['环境','账期','账单编号','收款编号','流水编号','币种','实收最小货币单位','佣金基点','佣金最小货币单位','发生时间UTC'],
              current.items.map(r => [current.mode,current.month,...fields.map(k => k === 'occurred' ? new Date(r[k] * 1000).toISOString() : r[k])]));
            break;
          }
        }
      }
    } catch (err) { output.textContent = localMessage(err.message); }
  };
}
