import {localMessage} from './locale.js';
const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const text=value=>'<span data-ui-label>'+esc(value)+'</span>';
const statuses={pending:'等待审批',approved:'已批准',rejected:'已拒绝'};
const stamp=time=>time?new Date(time*1000).toISOString().slice(0,16).replace('T',' ')+' UTC':'';
const nonce=()=>Array.from(crypto.getRandomValues(new Uint32Array(4)),n=>n.toString(16).padStart(8,'0')).join('');

export function capacityPanel(data){
  const q=data.capacity;
  return '<div data-capacity><p data-slot-limits>'+text('套餐基础额度')+' <b data-slot-base>'+q.base+'</b> · '+text('本月审批加额')+' <b data-slot-added>'+q.added+'</b> · <span data-slot-month>'+esc(q.period)+'</span> UTC</p>'+
    '<div class="tf-inline"><a class="btn" href="#plans">查看订阅套餐</a><a class="btn" href="#account?section=subscription">订阅管理</a></div>'+
    '<details data-slot-details><summary>按月申请额外监控名额</summary><p data-ui-label>工作区所有者可提交用途与数量，由平台管理员审批。审批加额于当月 UTC 月末到期。超出额度时按创建顺序保留较早的任务；其余任务结束，历史记录可继续查看。</p>'+
    (data.can_request?'<form class="tf-form" data-slot-request><label>所需额外名额<input required type="number" min="1" max="999999" step="1" name="slots"></label><label>申请用途<textarea required name="reason" maxlength="600" rows="2"></textarea></label><button class="btn primary" type="submit">提交额度申请</button><output role="status"></output></form><div data-slot-history></div>':
    '<a class="btn" href="#account">前往账户</a>')+'</details></div>';
}
async function history(root,get,operator,page=1){
  const route=operator?'admin/monitor-capacity':'monitor-capacity';
  const data=await get(route+'?page='+page);
  if(data.capacity){
    const panel=root.closest('.tf-panel');
    panel.querySelector('[data-slot-base]').textContent=data.capacity.base;
    panel.querySelector('[data-slot-added]').textContent=data.capacity.added;
    panel.querySelector('[data-slot-month]').textContent=data.capacity.period;
    panel.querySelector('[data-slot-usage]').textContent=data.active+' / '+data.capacity.limit;
  }
  root.innerHTML=(data.items.length?'':'<p data-ui-label>暂无额度申请。</p>')+data.items.map(row=>
    '<article class="research-turn" data-request-id="'+row.id+'"><p><b>#'+row.id+'</b> · '+esc(row.period)+' UTC · '+row.slots+' '+text('个名额')+' · '+text(statuses[row.status])+
    (row.expired?' · '+text('月份已结束'):'')+'</p>'+(operator?'<p data-source-text>'+esc(row.requester)+' · '+esc(row.email)+'</p>':'')+
    '<p data-source-text>'+esc(row.reason)+'</p><small>'+esc(stamp(row.created))+'</small>'+
    (row.decided?'<p>'+text('审批人')+' '+esc(row.reviewer)+' · '+esc(stamp(row.decided))+'</p><p data-source-text>'+esc(row.note)+'</p>':'')+
    (row.can_review?'<form class="tf-form" data-slot-review="'+row.id+'"><label>审批说明（拒绝时必填）<textarea maxlength="600" name="note" rows="2"></textarea></label><div class="tf-inline"><button class="btn" value="approved" type="submit">批准额度</button><button class="btn" value="rejected" type="submit">拒绝申请</button></div><output role="status"></output></form>':'')+'</article>').join('')+
    '<div class="tf-inline"><button class="btn" type="button" data-slot-page="'+page+'">刷新申请</button>'+(page>1?'<button class="btn" type="button" data-slot-page="'+(page-1)+'">上一页</button>':'')+
    (data.more?'<button class="btn" type="button" data-slot-page="'+(page+1)+'">下一页</button>':'')+'</div><output data-slot-error role="status"></output>';
  root.querySelectorAll('[data-slot-page]').forEach(b=>b.onclick=()=>{b.disabled=true;history(root,get,operator,Number(b.dataset.slotPage)).catch(err=>{b.disabled=false;root.querySelector('[data-slot-error]').textContent=localMessage(err.message);});});
  root.querySelectorAll('[data-slot-review]').forEach(f=>f.onsubmit=async ev=>{
    ev.preventDefault();const status=ev.submitter.value;
    if(status==='rejected'&&!f.elements.note.value.trim()){f.querySelector('output').textContent=localMessage('请填写拒绝原因');f.elements.note.focus();return;}
    const buttons=[...f.querySelectorAll('button')];buttons.forEach(b=>b.disabled=true);
    try{await get(route,{id:Number(f.dataset.slotReview),status,note:f.elements.note.value});await history(root,get,true,page);}
    catch(err){f.querySelector('output').textContent=localMessage(err.message);}
    finally{buttons.forEach(b=>b.disabled=false);}
  });
}
export function bindCapacity(root,get){
  const box=root.querySelector('[data-capacity]'),details=box.querySelector('[data-slot-details]'),form=details.querySelector('[data-slot-request]');
  if(!form)return;
  const table=details.querySelector('[data-slot-history]'),out=form.querySelector('output');
  const refresh=()=>history(table,get,false).catch(err=>{out.textContent=localMessage(err.message);});
  details.ontoggle=()=>{if(details.open)refresh();};
  let key=nonce();
  form.onsubmit=async ev=>{
    ev.preventDefault();const button=form.querySelector('button');if(button.disabled)return;
    button.disabled=true;
    try{await get('monitor-capacity',{nonce:key,slots:form.elements.slots.value,reason:form.elements.reason.value});key=nonce();form.reset();out.textContent=localMessage('额度申请已提交。');await refresh();}
    catch(err){out.textContent=localMessage(err.message);}
    finally{button.disabled=false;}
  };
}
export async function renderCapacityReview(root,get){
  root.innerHTML='<section class="panel tf-panel" data-capacity-review><h2>监控额度审批</h2><div data-slot-history></div><a class="btn" href="#admin">管理员后台</a></section>';
  await history(root.querySelector('[data-slot-history]'),get,true);
}
