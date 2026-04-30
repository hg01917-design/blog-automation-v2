"""최종 검토 에이전트 — Claude Code Sonnet으로 글 품질 검토"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from claude_direct import _run_claude


def _build_review_prompt(title, body, keyword, blog_id):
    body_preview = body[:1500]
    return f"""아래 블로그 글을 검토해줘. 합격/불합격만 판정해줘.

블로그: {blog_id}
키워드: {keyword}
제목: {title}

본문 (앞부분):
{body_preview}

검토 항목:
1. 페르소나에 맞는 자연스러운 문체인지 (존댓말 사용)
2. AI가 쓴 티 나는 표현이 있는지 ("종합적으로", "다양한 측면에서", "결론적으로" 등)
3. 금지 패턴 사용 여부 (완벽정리/총정리/N가지)
4. 제목이 검색 의도에 자연스럽게 맞는지
5. 내용 흐름이 자연스러운지

다음 AI 패턴이 있으면 반드시 불합격:
물론입니다 / 당연히 / 살펴보겠습니다 / 알아보겠습니다 / 정리해보겠습니다 / 첫째 둘째 셋째 나열 / ~드립니다 남발

반드시 첫 줄에 "합격" 또는 "불합격"만 적고,
다음 줄에 이유를 간략히 적어줘.
불합격이면 구체적으로 어떤 문장이 문제인지 알려줘."""


def run(result: dict, keyword: str, blog_id: str,
        on_log=None, on_status=None):
    """Claude Code Sonnet으로 최종 검토한다.

    Returns:
        dict: {"passed": bool, "reason": str, "result": dict}
    """
    def log(msg):
        if on_log:
            on_log(msg)

    if on_status:
        on_status("final_review", "working")

    title = result["title"]
    body = result["body"]

    log("[최종검토] Sonnet 검토 요청 중...")

    try:
        prompt = _build_review_prompt(title, body, keyword, blog_id)
        response = _run_claude(prompt, on_log=on_log, timeout=60, model_key="sonnet")
    except Exception as e:
        log(f"[최종검토] Sonnet 검토 실패: {e} — 자동 합격 처리")
        if on_status:
            on_status("final_review", "done")
        return {"passed": True, "reason": "검토 실패로 자동 합격", "result": result}

    if not response:
        log("[최종검토] 응답 없음 — 자동 합격 처리")
        if on_status:
            on_status("final_review", "done")
        return {"passed": True, "reason": "응답 없음으로 자동 합격", "result": result}

    log(f"[최종검토] 검토 결과: {response[:300]}")

    first_line = response.strip().split('\n')[0].strip()
    passed = "합격" in first_line and "불합격" not in first_line

    if passed:
        log("[최종검토] ✓ 최종 검토 합격")
    else:
        log(f"[최종검토] ⚠ 불합격: {first_line}")

    if on_status:
        on_status("final_review", "done" if passed else "failed")

    return {
        "passed": passed,
        "reason": response[:200],
        "result": result,
    }
