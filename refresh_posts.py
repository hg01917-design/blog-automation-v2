"""
발행 후 30~45일이 지난 글을 Claude로 내용 보완해서 재저장 (날짜 갱신).
구글/네이버는 최신 업데이트 글을 선호하므로 랭킹 유지에 효과적.

사용법:
  python3 refresh_posts.py          # 갱신 대상 체크 후 처리
  python3 refresh_posts.py --dry    # 드라이런 (실제 수정 없음)
"""

import os, re, json, sqlite3, time
from pathlib import Path
from datetime import datetime, timedelta

DB_PATH = Path(__file__).parent / "keyword_engine" / "engine.db"
LOG_DIR = Path(__file__).parent / "logs"

def _get_refresh_candidates(min_days=30, max_days=60):
    """30~60일 전 published 글 목록 반환."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cutoff_old = (datetime.now() - timedelta(days=max_days)).isoformat()
    cutoff_new = (datetime.now() - timedelta(days=min_days)).isoformat()
    cur.execute("""
        SELECT blog_id, keyword, title, updated_at
        FROM keyword_blog_status
        WHERE status='published'
          AND updated_at BETWEEN ? AND ?
          AND (refreshed_at IS NULL OR refreshed_at < ?)
        ORDER BY updated_at ASC
        LIMIT 3
    """, (cutoff_old, cutoff_new, cutoff_old))
    rows = cur.fetchall()
    conn.close()
    return rows

def _mark_refreshed(keyword: str, blog_id: str):
    """refreshed_at 필드 업데이트."""
    try:
        conn = sqlite3.connect(DB_PATH)
        # refreshed_at 컬럼이 없으면 추가
        try:
            conn.execute("ALTER TABLE keyword_blog_status ADD COLUMN refreshed_at TEXT")
            conn.commit()
        except:
            pass
        conn.execute(
            "UPDATE keyword_blog_status SET refreshed_at=? WHERE keyword=? AND blog_id=?",
            (datetime.now().isoformat(), keyword, blog_id)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[리프레시] DB 업데이트 실패: {e}")

def run_refresh(dry_run=False):
    """리프레시 대상 글 처리."""
    candidates = _get_refresh_candidates()
    if not candidates:
        print("[리프레시] 갱신 대상 없음")
        return
    print(f"[리프레시] 대상 {len(candidates)}개:")
    for blog_id, keyword, title, updated_at in candidates:
        print(f"  - [{blog_id}] {keyword} ({updated_at[:10]})")
        if not dry_run:
            _mark_refreshed(keyword, blog_id)
            print(f"  → refreshed_at 기록 완료 (실제 콘텐츠 보완은 overnight_run.py 재실행으로)")

if __name__ == '__main__':
    import sys
    dry = '--dry' in sys.argv
    run_refresh(dry_run=dry)
