"""Google Search Console 연동 — 성과 수집 + 키워드 파생"""
import json
import urllib.request
import urllib.parse
from datetime import datetime, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent

BLOG_SITES = {
    "goodisak":  "https://welfare.baremi542.com/",
    "nolja100":  "https://issue.baremi542.com/",
    "baremi542": "https://baremi542.com/",
    "woll100":   "sc-domain:info.baremi542.com",   # GSC에 도메인 속성으로 등록됨
    "phn0502":   "sc-domain:film.baremi542.com",   # GSC에 도메인 속성으로 등록됨
    "triplog":   "https://app.baremi542.com/",
}


def _get_token() -> str:
    import sys
    sys.path.insert(0, str(BASE_DIR))
    from gsc_indexing import _get_access_token
    return _get_access_token()


def _gsc_query(site_url: str, start_date: str, end_date: str,
               dimensions: list, row_limit: int = 100) -> list:
    token = _get_token()
    encoded = urllib.parse.quote(site_url, safe="")
    url = f"https://www.googleapis.com/webmasters/v3/sites/{encoded}/searchAnalytics/query"
    body = json.dumps({
        "startDate": start_date,
        "endDate": end_date,
        "dimensions": dimensions,
        "rowLimit": row_limit,
    }).encode()
    req = urllib.request.Request(
        url, data=body,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    resp = json.loads(urllib.request.urlopen(req, timeout=15).read())
    return resp.get("rows", [])


def collect_daily(date: str = None) -> dict:
    """모든 블로그 일별 성과 수집 → DB 저장. date: YYYY-MM-DD (기본: 그제)"""
    from keyword_engine.db_handler import save_gsc_daily, save_gsc_pages
    if date is None:
        date = (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d")

    results = {}
    for blog_id, site_url in BLOG_SITES.items():
        try:
            # 전체 합계 — dimensions 없이 쿼리해야 상위 N개 제한 없이 정확한 수치 확보
            total_rows = _gsc_query(site_url, date, date, [], row_limit=1)
            if total_rows:
                clicks = total_rows[0].get("clicks", 0)
                impressions = total_rows[0].get("impressions", 0)
                ctr = total_rows[0].get("ctr", 0)
                avg_pos = total_rows[0].get("position", 0)
            else:
                clicks = impressions = ctr = avg_pos = 0
            save_gsc_daily(date, blog_id, clicks, impressions, ctr, round(avg_pos, 1))

            # 페이지별 집계
            page_rows = _gsc_query(site_url, date, date, ["page"], row_limit=200)
            pages = [
                {
                    "url": r["keys"][0],
                    "clicks": r["clicks"],
                    "impressions": r["impressions"],
                    "ctr": r["ctr"],
                    "position": r["position"],
                }
                for r in page_rows
            ]
            save_gsc_pages(date, blog_id, pages)
            results[blog_id] = {"clicks": clicks, "impressions": impressions, "pages": len(pages)}
        except Exception as e:
            results[blog_id] = {"error": str(e)}
    return results


def get_performance_summary(days: int = 7) -> dict:
    """최근 N일 블로그별 성과 합산"""
    from keyword_engine.db_handler import _conn
    since = (datetime.now() - timedelta(days=days + 2)).strftime("%Y-%m-%d")
    with _conn() as db:
        rows = db.execute(
            """SELECT blog_id,
                      SUM(clicks) as total_clicks,
                      SUM(impressions) as total_impressions,
                      AVG(avg_position) as avg_pos
               FROM gsc_daily WHERE date >= ?
               GROUP BY blog_id ORDER BY total_clicks DESC""",
            (since,),
        ).fetchall()
    return {r["blog_id"]: dict(r) for r in rows}


def get_rising_keywords_from_gsc(days_recent: int = 3, top_n: int = 10) -> list:
    """급상승 쿼리 → 롱테일 키워드 후보 반환"""
    from keyword_engine.db_handler import get_rising_pages, _conn
    rising = get_rising_pages(days_recent=days_recent)
    keywords = []
    for item in rising[:top_n]:
        # URL에서 키워드 추출 (slug)
        url = item.get("page_url", "")
        slug = url.rstrip("/").split("/")[-1]
        slug = urllib.parse.unquote(slug).replace("-", " ").replace("_", " ")
        if len(slug) >= 4:
            keywords.append({
                "keyword": slug[:40],
                "blog_id": item.get("blog_id"),
                "growth_ratio": item.get("growth_ratio", 1),
            })
    return keywords


def get_low_ctr_pages_with_titles(threshold: float = 0.01,
                                   min_impressions: int = 50) -> list:
    """CTR 낮은 페이지 + 제목 조회 (제목 수정 후보)"""
    from keyword_engine.db_handler import get_low_ctr_pages
    pages = get_low_ctr_pages(threshold=threshold, min_impressions=min_impressions)
    # URL에서 제목 추출 (slug → 가독성 있게 변환)
    for p in pages:
        url = p.get("page_url", "")
        slug = url.rstrip("/").split("/")[-1]
        p["slug"] = urllib.parse.unquote(slug).replace("-", " ")
    return pages


def generate_keywords_from_gsc(on_log=None) -> int:
    """GSC 급상승/저CTR 패턴 → 유사 키워드 DB 추가. 추가된 개수 반환."""
    from keyword_engine.db_handler import upsert_keyword, keyword_exists

    def log(msg):
        if on_log:
            on_log(msg)
        else:
            print(msg)

    added = 0
    try:
        rising = get_rising_keywords_from_gsc(days_recent=3, top_n=15)
        for item in rising:
            kw = item["keyword"]
            blog_id = item.get("blog_id", "")
            if not keyword_exists(kw) and len(kw) >= 5:
                # 카테고리 매핑
                _cat_map = {
                    "goodisak": "IT", "nolja100": "여행", "triplog": "여행",
                    "salim1su": "살림", "baremi542": "정부지원금",
                    "woll100": "교통", "phn0502": "영화",
                }
                category = _cat_map.get(blog_id, "")
                score = min(item.get("growth_ratio", 1) * 30, 90)
                upsert_keyword(kw, score=score, volume=0, pub_count=0,
                               category=category, blog_id=blog_id)
                log(f"[GSC] 급상승 키워드 추가: {kw} (score={score:.0f})")
                added += 1
    except Exception as e:
        log(f"[GSC] 키워드 생성 오류: {e}")
    return added
