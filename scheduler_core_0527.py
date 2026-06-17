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
    """현재 solver 해에서 schedule 배열과 총 인건비를 추출한다."""
    schedule = []
    total_cost = 0
    for e, emp in enumerate(employees):
        assignments = []
        for d in range(D):
            for s in range(S):
                if solver.Value(work[e, d, s]):
                    assignments.append({"day": d, "shift": s})
                    h = shifts[s]["hours"]
                    total_cost += h * base_hw
                    if shifts[s]["is_night"]:
                        total_cost += int(h * base_hw * night_rate)
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
          ]

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

    E = len(employees)
    D = config.get("num_days", 7)   # 7=주간, 30/31=월간
    S = len(shifts)

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

    # ── [하드 2] 하루 최대 1교대 (이중 근무 금지) ─
    for e in range(E):
        for d in range(D):
            model.AddAtMostOne(work[e, d, s] for s in range(S))

    # ── [하드 3] 주 52시간 초과 금지 (근로기준법) ─
    for e in range(E):
        weekly_hours = sum(
            work[e, d, s] * shifts[s]["hours"]
            for d in range(D)
            for s in range(S)
        )
        model.Add(weekly_hours <= config.get("max_hours", 52))

    # ── [하드 4] 연속 5일 이상 근무 금지 ─────────
    for e in range(E):
        for d in range(D - 4):
            model.Add(
                sum(work[e, d + k, s]
                    for k in range(5)
                    for s in range(S)) <= 4
            )

    # ── [소프트 0] 최소 인원 미달 패널티 ─────────
    # 구 [하드 5]를 소프트 제약으로 완화.
    # 패널티가 충분히 크므로 가용 인원이 있으면 반드시 채우고,
    # 가용 인원 자체가 부족할 때는 스케줄을 생성한 뒤 shortage_report로 알린다.
    MIN_STAFF_W = 50_000_000   # 최소 인원 1명 부족 → 5천만 패널티
    min_shortage_vars = []

    for d in range(D):
        for s in range(S):
            actual = sum(work[e, d, s] for e in range(E))
            for k in range(1, min_s[s] + 1):
                v = model.NewBoolVar(f"ms_{d}_{s}_{k}")
                # v=1  ↔  actual < k (k번째 최소 인원 미달)
                model.Add(actual <= k - 1).OnlyEnforceIf(v)
                model.Add(actual >= k).OnlyEnforceIf(v.Not())
                min_shortage_vars.append(v)

    # ── [소프트 1] 목표 인원 미달 패널티 ─────────
    # 인원 부족 1명당 5,000,000 패널티 (운영 차질 방지)
    UNDERSTAFF_W = 5_000_000
    understaff_vars = []

    for d in range(D):
        for s in range(S):
            actual = sum(work[e, d, s] for e in range(E))
            target = target_s[s]
            for deficit in range(1, target + 1):
                v = model.NewBoolVar(f"us_{d}_{s}_{deficit}")
                model.Add(actual <= deficit - 1).OnlyEnforceIf(v)
                model.Add(actual >= deficit).OnlyEnforceIf(v.Not())
                understaff_vars.append(v)

    # ── [소프트 2] 주 15시간 미만 패널티 (주휴수당) ─
    # 주 15시간 이상 근무 시 주휴수당 발생 → 15시간 미달 패널티
    LOW_HOURS_W = 2_000_000
    low_hours_vars = []

    for e in range(E):
        hours = sum(
            work[e, d, s] * shifts[s]["hours"]
            for d in range(D)
            for s in range(S)
        )
        v = model.NewBoolVar(f"lh_{e}")
        model.Add(hours >= 15).OnlyEnforceIf(v.Not())
        model.Add(hours < 15).OnlyEnforceIf(v)
        low_hours_vars.append(v)

    # ── [소프트 3] 선호 교대 외 배정 패널티 ──────
    PREF_W = 100_000
    pref_vars = []

    for e, emp in enumerate(employees):
        pref = set(emp.get("preferred_shifts", []))
        for d in range(D):
            for s in range(S):
                if s not in pref:
                    v = model.NewBoolVar(f"pf_{e}_{d}_{s}")
                    model.Add(v == work[e, d, s])
                    pref_vars.append(v)

    # ── [소프트 4] 필수 휴무 위반 패널티 ──────────
    # type="must": 사실상 하드 제약. 인원부족 다음으로 최우선.
    # ── [소프트 5] 희망 휴무 위반 패널티 ──────────
    # type="prefer": 가능하면 배정 안 함. 선호 교대 위반보다 중요.
    MUST_OFF_W   = 10_000_000
    PREFER_OFF_W =    200_000
    must_off_vars   = []
    prefer_off_vars = []

    for e, emp in enumerate(employees):
        for req in emp.get("off_requests", []):
            d = req["day"]
            if d >= D:
                continue
            for s in range(S):
                if req.get("type", "prefer") == "must":
                    must_off_vars.append(work[e, d, s])
                else:
                    prefer_off_vars.append(work[e, d, s])

    # ── [소프트 6] 근무일수 편차 최소화 (타이브레이킹) ─
    # 직원 간 근무일수 max-min 차를 최소화 → 균등 배분 유도.
    FAIRNESS_W = 10
    work_days_vars = []
    for e in range(E):
        wd = model.NewIntVar(0, D, f"wd_{e}")
        model.Add(wd == sum(work[e, d, s] for d in range(D) for s in range(S)))
        work_days_vars.append(wd)
    max_wd = model.NewIntVar(0, D, "max_wd")
    min_wd = model.NewIntVar(0, D, "min_wd")
    model.AddMaxEquality(max_wd, work_days_vars)
    model.AddMinEquality(min_wd, work_days_vars)
    fairness_range = model.NewIntVar(0, D, "fairness_range")
    model.Add(fairness_range == max_wd - min_wd)

    # ── [소프트 7] 공휴일 근무 편차 최소화 (타이브레이킹) ─
    # holiday_indices에 지정된 공휴일의 근무 횟수 편차를 최소화.
    HOLIDAY_W = 5
    holiday_indices = [d for d in config.get("holiday_indices", []) if d < D]
    holiday_range_term = 0
    if holiday_indices and E > 1:
        hwork = []
        for e in range(E):
            hw = model.NewIntVar(0, len(holiday_indices), f"hw_{e}")
            model.Add(hw == sum(work[e, d, s] for d in holiday_indices for s in range(S)))
            hwork.append(hw)
        max_hw = model.NewIntVar(0, len(holiday_indices), "max_hw")
        min_hw = model.NewIntVar(0, len(holiday_indices), "min_hw")
        model.AddMaxEquality(max_hw, hwork)
        model.AddMinEquality(min_hw, hwork)
        h_range = model.NewIntVar(0, len(holiday_indices), "h_range")
        model.Add(h_range == max_hw - min_hw)
        holiday_range_term = HOLIDAY_W * h_range

    # ── 목적함수: 인건비 + 야간수당 + 패널티 최소화 ─
    labor = sum(
        work[e, d, s] * shifts[s]["hours"] * base_hw
        for e in range(E)
        for d in range(D)
        for s in range(S)
    )
    night = sum(
        work[e, d, s] * shifts[s]["hours"] * int(base_hw * night_rate)
        for e in range(E)
        for d in range(D)
        for s in range(S)
        if shifts[s]["is_night"]
    )

    model.Minimize(
        labor + night
        + MIN_STAFF_W   * sum(min_shortage_vars)   # 최소 인원 미달 (최우선)
        + MUST_OFF_W    * sum(must_off_vars)        # 필수 휴무 위반
        + UNDERSTAFF_W  * sum(understaff_vars)
        + LOW_HOURS_W   * sum(low_hours_vars)
        + PREFER_OFF_W  * sum(prefer_off_vars)      # 희망 휴무 위반
        + PREF_W        * sum(pref_vars)
        + FAIRNESS_W    * fairness_range            # 근무일수 편차 (타이브레이킹)
        + holiday_range_term                        # 공휴일 편차 (타이브레이킹)
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
            if actual_cnt < min_s[s]:
                shortage_report.append({
                    "day":      d,
                    "shift":    s,
                    "required": min_s[s],
                    "actual":   actual_cnt,
                    "shortage": min_s[s] - actual_cnt,
                })

    # ── 휴무 요청 위반 현황 ───────────────────────
    off_request_violations = []
    for e, emp in enumerate(employees):
        for req in emp.get("off_requests", []):
            d = req["day"]
            if d >= D:
                continue
            for s in range(S):
                if solver.Value(work[e, d, s]):
                    off_request_violations.append({
                        "employee_id": emp["id"],
                        "day":         d,
                        "shift":       s,
                        "type":        req.get("type", "prefer"),
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
