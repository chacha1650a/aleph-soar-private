"""케이스별(S1·S4·S7·S8·S10) n8n 워크플로 생성기.
공통 하위 워크플로(10 기록, 11 Discord, 12 포털 IP 차단, 13 포털 계정 잠금, 14 pfSense 차단, 15 Wazuh 복구·격리)를 부른다.
실행: cd tools && python gen_n8n_workflows.py && python gen_n8n_cases.py
모든 하위 호출은 dry_run 기본이다. 비밀값은 넣지 않는다."""
import gen_n8n_workflows as g
from gen_n8n_workflows import PORTAL, PROTECT_JS, code, exectrig, execwf, if_bool, node, respond, save, wf

# ------------------------------------------------------------ haedam-13 포털 계정 잠금 (111)
R13a = r"""// 입력 검증·Idempotency-Key. 키 형식: {ticket_id}-111-{username}-lock (API-CONTRACT n8n 규칙 #46)
const b = $input.first().json;
const ctx = b.ctx;
if (b.action !== 'lock') return [{ json: { result: 'failed', detail: 'only lock is automated (해제·재설정은 사람이)', stop: true, ctx } }];
if (!b.username || !/^[A-Za-z0-9_.\-]{1,64}$/.test(b.username)) return [{ json: { result: 'failed', detail: 'bad_username', stop: true, ctx } }];
if (!b.ticket_id) return [{ json: { result: 'failed', detail: 'ticket_id required for Idempotency-Key', stop: true, ctx } }];
const idem = `${b.ticket_id}-111-${b.username}-lock`;
return [{ json: { action: 'lock', username: b.username, idem, url: '%PORTAL%/api/v1/response/accounts/lock', method: 'POST',
  dry_run: b.dry_run !== false, stop: false, ctx, requested_at: new Date().toISOString() } }];
""".replace("%PORTAL%", PORTAL)

CLASSIFY13 = (g.CLASSIFY
              .replace("prev.action === 'list'", "false")
              .replace("else if (prev.action === 'block') result = d.changed ? 'applied' : 'already_applied';\n  else result = d.changed ? 'released' : 'already_applied';",
                       "else result = d.changed ? 'applied' : 'already_applied';")
              .replace("ip: prev.ip, action: prev.action", "username: prev.username, action: prev.action"))


def http_lock(name, pos):
    q = "$('요청 준비').first().json"
    return node(name, "n8n-nodes-base.httpRequest", {
        "method": "POST", "url": "={{ " + q + ".url }}",
        "authentication": "genericCredentialType", "genericAuthType": "httpHeaderAuth",
        "sendHeaders": True,
        "headerParameters": {"parameters": [{"name": "Idempotency-Key", "value": "={{ " + q + ".idem }}"}]},
        "sendBody": True, "specifyBody": "json",
        "jsonBody": "={{ JSON.stringify({ username: " + q + ".username }) }}",
        "options": {"timeout": 5000, "response": {"response": {"fullResponse": True, "neverError": True}}}},
        pos, 4.2, onError="continueRegularOutput")


R13dry = r"""// dry_run: 포털을 부르지 않고 보낼 요청만 돌려준다. S4 username 잠금은 backend #3 병합·배포 뒤에야 실제 호출 가능.
const p = $input.first().json;
return [{ json: { ok: true, result: 'dry_run', detail: `would ${p.method} ${p.url}`, username: p.username, action: p.action, idempotency_key: p.idem,
  applied_verified: null, requested_at: p.requested_at, finished_at: new Date().toISOString(), ctx: p.ctx } }];
"""
R13f = r"""const j = $input.first().json;
return [{ json: { ok: !['failed', 'rejected'].includes(j.result), result: j.result, detail: j.detail, username: j.username, action: j.action,
  idempotency_key: j.idem, applied_verified: null, requested_at: j.requested_at, finished_at: j.finished_at, ctx: j.ctx } }];
"""
w13 = wf("haedamAccountLock01", "haedam-13 포털 계정 잠금 (111)",
         [exectrig([0, 0]), code("요청 준비", R13a, [240, 0]),
          if_bool("검증 실패?", "$json.stop", [480, 0]),
          code("검증 실패 결과", g.R12stop, [720, -120]),
          if_bool("dry_run?", "$json.dry_run", [720, 80]),
          code("dry_run 결과", R13dry, [960, -20]),
          http_lock("포털 호출 1", [960, 180]), code("응답 분류 1", CLASSIFY13, [1200, 180]),
          if_bool("재시도?", "$json.retry", [1440, 180]),
          http_lock(g.RETRY2, [1680, 100]), code("응답 분류 2", CLASSIFY13, [1920, 100]),
          code("최종 결과", R13f, [2160, 180])],
         {"Execute Workflow Trigger": [["요청 준비"]], "요청 준비": [["검증 실패?"]],
          "검증 실패?": [["검증 실패 결과"], ["dry_run?"]],
          "dry_run?": [["dry_run 결과"], ["포털 호출 1"]],
          "포털 호출 1": [["응답 분류 1"]], "응답 분류 1": [["재시도?"]],
          "재시도?": [[g.RETRY2], ["최종 결과"]],
          g.RETRY2: [["응답 분류 2"]], "응답 분류 2": [["최종 결과"]]})
save("haedam-13-portal-account-lock.json", w13)

# ------------------------------------------------------------ haedam-14 pfSense 차단 / haedam-15 Wazuh 복구 (수단 미정, 자리표시)
R14 = PROTECT_JS + r"""// 자리표시: pfSense 차단 수단은 B의 사전 위험 시험 ①(SSH easyrule 또는 REST 패키지) 결과 뒤에 정한다.
const b = $input.first().json;
const t = new Date().toISOString();
if (b.action === 'skip') return [{ json: { ok: true, result: 'skipped', detail: 'S8은 pfSense 차단 대상 아님', requested_at: t, finished_at: t, ctx: b.ctx } }];
const bad = b.action !== 'block' ? 'only block is automated' : protectedIp(b.ip) ? 'protected_or_bad_ip:' + protectedIp(b.ip) : null;
if (bad) return [{ json: { ok: false, result: 'rejected', detail: bad, applied_verified: false, requested_at: t, finished_at: t, ctx: b.ctx } }];
if (b.dry_run !== false) return [{ json: { ok: true, result: 'dry_run', detail: 'would block via pfSense (수단 미정)', ip: b.ip, action: 'block', applied_verified: null, requested_at: t, finished_at: t, ctx: b.ctx } }];
return [{ json: { ok: false, result: 'failed', detail: 'not_configured: pfSense 차단 수단 미정', ip: b.ip, action: 'block', applied_verified: false, requested_at: t, finished_at: t, ctx: b.ctx } }];
"""
w14 = wf("haedamPfsense01", "haedam-14 pfSense 경계 차단 (112, 수단 미정)",
         [exectrig([0, 0]), code("pfSense 차단 (자리표시)", R14, [260, 0])],
         {"Execute Workflow Trigger": [["pfSense 차단 (자리표시)"]]})
save("haedam-14-pfsense-block.json", w14)

R15 = r"""// 자리표시: Wazuh 복구·격리(117) 수단은 C의 사전 시험(1안 n8n→Wazuh API active response, 2안 포털 API) 결과 뒤에 정한다.
const b = $input.first().json;
const t = new Date().toISOString();
if (!['restore', 'quarantine'].includes(b.action) || !b.asset_id || !b.file_key)
  return [{ json: { ok: false, result: 'failed', detail: 'bad input (action restore|quarantine, asset_id, file_key)', applied_verified: false, requested_at: t, finished_at: t, ctx: b.ctx } }];
if (b.dry_run !== false) return [{ json: { ok: true, result: 'dry_run', detail: `would ${b.action} ${b.asset_id}:${b.file_key} (수단 미정)`, action: b.action, applied_verified: null, requested_at: t, finished_at: t, ctx: b.ctx } }];
return [{ json: { ok: false, result: 'failed', detail: 'not_configured: Wazuh 복구·격리 수단 미정', action: b.action, applied_verified: false, requested_at: t, finished_at: t, ctx: b.ctx } }];
"""
w15 = wf("haedamWazuhRestore01", "haedam-15 Wazuh 파일 복구·격리 (117, 수단 미정)",
         [exectrig([0, 0]), code("복구·격리 (자리표시)", R15, [260, 0])],
         {"Execute Workflow Trigger": [["복구·격리 (자리표시)"]]})
save("haedam-15-wazuh-restore.json", w15)

# ------------------------------------------------------------ 케이스 메인 공통 골격
WF_ID = {"112": "haedamPortalIp01", "111": "haedamAccountLock01", "pfsense": "haedamPfsense01", "117": "haedamWazuhRestore01"}

DEDUP_JS = r"""// 중복 확인: 이 케이스가 하려는 조치가 열린 티켓에 이미 모두 반영(applied)됐으면 새로 하지 않는다.
const j = $input.first().json;
const x = j.ctx;
const done = (s) => (j.actions || []).some(a => a.bot === s.bot && a.action === s.action && a.target === s.target && a.result === 'applied');
if (j.ok && j.exists && x.expected.length && x.expected.every(done))
  return [{ json: { ok: true, verdict: 'duplicate_no_action', ticket_id: j.ticket_id, event_id: x.event_id, case_id: x.case_id, no_action: true } }];
return [{ json: { proceed: true, ctx: { ...x, existing_ticket: j.ticket_id || null, other_seat_open: j.other_seat_open || [] } } }];
"""
DETECTED_JS = r"""// 조치 전에 티켓을 먼저 만든다(stage detected). 이미 열린 티켓이 있으면 그 티켓을 쓴다.
const x = $input.first().json.ctx;
return [{ json: { ctx: x, mode: 'record', stage: 'detected', seat: x.seat, case_id: x.case_id, group_key: x.group_key, title: x.title,
  asset_id: x.asset_id, src_ip: x.src_ip || null, username: x.username || null, event_ids: [x.event_id],
  idempotency_key: `${$execution.id}-detected` } }];
"""
STEP_IN_JS = r"""const r = $input.first().json;
const x = r.ctx;
const ticket_id = r.ticket_id || x.ticket_id;
return [{ json: { ctx: { ...x, ticket_id }, ticket_id, dry_run: x.cfg.dry_run, %INPUT% } }];
"""
REC_IN_JS = r"""// 조치 결과를 티켓에 기록(stage applied). 중복 방지 키: {실행 ID}-applied-%I%
const r = $input.first().json;
const x = r.ctx;
if (r.result === 'skipped') return [{ json: { ctx: x, mode: 'record', stage: 'detected', seat: x.seat, case_id: x.case_id, group_key: x.group_key,
  asset_id: x.asset_id, src_ip: x.src_ip || null, username: x.username || null, event_ids: [x.event_id], idempotency_key: `${$execution.id}-skip-%I%` } }];
const res = { step: %I%, result: r.result, detail: r.detail };
return [{ json: { ctx: { ...x, results: [...(x.results || []), res] }, mode: 'record', stage: 'applied', seat: x.seat, case_id: x.case_id, group_key: x.group_key, title: x.title,
  asset_id: x.asset_id, src_ip: x.src_ip || null, username: x.username || null, event_ids: [x.event_id], idempotency_key: `${$execution.id}-applied-%I%`,
  action: { bot: '%BOT%', target: %TARGET%, via: '%VIA%', action: %ACT%, result: r.result,
    applied_verified: r.result === 'dry_run' ? null : (r.applied_verified ?? null), effect_verified: null, effect_verified_at: null,
    requested_at: r.requested_at, finished_at: r.finished_at, n8n_execution_id: String($execution.id), detail: r.detail } } }];
"""
NOTE_JS = r"""const r = $input.first().json;
const x = r.ctx;
const bad = (x.results || []).some(s => ['failed', 'rejected'].includes(s.result));
return [{ json: { ctx: { ...x, ticket: { ok: r.ok, ticket_id: r.ticket_id, status: r.status } }, level: bad ? 'error' : 'warn', case_id: x.case_id, title: x.title,
  src_ip: x.src_ip || undefined, ticket_id: r.ticket_id, result: (x.results || []).map(s => s.result).join(', '),
  detail: (x.username ? `계정 ${x.username} ` : '') + (x.file_key ? `파일 ${x.file_key} ` : '') + (x.results || []).map(s => s.detail).join(' / ') } }];
"""
FINAL_JS = r"""const r = $input.first().json;
const x = r.ctx;
return [{ json: { ok: true, verdict: 'responded', case_id: x.case_id, event_id: x.event_id, asset_id: x.asset_id, src_ip: x.src_ip || null, username: x.username || null,
  steps: x.results, ticket: x.ticket, discord_sent: r.sent, discord_error: r.error, n8n_execution_id: $execution.id } }];
"""
STOREFAIL_JS = r"""// 티켓 저장(detected)이 실패하면 조치를 하지 않는다. 기록 없는 차단을 막기 위해 조치 노드 앞에서 중단한다.
const r = $input.first().json;
const x = r.ctx || {};
return [{ json: { ok: false, verdict: 'ticket_store_failed_no_action', case_id: x.case_id, event_id: x.event_id, src_ip: x.src_ip || null, username: x.username || null,
  error: { code: (r.error && r.error.code) || 'STORE_FAILED' }, no_action: true, n8n_execution_id: $execution.id } }];
"""
NOACT_JS = r"""const j = $input.first().json;
return [{ json: { ...j, no_action: true, n8n_execution_id: $execution.id } }];
"""


def case_workflow(wid, name, path, validate_js, steps, fname, caller_credential=None, store_gate=True):
    """steps: [{label, wf, bot, via, act, target_js, input_js}] — input_js는 `x`(검증 컨텍스트)로 하위 워크플로 입력 속성을 만든다.
    caller_credential: 주면 웹훅에 헤더 인증을 건다(n8n httpHeaderAuth 자격 증명 이름). 반입 뒤 D가 연결하기 전에는 게시되지 않는다."""
    hook = {"httpMethod": "POST", "path": path, "responseMode": "responseNode", "options": {}}
    extra = {"webhookId": path}
    if caller_credential:
        hook["authentication"] = "headerAuth"
        extra["credentials"] = {"httpHeaderAuth": {"id": "", "name": caller_credential}}
    nodes = [
        node("Webhook", "n8n-nodes-base.webhook", hook, [0, 0], 2, **extra),
        code("입력 검증·설정", validate_js, [240, 0]),
        if_bool("대응 대상?", "$json.proceed === true", [480, 0]),
        execwf("중복 확인 (haedam-10 check)", "haedamResultLog01", [720, -60]),
        code("중복 판정", DEDUP_JS, [960, -60]),
        if_bool("중복 아님?", "$json.proceed === true", [1200, -60]),
        code("티켓 detected 입력", DETECTED_JS, [1440, -140]),
        execwf("티켓 detected (haedam-10)", "haedamResultLog01", [1680, -140]),
    ]
    if store_gate:
        nodes += [if_bool("티켓 저장됨?", "$json.ok === true", [1800, -140]),
                  code("저장 실패 응답", STOREFAIL_JS, [1920, 140]),
                  respond("응답: 저장 실패(조치 없음)", [2160, 140])]
    conns = {"Webhook": [["입력 검증·설정"]], "입력 검증·설정": [["대응 대상?"]],
             "대응 대상?": [["중복 확인 (haedam-10 check)"], ["대응 없음 응답"]],
             "중복 확인 (haedam-10 check)": [["중복 판정"]], "중복 판정": [["중복 아님?"]],
             "중복 아님?": [["티켓 detected 입력"], ["대응 없음 응답"]],
             "티켓 detected 입력": [["티켓 detected (haedam-10)"]]}
    if store_gate:
        conns["티켓 detected (haedam-10)"] = [["티켓 저장됨?"]]
        conns["저장 실패 응답"] = [["응답: 저장 실패(조치 없음)"]]
    prev = "티켓 저장됨?" if store_gate else "티켓 detected (haedam-10)"
    x = 2040 if store_gate else 1920
    for i, s in enumerate(steps, 1):
        n_in = f"조치{i} 입력 ({s['label']})"
        n_run = f"조치{i} ({s['label']})"
        n_rec_in = f"조치{i} 기록 입력"
        n_rec = f"조치{i} 기록 (haedam-10)"
        rec_js = (REC_IN_JS.replace("%I%", str(i)).replace("%BOT%", s["bot"]).replace("%VIA%", s["via"])
                  .replace("%ACT%", s["act"]).replace("%TARGET%", s["target_js"]))
        nodes += [code(n_in, STEP_IN_JS.replace("%INPUT%", s["input_js"]), [x, -140]),
                  execwf(n_run, WF_ID[s["wf"]], [x + 240, -140]),
                  code(n_rec_in, rec_js, [x + 480, -140]),
                  execwf(n_rec, "haedamResultLog01", [x + 720, -140])]
        conns[prev] = [[n_in], ["저장 실패 응답"]] if (i == 1 and store_gate) else [[n_in]]
        conns[n_in] = [[n_run]]
        conns[n_run] = [[n_rec_in]]
        conns[n_rec_in] = [[n_rec]]
        prev = n_rec
        x += 960
    nodes += [code("알림 입력", NOTE_JS, [x, -140]), execwf("Discord 알림 (haedam-11)", "haedamDiscord01", [x + 240, -140]),
              code("최종 응답", FINAL_JS, [x + 480, -140]), respond("응답: 대응", [x + 720, -140]),
              code("대응 없음 응답", NOACT_JS, [1440, 140]), respond("응답: 대응 없음", [1680, 140])]
    conns[prev] = [["알림 입력"]]
    conns["알림 입력"] = [["Discord 알림 (haedam-11)"]]
    conns["Discord 알림 (haedam-11)"] = [["최종 응답"]]
    conns["최종 응답"] = [["응답: 대응"]]
    conns["대응 없음 응답"] = [["응답: 대응 없음"]]
    save(fname, wf(wid, name, nodes, conns))


CFG = "const CFG = { dry_run: true, store_real: false };   // 기본은 관찰 모드. 실제 티켓 기록은 케이스별로 본문 store_real:true일 때만(11/03 D), 실제 조치는 dry_run:false + 별도 승인\n"

# ------------------------------------------------------------ S1
V_S1 = PROTECT_JS + CFG + r"""// S1 로그인 반복 실패(무차별 대입): count()>8 · 30분 · username + src_ip (A, 임계는 기획서 값, 측정 전)
const t = { ...($input.first().json.body || {}) };
const missing = ['event_id', 'asset_id', 'src_ip', 'username'].filter(k => !t[k]);
if (missing.length) return [{ json: { ok: false, verdict: 'invalid_input', missing } }];
const p = protectedIp(t.src_ip);
if (p) return [{ json: { ok: true, verdict: 'protected_source', reason: p, case_id: 'S1', event_id: t.event_id, src_ip: t.src_ip } }];
if (t.dry_run === false) CFG.dry_run = false;   // 실제 포털 차단은 Graylog 알림 본문의 dry_run:false로만 켠다(기본 true). 켜기 전 D 명시 승인(10/28)
if (t.store_real === true) CFG.store_real = true;   // 실제 티켓 기록(C 저장소)은 본문의 store_real:true(불리언)로만 켠다(기본 false). 케이스별 회차에서만 사용
const X = { seat: 'A', case_id: 'S1', title: 'S1 로그인 반복 실패(무차별 대입)', event_id: t.event_id, asset_id: t.asset_id, src_ip: t.src_ip, username: t.username,
  count: t.count ?? null, group_key: t.username, cfg: CFG, expected: [{ bot: '112', via: 'portal', action: 'block', target: t.src_ip }] };
return [{ json: { proceed: true, mode: 'check', seat: 'A', group_key: t.username, ctx: X } }];
"""
case_workflow("haedamS1Main01", "haedam-30 S1 계정 탈취 시도 → 출발지 차단 (A)", "haedam-s1", V_S1,
              [{"label": "포털 IP 차단", "wf": "112", "bot": "112", "via": "portal", "act": "'block'", "target_js": "x.src_ip",
                "input_js": "action: 'block', ip: x.src_ip"}], "haedam-30-s1-main.json", caller_credential="haedam-s1 caller")

# ------------------------------------------------------------ S4
V_S4 = CFG + r"""// S4 실패 뒤 성공: 실패·성공 합산 count()>5 · 10분 · username + src_ip (A). 순서 요구 없음.
const t = { ...($input.first().json.body || {}) };
const missing = ['event_id', 'asset_id', 'username'].filter(k => !t[k]);
if (missing.length) return [{ json: { ok: false, verdict: 'invalid_input', missing } }];
if (t.store_real === true) CFG.store_real = true;   // 실제 티켓 기록(C 저장소)은 본문의 store_real:true(불리언)로만 켠다(기본 false). 케이스별 회차에서만 사용
if (t.dry_run === false) {   // 실제 계정 잠금은 본문의 dry_run:false(불리언)로만 켠다(기본 true). 회차마다 D 명시 승인 후에만 사용
  if (!/^zz_[a-z0-9_]{1,40}$/.test(String(t.username))) return [{ json: { ok: true, verdict: 'protected_account', reason: 'live_lock_test_accounts_only', case_id: 'S4', event_id: t.event_id, username: t.username } }];   // 실제 잠금은 시험 계정(zz_)만
  CFG.dry_run = false;
}
const X = { seat: 'A', case_id: 'S4', title: 'S4 실패 뒤 성공(계정 탈취 의심)', event_id: t.event_id, asset_id: t.asset_id, src_ip: t.src_ip || null, username: t.username,
  count: t.count ?? null, group_key: t.username, cfg: CFG, expected: [{ bot: '111', via: 'portal', action: 'lock', target: t.username }] };
return [{ json: { proceed: true, mode: 'check', seat: 'A', group_key: t.username, ctx: X } }];
"""
case_workflow("haedamS4Main01", "haedam-31 S4 계정 탈취 의심 → 계정 잠금·세션 회수 (A)", "haedam-s4", V_S4,
              [{"label": "포털 계정 잠금", "wf": "111", "bot": "111", "via": "portal", "act": "'lock'", "target_js": "x.username",
                "input_js": "action: 'lock', username: x.username"}], "haedam-31-s4-main.json", caller_credential="haedam-s4 caller")

# ------------------------------------------------------------ S8 / S10
V_S810 = PROTECT_JS + CFG + r"""// S8 web-scan + login-bruteforce(card(rule)>1) / S10 pfsense-block 추가(card(rule)>2) · 15분 · src_ip (B). 같은 출발지는 한 티켓(자리 B)을 같이 쓴다.
const t = { ...($input.first().json.body || {}) };
const missing = ['event_id', 'asset_id', 'src_ip', 'case_id'].filter(k => !t[k]);
if (missing.length) return [{ json: { ok: false, verdict: 'invalid_input', missing } }];
if (!['S8', 'S10'].includes(t.case_id)) return [{ json: { ok: false, verdict: 'invalid_input', detail: 'case_id must be S8 or S10' } }];
const p = protectedIp(t.src_ip);
if (p) return [{ json: { ok: true, verdict: 'protected_source', reason: p, case_id: t.case_id, event_id: t.event_id, src_ip: t.src_ip } }];
if (t.dry_run === false) CFG.dry_run = false;   // 실제 포털·pfSense 차단은 본문의 dry_run:false(불리언)로만 켠다(기본 true). 회차마다 D 명시 승인 후에만 사용
if (t.store_real === true) CFG.store_real = true;   // 실제 티켓 기록(C 저장소)은 본문의 store_real:true(불리언)로만 켠다(기본 false). 케이스별 회차에서만 사용
const expected = [{ bot: '112', via: 'portal', action: 'block', target: t.src_ip }];
if (t.case_id === 'S10') expected.push({ bot: '112', via: 'pfsense', action: 'fw_block', target: t.src_ip });
const X = { seat: 'B', case_id: t.case_id, title: t.case_id === 'S10' ? 'S10 스캔 → 침입 연쇄(경계 차단 포함)' : 'S8 포털 스캔·로그인 반복',
  event_id: t.event_id, asset_id: t.asset_id, src_ip: t.src_ip, count: t.count ?? null, group_key: t.src_ip, cfg: CFG, expected };
return [{ json: { proceed: true, mode: 'check', seat: 'B', group_key: t.src_ip, ctx: X } }];
"""
case_workflow("haedamS8S10Main01", "haedam-32 S8·S10 스캔 → 침입 연쇄 → 앱 차단 + pfSense 차단 (B)", "haedam-s8-s10", V_S810,
              [{"label": "포털 IP 차단", "wf": "112", "bot": "112", "via": "portal", "act": "'block'", "target_js": "x.src_ip",
                "input_js": "action: 'block', ip: x.src_ip"},
               {"label": "pfSense 차단", "wf": "pfsense", "bot": "112", "via": "pfsense", "act": "'fw_block'", "target_js": "x.src_ip",
                "input_js": "action: x.case_id === 'S10' ? 'block' : 'skip', ip: x.src_ip"}], "haedam-32-s8-s10-main.json", caller_credential="haedam-s8-s10 caller")

# ------------------------------------------------------------ S7
CFG_S7 = "const CFG = { dry_run: true, store_real: true };   // S7: 실제 조치는 dry_run, 티켓·결과는 C 저장소에 실제 기록(11/02 D 결정)\n"
V_S7 = CFG_S7 + r"""// S7 FIM + 같은 경로 접근: card(signal_kind)>1 · 10분 · asset_id + file_key (C). 바뀐 파일은 원본 복구, 새 파일은 격리(117).
const t = { ...($input.first().json.body || {}) };
const missing = ['event_id', 'asset_id', 'file_key'].filter(k => !t[k]);
if (missing.length) return [{ json: { ok: false, verdict: 'invalid_input', missing } }];
const change = t.change_type === 'added' ? 'added' : 'modified';
const group = `${t.asset_id}:${t.file_key}`;
const X = { seat: 'C', case_id: 'S7', title: 'S7 홈페이지 파일 변조', event_id: t.event_id, asset_id: t.asset_id, src_ip: t.src_ip || null, file_key: t.file_key,
  change_type: change, group_key: group, cfg: CFG, expected: [{ bot: '117', via: 'wazuh-ar', action: change === 'added' ? 'quarantine' : 'restore', target: t.file_key }] };   // action.target은 파일 키만, group_key는 {asset_id}:{file_key}(C·B 합의 10/26)
return [{ json: { proceed: true, mode: 'check', seat: 'C', group_key: group, ctx: X } }];
"""
case_workflow("haedamS7Main01", "haedam-33 S7 홈페이지 변조 → 원본 복구·새 파일 격리 (C)", "haedam-s7", V_S7,
              [{"label": "Wazuh 복구·격리", "wf": "117", "bot": "117", "via": "wazuh-ar",
                "act": "x.change_type === 'added' ? 'quarantine' : 'restore'", "target_js": "x.file_key",
                "input_js": "action: x.change_type === 'added' ? 'quarantine' : 'restore', asset_id: x.asset_id, file_key: x.file_key"}],
              "haedam-33-s7-main.json", caller_credential="haedam-s7 caller", store_gate=False)   # 티켓 실기록(store_real) 경로라 호출자 인증 필수(11/02 B·C)
print("cases ok")

# ------------------------------------------------------------ haedam-01 티켓 저장소 연결 확인 (읽기 전용)
R01 = r"""// 티켓 저장소(C) 연결·키 확인용. 읽기(check)만 하고 아무것도 기록하지 않는다. 키는 n8n 자격 증명에만 있다.
const b = ($input.first().json.body) || {};
return [{ json: { mode: 'check', seat: b.seat || 'D', group_key: b.group_key || '__connectivity_check__', ctx: { cfg: { dry_run: false, store_real: true }, purpose: 'connectivity_check' } } }];
"""
w01 = wf("haedamTicketCheck01", "haedam-01 티켓 저장소 연결 확인 (읽기 전용)",
         [node("Webhook", "n8n-nodes-base.webhook", {"httpMethod": "POST", "path": "haedam-ticket-check", "responseMode": "responseNode", "options": {}},
               [0, 0], 2, webhookId="haedam-ticket-check"),
          code("check 입력", R01, [240, 0]), execwf("haedam-10 (실제 저장소 check)", "haedamResultLog01", [480, 0]),
          respond("응답", [720, 0])],
         {"Webhook": [["check 입력"]], "check 입력": [["haedam-10 (실제 저장소 check)"]], "haedam-10 (실제 저장소 check)": [["응답"]]})
save("haedam-01-ticket-check.json", w01)
