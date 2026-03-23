"""천하무적 키워드 엔진 — pub코드 역분석 + Tistory RSS 키워드 추출"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from keyword_engine import (
    analyze_titles,
    db_handler,
    gsc_connector,
    naver_api,
    pub_finder,
    queue_pusher,
    title_collector,
)
from keyword_engine import keyword_scorer

DEFAULT_MIN_SCORE = 100_000
DEFAULT_MIN_VOLUME = 500
DEFAULT_TOP_N = 50


def _log(msg: str, on_log=None):
    print(msg, flush=True)
    if on_log:
        on_log(msg)


def run(
    queries: list = None,
    top_n: int = DEFAULT_TOP_N,
    blog_id: str = None,
    min_score: float = DEFAULT_MIN_SCORE,
    min_volume: int = DEFAULT_MIN_VOLUME,
    push_to_notion: bool = True,
    use_playwright: bool = True,
    on_log=None,
) -> list:
    """
    천하무적 키워드 엔진 메인 실행

    흐름:
      Naver 검색 → Tistory URL 수집
      → Playwright로 각 사이트 pub코드 추출
      → pub코드로 운영자 그룹핑 (같은 pub = 검증된 수익 블로거)
      → 해당 사이트들 RSS에서 글 제목 대량 수집
      → 제목에서 키워드 추출 + 카테고리 분석
      → 기회점수 계산 (블로그 발행량 기반, API 비용 없음)
      → 상위 N개 Notion 큐 적재
    """
    _log("═" * 55, on_log)
    _log("  천하무적 키워드 엔진 (pub코드 역분석 모드)", on_log)
    _log("═" * 55, on_log)

    # ── 1단계: Naver 검색 → Tistory URL 수집 ─────────────
    _log("\n[1단계] Tistory 블로그 URL 수집 중...", on_log)
    tistory_urls = naver_api.collect_tistory_urls(queries, on_log=on_log)
    _log(f"[1단계] Tistory 블로그 {len(tistory_urls)}개 확보", on_log)

    if not tistory_urls:
        _log("[엔진] Tistory URL 수집 실패 — 종료", on_log)
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

    # ── 3단계: pub코드로 운영자 그룹핑 ───────────────────
    _log("\n[3단계] 운영자 그룹핑...", on_log)
    pub_groups = pub_finder.group_by_pub_code(pub_map)

    _log(f"[3단계] 운영자 {len(pub_groups)}명 식별", on_log)
    for pub, sites in list(pub_groups.items())[:5]:
        _log(f"  {pub}: {len(sites)}개 사이트 — {sites}", on_log)

    # pub코드 있는 사이트 (검증된 수익 블로거)
    adsense_urls = set(pub_map.keys())
    remaining_urls = tistory_urls - adsense_urls

    # ── 4단계: RSS 글 제목 수집 — pub코드 사이트 우선 ────
    _log("\n[4단계] RSS 피드에서 글 제목 수집 중...", on_log)
    _log(f"  - pub코드 검증 사이트: {len(adsense_urls)}개 (우선)", on_log)
    _log(f"  - 나머지 사이트: {len(remaining_urls)}개 (보충)", on_log)

    pub_titles = title_collector.collect_from_all(adsense_urls, on_log=on_log)
    _log(f"[4단계] pub코드 사이트 {len(pub_titles)}개 제목 수집", on_log)

    # pub코드 사이트 제목이 적으면 나머지 사이트로 보충
    if len(pub_titles) < 200:
        extra_titles = title_collector.collect_from_all(remaining_urls, on_log=on_log)
        all_titles = pub_titles + extra_titles
        _log(f"[4단계] 보충 후 총 {len(all_titles)}개 제목", on_log)
    else:
        all_titles = pub_titles
        _log(f"[4단계] 총 {len(all_titles)}개 제목 수집 (pub코드 사이트만)", on_log)

    if not all_titles:
        _log("[엔진] 제목 수집 실패 — 종료", on_log)
        return []

    # 카테고리 분석 (수익 니치 파악)
    _log("\n[분석] 수익 카테고리 분포:", on_log)
    analysis = analyze_titles.analyze(all_titles)
    analyze_titles.print_report(analysis)

    # pub코드 운영자별 카테고리 요약 (상위 3명)
    if pub_groups and pub_titles:
        _log("\n[분석] pub코드 운영자별 콘텐츠 분석 (상위 3명):", on_log)
        for pub, sites in list(pub_groups.items())[:3]:
            op_titles = title_collector.collect_from_all(set(sites), on_log=None)
            if op_titles:
                op_analysis = analyze_titles.analyze(op_titles)
                top_cats = sorted(
                    op_analysis.get("categories", {}).items(),
                    key=lambda x: x[1], reverse=True
                )[:3]
                cat_str = ", ".join(f"{c}({n})" for c, n in top_cats)
                _log(f"  {pub} ({len(sites)}개 사이트, {len(op_titles)}개 글): {cat_str}", on_log)

    # ── 5단계: 키워드 추출 ────────────────────────────────
    _log("\n[5단계] 키워드 추출 중...", on_log)
    candidates = title_collector.extract_keywords_from_titles(all_titles)
    _log(f"[5단계] 후보 키워드 {len(candidates)}개", on_log)

    if not candidates:
        _log("[엔진] 키워드 추출 실패 — 종료", on_log)
        return []

    # ── 6단계: 기회점수 계산 (블로그 발행량 기반, API 비용 없음) ──
    _log(f"\n[6단계] 기회점수 계산 중 ({len(candidates)}개)...", on_log)
    _log("  (Naver 블로그 발행량 기반 — 검색광고 API 비용 없음)", on_log)
    scored = keyword_scorer.score_keywords(
        candidates,
        get_pub_count_fn=naver_api.get_blog_count,
        on_log=on_log,
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

    # GSC 교차 (선택)
    gsc_boost = set(gsc_connector.get_rising_keywords())
    if gsc_boost:
        boosted = [k for k in filtered if k["keyword"] in gsc_boost]
        rest = [k for k in filtered if k["keyword"] not in gsc_boost]
        filtered = boosted + rest

    # DB 저장
    for item in filtered:
        db_handler.upsert_keyword(
            item["keyword"], item["score"], item["volume"], item["pub_count"]
        )

    top = filtered[:top_n]

    # 결과 출력
    _log(f"\n{'═' * 55}", on_log)
    _log(f"  결과: 상위 {len(top)}개 키워드", on_log)
    _log(f"{'═' * 55}", on_log)
    for i, item in enumerate(top, 1):
        _log(
            f"{i:3}. {item['keyword']:<22} "
            f"점수:{item['score']:>12,.0f}  "
            f"검색량:{item['volume']:>7,}  "
            f"발행량:{item['pub_count']:>7,}",
            on_log,
        )

    # pub코드 운영자 요약
    _log(f"\n{'─' * 55}", on_log)
    _log(f"[pub코드 요약] 발견된 AdSense 운영자:", on_log)
    for pub, sites in pub_groups.items():
        _log(f"  {pub} → {len(sites)}개 사이트", on_log)

    # ── 8단계: Notion 큐 적재 ────────────────────────────
    if push_to_notion and blog_id and top:
        _log(f"\n[8단계] Notion 큐 적재 → {blog_id}", on_log)
        saved = queue_pusher.push(top, blog_id, on_log)
        _log(f"[8단계] {saved}개 저장 완료", on_log)

    return top


# ─────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="천하무적 키워드 엔진 — pub코드 역분석 + Tistory RSS",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예시:
  # 기본 실행 (Notion 미적재, Playwright 사용)
  python -m keyword_engine.main --no-push

  # 특정 블로그에 적재
  python -m keyword_engine.main --blog nolja100

  # Playwright 없이 경량 모드
  python -m keyword_engine.main --no-playwright --no-push
        """,
    )
    parser.add_argument("--top", type=int, default=DEFAULT_TOP_N)
    parser.add_argument("--blog", default=None)
    parser.add_argument("--min-score", type=float, default=DEFAULT_MIN_SCORE)
    parser.add_argument("--min-volume", type=int, default=DEFAULT_MIN_VOLUME)
    parser.add_argument("--no-push", action="store_true")
    parser.add_argument("--no-playwright", action="store_true",
                        help="Playwright 대신 경량 urllib 모드 사용")
    args = parser.parse_args()

    run(
        top_n=args.top,
        blog_id=args.blog,
        min_score=args.min_score,
        min_volume=args.min_volume,
        push_to_notion=not args.no_push,
        use_playwright=not args.no_playwright,
    )
