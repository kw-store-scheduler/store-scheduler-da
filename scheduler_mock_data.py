"""
스케줄러 테스트용 목 데이터 모음
=================================

주간 시나리오 (D=7, 0=월 ~ 6=일)
  W01  기본 5인팀       - 정상 운영
  W02  인원부족_주말    - 주말 커버 불가  [shortage 테스트]
  W03  PT_복수해        - PT 주말 전담    [has_multiple_optimal 테스트]
  W04  대형팀_10인      - 3교대, 야간수당
  W05  야간_주간_분리   - 야간전담/주간전담 분리
  W06  카페_3교대_다수PT - 3교대, PT 4/7명, 교대별 전담 PT
  W07  편의점_24시간   - 24h 3교대, 야간수당 50%, 야간PT 3명
  W08  완전스케쥴제     - 고정 휴무 없음, 모델이 휴무 분배 (롤링)
  W09  패스트푸드_피크  - 피크타임 3교대, PT 6명 교대별 전담

월간 시나리오 (D=30, 2025년 6월 / June 1 = 일요일)
  공휴일: 6월 6일 현충일
  M01  소형매장 5인     - 교수님 피드백 예시 확장
  M02  중형매장 7인     - 휴가 집중, 대체 근무 필요
  M03  성수기 대형팀 12인 - 신입 투입, 높은 목표 인원
  M04  에지케이스 2인   - 심각한 인원 부족
  M05  편의점_월간_3교대 - 24h 3교대, 야간수당 50%, 8인
  M06  카페_롤링_월간   - 3교대, 8인 전원 완전 스케쥴제
"""

from datetime import date


# ─────────────────────────────────────────────────────────────
# 헬퍼: 2025년 6월 available_days 생성
# ─────────────────────────────────────────────────────────────
#   인덱스 = 날짜 - 1  (June 1 = idx 0, June 30 = idx 29)
#   요일: 0=월 1=화 2=수 3=목 4=금 5=토 6=일  (Python weekday())
#
#   June 2025 요일 조견표
#   일: idx  0  7 14 21 28
#   월: idx  1  8 15 22 29
#   화: idx  2  9 16 23
#   수: idx  3 10 17 24
#   목: idx  4 11 18 25
#   금: idx  5 12 19 26   ← 6월 6일(idx5) = 현충일
#   토: idx  6 13 20 27

def june2025_avail(
    fixed_off_weekdays=None,   # 매주 쉬는 요일 [0=월..6=일]
    off_dates=None,            # 특정 쉬는 날짜 (1~30)
    only_dates=None,           # 이 날짜만 출근 (PT 지정 등)
    last_date=None,            # 마지막 출근 날짜 (퇴사)
    first_date=None,           # 첫 출근 날짜 (신규 입사)
):
    fixed_off_weekdays = fixed_off_weekdays or []
    off_dates          = set(off_dates or [])

    avail = []
    for day in range(1, 31):
        d = date(2025, 6, day)
        if last_date  and day > last_date:  continue
        if first_date and day < first_date: continue
        if only_dates is not None and day not in only_dates: continue
        if d.weekday() in fixed_off_weekdays: continue
        if day in off_dates: continue
        avail.append(day - 1)  # 0-indexed
    return avail


# 6월 Sat/Sun 날짜 목록 (1-indexed, PT 스케줄 계산용)
_JUNE_SAT  = [7, 14, 21, 28]
_JUNE_SUN  = [1, 8, 15, 22, 29]
_JUNE_WKND = sorted(_JUNE_SAT + _JUNE_SUN)


# ─────────────────────────────────────────────────────────────
# ══════════ 주간 시나리오 (D = 7) ════════════════════════════
# ─────────────────────────────────────────────────────────────

# ── W01 기본 5인팀 ─────────────────────────────────────────
#  정상 운영 케이스. 오픈/마감 2교대.
#  기대: OPTIMAL · shortage 없음 · has_multiple_optimal 가능
W01_기본_5인팀 = {
    "label": "W01 기본 5인팀 (정상 운영)",
    "note": (
        "매니져 월~토 / 시니어 화~일 / 주니어2명 각각 주중+주말 일부 / PT 주말."
        " 인원 충분. shortage 없어야 함."
    ),
    "config": {
        "employees": [
            {
                "id": "mgr", "name": "매니져",
                "available_days": [0,1,2,3,4,5], "preferred_shifts": [0],
                "off_requests": [{"day": 4, "type": "prefer"}],  # 금요일 쉬고 싶음
            },
            {
                "id": "snr", "name": "시니어",
                "available_days": [1,2,3,4,5,6], "preferred_shifts": [0,1],
                "off_requests": [{"day": 6, "type": "must"}],    # 일요일 필수 휴무
            },
            {"id": "jnr_a", "name": "주니어A",  "available_days": [0,2,3,4,5],     "preferred_shifts": [1]},
            {
                "id": "jnr_b", "name": "주니어B",
                "available_days": [1,3,4,5,6], "preferred_shifts": [1],
                "off_requests": [{"day": 3, "type": "prefer"}],  # 목요일 쉬고 싶음
            },
            {"id": "pt",    "name": "PT",       "available_days": [5,6],            "preferred_shifts": [0,1]},
        ],
        "shifts": [
            {"name": "오픈", "hours": 4, "is_night": False},
            {"name": "마감", "hours": 4, "is_night": False},
        ],
        "target_staff": [2, 2],
        "min_staff":    [1, 1],
        "base_hourly":  9860,
        "night_bonus":  0.0,
        "time_limit":   10,
    },
}

# ── W02 인원부족_주말 ───────────────────────────────────────
#  주중 직원 3명, 주말 가용 인원 0명.
#  기대: OPTIMAL · 토/일 오픈+마감 모두 shortage(4건)
W02_인원부족_주말 = {
    "label": "W02 인원부족_주말 [shortage 테스트]",
    "note": (
        "직원 3명 모두 주중만 가능. 토/일 가용 인원 0명."
        " 기대: 토요일·일요일 오픈/마감 각각 1명 부족(총 4건)."
    ),
    "config": {
        "employees": [
            {"id": "e1", "name": "직원A", "available_days": [0,1,2,3,4], "preferred_shifts": [0]},
            {"id": "e2", "name": "직원B", "available_days": [0,1,2,3,4], "preferred_shifts": [1]},
            {"id": "e3", "name": "직원C", "available_days": [1,2,3,4],   "preferred_shifts": [0,1]},
        ],
        "shifts": [
            {"name": "오픈", "hours": 4, "is_night": False},
            {"name": "마감", "hours": 4, "is_night": False},
        ],
        "target_staff": [1, 1],
        "min_staff":    [1, 1],
        "base_hourly":  9860,
        "night_bonus":  0.0,
        "time_limit":   10,
    },
}

# ── W03 PT 주말전담 (복수 최적해 유발) ─────────────────────
#  풀타임 4명(주중) + PT 2명(주말 전담).
#  PT끼리 오픈·마감 교환이 자유로워 복수 최적해 발생.
#  기대: OPTIMAL · has_multiple_optimal=True
W03_PT_복수해 = {
    "label": "W03 PT 주말전담 [복수 최적해 테스트]",
    "note": (
        "PT 두 명이 토/일 오픈·마감을 서로 바꿔 배치 가능."
        " 기대: has_multiple_optimal=True, alt_schedules 1~2개."
    ),
    "config": {
        "employees": [
            {"id": "ft1", "name": "풀타임1",   "available_days": [0,1,2,3,4],   "preferred_shifts": [0]},
            {"id": "ft2", "name": "풀타임2",   "available_days": [0,1,2,3,4],   "preferred_shifts": [0]},
            {"id": "ft3", "name": "풀타임3",   "available_days": [1,2,3,4],     "preferred_shifts": [1]},
            {"id": "ft4", "name": "풀타임4",   "available_days": [0,2,3,4],     "preferred_shifts": [1]},
            {"id": "pt1", "name": "PT-주말1",  "available_days": [5,6],          "preferred_shifts": [0,1]},
            {"id": "pt2", "name": "PT-주말2",  "available_days": [5,6],          "preferred_shifts": [0,1]},
        ],
        "shifts": [
            {"name": "오픈", "hours": 4, "is_night": False},
            {"name": "마감", "hours": 4, "is_night": False},
        ],
        "target_staff": [2, 2],
        "min_staff":    [1, 1],
        "base_hourly":  9860,
        "night_bonus":  0.0,
        "time_limit":   10,
    },
}

# ── W04 대형팀 10인 (3교대, 야간수당) ──────────────────────
#  10인 3교대. 저녁 교대 야간수당 포함.
#  기대: OPTIMAL · shortage 없음 · 야간전담이 저녁교대 집중
W04_대형팀_10인 = {
    "label": "W04 대형팀 10인 (3교대, 야간수당)",
    "note": (
        "10명, 오전/오후/저녁 3교대. 저녁 야간수당 50%."
        " 야간전담(i) 직원이 저녁교대 선호 → 목적함수 최소화 시 저녁 집중."
        " shortage 없어야 함."
    ),
    "config": {
        "employees": [
            {"id": "a", "name": "매니져",    "available_days": [0,1,2,3,4],     "preferred_shifts": [0]},
            {"id": "b", "name": "시니어A",   "available_days": [1,2,3,4,5,6],   "preferred_shifts": [0,1]},
            {"id": "c", "name": "시니어B",   "available_days": [0,1,3,4,5],     "preferred_shifts": [1]},
            {"id": "d", "name": "주니어A",   "available_days": [0,2,3,4,5],     "preferred_shifts": [1,2]},
            {"id": "e", "name": "주니어B",   "available_days": [1,2,3,5,6],     "preferred_shifts": [2]},
            {"id": "f", "name": "주니어C",   "available_days": [0,1,2,4,6],     "preferred_shifts": [1]},
            {"id": "g", "name": "주니어D",   "available_days": [2,3,4,5,6],     "preferred_shifts": [0]},
            {"id": "h", "name": "PT-주말",   "available_days": [5,6],            "preferred_shifts": [0,1]},
            {"id": "i", "name": "야간전담",  "available_days": [1,2,3,4,5],     "preferred_shifts": [2]},
            {"id": "j", "name": "파트J",     "available_days": [0,3,4,5,6],     "preferred_shifts": [0,1]},
        ],
        "shifts": [
            {"name": "오전", "hours": 4, "is_night": False},
            {"name": "오후", "hours": 4, "is_night": False},
            {"name": "저녁", "hours": 4, "is_night": True},
        ],
        "target_staff": [2, 3, 2],
        "min_staff":    [1, 2, 1],
        "base_hourly":  9860,
        "night_bonus":  0.5,
        "time_limit":   15,
    },
}

# ── W05 야간주간 분리팀 ────────────────────────────────────
#  주간전담 3명 / 야간전담 2명 / 겸직 1명.
#  인건비 최적화 시 야간전담이 저녁교대로 몰려야 함.
#  기대: OPTIMAL · 야간 인건비 패턴 검증
W05_야간주간_분리 = {
    "label": "W05 야간·주간 분리팀 (인건비 최적화 검증)",
    "note": (
        "야간전담 직원이 저녁교대 선호. 비선호 교대 배정 시 패널티."
        " 목적함수 최소화 → 야간전담은 저녁, 주간전담은 오전/오후로 분리."
    ),
    "config": {
        "employees": [
            {"id": "d1", "name": "주간전담A", "available_days": [0,1,2,3,4],   "preferred_shifts": [0,1]},
            {"id": "d2", "name": "주간전담B", "available_days": [1,2,3,4,5],   "preferred_shifts": [0,1]},
            {"id": "d3", "name": "주간전담C", "available_days": [0,2,3,4,6],   "preferred_shifts": [0,1]},
            {"id": "n1", "name": "야간전담A", "available_days": [0,1,2,3,4,5], "preferred_shifts": [2]},
            {"id": "n2", "name": "야간전담B", "available_days": [2,3,4,5,6],   "preferred_shifts": [2]},
            {"id": "x1", "name": "겸직",      "available_days": [1,2,3,4,5,6], "preferred_shifts": [1,2]},
        ],
        "shifts": [
            {"name": "오전", "hours": 4, "is_night": False},
            {"name": "오후", "hours": 4, "is_night": False},
            {"name": "저녁", "hours": 4, "is_night": True},
        ],
        "target_staff": [2, 2, 2],
        "min_staff":    [1, 1, 1],
        "base_hourly":  9860,
        "night_bonus":  0.5,
        "time_limit":   10,
    },
}


# ─────────────────────────────────────────────────────────────
# ══════════ 월간 시나리오 (D=30, 2025년 6월) ═════════════════
# ─────────────────────────────────────────────────────────────
#
# ※ 현재 모델 제약
#   - target_staff / min_staff: 교대별 균일 적용 (요일별 차등 미지원)
#     → 월~목 2명 / 금 3명 / 토 4명 / 일 3명 요구는 근사값으로 표현
#   - max_hours: 주 52h 한도를 월간으로 확장 (기본값 200h)
#   - 공휴일 대체 휴무 자동 배정 미지원 → available_days 수동 반영
# ─────────────────────────────────────────────────────────────

_MONTHLY_SHIFTS = [
    {"name": "오픈", "hours": 4, "is_night": False},
    {"name": "마감", "hours": 4, "is_night": False},
]
_MONTHLY_BASE = {
    "shifts":       _MONTHLY_SHIFTS,
    "base_hourly":  9860,
    "night_bonus":  0.0,
    "num_days":     30,
    "max_hours":    200,   # 월간 최대 근무시간 (4h * 약 22근무일 = 88h 실제, 여유 설정)
    "time_limit":   30,
}

# ── M01 소형매장 5인 (교수님 피드백 예시) ─────────────────
#
# 직원별 규칙
#   매니져  : 고정휴무 일/월. 9일 요청(월→이미 고정 휴무라 반영 완료)
#   시니어  : 고정휴무 목/금. 13일 요청(금→이미 고정 휴무)
#   주니어K : 6/9일 퇴사 → 1~8일만 근무
#   주니어L : 고정휴무 화/수. 18일 요청(수→이미 고정 휴무)
#   PT      : 토/일 출근 원칙. 9일·26일 추가 출근 가능. 28일 연차
#
# 매장 규칙
#   오픈/마감 2교대. 하루 최소 2명(오픈1+마감1), 목표 4명(오픈2+마감2)
#   금요일은 인원 추가(target+1 명시적 처리 미지원 → 근사)
#
# 기대 결과
#   6/1~8  : 5명 활동(K 포함) → 대부분 OPTIMAL 달성
#   6/9~30 : K 없음(4명) → 금/토/일 일부 shortage 가능
#   현충일 6/6(금) : 시니어 금 고정 휴무 → 오픈조 매니져만 가능 → shortage 위험
M01_소형매장 = {
    "label": "M01 소형매장 5인 (교수님 피드백 예시, 2025년 6월)",
    "note": (
        "K 퇴사(6/9~), 현충일(6/6), 각종 요청 휴무 포함."
        " K 퇴사 이후 금·토·일 shortage 예상."
        " 현충일(6/6 금) : 시니어 금 고정휴무 → 오픈 인원 부족 가능."
    ),
    "config": {
        **_MONTHLY_BASE,
        "target_staff":    [2, 2],
        "min_staff":       [1, 1],
        "holiday_indices": [5],   # 6월 6일 현충일 (0-based idx=5)
        "employees": [
            {
                "id": "mgr", "name": "매니져",
                "available_days": june2025_avail(fixed_off_weekdays=[6, 0]),
                # 9일=월 이미 고정 휴무에 포함
                "preferred_shifts": [0],
            },
            {
                "id": "snr", "name": "시니어",
                "available_days": june2025_avail(fixed_off_weekdays=[3, 4]),
                # 13일=금 이미 고정 휴무에 포함
                "preferred_shifts": [0, 1],
            },
            {
                "id": "jnr_k", "name": "주니어K",
                "available_days": june2025_avail(last_date=8),
                # 9일 퇴사 → 8일(일)까지만 근무
                "preferred_shifts": [0, 1],
            },
            {
                "id": "jnr_l", "name": "주니어L",
                "available_days": june2025_avail(
                    fixed_off_weekdays=[1, 2],   # 화, 수
                    off_dates=[18],              # 18일=수 이미 포함이지만 명시
                ),
                "preferred_shifts": [1],
            },
            {
                "id": "pt", "name": "PT",
                # 토/일 + 9일(월) + 26일(목), 28일(토) 제외
                "available_days": june2025_avail(
                    only_dates=[d for d in _JUNE_WKND if d != 28] + [9, 26]
                ),
                "preferred_shifts": [0, 1],
            },
        ],
    },
}

# ── M02 중형매장 7인 (휴가 집중) ──────────────────────────
#
# 직원별 규칙
#   매니져  : 고정휴무 일/월. 23~26일 연차(화~금)
#   시니어A : 고정휴무 목/금. 9~11일 연차(월~수)
#   시니어B : 고정휴무 토/일. 16~20일 연차(월~금, 주 전체)
#   주니어A : 고정휴무 월. 4일 요청 휴무
#   주니어B : 고정휴무 수목. 25~27일 요청 휴무(목~토, 목 이미 고정)
#   PT-주말 : 토/일만 출근. 28일 연차
#   파트타임C: 화수목만 출근(파트). 추가 제약 없음
#
# 매장 규칙 (중형)
#   오픈/마감 2교대. 하루 최소 2명, 목표 하루 6명(오픈3+마감3)
#   매니져·시니어 동시 부재 최소화 (소프트 제약 근사: 항상 한 명 배정)
#
# 기대 결과
#   16~20일 (시니어B 연차 주간) + 23~26일 (매니져 연차 주간) 겹치는 구간에서
#   고참 인력 부족 → target 미달 가능
#   특히 23일(월): 매니져 연차 + 시니어A 목/금 아닌 월 → 시니어A 가능
M02_중형매장 = {
    "label": "M02 중형매장 7인 (휴가 집중, 2025년 6월)",
    "note": (
        "매니져 23~26일 연차, 시니어B 16~20일 연차 → 해당 주간 인력 약화."
        " PT 28일 연차. shortage 발생 구간 있어야 함."
    ),
    "config": {
        **_MONTHLY_BASE,
        "target_staff": [3, 3],
        "min_staff":    [1, 1],
        "employees": [
            {
                "id": "mgr", "name": "매니져",
                "available_days": june2025_avail(
                    fixed_off_weekdays=[6, 0],
                    off_dates=[23, 24, 25, 26],   # 23(화)~26(금) 연차
                ),
                "preferred_shifts": [0],
            },
            {
                "id": "snr_a", "name": "시니어A",
                "available_days": june2025_avail(
                    fixed_off_weekdays=[3, 4],
                    off_dates=[9, 10, 11],         # 9(월)~11(수) 연차
                ),
                "preferred_shifts": [0, 1],
            },
            {
                "id": "snr_b", "name": "시니어B",
                "available_days": june2025_avail(
                    fixed_off_weekdays=[5, 6],
                    off_dates=[16, 17, 18, 19, 20],  # 16(월)~20(금) 연차
                ),
                "preferred_shifts": [1],
            },
            {
                "id": "jnr_a", "name": "주니어A",
                "available_days": june2025_avail(
                    fixed_off_weekdays=[0],
                    off_dates=[4],                 # 4일(수) 요청
                ),
                "preferred_shifts": [0, 1],
            },
            {
                "id": "jnr_b", "name": "주니어B",
                "available_days": june2025_avail(
                    fixed_off_weekdays=[2, 3],
                    off_dates=[25, 26, 27],        # 25(목, 이미 고정)~27(금) 요청
                ),
                "preferred_shifts": [1],
            },
            {
                "id": "pt_w", "name": "PT-주말",
                "available_days": june2025_avail(
                    only_dates=[d for d in _JUNE_WKND if d != 28]
                ),
                "preferred_shifts": [0, 1],
            },
            {
                "id": "pt_c", "name": "파트C",
                "available_days": june2025_avail(fixed_off_weekdays=[0, 4, 5, 6]),
                # 화/수/목만 가능 (월·금·토·일 제외)
                "preferred_shifts": [0, 1],
            },
        ],
    },
}

# ── M03 성수기 대형팀 12인 ─────────────────────────────────
#
# 직원별 규칙
#   매니져A : 고정휴무 일. 14~18일 여름휴가
#   매니져B : 고정휴무 토/일. (부매니져 역할)
#   시니어A : 고정휴무 목. 7일 요청
#   시니어B : 고정휴무 금. 21일 요청
#   주니어A : 고정 없음. 3~7일 연차(월~금)
#   주니어B : 고정휴무 화. 28일 요청
#   주니어C : 고정휴무 수. 추가 없음
#   주니어D : 신규 입사(6/9 입사). 첫 달 토/일도 가능
#   PT-주말A: 토/일 전담. 제약 없음
#   PT-주말B: 토/일 전담. 21·28일 추가 연차
#   파트E   : 월/화/수만 출근. 추가 없음
#   파트F   : 목/금/토만 출근. 추가 없음
#
# 매장 규칙 (성수기, 대형)
#   오픈/마감 2교대 + 피크타임 추가(주말 오후). 하루 목표 8명(오픈4+마감4)
#   주말 고인원 필요(토 target=5, 평균으로 근사)
#
# 기대 결과
#   12명으로 하루 8명(4+4) 목표는 빡빡. 일부 요일 shortage 가능.
#   매니져A 14~18일 연차 + 시니어A 목 고정 → 해당 주간 리더 공백.
M03_성수기_대형팀 = {
    "label": "M03 성수기 대형팀 12인 (2025년 6월)",
    "note": (
        "12명. 하루 오픈4+마감4 목표. "
        "매니져A 14~18일 연차, 주니어A 3~7일 연차, PT-주말B 21·28일 연차."
        " 신규 주니어D는 6/9 입사. "
        "shortage 없거나 소수 발생이 기대값."
    ),
    "config": {
        **_MONTHLY_BASE,
        "target_staff": [4, 4],
        "min_staff":    [2, 2],
        "employees": [
            {
                "id": "mga", "name": "매니져A",
                "available_days": june2025_avail(
                    fixed_off_weekdays=[6],
                    off_dates=list(range(14, 19)),   # 14~18 연차
                ),
                "preferred_shifts": [0],
            },
            {
                "id": "mgb", "name": "매니져B",
                "available_days": june2025_avail(fixed_off_weekdays=[5, 6]),
                "preferred_shifts": [0],
            },
            {
                "id": "snra", "name": "시니어A",
                "available_days": june2025_avail(
                    fixed_off_weekdays=[3],
                    off_dates=[7],
                ),
                "preferred_shifts": [0, 1],
            },
            {
                "id": "snrb", "name": "시니어B",
                "available_days": june2025_avail(
                    fixed_off_weekdays=[4],
                    off_dates=[21],
                ),
                "preferred_shifts": [0, 1],
            },
            {
                "id": "jnra", "name": "주니어A",
                "available_days": june2025_avail(off_dates=list(range(3, 8))),
                "preferred_shifts": [1],
            },
            {
                "id": "jnrb", "name": "주니어B",
                "available_days": june2025_avail(
                    fixed_off_weekdays=[1],
                    off_dates=[28],
                ),
                "preferred_shifts": [1],
            },
            {
                "id": "jnrc", "name": "주니어C",
                "available_days": june2025_avail(fixed_off_weekdays=[2]),
                "preferred_shifts": [0, 1],
            },
            {
                "id": "jnrd", "name": "주니어D(신규)",
                "available_days": june2025_avail(first_date=9),
                # 6/9 입사, 주말도 가능
                "preferred_shifts": [0, 1],
            },
            {
                "id": "ptwa", "name": "PT-주말A",
                "available_days": june2025_avail(only_dates=_JUNE_WKND),
                "preferred_shifts": [0, 1],
            },
            {
                "id": "ptwb", "name": "PT-주말B",
                "available_days": june2025_avail(
                    only_dates=[d for d in _JUNE_WKND if d not in (21, 28)]
                ),
                "preferred_shifts": [0, 1],
            },
            {
                "id": "pte", "name": "파트E",
                "available_days": june2025_avail(fixed_off_weekdays=[2, 3, 4, 5, 6]),
                # 월/화만 가능
                "preferred_shifts": [0],
            },
            {
                "id": "ptf", "name": "파트F",
                "available_days": june2025_avail(fixed_off_weekdays=[0, 1, 2, 6]),
                # 목/금/토만 가능
                "preferred_shifts": [1],
            },
        ],
    },
}

# ── M04 에지케이스 — 직원 2명뿐 ───────────────────────────
#
# 직원 2명이 모든 날 가능하지만 min_staff=[2,2] → 매일 4명 필요
# 구조적으로 오픈+마감 최소 인원을 채울 수 없음
# 기대: OPTIMAL · 전 기간 오픈/마감 모두 shortage
M04_에지케이스_2인 = {
    "label": "M04 에지케이스 — 직원 2인, 심각한 인원 부족",
    "note": (
        "2명만 있고 min_staff=[2,2]이므로 하루 4명 필요."
        " 2명이므로 매일 오픈·마감 각 1명씩 부족."
        " 기대: 전 기간 shortage_report 60건(30일×2교대)."
    ),
    "config": {
        **_MONTHLY_BASE,
        "target_staff": [2, 2],
        "min_staff":    [2, 2],
        "employees": [
            {
                "id": "e1", "name": "직원A",
                "available_days": list(range(30)),
                "preferred_shifts": [0],
            },
            {
                "id": "e2", "name": "직원B",
                "available_days": list(range(30)),
                "preferred_shifts": [1],
            },
        ],
    },
}


# ─────────────────────────────────────────────────────────────
# ══════════ 주간 추가 시나리오 (W06~W09) ════════════════════
# ─────────────────────────────────────────────────────────────

# ── W06 카페형 3교대 · PT 다수 ─────────────────────────────
#
# 매장 형태: 카페
# 교대 구성: 아침(4h) / 점심(4h) / 저녁(5h) 3교대, 야간수당 없음
# 인원: 매니져 1 + 바리스타 2 + 파트 4 = 7명
#   파트 4명이 각각 아침·점심·저녁·주말 전담으로 교대가 분산됨
#
# 기대: OPTIMAL · shortage 없음 · PT 본인 선호 교대 위주 배정 · 복수해 가능
W06_카페_3교대_다수PT = {
    "label": "W06 카페형 3교대 PT 다수 (7인)",
    "note": (
        "매니져+바리스타2(주중)에 아침/점심/저녁/주말 전담 PT 4명."
        " PT마다 선호 교대 다름. 기대: shortage 없음, 복수해 가능."
    ),
    "config": {
        "employees": [
            {"id": "mgr",   "name": "매니져",   "available_days": [0,1,2,3,4,5],   "preferred_shifts": [0]},
            {"id": "bar_a", "name": "바리스타A", "available_days": [0,1,2,3,4],     "preferred_shifts": [0,1]},
            {"id": "bar_b", "name": "바리스타B", "available_days": [1,2,3,4,5],     "preferred_shifts": [1,2]},
            {"id": "pt_am", "name": "파트AM",   "available_days": [0,1,2,4,5,6],   "preferred_shifts": [0]},
            {"id": "pt_pm", "name": "파트PM",   "available_days": [0,2,3,4,5,6],   "preferred_shifts": [1]},
            {"id": "pt_ev", "name": "파트저녁", "available_days": [1,3,4,5,6],     "preferred_shifts": [2]},
            {"id": "pt_wk", "name": "파트주말", "available_days": [5,6],            "preferred_shifts": [0,1,2]},
        ],
        "shifts": [
            {"name": "아침", "hours": 4, "is_night": False},
            {"name": "점심", "hours": 4, "is_night": False},
            {"name": "저녁", "hours": 5, "is_night": False},
        ],
        "target_staff": [2, 2, 2],
        "min_staff":    [1, 1, 1],
        "base_hourly":  9860,
        "night_bonus":  0.0,
        "time_limit":   15,
    },
}

# ── W07 편의점 24시간 3교대 (야간수당 50%) ─────────────────
#
# 매장 형태: 편의점 (24시간 영업)
# 교대 구성: 주간(8h) / 저녁(8h) / 야간(8h, is_night=True) — 8시간 교대
# 인원: 점장 1 + 정직원 2 + 야간PT 3명 = 6명
#   야간PT 3명은 야간교대만 선호 → 야간수당 고려한 최적화 검증
#
# 기대: OPTIMAL · shortage 없음 · 야간PT가 야간교대 집중 배정
W07_편의점_24시간 = {
    "label": "W07 편의점 24시간 3교대 야간수당 50% (6인)",
    "note": (
        "8h 주간/저녁/야간(수당50%). 점장+정직원2+야간PT3."
        " 야간PT는 야간교대 선호. 기대: shortage 없음, 야간PT 야간 집중."
    ),
    "config": {
        "employees": [
            {"id": "ceo", "name": "점장",     "available_days": [0,1,2,3,4],     "preferred_shifts": [0]},
            {"id": "s1",  "name": "직원A",    "available_days": [0,2,3,4,5],     "preferred_shifts": [0,1]},
            {"id": "s2",  "name": "직원B",    "available_days": [1,2,3,5,6],     "preferred_shifts": [0,1]},
            {"id": "n1",  "name": "야간PT-A", "available_days": [0,1,2,3,4,5],   "preferred_shifts": [2]},
            {"id": "n2",  "name": "야간PT-B", "available_days": [1,2,4,5,6],     "preferred_shifts": [2]},
            {"id": "n3",  "name": "야간PT-C", "available_days": [0,3,4,5,6],     "preferred_shifts": [2]},
        ],
        "shifts": [
            {"name": "주간", "hours": 8, "is_night": False},
            {"name": "저녁", "hours": 8, "is_night": False},
            {"name": "야간", "hours": 8, "is_night": True},
        ],
        "target_staff": [1, 1, 1],
        "min_staff":    [1, 1, 1],
        "base_hourly":  9860,
        "night_bonus":  0.5,
        "time_limit":   10,
    },
}

# ── W08 완전 스케쥴제 (롤링 휴무, 고정 휴무 없음) ──────────
#
# 매장 형태: 일반 소매점 / 식당 (완전 스케쥴제 적용)
# 교대 구성: 오픈(4h) / 마감(4h) 2교대
# 인원: 8명 전원 주 7일 모두 가능 (고정 휴무 없음)
#   target=[3,3] → 하루 6명 필요 → 8명 중 매일 2명이 쉬는 구조
#   모델이 최적 휴무일 배분 → 각자 주 5~6일 근무 예상
#
# 기대: OPTIMAL · shortage 없음 · 직원별 쉬는 요일이 서로 다르게 분산
W08_완전스케쥴제 = {
    "label": "W08 완전 스케쥴제 롤링 휴무 (8인, 고정 휴무 없음)",
    "note": (
        "8명 모두 주 7일 가능. 고정 휴무 없음."
        " target=[3,3]이므로 하루 6명 필요 → 매일 2명 쉬는 구조."
        " 기대: 직원별 쉬는 요일이 다르게 분산됨(롤링 휴무 재현)."
    ),
    "config": {
        "employees": [
            {"id": "e1", "name": "직원1", "available_days": [0,1,2,3,4,5,6], "preferred_shifts": [0]},
            {"id": "e2", "name": "직원2", "available_days": [0,1,2,3,4,5,6], "preferred_shifts": [0]},
            {"id": "e3", "name": "직원3", "available_days": [0,1,2,3,4,5,6], "preferred_shifts": [0,1]},
            {"id": "e4", "name": "직원4", "available_days": [0,1,2,3,4,5,6], "preferred_shifts": [0,1]},
            {"id": "e5", "name": "직원5", "available_days": [0,1,2,3,4,5,6], "preferred_shifts": [1]},
            {"id": "e6", "name": "직원6", "available_days": [0,1,2,3,4,5,6], "preferred_shifts": [1]},
            {"id": "e7", "name": "직원7", "available_days": [0,1,2,3,4,5,6], "preferred_shifts": [0,1]},
            {"id": "e8", "name": "직원8", "available_days": [0,1,2,3,4,5,6], "preferred_shifts": [0,1]},
        ],
        "shifts": [
            {"name": "오픈", "hours": 4, "is_night": False},
            {"name": "마감", "hours": 4, "is_night": False},
        ],
        "target_staff": [3, 3],
        "min_staff":    [2, 2],
        "base_hourly":  9860,
        "night_bonus":  0.0,
        "time_limit":   10,
    },
}

# ── W09 패스트푸드 피크타임 3교대 PT 집중 ──────────────────
#
# 매장 형태: 패스트푸드
# 교대 구성: 아침피크(4h, 7-11) / 점심피크(3h, 11-14) / 저녁피크(4h, 17-21)
#   피크타임별 단시간 교대 → 시간당 급여 × 짧은 시간 = 인건비 낮음
# 인원: 매니져 1(올라운더) + 피크전담 PT 6명 (교대별 2명씩)
#
# 기대: OPTIMAL · PT가 선호 피크타임에 집중 배정 · 복수해 가능
W09_패스트푸드_피크 = {
    "label": "W09 패스트푸드 피크타임 3교대 PT 집중 (7인)",
    "note": (
        "매니져1(올라운더) + 피크전담 PT6(아침2/점심2/저녁2)."
        " 각 PT는 본인 피크타임만 선호. 기대: 선호 교대 위주 배정, 복수해 가능."
    ),
    "config": {
        "employees": [
            {"id": "mgr",  "name": "매니져",     "available_days": [0,1,2,3,4,5,6], "preferred_shifts": [0,1,2]},
            {"id": "pta1", "name": "파트AM-1",   "available_days": [0,1,2,3,4,5,6], "preferred_shifts": [0]},
            {"id": "pta2", "name": "파트AM-2",   "available_days": [0,2,3,5,6],     "preferred_shifts": [0]},
            {"id": "ptm1", "name": "파트점심-1", "available_days": [0,1,2,3,4],     "preferred_shifts": [1]},
            {"id": "ptm2", "name": "파트점심-2", "available_days": [1,2,3,4,5,6],   "preferred_shifts": [1]},
            {"id": "pte1", "name": "파트저녁-1", "available_days": [0,1,3,4,5,6],   "preferred_shifts": [2]},
            {"id": "pte2", "name": "파트저녁-2", "available_days": [0,2,4,5,6],     "preferred_shifts": [2]},
        ],
        "shifts": [
            {"name": "아침피크", "hours": 4, "is_night": False},
            {"name": "점심피크", "hours": 3, "is_night": False},
            {"name": "저녁피크", "hours": 4, "is_night": False},
        ],
        "target_staff": [2, 2, 2],
        "min_staff":    [1, 1, 1],
        "base_hourly":  9860,
        "night_bonus":  0.0,
        "time_limit":   15,
    },
}


# ─────────────────────────────────────────────────────────────
# ══════════ 월간 추가 시나리오 (M05~M06) ════════════════════
# ─────────────────────────────────────────────────────────────

_M05_SHIFTS = [
    {"name": "주간", "hours": 8, "is_night": False},
    {"name": "저녁", "hours": 8, "is_night": False},
    {"name": "야간", "hours": 8, "is_night": True},
]
_MONTHLY_BASE_NIGHT = {
    "shifts":       _M05_SHIFTS,
    "base_hourly":  9860,
    "night_bonus":  0.5,
    "num_days":     30,
    "max_hours":    200,
    "time_limit":   30,
}

# ── M05 편의점 월간 3교대 야간수당 ──────────────────────────
#
# 매장 형태: 편의점 (24시간, 월간)
# 교대 구성: 주간(8h) / 저녁(8h) / 야간(8h, 수당50%)
# 인원: 점장 1 + 정직원 3 + 야간PT 4명 = 8명
#   직원별 고정 휴무 다름, 직원B 16~18일 연차
#   야간PT 4명이 돌아가며 야간 커버
#
# 기대: OPTIMAL · shortage 없음 · 야간 비용 vs PT 활용 검증
M05_편의점_월간_3교대 = {
    "label": "M05 편의점 월간 3교대 야간수당 50% (8인, 2025년 6월)",
    "note": (
        "8h 3교대, 야간수당 50%. 점장+정직원3+야간PT4."
        " 직원B 16~18일 연차. 야간PT 4명이 돌아가며 야간 커버."
        " 기대: OPTIMAL, shortage 없음, 야간PT 야간 집중."
    ),
    "config": {
        **_MONTHLY_BASE_NIGHT,
        "target_staff": [1, 1, 1],
        "min_staff":    [1, 1, 1],
        "employees": [
            {
                "id": "ceo", "name": "점장",
                "available_days": june2025_avail(fixed_off_weekdays=[6]),
                "preferred_shifts": [0],
            },
            {
                "id": "s1", "name": "직원A",
                "available_days": june2025_avail(fixed_off_weekdays=[0, 1]),
                "preferred_shifts": [0, 1],
            },
            {
                "id": "s2", "name": "직원B",
                "available_days": june2025_avail(
                    fixed_off_weekdays=[3, 4],
                    off_dates=[16, 17, 18],
                ),
                "preferred_shifts": [0, 1],
            },
            {
                "id": "s3", "name": "직원C",
                "available_days": june2025_avail(fixed_off_weekdays=[5, 6]),
                "preferred_shifts": [1, 2],
            },
            {
                "id": "n1", "name": "야간PT-A",
                "available_days": june2025_avail(),
                "preferred_shifts": [2],
            },
            {
                "id": "n2", "name": "야간PT-B",
                "available_days": june2025_avail(fixed_off_weekdays=[1, 2]),
                "preferred_shifts": [2],
            },
            {
                "id": "n3", "name": "야간PT-C",
                "available_days": june2025_avail(fixed_off_weekdays=[4, 5]),
                "preferred_shifts": [2],
            },
            {
                "id": "n4", "name": "야간PT-D",
                "available_days": june2025_avail(fixed_off_weekdays=[0, 6]),
                "preferred_shifts": [2],
            },
        ],
    },
}

# ── M06 카페 월간 완전 스케쥴제 (3교대, 고정 휴무 없음) ────
#
# 매장 형태: 카페 (완전 스케쥴제 적용, 월간)
# 교대 구성: 아침(4h) / 점심(4h) / 저녁(4h) 3교대
# 인원: 매니져 1 + 바리스타 3 + 파트 4 = 8명 전원 고정 휴무 없음
#   available_days = 30일 전체
#   target=[2,2,2] → 하루 6명 필요 → 8명 중 매일 2명 쉬는 구조
#   모델이 월 전체 휴무일 최적 배분 (롤링 스케쥴)
#
# 기대: OPTIMAL(또는 FEASIBLE) · shortage 없음 · 직원별 월간 휴무 분산
M06_카페_롤링_월간 = {
    "label": "M06 카페 월간 완전 스케쥴제 3교대 (8인, 2025년 6월)",
    "note": (
        "8명 전원 30일 모두 available, 고정 휴무 없음. 3교대."
        " target=[2,2,2] → 하루 6명, 매일 2명 쉬는 구조."
        " 기대: 직원 월 휴무가 다르게 분산되는 롤링 스케쥴."
    ),
    "config": {
        "shifts": [
            {"name": "아침", "hours": 4, "is_night": False},
            {"name": "점심", "hours": 4, "is_night": False},
            {"name": "저녁", "hours": 4, "is_night": False},
        ],
        "base_hourly":  9860,
        "night_bonus":  0.0,
        "num_days":     30,
        "max_hours":    200,
        "time_limit":   60,
        "target_staff": [2, 2, 2],
        "min_staff":    [1, 1, 1],
        "employees": [
            {"id": "mgr",  "name": "매니져",   "available_days": list(range(30)), "preferred_shifts": [0]},
            {"id": "bar1", "name": "바리스타A", "available_days": list(range(30)), "preferred_shifts": [0, 1]},
            {"id": "bar2", "name": "바리스타B", "available_days": list(range(30)), "preferred_shifts": [1, 2]},
            {"id": "bar3", "name": "바리스타C", "available_days": list(range(30)), "preferred_shifts": [0, 1]},
            {"id": "pt1",  "name": "파트1",    "available_days": list(range(30)), "preferred_shifts": [0]},
            {"id": "pt2",  "name": "파트2",    "available_days": list(range(30)), "preferred_shifts": [1]},
            {"id": "pt3",  "name": "파트3",    "available_days": list(range(30)), "preferred_shifts": [2]},
            {"id": "pt4",  "name": "파트4",    "available_days": list(range(30)), "preferred_shifts": [2]},
        ],
    },
}


# ─────────────────────────────────────────────────────────────
# 전체 시나리오 딕셔너리 (실행 파일에서 import)
# ─────────────────────────────────────────────────────────────

SCENARIOS = {
    "W01": W01_기본_5인팀,
    "W02": W02_인원부족_주말,
    "W03": W03_PT_복수해,
    "W04": W04_대형팀_10인,
    "W05": W05_야간주간_분리,
    "W06": W06_카페_3교대_다수PT,
    "W07": W07_편의점_24시간,
    "W08": W08_완전스케쥴제,
    "W09": W09_패스트푸드_피크,
    "M01": M01_소형매장,
    "M02": M02_중형매장,
    "M03": M03_성수기_대형팀,
    "M04": M04_에지케이스_2인,
    "M05": M05_편의점_월간_3교대,
    "M06": M06_카페_롤링_월간,
}
