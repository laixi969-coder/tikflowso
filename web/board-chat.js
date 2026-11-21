let conversation;

function currentChat(scope) {
  const key = JSON.stringify([scope.source, scope.market, scope.date, scope.days]);
  if (conversation?.key !== key) conversation = {key, chat:null, answer:null, question:"", error:"", busy:false};
  return conversation;
}

export function boardAssistant(scope, {esc, href, t, icon}) {
  const state = currentChat(scope), answer = state.answer;
  const full = href("agent", {...scope, chat:state.chat});
  const references = (answer?.references || []).filter(r => r.href?.startsWith("#"));
  return '<section class="panel board-agent"><form id="board-question"><label class="inline-search">'+icon("agent",16)+
    '<input name="question" required maxlength="8000" aria-label="'+esc(t("研究问题"))+'" placeholder="'+esc(t("向数据助手提问"))+'"></label>'+
    '<button class="primary"'+(state.busy?' disabled':'')+'>'+esc(t("提问"))+'</button></form>'+
    '<div class="board-answer" aria-live="polite">'+(state.busy?esc(t("正在读取数据…")):'')+
    (state.error?'<p role="alert">'+esc(state.error)+'</p>':'')+(answer?'<h3>'+esc(state.question)+'</h3><small>'+esc(t(answer.mode))+
    '</small><p class="board-answer-text">'+esc(answer.result)+'</p>'+references.map(r=>'<a class="text-link" href="'+esc(r.href)+'">'+esc(r.label)+'</a>').join(' · '):'')+
    '</div><a class="text-link board-open-chat" href="'+esc(full)+'">'+esc(t("打开完整对话"))+'</a></section>';
}

export async function askOnBoard(form, scope, helpers) {
  const state=currentChat(scope), question=form.elements.question.value.trim();
  if (!question || state.busy) return;
  state.busy=true;
  state.error="";
  const refresh=()=>{
    const target=document.querySelector(".board-agent");
    if(target && conversation===state) target.outerHTML=boardAssistant(scope,helpers);
  };
  refresh();
  try {
    const answer=await helpers.api("assistant/ask", {...scope, chat:state.chat, text:question, locale:document.documentElement.lang}, true);
    Object.assign(state,{answer,chat:answer.chat,question});
  } catch (e) {
    state.error=e.message;
  } finally {
    state.busy=false;
    refresh();
    if (state.error && conversation===state) {
      const field=document.querySelector("#board-question input");
      if (field) field.value=question;
    }
  }
}
