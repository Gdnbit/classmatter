const test=require('node:test');
const assert=require('node:assert/strict');
const {spawnSync}=require('node:child_process');
const path=require('node:path');

test('live chat acceptance refuses default invocation before launching Electron or a model',()=>{
  const env={...process.env};delete env.CLASSMATTER_RUN_LIVE_CHAT_ACCEPTANCE;
  const result=spawnSync(process.execPath,[path.join(__dirname,'live-chat-acceptance.cjs')],{env,encoding:'utf8',timeout:5000,windowsHide:true});
  assert.notEqual(result.status,0);
  assert.equal(result.stdout,'');
  assert.match(result.stderr,/Explicit live synthetic acceptance opt-in required/);
});
