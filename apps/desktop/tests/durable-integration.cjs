// Real Electron/owned service/owned PG only. No intercepted API or Provider.
const {_electron:electron}=require('playwright-core');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const desktop=path.resolve(__dirname,'..'),stage=path.join(desktop,'.build/runtime-d1');
const fixture=process.env.CLASSMATTER_TEST_RUNTIME_ROOT,port=Number(process.env.CLASSMATTER_TEST_SERVICE_PORT);
const phase=process.env.CLASSMATTER_TEST_D1_PHASE;
if(!fixture || !path.isAbsolute(fixture) || !Number.isInteger(port) || port<1024 || port>65535 || !['create','restore-clear'].includes(phase))throw new Error('Owned D1 fixture required');
const origin=`http://127.0.0.1:${port}`,sourceFile=path.join(stage,'runtime-source.json'),original=fs.readFileSync(sourceFile);
const source=JSON.parse(original);
assert.equal(source.profile,'conversation-d1');source.runtimeRoot=fixture;source.servicePort=port;
const expectedFile=path.join(fixture,'synthetic-ui-evidence.json');
const env={...process.env};delete env.ELECTRON_RUN_AS_NODE;
let app, page;
const errors=[],external=[],writes=[];
async function closeOwned(){
  let timer;
  try{await Promise.race([app.close(),new Promise((_,reject)=>{timer=setTimeout(()=>reject(new Error('Owned D1 window did not close')),10000);})]);}
  catch(error){
    let exitTimer;
    try{await Promise.race([app.evaluate(({app})=>app.exit(1)).catch(()=>{}),new Promise(resolve=>{exitTimer=setTimeout(resolve,3000);})]);}
    finally{clearTimeout(exitTimer);if(app.process().exitCode===null)app.process().kill();}
    throw error;
  }
  finally{clearTimeout(timer);}
}
async function noOwnedApi(){
  const deadline=Date.now()+8000;
  while(Date.now()<deadline){
    try{await fetch(origin+'/health/live',{signal:AbortSignal.timeout(400)});}
    catch{return;}
    await new Promise(resolve=>setTimeout(resolve,50));
  }
  throw new Error('Owned D1 API did not stop; no shared listener is terminated');
}
async function commit(page,approval=false){
  await page.getByRole('button',{name:'生成预览',exact:true}).click();
  await page.getByRole('button',{name:approval?'明确批准并提交':'确认提交',exact:true}).click();
  await page.getByRole('dialog').waitFor({state:'hidden'});
  await page.waitForFunction(()=>!document.querySelector('[aria-label="刷新数据"]')?.disabled);
}
async function main(){
  fs.writeFileSync(sourceFile,JSON.stringify(source));
  try{
    app=await electron.launch({executablePath:require('electron'),args:[stage],env});
    page=await app.firstWindow();
    page.setDefaultTimeout(10000);
    console.error('Owned D1 checkpoint',phase,'window-ready');
    assert.equal(await page.evaluate(()=>typeof window.classMatterDesktop?.enterDevelopment),'undefined');
    page.on('pageerror',error=>errors.push(error.message));
    page.on('request',request=>{
      if(/^https?:/.test(request.url()) && !request.url().startsWith(origin+'/'))external.push(request.url());
      if(!['GET','HEAD'].includes(request.method()))writes.push(new URL(request.url()).pathname);
    });
    await page.getByLabel('密码', { exact: true }).fill('synthetic-test-passphrase-2026');
    await page.getByRole('button',{name:'登录',exact:true}).click();
    await page.getByRole('heading',{name:'今天想处理什么？',exact:true}).waitFor();
    assert.equal(await page.getByLabel('对话方式').inputValue(),'chat');
    assert.equal(await page.locator('.app-shell > .sidebar .new-chat').count(),1);
    assert.equal(await page.locator('.shell-main > .body-grid > .workspace').count(),1);
    assert.equal(await page.locator('.r1-sidebar').count(),0);
    const history=page.getByRole('region',{name:'已保存的对话'});
    if(phase==='create'){
      await page.getByRole('button',{name:'设置',exact:true}).click();
      await page.getByRole('button',{name:'建立班级与学期',exact:true}).click();
      await page.getByLabel('班级名称',{exact:true}).fill('合成D1桌面验收班');
      await page.getByLabel('学期名称',{exact:true}).fill('合成D1学期');
      await page.getByLabel('学期开始').fill('2026-09-01');
      await page.getByLabel('学期结束（不包含该日）').fill('2027-01-31');
      await commit(page,true);
      await page.getByRole('button',{name:'学生',exact:true}).click();
      await page.getByRole('button',{name:'添加学生',exact:true}).click();
      await page.getByLabel('学生姓名').fill('合成D1学生');
      await commit(page);
      await page.getByRole('button',{name:/合成D1学生/}).click();
      await page.getByRole('button',{name:'记录事实',exact:true}).click();
      await page.getByLabel('事实原文（观察类型请留空）').fill('合成D1重启保留事实');
      await commit(page);
      await page.getByRole('button',{name:'基于事实建立跟进',exact:true}).click();
      await page.getByLabel('跟进标题').fill('合成D1重启保留任务');
      await commit(page);
      await page.getByRole('button',{name:'对话',exact:true}).click();
      await page.getByLabel('对话方式').selectOption('read');
      await page.getByLabel('输入消息').fill('合成D1桌面持久查询');
      await page.getByRole('button',{name:'发送消息',exact:true}).click();
      await history.getByText('回复完成',{exact:true}).waitFor();
      console.error('Owned D1 checkpoint',phase,'answer-saved');
      await page.getByLabel('会话名称').fill('合成D1桌面已保存');
      await page.getByRole('button',{name:'保存名称',exact:true}).click();
      await page.waitForFunction(()=>!Array.from(document.querySelectorAll('button')).find(item=>item.textContent.trim()==='保存名称')?.disabled);
      const receipts=await history.locator('[data-source-id]').evaluateAll(nodes=>nodes.map(node=>node.dataset.sourceId));assert.equal(receipts.length,1);
      const savedPath=new URL(page.url()).pathname;
      const geometry=await page.locator('.r1-composer').evaluate(element=>{
        const rect=element.getBoundingClientRect();return {top:rect.top,bottom:rect.bottom,height:innerHeight};
      });
      assert(geometry.top>44 && geometry.bottom<=geometry.height && geometry.bottom>=geometry.height-60,'Composer stays near the window bottom inside the original shell');
      const evidence=path.join(desktop,'.build/evidence');fs.mkdirSync(evidence,{recursive:true});
      await page.screenshot({path:path.join(evidence,'unified-connected-workbench.png')});
      await page.reload();
      await history.getByText('合成D1桌面持久查询',{exact:true}).waitFor();
      assert.deepEqual(await history.locator('[data-source-id]').evaluateAll(nodes=>nodes.map(node=>node.dataset.sourceId)),receipts);
      assert.equal(writes.filter(item=>item.endsWith('/events')).length,1);
      fs.writeFileSync(expectedFile,JSON.stringify({savedPath,receipts}));
      console.error('Owned D1 checkpoint',phase,'reload-verified');
      await closeOwned();app=null;await noOwnedApi();
    }else{
      const expected=JSON.parse(fs.readFileSync(expectedFile,'utf8'));
      await page.getByRole('region',{name:'聊天列表'}).getByRole('button',{name:'合成D1桌面已保存',exact:true}).click();
      await history.getByText('合成D1桌面持久查询',{exact:true}).waitFor();
      assert.equal(new URL(page.url()).pathname,expected.savedPath);
      assert.deepEqual(await history.locator('[data-source-id]').evaluateAll(nodes=>nodes.map(node=>node.dataset.sourceId)),expected.receipts);
      assert.equal(writes.filter(item=>item.endsWith('/events')).length,0);
      await page.getByLabel('对话方式').selectOption('draft');
      await page.getByLabel('输入消息').fill('合成D1未提交任务草稿');
      await page.getByRole('button',{name:'发送消息',exact:true}).click();
      await history.getByRole('heading',{name:'未提交的任务草稿',exact:true}).waitFor();
      await history.getByRole('button',{name:'清除对话正文',exact:true}).click();
      await page.getByRole('dialog').getByRole('button',{name:'明确批准并提交',exact:true}).click();
      await page.getByRole('dialog').waitFor({state:'hidden'});
      await history.getByText('正文已清除；事实与手工任务不受影响。',{exact:true}).waitFor();
      console.error('Owned D1 checkpoint',phase,'clear-verified');
      await page.reload();
      await history.getByText('正文已清除；事实与手工任务不受影响。',{exact:true}).waitFor();
      assert.equal(await history.getByText('合成D1桌面持久查询',{exact:true}).count(),0);
      assert.equal(writes.filter(item=>item.endsWith('/events')).length,1);
      const closed=app.waitForEvent('close');
      await app.evaluate(({app})=>app.exit(137)).catch(()=>{});await closed;app=null;
      await noOwnedApi();
    }
    assert.deepEqual(errors,[]);assert.deepEqual(external,[]);
    console.log(JSON.stringify({synthetic:true,phase,pageErrors:errors,externalRequests:external,ownedApiStopped:true}));
  }catch(error){
    console.error('Owned D1 UI failed',phase,page?.url(),error);
    throw error;
  }finally{
    fs.writeFileSync(sourceFile,original);
    if(app)await closeOwned();
  }
}
main().catch(error=>{console.error(error);process.exitCode=1;});
