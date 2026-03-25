"""SQLite 저장소 — 키워드/사이트/제목 중복 제거 (카테고리 지원)"""
import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent / "engine.db"


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
        # 기존 테이블에 category 컬럼이 없으면 추가 (마이그레이션)
        try:
            db.execute("ALTER TABLE keywords ADD COLUMN category TEXT DEFAULT ''")
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
            SELECT keyword, score, volume, pub_count, category
            FROM keywords
            WHERE category = ? AND score >= ?
            ORDER BY score DESC
            LIMIT ?
            """,
            (category, min_score, n),
        ).fetchall()
    return [dict(r) for r in rows]


def get_sites_by_category(category: str) -> list:
    """카테고리별 수집된 사이트 목록"""
    with _conn() as db:
        rows = db.execute(
            "SELECT url, pub_code FROM sites WHERE category = ? ORDER BY collected_at DESC",
            (category,),
        ).fetchall()
    return [dict(r) for r in rows]


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


init_db()
