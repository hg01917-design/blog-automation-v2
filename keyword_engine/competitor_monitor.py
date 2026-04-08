"""경쟁 사이트 주기적 모니터링 — 새 포스트 감지 → 키워드 DB 추가

운영 방식:
  1. DB에 저장된 경쟁 사이트(pub코드 있는 다수 도메인 운영자) RSS 재크롤링
  2. 이전에 없던 새 제목만 추출
  3. 키워드 추출 + 네이버 자동완성 확장
  4. 기회점수 계산 후 DB에 추가
"""
import time
from datetime import datetime

from keyword_engine import db_handler, naver_api, title_collector
from keyword_engine.keyword_scorer import score_keywords

# 모니터링 기본값
DEFAULT_MIN_DOMAINS = 5      # 최소 도메인 수 (파워 운영자 기준)
DEFAULT_TOP_OWNERS = 30      # 상위 운영자 N명
DEFAULT_MIN_VOLUME = 300     # 신규 키워드 최소 검색량
DEFAULT_MIN_SCORE = 500      # 신규 키워드 최소 기회점수
DEFAULT_MAX_PUB_COUNT = 50_000  # 경쟁 글 최대 수


def _get_new_titles(site_url: str, rss_titles: list) -> list:
    """RSS 제목 중 DB titles 테이블에 없는 신규 제목만 반환"""
    with db_handler._conn() as db:
        existing = set(
            r[0] for r in db.execute(
                "SELECT title FROM titles WHERE site_url = ?", (site_url,)
            ).fetchall()
        )
    return [t for t in rss_titles if t not in existing]


def _update_monitored_at(site_url: str):
    """sites.monitored_at 갱신 (컬럼 없으면 자동 추가)"""
    with db_handler._conn() as db:
        try:
            db.execute("ALTER TABLE sites ADD COLUMN monitored_at TEXT")
        except Exception:
            pass
        db.execute(
            "UPDATE sites SET monitored_at = ? WHERE url = ?",
            (datetime.now().isoformat(), site_url),
        )


def monitor_competitors(
    category: str = None,
    min_domains: int = DEFAULT_MIN_DOMAINS,
    top_owners: int = DEFAULT_TOP_OWNERS,
    min_volume: int = DEFAULT_MIN_VOLUME,
    min_score: float = DEFAULT_MIN_SCORE,
    max_pub_count: int = DEFAULT_MAX_PUB_COUNT,
    on_log=None,
) -> int:
    """
    저장된 경쟁 사이트 RSS를 재크롤링하여 신규 키워드를 DB에 추가.

    Args:
        category: 특정 카테고리만 대상 (None = 전체)
        min_domains: 파워 운영자 최소 도메인 수
        top_owners: 상위 운영자 최대 수
        min_volume / min_score / max_pub_count: 키워드 필터 기준

    Returns:
        추가된 새 키워드 수
    """
    def _log(msg):
        print(msg, flush=True)
        if on_log:
            on_log(msg)

    _log("─" * 55)
    _log("  [경쟁 모니터] 신규 포스트 감지 시작")
    _log("─" * 55)

    # monitored_at 컬럼 사전 보장 (SELECT 전에)
    with db_handler._conn() as db:
        try:
            db.execute("ALTER TABLE sites ADD COLUMN monitored_at TEXT")
        except Exception:
            pass

    # ── 1. 모니터링 대상 사이트 결정 ──────────────────────
    if category:
        sites = db_handler.get_multidomain_sites(category, min_domains, top_owners)
        _log(f"[모니터] {category} 카테고리 {len(sites)}개 사이트")
    else:
        # 전체 카테고리 — pub코드 있는 다도메인 운영자 우선
        all_sites = []
        for cat in ["IT", "여행", "살림", "정부지원금", "정부지원", ""]:
            cat_sites = db_handler.get_multidomain_sites(cat, min_domains, top_owners)
            for s in cat_sites:
                if s not in all_sites:
                    all_sites.append(s)
        # 부족하면 단일 pub코드 사이트 보충
        if len(all_sites) < 50:
            with db_handler._conn() as db:
                rows = db.execute(
                    "SELECT url FROM sites WHERE pub_code IS NOT NULL AND pub_code != '' "
                    "ORDER BY monitored_at ASC NULLS FIRST, collected_at DESC LIMIT 100"
                ).fetchall()
            for r in rows:
                if r[0] not in all_sites:
                    all_sites.append(r[0])
        sites = all_sites
        _log(f"[모니터] 전체 {len(sites)}개 사이트 대상")

    if not sites:
        _log("[모니터] 모니터링 대상 없음 — 먼저 keyword_engine main.py 실행 필요")
        return 0

    # ── 2. 각 사이트 RSS 재크롤링 → 신규 제목 수집 ───────
    all_new_titles = []
    sites_with_new = 0

    for i, site_url in enumerate(sites):
        rss_titles = title_collector.collect_titles_from_rss(site_url)
        if not rss_titles:
            _update_monitored_at(site_url)
            continue

        new_titles = _get_new_titles(site_url, rss_titles)
        if new_titles:
            all_new_titles.extend(new_titles)
            db_handler.save_titles(site_url, new_titles)
            sites_with_new += 1
            _log(f"[모니터] {site_url} → 신규 {len(new_titles)}개")

        _update_monitored_at(site_url)

        if i > 0 and i % 20 == 0:
            _log(f"[모니터] 진행 {i}/{len(sites)}, 신규 제목 누적 {len(all_new_titles)}개")

        time.sleep(0.3)

    _log(f"\n[모니터] {sites_with_new}개 사이트에서 신규 제목 {len(all_new_titles)}개 발견")

    if not all_new_titles:
        _log("[모니터] 신규 포스트 없음 — DB 최신 상태")
        return 0

    # ── 3. 키워드 추출 + 자동완성 확장 ────────────────────
    raw_kws = title_collector.extract_keywords_from_titles(all_new_titles, top_n=120)
    _log(f"[모니터] 원시 키워드 {len(raw_kws)}개 추출")

    expanded = naver_api.expand_keywords_with_autocomplete(raw_kws, on_log=on_log)
    _log(f"[모니터] 자동완성 확장 후 {len(expanded)}개")

    # ── 4. 기회점수 계산 ───────────────────────────────────
    _log(f"[모니터] 기회점수 계산 중 ({len(expanded)}개)...")
    scored = score_keywords(
        expanded,
        get_pub_count_fn=naver_api.get_blog_count,
        on_log=on_log,
    )

    # ── 5. 필터링 + DB 저장 ────────────────────────────────
    added = 0
    for item in scored:
        if (item["volume"] >= min_volume
                and item["score"] >= min_score
                and item["pub_count"] <= max_pub_count):
            db_handler.upsert_keyword(
                item["keyword"], item["score"], item["volume"], item["pub_count"]
            )
            added += 1

    _log(
        f"[모니터] {added}개 키워드 DB 추가 "
        f"(검색량 {min_volume:,}+, 점수 {min_score:,}+, 경쟁글 {max_pub_count:,}↓)"
    )
    return added


if __name__ == "__main__":
    import argparse
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).parent.parent))

    parser = argparse.ArgumentParser(description="경쟁 사이트 주기적 모니터링")
    parser.add_argument("--category", default=None, help="특정 카테고리 (IT/여행/살림/정부지원금)")
    parser.add_argument("--min-domains", type=int, default=DEFAULT_MIN_DOMAINS)
    parser.add_argument("--top-owners", type=int, default=DEFAULT_TOP_OWNERS)
    parser.add_argument("--min-volume", type=int, default=DEFAULT_MIN_VOLUME)
    parser.add_argument("--min-score", type=float, default=DEFAULT_MIN_SCORE)
    parser.add_argument("--max-pub", type=int, default=DEFAULT_MAX_PUB_COUNT)
    args = parser.parse_args()

    count = monitor_competitors(
        category=args.category,
        min_domains=args.min_domains,
        top_owners=args.top_owners,
        min_volume=args.min_volume,
        min_score=args.min_score,
        max_pub_count=args.max_pub,
    )
    print(f"\n완료: {count}개 신규 키워드 추가됨")
