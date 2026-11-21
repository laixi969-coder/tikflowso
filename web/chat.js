let chatListeners;
const copy={
  title:['数据助手','Data assistant'],history:['历史对话','Chat history'],fresh:['新对话','New chat'],remove:['删除对话','Delete chat'],askRemove:['永久删除所选对话？','Permanently delete this chat?'],
  library:['研究模板','Research templates'],all:['全部模板','All templates'],general:['自由提问','Free question'],
  question:['研究问题','Research question'],focus:['对象名称、ID 或品类（可选）','Object name, ID or category (optional)'],
  comments:['已授权的评论，每行一条（可选）','Authorized comments, one per line (optional)'],
  run:['查询数据','Run query'],runSkill:['运行模板','Run template'],edit:['编辑并下载草稿','Edit and download draft'],
  download:['下载文本','Download text'],draft:['工作草稿','Working draft'],
  local:['本地模板按所选对象、市场和日期查询。可用筛选字段限定对象，再编辑生成的草稿。','Local templates use the selected objects, market and dates. Set the object filter to narrow the results, then edit the generated draft.'],
  cloud:['工作区授权后，提问与当前查询结果会发送到指定模型。评论和历史对话由账户页单独控制。','The designated model receives the question and current evidence when the workspace permits it. Account settings control comments and conversation history.'],
  day:['天','days']
};
const questions=[
  ['哪个商品销量最高？','Which products sell the most?'],
  ['哪些达人涨粉最快？','Which creators gained followers?'],
  ['市场概览','Market overview']
];

export async function renderChat(root,c,{get,form,panel,esc,scopeFor,mountForm,show}){
  const [config,history,library]=await Promise.all([get('config'),get('assistant/chats'),get('assistant/skills')]);
  const lang=()=>document.documentElement.lang==='en-US'?'en':'zh';
  const word=key=>copy[key][lang()==='en'?1:0];
  const label=key=>'<span data-chat-label="'+key+'">'+esc(word(key))+'</span>';
  const skills=new Map(library.items.map(s=>[s.id,s]));
  const groups=new Map(library.groups.map(g=>[g.id,g]));
  if(!document.querySelector('#chat-styles')){
    const css=document.createElement('link');css.id='chat-styles';css.rel='stylesheet';css.href='/chat.css';document.head.append(css);
  }
  let active='',category='',loaded=[],version=0;
  const edits=new Map();
  root.innerHTML=panel(label('title'),
    '<div class="tf-inline"><label>'+label('history')+' <select data-history><option value="">'+esc(word('fresh'))+'</option></select></label><button type="button" class="btn" data-new>'+label('fresh')+'</button><button type="button" class="btn" data-remove-chat>'+label('remove')+'</button></div>'+ 
    '<div data-turns></div>'+form('gen',
      '<div class="tf-inline">'+questions.map((_,i)=>'<button type="button" class="btn" data-question="'+i+'"></button>').join('')+'</div>'+
      '<div data-skill-fields hidden><div class="tf-inline"><strong data-selected-skill></strong><button class="btn" type="button" data-clear-skill>'+label('general')+'</button></div>'+
      '<label>'+label('focus')+'<input name="focus" maxlength="150"></label>'+
      '<label data-comments-field hidden>'+label('comments')+'<textarea rows="4" name="comments" maxlength="6000"></textarea></label></div>'+
      '<label>'+label('question')+'<textarea name="text" rows="3" maxlength="8000" required></textarea></label>'+
      '<p class="muted tf-note">'+label(config.model?'cloud':'local')+'</p>',word('run'))) +
    panel(label('library'),'<div class="tf-inline" data-groups></div><div class="research-skill-grid" data-skill-grid></div>');
  const select=root.querySelector('[data-history]'),newChat=root.querySelector('[data-new]'),turns=root.querySelector('[data-turns]');
  const input=root.querySelector('[name=text]'),focus=root.querySelector('[name=focus]'),comments=root.querySelector('[name=comments]');
  const send=root.querySelector('button[type=submit]'),output=root.querySelector('output');
  for(const h of history.items)select.add(new Option(h.title,h.id));
  function renderLibrary(){
    const language=lang();
    const filterButton=(id,text)=>'<button class="btn" type="button" data-group="'+id+'" aria-pressed="'+(category===id)+'">'+esc(text)+'</button>';
    root.querySelector('[data-groups]').innerHTML=filterButton('',word('all'))+library.groups.map(g=>filterButton(g.id,g[language])).join('');
    root.querySelector('[data-skill-grid]').innerHTML=library.items.filter(s=>!category||s.group===category).map(s=>
      '<button type="button" class="research-skill" data-skill="'+s.id+'" aria-pressed="'+(active===s.id)+'"><strong>'+esc(s.title[language])+
      '</strong><span>'+esc(s.prompt[language])+'</span></button>').join('');
  }
  function selectSkill(id,replaceText=true){
    const before=skills.get(active),skill=skills.get(id);
    active=skill?id:'';
    root.querySelector('[data-skill-fields]').hidden=!skill;
    root.querySelector('[data-comments-field]').hidden=id!=='interest';
    root.querySelector('[data-selected-skill]').textContent=skill?groups.get(skill.group)[lang()]+' · '+skill.title[lang()]:'';
    send.textContent=word(skill?'runSkill':'run');
    if(replaceText){
      if(skill||before){input.value=skill?skill.prompt[lang()]:'';focus.value='';comments.value='';}
    }
    renderLibrary();
  }
  function renderTurns(){
    turns.innerHTML=loaded.map((a,i)=>{
      const refs=(a.references||[]).filter(r=>r.href?.startsWith('#')).map(r=>'<a href="'+esc(r.href)+'">'+esc(r.label)+'</a>').join(' · ');
      const draft=a.skill?'<details class="research-draft"><summary>'+esc(word('edit'))+'</summary><label>'+esc(word('draft'))+'<textarea rows="9" data-draft="'+i+'">'+esc(edits.get(i)??a.result)+'</textarea></label>'+
        '<button type="button" class="btn" data-download-draft="'+i+'">'+esc(word('download'))+'</button></details>':'';
      return '<article class="research-turn"><h3>'+esc(a.question)+'</h3><small>'+esc([a.scope.source,a.scope.market,a.scope.date,a.scope.days+' '+word('day'),a.mode].filter(Boolean).join(' · '))+'</small>'+
        '<p data-source-text>'+esc(a.result)+'</p>'+refs+draft+'</article>';
    }).join('');
  }
  turns.oninput=e=>{if(e.target.hasAttribute('data-draft'))edits.set(Number(e.target.dataset.draft),e.target.value);};
  turns.onclick=e=>{
    const button=e.target.closest('[data-download-draft]');
    if(!button)return;
    const i=Number(button.dataset.downloadDraft),a=loaded[i];
    const lines=[edits.get(i)??a.result,...(a.references||[]).map(r=>r.label+' '+new URL(r.href,location.href).href)];
    const url=URL.createObjectURL(new Blob([lines.join('\n')],{type:'text/plain;charset=utf-8'}));
    const anchor=document.createElement('a');anchor.href=url;anchor.download='tikflowso-'+a.skill+'.txt';anchor.click();
    setTimeout(()=>URL.revokeObjectURL(url),1000);
  };
  function localize(){
    const selected=skills.get(active);
    if(selected&&[selected.prompt.zh,selected.prompt.en].includes(input.value))input.value=selected.prompt[lang()];
    root.querySelectorAll('[data-chat-label]').forEach(el=>el.textContent=word(el.dataset.chatLabel));
    root.querySelectorAll('[data-question]').forEach(b=>b.textContent=questions[Number(b.dataset.question)][lang()==='en'?1:0]);
    select.options[0].textContent=word('fresh');
    selectSkill(active,false);renderTurns();
  }
  localize();
  chatListeners?.abort();chatListeners=new AbortController();
  const signal=chatListeners.signal;
  window.addEventListener('tikflowso:locale',localize,{signal});
  window.addEventListener('hashchange',()=>chatListeners.abort(),{once:true,signal});
  root.querySelector('[data-groups]').onclick=e=>{
    const b=e.target.closest('[data-group]');if(b){category=b.dataset.group;renderLibrary();}
  };
  root.querySelector('[data-skill-grid]').onclick=e=>{
    const b=e.target.closest('[data-skill]');if(!b||send.disabled)return;
    selectSkill(b.dataset.skill);input.focus();
  };
  root.querySelector('[data-clear-skill]').onclick=()=>{if(!send.disabled){selectSkill('');input.focus();}};
  async function switchChat(){
    const token=++version;
    loaded=[];edits.clear();selectSkill('');renderTurns();input.value='';show(output,'');send.disabled=!!select.value;
    if(!select.value)return;
    try{const data=await get('assistant/chats?chat='+encodeURIComponent(select.value));if(token===version){loaded=data.turns;renderTurns();}}
    catch(e){if(token===version){select.value='';show(output,e.message,true);}}
    finally{if(token===version)send.disabled=false;}
  }
  root.querySelector('[data-remove-chat]').onclick=async()=>{
    if(!select.value||select.disabled||!window.confirm(word('askRemove')))return;
    try{await get('assistant/chats/remove',{chat:select.value});select.remove(select.selectedIndex);select.value='';await switchChat();}
    catch(e){show(output,e.message,true);}
  };
  select.onchange=switchChat;
  newChat.onclick=()=>{select.value='';switchChat();input.focus();};
  root.querySelectorAll('[data-question]').forEach(b=>b.onclick=()=>{if(!send.disabled){selectSkill('');input.value=b.textContent;input.form.requestSubmit();}});
  mountForm(root,'gen',async(d,out)=>{
    select.disabled=newChat.disabled=true;
    try{
      const params=active?{skill:active,focus:d.focus,...(active==='interest'?{comments:d.comments}:{})}:{};
      const a=await get('assistant/ask',{...scopeFor(c),...params,text:d.text,locale:document.documentElement.lang,chat:select.value||null});
      if(!select.value){select.add(new Option(d.text.trim().slice(0,80),a.chat),1);select.value=String(a.chat);}
      loaded.push({...a,question:d.text});selectSkill('');renderTurns();input.value='';show(out,a.mode);
    }finally{select.disabled=newChat.disabled=false;}
  });
  const requested=String(c.params?.chat||'');
  if(requested&&history.items.some(h=>String(h.id)===requested)){select.value=requested;await switchChat();}
}
