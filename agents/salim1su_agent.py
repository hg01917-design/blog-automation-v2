"""salim1su 전용 에이전트 — naver_agent 기반 + 세부 키워드 확장"""
import re
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from agents import naver_agent as _base
except ImportError:
    import naver_agent as _base

from claude_playwright import generate_text
from gemini_image import generate_images
from overnight_run import _truncate_title

BLOG_ID = "salim1su"
PERSONA_RULE = _base.PERSONA_RULE
_parse_raw = _base._parse_raw


def _expand_keyword(keyword: str, on_log=None) -> str:
    """단어 1개(띄어쓰기 없음)인 키워드를 세부 롱테일로 확장.

    claude.ai에 세부 롱테일 키워드 5개를 요청하고 첫 번째 줄을 반환.
    확장 실패 시 원본 키워드 반환.
    """
    def log(msg):
        if on_log:
            on_log(msg)

    # 띄어쓰기가 있으면 이미 롱테일 → 건너뜀
    if " " in keyword.strip():
        log(f"[키워드확장] '{keyword}' — 이미 롱테일, 확장 생략")
        return keyword

    log(f"[키워드확장] '{keyword}' — 세부 롱테일 확장 시작")

    expand_prompt = (
        f"키워드: {keyword}\n"
        "이 키워드로 네이버 블로그에 쓸 수 있는 세부 롱테일 키워드 5개 뽑아줘.\n"
        "조건: 실제 검색할 것 같은 표현, 중복 의미 없이, 번호 없이 한 줄에 하나씩만"
    )

    try:
        response = generate_text(expand_prompt, blog_id=BLOG_ID, keyword=keyword, on_log=log)
        if not response or "추출 실패" in response:
            log(f"[키워드확장] 응답 없음 — 원본 키워드 사용")
            return keyword

        # 응답에서 첫 번째 비어있지 않은 줄 선택
        lines = [line.strip() for line in response.strip().splitlines() if line.strip()]
        if lines:
            expanded = lines[0]
            log(f"[키워드확장] '{keyword}' → '{expanded}'")
            return expanded
        else:
            log(f"[키워드확장] 파싱 실패 — 원본 키워드 사용")
            return keyword
    except Exception as e:
        log(f"[키워드확장] 오류: {e} — 원본 키워드 사용")
        return keyword


def run(keyword: str, on_log=None, on_status=None):
    """글 + 이미지 생성 후 파싱된 결과를 반환한다.

    blog_id는 "salim1su"으로 고정됩니다.
    단어 1개(띄어쓰기 없음)인 키워드는 claude.ai로 롱테일 확장 후 글 생성.

    Returns:
        dict: {
            "title": str,
            "body": str,
            "tags": list,
            "images": list[dict],
            "image_paths": dict,
            "raw": str,
        } or None
    """
    blog_id = BLOG_ID

    def log(msg):
        if on_log:
            on_log(msg)

    if on_status:
        on_status("writer", "working")

    log(f"[{blog_id}] 페르소나 규칙 적용: {PERSONA_RULE}")

    # 1단계: 단어 1개 키워드면 세부 롱테일로 확장
    actual_keyword = _expand_keyword(keyword, on_log=log)

    # 2단계: Claude.ai 글 생성 (확장된 키워드로)
    log(f"[작성] {blog_id} / '{actual_keyword}' — Claude.ai 글 생성")
    raw = generate_text("", blog_id=blog_id, keyword=actual_keyword, on_log=log)

    if not raw or "추출 실패" in raw:
        log("[작성] 글 생성 실패")
        if on_status:
            on_status("writer", "failed")
        return None

    # 파싱
    result = _parse_raw(raw, actual_keyword, log)
    if not result:
        if on_status:
            on_status("writer", "failed")
        return None

    # Gemini 이미지 생성
    image_paths = {}
    if result["images"]:
        log(f"[작성] Gemini 이미지 {len(result['images'])}개 생성 시작")
        image_paths = generate_images(result["images"], on_log=log)
        log(f"[작성] 이미지 {len(image_paths)}개 생성 완료")

    result["image_paths"] = image_paths
    result["raw"] = raw

    log(f"[작성] 완료 — 제목: \"{result['title']}\" / 본문: {len(result['body'])}자 / 태그: {len(result['tags'])}개")
    if on_status:
        on_status("writer", "done")
    return result
