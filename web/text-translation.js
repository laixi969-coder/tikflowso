import { localeTag, localMessage } from "./locale.js";

export function translateText(api, source, scope, searchWith) {
  const dialog = document.createElement("dialog");
  dialog.className = "text-translation";
  dialog.setAttribute("aria-label",localMessage("文本翻译"));
  dialog.innerHTML = '<header><h2 data-ui-label>文本翻译</h2><button type="button" class="btn" data-close>关闭</button></header><div></div>';
  dialog.querySelector("[data-close]").onclick = () => dialog.close();
  dialog.onclose = () => dialog.remove();
  document.body.append(dialog);
  dialog.showModal();
  renderTranslation(dialog.querySelector("div"),api,scope,source,searchWith ? translation=>{
    dialog.close();searchWith(translation);
  }:null);
}

export async function renderTranslation(root,api,scope,source=null,searchWith=null) {
  root.innerHTML = '<form class="translation-form"><label><span data-ui-label>原文</span><textarea required rows="2" maxlength="8000"></textarea></label>'+
    '<label><span data-ui-label>目标语言</span><select></select></label>'+
    '<p data-ui-label>翻译时将原文发送给已配置的文本模型。</p>'+
    '<button class="primary" disabled>翻译</button></form><output role="status"></output>'+
    (searchWith?'<button type="button" class="btn" data-use hidden>用译文搜索</button>':'');
  const input = root.querySelector("textarea");
  input.value = source || "";
  input.readOnly = source !== null;
  const select = root.querySelector("select");
  const languages = ["en","zh","ja","ko","fr","de","it","es","pt","id","ms","th","vi","fil"];
  const names = new Intl.DisplayNames([localeTag()], {type:"language"});
  for (const id of languages) select.add(new Option(names.of(id),id));
  select.value = localeTag() === "zh-CN" && !/[\u3400-\u9fff]/u.test(input.value) ? "zh" : "en";
  const form = root.querySelector("form"), run = form.querySelector("button");
  form.onsubmit = event => event.preventDefault();
  const output = root.querySelector("output"), use = root.querySelector("[data-use]");
  try {
    const config = await api("config");
    if (!config.model) {
      output.textContent = localMessage("文本翻译待配置，请管理员启用文本模型。");
      return;
    }
    run.disabled = false;
  } catch (error) {
    output.textContent = localMessage(error.message);
    return;
  }
  input.oninput = select.onchange = () => { output.textContent=""; if (use) use.hidden=true; };
  form.onsubmit = async event => {
    event.preventDefault();
    if (run.disabled) return;
    run.disabled = select.disabled = true;
    input.readOnly = true;
    if (use) use.hidden = true;
    output.textContent = localMessage("处理中…");
    try {
      const response = await api("generate", {tool:"text_translate",text:input.value,target:select.value,...scope}, true);
      output.textContent = response.result;
      if (use) {
        use.hidden = false;
        use.onclick = () => searchWith(response.result);
      }
    } catch (error) { output.textContent = localMessage(error.message); }
    finally { run.disabled = select.disabled = false; input.readOnly = source !== null; }
  };
}
