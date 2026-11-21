import {localMessage} from './locale.js';
const e=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const statusText={running:'执行中',passed:'通过',failed:'失败',interrupted:'已中断',pending_key:'等待密钥'};
const actions={sync:'同步模型',probe:'测试连接',acceptance:'一键样例验收'};
const cases={en:'英文商品图 → 中文',zh:'中文商品图 → 英文',empty:'空白图',video:'双镜头视频'};

async function api(path,data){
  const res=await fetch('/api/admin/'+path,data===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
  const body=await res.json();
  if(!res.ok)throw Error(body.error||'请求失败');
  return body;
}
const time=stamp=>stamp?new Date(stamp*1000).toLocaleString():'尚未同步';

export async function renderAdmin(root){
  const access=await api('access');
  if(!access.admin){
    const me=await (await fetch('/api/me')).json();
    root.innerHTML='<section class="panel ca-gate"><h2>平台管理员登录</h2>'+(me.guest?'<p>请先登录要用于管理此部署的账户。</p><a class="btn primary" href="#account">登录或注册</a>':access.initial_setup?
      '<form><label>首次绑定初始化码<input type="password" name="code" required autocomplete="off"></label><p>初始化码位于部署主机数据库旁的 <code>*.admin-setup.txt</code> 文件。</p><button class="btn primary">绑定当前账户</button><output role="status"></output></form>':'<p>当前账户没有平台管理权限。</p><a class="btn" href="#account">返回账户设置</a>')+'</section>';
    const form=root.querySelector('form');
    if(form)form.onsubmit=async ev=>{ev.preventDefault();try{await api('claim',{code:form.elements.code.value});await renderAdmin(root);}catch(err){form.querySelector('output').textContent=err.message;}};
    return;
  }
  let config=await api('settings'), selected=config.providers.some(p=>p.name===config.active)?config.active:'bailian';
  let tab='providers',prompt=config.prompts[0].name,records=(await api('jobs')).items,timer=0,weekly=null;
  let message='',busy=false,watchId=null;
  const provider=()=>config.providers.find(p=>p.name===selected);
  const stamp=()=>config.revision;
  function tell(text){message=text;const target=root.querySelector('[data-message]');if(target)target.textContent=text;}
  function history(rows){
    if(!rows.length)return '<p class="ca-muted">还没有运行记录。</p>';
    return rows.map(j=>'<details class="ca-run" '+(j.id===watchId?'open':'')+'><summary><strong>'+e(actions[j.kind])+'</strong><span>'+e(j.provider)+' · '+e(j.model)+'</span><b data-state="'+e(j.status)+'">'+e(statusText[j.status]||j.status)+'</b></summary><p>'+e(time(j.created))+' · 配置版本 '+Number(j.revision)+'</p>'+
      (j.error?'<p>'+e(j.error)+'</p>':'')+j.results.map(row=>{
        if(row.case)return '<div class="ca-case"><b>'+e(cases[row.case])+' · '+(row.passed?'通过':'失败')+'</b>'+(!row.passed&&row.expected?'<p>验收条件　'+e(row.expected)+'</p>':'')+'<pre>'+e(row.error||row.output?.result)+'</pre></div>';
        if(j.kind==='sync')return '<p>'+(row.state==='pending_key'?'服务商已响应，请填写密钥。':'已刷新 '+Number(row.count)+' 个模型，当前模型'+(row.listed?'在目录中。':'未列入目录。'))+'</p>';
        return '<p>样图首行识别结果　'+e(row.title)+'</p>';
      }).join('')+'<button type="button" class="btn" data-report="'+Number(j.id)+'">下载报告 JSON</button></details>').join('');
  }
  function options(p){
    const choices=p.entries.filter(r=>!r.inputs?.length||r.inputs.includes('image')||r.inputs.includes('vision'));
    return '<option value="">从已同步目录选择（'+choices.length+'）</option>'+choices.map(r=>'<option value="'+e(r.id)+'">'+e(r.id)+(r.inputs?.length?'':' · 输入类型待测')+'</option>').join('');
  }
  function providers(){
    const p=provider(),active=p.name===config.active;
    return '<div class="ca-layout"><nav class="ca-platforms" aria-label="云平台">'+config.providers.map(x=>'<button data-provider="'+e(x.name)+'" aria-pressed="'+(selected===x.name)+'"><strong>'+e(x.label)+'</strong><span>'+(x.name===config.active?'正在使用 · ':'')+(x.has_key?'已设密钥':'待填密钥')+'</span></button>').join('')+'</nav><section class="panel ca-editor"><h2>'+e(p.label)+'</h2><code>'+e(p.base)+'</code><form data-config><label>API key<input name="key" type="password" autocomplete="new-password" placeholder="'+(p.has_key?'已设置，留空保留':'输入服务端密钥')+'"></label><label>视觉模型<select name="catalog">'+options(p)+'</select><input required maxlength="250" name="model" value="'+e(p.model)+'" aria-label="模型 ID" placeholder="模型 ID 或专属接入点"></label><small data-sync-time>目录更新　'+e(time(p.synced_at))+'</small><label class="ca-check"><input type="checkbox" name="activate" '+(active?'checked disabled':'')+'>将此平台用于工作台视觉任务</label><label class="ca-check"><input type="checkbox" name="text" '+(active?'':'disabled ')+(active&&config.use_for_text?'checked':'')+'>同时用于数据问答与文本创作</label><div class="ca-actions"><button class="btn primary" type="submit">保存配置</button>'+(p.has_key?'<button class="btn" type="button" data-clear>清除密钥</button>':'')+'</div></form><div class="ca-test"><h3>连接与验收</h3><p>测试连接会发送一张英文样图。一键验收会提交中英文商品图、空白图和四秒视频的镜头采样，按所选平台计费。</p><details class="ca-fixtures"><summary>查看验收素材</summary><div>'+Object.entries(cases).map(([k,label])=>'<figure>'+(k==='video'?'<video controls preload="none" src="/api/admin/sample/video"></video>':'<img loading="lazy" src="/api/admin/sample/'+k+'" alt="'+e(label)+'">')+'<figcaption>'+e(label)+'</figcaption></figure>').join('')+'</div></details><div class="ca-actions">'+Object.entries(actions).map(([k,v])=>'<button class="btn" data-job="'+k+'" '+(k!=='sync'&&!p.has_key?'disabled':'')+'>'+v+'</button>').join('')+'<button type="button" class="btn" data-sync-all>同步全部目录</button></div></div><h3>最近运行</h3><div data-jobs></div></section></div>';
  }
  function prompts(){
    const p=config.prompts.find(x=>x.name===prompt);
    return '<section class="panel ca-editor"><h2>任务提示词</h2><form data-prompt-form><label>任务<select name="task">'+config.prompts.map(x=>'<option value="'+e(x.name)+'" '+(x.name===prompt?'selected':'')+'>'+e(x.label)+'</option>').join('')+'</select></label><label>模型指令<textarea name="body" required maxlength="6000" rows="7">'+e(p.text)+'</textarea></label><p>修改用于后续云端请求。图片坐标、镜头时间和 JSON 格式由程序校验。</p><div class="ca-actions"><button class="btn primary">保存提示词</button><button class="btn" type="button" data-reset '+(!p.custom?'disabled':'')+'>恢复默认提示词</button></div></form></section>';
  }
  function showJobs(){
    const box=root.querySelector('[data-jobs]');
    if(box)box.innerHTML=history(tab==='history'?records:records.filter(r=>r.provider===selected).slice(0,5));
  }
  function draw(){
    root.innerHTML='<div class="ca-tabs" aria-label="后台导航">'+Object.entries({providers:'供应商配置',prompts:'提示词',history:'运行记录',weekly:'研究周报'}).map(([k,v])=>'<button class="btn" aria-pressed="'+(tab===k)+'" data-tab="'+k+'">'+v+'</button>').join('')+'</div><output class="ca-message" data-message role="status">'+e(message)+'</output>'+(tab==='providers'?providers():tab==='prompts'?prompts():tab==='weekly'?weeklyReport():'<section class="panel ca-editor"><h2>运行记录</h2><div data-jobs></div></section>');
    showJobs();
  }
  function weeklyReport(){
    const pct=value=>value==null?'—':value+'%';
    return '<section class="panel ca-editor"><h2>研究周报</h2><form data-weekly><label>统计截止日（UTC）<input required name="date" type="date" value="'+e(weekly.end)+'"></label><button class="btn">查看周报</button></form><p>'+e(weekly.start)+' — '+e(weekly.end)+'</p>'+
      '<div class="table-wrap"><table class="records"><thead><tr>'+['数据来源','活跃工作区','首次完成选品','首次完成占比','跨日复访','跨日复访占比'].map(v=>'<th>'+e(v)+'</th>').join('')+'</tr></thead><tbody>'+
      weekly.items.map(r=>'<tr><td data-ui-label>'+(r.cohort==='demo'?'演示数据':'导入数据')+'</td>'+[r.active,r.first_completed,pct(r.first_completed_pct),r.repeat_days,pct(r.repeat_pct)].map(v=>'<td>'+e(v)+'</td>').join('')+'</tr>').join('')+
      '</tbody></table></div><p>活跃指在工作台查看商品榜或详情。首次完成指同一统计日、市场、来源与研究窗口中，查看榜单和详情后首次收藏商品或导出榜单。跨日复访指本周至少两天有研究行为。</p></section>';
  }
  async function poll(){
    clearTimeout(timer);
    if(!root.isConnected)return;
    try{
      const synced=new Set(records.filter(r=>r.kind==='sync'&&r.status==='passed').map(r=>r.id));
      records=(await api('jobs')).items;
      if(records.some(r=>!synced.has(r.id)&&r.kind==='sync'&&r.status==='passed')){
        config=await api('settings');
        const select=root.querySelector('[name=catalog]');
        if(select){select.innerHTML=options(provider());root.querySelector('[data-sync-time]').textContent='目录更新　'+time(provider().synced_at);}
      }
      showJobs();
    }catch(err){tell(err.message);}
    if(records.some(r=>r.status==='running'))timer=setTimeout(poll,1200);
  }
  async function perform(fn){
    if(busy)return;busy=true;
    try{await fn();}catch(err){tell(err.message);}finally{busy=false;}
  }
  root.onclick=event=>{
    const btn=event.target.closest('button');if(!btn)return;
    if(btn.dataset.tab==='weekly'){perform(async()=>{weekly=await api('weekly');tab='weekly';message='';draw();});return;}
    if(btn.dataset.tab||btn.dataset.provider){if(busy)return;message='';if(btn.dataset.tab)tab=btn.dataset.tab;else selected=btn.dataset.provider;draw();return;}
    if(btn.dataset.report){
      const row=records.find(r=>r.id===Number(btn.dataset.report));if(!row)return;
      const url=URL.createObjectURL(new Blob([JSON.stringify(row,null,2)],{type:'application/json'}));
      const a=document.createElement('a');a.href=url;a.download='tikflowso-'+row.provider+'-'+row.id+'.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);return;
    }
    if(btn.hasAttribute('data-sync-all'))perform(async()=>{
      const outcomes=await Promise.allSettled(config.providers.map(p=>api('jobs',{provider:p.name,kind:'sync',revision:stamp()})));
      const count=outcomes.filter(r=>r.status==='fulfilled').length;
      tab='history';message=count+' / '+outcomes.length+' 个模型目录同步任务已提交。';draw();await poll();
    });
    if(btn.dataset.job)perform(async()=>{
      const form=root.querySelector('[data-config]');
      if(form.elements.key.value||form.elements.model.value!==provider().model){tell('请先保存输入的密钥和模型，再执行测试。');return;}
      const job=await api('jobs',{provider:selected,kind:btn.dataset.job,revision:stamp()});
      watchId=job.id;tell('任务已提交，可在运行记录中查看结果。');await poll();
    });
    if(btn.hasAttribute('data-clear')&&confirm(localMessage('清除此平台密钥？')))perform(async()=>{
      await api('provider',{revision:stamp(),provider:selected,model:provider().model,clear_key:true});
      config=await api('settings');message='密钥已清除。';draw();
    });
    if(btn.hasAttribute('data-reset'))perform(async()=>{
      await api('prompt',{revision:stamp(),name:prompt,reset:true});config=await api('settings');message='已恢复默认提示词。';draw();
    });
  };
  root.onchange=ev=>{
    if(ev.target.name==='activate')root.querySelector('[name=text]').disabled=!ev.target.checked;
    if(ev.target.name==='catalog'&&ev.target.value)root.querySelector('[name=model]').value=ev.target.value;
    if(ev.target.name==='task'){prompt=ev.target.value;message='';draw();}
  };
  root.onsubmit=ev=>{
    ev.preventDefault();const f=ev.target;
    perform(async()=>{
      if(f.hasAttribute('data-weekly')){
        weekly=await api('weekly?'+new URLSearchParams({date:f.elements.date.value}));draw();
      }else if(f.hasAttribute('data-config')){
        await api('provider',{provider:selected,revision:stamp(),model:f.elements.model.value,key:f.elements.key.value,activate:f.elements.activate.checked,use_for_text:f.elements.text.checked});
        f.elements.key.value='';message='配置已保存并生效。';
      }else{await api('prompt',{name:prompt,revision:stamp(),text:f.elements.body.value});message='提示词已保存并生效。';}
      config=await api('settings');draw();
    });
  };
  draw();
  if(records.some(r=>r.status==='running'))timer=setTimeout(poll,1200);
}
