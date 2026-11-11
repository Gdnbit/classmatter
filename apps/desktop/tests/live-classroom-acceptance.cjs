// Explicit real-model acceptance; same native UI and APIs, isolated synthetic DB.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
if(process.env.CLASSMATTER_RUN_LIVE_CLASSROOM!=='1')throw Error('Explicit live synthetic opt-in required');
const stage=process.env.CLASSMATTER_LIVE_STAGE,report=process.env.CLASSMATTER_LIVE_REPORT;
const model=process.env.CLASSMATTER_LIVE_MODEL||'gemini-3.1-flash-lite';
const attempts=Number(process.env.CLASSMATTER_LIVE_ATTEMPTS||'1');
const scenario=process.env.CLASSMATTER_LIVE_SCENARIO||'classroom';
if(!['classroom','full-workbench'].includes(scenario))throw Error('Explicit supported scenario required');
if(![1,2,3].includes(attempts))throw Error('Bounded explicit test attempts required');
if(!['gemini-3.1-flash-lite','glm-4-flash-250414'].includes(model))throw Error('Explicit approved free model required');
if(!stage||!report||!path.isAbsolute(stage)||!path.isAbsolute(report))throw Error('Explicit isolated stage/report required');
const {_electron:electron}=require('playwright-core');
let app,page,lastResult;const rows=[],errors=[];
function save(){fs.writeFileSync(report,JSON.stringify({live:true,model,scenario,test_attempt_limit:attempts,rows,errors},null,2));}
async function launch(){
 const env={...process.env};delete env.ELECTRON_RUN_AS_NODE;
 app=await electron.launch({executablePath:require('electron'),args:[stage,'--classmatter-development-no-password'],env,timeout:60000});
 page=await app.firstWindow({timeout:60000});page.setDefaultTimeout(30000);
 page.on('pageerror',e=>errors.push(e.name));
 await page.getByLabel('输入消息').waitFor();
 await page.getByRole('button',{name:'切换模型',exact:true}).filter({hasText:model}).waitFor();
 // Passive same-origin response clone only: no request/output mocking. Capture
 // metadata before Chromium discards CDP response bodies on route transitions.
 const observe=()=>{
  window.__liveToolEvents={};const original=window.fetch.bind(window);
  window.fetch=async(...args)=>{const response=await original(...args);const url=new URL(response.url);
   if(/\/turns\/[^/]+\/events$/.test(url.pathname)){
    const request=url.pathname.split('/').at(-2);
    void response.clone().text().then(text=>{window.__liveToolEvents[request]=text.split('\n').filter(line=>line.startsWith('data:')).map(line=>JSON.parse(line.slice(5))).filter(event=>event.type==='tool.started').map(event=>event.payload.tool);}).catch(()=>{window.__liveToolEvents[request]=null;});
   }return response;
  };
 };
 await page.addInitScript(observe);await page.evaluate(observe);
}
async function read(relative){return await page.evaluate(async suffix=>{
 const s=await(await fetch('/api/identity/session')).json();const r=await fetch(`/api/workspaces/${s.subject.workspace_id}${suffix}`);
 if(!r.ok)throw Error(`Read failed ${r.status}`);return await r.json();
},relative);}
async function world(){
 const context=(await read('/context')).data;
 if(!context)return {context:null};
 const base=`/classes/${context.class_id}/terms/${context.term_id}`;
 const students=(await read(base+'/students')).data,term=await read(base+'/metadata');
 const tasks=(await read('/conversation-d1'+base+'/activity')).data.tasks.map(({task_id,title,status,version})=>({task_id,title,status,version}));
 const docs=(await read(base+'/documents')).data,documents=[];
 for(const doc of docs){const d=(await read(base+'/documents/'+doc.document_id)).data;documents.push({document_id:d.document_id,title:d.title,body:d.body,format:d.format,status:d.status,version:d.version});}
 const exams=(await read(base+'/exams')).exams,results=[];
 for(const exam of exams)results.push(await read(base+'/exams/'+exam.exam_id));
 return {context,term,students,tasks,documents,exams,results,seating:(await read(base+'/seating')).layout};
}
function assertSaved(candidate,before,after,receipt){
 const c=candidate,cmd=c.command;
 if(cmd==='class.create'){assert.equal(after.context.class_id,c.class_id);assert.equal(after.context.term_id,c.term_id);assert.equal(after.context.name,c.name);assert.equal(after.term.name,c.term_name);}
 if(cmd==='class.update')assert.equal(after.context.name,c.name);
 if(cmd==='term.update'){assert.equal(after.term.name,c.name);assert.equal(after.term.start_date,c.start_date);assert.equal(after.term.end_date,c.end_date);}
 if(cmd.startsWith('student.')){const student=after.students.find(s=>s.student_id===c.student_id);assert(student);assert.equal(student.name,c.name);assert.equal(student.version,receipt.version);assert.equal(after.students.length,before.students.length+(cmd==='student.create'?1:0));}
 if(cmd.startsWith('task.')){const task=after.tasks.find(t=>t.task_id===c.task_id);assert(task);assert.equal(task.title,c.title);assert.equal(task.version,receipt.version);if(c.status)assert.equal(task.status,c.status);assert.equal(after.tasks.length,before.tasks.length+(cmd==='task.create'?1:0));}
 if(cmd.startsWith('document.')){const doc=after.documents.find(d=>d.document_id===c.document_id);assert(doc);assert.equal(doc.title,c.title);assert.equal(doc.body,c.body);assert.equal(doc.format,c.format);assert.equal(doc.version,receipt.version);assert.equal(after.documents.length,before.documents.length+(cmd==='document.create'?1:0));}
 if(cmd==='exam.create'){const exam=after.exams.find(e=>e.exam_id===c.exam_id);assert(exam);assert.equal(exam.title,c.title);assert.equal(exam.subject,c.subject);assert.equal(Number(exam.maximum_score),Number(c.maximum_score));}
 if(cmd==='score.record'){const exam=after.results.find(e=>e.exam_id===c.exam_id);assert(exam);const result=exam.results.find(r=>r.student_id===c.student_id);assert(result);assert.equal(result.status,c.status);assert.equal(result.score===null?null:Number(result.score),c.score===null?null:Number(c.score));assert.equal(result.version,receipt.version);}
 if(cmd==='seat.layout.create'){assert.equal(after.seating.rows,c.rows);assert.equal(after.seating.columns,c.columns);assert.equal(after.seating.seats.length,c.rows*c.columns);assert(after.seating.seats.every(s=>s.student_id===null));}
 if(cmd==='seat.assign')assert.equal(after.seating.seats.find(s=>s.row_index===c.row&&s.column_index===c.column).student_id,c.student_id);
 if(cmd==='seat.swap'){for(const [r,col,otherR,otherCol] of [[c.first_row,c.first_column,c.second_row,c.second_column],[c.second_row,c.second_column,c.first_row,c.first_column]])assert.equal(after.seating.seats.find(s=>s.row_index===r&&s.column_index===col).student_id,before.seating.seats.find(s=>s.row_index===otherR&&s.column_index===otherCol).student_id);}
 if(cmd.startsWith('seat.'))assert.equal(after.seating.version,receipt.version);
}
async function assertDialog(candidate,before,dialog){
 const comparison=dialog.getByRole('region',{name:'变更前后对比',exact:true});
 const hasComparison=await comparison.count();
 const target=hasComparison?comparison.getByLabel('待确认的结果',{exact:true}):dialog;
 const fields=await target.locator('dl>div').evaluateAll(nodes=>Object.fromEntries(nodes.map(n=>[n.querySelector('dt').textContent,n.querySelector('dd').textContent])));
 if(hasComparison){
  const old=await comparison.getByLabel('修改前',{exact:true}).locator('dl>div').evaluateAll(nodes=>Object.fromEntries(nodes.map(n=>[n.querySelector('dt').textContent,n.querySelector('dd').textContent])));
  if(candidate.command==='class.update')assert.equal(old['名称'],before.context.name);
  if(candidate.command==='term.update'){assert.equal(old['名称'],before.term.name);assert.equal(old['开始日期'],before.term.start_date);assert.equal(old['结束日期'],before.term.end_date);}
  if(candidate.command==='student.update_name')assert.equal(old['名称'],before.students.find(s=>s.student_id===candidate.student_id).name);
  if(candidate.command==='task.update')assert.equal(old['标题'],before.tasks.find(t=>t.task_id===candidate.task_id).title);
  if(candidate.command==='document.revise'){const doc=before.documents.find(d=>d.document_id===candidate.document_id);assert.equal(old['标题'],doc.title);assert.equal(old['正文'],doc.body);}
  if(candidate.command==='score.record'){const prior=before.results.find(e=>e.exam_id===candidate.exam_id).results.find(r=>r.student_id===candidate.student_id);assert.equal(old['成绩'],prior?.score??'—');}
 }
 const labels={name:'名称',term_name:'学期',start_date:'开始日期',end_date:'结束日期',title:'标题',body:'正文',reason:hasComparison?'更正原因':'原因',subject:'科目',...(!hasComparison?{rows:'排数',columns:'每排座位数',row:'目标排',column:'目标座位',first_row:'原座位排',first_column:'原座位号',second_row:'目标排',second_column:'目标座位号'}:{})};
 for(const [key,label]of Object.entries(labels))if(candidate[key]!==undefined&&candidate[key]!==''&&candidate[key]!==null)assert.equal(fields[label],String(candidate[key]),`Preview field ${key}`);
 for(const [key,label]of [['score',hasComparison?'成绩':'分数'],['maximum_score','满分']])if(candidate[key]!==undefined&&candidate[key]!==null)assert.equal(Number(fields[label]),Number(candidate[key]),`Preview field ${key}`);
 if(candidate.student_id&&before.students&&!candidate.command.startsWith('seat.')&&candidate.command!=='student.update_name'){const name=before.students.find(s=>s.student_id===candidate.student_id)?.name;if(name)assert.equal(fields['学生'],name,'Student target must be visible');}
 if(candidate.command==='score.record'){const exam=before.exams.find(e=>e.exam_id===candidate.exam_id);if(hasComparison){assert.equal(fields['标题'],exam.title);assert.equal(fields['科目'],exam.subject);}else assert.equal(fields['考试'],`${exam.title} · ${exam.subject}`,'Exam and subject must be visible');}
 if(hasComparison&&candidate.command.startsWith('seat.')){
  const previous=before.seating;
  const oldSide=comparison.getByLabel('修改前',{exact:true});
  if(previous){
   const next=structuredClone(previous);
   if(candidate.command==='seat.assign'){
    for(const cell of next.seats)if(cell.student_id===candidate.student_id)cell.student_id=null;
    next.seats.find(s=>s.row_index===candidate.row&&s.column_index===candidate.column).student_id=candidate.student_id;
   }else if(candidate.command==='seat.swap'){
    const a=next.seats.find(s=>s.row_index===candidate.first_row&&s.column_index===candidate.first_column),b=next.seats.find(s=>s.row_index===candidate.second_row&&s.column_index===candidate.second_column);
    [a.student_id,b.student_id]=[b.student_id,a.student_id];
   }
   for(const [side,board]of [[oldSide,previous],[target,next]])for(const cell of board.seats){
    const name=cell.student_id?before.students.find(s=>s.student_id===cell.student_id).name:'空座';
    const label=`${cell.row_index}排${cell.column_index}座：${name}`;
    assert.equal(await side.getByRole('cell').filter({hasText:name}).evaluateAll((nodes,prefix)=>nodes.filter(n=>n.getAttribute('aria-label').startsWith(prefix)).length,label),1,'Actual seating comparison');
   }
  }else assert.match(await oldSide.innerText(),/尚未创建/);
 }
 if(candidate.command==='seat.layout.create')assert.equal(await dialog.getByRole('cell').count(),candidate.rows*candidate.columns);
}
async function turn(text,continuation=false,attempt=1){
 const before=scenario==='full-workbench'?await world():null;
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
 console.log(JSON.stringify(rows.at(-1)));lastResult={last,thread,request,before};return lastResult;
}
async function confirm(command){
 assert.equal(lastResult.last.candidate?.command,command);
 const card=page.getByRole('region',{name:'对话中的操作候选'}).last();
 if(scenario==='full-workbench'){assert.deepEqual(await world(),lastResult.before,'Preparation must not change business state');await page.reload();await card.getByRole('button',{name:'预览这项操作',exact:true}).waitFor();assert.deepEqual(await world(),lastResult.before,'Refreshing a candidate must not save it');}
 const [preview]=await Promise.all([page.waitForResponse(r=>r.request().method()==='POST'&&/\/turns\/[^/]+\/proposal$/.test(new URL(r.url()).pathname)),card.getByRole('button',{name:'预览这项操作',exact:true}).click()]);
 assert.equal(preview.status(),200);assert.deepEqual((await preview.json()).payload,lastResult.last.candidate,'Dialog proposal must equal the durable candidate');
 const dialog=page.getByRole('dialog');await dialog.getByRole('button',{name:/^(确认提交|明确批准并提交)$/}).waitFor();assert.equal(await dialog.locator('input,textarea,select').count(),0);
 if(scenario==='full-workbench'){await assertDialog(lastResult.last.candidate,lastResult.before,dialog);assert.deepEqual(await world(),lastResult.before,'Preview must not save business data');await page.screenshot({path:path.join(path.dirname(report),`${rows.filter(r=>r.case==='confirmed').length+1}-${command}.png`)});}
 await dialog.getByRole('button',{name:/^(确认提交|明确批准并提交)$/}).click();await dialog.waitFor({state:'hidden'});
 await card.getByRole('status').filter({hasText:'已保存'}).waitFor();
 if(scenario==='full-workbench'){
  const saved=await read(`/workspace-chat/threads/${lastResult.thread}`),turn=saved.turns.find(t=>t.request_id===lastResult.request);assert(turn.action_receipt,'Actual saved receipt required');
  assert(turn.change_preview,'Every new action needs a factual comparison');assert.deepEqual(turn.change_preview,lastResult.last.change_preview,'Confirmation cannot change frozen preview');
  const after=await world();assertSaved(lastResult.last.candidate,lastResult.before,after,turn.action_receipt);
  await page.reload();await card.getByRole('status').filter({hasText:'已保存'}).waitFor();assert.deepEqual(await world(),after,'Reloaded world must equal the committed state');
 }
 rows.push({case:'confirmed',command});save();
}
(async()=>{try{
 await launch();
 await page.getByRole('button',{name:'新对话',exact:true}).click();
 let result=await turn('这是合成测试，只回复：准备好了。');assert.equal(result.last.candidate,null);assert.deepEqual(rows.at(-1).tools,[]);
 if(scenario==='full-workbench'){
  assert.equal((await read('/context')).data,null,'No pre-seeded class or students');
  const core=[
   ['class.create',{name:'合成联测班',term_name:'合成联测学期',start_date:'2026-09-01',end_date:'2027-01-30'}],
   ['class.update',{name:'合成联测修订班'}],['term.update',{name:'合成联测修订学期'}],
   ['student.create',{name:'合成学生甲'}],['student.create',{name:'合成学生丙'}],['student.update_name',{name:'合成学生乙'}],
   ['task.create',{title:'合成联测回执'}],['task.update',{title:'合成联测核对回执'}],
   ['document.create',{title:'合成联测小结'}],['document.revise',{title:'合成联测小结'}],
  ];
  result=await turn('请按顺序完成以下十步，每次只准备下一步让我预览确认，已保存的步骤不要重复：1.创建合成联测班，学期合成联测学期，2026-09-01至2027-01-30；2.班名改为合成联测修订班；3.学期名改为合成联测修订学期，日期不变；4.添加学生合成学生甲；5.添加学生合成学生丙；6.把合成学生丙改名为合成学生乙；7.创建任务合成联测回执；8.把任务合成联测回执改为合成联测核对回执；9.创建文档合成联测小结，正文为：本周收集回执，仍待核对。；10.给该文档追加正文：下周继续跟进。');
  for(let i=0;i<core.length;i++){
   if(i)result=await turn('',true);
   const [command,expected]=core[i];assert.equal(result.last.candidate?.command,command,JSON.stringify(rows.at(-1)));
   for(const [key,value]of Object.entries(expected))assert.equal(result.last.candidate[key],value,`${command} ${key}`);
   if(command.startsWith('document.')){assert(result.last.candidate.body.includes('本周收集回执'));if(command==='document.revise')assert(result.last.candidate.body.includes('下周继续跟进'));}
   await confirm(command);
  }
 }
 const context=(await read('/context')).data;assert.equal(context.name,scenario==='full-workbench'?'合成联测修订班':'合成联测班');
 result=await turn(`在${context.name}中，请按顺序完成以下六步：1.建立合成联测月考，科目数学，满分100；2.给合成学生甲录入这次考试80分；3.建立2排3座的座位表；4.把合成学生甲安排到1排1座；5.把合成学生乙安排到1排2座；6.交换合成学生甲和合成学生乙的座位。每次先准备下一步供我确认，已保存的步骤不要重复。`);
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
 async function classroomPages(){
  await page.getByLabel('更多功能',{exact:true}).click();await page.getByRole('button',{name:'成绩',exact:true}).click();
  const score=()=>page.getByRole('region',{name:'成绩表格',exact:true}).getByRole('row').filter({hasText:'合成学生甲'}).filter({hasText:'88.50'});
  await score().waitFor();await page.reload();await score().waitFor();
  await page.getByLabel('更多功能',{exact:true}).click();await page.getByRole('button',{name:'座位',exact:true}).click();
  await page.getByRole('button',{name:'1排2座 合成学生甲',exact:true}).waitFor();await page.getByRole('button',{name:'1排1座 合成学生乙',exact:true}).waitFor();
  await page.reload();await page.getByRole('button',{name:'1排2座 合成学生甲',exact:true}).waitFor();
 }
 await classroomPages();const chat=`/chats/${result.thread}`;
 async function corePages(){
  await page.getByRole('button',{name:'设置',exact:true}).click();const settings=page.getByRole('dialog',{name:'设置',exact:true});
  await settings.locator('p').getByText('合成联测修订班 · 合成联测修订学期',{exact:true}).waitFor();
  assert.equal(await settings.getByLabel('设置中切换班级',{exact:true}).locator('option:checked').innerText(),'合成联测修订班 · 合成联测修订学期');
  await settings.getByRole('button',{name:'关闭设置',exact:true}).click();
  await page.getByRole('button',{name:'学生',exact:true}).click();
  for(const name of ['合成学生甲','合成学生乙'])await page.getByRole('region',{name:'学生清单',exact:true}).getByRole('button',{name:new RegExp(name)}).waitFor();
  await page.reload();await page.getByRole('region',{name:'学生清单',exact:true}).getByRole('button',{name:/合成学生乙/}).waitFor();
  await page.getByRole('button',{name:'工作',exact:true}).click();await page.getByRole('main').getByRole('button',{name:/合成联测核对回执/}).waitFor();
  await page.reload();await page.getByRole('main').getByRole('button',{name:/合成联测核对回执/}).waitFor();
  await page.getByLabel('更多功能',{exact:true}).click();await page.getByRole('button',{name:'数据与内容',exact:true}).click();
  await page.getByRole('button',{name:/合成联测小结/}).first().click();await page.getByRole('button',{name:'原文',exact:true}).click();
  for(const text of ['本周收集回执','下周继续跟进'])assert((await page.locator('.document-text').innerText()).includes(text));
  await page.reload();await page.getByRole('button',{name:'原文',exact:true}).click();assert((await page.locator('.document-text').innerText()).includes('下周继续跟进'));
  rows.push({case:'original students/tasks/documents pages and refresh',passed:true});save();
 }
 if(scenario==='full-workbench')await corePages();
 const accepted=scenario==='full-workbench'?await world():null;
 await app.close();app=null;await launch();await page.goto(new URL(chat,page.url()).href);await page.getByLabel('输入消息').waitFor();
 scores=await read(`/classes/${context.class_id}/terms/${context.term_id}/exams/${exam.exam_id}`);assert.equal(scores.average,'88.50');
 assert.equal((await read(`/classes/${context.class_id}/terms/${context.term_id}/seating`)).layout.version,seats.version);
 const history=await read(`/workspace-chat/threads/${result.thread}`);assert(history.turns.some(t=>t.request_id===result.request&&t.assistant_text.includes('88.5')));
 if(scenario==='full-workbench'){assert.deepEqual(await world(),accepted,'Complete native/API restart must preserve every domain');await classroomPages();await corePages();}
 rows.push({case:'real native API restart, chat/grades/seats persisted',passed:true});assert.deepEqual(errors,[]);save();console.log('PASS real provider/native conversation/classroom chain');
}catch(error){rows.push({case:'failed',type:error.name,message:String(error.message).slice(0,1200)});save();if(page&&!page.isClosed())await page.screenshot({path:path.join(path.dirname(report),'failed.png')}).catch(()=>{});throw error;}finally{if(app)await app.close();}})().catch(e=>{console.error(e);process.exitCode=1;});
