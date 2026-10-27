import { chromium } from '@playwright/test';
import assert from 'node:assert/strict';

const base=process.env.CLASS_OS_TEST_URL,fault=process.env.CLASS_OS_D1_FAULT;
if(!/^http:\/\/127\.0\.0\.1:\d+$/.test(base||'') || !['cancel','timeout','save','claim','audit'].includes(fault))throw new Error('Owned synthetic fault fixture required');
const browser=await chromium.launch({headless:true,...(process.platform==='win32'?{channel:'msedge'}:{})});
const context=await browser.newContext(),page=await context.newPage(),errors=[],external=[],starts=[];
page.on('pageerror',error=>errors.push(error.message));
page.on('request',request=>{
  if(/^https?:/.test(request.url()) && !request.url().startsWith(base+'/'))external.push(request.url());
  if(request.method()==='POST' && new URL(request.url()).pathname.endsWith('/events'))starts.push(request.url());
});
try{
  await page.goto(base+'/');
  await page.getByLabel('Owner 密码').fill('synthetic-test-passphrase-2026');
  await page.getByRole('button',{name:'登录',exact:true}).click();
  await page.getByLabel('Agent 交互模式').selectOption('chat');
  await page.getByLabel('输入消息').fill('synthetic '+fault+' user input');
  // Two same-frame submissions must still produce only one user intent/run.
  await page.locator('form.r1-composer').evaluate(form=>{form.requestSubmit();form.requestSubmit();});
  const history=page.getByRole('region',{name:'已保存的对话'});
  if(fault==='cancel'){
    await page.getByRole('status').filter({hasText:'正在运行；以数据库核对结果为准'}).waitFor();
    const cancelled=page.waitForResponse(response=>new URL(response.url()).pathname.endsWith('/cancel'));
    await page.getByRole('button',{name:'停止 Agent',exact:true}).click();
    assert.equal((await cancelled).status(),200);
  }
  await history.getByText('synthetic '+fault+' user input',{exact:true}).waitFor();
  await page.waitForFunction(()=>!document.querySelector('[aria-label="输入消息"]')?.disabled);
  await page.waitForURL(/\/conversations\//);
  const path=new URL(page.url()).pathname;
  assert.match(path,/^\/conversations\//);
  await page.reload();
  await history.getByText('synthetic '+fault+' user input',{exact:true}).waitFor();
  await history.getByText('来自当前授权数据库',{exact:true}).waitFor();
  assert.equal(await history.locator('article.assistant').count(),0);
  const visible=await page.locator('body').innerText();
  assert.doesNotMatch(visible,/synthetic unsaved failure answer|synthetic private failure canary|会话输出已保存/);
  assert.equal(starts.length,1);assert.deepEqual(errors,[]);assert.deepEqual(external,[]);
  console.log(JSON.stringify({synthetic:true,fault,starts:starts.length,unsavedAnswerHidden:true,refreshDidNotReplay:true,pageErrors:errors,externalRequests:external}));
}finally{await context.close();await browser.close();}
