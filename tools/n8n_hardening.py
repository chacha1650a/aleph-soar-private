"""Final source for C/D ticket guards and evidence semantics (home candidate).

Called by gen_n8n_stage2 after its layout pass. No network or target execution.
The builder always emits inactive workflows with dry_run=true.
"""
import json
from s12_health import RECOVER

COMMON = r"""
const validText = v => typeof v === 'string' && v.length > 0 && v.length <= 300 && !/[\x00-\x1f\x7f]/.test(v);
const ticketId = v => typeof v === 'string' && /^T-\d{8}-\d{4}$/.test(v);
const states = ['open','responding','verified','restored','closed'];
const canon = a => a.via === 'pfsense' && a.action === 'fw_block' ? 'block' : a.action;
const same = (a,b) => a.bot === b.bot && a.via === b.via && canon(a) === canon(b) && a.target === b.target;
const refOK = (a, dry=false) => a && typeof a.bot === 'string' && /^(\d{3}|manual)$/.test(a.bot) && ['portal','pfsense','wazuh-ar','manual'].includes(a.via) && typeof a.action === 'string' && /^[a-z][a-z_]{1,31}$/.test(a.action) && validText(a.target) && (a.result === undefined || ['applied','already_applied'].includes(a.result) || (dry && a.result === 'dry_run'));
const held = (ctx,code) => [{json:{ok:false,no_action:true,verdict:code,ctx}}];
const snapshotOK = j => j.ok === true && typeof j.exists === 'boolean' && Array.isArray(j.actions) && j.actions.every(a=>refOK(a,!!j.ctx?.cfg?.dry_run) && (['applied','already_applied'].includes(a.result) || (j.ctx?.cfg?.dry_run && a.result==='dry_run'))) && (j.exists ? ticketId(j.ticket_id) && states.includes(j.status) : j.ticket_id === null && j.status === null && j.actions.length === 0);
"""

DEDUP = COMMON + r"""
const j = $input.first().json, x = j.ctx;
if (!snapshotOK(j)) return held(x,'held_ticket_check');
if (j.exists && (j.status==='closed' || j.status==='restored' && j.actions.length)) return held(x,'held_ticket_cycle');
const expected = x.expected || [{bot:'112',via:'portal',action:'block',target:x.src_ip}];
// dry_run 기록은 30분 안의 것만 처리됨으로 센다(시각이 없거나 오래된 시험 기록이 그 출발지를 영구히 막지 않게).
const DRY_DEDUP_MS = 30 * 60 * 1000;
const fresh = a => { const t = Date.parse(a.finished_at || a.requested_at || ''); const age = Date.now() - t; return Number.isFinite(t) && age >= 0 && age < DRY_DEDUP_MS; };
const done = s => j.actions.some(a => same(a,s) && (['applied','already_applied'].includes(a.result) || (x.cfg.dry_run && a.result === 'dry_run' && fresh(a))));
if (j.exists && expected.length && expected.every(done)) return [{json:{ok:true,no_action:true,verdict:'duplicate_no_action',ticket_id:j.ticket_id,event_id:x.event_id,case_id:x.case_id}}];
return [{json:{ok:true,proceed:true,ctx:{...x,existing_ticket:j.ticket_id,new_round_required:j.exists && j.status==='restored'}}}];
"""

CLASSIFY = COMMON + r"""
const j=$input.first().json, prev=$('저장소 요청 만들기').first().json, ctx=prev.ctx;
const status=j.statusCode ?? null, b=j.body;
if (status === null || status >= 500) return [{json:{ok:false,retry:RETRY,ctx,error:{code:status===null?'NETWORK':'SERVER_ERROR',message:'ticket store unavailable'}}}];
if (![200,201].includes(status)) return [{json:{ok:false,retry:false,ctx,error:{code:b?.error?.code || 'HTTP_ERROR',message:'ticket request rejected'}}}];
if (!b || b.ok !== true) return held(ctx,'held_invalid_ticket_response');
if (prev.mode === 'active') {
  const r=prev.resource;
  if (!b.resource || Object.keys(b.resource).length!==4 || !['asset_id','via','action','target'].every(k=>b.resource[k]===r[k]) || !Array.isArray(b.tickets) || !b.tickets.every(t=>ticketId(t.ticket_id) && ['A','B','C','D'].includes(t.seat) && states.includes(t.status) && Array.isArray(t.active_actions) && t.active_actions.length>0 && t.active_actions.every(a=>refOK(a) && a.via===r.via && canon(a)===r.action && a.target===r.target))) return held(ctx,'held_invalid_resource_response');
  return [{json:{ok:true,mode:'active',resource:b.resource,tickets:b.tickets,ctx}}];
}
if (prev.mode === 'check') {
  if (['target','all_seats'].includes(prev.query_scope)) {
    const target = prev.query_scope === 'target' ? prev.target : null;
    if ((target !== null && !validText(target)) || !Array.isArray(b.tickets) || !b.tickets.every(t =>
      ticketId(t.ticket_id) && ['A','B','C','D'].includes(t.seat) && states.includes(t.status) &&
      Array.isArray(t.active_actions) && (target === null || t.active_actions.length > 0) &&
      t.active_actions.every(a => refOK(a) && (target === null || a.target === target)))) return held(ctx,'held_invalid_ticket_list');
    return [{json:{ok:true,mode:'check',tickets:b.tickets.map(t => ({...t,
      active_actions:t.active_actions.map(a => ({...a,action:canon(a)}))})),ctx}}];
  }
  const result={ok:true,mode:'check',exists:b.exists,ticket_id:b.ticket_id,status:b.status,actions:b.applied_actions,ctx};
  if (!snapshotOK(result)) return held(ctx,'held_invalid_ticket_response');
  result.actions=result.actions.map(a=>({...a,action:canon(a)}));
  return [{json:result}];
}
if (!ticketId(b.ticket_id) || !states.includes(b.status) || typeof b.created!=='boolean' || typeof b.duplicate!=='boolean') return held(ctx,'held_invalid_record_response');
return [{json:{ok:true,mode:'record',ticket_id:b.ticket_id,status:b.status,created:b.created,duplicate:b.duplicate,ctx}}];
"""

PICK = COMMON + r"""
const j=$input.first().json,x=j.ctx;
if (!snapshotOK(j)) return held(x,'held_ticket_check');
if (!j.exists) return [{json:{ok:true,no_action:true,verdict:'no_open_ticket'}}];
const actions=j.actions.map(a=>({...a,action:canon(a)}));
if (['restored','closed'].includes(j.status) && actions.length) return held(x,'held_inconsistent_ticket_cycle');
const selected=actions.filter(a=>a.bot==='112' && a.action==='block' && ['portal','pfsense'].includes(a.via));
const ips=[...new Set(selected.map(a=>a.target))];
if (!ips.length) return [{json:{ok:true,no_action:true,verdict:'nothing_to_release',ticket_id:j.ticket_id}}];
if (ips.length!==1) return held(x,'held_multiple_targets');
const resources=[...new Set(selected.map(a=>a.via))].sort().map(via=>({asset_id:x.asset_id,via,action:'block',target:ips[0]}));
return [{json:{ok:true,mode:'active',resource:resources[0],ctx:{...x,ticket_id:j.ticket_id,ip:ips[0],resources,resource_index:0,hasFw:selected.some(a=>a.via==='pfsense'),hasApp:selected.some(a=>a.via==='portal'),manual_required:actions.filter(a=>!selected.includes(a)).map(a=>`${a.bot}:${a.via}:${a.action}:${a.target}`)}}}];
"""

HOLD = COMMON + r"""
const j=$input.first().json,x=j.ctx,r=x.resources[x.resource_index];
if (j.ok!==true || !j.resource || !['asset_id','via','action','target'].every(k=>j.resource[k]===r[k]) || !Array.isArray(j.tickets) || !j.tickets.every(t=>ticketId(t.ticket_id) && states.includes(t.status) && Array.isArray(t.active_actions) && t.active_actions.length>0 && t.active_actions.every(a=>refOK(a,!!x.cfg.dry_run) && a.via===r.via && canon(a)===r.action && a.target===r.target))) return held(x,'held_resource_check');
if (!j.tickets.some(t=>t.ticket_id===x.ticket_id && t.active_actions.some(a=>a.bot==='112'))) return held(x,'held_own_claim_missing');
const others=j.tickets.filter(t=>t.ticket_id!==x.ticket_id || t.active_actions.some(a=>a.bot!=='112'));
if (others.length) return [{json:{ok:true,no_action:true,verdict:'held_other_resource_ticket',other_tickets:others.map(t=>t.ticket_id),ctx:x}}];
const next=x.resource_index+1;
if (next<x.resources.length) return [{json:{ok:true,more_resources:true,mode:'active',resource:x.resources[next],ctx:{...x,resource_index:next}}}];
return [{json:{ok:true,proceed:true,more_resources:false,ctx:x}}];
"""

CURRENT_REQUEST = COMMON + r"""
const r=$input.first().json,x=r.ctx;
if(r.ok!==true || !ticketId(r.ticket_id) || !['open','responding','verified'].includes(r.status)) throw new Error('TICKET_RECORD_REQUIRED');
const seat=x?.seat||x?.cfg?.seat,group=x?.group_key||x?.src_ip;
if(!['A','B','C','D'].includes(seat) || !validText(group)) throw new Error('TICKET_CURRENT_REQUIRED');
return [{json:{mode:'check',seat,group_key:group,ctx:{...x,record_ack:{ticket_id:r.ticket_id,created:r.created,duplicate:r.duplicate,status:r.status}}}}];
"""

CURRENT_COMPARE = COMMON + r"""
const j=$input.first().json,x=j.ctx,a=x?.record_ack;
if(!snapshotOK(j) || !j.exists || !a || j.ticket_id!==a.ticket_id || !['open','responding','verified'].includes(j.status)) throw new Error('TICKET_CURRENT_REQUIRED');
const {record_ack,...ctx}=x;
return [{json:{...a,ok:true,status:j.status,ticket_current:true,ctx}}];
"""


# Synthetic state only. C remains authoritative for live records.
PLACEHOLDER = COMMON + r"""
const b=$input.first().json,ctx=b.ctx,sd=$getWorkflowStaticData('global');
const out=o=>[{json:{...o,ctx}}],fail=(code,message)=>out({ok:false,error:{code,message}});
const tickets=Object.values(sd.tickets||{});
const released=a=>({...a,action:({unblock:'block',unlock:'lock',restore:'quarantine'})[a.action]||a.action});
const activeOf=t=>{
 const active=new Map(),key=a=>JSON.stringify([a.bot,a.via,canon(a),a.target]);
 for(const a of t.actions) {
  if(a.duplicate) continue;
  if(['applied','already_applied','dry_run'].includes(a.result)) active.set(key(a),a);
  else if(a.result==='released') active.delete(key(released(a)));
 }
 return [...active.values()];
};
if(b.mode==='active') {
 const r=b.resource;
 if(!r || !['asset_id','via','action','target'].every(k=>validText(r[k]))) return fail('VALIDATION_ERROR','invalid resource');
 return out({ok:true,resource:r,tickets:tickets.filter(t=>t.asset_id===r.asset_id).map(t=>({...t,active_actions:activeOf(t).filter(a=>a.via===r.via && canon(a)===r.action && a.target===r.target)})).filter(t=>t.active_actions.length).map(t=>({seat:t.seat,ticket_id:t.ticket_id,status:t.status,active_actions:t.active_actions}))});
}
if(b.mode==='check' && ((b.target && !b.group_key) || !b.seat && validText(b.group_key))) {
 const target=b.target && !b.group_key?b.target:null;
 if(target!==null && !validText(target)) return fail('VALIDATION_ERROR','invalid target');
 const list=tickets.filter(t=>target!==null || t.group_key===b.group_key && t.status!=='closed')
   .map(t=>({seat:t.seat,ticket_id:t.ticket_id,status:t.status,
     active_actions:activeOf(t).filter(a=>target===null || a.target===target)}))
   .filter(t=>target===null || t.active_actions.length);
 return out({ok:true,mode:'check',tickets:list});
}
if(!['check','record'].includes(b.mode) || !['A','B','C','D'].includes(b.seat) || !validText(b.group_key)) return fail('VALIDATION_ERROR','invalid mode/seat/group');
// 실제 조치(applied/already_applied)가 없고 마지막 기록이 30분보다 오래된 티켓은 끝난 시험 기록으로 보고 열린 티켓으로 쓰지 않는다(데이터는 그대로 둔다).
const STALE_DRY_MS=30*60*1000;
const lastAt=t=>Math.max(Date.parse(t.created_at)||0,...(t.actions||[]).map(a=>Date.parse(a.recorded_at||a.finished_at||a.requested_at)||0));
const staleDry=t=>!(t.actions||[]).some(a=>['applied','already_applied'].includes(a.result)) && Date.now()-lastAt(t)>=STALE_DRY_MS;
const open=tickets.find(t=>t.seat===b.seat && t.group_key===b.group_key && t.status!=='closed' && !staleDry(t));
if(b.mode==='check') return out({ok:true,mode:'check',exists:!!open,ticket_id:open?.ticket_id||null,status:open?.status||null,actions:open?activeOf(open):[]});
if(!['detected','applied','effect','released'].includes(b.stage) || !validText(b.asset_id) || !Array.isArray(b.event_ids) || !b.event_ids.length || !b.event_ids.every(validText)) return fail('VALIDATION_ERROR','invalid record');
const stable=v=>Array.isArray(v)?v.map(stable):v && typeof v==='object'?Object.fromEntries(Object.keys(v).sort().map(k=>[k,stable(v[k])])):v;
const fingerprint=JSON.stringify(stable(Object.fromEntries(Object.entries(b).filter(([k])=>!['ctx','real','idempotency_key'].includes(k)))));
const prev=(sd.idem||{})[b.idempotency_key];
if(prev) return prev.fingerprint===fingerprint?out(prev.response):fail('IDEMPOTENCY_CONFLICT','key reused with different body');
const finish=res=>{
 sd.idem=sd.idem||{};
 if(b.idempotency_key) sd.idem[b.idempotency_key]={fingerprint,response:res};
 return out(res);
};
if(open && open.asset_id!==b.asset_id) return fail('INVALID_TRANSITION','asset_id differs from existing ticket');
if(['detected','applied'].includes(b.stage)) {
 const owners=tickets.filter(t=>t.seat===b.seat && t.group_key===b.group_key && t.event_ids.some(e=>b.event_ids.includes(e)));
 const holder=owners.find(t=>t.ticket_id!==open?.ticket_id)||owners[0];
 if(holder && (!open || holder.ticket_id!==open.ticket_id || open.status==='restored')) return finish({ok:true,mode:'record',ticket_id:holder.ticket_id,created:false,duplicate:true,status:holder.status});
}
const a=b.action||{},now=new Date().toISOString();
const starts=open?.status==='restored' && (b.stage==='detected' || b.stage==='applied' && ['applied','already_applied','dry_run'].includes(a.result));
if(starts && activeOf(open).length) return fail('INVALID_TRANSITION','restored ticket still has active actions');
let t=open && !starts?JSON.parse(JSON.stringify(open)):null,created=!t,duplicate=false;
if(!t) {
 if(['effect','released'].includes(b.stage)) return fail('VALIDATION_ERROR','no active action');
 t={ticket_id:`T-${now.slice(0,10).replace(/-/g,'')}-${String((sd.seq||0)+1).padStart(4,'0')}`,seat:b.seat,case_id:b.case_id,group_key:b.group_key,title:b.title,asset_id:b.asset_id,event_ids:[],status:'open',actions:[],created_at:now};
}
const active=activeOf(t),line=active.find(x=>same(x,a));
if(b.stage!=='detected') {
 if(!refOK(a,true) && a.result!=='released' && !['failed','rejected','skipped'].includes(a.result)) return fail('VALIDATION_ERROR','invalid action');
 if(b.stage==='effect') {
  if(!line) return fail('VALIDATION_ERROR','no matching active action');
  const since=Date.parse(line.finished_at||line.requested_at||line.recorded_at);
  const at=Date.parse(a.effect_verified_at);
  if(!Number.isFinite(at)) return fail('VALIDATION_ERROR','invalid effect time');
  if(at<since) return fail('STALE_EFFECT','effect predates active action');
  line.effect_verified=a.effect_verified;line.effect_verified_at=a.effect_verified_at;
  if(a.effect_verified===true && t.status==='responding') t.status='verified';
 } else {
  if(a.result==='released' && !active.some(x=>same(x,released(a)))) return fail('VALIDATION_ERROR','no matching active action');
  duplicate=b.stage==='applied' && ['applied','already_applied','dry_run'].includes(a.result) && !!line;
  t.actions.push({...a,recorded_at:now,duplicate});
  if(['applied','already_applied','dry_run'].includes(a.result) && t.status==='open') t.status='responding';
  if(a.result==='released' && ['responding','verified'].includes(t.status) && !activeOf(t).length) t.status='restored';
 }
}
for(const e of b.event_ids) if(!t.event_ids.includes(e)) t.event_ids.push(e);
if(starts) {open.status='closed';open.closed_at=now;open.close_note=`재차단: 새 회차로 분리 (${t.ticket_id})`;}
sd.tickets=sd.tickets||{};sd.tickets[t.ticket_id]=t;
if(created) sd.seq=(sd.seq||0)+1;
return finish({ok:true,mode:'record',ticket_id:t.ticket_id,created,duplicate,status:t.status});
"""


def harden(folder):
    def read(name):
        return json.loads((folder / name).read_text(encoding="utf-8"))[0]

    def node(w, name):
        return next(n for n in w["nodes"] if n["name"] == name)

    def script(w, name, js):
        node(w, name)["parameters"]["jsCode"] = js

    def write(name, w):
        (folder / name).write_text(json.dumps([w], ensure_ascii=False, indent=1)+"\n", encoding="utf-8", newline="\n")

    mains = ["haedam-20-s12-main.json", "haedam-30-s1-main.json", "haedam-31-s4-main.json", "haedam-32-s8-s10-main.json", "haedam-33-s7-main.json"]
    for name in mains:
        w = read(name)
        script(w, "중복 판정", DEDUP)
        for n in w["nodes"]:
            js=n["parameters"].get("jsCode")
            if not js:
                continue
            js=js.replace("? v : null;", "&& Number.isFinite(Date.parse(v)) ? v : null;")
            js=js.replace("condition_met_at: iso(t.condition_met_at), received_at:", "condition_met_at: iso(t.condition_met_at), detected_at: iso(t.detected_at), received_at:")
            js=js.replace("detected_at: new Date().toISOString(), received_at: x.times", "detected_at: x.times ? x.times.detected_at : null, received_at: x.times")
            js=js.replace("action: 'fw_block'", "action: 'block'")
            if name == "haedam-33-s7-main.json":
                js=js.replace("target: group", "target: t.file_key").replace("target: x.group_key", "target: x.file_key")
            if n["name"] in ("차단 입력", "알림 입력") or n["name"].startswith("조치") and "입력 (" in n["name"]:
                js="const record=$input.first().json;\nif (record.ok !== true || !record.ticket_id || !['open','responding','verified'].includes(record.status) || record.ctx?.new_round_required && record.ticket_id===record.ctx.existing_ticket) throw new Error('TICKET_RECORD_REQUIRED');\n"+js
                if "입력 (" in n["name"]:
                    js="if (($input.first().json.ctx?.results || []).some(s=>['failed','rejected'].includes(s.result))) throw new Error('PREVIOUS_ACTION_FAILED');\n"+js
            n["parameters"]["jsCode"]=js
        # Final results must retain a failed response/record, including S12's effect branch.
        final=node(w,"최종 응답")
        final["parameters"]["jsCode"]=final["parameters"]["jsCode"].replace("ok: true, verdict: 'responded'", "ok: !(x.results || [x.block]).filter(Boolean).some(s=>['failed','rejected'].includes(s.result)) && (x.ticket || x.record)?.ok === true, verdict: x.cfg.dry_run ? 'dry_run' : 'responded'")
        if name == "haedam-20-s12-main.json":
            script(w,"회복 확인",RECOVER)
        # An idempotent ACK can describe a ticket closed since the original call.
        # Read the current grouping immediately before every target action.
        from gen_n8n_workflows import code, execwf
        targets=[n for n in w['nodes'] if n['name']=='차단 입력'
                 or n['name'].startswith('조치') and '입력 (' in n['name']]
        for i,target in enumerate(targets,1):
            request_name=f'조치 전 티켓 조회 입력 {i}'
            check_name=f'조치 전 티켓 조회 {i}'
            compare_name=f'조치 전 티켓 대조 {i}'
            for connection in w['connections'].values():
                for branch in connection['main']:
                    for edge in branch:
                        if edge['node']==target['name']:
                            edge['node']=request_name
            px,py=target['position']
            w['nodes'] += [code(request_name,CURRENT_REQUEST,[px-180,py-420]),
                           execwf(check_name,'haedamResultLog01',[px+60,py-420]),
                           code(compare_name,CURRENT_COMPARE,[px+300,py-420])]
            for source,dest in [(request_name,check_name),(check_name,compare_name),(compare_name,target['name'])]:
                w['connections'][source]={'main':[[{'node':dest,'type':'main','index':0}]]}
            record_guard="throw new Error('TICKET_RECORD_REQUIRED');\n"
            assert record_guard in target['parameters']['jsCode']
            target['parameters']['jsCode'] = target['parameters']['jsCode'].replace(
                record_guard,record_guard+"if (record.ticket_current !== true) throw new Error('TICKET_CURRENT_REQUIRED');\n",1)
        write(name,w)

    name="haedam-10-result-log.json"
    w=read(name)
    route=node(w,"저장소 요청 만들기")["parameters"]["jsCode"]
    route=route.replace("if (b.mode === 'check') {", "if (b.mode === 'active') {\n const r=b.resource;\n if (!r || !['asset_id','via','action','target'].every(k=>typeof r[k]==='string' && r[k].length>0)) return [{json:{ok:false,no_action:true,real:false,ctx,error:{code:'INVALID_RESOURCE'}}}];\n const query=['asset_id','via','action','target'].map(k=>k+'='+encodeURIComponent(r[k])).join('&');\n return [{json:{real:true,mode:'active',method:'GET',url:base+'/active?'+query,idem:'',body:null,resource:r,ctx}}];\n}\nif (b.mode === 'check') {",1)
    script(w,"저장소 요청 만들기",route)
    for i in (1,2):
        script(w,f"응답 변환 {i}",CLASSIFY.replace("RETRY", "true" if i==1 else "false"))
    for n in w["nodes"]:
        if n["type"]=="n8n-nodes-base.httpRequest":
            n["retryOnFail"]=False
            n.pop("maxTries",None)
            n.pop("waitBetweenTries",None)
    ph = PLACEHOLDER
    script(w,"check/record (자리표시 저장소)",ph)
    write(name,w)

    name="haedam-50-release.json"
    w=read(name)
    s=node(w,"승인 확인·티켓 조회 입력")["parameters"]["jsCode"]
    s=s.replace("const CFG = { dry_run: true };", "const CFG = { dry_run: true, live_release_enabled: false };")
    s=s.replace("const need =", "if (!CFG.dry_run && !CFG.live_release_enabled) return [{json:{ok:false,stop:true,no_action:true,verdict:'held_live_release_not_accepted'}}];\nconst need =")
    script(w,"승인 확인·티켓 조회 입력",s)
    script(w,"해제 대상 고르기",PICK)
    script(w,"보류 판정",HOLD)
    # Reuse the existing IF node for the per-resource query loop.
    from gen_n8n_workflows import if_bool
    w["nodes"].append(if_bool("다음 자원 조회?","$json.more_resources === true",[1800,-260]))
    def connect(source,branches):
        w["connections"][source]={"main":[[{"node":target,"type":"main","index":0} for target in branch] for branch in branches]}
    connect("보류 판정",[["다음 자원 조회?"]])
    connect("다음 자원 조회?",[["다른 자리 티켓 조회 (haedam-10 check)"],["보류 아님?"]])
    for n in w["nodes"]:
        js=n["parameters"].get("jsCode")
        if not js:
            continue
        if n["name"].startswith("해제") and "입력 (" in n["name"]:
            js="if ($input.first().json.ok !== true) throw new Error('RELEASE_RECORD_REQUIRED');\n"+js
        if n["name"].endswith("기록 입력"):
            js=js.replace("action: 'fw_block'", "action: 'unblock'").replace("action: 'block'", "action: 'unblock'")
            js=js.replace("const ok =", "if (r.applied_verified === false) throw new Error('RELEASE_STATE_MISMATCH');\nconst ok =")
        if n["name"]=="알림 입력":
            js="if ($input.first().json.ok !== true) throw new Error('RELEASE_RECORD_REQUIRED');\n"+js
        if n["name"]=="최종 응답":
            js=js.replace("verdict: 'released'", "verdict: x.cfg.dry_run ? 'dry_run' : 'released'")
        n["parameters"]["jsCode"]=js
    write(name,w)
    print("n8n ticket/evidence guards applied")
