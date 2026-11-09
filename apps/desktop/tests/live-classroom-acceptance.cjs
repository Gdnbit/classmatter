// Explicit real-model acceptance; same native UI and APIs, isolated synthetic DB.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
if(process.env.CLASSMATTER_RUN_LIVE_CLASSROOM!=='1')throw Error('Explicit live synthetic opt-in required');
const {_electron:electron}=require('playwright-core');
const stage=process.env.CLASSMATTER_LIVE_STAGE,report=process.env.CLASSMATTER_LIVE_REPORT;
const model=process.env.CLASSMATTER_LIVE_MODEL||'gemini-3.1-flash-lite';
const attempts=Number(process.env.CLASSMATTER_LIVE_ATTEMPTS||'1');
if(![1,2,3].includes(attempts))throw Error('Bounded explicit test attempts required');
if(!['gemini-3.1-flash-lite','glm-4-flash-250414'].includes(model))throw Error('Explicit approved free model required');
if(!stage||!report||!path.isAbsolute(stage)||!path.isAbsolute(report))throw Error('Explicit isolated stage/report required');
let app,page;const rows=[],errors=[];
function save(){fs.writeFileSync(report,JSON.stringify({live:true,model,test_attempt_limit:attempts,rows,errors},null,2));}
async function launch(){
 const env={...process.env};delete env.ELECTRON_RUN_AS_NODE;
 app=await electron.launch({executablePath:require('electron'),args:[stage,'--classmatter-development-no-password'],env,timeout:60000});
 page=await app.firstWindow({timeout:60000});page.setDefaultTimeout(30000);
 page.on('pageerror',e=>errors.push(e.name));
 await page.getByLabel('输入消息').waitFor();
 await page.getByRole('button',{name:'切换模型',exact:true}).filter({hasText:model}).waitFor();
 // Passive same-origin response clone only: no request/output mocking. Capture
 // metadata before Chromium discards CDP response bodies on route transitions.
 await page.evaluate(()=>{
  window.__liveToolEvents={};const original=window.fetch.bind(window);
  window.fetch=async(...args)=>{const response=await original(...args);const url=new URL(response.url);
   if(/\/turns\/[^/]+\/events$/.test(url.pathname)){
    const request=url.pathname.split('/').at(-2);
    void response.clone().text().then(text=>{window.__liveToolEvents[request]=text.split('\n').filter(line=>line.startsWith('data:')).map(line=>JSON.parse(line.slice(5))).filter(event=>event.type==='tool.started').map(event=>event.payload.tool);}).catch(()=>{window.__liveToolEvents[request]=null;});
   }return response;
  };
 });
}
async function read(relative){return await page.evaluate(async suffix=>{
 const s=await(await fetch('/api/identity/session')).json();const r=await fetch(`/api/workspaces/${s.subject.workspace_id}${suffix}`);
 if(!r.ok)throw Error(`Read failed ${r.status}`);return await r.json();
},relative);}
async function turn(text,continuation=false,attempt=1){
 const start=Date.now();
 const [response]=await Promise.all([
  page.waitForResponse(r=>r.request().method()==='POST'&&/\/workspace-chat\/threads\/[^/]+\/turns$/.test(new URL(r.url()).pathname)),
  (async()=>{if(continuation)await page.getByRole('button',{name:'继续任务',exact:true}).last().click();
   else{await page.getByLabel('输入消息').fill(text);await page.getByRole('button',{name:'发送消息',exact:true}).click();}})(),
 ]);assert.equal(response.status(),200);
 const thread=new URL(response.url()).pathname.split('/').at(-2),request=response.request().postDataJSON().request_id;
 const deadline=Date.now()+70000;let last;
 do{
  const history=await read(`/workspace-chat/threads/${thread}`);last=history.turns.find(t=>t.request_id===request);
  if(last&&!['queued','running'].includes(last.state))break;
  await new Promise(resolve=>setTimeout(resolve,700));
 }while(Date.now()<deadline);
 assert(last,'Accepted request missing from durable history');
 await page.waitForFunction(id=>Object.hasOwn(window.__liveToolEvents,id),request,{timeout:6000});
 const tools=await page.evaluate(id=>window.__liveToolEvents[id],request);assert(Array.isArray(tools),'Tool stream observation must complete');
 rows.push({request_id:request,prompt:text||'continue',attempt,state:last.state,candidate:last.candidate?.command??null,tools,input_tokens:last.input_tokens,output_tokens:last.output_tokens,ms:Date.now()-start});save();
 await page.waitForURL(url=>url.pathname===`/chats/${thread}`);
 await page.waitForFunction(()=>!document.querySelector('[aria-label="停止回复"]'));
 if(last.state==='failed'&&attempt<attempts){
  assert.equal(last.candidate,null);assert.equal(last.action_receipt,null);
  // Test-only explicit user resend, a new request in the same conversation.
  // Never replay a commit, clear failures or retry inside the application.
  await new Promise(resolve=>setTimeout(resolve,2000));return turn(text||'继续完成上面的任务，只处理尚未完成的步骤。',false,attempt+1);
 }
 assert.equal(last.state,'completed',JSON.stringify(rows.at(-1)));assert(last.input_tokens>0&&last.output_tokens>0,'Real provider usage required');
 console.log(JSON.stringify(rows.at(-1)));return {last,thread,request};
}
async function confirm(command){
 const card=page.getByRole('region',{name:'对话中的操作候选'}).last();await card.getByRole('button',{name:'预览这项操作',exact:true}).click();
 const dialog=page.getByRole('dialog');assert.equal(await dialog.locator('input,textarea,select').count(),0);
 await dialog.getByRole('button',{name:/^(确认提交|明确批准并提交)$/}).click();await dialog.waitFor({state:'hidden'});
 await card.getByRole('status').filter({hasText:'已保存'}).waitFor();
 rows.push({case:'confirmed',command});save();
}
(async()=>{try{
 await launch();
 await page.getByRole('button',{name:'新对话',exact:true}).click();
 let result=await turn('这是合成测试，只回复：准备好了。');assert.equal(result.last.candidate,null);assert.deepEqual(rows.at(-1).tools,[]);
 const context=(await read('/context')).data;assert.equal(context.name,'合成联测班');
 result=await turn('在合成联测班中，请按顺序完成以下六步：1.建立合成联测月考，科目数学，满分100；2.给合成学生甲录入这次考试80分；3.建立2排3座的座位表；4.把合成学生甲安排到1排1座；5.把合成学生乙安排到1排2座；6.交换合成学生甲和合成学生乙的座位。每次先准备下一步供我确认，已保存的步骤不要重复。');
 const steps=['exam.create','score.record','seat.layout.create','seat.assign','seat.assign','seat.swap'];
 for(let i=0;i<steps.length;i++){
  if(i)result=await turn('',true);
  assert.equal(result.last.candidate?.command,steps[i],JSON.stringify(result.last));
  const expectedTool={'exam.create':'prepare_exam','score.record':'prepare_score','seat.layout.create':'prepare_seat_layout','seat.assign':'prepare_seat_assignment','seat.swap':'prepare_seat_swap'}[steps[i]];
  assert(rows.filter(r=>r.request_id).at(-1).tools.includes(expectedTool),'The real model must select the corresponding typed tool');
  await confirm(steps[i]);
 }
 const exam=(await read(`/classes/${context.class_id}/terms/${context.term_id}/exams`)).exams[0];
 let scores=await read(`/classes/${context.class_id}/terms/${context.term_id}/exams/${exam.exam_id}`);assert.equal(scores.average,'80.00');
 let seats=(await read(`/classes/${context.class_id}/terms/${context.term_id}/seating`)).layout;
 result=await turn('',true);assert.equal(result.last.candidate,null,'Completed plan must not repeat a write');
 result=await turn('请把合成联测月考数学中合成学生甲的成绩更正为88.5分，更正原因：合成核对。');assert.equal(result.last.candidate?.command,'score.record');await confirm('score.record');
 result=await turn('查询合成联测月考数学成绩，并查看当前座位，告诉我合成学生甲的成绩和两个学生现在分别坐在哪里。只查询，不修改。');assert.equal(result.last.candidate,null);
 for(const value of ['88.5','合成学生甲','合成学生乙'])assert(result.last.assistant_text.includes(value),'Read-only answer must identify the verified students and corrected score');
 await page.getByLabel('更多功能',{exact:true}).click();await page.getByRole('button',{name:'成绩',exact:true}).click();
 await page.getByRole('region',{name:'成绩表格',exact:true}).getByRole('row').filter({hasText:'合成学生甲'}).filter({hasText:'88.50'}).waitFor();
 await page.getByLabel('更多功能',{exact:true}).click();await page.getByRole('button',{name:'座位',exact:true}).click();
 await page.getByRole('button',{name:'1排2座 合成学生甲',exact:true}).waitFor();await page.getByRole('button',{name:'1排1座 合成学生乙',exact:true}).waitFor();
 const chat=`/chats/${result.thread}`;await page.reload();await page.getByRole('button',{name:'1排2座 合成学生甲',exact:true}).waitFor();
 await app.close();app=null;await launch();await page.goto(new URL(chat,page.url()).href);await page.getByLabel('输入消息').waitFor();
 scores=await read(`/classes/${context.class_id}/terms/${context.term_id}/exams/${exam.exam_id}`);assert.equal(scores.average,'88.50');
 assert.equal((await read(`/classes/${context.class_id}/terms/${context.term_id}/seating`)).layout.version,seats.version);
 const history=await read(`/workspace-chat/threads/${result.thread}`);assert(history.turns.some(t=>t.request_id===result.request&&t.assistant_text.includes('88.5')));
 rows.push({case:'real native API restart, chat/grades/seats persisted',passed:true});assert.deepEqual(errors,[]);save();console.log('PASS real provider/native conversation/classroom chain');
}catch(error){rows.push({case:'failed',type:error.name,message:String(error.message).slice(0,1200)});save();throw error;}finally{if(app)await app.close();}})().catch(e=>{console.error(e);process.exitCode=1;});
