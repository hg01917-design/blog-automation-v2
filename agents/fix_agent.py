"""검수 불합격 자동 수정 에이전트 — AI 패턴 치환으로 재생성 없이 통과 시도"""
import re

# 블로그별 허용 패턴 (IT 블로그는 기술 용어 OK)
BLOG_WHITELIST = {
    "goodisak": {"AI", "ChatGPT", "LLM"},
}

# AI 패턴 → 자연스러운 한국어 치환
REPLACEMENTS = {
    "물론입니다": "맞아요",
    "당연히 ": "",
    "당연히": "",
    "주목해야": "눈여겨봐야",
    "살펴보겠습니다": "살펴볼게요",
    "알아보겠습니다": "알아볼게요",
    "정리해보겠습니다": "정리해볼게요",
    "해드리겠습니다": "해드릴게요",
    "첫째,": "1.",
    "둘째,": "2.",
    "셋째,": "3.",
    "핵심은 ": "중요한 건 ",
    "핵심은": "중요한 건",
    "포인트는 ": "중요한 건 ",
    "포인트는": "중요한 건",
    "ChatGPT": "챗GPT",
    "LLM": "대형 언어 모델",
    "AI": "인공지능",
    # 최종 검토 에이전트(Claude.ai)가 거부하는 AI 패턴 추가
    "결론적으로": "결국",
    "종합적으로": "전반적으로 보면",
    "다양한 측면에서": "여러 면에서",
    "정리했습니다": "정리했어요",
    "참고하시길 바랍니다": "참고하세요",
    "알아보도록 하겠습니다": "알아볼게요",
    "살펴보도록 하겠습니다": "살펴볼게요",
    "소개해드리겠습니다": "소개할게요",
    "설명해드리겠습니다": "설명할게요",
    "도움이 되셨으면 합니다": "도움이 됐으면 해요",
    "도움이 되길 바랍니다": "도움이 됐으면 해요",
}


def pre_clean(result: dict, blog_id: str, on_log=None) -> dict:
    """최종 검토 전 AI 패턴을 선제적으로 치환한다. 항상 result를 반환한다."""
    def log(msg):
        if on_log:
            on_log(msg)

    whitelist = BLOG_WHITELIST.get(blog_id, set())
    body = result["body"]
    fixed_count = 0

    for pattern, replacement in REPLACEMENTS.items():
        if pattern in whitelist:
            continue
        if pattern in body:
            body = body.replace(pattern, replacement)
            fixed_count += 1

    if fixed_count > 0:
        log(f"[fix] 사전 정제: {fixed_count}개 AI 패턴 치환 완료")
        result = dict(result)
        result["body"] = body

    return result


def run(result: dict, issues: list, blog_id: str, on_log=None) -> dict:
    """
    검수 이슈 목록을 받아 본문에서 AI 패턴을 치환.

    Returns:
        수정된 result dict (변경 없으면 None)
    """
    def log(msg):
        if on_log:
            on_log(msg)

    whitelist = BLOG_WHITELIST.get(blog_id, set())

    # AI 패턴 감지 이슈만 처리
    ai_issues = [i for i in issues if "AI 패턴 감지" in i]
    if not ai_issues:
        return None

    body = result["body"]
    fixed_count = 0

    for issue in ai_issues:
        # 이슈 메시지에서 패턴 추출: "AI 패턴 감지: 'XXX' 사용됨"
        m = re.search(r"'(.+?)' 사용됨", issue)
        if not m:
            continue
        pattern = m.group(1)

        # 블로그 화이트리스트에 있으면 스킵
        if pattern in whitelist:
            log(f"[fix] '{pattern}' → 화이트리스트 허용 (blog: {blog_id})")
            continue

        replacement = REPLACEMENTS.get(pattern)
        if replacement is None:
            log(f"[fix] '{pattern}' → 치환 규칙 없음")
            continue

        if pattern in body:
            body = body.replace(pattern, replacement)
            fixed_count += 1
            log(f"[fix] '{pattern}' → '{replacement}' ({body.count(replacement) if replacement else 0}곳)")

    if fixed_count == 0:
        log("[fix] 수정 가능한 패턴 없음")
        return None

    log(f"[fix] {fixed_count}개 패턴 수정 완료 — 재검수 시도")
    result = dict(result)
    result["body"] = body
    return result
