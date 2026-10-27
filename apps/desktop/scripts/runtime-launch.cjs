const {spawn}=require('node:child_process');
const path=require('node:path');
const fs=require('node:fs');
const {prerequisites}=require('../runtime-check.cjs');
const args=process.argv.slice(2);
if(args.length && (args.length!==2 || args[0]!=='--profile' || args[1]!=='conversation-d1'))throw new Error('Unknown profile arguments');
const d1=args.length===2;
const stage=path.resolve(__dirname,d1?'../.build/runtime-d1':'../.build/runtime');
const repositoryRoot=path.resolve(__dirname,'../../..');
const report=prerequisites(repositoryRoot,process.platform,d1?'conversation-d1':'r1');
if(!report.prerequisites_present) {
  console.error(JSON.stringify(report));
  console.error('真实桌面前置条件未齐。请按桌面 README 的 next_steps 对照表处理；未初始化、迁移、启动数据库或设置 Owner，也不会退回 Demo。');
  process.exit(2);
}
const source=JSON.parse(fs.readFileSync(path.join(stage,'runtime-source.json'),'utf8'));
if(typeof source.repositoryRoot!=='string' || path.resolve(source.repositoryRoot)!==repositoryRoot || typeof source.runtimeRoot!=='string' || path.resolve(source.runtimeRoot)!==path.join(repositoryRoot,d1?'.local-runtime/synthetic-conversation-d1':'.local-runtime/synthetic-v1')) {
  console.error('Rebuild the runtime before launch; an integration fixture descriptor is not a user profile.');process.exit(1);
}
const env={...process.env};delete env.ELECTRON_RUN_AS_NODE;
const child=spawn(require('electron'),[stage],{stdio:'ignore',env,windowsHide:true});
child.on('error',()=>{console.error('Desktop runtime could not start.');process.exitCode=1;});
child.on('exit',code=>{process.exitCode=code||0;});
