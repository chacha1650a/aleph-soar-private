"""실제 호출 생성기: 자리표시였던 haedam-14(pfSense 차단·해제)와 haedam-15(Wazuh 복구·격리)를 실제 호출 노드로 바꾼다.
gen_n8n_workflows.py → gen_n8n_cases.py 다음, gen_n8n_stage2.py 앞에 실행한다(공통 모듈을 불러올 때 1단계 파일을 다시 만들기 때문에 stage2를 맨 뒤에 둔다).
실행: cd tools && python gen_n8n_workflows.py && python gen_n8n_cases.py && python gen_n8n_actions.py && python gen_n8n_stage2.py
모든 호출은 dry_run 기본이다(dry_run !== false 이면 외부로 나가지 않는다). 비밀값(SSH 개인키, Wazuh 계정)은 넣지 않는다.
자격 증명 이름만 README에 적고, 연결은 n8n에서 한다. 아래 두 호출 방식은 상대 담당의 문서를 근거로 했고 아직 한 번도 실행하지 않았다."""
import gen_n8n_workflows as g
from gen_n8n_workflows import PROTECT_JS, code, exectrig, execwf, if_bool, node, save, wf

# ------------------------------------------------------------ haedam-14 pfSense 차단·해제 (B의 haedam-pf-response, SSH 강제 명령)
# 근거: lab/pfsense/README.md (PR #64). 입력 `ACTION TARGET REQUEST_ID OWNER_ID`, 출력은 JSON 1개.
# 도구는 203.0.113.22 하나만 받는다. 다른 주소는 도구가 rejected로 돌려준다(n8n도 보호 목록은 먼저 거른다).
R14PREP = PROTECT_JS + r"""// 요청 준비: 입력 검사 → 보호 목록 → dry_run. 불확실한 결과는 자동 재시도하지 않는다(도구 문서).
const b = $input.first().json;
const t = new Date().toISOString();
const ID = /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}$/;
const fail = (result, detail) => [{ json: { stop: true, final: { ok: false, result, detail, ip: b.ip, action: b.action, applied_verified: false, requested_at: t, finished_at: t, ctx: b.ctx } } }];
if (b.action === 'skip') return [{ json: { stop: true, final: { ok: true, result: 'skipped', detail: 'S8은 pfSense 차단 대상 아님', requested_at: t, finished_at: t, ctx: b.ctx } } }];
if (!['block', 'unblock', 'status'].includes(b.action)) return fail('rejected', 'action must be block|unblock|status');
const p = protectedIp(b.ip);
if (p) return fail('rejected', 'protected_or_bad_ip:' + p);
const owner = String(b.ticket_id || '');
const reqId = `${owner}-pf-${b.ip}-${b.action}`;
if (b.action !== 'status' && (!ID.test(owner) || !ID.test(reqId))) return fail('rejected', 'bad_ticket_id_for_pfsense_request');
const reqId2 = b.action === 'status' ? `status-${Date.now()}` : reqId;
const owner2 = b.action === 'status' ? 'status' : owner;
// 원격 명령은 도구 계약 그대로 (`ACTION TARGET REQUEST_ID OWNER_ID`). 전용 키의 forced command가 SSH_ORIGINAL_COMMAND를 엄격히 파싱한다.
const command = `haedam-pf-response ${b.action} ${b.ip} ${reqId2} ${owner2}`;
const base = { ctx: b.ctx, ip: b.ip, action: b.action, request_id: reqId2, owner_id: owner2, requested_at: t };
if (b.dry_run !== false) return [{ json: { stop: true, final: { ok: true, result: 'dry_run', detail: `would run via pfSense SSH: haedam-pf-response ${b.action} ${b.ip}`, ip: b.ip, action: b.action,
  request_id: reqId2, applied_verified: null, requested_at: t, finished_at: t, ctx: b.ctx } } }];
return [{ json: { ...base, command } }];
"""
R14OUT = r"""// 도구 출력(JSON 1개)을 결과 값으로 바꾼다. 출력 파싱 실패·비정상 종료·불확실한 결과는 성공으로 만들지 않고 재시도도 하지 않는다.
const j = $input.first().json;
const prev = $('요청 준비').first().json;
const fin = (o) => [{ json: { ok: !['failed', 'rejected'].includes(o.result), ip: prev.ip, action: prev.action, request_id: prev.request_id, applied_verified: o.applied_verified ?? false,
  requested_at: prev.requested_at, finished_at: new Date().toISOString(), ctx: prev.ctx, ...o } }];
if (j.error) return fin({ result: 'failed', detail: 'ssh_error:' + String((j.error && j.error.message) || j.error).slice(0, 160) });
let out = null;
try { out = JSON.parse(String(j.stdout || '').trim()); } catch (e) { /* 아래에서 처리 */ }
if (!out || typeof out !== 'object') return fin({ result: 'failed', detail: `unparseable_output exit=${j.code ?? '?'} stderr=${String(j.stderr || '').slice(0, 100)}` });
const map = { applied: 'applied', already_applied: 'already_applied', released: 'released', status: 'listed', rejected: 'rejected', failed: 'failed' };
const result = out.ok === true ? (map[out.result] || 'failed') : (out.result === 'rejected' ? 'rejected' : 'failed');
const uncertain = out.changed === null;
return fin({ result: uncertain ? 'failed' : result, detail: `${out.result}:${out.reason}${uncertain ? ' (changed:null — 운영자가 pfSense 설정·journal을 대조)' : ''}${out.replayed ? ' replayed' : ''}`,
  applied_verified: out.ok === true ? (out.applied_verified ?? null) : false, tool_state: out.state || null,
  // 대조용(11/03 B 요청): 도구가 남긴 journal 상태와 실패 사유를 요약에도 넘긴다. 객체·문자열만, 길이 제한
  journal_state: out.journal_state && typeof out.journal_state === 'object' && JSON.stringify(out.journal_state).length <= 2000 ? out.journal_state : null,
  failure_detail: typeof out.failure_detail === 'string' ? out.failure_detail.slice(0, 200) : null });
"""
R14FIN = r"""const j = $input.first().json;
return [{ json: j.stop ? j.final : j }];
"""
ssh = node("pfSense SSH (haedam-pf-response)", "n8n-nodes-base.ssh",
           # cwd는 빈 문자열 식: 값이 있으면 node-ssh가 `cd <cwd> ;`를 앞에 붙여 forced command가 거부한다(11/03 실측 837). 필수값이라 빈 값 대신 식을 쓴다.
           {"resource": "command", "operation": "execute", "authentication": "privateKey", "command": "={{ $json.command }}", "cwd": "={{ '' }}"},
           [720, 0], 1, onError="continueRegularOutput", retryOnFail=False,
           credentials={"sshPrivateKey": {"id": "", "name": "haedam-pf-response D"}})   # D 전용 키(from 10.250.0.100, forced command). 이름만, 반입 뒤 D가 연결
w14 = wf("haedamPfsense01", "haedam-14 pfSense 경계 차단·해제 (112, SSH 강제 명령)",
         [exectrig([0, 0]), code("요청 준비", R14PREP, [240, 0]), if_bool("외부 호출?", "$json.stop !== true", [480, 0]),
          ssh, code("출력 해석", R14OUT, [960, -60]), code("결과 정리", R14FIN, [1200, 0])],
         {"Execute Workflow Trigger": [["요청 준비"]], "요청 준비": [["외부 호출?"]],
          "외부 호출?": [["pfSense SSH (haedam-pf-response)"], ["결과 정리"]],
          "pfSense SSH (haedam-pf-response)": [["출력 해석"]], "출력 해석": [["결과 정리"]]})
save("haedam-14-pfsense-block.json", w14)

# ------------------------------------------------------------ haedam-15 Wazuh 복구·격리 (117, Wazuh API active response)
# 근거: lab/s7/restore/README.md, docs/capstone/evidence/S07/2026-10-28-ar-api-call-test.md — agent의 연결 파일
# `s7-restore-ar`을 `{command:"!s7-restore-ar", arguments:[웹 루트 기준 경로, run_id]}`로 부른다(10/28 C의 API 직접 호출로 확인).
# n8n 경유 호출은 미시험이다. Wazuh 응답은 전달까지만 알려 주므로 실제 복구는 로그·verify·FIM 경보로 확인한다.
R15PREP = r"""// 요청 준비: 입력 검사 → dry_run. Wazuh API 응답은 "에이전트에 보냈다"까지만 알려 준다(복구 성공은 아님).
const b = $input.first().json;
const t = new Date().toISOString();
const CFG = { api: 'https://10.250.0.3:55000', agent: '010', script: '!s7-restore-ar', web_root: '/home/haedam/haedam-portal-frontend/dist' };  // C 10/28 API 호출 확인 값
const fail = (detail) => [{ json: { stop: true, final: { ok: false, result: 'failed', detail, action: b.action, applied_verified: false, requested_at: t, finished_at: t, ctx: b.ctx } } }];
if (!['restore', 'quarantine'].includes(b.action) || !b.asset_id || !b.file_key) return fail('bad input (action restore|quarantine, asset_id, file_key)');
const key = String(b.file_key);
if (!/^[A-Za-z0-9._\-\/]{1,200}$/.test(key) || key.split('/').includes('..')) return fail('bad_file_key');
const path = key.startsWith('/') ? key : `${CFG.web_root}/${key.replace(/^\.?\//, '')}`;
if (!path.startsWith(CFG.web_root + '/')) return fail('path_outside_web_root');
// 승인된 회차 run_id(S7-YYYYMMDD-XXXX)가 입력에 있으면 그대로 AR 인자까지 전달한다. 필드가 아예 없을 때만 기존대로 event_id에서 만든다.
// 필드를 명시했는데(null 포함) 형식이 다르면 다른 값으로 바꾸지 않고 AR 전에 거절한다.
const hasRunId = Object.prototype.hasOwnProperty.call(b, 'run_id');
if (hasRunId && !(typeof b.run_id === 'string' && /^S7-\d{8}-[A-Z0-9]{2,12}$/.test(b.run_id))) return fail('bad_run_id');
const runId = hasRunId ? b.run_id : `n8n-${String(b.ctx && b.ctx.event_id || t).replace(/[^A-Za-z0-9_.-]/g, '').slice(0, 40)}`;
if (b.dry_run !== false) return [{ json: { stop: true, final: { ok: true, result: 'dry_run', detail: `would send active response ${CFG.script} to agent ${CFG.agent}: ${b.action} ${path}`, action: b.action,
  applied_verified: null, requested_at: t, finished_at: t, ctx: b.ctx } } }];
return [{ json: { ctx: b.ctx, action: b.action, path, file_key: path.slice(CFG.web_root.length + 1), run_id: runId, api: CFG.api, agent: CFG.agent, script: CFG.script, execute: true, requested_at: t } }];
"""
# ---- haedam-17: Wazuh 토큰 구간만 담는 하위 워크플로. 실행 기록을 저장하지 않는다(토큰이 n8n DB에 남지 않게).
# haedam-15는 입력 검사·dry_run·결과 해석을 맡고, 실행 기록을 저장한다(노드별 증적). 토큰을 만들거나 쓰는 노드는 이 하위 워크플로에만 있다.
R17IN = r"""// 입구 검증: 이 하위 워크플로는 haedam-15가 검증한 실행 의도(execute === true)와 고정된 대상만 받는다.
// 허용 대상·명령을 상수로 두고 입력과 같은지 확인한다. 어긋나거나 실행 의도가 없으면 로그인(자격 증명 사용)과 AR 전에 멈춘다.
const b = $input.first().json;
const ALLOWED = { api: 'https://10.250.0.3:55000', agent: '010', script: '!s7-restore-ar' };
const reject = (reason) => [{ json: { stop: true, summary: { rejected: reason } } }];
if (b.execute !== true) return reject('not_authorized');
if (b.api !== ALLOWED.api || b.agent !== ALLOWED.agent || b.script !== ALLOWED.script) return reject('target_not_allowed');
const key = b.file_key;
if (typeof key !== 'string' || !/^[A-Za-z0-9._\-\/]{1,200}$/.test(key) || key.startsWith('/') || key.split('/').includes('..')) return reject('bad_file_key');
if (typeof b.run_id !== 'string' || !/^(S7-\d{8}-[A-Z0-9]{2,12}|n8n-[A-Za-z0-9_.-]{1,40})$/.test(b.run_id)) return reject('bad_run_id');
return [{ json: { api: ALLOWED.api, agent: ALLOWED.agent, script: ALLOWED.script, file_key: key, run_id: b.run_id } }];
"""
R17BODY = r"""// 토큰은 이 실행 안에서만 쓰고 결과에 담지 않는다. 이 하위 워크플로는 실행 기록을 저장하지 않는다.
const tok = String($input.first().json.data || $input.first().json.body || '').trim();
const p = $('입력 정리').first().json;
if (!tok) return [{ json: { stop: true, summary: { auth_failed: true } } }];
return [{ json: { token: tok, url: `${p.api}/active-response?agents_list=${p.agent}`,
  body: JSON.stringify({ command: p.script, arguments: [p.file_key, p.run_id] }) } }];
"""
R17OUT = r"""// 부모(저장되는 haedam-15)로 넘기는 값은 허용된 형태만 담는다: 숫자·고정 단어·3자리 agent ID.
// 응답 원문(detail·title·message)이나 오류 문자열은 토큰이 섞일 수 있어 길이만 줄여 넘기지 않고 아예 넘기지 않는다.
const j = $input.first().json;
const d = (j.body && j.body.data) || {};
const status = Number.isInteger(j.statusCode) ? j.statusCode : null;
const failed = Array.isArray(d.failed_items) ? d.failed_items : [];
const ids = [];
for (const f of failed) for (const id of [].concat((f && f.id) || [])) if (/^\d{3}$/.test(String(id)) && ids.length < 5) ids.push(String(id));
const reason = status === null ? 'network' : status === 401 ? 'unauthorized' : status === 403 ? 'forbidden'
  : status >= 500 ? 'server_error' : status >= 400 ? 'client_error' : '';
return [{ json: { summary: { status, affected: Number.isInteger(d.total_affected_items) ? d.total_affected_items : 0,
  failed_count: failed.length, failed_ids: ids, reason } } }];
"""
R17FIN = r"""const j = $input.first().json;
return [{ json: j.summary }];
"""
auth = node("Wazuh 로그인", "n8n-nodes-base.httpRequest", {
    "method": "POST", "url": "={{ $json.api }}/security/user/authenticate?raw=true",
    "authentication": "genericCredentialType", "genericAuthType": "httpBasicAuth",
    "options": {"timeout": 8000, "allowUnauthorizedCerts": True, "response": {"response": {"responseFormat": "text"}}}},
    [480, 0], 4.2, onError="continueRegularOutput")
send = node("Wazuh active response 전송", "n8n-nodes-base.httpRequest", {
    "method": "PUT", "url": "={{ $json.url }}",
    "sendHeaders": True, "headerParameters": {"parameters": [{"name": "Authorization", "value": "=Bearer {{ $json.token }}"}]},
    "sendBody": True, "specifyBody": "json", "jsonBody": "={{ $json.body }}",
    "options": {"timeout": 8000, "allowUnauthorizedCerts": True, "response": {"response": {"fullResponse": True, "neverError": True}}}},
    [1200, -60], 4.2, onError="continueRegularOutput")
w17 = wf("haedamWazuhToken01", "haedam-17 Wazuh 토큰·전송 (haedam-15 하위, 실행 기록 저장 안 함)",
         [exectrig([0, 0]), code("입력 정리", R17IN, [240, 0]), if_bool("입력 통과?", "$json.stop !== true", [360, 0]), auth,
          code("전송 준비", R17BODY, [720, 0]),
          if_bool("토큰 받음?", "$json.stop !== true", [960, 0]), send, code("응답 요약", R17OUT, [1440, -60]),
          code("요약 정리", R17FIN, [1680, 0])],
         {"Execute Workflow Trigger": [["입력 정리"]], "입력 정리": [["입력 통과?"]],
          "입력 통과?": [["Wazuh 로그인"], ["요약 정리"]], "Wazuh 로그인": [["전송 준비"]],
          "전송 준비": [["토큰 받음?"]], "토큰 받음?": [["Wazuh active response 전송"], ["요약 정리"]],
          "Wazuh active response 전송": [["응답 요약"]], "응답 요약": [["요약 정리"]]})
# 토큰이 실행 기록에 남지 않도록 토큰 구간(이 워크플로)만 실행 기록을 저장하지 않는다(만료 15분이지만 남기지 않는다).
w17[0]["settings"].update({"saveDataSuccessExecution": "none", "saveDataErrorExecution": "none", "saveExecutionProgress": False, "saveManualExecutions": False})
save("haedam-17-wazuh-token.json", w17)

R15OUT = r"""const j = $input.first().json;   // haedam-17의 응답 요약(토큰 없음)
const p = $('요청 준비').first().json;
const fin = (o) => [{ json: { ok: o.result !== 'failed', action: p.action, applied_verified: null, requested_at: p.requested_at, finished_at: new Date().toISOString(), ctx: p.ctx, ...o } }];
if (j.rejected) return fin({ result: 'failed', detail: 'rejected:' + String(j.rejected).replace(/[^a-z_]/g, '').slice(0, 30) });
if (j.auth_failed) return fin({ result: 'failed', detail: 'wazuh_auth_failed' });
const status = Number.isInteger(j.status) ? j.status : null;
const reason = ['network', 'unauthorized', 'forbidden', 'server_error', 'client_error'].includes(j.reason) ? j.reason : '';
if (status === null) return fin({ result: 'failed', detail: 'timeout_or_network' });
if (status === 200 && j.affected >= 1)
  return fin({ result: 'applied', detail: `active response sent to agent ${p.agent} (${p.action} ${p.path}); 복구 결과는 Wazuh 경보의 sha256_after로 따로 확인(미구현)` });
if (status === 200) return fin({ result: 'failed', detail: `not_sent:failed_count=${Number(j.failed_count) || 0} ids=${(Array.isArray(j.failed_ids) ? j.failed_ids : []).filter(x => /^\d{3}$/.test(String(x))).join(',')}` });
return fin({ result: 'failed', detail: `${status} ${reason}`.trim() });
"""
R15FIN = r"""const j = $input.first().json;
return [{ json: j.stop ? j.final : j }];
"""
w15 = wf("haedamWazuhRestore01", "haedam-15 Wazuh 파일 복구·격리 (117, active response)",
         [exectrig([0, 0]), code("요청 준비", R15PREP, [240, 0]), if_bool("외부 호출?", "$json.stop !== true", [480, 0]),
          execwf("Wazuh 호출 (haedam-17)", "haedamWazuhToken01", [720, -60]),
          code("응답 해석", R15OUT, [960, -60]), code("결과 정리", R15FIN, [1200, 0])],
         {"Execute Workflow Trigger": [["요청 준비"]], "요청 준비": [["외부 호출?"]],
          "외부 호출?": [["Wazuh 호출 (haedam-17)"], ["결과 정리"]], "Wazuh 호출 (haedam-17)": [["응답 해석"]],
          "응답 해석": [["결과 정리"]]})
# haedam-15는 실행 기록을 저장한다(기본값). 입력 검사·dry_run·응답 해석이 노드별로 남는다. 토큰은 haedam-17에만 있다.
save("haedam-15-wazuh-restore.json", w15)
print("actions ok")
