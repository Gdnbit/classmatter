// Explicit real-model acceptance; same native UI and APIs, isolated synthetic DB.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
if(process.env.CLASSMATTER_RUN_LIVE_CLASSROOM!=='1')throw Error('Explicit live synthetic opt-in required');
const stage=process.env.CLASSMATTER_LIVE_STAGE,report=process.env.CLASSMATTER_LIVE_REPORT;
const model=process.env.CLASSMATTER_LIVE_MODEL||'gemini-3.1-flash-lite';
const attempts=Number(process.env.CLASSMATTER_LIVE_ATTEMPTS||'1');
const turnInterval=Number(process.env.CLASSMATTER_LIVE_TURN_INTERVAL||'0');
if(![0,15,65].includes(turnInterval))throw Error('Bounded explicit test pacing required');
const scenario=process.env.CLASSMATTER_LIVE_SCENARIO||'classroom';
if(!['classroom','classroom-documents','classroom-recovery','full-workbench','daily-work','daily-work-recovery','daily-work-waiting-recovery'].includes(scenario))throw Error('Explicit supported scenario required');
const recovery=scenario==='classroom-recovery',resumeThread=process.env.CLASSMATTER_LIVE_THREAD;
const dailyRecovery=scenario==='daily-work-recovery';
const waitingRecovery=scenario==='daily-work-waiting-recovery',priorRecoveryFailures=[];
if((recovery||dailyRecovery||waitingRecovery)&&!/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/.test(resumeThread||''))throw Error('Explicit synthetic recovery thread required');
const verifyWorld=scenario!=='classroom';
if(![1,2,3].includes(attempts))throw Error('Bounded explicit test attempts required');
if(!['gemini-3.1-flash-lite','glm-4-flash-250414','glm-4.7-flash'].includes(model))throw Error('Explicit approved free model required');
if(!stage||!report||!path.isAbsolute(stage)||!path.isAbsolute(report))throw Error('Explicit isolated stage/report required');
const {_electron:electron}=require('playwright-core');
let app,page,lastResult,recoveredLayout=false,recoveredSeating=false;const rows=[],errors=[];
function save(){fs.writeFileSync(report,JSON.stringify({live:true,model,scenario,resumed_isolated_fixture:process.env.CLASSMATTER_LIVE_RESUMED==='1',test_attempt_limit:attempts,test_turn_interval_seconds:turnInterval,rows,errors},null,2));}
async function closeOwnedApp(){
 const owned=app;app=null;if(!owned)return;const child=owned.process();let timer;
 try{await Promise.race([owned.close(),new Promise((_,reject)=>{timer=setTimeout(()=>reject(Error('Owned fixture close timeout')),10000);})]);}
 catch(error){if(child&&child.exitCode===null)child.kill();throw error;}finally{clearTimeout(timer);}
}
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
  window.__liveToolEvents={};window.__livePreviews={};const original=window.fetch.bind(window);
  window.fetch=async(...args)=>{const response=await original(...args);const url=new URL(response.url);
   if(/\/turns\/[^/]+\/events$/.test(url.pathname)){
    const request=url.pathname.split('/').at(-2);
    void response.clone().text().then(text=>{window.__liveToolEvents[request]=text.split('\n').filter(line=>line.startsWith('data:')).map(line=>JSON.parse(line.slice(5))).filter(event=>event.type==='tool.started').map(event=>event.payload.tool);}).catch(()=>{window.__liveToolEvents[request]=null;});
   }
   if(/\/turns\/[^/]+\/proposal$/.test(url.pathname)&&response.ok){const request=url.pathname.split('/').at(-2);void response.clone().json().then(value=>{window.__livePreviews[request]=value;}).catch(()=>{window.__livePreviews[request]=null;});}
   return response;
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
 const activity=(await read('/conversation-d1'+base+'/activity')).data;
 const tasks=activity.tasks.map(({task_id,title,status,version,evidence,source_record_id})=>({task_id,title,status,version,evidence,source_record_id}));
 const docs=(await read(base+'/documents')).data,documents=[];
 for(const doc of docs){const d=(await read(base+'/documents/'+doc.document_id)).data;documents.push({document_id:d.document_id,title:d.title,body:d.body,format:d.format,status:d.status,version:d.version});}
 const exams=(await read(base+'/exams')).exams,results=[];
 for(const exam of exams)results.push(await read(base+'/exams/'+exam.exam_id));
 return {context,term,students,tasks,records:activity.records,documents,exams,results,seating:(await read(base+'/seating')).layout};
}
function assertSaved(candidate,before,after,receipt){
 const c=candidate,cmd=c.command;
 if(cmd==='class.create'){assert.equal(after.context.class_id,c.class_id);assert.equal(after.context.term_id,c.term_id);assert.equal(after.context.name,c.name);assert.equal(after.term.name,c.term_name);}
 if(cmd==='class.update')assert.equal(after.context.name,c.name);
 if(cmd==='term.update'){assert.equal(after.term.name,c.name);assert.equal(after.term.start_date,c.start_date);assert.equal(after.term.end_date,c.end_date);}
 if(cmd.startsWith('student.')){const student=after.students.find(s=>s.student_id===c.student_id);assert(student);assert.equal(student.name,c.name);assert.equal(student.version,receipt.version);assert.equal(after.students.length,before.students.length+(cmd==='student.create'?1:0));}
 if(cmd==='record.create'){const record=after.records.find(r=>r.record_id===c.record_id);assert(record);assert.equal(record.fact_text,c.fact_text);assert.equal(record.student_id,c.student_id);assert.equal(record.version,receipt.version);assert.equal(after.records.length,before.records.length+1);}
 if(cmd.startsWith('task.')){const task=after.tasks.find(t=>t.task_id===c.task_id);assert(task);assert.equal(task.title,c.title??before.tasks.find(t=>t.task_id===c.task_id).title);assert.equal(task.version,receipt.version);if(c.status)assert.equal(task.status,c.status);if(c.evidence!==undefined)assert.equal(task.evidence,c.evidence);assert.equal(after.tasks.length,before.tasks.length+(cmd==='task.create'?1:0));}
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
 const target=hasComparison?comparison.getByLabel(/^(待确认的结果|已保存的结果)$/):dialog;
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
 const labels={name:'名称',term_name:'学期',start_date:'开始日期',end_date:'结束日期',title:'标题',body:'正文',fact_text:'事实',evidence:'跟进记录',reason:hasComparison?'更正原因':'原因',subject:'科目',...(!hasComparison?{rows:'排数',columns:'每排座位数',row:'目标排',column:'目标座位',first_row:'原座位排',first_column:'原座位号',second_row:'目标排',second_column:'目标座位号'}:{})};
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
async function turn(text,continuation=false,attempt=1,retryExisting=false){
 if(turnInterval)await new Promise(resolve=>setTimeout(resolve,turnInterval*1000));
 const before=verifyWorld?await world():null;
 const start=Date.now();
 const [response]=await Promise.all([
  page.waitForResponse(r=>r.request().method()==='POST'&&/\/workspace-chat\/threads\/[^/]+\/turns$/.test(new URL(r.url()).pathname)),
  (async()=>{if(attempt>1||retryExisting){await page.getByLabel('输入消息').fill('合成重试保留的未发送草稿');await page.getByRole('region',{name:'已保存的对话'}).getByRole('button',{name:'重试回复',exact:true}).click();}
   else if(continuation)await page.getByRole('button',{name:'继续任务',exact:true}).last().click();
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
 rows.push({thread_id:thread,request_id:request,prompt:text||'continue',attempt,retry_existing_failure:retryExisting,state:last.state,candidate:last.candidate?.command??null,answer:last.assistant_text,tools,input_tokens:last.input_tokens,output_tokens:last.output_tokens,ms:Date.now()-start});save();
 await page.waitForURL(url=>url.pathname===`/chats/${thread}`);
 await page.waitForFunction(()=>!document.querySelector('[aria-label="停止回复"]'));
 if(attempt>1||retryExisting){assert.equal(await page.getByLabel('输入消息').inputValue(),'合成重试保留的未发送草稿');await page.getByLabel('输入消息').fill('');rows.push({case:'explicit retry retained unsent draft',passed:true});save();}
 if(last.state==='failed'&&attempt<attempts){
  assert.equal(last.candidate,null);assert.equal(last.action_receipt,null);
  // Explicit user retry uses the original UI, a new request in this conversation.
  // Never replay a commit, clear failures or automatically retry in production.
  await new Promise(resolve=>setTimeout(resolve,2000));return turn(text||'继续完成上面的任务，只处理尚未完成的步骤。',false,attempt+1);
 }
 assert.equal(last.state,'completed',JSON.stringify(rows.at(-1)));assert(last.input_tokens>0&&last.output_tokens>0,'Real provider usage required');
 console.log(JSON.stringify(rows.at(-1)));lastResult={last,thread,request,before};return lastResult;
}
async function confirm(command){
 assert.equal(lastResult.last.candidate?.command,command);
 const card=page.getByRole('region',{name:'对话中的操作候选'}).last();
 if(verifyWorld){assert.deepEqual(await world(),lastResult.before,'Preparation must not change business state');await page.reload();await card.getByRole('button',{name:'预览这项操作',exact:true}).waitFor();assert.deepEqual(await world(),lastResult.before,'Refreshing a candidate must not save it');await assertDialog(lastResult.last.candidate,lastResult.before,card);}
 const [preview]=await Promise.all([page.waitForResponse(r=>r.request().method()==='POST'&&/\/turns\/[^/]+\/proposal$/.test(new URL(r.url()).pathname)),card.getByRole('button',{name:'预览这项操作',exact:true}).click()]);
 assert.equal(preview.status(),200);await page.waitForFunction(id=>Object.hasOwn(window.__livePreviews,id),lastResult.request);
 const captured=await page.evaluate(id=>window.__livePreviews[id],lastResult.request);
 assert(captured,'Actual proposal response must be captured');assert.deepEqual(captured.payload,lastResult.last.candidate,'Dialog proposal must equal the durable candidate');
 const dialog=page.getByRole('dialog');await dialog.getByRole('button',{name:/^(确认提交|明确批准并提交)$/}).waitFor();assert.equal(await dialog.locator('input,textarea,select').count(),0);
 if(verifyWorld){await assertDialog(lastResult.last.candidate,lastResult.before,dialog);assert.deepEqual(await world(),lastResult.before,'Preview must not save business data');await page.screenshot({path:path.join(path.dirname(report),`${rows.filter(r=>r.case==='confirmed').length+1}-${command}.png`)});}
 await dialog.getByRole('button',{name:/^(确认提交|明确批准并提交)$/}).click();await dialog.waitFor({state:'hidden'});
 await card.getByRole('status').filter({hasText:'已保存'}).waitFor();
 if(verifyWorld){
  const saved=await read(`/workspace-chat/threads/${lastResult.thread}`),turn=saved.turns.find(t=>t.request_id===lastResult.request);assert(turn.action_receipt,'Actual saved receipt required');
  assert(turn.change_preview,'Every new action needs a factual comparison');assert.deepEqual(turn.change_preview,lastResult.last.change_preview,'Confirmation cannot change frozen preview');
  const after=await world();assertSaved(lastResult.last.candidate,lastResult.before,after,turn.action_receipt);
  await page.reload();await card.getByRole('status').filter({hasText:'已保存'}).waitFor();assert.deepEqual(await world(),after,'Reloaded world must equal the committed state');await assertDialog(lastResult.last.candidate,lastResult.before,card);
 }
 rows.push({case:'confirmed',command});save();
}
(async()=>{try{
 await launch();
 let result;
 if(recovery){
  await page.goto(new URL(`/chats/${resumeThread}`,page.url()).href);await page.getByLabel('输入消息').waitFor();
  const history=await read(`/workspace-chat/threads/${resumeThread}`),initial=await world();
  assert.equal(history.thread.status,'active');assert.equal(history.next_before,null,'Recovery must inspect the full original thread');
  assert(initial.documents.length===1&&initial.exams.length===1,'No extra document/exam may be overwritten');
  assert.deepEqual(initial.students.map(s=>s.name).sort(),['合成学生乙','合成学生甲'].sort());
  const committed=history.turns.filter(t=>t.action_receipt);
  assert([4,5,8].includes(committed.length),'Only explicit pre-seating, empty-layout or completed-seating checkpoints may resume');
  assert.deepEqual(committed.map(t=>t.candidate.command),['document.create','document.revise','exam.create','score.record','seat.layout.create','seat.assign','seat.assign','seat.swap'].slice(0,committed.length));
  recoveredLayout=committed.length>=5;recoveredSeating=committed.length===8;
  if(recoveredLayout){
   assert(initial.seating);assert.equal(initial.seating.rows,2);assert.equal(initial.seating.columns,3);assert.equal(initial.seating.seats.length,6);
   assert.equal(initial.seating.layout_id,committed[4].action_receipt.resource_id);assert.equal(initial.seating.version,committed.at(-1).action_receipt.version);
   if(recoveredSeating){
    const frozen=committed[7].change_preview.after_seats;assert(frozen);
    for(const cell of initial.seating.seats)assert.equal(cell.student_id,frozen.cells.find(s=>s.row===cell.row_index&&s.column===cell.column_index).student_id);
    for(const [name,column]of [['合成学生甲',2],['合成学生乙',1]])assert.equal(initial.seating.seats.find(s=>s.row_index===1&&s.column_index===column).student_id,initial.students.find(s=>s.name===name).student_id);
    const failed=history.turns.slice(-3);assert(failed.every(t=>t.state==='failed'&&t.candidate===null&&t.action_receipt===null&&t.user_text==='继续完成上面的任务，只处理尚未完成的步骤。'));
    rows.push({case:'prior terminal reply still failed; not promoted to success',failed_requests:failed.map(t=>t.request_id),prior_failure:true});
   }else assert(initial.seating.seats.every(s=>s.student_id===null));
  }else assert.equal(initial.seating,null);
  assert(history.turns.every(t=>!t.candidate||t.action_receipt),'An unconfirmed candidate must be handled before recovery');
  for(const row of committed){assert(row.change_preview);assert.equal(row.candidate.class_id,initial.context.class_id);assert.equal(row.candidate.term_id,initial.context.term_id);}
  const doc=initial.documents[0],exam=initial.exams[0],student=initial.students.find(s=>s.name==='合成学生甲');
  assert.equal(doc.title,'合成联测小结');assert.equal(doc.body,committed[1].candidate.body);assert.equal(doc.document_id,committed[1].action_receipt.resource_id);assert.equal(doc.version,committed[1].action_receipt.version);
  for(const text of ['本周收集回执','下周继续跟进'])assert(doc.body.includes(text));
  assert.equal(exam.title,'合成联测月考');assert.equal(exam.subject,'数学');assert.equal(Number(exam.maximum_score),100);assert.equal(exam.exam_id,committed[2].action_receipt.resource_id);
  const score=initial.results[0].results.find(s=>s.student_id===student.student_id);assert.equal(score.score,'80.00');assert.equal(score.version,committed[3].action_receipt.version);assert.equal(committed[3].candidate.exam_id,exam.exam_id);assert.equal(committed[3].candidate.student_id,student.student_id);
  rows.push({case:'same-thread prior receipts and current document/80-score verified; no reset',thread_id:resumeThread,prior_commands:committed.map(t=>t.candidate.command),passed:true});save();
 }else if(dailyRecovery){
  await page.goto(new URL(`/chats/${resumeThread}`,page.url()).href);await page.getByLabel('输入消息').waitFor();
  const history=await read(`/workspace-chat/threads/${resumeThread}`),initial=await world();
  assert.equal(history.thread.status,'active');assert.equal(history.next_before,null);
  assert.equal(initial.records.length,1);assert.equal(initial.tasks.length,0);assert.equal(initial.documents.length,0);assert.equal(initial.exams.length,0);assert.equal(initial.seating,null);
  const committed=history.turns.filter(t=>t.action_receipt);assert.equal(committed.length,1);assert.equal(committed[0].candidate.command,'record.create');assert.equal(committed[0].action_receipt.resource_id,initial.records[0].record_id);
  const last=history.turns.at(-1);assert.equal(last.user_text,'继续完成上面的任务，只处理尚未完成的步骤。');
  if(last.state==='completed'){
   assert.equal(last.candidate?.command,'task.create');assert.equal(last.candidate.title,'合成作品核对');assert.equal(last.candidate.source_record_id,initial.records[0].record_id);assert.equal(last.candidate.student_id,initial.records[0].student_id);assert.equal(last.action_receipt,null);
   assert(last.input_tokens>0&&last.output_tokens>0,'The resumed candidate must retain real provider usage');
   lastResult={thread:resumeThread,last,request:last.request_id,before:initial};result=lastResult;
  }else assert.equal(last.state,'failed');
  rows.push({case:'same original fact/receipt and failed continuation preserved; no reset',prior_failure:true,thread_id:resumeThread,failed_requests:history.turns.filter(t=>t.state==='failed').map(t=>t.request_id),passed:true});save();
 }else if(waitingRecovery){
  await page.goto(new URL(`/chats/${resumeThread}`,page.url()).href);await page.getByLabel('输入消息').waitFor();
  const history=await read(`/workspace-chat/threads/${resumeThread}`),initial=await world();
  assert.equal(history.thread.status,'active');assert.equal(history.next_before,null);
  assert.equal(initial.records.length,1);assert.equal(initial.tasks.length,1);assert.equal(initial.documents.length,0);assert.equal(initial.exams.length,0);assert.equal(initial.seating,null);
  const task=initial.tasks[0];assert.equal(task.title,'合成作品核对');assert.equal(task.status,'not-started');assert.equal(task.version,1);assert.equal(task.evidence,'');assert.equal(task.source_record_id,initial.records[0].record_id);
  const committed=history.turns.filter(t=>t.action_receipt);assert.deepEqual(committed.map(t=>t.candidate.command),['record.create','task.create']);
  assert.equal(committed[0].action_receipt.resource_id,initial.records[0].record_id);assert.equal(committed[1].action_receipt.resource_id,task.task_id);
  assert.equal(committed[0].action_receipt.version,1);assert.equal(committed[1].action_receipt.version,1);
  assert(!history.turns.some(t=>['queued','running','unknown'].includes(t.state)||t.candidate&&!t.action_receipt));
  const last=history.turns.at(-1);assert.equal(last.state,'failed');assert.equal(last.candidate,null);assert.equal(last.action_receipt,null);
  assert.equal(last.user_text,'合成作品核对先等待，跟进记录原文为“班长正在收集”');
  priorRecoveryFailures.push(...history.turns.filter(t=>t.state==='failed').map(t=>t.request_id));
  rows.push({case:'same original fact/task v1 and all failed waiting attempts verified; no reset',prior_failure:true,failed_requests:[...priorRecoveryFailures],passed:true});save();
 }else{
  await page.getByRole('button',{name:'新对话',exact:true}).click();
  result=await turn('这是合成测试，只回复：准备好了。');assert.equal(result.last.candidate,null);assert.deepEqual(rows.filter(row=>row.request_id).at(-1).tools,[]);
 }
 if(scenario==='daily-work'||dailyRecovery||waitingRecovery){
  const fact='合成学生甲交来展示作品',title='合成作品核对';
  const note=`刚刚${fact}，记下来，再根据这条记录建立名为“${title}”的任务。今晚我还要整理自己的书架。每次只准备下一步，先让我确认。`;
  if(!dailyRecovery&&!waitingRecovery){
   result=await turn(note);
   if(!result.last.candidate&&['要记录哪位学生的哪件事？','这件事是什么时候发生的？'].includes(result.last.assistant_text)){
    rows.push({case:'necessary explicit fact clarification',passed:true});save();
    result=await turn(`学生是合成学生甲。事实原文为“${fact}”，刚刚发生。先记录这条事实，再根据这条记录建立名为“${title}”的任务；不要把个人随记写入。`);
   }
   assert.equal(result.last.candidate?.command,'record.create');assert(note.includes(result.last.candidate.fact_text)&&result.last.candidate.fact_text.includes('交来展示作品'));assert(!result.last.candidate.fact_text.includes('书架'));assert.equal(result.last.candidate.student_id,(await world()).students.find(s=>s.name==='合成学生甲').student_id);await confirm('record.create');
  }
  if(!waitingRecovery){
   if(!dailyRecovery||!result?.last?.candidate)result=dailyRecovery?await turn('继续完成上面的任务，只处理尚未完成的步骤。',false,1,true):await turn('',true);
   assert.equal(result.last.candidate?.command,'task.create');assert.equal(result.last.candidate.title,title);
   assert.equal(result.last.candidate.source_record_id,(await world()).records[0].record_id);await confirm('task.create');
  }
  for(const [message,command,status,evidence]of [
   [`${title}先等待，跟进记录原文为“班长正在收集”`,'task.update','waiting','班长正在收集'],
   [`结束${title}，实际结果原文为“班长交齐，我已核对”`,'task.complete','done','班长交齐，我已核对'],
  ]){result=await turn(message);assert.equal(result.last.candidate?.command,command);assert.equal(result.last.candidate.status,status);assert.equal(result.last.candidate.evidence,evidence);await confirm(command);}
  result=await turn('根据刚才已保存的普通事实和任务，生成文档合成工作小结，引用事实原文、实际来源和结果；个人书架随记不写进班级小结。');
  assert.equal(result.last.candidate?.command,'document.create');assert.equal(result.last.candidate.title,'合成工作小结');
  const body=result.last.candidate.body;assert(body.includes('合成学生甲')&&body.includes('交来展示作品')&&body.includes('班长交齐')&&!body.includes('书架'));
  const tools=rows.filter(row=>row.request_id).at(-1).tools;assert(tools.includes('read_class_records')&&tools.includes('read_class_work'));
  await confirm('document.create');
  const accepted=await world();assert.equal(accepted.records.length,1);assert.equal(accepted.tasks.length,1);assert.equal(accepted.tasks[0].status,'done');assert.equal(accepted.tasks[0].version,3);assert.equal(accepted.documents.length,1);
  const chat=page.url(),thread=result.thread;
  await closeOwnedApp();await launch();await page.goto(chat);await page.getByLabel('输入消息').waitFor();
  assert.deepEqual(await world(),accepted,'Daily work persists across complete native/API restart');
  const history=await read(`/workspace-chat/threads/${thread}`);assert.equal(history.turns.filter(t=>t.action_receipt).length,5);
  const failed=rows.filter(row=>row.request_id&&row.state==='failed');
  for(const row of failed){const stored=history.turns.find(turn=>turn.request_id===row.request_id);assert.equal(stored?.state,'failed','A successful retry/restart must retain the original failed turn');assert.equal(stored.candidate,null);assert.equal(stored.action_receipt,null);}
  for(const request of priorRecoveryFailures){const stored=history.turns.find(turn=>turn.request_id===request);assert.equal(stored?.state,'failed');assert.equal(stored.candidate,null);assert.equal(stored.action_receipt,null);}
  if(waitingRecovery)rows.push({case:'all prior failed waiting attempts retained after complete restart',count:priorRecoveryFailures.length,passed:true});
  rows.push({case:'failed turns retained after restart',count:new Set([...failed.map(row=>row.request_id),...priorRecoveryFailures]).size,passed:true});
  rows.push({case:'fact→linked followup→waiting→end→sourced summary and complete restart',passed:true});assert.deepEqual(errors,[]);save();return;
 }
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
 const context=(await read('/context')).data;
 if(scenario==='classroom-documents'||recovery)assert(['合成联测班','合成联测修订班'].includes(context.name));
 else assert.equal(context.name,scenario==='full-workbench'?'合成联测修订班':'合成联测班');
 if(scenario==='classroom-documents'){
  const initial=await world();assert.deepEqual(initial.documents,[]);assert.deepEqual(initial.exams,[]);assert.equal(initial.seating,null);
  assert.deepEqual(initial.students.map(s=>s.name).sort(),['合成学生乙','合成学生甲'].sort());
  rows.push({case:'existing synthetic class/students; documents/exams/seating initially empty',passed:true});save();
  result=await turn('请按顺序完成两步，每次只准备下一步让我预览确认：1.创建文档合成联测小结，正文为：本周收集回执，仍待核对。；2.给这份文档追加正文：下周继续跟进。已保存的步骤不要重复。');
  for(const command of ['document.create','document.revise']){
   if(command==='document.revise')result=await turn('',true);
   assert.equal(result.last.candidate?.command,command,JSON.stringify(rows.at(-1)));
   assert.equal(result.last.candidate.title,'合成联测小结');assert(result.last.candidate.body.includes('本周收集回执'));
   if(command==='document.revise')assert(result.last.candidate.body.includes('下周继续跟进'));
   assert(rows.filter(r=>r.request_id).at(-1).tools.includes('prepare_document'));
   await confirm(command);
  }
 }
 if(!recoveredSeating)result=await turn(recovery?'继续完成上面的任务，只处理尚未完成的步骤。':`在${context.name}中，请按顺序完成以下六步：1.建立合成联测月考，科目数学，满分100；2.给合成学生甲录入这次考试80分；3.建立2排3座的座位表；4.把合成学生甲安排到1排1座；5.把合成学生乙安排到1排2座；6.交换合成学生甲和合成学生乙的座位。每次先准备下一步供我确认，已保存的步骤不要重复。`);
 const steps=recoveredSeating?[]:recovery?(recoveredLayout?['seat.assign','seat.assign','seat.swap']:['seat.layout.create','seat.assign','seat.assign','seat.swap']):['exam.create','score.record','seat.layout.create','seat.assign','seat.assign','seat.swap'];
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
 if(!recoveredSeating){result=await turn('',true);assert.equal(result.last.candidate,null,'Completed plan must not repeat a write');}
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
 async function documentPage(){
  await page.getByLabel('更多功能',{exact:true}).click();await page.getByRole('button',{name:'数据与内容',exact:true}).click();
  await page.getByRole('button',{name:/合成联测小结/}).first().click();await page.getByRole('button',{name:'原文',exact:true}).click();
  for(const text of ['本周收集回执','下周继续跟进'])assert((await page.locator('.document-text').innerText()).includes(text));
  await page.reload();await page.getByRole('button',{name:'原文',exact:true}).click();assert((await page.locator('.document-text').innerText()).includes('下周继续跟进'));
 }
 if(scenario==='full-workbench')await corePages();
 if(scenario==='classroom-documents'||recovery)await documentPage();
 const accepted=verifyWorld?await world():null;
 await closeOwnedApp();await launch();await page.goto(new URL(chat,page.url()).href);await page.getByLabel('输入消息').waitFor();
 scores=await read(`/classes/${context.class_id}/terms/${context.term_id}/exams/${exam.exam_id}`);assert.equal(scores.average,'88.50');
 assert.equal((await read(`/classes/${context.class_id}/terms/${context.term_id}/seating`)).layout.version,seats.version);
 const history=await read(`/workspace-chat/threads/${result.thread}`);assert(history.turns.some(t=>t.request_id===result.request&&t.assistant_text.includes('88.5')));
 if(verifyWorld){assert.deepEqual(await world(),accepted,'Complete native/API restart must preserve every domain');await classroomPages();if(scenario==='full-workbench')await corePages();else await documentPage();}
 rows.push({case:'real native API restart, chat/grades/seats persisted',passed:true});assert.deepEqual(errors,[]);save();console.log(recoveredSeating?'PASS remaining business operations; prior failed terminal replies retained':'PASS real provider/native conversation/classroom chain');
}catch(error){rows.push({case:'failed',type:error.name,message:String(error.message).slice(0,1200)});save();if(page&&!page.isClosed())await page.screenshot({path:path.join(path.dirname(report),'failed.png')}).catch(()=>{});throw error;}finally{await closeOwnedApp().catch(error=>{rows.push({case:'owned fixture cleanup failed',type:error.name});save();process.exitCode=1;});}})().catch(e=>{console.error(e);process.exitCode=1;});
