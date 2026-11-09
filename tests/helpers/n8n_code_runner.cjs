// Pure Code-node evaluation; HTTP helpers are injected synthetic responses only.
// This is not an n8n engine emulator or a live transport.
const fs=require('node:fs'),path=require('node:path');
const root=path.resolve(__dirname,'../..');
const AsyncFunction=Object.getPrototypeOf(async function(){}).constructor;
const payload=JSON.parse(fs.readFileSync(0,'utf8'));
const results=[],store={};
(async()=>{
 for(const step of payload){
  if(step.static) Object.assign(store,JSON.parse(JSON.stringify(step.static)));   // optional seed of workflow static data
  const workflows=JSON.parse(fs.readFileSync(path.join(root,'infra/n8n/workflows',step.file),'utf8'));
  const n=workflows[0].nodes.find(n=>n.name===step.node);
  let calls=0,now=step.clock_ms??Date.now();const requests=[];
  const Clock=step.clock_ms===undefined?Date:class extends Date {constructor(...args){super(...(args.length?args:[now]));}static now(){return now;}};
  const sleep=step.clock_ms===undefined?setTimeout:(fn,ms)=>{now+=ms;fn();};
  const context={helpers:{httpRequest:async options=>{
   if(step.responses){
    const spec=step.responses[calls++];requests.push({url:options.url,timeout:options.timeout});
    if(!spec)throw Error('SYNTHETIC_SEQUENCE_EXHAUSTED');
    now+=spec.delay_ms||0;
    if(spec.error)throw Object.assign(new Error(spec.error.message||'synthetic'),{code:spec.error.code,name:spec.error.name||'Error'});
    return spec.response;
   }
   if(!step.http) throw Error('REAL_HTTP_FORBIDDEN');
   calls++;return step.http;
  }}};
  try {
   const output=await new AsyncFunction('$input','$execution','$','$getWorkflowStaticData','Date','setTimeout',n.parameters.jsCode).call(context,
    {first:()=>({json:step.input})},{id:step.execution_id||'synthetic-exec-1026'},
    name=>({first:()=>({json:step.prior?.[name]})}),()=>store,Clock,sleep);
   if(step.responses && calls>step.responses.length)throw Error('SYNTHETIC_SEQUENCE_EXHAUSTED');
   results.push({output:output[0].json,http_calls:calls,...(step.responses?{requests}: {})});
  }catch(e){results.push({error:e.message,http_calls:calls});}
 }
 process.stdout.write(JSON.stringify(results));
})().catch(e=>{process.stderr.write(e.stack);process.exitCode=1;});
