// Exercise each template using a fresh empty-key SQLite deployment and a real Chrome page.
const assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {spawn}=require('node:child_process'),{once}=require('node:events'),{createInterface}=require('node:readline');
const {chromium}=require(process.env.PLAYWRIGHT_CORE||'/opt/homebrew/lib/node_modules/rea-agents/node_modules/playwright-core');
const root=path.resolve(__dirname,'..'),dir=fs.mkdtempSync(path.join(os.tmpdir(),'tikflowso-skills-'));
const env=Object.fromEntries(Object.entries(process.env).filter(([key])=>!key.startsWith('TIKFLOWSO_')));
env.TIKFLOWSO_ENV_FILE=path.join(dir,'empty.env');env.DASHSCOPE_API_KEY='';
const server=spawn('python3',['server.py','--db',path.join(dir,'qa.db'),'--port','0'],{cwd:root,env,stdio:['ignore','pipe','inherit']});
async function main(){
  const line=createInterface({input:server.stdout});const [ready]=await once(line,'line');line.close();
  const base=ready.trim().split(/\s+/).at(-1);
  const browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_PATH||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
  try{
    const page=await browser.newPage({viewport:{width:920,height:800}}),errors=[];
    page.on('pageerror',e=>errors.push(e.message));
    const url=base+'/#agent?market=GB&source=demo&days=7&date=2026-11-15';
    await page.goto(url);
    const cards=page.locator('button[data-skill]'),input=page.locator('textarea[name=text]');
    await cards.first().waitFor();assert.equal(await cards.count(),12);
    const library=await (await page.request.get(base+'/api/assistant/skills')).json();
    const cloud=await (await page.request.get(base+'/api/config')).json();assert.equal(cloud.model,false);
    let count=0,chat='';
    for(const group of library.groups){
      await page.locator('[data-group="'+group.id+'"]').click();assert.equal(await cards.count(),3);
      for(const template of library.items.filter(s=>s.group===group.id)){
        await page.locator('[data-skill="'+template.id+'"]').click();
        assert.equal(await input.inputValue(),template.prompt.zh);
        if(template.id==='interest')await page.locator('[name=comments]').fill('哪里买？\n很喜欢');
        if(template.id==='video_script'){
          await input.fill('拍摄自然光下的展示');await page.locator('[name=focus]').fill('p01');
          await page.locator('[data-locale-toggle]').click();
          assert.equal(await input.inputValue(),'拍摄自然光下的展示');
          await page.getByRole('button',{name:'Run template'}).waitFor();
          await page.locator('[data-locale-toggle]').click();
        }
        await page.locator('[data-action=gen] [type=submit]').click();
        const turn=page.locator('[data-turns] article').nth(count++);
        await turn.waitFor();
        assert.ok((await turn.innerText()).includes(template.title.zh));
        const href=await turn.locator('a').first().getAttribute('href');
        const ref=new URLSearchParams(href.split('?')[1]);assert.equal(ref.get('market'),'GB');assert.equal(ref.get('days'),'7');
        if(template.id==='interest')assert.ok((await turn.innerText()).includes('粘贴的评论 · 2'));
        if(template.id==='video_script'){
          assert.equal(ref.get('id'),'p01');
          const edited='现场拍摄草稿 QA';
          await turn.locator('summary').click();await turn.locator('[data-draft]').fill(edited);
          const next=page.waitForEvent('download');await turn.locator('[data-download-draft]').click();
          assert.ok(fs.readFileSync(await (await next).path(),'utf8').startsWith(edited));
        }
        chat=await page.locator('[data-history]').inputValue();
      }
    }
    await page.goto(url+'&chat='+chat);await page.locator('[data-turns] article').nth(11).waitFor();
    await page.locator('[data-locale-toggle]').click();
    await page.locator('[data-group=operations]').click();
    await page.getByRole('button',{name:/Full-cycle shop plan/}).click();
    assert.equal(await input.inputValue(),library.items.find(s=>s.id==='shop_plan').prompt.en);
    await page.locator('[name=focus]').fill('no-such-shop-qa');await page.getByRole('button',{name:'Run template'}).click();
    await page.getByText(/No qualifying records with comparable measurements/).first().waitFor();
    await page.locator('[data-new]').click();await page.locator('[data-question]').first().click();
    await page.locator('[data-turns] a').first().waitFor();
    assert.equal(await page.locator('[data-turns] article').count(),1);
    assert.deepEqual(errors,[]);
    console.log('PASS 4 groups / 12 empty-key templates, scoped links, comments, editable downloaded draft, two languages, chat deep link, empty results and free question');
  }finally{await browser.close();}
}
main().catch(e=>{console.error(e);process.exitCode=1;}).finally(()=>{server.kill();fs.rmSync(dir,{recursive:true,force:true});});
