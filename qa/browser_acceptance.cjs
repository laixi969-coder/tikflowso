// Run against an isolated server and synthetic fixtures. No production identities or keys are used.
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const assert = require('node:assert/strict');
const {spawn,execFileSync} = require('node:child_process');
const {once} = require('node:events');
const {createInterface} = require('node:readline');
process.env.PW_CHROMIUM_ATTACH_TO_OTHER='1'; // Chrome exposes extension popups as other targets.
const {chromium} = require(process.env.PLAYWRIGHT_CORE || '/opt/homebrew/lib/node_modules/rea-agents/node_modules/playwright-core');
const root=path.resolve(__dirname,'..');
const dir=fs.mkdtempSync(path.join(os.tmpdir(),'tikflowso-browser-'));
const db=path.join(dir,'qa.db');
const env={...process.env};
for(const k of Object.keys(env)) if(k.startsWith('STRIPE_')||k.startsWith('TIKFLOWSO_')&&k!=='TIKFLOWSO_WHISPER_MODEL')delete env[k];
env.TIKFLOWSO_ENV_FILE=path.join(dir,'isolated.env');
const drop=path.join(dir,'delivery');fs.mkdirSync(drop);
env.TIKFLOWSO_FEEDS=path.join(dir,'feeds.json');
fs.writeFileSync(env.TIKFLOWSO_FEEDS,JSON.stringify([{id:'local-check',source:'delivery-qa',directory:drop,
  daily_delivery:{markets:['GB'],due_utc:'12:00',lag_days:1}}]));
const server=spawn('python3',['server.py','--db',db,'--port','0'],{cwd:root,env,stdio:['ignore','pipe','inherit']});
const run=(cmd,args)=>execFileSync(cmd,args,{cwd:root,env,stdio:['ignore','pipe','pipe']});
async function main(){
  const line=createInterface({input:server.stdout});
  const [start]=await once(line,'line');line.close();
  const base=start.trim().split(/\s+/).at(-1);
  const browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_PATH||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
  try{
    const page=await browser.newPage({viewport:{width:1280,height:850}}),errors=[];
    page.on('pageerror',e=>errors.push(e.message));
    const go=async h=>{await page.goto(base+'/'+h);};
    const output=page.locator('output');
    const waitText=async s=>page.getByText(s,{exact:false}).first().waitFor({timeout:60000});
    await go('#dashboard');await page.locator('.records tbody tr').first().waitFor();
    await page.locator('[data-scope=market]').selectOption('GB');
    await page.locator('.kpi-label').filter({hasText:'GBP'}).first().waitFor();
    await page.locator('[data-scope=market]').selectOption('US');
    for(const kind of ['products','creators','shops','lives','videos']){
      await go('#'+kind);await page.locator('.records tbody tr').first().waitFor();
    }
    await go('#products?q=missing-fixture-xyz');await page.locator('.empty').waitFor();
    await go('#products?source=demo&market=JP');await page.locator('.empty').waitFor();
    assert.equal(await page.locator('[data-scope=market]').inputValue(),'JP');
    await go('#products?source=demo&market=US&q=missing-fixture-xyz');await page.locator('.empty').waitFor();
    await page.locator('#search-button').click();await page.locator('#query').press('Escape');
    assert.ok(!(await page.locator('#search-dialog').isVisible()));
    const ranking='**/api/rankings?**';
    await page.route(ranking,route=>route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({error:'temporary fixture error'})}),{times:1});
    await go('#products');await page.locator('[data-retry]').click();await page.locator('.records .record').first().waitFor();
    let release,entered;
    const delayed=new Promise(resolve=>{release=resolve;}),seen=new Promise(resolve=>{entered=resolve;});
    await page.route(ranking,async route=>{entered();await delayed;await route.continue();},{times:1});
    await go('#products?sort=sales');await seen;await go('#shops');await page.locator('.record[href*="kind=shops"]').first().waitFor();
    const delivered=page.waitForResponse(r=>r.url().includes('/api/rankings')&&r.url().includes('kind=products'));
    release();await delivered;await page.evaluate(()=>new Promise(requestAnimationFrame));
    assert.ok(await page.locator('.record[href*="kind=shops"]').count());
    console.log('PASS empty rankings, keyboard dismissal, failed request retry and stale response isolation');
    await go('#shops');await page.locator('[data-segment=local]').click();await page.locator('.record').first().click();
    await page.locator('[data-save]').click();await waitText('已加入收藏');
    await go('#favorites');await page.locator('.tf-entity').first().waitFor();
    await go('#tools?tool=calc');await waitText('USD 19.00');
    await page.locator('[name=currency]').selectOption('EUR');await page.getByText('计算利润',{exact:true}).click();await waitText('EUR 19.00');
    await page.locator('[name=fee]').fill('90');await page.getByText('计算利润',{exact:true}).click();await waitText('无正数解');
    for(const field of ['cost','ship'])await page.locator('[name='+field+']').fill('0');
    await page.getByText('计算利润',{exact:true}).click();await waitText('任意售价均盈亏平衡');
    console.log('PASS market switch, five libraries, local shops, saved detail and unit profit');
    await go('#products');await page.locator('[data-queue-export]').click();
    const file=page.getByRole('link',{name:/下载 CSV/});
    await file.waitFor();const downloaded=page.waitForEvent('download');await file.click();
    assert.match(fs.readFileSync(await (await downloaded).path(),'utf8'),/follower_growth/);
    console.log('PASS ranked export queue and CSV download');
    const started=Date.now();
    await go('#products?market=US&source=demo&days=14&date=2026-11-15&sort=sales');
    await page.locator('.record').first().click();await page.locator('[data-save]').click();await waitText('已加入收藏');
    await go('#favorites');const savedProduct=page.locator('.tf-entity[href*="kind=products"]').first();
    const params=new URLSearchParams((await savedProduct.getAttribute('href')).split('?')[1]);
    assert.equal(params.get('date'),'2026-11-15');assert.equal(params.get('days'),'14');
    await savedProduct.click();await page.locator('[data-save]').waitFor();
    assert.equal(await page.locator('[data-scope=days]').inputValue(),'14');assert.equal(await page.locator('[data-scope=date]').inputValue(),'2026-11-15');
    const elapsed=(Date.now()-started)/1000;assert.ok(elapsed<300);
    console.log('PASS saved product reopens original date and window in '+elapsed.toFixed(2)+' s');
    await go('#products?date=2026-11-19&days=7');
    await go('#detail?kind=products&id=p01');await waitText('中英词典与否定规则');
    await go('#trends');await waitText('趋势预测与采样覆盖');
    await page.locator('[data-locale-toggle]').click();await waitText('Forecast and sample coverage');
    await page.locator('[data-locale-toggle]').click();await waitText('趋势预测与采样覆盖');
    await page.locator('.group-link').first().click();await waitText('趋势预测与采样覆盖');
    await page.locator('[data-save-topic]').click();await waitText('已加入收藏');
    await go('#favorites');await page.getByText('已收藏的灵感').waitFor();
    const topicLink=page.locator('a[href*="topic="]').first();await topicLink.click();
    await waitText('趋势预测与采样覆盖');
    await go('#favorites');await page.locator('[data-remove-topic]').first().click();
    await page.getByText('已收藏的灵感').waitFor({state:'hidden'});
    console.log('PASS review sentiment, topic forecast, English language switch, save/reopen/remove inspiration');
    await go('#detail?kind=products&id=p01');await page.locator('[data-monitor]').click();await waitText('已加入监控');
    await go('#monitor');await page.locator('[data-th]').first().fill('1');
    await page.locator('[data-threshold]').first().click();await waitText('已达到阈值');
    await page.getByRole('link',{name:'查看监控通知 →'}).click();await page.locator('[data-seen]').first().click();await waitText('已读');
    console.log('PASS persisted monitor alert and read state');
    await go('#tools?tool=transcribe');
    const speech=path.join(dir,'sound.aiff'),video=path.join(dir,'clip.mp4');
    run('say',['-v','Samantha','-o',speech,'The green bottle is on the kitchen table. Today we are testing the sound quality.']);
    run('ffmpeg',['-loglevel','error','-f','lavfi','-i','color=c=green:s=160x90:r=5','-i',speech,'-c:v','libx264','-c:a','aac','-shortest',video]);
    await page.locator('[name=media]').setInputFiles(video);await page.locator('[name=language]').selectOption('en');
    await page.getByRole('button',{name:'转写音轨'}).click();
    await waitText('green bottle');assert.match(await output.innerText(),/kitchen table/i);
    const srt=page.waitForEvent('download');await page.getByText('下载 SRT 字幕').click();
    assert.match(fs.readFileSync(await (await srt).path(),'utf8'),/00:00:00,000 --> /);
    await go('#tools?tool=video');await page.locator('[name=media]').setInputFiles(video);
    await page.getByRole('button',{name:'生成结果'}).click();await waitText('本机分镜');
    assert.equal(await output.locator('figure img').count(),5);
    assert.ok(await output.locator('figure img').first().evaluate(async img=>{
      await img.decode();const canvas=document.createElement('canvas'),ctx=canvas.getContext('2d');
      ctx.drawImage(img,0,0);const [r,g,b]=ctx.getImageData(10,10,1,1).data;return g>r+50&&g>b+50;
    }));
    console.log('PASS actual offline video transcription, SRT download and sampled storyboard');
    await go('#tools?tool=erase');
    await page.locator('input[type=file]').setInputFiles(path.join(root,'qa/samples/vision/en.png'));
    const imageCanvas=page.locator('.tf-canvas canvas');await imageCanvas.waitFor();
    const before=await imageCanvas.evaluate(cv=>cv.toDataURL());
    const rect=await imageCanvas.boundingBox();
    await page.mouse.move(rect.x+rect.width*.04,rect.y+rect.height*.17);await page.mouse.down();
    await page.mouse.move(rect.x+rect.width*.78,rect.y+rect.height*.40);await page.mouse.up();
    await waitText('已填充选区');assert.notEqual(await imageCanvas.evaluate(cv=>cv.toDataURL()),before);
    const png=page.waitForEvent('download');await page.locator('[data-download]').click();
    assert.equal(fs.readFileSync(await (await png).path()).readUInt32BE(16),640);
    await page.locator('[data-undo]').click();assert.equal(await imageCanvas.evaluate(cv=>cv.toDataURL()),before);
    console.log('PASS image erasure changes pixels, downloads PNG and restores original on undo');
    await go('#account');const f=page.locator('[data-action=register]');
    await f.locator('[name=name]').fill('Tester');await f.locator('[name=email]').fill('review@test.invalid');
    await f.locator('[name=password]').fill('test-auth-12345');await f.locator('button').click();
    await page.locator('[data-action=logout]').waitFor();
    run('python3',['feeds.py','--db',db,'--config',env.TIKFLOWSO_FEEDS]);
    await go('#resources');
    await waitText('交付时效');
    const counters=page.locator('[data-action=counters]');
    await counters.locator('[name=file]').setInputFiles({name:'counter.csv',mimeType:'text/csv',buffer:Buffer.from(
      'market,kind,id,name,date,cumulative_gmv,cumulative_sales\nGB,shops,shop,Shop,2026-11-01,10.25,2\nGB,shops,shop,Shop,2026-11-02,11.75,4')});
    await counters.locator('[type=submit]').click();
    const dailyDownload=page.waitForEvent('download');await counters.getByText('下载日快照 JSON').click();
    const converted=JSON.parse(fs.readFileSync(await (await dailyDownload).path(),'utf8'));
    assert.deepEqual(converted.map(r=>[r.gmv,r.sales]),[['1.50',2]]);
    const upload=async(name,body)=>{
      const f=page.locator('[data-action=upload]');
      await f.locator('[name=source]').fill('browser');
      await f.locator('[name=file]').setInputFiles({name,mimeType:'text/plain',buffer:Buffer.from(body)});
      const pending=page.waitForResponse(r=>r.url().endsWith('/api/import')&&r.request().method()==='POST');
      await f.locator('[type=submit]').click();return (await pending).status();
    };
    assert.equal(await upload('bad.json','[broken'),400);await waitText('bad.json');
    const csv='market,kind,id,name,date,gmv,sales\nGB,shops,qa,QA Shop,2026-10-01,10,2';
    assert.equal(await upload('gb.csv',csv),200);
    const imported=page.getByRole('link',{name:'查看导入结果'});await imported.waitFor();
    assert.match(await imported.getAttribute('href'),/^#shops\?.*market=GB/);
    assert.equal(await upload('revised.csv',csv.replace(',10,2',',20,2')),200);
    await waitText('revised.csv');await page.locator('summary').filter({hasText:'2026-10-01'}).first().click();await waitText('gmv_units');
    console.log('PASS import failures, non-US CSV drill-down and before/after revision history');
    run('python3',['-c',`import sqlite3,sys,time
with sqlite3.connect(sys.argv[1]) as db:
 uid=db.execute("select id from users where email='review@test.invalid'").fetchone()[0]
 db.execute("insert into partner_ledger values(?,?,?,?,?,?,?,?,?,?)",('test','ch_fixture','ch_fixture','inv_fixture',uid,uid,'usd',2000,1000,int(time.time())))`,db]);
    await page.request.post(base+'/api/partners/library',{data:{kind:'product',name:'Other category',rights:'Test permission',url:'https://example.test/other',category:'Toys'}});
    await go('#tools?tool=partners');const editor=page.locator('[data-editor]');
    await editor.locator('[name=name]').fill('QA asset');await editor.locator('[name=url]').fill('https://example.test/asset');
    await editor.locator('[name=rights]').fill('Synthetic test only');
    await editor.locator('[name=category]').fill('Drinkware');
    await editor.locator('[name=attachment]').setInputFiles({name:'fixture.txt',mimeType:'text/plain',buffer:Buffer.from('licensed fixture')});
    await editor.getByText('保存条目').click();
    const asset=page.waitForEvent('download');await page.getByRole('link',{name:/下载附件/}).click();
    assert.equal(fs.readFileSync(await (await asset).path(),'utf8'),'licensed fixture');
    await page.locator('[data-library-filter]').fill('unmatched');await waitText('没有符合筛选条件的条目。');
    await page.locator('[data-library-filter]').fill('drinkware');await waitText('QA asset');
    const exported=page.waitForEvent('download');await page.locator('[data-action=exportLibrary]').click();
    const filteredCsv=fs.readFileSync(await (await exported).path(),'utf8');
    assert.match(filteredCsv,/Drinkware/);assert.doesNotMatch(filteredCsv,/Toys/);
    await page.locator('[data-action=review]').click();await waitText('pending');
    run('python3',['manage.py','review','--db',db,'1','approved','--reviewer','QA','--reason','local test']);
    await page.reload();await waitText('approved');
    console.log('PASS asset upload/download and request/operator-review loop');
    await go('#api');const bundle=page.waitForEvent('download');await page.getByText('下载扩展 ZIP').click();
    const zip=await (await bundle).path();
    assert.equal(run('python3',['-c','import json,sys,zipfile;print(json.loads(zipfile.ZipFile(sys.argv[1]).read("manifest.json"))["manifest_version"])',zip]).toString().trim(),'3');
    const unpacked=path.join(dir,'extension');
    run('python3',['-m','zipfile','-e',zip,unpacked]);
    const extContext=await chromium.launchPersistentContext(path.join(dir,'extension-profile'),{
      executablePath:process.env.CHROME_PATH||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
      headless:true,args:['--enable-unsafe-extension-debugging'],ignoreDefaultArgs:['--disable-extensions']});
    try{
      const cdp=await extContext.browser().newBrowserCDPSession();
      const {id}=await cdp.send('Extensions.loadUnpacked',{path:unpacked});
      const source=extContext.pages()[0];
      await source.route('https://www.tiktok.com/**',r=>r.fulfill({body:'Synthetic creator page',contentType:'text/html'}));
      await source.goto('https://www.tiktok.com/@c01');
      const {targetInfos}=await cdp.send('Target.getTargets',{filter:[{type:'tab'}]});
      const opening=extContext.waitForEvent('page');
      await cdp.send('Extensions.triggerAction',{id,targetId:targetInfos.find(t=>t.url===source.url()).targetId});
      const popup=await opening;
      await popup.locator('#open button:enabled').waitFor();
      assert.match(await popup.locator('#selection').innerText(),/c01/);
      await popup.locator('#workspace').fill(base);
      const opened=extContext.waitForEvent('page');await popup.locator('#open button').click();
      const destination=await opened;await destination.waitForURL('**/#search?q=c01&kind=creators');
      await destination.locator('a[href*="id=c01"]').first().waitFor();
      await source.bringToFront();
      const reopen=extContext.waitForEvent('page');
      await cdp.send('Extensions.triggerAction',{id,targetId:targetInfos.find(t=>t.url===source.url()).targetId});
      const savedPopup=await reopen;
      await savedPopup.waitForFunction(url=>document.querySelector('#workspace')?.value===url,new URL(base).href);
    }finally{await extContext.close();}
    await page.setViewportSize({width:390,height:844});await go('#tools?tool=exports');await waitText('刷新任务');
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth));
    assert.deepEqual(errors,[]);
    console.log('PASS extension package, mobile layout, no uncaught browser errors');
  }finally{await browser.close();}
}
main().catch(e=>{console.error(e);process.exitCode=1;}).finally(async()=>{
  if(server.exitCode===null){const stopped=once(server,'exit');server.kill();await stopped;}
  fs.rmSync(dir,{recursive:true,force:true});
});
