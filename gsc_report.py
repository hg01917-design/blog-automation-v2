"""
gsc_report.py
매일 오전 8시 텔레그램 아침 리포트
- 어제 AdSense 수익 / 이번달 누적 / 목표까지 잔액
- 급상승 키워드 + 조치 내용
- 오늘 발행 예정 키워드 목록
- GSC 성과 요약

실행: python3 gsc_report.py
launchd: com.hana.blog-gsc-report (08:00 KST)
"""
import os
import urllib.request
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE_DIR = Path(__file__).parent
KST = timezone(timedelta(hours=9))


def _load_env():
    env_path = BASE_DIR / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())


def _send_telegram(text: str):
    _load_env()
    token = os.environ.get("HanaAutobot", "")
    chat_id = "8674424194"
    if not token:
        print("[리포트] HanaAutobot 없음 — 출력만 합니다")
        print(text)
        return
    data = urllib.parse.urlencode({"chat_id": chat_id, "text": text}).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage", data=data,
    )
    urllib.request.urlopen(req, timeout=10)


def build_morning_report() -> str:
    now = datetime.now(KST)
    today_str = now.strftime("%Y-%m-%d")
    yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")
    lines = [f"🌅 아침 리포트 {today_str}\n{'─'*28}"]

    # ── 1. AdSense 수익 (어제 하루치) ────────────────────────────────────
    try:
        from adsense_tracker import collect_earnings
        earned_yesterday = collect_earnings(yesterday)
        if earned_yesterday is not None:
            lines.append(f"💰 AdSense ({yesterday}): ₩{earned_yesterday:,.0f}")
        else:
            lines.append(f"💰 AdSense ({yesterday}): 데이터 없음")
        lines.append("")
    except Exception as e:
        lines.append(f"💰 AdSense: 조회 실패 ({e})\n")

    # ── 2. GSC 성과 (어제 하루치) ────────────────────────────────────────
    try:
        from keyword_engine.gsc_connector import collect_daily, get_performance_summary
        # GSC는 2-3일 딜레이 → 3일 전 데이터 수집 (yesterday는 아직 비어있음)
        gsc_date = (now - timedelta(days=3)).strftime("%Y-%m-%d")
        collect_daily(gsc_date)
        perf = get_performance_summary(days=7)
        if perf:
            lines.append(f"📈 GSC 성과 (최근 7일 누적, {gsc_date}까지)")
            total_clicks = sum(v.get("total_clicks", 0) for v in perf.values())
            total_imp = sum(v.get("total_impressions", 0) for v in perf.values())
            lines.append(f"전체  클릭 {total_clicks:,}  노출 {total_imp:,}")
            top3 = sorted(perf.items(), key=lambda x: x[1].get("total_clicks", 0), reverse=True)[:3]
            for blog_id, data in top3:
                c = data.get("total_clicks", 0)
                i = data.get("total_impressions", 0)
                lines.append(f"  {blog_id}: 클릭 {c:,} / 노출 {i:,}")
            lines.append("")
    except Exception as e:
        lines.append(f"📈 GSC: 조회 실패 ({e})\n")

    # ── 3. 급상승 키워드 ─────────────────────────────────────────────────
    try:
        from decision_engine import run_daily_analysis
        analysis = run_daily_analysis()
        kw_added = analysis.get("keywords_added", 0)
        season = analysis.get("season_boosted", 0)
        low_ctr = analysis.get("low_ctr", 0)
        lines.append("🔍 오늘 조치")
        lines.append(f"  급상승 키워드 +{kw_added}개 추가")
        if season:
            lines.append(f"  시즌 키워드 {season}개 점수 상향")
        if low_ctr:
            lines.append(f"  CTR 낮은 글 {low_ctr}개 감지")
        lines.append("")
    except Exception as e:
        lines.append(f"🔍 분석: 오류 ({e})\n")

    # ── 4. 오늘 발행 예정 키워드 ─────────────────────────────────────────
    try:
        from keyword_engine.db_handler import fetch_next_pending
        lines.append("📝 오늘 발행 예정")
        blogs = ["goodisak", "nolja100", "salim1su", "baremi542",
                 "triplog", "woll100", "phn0502"]
        for blog_id in blogs:
            kw = fetch_next_pending(blog_id)
            if kw:
                lines.append(f"  {blog_id}: {kw}")
        lines.append("")
    except Exception as e:
        lines.append(f"📝 키워드: 오류 ({e})\n")

    return "\n".join(lines)


if __name__ == "__main__":
    print("아침 리포트 생성 중...")
    report = build_morning_report()
    print(report)
    _send_telegram(report)
    print("✅ 리포트 생성 완료")
