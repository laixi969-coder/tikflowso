// Only the question and research scope go to TikFlowSo. Gold answers stay in the grader.
const fs = require('node:fs');

class WorkspaceAssistant {
  id() { return 'tikflowso-research-http'; }
  async callApi(prompt, context) {
    const session = JSON.parse(fs.readFileSync(process.env.TIKFLOWSO_EVAL_SESSION, 'utf8'));
    const {scope, language} = context.vars;
    const start = performance.now();
    const response = await fetch(session.base + '/api/assistant/ask', {
      method: 'POST', redirect: 'error', signal: AbortSignal.timeout(60000),
      headers: {'Content-Type': 'application/json', Cookie: session.cookie},
      body: JSON.stringify({...scope, locale:language, text:prompt}),
    });
    const body = await response.json();
    return {output: JSON.stringify({...body, status:response.status}), metadata:{httpMs:performance.now()-start}};
  }
}
module.exports = WorkspaceAssistant;
