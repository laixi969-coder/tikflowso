// Run the product research path against a private, synthetic merchant and a temporary database.
const assert = require('node:assert/strict');
const { execFileSync, spawn } = require('node:child_process');
const { once } = require('node:events');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { createInterface } = require('node:readline');
const { chromium } = require('playwright-core');

const root = path.resolve(__dirname, '..');
const cutoff = '2026-11-14';
const shop = '合成试点店';
const statDay = day => '2026-11-' + String(day).padStart(2, '0');

function fixture() {
  const rows = [];
  for (let day = 1; day <= 14; day++) {
    for (let rank = 1; rank <= 23; rank++) {
      const id = 'p' + String(rank).padStart(2, '0');
      const sales = (25 - rank) * (day <= 7 ? 1 : 2);
      rows.push({ date: statDay(day), market: 'US', kind: 'products', id, shop_id: 's1',
        name: [3, 21].includes(rank) ? '同名水杯' : '商品 ' + id, sales, gmv: sales * 4 });
    }
    rows.push({ date: statDay(day), market: 'US', kind: 'videos', id: 'v-switch',
      name: '换品视频', product_id: day < 10 ? 'p03' : 'p21', sales: 1, gmv: day < 10 ? 100 : 5 });
    rows.push({ date: statDay(day), market: 'US', kind: 'videos', id: 'v03',
      name: '只关联排名第三的商品', product_id: 'p03', sales: 1, gmv: 1 });
    rows.push({ date: statDay(day), market: 'US', kind: 'videos', id: 'v22',
      name: '榜外商品视频', product_id: 'p22', sales: 1, gmv: 1 });
  }
  return rows;
}

async function post(page, base, route, body) {
  const response = await page.request.post(base + '/api/' + route, { data: body });
  const result = await response.json();
  assert.equal(response.status(), 200, route + ' ' + JSON.stringify(result));
  return result;
}

async function checkDecision(page, base, upload, rows) {
  const reason = '同名水杯 p21：销量由 28 件增至 56 件，成交均价维持 4 美元，继续跟踪。';
  const form = page.locator('#research-decision');
  const sales = page.locator('[data-decision-comparison] tbody tr').first();
  assert.deepEqual(await sales.locator('td').allTextContents(), ['56', '28', '+100.0%']);
  await form.locator('[name=reason]').fill(reason);
  await form.locator('button[type=submit]').click();
  await form.locator('output').getByText('选品判断已保存').waitFor();
  // A late reply to an idempotent save must not mark newly edited text as saved, even after redraw.
  let opened, release;
  const pending = new Promise(resolve => { opened=resolve; });
  const resume = new Promise(resolve => { release=resolve; });
  await page.route('**/api/research-decisions', async route => {
    opened();
    await resume;
    await route.continue();
  },{times:1});
  const viewport = page.viewportSize();
  const reply = page.waitForResponse(response => response.url().endsWith('/api/research-decisions'));
  await form.locator('button[type=submit]').click();
  await pending;
  try {
    await form.locator('[name=reason]').fill('暂缓，等待补充样本。');
    await page.setViewportSize({width:540,height:800});
  } finally { release(); }
  await (await reply).finished();
  await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  assert.equal(await form.locator('[name=reason]').inputValue(),'暂缓，等待补充样本。');
  assert.equal(await form.locator('output').textContent(),'');
  await page.setViewportSize(viewport);
  const last = rows.find(row => row.id === 'p21' && row.date === cutoff);
  await upload([{ ...last, sales: 9, gmv: 36 }, { ...last, date: statDay(21), sales: 90, gmv: 360 }]);

  // Reopen from a fresh session, with a corrected fact and a newer reporting week in the same source.
  const context = await page.context().browser().newContext({ locale: 'zh-CN' });
  try {
    const later = await context.newPage();
    const guest = await later.request.get(base + '/api/research-decisions');
    assert.equal(guest.status(), 200);
    assert.equal((await guest.json()).items.length, 0);
    await post(later, base, 'login', { email: 'pilot@test.invalid', password: 'local-test-12345' });
    await later.goto(base + '/#favorites');
    const record = later.locator('[data-decision-record]').filter({ hasText: reason });
    await record.locator('summary').first().click();
    const saved = record.locator('[data-decision-comparison]').first().locator('tbody tr').first();
    assert.deepEqual(await saved.locator('td').allTextContents(), ['56', '28', '+100.0%']);
    await record.locator('[data-compare-decision]').click();
    const current = record.locator('[data-current-decision]');
    await current.getByText('依据已更新').waitFor();
    assert.equal(await current.locator('tbody tr').first().locator('td').first().textContent(), '57');
    assert.equal(await saved.locator('td').first().textContent(), '56');
    console.log('PASS compare periods, save reasoning, reopen in a new session after revision, and retain original evidence');
  } finally {
    await context.close();
  }
}

async function verify(base, page, dir, db, env) {
  const errors = [];
  const externalSearches = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('request', req => {
    if (new URL(req.url()).pathname === '/api/inspiration/videos') externalSearches.push(req.url());
  });
  await post(page, base, 'register', { email: 'pilot@test.invalid', name: '试点运营', password: 'local-test-12345' });
  const rows = fixture();
  const omitted = row => row.date === statDay(9) || (row.date === statDay(10) && row.id === 'p23');
  const upload = batch => post(page, base, 'import', { source: 'pilot', filename: 'synthetic.json', rows: batch });
  const { source } = await upload(rows.filter(row => !omitted(row)));
  assert.match(source, /^ws-\d+-pilot$/);

  // Independent daily controls include product facts only, even when the source also supplies videos.
  const manifest = ['source,market,date,shop_scope,product_rows,sales,gmv'];
  for (let day = 1; day <= 14; day++) {
    manifest.push([source, 'US', statDay(day), shop, 23, day <= 7 ? 299 : 598, day <= 7 ? 1196 : 2392].join(','));
  }
  const file = path.join(dir, 'controls.csv');
  fs.writeFileSync(file, manifest.join('\n') + '\n');
  execFileSync('python3', ['manage.py', 'import-source-baseline', '--db', db, '--file', file], { cwd: root, env });

  const scope = new URLSearchParams({ source, market: 'US', date: cutoff, days: '14' });
  const ranking = () => base + '/#products?' + scope;
  await page.goto(ranking());
  await page.locator('[data-source-reconciliation][data-matched="12"][data-missing="1"][data-mismatch="1"]').waitFor();
  assert.ok((await page.locator('[data-source-reconciliation]').textContent()).includes(shop));
  await upload(rows.filter(omitted));
  await upload(rows);
  await page.reload();
  await page.locator('[data-source-reconciliation][data-matched="14"][data-unverified="0"]').waitFor();
  console.log('PASS 14 merchant days, missing delivery, short delivery, repair and replay');

  scope.set('days', '7');
  await page.goto(ranking());
  await page.locator('[data-source-reconciliation][data-matched="7"]').waitFor();
  const download = page.waitForEvent('download');
  await page.locator('[data-export]').click();
  const csv = fs.readFileSync(await (await download).path(), 'utf8').trim().split(/\r?\n/);
  const headers = csv.shift().replace(/^\uFEFF/, '').split(',');
  assert.equal(csv.length, 23);
  const exported = Object.fromEntries(headers.map((name, i) => [name, csv[20].split(',')[i]]));
  assert.deepEqual([exported.id, exported.source, exported.rank, exported.days, exported.sales, Number(exported.gmv)],
    ['p21', source, '21', '7', '56', 224]);

  async function detailFromRanking(id, pageNumber) {
    await page.goto(ranking() + '&page=' + pageNumber);
    await page.locator('a.record[href*="id=' + id + '&"]').click();
    await page.locator('[data-product-inspiration]').waitFor();
  }
  async function checkInspiration(id, expectedVideos, video, linkedDays) {
    await page.locator('[data-product-inspiration]').click();
    const query = new URLSearchParams(new URL(page.url()).hash.split('?')[1]);
    assert.deepEqual(['source', 'market', 'date', 'days', 'product_id'].map(key => query.get(key)),
      [source, 'US', cutoff, '7', id]);
    const panel = page.locator('[data-product-videos]');
    await panel.waitFor();
    const ids = await panel.locator('a[data-video-id]').evaluateAll(links => links.map(a => a.dataset.videoId));
    assert.deepEqual(ids.sort(), expectedVideos);
    const link = panel.locator('a[data-video-id="' + video + '"]');
    assert.ok((await link.textContent()).includes('关联 ' + linkedDays + ' 天'));
    await link.click();
    await page.locator('.fact-panel').waitFor();
    const linked = new URLSearchParams(new URL(page.url()).hash.split('?')[1]);
    assert.deepEqual(['kind', 'id', 'source', 'date', 'days'].map(key => linked.get(key)), ['videos', video, source, cutoff, '7']);
  }
  await detailFromRanking('p03', 1);
  await checkInspiration('p03', ['v-switch', 'v03'], 'v-switch', 2);
  await detailFromRanking('p21', 3);
  await checkInspiration('p21', ['v-switch'], 'v-switch', 5);
  await detailFromRanking('p22', 3);
  await checkInspiration('p22', ['v22'], 'v22', 7);
  assert.deepEqual(externalSearches, []);
  console.log('PASS duplicate product names, products beyond rank 20, video switching products, and CSV ranking');
  await detailFromRanking('p21', 3);
  await checkDecision(page, base, upload, rows);
  await post(page, base, 'admin/claim', { code: fs.readFileSync(path.join(dir, 'research.admin-setup.txt'), 'utf8').trim() });
  await page.goto(base + '/#admin');
  await page.locator('[data-tab=weekly]').click();
  const cohort = page.locator('[data-weekly-research] [data-cohort=imported]');
  await cohort.waitFor();
  assert.deepEqual((await cohort.locator('td').allTextContents()).slice(-3), ['1', '1', '100%']);
  console.log('PASS five-minute completion appears in the imported-source weekly report');
  const precise = {market:'US',kind:'products',id:'high',name:'高金额合成样本',sales:4,gmv:'99999999999999.01',date:cutoff};
  const precisionSource = await post(page,base,'import',{source:'precision',rows:[precise]});
  await page.goto(base+'/#products?'+new URLSearchParams({source:precisionSource.source,market:'US',date:cutoff,days:'1'}));
  const rankedGMV = page.locator('table.records tr').filter({hasText:precise.name}).locator('td.num').first();
  await rankedGMV.waitFor();
  assert.ok((await rankedGMV.textContent()).includes('99,999,999,999,999.01'));
  await page.goto(base+'/#detail?'+new URLSearchParams({source:precisionSource.source,market:'US',
    id:precise.id,kind:'products',date:cutoff,days:'1'}));
  const exactGMV = page.locator('[data-decision-comparison] tbody tr').nth(1).locator('td').first();
  await exactGMV.waitFor();
  assert.ok((await exactGMV.textContent()).includes('99,999,999,999,999.01'));
  await post(page,base,'import',{source:'precision',rows:[{...precise,gmv:'99999999999999.02'}]});
  await page.reload();
  await exactGMV.waitFor();
  assert.ok((await exactGMV.textContent()).includes('99,999,999,999,999.02'));
  console.log('PASS exact cent revisions and late responses after editing a decision');
  assert.deepEqual(errors, []);
}

async function main() {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'tikflowso-research-'));
  const db = path.join(dir, 'research.db');
  const env = { PATH: process.env.PATH, PYTHONDONTWRITEBYTECODE: '1', TIKFLOWSO_ENV_FILE: path.join(dir, 'empty.env') };
  const server = spawn('python3', ['server.py', '--db', db, '--port', '0'], { cwd: root, env, stdio: ['ignore', 'pipe', 'inherit'] });
  const exited = once(server, 'exit');
  let browser;
  try {
    const lines = createInterface({ input: server.stdout });
    const [ready] = await Promise.race([once(lines, 'line'), exited.then(([code]) => { throw Error('Server exited: ' + code); })]);
    lines.close();
    assert.match(ready, /^tikflowso\s+http:\/\/127\.0\.0\.1:\d+$/);
    const base = ready.trim().split(/\s+/).at(-1);
    browser = await chromium.launch({ executablePath: process.env.CHROME_PATH });
    const page = await browser.newPage({ locale: 'zh-CN' });
    page.setDefaultTimeout(10000);
    await verify(base, page, dir, db, env);
  } finally {
    try {
      await browser?.close();
    } finally {
      if (server.exitCode === null) server.kill();
      await exited;
      fs.rmSync(dir, { recursive: true, force: true });
    }
  }
}

main().catch(error => { console.error(error); process.exitCode = 1; });
