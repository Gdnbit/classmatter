import {consumeEvents} from './client.mjs';
const token = JSON.parse(document.getElementById('config').textContent).token;
document.getElementById('config').remove();
const button = document.getElementById('run'), summary = document.getElementById('summary');
const results = document.getElementById('results'), live = document.getElementById('live');
const headers = {'Authorization':`Bearer ${token}`, 'Content-Type':'application/json'};
const assert = (condition, message) => {if (!condition) throw new Error(message);};
const status = async () => {
  const r = await fetch('/spike/status', {headers:{Authorization:headers.Authorization}, cache:'no-store'});
  assert(r.ok,'status_denied'); return r.json();
};
const request = (route_mode, user_text = 'synthetic', signal) => fetch('/spike/events', {
  method:'POST',headers,body:JSON.stringify({route_mode,user_text}),signal,cache:'no-store',
});
const show = e => {live.textContent += `\n${e.cursor} · ${e.type}`;};
async function run(route, text) {return consumeEvents(await request(route,text),show);}
async function until(predicate) {
  for(let i=0;i<50;i++) {const s = await status(); if(predicate(s)) return s;
    await new Promise(r=>setTimeout(r,20));}
  throw new Error('server_cleanup_timeout');
}

button.addEventListener('click',async()=>{
  button.disabled=true; results.replaceChildren(); live.textContent='SYNTHETIC ONLY'; summary.textContent='运行中';
  let passed=0;
  async function check(name, action) {
    const row=document.createElement('li'); row.textContent=`运行：${name}`; results.append(row);
    await action(); row.textContent=`PASS · ${name}`; passed++;
  }
  try {
    await check('首事件早于模型完成，中文 UTF-8 保持完整', async()=>{
      const controller=new AbortController();
      let resolve; const first = new Promise(r=>{resolve=r;});
      const pending=consumeEvents(await request('answer_only','synthetic:slow',controller.signal),e=>{show(e);resolve(e);});
      const settled=pending.then(events=>({events}),error=>({error}));
      try {
        const e=await Promise.race([first,settled.then(r=>{throw r.error ?? new Error('missing_first_event');})]);
        const s=await status();
        assert(s.active_streams>0 && !s.outcomes.some(r=>r.run_id===e.run_id),'buffered_until_done');
        await until(s=>s.models.active>0 && !s.outcomes.some(r=>r.run_id===e.run_id));
        const result=await settled; if(result.error) throw result.error;
        assert(result.events.find(e=>e.type==='message.delta')?.payload.text==='合成 🧪 中文','unicode_corrupted');
      } finally {controller.abort(); await settled;}
    });
    await check('只读查询带来源，终态成功',async()=>{
      const events=await run('read');
      assert(events.at(-1).type==='run.completed','read_failed');
      assert(events.find(e=>e.type==='message.delta')?.payload.source_refs.includes('synthetic-record@v1'),'missing_source');
    });
    await check('草稿仅为未提交候选',async()=>{
      const events=await run('draft_write');
      assert(events.find(e=>e.type==='draft.available')?.payload.draft.committed===false,'draft_committed');
    });
    await check('无来源回答失败，不显示编造成功',async()=>{
      const events=await run('read','synthetic:ungrounded');
      assert(events.at(-1).type==='run.failed' && !events.some(e=>e.type==='message.delta'),'ungrounded_answer');
    });
    await check('模型超时显示失败',async()=>{
      const events=await run('answer_only','synthetic:timeout');
      assert(events.at(-1).type==='run.failed' && events.at(-1).payload.code==='timeout','timeout_hidden');
    });
    await check('AbortController 断连，服务器取消并清理',async()=>{
      const controller=new AbortController(); let resolve;
      const first=new Promise(r=>{resolve=r;});
      const pending=consumeEvents(await request('answer_only','synthetic:cancel',controller.signal),e=>{show(e);resolve(e);});
      // Attach rejection handler before abort; never allow an unhandled rejection.
      const settled=pending.then(()=>({unexpected:true}),e=>({error:e.name}));
      const e=await Promise.race([first,settled.then(()=>{throw new Error('missing_first_event');})]);
      await until(s=>s.models.active>0); controller.abort();
      assert(!(await settled).unexpected,'abort_ignored');
      await until(s=>s.active_streams===0 && s.models.active===0 && s.outcomes.some(r=>r.run_id===e.run_id && r.outcome==='cancelled'));
    });
    await check('缺 capability 与篡改 workspace 拒绝',async()=>{
      const denied=await fetch('/spike/events',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
      assert(denied.status===403,'missing_token_accepted');
      const forged=await fetch('/spike/events',{method:'POST',headers,
        body:JSON.stringify({user_text:'synthetic',route_mode:'read',workspace_id:'other'})});
      assert(forged.status===400,'forged_scope_accepted');
    });
    await check('服务器无残留运行，业务写入为零',async()=>{
      const s=await until(s=>s.active_streams===0 && s.models.active===0);
      assert(s.synthetic_only && s.business_writes===0,'business_write_detected');
    });
    summary.textContent=`PASS · ${passed}/8 · TCP/browser synthetic only · 零业务写入`;
  } catch(error) {summary.textContent=`FAIL · ${passed}/8 · ${error.message}`;}
  finally {button.disabled=false;}
});
