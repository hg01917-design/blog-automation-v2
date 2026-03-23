"""키워드 에이전트 — Notion 큐에서 키워드 선택 + 필터링"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from overnight_run import (
    fetch_next_keyword,
    update_keyword_status,
    check_duplicate_post,
    check_keyword_duplicate_in_notion,
)
from keyword_crawler import _is_banned


def run(blog_id: str, on_log=None, on_status=None):
    """대기 키워드 중 유효한 것 하나를 반환한다.

    Returns:
        dict: {"keyword": str, "page_id": str} or None
    """
    def log(msg):
        if on_log:
            on_log(msg)

    if on_status:
        on_status("keyword", "working")

    log(f"[키워드] {blog_id} 대기 키워드 탐색 중...")

    # 최대 5개 키워드를 시도 (금지/유사문서 필터에 걸릴 수 있으므로)
    for attempt in range(5):
        kw, page_id = fetch_next_keyword(blog_id)

        if not kw:
            log(f"[키워드] {blog_id} 대기 키워드 없음")
            if on_status:
                on_status("keyword", "failed")
            return None

        log(f"[키워드] 후보: '{kw}'")

        # 노션 큐 내 중복 키워드 체크 (이미 완료된 유사 키워드)
        is_notion_dup, notion_matched = check_keyword_duplicate_in_notion(blog_id, kw)
        if is_notion_dup:
            log(f"[키워드] ⚠ 이미 완료된 유사 키워드: '{notion_matched}' — '{kw}' 실패 처리")
            update_keyword_status(page_id, "실패", memo=f"유사키워드 중복: {notion_matched[:30]}")
            continue

        # 금지 카테고리 필터
        if _is_banned(kw, blog_id):
            log(f"[키워드] ⚠ 금지 카테고리: '{kw}' → 실패 처리")
            update_keyword_status(page_id, "실패", memo="금지카테고리")
            continue

        # 유사문서 체크
        is_dup, matched = check_duplicate_post(blog_id, kw, on_log=log)
        if is_dup:
            log(f"[키워드] ⚠ 유사문서 발견: '{kw}' → 실패 처리")
            update_keyword_status(page_id, "실패", memo=f"유사문서: {matched[:30]}")
            continue

        # 통과
        log(f"[키워드] ✓ 키워드 확정: '{kw}'")
        update_keyword_status(page_id, "진행중")
        if on_status:
            on_status("keyword", "done")
        return {"keyword": kw, "page_id": page_id}

    log(f"[키워드] {blog_id} 유효한 키워드를 찾지 못함 (5회 시도)")
    if on_status:
        on_status("keyword", "failed")
    return None
