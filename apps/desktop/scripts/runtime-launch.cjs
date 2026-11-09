const {spawn}=require('node:child_process');
const path=require('node:path');
const fs=require('node:fs');
const {prerequisites}=require('../runtime-check.cjs');
const {parseLaunchArguments,electronArguments}=require('../model-network.cjs');
const args=process.argv.slice(2),development=args.includes('--development-no-password');
if(args.filter(value=>value==='--development-no-password').length>1)throw new Error('Duplicate development switch');
const options=parseLaunchArguments(args.filter(value=>value!=='--development-no-password'));
const d1=options.profile!=='r1';
if(development&&!d1)throw new Error('Development identity requires the synthetic D1 profile');
const stage=path.resolve(__dirname,options.profile==='classroom-work-d4'?'../.build/runtime-d4':options.profile==='workspace-chat-d3'?'../.build/runtime-d3':d1?'../.build/runtime-d1':'../.build/runtime');
const repositoryRoot=path.resolve(__dirname,'../../..');
const report=prerequisites(repositoryRoot,process.platform,options.profile);
if(!report.prerequisites_present) {
  console.error(JSON.stringify(report));
  console.error('真实桌面前置条件未齐。请按桌面 README 的 next_steps 对照表处理；未初始化、迁移、启动数据库或设置 Owner，也不会退回 Demo。');
  process.exit(2);
}
const source=JSON.parse(fs.readFileSync(path.join(stage,'runtime-source.json'),'utf8'));
if(options.network.bases.length&&!fs.existsSync(path.join(stage,'model-network.cjs'))) {
  console.error('Rebuild the runtime before using explicit model transport options.');process.exit(1);
}
if(typeof source.repositoryRoot!=='string' || path.resolve(source.repositoryRoot)!==repositoryRoot || typeof source.runtimeRoot!=='string' || path.resolve(source.runtimeRoot)!==path.join(repositoryRoot,d1?'.local-runtime/synthetic-conversation-d1':'.local-runtime/synthetic-v1')) {
  console.error('Rebuild the runtime before launch; an integration fixture descriptor is not a user profile.');process.exit(1);
}
const env={...process.env};delete env.ELECTRON_RUN_AS_NODE;
// This child is the user-requested GUI, not a background helper. SW_HIDE can
// suppress the first native show even though its API and renderer are ready.
const child=spawn(require('electron'),[stage,...electronArguments(options.network),...(development?['--classmatter-development-no-password']:[])],{stdio:'ignore',env,windowsHide:false});
child.on('error',()=>{console.error('Desktop runtime could not start.');process.exitCode=1;});
child.on('exit',code=>{process.exitCode=code||0;});
