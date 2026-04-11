"""
adsense_tracker.py
AdSense 일별 수익 수집 + 목표 달성률 추적 + 발행량 자동 조정
"""
import json
import urllib.request
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE_DIR = Path(__file__).parent
KST = timezone(timedelta(hours=9))


def _load_env():
    env_path = BASE_DIR / ".env"
    if env_path.exists():
        import os
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())


def _get_token() -> str:
    from gsc_indexing import _get_access_token
    return _get_access_token()


def _adsense_api(path: str, params: dict = None) -> dict:
    token = _get_token()
    url = f"https://adsense.googleapis.com/v2/{path}"
    if params:
        # doseq=True: list 값을 개별 파라미터로 인코딩 (metrics 등 다중값 지원)
        url += "?" + urllib.parse.urlencode(params, doseq=True)
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def get_account_name() -> str | None:
    """AdSense 계정 이름 조회"""
    try:
        data = _adsense_api("accounts")
        accounts = data.get("accounts", [])
        return accounts[0]["name"] if accounts else None
    except Exception:
        return None


def collect_earnings(date: str = None) -> float | None:
    """특정 날짜 수익 수집 → DB 저장. date: YYYY-MM-DD (기본: 어제)"""
    from keyword_engine.db_handler import save_adsense_daily
    if date is None:
        date = (datetime.now(KST) - timedelta(days=1)).strftime("%Y-%m-%d")

    account = get_account_name()
    if not account:
        return None

    y, m, d = date.split("-")
    try:
        resp = _adsense_api(
            f"{account}/reports:generate",
            {
                "dateRange": "CUSTOM",
                "startDate.year": y, "startDate.month": m, "startDate.day": d,
                "endDate.year": y, "endDate.month": m, "endDate.day": d,
                "metrics": ["ESTIMATED_EARNINGS", "PAGE_VIEWS", "CLICKS"],
                "currencyCode": "KRW",
            },
        )
        cells = resp.get("totals", {}).get("cells", [])
        earnings = float(cells[0]["value"]) if len(cells) > 0 else 0.0
        pageviews = int(float(cells[1]["value"])) if len(cells) > 1 else 0
        clicks = int(float(cells[2]["value"])) if len(cells) > 2 else 0
        save_adsense_daily(date, earnings, pageviews, clicks)
        return earnings
    except Exception as e:
        print(f"[AdSense] 수집 오류 ({date}): {e}")
        return None


def get_goal_status() -> dict:
    """이번달 목표 달성 현황"""
    from keyword_engine.db_handler import get_monthly_earnings, get_revenue_goal
    now = datetime.now(KST)
    year, month = now.year, now.month
    day_of_month = now.day
    days_in_month = 31 if month in (1, 3, 5, 7, 8, 10, 12) else (
        30 if month in (4, 6, 9, 11) else (
            29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28
        )
    )

    earned = get_monthly_earnings(year, month)
    goal = get_revenue_goal()
    remaining = max(0, goal - earned)

    # 현재 pace (일별 평균) vs 필요 pace
    daily_earned_avg = earned / day_of_month if day_of_month > 0 else 0
    days_left = days_in_month - day_of_month
    required_daily = remaining / days_left if days_left > 0 else 0
    pace_ratio = daily_earned_avg / required_daily if required_daily > 0 else 1.0

    achievement_pct = (earned / goal * 100) if goal > 0 else 0

    return {
        "year": year,
        "month": month,
        "goal_krw": goal,
        "earned_krw": earned,
        "remaining_krw": remaining,
        "achievement_pct": round(achievement_pct, 1),
        "daily_avg_krw": round(daily_earned_avg),
        "required_daily_krw": round(required_daily),
        "pace_ratio": round(pace_ratio, 2),
        "days_left": days_left,
        "is_on_track": pace_ratio >= 0.8,
    }


def get_recommended_publish_count(blog_id: str = None) -> int:
    """목표 달성 pace에 따른 권장 발행량 (블로그당 하루 글 수)"""
    status = get_goal_status()
    pace = status["pace_ratio"]

    if pace >= 1.2:   # 초과 달성 중
        return 1
    elif pace >= 0.8: # 정상 범위
        return 1
    elif pace >= 0.5: # 느림
        return 2
    else:             # 매우 느림
        return 3


def set_monthly_goal(krw: int):
    """월 목표 수익 설정"""
    from keyword_engine.db_handler import set_revenue_goal
    set_revenue_goal(krw)
    print(f"[AdSense] 월 목표 설정: ₩{krw:,}")


def format_goal_report() -> str:
    s = get_goal_status()
    pace_emoji = "🟢" if s["is_on_track"] else "🔴"
    return (
        f"💰 AdSense 수익 현황 ({s['year']}-{s['month']:02d})\n"
        f"목표: ₩{s['goal_krw']:,}\n"
        f"현재: ₩{s['earned_krw']:,.0f} ({s['achievement_pct']}%)\n"
        f"잔액: ₩{s['remaining_krw']:,.0f} ({s['days_left']}일 남음)\n"
        f"{pace_emoji} 일 평균 ₩{s['daily_avg_krw']:,} "
        f"(필요 ₩{s['required_daily_krw']:,}/일)"
    )


if __name__ == "__main__":
    _load_env()
    print("AdSense 어제 수익 수집 중...")
    earned = collect_earnings()
    if earned is not None:
        print(f"수집 완료: ₩{earned:,.0f}")
    print(format_goal_report())
