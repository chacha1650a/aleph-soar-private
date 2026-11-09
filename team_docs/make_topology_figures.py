"""Draw the overall and per-seat topology figures from the proposal (section 3).

Usage: python team_docs/make_topology_figures.py --chrome PATH
Builds one HTML page per figure and, with --chrome (Chrome or Edge), renders
the PNGs that the docs link to. Addresses and ports are planned values.
"""
import argparse
import html
import math
import pathlib
import subprocess
import tempfile
import time

HERE = pathlib.Path(__file__).resolve().parent
W, H = 2000, 1240
FONT = "Malgun Gothic, Noto Sans KR, sans-serif"
COLOR = {"attack": "#DC2626", "normal": "#6B7280", "log": "#2563EB",
         "resp": "#059669", "health": "#D97706", "dim": "#D1D5DB"}
DASHED = {"log", "health"}

# name: (x, y, w, h, title, sub, small)
NODES = {
    "kali": (74, 253, 222, 95, "Kali 공격자", "203.0.113.10", ""),
    "normal": (74, 513, 222, 95, "정상 출발지", "203.0.113.100~109", "(Kali·외주 PC 추가 주소)"),
    "vendor": (74, 773, 222, 95, "외주 업체 PC", "203.0.113.20", "OpenVPN 클라이언트"),
    "portal": (586, 306, 228, 108, "해담시청 민원포털", "10.250.0.2 (팀 VPN)", "React + Flask · Wazuh agent"),
    "work": (586, 736, 228, 108, "민원 DB(MySQL)", "10.10.20.10", "3306(포털만)"),
    "gl": (1060, 236, 208, 88, "Graylog", "GELF 12201 · Syslog", ""),
    "n8n": (1060, 416, 208, 88, "n8n", "Webhook(같은 Docker)", ""),
    "wz": (1060, 670, 208, 88, "Wazuh manager", "1514·1515/tcp · API", ""),
    "dash": (1060, 870, 208, 88, "보안 대시보드·티켓", "티켓 저장소 API", ""),
}
# name: (kind, points, label, label position)
# label position: ("along", t) puts a tilted label on a straight edge, or (x, y) for a fixed spot.
EDGES = {
    "kali_pf": ("attack", [(296, 300), (390, 300), (390, 485)], "", None),
    "norm_pf": ("normal", [(296, 560), (345, 560)], "", None),
    "vendor_pf": ("normal", [(296, 820), (390, 820), (390, 635)], "OpenVPN 터널 10.10.40.0/24", (78, 905)),
    "pf_portal": ("normal", [(490, 485), (490, 360), (586, 360)], "", None),
    "pf_work": ("normal", [(490, 635), (490, 790), (586, 790)], "", None),
    "portal_db": ("normal", [(700, 414), (700, 736)], "", None),
    "gelf": ("log", [(814, 322), (1060, 290)], "GELF", ("along", 0.5)),
    "agent": ("log", [(814, 400), (1060, 700)], "agent", ("along", 0.4)),
    "wz_gl": ("log", [(1268, 700), (1288, 700), (1288, 290), (1268, 290)], "", None),
    "pf_gl": ("log", [(425, 635), (425, 1075), (880, 1075), (880, 248), (1060, 248)],
              "filterlog · Suricata · OpenVPN 로그", (500, 1066)),
    "gl_n8n": ("resp", [(1164, 324), (1164, 416)], "", None),
    "n8n_portal": ("resp", [(1060, 430), (814, 372)], "잠금·세션 회수·앱 차단", ("along", 0.5)),
    "n8n_pf": ("resp", [(1060, 490), (980, 490), (980, 1100), (460, 1100), (460, 635)],
               "IP 차단 · state 삭제", (500, 1124)),
    "n8n_wz": ("resp", [(1240, 504), (1240, 670)], "복구 요청", (1150, 575)),
    "wz_portal": ("resp", [(1060, 735), (780, 414)], "active response", ("along", 0.55)),
    "n8n_dash": ("resp", [(1268, 480), (1308, 480), (1308, 900), (1268, 900)], "티켓", (1272, 800)),
    "health": ("health", [(1060, 458), (790, 414)], "헬스체크(S12)", ("along", 0.5)),
}

FIGURES = [
    {
        "file": "토폴로지-00-전체",
        "title": "NoBugs 전체 네트워크 토폴로지 (해담시청)",
        "sub": "학원 PC 4대 분산 배치 · PC 사이는 pfSense 팀 VPN(10.250.0.0/24)으로만 연결 · 10/22 연결 확인 반영 · 미시험 값은 계획값",
        "accent": "#374151", "panel": "구역과 규칙 요약", "panel_sub": "기획서 ③ 망 분리 정책 · 10/22 기준",
        "kali": "203.0.113.10", "nodes": None, "edges": None, "marks": [],
        "sections": [
            ("자리별 공격 출발지(Kali 추가 주소)", ["A 203.0.113.11~19 · B 21~29 · C 31~39 · D 41~49",
                                         "정상 출발지 203.0.113.100~109"]),
            ("팀 VPN", ["pfSense TRANSIT(학원 유선망) UDP 1195 → 터널 10.250.0.0/24",
                       "주소(10/22 고정): A 포털 .2 · C .3 · D .100",
                       "터널 안 기본 차단, 아래 연결만 허용 · 팀원 PC 간 직접 통신 끔"]),
            ("허용 연결", ["외부 → A 포털: WAN 80 전달만 (그 외 차단 = S10 경계 신호)",
                         "외부 → 업무망·관리망·팀 VPN 주소: 차단",
                         "A 포털 → B DB: 3306만",
                         "A 포털 → D Graylog GELF, A agent → C Wazuh 1514·1515",
                         "pfSense → D Syslog, C Wazuh → D 경보(TCP 5514)",
                         "D n8n → 포털 대응 API · pfSense SSH · Wazuh API · 티켓 API"]),
            ("주의", ["출발지 보존: WAN 전달·터널에서 바꾸지 않음 (10/21 확인)",
                    "Windows의 VPN 연결 ≠ VM·Docker 서비스 연결: 도착을 실측",
                    "웹 화면·n8n Webhook은 각 PC 안(127.0.0.1)",
                    "B의 VMnet2·3은 수업 설정 보존, 외부 구역은 VMnet5"]),
        ],
    },
    {
        "file": "토폴로지-A-S1-S4-계정탈취",
        "title": "A 자리 · S1 저속 브루트포스 · S4 실패 뒤 성공 (계정 탈취)",
        "sub": "담당 whiteclover0542 · 기밀성 · 앱 로그 → Graylog · 계획값 · 미구현·미시험",
        "accent": "#B91C1C", "panel": "A · S1·S4 흐름", "panel_sub": "공격 출발지 203.0.113.11~19 · 정상 출발지 203.0.113.100~109",
        "kali": "203.0.113.11~19",
        "nodes": {"kali", "normal", "portal", "work", "gl", "n8n", "dash"},
        "edges": {"kali_pf", "norm_pf", "pf_portal", "portal_db", "gelf", "gl_n8n", "n8n_portal", "n8n_dash"},
        "marks": [(1, "kali_pf", 0.3), (1, "pf_portal", 0.8), (2, "gelf", 0.85), (3, "gl_n8n", 0.5),
                  (4, "n8n_portal", 0.08), (5, "n8n_dash", 0.5)],
        "steps": ["Kali가 포털 로그인을 반복 시도(S1: 천천히 실패, S4: 실패 뒤 성공)",
                  "포털(A)이 로그인 실패·성공 이벤트를 GELF로 Graylog(D)에 보냄",
                  "이벤트 발동 → Webhook으로 n8n 실행",
                  "S1: 출발지 차단(앱 112, 자동 만료 없음). S4: username으로 계정 잠금 + 기존 세션 회수(111)",
                  "티켓(114)·보안 대시보드(C) 기록"],
        "sections": [
            ("탐지 규칙", ["S1 count()>8 · 30분 · username + src_ip",
                       "S4 실패·성공 합계 count()>5 · 10분 · username + src_ip (순서 무관)",
                       "포털 규칙은 모두 source:haedam-portal 조건"]),
            ("효과 확인", ["S1: 같은 IP 새 요청 403, 같은 계정은 다른 정상 출발지에서 로그인 가능",
                       "S4: 로그인 거부(401, 잠긴 계정도 같은 안내), 대응 전에 발급된 세션 거부"]),
            ("원복", ["S1: 담당자가 출발지 차단 해제(자동 만료 없음)",
                    "S4: 탈취면 재설정 뒤 해제, 오탐이면 관리자 해제(세션은 되살리지 않음)"]),
        ],
    },
    {
        "file": "토폴로지-B-S8-S10-스캔침입",
        "title": "B 자리 · S8 스캐너→브루트포스 · S10 전 계층 관통",
        "sub": "담당 myeongjundev · 기밀성(네트워크) · Suricata·pfSense 로그 + 앱 로그 · 계획값 · 미구현·미시험",
        "accent": "#1D4ED8", "panel": "B · S8·S10 흐름", "panel_sub": "공격 출발지 203.0.113.21~29",
        "kali": "203.0.113.21~29",
        "nodes": {"kali", "portal", "gl", "n8n", "dash"},
        "edges": {"kali_pf", "pf_portal", "gelf", "pf_gl", "gl_n8n", "n8n_portal", "n8n_pf", "n8n_dash"},
        "marks": [(1, "kali_pf", 0.3), (2, "pf_portal", 0.8), (3, "gelf", 0.85), (3, "pf_gl", 0.6),
                  (4, "gl_n8n", 0.5), (5, "n8n_portal", 0.08), (5, "n8n_pf", 0.5), (6, "n8n_dash", 0.5)],
        "steps": ["Kali가 포트 스캔·경계 두드림 → pfSense 차단 기록, Suricata 경보",
                  "포털 탐색(web-scan) 뒤 로그인 반복",
                  "pfSense filterlog·Suricata는 Syslog로, 포털은 GELF로 Graylog(D)에 보냄",
                  "S8·S10 이벤트 발동 → n8n 실행",
                  "앱 IP 차단(112) + S10은 n8n이 팀 VPN으로 pfSense에 SSH 접속해 경계 차단(easyrule)과 기존 연결 상태 삭제(pfctl -k)",
                  "티켓(114) 1건으로 묶음(같은 자리·같은 출발지)"],
        "sections": [
            ("탐지 규칙", ["S8 card(rule)>1 · 15분 · src_ip (web-scan + login-bruteforce, 순서 무관)",
                       "S10 pfsense-block + web-scan + login-bruteforce만 검색, card(rule)>2 · 15분 · src_ip"]),
            ("효과 확인 · 원복", ["같은 IP 새 연결 실패, 차단 전 연결도 끊겼는지 확인",
                            "경계 차단 → 앱 차단 순서로 해제",
                            "n8n → pfSense는 팀 VPN 터널 주소(10.250.0.1)의 SSH, IPv4만"]),
        ],
    },
    {
        "file": "토폴로지-C-S7-홈페이지변조",
        "title": "C 자리 · S7 홈페이지 변조",
        "sub": "담당 shk12170-dev · 무결성 · Wazuh FIM + 웹 접근 로그 · 계획값 · 미구현·미시험",
        "accent": "#7C3AED", "panel": "C · S7 흐름", "panel_sub": "접근 출발지 203.0.113.31~39",
        "kali": "203.0.113.31~39",
        "nodes": {"kali", "portal", "gl", "wz", "n8n", "dash"},
        "edges": {"kali_pf", "pf_portal", "gelf", "agent", "wz_gl", "gl_n8n", "n8n_wz", "wz_portal", "n8n_dash"},
        "marks": [(1, (586, 300)), (2, "kali_pf", 0.3), (2, "pf_portal", 0.8), (3, "gelf", 0.85),
                  (3, "agent", 0.75), (3, "wz_gl", 0.5), (4, "gl_n8n", 0.5), (5, "n8n_wz", 0.5),
                  (5, "wz_portal", 0.15), (6, "n8n_dash", 0.5)],
        "steps": ["포털(A) 웹 디렉터리의 파일이 바뀌거나 새 파일이 생김(시험에서 재현)",
                  "Kali가 그 경로로 접근",
                  "A의 Wazuh agent realtime FIM 경보 → C manager → D Graylog, 웹 접근 로그는 GELF",
                  "S7 이벤트 발동 → n8n 실행",
                  "n8n이 Wazuh API(C)로 active response 요청 → 에이전트가 바뀐 파일은 원본 복구(해시 대조), 새 파일은 격리(117, 안 되면 포털 API)",
                  "티켓(114)·보안 대시보드(C) 기록"],
        "sections": [
            ("탐지 규칙", ["card(signal_kind)>1 · 10분 · 자산 + 파일 키(웹 루트 기준 상대 경로)",
                       "웹 접근은 성공 응답(file-access)만 · 화면 경로는 index.html 키",
                       "정상 배포·복구본은 해시 목록(lookup table)으로 허용"]),
            ("효과 확인 · 원복", ["바뀐 경로는 원본 응답, 새 파일 경로는 404",
                            "원본(기준본)은 감시 디렉터리 밖 읽기 전용 위치",
                            "원복: 격리한 시험 파일 삭제, 원본 해시 확인"]),
        ],
    },
    {
        "file": "토폴로지-D-S12-서비스장애-chacha1650a",
        "title": "D 자리 · S12 요청 폭주로 인한 서비스 장애",
        "sub": "담당 chacha1650a · 가용성 · 요청 수 + 헬스체크 응답시간 · 계획값 · 미구현·미시험",
        "accent": "#C2410C", "panel": "D · S12 흐름", "panel_sub": "공격 203.0.113.41~49 · 정상 203.0.113.100~109",
        "kali": "203.0.113.41~49",
        "nodes": {"kali", "normal", "portal", "work", "gl", "n8n", "dash"},
        "edges": {"kali_pf", "norm_pf", "pf_portal", "portal_db", "gelf", "gl_n8n", "health",
                  "n8n_portal", "n8n_pf", "n8n_dash"},
        "marks": [(1, "kali_pf", 0.3), (1, "pf_portal", 0.8), (2, "gelf", 0.85), (3, "gl_n8n", 0.5),
                  (4, "health", 0.2), (5, "n8n_portal", 0.08), (5, "n8n_pf", 0.5), (6, "n8n_dash", 0.5)],
        "steps": ["Kali가 한 출발지에서 포털로 요청을 몰아 보냄(정상 출발지는 평소 요청)",
                  "포털(A)이 요청 이벤트를 GELF로 Graylog(D)에 보냄",
                  "출발지별 요청 수 이벤트 발동(후보) → n8n 실행",
                  "n8n이 팀 VPN으로 DB를 읽는 경로를 헬스체크, 연속 횟수로 기준선 초과 판정(최종 탐지)",
                  "초과일 때만 출발지 차단(112, 속도 제한은 확장). 차단 지점(앱 403 / pfSense)은 사전 시험으로 결정",
                  "티켓(114), 회복 확인(116)"],
        "sections": [
            ("탐지 규칙", ["출발지별 count()>N · 1분 · src_ip",
                       "요청 수만 초과(응답시간 정상)는 Graylog는 발동하지만 대응 없음",
                       "MTTD 종점은 n8n 판정 시각"]),
            ("효과 확인 · 원복", ["회복: 정상 출발지 연속 K회 응답시간이 기준선 안(시민과 같은 외부 경로)",
                            "n8n 헬스체크(팀 VPN 경로)는 대응 판정용",
                            "원복: 차단 해제 뒤 응답시간 기준선 확인"]),
        ],
    },
]


def esc(s):
    return html.escape(s, quote=True)


def text_width(s, size):
    return sum(size if ord(c) > 0x2E80 else (size * 0.33 if c == " " else size * 0.58) for c in s)


def wrap(s, size, width):
    lines, cur = [], ""
    for word in s.split(" "):
        trial = (cur + " " + word).strip()
        if cur and text_width(trial, size) > width:
            lines.append(cur)
            cur = word
        else:
            cur = trial
    return lines + [cur]


def text(x, y, s, size, color="#111827", weight="normal", anchor="start", extra=""):
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" font-weight="{weight}" fill="{color}" '
            f'text-anchor="{anchor}"{extra}>{esc(s)}</text>')


def point_on(points, t):
    segs = list(zip(points, points[1:]))
    lengths = [math.dist(a, b) for a, b in segs]
    d = t * sum(lengths)
    for (a, b), ln in zip(segs, lengths):
        if d <= ln:
            r = d / ln
            return a[0] + (b[0] - a[0]) * r, a[1] + (b[1] - a[1]) * r
        d -= ln
    return points[-1]


def figure_svg(fig):
    out = []
    add = out.append
    active_nodes = fig["nodes"] or set(NODES)
    active_edges = fig["edges"] or set(EDGES)
    attack_path = fig["nodes"] is not None
    add(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" font-family="{FONT}">')
    add("<defs>")
    for kind, c in COLOR.items():
        add(f'<marker id="a-{kind}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="4" markerHeight="4" orient="auto-start-reverse">'
            f'<path d="M0,0 L10,5 L0,10 z" fill="{c}"/></marker>')
    add("</defs>")
    add(f'<rect width="{W}" height="{H}" fill="#FFFFFF"/>')
    add(text(40, 70, fig["title"], 40, weight="bold"))
    add(text(40, 103, fig["sub"], 19, "#4B5563"))
    lx = 40
    for kind, label in [("attack", "공격"), ("normal", "정상·서비스"), ("log", "로그·경보"),
                        ("resp", "탐지 → 대응"), ("health", "헬스체크(S12)")]:
        dash = ' stroke-dasharray="9 6"' if kind in DASHED else ""
        add(f'<line x1="{lx}" y1="126" x2="{lx + 46}" y2="126" stroke="{COLOR[kind]}" stroke-width="4"{dash}/>')
        add(text(lx + 56, 132, label, 17, "#374151"))
        lx += 56 + text_width(label, 17) + 34

    def zone(x, y, w, h, fill, stroke, label, ly=None):
        add(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="14" fill="{fill}" stroke="{stroke}" stroke-width="2"/>')
        add(text(x + 12, ly or y + 24, label, 15, "#374151", "bold"))

    def pc(points, label, ly):
        p = " ".join(f"{x},{y}" for x, y in points)
        add(f'<polygon points="{p}" fill="#F8FAFC" stroke="#64748B" stroke-width="2.5" stroke-linejoin="round"/>')
        add(text(points[0][0] + 12, ly, label, 17, "#111827", "bold"))

    # Four academy PCs; B's outline is an L so A's portal VM can sit above B's work zone.
    pc([(30, 150), (540, 150), (540, 580), (860, 580), (860, 1020), (30, 1020)], "B PC · pfSense·민원 DB·Kali (VMware)", 180)
    zone(60, 200, 250, 760, "#FEF2F2", "#FCA5A5", "외부 VMnet5  203.0.113.0/24")
    zone(560, 600, 280, 360, "#ECFDF5", "#86EFAC", "업무망 VMnet4  10.10.20.0/24", 945)
    pc([(550, 150), (860, 150), (860, 560), (550, 560)], "A PC · 포털 VM (VMware Ubuntu)", 180)
    zone(565, 200, 280, 340, "#EFF6FF", "#93C5FD", "DMZ(포털) · 팀 VPN .2")
    pc([(1000, 150), (1320, 150), (1320, 560), (1000, 560)], "D PC · Graylog·n8n", 180)
    zone(1020, 195, 285, 350, "#F5F3FF", "#C4B5FD", "관제(Docker) · 팀 VPN .100")
    pc([(1000, 580), (1320, 580), (1320, 1020), (1000, 1020)], "C PC · Wazuh·대시보드", 608)
    zone(1020, 625, 285, 380, "#F5F3FF", "#C4B5FD", "관제(Docker) · 팀 VPN .3")
    add(text(675, 1170, "PC 사이 화살표는 모두 팀 VPN 안의 경로 · pfSense TRANSIT UDP 1195(학원 유선망은 전송로로만) · "
             "터널 기본 차단 + 연결별 허용", 16, "#111827", "bold", "middle"))

    halo = ' stroke="#FFFFFF" stroke-width="5" paint-order="stroke"'
    for name, (kind, pts, label, pos) in EDGES.items():
        on = name in active_edges
        k = "attack" if on and attack_path and name == "pf_portal" else kind
        color = COLOR[k] if on else COLOR["dim"]
        dash = ' stroke-dasharray="10 7"' if kind in DASHED else ""
        p = " ".join(f"{x},{y}" for x, y in pts)
        add(f'<polyline points="{p}" fill="none" stroke="{color}" stroke-width="{4 if on else 3}"{dash} '
            f'marker-end="url(#a-{k if on else "dim"})"/>')
        if not (label and on):
            continue
        if pos[0] == "along":
            (x1, y1), (x2, y2) = sorted(pts)
            cx, cy = point_on([(x1, y1), (x2, y2)], pos[1])
            ang = math.degrees(math.atan2(y2 - y1, x2 - x1))
            nx, ny = math.sin(math.radians(ang)), -math.cos(math.radians(ang))
            cx, cy = cx + nx * 9, cy + ny * 9
            add(text(cx, cy, label, 14, color, "bold", "middle",
                     f' transform="rotate({ang:.1f} {cx:.1f} {cy:.1f})"{halo}'))
        else:
            add(text(pos[0], pos[1], label, 14, color, "bold", "start", halo))

    hx, hy = 440, 560
    hex_pts = f"{hx - 95},{hy} {hx - 60},{hy - 75} {hx + 60},{hy - 75} {hx + 95},{hy} {hx + 60},{hy + 75} {hx - 60},{hy + 75}"
    add(f'<polygon points="{hex_pts}" fill="#FFFFFF" stroke="#111827" stroke-width="3"/>')
    add(text(hx, hy - 18, "pfSense", 22, weight="bold", anchor="middle"))
    add(text(hx, hy + 8, "WAN .1 · 업무망 .1", 15, "#374151", anchor="middle"))
    add(text(hx, hy + 30, "팀 VPN 서버 10.250.0.1", 13, "#4B5563", anchor="middle"))

    for name, (x, y, w, h, title, sub, small) in NODES.items():
        on = name in active_nodes
        if name == "kali":
            sub = fig["kali"]
        fill, stroke, c1, c2 = ("#FFFFFF", "#111827", "#111827", "#374151") if on else ("#F3F4F6", "#D1D5DB", "#9CA3AF", "#9CA3AF")
        add(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" fill="{fill}" stroke="{stroke}" stroke-width="3"/>')
        lines = [(title, 21, "bold", c1), (sub, 16, "normal", c2)] + ([(small, 14, "normal", c2)] if small else [])
        y0 = y + h / 2 - (len(lines) - 1) * 12 + 6
        for i, (s, size, weight, col) in enumerate(lines):
            add(text(x + w / 2, y0 + i * 25, s, size, col, weight, "middle"))

    for mark in fig["marks"]:
        n, where = mark[0], mark[1]
        x, y = where if isinstance(where, tuple) else point_on(EDGES[where][1], mark[2])
        add(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="15" fill="{fig["accent"]}" stroke="#FFFFFF" stroke-width="2"/>')
        add(text(x, y + 6, str(n), 16, "#FFFFFF", "bold", "middle"))

    px, py, pw = 1350, 150, 610
    add(f'<rect x="{px}" y="{py}" width="{pw}" height="1030" rx="14" fill="#FFFFFF" stroke="#E5E7EB" stroke-width="2"/>')
    add(f'<path d="M{px},{py + 14} a14,14 0 0 1 14,-14 h{pw - 28} a14,14 0 0 1 14,14 v76 h-{pw} z" fill="{fig["accent"]}"/>')
    add(text(px + 24, py + 42, fig["panel"], 28, "#FFFFFF", "bold"))
    add(text(px + 24, py + 72, fig["panel_sub"], 16, "#F3F4F6"))
    y = py + 125
    if fig.get("steps"):
        add(text(px + 24, y, "단계", 22, fig["accent"], "bold"))
        y += 34
        for i, s in enumerate(fig["steps"], 1):
            add(f'<circle cx="{px + 38}" cy="{y - 6}" r="13" fill="{fig["accent"]}"/>')
            add(text(px + 38, y - 1, str(i), 14, "#FFFFFF", "bold", "middle"))
            lines = wrap(s, 17, pw - 90)
            for j, line in enumerate(lines):
                add(text(px + 62, y + j * 24, line, 17, "#1F2937"))
            y += 24 * len(lines) + 8
        y += 14
    for title, items in fig["sections"]:
        add(text(px + 24, y, title, 22, fig["accent"], "bold"))
        y += 32
        for s in items:
            lines = wrap(s, 17, pw - 70)
            for j, line in enumerate(lines):
                add(text(px + 44, y + j * 24, ("• " if j == 0 else "  ") + line, 17, "#1F2937"))
            y += 24 * len(lines) + 6
        y += 14
    if y > py + 1020:
        raise SystemExit(f"{fig['file']}: panel text overflows ({y})")
    add(text(40, 1225, "출처: 기획서 ③·④·⑤ · 10/22 기준 · 포털 → D 로그 도착 확인, 탐지·대응 연동 시험 전 · 미시험 값은 계획값", 16, "#6B7280"))
    add("</svg>")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--chrome", help="Chrome or Edge executable; renders PNGs when given")
    ap.add_argument("--out", default=str(HERE))
    args = ap.parse_args()
    out = pathlib.Path(args.out)
    for fig in FIGURES:
        page = out / f'{fig["file"]}.html'
        page.write_text('<!doctype html><meta charset="utf-8"><body style="margin:0">' + figure_svg(fig), encoding="utf-8")
        if args.chrome:
            png = out / f'{fig["file"]}.png'
            old = png.stat().st_mtime if png.exists() else 0
            # A separate profile keeps an already open browser from taking over the headless run.
            with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as profile:
                subprocess.run([args.chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars",
                                f"--user-data-dir={profile}", f"--window-size={W},{H}",
                                f"--screenshot={png}", page.as_uri()], check=True, capture_output=True)
                # On Windows the launcher can exit before the screenshot is written, so wait for it.
                for _ in range(60):
                    if png.exists() and png.stat().st_mtime > old:
                        time.sleep(1)
                        break
                    time.sleep(0.5)
                else:
                    raise SystemExit(f"{png.name}: screenshot was not written")
            page.unlink()
        print(fig["file"])


if __name__ == "__main__":
    main()
