"""2단계 생성기: 시각 필드, 반영 확인, 효과 확인(effect), 사람 승인 원복(released).
gen_n8n_workflows.py → gen_n8n_cases.py가 만든 JSON을 읽어 노드를 추가·수정하고 새 워크플로(haedam-40 효과 보고, haedam-50 원복)를 만든다.
실행: cd tools && python gen_n8n_workflows.py && python gen_n8n_cases.py && python gen_n8n_actions.py && python gen_n8n_stage2.py
모든 조치는 dry_run 기본이다. 비밀값은 넣지 않는다."""
import json

import gen_n8n_workflows as g
from gen_n8n_workflows import PORTAL, OUT, code, execwf, exectrig, if_bool, node, respond, save, wf


def load(fname):
    return json.loads((OUT / fname).read_text(encoding="utf-8"))


def find(w, name):
    for n in w[0]["nodes"]:
        if n["name"] == name:
            return n
    raise KeyError(name)


def rep(n, old, new, count=1):
    js = n["parameters"]["jsCode"]
    assert js.count(old) >= 1, f"{n['name']}: pattern not found: {old[:60]}"
    n["parameters"]["jsCode"] = js.replace(old, new) if count == 0 else js.replace(old, new, count)


def conn(w, src, outs):
    w[0]["connections"][src] = {"main": [[{"node": t, "type": "main", "index": 0} for t in o] for o in outs]}


# ------------------------------------------------------------ T1 시각 필드 (first_attack_at, condition_met_at, detected_at, received_at)
T_DEF = r"""const iso = (v) => (typeof v === 'string' && /T.*(Z|[+-]\d\d:?\d\d)$/.test(v)) ? v : null;
const T = { first_attack_at: iso(t.first_attack_at), condition_met_at: iso(t.condition_met_at), received_at: new Date().toISOString() };"""
TIMES_DETECTED = ("first_attack_at: x.times ? x.times.first_attack_at : null, condition_met_at: x.times ? x.times.condition_met_at : null, "
                  "detected_at: new Date().toISOString(), received_at: x.times ? x.times.received_at : null,\n  idempotency_key: `${$execution.id}-detected`")
MAINS = ["haedam-20-s12-main.json", "haedam-30-s1-main.json", "haedam-31-s4-main.json", "haedam-32-s8-s10-main.json", "haedam-33-s7-main.json"]
for f in MAINS:
    w = load(f)
    v = find(w, "입력 검증·설정")
    rep(v, "const t = { ...($input.first().json.body || {}) };", "const t = { ...($input.first().json.body || {}) };\n" + T_DEF)
    rep(v, "cfg: CFG", "cfg: CFG, times: T")
    rep(find(w, "티켓 detected 입력"), "idempotency_key: `${$execution.id}-detected`", TIMES_DETECTED)
    if f == "haedam-20-s12-main.json":
        rep(v, "dry_run: true,", "recover_timeout_ms: 60000, dry_run: true,")   # #73: dry_run 뒤에 store_real이 붙어 쉼표로 끝난다
        rep(v, "if (CFG.dry_run && typeof t.test_baseline_ms === 'number') CFG.baseline_ms = t.test_baseline_ms;",
            "if (CFG.dry_run && typeof t.test_baseline_ms === 'number') CFG.baseline_ms = t.test_baseline_ms;\nif (CFG.dry_run && t.test_effect === true) CFG.test_effect = true;   // 시험 전용: dry_run에서도 효과 확인 단계를 돌려 본다")
    w[0]["nodes"] = w[0]["nodes"]
    save(f, w)

# haedam-10: record 본문에 시각 필드, check는 seat 없이도(다른 자리 티켓), active 조치 계산
w10 = load("haedam-10-result-log.json")
rep(find(w10, "저장소 요청 만들기"), "asset_id: b.asset_id, src_ip: b.src_ip || null, username: b.username || null, event_ids: b.event_ids || [],",
    "asset_id: b.asset_id, src_ip: b.src_ip || null, username: b.username || null, event_ids: b.event_ids || [],\n  first_attack_at: b.first_attack_at ?? null, condition_met_at: b.condition_met_at ?? null, detected_at: b.detected_at ?? null, received_at: b.received_at ?? null,")
for nm in ("응답 변환 1", "응답 변환 2"):
    rep(find(w10, nm), "  if (prev.mode === 'check') {",
        "  if (prev.mode === 'check' && body.tickets) return [{ json: { retry: false, ok: true, mode: 'check', tickets: body.tickets, ctx } }];\n  if (prev.mode === 'check') {")
ph = find(w10, "check/record (자리표시 저장소)")
js = ph["parameters"]["jsCode"]
a = js.index("if (b.mode === 'check') {")
b = js.index("// record")
NEW_CHECK = r"""const activeOf = (t) => {   // 같은 (bot, action, target)의 applied 중 같은 bot·target으로 released 되지 않은 것
  const act = {};
  for (const a of t.actions) {
    const k = a.bot + '|' + a.action + '|' + a.target;
    if (['applied', 'already_applied', 'dry_run'].includes(a.result)) act[k] = a;   // 자리표시 저장소는 dry_run 전용이라 dry_run 줄도 해제 시험이 되게 활성으로 본다
    else if (a.result === 'released') for (const kk of Object.keys(act)) if (kk.startsWith(a.bot + '|') && act[kk].target === a.target) delete act[kk];
  }
  return Object.values(act);
};
if (b.mode === 'check') {
  if (!b.seat) {   // 모든 자리의 열린 티켓과 해제 안 된 조치(원복 보류 판단용)
    const list = tickets.filter(t => t.group_key === b.group_key && t.status !== 'closed').map(t => ({ seat: t.seat, ticket_id: t.ticket_id, status: t.status,
      active_actions: activeOf(t).map(a => ({ bot: a.bot, action: a.action, target: a.target, via: a.via })) }));
    return out({ ok: true, mode: 'check', tickets: list });
  }
  const other = tickets.filter(t => t.group_key === b.group_key && t.seat !== b.seat && t.status !== 'closed' && t.status !== 'restored').map(t => t.ticket_id);
  return out({ ok: true, mode: 'check', exists: !!open, ticket_id: open ? open.ticket_id : null,
    status: open ? open.status : null, actions: open ? activeOf(open) : [], other_seat_open: other });
}

"""
js = js[:a] + NEW_CHECK + js[b:]
js = js.replace("for (const k of ['seat', 'group_key']) if (!b[k]) return fail('VALIDATION_ERROR', 'missing ' + k);",
                "if (!b.group_key) return fail('VALIDATION_ERROR', 'missing group_key');\nif (b.mode === 'record' && !b.seat) return fail('VALIDATION_ERROR', 'missing seat');")
ph["parameters"]["jsCode"] = js
save("haedam-10-result-log.json", w10)

# ------------------------------------------------------------ T2 haedam-12: 반영 확인(applied_verified)과 skip
w12 = load("haedam-12-portal-ip-block.json")
rep(find(w12, "요청 준비"), "if (!['block', 'unblock', 'list'].includes(action))",
    "if (action === 'skip') return [{ json: { result: 'skipped', detail: 'not applicable', stop: true, ctx } }];\nif (!['block', 'unblock', 'list'].includes(action))")
w12[0]["nodes"] += [
    if_bool("반영 확인 필요?", "['applied', 'already_applied', 'released'].includes($json.result) && ['block', 'unblock'].includes($json.action)", [2400, 180]),
    node("차단 목록 조회", "n8n-nodes-base.httpRequest", {
        "method": "GET", "url": PORTAL + "/api/v1/response/ips",
        "authentication": "genericCredentialType", "genericAuthType": "httpHeaderAuth",
        "options": {"timeout": 5000, "response": {"response": {"fullResponse": True, "neverError": True}}}},
        [2640, 100], 4.2, onError="continueRegularOutput"),
    code("반영 확인 판정", r"""// 반영 확인(applied_verified): 차단은 목록에 있어야, 해제는 목록에 없어야 한다. 목록을 못 읽으면 null(미확인).
const j = $input.first().json;
const prev = $('최종 결과').first().json;
const items = (j.statusCode === 200 && j.body && j.body.data && j.body.data.items) || null;
let v = null, note = '';
if (items) { const has = items.some(i => i.ip === prev.ip); v = prev.action === 'block' ? has : !has; }
else note = ' / list_unavailable:' + (j.statusCode ?? 'no_response');
return [{ json: { ...prev, applied_verified: v, detail: (prev.detail || '') + (v === null ? note : v ? ' / listed' : ' / list_mismatch') } }];
""", [2880, 100])]
conn(w12, "최종 결과", [["반영 확인 필요?"]])
conn(w12, "반영 확인 필요?", [["차단 목록 조회"], []])
conn(w12, "차단 목록 조회", [["반영 확인 판정"]])
save("haedam-12-portal-ip-block.json", w12)

# haedam-14·15는 gen_n8n_actions.py가 실제 호출 노드로 다시 만든다(해제 포함).

# ------------------------------------------------------------ T3 haedam-20: 회복 확인(effect)
w20 = load("haedam-20-s12-main.json")
R_RECOVER = r"""// 회복 확인(116): 차단 뒤 정상 경로(D→A 팀 VPN 헬스체크)가 기준선 안으로 돌아오는지 K회 연속 확인, 제한 시간 안에.
// 응답은 이미 돌려줬다(이 가지는 응답 뒤에 계속 돈다). 공격 출발지가 실제로 막혔는지는 시험 스크립트(기획서 5.4)가 확인한다.
const x = $input.first().json.ctx;
const c = x.cfg;
if (c.baseline_ms === null) return [{ json: { noop: true, ctx: x } }];
const deadline = Date.now() + (c.recover_timeout_ms || 60000);
let streak = 0;
const samples = [];
while (Date.now() < deadline && streak < c.health_k) {
  const t0 = Date.now();
  let ok = false, st = null;
  try {
    const r = await this.helpers.httpRequest({ method: 'GET', url: c.health_url, timeout: c.health_timeout_ms, returnFullResponse: true, ignoreHttpStatusCodes: true });
    st = r.statusCode; ok = st < 500 && (Date.now() - t0) <= c.baseline_ms;
  } catch (e) { ok = false; }
  samples.push({ ms: Date.now() - t0, status: st, ok });
  streak = ok ? streak + 1 : 0;
  if (streak < c.health_k) await new Promise(r => setTimeout(r, c.health_interval_ms));
}
const recovered = streak >= c.health_k;
return [{ json: { noop: false, recovered, ctx: { ...x, recovery: { recovered, samples: samples.slice(-10) } } } }];
"""
R_EFFECT_IN = r"""const r = $input.first().json;
const x = r.ctx;
const now = new Date().toISOString();
return [{ json: { ctx: x, mode: 'record', stage: 'effect', seat: x.cfg.seat, case_id: x.cfg.case_id, group_key: x.src_ip, title: '포털 요청 폭주로 응답 지연',
  asset_id: x.asset_id, src_ip: x.src_ip, event_ids: [x.event_id], idempotency_key: `${$execution.id}-effect`,
  action: { bot: '112', target: x.src_ip, via: 'portal', action: 'block', result: 'applied', applied_verified: (x.block && x.block.applied_verified) ?? null,
    effect_verified: r.recovered, effect_verified_at: now, requested_at: now, finished_at: now, n8n_execution_id: String($execution.id),
    detail: `회복 ${r.recovered ? '확인' : '실패'}(연속 ${x.cfg.health_k}회, 기준선 ${x.cfg.baseline_ms}ms)` } } }];
"""
R_EFFECT_NOTE = r"""const r = $input.first().json;
const x = r.ctx;
const rec = x.recovery || {};
return [{ json: { ctx: x, level: rec.recovered ? 'info' : 'error', case_id: 'S12', title: rec.recovered ? '서비스 회복 확인' : '회복 확인 실패(효과 검증 실패)', src_ip: x.src_ip,
  ticket_id: r.ticket_id, result: rec.recovered ? 'effect_verified' : 'effect_failed', detail: `기준선 ${x.cfg.baseline_ms}ms, 연속 ${x.cfg.health_k}회` } }];
"""
w20[0]["nodes"] += [
    if_bool("효과 확인 대상?", "$json.ctx.block && ($json.ctx.block.result === 'applied' || $json.ctx.block.result === 'already_applied' || ($json.ctx.cfg.test_effect === true && $json.ctx.block.result === 'dry_run'))", [3840, 80]),
    code("회복 확인", R_RECOVER, [4080, 80]),
    if_bool("기록할 효과?", "$json.noop !== true", [4320, 80]),
    code("효과 기록 입력", R_EFFECT_IN, [4560, 0]),
    execwf("효과 기록 (haedam-10 effect)", "haedamResultLog01", [4800, 0]),
    code("효과 알림 입력", R_EFFECT_NOTE, [5040, 0]),
    execwf("효과 알림 (haedam-11)", "haedamDiscord01", [5280, 0])]
conn(w20, "Discord 알림 (haedam-11)", [["최종 응답", "효과 확인 대상?"]])
conn(w20, "효과 확인 대상?", [["회복 확인"], []])
conn(w20, "회복 확인", [["기록할 효과?"]])
conn(w20, "기록할 효과?", [["효과 기록 입력"], []])
conn(w20, "효과 기록 입력", [["효과 기록 (haedam-10 effect)"]])
conn(w20, "효과 기록 (haedam-10 effect)", [["효과 알림 입력"]])
conn(w20, "효과 알림 입력", [["효과 알림 (haedam-11)"]])
save("haedam-20-s12-main.json", w20)

# ------------------------------------------------------------ T4 haedam-40 효과 확인 보고 (시험 스크립트·사람이 결과를 알려 주는 입구)
R40 = r"""// 효과 확인 보고 수신: 각 자리의 시험 스크립트(공격 출발지가 403을 받는지 등)나 사람이 결과를 보내면 티켓의 해당 조치 줄에 effect를 기록한다.
const b = $input.first().json.body || {};
const CFG = { dry_run: true };   // 실제 티켓 저장소에 쓰려면 false (A·C 연결 뒤)
const need = ['seat', 'case_id', 'group_key', 'asset_id', 'bot', 'via', 'action', 'target'];
const missing = need.filter(k => !b[k]);
if (missing.length || typeof b.effect_verified !== 'boolean') return [{ json: { ok: false, error: { code: 'VALIDATION_ERROR', message: 'missing: ' + missing.concat(typeof b.effect_verified !== 'boolean' ? ['effect_verified(boolean)'] : []).join(',') } , bad: true } }];
const now = new Date().toISOString();
return [{ json: { ctx: { cfg: CFG, reporter: b.reporter || null }, mode: 'record', stage: 'effect', seat: b.seat, case_id: b.case_id, group_key: b.group_key,
  title: b.title || `${b.case_id} 효과 확인`, asset_id: b.asset_id, src_ip: b.src_ip || null, username: b.username || null,
  event_ids: [b.event_id || `effect-${$execution.id}`], idempotency_key: `${$execution.id}-effect`,
  action: { bot: String(b.bot), target: b.target, via: b.via, action: b.action, result: 'applied', applied_verified: b.applied_verified ?? null,
    effect_verified: b.effect_verified, effect_verified_at: b.effect_verified_at || now, requested_at: now, finished_at: now,
    n8n_execution_id: String($execution.id), detail: String(b.detail || '').slice(0, 300) } } }];
"""
R40out = r"""const r = $input.first().json;
if (r.bad) return [{ json: r }];
return [{ json: { ok: r.ok, ticket_id: r.ticket_id || null, status: r.status || null, error: r.error || null, n8n_execution_id: $execution.id } }];
"""
w40 = wf("haedamEffectReport01", "haedam-40 효과 확인 보고 수신",
         [node("Webhook", "n8n-nodes-base.webhook", {"httpMethod": "POST", "path": "haedam-effect-report", "responseMode": "responseNode", "options": {}}, [0, 0], 2, webhookId="haedam-effect-report"),
          code("보고 검증·기록 입력", R40, [240, 0]), if_bool("검증 통과?", "$json.bad !== true", [480, 0]),
          execwf("효과 기록 (haedam-10 effect)", "haedamResultLog01", [720, -60]),
          code("응답 정리", R40out, [960, 0]), respond("응답", [1200, 0])],
         {"Webhook": [["보고 검증·기록 입력"]], "보고 검증·기록 입력": [["검증 통과?"]], "검증 통과?": [["효과 기록 (haedam-10 effect)"], ["응답 정리"]],
          "효과 기록 (haedam-10 effect)": [["응답 정리"]], "응답 정리": [["응답"]]})
save("haedam-40-effect-report.json", w40)

# ------------------------------------------------------------ T4 haedam-50 원복(해제): 사람이 확인한 뒤에만
R50a = r"""// 원복(해제)은 자동으로 하지 않는다. 사람이 확인한 뒤 approver(이름)와 함께 부른다. 순서: 경계(pfSense) → 앱(포털).
const b = $input.first().json.body || {};
const CFG = { dry_run: true };   // 실제 해제는 포털 키·pfSense 수단이 정해진 뒤 false
const need = ['seat', 'case_id', 'group_key', 'approver'];
const missing = need.filter(k => !b[k] || typeof b[k] !== 'string');
if (missing.length) return [{ json: { ok: false, verdict: 'invalid_input', missing, stop: true } }];
if (!['A', 'B', 'C', 'D'].includes(b.seat)) return [{ json: { ok: false, verdict: 'invalid_input', detail: 'seat', stop: true } }];
const X = { seat: b.seat, case_id: b.case_id, group_key: b.group_key, approver: b.approver.slice(0, 40), asset_id: b.asset_id || 'haedam-portal', cfg: CFG, reason: b.reason ? String(b.reason).slice(0, 200) : null };
return [{ json: { mode: 'check', seat: b.seat, group_key: b.group_key, ctx: X, stop: false } }];
"""
R50pick = r"""// 해제할 조치 고르기: 열린 티켓의 반영된 차단(112)만 자동 해제한다. 계정 잠금(111)·파일 복구(117)는 사람이 직접 한다.
const j = $input.first().json;
const x = j.ctx;
if (!j.ok || !j.exists) return [{ json: { ok: true, verdict: 'no_open_ticket', no_action: true, case_id: x.case_id, group_key: x.group_key } }];
const acts = j.actions || [];
const ips = [...new Set(acts.filter(a => a.bot === '112' && ['block', 'fw_block'].includes(a.action)).map(a => a.target))];
const manual = acts.filter(a => !(a.bot === '112' && ['block', 'fw_block'].includes(a.action))).map(a => `${a.bot}:${a.action}:${a.target}`);
if (ips.length === 0) return [{ json: { ok: true, verdict: 'nothing_to_release', no_action: true, ticket_id: j.ticket_id, manual_required: manual } }];
if (ips.length > 1) return [{ json: { ok: true, verdict: 'multiple_targets_manual', no_action: true, ticket_id: j.ticket_id, targets: ips } }];
const ip = ips[0];
const hasFw = acts.some(a => a.bot === '112' && a.action === 'fw_block' && a.target === ip);
const hasApp = acts.some(a => a.bot === '112' && a.action === 'block' && a.target === ip);
return [{ json: { mode: 'check', group_key: ip, ctx: { ...x, ticket_id: j.ticket_id, ip, hasFw, hasApp, manual_required: manual } } }];
"""
R50hold = r"""// 보류 판정: 같은 IP를 막고 있는 다른 자리의 열린 티켓이 있으면 해제하지 않는다(해제는 케이스와 관계없이 그 IP를 푼다).
const j = $input.first().json;
const x = j.ctx;
const others = (j.tickets || []).filter(t => t.seat !== x.seat && (t.active_actions || []).some(a => a.bot === '112' && a.target === x.ip));
if (!j.ok) return [{ json: { ok: false, verdict: 'hold_check_failed', error: j.error, no_action: true, ticket_id: x.ticket_id } }];
if (others.length) return [{ json: { ok: true, verdict: 'held_other_seat_ticket', no_action: true, ticket_id: x.ticket_id, ip: x.ip, other_tickets: others.map(t => t.ticket_id) } }];
return [{ json: { proceed: true, ctx: x } }];
"""
R50step = r"""const r = $input.first().json;
const x = r.ctx;
const ticket_id = x.ticket_id;
return [{ json: { ctx: x, ticket_id, dry_run: x.cfg.dry_run, %INPUT% } }];
"""
R50rec = r"""// 해제 결과를 티켓에 기록(stage released). 실패하면 기록하지 않고 중단 표시.
const r = $input.first().json;
const x = r.ctx;
if (r.result === 'skipped') return [{ json: { ctx: x, mode: 'record', stage: 'detected', seat: x.seat, case_id: x.case_id, group_key: x.group_key, title: x.title || x.case_id,
  asset_id: x.asset_id, event_ids: [`release-skip-${$execution.id}-%I%`], idempotency_key: `${$execution.id}-skip-%I%` } }];
const ok = ['released', 'already_applied', 'dry_run'].includes(r.result);
const res = { step: %I%, result: ok ? 'released' : r.result, detail: r.detail };
if (!ok) return [{ json: { ctx: { ...x, abort: true, results: [...(x.results || []), res] }, mode: 'record', stage: 'detected', seat: x.seat, case_id: x.case_id, group_key: x.group_key,
  title: x.title || x.case_id, asset_id: x.asset_id, event_ids: [`release-fail-${$execution.id}-%I%`], idempotency_key: `${$execution.id}-fail-%I%` } }];
const now = new Date().toISOString();
return [{ json: { ctx: { ...x, results: [...(x.results || []), res] }, mode: 'record', stage: 'released', seat: x.seat, case_id: x.case_id, group_key: x.group_key, title: x.title || x.case_id,
  asset_id: x.asset_id, event_ids: [`release-${$execution.id}-%I%`], idempotency_key: `${$execution.id}-released-%I%`,
  action: { bot: '112', target: x.ip, via: '%VIA%', action: %ACT%, result: 'released', applied_verified: r.applied_verified ?? null, effect_verified: null, effect_verified_at: null,
    requested_at: r.requested_at || now, finished_at: r.finished_at || now, n8n_execution_id: String($execution.id), detail: `승인 ${x.approver}${r.result === 'already_applied' ? ' (이미 해제됨)' : ''}`.slice(0, 300) } } }];
"""
R50note = r"""const r = $input.first().json;
const x = r.ctx;
const failed = (x.results || []).some(s => !['released'].includes(s.result));
return [{ json: { ctx: { ...x, ticket: { ticket_id: r.ticket_id, status: r.status } }, level: failed ? 'error' : 'info', case_id: x.case_id, title: failed ? '원복 중단(해제 실패)' : '원복 완료',
  src_ip: x.ip, ticket_id: r.ticket_id, result: (x.results || []).map(s => s.result).join(', '),
  detail: `승인 ${x.approver}` + (x.manual_required && x.manual_required.length ? ' / 사람이 직접 할 것: ' + x.manual_required.join(', ') : '') } }];
"""
R50final = r"""const r = $input.first().json;
const x = r.ctx;
return [{ json: { ok: !(x.results || []).some(s => s.result !== 'released'), verdict: 'released', case_id: x.case_id, ip: x.ip, steps: x.results, ticket: x.ticket,
  manual_required: x.manual_required, discord_sent: r.sent, n8n_execution_id: $execution.id } }];
"""
NOACT50 = r"""const j = $input.first().json;
return [{ json: { ...j, no_action: true, n8n_execution_id: $execution.id } }];
"""


def s50(i, wf_id, via, act, input_js, label):
    return [code(f"해제{i} 입력 ({label})", R50step.replace("%INPUT%", input_js), [0, 0]),
            execwf(f"해제{i} ({label})", wf_id, [0, 0]),
            code(f"해제{i} 기록 입력", R50rec.replace("%I%", str(i)).replace("%VIA%", via).replace("%ACT%", act), [0, 0]),
            execwf(f"해제{i} 기록 (haedam-10 released)", "haedamResultLog01", [0, 0])]


steps = s50(1, "haedamPfsense01", "pfsense", "'fw_block'", "action: x.abort || !x.hasFw ? 'skip' : 'unblock', ip: x.ip", "pfSense 해제") + \
        s50(2, "haedamPortalIp01", "portal", "'block'", "action: x.abort || !x.hasApp ? 'skip' : 'unblock', ip: x.ip", "포털 해제")
nodes50 = [node("Webhook", "n8n-nodes-base.webhook", {"httpMethod": "POST", "path": "haedam-release", "responseMode": "responseNode", "options": {}}, [0, 0], 2, webhookId="haedam-release"),
           code("승인 확인·티켓 조회 입력", R50a, [240, 0]), if_bool("입력 통과?", "$json.stop !== true", [480, 0]),
           execwf("열린 티켓 조회 (haedam-10 check)", "haedamResultLog01", [720, -60]), code("해제 대상 고르기", R50pick, [960, -60]),
           if_bool("해제 대상 있음?", "$json.no_action !== true", [1200, -60]),
           execwf("다른 자리 티켓 조회 (haedam-10 check)", "haedamResultLog01", [1440, -140]), code("보류 판정", R50hold, [1680, -140]),
           if_bool("보류 아님?", "$json.proceed === true", [1920, -140])] + steps + [
           code("알림 입력", R50note, [0, 0]), execwf("Discord 알림 (haedam-11)", "haedamDiscord01", [0, 0]), code("최종 응답", R50final, [0, 0]),
           respond("응답: 원복", [0, 0]), code("처리 없음 응답", NOACT50, [1920, 140]), respond("응답: 처리 없음", [2160, 140])]
for i, n in enumerate(nodes50):   # 노드 위치를 한 줄로 펼친다
    if n["position"] == [0, 0] and i > 0 and n["type"] != "n8n-nodes-base.webhook":
        n["position"] = [240 * i, -140 if i > 8 else 0]
conns50 = {"Webhook": [["승인 확인·티켓 조회 입력"]], "승인 확인·티켓 조회 입력": [["입력 통과?"]], "입력 통과?": [["열린 티켓 조회 (haedam-10 check)"], ["처리 없음 응답"]],
           "열린 티켓 조회 (haedam-10 check)": [["해제 대상 고르기"]], "해제 대상 고르기": [["해제 대상 있음?"]],
           "해제 대상 있음?": [["다른 자리 티켓 조회 (haedam-10 check)"], ["처리 없음 응답"]],
           "다른 자리 티켓 조회 (haedam-10 check)": [["보류 판정"]], "보류 판정": [["보류 아님?"]],
           "보류 아님?": [["해제1 입력 (pfSense 해제)"], ["처리 없음 응답"]],
           "해제1 입력 (pfSense 해제)": [["해제1 (pfSense 해제)"]], "해제1 (pfSense 해제)": [["해제1 기록 입력"]], "해제1 기록 입력": [["해제1 기록 (haedam-10 released)"]],
           "해제1 기록 (haedam-10 released)": [["해제2 입력 (포털 해제)"]],
           "해제2 입력 (포털 해제)": [["해제2 (포털 해제)"]], "해제2 (포털 해제)": [["해제2 기록 입력"]], "해제2 기록 입력": [["해제2 기록 (haedam-10 released)"]],
           "해제2 기록 (haedam-10 released)": [["알림 입력"]], "알림 입력": [["Discord 알림 (haedam-11)"]], "Discord 알림 (haedam-11)": [["최종 응답"]],
           "최종 응답": [["응답: 원복"]], "처리 없음 응답": [["응답: 처리 없음"]]}
w50 = wf("haedamRelease01", "haedam-50 원복(해제) — 사람 승인 후", nodes50, {})
w50[0]["connections"] = {k: {"main": [[{"node": t, "type": "main", "index": 0} for t in o] for o in v]} for k, v in conns50.items()}
save("haedam-50-release.json", w50)
print("stage2 ok")

# ------------------------------------------------------------ haedam-02 포털 호출 시험 (dry_run 고정)
R02 = r"""// 포털 IP 차단 호출 시험용 입구. **dry_run을 항상 true로 고정**해 haedam-12의 보호 목록·키 형식·Idempotency-Key를 실제 호출 없이 확인한다.
const b = $input.first().json.body || {};
return [{ json: { action: b.action || 'block', ip: b.ip, ticket_id: b.ticket_id || 'T-TEST-0001', dry_run: true, ctx: { purpose: 'portal_call_test', cfg: { dry_run: true } } } }];
"""
w02 = wf("haedamPortalTest01", "haedam-02 포털 호출 시험 (dry_run 고정)",
         [node("Webhook", "n8n-nodes-base.webhook", {"httpMethod": "POST", "path": "haedam-portal-test", "responseMode": "responseNode", "options": {}}, [0, 0], 2, webhookId="haedam-portal-test"),
          code("입력", R02, [240, 0]), execwf("haedam-12 (dry_run 고정)", "haedamPortalIp01", [480, 0]), respond("응답", [720, 0])],
         {"Webhook": [["입력"]], "입력": [["haedam-12 (dry_run 고정)"]], "haedam-12 (dry_run 고정)": [["응답"]]})
save("haedam-02-portal-test.json", w02)
print("haedam-02 ok")

# Final source pass shared by the canonical builder and its --check command.
from n8n_hardening import harden
harden(OUT)
