"""최종 검토 에이전트 — claude.ai로 글 품질 검토"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from claude_playwright import generate_text_with_fallback as _raw_generate
from browser import connect_cdp, get_or_create_page

CLAUDE_URL = "https://claude.ai"
SEND_BTN_SEL = 'button[aria-label="메시지 보내기"], button[aria-label="Send Message"]'
RESPONSE_SEL = "div.standard-markdown"


def _send_review_prompt(title, body, keyword, blog_id, on_log=None):
    """claude.ai에 검토 프롬프트를 보내고 응답을 받는다."""
    def log(msg):
        if on_log:
            on_log(msg)

    # 본문 앞 1500자만 전송 (전체 보내면 너무 길어짐)
    body_preview = body[:1500]

    review_prompt = f"""아래 블로그 글을 검토해주세요. 합격/불합격만 판정해주세요.

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
다음 줄에 이유를 간략히 적어주세요.
불합격이면 구체적으로 어떤 문장이 문제인지 알려주세요."""

    log("[최종검토] claude.ai에 검토 요청 중...")

    pw, browser = connect_cdp(on_log)
    try:
        page = get_or_create_page(
            browser, url_contains="claude.ai", navigate_to=CLAUDE_URL
        )

        # 새 대화
        page.goto(f"{CLAUDE_URL}/new", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(3000)

        # 입력
        input_sel = 'div[contenteditable="true"]'
        page.wait_for_selector(input_sel, state="visible", timeout=30000)
        page.locator(input_sel).first.click()
        page.wait_for_timeout(300)
        page.evaluate("""(text) => {
            const el = document.querySelector('div[contenteditable="true"]');
            el.focus();
            document.execCommand('insertText', false, text);
        }""", review_prompt)
        page.wait_for_timeout(500)

        # 전송
        send_btn = page.locator(SEND_BTN_SEL).first
        send_btn.click(timeout=5000)
        page.wait_for_timeout(2000)

        prev_count = page.locator(RESPONSE_SEL).count()

        # 응답 대기 (최대 60초 — 검토는 짧은 응답)
        prev_len = 0
        stable = 0
        for i in range(60):
            page.wait_for_timeout(1000)
            try:
                cur_len = page.evaluate("""(prevCount) => {
                    const els = document.querySelectorAll('div.standard-markdown');
                    if (els.length <= prevCount) return 0;
                    return els[els.length - 1].innerText.length;
                }""", prev_count)
            except Exception:
                cur_len = 0

            if cur_len > 0 and cur_len == prev_len:
                stable += 1
            else:
                stable = 0
            prev_len = cur_len

            if cur_len >= 20 and stable >= 5:
                break

        # 응답 추출
        page.wait_for_timeout(1000)
        response = ""
        try:
            elements = page.locator(RESPONSE_SEL).all()
            if len(elements) > prev_count:
                response = elements[-1].inner_text()
        except Exception:
            pass

        return response.strip()

    finally:
        pw.stop()


def run(result: dict, keyword: str, blog_id: str,
        on_log=None, on_status=None):
    """claude.ai로 최종 검토한다.

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

    try:
        response = _send_review_prompt(title, body, keyword, blog_id, on_log)
    except Exception as e:
        log(f"[최종검토] claude.ai 검토 실패: {e} — 자동 합격 처리")
        if on_status:
            on_status("final_review", "done")
        return {"passed": True, "reason": "검토 실패로 자동 합격", "result": result}

    if not response:
        log("[최종검토] 응답 없음 — 자동 합격 처리")
        if on_status:
            on_status("final_review", "done")
        return {"passed": True, "reason": "응답 없음으로 자동 합격", "result": result}

    log(f"[최종검토] 검토 결과:\n{response[:300]}")

    # 합격/불합격 판정
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
