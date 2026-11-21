// Rebuild the synthetic media, then exercise the image and video tool pages against a cloud protocol fixture or the selected live cloud provider.
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const assert = require('node:assert/strict');
const {spawn,execFileSync} = require('node:child_process');
const {once} = require('node:events');
const {createInterface} = require('node:readline');
const {chromium} = require(process.env.PLAYWRIGHT_CORE || '/opt/homebrew/lib/node_modules/rea-agents/node_modules/playwright-core');
const root=path.resolve(__dirname,'..'), samples=path.join(root,'qa/samples/vision');
const live=process.argv.includes('--live'), tmp=fs.mkdtempSync(path.join(os.tmpdir(),'tikflowso-vision-'));
const reportDir=path.join(root,'docs/视觉验收',live?'live':'contract');
const env={...process.env};
const adminTest=process.argv.includes('--admin');
const observedPrompts=[];
const keys=['DASHSCOPE_API_KEY','ARK_API_KEY','OPENROUTER_API_KEY','ATLASCLOUD_API_KEY','DEEPSEEK_API_KEY'];
const visual=k=>keys.includes(k)||/^TIKFLOWSO_(VISION_|(?:BAILIAN|VOLCENGINE|OPENROUTER|ATLAS|DEEPSEEK|CUSTOM)_(?:MODEL|BASE_URL)$|MODEL_KEY$)/.test(k);
for(const k of Object.keys(env))if(k.startsWith('STRIPE_')||k.startsWith('TIKFLOWSO_')||keys.includes(k)){
  if(!live||!visual(k))delete env[k];
}
env.TIKFLOWSO_ENV_FILE=path.join(tmp,'isolated.env');
if(live){
  const overrides=path.join(root,'.data/tikflowso.providers.json');
  if(fs.existsSync(overrides))fs.copyFileSync(overrides,path.join(tmp,'qa.providers.json'));
  const source=process.env.TIKFLOWSO_ENV_FILE||path.join(root,'.env');
  const filtered=(fs.existsSync(source)?fs.readFileSync(source,'utf8'):'').split(/\r?\n/).filter(l=>visual(l.split('=')[0])).join('\n');
  fs.writeFileSync(env.TIKFLOWSO_ENV_FILE,filtered,{mode:0o600});
}
async function fixtureGateway(){
  const http=require('node:http');
  const service=http.createServer(async(req,res)=>{
    try{
      const expectedKey=adminTest?'contract-only-'+req.url.split('/')[2]:'contract-only';
      assert.equal(req.headers.authorization,'Bearer '+expectedKey);
      if(req.url.endsWith('/models')){
        res.writeHead(200,{'Content-Type':'application/json'});
        res.end(JSON.stringify({data:[{id:'fixture-vision',input_modalities:['image','text']},{id:'text-only',input_modalities:['text']}]}));return;
      }
      let body='';for await(const b of req)body+=b;
      const data=JSON.parse(body), [prompt,picture]=data.messages.find(m=>m.role==='user').content;
      assert.equal(data.model,'fixture-vision');
      observedPrompts.push(data.messages.find(m=>m.role==='system')?.content);
      if(!picture){res.end(JSON.stringify({choices:[{message:{content:'Fixture text output'}}]}));return;}
      assert.ok(picture.image_url.url.startsWith('data:image/'));
      let output;
      if(prompt.text.includes('first printed line'))output={title:'Green Tea'};
      else if(prompt.text.includes('OCR line')){
        const rows=JSON.parse(prompt.text.slice(prompt.text.indexOf('[{'),prompt.text.indexOf(' Return only valid JSON')));
        output={lines:rows.map(r=>({id:r.id,translation:({'Green Tea':'绿茶','No added sugar':'无添加糖','蓝色水杯':'Blue water cup'})[r.text]||'Capacity 500 ml'}))};
      }else if(prompt.text.includes('Read visible text')){
        const bytes=Buffer.from(picture.image_url.url.split(',')[1],'base64');
        const pixels=b=>execFileSync('ffmpeg',['-loglevel','error','-i','pipe:0','-vf','scale=32:18','-frames:v','1','-f','rawvideo','-pix_fmt','gray','pipe:1'],{input:b});
        const actual=pixels(bytes);
        const nearest=['en','zh','empty'].map(name=>{
          const ref=pixels(fs.readFileSync(path.join(samples,name+'.png')));
          return [name,actual.reduce((sum,n,i)=>sum+Math.abs(n-ref[i]),0)];
        }).sort((a,b)=>a[1]-b[1])[0][0];
        const lines={en:[['Green Tea','绿茶'],['No added sugar','无添加糖']],zh:[['蓝色水杯','Blue water cup'],['容量 500 毫升','Capacity 500 ml']],empty:[]};
        output={blocks:lines[nearest].map(([original,translation],i)=>({original,translation,bbox:i?[70,560,540,690]:[70,250,450,385]}))};
      }else if(prompt.text.includes('同一镜头')){
        const jpg=Buffer.from(picture.image_url.url.split(',')[1],'base64');
        const rgb=execFileSync('ffmpeg',['-loglevel','error','-i','pipe:0','-vf','scale=40:10','-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','pipe:1'],{input:jpg});
        const px=(5*40+10)*3;
        output={subject:rgb[px+1]>120?'黄色圆形':'红色方块',action:'静止',composition:'居中'};
      }else throw Error('Unknown fixture prompt');
      res.writeHead(200,{'Content-Type':'application/json'});res.end(JSON.stringify({choices:[{finish_reason:'stop',message:{content:JSON.stringify(output)}}]}));
    }catch(e){res.writeHead(400);res.end(JSON.stringify({error:e.message}));}
  });
  service.listen(0,'127.0.0.1');await once(service,'listening');
  Object.assign(env,{TIKFLOWSO_VISION_PROVIDER:'custom',TIKFLOWSO_CUSTOM_BASE_URL:'http://127.0.0.1:'+service.address().port+'/v1',TIKFLOWSO_CUSTOM_MODEL:'fixture-vision',TIKFLOWSO_MODEL_KEY:'contract-only'});
  if(adminTest){
    env.TIKFLOWSO_VISION_PROVIDER='bailian';
    for(const name of ['BAILIAN','VOLCENGINE','ATLAS','OPENROUTER','DEEPSEEK'])env['TIKFLOWSO_'+name+'_BASE_URL']=env.TIKFLOWSO_CUSTOM_BASE_URL+'/'+name.toLowerCase();
  }
  return service;
}
async function exerciseAdmin(page,base,browser){
  page.setDefaultTimeout(15000);
  const post=(name,data)=>page.request.post(base+'/api/admin/'+name,{data});
  assert.equal((await page.request.get(base+'/api/admin/settings')).status(),403);
  assert.equal((await post('claim',{code:'wrong'})).status(),403);
  await page.goto(base+'/#admin');
  const secret=fs.readFileSync(path.join(tmp,'qa.admin-setup.txt'),'utf8').trim();
  await page.getByLabel('首次绑定初始化码').fill(secret);
  await page.getByRole('button',{name:'绑定当前账户'}).click();
  await page.locator('[data-config]').waitFor();
  await page.locator('[data-locale-toggle]').click();
  await page.getByRole('button',{name:'Test connection',exact:true}).waitFor();
  await page.getByRole('button',{name:'Weekly research report',exact:true}).click();
  await page.locator('[data-weekly] [name=date]').fill('2026-01-01');
  await page.getByRole('button',{name:'View report',exact:true}).click();
  await page.getByText('2025-12-29 — 2026-01-01').waitFor();
  await page.getByRole('button',{name:'Prompts',exact:true}).click();
  await page.getByRole('button',{name:'Save prompt',exact:true}).waitFor();
  assert.match(await page.locator('[name=body]').inputValue(),/商品/);
  await page.getByRole('button',{name:'Provider settings',exact:true}).click();
  await page.locator('[data-locale-toggle]').click();await page.locator('[data-config]').waitFor();
  assert.ok(!fs.existsSync(path.join(tmp,'qa.admin-setup.txt')));
  const outsider=await browser.newContext();
  assert.equal((await outsider.request.get(base+'/api/admin/settings')).status(),401);
  await outsider.request.post(base+'/api/register',{data:{name:'Other',email:'other@contract.invalid',password:'other-qa-12345'}});
  assert.equal((await outsider.request.post(base+'/api/admin/claim',{data:{code:secret}})).status(),403);
  assert.equal((await outsider.request.post(base+'/api/admin/jobs',{data:{provider:'bailian',kind:'sync',revision:0}})).status(),403);
  await outsider.close();
  const runJob=async(kind)=>{
    const response=page.waitForResponse(r=>r.request().method()==='POST'&&r.url().endsWith('/admin/jobs'));
    await page.locator('[data-job="'+kind+'"]').click();
    const accepted=await response;
    assert.equal(accepted.status(),200);
    const job=await accepted.json();
    await page.waitForFunction(id=>{
      return document.querySelector('[data-report="'+id+'"]')?.closest('details')?.querySelector('[data-state=passed]');
    },job.id,{timeout:45000});
  };
  for(const name of ['bailian','volcengine','openrouter','atlas','deepseek']){
    await page.locator('[data-provider="'+name+'"]').click();
    await page.locator('[name=key]').fill('contract-only-'+name);
    await page.locator('[name=model]').fill('fixture-vision');
    if(name==='bailian')await page.locator('[name=text]').check();
    const saved=page.waitForResponse(r=>r.url().endsWith('/admin/provider'));
    await page.getByRole('button',{name:'保存配置'}).click();assert.equal((await saved).status(),200);
    await page.waitForFunction(()=>document.querySelector('[name=key]')?.value==='');
    await runJob('sync');
    await page.locator('[name=catalog]').selectOption('fixture-vision');
    assert.equal(await page.locator('option[value="text-only"]').count(),0);
    await runJob('probe');
    await runJob('acceptance');
    const latest=(await (await page.request.get(base+'/api/admin/jobs')).json()).items[0];
    assert.equal(latest.provider,name);
    assert.deepEqual(latest.results.map(row=>[row.case,row.passed]),[['en',true],['zh',true],['empty',true],['video',true]]);
  }
  let cfg=await (await page.request.get(base+'/api/admin/settings')).json();
  assert.equal(cfg.active,'bailian');assert.ok(cfg.providers.every(p=>p.has_key));
  assert.ok(!JSON.stringify(cfg).includes('contract-only'));
  assert.equal((await post('provider',{provider:'bailian',revision:0,model:'stale'})).status(),409);
  await page.locator('[data-tab=prompts]').click();
  await page.locator('[name=task]').selectOption('image_translate');
  await page.locator('[name=body]').fill('Fixture custom translation rule.');
  await page.getByRole('button',{name:'保存提示词'}).click();
  await page.getByText('提示词已保存并生效。').waitFor();
  await page.locator('[data-tab=providers]').click();await page.locator('[data-provider=bailian]').click();
  await runJob('acceptance');
  const records=(await (await page.request.get(base+'/api/admin/jobs')).json()).items;
  assert.deepEqual(records[0].results.map(r=>[r.case,r.passed]),[['en',true],['zh',true],['empty',true],['video',true]]);
  assert.ok(observedPrompts.includes('Fixture custom translation rule.'));
  await page.locator('[data-tab=prompts]').click();await page.locator('[data-reset]').click();
  await page.getByText('已恢复默认提示词。').waitFor();
  const generated=await page.request.post(base+'/api/generate',{data:{tool:'promotion',text:'蓝色水杯'}});
  assert.equal((await generated.json()).result,'Fixture text output');
  assert.ok(observedPrompts.some(x=>x?.includes('25 秒')));
  await page.reload();await page.locator('[data-tab=history]').click();
  const download=page.waitForEvent('download');await page.locator('.ca-run summary').first().click();
  await page.locator('[data-report]').first().click();const report=JSON.parse(fs.readFileSync(await (await download).path()));
  assert.equal(report.status,'passed');assert.equal(report.results.length,4);
  await page.locator('[data-tab=providers]').click();await page.locator('[data-sync-all]').click();
  await page.waitForFunction(()=>document.querySelectorAll('.ca-run').length>=21&&!document.querySelector('.ca-run [data-state=running]'));
  await page.locator('[data-tab=providers]').click();
  await page.setViewportSize({width:390,height:844});
  assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth));
  const image=await page.request.get(base+'/api/admin/sample/en');assert.equal(image.status(),200);
  assert.equal(image.headers()['content-type'],'image/png');
  await page.locator('[data-provider=atlas]').click();
  page.once('dialog',d=>d.accept());await page.locator('[data-clear]').click();await page.getByText('密钥已清除。').waitFor();
  assert.ok(await page.locator('[data-job=probe]').isDisabled());
  console.log('ADMIN PASS bootstrap, role isolation, five key saves/catalogs/probes, active provider, stale edits, prompt runtime/reset, four sample cases, text generation and JSON report');
}
async function makeFixtures(page){
  fs.mkdirSync(samples,{recursive:true});
  for(const kind of ['en','zh','empty','first','second']){
    const data=await page.evaluate(kind=>{
      const c=document.createElement('canvas');c.width=640;c.height=360;const ctx=c.getContext('2d');
      ctx.fillStyle=kind==='second'?'#15234a':'#ffffff';ctx.fillRect(0,0,640,360);
      if(kind==='first'){ctx.fillStyle='#de2020';ctx.fillRect(235,95,170,170);}
      if(kind==='second'){ctx.fillStyle='#ffdc20';ctx.beginPath();ctx.arc(320,180,85,0,2*Math.PI);ctx.fill();}
      if(kind==='en'||kind==='zh'){
        ctx.fillStyle='#172128';ctx.font='bold 50px sans-serif';ctx.fillText(kind==='en'?'Green Tea':'蓝色水杯',48,130);
        ctx.font='38px sans-serif';ctx.fillText(kind==='en'?'No added sugar':'容量 500 毫升',48,235);
      }
      return c.toDataURL('image/png').split(',')[1];
    },kind);
    fs.writeFileSync(path.join(['first','second'].includes(kind)?tmp:samples,kind+'.png'),Buffer.from(data,'base64'));
  }
  execFileSync('ffmpeg',['-loglevel','error','-y','-loop','1','-t','2','-i',path.join(tmp,'first.png'),'-loop','1','-t','2','-i',path.join(tmp,'second.png'),
    '-filter_complex','[0:v][1:v]concat=n=2:v=1:a=0,format=yuv420p','-c:v','libx264','-r','25','-threads','2',path.join(samples,'two-shots.mp4')]);
}
async function run(){
  let server,gateway;
  const browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_PATH||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
  try{
    const p=await browser.newPage();p.setDefaultTimeout(240000);
    await makeFixtures(p);
    if(process.argv.includes('--fixtures'))return;
    if(!live)gateway=await fixtureGateway();
    server=spawn('python3',['server.py','--port','0','--db',path.join(tmp,'qa.db')],{env,cwd:root,stdio:['ignore','pipe','inherit']});
    const lines=createInterface({input:server.stdout});const [line]=await once(lines,'line');lines.close();
    const base=line.trim().split(/\s+/).at(-1);
    const errors=[];p.on('pageerror',e=>errors.push(e.message));
    const account=await p.request.post(base+'/api/register',{data:{name:'QA',email:'qa@contract.invalid',password:'tikflowso-qa-12345'}});
    assert.equal(account.status(),200);
    if(adminTest){
      assert.ok(!live,'use an isolated contract gateway for the admin UI test');
      await exerciseAdmin(p,base,browser);assert.deepEqual(errors,[]);return;
    }
    const cfg=await (await p.request.get(base+'/api/config')).json();
    assert.equal(cfg.vision_status,'configured','Deployment needs the selected provider key');
    const report={run:live?'live cloud inference':'protocol fixture; model outputs are simulated',model:cfg.vision_model,images:{},video:null};
    for(const [name,target] of [['en','简体中文'],['zh','English'],['empty','简体中文']]){
      await p.goto(base+'/#tools?tool=image_translate');
      await p.locator('input[name=media]').setInputFiles(path.join(samples,name+'.png'));
      await p.locator('textarea').fill(target);
      const pending=p.waitForResponse(r=>r.url().endsWith('/api/generate'));
      await p.getByRole('button',{name:'生成结果'}).click();
      const res=await pending, data=await res.json();assert.equal(res.status(),200,JSON.stringify(data));
      report.images[name]=data.blocks;
      if(name==='empty'){assert.equal(data.blocks.length,0);continue;}
      const text=data.blocks.map(r=>r.translation).join(' '),original=data.blocks.map(r=>r.original).join(' ');
      assert.ok(name==='en'?/Green Tea/i.test(original)&&/No added sugar/i.test(original):/蓝色水杯/.test(original)&&/500/.test(original),original);
      assert.ok(name==='en'?/绿茶/.test(text)&&/糖/.test(text)&&/[无未不零]/.test(text):/blue/i.test(text)&&/cup|bottle|tumbler/i.test(text)&&/500/.test(text),text);
      assert.ok(data.blocks.every(r=>r.box[0]>=0&&r.box[0]<.25&&r.box[2]>.1&&r.box[1]+r.box[3]<=1.001));
      assert.ok(data.blocks.some(r=>r.box[1]<.4)&&data.blocks.some(r=>r.box[1]>.45));
      const download=p.waitForEvent('download');await p.getByRole('button',{name:'下载译图 PNG'}).click();
      await (await download).saveAs(path.join(tmp,name+'-translated.png'));
      const png=fs.readFileSync(path.join(tmp,name+'-translated.png'));assert.equal(png.readUInt32BE(16),640);assert.equal(png.readUInt32BE(20),360);
    }
    await p.goto(base+'/#tools?tool=video');await p.locator('input[name=media]').setInputFiles(path.join(samples,'two-shots.mp4'));
    const pending=p.waitForResponse(r=>r.request().method()==='POST'&&r.url().includes('/api/video-analysis'));
    await p.getByRole('button',{name:'生成结果'}).click();
    const res=await pending;assert.equal(res.status(),200,await p.locator('output').innerText());
    await p.waitForFunction(()=>document.querySelector('output.bad')||document.querySelector('output button'));
    assert.equal(await p.locator('output.bad').count(),0,await p.locator('output').innerText());
    const dl=p.waitForEvent('download');await p.getByRole('button',{name:'下载镜头分析 JSON'}).click();
    const video=JSON.parse(fs.readFileSync(await (await dl).path(),'utf8'));
    assert.equal(video.total_shots,2,JSON.stringify(video));assert.equal(video.shots.length,2);
    assert.ok(Math.abs(video.shots[0].end-2)<.12&&video.shots[0].start===0&&video.shots[1].end===4);
    const shotText=video.shots.map(s=>s.subject+s.action+s.composition);
    assert.ok(/红/.test(shotText[0])&&/方|矩形/.test(shotText[0]),shotText[0]);
    assert.ok(/黄/.test(shotText[1])&&/圆/.test(shotText[1]),shotText[1]);

    report.video=video;assert.deepEqual(errors,[]);
    fs.mkdirSync(reportDir,{recursive:true});
    for(const n of ['en','zh'])fs.copyFileSync(path.join(tmp,n+'-translated.png'),path.join(reportDir,n+'-translated.png'));
    fs.writeFileSync(path.join(reportDir,'result.json'),JSON.stringify(report,null,2)+'\n');
    console.log((live?'LIVE ':'CONTRACT ')+'PASS EN→ZH, ZH→EN, blank image, OCR coordinates, translated PNG, measured scene boundaries, subject fields, shot JSON');
  }finally{
    await browser.close();if(server&&server.exitCode===null){const stopped=once(server,'exit');server.kill();await stopped;}
    if(gateway)await new Promise(resolve=>gateway.close(resolve));
    fs.rmSync(tmp,{recursive:true,force:true});
  }
}
run().catch(err=>{console.error(err);process.exitCode=1;});
