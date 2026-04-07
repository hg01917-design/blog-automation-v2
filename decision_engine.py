"""
decision_engine.py
판단 엔진 — GSC 패턴 분석 + 키워드 확장 + CTR 낮은 글 제목 수정 + 발행량 조정
overnight_run.py에서 라운드 시작 전 호출
"""
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE_DIR = Path(__file__).parent
KST = timezone(timedelta(hours=9))


def _log(msg: str, on_log=None):
    if on_log:
        on_log(msg)
    else:
        print(msg, flush=True)


# ── 1. 잘 되는 글 패턴 → 유사 키워드 확장 ─────────────────────────────────

def expand_from_rising_pages(on_log=None) -> int:
    """급상승 페이지 감지 → 유사 키워드 DB 추가"""
    try:
        from keyword_engine.gsc_connector import generate_keywords_from_gsc
        added = generate_keywords_from_gsc(on_log=on_log)
        if added:
            _log(f"[판단엔진] 급상승 패턴에서 키워드 {added}개 추가", on_log)
        return added
    except Exception as e:
        _log(f"[판단엔진] 키워드 확장 오류: {e}", on_log)
        return 0


# ── 2. CTR 낮은 글 제목 수정 시도 ─────────────────────────────────────────

def fix_low_ctr_titles(on_log=None) -> int:
    """CTR 1% 미만 + 노출 50회↑ 글 → Claude로 제목 개선안 생성 → Tistory 수정"""
    try:
        from keyword_engine.gsc_connector import get_low_ctr_pages_with_titles
        pages = get_low_ctr_pages_with_titles(threshold=0.01, min_impressions=50)
        if not pages:
            return 0
        _log(f"[판단엔진] CTR 낮은 글 {len(pages)}개 감지", on_log)
        # TODO: Claude API로 제목 개선안 생성 후 Tistory 수정 (v2)
        # 현재는 감지 + 로그만
        for p in pages[:5]:
            _log(
                f"  └ {p['blog_id']}: {p['slug'][:40]} "
                f"(노출 {p['total_impressions']}, CTR {p['avg_ctr']:.1%})",
                on_log,
            )
        return len(pages)
    except Exception as e:
        _log(f"[판단엔진] CTR 분석 오류: {e}", on_log)
        return 0


# ── 3. 시즌/트렌드 키워드 우선순위 상향 ────────────────────────────────────

_SEASON_KEYWORDS = {
    # 월 → (시즌 키워드 패턴, 점수 보정)
    3:  (["벚꽃", "봄나들이", "입학", "이사", "봄옷"], 20),
    4:  (["벚꽃", "어버이날", "봄여행", "축제"], 20),
    5:  (["어린이날", "어버이날", "가정의달", "황금연휴"], 25),
    6:  (["장마", "에어컨", "여름준비", "여행"], 15),
    7:  (["휴가", "여름여행", "제주도", "해수욕장"], 25),
    8:  (["휴가", "여름여행", "말복", "개학준비"], 20),
    9:  (["추석", "단풍", "가을여행", "국감"], 20),
    10: (["단풍", "핼러윈", "국감", "가을낚시"], 20),
    11: (["수능", "김장", "연말", "겨울준비"], 20),
    12: (["크리스마스", "연말정산", "송년", "겨울여행"], 25),
    1:  (["새해", "연말정산", "신년", "겨울"], 15),
    2:  (["설날", "밸런타인", "졸업", "입학준비"], 20),
}


def boost_seasonal_keywords(on_log=None) -> int:
    """현재 달 시즌 키워드 점수 상향"""
    from keyword_engine.db_handler import _conn
    month = datetime.now(KST).month
    season_data = _SEASON_KEYWORDS.get(month, ([], 0))
    patterns, boost = season_data
    if not patterns:
        return 0

    boosted = 0
    with _conn() as db:
        for pattern in patterns:
            result = db.execute(
                """UPDATE keywords SET score = MIN(score + ?, 100)
                   WHERE keyword LIKE ? AND score < 80""",
                (boost, f"%{pattern}%"),
            )
            boosted += result.rowcount
    if boosted:
        _log(f"[판단엔진] 시즌 키워드 {boosted}개 점수 +{boost}", on_log)
    return boosted


# ── 4. 발행량 조정 권고 ────────────────────────────────────────────────────

def get_publish_count_recommendation(on_log=None) -> dict:
    """블로그별 오늘 권장 발행량 반환 {blog_id: count}"""
    try:
        from adsense_tracker import get_recommended_publish_count
        count = get_recommended_publish_count()
        blogs = ["goodisak", "nolja100", "salim1su", "baremi542",
                 "triplog", "woll100", "phn0502"]
        rec = {b: count for b in blogs}
        if count > 1:
            _log(f"[판단엔진] 수익 pace 저조 → 발행량 {count}개/블로그 권고", on_log)
        return rec
    except Exception:
        return {}


# ── 메인: overnight_run.py에서 라운드 시작 전 호출 ─────────────────────────

def run_daily_analysis(on_log=None) -> dict:
    """
    매일 1회 실행 (overnight_run.py 첫 라운드 전).
    - GSC 데이터 수집
    - 급상승 키워드 추가
    - 시즌 키워드 점수 상향
    - CTR 낮은 글 감지
    반환: {"keywords_added": N, "season_boosted": N, "low_ctr": N}
    """
    _log("[판단엔진] 일간 분석 시작", on_log)
    results = {}

    # GSC 어제 데이터 수집
    try:
        from keyword_engine.gsc_connector import collect_daily
        gsc_result = collect_daily()
        _log(f"[판단엔진] GSC 수집 완료: {list(gsc_result.keys())}", on_log)
    except Exception as e:
        _log(f"[판단엔진] GSC 수집 생략 ({e})", on_log)

    # AdSense 어제 수익 수집
    try:
        from adsense_tracker import collect_earnings
        earned = collect_earnings()
        if earned is not None:
            _log(f"[판단엔진] AdSense 어제 수익: ₩{earned:,.0f}", on_log)
    except Exception as e:
        _log(f"[판단엔진] AdSense 수집 생략 ({e})", on_log)

    # 급상승 키워드 추가
    results["keywords_added"] = expand_from_rising_pages(on_log=on_log)

    # 시즌 키워드 점수 상향
    results["season_boosted"] = boost_seasonal_keywords(on_log=on_log)

    # CTR 낮은 글 감지 (로그만)
    results["low_ctr"] = fix_low_ctr_titles(on_log=on_log)

    _log(f"[판단엔진] 완료 — 키워드+{results['keywords_added']}, 시즌+{results['season_boosted']}", on_log)
    return results


if __name__ == "__main__":
    run_daily_analysis()
