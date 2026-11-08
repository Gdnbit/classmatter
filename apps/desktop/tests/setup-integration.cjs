// Disposable synthetic first-run UI only. No user instance or real Provider.
const {_electron:electron}=require('playwright-core');
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path');
const stage=path.resolve(__dirname,'../.build/runtime-d1');
const root=process.env.CLASSMATTER_TEST_RUNTIME_ROOT,port=Number(process.env.CLASSMATTER_TEST_SERVICE_PORT);
if(!root||!path.isAbsolute(root)||!Number.isInteger(port)||port<1024||port>65535)throw new Error('Disposable fixture required');
const sourceFile=path.join(stage,'runtime-source.json'),original=fs.readFileSync(sourceFile),source=JSON.parse(original);
source.runtimeRoot=root;source.servicePort=port;
const env={...process.env};delete env.ELECTRON_RUN_AS_NODE;
async function main(){
  let app;const errors=[],external=[];
  try{
    fs.writeFileSync(sourceFile,JSON.stringify(source));
    app=await electron.launch({executablePath:require('electron'),args:[stage],env});
    const setup=await app.firstWindow();setup.on('pageerror',error=>errors.push(error.message));
    setup.on('request',request=>{if(/^https?:/.test(request.url()))external.push(request.url());});
    await setup.getByLabel('本机 密码',{exact:true}).fill('synthetic-test-passphrase-2026');
    await setup.getByLabel('再次输入密码',{exact:true}).fill('synthetic-test-passphrase-2026');
    await setup.getByRole('button',{name:'设置并继续',exact:true}).click();
    await setup.getByRole('heading',{name:'请保存一次性恢复码'}).waitFor();
    assert.equal((await setup.locator('#codes').textContent()).trim().split('\n').length,5);
    assert.equal(await setup.locator('#password').inputValue(),'');
    await setup.getByLabel('我已在安全位置保存恢复码').check();
    await setup.getByRole('button',{name:'继续',exact:true}).click();
    assert.equal(await setup.locator('#codes').textContent(),'');
    await setup.getByLabel('本机 密码',{exact:true}).fill('synthetic-test-passphrase-2026');
    await setup.getByRole('button',{name:'验证并查看初始化预览',exact:true}).click();
    await setup.getByRole('heading',{name:'启用本机会话存储'}).waitFor();
    assert.match(await setup.locator('#hash').textContent(),/风险 X/);
    await setup.getByRole('button',{name:'批准本次初始化',exact:true}).click();
    const next=app.waitForEvent('window');
    await setup.getByRole('button',{name:'进入工作台',exact:true}).click();
    const page=await next;page.on('pageerror',error=>errors.push(error.message));
    page.on('request',request=>{if(/^https?:/.test(request.url())&&!request.url().startsWith(`http://127.0.0.1:${port}/`))external.push(request.url());});
    await page.getByLabel('密码', { exact: true }).fill('synthetic-test-passphrase-2026');
    await page.getByRole('button',{name:'登录',exact:true}).click();
    await page.locator('.app-shell > .sidebar .new-chat').waitFor();
    assert.equal(await page.locator('.app-shell .shell-main .body-grid > .workspace').count(),1);
    assert.equal(await page.locator('.r1-sidebar').count(),0);
    assert.equal(await page.evaluate(()=>typeof window.classMatterSetup),'undefined');
    assert.deepEqual(errors,[]);assert.deepEqual(external,[]);
    console.log(JSON.stringify({synthetic:true,nativeFirstRun:true,originalShell:true,setupCapabilityNotInBusinessWindow:true,pageErrors:errors,externalRequests:external}));
  }finally{if(app)await app.close();fs.writeFileSync(sourceFile,original);}
}
main().catch(error=>{console.error(error);process.exitCode=1;});
