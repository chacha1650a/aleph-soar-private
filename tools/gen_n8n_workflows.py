"""해담 n8n 워크플로 JSON 생성기 (haedam-10 결과 기록, 11 Discord 알림, 12 포털 IP 차단·해제, 20 S12 메인).
실행: python tools/gen_n8n_workflows.py  → infra/n8n/workflows/*.json
비밀값은 넣지 않는다. 키·Discord 웹훅 주소는 n8n 자격 증명에만 둔다."""
import json
import os
import pathlib
import uuid
from s12_health import DETECT as S12_HEALTH_DETECT

OUT = pathlib.Path(os.environ.get("ALEPH_N8N_OUTPUT", pathlib.Path(__file__).resolve().parent.parent / "infra" / "n8n" / "workflows"))
PORTAL = "http://10.250.0.2:5000"   # A 포털 VM(팀 VPN). 마지막 확인값

PROTECT_JS = r"""
function protectedIp(ip) {
  if (!/^\d+\.\d+\.\d+\.\d+$/.test(ip)) return 'bad_ip';
  if (ip.startsWith('10.250.0.')) return 'team_vpn';
  if (ip === '203.0.113.10') return 'kali_host';
  if (ip === '203.0.113.12') return 'normal_control';   // B 요청(10/26): 정상 대조용 출발지
  const m = ip.match(/^203\.0\.113\.(\d+)$/);
  if (m && +m[1] >= 100 && +m[1] <= 109) return 'normal_source';
  return null;
}
"""


def node(name, type_, params, pos, ver=1, **extra):
    n = {"id": str(uuid.uuid5(uuid.NAMESPACE_DNS, name)), "name": name, "type": type_,
         "typeVersion": ver, "position": pos, "parameters": params}
    n.update(extra)
    return n


def code(name, js, pos):
    return node(name, "n8n-nodes-base.code", {"jsCode": js}, pos, 2)


def execwf(name, wid, pos):
    return node(name, "n8n-nodes-base.executeWorkflow",
                {"source": "database", "workflowId": {"__rl": True, "value": wid, "mode": "id"}, "options": {}},
                pos, 1.2)


def exectrig(pos):
    return node("Execute Workflow Trigger", "n8n-nodes-base.executeWorkflowTrigger",
                {"inputSource": "passthrough"}, pos, 1.1)


def if_bool(name, expr, pos):
    return node(name, "n8n-nodes-base.if", {"conditions": {
        "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict", "version": 2},
        "conditions": [{"id": str(uuid.uuid5(uuid.NAMESPACE_DNS, name + "c")), "leftValue": "={{ " + expr + " }}",
                        "rightValue": "", "operator": {"type": "boolean", "operation": "true", "singleValue": True}}],
        "combinator": "and"}, "options": {}}, pos, 2.2)


def respond(name, pos):
    return node(name, "n8n-nodes-base.respondToWebhook", {"respondWith": "allIncomingItems", "options": {}}, pos, 1.1)


def wf(wid, name, nodes, conns):
    c = {}
    for src, outs in conns.items():
        c[src] = {"main": [[{"node": t, "type": "main", "index": 0} for t in o] for o in outs]}
    return [{"id": wid, "name": name, "active": False, "nodes": nodes, "connections": c,
             "settings": {"executionOrder": "v1"}}]


def save(fname, data):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / fname).write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")


# ------------------------------------------------------------ haedam-10 결과 기록
R10 = r"""// 결과 기록(check/record). 티켓 저장소(C #50/#55, 미구현)가 생기기 전까지 워크플로 정적 데이터를 자리표시로 쓴다.
// 입력·응답 모양은 C 티켓 저장소 계약 초안을 따른다. 실제 API로 바꿀 때 '저장·조회' 부분만 HTTP 호출로 교체한다.
const b = $input.first().json;
const ctx = b.ctx;
const out = (o) => [{ json: { ...o, ctx } }];
const fail = (code, message) => out({ ok: false, error: { code, message } });
const sd = $getWorkflowStaticData('global');
sd.tickets = sd.tickets || {};   // ticket_id -> ticket
sd.idem = sd.idem || {};         // idempotency_key -> 처음 응답
sd.seq = sd.seq || 0;
const now = new Date().toISOString();
const ymd = now.slice(0, 10).replace(/-/g, '');

if (!['check', 'record'].includes(b.mode)) return fail('VALIDATION_ERROR', 'bad mode');
if (b.mode === 'check' && b.target && !b.group_key) {   // target 단독 조회(원복 보류 확인): 자리 구분 없이 열린 조치를 모은다
  const hit = Object.values(sd.tickets).filter(t => t.status !== 'closed' && t.status !== 'restored' && t.actions.some(a => a.target === b.target));
  return out({ ok: true, mode: 'check', exists: hit.length > 0, ticket_id: null, status: null, actions: [], other_seat_open: [], tickets: hit });
}
for (const k of ['seat', 'group_key']) if (!b[k]) return fail('VALIDATION_ERROR', 'missing ' + k);

const tickets = Object.values(sd.tickets);
const open = tickets.find(t => t.seat === b.seat && t.group_key === b.group_key && t.status !== 'closed');

if (b.mode === 'check') {
  const other = tickets.filter(t => t.group_key === b.group_key && t.seat !== b.seat && t.status !== 'closed' && t.status !== 'restored').map(t => t.ticket_id);
  return out({ ok: true, mode: 'check', exists: !!open, ticket_id: open ? open.ticket_id : null,
    status: open ? open.status : null, actions: open ? open.actions : [], other_seat_open: other });
}

// record
for (const k of ['case_id', 'stage', 'asset_id'])   // src_ip는 S7처럼 없을 수 있다
   if (!b[k]) return fail('VALIDATION_ERROR', 'missing ' + k);
if (!['detected', 'applied', 'effect', 'released'].includes(b.stage)) return fail('VALIDATION_ERROR', 'bad stage');
if (b.idempotency_key) {
  const prev = sd.idem[b.idempotency_key];
  if (prev) return out({ ...prev, duplicate: true });
}
const a = b.action || {};
const statusOf = { detected: 'open', applied: 'responding', effect: 'verified', released: 'restored' };
let t = open, created = false, duplicate = false;
if (!t) {
  if (b.stage === 'effect' || b.stage === 'released') return fail('NOT_FOUND', 'no open ticket for ' + b.group_key);
  sd.seq += 1; created = true;
  t = { ticket_id: `T-${ymd}-${String(sd.seq).padStart(4, '0')}`, seat: b.seat, case_id: b.case_id, group_key: b.group_key,
        title: b.title || null, asset_id: b.asset_id, src_ip: b.src_ip, username: b.username || null,
        event_ids: [], status: 'open', actions: [], created_at: now };
  sd.tickets[t.ticket_id] = t;
}
if (b.event_ids) for (const e of b.event_ids) if (!t.event_ids.includes(e)) t.event_ids.push(e);
if (b.stage !== 'detected') {
  if (!a.bot || !a.action || !a.target) return fail('VALIDATION_ERROR', 'missing action fields');
  const line = t.actions.find(x => x.bot === String(a.bot) && x.action === a.action && x.target === a.target);
  if (b.stage === 'effect') {
    if (!line) return fail('NOT_FOUND', 'no matching action');
    line.effect_verified = a.effect_verified ?? null; line.effect_verified_at = now;
  } else if (line && line.result === 'applied' && b.stage === 'applied') {
    duplicate = true;   // 같은 조치가 이미 반영됨
  } else {
    t.actions.push({ bot: String(a.bot), target: a.target, via: a.via, action: a.action, result: a.result || null,
      applied_verified: a.applied_verified ?? null, effect_verified: a.effect_verified ?? null,
      requested_at: a.requested_at || null, finished_at: a.finished_at || now,
      n8n_execution_id: a.n8n_execution_id || $execution.id, detail: a.detail || null });
  }
}
if (!duplicate && !(b.stage === 'detected' && !created)) t.status = statusOf[b.stage];   // 기존 티켓에 detected가 다시 와도 상태를 되돌리지 않는다
const res = { ok: true, mode: 'record', ticket_id: t.ticket_id, created, duplicate, status: t.status };
if (b.idempotency_key) sd.idem[b.idempotency_key] = res;
return out(res);
"""
TICKET = "http://10.250.0.3:8088"   # C 티켓 저장소(PR #55). cfg.store_real이 true일 때만 부른다

R10route = r"""// 저장소 선택: ctx.cfg.store_real이 true일 때만 실제 티켓 저장소(C, 10.250.0.3:8088)를 쓴다. 그 밖에는 워크플로 안 자리표시 저장소.
// store_real(저장소 기록)과 dry_run(포털·pfSense·Wazuh 실제 조치)은 따로다. store_real이 없는 옛 호출만 dry_run === false를 저장소 사용으로 본다.
// dry_run 결과('dry_run'·'skipped')는 실제 저장소 계약(result 5가지)에 없어 조치 줄(applied)로 쓰지 않고, 티켓만 연다(stage detected).
const b = $input.first().json;
const cfg = (b.ctx && b.ctx.cfg) || {};
const real = cfg.store_real === true || (cfg.store_real === undefined && cfg.dry_run === false);
const base = '%TICKET%/api/v1/tickets';
if (!real) return [{ json: { ...b, real: false } }];
const ctx = b.ctx;
if (b.mode === 'check') {
  // 원복 보류 확인: target만 주면 target 단독 조회(다른 자리 차단까지 나온다). group_key가 있으면 기존 방식.
  const parts = [];
  if (b.group_key) parts.push(`group_key=${encodeURIComponent(b.group_key)}`);
  if (b.seat && !(b.target && !b.group_key)) parts.push(`seat=${encodeURIComponent(b.seat)}`);   // target 단독이면 seat도 붙이지 않는다
  if (b.target && !b.group_key) parts.push(`target=${encodeURIComponent(b.target)}`);
  const query_scope = b.target && !b.group_key ? 'target' : (b.seat ? 'seat' : 'all_seats');
  return [{ json: { real: true, mode: 'check', method: 'GET', url: `${base}/open?${parts.join('&')}`, idem: '', body: null,
    query_scope, target: query_scope === 'target' ? b.target : null, ctx } }];
}
let a = b.action || null, stage = b.stage, idem = b.idempotency_key || `${$execution.id}-${b.stage}`;
if (a && ['dry_run', 'skipped'].includes(a.result)) { a = null; stage = 'detected'; idem = `${idem}-dry`; }   // 실제 조치가 없으면 조치 줄을 남기지 않는다
const body = { seat: b.seat, case_id: b.case_id, group_key: b.group_key, stage, title: b.title || ctx.title || b.case_id,
  asset_id: b.asset_id, src_ip: b.src_ip || null, username: b.username || null, event_ids: b.event_ids || [],
  action: stage === 'detected' ? null : (a && {
    bot: String(a.bot), target: a.target, via: a.via, action: a.action, result: a.result,
    applied_verified: a.applied_verified ?? null, effect_verified: a.effect_verified ?? null,
    requested_at: a.requested_at || null, finished_at: a.finished_at || null, effect_verified_at: a.effect_verified_at ?? null,
    n8n_execution_id: String(a.n8n_execution_id || $execution.id), detail: a.detail ? String(a.detail).slice(0, 300) : undefined }) };
return [{ json: { real: true, mode: 'record', method: 'POST', url: `${base}/record`, idem, body, ctx } }];
""".replace("%TICKET%", TICKET)

R10class = r"""// 티켓 저장소 응답을 자리표시 저장소와 같은 모양으로 바꾼다. 5xx·시간 초과는 같은 Idempotency-Key로 1회만 다시 보낸다(C 합의: 노드 재시도는 네트워크 오류만, 4xx는 재시도 안 함).
const j = $input.first().json;
const prev = $('저장소 요청 만들기').first().json;
const status = j.statusCode ?? null, body = j.body ?? null;
const ctx = prev.ctx;
if (status === null || status >= 500) return [{ json: { retry: RETRY, ok: false, ctx, error: { code: status === null ? 'NETWORK' : 'HTTP_' + status, message: String((j.error && (j.error.message || j.error)) || j.message || 'ticket store unreachable or 5xx').slice(0, 200) } } }];
if (status === 200 || status === 201) {
  if (prev.mode === 'check') {
    const list = (body.applied_actions || []).map(a => ({ bot: a.bot, via: a.via, action: a.action, target: a.target, result: a.result }));
    return [{ json: { retry: false, ok: true, mode: 'check', exists: !!body.exists, ticket_id: body.ticket_id || null, status: body.status || null, actions: list, other_seat_open: [], tickets: body.tickets || null, ctx } }];
  }
  return [{ json: { retry: false, ok: true, mode: 'record', ticket_id: body.ticket_id, created: !!body.created, duplicate: !!body.duplicate, status: body.status, ctx } }];
}
const e = (body && body.error) || {};
return [{ json: { retry: false, ok: false, ctx, error: { code: e.code || 'HTTP_' + status, message: String(e.message || '').slice(0, 200) } } }];
"""


def http_ticket(name, pos):
    q = "$('저장소 요청 만들기').first().json"
    n = node(name, "n8n-nodes-base.httpRequest", {
        "method": "={{ " + q + ".method }}", "url": "={{ " + q + ".url }}",
        "authentication": "genericCredentialType", "genericAuthType": "httpHeaderAuth",
        "sendHeaders": True,
        "headerParameters": {"parameters": [{"name": "Idempotency-Key", "value": "={{ " + q + ".idem }}"}]},
        # sendBody는 식(expression)이 아니라 true로 둔다. 식으로 두면 POST 본문이 안 나가 저장소가 400(body must be a JSON object)을 줬다(10/26 시험).
        # GET(check)은 본문이 없어 '{}'를 보낸다.
        "sendBody": True, "specifyBody": "json",
        "jsonBody": "={{ " + q + ".body ? JSON.stringify(" + q + ".body) : '{}' }}",
        "options": {"timeout": 10000, "response": {"response": {"fullResponse": True, "neverError": True}}}},
        pos, 4.2, onError="continueRegularOutput")
    n["retryOnFail"] = True
    n["maxTries"] = 3
    n["waitBetweenTries"] = 2000
    return n


w10 = wf("haedamResultLog01", "haedam-10 결과 기록 (티켓 저장소 / dry_run은 자리표시)",
         [exectrig([0, 0]), code("저장소 요청 만들기", R10route, [240, 0]),
          if_bool("실제 저장소?", "$json.real === true", [480, 0]),
          code("check/record (자리표시 저장소)", R10, [720, -160]),
          http_ticket("티켓 저장소 호출 1", [720, 80]), code("응답 변환 1", R10class.replace("RETRY", "true"), [960, 80]),
          if_bool("재시도?", "$json.retry === true", [1200, 80]),
          http_ticket("티켓 저장소 호출 2 (같은 키, 1회)", [1440, 0]), code("응답 변환 2", R10class.replace("RETRY", "false").replace("$('저장소 요청 만들기')", "$('저장소 요청 만들기')"), [1680, 0]),
          code("결과 전달", "return $input.all();   // 재시도 없이 끝난 경우: IF의 false 가지 결과를 하위 워크플로 출력으로 내보낸다", [1440, 200])],
         {"Execute Workflow Trigger": [["저장소 요청 만들기"]], "저장소 요청 만들기": [["실제 저장소?"]],
          "실제 저장소?": [["티켓 저장소 호출 1"], ["check/record (자리표시 저장소)"]],
          "티켓 저장소 호출 1": [["응답 변환 1"]], "응답 변환 1": [["재시도?"]],
          "재시도?": [["티켓 저장소 호출 2 (같은 키, 1회)"], ["결과 전달"]],
          "티켓 저장소 호출 2 (같은 키, 1회)": [["응답 변환 2"]]})
save("haedam-10-result-log.json", w10)

# ------------------------------------------------------------ haedam-11 Discord 알림
R11 = r"""// Discord 알림(113) 본문 만들기. 웹훅 주소는 Discord 노드의 자격 증명에만 둔다.
const b = $input.first().json;
const lv = { info: '[정보]', warn: '[경고]', error: '[오류]' }[b.level || 'info'] || '[정보]';
const lines = [`${lv} **[${b.case_id || '-'}] ${b.title || '알림'}**`];
if (b.src_ip) lines.push(`출발지: ${b.src_ip}`);
if (b.ticket_id) lines.push(`티켓: ${b.ticket_id}`);
if (b.result) lines.push(`결과: ${b.result}`);
if (b.detail) lines.push(String(b.detail).slice(0, 500));
lines.push(`n8n 실행: ${$execution.id}`);
return [{ json: { content: lines.join('\n'), ctx: b.ctx } }];
"""
R11b = r"""// Discord 노드 결과(또는 자격 증명 없음·전송 실패)를 sent 여부로 정리
const j = $input.first().json;
const failed = !!(j.error || (j.message && /credential|webhook|ENOTFOUND|\b4\d\d\b/i.test(String(j.message))));
return [{ json: { sent: !failed, error: failed ? String((j.error && j.error.message) || j.message || j.error) : null, ctx: $('Discord 본문').first().json.ctx } }];
"""
w11 = wf("haedamDiscord01", "haedam-11 Discord 알림 (113)",
         [exectrig([0, 0]), code("Discord 본문", R11, [260, 0]),
          node("Discord 웹훅", "n8n-nodes-base.discord",
               {"authentication": "webhook", "content": "={{ $json.content }}", "options": {}}, [520, 0], 2,
               onError="continueRegularOutput"),
          code("전송 결과", R11b, [780, 0])],
         {"Execute Workflow Trigger": [["Discord 본문"]], "Discord 본문": [["Discord 웹훅"]],
          "Discord 웹훅": [["전송 결과"]]})
save("haedam-11-discord-notify.json", w11)

# ------------------------------------------------------------ haedam-12 포털 IP 차단·해제
R12a = PROTECT_JS + r"""// 입력 검증·Idempotency-Key·보호 대상 확인. 키 형식은 API-CONTRACT n8n 규칙(#46): {ticket_id}-{봇}-{대상}-{동작}
const b = $input.first().json;
const ctx = b.ctx;
const action = b.action;
if (!['block', 'unblock', 'list'].includes(action)) return [{ json: { result: 'failed', detail: 'bad action', stop: true, ctx } }];
if (action !== 'list') {
  const p = protectedIp(b.ip);
  if (p) return [{ json: { result: 'rejected', detail: 'protected_or_bad_ip:' + p, stop: true, ctx } }];
  if (!b.ticket_id) return [{ json: { result: 'failed', detail: 'ticket_id required for Idempotency-Key', stop: true, ctx } }];
}
const round = b.round && b.round > 1 ? `-${b.round}` : '';
const idem = action === 'list' ? null : `${b.ticket_id}-112-${b.ip}-${action}${round}`;
const path = action === 'list' ? '/api/v1/response/ips' : `/api/v1/response/ips/${action}`;
return [{ json: { action, ip: b.ip, idem, path, url: '%PORTAL%' + path, method: action === 'list' ? 'GET' : 'POST',
  dry_run: b.dry_run !== false, stop: false, ctx, requested_at: new Date().toISOString() } }];
""".replace("%PORTAL%", PORTAL)

CLASSIFY = r"""// 포털 응답을 결과 값으로 바꾼다(API-CONTRACT n8n 규칙 표). 시간 초과·연결 실패는 응답이 없다.
const j = $input.first().json;
const prev = $('요청 준비').first().json;
const status = j.statusCode ?? null;
const body = j.body ?? null;
let result = 'failed', retry = false, detail = '';
if (status === null) { retry = true; detail = 'timeout_or_network:' + String((j.error && j.error.message) || j.message || '').slice(0, 120); }
else if (status === 200) {
  const d = (body && body.data) || {};
  if (prev.action === 'list') result = 'listed';
  else if (prev.action === 'block') result = d.changed ? 'applied' : 'already_applied';
  else result = d.changed ? 'released' : 'already_applied';
  detail = `${status} changed:${d.changed}`;
} else if (status === 403) { result = 'rejected'; detail = '403 FORBIDDEN'; }
else if (status === 409 || status >= 500) { retry = true; detail = `${status}`; }
else { detail = `${status} ${(body && body.error && body.error.code) || ''}`; }
return [{ json: { result, retry, detail, status, body_data: (body && body.data) || null, ctx: prev.ctx, idem: prev.idem, ip: prev.ip, action: prev.action,
  requested_at: prev.requested_at, finished_at: new Date().toISOString() } }];
"""


def http_portal(name, pos):
    q = "$('요청 준비').first().json"
    return node(name, "n8n-nodes-base.httpRequest", {
        "method": "={{ " + q + ".method }}",
        "url": "={{ " + q + ".url }}",
        "authentication": "genericCredentialType", "genericAuthType": "httpHeaderAuth",
        "sendHeaders": True,
        "headerParameters": {"parameters": [{"name": "Idempotency-Key", "value": "={{ " + q + ".idem || '' }}"}]},
        # 10/27 실제 호출(.11 차단 15:52·재전송 17:02·해제 17:06, 모두 200)에 쓴 게시본과 같은 설정.
        # sendBody를 식으로 두면 본문 없이 나가 포털이 400 VALIDATION_ERROR를 돌려줬다(10/27 14:09).
        "sendBody": True,
        "contentType": "json",
        "specifyBody": "keypair",
        "bodyParameters": {"parameters": [{"name": "ip", "value": "={{ " + q + ".ip }}"}]},
        "options": {"timeout": 5000, "response": {"response": {"fullResponse": True, "neverError": True}}}},
        pos, 4.2, onError="continueRegularOutput")


R12f = r"""// 최종 결과 정리. 재시도는 같은 Idempotency-Key로 1회만 했다.
const j = $input.first().json;
const final = { ok: !['failed', 'rejected'].includes(j.result), result: j.result, detail: j.detail, ip: j.ip, action: j.action, idempotency_key: j.idem,
  applied_verified: null, requested_at: j.requested_at, finished_at: j.finished_at, ctx: j.ctx };
if (j.action === 'list') final.items = (j.body_data && j.body_data.items) || [];
return [{ json: final }];
"""
R12dry = r"""// 시험·기준선 측정 전에는 포털을 부르지 않는다(dry_run 기본값 true). 보낼 요청만 돌려준다. 키 값은 포함하지 않는다.
const p = $input.first().json;
return [{ json: { ok: true, result: 'dry_run', detail: `would ${p.method} ${p.url}`, ip: p.ip, action: p.action, idempotency_key: p.idem,
  applied_verified: null, requested_at: p.requested_at, finished_at: new Date().toISOString(), ctx: p.ctx } }];
"""
R12stop = r"""const p = $input.first().json;
const t = new Date().toISOString();
return [{ json: { ok: false, result: p.result, detail: p.detail, applied_verified: false, requested_at: t, finished_at: t, ctx: p.ctx } }];
"""
RETRY2 = "포털 호출 2 (같은 키, 1회)"
w12 = wf("haedamPortalIp01", "haedam-12 포털 IP 차단·해제 (112)",
         [exectrig([0, 0]), code("요청 준비", R12a, [240, 0]),
          if_bool("검증 실패?", "$json.stop", [480, 0]),
          code("검증 실패 결과", R12stop, [720, -120]),
          if_bool("dry_run?", "$json.dry_run", [720, 80]),
          code("dry_run 결과", R12dry, [960, -20]),
          http_portal("포털 호출 1", [960, 180]), code("응답 분류 1", CLASSIFY, [1200, 180]),
          if_bool("재시도?", "$json.retry", [1440, 180]),
          http_portal(RETRY2, [1680, 100]), code("응답 분류 2", CLASSIFY, [1920, 100]),
          code("최종 결과", R12f, [2160, 180])],
         {"Execute Workflow Trigger": [["요청 준비"]], "요청 준비": [["검증 실패?"]],
          "검증 실패?": [["검증 실패 결과"], ["dry_run?"]],
          "dry_run?": [["dry_run 결과"], ["포털 호출 1"]],
          "포털 호출 1": [["응답 분류 1"]], "응답 분류 1": [["재시도?"]],
          "재시도?": [[RETRY2], ["최종 결과"]],
          RETRY2: [["응답 분류 2"]], "응답 분류 2": [["최종 결과"]]})
save("haedam-12-portal-ip-block.json", w12)

# ------------------------------------------------------------ haedam-20 S12 메인
R20a = PROTECT_JS + r"""// 독립 D→health 기준(11/03 실측)을 고정한다. /login에서 얻은 과거3414ms는 재사용하지 않는다.
const CFG = {
  seat: 'D', case_id: 'S12',
  health_url: '%PORTAL%/api/v1/health', health_interval_ms: 2000, health_timeout_ms: 5000, health_k: 3,
  // S12-20261103-D-HEALTH-BASELINE01(10.250.0.100→/api/v1/health, 2초·300초·n150 전부 200): median 38.8·p95 293.8·max 1759.1ms.
  // 계산식 881.4ms(p95×3)는 정상 구간에서 3회 연속 초과(19:35:46~50)라 K=3 오탐 → 정상 최댓값 위 2000ms로 D 결정(11/03)
  baseline_ms: 2000, baseline_source: 'S12-20261103-D-HEALTH-BASELINE01',
  dry_run: true,                                                                                         // A가 키·허용 대역을 반영하고 시험하기 전까지 true (포털 실제 호출)
  store_real: false                                                                                     // 기본 관찰 모드. 본문 store_real:true(불리언)일 때만 티켓을 C 저장소에 기록한다(조치는 dry_run을 따른다)
};
const t = { ...($input.first().json.body || {}) };
if (t.store_real === true) CFG.store_real = true;
if (t.dry_run === false) CFG.dry_run = false;   // 실제 포털 차단은 본문의 dry_run:false(불리언)로만 켠다(기본 true). 회차마다 D 명시 승인 후에만 사용. 기준 미확정이면 no_baseline으로 대응하지 않는다
// 시험 전용: dry_run일 때만 기준선을 임시로 줄 수 있다
if (CFG.dry_run && typeof t.test_baseline_ms === 'number') CFG.baseline_ms = t.test_baseline_ms;
if (CFG.dry_run && typeof t.test_baseline_ms === 'number') CFG.baseline_source = 'synthetic_override';
const missing = ['event_id', 'asset_id', 'src_ip'].filter(k => !t[k]);
if (missing.length) return [{ json: { ok: false, verdict: 'invalid_input', missing, no_action: true } }];
const p = protectedIp(t.src_ip);
const X = { event_id: t.event_id, asset_id: t.asset_id, src_ip: t.src_ip, count: t.count ?? null, cfg: CFG };
if (p) return [{ json: { ok: true, verdict: 'protected_source', reason: p, event_id: t.event_id, asset_id: t.asset_id, src_ip: t.src_ip, no_action: true } }];
return [{ json: { proceed: true, mode: 'check', seat: CFG.seat, case_id: CFG.case_id, group_key: t.src_ip, ctx: X } }];
""".replace("%PORTAL%", PORTAL)

R20b = r"""// 중복 확인 결과: 이미 열린 티켓에서 이 출발지 차단이 반영됐으면 새 조치를 하지 않는다.
const j = $input.first().json;
const x = j.ctx;
const applied = (j.actions || []).some(a => a.bot === '112' && a.action === 'block' && a.result === 'applied');
if (j.ok && j.exists && applied) return [{ json: { ok: true, verdict: 'duplicate_no_action', ticket_id: j.ticket_id, event_id: x.event_id, asset_id: x.asset_id, src_ip: x.src_ip, no_action: true } }];
return [{ json: { proceed: true, ctx: { ...x, existing_ticket: j.ticket_id || null, other_seat_open: j.other_seat_open || [] } } }];
"""

R20c = S12_HEALTH_DETECT

R20det = r"""// 조치 전에 티켓을 먼저 만든다(stage detected, 응답이 늦거나 실패해도 사건이 남게).
const x = $input.first().json.ctx;
return [{ json: { ctx: x, mode: 'record', stage: 'detected', seat: x.cfg.seat, case_id: x.cfg.case_id, group_key: x.src_ip,
  title: '포털 요청 폭주로 응답 지연', asset_id: x.asset_id, src_ip: x.src_ip, event_ids: [x.event_id],
  idempotency_key: `${$execution.id}-detected` } }];
"""
R20blk = r"""const r = $input.first().json;
const x = r.ctx;
return [{ json: { ctx: { ...x, ticket_id: r.ticket_id }, action: 'block', ip: x.src_ip, ticket_id: r.ticket_id, dry_run: x.cfg.dry_run } }];
"""
R20app = r"""// 차단 결과를 티켓에 기록(stage applied). Idempotency-Key = {실행 ID}-applied
const r = $input.first().json;
const x = r.ctx;
const block = { result: r.result, detail: r.detail, idempotency_key: r.idempotency_key };
return [{ json: { ctx: { ...x, block }, mode: 'record', stage: 'applied', seat: x.cfg.seat, case_id: x.cfg.case_id, group_key: x.src_ip, title: '포털 요청 폭주로 응답 지연',
  asset_id: x.asset_id, src_ip: x.src_ip, event_ids: [x.event_id], idempotency_key: `${$execution.id}-applied`,
  action: { bot: '112', target: x.src_ip, via: 'portal', action: 'block', result: r.result,
    applied_verified: r.result === 'dry_run' ? null : (r.applied_verified ?? null), effect_verified: null, effect_verified_at: null,
    requested_at: r.requested_at, finished_at: r.finished_at, n8n_execution_id: String($execution.id), detail: r.detail } } }];
"""
R20note = r"""const r = $input.first().json;
const x = r.ctx;
return [{ json: { ctx: { ...x, record: { ok: r.ok, ticket_id: r.ticket_id, created: r.created, duplicate: r.duplicate, status: r.status } },
  level: r.ok ? 'warn' : 'error', case_id: 'S12', title: '요청 폭주 대응', src_ip: x.src_ip,
  ticket_id: r.ticket_id, result: x.block ? x.block.result : null, detail: `헬스체크 ${x.health.verdict}, 기준선 ${x.health.baseline_ms}ms` } }];
"""
R20final = r"""// 최종 응답. 비밀값은 포함하지 않는다.
const r = $input.first().json;
const x = r.ctx;
return [{ json: { ok: true, verdict: 'responded', event_id: x.event_id, asset_id: x.asset_id, src_ip: x.src_ip,
  block: x.block || null, ticket: x.record || null, discord_sent: r.sent, discord_error: r.error, health: x.health, n8n_execution_id: $execution.id } }];
"""
R20noact = r"""// 대응하지 않는 경우(기준선 안, 기준선 없음, 중복, 보호 대상, 입력 오류)의 응답. 티켓을 만들지 않는다.
const j = $input.first().json;
const out = j.no_action ? j : { ok: true, verdict: j.verdict, event_id: j.event_id, asset_id: j.asset_id, src_ip: j.src_ip, health: j.health, no_action: true };
return [{ json: { ...out, n8n_execution_id: $execution.id } }];
"""
w20 = wf("haedamS12Main01", "haedam-20 S12 요청 폭주 대응 (메인)",
         [node("Webhook", "n8n-nodes-base.webhook",
               {"httpMethod": "POST", "path": "haedam-s12", "responseMode": "responseNode", "authentication": "headerAuth", "options": {}},
               [0, 0], 2, webhookId="haedam-s12",
               credentials={"httpHeaderAuth": {"id": "", "name": "haedam-s12 caller"}}),   # 티켓 실기록 경로라 호출자 인증 필수(11/02 B·C 기준)
          code("입력 검증·설정", R20a, [240, 0]),
          if_bool("대응 대상?", "$json.proceed === true", [480, 0]),
          execwf("중복 확인 (haedam-10 check)", "haedamResultLog01", [720, -60]),
          code("중복 판정", R20b, [960, -60]),
          if_bool("중복 아님?", "$json.proceed === true", [1200, -60]),
          code("헬스체크 K회", R20c, [1440, -120]),
          if_bool("기준선 초과?", "$json.verdict === 'exceeded'", [1680, -120]),
          code("티켓 detected 입력", R20det, [1920, -200]),
          execwf("티켓 detected (haedam-10)", "haedamResultLog01", [2160, -200]),
          code("차단 입력", R20blk, [2400, -200]),
          execwf("차단 (haedam-12)", "haedamPortalIp01", [2640, -200]),
          code("차단 기록 입력", R20app, [2880, -200]),
          execwf("차단 기록 (haedam-10 applied)", "haedamResultLog01", [3120, -200]),
          code("알림 입력", R20note, [3360, -200]),
          execwf("Discord 알림 (haedam-11)", "haedamDiscord01", [3600, -200]),
          code("최종 응답", R20final, [3840, -200]),
          code("대응 없음 응답", R20noact, [1680, 120]),
          respond("응답: 대응", [4080, -200]),
          respond("응답: 대응 없음", [1920, 120])],
         {"Webhook": [["입력 검증·설정"]], "입력 검증·설정": [["대응 대상?"]],
          "대응 대상?": [["중복 확인 (haedam-10 check)"], ["대응 없음 응답"]],
          "중복 확인 (haedam-10 check)": [["중복 판정"]], "중복 판정": [["중복 아님?"]],
          "중복 아님?": [["헬스체크 K회"], ["대응 없음 응답"]],
          "헬스체크 K회": [["기준선 초과?"]],
          "기준선 초과?": [["티켓 detected 입력"], ["대응 없음 응답"]],
          "티켓 detected 입력": [["티켓 detected (haedam-10)"]], "티켓 detected (haedam-10)": [["차단 입력"]],
          "차단 입력": [["차단 (haedam-12)"]], "차단 (haedam-12)": [["차단 기록 입력"]],
          "차단 기록 입력": [["차단 기록 (haedam-10 applied)"]], "차단 기록 (haedam-10 applied)": [["알림 입력"]],
          "알림 입력": [["Discord 알림 (haedam-11)"]], "Discord 알림 (haedam-11)": [["최종 응답"]],
          "최종 응답": [["응답: 대응"]], "대응 없음 응답": [["응답: 대응 없음"]]})
save("haedam-20-s12-main.json", w20)
print("ok")
