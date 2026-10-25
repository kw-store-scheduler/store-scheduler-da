"""
매장 근무 스케줄 자동 생성 — 핵심 최적화 엔진
백엔드(Spring Boot) 연동용

사용법:
    result = solve_schedule(config)
    # result["schedule"] → 스케줄 배열
    # result["cost"]     → 총 인건비 (원)
    # result["status"]   → "OPTIMAL" / "FEASIBLE" / "INFEASIBLE"
"""

from ortools.sat.python import cp_model
import time


def _extract_schedule_result(solver, work, employees, shifts, E, D, S, base_hw, night_rate):
    """현재 solver 해에서 schedule 배열과 총 인건비를 추출한다. 직원별 hourly가 있으면 그 시급을 쓴다."""
    schedule = []
    total_cost = 0
    for e, emp in enumerate(employees):
        assignments = []
        for d in range(D):
            for s in range(S):
                if solver.Value(work[e, d, s]):
                    assignments.append({"day": d, "shift": s})
                    h = shifts[s]["hours"]
                    hw = emp.get("hourly", base_hw)
                    total_cost += h * hw
                    if shifts[s]["is_night"]:
                        total_cost += int(h * hw * night_rate)
        schedule.append({"employee_id": emp["id"], "assignments": assignments})
    return schedule, total_cost


def _add_no_good_cut(model, work, solver, E, D, S):
    """현재 해를 제외하는 no-good 절을 모델에 추가한다 (복수 해 탐색용)."""
    literals = []
    for e in range(E):
        for d in range(D):
            for s in range(S):
                if solver.Value(work[e, d, s]) == 1:
                    literals.append(work[e, d, s].Not())
                else:
                    literals.append(work[e, d, s])
    model.AddBoolOr(literals)


def solve_schedule(config: dict, max_alt_solutions: int = 3) -> dict:
    """
    CP-SAT 최적 스케줄 생성 함수 — 백엔드 호출 진입점

    Parameters
    ----------
    config : dict
        {
          "employees": [
              {
                "id": "emp_001",
                "name": "참빛",
                "available_days": [0, 1, 2, 3, 4],   # 0=월 ~ 6=일
                "preferred_shifts": [0, 1]             # 선호 교대 인덱스
              },
              ...
          ],
          "shifts": [
              {"name": "오전", "hours": 4, "is_night": False},
              {"name": "오후", "hours": 4, "is_night": False},
              {"name": "저녁", "hours": 4, "is_night": True},
          ],
          "target_staff":  [2, 3, 2],   # 교대별 목표 인원 (소프트 제약)
          "min_staff":     [1, 1, 1],   # 교대별 최소 인원 (소프트 제약·고패널티)
          "base_hourly":   9860,        # 기본 시급 (원)
          "night_bonus":   0.5,         # 야간수당 비율 (0.5 = 50%)
          "time_limit":    10,          # 최대 풀이 시간 (초)
          "holiday_indices": [5, 14]    # (선택) 공휴일 인덱스 목록 (0-based)
        }
        employees 항목에 추가 가능한 선택 필드:
          "off_requests": [
              {"day": 3,  "type": "must"},    # 필수 휴무 (위반 시 고패널티)
              {"day": 10, "type": "prefer"},  # 희망 휴무 (위반 시 중간 패널티)
              {"day": 5, "type": "must", "weight": 9_000_000},  # (5차 추가) 요청별 패널티 지정
          ]
          "unavailable_slots": [              # (백엔드 추가) 특정 요일의 특정 교대 근무 불가 (하드 제약)
              {"day": 0, "shift": 2},         # 예: 월요일은 가용 시간이 오전까지라 저녁 교대 불가
          ]
          "skills": ["일본어", "바리스타"]       # (4차 추가) 보유 역량
          "hourly": 10030                     # (5차 추가) 직원별 시급. 없으면 base_hourly
        config에 추가 가능한 선택 필드:
          "skill_requirements": [             # (4차 추가) 교대별 필요 역량 인원 (소프트 제약·고패널티)
              {"shift": 0, "skill": "일본어", "count": 1},   # 오전 교대에 일본어 가능자 최소 1명
          ]
          "max_staff": [2, 3, 2],             # (5차 추가) 교대별 최대 인원 (하드 제약). 없으면 상한 없음
          "weight_overrides": {               # (5차 추가) 소프트 제약 가중치 덮어쓰기. 없는 키는 기본값
              "FAIRNESS_W": 1_000_000,        # 예: 공평성 우선안
          }
          "weeks": [[0,1,...,6], [7,...,13]], # (6차 추가) 주 단위 묶음. 있으면 주 최대 시간·주 15시간을 주마다 적용
          "min_staff_by_day":    [[1,1,1], ...],  # (6차 추가) 날짜×교대 최소 인원. 있으면 min_staff 대신 사용
          "target_staff_by_day": [[2,3,2], ...],  # (6차 추가) 날짜×교대 목표 인원
          "max_staff_by_day":    [[2,3,2], ...],  # (6차 추가) 날짜×교대 최대 인원 (하드)
          "weekend_days": [5, 6, 12, 13],     # (6차 추가) 주말 날짜 인덱스. max_weekend_shifts 계산용
          "open_shifts": [0], "close_shifts": [2],  # (6차 추가) no_open_after_close 판단용 교대 인덱스
          "max_shifts_per_day": 1,            # (6차 추가) 하루 최대 교대 수 (쪼개기 근무면 2)
          "conflicting_shifts": [[0, 1]],     # (6차 추가) 시간이 겹쳐 같은 날 함께 할 수 없는 교대 쌍
          "consecutive_days_limit": 5,        # (7차 추가, 하드) 매장 연속 근무 한도. 없으면 4 (연속 5일 이상 금지)
          skill_requirements 항목에 추가 가능 (7차 추가):
            {"shifts": [0, 1], "skill": "응대@HIGH", "count": 1,   # 여러 교대 중 어디에든 있으면 충족 (예: 피크 12-14시를 덮는 오픈·미들)
             "days": [1, 4],                                       # 이 날짜에만 적용
             "weight": 300_000}                                    # 요청별 패널티 (우선 역량은 낮게)
        employees 항목에 추가 가능한 선택 필드 (6차 추가, 모두 소프트 제약):
          "preferred_slots": [{"day": 3, "shift": 0}],  # 날짜×교대 선호. 있으면 preferred_shifts 대신 사용
          "max_weekend_shifts": 2,            # 기간 내 주말 근무 최대 횟수
          "max_consecutive_days": 3,          # 최대 연속 근무일
          "no_open_after_close": True,        # 마감 다음 날 오픈 금지
          "min_total_hours": 64, "max_total_hours": 86,  # 기간 내 근무 시간 범위
          "weight_scale": {"PREF_W": 2.0},    # 이 직원의 개인 선호 패널티 배율 (우선순위 반영)
          off_requests 항목에 "shifts": [1, 2] # 일부 교대만 쉬기 (예: 오후만 쉬기)
          "mentor_required_days": [0, 1, 2],  # (7차 추가, 하드) 수습 기간. 이 날 근무하면 같은 교대에 수습이 아닌 직원이 1명 이상
          "max_weekly_hours": 48,             # (7차 추가, 하드) 직원별 주 최대 시간. 다른 직장 시간을 뺀 값 (없으면 max_hours)
          "avoid_shifts": [2],                # (7차 추가) 피하고 싶은 교대
          "rest_days_together": True,         # (7차 추가) 주마다 쉬는 날을 이틀 붙여서

    Returns
    -------
    dict
        {
          "status":    "OPTIMAL" | "FEASIBLE" | "INFEASIBLE",
          "schedule":  [                     # None if INFEASIBLE
              {
                "employee_id": "emp_001",
                "assignments": [
                    {"day": 0, "shift": 1}, # 월요일 오후 교대
                    ...
                ]
              },
              ...
          ],
          "cost":                 966280,
          "solve_ms":             619,
          "shortage_report": [          # 최소 인원 미달 항목 (부족 없으면 빈 리스트)
              {"day": 0, "shift": 1, "required": 1, "actual": 0, "shortage": 1},
              ...
          ],
          "off_request_violations": [   # 휴무 요청 위반 항목 (위반 없으면 빈 리스트)
              {"employee_id": "emp_001", "day": 3, "shift": 0, "type": "must"},
              ...
          ],
          "skill_shortage_report": [    # (4차 추가) 필요 역량 인원 미달 항목 (없으면 빈 리스트)
              {"day": 0, "shift": 0, "skill": "일본어", "required": 1, "actual": 0},
              ...
          ],
          "has_multiple_optimal": False,  # 동일 비용의 최적해가 2개 이상인지 여부
          "alt_schedules":        [...]   # 대안 스케줄 목록 (has_multiple_optimal=True 시)
        }
    """

    # ── 입력값 파싱 ──────────────────────────────
    employees  = config["employees"]
    shifts     = config["shifts"]
    target_s   = config["target_staff"]   # 교대별 목표 인원
    min_s      = config["min_staff"]      # 교대별 최소 인원
    base_hw    = config["base_hourly"]
    night_rate = config["night_bonus"]
    time_limit = config.get("time_limit", 10)
    weight_overrides = config.get("weight_overrides", {})

    def _w(name, default):
        return weight_overrides.get(name, default)

    E = len(employees)
    D = config.get("num_days", 7)   # 7=주간, 30/31=월간
    S = len(shifts)

    # (6차 추가) 날짜별 인원이 있으면 그것을, 없으면 교대별 인원을 모든 날짜에 쓴다
    def _by_day(key, per_shift):
        by_day = config.get(key)
        if by_day is not None:
            return [[by_day[d][s] for s in range(S)] for d in range(D)]
        return [list(per_shift) for _ in range(D)]

    min_sd    = _by_day("min_staff_by_day", min_s)
    target_sd = _by_day("target_staff_by_day", target_s)

    # (6차 추가) 직원별 개인 선호 패널티 배율. 직원이 정한 우선순위를 가중치로 바꾼 값
    def _ew(emp, name, base):
        return int(base * emp.get("weight_scale", {}).get(name, 1))

    week_groups = [[d for d in wk if d < D] for wk in config["weeks"]] if config.get("weeks") else [list(range(D))]

    model  = cp_model.CpModel()
    solver = cp_model.CpSolver()

    # ── 결정변수: work[e][d][s] ∈ {0, 1} ────────
    # work[e,d,s] = 1 이면 직원 e가 요일 d에 교대 s 근무
    work = {
        (e, d, s): model.NewBoolVar(f"w_{e}_{d}_{s}")
        for e in range(E)
        for d in range(D)
        for s in range(S)
    }

    # ── [하드 1] 가용 요일 외 근무 불가 ──────────
    for e, emp in enumerate(employees):
        avail = set(emp["available_days"])
        for d in range(D):
            if d not in avail:
                for s in range(S):
                    model.Add(work[e, d, s] == 0)

    # ── [하드 1-1] 요일별 가용 시간 외 교대 근무 불가 (백엔드 추가) ─
    # available_days는 요일 단위라, 가용 시간이 09~13시인 직원도 그날 저녁 교대에 배정될 수 있었다.
    # 백엔드가 직원의 요일별 가용 시간과 교대 시간을 비교해 불가능한 (요일, 교대)를 넘겨준다.
    for e, emp in enumerate(employees):
        for slot in emp.get("unavailable_slots", []):
            if slot["day"] < D and slot["shift"] < S:
                model.Add(work[e, slot["day"], slot["shift"]] == 0)

    # ── [하드 2] 하루 최대 1교대 (이중 근무 금지) ─
    # (6차 추가) max_shifts_per_day가 2 이상이면 쪼개기 근무 허용. 시간이 겹치는 교대는 함께 배정하지 않는다
    max_per_day = config.get("max_shifts_per_day", 1)
    for e in range(E):
        for d in range(D):
            if max_per_day <= 1:
                model.AddAtMostOne(work[e, d, s] for s in range(S))
            else:
                model.Add(sum(work[e, d, s] for s in range(S)) <= max_per_day)
                for a, b in config.get("conflicting_shifts", []):
                    if a < S and b < S:
                        model.Add(work[e, d, a] + work[e, d, b] <= 1)

    # ── [하드 3] 주 52시간 초과 금지 (근로기준법) ─
    # (6차 수정) weeks가 있으면 주마다 적용. 없으면 기존처럼 전체 기간에 적용
    for e, emp in enumerate(employees):
        weekly_cap = min(config.get("max_hours", 52), emp.get("max_weekly_hours", config.get("max_hours", 52)))
        for wk in week_groups:
            weekly_hours = sum(
                work[e, d, s] * shifts[s]["hours"]
                for d in wk
                for s in range(S)
            )
            model.Add(weekly_hours <= weekly_cap)

    # ── [하드 4] 연속 5일 이상 근무 금지 ─────────
    # (7차 수정) 매장이 consecutive_days_limit을 정하면 그 일수까지 연속 근무 허용. 없으면 기존처럼 4일
    max_run = config.get("consecutive_days_limit", 4)
    for e in range(E):
        for d in range(D - max_run):
            model.Add(
                sum(work[e, d + k, s]
                    for k in range(max_run + 1)
                    for s in range(S)) <= max_run
            )

    # ── [하드 5] 교대별 최대 인원 (5차 추가, 선택) ──
    # 없으면 상한 없음. 공평성 가중치를 키웠을 때 근무일을 맞추려고 필요 이상 배정하는 것을 막는다.
    max_s = config.get("max_staff")
    if max_s is not None or config.get("max_staff_by_day") is not None:
        max_sd = _by_day("max_staff_by_day", max_s)
        for d in range(D):
            for s in range(S):
                model.Add(sum(work[e, d, s] for e in range(E)) <= max_sd[d][s])

    # ── [소프트 0] 최소 인원 미달 패널티 ─────────
    # 구 [하드 5]를 소프트 제약으로 완화.
    # 패널티가 충분히 크므로 가용 인원이 있으면 반드시 채우고,
    # 가용 인원 자체가 부족할 때는 스케줄을 생성한 뒤 shortage_report로 알린다.
    MIN_STAFF_W = _w("MIN_STAFF_W", 50_000_000)   # 최소 인원 1명 부족 → 5천만 패널티
    min_shortage_vars = []

    for d in range(D):
        for s in range(S):
            actual = sum(work[e, d, s] for e in range(E))
            for k in range(1, min_sd[d][s] + 1):
                v = model.NewBoolVar(f"ms_{d}_{s}_{k}")
                # v=1  ↔  actual < k (k번째 최소 인원 미달)
                model.Add(actual <= k - 1).OnlyEnforceIf(v)
                model.Add(actual >= k).OnlyEnforceIf(v.Not())
                min_shortage_vars.append(v)

    # ── [소프트 1] 목표 인원 미달 패널티 ─────────
    # 인원 부족 1명당 5,000,000 패널티 (운영 차질 방지)
    UNDERSTAFF_W = _w("UNDERSTAFF_W", 5_000_000)
    understaff_vars = []

    for d in range(D):
        for s in range(S):
            actual = sum(work[e, d, s] for e in range(E))
            target = target_sd[d][s]
            for deficit in range(1, target + 1):
                v = model.NewBoolVar(f"us_{d}_{s}_{deficit}")
                model.Add(actual <= deficit - 1).OnlyEnforceIf(v)
                model.Add(actual >= deficit).OnlyEnforceIf(v.Not())
                understaff_vars.append(v)

    # ── [소프트 2] 주 15시간 미만 패널티 (주휴수당) ─
    # 주 15시간 이상 근무 시 주휴수당 발생 → 15시간 미달 패널티
    LOW_HOURS_W = _w("LOW_HOURS_W", 2_000_000)
    low_hours_vars = []

    # (6차 수정) weeks가 있으면 7일이 다 들어 있는 주마다 따진다. 월 경계에 걸친 짧은 주는 제외
    # 직원이 근무량 범위(min/max_total_hours)를 정했으면 그 범위가 이 규칙을 대신한다
    low_hours_groups = [wk for wk in week_groups if len(wk) == 7] if config.get("weeks") else week_groups
    for e, emp in enumerate(employees):
        if emp.get("min_total_hours") is not None or emp.get("max_total_hours") is not None:
            continue
        for w, wk in enumerate(low_hours_groups):
            hours = sum(
                work[e, d, s] * shifts[s]["hours"]
                for d in wk
                for s in range(S)
            )
            v = model.NewBoolVar(f"lh_{e}_{w}")
            model.Add(hours >= 15).OnlyEnforceIf(v.Not())
            model.Add(hours < 15).OnlyEnforceIf(v)
            low_hours_vars.append(v)

    # ── [소프트 3] 선호 교대 외 배정 패널티 ──────
    # (6차 추가) preferred_slots가 있으면 날짜×교대 단위로 판단. 비어 있으면 선호가 없는 것으로 보고 패널티 없음
    PREF_W = _w("PREF_W", 100_000)
    pref_terms = []

    for e, emp in enumerate(employees):
        weight = _ew(emp, "PREF_W", PREF_W)
        if "preferred_slots" in emp:
            pref_slots = {(p["day"], p["shift"]) for p in emp["preferred_slots"]}
            if pref_slots:
                for d in range(D):
                    for s in range(S):
                        if (d, s) not in pref_slots:
                            pref_terms.append((work[e, d, s], weight))
            continue
        pref = set(emp.get("preferred_shifts", []))
        for d in range(D):
            for s in range(S):
                if s not in pref:
                    pref_terms.append((work[e, d, s], weight))

    # ── [소프트 4] 필수 휴무 위반 패널티 ──────────
    # type="must": 사실상 하드 제약. 인원부족 다음으로 최우선.
    # ── [소프트 5] 희망 휴무 위반 패널티 ──────────
    # type="prefer": 가능하면 배정 안 함. 선호 교대 위반보다 중요.
    MUST_OFF_W   = _w("MUST_OFF_W", 10_000_000)
    PREFER_OFF_W = _w("PREFER_OFF_W", 200_000)
    # (5차 추가) 요청마다 "weight"를 주면 그 값으로 패널티. 예: 정규직 필수 휴무를 알바보다 먼저 깨도록 낮게
    must_off_terms   = []
    prefer_off_terms = []

    for e, emp in enumerate(employees):
        for req in emp.get("off_requests", []):
            d = req["day"]
            if d >= D:
                continue
            is_must = req.get("type", "prefer") == "must"
            weight = req.get("weight", MUST_OFF_W if is_must else _ew(emp, "PREFER_OFF_W", PREFER_OFF_W))
            # (6차 추가) shifts가 있으면 그 교대만 쉰다 (예: 오후만 쉬기)
            for s in req.get("shifts", range(S)):
                if s < S:
                    (must_off_terms if is_must else prefer_off_terms).append((work[e, d, s], weight))

    # ── [소프트 6] 근무일수 편차 최소화 (타이브레이킹) ─
    # 직원 간 근무일수 max-min 차를 최소화 → 균등 배분 유도.
    FAIRNESS_W = _w("FAIRNESS_W", 10)
    # (6차 수정) 쪼개기 근무면 하루 교대 수가 1을 넘을 수 있어 상한을 늘린다
    max_slots = D * max(1, max_per_day)
    work_days_vars = []
    for e in range(E):
        wd = model.NewIntVar(0, max_slots, f"wd_{e}")
        model.Add(wd == sum(work[e, d, s] for d in range(D) for s in range(S)))
        work_days_vars.append(wd)
    max_wd = model.NewIntVar(0, max_slots, "max_wd")
    min_wd = model.NewIntVar(0, max_slots, "min_wd")
    model.AddMaxEquality(max_wd, work_days_vars)
    model.AddMinEquality(min_wd, work_days_vars)
    fairness_range = model.NewIntVar(0, max_slots, "fairness_range")
    model.Add(fairness_range == max_wd - min_wd)

    # ── [소프트 7] 공휴일 근무 편차 최소화 (타이브레이킹) ─
    # holiday_indices에 지정된 공휴일의 근무 횟수 편차를 최소화.
    HOLIDAY_W = _w("HOLIDAY_W", 5)
    holiday_indices = [d for d in config.get("holiday_indices", []) if d < D]
    holiday_range_term = 0
    if holiday_indices and E > 1:
        max_h_slots = len(holiday_indices) * max(1, max_per_day)
        hwork = []
        for e in range(E):
            hw = model.NewIntVar(0, max_h_slots, f"hw_{e}")
            model.Add(hw == sum(work[e, d, s] for d in holiday_indices for s in range(S)))
            hwork.append(hw)
        max_hw = model.NewIntVar(0, max_h_slots, "max_hw")
        min_hw = model.NewIntVar(0, max_h_slots, "min_hw")
        model.AddMaxEquality(max_hw, hwork)
        model.AddMinEquality(min_hw, hwork)
        h_range = model.NewIntVar(0, max_h_slots, "h_range")
        model.Add(h_range == max_hw - min_hw)
        holiday_range_term = HOLIDAY_W * h_range

    # ── [소프트 9] 교대별 필요 역량 인원 미달 패널티 (4차 추가) ─
    # 예: 외국인 손님이 많은 오전 교대에 일본어 가능자 최소 1명.
    # 하드 제약으로 두면 역량 보유자가 없는 날 스케줄 전체가 INFEASIBLE이 되므로
    # 최소 인원([소프트 0])과 같은 방식으로 고패널티 소프트 제약 + skill_shortage_report로 처리한다.
    # 필수 휴무보다는 낮게 둬서, 역량 보유자의 필수 휴무를 깨면서까지 채우지는 않는다.
    SKILL_W = _w("SKILL_W", 8_000_000)
    skill_shortage_terms = []

    # (7차 추가) "shift" 하나 대신 "shifts" 여러 개, 적용 날짜 "days", 요청별 "weight"를 받는다
    def _req_shifts(r):
        return [s for s in (r["shifts"] if "shifts" in r else [r["shift"]]) if s < S]

    def _req_days(r):
        return [d for d in r["days"] if d < D] if "days" in r else list(range(D))

    skill_reqs = [r for r in config.get("skill_requirements", []) if _req_shifts(r) and r.get("count", 1) > 0]
    for i, r in enumerate(skill_reqs):
        skilled = [e for e, emp in enumerate(employees) if r["skill"] in emp.get("skills", [])]
        weight = r.get("weight", SKILL_W)
        for d in _req_days(r):
            actual = sum(work[e, d, s] for e in skilled for s in _req_shifts(r))
            for k in range(1, r.get("count", 1) + 1):
                v = model.NewBoolVar(f"sk_{i}_{d}_{k}")
                model.Add(actual <= k - 1).OnlyEnforceIf(v)
                model.Add(actual >= k).OnlyEnforceIf(v.Not())
                skill_shortage_terms.append((v, weight))

    # ── [하드 6] 수습 기간 선임 동행 (7차 추가) ──
    # 수습인 날 근무하면 같은 교대에 그날 수습이 아닌 직원이 최소 1명 있어야 한다
    mentor_days = [set(d for d in emp.get("mentor_required_days", []) if d < D) for emp in employees]
    for e in range(E):
        for d in mentor_days[e]:
            mentors = [k for k in range(E) if k != e and d not in mentor_days[k]]
            for s in range(S):
                model.Add(work[e, d, s] <= sum(work[k, d, s] for k in mentors))

    # ── [소프트 10] 개인 근무 규칙 (6차 추가) ─────
    # 직원이 희망 제출 때 정한 주말 횟수·연속 근무·근무 리듬·근무량. 인원 확보보다는 낮고 희망 휴무와 비슷한 수준
    WEEKEND_W = _w("WEEKEND_W", 300_000)
    CONSEC_W  = _w("CONSEC_W", 300_000)
    RHYTHM_W  = _w("RHYTHM_W", 300_000)
    HOURS_W   = _w("HOURS_W", 20_000)    # 범위를 벗어난 1시간당
    AVOID_W   = _w("AVOID_W", 300_000)   # (7차) 피하고 싶은 교대 배정 1건
    REST_PAIR_W = _w("REST_PAIR_W", 200_000)  # (7차) 쉬는 날을 붙이지 못한 주 1개
    personal_terms = []
    weekend_days = [d for d in config.get("weekend_days", []) if d < D]
    open_shifts  = [s for s in config.get("open_shifts", []) if s < S]
    close_shifts = [s for s in config.get("close_shifts", []) if s < S]

    for e, emp in enumerate(employees):
        limit = emp.get("max_weekend_shifts")
        if limit is not None and weekend_days:
            excess = model.NewIntVar(0, len(weekend_days) * S, f"wk_{e}")
            model.Add(excess >= sum(work[e, d, s] for d in weekend_days for s in range(S)) - limit)
            personal_terms.append((excess, _ew(emp, "WEEKEND_W", WEEKEND_W)))

        k = emp.get("max_consecutive_days")
        if k is not None and k < D:
            worked = []
            for d in range(D):
                w = model.NewBoolVar(f"wd_{e}_{d}")
                model.AddMaxEquality(w, [work[e, d, s] for s in range(S)])
                worked.append(w)
            for d in range(D - k):
                over = model.NewBoolVar(f"cs_{e}_{d}")
                model.Add(sum(worked[d:d + k + 1]) <= k + over)
                personal_terms.append((over, _ew(emp, "CONSEC_W", CONSEC_W)))

        if emp.get("no_open_after_close") and open_shifts and close_shifts:
            for d in range(D - 1):
                v = model.NewBoolVar(f"rh_{e}_{d}")
                for c in close_shifts:
                    for o in open_shifts:
                        model.Add(work[e, d, c] + work[e, d + 1, o] <= 1 + v)
                personal_terms.append((v, _ew(emp, "RHYTHM_W", RHYTHM_W)))

        for s in emp.get("avoid_shifts", []):
            if s < S:
                for d in range(D):
                    personal_terms.append((work[e, d, s], _ew(emp, "AVOID_W", AVOID_W)))

        # 7일이 다 들어 있는 주마다, 이어진 이틀을 모두 쉬는 날이 한 번이라도 있으면 충족
        if emp.get("rest_days_together"):
            full_weeks = [wk for wk in week_groups if len(wk) == 7]
            for w, wk in enumerate(full_weeks):
                rest = []
                for d in wk:
                    r = model.NewBoolVar(f"rest_{e}_{d}")
                    model.Add(sum(work[e, d, s] for s in range(S)) == 0).OnlyEnforceIf(r)
                    model.Add(sum(work[e, d, s] for s in range(S)) >= 1).OnlyEnforceIf(r.Not())
                    rest.append(r)
                pairs = []
                for i in range(len(rest) - 1):
                    p = model.NewBoolVar(f"rp_{e}_{w}_{i}")
                    model.AddBoolAnd([rest[i], rest[i + 1]]).OnlyEnforceIf(p)
                    model.AddBoolOr([rest[i].Not(), rest[i + 1].Not()]).OnlyEnforceIf(p.Not())
                    pairs.append(p)
                missing = model.NewBoolVar(f"rpm_{e}_{w}")
                model.AddBoolOr(pairs + [missing])
                personal_terms.append((missing, _ew(emp, "REST_PAIR_W", REST_PAIR_W)))

        min_h, max_h = emp.get("min_total_hours"), emp.get("max_total_hours")
        if min_h is not None or max_h is not None:
            total = sum(work[e, d, s] * shifts[s]["hours"] for d in range(D) for s in range(S))
            horizon = D * S * max(sh["hours"] for sh in shifts)
            if min_h is not None:
                under = model.NewIntVar(0, horizon, f"hu_{e}")
                model.Add(under >= min_h - total)
                personal_terms.append((under, _ew(emp, "HOURS_W", HOURS_W)))
            if max_h is not None:
                over = model.NewIntVar(0, horizon, f"ho_{e}")
                model.Add(over >= total - max_h)
                personal_terms.append((over, _ew(emp, "HOURS_W", HOURS_W)))

    # ── [소프트 8] 재스케줄 시 기존 근무표 변경 최소화 ─
    CHANGE_W = _w("CHANGE_W", config.get("change_weight", 300_000))
    change_vars = []
    prev = config.get("prev_assignments")  # {(emp_id, day): shift}
    if prev:
        ids = [emp["id"] for emp in employees]
        for e in range(E):
            for d in range(D):
                ps = prev.get((ids[e], d))
                for s in range(S):
                    if ps == s:
                        change_vars.append(work[e, d, s].Not())
                    else:
                        change_vars.append(work[e, d, s]) if ps is not None else None
    # ── 목적함수: 인건비 + 야간수당 + 패널티 최소화 ─
    labor = sum(
        work[e, d, s] * shifts[s]["hours"] * employees[e].get("hourly", base_hw)
        for e in range(E)
        for d in range(D)
        for s in range(S)
    )
    night = sum(
        work[e, d, s] * shifts[s]["hours"] * int(employees[e].get("hourly", base_hw) * night_rate)
        for e in range(E)
        for d in range(D)
        for s in range(S)
        if shifts[s]["is_night"]
    )

    model.Minimize(
        labor + night
        + MIN_STAFF_W   * sum(min_shortage_vars)   # 최소 인원 미달 (최우선)
        + sum(w * v for v, w in must_off_terms)     # 필수 휴무 위반
        + UNDERSTAFF_W  * sum(understaff_vars)
        + LOW_HOURS_W   * sum(low_hours_vars)
        + sum(w * v for v, w in prefer_off_terms)   # 희망 휴무 위반
        + sum(w * v for v, w in pref_terms)         # 비선호 교대·칸 배정
        + sum(w * v for v, w in personal_terms)     # 개인 근무 규칙 (6차 추가)
        + FAIRNESS_W    * fairness_range            # 근무일수 편차 (타이브레이킹)
        + holiday_range_term                        # 공휴일 편차 (타이브레이킹)
        + CHANGE_W * sum(change_vars)
        + sum(w * v for v, w in skill_shortage_terms)  # 필요 역량 인원 미달 (4차 추가, 7차 요청별 가중치)
    )

    # ── 솔버 실행 ────────────────────────────────
    solver.parameters.max_time_in_seconds = time_limit
    solver.parameters.log_search_progress = False

    t0 = time.time()
    status = solver.Solve(model)
    solve_ms = int((time.time() - t0) * 1000)

    STATUS_MAP = {
        cp_model.OPTIMAL:    "OPTIMAL",
        cp_model.FEASIBLE:   "FEASIBLE",
        cp_model.INFEASIBLE: "INFEASIBLE",
        cp_model.UNKNOWN:    "UNKNOWN",
    }

    # ── 결과 추출 ────────────────────────────────
    # [하드 1~4]만으로 INFEASIBLE이 되는 극단적 경우
    if status not in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
        return {
            "status":                 STATUS_MAP.get(status, "UNKNOWN"),
            "schedule":               None,
            "cost":                   None,
            "solve_ms":               solve_ms,
            "shortage_report":        [],
            "off_request_violations": [],
            "skill_shortage_report":  [],
            "has_multiple_optimal":   False,
            "alt_schedules":          [],
        }

    schedule, total_cost = _extract_schedule_result(
        solver, work, employees, shifts, E, D, S, base_hw, night_rate
    )

    # ── 최소 인원 부족 현황 ───────────────────────
    shortage_report = []
    for d in range(D):
        for s in range(S):
            actual_cnt = sum(solver.Value(work[e, d, s]) for e in range(E))
            if actual_cnt < min_sd[d][s]:
                shortage_report.append({
                    "day":      d,
                    "shift":    s,
                    "required": min_sd[d][s],
                    "actual":   actual_cnt,
                    "shortage": min_sd[d][s] - actual_cnt,
                })

    # ── 휴무 요청 위반 현황 ───────────────────────
    off_request_violations = []
    for e, emp in enumerate(employees):
        for req in emp.get("off_requests", []):
            d = req["day"]
            if d >= D:
                continue
            for s in req.get("shifts", range(S)):
                if s < S and solver.Value(work[e, d, s]):
                    off_request_violations.append({
                        "employee_id": emp["id"],
                        "day":         d,
                        "shift":       s,
                        "type":        req.get("type", "prefer"),
                    })

    # ── 필요 역량 인원 부족 현황 (4차 추가) ─────────
    skill_shortage_report = []
    for r in skill_reqs:
        required = r.get("count", 1)
        for d in _req_days(r):
            actual_cnt = sum(
                solver.Value(work[e, d, s])
                for e, emp in enumerate(employees)
                if r["skill"] in emp.get("skills", [])
                for s in _req_shifts(r)
            )
            if actual_cnt < required:
                skill_shortage_report.append({
                    "day":      d,
                    "shift":    _req_shifts(r)[0],
                    "shifts":   _req_shifts(r),   # (7차 추가)
                    "skill":    r["skill"],
                    "required": required,
                    "actual":   actual_cnt,
                })

    # ── 복수 최적해 탐색 ──────────────────────────
    # OPTIMAL인 경우에만 수행.
    # no-good cut: 현재 해를 제외하고 재풀어 같은 목적함수값이 나오면
    # 복수 최적해가 존재한다고 판단한다.
    has_multiple_optimal = False
    alt_schedules = []

    if status == cp_model.OPTIMAL:
        optimal_obj = solver.ObjectiveValue()
        solver.parameters.max_time_in_seconds = max(2, time_limit // 3)

        for _ in range(max_alt_solutions - 1):
            _add_no_good_cut(model, work, solver, E, D, S)
            status2 = solver.Solve(model)
            if status2 not in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
                break
            if abs(solver.ObjectiveValue() - optimal_obj) > 0.5:
                break   # 목적함수값이 달라지면 더 이상 동등 최적해 없음
            has_multiple_optimal = True
            alt_sch, _ = _extract_schedule_result(
                solver, work, employees, shifts, E, D, S, base_hw, night_rate
            )
            alt_schedules.append(alt_sch)

    return {
        "status":                 STATUS_MAP[status],
        "schedule":               schedule,
        "cost":                   total_cost,
        "solve_ms":               solve_ms,
        "shortage_report":        shortage_report,
        "off_request_violations": off_request_violations,
        "skill_shortage_report":  skill_shortage_report,
        "has_multiple_optimal":   has_multiple_optimal,
        "alt_schedules":          alt_schedules,
    }


# ─────────────────────────────────────────
# 호출 예시 (백엔드 연동 테스트용)
# ─────────────────────────────────────────

if __name__ == "__main__":

    # Spring Boot에서 이런 형태로 호출하면 됨
    config = {
        "employees": [
            {"id": "emp_001", "name": "참빛",  "available_days": [0,1,2,3,4],       "preferred_shifts": [0,1]},
            {"id": "emp_002", "name": "새빛",  "available_days": [1,3,5],           "preferred_shifts": [1,2]},
            {"id": "emp_003", "name": "비마",  "available_days": [0,2,4,6],         "preferred_shifts": [2]},
            {"id": "emp_004", "name": "누리",  "available_days": [0,1,2,3,4,5,6],   "preferred_shifts": [0]},
            {"id": "emp_005", "name": "한울",  "available_days": [2,3,4,5,6],       "preferred_shifts": [1,2]},
        ],
        "shifts": [
            {"name": "오전", "hours": 4, "is_night": False},
            {"name": "오후", "hours": 4, "is_night": False},
            {"name": "저녁", "hours": 4, "is_night": True},
        ],
        "target_staff":  [2, 3, 2],
        "min_staff":     [1, 1, 1],
        "base_hourly":   9860,
        "night_bonus":   0.5,
        "time_limit":    10,
    }

    DAYS   = ["월","화","수","목","금","토","일"]
    SHIFTS = [s["name"] for s in config["shifts"]]

    def print_result(res, cfg, label=""):
        print(f"\n{'='*50}  {label}")
        print(f"상태    : {res['status']}")
        if res["cost"] is not None:
            print(f"인건비  : {res['cost']:,}원")
        print(f"풀이시간: {res['solve_ms']}ms")

        if res["shortage_report"]:
            print("\n[인원 부족 현황]")
            shift_names = [s["name"] for s in cfg["shifts"]]
            for r in res["shortage_report"]:
                print(f"  {DAYS[r['day']]}요일 {shift_names[r['shift']]}교대"
                      f" -> 필요 {r['required']}명 / 실제 {r['actual']}명"
                      f" (부족 {r['shortage']}명)")
        else:
            print("\n인원 부족 없음")

        if res["schedule"]:
            print("\n스케줄:")
            for emp_result in res["schedule"]:
                emp_name = next(e["name"] for e in cfg["employees"] if e["id"] == emp_result["employee_id"])
                assigns  = ", ".join(
                    f"{DAYS[a['day']]} {SHIFTS[a['shift']]}"
                    for a in emp_result["assignments"]
                )
                print(f"  {emp_name}: {assigns if assigns else '배정 없음'}")

        if res["has_multiple_optimal"]:
            print(f"\n※ 동일 비용의 최적해가 {len(res['alt_schedules'])+1}개 이상 존재합니다.")
            for i, alt in enumerate(res["alt_schedules"], 2):
                print(f"\n  [대안 스케줄 #{i}]")
                for emp_result in alt:
                    emp_name = next(e["name"] for e in cfg["employees"] if e["id"] == emp_result["employee_id"])
                    assigns  = ", ".join(
                        f"{DAYS[a['day']]} {SHIFTS[a['shift']]}"
                        for a in emp_result["assignments"]
                    )
                    print(f"    {emp_name}: {assigns if assigns else '배정 없음'}")

    # ── 테스트 1: 정상 케이스 ────────────────────
    result = solve_schedule(config)
    print_result(result, config, "정상 케이스")

    # ── 테스트 2: 인원 부족 케이스 ───────────────
    # 오전 최소 3명 필요 / 전체 직원 2명 → 매일 오전 1명 부족
    # 구 버전: INFEASIBLE  →  신 버전: 스케줄 생성 + shortage_report 반환
    config_shortage = {
        "employees": [
            {"id": "emp_001", "name": "참빛", "available_days": [0,1,2,3,4,5,6], "preferred_shifts": [0]},
            {"id": "emp_002", "name": "새빛", "available_days": [0,1,2,3,4,5,6], "preferred_shifts": [0]},
        ],
        "shifts": [
            {"name": "오전", "hours": 4, "is_night": False},
            {"name": "오후", "hours": 4, "is_night": False},
            {"name": "저녁", "hours": 4, "is_night": True},
        ],
        "target_staff":  [3, 2, 1],
        "min_staff":     [3, 1, 1],
        "base_hourly":   9860,
        "night_bonus":   0.5,
        "time_limit":    10,
    }
    result_shortage = solve_schedule(config_shortage)
    print_result(result_shortage, config_shortage, "인원 부족 케이스")
