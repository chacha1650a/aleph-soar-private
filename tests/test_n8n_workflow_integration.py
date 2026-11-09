"""Committed D Code nodes against C test clients, without n8n/device/network calls."""
from copy import deepcopy
import json
from pathlib import Path
import shutil
import subprocess

import pytest

from ticket_store.app import create_n8n_app

ROOT=Path(__file__).resolve().parents[1]
CHECK='haedam-10-result-log.json'
S10='haedam-32-s8-s10-main.json'
RELEASE='haedam-50-release.json'
TICKET='T-20261026-0001'
IP='203.0.113.22'
RESOURCE={'asset_id':'haedam-portal','via':'portal','action':'block','target':IP}
ACTION={'bot':'112','via':'portal','action':'block','target':IP,'result':'applied'}


def evaluate(file,node,input,**kwargs):
    return evaluate_steps([{'file':file,'node':node,'input':input,**kwargs}])[0]


def evaluate_steps(steps):
    executable=shutil.which('node')
    if not executable:
        pytest.skip('Node.js is required to execute the actual n8n Code snippets')
    result=subprocess.run([executable,str(ROOT/'tests/helpers/n8n_code_runner.cjs')],
                          input=json.dumps(steps),
                          capture_output=True,text=True,encoding='utf-8',check=True,timeout=15)
    return json.loads(result.stdout)


@pytest.mark.parametrize('dry_run', ['missing', None, True, 'false', 0])
@pytest.mark.parametrize('file,payload', [
    ('haedam-14-pfsense-block.json', {'action':'block','ip':IP,'ticket_id':TICKET}),
    ('haedam-15-wazuh-restore.json', {'action':'restore','asset_id':'haedam-portal','file_key':'index.html'}),
])
def test_merged_device_preparation_requires_explicit_false_before_call_branch(file,payload,dry_run):
    payload = {**payload, 'ctx':{'event_id':'synthetic-merge-test'}}
    if dry_run != 'missing':
        payload['dry_run'] = dry_run
    result = evaluate(file, '요청 준비', payload)
    assert result['http_calls'] == 0
    assert result['output']['stop'] is True
    assert result['output']['final']['result'] == 'dry_run'
    assert result['output']['final']['applied_verified'] is None


def test_merged_portal_test_entry_cannot_disable_dry_run():
    result = evaluate('haedam-02-portal-test.json', '입력',
                      {'body':{'dry_run':False,'action':'block','ip':IP}})
    assert result['http_calls'] == 0
    assert result['output']['dry_run'] is True
    assert result['output']['ctx']['cfg']['dry_run'] is True


def context(**changes):
    return {'seat':'B','case_id':'S10','group_key':IP,'asset_id':'haedam-portal',
            'event_id':'synthetic-event','src_ip':IP,'cfg':{'dry_run':False},'expected':[ACTION],**changes}


def snapshot(**changes):
    return {'ok':True,'exists':True,'ticket_id':TICKET,'status':'responding','actions':[ACTION],
            'ctx':context(),**changes}


@pytest.mark.parametrize('input',[
    snapshot(ok=False,error={'code':'NETWORK'}),snapshot(actions=None),snapshot(actions=[{k:v for k,v in ACTION.items() if k!='via'}]),
    snapshot(status='restored'),snapshot(exists=False,ticket_id=None,status=None,actions=[ACTION]),
    snapshot(actions=[{**ACTION,'bot':112}]),snapshot(actions=[{k:v for k,v in ACTION.items() if k!='result'}]),
])
def test_failed_incomplete_or_restored_check_never_proceeds(input):
    output=evaluate(S10,'중복 판정',input)['output']
    assert output['ok'] is False and output['no_action'] is True and not output.get('proceed')


@pytest.mark.parametrize('result',['applied','already_applied'])
def test_duplicate_requires_exact_route_and_accepts_both_active_results(result):
    exact=snapshot(actions=[{**ACTION,'result':result}])
    assert evaluate(S10,'중복 판정',exact)['output']['verdict']=='duplicate_no_action'
    other=snapshot(actions=[{**ACTION,'via':'pfsense','result':result}])
    assert evaluate(S10,'중복 판정',other)['output']['proceed'] is True


def _dry_snapshot(**action):
    ctx=context(cfg={'dry_run':True})
    return snapshot(ctx=ctx,actions=[{**ACTION,'result':'dry_run',**action}])


def test_recent_dry_run_record_counts_as_duplicate():
    from datetime import datetime, timedelta, timezone
    recent=(datetime.now(timezone.utc)-timedelta(minutes=5)).isoformat()
    assert evaluate(S10,'중복 판정',_dry_snapshot(finished_at=recent))['output']['verdict']=='duplicate_no_action'


@pytest.mark.parametrize('when',['old','missing','future'])
def test_old_or_undated_dry_run_record_does_not_block_the_source(when):
    # a dry_run test ticket left open for days must not stop the health check forever
    from datetime import datetime, timedelta, timezone
    now=datetime.now(timezone.utc)
    action={'old':{'finished_at':(now-timedelta(days=7)).isoformat()},'missing':{},
            'future':{'finished_at':(now+timedelta(hours=1)).isoformat()}}[when]
    output=evaluate(S10,'중복 판정',_dry_snapshot(**action))['output']
    assert output['proceed'] is True and output.get('verdict')!='duplicate_no_action'


@pytest.mark.parametrize('body',[
    {'ok':True,'exists':False},
    {'ok':False,'exists':False,'ticket_id':None,'status':None,'applied_actions':[]},
    {'ok':True,'exists':False,'ticket_id':None,'status':None,'applied_actions':None},
])
def test_http_200_with_bad_ticket_shape_does_not_become_zero(body):
    output=evaluate(CHECK,'응답 변환 1',{'statusCode':200,'body':body},prior={
        '저장소 요청 만들기':{'mode':'check','ctx':context()}})['output']
    assert output['ok'] is False


@pytest.mark.parametrize('file,node',[
    (S10,'조치1 입력 (포털 IP 차단)'),(S10,'조치2 입력 (pfSense 차단)'),
    ('haedam-20-s12-main.json','차단 입력'),(RELEASE,'해제2 입력 (포털 해제)'),
])
def test_failed_record_stops_before_the_next_target_subworkflow(file,node):
    result=evaluate(file,node,{'ok':False,'ctx':context(),'error':{'code':'SERVER_ERROR'}})
    assert 'RECORD_REQUIRED' in result['error']
    assert result['http_calls']==0


def test_failed_previous_action_stops_the_second_action():
    result=evaluate(S10,'조치2 입력 (pfSense 차단)',{'ok':True,'ticket_id':TICKET,
                    'ctx':context(results=[{'result':'failed'}])})
    assert result['error']=='PREVIOUS_ACTION_FAILED'


@pytest.mark.parametrize('status',['restored','closed'])
def test_terminal_record_response_stops_before_target(status):
    result=evaluate(S10,'조치1 입력 (포털 IP 차단)',{'ok':True,'ticket_id':TICKET,'status':status,'ctx':context()})
    assert result['error']=='TICKET_RECORD_REQUIRED'


def test_release_query_error_and_real_zero_are_distinct():
    failed=evaluate(RELEASE,'해제 대상 고르기',snapshot(ok=False))['output']
    zero=evaluate(RELEASE,'해제 대상 고르기',snapshot(exists=False,ticket_id=None,status=None,actions=[]))['output']
    assert failed['ok'] is False and failed['verdict']=='held_ticket_check'
    assert zero['ok'] is True and zero['verdict']=='no_open_ticket'


def test_cross_group_claim_is_held_by_actual_c_resource_response(tmp_path):
    key='synthetic-c-key-1026'
    client=create_n8n_app(str(tmp_path/'tickets.db'),key).test_client()
    body=json.loads((ROOT/'contracts/ticket-examples/record-s12-applied.json').read_text(encoding='utf-8'))
    body.update(seat='B',case_id='S10',group_key=IP,src_ip=IP,event_ids=['synthetic-b'])
    body['action']['target']=IP
    headers={'X-Response-Key':key,'Idempotency-Key':'synthetic-b-apply'}
    own=client.post('/api/v1/tickets/record',json=body,headers=headers)
    assert own.status_code==201
    current=own.get_json()['ticket_id']
    other=deepcopy(body)
    other.update(seat='A',case_id='S1',group_key='zz_other_username',event_ids=['synthetic-a'])
    other['action']['bot']='manual'
    response=client.post('/api/v1/tickets/record',json=other,headers={**headers,'Idempotency-Key':'synthetic-a-apply'})
    assert response.status_code==201
    other_id=response.get_json()['ticket_id']
    pick=evaluate(RELEASE,'해제 대상 고르기',snapshot(ticket_id=current))['output']
    actual=client.get('/api/v1/tickets/active',query_string=pick['resource'],headers={'X-Response-Key':key})
    assert actual.status_code==200
    mapped=evaluate(CHECK,'응답 변환 1',{'statusCode':200,'body':actual.get_json()},prior={
        '저장소 요청 만들기':{'mode':'active','resource':pick['resource'],'ctx':pick['ctx']}})['output']
    decision=evaluate(RELEASE,'보류 판정',mapped)['output']
    assert decision['verdict']=='held_other_resource_ticket' and decision['other_tickets']==[other_id]
    assert not decision.get('proceed')


@pytest.mark.parametrize('tickets',[
    None,[],[{'ticket_id':TICKET,'seat':'B','status':'responding','active_actions':[]}],
    [{'ticket_id':TICKET,'seat':'B','status':'responding','active_actions':[{**ACTION,'target':'203.0.113.23'}]}],
])
def test_release_resource_requires_complete_matching_own_claim(tickets):
    ctx=context(ticket_id=TICKET,resources=[RESOURCE],resource_index=0)
    out=evaluate(RELEASE,'보류 판정',{'ok':True,'resource':RESOURCE,'tickets':tickets,'ctx':ctx})['output']
    assert out['no_action'] is True and not out.get('proceed')


def test_same_seat_other_ticket_and_closed_claim_hold_release():
    ctx=context(ticket_id=TICKET,resources=[RESOURCE],resource_index=0)
    own={'ticket_id':TICKET,'seat':'B','status':'responding','active_actions':[ACTION]}
    other={**own,'ticket_id':'T-20261026-0002','status':'closed'}
    out=evaluate(RELEASE,'보류 판정',{'ok':True,'resource':RESOURCE,'tickets':[own,other],'ctx':ctx})['output']
    assert out['verdict']=='held_other_resource_ticket'


def test_both_execution_routes_are_checked_before_release():
    fw={**RESOURCE,'via':'pfsense'}
    ctx=context(ticket_id=TICKET,resources=[fw,RESOURCE],resource_index=0)
    own={'ticket_id':TICKET,'seat':'B','status':'responding','active_actions':[{**ACTION,'via':'pfsense'}]}
    first=evaluate(RELEASE,'보류 판정',{'ok':True,'resource':fw,'tickets':[own],'ctx':ctx})['output']
    assert first['more_resources'] is True and not first.get('proceed')
    second=evaluate(RELEASE,'보류 판정',{'ok':True,'resource':RESOURCE,'tickets':[{**own,'active_actions':[ACTION]}],'ctx':first['ctx']})['output']
    assert second['proceed'] is True and second['more_resources'] is False


def test_graylog_detected_time_is_preserved_and_missing_stays_null():
    event={'event_id':'test-event','asset_id':'haedam-portal','src_ip':IP,'case_id':'S10',
           'condition_met_at':'2026-10-26T15:20:00+09:00','detected_at':'2026-10-26T15:20:03+09:00'}
    for detected in (event['detected_at'],None):
        validated=evaluate(S10,'입력 검증·설정',{'body':{**event,'detected_at':detected}})['output']
        record=evaluate(S10,'티켓 detected 입력',validated)['output']
        assert record['detected_at']==detected
        assert record['received_at'] is not None


@pytest.mark.parametrize('status,body,recovered',[
    (403,{'success':True,'data':{'status':'ok'}},False),
    (404,{},False),(200,{},False),
    (200,{'success':True,'data':{'status':'ok'}},True),
])
def test_recovery_requires_health_contract_and_never_proves_external_effect(status,body,recovered):
    ctx=context(cfg={'dry_run':False,'baseline_ms':1,'baseline_source':'synthetic-evidence','recover_timeout_ms':10,'health_k':1,
                     'health_timeout_ms':10,'health_interval_ms':1,'health_url':'synthetic-only'})
    result=evaluate('haedam-20-s12-main.json','회복 확인',{'ctx':ctx},clock_ms=1793664000000,
                    responses=[{'delay_ms':1,'response':{'statusCode':status,'body':body}}])
    assert result['output']['recovered'] is recovered
    assert result['output']['effect_verified'] is None and result['output']['noop'] is True


def test_build_is_reproducible_and_exports_stay_inactive():
    import sys
    subprocess.run([sys.executable,str(ROOT/'tools/build_n8n_workflows.py'),'--check'],check=True,
                   capture_output=True,text=True,timeout=30)
    for source in (ROOT/'infra/n8n/workflows').glob('*.json'):
        for workflow in json.loads(source.read_text(encoding='utf-8')):
            assert workflow['active'] is False
            for node in workflow['nodes']:
                if node['type']=='n8n-nodes-base.httpRequest' and source.name==CHECK:
                    assert node.get('retryOnFail') is False


def test_s7_keeps_group_key_distinct_from_action_target():
    data={'body':{'event_id':'synthetic-s7','asset_id':'haedam-portal','file_key':'assets/x.txt','change_type':'added'}}
    result=evaluate('haedam-33-s7-main.json','입력 검증·설정',data)['output']
    assert result['group_key']=='haedam-portal:assets/x.txt'
    assert result['ctx']['expected'][0]['target']=='assets/x.txt'


def test_s7_dry_run_still_writes_tickets_to_the_real_store():
    """S7 공용 경로: 실제 조치는 dry_run이지만 티켓은 C 저장소(8088)로 보낸다(11/02 D 결정)."""
    data={'body':{'event_id':'synthetic-s7','asset_id':'haedam-portal','file_key':'assets/x.txt','change_type':'added'}}
    ctx=evaluate('haedam-33-s7-main.json','입력 검증·설정',data)['output']['ctx']
    assert ctx['cfg']=={'dry_run':True,'store_real':True}
    route=evaluate(CHECK,'저장소 요청 만들기',{'mode':'check','seat':'C','group_key':ctx['group_key'],'ctx':ctx})['output']
    assert route['real'] is True and route['url'].startswith('http://10.250.0.3:8088/api/v1/tickets/open?')


def test_s7_shared_webhook_requires_caller_header_auth_before_any_node_runs():
    """실기록 경로라 미인증·오인증 요청은 n8n 웹훅 인증 단계(워크플로 실행 전)에서 거절돼야 한다.
    자격 증명은 이름만 둔다: 반입 직후 미연결이면 게시되지 않는다(fail-closed). 비밀값은 저장소에 없다."""
    main=json.loads((ROOT/'infra/n8n/workflows/haedam-33-s7-main.json').read_text(encoding='utf-8'))[0]
    hook=next(n for n in main['nodes'] if n['type']=='n8n-nodes-base.webhook')
    assert hook['parameters']['authentication']=='headerAuth' and hook['parameters']['path']=='haedam-s7'
    assert hook['credentials']=={'httpHeaderAuth':{'id':'','name':'haedam-s7 caller'}}
    assert main['connections']['Webhook']['main'][0][0]['node']=='입력 검증·설정'   # 인증 뒤 첫 노드


CASE_MAINS={'haedam-20-s12-main.json':('haedam-s12','haedam-s12 caller'),
            'haedam-30-s1-main.json':('haedam-s1','haedam-s1 caller'),
            'haedam-31-s4-main.json':('haedam-s4','haedam-s4 caller'),
            'haedam-32-s8-s10-main.json':('haedam-s8-s10','haedam-s8-s10 caller'),
            'haedam-33-s7-main.json':('haedam-s7','haedam-s7 caller')}


def case_cfg_source(file):
    wf=load_wf(file)
    return next(n['parameters']['jsCode'] for n in wf['nodes'] if n['name']=='입력 검증·설정')


@pytest.mark.parametrize('file',[f for f in CASE_MAINS if f!='haedam-33-s7-main.json'])
def test_case_mains_default_to_observation_and_enable_ticket_storage_only_by_literal_body_switch(file):
    """11/03: 케이스별 회차에서만 store_real:true. 기본은 관찰(store_real false, dry_run true)."""
    source=case_cfg_source(file)
    assert 'dry_run: true' in source and 'store_real: false' in source
    assert "t.store_real === true) CFG.store_real = true" in source   # 불리언 true만


@pytest.mark.parametrize('file',list(CASE_MAINS))
def test_every_real_ticket_webhook_requires_caller_header_auth_fail_closed(file):
    path,credential=CASE_MAINS[file]
    wf=load_wf(file)
    hook=next(n for n in wf['nodes'] if n['type']=='n8n-nodes-base.webhook')
    assert hook['parameters']['authentication']=='headerAuth' and hook['parameters']['path']==path
    assert hook['credentials']=={'httpHeaderAuth':{'id':'','name':credential}}   # 이름만, 값·ID 없음
    assert wf['connections']['Webhook']['main'][0][0]['node']=='입력 검증·설정'      # 인증 뒤 첫 노드
    assert wf['active'] is False
    assert len({v[1] for v in CASE_MAINS.values()})==len(CASE_MAINS)               # 케이스별 자격 증명 분리


@pytest.mark.parametrize('file,body',[
    ('haedam-30-s1-main.json',{'event_id':'e','asset_id':'haedam-portal','src_ip':IP,'username':'zz_s1'}),
    ('haedam-31-s4-main.json',{'event_id':'e','asset_id':'haedam-portal','username':'zz_s4'}),
    ('haedam-32-s8-s10-main.json',{'event_id':'e','asset_id':'haedam-portal','src_ip':IP,'case_id':'S8'}),
    ('haedam-20-s12-main.json',{'event_id':'e','asset_id':'haedam-portal','src_ip':IP}),
])
def test_case_ticket_goes_to_c_store_only_with_literal_switch_and_actions_stay_dry_run(file,body):
    default=evaluate(file,'입력 검증·설정',{'body':body})['output']['ctx']['cfg']
    assert default['store_real'] is False and default['dry_run'] is True
    for extra in ({'store_real':'true'},{'store_real':1},{'dry_run':'yes'}):
        cfg=evaluate(file,'입력 검증·설정',{'body':{**body,**extra}})['output']['ctx']['cfg']
        assert cfg['store_real'] is False and cfg['dry_run'] is True
    ctx=evaluate(file,'입력 검증·설정',{'body':{**body,'store_real':True}})['output']['ctx']
    assert ctx['cfg']['store_real'] is True and ctx['cfg']['dry_run'] is True
    route=evaluate(CHECK,'저장소 요청 만들기',{'mode':'check','seat':ctx.get('seat','D'),'group_key':ctx.get('group_key',IP),'ctx':ctx})['output']
    assert route['real'] is True and route['url'].startswith('http://10.250.0.3:8088/api/v1/tickets/open?')


LIVE_COPY='haedam-34-s7-live-acceptance.json'
LIVE_RUN='S7-20261102-AR01'
LIVE_FILE='assets/zz_s7_1102_ar01.txt'


def live_copy(approved, tmp_path):
    """승인 반입본은 저장소에 두지 않으므로 tmp에 만들고 runner가 읽는 상대 경로를 돌려준다."""
    import importlib.util, os
    spec=importlib.util.spec_from_file_location('make_s7_live_copy',ROOT/'tools/make_s7_live_copy.py')
    module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    # runner는 infra/n8n/workflows 기준 상대 경로만 읽는다. tmp_path는 다른 드라이브일 수 있어(Windows CI) 저장소 안 무시 폴더를 쓴다.
    folder=ROOT/'.pytest_cache'/'s7-live-approved'/tmp_path.name
    folder.mkdir(parents=True,exist_ok=True)
    target=folder/'haedam-34-approved.json'
    target.write_text(module.render(approved),encoding='utf-8')
    return os.path.relpath(target,ROOT/'infra/n8n/workflows'),module


def test_s7_live_copy_is_isolated_inactive_and_in_sync_with_generator():
    import sys
    subprocess.run([sys.executable,str(ROOT/'tools/make_s7_live_copy.py'),'--check'],check=True,
                   capture_output=True,text=True,timeout=30)
    live=json.loads((ROOT/'infra/n8n/workflows'/LIVE_COPY).read_text(encoding='utf-8'))[0]
    main=json.loads((ROOT/'infra/n8n/workflows/haedam-33-s7-main.json').read_text(encoding='utf-8'))[0]
    assert live['id']!=main['id'] and live['active'] is False
    hooks=lambda w:[n for n in w['nodes'] if n['type']=='n8n-nodes-base.webhook']
    assert [n['parameters']['path'] for n in hooks(live)]==['haedam-s7-live']
    assert [n['parameters']['path'] for n in hooks(main)]==['haedam-s7']
    # 호출자 인증: 복사본만 헤더 인증, 자격 증명은 이름만(반입 뒤 D가 연결하기 전에는 게시 불가)
    assert hooks(live)[0]['parameters']['authentication']=='headerAuth'
    assert hooks(live)[0]['credentials']=={'httpHeaderAuth':{'id':'','name':'haedam-s7-live caller'}}
    assert hooks(main)[0]['credentials']=={'httpHeaderAuth':{'id':'','name':'haedam-s7 caller'}}   # 공용과 자격 증명을 나눔
    code=lambda w:next(n['parameters']['jsCode'] for n in w['nodes'] if n['name']=='입력 검증·설정')
    assert 'dry_run: true, store_real: true' in code(main)       # 공용 경로: 조치 dry_run, 티켓만 실기록
    assert 'dry_run: false, store_real: true' in code(live)
    assert "const APPROVED_RUN_ID = '';" in code(live)            # 저장소 파일은 항상 승인 OFF


@pytest.mark.parametrize('body', [
    {'asset_id':'haedam-portal','file_key':LIVE_FILE,'change_type':'added'},
    {'asset_id':'haedam-portal','file_key':'assets/zz_s7_1102_01.txt','change_type':'added'},
    {'asset_id':'haedam-portal','file_key':LIVE_FILE,'change_type':'added','run_id':LIVE_RUN,'approved':True,
     'dry_run':False,'cfg':{'dry_run':False}},   # payload로 승인·모드를 켤 수 없음
])
def test_s7_live_copy_committed_file_is_approval_off_for_every_input(body):
    result=evaluate(LIVE_COPY,'입력 검증·설정',{'body':{'event_id':'synthetic-s7-live',**body}})['output']
    assert not result.get('proceed') and result['verdict']=='approval_off'


@pytest.mark.parametrize('body,in_scope', [
    ({'asset_id':'haedam-portal','file_key':LIVE_FILE,'change_type':'added'}, True),
    ({'asset_id':'haedam-portal','file_key':'assets/zz_s7_1102_01.txt','change_type':'added'}, False),     # dry-run 파일은 실제 경로 금지
    ({'asset_id':'haedam-portal','file_key':'index.html','change_type':'added'}, False),
    ({'asset_id':'haedam-portal','file_key':LIVE_FILE,'change_type':'modified'}, False),  # 복구 동작 금지
    ({'asset_id':'haedam-portal','file_key':LIVE_FILE}, False),                           # change_type 누락은 modified 취급
    ({'asset_id':'other','file_key':LIVE_FILE,'change_type':'added'}, False),
])
def test_s7_live_copy_approved_build_allows_only_the_one_quarantine_target(body,in_scope,tmp_path):
    file,_=live_copy(LIVE_RUN,tmp_path)
    result=evaluate(file,'입력 검증·설정',{'body':{'event_id':'synthetic-s7-live',**body}})['output']
    if in_scope:
        assert result['proceed'] is True and result['ctx']['cfg']=={'dry_run':False,'store_real':True}
        assert result['ctx']['run_id']==LIVE_RUN and result['ctx']['expected'][0]['action']=='quarantine'
    else:
        assert not result.get('proceed') and result['verdict']=='out_of_scope'


@pytest.mark.parametrize('run_id,ok', [
    (LIVE_RUN, True),                      # 명시했고 승인 회차와 같음
    ('S7-20261102-AR02', False),           # 다른 회차
    ('s7-20261102-ar01', False),           # 대소문자만 다른 값도 거절
    ('../../etc', False), ('', False), (None, False), (7, False),
])
def test_s7_live_copy_rejects_explicit_run_id_that_is_not_the_approved_round(run_id,ok,tmp_path):
    file,_=live_copy(LIVE_RUN,tmp_path)
    body={'event_id':'synthetic-s7-live','asset_id':'haedam-portal','file_key':LIVE_FILE,'change_type':'added','run_id':run_id}
    result=evaluate(file,'입력 검증·설정',{'body':body})['output']
    if ok:
        assert result['proceed'] is True and result['ctx']['run_id']==LIVE_RUN
    else:
        assert not result.get('proceed') and result['verdict']=='run_id_mismatch'   # AR01로 덮어쓰지 않음


def wazuh_send_body(prepared):
    """토큰 구간은 haedam-17에 있다: haedam-15가 보낸 입력을 정리한 뒤 요청 본문을 만든다."""
    cleaned=evaluate('haedam-17-wazuh-token.json','입력 정리',prepared)['output']
    return evaluate('haedam-17-wazuh-token.json','전송 준비',{'data':'synthetic-token'},
                    prior={'입력 정리':cleaned})['output']


def test_s7_absent_run_id_keeps_the_legacy_event_based_value():
    result=evaluate('haedam-15-wazuh-restore.json','요청 준비',
                    {'action':'quarantine','asset_id':'haedam-portal','file_key':LIVE_FILE,'dry_run':False,
                     'ctx':{'event_id':'synthetic-s7-live'}})['output']
    assert result['run_id']=='n8n-synthetic-s7-live'      # 필드 부재만 기존 방식으로 대체


def test_s7_live_copy_only_binds_the_fixed_run_and_keeps_it_out_of_the_repository(tmp_path):
    import sys
    _,module=live_copy('',tmp_path)
    with pytest.raises(ValueError):
        module.build('S7-20261102-AR02')
    step=lambda w:next(n['parameters']['jsCode'] for n in w['nodes'] if n['name']=='조치1 입력 (Wazuh 복구·격리)')
    assert 'run_id: x.run_id' in step(module.build(LIVE_RUN))   # 승인 run_id를 haedam-15 입력까지 전달
    done=subprocess.run([sys.executable,str(ROOT/'tools/make_s7_live_copy.py'),'--approve-run-id',LIVE_RUN,
                         '--out',str(ROOT/'infra/n8n/workflows/approved.json')],capture_output=True,text=True,timeout=30)
    assert done.returncode!=0 and not (ROOT/'infra/n8n/workflows/approved.json').exists()


def test_s7_approved_run_id_reaches_the_wazuh_active_response_arguments():
    prepared=evaluate('haedam-15-wazuh-restore.json','요청 준비',
                      {'action':'quarantine','asset_id':'haedam-portal','file_key':LIVE_FILE,'dry_run':False,
                       'run_id':LIVE_RUN,'ctx':{'event_id':'synthetic-s7-live'}})['output']
    sent=wazuh_send_body(prepared)
    assert json.loads(sent['body'])=={'command':'!s7-restore-ar','arguments':[LIVE_FILE,LIVE_RUN]}


@pytest.mark.parametrize('run_id', ['../../etc', '', 'S7-20261102-ar01', 'n8n-other', 7, None])
def test_s7_bad_run_id_is_rejected_before_active_response_not_replaced(run_id):
    result=evaluate('haedam-15-wazuh-restore.json','요청 준비',
                    {'action':'quarantine','asset_id':'haedam-portal','file_key':LIVE_FILE,'dry_run':False,
                     'run_id':run_id,'ctx':{'event_id':'synthetic-s7-live'}})
    assert result['http_calls']==0 and result['output']['stop'] is True
    assert result['output']['final']['result']=='failed' and result['output']['final']['detail']=='bad_run_id'
    assert 'run_id' not in result['output']        # 다른 값으로 대체하지 않음


@pytest.mark.parametrize('file_key', ['index.html', '/home/haedam/haedam-portal-frontend/dist/index.html'])
def test_s7_active_response_matches_verified_wazuh_call(file_key):
    prepared=evaluate('haedam-15-wazuh-restore.json','요청 준비',
                      {'action':'restore','asset_id':'haedam-portal','file_key':file_key,'dry_run':False,
                       'ctx':{'event_id':'synthetic-s7'}})['output']
    sent=wazuh_send_body(prepared)
    assert sent['url'].endswith('/active-response?agents_list=010')
    assert json.loads(sent['body'])=={'command':'!s7-restore-ar','arguments':['index.html','n8n-synthetic-s7']}


def load_wf(name):
    return json.loads((ROOT/'infra/n8n/workflows'/name).read_text(encoding='utf-8'))[0]


def test_wazuh_token_stays_in_the_unsaved_child_and_haedam_15_keeps_execution_records():
    parent=load_wf('haedam-15-wazuh-restore.json')
    child=load_wf('haedam-17-wazuh-token.json')
    # 토큰을 만들고 쓰는 호출 노드는 하위 워크플로에만 있고, 그 워크플로는 실행 기록을 저장하지 않는다.
    assert not [n for n in parent['nodes'] if n['type'].endswith('.httpRequest')]
    assert {n['name'] for n in child['nodes'] if n['type'].endswith('.httpRequest')}=={'Wazuh 로그인','Wazuh active response 전송'}
    assert child['settings']['saveDataSuccessExecution']=='none' and child['settings']['saveDataErrorExecution']=='none'
    assert child['settings']['saveExecutionProgress'] is False and child['settings']['saveManualExecutions'] is False
    # haedam-15는 실행 기록을 저장한다(저장을 끄는 설정이 없다).
    assert not {k for k in parent['settings'] if k.startswith('save')}
    ref=next(n for n in parent['nodes'] if n['type'].endswith('.executeWorkflow'))
    assert ref['parameters']['workflowId']['value']==child['id']
    assert child['active'] is False and parent['active'] is False


def test_wazuh_child_summary_and_parent_result_never_contain_the_token():
    prepared=evaluate('haedam-15-wazuh-restore.json','요청 준비',
                      {'action':'quarantine','asset_id':'haedam-portal','file_key':LIVE_FILE,'dry_run':False,
                       'run_id':LIVE_RUN,'ctx':{'event_id':'synthetic-s7-live'}})['output']
    sent=wazuh_send_body(prepared)
    assert sent['token']=='synthetic-token'                      # 토큰은 하위 워크플로 안에서만 존재
    summary=evaluate('haedam-17-wazuh-token.json','응답 요약',
                     {'statusCode':200,'body':{'data':{'total_affected_items':1,'failed_items':[]}},
                      'headers':{'authorization':'Bearer synthetic-token'}},
                     prior={'입력 정리':prepared})['output']['summary']
    assert summary=={'status':200,'affected':1,'failed_count':0,'failed_ids':[],'reason':''}
    final=evaluate('haedam-15-wazuh-restore.json','응답 해석',summary,prior={'요청 준비':prepared})['output']
    assert final['result']=='applied' and final['ok'] is True and final['applied_verified'] is None
    assert 'synthetic-token' not in json.dumps(summary)+json.dumps(final)


@pytest.mark.parametrize('summary,result,detail',[
    ({'auth_failed':True},'failed','wazuh_auth_failed'),
    ({'rejected':'target_not_allowed'},'failed','rejected:target_not_allowed'),
    ({'status':None,'affected':0,'reason':'network'},'failed','timeout_or_network'),
    ({'status':200,'affected':0,'failed_count':1,'failed_ids':['010']},'failed','not_sent:failed_count=1 ids=010'),
    ({'status':403,'affected':0,'reason':'forbidden'},'failed','403 forbidden'),
])
def test_wazuh_response_interpretation_from_child_summary(summary,result,detail):
    prepared=evaluate('haedam-15-wazuh-restore.json','요청 준비',
                      {'action':'quarantine','asset_id':'haedam-portal','file_key':LIVE_FILE,'dry_run':False,
                       'run_id':LIVE_RUN,'ctx':{'event_id':'synthetic-s7-live'}})['output']
    final=evaluate('haedam-15-wazuh-restore.json','응답 해석',summary,prior={'요청 준비':prepared})['output']
    assert final['result']==result and final['ok'] is False and final['detail']==detail


TOKEN='synthetic-token-abc123'


def live_prepared(**over):
    body={'action':'quarantine','asset_id':'haedam-portal','file_key':LIVE_FILE,'dry_run':False,
          'run_id':LIVE_RUN,'ctx':{'event_id':'synthetic-s7-live'}}
    body.update(over)
    return evaluate('haedam-15-wazuh-restore.json','요청 준비',body)['output']


def test_wazuh_child_entry_requires_the_execute_intent_only_haedam_15_creates():
    prepared=live_prepared()
    assert prepared['execute'] is True
    dry=evaluate('haedam-15-wazuh-restore.json','요청 준비',{'action':'quarantine','asset_id':'haedam-portal',
        'file_key':LIVE_FILE,'ctx':{'event_id':'e'}})['output']
    assert dry['stop'] is True and 'execute' not in dry and dry['final']['result']=='dry_run'


@pytest.mark.parametrize('override,reason',[
    ({'execute':False},'not_authorized'),
    ({'execute':'true'},'not_authorized'),
    ({'api':'https://example.invalid'},'target_not_allowed'),
    ({'agent':'999'},'target_not_allowed'),
    ({'script':'!other-command'},'target_not_allowed'),
    ({'file_key':'../outside'},'bad_file_key'),
    ({'file_key':'/etc/passwd'},'bad_file_key'),
    ({'file_key':'a b.txt'},'bad_file_key'),
    ({'run_id':'../x'},'bad_run_id'),
    ({'run_id':None},'bad_run_id'),
])
def test_wazuh_child_rejects_unapproved_target_or_intent_before_login(override,reason):
    entry={**live_prepared(),**override}
    result=evaluate('haedam-17-wazuh-token.json','입력 정리',entry)
    assert result['http_calls']==0
    assert result['output']=={'stop':True,'summary':{'rejected':reason}}


def test_wazuh_child_without_execute_never_reaches_authentication():
    entry={k:v for k,v in live_prepared().items() if k!='execute'}
    out=evaluate('haedam-17-wazuh-token.json','입력 정리',entry)['output']
    assert out['stop'] is True and out['summary']=={'rejected':'not_authorized'}
    child=load_wf('haedam-17-wazuh-token.json')
    assert child['connections']['입력 정리']['main'][0][0]['node']=='입력 통과?'
    gate=child['connections']['입력 통과?']['main']
    assert gate[0][0]['node']=='Wazuh 로그인' and gate[1][0]['node']=='요약 정리'    # 거절은 로그인 없이 끝남


@pytest.mark.parametrize('raw',[
    {'statusCode':None,'error':{'message':'connect failed Bearer '+TOKEN}},
    {'statusCode':None,'message':'token '+TOKEN},
    {'statusCode':403,'body':{'detail':'bad token '+TOKEN,'title':TOKEN}},
    {'statusCode':200,'body':{'data':{'total_affected_items':0,'failed_items':[{'error':{'message':TOKEN},'id':['010']}]}}},
    {'statusCode':200,'body':{'data':{'total_affected_items':0,'failed_items':[{'error':{'message':TOKEN},'id':[TOKEN]}]}}},
    {'statusCode':500,'body':{'detail':TOKEN},'headers':{'authorization':'Bearer '+TOKEN}},
])
def test_wazuh_error_summary_and_parent_result_never_carry_response_or_error_text(raw):
    prepared=live_prepared()
    summary=evaluate('haedam-17-wazuh-token.json','응답 요약',raw,prior={'입력 정리':prepared})['output']['summary']
    assert TOKEN not in json.dumps(summary)
    assert set(summary)=={'status','affected','failed_count','failed_ids','reason'}
    assert all(len(i)==3 and i.isdigit() for i in summary['failed_ids'])       # 3자리 agent ID만
    final=evaluate('haedam-15-wazuh-restore.json','응답 해석',summary,prior={'요청 준비':prepared})['output']
    assert TOKEN not in json.dumps(final)


def test_wazuh_child_stops_before_sending_when_authentication_returns_no_token():
    prepared=evaluate('haedam-15-wazuh-restore.json','요청 준비',
                      {'action':'quarantine','asset_id':'haedam-portal','file_key':LIVE_FILE,'dry_run':False,
                       'run_id':LIVE_RUN,'ctx':{'event_id':'synthetic-s7-live'}})['output']
    cleaned=evaluate('haedam-17-wazuh-token.json','입력 정리',prepared)['output']
    assert set(cleaned)=={'api','agent','script','file_key','run_id'}    # 토큰 구간에는 필요한 값만 넘어간다
    out=evaluate('haedam-17-wazuh-token.json','전송 준비',{'data':''},prior={'입력 정리':cleaned})['output']
    assert out=={'stop':True,'summary':{'auth_failed':True}}


def test_s1_candidate_with_c_reserves_next_round_and_stops_old_or_cached_replays(tmp_path):
    """Actual generated code and Flask/SQLite; the target itself is synthetic."""
    key='synthetic-full-flow-1026'
    client=create_n8n_app(str(tmp_path/'tickets.db'),key).test_client()
    headers={'X-Response-Key':key}
    s1='haedam-30-s1-main.json'
    v=evaluate(s1,'입력 검증·설정',{'body':{
        'event_id':'synthetic-s1-one','asset_id':'haedam-portal','src_ip':IP,'username':'zz_s1',
        'condition_met_at':'2026-10-26T15:20:00+09:00','detected_at':'2026-10-26T15:20:01+09:00'}})['output']
    # Exercise the candidate's real-store branch with an in-process client only.
    v['ctx']['cfg']['dry_run']=False
    v['ctx']['cfg']['store_real']=True

    def c_request(input):
        route=evaluate(CHECK,'저장소 요청 만들기',input)['output']
        from urllib.parse import urlsplit
        url=urlsplit(route['url'])
        assert url.hostname=='10.250.0.3'  # Parsed only: never opened.
        if route['method']=='GET':
            response=client.get(url.path+'?'+url.query,headers=headers)
        else:
            response=client.post(url.path,json=route['body'],headers={**headers,'Idempotency-Key':route['idem']})
        return evaluate(CHECK,'응답 변환 1',{'statusCode':response.status_code,'body':response.get_json()},
                        prior={'저장소 요청 만들기':route})['output']

    def current_ack(ack):
        query=evaluate(s1,'조치 전 티켓 조회 입력 1',ack)['output']
        return evaluate(s1,'조치 전 티켓 대조 1',c_request(query))

    decision=evaluate(s1,'중복 판정',c_request(v))['output']
    assert decision['proceed'] is True
    detected=evaluate(s1,'티켓 detected 입력',decision)['output']
    stored=c_request(detected)
    target_input=evaluate(s1,'조치1 입력 (포털 IP 차단)',current_ack(stored)['output'])['output']
    synthetic_target={'blocked':True,'calls':1}
    t='2026-10-26T15:20:02+09:00'
    receipt={'ok':True,'result':'applied','applied_verified':True,'requested_at':t,'finished_at':t,
             'detail':'synthetic target only','ctx':target_input['ctx']}
    applied=c_request(evaluate(s1,'조치1 기록 입력',receipt)['output'])
    assert applied['status']=='responding'
    replay=evaluate(s1,'중복 판정',c_request(v))['output']
    assert replay['verdict']=='duplicate_no_action' and synthetic_target['calls']==1
    action={**ACTION,'applied_verified':True,'effect_verified':True,'effect_verified_at':t,
            'requested_at':t,'finished_at':t,'n8n_execution_id':'synthetic-1026','detail':'synthetic effect'}
    effect={**detected,'stage':'effect','action':action,'idempotency_key':'synthetic-full-effect'}
    assert c_request(effect)['status']=='verified'
    pick=evaluate(RELEASE,'해제 대상 고르기',c_request(v))['output']
    held=evaluate(RELEASE,'보류 판정',c_request(pick))['output']
    assert held['proceed'] is True
    synthetic_target.update(blocked=False,calls=2)
    released={**effect,'stage':'released','action':{**action,'action':'unblock','result':'released',
              'effect_verified':None,'effect_verified_at':None},'idempotency_key':'synthetic-full-release'}
    assert c_request(released)['status']=='restored'
    active=c_request({'mode':'active','resource':RESOURCE,'ctx':v['ctx']})
    assert active['tickets']==[] and synthetic_target['blocked'] is False
    new=evaluate(s1,'중복 판정',c_request(v))['output']
    assert new['proceed'] is True and new['ctx']['new_round_required'] is True
    # The original Idempotency-Key returns the original open response. It cannot authorize a re-block.
    cached=c_request(evaluate(s1,'티켓 detected 입력',new)['output'])
    assert cached['ticket_id']==stored['ticket_id'] and cached['status']=='open'
    stopped=evaluate(s1,'조치1 입력 (포털 IP 차단)',cached)
    assert stopped['error'] in ('TICKET_RECORD_REQUIRED','TICKET_CURRENT_REQUIRED') and stopped['http_calls']==0
    old=evaluate(s1,'티켓 detected 입력',new)['output']
    old['idempotency_key']='synthetic-old-event-new-key'
    replay=c_request(old)
    assert replay['status']=='restored' and replay['duplicate'] is True
    assert evaluate(s1,'조치1 입력 (포털 IP 차단)',replay)['error'] in ('TICKET_RECORD_REQUIRED','TICKET_CURRENT_REQUIRED')
    # Human close removes the open grouping. The old key still returns its original open ACK.
    from ticket_store import db
    with db.connect(str(tmp_path/'tickets.db')) as conn:
        db.close_ticket(conn,stored['ticket_id'],'synthetic release confirmed')
    absent=evaluate(s1,'중복 판정',c_request(v))['output']
    assert absent['proceed'] and not absent['ctx']['new_round_required']
    cached_after_close=c_request(evaluate(s1,'티켓 detected 입력',absent)['output'])
    assert cached_after_close['status']=='open' and cached_after_close['ticket_id']==stored['ticket_id']
    assert current_ack(cached_after_close)['error']=='TICKET_CURRENT_REQUIRED'
    assert synthetic_target['calls']==2
    fresh=deepcopy(v)
    fresh['ctx']['event_id']='synthetic-s1-two'
    ready=evaluate(s1,'중복 판정',c_request(fresh))['output']
    second=evaluate(s1,'티켓 detected 입력',ready)['output']
    second['idempotency_key']='synthetic-second-detected'
    allocated=c_request(second)
    assert allocated['status']=='open' and allocated['ticket_id']!=stored['ticket_id']
    assert current_ack(cached_after_close)['error']=='TICKET_CURRENT_REQUIRED'  # new grouping differs too
    target=evaluate(s1,'조치1 입력 (포털 IP 차단)',current_ack(allocated)['output'])
    assert 'error' not in target and target['http_calls']==0
    synthetic_target.update(blocked=True,calls=3)
    receipt['ctx']=target['output']['ctx']
    applied2=evaluate(s1,'조치1 기록 입력',receipt)['output']
    applied2['idempotency_key']='synthetic-second-applied'
    assert c_request(applied2)['status']=='responding'
    from ticket_store import db
    with db.connect(str(tmp_path/'tickets.db')) as conn:
        assert db.get_ticket(conn,stored['ticket_id'])['status']=='closed'
        assert db.get_ticket(conn,allocated['ticket_id'])['event_ids']==['synthetic-s1-two']
    assert synthetic_target['calls']==3


@pytest.mark.parametrize('file', ['haedam-20-s12-main.json','haedam-30-s1-main.json',
                                  'haedam-31-s4-main.json',S10,'haedam-33-s7-main.json'])
def test_restored_empty_snapshot_can_only_prepare_a_new_record(file):
    output=evaluate(file,'중복 판정',snapshot(status='restored',actions=[]))['output']
    assert output['proceed'] is True and output['ctx']['new_round_required'] is True


def placeholder_steps(inputs):
    steps=[]
    for item in inputs:
        item=dict(item); seed=item.pop('static',None)   # 'static' seeds the workflow static data before the step
        steps.append({'file':CHECK,'node':'check/record (자리표시 저장소)','input':item,**({'static':seed} if seed is not None else {})})
    return evaluate_steps(steps)


def test_placeholder_keeps_rounds_replays_and_resource_claims_separate():
    ctx=context(cfg={'dry_run':True})
    base={'mode':'record','seat':'B','group_key':IP,'case_id':'S10','asset_id':'haedam-portal',
          'stage':'detected','event_ids':['synthetic-one'],'action':None,'idempotency_key':'ph-one-detected','ctx':ctx}
    apply={**base,'stage':'applied','action':{**ACTION,'result':'dry_run','finished_at':'2026-10-27T10:00:00+09:00'},'idempotency_key':'ph-one-applied'}
    release={**base,'stage':'released','action':{**ACTION,'action':'unblock','result':'released'},'idempotency_key':'ph-one-released'}
    second={**base,'event_ids':['synthetic-two'],'idempotency_key':'ph-two-detected'}
    results=placeholder_steps([base,apply,release,base,{**base,'idempotency_key':'ph-old-replay'},second,
        {**apply,'idempotency_key':'ph-old-after-new'},
        {**apply,'event_ids':['synthetic-two'],'idempotency_key':'ph-two-applied'},
        {'mode':'active','resource':RESOURCE,'ctx':ctx},
        {**apply,'event_ids':['different'],'idempotency_key':'ph-two-applied'}])
    assert all(r['http_calls']==0 and 'error' not in r for r in results)
    out=[r['output'] for r in results]
    assert out[2]['status']=='restored'
    assert out[3]==out[0]  # cached response, not current state
    assert out[4]['duplicate'] and out[4]['status']=='restored'
    assert out[5]['created'] and out[5]['ticket_id']!=out[0]['ticket_id']
    assert out[6]['ticket_id']==out[0]['ticket_id'] and out[6]['status']=='closed'
    assert out[7]['ticket_id']==out[5]['ticket_id'] and out[7]['status']=='responding'
    assert [t['ticket_id'] for t in out[8]['tickets']]==[out[5]['ticket_id']]
    assert out[9]['error']['code']=='IDEMPOTENCY_CONFLICT'


def _seeded_ticket(age, result='dry_run'):
    from datetime import datetime, timedelta, timezone
    at=(datetime.now(timezone.utc)-age).isoformat()
    old='T-20261023-0999'
    return old,{'tickets':{old:{'ticket_id':old,'seat':'B','case_id':'S10','group_key':IP,'asset_id':'haedam-portal',
        'event_ids':['old-event'],'status':'responding','created_at':at,
        'actions':[{**ACTION,'result':result,'finished_at':at,'recorded_at':at,'duplicate':False}]}},'seq':999,'idem':{}}


def test_stale_dry_run_only_ticket_is_not_reused_as_open():
    from datetime import timedelta
    old,seed=_seeded_ticket(timedelta(days=7))
    ctx=context(cfg={'dry_run':True})
    check={'mode':'check','seat':'B','group_key':IP,'ctx':ctx,'static':seed}
    detect={'mode':'record','seat':'B','group_key':IP,'case_id':'S10','asset_id':'haedam-portal','stage':'detected',
            'event_ids':['new-event'],'action':None,'idempotency_key':'stale-new-detected','ctx':ctx}
    out=[r['output'] for r in placeholder_steps([check,detect])]
    assert out[0]['exists'] is False and out[0]['ticket_id'] is None
    assert out[1]['created'] is True and out[1]['ticket_id']!=old


def test_recent_dry_run_ticket_and_any_real_action_stay_open():
    from datetime import timedelta
    ctx=context(cfg={'dry_run':True})
    old,recent=_seeded_ticket(timedelta(minutes=5))
    _,real=_seeded_ticket(timedelta(days=7),result='applied')
    out=[r['output'] for r in placeholder_steps([{'mode':'check','seat':'B','group_key':IP,'ctx':ctx,'static':recent}])]
    assert out[0]['exists'] is True and out[0]['ticket_id']==old
    out=[r['output'] for r in placeholder_steps([{'mode':'check','seat':'B','group_key':IP,'ctx':ctx,'static':real}])]
    assert out[0]['exists'] is True and out[0]['ticket_id']==old


def test_placeholder_rejects_stale_effect_and_unmatched_release_without_mutation():
    base={'mode':'record','seat':'B','group_key':IP,'case_id':'S10','asset_id':'haedam-portal',
          'stage':'applied','event_ids':['synthetic-one'],'action':{**ACTION,'finished_at':'2026-10-27T10:00:00+09:00'},
          'idempotency_key':'ph-apply','ctx':context(cfg={'dry_run':True})}
    effect={**base,'stage':'effect','action':{**base['action'],'effect_verified':True,'effect_verified_at':'2026-10-27T09:00:00+09:00'},'idempotency_key':'ph-effect'}
    release={**base,'stage':'released','action':{**ACTION,'via':'pfsense','action':'unblock','result':'released'},'idempotency_key':'ph-release'}
    result=placeholder_steps([base,effect,release,{'mode':'check','seat':'B','group_key':IP,'ctx':base['ctx']}])
    assert result[1]['output']['error']['code']=='STALE_EFFECT'
    assert result[2]['output']['error']['code']=='VALIDATION_ERROR'
    current=result[3]['output']
    assert current['status']=='responding' and len(current['actions'])==1
    assert current['actions'][0].get('effect_verified') is None


@pytest.mark.parametrize('changes', [
    {'ok':False}, {'exists':False,'ticket_id':None,'status':None,'actions':[]},
    {'ticket_id':'T-20261026-0099'}, {'status':'closed'}, {'status':'restored'},
    {'actions':None},
])
def test_pre_action_current_snapshot_refuses_errors_absence_changed_round_and_terminal(changes):
    ctx=context(record_ack={'ticket_id':TICKET,'created':True,'duplicate':False,'status':'open'})
    result=evaluate('haedam-30-s1-main.json','조치 전 티켓 대조 1',snapshot(ctx=ctx,**changes))
    assert result['error']=='TICKET_CURRENT_REQUIRED' and result['http_calls']==0


def test_pre_action_current_snapshot_preserves_new_status_and_context():
    ctx=context(record_ack={'ticket_id':TICKET,'created':True,'duplicate':False,'status':'open'})
    result=evaluate('haedam-30-s1-main.json','조치 전 티켓 대조 1',snapshot(ctx=ctx))['output']
    assert result['ticket_current'] is True and result['status']=='responding'
    assert 'record_ack' not in result['ctx'] and result['ctx']['event_id']==ctx['event_id']


def test_all_main_target_paths_require_a_fresh_group_lookup_after_record():
    for file in ['haedam-20-s12-main.json','haedam-30-s1-main.json','haedam-31-s4-main.json',S10,'haedam-33-s7-main.json']:
        w=json.loads((ROOT/'infra/n8n/workflows'/file).read_text(encoding='utf-8'))[0]
        nodes={n['name']:n for n in w['nodes']}
        incoming={name:[] for name in nodes}
        for source,value in w['connections'].items():
            for branch in value['main']:
                for edge in branch:
                    incoming[edge['node']].append(source)
        targets=[n for n in nodes if n=='차단 입력' or n.startswith('조치') and '입력 (' in n]
        for i,name in enumerate(targets,1):
            compare=f'조치 전 티켓 대조 {i}'
            check=f'조치 전 티켓 조회 {i}'
            assert incoming[name]==[compare] and incoming[compare]==[check]
            assert incoming[check]==[f'조치 전 티켓 조회 입력 {i}']
            assert nodes[check]['type']=='n8n-nodes-base.executeWorkflow'
            assert nodes[check]['parameters']['workflowId']['value']=='haedamResultLog01'
            result=evaluate(file,name,{'ok':True,'ticket_id':TICKET,'status':'open','ctx':context()})
            assert result['error']=='TICKET_CURRENT_REQUIRED' and result['http_calls']==0


GATED_MAINS=['haedam-30-s1-main.json','haedam-31-s4-main.json','haedam-32-s8-s10-main.json']


@pytest.mark.parametrize('file',GATED_MAINS)
def test_ticket_store_failure_stops_before_any_action_node(file):
    wf=load_wf(file)
    conn=wf['connections']
    assert conn['티켓 detected (haedam-10)']['main'][0][0]['node']=='티켓 저장됨?'
    ok_branch,fail_branch=conn['티켓 저장됨?']['main'][0][0]['node'],conn['티켓 저장됨?']['main'][1][0]['node']
    assert ok_branch=='조치 전 티켓 조회 입력 1' and fail_branch=='저장 실패 응답'   # stage2가 넣은 조치 전 조회가 조치의 첫 관문
    assert conn['저장 실패 응답']['main'][0][0]['node']=='응답: 저장 실패(조치 없음)'
    out=evaluate(file,'저장 실패 응답',{'ok':False,'error':{'code':'HTTP_503','message':'synthetic secret text'},
                                         'ctx':{'case_id':'S8','event_id':'e','src_ip':IP}})['output']
    assert out['no_action'] is True and out['verdict']=='ticket_store_failed_no_action'
    assert out['error']=={'code':'HTTP_503'} and 'secret' not in json.dumps(out)


def test_s8_s10_real_action_needs_literal_dry_run_false_in_body():
    body={'event_id':'e','asset_id':'haedam-portal','src_ip':IP,'case_id':'S8'}
    for extra in ({},{'dry_run':'false'},{'dry_run':0},{'dry_run':True}):
        cfg=evaluate('haedam-32-s8-s10-main.json','입력 검증·설정',{'body':{**body,**extra}})['output']['ctx']['cfg']
        assert cfg['dry_run'] is True
    cfg=evaluate('haedam-32-s8-s10-main.json','입력 검증·설정',{'body':{**body,'dry_run':False}})['output']['ctx']['cfg']
    assert cfg['dry_run'] is False and cfg['store_real'] is False


def test_s12_real_action_needs_literal_dry_run_false_and_ignores_test_baseline():
    body={'event_id':'e','asset_id':'haedam-portal','src_ip':IP}
    for extra in ({},{'dry_run':'false'},{'dry_run':0},{'dry_run':True}):
        cfg=evaluate('haedam-20-s12-main.json','입력 검증·설정',{'body':{**body,**extra}})['output']['ctx']['cfg']
        assert cfg['dry_run'] is True
    cfg=evaluate('haedam-20-s12-main.json','입력 검증·설정',{'body':{**body,'dry_run':False}})['output']['ctx']['cfg']
    assert cfg['dry_run'] is False and cfg['store_real'] is False
    # 실제 모드에서는 본문의 시험 기준·효과 단계가 적용되지 않는다(기준은 소스에 고정한 실측값만)
    cfg=evaluate('haedam-20-s12-main.json','입력 검증·설정',
                 {'body':{**body,'dry_run':False,'test_baseline_ms':1,'test_effect':True}})['output']['ctx']['cfg']
    assert cfg['dry_run'] is False and cfg['baseline_source']!='synthetic_override' and 'test_effect' not in cfg


def test_s4_real_lock_needs_literal_dry_run_false_and_a_test_account():
    body={'event_id':'e','asset_id':'haedam-portal','username':'zz_s4_1103'}
    for extra in ({},{'dry_run':'false'},{'dry_run':0},{'dry_run':True}):
        cfg=evaluate('haedam-31-s4-main.json','입력 검증·설정',{'body':{**body,**extra}})['output']['ctx']['cfg']
        assert cfg['dry_run'] is True
    cfg=evaluate('haedam-31-s4-main.json','입력 검증·설정',{'body':{**body,'dry_run':False}})['output']['ctx']['cfg']
    assert cfg['dry_run'] is False and cfg['store_real'] is False
    # 실제 잠금은 시험 계정(zz_)만. 일반 계정은 조치 없이 끝난다(관찰 모드는 그대로 진행)
    for name in ('staff01','admin','zz_','ZZ_S4',"zz_s4'--"):
        out=evaluate('haedam-31-s4-main.json','입력 검증·설정',{'body':{**body,'username':name,'dry_run':False}})['output']
        assert out['verdict']=='protected_account' and 'ctx' not in out
    assert evaluate('haedam-31-s4-main.json','입력 검증·설정',{'body':{**body,'username':'staff01'}})['output']['ctx']['cfg']['dry_run'] is True


def test_pf_ssh_node_sends_the_bare_forced_command_with_the_d_key():
    """11/03 실측 837: cwd가 있으면 node-ssh가 `cd / ;`를 앞에 붙여 PF forced command가 invalid_ssh_command로 거부했다."""
    wf=load_wf('haedam-14-pfsense-block.json')
    ssh=next(n for n in wf['nodes'] if n['type']=='n8n-nodes-base.ssh')
    assert ssh['parameters']['cwd']=="={{ '' }}"   # 필수값이라 빈 문자열 식, 실행 시 falsy → cd 접두어 없음
    assert ssh['parameters']['authentication']=='privateKey'
    assert ssh['credentials']=={'sshPrivateKey':{'id':'','name':'haedam-pf-response D'}}   # 이름만, 키 값·ID 없음
    assert ssh['parameters']['command']=='={{ $json.command }}'


def test_pf_summary_keeps_journal_state_and_failure_detail_for_reconciliation():
    """11/03 ACCEPT01: 841·843 대조에 journal 상태가 필요했는데 최종 요약에서 빠졌다(B 요청)."""
    prior={'요청 준비':{'ip':IP,'action':'block','request_id':'T-pf-block','requested_at':'2026-11-03T08:00:00Z','ctx':{'case_id':'S10'}}}
    journal={'claim_owner_id':'T','pending_request_id':'T-pf-block','pending_action':'block'}
    tool={'ok':False,'result':'failed','reason':'readback_timeout','changed':None,'replayed':False,'applied_verified':False,
          'state':{'configured':True,'rule_present':False,'table_present':False},'journal_state':journal,'failure_detail':'readback_timeout '+'x'*400}
    out=evaluate('haedam-14-pfsense-block.json','출력 해석',{'stdout':json.dumps(tool),'code':1},prior=prior)['output']
    assert out['result']=='failed' and out['ok'] is False and out['applied_verified'] is False   # 실패를 성공으로 바꾸지 않음
    assert out['journal_state']==journal and out['tool_state']==tool['state']
    assert out['failure_detail'].startswith('readback_timeout') and len(out['failure_detail'])==200
    ok={**tool,'ok':True,'result':'applied','changed':True,'applied_verified':True,'journal_state':None}
    ok.pop('failure_detail')
    out=evaluate('haedam-14-pfsense-block.json','출력 해석',{'stdout':json.dumps(ok),'code':0},prior=prior)['output']
    assert out['result']=='applied' and out['journal_state'] is None and out['failure_detail'] is None
