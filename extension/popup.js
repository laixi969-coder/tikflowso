const form = document.querySelector("#open");
const address = document.querySelector("#workspace");
const message = document.querySelector("#message");
const selection = document.querySelector("#selection");
const msg = key => chrome.i18n.getMessage(key);
document.documentElement.lang=chrome.i18n.getUILanguage();
document.title=msg("name");
document.querySelector('label[for="workspace"]').textContent=msg("workspace");
form.querySelector("button").textContent=msg("open");
selection.textContent=msg("loading");
let selected;

async function prepare() {
  const [tab] = await chrome.tabs.query({currentWindow: true, active: true});
  selected = identifyTikTok(tab?.url);
  const settings = await chrome.storage.local.get("workspace");
  if (settings.workspace) address.value = settings.workspace;
  selection.textContent = selected
    ? msg(selected.kind) + " · " + selected.query
    : msg("unsupported");
  form.querySelector("button").disabled = !selected;
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!selected) return;
  try {
    const workspace = new URL(address.value);
    const local = ["localhost", "127.0.0.1", "[::1]"].includes(workspace.hostname);
    if (workspace.username || workspace.password ||
        !(workspace.protocol === "https:" || (local && workspace.protocol === "http:"))) {
      throw Error(msg("invalid"));
    }
    workspace.search = "";
    workspace.hash = "";
    await chrome.storage.local.set({workspace: workspace.href});
    workspace.hash = "search?" + new URLSearchParams({q: selected.query, kind: selected.kind});
    await chrome.tabs.create({url: workspace.href});
    window.close();
  } catch (err) {
    message.textContent = err.message;
  }
});

prepare().catch(() => { selection.textContent = msg("error"); });
