import assert from 'node:assert/strict';
import test from 'node:test';
import {consumeEvents} from './client.mjs';

test('real loopback TCP: early event, grounding, abort and zero write', async () => {
  const origin=process.env.CLASS_OS_SPIKE_ORIGIN;
  assert.match(origin ?? '',/^http:\/\/127\.0\.0\.1:\d+$/);
  const page=await (await fetch(`${origin}/spike`)).text();
  const token=JSON.parse(page.match(/id="config">([^<]+)<\/script>/)[1]).token;
  const headers={Authorization:`Bearer ${token}`,'Content-Type':'application/json',Origin:origin};
  const status=async()=> (await fetch(`${origin}/spike/status`,{headers})).json();
  const send=(route_mode,user_text,signal)=>fetch(`${origin}/spike/events`,{
    method:'POST',headers,body:JSON.stringify({route_mode,user_text}),signal,
  });
  let first;
  const early=new Promise(r=>{first=r;});
  const pending=consumeEvents(await send('answer_only','synthetic:slow'),e=>first(e));
  const firstEvent=await early;
  let earlyState=await status();
  assert.equal(earlyState.active_streams,1);
  assert(!earlyState.outcomes.some(r=>r.run_id===firstEvent.run_id));
  for(let i=0;i<50 && !earlyState.models.active;i++) {
    await new Promise(r=>setTimeout(r,20)); earlyState=await status();
  }
  assert.equal(earlyState.models.active,1);
  assert(!earlyState.outcomes.some(r=>r.run_id===firstEvent.run_id));
  assert.equal((await pending).at(-1).type,'run.completed');
  const read=await consumeEvents(await send('read','synthetic'),()=>{});
  assert.deepEqual(read.find(e=>e.type==='message.delta').payload.source_refs,['synthetic-record@v1']);
  const controller=new AbortController(); let observed;
  const started=new Promise(r=>{observed=r;});
  const reading=consumeEvents(await send('answer_only','synthetic:cancel',controller.signal),e=>observed(e));
  const settled=reading.then(()=>false,()=>true);
  const e=await started;
  for(let i=0;i<50 && !(await status()).models.active;i++) await new Promise(r=>setTimeout(r,20));
  controller.abort(); assert.equal(await settled,true);
  let state;
  for(let i=0;i<50;i++) {
    state=await status();
    if(state.outcomes.some(r=>r.run_id===e.run_id && r.outcome==='cancelled')) break;
    await new Promise(r=>setTimeout(r,20));
  }
  assert(state.outcomes.some(r=>r.run_id===e.run_id && r.outcome==='cancelled'));
  assert.equal(state.models.active,0); assert.equal(state.active_streams,0);
  assert.equal(state.business_writes,0);
});
