const {createRequire}=require('node:module');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
// Manual live-provider test only: an empty synthetic D3 instance with a model
// already tested/enabled by its operator. Never configures a Key or billing.
if(process.env.CLASSMATTER_RUN_LIVE_CHAT_ACCEPTANCE!=='1')throw new Error('Explicit live synthetic acceptance opt-in required');
const root=path.resolve(__dirname,'../../..'),desktop=path.join(root,'apps/desktop'),req=createRequire(path.join(desktop,'package.json'));
const report=path.join(root,'test-results/live-chat-acceptance.json');fs.mkdirSync(path.dirname(report),{recursive:true});
const {_electron:electron}=req('playwright-core'),stage=path.join(desktop,'.build/runtime-d3');
let app,page;const results=[],errors=[];
async function launch(){
 const env={...process.env};delete env.ELECTRON_RUN_AS_NODE;
 app=await electron.launch({executablePath:req('electron'),args:[stage,'--classmatter-development-no-password'],env});
 page=await app.firstWindow({timeout:60000});page.setDefaultTimeout(60000);page.on('pageerror',e=>errors.push(e.message));await page.getByLabel('������Ϣ').waitFor();
}
async function turn(text,expected){
 const start=Date.now();await page.getByLabel('������Ϣ').fill(text);
 const reply=page.waitForResponse(r=>r.request().method()==='POST'&&/\/workspace-chat\/threads\/[^/]+\/turns$/.test(new URL(r.url()).pathname));
 await page.getByRole('button',{name:'������Ϣ',exact:true}).click();
 const response=await reply;assert.equal(response.status(),200);const accepted=await response.json();
 const id=new URL(response.url()).pathname.split('/').at(-2),request=accepted.turn.request_id;
 await page.waitForFunction(async target=>{
   const session=await(await fetch('/api/identity/session')).json();
   const saved=await(await fetch(`/api/workspaces/${session.subject.workspace_id}/workspace-chat/threads/${target.id}`)).json();
   const last=saved.turns?.find(row=>row.request_id===target.request);
   return last&&!['queued','running'].includes(last.state);
 },{id,request},{timeout:60000,polling:500});
 await page.waitForFunction(()=>!document.querySelector('[aria-label="ֹͣ Agent"]'),null,{timeout:60000});
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
 const card=page.getByRole('region',{name:'�Ի��еĲ�����ѡ'}).last();await card.getByRole('button',{name:'Ԥ���������',exact:true}).click();
 const dialog=page.getByRole('dialog');assert.equal(await dialog.locator('input,textarea,select').count(),0);
 await dialog.getByRole('button',{name:/^(ȷ���ύ|��ȷ��׼���ύ)$/}).click();await dialog.waitFor({state:'hidden'});await card.getByRole('status').filter({hasText:'�ѱ���'}).waitFor();
}
(async()=>{try{
 await launch();
 await page.getByText('ClassMatter �� gemini-3.1-flash-lite',{exact:true}).waitFor();
 assert.equal(await page.getByLabel('�л��༶ѧ��').inputValue(),'','Empty synthetic class scope required; existing data preserved');
 await turn('���Ǻϳ����ա���ס���ΰ��ţ���ɫ���731����ֻ�ظ����Ѽ�ס��','�Ѽ�ס');
 await turn('�ղŵİ�����ʲô��ֻ�ظ����š�','��ɫ���731');
 const url=page.url();await page.reload();await page.getByRole('region',{name:'�ѱ���ĶԻ�'}).getByText('�ղŵİ�����ʲô��ֻ�ظ����š�',{exact:true}).waitFor();
 results.push({case:'refresh persistence',passed:true});
 await app.close();app=null;await launch();await page.getByText('ClassMatter �� gemini-3.1-flash-lite',{exact:true}).waitFor();await page.goto(url);await page.getByLabel('������Ϣ').waitFor();
 await turn('�ٴ�ȷ�ϣ��ղŵİ�����ʲô��ֻ�ظ����š�','��ɫ���731');
 results.push({case:'full app restart, model and DB context restored',passed:true});
 const steps=[
 ['�����ϳ�������һ�࣬�ϳɵ�һѧ�ڣ�2026-09-01��2027-01-30��','class.create'],
 ['�Ѱ༶���Ƹ�Ϊ�ϳ������߶��ࡣ','class.update'],
 ['��ѧ�����Ƹ�Ϊ�ϳ������޶�ѧ�ڡ�','term.update'],
 ['����ѧ���ϳ�����ѧ���ס�','student.create'],
 ['�Ѻϳ�����ѧ���׸���Ϊ�ϳ�����ѧ���ҡ�','student.update_name'],
 ['��������ϳ������ռ���ִ��','task.create'],
 ['������ϳ������ռ���ִ��Ϊ�ϳ�����ǩ�ֻ�ִ��','task.update'],
 ['�����ĵ��ϳ����հ༶С�ᣬ����Ϊ�����Ǻϳɲ���С�ᣬ����ʦ�˶ԡ�','document.create'],
 ['���ĵ��ϳ����հ༶С��׷��һ�Σ��ϳ����ղ�����䡣����ԭ�ġ�','document.revise']];
 for(const[text,command]of steps){const last=await turn(text);assert.equal(last.candidate?.command,command,JSON.stringify(last));await confirm();}
 await page.getByRole('button',{name:'ѧ��',exact:true}).click();await page.getByRole('region',{name:'ѧ���嵥',exact:true}).getByRole('button',{name:/�ϳ�����ѧ����/}).waitFor();
 await page.getByRole('button',{name:'����',exact:true}).click();await page.getByRole('button',{name:/�ϳ�����ǩ�ֻ�ִ/}).waitFor();
 await page.getByRole('button',{name:'����������',exact:true}).click();await page.getByRole('button',{name:/�ϳ����հ༶С��/}).first().click();await page.getByRole('button',{name:'ԭ��',exact:true}).click();
 const doc=page.locator('.document-text');assert((await doc.innerText()).includes('����ʦ�˶�'));assert((await doc.innerText()).includes('�ϳ����ղ������'));
 results.push({case:'same-world student, task and document pages',passed:true});assert.deepEqual(errors,[]);fs.writeFileSync(report,JSON.stringify(results,null,2));console.log('PASS real Gemini + original desktop/UI/QG/BCG/PG, no mock');
}finally{if(app)await app.close();}})().catch(e=>{console.error(e);process.exitCode=1;});
