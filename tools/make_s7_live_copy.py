"""haedam-33(S7 메인)에서 시험 전용 복사본 haedam-34를 만든다. 네트워크·대상 실행 없음.

복사본이 공용 haedam-33과 다른 점(그 밖의 노드·연결은 그대로 둔다):
- 워크플로 id·이름·웹훅 경로를 분리한다 (haedamS7Live01, haedam-s7-live). 공용 haedam-s7은 건드리지 않는다.
- 호출자 인증: 웹훅에 헤더 인증(httpHeaderAuth 자격 증명 'haedam-s7-live caller')을 건다. 반입 직후에는
  자격 증명이 연결돼 있지 않아 게시되지 않으며(fail-closed), 미인증·오인증 요청은 워크플로 실행 전에 거절된다.
- 입력 검증 노드의 CFG를 dry_run=false, store_real=true로 고정한다. 요청 body로는 바꿀 수 없다.
- 회차 승인 기본 OFF: 저장소 파일은 승인 run_id가 비어 있어 모든 입력을 대응 없이(approval_off) 끝낸다.
  기록·AR 노드에 닿기 전이므로 수동·시험 실행도 호출 0건이다. 승인 회차 반입본은
  `--approve-run-id S7-20261102-AR01 --out <저장소 밖 경로>`로만 만든다(저장소 파일은 항상 OFF).
- run_id 고정·전달: 승인 run_id는 RUN_ID와 같아야 하고, ctx.run_id로 실어 haedam-15 입력까지 보낸다.
  haedam-15는 이 형식의 run_id를 Wazuh AR 인자([file_key, run_id])에 그대로 쓴다.
- 범위 제한: asset_id=haedam-portal, file_key=assets/zz_s7_1102_ar01.txt, change_type=added(quarantine)만.
- 항상 비게시(active=false)로 만든다.

사용: python tools/make_s7_live_copy.py          (infra/n8n/workflows/haedam-34-s7-live-acceptance.json 생성, 승인 OFF)
      python tools/make_s7_live_copy.py --check  (저장소 파일과 같은지만 확인, 쓰지 않음)
      python tools/make_s7_live_copy.py --approve-run-id S7-20261102-AR01 --out <저장소 밖 경로>
"""
import argparse
import copy
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "infra" / "n8n" / "workflows" / "haedam-33-s7-main.json"
DST = ROOT / "infra" / "n8n" / "workflows" / "haedam-34-s7-live-acceptance.json"

RUN_ID = "S7-20261102-AR01"
FILE_KEY = "assets/zz_s7_1102_ar01.txt"
CALLER_CREDENTIAL = "haedam-s7-live caller"

OLD_CFG = "const CFG = { dry_run: true, store_real: true };"
NEW_CFG = "const CFG = { dry_run: false, store_real: true };   // 시험 전용 복사본: 비게시 반입, D가 승인한 회차 직전에만 게시"
GATE_ANCHOR = "const missing = ['event_id', 'asset_id', 'file_key'].filter(k => !t[k]);\n"
CTX_ANCHOR = "cfg: CFG,"
STEP_NODE = "조치1 입력 (Wazuh 복구·격리)"
STEP_ANCHOR = "file_key: x.file_key } }];"


def gate_js(approved):
    return (
        f"const APPROVED_RUN_ID = '{approved}';   // 회차 승인: 저장소 파일은 항상 빈 값(OFF). 승인 반입본만 채운다\n"
        f"const RUN_ID = '{RUN_ID}';\n"
        "if (APPROVED_RUN_ID !== RUN_ID)\n"
        "  return [{ json: { ok: true, no_action: true, verdict: 'approval_off', event_id: t.event_id || null, case_id: 'S7' } }];\n"
        "// 입력에 run_id를 명시했다면(null 포함) 승인 회차와 정확히 같아야 한다. 덮어쓰지 않고 저장·AR 전에 거절한다.\n"
        "if (Object.prototype.hasOwnProperty.call(t, 'run_id') && t.run_id !== APPROVED_RUN_ID)\n"
        "  return [{ json: { ok: true, no_action: true, verdict: 'run_id_mismatch', event_id: t.event_id || null, case_id: 'S7' } }];\n"
        f"const SCOPE = {{ asset_id: 'haedam-portal', file_key: '{FILE_KEY}', change_type: 'added' }};   // 이번 실제 AR 시험 파일 하나만\n"
        "if (t.asset_id !== SCOPE.asset_id || t.file_key !== SCOPE.file_key || t.change_type !== SCOPE.change_type)\n"
        "  return [{ json: { ok: true, no_action: true, verdict: 'out_of_scope', event_id: t.event_id || null, case_id: 'S7' } }];\n"
    )


def build(approved=""):
    if approved not in ("", RUN_ID):
        raise ValueError(f"approve-run-id must be {RUN_ID}")
    wf = json.loads(SRC.read_text(encoding="utf-8"))
    wf = copy.deepcopy(wf[0] if isinstance(wf, list) else wf)
    wf["id"] = "haedamS7Live01"
    wf["name"] = f"haedam-34 S7 실제 AR 시험 전용 복사본 (비게시 기본, {FILE_KEY} 한정)"
    wf["active"] = False
    hit = {"webhook": 0, "validate": 0, "step": 0}
    for n in wf["nodes"]:
        p = n.get("parameters", {})
        if n["type"].endswith(".webhook"):
            p["path"] = "haedam-s7-live"
            p["authentication"] = "headerAuth"
            n["webhookId"] = "haedam-s7-live"
            n["credentials"] = {"httpHeaderAuth": {"id": "", "name": CALLER_CREDENTIAL}}
            hit["webhook"] += 1
        if n["name"] == "입력 검증·설정":
            js = p["jsCode"]
            assert OLD_CFG in js and GATE_ANCHOR in js and js.count(CTX_ANCHOR) == 1, \
                "haedam-33 검증 노드 형식이 달라졌다. 복사본 규칙을 다시 확인할 것"
            head, rest = js.split(OLD_CFG, 1)   # CFG 줄 전체(뒤의 주석 포함)를 새 줄로 바꾼다
            js = head + NEW_CFG + "\n" + rest.split("\n", 1)[1]
            js = js.replace(GATE_ANCHOR, GATE_ANCHOR + gate_js(approved))
            js = js.replace(CTX_ANCHOR, CTX_ANCHOR + " run_id: APPROVED_RUN_ID,")
            p["jsCode"] = js
            hit["validate"] += 1
        if n["name"] == STEP_NODE:
            js = p["jsCode"]
            assert js.count(STEP_ANCHOR) == 1, "haedam-33 조치1 입력 노드 형식이 달라졌다"
            p["jsCode"] = js.replace(STEP_ANCHOR, "file_key: x.file_key, run_id: x.run_id } }];")
            hit["step"] += 1
    assert hit == {"webhook": 1, "validate": 1, "step": 1}, hit
    return wf


def render(approved=""):
    return json.dumps([build(approved)], ensure_ascii=False, indent=1) + "\n"   # 다른 export처럼 목록 하나, LF


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--approve-run-id", default="")
    ap.add_argument("--out")
    a = ap.parse_args()
    if a.approve_run_id:
        if not a.out:
            raise SystemExit("--approve-run-id needs --out outside the repository")
        out = Path(a.out).resolve()
        if ROOT in out.parents:
            raise SystemExit("approved copy must not be written inside the repository")
        out.write_bytes(render(a.approve_run_id).encode("utf-8"))
        print("wrote approved copy", out)
        return
    text = render()
    if a.check:
        ok = DST.exists() and DST.read_bytes() == text.encode("utf-8")
        print("same" if ok else "DIFFERENT")
        raise SystemExit(0 if ok else 1)
    DST.write_bytes(text.encode("utf-8"))
    print("wrote", DST.relative_to(ROOT))


if __name__ == "__main__":
    main()
