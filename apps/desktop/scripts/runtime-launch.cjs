const {spawn}=require('node:child_process');
const path=require('node:path');
const fs=require('node:fs');
const {prerequisites}=require('../runtime-check.cjs');
const stage=path.resolve(__dirname,'../.build/runtime');
const repositoryRoot=path.resolve(__dirname,'../../..');
const report=prerequisites(repositoryRoot);
if(!report.prerequisites_present) {
  console.error(JSON.stringify(report));
  console.error('真实桌面前置条件未齐。请按桌面 README 的 next_steps 对照表处理；未初始化、迁移、启动数据库或设置 Owner，也不会退回 Demo。');
  process.exit(2);
}
const source=JSON.parse(fs.readFileSync(path.join(stage,'runtime-source.json'),'utf8'));
if(typeof source.repositoryRoot!=='string' || path.resolve(source.repositoryRoot)!==repositoryRoot || typeof source.runtimeRoot!=='string' || path.resolve(source.runtimeRoot)!==path.join(repositoryRoot,'.local-runtime/synthetic-v1')) {
  console.error('Rebuild the runtime before launch; an integration fixture descriptor is not a user profile.');process.exit(1);
}
const env={...process.env};delete env.ELECTRON_RUN_AS_NODE;
const child=spawn(require('electron'),[stage],{stdio:'ignore',env,windowsHide:true});
child.on('error',()=>{console.error('Desktop runtime could not start.');process.exitCode=1;});
child.on('exit',code=>{process.exitCode=code||0;});
