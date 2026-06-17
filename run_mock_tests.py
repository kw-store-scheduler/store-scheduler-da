"""
목 데이터 일괄 실행 스크립트
  python run_mock_tests.py            → 전체 시나리오
  python run_mock_tests.py W02 M01   → 지정 키만 실행
"""

import sys
from scheduler_core_0527 import solve_schedule
from scheduler_mock_data  import SCENARIOS

# ── 날짜·교대 레이블 ───────────────────────────────────────

def _day_label(day_idx: int, num_days: int) -> str:
    if num_days == 7:
        return ["월", "화", "수", "목", "금", "토", "일"][day_idx]
    # 월간: '6/1', '6/2', ...
    return f"6/{day_idx + 1}"


def _print_result(key: str, scenario: dict, result: dict) -> None:
    cfg       = scenario["config"]
    label     = scenario["label"]
    note      = scenario.get("note", "")
    num_days  = cfg.get("num_days", 7)
    shifts    = cfg["shifts"]
    employees = cfg["employees"]
    shift_names = [s["name"] for s in shifts]

    print(f"\n{'='*65}")
    print(f"  [{key}] {label}")
    print(f"  {note}")
    print(f"{'─'*65}")
    print(f"  상태     : {result['status']}")
    if result["cost"] is not None:
        print(f"  인건비   : {result['cost']:,}원")
    print(f"  풀이시간 : {result['solve_ms']}ms")

    # ── 휴무 요청 위반 현황 ──
    vr = result.get("off_request_violations", [])
    if vr:
        print(f"\n  [휴무 요청 위반] ({len(vr)}건)")
        for v in vr:
            d     = _day_label(v["day"], num_days)
            sn    = shift_names[v["shift"]]
            etype = "필수" if v["type"] == "must" else "희망"
            emp_name = next(
                e["name"] for e in employees if e["id"] == v["employee_id"]
            )
            print(f"    {emp_name} {d} {sn} [{etype} 휴무 위반]")

    # ── 인원 부족 현황 ──
    sr = result["shortage_report"]
    if sr:
        print(f"\n  [인원 부족 현황] ({len(sr)}건)")
        for r in sr[:20]:     # 20건까지만 출력
            d = _day_label(r["day"], num_days)
            sn = shift_names[r["shift"]]
            print(f"    {d} {sn} -> 필요 {r['required']}명 / 실제 {r['actual']}명 (부족 {r['shortage']}명)")
        if len(sr) > 20:
            print(f"    ... 외 {len(sr)-20}건 생략")
    else:
        print(f"\n  인원 부족 없음")

    # ── 스케줄 요약 ──
    if result["schedule"]:
        print(f"\n  [스케줄 요약]")
        for er in result["schedule"]:
            emp_name = next(
                e["name"] for e in employees if e["id"] == er["employee_id"]
            )
            cnt = len(er["assignments"])
            days_list = ", ".join(
                f"{_day_label(a['day'], num_days)}{shift_names[a['shift']][0]}"
                for a in er["assignments"][:10]
            )
            suffix = " ..." if cnt > 10 else ""
            print(f"    {emp_name:8s}: {cnt:2d}일 출근  [{days_list}{suffix}]")

    # ── 복수 최적해 ──
    if result["has_multiple_optimal"]:
        n = len(result["alt_schedules"]) + 1
        print(f"\n  *** 복수 최적해 존재: 동일 비용 해 {n}개 이상 ***")
        for i, alt in enumerate(result["alt_schedules"], 2):
            print(f"  [대안 #{i}]")
            for er in alt:
                emp_name = next(
                    e["name"] for e in employees if e["id"] == er["employee_id"]
                )
                cnt = len(er["assignments"])
                days_list = ", ".join(
                    f"{_day_label(a['day'], num_days)}{shift_names[a['shift']][0]}"
                    for a in er["assignments"][:10]
                )
                suffix = " ..." if cnt > 10 else ""
                print(f"    {emp_name:8s}: {cnt:2d}일 [{days_list}{suffix}]")


# ── 메인 ───────────────────────────────────────────────────

def main():
    keys = sys.argv[1:] if len(sys.argv) > 1 else list(SCENARIOS.keys())

    total = len(keys)
    print(f"\n스케줄러 목 데이터 실행 — {total}개 시나리오")

    for key in keys:
        if key not in SCENARIOS:
            print(f"[SKIP] '{key}' 시나리오 없음. 사용 가능: {list(SCENARIOS.keys())}")
            continue

        scenario = SCENARIOS[key]
        result   = solve_schedule(scenario["config"], max_alt_solutions=3)
        _print_result(key, scenario, result)

    print(f"\n{'='*65}")
    print("  완료")


if __name__ == "__main__":
    main()
