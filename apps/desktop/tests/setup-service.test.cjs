const {test}=require('node:test');
const assert=require('node:assert/strict');
const {EventEmitter}=require('node:events');
const {PassThrough,Writable}=require('node:stream');
const {SetupPipe,validRequest}=require('../setup-service.cjs');
function fixture(timeout=1000){
  const child=new EventEmitter();child.stdout=new PassThrough();child.exitCode=null;child.killed=0;child.kill=()=>child.killed++;
  const sent=[];child.stdin=new Writable({write(chunk,_encoding,done){sent.push(JSON.parse(String(chunk)));done();}});
  return {child,sent,pipe:new SetupPipe(child,'a'.repeat(64),timeout)};
}
test('closed setup requests reject extra fields, bad types and arbitrary operations',()=>{
  for(const request of [null,[],{operation:'exec',command:'whoami'},{operation:'status',path:'elsewhere'},{operation:'create_owner',password:'short'},{operation:'approve_control',operation_id:'1',payload_hash:'a'.repeat(64),confirmed:true}])assert.equal(validRequest(request),false);
  assert.equal(validRequest({operation:'status'}),true);
  assert.equal(validRequest({operation:'create_owner',password:'synthetic-password-only'}),true);
});
test('developer identity pipe has a closed context and no renderer-selected paths',()=>{
  const context={operation:'development_reauthenticate',client:'a'.repeat(43),session:'b'.repeat(43),csrf:'c'.repeat(43)};
  assert.equal(validRequest(context),true);
  assert.equal(validRequest({...context,path:'elsewhere'}),false);
  assert.equal(validRequest({...context,session:2}),false);
  assert.equal(validRequest({...context,csrf:''}),false);
  assert.equal(validRequest({operation:'development_access',password:'synthetic-unregistered'}),false);
});
test('one request at a time; proof and credentials stay on the private pipe',async()=>{
  const {child,sent,pipe}=fixture();
  const reply=pipe.request({operation:'status'});
  await assert.rejects(pipe.request({operation:'status'}));
  assert.equal(sent[0].key,'a'.repeat(64));
  child.stdout.write(JSON.stringify({id:sent[0].id,ok:true,result:{owner_present:false,ready:false}})+'\n');
  assert.deepEqual(await reply,{owner_present:false,ready:false});pipe.stop();assert.equal(child.killed,1);
});
test('wrong response identity closes channel without retry or raw output',async()=>{
  const {child,pipe}=fixture();const reply=pipe.request({operation:'status'});
  child.stdout.write(JSON.stringify({id:'wrong',ok:false,code:'private-canary'})+'\n');
  await assert.rejects(reply,{message:'setup_not_completed'});assert.equal(child.killed,1);
});
test('absolute timeout closes worker and never replays request',async()=>{
  const {child,sent,pipe}=fixture(10);await assert.rejects(pipe.request({operation:'status'}));
  assert.equal(sent.length,1);assert.equal(child.killed,1);await assert.rejects(pipe.request({operation:'status'}));
});
test('oversized and malformed worker output fail closed',async()=>{
  for(const output of ['x'.repeat(16385),'invalid-json\n']){
    const {child,pipe}=fixture();const reply=pipe.request({operation:'status'});child.stdout.write(output);await assert.rejects(reply);assert.equal(child.killed,1);
  }
});
