// Actual local synthetic development entry: no password/setup window or API mock.
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
    for(let pass=0;pass<2;pass++){
      app=await electron.launch({executablePath:require('electron'),args:[stage,'--classmatter-development-no-password'],env});
      const page=await app.firstWindow();page.on('pageerror',error=>errors.push(error.message));
      page.on('request',request=>{if(/^https?:/.test(request.url())&&!request.url().startsWith(`http://127.0.0.1:${port}/`))external.push(request.url());});
      await page.locator('.app-shell > .sidebar .new-chat').waitFor();
      assert.equal(await page.getByLabel('Owner 密码').count(),0);
      assert.equal(await page.evaluate(()=>typeof window.classMatterSetup),'undefined');
      assert.equal(await page.evaluate(()=>document.cookie.includes('class_os_')),false);
      // Electron uses an isolated BrowserWindow session, not Playwright's
      // default context. Inspect only cookie flags, never return secret values.
      const cookies=await app.evaluate(async({BrowserWindow},url)=>(await BrowserWindow.getAllWindows()[0].webContents.session.cookies.get({url})).map(({name,httpOnly,sameSite,path})=>({name,httpOnly,sameSite,path})),`http://127.0.0.1:${port}/api`);
      for(const name of ['class_os_client','class_os_csrf','class_os_session']){
        const cookie=cookies.find(item=>item.name===name);
        assert(cookie?.httpOnly && cookie.sameSite==='strict' && cookie.path==='/api');
      }
      if(pass===0){
        await page.getByRole('button',{name:'建立班级与学期',exact:true}).click();
        await page.getByLabel('班级名称',{exact:true}).fill('合成免密码开发验收班');
        await page.getByLabel('学期名称',{exact:true}).fill('合成开发学期');
        await page.getByLabel('学期开始').fill('2026-09-01');
        await page.getByLabel('学期结束（不包含该日）').fill('2027-01-31');
        await page.getByRole('button',{name:'生成预览',exact:true}).click();
        await page.getByRole('button',{name:'明确批准并提交',exact:true}).click();
        await page.getByRole('dialog').waitFor({state:'hidden'});
      }
      await page.getByRole('combobox',{name:'切换班级学期'}).getByRole('option',{name:'合成免密码开发验收班 · 合成开发学期',exact:true}).waitFor({state:'attached'});
      await page.reload();await page.locator('.app-shell > .sidebar .new-chat').waitFor();
      assert.equal(await page.getByLabel('Owner 密码').count(),0);
      await app.close();app=null;
    }
    assert.deepEqual(errors,[]);assert.deepEqual(external,[]);
    console.log(JSON.stringify({synthetic:true,passwordPrompts:0,originalISB:true,BCGPreviewAndApproval:true,restartPreserved:true,pageErrors:errors,externalRequests:external}));
  }finally{if(app)await app.close();fs.writeFileSync(sourceFile,original);}
}
main().catch(error=>{console.error(error);process.exitCode=1;});
