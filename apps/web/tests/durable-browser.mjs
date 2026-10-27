import { chromium } from '@playwright/test';
import assert from 'node:assert/strict';

const base = process.env.CLASS_OS_TEST_URL;
if (!/^http:\/\/127\.0\.0\.1:\d+$/.test(base || '')) throw new Error('Owned synthetic fixture required');
const browser = await chromium.launch({ headless: true, ...(process.platform === 'win32' ? { channel: 'msedge' } : {}) });
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, timezoneId: 'Asia/Shanghai' });
const page = await context.newPage(), errors = [], external = [], writes = [];
page.on('pageerror', error => errors.push(error.message));
page.on('request', request => {
  if (/^https?:/.test(request.url()) && !request.url().startsWith(base + '/')) external.push(request.url());
  if (!['GET', 'HEAD'].includes(request.method())) writes.push(new URL(request.url()).pathname);
});
const history = page.getByRole('region', { name: '已保存的对话' });
try {
  await page.goto(base + '/');
  await page.getByLabel('Owner 密码').fill('synthetic-test-passphrase-2026');
  await page.getByRole('button', { name: '登录', exact: true }).click();
  await page.getByText('已发送文字和完成结果由数据库保存。', { exact: false }).waitFor();
  await page.getByLabel('输入消息').fill('合成耐久浏览器查询');
  await page.getByRole('button', { name: '发送消息', exact: true }).click();
  await history.getByText('会话输出已保存 · 无业务写入', { exact: true }).waitFor();
  // Saved history can render before the existing protected navigation and
  // class reread finish. Observe the real URL transition, not a React tick.
  await page.waitForURL(/\/conversations\/[a-f0-9-]{36}\/[a-f0-9-]{36}\/[a-f0-9-]{36}$/, { timeout: 5000 });
  assert.match(new URL(page.url()).pathname, /^\/conversations\/[a-f0-9-]{36}\/[a-f0-9-]{36}\/[a-f0-9-]{36}$/);
  await history.getByText('合成耐久浏览器查询', { exact: true }).waitFor();
  await history.getByText(/当时的查询来源/).click();
  assert.match(await history.innerText(), /查询回执：[a-f0-9-]{36}/);
  const firstPath = new URL(page.url()).pathname;
  await page.getByLabel('会话名称').fill('合成耐久浏览器验收');
  await page.getByRole('button', { name: '保存名称', exact: true }).click();
  await page.waitForFunction(() => document.querySelector('[aria-label="会话名称"]')?.value === '合成耐久浏览器验收'
    && !Array.from(document.querySelectorAll('button')).find(item => item.textContent.trim() === '保存名称')?.disabled);
  const starts = () => writes.filter(path => path.endsWith('/events')).length;
  assert.equal(starts(), 1);
  await page.reload();
  await history.getByText('合成耐久浏览器查询', { exact: true }).waitFor();
  assert.equal(new URL(page.url()).pathname, firstPath);
  assert.equal(await page.getByLabel('会话名称').inputValue(), '合成耐久浏览器验收');
  assert.equal(starts(), 1);  // Refresh is reads, never a Provider restart.
  // Delay the real authorized response, not its body or source data. Ignore
  // the browser abort here deliberately to prove the connection fence wins.
  await page.evaluate(() => {
    const original = window.fetch;
    window.d1RealFetch = original;
    window.d1DelayedReady = false;
    window.d1GateTaken = false;
    window.fetch = async (...args) => {
      const response = await original(...args);
      if (String(args[0]).endsWith('/history') && !window.d1GateTaken) {
        window.d1GateTaken = true;
        window.d1DelayedReady = true;
        await new Promise(resolve => { window.d1Release = resolve; });
      }
      return response;
    };
  });
  await history.getByRole('button', {name:'重新读取对话',exact:true}).click();
  await page.waitForFunction(() => window.d1DelayedReady);
  await page.evaluate(() => { window.dispatchEvent(new Event('offline')); window.d1Release(); });
  await history.getByText('正在核对；上次快照不能用于提交',{exact:true}).waitFor();
  await page.waitForTimeout(300);
  assert.equal(await history.getByText('来自当前授权数据库',{exact:true}).count(),0);
  await page.evaluate(() => { window.fetch=window.d1RealFetch; window.dispatchEvent(new Event('online')); });
  await history.getByText('来自当前授权数据库',{exact:true}).waitFor();
  const reads=[];
  const countRead=request=>{if(request.method()==='GET' && new URL(request.url()).pathname.endsWith('/history'))reads.push(request.url());};
  page.on('request',countRead);
  await page.evaluate(() => { for(let index=0;index<20;index++)window.dispatchEvent(new Event('focus')); });
  await page.waitForTimeout(750);
  assert.ok(reads.length<=1,`focus burst must coalesce, saw ${reads.length}`);
  page.off('request',countRead);
  await page.getByLabel('会话名称').fill('合成未保存标题');
  await page.evaluate(() => window.dispatchEvent(new Event('focus')));
  await page.waitForTimeout(300);
  assert.equal(await page.getByLabel('会话名称').inputValue(),'合成未保存标题');
  await page.getByLabel('会话名称').fill('合成耐久浏览器验收');
  await page.getByLabel('输入消息').fill('合成未发送内容不得跨范围');
  await context.setOffline(true);
  await page.waitForFunction(()=>navigator.onLine===false);
  assert.equal(await page.evaluate(()=>fetch('/health/live').then(()=>false,()=>true)),true);
  await history.getByText('正在核对；上次快照不能用于提交',{exact:true}).waitFor();
  assert.equal(await page.getByLabel('输入消息').inputValue(),'合成未发送内容不得跨范围');
  assert.equal(await page.getByLabel('输入消息').isEnabled(),true);
  assert.equal(await page.getByRole('button',{name:'发送消息',exact:true}).isDisabled(),true);
  await context.setOffline(false);
  await page.waitForFunction(()=>navigator.onLine===true);
  await history.getByText('来自当前授权数据库',{exact:true}).waitFor();
  await page.getByRole('button',{name:'发送消息',exact:true}).waitFor();
  await page.waitForFunction(()=>!document.querySelector('[aria-label="发送消息"]')?.disabled);
  assert.equal(await page.getByLabel('输入消息').inputValue(),'合成未发送内容不得跨范围');
  await page.evaluate(() => {
    history.pushState(null,'','/dashboard'); window.dispatchEvent(new PopStateEvent('popstate'));
  });
  await page.waitForTimeout(300);
  assert.equal(await page.getByLabel('输入消息').inputValue(),'合成未发送内容不得跨范围');
  await page.getByLabel('输入消息').fill('');
  await page.getByText('synthetic browser retained fact',{exact:true}).waitFor();
  await page.goto(base+firstPath);
  await history.getByText('合成耐久浏览器查询',{exact:true}).waitFor();
  assert.equal(await page.getByLabel('输入消息').inputValue(),'');
  await page.getByLabel('Agent 交互模式').selectOption('draft');
  await page.getByLabel('输入消息').fill('合成耐久任务草稿');
  await page.getByRole('button', { name: '发送消息', exact: true }).click();
  await history.getByRole('heading', { name: '未提交的任务草稿', exact: true }).waitFor();
  await history.getByRole('button', { name: '打开任务草稿并核对', exact: true }).click();
  await page.getByRole('dialog').getByRole('heading', { name: '建立手工跟进', exact: true }).waitFor();
  await page.getByRole('dialog').getByRole('button', { name: '关闭表单', exact: true }).click();
  assert.equal(starts(), 2);
  await page.getByRole('button',{name:'设置',exact:true}).click();
  await page.getByRole('button',{name:'生成耐久会话退出预览',exact:true}).click();
  let exitDialog=page.getByRole('dialog');
  const refusal=page.waitForResponse(response=>new URL(response.url()).pathname.endsWith('/commands/'+process.env.CLASS_OS_D1_REAUTH_PHASE));
  await exitDialog.getByRole('button',{name:'明确批准并生成证据包',exact:true}).click();
  assert.equal((await refusal).status(),428);
  // A definite first-request refusal is not an unknown commit. Cancel the
  // uncommitted preview, use the original ISB password form, then re-preview.
  await exitDialog.getByRole('button',{name:'取消导出预览',exact:true}).click();
  await page.getByRole('button',{name:'重新验证身份',exact:true}).click();
  await page.getByLabel('当前密码（身份验证）').fill('synthetic-test-passphrase-2026');
  await page.getByRole('button',{name:'明确执行身份操作',exact:true}).click();
  await page.getByRole('dialog').waitFor({state:'hidden'});
  await page.getByRole('button',{name:'生成耐久会话退出预览',exact:true}).click();
  exitDialog=page.getByRole('dialog');
  // Drop one REAL commit reply after the database has responded. The UI must
  // retain the same proposal/key and resolve by GET, never submit a new export.
  await page.evaluate(()=>{
    const original=window.fetch;
    window.fetch=async(...args)=>{
      const response=await original(...args);
      if(String(args[0]).endsWith('/commands/commit') && args[1]?.method==='POST'){
        window.fetch=original;throw new TypeError('synthetic response delivery lost');
      }
      return response;
    };
  });
  await exitDialog.getByRole('button',{name:'明确批准并生成证据包',exact:true}).click();
  await exitDialog.getByRole('button',{name:'使用原预览与同键重试导出',exact:true}).waitFor();
  assert.equal(await exitDialog.getByRole('button',{name:'取消导出预览',exact:true}).count(),0);
  await exitDialog.getByRole('button',{name:'核对原导出结果',exact:true}).click();
  await exitDialog.waitFor({state:'hidden'});
  const downloadLink=page.getByRole('link',{name:'下载已批准的合成 v6 证据包（30分钟内）',exact:true});
  const downloadPath=await downloadLink.getAttribute('href');
  const downloaded=page.waitForEvent('download');await downloadLink.click();
  const artifact=await downloaded,stream=await artifact.createReadStream(),chunks=[];
  for await (const chunk of stream)chunks.push(chunk);
  const bundle=JSON.parse(Buffer.concat(chunks).toString('utf8'));
  assert.equal(bundle.schema_version,'classmatter.synthetic-exit.v6');
  assert.equal(bundle.activation_allowed,false);assert.equal(bundle.run_authority,'source-evidence-only');
  await page.goto(base+firstPath);
  await history.getByRole('heading',{name:'未提交的任务草稿',exact:true}).waitFor();
  await history.getByRole('button', { name: '清除对话正文', exact: true }).click();
  const confirm = page.getByRole('dialog');
  await confirm.getByRole('heading', { name: '确认清除会话正文', exact: true }).waitFor();
  const clearRefusal=page.waitForResponse(response=>new URL(response.url()).pathname.endsWith('/commands/commit'));
  await confirm.getByRole('button', { name: '明确批准并提交', exact: true }).click();
  assert.equal((await clearRefusal).status(),409);
  await confirm.getByRole('button',{name:'使用原预览与同键重试提交',exact:true}).waitFor();
  assert.equal(await confirm.getByRole('button',{name:'取消预览',exact:true}).count(),0);
  await confirm.getByRole('button',{name:'使用原预览与同键重试提交',exact:true}).click();
  await confirm.waitFor({ state: 'hidden' });
  await history.getByText('正文已清除；事实与手工任务不受影响。', { exact: true }).waitFor();
  assert.equal(await history.locator('.r1-messages article').count(), 0);
  await page.reload();
  await history.getByText('正文已清除；事实与手工任务不受影响。', { exact: true }).waitFor();
  assert.equal(await history.getByText('合成耐久浏览器查询', { exact: true }).count(), 0);
  assert.equal(starts(), 2);
  assert.equal((await page.request.get(base+downloadPath)).status(),409);
  await page.goto(base + '/dashboard');
  await page.getByText('synthetic browser retained fact', { exact: true }).waitFor();
  assert.equal(starts(), 2);
  assert.deepEqual(errors, []); assert.deepEqual(external, []);
  console.log(JSON.stringify({ synthetic: true, pageErrors: errors, externalRequests: external, starts: starts(),
    reloadRestoredHistory: true, historicalSourceVisible: true, clearHiddenAfterReload: true, draftNotExecuted: true }));
} catch (error) {
  console.error(JSON.stringify({synthetic:true, pageErrors:errors,
    browser:await page.evaluate(()=>({online:navigator.onLine,visibility:document.visibilityState,
      title:document.querySelector('[aria-label="会话名称"]')?.value,
      buttons:Array.from(document.querySelectorAll('.r1-durable button')).map(item=>[item.textContent,item.disabled])})),
    alerts:await page.getByRole('alert').allTextContents(), statuses:await page.getByRole('status').allTextContents(),
    fresh:await history.getByText('来自当前授权数据库',{exact:true}).count()}));
  throw error;
} finally { await context.close(); await browser.close(); }
