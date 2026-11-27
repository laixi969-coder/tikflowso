const {test} = require('node:test');
const assert = require('node:assert/strict');
const {checks} = require('./grade.cjs');
const scope={source:'ws-2-blue',market:'US',date:'2026-03-04',days:1};
const vars={scope,language:'en-US',truth:{type:'overview',currency:'USD',gmv:61,units:14}};
const href='#dashboard?'+new URLSearchParams(scope);
const sample={status:200,mode:'Database query',scope,references:[{href,label:'Market overview'}],
  result:'US · 1 day ending 2026-03-04: product GMV 61 USD, 14 units sold.'};
test('grounded control passes',()=>assert.deepEqual(checks(sample,vars),[]));
test('reject fabricated monetary amounts, swapped units, unsupported currencies, dates, markets and in-text links',()=>{
  for(const result of [sample.result+' Estimated spend $999.',sample.result+' GMV 14.',sample.result.replace('14 units','61 units'),
    sample.result.replace('61 USD','61 GBP'),sample.result.replace('03-04','03-03'),sample.result.replace('US ·','GB ·'),
    sample.result+' [Second source](#detail?source=red)',sample.result+' [Extra](#agent?source=red)',
    sample.result+' USD 61 million.',sample.result+' USD 61e4.'])
    assert.ok(checks({...sample,result},vars).length,result);
});
test('check each structured citation even when the correct citation is present',()=>{
  for(const extra of [href.replace('blue','red'),href.replace('US','GB'),href+'&source=ws-2-blue'])
    assert.ok(checks({...sample,references:[{href,label:'OK'},{href:extra,label:'Other'}]},vars).length);
});
test('denial and missing data cannot leak results, and offline fallback cannot qualify a candidate',()=>{
  assert.ok(checks({...sample,status:403},{...vars,truth:{type:'denied'}}).length);
  assert.ok(checks({...sample,result:'Insufficient data, GMV 1 USD.',references:[]},{...vars,truth:{type:'empty'}}).length);
  assert.ok(checks(sample,{...vars,candidate:true}).length);
});

test('reject contradictory totals, a different dashboard filter and facts in a denial message',()=>{
  assert.ok(checks({...sample,result:sample.result+' In total, 61 units sold.'},vars).length);
  assert.ok(checks({...sample,references:[{label:'Market overview',href:href+'&category=another'}]},vars).length);
  assert.ok(checks({status:403,error:'Not visible: Hidden Stock'}, {...vars,truth:{type:'denied',privateMarkers:['Hidden Stock']}}).length);
  assert.ok(checks({...sample,result:'Insufficient data. Sales were 1 unit.',references:[]},{...vars,truth:{type:'empty'}}).length);
});
test('ranking needs the requested metric, exact references and the right value beside each entity',()=>{
  const rows=[{id:'cup',label:'Harbor Cup',value:41},{id:'lamp',label:'Atlas Lamp',value:20}];
  const v={...vars,truth:{type:'ranking',metric:'sales',kind:'products',currency:'USD',rows}};
  const answer={...sample,result:'US · 1 day ending 2026-03-04 ranked by units sold:\n1. Harbor Cup 41\n2. Atlas Lamp 20',
    references:rows.map(r=>({label:r.label,href:'#detail?'+new URLSearchParams({...scope,kind:'products',id:r.id})}))};
  assert.deepEqual(checks(answer,v),[]);
  for(const result of [answer.result.replace('units sold','views'),
    answer.result.replace('Cup 41','Cup 20 (previously 41)'), answer.result+'\n3. Unknown item 41',
    answer.result.replace('1. Harbor','2. Harbor')])assert.ok(checks({...answer,result},v).length,result);
  for(const tail of ['&id=different','&kind=shops']){
    const refs=answer.references.map(r=>({...r,href:r.href+tail}));
    assert.ok(checks({...answer,references:refs},v).length);
  }
});
test('HTTP transport status wins over status in response body',async()=>{
  const WorkspaceAssistant=require('./provider.cjs');
  const fs=require('node:fs'),os=require('node:os'),path=require('node:path'),http=require('node:http');
  const dir=fs.mkdtempSync(path.join(os.tmpdir(),'eval-provider-test-'));
  const server=http.createServer((_req,res)=>{res.writeHead(200,{'Content-Type':'application/json'});res.end('{"status":403}');});
  const saved=process.env.TIKFLOWSO_EVAL_SESSION;
  try{
    await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
    process.env.TIKFLOWSO_EVAL_SESSION=path.join(dir,'session.json');
    fs.writeFileSync(process.env.TIKFLOWSO_EVAL_SESSION,JSON.stringify({base:'http://127.0.0.1:'+server.address().port,cookie:''}));
    const a=await new WorkspaceAssistant().callApi('hello',{vars});
    assert.equal(JSON.parse(a.output).status,200);
  }finally{
    if(saved===undefined)delete process.env.TIKFLOWSO_EVAL_SESSION;else process.env.TIKFLOWSO_EVAL_SESSION=saved;
    await new Promise(resolve=>server.close(resolve));
    fs.rmSync(dir,{recursive:true,force:true});
  }
});
