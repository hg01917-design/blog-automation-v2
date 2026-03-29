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


def upsert_keyword(keyword: str, score: float, volume: int, pub_count: int,
                   category: str = ""):
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


def set_keyword_status(keyword: str, status: str, blog_id: str = None):
    """키워드 상태 변경.
    blog_id 있으면 keyword_blog_status에 per-blog 기록 (글로벌 상태 유지).
    blog_id 없으면 keywords 테이블의 글로벌 status 변경 (하위 호환).
    """
    with _conn() as db:
        if blog_id:
            db.execute(
                """
                INSERT INTO keyword_blog_status (keyword, blog_id, status, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(keyword, blog_id) DO UPDATE SET
                    status = excluded.status,
                    updated_at = excluded.updated_at
                """,
                (keyword, blog_id, status, datetime.now().isoformat()),
            )
            # in_progress는 글로벌에도 반영
            if status == "in_progress":
                db.execute(
                    "UPDATE keywords SET status = 'in_progress' WHERE keyword = ?",
                    (keyword,),
                )
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


def fetch_next_pending(blog_id: str = None) -> str | None:
    """상태가 pending인 키워드 중 점수 높은 것 1개 반환. 없으면 None.

    blog_id 지정 시: 해당 블로그 카테고리에 맞는 키워드만 반환.
    """
    with _conn() as db:
        if blog_id:
            # 블로그 카테고리 매핑
            _BLOG_CATEGORY = {
                "goodisak": "IT",
                "nolja100": "여행",
                "salim1su": "살림",
                "baremi542": "정부지원금",
            }
            category = _BLOG_CATEGORY.get(blog_id)
            if category:
                row = db.execute(
                    """
                    SELECT k.keyword FROM keywords k
                    WHERE k.category = ?
                      AND k.status NOT IN ('published')
                      AND NOT EXISTS (
                        SELECT 1 FROM keyword_blog_status kbs
                        WHERE kbs.keyword = k.keyword
                          AND kbs.blog_id = ?
                          AND kbs.status IN ('published', 'failed', 'in_progress')
                      )
                    ORDER BY k.score DESC LIMIT 1
                    """,
                    (category, blog_id),
                ).fetchone()
            else:
                row = db.execute(
                    """
                    SELECT k.keyword FROM keywords k
                    WHERE k.status NOT IN ('published')
                      AND NOT EXISTS (
                        SELECT 1 FROM keyword_blog_status kbs
                        WHERE kbs.keyword = k.keyword
                          AND kbs.blog_id = ?
                          AND kbs.status IN ('published', 'failed', 'in_progress')
                      )
                    ORDER BY k.score DESC LIMIT 1
                    """,
                    (blog_id,),
                ).fetchone()
        else:
            row = db.execute(
                "SELECT keyword FROM keywords WHERE status = 'pending' ORDER BY score DESC LIMIT 1"
            ).fetchone()
    return row["keyword"] if row else None


def get_published_keywords(blog_id: str = None) -> list:
    """상태가 published인 키워드 목록 반환 (중복 체크용).

    blog_id 지정 시: 해당 블로그에서 발행된 키워드만 반환.
    """
    with _conn() as db:
        if blog_id:
            rows = db.execute(
                "SELECT keyword FROM keyword_blog_status WHERE blog_id = ? AND status = 'published'",
                (blog_id,),
            ).fetchall()
        else:
            rows = db.execute(
                "SELECT keyword FROM keywords WHERE status = 'published'"
            ).fetchall()
    return [r["keyword"] for r in rows]


init_db()
