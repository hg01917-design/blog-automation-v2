"""SQLite 저장소 — 키워드/사이트/제목 중복 제거"""
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
                keyword TEXT PRIMARY KEY,
                score   REAL    DEFAULT 0,
                volume  INTEGER DEFAULT 0,
                pub_count INTEGER DEFAULT 0,
                created_at TEXT
            );
            CREATE TABLE IF NOT EXISTS sites (
                url         TEXT PRIMARY KEY,
                pub_code    TEXT,
                collected_at TEXT
            );
            CREATE TABLE IF NOT EXISTS titles (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                site_url TEXT,
                title    TEXT,
                UNIQUE(site_url, title)
            );
        """)


def upsert_keyword(keyword: str, score: float, volume: int, pub_count: int):
    with _conn() as db:
        db.execute(
            """
            INSERT INTO keywords (keyword, score, volume, pub_count, created_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(keyword) DO UPDATE SET
                score     = excluded.score,
                volume    = excluded.volume,
                pub_count = excluded.pub_count
            """,
            (keyword, score, volume, pub_count, datetime.now().isoformat()),
        )


def save_site(url: str, pub_code: str):
    with _conn() as db:
        db.execute(
            "INSERT OR IGNORE INTO sites (url, pub_code, collected_at) VALUES (?, ?, ?)",
            (url, pub_code, datetime.now().isoformat()),
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
            SELECT keyword, score, volume, pub_count
            FROM keywords
            WHERE score >= ?
            ORDER BY score DESC
            LIMIT ?
            """,
            (min_score, n),
        ).fetchall()
    return [dict(r) for r in rows]


def keyword_exists(keyword: str) -> bool:
    with _conn() as db:
        return (
            db.execute(
                "SELECT 1 FROM keywords WHERE keyword = ?", (keyword,)
            ).fetchone()
            is not None
        )


init_db()
