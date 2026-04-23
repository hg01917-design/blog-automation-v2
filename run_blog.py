"""단일 블로그 파이프라인 실행 — app.py SchedulerWorker subprocess용"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

if __name__ == "__main__":
    blog_id = sys.argv[1] if len(sys.argv) > 1 else ""
    keyword = sys.argv[2] if len(sys.argv) > 2 else None
    if not blog_id:
        print("사용법: python3 run_blog.py <blog_id> [keyword]", flush=True)
        sys.exit(1)

    from agents import orchestrator
    result = orchestrator.run_single(
        blog_id,
        keyword=keyword,
        on_log=lambda m: print(m, flush=True),
    )
    import json
    print(f"__RESULT__:{json.dumps(result, ensure_ascii=False)}", flush=True)
