"""카테고리별 키워드 수집 엔진 — 빠른 키워드 반환 + 펍코드 백그라운드"""
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from keyword_engine import db_handler
from keyword_engine import gsc_connector
from keyword_engine import naver_api
from keyword_engine import pub_finder
from keyword_engine import queue_pusher
from keyword_engine import title_collector
from keyword_engine import keyword_scorer
from keyword_engine import related_finder

# 카테고리 ↔ 블로그 ID 매핑
CATEGORY_MAP = {
    "IT":         "goodisak",
    "여행":       "nolja100",
    "살림":       "salim1su",
    "정부지원금": "baremi542",
}
BLOG_TO_CATEGORY = {v: k for k, v in CATEGORY_MAP.items()}
ALL_CATEGORIES = list(CATEGORY_MAP.keys())

# 카테고리별 제목 필터 — 해당 단어가 하나라도 포함된 제목만 키워드 추출
CATEGORY_TITLE_KEYWORDS = {
    "IT": {
        "추천", "후기", "리뷰", "비교", "사용법", "설정", "갤럭시", "아이폰", "맥북",
        "노트북", "스마트폰", "이어폰", "태블릿", "청정기", "청소기", "워치", "모니터",
        "스피커", "웹캠", "OTT", "넷플릭스", "티빙", "요금제", "미니PC", "게이밍",
        "앱", "프로그램", "소프트웨어", "하드웨어", "CPU", "GPU", "SSD", "RAM",
    },
    "여행": {
        "여행", "코스", "맛집", "숙소", "카페", "관광", "명소", "드라이브", "캠핑",
        "글램핑", "호텔", "펜션", "리조트", "휴가", "제주", "부산", "강원", "경주",
        "속초", "전주", "여수", "통영", "남해", "당일치기", "국내여행", "해외여행",
        "등산", "국립공원", "둘레길", "트레킹", "여행지",
    },
    "살림": {
        "절약", "정리", "청소", "살림", "인테리어", "요리", "레시피", "세탁",
        "냉장고", "주방", "수납", "에너지", "관리비", "전기", "가스비", "통신비",
        "식비", "생활비", "가전", "꿀팁", "분리수거", "재활용", "옷",
    },
    "정부지원금": {
        "지원금", "복지", "혜택", "지원", "신청", "급여", "바우처", "수급", "청년",
        "장애인", "출산", "육아", "노인", "실업", "취업", "주거", "교육", "의료",
        "정부", "국가", "보조금", "감면", "할인", "무료", "제도", "정책",
    },
}

DEFAULT_MIN_SCORE  = 100_000
DEFAULT_MIN_VOLUME = 500
DEFAULT_TOP_N      = 50


def _log(msg, on_log=None):
    print(msg, flush=True)
    if on_log:
        on_log(msg)


def run_category(
    category: str,
    top_n: int = DEFAULT_TOP_N,
    min_score: float = DEFAULT_MIN_SCORE,
    min_volume: int = DEFAULT_MIN_VOLUME,
    push_to_notion: bool = True,
    use_playwright: bool = False,
    on_log=None,
    on_keyword=None,
) -> list:
    """
    카테고리별 키워드 수집

    흐름:
      1단계: Naver 검색 → Tistory URL 수집
      2단계: RSS 제목 즉시 수집 (카테고리 제목 필터 적용)
      3단계: 키워드 추출 + 점수 계산 → 즉시 반환
      백그라운드: pub코드 추출 + 연관 도메인 확장 (DB 저장용)
    """
    blog_id = CATEGORY_MAP.get(category)
    if not blog_id:
        _log(f"[category_engine] 알 수 없는 카테고리: {category}", on_log)
        return []

    _log("═" * 55, on_log)
    _log(f"  카테고리: {category}  블로그: {blog_id}", on_log)
    _log("═" * 55, on_log)

    queries = naver_api.BLOG_QUERIES.get(blog_id, [])

    # ── 1단계: Naver 검색 → Tistory URL 수집 ─────────────
    _log("\n[1단계] Tistory 도메인 수집 중...", on_log)
    tistory_urls = naver_api.collect_tistory_urls(queries, display=100, on_log=on_log)
    _log(f"[1단계] {len(tistory_urls)}개 도메인 확보", on_log)

    if not tistory_urls:
        _log("[엔진] URL 수집 실패 — 종료", on_log)
        return []

    # ── 백그라운드: pub코드 추출 + 연관 도메인 (DB 저장용) ──
    def _bg_pub_job():
        try:
            url_list = list(tistory_urls)
            pub_map = pub_finder.find_pub_codes_fast(url_list, on_log=None)
            pub_groups = pub_finder.group_by_pub_code(pub_map)
            for url, pub in pub_map.items():
                db_handler.save_site(url, pub, category=category)
            extra_urls = related_finder.expand_by_pub_codes(pub_groups, on_log=None)
            top_pub = list(pub_groups.keys())[0] if pub_groups else ""
            for url in extra_urls:
                db_handler.save_site(url, top_pub, category=category)
        except Exception:
            pass

    bg = threading.Thread(target=_bg_pub_job, daemon=True)
    bg.start()
    _log("[백그라운드] pub코드/연관 도메인 탐색 시작 (결과는 DB에 저장)", on_log)

    # ── 2단계: RSS 제목 수집 (즉시) ───────────────────────
    _log("\n[2단계] RSS 제목 수집 중...", on_log)
    all_titles = title_collector.collect_from_all(tistory_urls, on_log=on_log)
    _log(f"[2단계] {len(all_titles)}개 제목 수집", on_log)

    if not all_titles:
        _log("[엔진] 제목 수집 실패 — 종료", on_log)
        return []

    # ── 카테고리 제목 필터 ─────────────────────────────────
    cat_filter = CATEGORY_TITLE_KEYWORDS.get(category, set())
    if cat_filter:
        filtered_titles = [t for t in all_titles if any(kw in t for kw in cat_filter)]
        _log(f"[필터] {len(all_titles)}개 → {len(filtered_titles)}개 ({category} 관련)", on_log)
        all_titles = filtered_titles if len(filtered_titles) >= 30 else all_titles

    if not all_titles:
        _log("[엔진] 제목 필터 후 데이터 없음 — 종료", on_log)
        return []

    # ── 3단계: 키워드 추출 ────────────────────────────────
    _log("\n[3단계] 키워드 추출 중...", on_log)
    candidates = title_collector.extract_keywords_from_titles(all_titles, top_n=100)
    _log(f"[3단계] 상위 후보 {len(candidates)}개", on_log)

    if not candidates:
        _log("[엔진] 키워드 추출 실패 — 종료", on_log)
        return []

    # ── 4단계: 점수 계산 + 실시간 반환 ───────────────────
    _log(f"\n[4단계] 점수 계산 중 ({len(candidates)}개)...", on_log)

    def _realtime_kw(item):
        # UI 실시간 표시: 검색량만 체크 (점수와 무관하게 바로 보여줌)
        if item["volume"] >= min_volume:
            if on_keyword:
                on_keyword(item)

    scored = keyword_scorer.score_keywords(
        candidates,
        get_pub_count_fn=naver_api.get_blog_count,
        on_log=on_log,
        on_keyword=_realtime_kw,
    )

    # ── 5단계: 필터링 + DB 저장 ───────────────────────────
    result = [
        k for k in scored
        if k["volume"] >= min_volume and k["score"] >= min_score
    ]
    _log(f"\n[5단계] 필터 후 {len(result)}개 (검색량 {min_volume:,}+, 점수 {min_score:,}+)", on_log)

    gsc_boost = set(gsc_connector.get_rising_keywords())
    if gsc_boost:
        result = (
            [k for k in result if k["keyword"] in gsc_boost] +
            [k for k in result if k["keyword"] not in gsc_boost]
        )

    for item in result:
        db_handler.upsert_keyword(
            item["keyword"], item["score"], item["volume"], item["pub_count"],
            category=category,
        )

    top = result[:top_n]

    _log(f"\n{'═' * 55}", on_log)
    _log(f"  [{category}] 완료: {len(top)}개 키워드", on_log)
    _log(f"{'═' * 55}", on_log)
    for i, item in enumerate(top, 1):
        _log(
            f"{i:3}. {item['keyword']:<22} "
            f"점수:{item['score']:>12,.0f}  "
            f"검색량:{item['volume']:>7,}  "
            f"발행량:{item['pub_count']:>7,}",
            on_log,
        )

    # ── 6단계: Notion 큐 적재 ────────────────────────────
    if push_to_notion and blog_id and top:
        _log(f"\n[6단계] Notion 큐 적재 → {blog_id}", on_log)
        saved = queue_pusher.push(top, blog_id, on_log)
        _log(f"[6단계] {saved}개 저장 완료", on_log)

    return top


# ── 에이전트/GUI 조회용 API ──────────────────────────────

def get_keywords(category: str, n: int = 20, min_score: float = 0) -> list:
    """카테고리별 키워드 즉시 조회 — 에이전트 호출용 (로컬 DB 기반, 빠름)"""
    return db_handler.get_keywords_by_category(category, n=n, min_score=min_score)


def get_stats() -> dict:
    """카테고리별 수집 현황 반환"""
    return db_handler.get_category_stats()


def get_sites(category: str) -> list:
    """카테고리별 수집된 사이트 목록"""
    return db_handler.get_sites_by_category(category)


# ── CLI ──────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="카테고리별 키워드 엔진")
    parser.add_argument("--category", choices=ALL_CATEGORIES, required=True)
    parser.add_argument("--top", type=int, default=DEFAULT_TOP_N)
    parser.add_argument("--min-score", type=float, default=DEFAULT_MIN_SCORE)
    parser.add_argument("--min-volume", type=int, default=DEFAULT_MIN_VOLUME)
    parser.add_argument("--no-push", action="store_true")
    parser.add_argument("--query", action="store_true", help="수집 없이 DB에서 조회만")
    args = parser.parse_args()

    if args.query:
        kws = get_keywords(args.category, n=args.top)
        print(f"\n[{args.category}] 저장된 키워드 {len(kws)}개:")
        for i, k in enumerate(kws, 1):
            print(f"{i:3}. {k['keyword']:<22} 점수:{k['score']:>12,.0f}  검색량:{k['volume']:>7,}")
    else:
        run_category(
            category=args.category,
            top_n=args.top,
            min_score=args.min_score,
            min_volume=args.min_volume,
            push_to_notion=not args.no_push,
        )
