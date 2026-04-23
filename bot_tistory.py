"""Tistory 봇 — nolja100 + goodisak + woll100 + phn0502 임시저장
링크 피라미드 3단계:
  - nolja100: blogspot_travel URL 백링크 포함 (triplog URL 폴백)
  - woll100: blogspot_travel URL 백링크 포함
  - goodisak: blogspot_it URL 백링크 포함
임시저장 후 Claude Code가 검수하여 발행
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

# nolja100은 여행 계열 crosslink 우선 — 단독으로 먼저 처리
TISTORY_BLOGS = ["nolja100", "woll100", "goodisak", "phn0502"]

if __name__ == "__main__":
    log("=" * 60)
    log(f"[Tistory 봇] 시작 ({datetime.now().strftime('%Y-%m-%d %H:%M')})")
    log("=" * 60)

    target = sys.argv[1] if len(sys.argv) > 1 else None
    blogs = [target] if target and target in TISTORY_BLOGS else TISTORY_BLOGS

    results = {}
    for blog_id in blogs:
        log(f"\n[Tistory 봇] {blog_id} 처리 시작")
        try:
            ok = post_one_blog(blog_id)
            results[blog_id] = "✅" if ok else "⚠"
        except Exception as e:
            log(f"[Tistory 봇] ❌ {blog_id} 예외: {e}")
            results[blog_id] = "❌"
        if blog_id != blogs[-1]:
            wait = random.uniform(90, 240)
            log(f"[Tistory 봇] 다음 블로그까지 {wait:.0f}초 대기 (캡챠 방지)")
            time.sleep(wait)

    log(f"\n[Tistory 봇] 완료: " + " / ".join(f"{k}:{v}" for k, v in results.items()))
    save_log()
