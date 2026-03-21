"""claude.ai Playwright 자동화 — CDP 연결로 글 생성"""
import re
import time
import random
from playwright.sync_api import TimeoutError as PlaywrightTimeout
from browser import connect_cdp as _connect_cdp, get_or_create_page
from notion_prompt import fetch_prompt

CLAUDE_URL = "https://claude.ai"

# 전송 버튼 (한국어/영어)
SEND_BTN_SEL = 'button[aria-label="메시지 보내기"], button[aria-label="Send Message"]'
# assistant 응답 텍스트 셀렉터 (thinking 제외, 본문만)
RESPONSE_SEL = "div.standard-markdown"

# 응답 완료 판정 기준
MIN_CHARS_FOR_DONE = 1000   # 이 글자수 미만이면 절대 완료 아님
STABLE_SECS_REQUIRED = 20   # 텍스트 변화 없음이 이 초 이상이어야 완료
MAX_WAIT_SECS = 300         # 최대 대기 5분
# 재시도
RETRY_THRESHOLD = 500       # 이 글자수 미만이면 재시도
MAX_RETRIES = 2


def _count_body_chars(text):
    """===본문=== 안의 순수 텍스트 글자수를 센다 (##, {{}}, 공백 제외)."""
    body_m = re.search(r"===본문===\s*\n(.*?)\n*===본문끝===", text, re.DOTALL)
    if not body_m:
        plain = re.sub(r"===\S+===|##.*|{{.*?}}|\[애드센스\]", "", text)
        return len(re.sub(r"\s+", "", plain))
    body = body_m.group(1)
    plain = re.sub(r"##.*|{{.*?}}|\[애드센스\]|\|.*", "", body)
    return len(re.sub(r"\s+", "", plain))


def _is_streaming_done(page):
    """스트리밍이 끝났는지 확인 — 전송 버튼 또는 stop 버튼 상태로 판단."""
    try:
        # 방법1: 전송 버튼이 다시 나타남 = 스트리밍 완료
        send_count = page.locator(SEND_BTN_SEL).count()
        if send_count > 0:
            return True
    except Exception:
        pass
    try:
        # 방법2: stop 버튼이 없으면 = 스트리밍 완료
        stop_btn = page.locator('button[aria-label="Stop Response"], button[aria-label="응답 중지"]')
        if stop_btn.count() == 0:
            return True
    except Exception:
        pass
    return False


def _wait_for_response(page, prev_response_count, log):
    """claude.ai 스트리밍 응답이 완료될 때까지 대기한다.

    완료 조건 (모두 충족해야 함):
    1. 텍스트 길이가 20초 이상 변화 없음
    2. 글자수가 1000자 이상
    예외: 스트리밍이 확실히 끝났으면 (전송 버튼 재출현) 글자수 무관하게 완료
    """
    prev_len = 0
    stable_count = 0

    for i in range(MAX_WAIT_SECS):
        page.wait_for_timeout(1000)

        # 현재 응답 길이
        cur_len = 0
        try:
            cur_len = page.evaluate("""(prevCount) => {
                const els = document.querySelectorAll('div.standard-markdown');
                if (els.length <= prevCount) return 0;
                return els[els.length - 1].innerText.length;
            }""", prev_response_count)
        except Exception:
            pass

        # 10초마다 로그
        if i > 0 and i % 10 == 0:
            log(f"[Playwright] {i}초 경과... ({cur_len}자 생성됨, 안정 {stable_count}초)")

        # 텍스트 변화 감지
        if cur_len > 0 and cur_len == prev_len:
            stable_count += 1
        else:
            stable_count = 0
        prev_len = cur_len

        # ── 완료 판정 ──

        # 조건A: 충분한 글자수 + 20초 변화 없음
        if cur_len >= MIN_CHARS_FOR_DONE and stable_count >= STABLE_SECS_REQUIRED:
            log(f"[Playwright] 응답 완료 ({cur_len}자, {stable_count}초 변화 없음)")
            return cur_len

        # 조건B: 스트리밍이 확실히 끝남 (전송 버튼 재출현) + 최소 대기 20초
        if i >= 20 and stable_count >= 5 and _is_streaming_done(page):
            if cur_len >= MIN_CHARS_FOR_DONE:
                log(f"[Playwright] 응답 완료 (스트리밍 종료 확인, {cur_len}자)")
                return cur_len
            else:
                # 글자수 부족하지만 스트리밍은 끝남
                log(f"[Playwright] ⚠ 스트리밍 종료됐지만 글자수 부족 ({cur_len}자 < {MIN_CHARS_FOR_DONE}자)")
                # 10초 더 대기 후 변화 없으면 포기
                if stable_count >= STABLE_SECS_REQUIRED:
                    log(f"[Playwright] 응답 정지 확정 ({cur_len}자)")
                    return cur_len

    log(f"[Playwright] 최대 대기 시간 초과 (5분) — {prev_len}자")
    return prev_len


def _extract_response(page, prev_response_count, log):
    """DOM에서 응답 텍스트를 추출한다."""
    page.wait_for_timeout(2000)
    response_text = ""

    # 1차: div.standard-markdown (새로 생긴 마지막 요소)
    try:
        elements = page.locator(RESPONSE_SEL).all()
        if len(elements) > prev_response_count:
            response_text = elements[-1].inner_text()
    except Exception:
        pass

    # 2차 fallback: div.font-claude-response
    if not response_text.strip():
        try:
            elements = page.locator("div.font-claude-response").all()
            if elements:
                last_resp = elements[-1]
                md_child = last_resp.locator("div.standard-markdown")
                if md_child.count() > 0:
                    response_text = md_child.last.inner_text()
                else:
                    response_text = last_resp.inner_text()
        except Exception:
            pass

    # 3차 fallback
    if not response_text.strip():
        try:
            all_els = page.locator(RESPONSE_SEL).all()
            if all_els:
                response_text = all_els[-1].inner_text()
        except Exception:
            pass

    if not response_text.strip():
        response_text = "[추출 실패] DOM에서 응답을 찾지 못했습니다."

    return response_text.strip()


def generate_text(prompt: str, blog_id: str = None, keyword: str = None,
                   on_log=None):
    """claude.ai에 프롬프트를 보내고 응답 텍스트를 반환한다.

    blog_id + keyword가 주어지면 Notion에서 프롬프트를 가져와 사용.
    응답 500자 미만이면 최대 2회 재시도.
    """

    def log(msg):
        if on_log:
            on_log(msg)

    # Notion 프롬프트 가져오기
    if blog_id and keyword:
        try:
            prompt = fetch_prompt(blog_id, keyword, on_log)
        except Exception as e:
            log(f"[Notion] 프롬프트 가져오기 실패: {e}")
            log("[Notion] 기본 프롬프트로 진행합니다.")

    # 프롬프트 내용 확인 로그
    log(f"[Playwright] 프롬프트 길이: {len(prompt)}자")
    log(f"[Playwright] 프롬프트 처음 200자: {prompt[:200]}...")

    log("[Playwright] CDP 연결 중...")
    pw, browser = _connect_cdp(on_log)
    page = get_or_create_page(browser, url_contains="claude.ai", navigate_to=CLAUDE_URL)

    try:
        for attempt in range(1, MAX_RETRIES + 2):
            if attempt > 1:
                log(f"[Playwright] === 재시도 {attempt - 1}/{MAX_RETRIES} ===")

            log(f"[Playwright] claude.ai 페이지 준비 ({page.url})")

            # 새 대화 시작
            try:
                page.keyboard.press("Escape")
                page.wait_for_timeout(500)
            except Exception:
                pass

            page.goto(f"{CLAUDE_URL}/new", wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(3000)

            if "/new" not in page.url:
                log("[Playwright] /new 페이지 로딩 재시도...")
                page.goto(f"{CLAUDE_URL}/new", wait_until="networkidle", timeout=30000)
                page.wait_for_timeout(3000)

            # 입력창
            input_sel = 'div[contenteditable="true"]'
            page.wait_for_selector(input_sel, state="visible", timeout=30000)
            log(f"[Playwright] 프롬프트 입력 중 ({len(prompt)}자)...")

            page.locator(input_sel).first.click()
            page.wait_for_timeout(300)
            page.evaluate("""(text) => {
                const el = document.querySelector('div[contenteditable="true"]');
                el.focus();
                document.execCommand('insertText', false, text);
            }""", prompt)
            page.wait_for_timeout(500)

            # 입력된 텍스트 길이 확인
            typed_len = page.evaluate("""() => {
                const el = document.querySelector('div[contenteditable="true"]');
                return el ? el.innerText.length : 0;
            }""")
            log(f"[Playwright] 입력창에 {typed_len}자 입력됨")

            if typed_len < 100:
                log("[Playwright] ⚠ 프롬프트 입력 실패 — 재시도")
                page.wait_for_timeout(2000)
                continue

            # 전송
            log("[Playwright] 전송 중...")
            send_btn = page.locator(SEND_BTN_SEL).first
            send_btn.click(timeout=5000)
            page.wait_for_timeout(2000)

            prev_response_count = page.locator(RESPONSE_SEL).count()
            log(f"[Playwright] 기존 응답 블록: {prev_response_count}개")

            # 응답 대기
            log("[Playwright] 응답 대기 중...")
            final_len = _wait_for_response(page, prev_response_count, log)

            # 응답 추출
            log("[Playwright] 응답 추출 중...")
            response_text = _extract_response(page, prev_response_count, log)

            # 글자수 확인
            body_chars = _count_body_chars(response_text)
            log(f"[Playwright] 추출 완료 (전체 {len(response_text)}자, 본문 순수 {body_chars}자)")
            log(f"[Playwright] 응답 처음 200자: {response_text[:200]}")

            # 500자 이상이면 성공
            if body_chars >= RETRY_THRESHOLD:
                return response_text

            # 500자 미만이고 재시도 횟수 남았으면 재시도
            if attempt <= MAX_RETRIES:
                log(f"[Playwright] ⚠ 본문 {body_chars}자 < {RETRY_THRESHOLD}자 — 재시도합니다")
                page.wait_for_timeout(3000)
                continue

            # 재시도 소진
            log(f"[Playwright] ⚠ 재시도 소진 — {body_chars}자로 진행")
            return response_text

        return response_text

    finally:
        pw.stop()
