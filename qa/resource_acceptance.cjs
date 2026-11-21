// Isolated browser acceptance for reports, help, editorial resources and local support.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const os=require('node:os');
const path=require('node:path');
const {spawn}=require('node:child_process');
const {once}=require('node:events');
const {createInterface}=require('node:readline');
const {chromium}=require(process.env.PLAYWRIGHT_CORE||'/opt/homebrew/lib/node_modules/rea-agents/node_modules/playwright-core');
const root=path.resolve(__dirname,'..');
const dir=fs.mkdtempSync(path.join(os.tmpdir(),'tikflowso-resources-'));
const env=Object.fromEntries(Object.entries(process.env).filter(([k])=>!k.startsWith('TIKFLOWSO_')&&!k.startsWith('STRIPE_')));
env.TIKFLOWSO_ENV_FILE=path.join(dir,'isolated.env');
const db=path.join(dir,'qa.db');
const service=spawn('python3',['server.py','--db',db,'--port','0'],{cwd:root,env,stdio:['ignore','pipe','inherit']});

async function main(){
  const output=createInterface({input:service.stdout});
  const [first]=await once(output,'line');output.close();
  const base=first.trim().split(/\s+/).at(-1);
  const browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_PATH||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
  try{
    const customer=await browser.newPage(),operator=await browser.newPage();
    const errors=[];
    for(const page of [customer,operator])page.on('pageerror',e=>errors.push(e.message));
    const scope={source:'demo',market:'GB',days:'14',date:'2026-11-15'};
    const goto=(page,section,params={})=>page.goto(base+'/#resources?'+new URLSearchParams({...scope,section,...params}));
    const center=customer.locator('tf-resource-center');
    const select=async id=>{
      await center.locator('[data-resource-section="'+id+'"]').click();
      await center.locator('[data-resource-article="'+id+'"]').waitFor();
    };
    await goto(customer,'reports');
    const panel=center.locator('[data-resource-article=reports]');
    const snapshot=await (await customer.request.get(base+'/api/overview?'+new URLSearchParams(scope))).json();
    const file=customer.waitForEvent('download');await panel.locator('button').click();
    const downloaded=await file;
    assert.equal(downloaded.suggestedFilename(),'tikflowso-GB-2026-11-15.txt');
    const report=fs.readFileSync(await downloaded.path(),'utf8');
    for(const value of ['GBP','覆盖天数',snapshot.start_date,snapshot.date,String(snapshot.coverage.sales)+'/14'])assert(report.includes(value));
    assert(report.includes(new Intl.NumberFormat('zh-CN').format(snapshot.metrics.sales)));
    assert.equal(report.split('\n').filter(s=>/^2026-11-\d\d\t/.test(s)).length,14);
    const dashboard=panel.getByRole('link');
    await dashboard.click();await customer.locator('.board-list').waitFor();
    assert.equal(new URLSearchParams(new URL(customer.url()).hash.split('?')[1]).get('market'),'GB');
    await goto(customer,'updates');await center.getByRole('heading',{name:'1.2.0',exact:true}).waitFor();
    assert.match(await center.locator('a[href*="/releases/"]').getAttribute('href'),/v1\.2\.0$/);
    await select('help');const search=center.locator('[data-help-search]');
    await search.fill('key');assert.equal(await center.locator('[data-help-items] details:visible').count(),1);
    await search.fill('xyz-unmatched');await center.locator('[data-help-empty]').waitFor();
    await customer.locator('[data-locale-toggle]').click();
    await center.getByRole('heading',{name:'Help center',exact:true}).waitFor();
    await search.fill('export');await center.locator('[data-help-items] details:visible summary').click();
    assert.match(await center.getByRole('link',{name:'Open product library'}).getAttribute('href'),/market=GB/);
    await select('playbooks');assert.equal(await center.locator('article details').count(),3);
    await center.getByText('Evaluate creators for outreach',{exact:true}).click();
    const board=center.getByRole('link',{name:'Open follower-growth board'});
    assert.match(await board.getAttribute('href'),/sort=follower_growth/);
    await select('tools');await center.getByRole('link',{name:'Open Fee calculator'}).click();
    await customer.locator('[data-action=calc]').waitFor();
    await goto(customer,'partners');await center.getByRole('link',{name:'Sign in or register'}).waitFor();
    console.log('PASS bilingual scoped resource directory, report content, dashboard, FAQ, guides and tools');

    async function register(page,email){
      const res=await page.request.post(base+'/api/register',{data:{name:email.split('@')[0],email,password:'resources-test-1234'}});
      assert.equal(res.status(),200);
    }
    await register(customer,'customer@test.invalid');
    await customer.reload();
    const form=center.locator('[data-support-form]');
    await form.locator('[name=subject]').fill('Data source inquiry');
    await form.locator('[name=message]').fill('How can I inspect the latest delivery?');
    await form.locator('button').click();
    await center.getByText('How can I inspect the latest delivery?',{exact:true}).waitFor();
    const caseId=new URLSearchParams(new URL(customer.url()).hash.split('?')[1]).get('ticket');
    const customerTicket=customer.url();
    assert.match(caseId,/^\d+$/);
    assert.equal((await customer.request.get(base+'/api/admin/support')).status(),403);
    await goto(operator,'partners');await register(operator,'operator@test.invalid');
    assert.equal((await operator.request.get(base+'/api/support?id='+caseId)).status(),404);
    assert.equal((await operator.request.post(base+'/api/support',{data:{id:caseId,message:'unrelated',nonce:'unrelated_nonce_001'}})).status(),404);
    const claim=await operator.request.post(base+'/api/admin/claim',{data:{code:fs.readFileSync(path.join(dir,'qa.admin-setup.txt'),'utf8').trim()}});
    assert.equal(claim.status(),200);
    await operator.goto(base+'/#admin');await operator.locator('[data-support-inbox]').click();
    const inbox=operator.locator('tf-resource-center');
    await inbox.getByRole('link',{name:'#'+caseId+' · Data source inquiry'}).click();
    await inbox.getByText('How can I inspect the latest delivery?',{exact:true}).waitFor();
    const reply=inbox.locator('[data-support-form]');
    await reply.locator('[name=message]').fill('Open snapshot coverage in the resource center.');
    await reply.locator('button').click();await inbox.getByText('Open snapshot coverage in the resource center.',{exact:true}).waitFor();
    await customer.goto(customerTicket);await customer.reload();await center.getByText('Support replied',{exact:true}).waitFor();
    await center.getByText('Open snapshot coverage in the resource center.',{exact:true}).waitFor();
    const key={id:caseId,nonce:'stable_nonce_1234',message:'Follow-up details'};
    for(const i of [0,1]){
      const res=await customer.request.post(base+'/api/support',{data:key});assert.equal(res.status(),200);
      const detail=await res.json();assert.equal(detail.messages.length,3);assert.equal(detail.awaiting_reply,1);
    }
    await customer.goto(customerTicket);await customer.reload();
    await center.getByText('Follow-up details',{exact:true}).waitFor();await center.getByText('Awaiting support',{exact:true}).waitFor();
    assert.deepEqual(errors,[]);
    console.log('PASS local support intake, private requester scope, authenticated operator response, status and idempotent follow-up');
  } finally {await browser.close();}
}
main().catch(e=>{console.error(e);process.exitCode=1;}).finally(async()=>{
  if(service.exitCode===null){const done=once(service,'exit');service.kill();await done;}
  fs.rmSync(dir,{recursive:true,force:true});
});
