"""매일 미채점 키워드 1,000개 네이버 API 채점 — cron 실행용"""
import sys
import time
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))

from keyword_engine import db_handler
from keyword_engine.keyword_scorer import get_search_volume, opportunity_score
from keyword_engine.naver_api import get_blog_count

DAILY_LIMIT = 1000
DELAY = 0.4  # API 호출 간격 (초)

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def run():
    log("=== 일일 키워드 채점 시작 ===")

    # 미채점(volume=0) 키워드 우선, 카테고리별 고르게 추출
    import sqlite3
    conn = sqlite3.connect(db_handler.DB_PATH)
    # 2~3어절 키워드 우선 (검색량 1000~3000 범위에 가장 많이 분포)
    rows = conn.execute(
        """
        SELECT keyword, category FROM keywords
        WHERE volume = 0 AND status = 'pending'
        ORDER BY
            CASE
                WHEN (LENGTH(keyword) - LENGTH(REPLACE(keyword, ' ', ''))) BETWEEN 1 AND 2 THEN 0
                WHEN (LENGTH(keyword) - LENGTH(REPLACE(keyword, ' ', ''))) = 3 THEN 1
                ELSE 2
            END,
            RANDOM()
        LIMIT ?
        """,
        (DAILY_LIMIT,)
    ).fetchall()
    conn.close()

    if not rows:
        log("채점할 키워드 없음 — 종료")
        return

    log(f"채점 대상: {len(rows)}개")
    scored = 0
    skipped = 0

    for keyword, category in rows:
        try:
            volume = get_search_volume(keyword)
            time.sleep(DELAY)
            pub_count = get_blog_count(keyword)
            score = opportunity_score(volume, pub_count)

            db_handler.upsert_keyword(keyword, score, volume, pub_count, category)
            scored += 1

            if scored % 50 == 0:
                log(f"진행: {scored}/{len(rows)}개")

        except Exception as e:
            log(f"⚠ '{keyword}' 오류: {e}")
            skipped += 1
            time.sleep(1)

    log(f"=== 완료: {scored}개 채점 / {skipped}개 스킵 ===")


if __name__ == "__main__":
    run()
