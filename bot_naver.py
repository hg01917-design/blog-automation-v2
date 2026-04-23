"""네이버 봇 — salim1su + me1091 임시저장 (독립 운영)
네이버 블로그는 링크 피라미드와 무관하게 독립적으로 운영
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

NAVER_BLOGS = ["salim1su", "me1091"]

if __name__ == "__main__":
    log("=" * 60)
    log(f"[네이버 봇] 시작 ({datetime.now().strftime('%Y-%m-%d %H:%M')})")
    log("=" * 60)

    target = sys.argv[1] if len(sys.argv) > 1 else None
    blogs = [target] if target and target in NAVER_BLOGS else NAVER_BLOGS

    results = {}
    for blog_id in blogs:
        log(f"\n[네이버 봇] {blog_id} 처리 시작")
        try:
            ok = post_one_blog(blog_id)
            results[blog_id] = "✅" if ok else "⚠"
        except Exception as e:
            log(f"[네이버 봇] ❌ {blog_id} 예외: {e}")
            results[blog_id] = "❌"
        if blog_id != blogs[-1]:
            wait = random.uniform(120, 300)
            log(f"[네이버 봇] 다음 블로그까지 {wait:.0f}초 대기")
            time.sleep(wait)

    log(f"\n[네이버 봇] 완료: " + " / ".join(f"{k}:{v}" for k, v in results.items()))
    save_log()
