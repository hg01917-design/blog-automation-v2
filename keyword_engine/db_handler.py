"""SQLite 저장소 — 키워드/사이트/제목 중복 제거 (카테고리 지원)"""
import os
import sqlite3
from datetime import datetime
from pathlib import Path

# .app 번들에서도 프로젝트 루트의 DB 파일 사용 (영구 저장)
_project_root = Path(os.environ.get("BLOG_AUTO_PROJECT_ROOT", str(Path(__file__).parent.parent)))
DB_PATH = _project_root / "keyword_engine" / "engine.db"


def _conn():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    return db


def init_db():
    with _conn() as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS keywords (
                keyword   TEXT PRIMARY KEY,
                score     REAL    DEFAULT 0,
                volume    INTEGER DEFAULT 0,
                pub_count INTEGER DEFAULT 0,
                category  TEXT    DEFAULT '',
                created_at TEXT
            );
            CREATE TABLE IF NOT EXISTS keyword_blog_status (
                keyword    TEXT,
                blog_id    TEXT,
                status     TEXT DEFAULT 'pending',
                title      TEXT DEFAULT '',
                updated_at TEXT,
                PRIMARY KEY (keyword, blog_id)
            );
            CREATE TABLE IF NOT EXISTS sites (
                url          TEXT PRIMARY KEY,
                pub_code     TEXT,
                category     TEXT DEFAULT '',
                collected_at TEXT
            );
            CREATE TABLE IF NOT EXISTS titles (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                site_url TEXT,
                title    TEXT,
                UNIQUE(site_url, title)
            );
        """)
        # 마이그레이션: 기존 테이블에 컬럼 추가
        for col, dflt in [
            ("category", "''"),
            ("status",   "'pending'"),
        ]:
            try:
                db.execute(f"ALTER TABLE keywords ADD COLUMN {col} TEXT DEFAULT {dflt}")
            except Exception:
                pass
        try:
            db.execute("ALTER TABLE sites ADD COLUMN category TEXT DEFAULT ''")
        except Exception:
            pass
        try:
            db.execute("ALTER TABLE keyword_blog_status ADD COLUMN title TEXT DEFAULT ''")
        except Exception:
            pass

        # ── analytics 테이블 (GSC + AdSense 일별 수집) ──
        db.executescript("""
            CREATE TABLE IF NOT EXISTS gsc_daily (
                date       TEXT,
                blog_id    TEXT,
                clicks     INTEGER DEFAULT 0,
                impressions INTEGER DEFAULT 0,
                ctr        REAL    DEFAULT 0,
                avg_position REAL  DEFAULT 0,
                PRIMARY KEY (date, blog_id)
            );
            CREATE TABLE IF NOT EXISTS gsc_pages (
                date       TEXT,
                blog_id    TEXT,
                page_url   TEXT,
                clicks     INTEGER DEFAULT 0,
                impressions INTEGER DEFAULT 0,
                ctr        REAL    DEFAULT 0,
                position   REAL    DEFAULT 0,
                PRIMARY KEY (date, blog_id, page_url)
            );
            CREATE TABLE IF NOT EXISTS adsense_daily (
                date       TEXT PRIMARY KEY,
                earnings_krw REAL DEFAULT 0,
                pageviews  INTEGER DEFAULT 0,
                clicks     INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS revenue_goals (
                id         INTEGER PRIMARY KEY,
                monthly_target_krw INTEGER DEFAULT 1000000,
                updated_at TEXT
            );
        """)
        # revenue_goals 기본값
        db.execute(
            "INSERT OR IGNORE INTO revenue_goals (id, monthly_target_krw, updated_at) VALUES (1, 1000000, ?)",
            (datetime.now().isoformat(),)
        )


# 블로그별 주제 포화 임계값 (같은 지역/주제 이미 N개 이상이면 스킵)
_TOPIC_SATURATION = 2  # 같은 지역/OTT 2개 이상 발행 시 포화 (기존 3 → 2로 강화)

# 블로그 → 키워드 카테고리 매핑 (fetch_next_pending 카테고리 필터용)
# me1091은 쿠팡파트너스 제휴 블로그 — 키워드 엔진 미사용 (None으로 처리)
_BLOG_CATEGORY = {
    "goodisak": "IT",
    "nolja100": "여행",
    "triplog": "여행",
    "salim1su": "살림",
    "baremi542": "정부지원금",
    "woll100": "교통",
    "phn0502": "영화",
    "me1091": None,  # 제휴 블로그 — 키워드 엔진 미사용
    "blogspot_daily": "BlogspotKoreaTravel",
    "blogspot_travel": "Blogspot여행",
    "blogspot_it": "BlogspotIT",
}

# 블로그별 금지 키워드 접두/접미 (해당 단어 포함 시 스킵)
_BLOG_KEYWORD_BLACKLIST: dict[str, list[str]] = {
    "goodisak": ["대출", "주식", "증권", "코인", "펀드", "ETF", "장려금", "지원금", "실업급여"],
    "salim1su": ["주식", "증권", "코인", "펀드", "ETF", "투자", "대출", "청약", "부동산",
                 "장려금", "지원금", "실업급여", "육아휴직급여", "복지급여"],
    "nolja100": ["주식", "증권", "코인", "대출", "장려금", "지원금"],
    "triplog":  ["주식", "증권", "코인", "대출", "장려금", "지원금"],
}

# 여행 블로그 지역 키워드 목록 (nolja100/triplog)
_TRAVEL_LOCATIONS = [
    "제주", "부산", "서울", "강릉", "속초", "여수", "통영", "경주", "전주",
    "남해", "거제", "강화", "춘천", "안동", "포항", "울릉", "태안", "담양",
    "인천", "대전", "광주", "수원", "제천", "양양", "가평", "남이섬", "평창",
]

# phn0502 OTT 플랫폼 포화 임계값 (같은 플랫폼으로 N개 이상 발행 시 스킵)
_OTT_PLATFORMS = ["왓챠", "넷플릭스", "웨이브", "티빙", "쿠팡플레이", "시즌", "애플TV"]


def _is_topic_saturated(keyword: str, blog_id: str) -> bool:
    """이미 같은 주제(지역명/OTT)로 _TOPIC_SATURATION개 이상 발행했으면 True."""
    kw_lower = keyword.replace(" ", "")

    if blog_id in ("nolja100", "triplog"):
        for loc in _TRAVEL_LOCATIONS:
            if loc in kw_lower:
                with _conn() as db:
                    count = db.execute(
                        """SELECT COUNT(*) FROM keyword_blog_status
                           WHERE blog_id = ? AND status IN ('published', 'draft_saved')
                           AND REPLACE(keyword, ' ', '') LIKE ?""",
                        (blog_id, f"%{loc}%"),
                    ).fetchone()[0]
                if count >= _TOPIC_SATURATION:
                    return True

    if blog_id == "phn0502":
        for ott in _OTT_PLATFORMS:
            if ott in kw_lower:
                with _conn() as db:
                    count = db.execute(
                        """SELECT COUNT(*) FROM keyword_blog_status
                           WHERE blog_id = ? AND status IN ('published', 'draft_saved')
                           AND REPLACE(keyword, ' ', '') LIKE ?""",
                        (blog_id, f"%{ott}%"),
                    ).fetchone()[0]
                if count >= _TOPIC_SATURATION:
                    return True

    return False


def upsert_keyword(keyword: str, score: float, volume: int, pub_count: int,
                   category: str = "", blog_id: str = None):
    # 주제 포화 체크 — 이미 많이 발행된 지역이면 낮은 우선순위로 저장
    if blog_id and _is_topic_saturated(keyword, blog_id):
        score = score * 0.1  # 점수 대폭 낮춰서 큐 후순위로 밀기
    with _conn() as db:
        db.execute(
            """
            INSERT INTO keywords (keyword, score, volume, pub_count, category, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(keyword) DO UPDATE SET
                score      = excluded.score,
                volume     = excluded.volume,
                pub_count  = excluded.pub_count,
                category   = CASE WHEN excluded.category != '' THEN excluded.category
                                  ELSE keywords.category END
            """,
            (keyword, score, volume, pub_count, category, datetime.now().isoformat()),
        )


def save_site(url: str, pub_code: str, category: str = ""):
    with _conn() as db:
        db.execute(
            """
            INSERT INTO sites (url, pub_code, category, collected_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(url) DO UPDATE SET
                pub_code  = excluded.pub_code,
                category  = CASE WHEN excluded.category != '' THEN excluded.category
                                 ELSE sites.category END
            """,
            (url, pub_code, category, datetime.now().isoformat()),
        )


def save_titles(site_url: str, titles: list):
    with _conn() as db:
        db.executemany(
            "INSERT OR IGNORE INTO titles (site_url, title) VALUES (?, ?)",
            [(site_url, t) for t in titles],
        )


def get_top_keywords(n: int = 50, min_score: float = 0) -> list:
    with _conn() as db:
        rows = db.execute(
            """
            SELECT keyword, score, volume, pub_count, category
            FROM keywords
            WHERE score >= ?
            ORDER BY score DESC
            LIMIT ?
            """,
            (min_score, n),
        ).fetchall()
    return [dict(r) for r in rows]


def get_keywords_by_category(category: str, n: int = 50, min_score: float = 0) -> list:
    """카테고리별 키워드 조회 — 에이전트/GUI에서 호출"""
    with _conn() as db:
        rows = db.execute(
            """
            SELECT keyword, score, volume, pub_count, category,
                   COALESCE(status, 'pending') AS status
            FROM keywords
            WHERE category = ? AND score >= ?
            ORDER BY score DESC
            LIMIT ?
            """,
            (category, min_score, n),
        ).fetchall()
    return [dict(r) for r in rows]


def delete_keyword(keyword: str):
    """키워드 삭제"""
    with _conn() as db:
        db.execute("DELETE FROM keywords WHERE keyword = ?", (keyword,))


def set_keyword_status(keyword: str, status: str, blog_id: str = None, title: str = ""):
    """키워드 상태 변경.
    blog_id 있으면 keyword_blog_status에 per-blog 기록 (글로벌 상태 유지).
    blog_id 없으면 keywords 테이블의 글로벌 status 변경 (하위 호환).
    published 상태가 되면 keywords 테이블에서 삭제 (큐 정리).
    title: draft_saved 저장 시 생성된 글 제목 기록 (발행 후 정확한 매칭에 사용).
    """
    with _conn() as db:
        if blog_id:
            db.execute(
                """
                INSERT INTO keyword_blog_status (keyword, blog_id, status, title, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(keyword, blog_id) DO UPDATE SET
                    status = excluded.status,
                    title = CASE WHEN excluded.title != '' THEN excluded.title ELSE keyword_blog_status.title END,
                    updated_at = excluded.updated_at
                """,
                (keyword, blog_id, status, title, datetime.now().isoformat()),
            )
            # published → keywords 테이블에서 삭제 (큐 정리)
            if status == "published":
                db.execute("DELETE FROM keywords WHERE keyword = ?", (keyword,))
            # in_progress는 글로벌에도 반영
            elif status == "in_progress":
                db.execute(
                    "UPDATE keywords SET status = 'in_progress' WHERE keyword = ?",
                    (keyword,),
                )
        else:
            if status == "published":
                db.execute("DELETE FROM keywords WHERE keyword = ?", (keyword,))
            else:
                db.execute(
                    "UPDATE keywords SET status = ? WHERE keyword = ?",
                    (status, keyword),
                )


def get_sites_by_category(category: str) -> list:
    """카테고리별 수집된 사이트 목록"""
    with _conn() as db:
        rows = db.execute(
            "SELECT url, pub_code FROM sites WHERE category = ? ORDER BY collected_at DESC",
            (category,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_multidomain_sites(category: str, min_domains: int = 2, top_owners: int = 10) -> list:
    """카테고리별 다수 도메인 보유 펍코드 소유자의 사이트 목록 (도메인 많은 순)"""
    from collections import defaultdict
    with _conn() as db:
        rows = db.execute(
            "SELECT url, pub_code FROM sites "
            "WHERE category = ? AND pub_code IS NOT NULL AND pub_code != '' "
            "ORDER BY collected_at DESC",
            (category,),
        ).fetchall()
    pub_to_sites: dict = defaultdict(list)
    for r in rows:
        pub_to_sites[r["pub_code"]].append(r["url"])
    ranked = sorted(pub_to_sites.items(), key=lambda x: len(x[1]), reverse=True)
    result = []
    owner_count = 0
    for pub, sites in ranked:
        if len(sites) >= min_domains:
            result.extend(sites)
            owner_count += 1
            if owner_count >= top_owners:
                break
    return result


def get_category_stats() -> dict:
    """카테고리별 키워드/사이트 수 통계"""
    with _conn() as db:
        kw_rows = db.execute(
            "SELECT category, COUNT(*) as cnt FROM keywords WHERE category != '' "
            "GROUP BY category"
        ).fetchall()
        site_rows = db.execute(
            "SELECT category, COUNT(*) as cnt FROM sites WHERE category != '' "
            "GROUP BY category"
        ).fetchall()
    stats = {}
    for r in kw_rows:
        stats.setdefault(r["category"], {})["keywords"] = r["cnt"]
    for r in site_rows:
        stats.setdefault(r["category"], {})["sites"] = r["cnt"]
    return stats


def keyword_exists(keyword: str) -> bool:
    with _conn() as db:
        return (
            db.execute(
                "SELECT 1 FROM keywords WHERE keyword = ?", (keyword,)
            ).fetchone()
            is not None
        )


def _blacklist_sql(blog_id: str) -> tuple[str, list]:
    """블로그 금지 키워드를 SQL AND 조건과 파라미터로 반환."""
    terms = _BLOG_KEYWORD_BLACKLIST.get(blog_id, [])
    if not terms:
        return "", []
    conditions = " AND ".join(["k.keyword NOT LIKE ?" for _ in terms])
    params = [f"%{t}%" for t in terms]
    return f" AND {conditions}", params


def fetch_next_pending(blog_id: str = None) -> str | None:
    """상태가 pending인 키워드 중 점수 높은 것 1개 반환. 없으면 None.

    blog_id 지정 시: 해당 블로그 카테고리에 맞는 키워드만 반환.
    me1091은 키워드 엔진 미사용 → 항상 None 반환.
    """
    # 제휴 블로그는 키워드 엔진 미사용
    if blog_id == "me1091":
        return None

    bl_sql, bl_params = _blacklist_sql(blog_id or "")

    with _conn() as db:
        if blog_id:
            category = _BLOG_CATEGORY.get(blog_id)
            # baremi542는 '정부지원금'+'정부지원' 두 카테고리 모두 사용
            extra_category = "정부지원" if blog_id == "baremi542" else None
            if category:
                if extra_category:
                    row = db.execute(
                        f"""
                        SELECT k.keyword FROM keywords k
                        WHERE k.category IN (?, ?)
                          AND k.status NOT IN ('published')
                          AND LENGTH(k.keyword) >= 7
                          AND NOT EXISTS (
                            SELECT 1 FROM keyword_blog_status kbs
                            WHERE kbs.keyword = k.keyword
                              AND kbs.blog_id = ?
                              AND kbs.status IN ('published', 'failed', 'in_progress', 'draft_saved')
                          )
                          {bl_sql}
                        ORDER BY k.score DESC LIMIT 20
                        """,
                        (category, extra_category, blog_id, *bl_params),
                    ).fetchall()
                else:
                    row = db.execute(
                        f"""
                        SELECT k.keyword FROM keywords k
                        WHERE k.category = ?
                          AND k.status NOT IN ('published')
                          AND LENGTH(k.keyword) >= 7
                          AND NOT EXISTS (
                            SELECT 1 FROM keyword_blog_status kbs
                            WHERE kbs.keyword = k.keyword
                              AND kbs.blog_id = ?
                              AND kbs.status IN ('published', 'failed', 'in_progress', 'draft_saved')
                          )
                          {bl_sql}
                        ORDER BY k.score DESC LIMIT 20
                        """,
                        (category, blog_id, *bl_params),
                    ).fetchall()
            else:
                row = db.execute(
                    f"""
                    SELECT k.keyword FROM keywords k
                    WHERE k.status NOT IN ('published')
                      AND NOT EXISTS (
                        SELECT 1 FROM keyword_blog_status kbs
                        WHERE kbs.keyword = k.keyword
                          AND kbs.blog_id = ?
                          AND kbs.status IN ('published', 'failed', 'in_progress', 'draft_saved')
                      )
                      {bl_sql}
                    ORDER BY k.score DESC LIMIT 20
                    """,
                    (blog_id, *bl_params),
                ).fetchall()
        else:
            row = db.execute(
                "SELECT keyword FROM keywords WHERE status = 'pending' ORDER BY score DESC LIMIT 20"
            ).fetchall()

    # 포화 주제 건너뛰기
    for r in (row if isinstance(row, list) else [row] if row else []):
        kw = r["keyword"] if r else None
        if kw and not _is_topic_saturated(kw, blog_id or ""):
            return kw
    return None


def get_published_keywords(blog_id: str = None) -> list:
    """발행/임시저장/진행중 키워드 목록 반환 (중복 체크용).

    draft_saved·in_progress도 포함 — 이미 쓴 글이 DB에 있으면 재사용 방지.
    """
    with _conn() as db:
        if blog_id:
            rows = db.execute(
                "SELECT keyword FROM keyword_blog_status "
                "WHERE blog_id = ? AND status IN ('published', 'draft_saved', 'in_progress')",
                (blog_id,),
            ).fetchall()
        else:
            rows = db.execute(
                "SELECT keyword FROM keywords WHERE status IN ('published', 'draft_saved', 'in_progress')"
            ).fetchall()
    return [r["keyword"] for r in rows]


# ── Analytics 저장/조회 ──────────────────────────────────────────────────────

def save_gsc_daily(date: str, blog_id: str, clicks: int, impressions: int,
                   ctr: float, avg_position: float):
    with _conn() as db:
        db.execute(
            """INSERT INTO gsc_daily (date, blog_id, clicks, impressions, ctr, avg_position)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(date, blog_id) DO UPDATE SET
                   clicks=excluded.clicks, impressions=excluded.impressions,
                   ctr=excluded.ctr, avg_position=excluded.avg_position""",
            (date, blog_id, clicks, impressions, ctr, avg_position),
        )


def save_gsc_pages(date: str, blog_id: str, pages: list):
    """pages: [{"url": ..., "clicks": ..., "impressions": ..., "ctr": ..., "position": ...}]"""
    with _conn() as db:
        for p in pages:
            db.execute(
                """INSERT INTO gsc_pages (date, blog_id, page_url, clicks, impressions, ctr, position)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(date, blog_id, page_url) DO UPDATE SET
                       clicks=excluded.clicks, impressions=excluded.impressions,
                       ctr=excluded.ctr, position=excluded.position""",
                (date, blog_id, p["url"], p.get("clicks", 0),
                 p.get("impressions", 0), p.get("ctr", 0), p.get("position", 0)),
            )


def save_adsense_daily(date: str, earnings_krw: float, pageviews: int = 0, clicks: int = 0):
    with _conn() as db:
        db.execute(
            """INSERT INTO adsense_daily (date, earnings_krw, pageviews, clicks)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(date) DO UPDATE SET
                   earnings_krw=excluded.earnings_krw,
                   pageviews=excluded.pageviews, clicks=excluded.clicks""",
            (date, earnings_krw, pageviews, clicks),
        )


def get_monthly_earnings(year: int, month: int) -> float:
    prefix = f"{year:04d}-{month:02d}"
    with _conn() as db:
        row = db.execute(
            "SELECT COALESCE(SUM(earnings_krw), 0) FROM adsense_daily WHERE date LIKE ?",
            (f"{prefix}%",),
        ).fetchone()
    return row[0]


def get_revenue_goal() -> int:
    with _conn() as db:
        row = db.execute("SELECT monthly_target_krw FROM revenue_goals WHERE id=1").fetchone()
    return row[0] if row else 1_000_000


def set_revenue_goal(monthly_target_krw: int):
    with _conn() as db:
        db.execute(
            "UPDATE revenue_goals SET monthly_target_krw=?, updated_at=? WHERE id=1",
            (monthly_target_krw, datetime.now().isoformat()),
        )


def get_low_ctr_pages(threshold: float = 0.01, min_impressions: int = 100,
                      days: int = 7) -> list:
    """노출 많은데 CTR 낮은 페이지 (제목 수정 후보)"""
    from datetime import timedelta
    since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    with _conn() as db:
        rows = db.execute(
            """SELECT blog_id, page_url,
                      SUM(clicks) as total_clicks,
                      SUM(impressions) as total_impressions,
                      CAST(SUM(clicks) AS REAL)/NULLIF(SUM(impressions),0) as avg_ctr,
                      AVG(position) as avg_position
               FROM gsc_pages
               WHERE date >= ? AND impressions >= ?
               GROUP BY blog_id, page_url
               HAVING avg_ctr < ?
               ORDER BY total_impressions DESC
               LIMIT 20""",
            (since, min_impressions, threshold),
        ).fetchall()
    return [dict(r) for r in rows]


def get_rising_pages(days_recent: int = 3, days_compare: int = 7) -> list:
    """최근 N일 vs 이전 M일 대비 급상승 페이지"""
    from datetime import timedelta
    now = datetime.now()
    recent_start = (now - timedelta(days=days_recent)).strftime("%Y-%m-%d")
    compare_start = (now - timedelta(days=days_recent + days_compare)).strftime("%Y-%m-%d")
    compare_end = (now - timedelta(days=days_recent + 1)).strftime("%Y-%m-%d")
    with _conn() as db:
        rows = db.execute(
            """SELECT r.blog_id, r.page_url,
                      r.recent_clicks, c.prev_clicks,
                      CASE WHEN c.prev_clicks > 0
                           THEN CAST(r.recent_clicks AS REAL)/c.prev_clicks
                           ELSE 99 END AS growth_ratio
               FROM (
                   SELECT blog_id, page_url, SUM(clicks) as recent_clicks
                   FROM gsc_pages WHERE date >= ?
                   GROUP BY blog_id, page_url
               ) r
               LEFT JOIN (
                   SELECT blog_id, page_url, SUM(clicks) as prev_clicks
                   FROM gsc_pages WHERE date >= ? AND date <= ?
                   GROUP BY blog_id, page_url
               ) c USING(blog_id, page_url)
               WHERE r.recent_clicks >= 3
               ORDER BY growth_ratio DESC
               LIMIT 20""",
            (recent_start, compare_start, compare_end),
        ).fetchall()
    return [dict(r) for r in rows]


init_db()
