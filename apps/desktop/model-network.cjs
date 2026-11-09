// Trusted operator startup options only. Never read renderer data or API keys.
const fail=()=>{throw new Error('Invalid desktop model transport options');};
function baseURL(value) {
  if(typeof value!=='string'||value.length<1||value.length>512||!/^[\x21-\x7e]+$/.test(value)||/[?#\\]/.test(value))return false;
  try {
    const url=new URL(value);
    return (url.protocol==='https:'||(url.protocol==='http:'&&url.hostname==='127.0.0.1'))
      && !url.username&&!url.password&&!url.search&&!url.hash
      && (!url.port||(Number(url.port)>=1&&Number(url.port)<=65535))
      && /^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)*$/.test(url.hostname)
      && /^(?:\/[A-Za-z0-9_-]+)*\/?$/.test(url.pathname)
      && (value===url.href||value+'/'===url.href);
  } catch{return false;}
}
function validateNetwork(value={bases:[],proxy:null}) {
  if(!value||typeof value!=='object'||Object.keys(value).sort().join(',')!=='bases,proxy'
    ||!Array.isArray(value.bases)||value.bases.length>4||new Set(value.bases).size!==value.bases.length
    ||value.bases.some(url=>!baseURL(url)))fail();
  if(value.proxy!==null) {
    const match=typeof value.proxy==='string'&&/^http:\/\/127\.0\.0\.1:([1-9][0-9]{0,4})$/.exec(value.proxy);
    if(!match||Number(match[1])>65535||!value.bases.length)fail();
  }
  return Object.freeze({bases:Object.freeze([...value.bases]),proxy:value.proxy});
}
function parseLaunchArguments(args) {
  if(!Array.isArray(args)||args.length>12||args.some(x=>typeof x!=='string'))fail();
  let profile='r1',seenProfile=false,proxy=null;const bases=[];
  for(let index=0;index<args.length;index+=2) {
    const flag=args[index],value=args[index+1];
    if(typeof value!=='string')fail();
    if(flag==='--profile'&&!seenProfile&&['r1','conversation-d1','workspace-chat-d3','classroom-work-d4'].includes(value)){profile=value;seenProfile=true;}
    else if(flag==='--model-api-base-url'){bases.push(value);}
    else if(flag==='--model-api-proxy'&&proxy===null){proxy=value;}
    else fail();
  }
  return {profile,network:validateNetwork({bases,proxy})};
}
function networkFromSwitches(bases,proxy) {
  if(bases!==undefined&&(typeof bases!=='string'||bases.length>2051))fail();
  return validateNetwork({bases:bases===undefined?[]:bases.split(','),proxy:proxy===undefined?null:proxy});
}
function electronArguments(value) {
  const network=validateNetwork(value),args=[];
  if(network.bases.length)args.push('--classmatter-model-api-bases='+network.bases.join(','));
  if(network.proxy!==null)args.push('--classmatter-model-api-proxy='+network.proxy);
  return args;
}
module.exports={validateNetwork,parseLaunchArguments,networkFromSwitches,electronArguments};
