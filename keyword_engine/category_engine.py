"""카테고리별 키워드 수집 엔진 — pub코드 역분석 + 연관 도메인 확장 + DB 저장"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from keyword_engine import analyze_titles
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
    "IT":      "goodisak",
    "여행":    "nolja100",
    "살림":    "salim1su",
    "정부지원금": "baremi542",
}
BLOG_TO_CATEGORY = {v: k for k, v in CATEGORY_MAP.items()}
ALL_CATEGORIES = list(CATEGORY_MAP.keys())

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
    use_playwright: bool = True,
    on_log=None,
    on_keyword=None,
) -> list:
    """
    카테고리별 전체 파이프라인 실행

    흐름:
      카테고리 쿼리 → Tistory URL 수집 (상위 100위)
      → pub코드 추출 (AdSense)
      → pub코드로 연관 도메인 확장
      → 전체 도메인 RSS 제목 수집
      → 키워드 추출 + 점수 계산
      → DB 저장 (category 태그)
      → Notion 큐 적재 (옵션)
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
    _log("\n[1단계] Tistory 상위 도메인 수집 중...", on_log)
    tistory_urls = naver_api.collect_tistory_urls(queries, display=100, on_log=on_log)
    _log(f"[1단계] {len(tistory_urls)}개 도메인 확보", on_log)

    if not tistory_urls:
        _log("[엔진] URL 수집 실패 — 종료", on_log)
        return []

    # ── 2단계: pub코드 추출 ────────────────────────────────
    _log("\n[2단계] AdSense pub코드 추출 중...", on_log)
    url_list = list(tistory_urls)

    if use_playwright:
        try:
            pub_map = pub_finder.find_pub_codes_playwright(url_list, on_log)
        except Exception as e:
            _log(f"[2단계] Playwright 오류({e}), 경량 모드로 폴백", on_log)
            pub_map = pub_finder.find_pub_codes_fast(url_list, on_log)
    else:
        pub_map = pub_finder.find_pub_codes_fast(url_list, on_log)

    _log(f"[2단계] pub코드 발견: {len(pub_map)}/{len(url_list)}개 사이트", on_log)

    # pub코드별 그룹핑
    pub_groups = pub_finder.group_by_pub_code(pub_map)
    _log(f"[2단계] 운영자 {len(pub_groups)}명 식별", on_log)
    for pub, sites in list(pub_groups.items())[:3]:
        _log(f"  {pub} → {len(sites)}개 사이트", on_log)

    # DB에 사이트 저장
    for url, pub in pub_map.items():
        db_handler.save_site(url, pub, category=category)

    # ── 3단계: pub코드로 연관 도메인 확장 ─────────────────
    _log("\n[3단계] pub코드 연관 도메인 확장 중...", on_log)
    extra_urls = related_finder.expand_by_pub_codes(pub_groups, on_log=on_log)

    all_urls = tistory_urls | set(pub_map.keys()) | extra_urls
    _log(f"[3단계] 총 {len(all_urls)}개 도메인 (원본 {len(tistory_urls)} + 확장 {len(extra_urls)})", on_log)

    # 확장된 사이트도 DB 저장
    for url in extra_urls:
        # pub코드는 모름 — 가장 많이 나온 pub코드로 임시 태깅
        top_pub = list(pub_groups.keys())[0] if pub_groups else ""
        db_handler.save_site(url, top_pub, category=category)

    # ── 4단계: RSS 글 제목 수집 ───────────────────────────
    _log("\n[4단계] RSS 피드에서 글 제목 수집 중...", on_log)
    # pub코드 있는 검증 사이트 우선
    verified = set(pub_map.keys())
    other    = all_urls - verified

    pub_titles = title_collector.collect_from_all(verified, on_log=on_log)
    _log(f"[4단계] 검증 사이트 {len(pub_titles)}개 제목", on_log)

    if len(pub_titles) < 200:
        extra_titles = title_collector.collect_from_all(other, on_log=on_log)
        all_titles = pub_titles + extra_titles
        _log(f"[4단계] 보충 후 총 {len(all_titles)}개 제목", on_log)
    else:
        all_titles = pub_titles
        _log(f"[4단계] 총 {len(all_titles)}개 제목", on_log)

    if not all_titles:
        _log("[엔진] 제목 수집 실패 — 종료", on_log)
        return []

    # 카테고리 분포 분석
    _log("\n[분석] 수익 카테고리 분포:", on_log)
    analysis = analyze_titles.analyze(all_titles)
    analyze_titles.print_report(analysis)

    # ── 5단계: 키워드 추출 ────────────────────────────────
    _log("\n[5단계] 키워드 추출 중...", on_log)
    candidates = title_collector.extract_keywords_from_titles(all_titles)
    _log(f"[5단계] 후보 키워드 {len(candidates)}개", on_log)

    if not candidates:
        _log("[엔진] 키워드 추출 실패 — 종료", on_log)
        return []

    # ── 6단계: 기회점수 계산 ──────────────────────────────
    _log(f"\n[6단계] 기회점수 계산 중 ({len(candidates)}개)...", on_log)
    scored = keyword_scorer.score_keywords(
        candidates,
        get_pub_count_fn=naver_api.get_blog_count,
        on_log=on_log,
        on_keyword=on_keyword,
    )

    # ── 7단계: 필터링 ─────────────────────────────────────
    filtered = [
        k for k in scored
        if k["volume"] >= min_volume and k["score"] >= min_score
    ]
    _log(
        f"\n[7단계] 필터 후 {len(filtered)}개 "
        f"(검색량 {min_volume:,}+, 점수 {min_score:,}+)",
        on_log,
    )

    # GSC 교차 부스트 (선택)
    gsc_boost = set(gsc_connector.get_rising_keywords())
    if gsc_boost:
        filtered = (
            [k for k in filtered if k["keyword"] in gsc_boost] +
            [k for k in filtered if k["keyword"] not in gsc_boost]
        )

    # DB 저장 (category 태그 포함)
    for item in filtered:
        db_handler.upsert_keyword(
            item["keyword"], item["score"], item["volume"], item["pub_count"],
            category=category,
        )

    top = filtered[:top_n]

    # 결과 출력
    _log(f"\n{'═' * 55}", on_log)
    _log(f"  [{category}] 결과: 상위 {len(top)}개 키워드", on_log)
    _log(f"{'═' * 55}", on_log)
    for i, item in enumerate(top, 1):
        _log(
            f"{i:3}. {item['keyword']:<22} "
            f"점수:{item['score']:>12,.0f}  "
            f"검색량:{item['volume']:>7,}  "
            f"발행량:{item['pub_count']:>7,}",
            on_log,
        )

    # ── 8단계: Notion 큐 적재 ────────────────────────────
    if push_to_notion and blog_id and top:
        _log(f"\n[8단계] Notion 큐 적재 → {blog_id}", on_log)
        saved = queue_pusher.push(top, blog_id, on_log)
        _log(f"[8단계] {saved}개 저장 완료", on_log)

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
    parser.add_argument("--no-playwright", action="store_true")
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
            use_playwright=not args.no_playwright,
        )
