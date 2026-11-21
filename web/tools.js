import { localMessage } from "./locale.js";
const tools = {
  agent: ['数据助手', '查询当前市场的成交、销量、观看与增长。'],
  ideas: ['选题灵感', '从商品或人群出发寻找拍摄角度。'],
  promotion: ['推广脚本', '将商品卖点整理成分镜与时间段。'],
  title: ['视频标题', '围绕选题撰写多版短视频标题。'],
  product_title: ['商品标题', '根据提供的规格整理商品名称。'],
  outreach: ['达人邀约', '草拟合作邀请与交付沟通邮件。'],
  extract: ['文本脚本拆解', '从现有口播文字提取结构。'],
  video: ['视频拆解', '从本地视频抽取关键时间点并分析画面。'],
  image_translate: ['图片翻译', '识别图中文字，输出原文和译文。'],
  erase: ['图片去字', '框选文字，用周围像素填充并下载。'],
  calc: ['费用计算器', '按实际费率估算单件利润与盈亏平衡售价。']
};
const labels = {products:'商品',shops:'店铺',creators:'达人',videos:'视频',lives:'直播',sales:'销量',gmv:'GMV',views:'观看次数',online_viewers:'在线人数'};
const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const link = (view,p={}) => '#'+view+'?'+new URLSearchParams(p);
const field = (label,name,type='text',value='',attrs='') => '<label>'+label+'<input name="'+name+'" type="'+type+'" value="'+esc(value)+'" '+attrs+'></label>';
const button = (text,action='') => '<button class="btn primary" '+action+'>'+text+'</button>';
const panel = (title,body) => '<section class="panel tf-panel"><h2>'+title+'</h2>'+body+'</section>';
const note = (text) => '<p class="muted tf-note">'+text+'</p>';
const submit = text => button(text,'type="submit"');
const resultBox = '<output class="tf-result" aria-live="polite"></output>';
const form = (id,inside,buttonText) => '<form class="tf-form" data-action="'+id+'">'+inside+submit(buttonText)+resultBox+'</form>';
const get = async (path,data) => {
  const options=data===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)};
  const r=await fetch('/api/'+path,options),json=await r.json();
  if(!r.ok) throw Error(json.error||'请求失败'); return json;
};
const scopeFor = c => Object.fromEntries(['market','source','days','date'].filter(k=>c[k]).map(k=>[k,c[k]]));
const sampleRows=[{market:'US',kind:'products',id:'example-01',name:'示例保温杯',date:'2026-11-19',gmv:90,sales:3,price:30,category:'家居生活'}];

function initCss(){
  if(document.querySelector('#tool-styles'))return;
  const css=document.createElement('link');css.rel='stylesheet';css.id='tool-styles';css.href='/tools.css';document.head.append(css);
}
function show(output,text,bad=false){output.textContent=bad?localMessage(text):text;output.classList.toggle('bad',bad);}
function download(blob,file){
  const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download=file;a.click();
  setTimeout(()=>URL.revokeObjectURL(a.href),1000);
}
function mountForm(root,id,fn){
  const f=root.querySelector('form[data-action="'+id+'"]');if(!f)return;
  f.onsubmit=async event=>{
    event.preventDefault();const out=f.querySelector('output'),btn=f.querySelector('[type=submit]');
    btn.disabled=true;show(out,localMessage('处理中…'));
    try{await fn(Object.fromEntries(new FormData(f)),out,f);}
    catch(e){show(out,e.message,true);}finally{btn.disabled=false;}
  };
}
function toolHref(id){return link('tools',{tool:id});}
function scopeLink(r){return link('detail',{market:r.market,source:r.source,kind:r.kind,id:r.id,...(r.date&&r.days?{date:r.date,days:r.days}:{})});}
function itemCard(r,controls=''){
  return '<article class="tf-row"><div><small>'+esc([labels[r.kind],r.market,r.source].filter(Boolean).join(' · '))+'</small><a class="tf-entity" href="'+esc(scopeLink(r))+'">'+esc(r.name)+'</a></div>'+controls+'</article>';
}
async function researchLists(root,c,view){
  const isMon=view==='monitor',endpoint=isMon?'monitors':'favorites',data=await get(endpoint);
  const rows=data.items;
  let prefix=isMon?'<a class="tf-back" href="#tools?tool=alerts">查看监控通知 →</a>':'';
  const topics=data.topics||[];
  if(topics.length){
    prefix+=panel('已收藏的灵感',topics.map((r,i)=>'<article class="tf-row"><div><small>'+esc(r.market+' · '+r.date+' · '+r.days+'d')+'</small><a class="tf-entity" href="'+esc(link(r.group==='script'?'inspiration':'trends',r))+'">'+esc(r.topic)+'</a></div><button class="btn" data-remove-topic="'+i+'">移除</button></article>').join(''));
  }
  root.onclick=async e=>{
    const b=e.target.closest('[data-remove-topic]');
    if(b)try{await get('saved-topics',{...topics[Number(b.dataset.removeTopic)],remove:true});await researchLists(root,c,view);}catch(err){b.textContent=err.message;}
  };
  const removeTopic=root.onclick;
  if(!rows.length){
    root.innerHTML=prefix+panel(isMon?'监控任务':'收藏清单',note(isMon?'在商品、视频或直播详情页点击「监控」，即可在这里查看最新快照和历史记录。':'在对象详情页点击「收藏」，即可在这里继续研究。')+'<a class="btn" href="#products">浏览商品</a>');return;
  }
  root.innerHTML=prefix+panel(isMon?'监控任务 · '+rows.length:'收藏清单 · '+rows.length,rows.map((r,i)=>{
    if(!isMon)return itemCard(r,(r.date?'<time>'+esc(r.date)+' · '+Number(r.days)+'d</time>':'')+'<button class="btn" data-delete="'+i+'">移除</button>');
    const last=r.readings[0],state=r.status==='active'?'监控中':'已结束';
    return itemCard(r,'<span class="tf-badge">'+esc(state)+'</span>')+'<div class="tf-monitor"><p>'+esc(labels[r.metric])+' · '+(last?esc(last.day)+'　'+esc(last.value):'等待快照')+(last?.hit?'　已达到阈值':'')+'</p>'+
      '<p><span data-ui-label>来源最新日期</span> '+esc(r.source_latest||'—')+' · <span data-ui-label>观测落后天数</span> '+(r.observation_lag_days??'—')+'</p>'+
      '<div class="tf-inline"><label>提醒阈值 <input aria-label="提醒阈值" type="number" min="0" step="any" data-th="'+i+'" value="'+esc(r.threshold)+'" placeholder="仅记录"></label><button class="btn" data-threshold="'+i+'">保存阈值</button><button class="btn" data-status="'+i+'">'+(r.status==='active'?'结束监控':'恢复监控')+'</button><button class="btn" data-delete="'+i+'">移除</button></div>'+
      '<details><summary>历史记录（'+r.readings.length+'）</summary>'+r.readings.map(x=>'<div class="tf-reading"><time>'+esc(x.day)+'</time><b>'+esc(x.value)+'</b><span>'+ (x.hit?'已达阈值':'')+'</span></div>').join('')+'</details>'+(r.points?.length?'<details open><summary>供应商时点观测（UTC）</summary>'+r.points.map(p=>'<div class="tf-reading"><time>'+esc(p.stamp.slice(0,19).replace('T',' '))+'</time><span>'+esc(labels[p.metric])+'</span><b>'+esc(p.value)+'</b></div>').join('')+'</details>':'')+'</div>';
  }).join('')+resultBox);
  if(isMon){const btn=document.createElement('button');btn.className='btn';btn.textContent='刷新监控记录';btn.onclick=()=>researchLists(root,c,view);root.querySelector('h2').after(btn);}
  root.onclick=async e=>{
    const b=e.target.closest('button');if(!b)return;
    if(b.hasAttribute('data-remove-topic'))return removeTopic(e);
    const action=Object.keys(b.dataset)[0],r=rows[Number(b.dataset[action])];if(!action||!r)return;
    let data=action==='threshold'?{...r,mid:null,threshold:root.querySelector('[data-th="'+b.dataset.threshold+'"]').value||null}:action==='status'?{mid:r.mid,status:r.status==='active'?'completed':'active'}:{...r,remove:true};
    b.disabled=true;
    try{await get(endpoint,data);await researchLists(root,c,view);}catch(err){show(root.querySelector('output'),err.message,true);}finally{b.disabled=false;}
  };
}
function calculator(root,c){
  const money=c.meta?.currency||'USD';
  root.innerHTML=panel('单件利润测算',form('calc','<label>币种<select name="currency">'+[...new Set([money,'USD','GBP','IDR','MYR','CNY','EUR','THB','VND','PHP','SGD','MXN','BRL','JPY'])].map(code=>'<option '+(code===money?'selected':'')+'>'+code+'</option>').join('')+'</select></label><div class="tf-fields">'+[
    ['售价','price',50],['货品成本','cost',18],['履约运费','ship',5],['其他固定费用','other',0],['平台费率 %','fee',6],['达人佣金率 %','commission',10]
  ].map(([l,k,v])=>field(l,k,'number',v,'required min="0" step="any"')).join('')+'</div>'+note('初始数值仅供试算，可按实际合同修改。'),'计算利润'));
  mountForm(root,'calc',(d,out)=>{
    const sum=Number(d.cost)+Number(d.ship)+Number(d.other), rate=(Number(d.fee)+Number(d.commission))/100;
    const profit=d.price*(1-rate)-sum;
    const line=(label,value)=>localMessage(label)+'　'+value;
    const breakEven=rate<1?d.currency+' '+(sum/(1-rate)).toFixed(2):sum>0?localMessage('费率达到或超过 100%，无正数解'):
      rate===1?localMessage('任意售价均盈亏平衡'):d.currency+' 0.00';
    show(out,[line('单件利润',d.currency+' '+profit.toFixed(2)),line('利润率',Number(d.price)>0?(100*profit/d.price).toFixed(1)+'%':'—'),
              line('盈亏平衡售价',breakEven)].join('\n'));
  });root.querySelector('form').requestSubmit();
}
async function fileImage(file){
  const url=URL.createObjectURL(file),image=new Image();try{image.src=url;await image.decode();
    const scale=Math.min(1,1400/Math.max(image.width,image.height)),canvas=document.createElement('canvas');
    canvas.width=Math.max(1,Math.round(image.width*scale));canvas.height=Math.max(1,Math.round(image.height*scale));
    canvas.getContext('2d').drawImage(image,0,0,canvas.width,canvas.height);return canvas;
  }finally{URL.revokeObjectURL(url);}
}
async function videoFrames(file){
  const video=document.createElement('video'),url=URL.createObjectURL(file);video.muted=true;
  const wait=(event)=>new Promise((resolve,reject)=>{
    const cleanup=()=>{clearTimeout(t);video.removeEventListener(event,ok);video.removeEventListener('error',fail);};
    const ok=()=>{cleanup();resolve();},fail=()=>{cleanup();reject(Error('浏览器无法读取此视频'));},t=setTimeout(fail,12000);
    video.addEventListener(event,ok);video.addEventListener('error',fail);
  });
  try{
    const ready=wait('loadeddata');video.src=url;await ready;
    if(!Number.isFinite(video.duration)||video.duration<=0)throw Error('视频时长无效');
    const cf=document.createElement('canvas'),ratio=Math.min(1,720/Math.max(video.videoWidth,video.videoHeight));
    cf.width=Math.max(1,Math.round(video.videoWidth*ratio));cf.height=Math.max(1,Math.round(video.videoHeight*ratio));
    const frames=[],seconds=[];for(const part of [.04,.25,.5,.74,.95]){
      const t=video.duration*part,seek=wait('seeked');video.currentTime=t;await seek;
      cf.getContext('2d').drawImage(video,0,0,cf.width,cf.height);frames.push(cf.toDataURL('image/jpeg',.75));seconds.push(t.toFixed(1));
    }return {frames,seconds};
  }finally{video.removeAttribute('src');video.load();URL.revokeObjectURL(url);}
}
function eraser(root){
  root.innerHTML=panel('图片去字',note('选择图片，拖动框选要清除的文字。工具使用选区两侧的颜色插值填充，适合纯色或渐变背景。')+
    '<input aria-label="选择图片" type="file" accept="image/*"><div class="tf-canvas"></div><div class="tf-inline"><button class="btn" data-undo disabled>撤销</button><button class="btn primary" data-download disabled>下载 PNG</button></div>'+resultBox);
  const wrap=root.querySelector('.tf-canvas'),out=root.querySelector('output'),undo=root.querySelector('[data-undo]'),save=root.querySelector('[data-download]');
  root.querySelector('input').onchange=async e=>{try{
    if(!e.target.files[0])return;const cv=await fileImage(e.target.files[0]);wrap.replaceChildren(cv);
    const ctx=cv.getContext('2d',{willReadFrequently:true});let start=null,backup=null;
    const xy=ev=>{let box=cv.getBoundingClientRect();return [Math.min(cv.width-1,Math.max(0,Math.floor((ev.clientX-box.left)*cv.width/box.width))),Math.min(cv.height-1,Math.max(0,Math.floor((ev.clientY-box.top)*cv.height/box.height)))];};
    cv.onpointerdown=ev=>{start=xy(ev);cv.setPointerCapture(ev.pointerId);};
    cv.onpointerup=ev=>{if(!start)return;const end=xy(ev),x0=Math.min(start[0],end[0]),x1=Math.max(start[0],end[0]),y0=Math.min(start[1],end[1]),y1=Math.max(start[1],end[1]);start=null;
      if(x1-x0<2||y1-y0<2)return;
      backup=ctx.getImageData(0,0,cv.width,cv.height);const region=ctx.getImageData(x0,y0,x1-x0+1,y1-y0+1);
      for(let y=0;y<region.height;y++){const j=(y+y0)*cv.width,left=(j+Math.max(x0-1,0))*4,right=(j+Math.min(cv.width-1,x1+1))*4;
        for(let x=0;x<region.width;x++){const a=(x+1)/(region.width+1);for(let z=0;z<4;z++)region.data[(y*region.width+x)*4+z]=backup.data[left+z]*(1-a)+backup.data[right+z]*a;}}
      ctx.putImageData(region,x0,y0);undo.disabled=false;show(out,localMessage('已填充选区'));
    };save.disabled=false;undo.disabled=true;undo.onclick=()=>{if(backup)ctx.putImageData(backup,0,0);backup=null;undo.disabled=true;show(out,localMessage('已撤销'));};
    save.onclick=()=>cv.toBlob(blob=>download(blob,'tikflowso-image.png'));show(out,localMessage('拖动图片框选文字'));
  }catch(err){show(out,err.message,true);}};
}
async function creative(root,c,key){
  if(key==='erase'){eraser(root);return;}if(key==='calc'){calculator(root,c);return;}
  const conf=await get('config'),isMedia=['image_translate','video'].includes(key),media=key==='video'?'video':'image';
  const suggestions=key==='agent'?['哪个商品销量最高？','哪些达人涨粉最快？','市场概览']:null;
  root.innerHTML=panel(esc(tools[key][0]),note(esc(tools[key][1]))+form('gen',
    (suggestions?'<div class="tf-inline">'+suggestions.map(x=>'<button class="btn" type="button" data-prompt="'+x+'">'+x+'</button>').join('')+'</div>':'')+
    (key==='video'&&conf.cloud_vision?'<label>分析方式<select name="method"><option value="semantic">云端镜头语义分析</option><option value="preview">五帧预览</option></select></label>':'')+
    (isMedia?'<label>本地文件<input required type="file" accept="'+media+'/*" name="media"></label>':'')+
    '<label>'+ (key==='image_translate'?'目标语言':key==='extract'?'口播文字':'研究问题或创作素材')+'<textarea required maxlength="8000" rows="4" name="text" placeholder="'+esc(key==='agent'?'例如：当前市场哪些商品销量最高？':'填写与任务相关的素材…')+'">'+(key==='image_translate'?(document.documentElement.lang==='en-US'?'English':'简体中文'):key==='video'?(document.documentElement.lang==='en-US'?'Describe the opening, product demonstration and closing by shot.':'按镜头分析开场、产品展示和收尾。'):'')+'</textarea></label>'+
    note(isMedia&&conf.cloud_vision?'云端视觉模型 · '+esc(conf.vision_model)+(conf.vision_status==='pending_key'?' · 等待部署时填写密钥':' · 提交后发送图片或镜头采样帧'):key==='agent'?(conf.model?'提交后将问题和当前窗口的查询结果发送至已配置的模型。':'答案使用所选市场和时间窗口。'):conf.model?'生成请求将发送到已配置的模型服务。':key==='video'?'本机抽取五个时间点的实际画面。':isMedia?'此功能需要配置支持图像输入的模型。':'当前使用本地文本模板。'),key==='agent'?'查询数据':'生成结果'));
  root.querySelectorAll('[data-prompt]').forEach(b=>b.onclick=()=>{root.querySelector('textarea').value=b.textContent;root.querySelector('form').requestSubmit();});
  mountForm(root,'gen',async(d,out)=>{
    let text=d.text,images=[],sourceCanvas=null;
    if(isMedia&&conf.cloud_vision&&conf.vision_status==='pending_key'&&d.method!=='preview')throw Error('云端视觉 API 尚未填写密钥，请联系平台管理员在后台配置。');
    if(key==='image_translate'&&!conf.model&&!conf.cloud_vision)throw Error('请先配置支持图像输入的模型服务，详见项目 README。');
    if(isMedia){
      if(!d.media?.size)throw Error('请选择媒体文件');
      if(key==='video'&&conf.cloud_vision&&d.method!=='preview'){
        if(d.media.size>48*1024*1024)throw Error('视频最大为 48 MiB');
        const response=await fetch('/api/video-analysis?'+new URLSearchParams({brief:text}),{method:'POST',headers:{'Content-Type':'application/octet-stream'},body:d.media});
        const analysis=await response.json();if(!response.ok)throw Error(analysis.error);
        show(out,analysis.mode+' · '+analysis.shots.length+' / '+analysis.total_shots+' 个镜头 · '+analysis.duration.toFixed(2)+' s\n\n'+analysis.result);
        const save=document.createElement('button');save.type='button';save.className='btn';save.textContent='下载镜头分析 JSON';
        save.onclick=()=>download(new Blob([JSON.stringify(analysis,null,2)],{type:'application/json'}),'tikflowso-shots.json');out.append(save);return;
      }
      if(key==='video'){
        const {frames,seconds}=await videoFrames(d.media);
        if(d.method==='preview'||!conf.model){
          show(out,document.documentElement.lang==='en-US'?'Local storyboard · 5 sampled frames':'本机分镜 · 5 张采样画面');
          for(const [i,src] of frames.entries()){
            const figure=document.createElement('figure'),image=new Image(),caption=document.createElement('figcaption');
            caption.textContent=seconds[i]+' s';image.src=src;image.alt=caption.textContent;image.style.maxWidth='100%';
            figure.append(image,caption);out.append(figure);
          }
          return;
        }
        images=frames;text+='\n采样时间（秒）：'+seconds.join('，');
      }
      else {sourceCanvas=await fileImage(d.media);images=[sourceCanvas.toDataURL('image/jpeg',.85)];}
    }
    const a=await get('generate',{tool:key,text,images,locale:document.documentElement.lang,...scopeFor(c)});show(out,localMessage(a.mode)+'\n\n'+a.result);
    if(sourceCanvas&&a.blocks?.length){
      const cv=sourceCanvas,ctx=cv.getContext('2d');
      for(const block of a.blocks){
        const [left,top,width,height]=block.box;
        const x=left*cv.width,y=top*cv.height,w=width*cv.width,h=height*cv.height;
        const at=(px,py)=>ctx.getImageData(Math.max(0,Math.min(cv.width-1,Math.floor(px))),Math.max(0,Math.min(cv.height-1,Math.floor(py))),1,1).data;
        const samples=[at(x-2,y+h/2),at(x+w+2,y+h/2),at(x+w/2,y-2),at(x+w/2,y+h+2)];
        const rgb=[0,1,2].map(i=>samples.map(c=>c[i]).sort((a,b)=>a-b)[1]);
        ctx.fillStyle='rgb('+rgb.join(',')+')';ctx.fillRect(x-1,y-1,w+2,h+2);
        ctx.fillStyle=(.299*rgb[0]+.587*rgb[1]+.114*rgb[2])>128?'#142019':'#fff';
        let size=Math.max(4,Math.floor(h*.8));ctx.font=size+'px sans-serif';
        const measured=ctx.measureText(block.translation).width;
        if(measured>w-2)size=Math.max(4,size*Math.max(1,w-2)/measured);
        ctx.font=size+'px sans-serif';ctx.textBaseline='middle';
        ctx.fillText(block.translation,x+1,y+h/2,Math.max(1,w-2));
      }
      cv.style.maxWidth='100%';cv.style.display='block';out.append(cv);
      const dl=document.createElement('button');dl.type='button';dl.className='btn';dl.textContent='下载译图 PNG';
      dl.onclick=()=>cv.toBlob(blob=>download(blob,'tikflowso-translated.png'));out.append(dl);
    }
    for(const ref of a.references||[]){const l=document.createElement('a');l.textContent=ref.label;l.href=ref.href;out.append('　',l);}
  });
}
async function account(root,c){
  const [u,conf]=await Promise.all([get('me'),get('config')]);
  const email=field('邮箱','email','email','','required autocomplete="email"'),pw=(fresh)=>field('密码','password','password','','required minlength="10" autocomplete="'+(fresh?'new-password':'current-password')+'"');
  if(u.guest){
    const referral=new URLSearchParams(location.search).get('ref')||'';
    root.innerHTML='<div class="tf-grid">'+panel('登录',form('login',email+pw(false),'登录工作区'))+
      panel('注册个人账户',form('register',field('显示名称','name','text','','required maxlength="60"')+email+pw(true)+field('推荐码（选填）','referral_code','text',referral)+'<label><span><input type="checkbox" name="referral_consent" value="yes"> 我同意将此账户与填写的推荐码关联</span></label>','创建账户'))+'</div>';
    for(const action of ['login','register'])mountForm(root,action,async d=>{if(action==='register')d.referral_consent=d.referral_consent==='yes';await get(action,d);location.reload();});return;
  }
  const isOwner=u.role==='owner',cfg=conf.billing,access=await get('admin/access');
  root.innerHTML='<div class="tf-grid">'+panel(esc(u.name),(access.admin||access.initial_setup?'<a class="btn" href="#admin">管理员后台</a>':'')+note(esc(u.email)+' · '+(isOwner?'工作区所有者':'团队成员'))+
    '<p class="tf-big">'+esc(u.plan.toUpperCase())+'</p>'+form('logout','','退出登录'))+
    panel('本月额度','<div class="tf-reading"><span>开发者 API 调用</span><b>'+Number(u.usage.api||0)+' / '+u.limits.api+'</b></div><div class="tf-reading"><span>生成任务</span><b>'+Number(u.usage.generation||0)+' / '+u.limits.generation+'</b></div><div class="tf-reading"><span>今日导出行数</span><b>'+Number(u.usage.export_rows||0)+' / '+u.limits.export_rows+'</b></div><div class="tf-reading"><span>今日详情浏览</span><b>'+Number(u.usage.detail_views||0)+' / '+u.limits.detail_views+'</b></div><div class="tf-reading"><span>并行监控上限</span><b>'+u.limits.monitors+'</b></div>')+
    (isOwner?panel('订阅管理',cfg.configured?form('checkout','<label>套餐<select name="plan"><option value="pro">Pro</option><option value="team">Team</option></select></label>','前往结账')+(cfg.has_customer?form('portal','','管理账单与订阅'):''):note('当前使用本地账户。连接 Stripe 并配置套餐价格后，可在此订阅及管理账单。')):'')+
    panel('团队成员',u.members.map(m=>'<p>'+esc(m.name)+'　'+esc(m.email)+(isOwner&&m.email!==u.email?'　<button class="btn" data-remove-member="'+esc(m.email)+'">移出团队</button>':'')+'</p>').join('')+
    (isOwner&&u.limits.seats>1?form('invite',field('邀请成员邮箱','email','email','','required'),'生成邀请码'):'')+
    (u.role==='member'?form('leave','','退出团队'):'')+(u.role==='owner'&&u.plan==='free'?form('join',field('团队邀请码','invite','text','','required'),'加入团队'):''))+'</div>';
  mountForm(root,'logout',async()=>{await get('logout',{});localStorage.removeItem('tikflowso-scope');location.reload();});
  for(const a of ['checkout','portal'])mountForm(root,a,async d=>{const r=await get(a,d);location.assign(r.url);});
  root.querySelectorAll('[data-remove-member]').forEach(b=>b.onclick=async()=>{try{await get('team/remove',{email:b.dataset.removeMember});await account(root,c);}catch(e){b.textContent=e.message;}});
  mountForm(root,'leave',async()=>{await get('team/leave',{});location.reload();});
  mountForm(root,'invite',async(d,out)=>{const r=await get('invite',d);show(out,'请将此一次性邀请码提供给对应邮箱的成员（24 小时内有效）\n'+r.invite);});
  mountForm(root,'join',async d=>{await get('join',d);location.reload();});
}
async function apiPage(root){
  const u=await get('me');
  const rows=u.guest?[]:(await get('keys')).items;
  root.innerHTML='<div class="tf-grid">'+panel('访问密钥',u.guest?note('请先登录，以便将密钥和月度用量关联到你的账户。')+'<a class="btn primary" href="#account">前往账户</a>':
    form('newkey',field('密钥用途','label','text','','required placeholder="例如：销售周报"'),'创建只读密钥')+
    rows.map(k=>'<div class="tf-row"><div><b>'+esc(k.label)+'</b><p>'+esc(k.prefix)+'…</p></div><button class="btn" data-revoke="'+esc(k.prefix)+'">撤销</button></div>').join('')+resultBox)+
    panel('数据接口',note('每个工作区每分钟最多调用 60 次。HTTP 429 的 Retry-After 给出可重试的秒数，月度额度在 UTC 下月 1 日重置。')+
    '<pre>GET /api/v1/meta\nGET /api/v1/markets\nGET /api/v1/overview\nGET /api/v1/rankings\nGET /api/v1/detail\nGET /api/v1/trends\nGET /api/v1/trend-study</pre>'+
    '<pre>curl -H "Authorization: Bearer $TIKFLOWSO_API_KEY" \\\n  "'+esc(location.origin)+'/api/v1/rankings?kind=products&amp;market=US&amp;days=7&amp;limit=5"</pre>'+
    note('参数包括 source、market、date、days。榜单支持 kind、q、category、segment、sort、page、limit。详情传入 kind、id。'))+
    panel('CLI 与 MCP',note('在本机设置 TIKFLOWSO_URL 与 TIKFLOWSO_API_KEY。命令行和 stdio MCP 共用只读接口。')+'<pre>python3 cli.py rankings --kind products\npython3 cli.py mcp</pre>')+
    panel('浏览器扩展','<a class="btn" href="/downloads/tikflowso-extension.zip" download>下载扩展 ZIP</a>'+note('在 Chrome 扩展程序页启用开发者模式，加载项目中的 extension 文件夹。打开 TikTok 对象页后，点击扩展可在本研究台搜索。'))+'</div>';
  mountForm(root,'newkey',async(d,out)=>{const r=await get('keys',d);await apiPage(root);show(root.querySelector('form output'),'请现在保存密钥，此值只显示一次。\n'+r.key);});
  root.querySelectorAll('[data-revoke]').forEach(b=>b.onclick=async()=>{try{await get('keys',{remove:true,prefix:b.dataset.revoke});await apiPage(root);}catch(e){show(root.querySelector('output'),e.message,true);}});
}
async function resources(root){
  const [u,history]=await Promise.all([get('me'),get('imports')]);
  const deliveryStates={missing:'到期未收到',on_time:'准时收到',late:'逾期收到'};
  const deliveries=history.deliveries.map(r=>'<details><summary data-source-text>'+esc([r.feed,r.market,r.due_utc+' UTC'].join(' · '))+'</summary>'+
    '<p><span data-ui-label>最近七个到期日准时交付</span> '+r.on_time+' / '+r.expected+'</p>'+
    r.history.map(h=>'<div class="tf-row"><time>'+esc(h.day)+'</time><time>'+esc(h.due)+'</time><span data-ui-label>'+deliveryStates[h.status]+'</span></div>').join('')+'</details>').join('');
  root.innerHTML='<div class="tf-grid">'+panel('导入授权日快照',note('文件支持 CSV 或 JSON 数组，单批最多 20,000 行。相同市场、对象和日期的快照将更新覆盖。')+
    '<button class="btn" data-example>下载 JSON 示例</button>'+
    (u.guest?'<p><a href="#account">登录后导入私有数据</a></p>':u.role!=='owner'?note('工作区所有者可以导入数据。'):form('upload',field('数据来源标识','source','text','','required pattern="[A-Za-z0-9_-]{1,32}" placeholder="supplier-us"')+
    '<label>日快照文件<input required name="file" type="file" accept=".json,.csv"></label>','验证并导入')))+
    panel('数据口径','<dl class="tf-dl"><dt>成交额 / GMV</dt><dd>选择市场内商品日成交额之和，使用市场本币。</dd><dt>成交额环比</dt><dd>对比两个相邻等长窗口。基数为零或覆盖不足时显示缺失。</dd><dt>观看次数</dt><dd>视频与直播快照中记录的观看次数，未按观众去重。</dd><dt>数据来源</dt><dd>演示来源使用合成日快照。切换数据源可以单独研究授权记录。</dd></dl>')+
    panel('操作指南','<ol class="tf-guide"><li>选择市场、来源与研究窗口。</li><li>打开商品、店铺或达人榜，按成交或增长排序。</li><li>点击对象名称查看趋势与关联内容。</li><li>收藏候选对象，或为商品、直播、视频开启监控。</li><li>按当前筛选导出完整结果。</li></ol>')+
    (!u.guest&&u.role==='owner'?panel('累计快照转日增量',note('上传同一来源的累计快照，包含前一日基线、cumulative_gmv 和 cumulative_sales。转换后可下载日快照，再从上方导入。')+
      form('counters','<label>累计快照文件<input name="file" required type="file" accept=".json,.csv"></label>','转换并预览')):'')+
    panel('最新快照覆盖',history.coverage.map(x=>'<div class="tf-row"><b>'+esc(x.source)+' · '+esc(x.market)+'</b><time>'+esc(x.day)+'</time><span data-ui-label>'+x.rows+' 行</span></div>').join(''))+
    (deliveries?panel('交付时效',deliveries):'')+
    panel('快照修订',history.revisions.length?history.revisions.map(x=>'<details><summary data-source-text>'+esc([x.source,x.market,x.kind,x.id,x.date].join(' · '))+'</summary><time>'+esc(new Date(x.changed_at*1000).toLocaleString())+'</time><pre>'+esc(JSON.stringify(x.changes,null,2))+'</pre></details>').join('')+note('每个字段依次列出旧值和新值。金额字段以本币的百分之一计。'):note('暂无快照修订。'))+
    panel('导入记录',history.items.length?history.items.map(x=>'<div class="tf-row"><div><b>'+esc(x.filename)+'</b><p>'+esc(x.source)+' · '+esc(new Date(x.created*1000).toLocaleString())+'</p><small>'+esc(x.error||x.latest_date||'')+'</small></div><span data-ui-label>'+(x.status==='failed'?'失败':x.count+' 行')+'</span></div>').join(''):note('当前工作区暂无导入批次。'))+'</div>';
  root.querySelector('[data-example]').onclick=()=>download(new Blob([JSON.stringify(sampleRows,null,2)],{type:'application/json'}),'tikflowso-snapshot.json');
  mountForm(root,'counters',async(d,out)=>{
    if(d.file.size>10*1024*1024)throw Error('请选择小于 10 MB 的文件');
    const text=(await d.file.text()).replace(/^\uFEFF/,'');
    const result=await get('normalize-snapshots',d.file.name.toLowerCase().endsWith('.csv')?{csv:text}:{json:text});
    const reasons={baseline:'基线',gap:'缺少前一日',counter_decrease:'计数器下降'};
    show(out,localMessage('可导入日快照')+' '+result.rows.length+' / '+localMessage('跳过')+' '+result.skipped.length);
    for(const [list,label,file] of [[result.rows,'下载日快照 JSON','daily'],[result.skipped,'下载跳过明细','skipped']]){
      if(!list.length)continue;
      const button=document.createElement('button');button.type='button';button.className='btn';button.textContent=localMessage(label);
      button.onclick=()=>download(new Blob([JSON.stringify(list,null,2)],{type:'application/json'}),'tikflowso-'+file+'.json');
      out.append(' ',button);
    }
    if(result.skipped.length)out.append(document.createElement('br'),[...new Set(result.skipped.map(r=>localMessage(reasons[r.reason])))].join(' · '));
  });
  mountForm(root,'upload',async(d,out)=>{if(d.file.size>10*1024*1024)throw Error('请选择小于 10 MB 的文件');
    const raw=(await d.file.text()).replace(/^\uFEFF/,''),data={source:d.source,filename:d.file.name};
    if(d.file.name.toLowerCase().endsWith('.csv'))data.csv=raw;else data.json=raw;
    let r;
    try{r=await get('import',data);}catch(err){await resources(root);show(root.querySelector('form output'),err.message,true);return;}
    await resources(root);
    show(root.querySelector('form output'),'已导入 '+r.rows+' 行、'+r.entities+' 个对象。数据截止 '+r.date+'。');
    const a=document.createElement('a');a.dataset.uiLabel='';a.textContent='查看导入结果';a.href=link(r.kind,{source:r.source,market:r.market,date:r.date});root.querySelector('form output').append('　',a);
  });
}
async function contactBook(root,c){
  const me=await get('me');
  if(me.guest){root.innerHTML=panel('合作联系簿',note('登录后可查阅当前工作区已获授权的达人合作渠道。')+'<a class="btn primary" href="#account">登录或注册</a>');return;}
  const p={source:c.source,market:c.market,...(c.params.id?{id:c.params.id}:{})};
  const search=async(q='')=>{
    const params=new URLSearchParams({...p,q});
    const {items}=await get('contacts?'+params);
    root.querySelector('[data-contact-list]').innerHTML=items.length?items.map(r=>'<article class="tf-row"><div><b>'+esc(r.name)+'</b><p>'+esc(r.email||r.channel)+'</p>'+ (r.email&&r.channel?'<p>'+esc(r.channel)+'</p>':'') +'<small>'+esc(r.rights)+'</small></div>'+(me.role==='owner'?'<button class="btn" data-remove="'+esc(r.id)+'">移除</button>':'')+'</article>').join(''):note('当前筛选范围还没有授权合作记录。');
    const exp=root.querySelector('[data-contacts-export]');if(exp)exp.href='/api/contacts/export?'+params;
  };
  const editor=me.role==='owner'?panel('登记合作渠道',form('contact',field('达人 ID','id','text',c.params.id||'','required')+field('合作邮箱','email','email')+field('合作渠道链接','channel','url')+field('授权依据与用途','rights','text','','required'),'保存记录')+
    form('contacts-file','<label>批量导入 CSV<input type="file" name="file" required accept=".csv"></label>'+note('列名使用 id、email、channel、rights。每行需要邮箱或合作链接，并填写授权依据。'),'导入联系簿')):'';
  root.innerHTML='<a class="tf-back" href="#tools">← 运营工具</a><div class="tf-grid">'+panel('合作联系簿 · '+esc(c.market),
    form('findcontacts',field('搜索姓名、ID 或邮箱','q'),'搜索')+'<div data-contact-list></div>'+(me.role==='owner'&&me.plan==='team'?'<a class="btn" data-contacts-export>导出已筛选记录</a>':''))+editor+'</div>';
  await search();
  mountForm(root,'findcontacts',async(d,out)=>{await search(d.q);show(out,'');});
  mountForm(root,'contact',async(d,out)=>{await get('contacts',{...p,rows:[d]});await search();show(out,'合作记录已保存');});
  mountForm(root,'contacts-file',async(d,out)=>{const r=await get('contacts',{...p,csv:await d.file.text()});await search();show(out,'已导入 '+r.rows+' 条合作记录');});
  root.querySelector('[data-contact-list]').onclick=async e=>{const b=e.target.closest('[data-remove]');if(!b)return;try{await get('contacts',{...p,id:b.dataset.remove,remove:true});await search();}catch(err){show(root.querySelector('output'),err.message,true);}};
}

async function exportCenter(root){
  const {items}=await get('exports');
  const labels={queued:'排队中',running:'生成中',ready:'已生成',failed:'失败'};
  root.innerHTML=panel('后台导出',note('文件保留 7 天；刷新或离开页面后任务继续。')+
    '<button class="btn" data-refresh-jobs>刷新任务</button>'+items.map(r=>'<article class="tf-row"><div><b>#'+r.job+' · '+esc(r.params.kind)+'</b><p>'+
    esc([r.params.source||'demo',r.params.market||'US',r.params.date,localMessage(labels[r.state])].join(' · '))+'</p>'+esc(r.error||'')+'</div>'+
    (r.state==='ready'?'<a class="btn" download href="/api/exports/file?job='+r.job+'">下载 CSV · '+r.rows+' 行</a>':'')+'</article>').join('')+
    (!items.length?note('在任一榜单选择“后台导出”即可创建任务。'):''));
  root.querySelector('[data-refresh-jobs]').onclick=()=>exportCenter(root);
  if(items.some(r=>r.state==='queued'||r.state==='running')){
    const old=root.firstElementChild;
    setTimeout(()=>{if(old?.isConnected)exportCenter(root).catch(e=>show(old.appendChild(document.createElement('output')),e.message,true));},1500);
  }
}
async function transcribeMedia(root){
  const config=await get('config');
  root.innerHTML=panel('本机音轨转写',note(config.transcription?'FFmpeg + Whisper · 支持含音轨的视频和音频，最大 48 MiB、10 分钟。':'本机缺少 FFmpeg、whisper-cli 或模型文件。')+
    form('transcribe','<label>音频或视频<input name="media" type="file" required accept="audio/*,video/*"></label>'+
    '<label>语言<select name="language"><option value="auto">自动识别</option><option value="zh">中文</option><option value="en">English</option></select></label>','转写音轨'));
  mountForm(root,'transcribe',async(d,out)=>{
    if(!d.media.size||d.media.size>48*1024*1024)throw Error('文件大小需在 1 字节至 48 MiB 之间');
    const res=await fetch('/api/transcribe?language='+encodeURIComponent(d.language),{method:'POST',headers:{'Content-Type':'application/octet-stream'},body:d.media});
    const r=await res.json();if(!res.ok)throw Error(r.error);
    show(out,r.text||'未识别出语音');
    if(r.srt){const btn=document.createElement('button');btn.type='button';btn.className='btn';btn.textContent='下载 SRT 字幕';
      btn.onclick=()=>download(new Blob([r.srt],{type:'text/plain;charset=utf-8'}),'tikflowso-captions.srt');out.append(document.createElement('br'),btn);}
  });
}
async function alertCenter(root){
  const {items}=await get('alerts');
  root.innerHTML=panel('监控通知',items.length? items.map(r=>'<article class="tf-row"><div><b>'+esc(r.title)+'</b><p>'+esc(r.day)+' · '+esc(labels[r.metric])+' '+esc(r.value)+' ≥ '+esc(r.threshold)+'</p><small>'+esc(r.delivery||'站内通知')+'</small></div>'+
    (r.seen?'已读':'<button class="btn" data-seen="'+r.aid+'">标为已读</button>')+'</article>').join(''):note('达到监控阈值的最新快照将出现在这里。'));
  root.querySelectorAll('[data-seen]').forEach(b=>b.onclick=async()=>{try{await get('alerts/read',{id:Number(b.dataset.seen)});await alertCenter(root);}catch(e){b.textContent=e.message;}});
}

export async function renderTools(root,c){
  initCss();root.onclick=null;
  const view=c.view,key=view==='agent'?'agent':c.params?.tool;
  try{
    if(view==='admin'){const {renderAdmin}=await import('./admin.js');return renderAdmin(root);}
    if(view==='account')return await account(root,c);
    if(view==='api')return await apiPage(root);
    if(view==='resources')return await resources(root);
    if(view==='favorites'||view==='monitor'){await researchLists(root,c,view);return;}
    if(key==='exports')return await exportCenter(root);
    if(key==='transcribe')return await transcribeMedia(root);
    if(key==='alerts')return await alertCenter(root);
    if(key==='contacts')return await contactBook(root,c);
    if(key==='partners'){const {renderPartnerships}=await import('./partnerships.js');return await renderPartnerships(root,c);}
    if(key&&Object.hasOwn(tools,key)){
      await creative(root,c,key);
      if(view!=='agent')root.insertAdjacentHTML('afterbegin','<a class="tf-back" href="#tools">← 所有工具</a>');
      return;
    }
    root.innerHTML='<div class="tf-tools">'+Object.entries({...tools,exports:['后台导出','查看任务进度，下载完整榜单。'],transcribe:['本机音轨转写','识别音轨并导出带时间码的字幕。'],alerts:['监控通知','查看阈值提醒和投递状态。'],contacts:['合作联系簿','登记和查找已授权的达人合作渠道。'],partners:['合作与货盘','整理素材、商品清单与推荐记录。']}).map(([id,[label,desc]])=>'<a class="panel tf-tool" href="'+toolHref(id)+'"><span class="tf-tool-name">'+esc(label)+'<span>↗</span></span><small>'+esc(desc)+'</small></a>').join('')+'</div>';
  }catch(err){root.innerHTML=panel('加载失败',note(esc(err.message))+'<button class="btn" data-retry>重试</button>');root.querySelector('[data-retry]').onclick=()=>renderTools(root,c);}
}
