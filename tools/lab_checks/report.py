"""Render only allowlisted comparison facts, never raw source contents."""


def render(comparison):
    lines = [f"# Lab check: {comparison['run_id']}", "",
             f"Environment: {comparison['environment']} / offline exports / {comparison['scope']}",
             f"Result: {comparison['status']} (exit {comparison['exit_code']})", "",
             "읽기 전용 파일 대조 결과입니다. 현재 장비 준비·실제 입력·최종 완료를 승인하지 않습니다.", "",
             "| 검사 | 사람 자리 | 판정 | 확인된 수 | 범위 밖 수 | 사유·다음 확인 |",
             "| --- | --- | --- | --- | --- | --- |"]
    for row in comparison["rows"]:
        count = "확인 불가" if row["count"] is None else str(row["count"])
        action = "" if row["verdict"] in ("pass", "not_applicable") else f"; {row['seat']} 원본/조회 범위 확인"
        lines.append(f"| {row['check_id']} | {row['seat']} | {row['verdict']} | {count} | {row['excluded_count']} | {row['reason_code']}{action} |")
    lines += ["", f"Card SHA-256: {comparison['card_sha256']}", "",
              "최신 현황 반영은 지정 편집자가 근거를 검토한 뒤 수행합니다. 미가동·정의 없음은 기능 성공이 아닙니다."]
    return "\n".join(lines) + "\n"
