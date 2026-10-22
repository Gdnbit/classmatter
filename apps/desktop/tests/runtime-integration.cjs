const {_electron:electron}=require('playwright-core');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const desktop=path.resolve(__dirname,'..'),stage=path.join(desktop,'.build/runtime');
const fixtureRoot=process.env.CLASSMATTER_TEST_RUNTIME_ROOT;
if(!fixtureRoot || !path.isAbsolute(fixtureRoot))throw new Error('Owned synthetic fixture required');
const sourceFile=path.join(stage,'runtime-source.json'),original=fs.readFileSync(sourceFile);
const config=JSON.parse(original);config.runtimeRoot=fixtureRoot;
const env={...process.env};delete env.ELECTRON_RUN_AS_NODE;
const evidence=path.join(desktop,'.build/evidence/runtime');fs.mkdirSync(evidence,{recursive:true});
let app;
const errors=[],remote=[];
async function launch(){
  app=await electron.launch({executablePath:require('electron'),args:[stage],env});
  const page=await app.firstWindow();
  page.on('pageerror',error=>errors.push(error.message));
  page.on('request',request=>{if(/^https?:/.test(request.url()) && !request.url().startsWith('http://127.0.0.1:8000/'))remote.push(request.url());});
  await page.getByLabel('Owner 密码').fill('synthetic-test-passphrase-2026');
  await page.getByRole('button',{name:'登录',exact:true}).click();
  await page.getByRole('heading',{name:'今天想处理什么？',exact:true}).waitFor();
  return page;
}
async function commit(page,approved=false){
  await page.getByRole('button',{name:'生成预览',exact:true}).click();
  await page.getByRole('button',{name:approved?'明确批准并提交':'确认提交',exact:true}).click();
  await page.getByRole('dialog').waitFor({state:'hidden'});
}
async function main(){
  fs.writeFileSync(sourceFile,JSON.stringify(config));
  try {
    let page=await launch();
    await page.getByRole('button',{name:'建立班级与学期',exact:true}).click();
    await page.getByLabel('班级名称',{exact:true}).fill('合成桌面验收班');
    await page.getByLabel('学期名称',{exact:true}).fill('合成学期');
    await page.getByLabel('学期开始').fill('2026-09-01');
    await page.getByLabel('学期结束（不包含该日）').fill('2027-01-31');
    await commit(page,true);
    await page.getByRole('button',{name:'学生',exact:true}).click();
    await page.getByRole('button',{name:'添加学生',exact:true}).click();
    await page.getByLabel('学生姓名（允许同名，内部 ID 区分）').fill('合成桌面学生');
    await commit(page);
    await page.getByRole('button',{name:/合成桌面学生.*版本/}).click();
    await page.getByRole('button',{name:'记录事实',exact:true}).click();
    await page.getByLabel('发生时间（本机时区）').fill('2026-10-08T08:00');
    await page.getByLabel('事实原文（观察类型请留空）').fill('合成桌面持久化事实');
    await commit(page);
    await page.getByText('合成桌面持久化事实',{exact:true}).waitFor();
    await page.getByRole('button',{name:'基于事实建立跟进',exact:true}).click();
    await page.getByLabel('跟进标题').fill('合成桌面持久化任务');
    await commit(page);
    assert.ok(await page.locator('.desktop-titlebar').isVisible());
    await page.screenshot({path:path.join(evidence,'01-saved.png')});
    await app.close();app=null;
    await assert.rejects(fetch('http://127.0.0.1:8000/health/live',{signal:AbortSignal.timeout(1000)}));
    page=await launch();
    await page.getByRole('button',{name:'工作',exact:true}).click();
    await page.getByText('合成桌面持久化任务',{exact:true}).waitFor();
    await page.getByRole('button',{name:'学生',exact:true}).click();
    await page.getByRole('button',{name:/合成桌面学生.*版本/}).click();
    await page.getByText('合成桌面持久化事实',{exact:true}).waitFor();
    await page.screenshot({path:path.join(evidence,'02-after-restart.png')});
    await page.getByRole('button',{name:'对话',exact:true}).click();
    await page.getByLabel('输入消息').fill('合成查询当前工作');
    await page.getByRole('button',{name:'发送消息',exact:true}).click();
    await page.locator('.r1-messages').getByText(/来源已重新查询/).waitFor();
    assert.ok(await page.locator('.r1-composer').evaluate(el=>el.getBoundingClientRect().bottom<=innerHeight));
    await page.getByLabel('Agent 交互模式').selectOption('draft');
    await page.getByLabel('输入消息').fill('合成桌面未提交草稿');
    await page.getByRole('button',{name:'发送消息',exact:true}).click();
    await page.getByRole('heading',{name:'未提交的任务草稿',exact:true}).waitFor();
    await page.getByRole('button',{name:'工作',exact:true}).click();
    assert.equal(await page.getByText('合成桌面未提交草稿',{exact:true}).count(),0);
    await page.screenshot({path:path.join(evidence,'03-draft-not-saved.png')});
    assert.deepEqual(errors,[]);assert.deepEqual(remote,[]);
    // Electron's forced app.exit bypasses before-quit, unlike the ordinary
    // application close above. Observe the actual app, not a Windows launcher.
    const exited=app.waitForEvent('close');
    await app.evaluate(({app})=>app.exit(137)).catch(()=>{});
    await exited;app=null;
    const deadline=Date.now()+8000;
    let gone=false;
    while(Date.now()<deadline){
      try {await fetch('http://127.0.0.1:8000/health/live',{signal:AbortSignal.timeout(500)});}
      catch {gone=true;break;}
      await new Promise(resolve=>setTimeout(resolve,50));
    }
    assert.ok(gone,'Owned API must exit on parent pipe EOF after desktop crash');
    fs.writeFileSync(path.join(evidence,'result.json'),JSON.stringify({scope:'Synthetic disposable database and existing R1 UI; deterministic fake provider, not real-model quality or frozen shell migration',checks:['owned-process-proof','private-approval-and-command','record-task-linked','restart-persistence','owned-api-stop','read-tool-source','draft-not-committed','parent-crash-pipe-cleanup'],pageErrors:errors,externalRequests:remote},null,2));
    console.log('Synthetic desktop record/task/restart passed');
  } catch(error){if(app){const page=await app.firstWindow();await page.screenshot({path:path.join(evidence,'failure.png')}).catch(()=>{});console.error('Runtime UI failed:',page.url());}throw error;}
  finally {try{if(app)await app.close();}finally{fs.writeFileSync(sourceFile,original);}}
}
main().catch(error=>{console.error(error);process.exitCode=1;});
