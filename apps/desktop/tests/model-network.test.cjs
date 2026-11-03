const test=require('node:test'),assert=require('node:assert/strict');
const {validateNetwork,parseLaunchArguments,networkFromSwitches,electronArguments}=require('../model-network.cjs');
const google='https://generativelanguage.googleapis.com/v1beta/openai/';
const zhipu='https://open.bigmodel.cn/api/paas/v4/';
test('default launch is offline and has no credentials, model or provider activation',()=>{
  const result=parseLaunchArguments([]);
  assert.equal(result.profile,'r1');assert.deepEqual(result.network,{bases:[],proxy:null});
  assert.deepEqual(electronArguments(result.network),[]);
  assert.deepEqual(networkFromSwitches(undefined,undefined),result.network);
});
test('explicit R1/D1 options roundtrip through bounded Electron switches',()=>{
  const result=parseLaunchArguments(['--profile','conversation-d1','--model-api-base-url',google,'--model-api-base-url',zhipu,'--model-api-proxy','http://127.0.0.1:7890']);
  assert.equal(result.profile,'conversation-d1');
  const args=electronArguments(result.network);
  assert.deepEqual(args,['--classmatter-model-api-bases='+google+','+zhipu,'--classmatter-model-api-proxy=http://127.0.0.1:7890']);
  assert.deepEqual(networkFromSwitches(google+','+zhipu,'http://127.0.0.1:7890'),result.network);
  assert.ok(Object.isFrozen(result.network)&&Object.isFrozen(result.network.bases));
});
test('ambiguous or credential-bearing endpoints are refused without echo',()=>{
  for(const value of ['https://user:synthetic-private-canary@127.0.0.1/v1','https://provider.invalid/v1?api_key=synthetic-private-canary',
    'https://provider.invalid/v1#fragment','https://provider.invalid/a/../v1','https://provider.invalid/%61','https://provider.invalid//v1',
    'http://remote.invalid/v1','http://localhost:8000/v1','http://127.0.0.1:0/v1','http://127.1:8000/v1','https://PROVIDER.invalid/v1',
    'https://provider.invalid/v1\n','https://provider.invalid/v1?',google+',',google+'x'.repeat(512),'file:///tmp/key']) {
    assert.throws(()=>parseLaunchArguments(['--model-api-base-url',value]),error=>!String(error).includes(value));
  }
});
test('unknown flags, duplicate permission and nonloopback proxy fail closed',()=>{
  for(const args of [['--api-key','synthetic-private-canary'],['--profile','unknown'],['--profile','r1','--profile','conversation-d1'],
    ['--model-api-base-url',google,'--model-api-base-url',google],['--model-api-base-url'],['--model-api-proxy','http://127.0.0.1:7890'],
    ['--model-api-base-url',google,'--model-api-proxy','http://remote.invalid:7890'],
    ['--model-api-base-url',google,'--model-api-proxy','http://127.0.0.1:07890'],
    ['--model-api-base-url',google,'--model-api-proxy','http://127.0.0.1:65536'],
    ['--model-api-base-url',google,'--model-api-proxy','http://127.0.0.1:7890','--model-api-proxy','http://127.0.0.1:7891']])assert.throws(()=>parseLaunchArguments(args));
  assert.throws(()=>networkFromSwitches('',undefined));assert.throws(()=>networkFromSwitches(google, ''));
  assert.throws(()=>networkFromSwitches('x'.repeat(2052),undefined));
  assert.throws(()=>validateNetwork({bases:[google],proxy:null,api_key:'synthetic-private-canary'}));
});
test('caller mutation cannot widen the captured launch permissions',()=>{
  const original={bases:[google],proxy:null},snapshot=validateNetwork(original);
  original.bases.push(zhipu);original.proxy='http://remote.invalid:7890';
  assert.deepEqual(snapshot,{bases:[google],proxy:null});
});
