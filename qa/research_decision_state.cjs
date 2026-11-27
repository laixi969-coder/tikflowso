// Repeat a save from a redrawn product panel, then complete two different saves in reverse order.
const assert=require('node:assert/strict');
const test=require('node:test');
test('redrawing a saved decision cannot duplicate pending saves or overwrite the current response',async()=>{
  const oldDocument=globalThis.document;
  const output={textContent:''};
  const form=reason=>({elements:{reason:{value:reason}},button:{disabled:false},querySelector(){return this.button;}});
  let active=form('A');
  globalThis.document={
    readyState:'loading',addEventListener(){},
    querySelector(selector){return selector.includes('output')?output:active.button;},
  };
  try{
    const {submitDecision,decisionForm}=await import('../web/research-decisions.js');
    const metrics={covered_days:1,sales_exact:'1',gmv:'2.00',avg_price:'2.00'};
    const data={decision_evidence:{version:'1',currency:'USD',current:metrics,previous:metrics,
      days:1,videos:[],video_count:0,product:'p',date:'2026-11-15',start_date:'2026-11-15',prev_date:'2026-11-14',previous_end:'2026-11-14'}};
    let calls=0,rejectOld;
    const pending=submitDecision(active,data,()=>{calls++;return new Promise((_r,j)=>{rejectOld=j;});},()=>data);
    assert.match(decisionForm(data,String),/type="submit" disabled/);
    active=form('A');
    await submitDecision(active,data,()=>{calls++;return Promise.resolve();},()=>data);
    assert.equal(calls,1);
    active=form('B');
    data.decisionDraft='B';
    await submitDecision(active,data,()=>{calls++;return Promise.resolve();},()=>data);
    assert.equal(calls,2);
    rejectOld(Error('Old network failure'));
    await pending;
    assert.equal(data.decisionSaved,true);
    assert.equal(data.decisionDraft,'B');
    assert.equal(active.button.disabled,false);
    assert.equal(output.textContent,'选品判断已保存');
    assert.doesNotMatch(decisionForm(data,String),/type="submit" disabled/);
  }finally{globalThis.document=oldDocument;}
});
