const {createRequire}=require('node:module');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
// Manual live test: empty synthetic D3 instance; an operator-enabled model.
if(process.env.CLASSMATTER_RUN_LIVE_CHAT_ACCEPTANCE!=='1')throw new Error('Explicit live synthetic acceptance opt-in required');
const root=path.resolve(__dirname,'../../..'),desktop=path.join(root,'apps/desktop'),req=createRequire(path.join(desktop,'package.json'));
const report=path.join(root,'test-results/live-chat-acceptance.json');fs.mkdirSync(path.dirname(report),{recursive:true});
const {_electron:electron}=req('playwright-core'),stage=path.join(desktop,'.build/runtime-d3');
let app,page;const results=[],errors=[];
async function launch(){
 const env={...process.env};delete env.ELECTRON_RUN_AS_NODE;
 app=await electron.launch({executablePath:req('electron'),args:[stage,'--classmatter-development-no-password'],env});
 page=await app.firstWindow({timeout:60000});page.setDefaultTimeout(60000);page.on('pageerror',e=>errors.push(e.message));await page.getByLabel('输入消息').waitFor();
}
async function turn(text,expected){
 const start=Date.now();await page.getByLabel('输入消息').fill(text);
 const reply=page.waitForResponse(r=>r.request().method()==='POST'&&/\/workspace-chat\/threads\/[^/]+\/turns$/.test(new URL(r.url()).pathname));
 await page.getByRole('button',{name:'发送消息',exact:true}).click();
 const response=await reply;assert.equal(response.status(),200);const accepted=await response.json();
 const id=new URL(response.url()).pathname.split('/').at(-2),request=accepted.turn.request_id;
 await page.waitForFunction(async target=>{
   const session=await(await fetch('/api/identity/session')).json();
   const saved=await(await fetch(`/api/workspaces/${session.subject.workspace_id}/workspace-chat/threads/${target.id}`)).json();
   const last=saved.turns?.find(row=>row.request_id===target.request);
   return last&&!['queued','running'].includes(last.state);
 },{id,request},{timeout:60000,polling:500});
 await page.waitForFunction(()=>!document.querySelector('[aria-label="停止回复"]'),null,{timeout:60000});
 await page.waitForURL(url=>/^\/chats\/[a-f0-9-]{36}$/.test(url.pathname));
 const thread=await page.evaluate(()=>location.pathname.split('/').at(-1));
 const saved=await page.evaluate(async id=>{const session=await(await fetch('/api/identity/session')).json();return await(await fetch(`/api/workspaces/${session.subject.workspace_id}/workspace-chat/threads/${id}`)).json()},thread);
 assert(Array.isArray(saved.turns),JSON.stringify({url:page.url(),saved}));
 const last=saved.turns.at(-1);assert.equal(last.user_text,text);assert.equal(last.state,'completed',JSON.stringify(last));
 if(expected)assert(last.assistant_text.includes(expected),last.assistant_text);
 results.push({case:text,passed:true,state:last.state,input_tokens:last.input_tokens,output_tokens:last.output_tokens,ms:Date.now()-start,candidate:last.candidate?.command||null});
 console.log(JSON.stringify(results.at(-1)));fs.writeFileSync(report,JSON.stringify(results,null,2));
 return last;
}
async function confirm(){
 const card=page.getByRole('region',{name:'对话中的操作候选'}).last();await card.getByRole('button',{name:'预览这项操作',exact:true}).click();
 const dialog=page.getByRole('dialog');assert.equal(await dialog.locator('input,textarea,select').count(),0);
 await dialog.getByRole('button',{name:/^(确认提交|明确批准并提交)$/}).click();await dialog.waitFor({state:'hidden'});await card.getByRole('status').filter({hasText:'已保存'}).waitFor();
}
(async()=>{try{
 await launch();
 await page.getByRole('button',{name:'切换模型',exact:true}).filter({hasText:'gemini-3.1-flash-lite'}).waitFor();
 const context=await page.evaluate(async()=>{const session=await(await fetch('/api/identity/session')).json();return await(await fetch('/api/workspaces/'+session.subject.workspace_id+'/context')).json()});
 assert.equal(context.data,null,'Empty synthetic class scope required; existing data preserved');
 await turn('这是合成验收。记住本次暗号：蓝色书包731。请只回复：已记住。','已记住');
 await turn('刚才的暗号是什么？只回复暗号。','蓝色书包731');
 const url=page.url();await page.reload();await page.getByRole('region',{name:'已保存的对话'}).getByText('刚才的暗号是什么？只回复暗号。',{exact:true}).waitFor();
 results.push({case:'refresh persistence',passed:true});
 await app.close();app=null;await launch();await page.getByRole('button',{name:'切换模型',exact:true}).filter({hasText:'gemini-3.1-flash-lite'}).waitFor();await page.goto(url);await page.getByLabel('输入消息').waitFor();
 await turn('再次确认，刚才的暗号是什么？只回复暗号。','蓝色书包731');
 results.push({case:'full app restart, model and DB context restored',passed:true});
 const steps=[
 ['建立合成验收七一班，合成第一学期，2026-09-01至2027-01-30。','class.create'],
 ['把班级名称改为合成验收七二班。','class.update'],
 ['把学期名称改为合成验收修订学期。','term.update'],
 ['添加学生合成验收学生甲。','student.create'],
 ['把合成验收学生甲改名为合成验收学生乙。','student.update_name'],
 ['创建任务合成验收收集回执。','task.create'],
 ['把任务合成验收收集回执改为合成验收签字回执。','task.update'],
 ['生成文档合成验收班级小结，正文为：这是合成测试小结，待教师核对。','document.create'],
 ['给文档合成验收班级小结追加一段：合成验收补充段落。保留原文。','document.revise']];
 for(const[text,command]of steps){const last=await turn(text);assert.equal(last.candidate?.command,command,JSON.stringify(last));await confirm();}
 await page.getByRole('button',{name:'学生',exact:true}).click();await page.getByRole('region',{name:'学生清单',exact:true}).getByRole('button',{name:/合成验收学生乙/}).waitFor();
 await page.getByRole('button',{name:'工作',exact:true}).click();await page.getByRole('main').getByRole('button',{name:/合成验收签字回执/}).waitFor();
 await page.getByLabel('更多功能',{exact:true}).click();await page.getByRole('button',{name:'数据与内容',exact:true}).click();await page.getByRole('button',{name:/合成验收班级小结/}).first().click();await page.getByRole('button',{name:'原文',exact:true}).click();
 const doc=page.locator('.document-text');assert((await doc.innerText()).includes('待教师核对'));assert((await doc.innerText()).includes('合成验收补充段落'));
 results.push({case:'same-world student, task and document pages',passed:true});assert.deepEqual(errors,[]);fs.writeFileSync(report,JSON.stringify(results,null,2));console.log('PASS real Gemini + original desktop/UI/QG/BCG/PG, no mock');
}finally{if(app)await app.close();}})().catch(e=>{console.error(e);process.exitCode=1;});
