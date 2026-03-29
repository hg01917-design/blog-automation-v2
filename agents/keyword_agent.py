"""키워드 에이전트 — 로컬 DB(engine.db)에서 키워드 선택 + 필터링"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from keyword_engine import db_handler
from overnight_run import check_duplicate_post
from keyword_crawler import _is_banned, _is_allowed


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

    published = set(db_handler.get_published_keywords(blog_id))

    # 최대 10개 키워드를 시도 (필터에 걸릴 수 있으므로)
    for attempt in range(10):
        kw = db_handler.fetch_next_pending(blog_id)

        if not kw:
            log(f"[키워드] {blog_id} 대기 키워드 없음")
            if on_status:
                on_status("keyword", "failed")
            return None

        log(f"[키워드] 후보: '{kw}'")

        # 로컬 DB 중복 체크 (이미 발행된 유사 키워드)
        matched = _find_similar(kw, published)
        if matched:
            log(f"[키워드] ⚠ 이미 발행된 유사 키워드: '{matched}' — '{kw}' 건너뜀")
            db_handler.set_keyword_status(kw, "failed", blog_id)
            continue

        # 카테고리 불일치 필터 (양성: 블로그 주제와 맞는 키워드인지)
        if not _is_allowed(kw, blog_id):
            log(f"[키워드] ⚠ 카테고리 불일치: '{kw}' → {blog_id} 건너뜀")
            db_handler.set_keyword_status(kw, "failed", blog_id)
            continue

        # 금지 단어 필터 (음성: 명시적으로 금지된 단어 포함 여부)
        if _is_banned(kw, blog_id):
            log(f"[키워드] ⚠ 금지 단어 포함: '{kw}' → 건너뜀")
            db_handler.set_keyword_status(kw, "failed", blog_id)
            continue

        # 유사문서 체크 (블로그 실제 검색)
        is_dup, dup_matched = check_duplicate_post(blog_id, kw, on_log=log)
        if is_dup:
            log(f"[키워드] ⚠ 유사문서 발견: '{kw}' → 건너뜀")
            db_handler.set_keyword_status(kw, "failed", blog_id)
            continue

        # 통과 — 진행중으로 표시
        db_handler.set_keyword_status(kw, "in_progress", blog_id)
        log(f"[키워드] ✓ 키워드 확정: '{kw}'")
        if on_status:
            on_status("keyword", "done")
        return {"keyword": kw, "page_id": ""}

    log(f"[키워드] {blog_id} 유효한 키워드를 찾지 못함 (10회 시도)")
    if on_status:
        on_status("keyword", "failed")
    return None


def _find_similar(keyword: str, published: set) -> str:
    """발행된 키워드 중 유사한 것이 있으면 반환, 없으면 빈 문자열."""
    kw_norm = keyword.replace(" ", "")
    for p in published:
        if kw_norm == p.replace(" ", ""):
            return p
        # 핵심어 겹침: 2어절 이상 공통
        kw_words = set(keyword.split())
        p_words = set(p.split())
        if len(kw_words) >= 2 and len(kw_words & p_words) >= 2:
            return p
    return ""
