// Empty-key operator approval and rejection against an isolated local server.
const assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {spawn}=require('node:child_process'),{once}=require('node:events'),{createInterface}=require('node:readline');
const {chromium}=require(process.env.PLAYWRIGHT_CORE||'/opt/homebrew/lib/node_modules/rea-agents/node_modules/playwright-core');
const root=path.resolve(__dirname,'..'),dir=fs.mkdtempSync(path.join(os.tmpdir(),'tikflowso-quota-'));
const env=Object.fromEntries(Object.entries(process.env).filter(([k])=>!k.startsWith('TIKFLOWSO_')&&!k.startsWith('STRIPE_')));
env.TIKFLOWSO_ENV_FILE=path.join(dir,'empty.env');env.DASHSCOPE_API_KEY='';
const server=spawn('python3',['server.py','--port','0','--db',path.join(dir,'qa.db')],{cwd:root,env,stdio:['ignore','pipe','inherit']});
async function main(){
  const lines=createInterface({input:server.stdout});const [ready]=await once(lines,'line');lines.close();
  const base=ready.trim().split(/\s+/).at(-1);
  const browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_PATH||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
  try{
    const owner=await browser.newPage(),operator=await browser.newPage(),errors=[];
    for(const [page,name] of [[owner,'owner'],[operator,'operator']]){
      page.on('pageerror',e=>errors.push(e.message));
      await page.goto(base);
      assert.equal((await page.request.post(base+'/api/register',{data:{name,email:name+'@qa.test',password:'test-account-passphrase'}})).status(),200);
    }
    await owner.goto(base+'/#monitor');await owner.locator('[data-slot-details] summary').click();
    const form=owner.locator('[data-slot-request]');
    const submit=async(slots,reason)=>{
      await form.locator('[name=slots]').fill(String(slots));await form.locator('[name=reason]').fill(reason);
      await form.locator('button').click();await owner.locator('[data-request-id]').filter({hasText:reason}).waitFor();
    };
    await submit(2,'Launch campaign');await submit(1,'Follow-up tracking');
    assert.equal(await owner.locator('[data-slot-added]').textContent(),'0');
    assert.equal((await owner.request.post(base+'/api/admin/monitor-capacity',{data:{id:1,status:'approved'}})).status(),403);
    await operator.goto(base+'/#admin');
    await operator.locator('[name=code]').fill(fs.readFileSync(path.join(dir,'qa.admin-setup.txt'),'utf8').trim());
    await operator.locator('.ca-gate button').click();
    await operator.locator('a[href*="capacity-review"]').click();
    const row1=operator.locator('[data-request-id="1"]'),row2=operator.locator('[data-request-id="2"]');
    await row1.locator('[value=approved]').click();await row1.getByText('已批准').waitFor();
    await row2.locator('[value=rejected]').click();await row2.getByText('请填写拒绝原因').waitFor();
    await row2.locator('[name=note]').fill('Covered by first request');
    await row2.locator('[value=rejected]').click();await row2.getByText('已拒绝').waitFor();
    await owner.locator('[data-slot-page]').click();await owner.getByText('Covered by first request').waitFor();
    assert.equal(await owner.locator('[data-slot-usage]').textContent(),'0 / 12');assert.equal(await owner.locator('[data-slot-added]').textContent(),'2');
    await owner.locator('[data-locale-toggle]').click();await owner.getByText('Approved extra slots this month').waitFor();
    await owner.locator('[data-capacity] a[href="#plans"]').click();await owner.locator('.tf-panel h2').filter({hasText:'TEAM'}).waitFor();
    await owner.goto(base+'/#monitor');await owner.locator('[data-capacity] a[href*="subscription"]').click();
    await owner.locator('.tf-panel h2').filter({hasText:'Subscription'}).waitFor();
    assert.deepEqual(errors,[]);console.log('PASS zero-Stripe owner request, platform-only approval/rejection, audit, refreshed effective slots, English, plans and subscription links');
  }finally{await browser.close();}
}
main().catch(e=>{console.error(e);process.exitCode=1;}).finally(()=>{server.kill();fs.rmSync(dir,{recursive:true,force:true});});
