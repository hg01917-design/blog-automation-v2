"""Blogspot 봇 — blogspot_daily + blogspot_travel + blogspot_it 발행
링크 피라미드 2단계:
  - blogspot_travel: WP triplog URL 백링크 포함
  - blogspot_it: WP baremi542 URL 백링크 포함
  발행 후 crosslink 저장 → bot_tistory.py가 읽음
"""
import sys
import time
import random
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))

from overnight_run import (
    log, save_log, post_one_blog,
    LOG_DIR,
)

# 여행 계열 먼저, IT 계열 다음, 일반 마지막
BLOGSPOT_BLOGS = ["blogspot_travel", "blogspot_it", "blogspot_daily"]

if __name__ == "__main__":
    log("=" * 60)
    log(f"[Blogspot 봇] 시작 ({datetime.now().strftime('%Y-%m-%d %H:%M')})")
    log("=" * 60)

    target = sys.argv[1] if len(sys.argv) > 1 else None
    blogs = [target] if target and target in BLOGSPOT_BLOGS else BLOGSPOT_BLOGS

    results = {}
    for blog_id in blogs:
        log(f"\n[Blogspot 봇] {blog_id} 처리 시작")
        try:
            ok = post_one_blog(blog_id)
            results[blog_id] = "✅" if ok else "⚠"
        except Exception as e:
            log(f"[Blogspot 봇] ❌ {blog_id} 예외: {e}")
            results[blog_id] = "❌"
        if blog_id != blogs[-1]:
            wait = random.uniform(60, 180)
            log(f"[Blogspot 봇] 다음 블로그까지 {wait:.0f}초 대기")
            time.sleep(wait)

    log(f"\n[Blogspot 봇] 완료: " + " / ".join(f"{k}:{v}" for k, v in results.items()))
    save_log()
