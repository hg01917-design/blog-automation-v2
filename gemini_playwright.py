"""gemini.google.com Playwright 자동화 — CDP 연결로 글 생성
claude_playwright.py와 동일한 generate_text() 인터페이스 제공
"""
import re
import time
import random
from browser import connect_cdp as _connect_cdp, get_or_create_page
from notion_prompt import fetch_prompt

GEMINI_URL = "https://gemini.google.com"

# blog_id별 Gemini Gem URL (없으면 일반 /app으로 이동)
BLOG_GEM_URLS = {
    "goodisak":  "https://gemini.google.com/gem/36eac0848ab2",
    "nolja100":  "https://gemini.google.com/gem/2941e44dba74",
    "salim1su":  "https://gemini.google.com/gem/d3f7514de1d7",
    "baremi542": "https://gemini.google.com/gem/c3a94011fe5c",
}

# 입력창 셀렉터 (Quill 에디터 기반)
INPUT_SEL_LIST = [
    'div.ql-editor[contenteditable="true"]',
    'rich-textarea .ql-editor',
    'div[role="textbox"][contenteditable="true"]',
    'textarea',
]

# 전송 버튼
SEND_BTN_SEL = ', '.join([
    'button[aria-label="Send message"]',
    'button[aria-label="메시지 보내기"]',
    'button.send-button',
    'button[data-test-id="send-button"]',
    'button[aria-label="Submit"]',
])

# 응답 텍스트 셀렉터
RESPONSE_SEL_LIST = [
    '.model-response-text',
    'message-content .markdown',
    'model-response .markdown-main-panel',
    '.response-content',
    'div.markdown.markdown-main-panel',
]

# 응답 완료 판정
MIN_CHARS_FOR_DONE = 1000
STABLE_SECS_REQUIRED = 15   # 15초 변화 없으면 완료
MAX_WAIT_SECS = 300          # 최대 5분
RETRY_THRESHOLD = 500
MAX_RETRIES = 2


def _count_body_chars(text):
    """===본문=== 안의 순수 텍스트 글자수를 센다."""
    body_m = re.search(r"===본문===\s*\n(.*?)\n*===본문끝===", text, re.DOTALL)
    if not body_m:
        plain = re.sub(r"===\S+===|##.*|{{.*?}}|\[애드센스\]", "", text)
        return len(re.sub(r"\s+", "", plain))
    body = body_m.group(1)
    plain = re.sub(r"##.*|{{.*?}}|\[애드센스\]|\|.*", "", body)
    return len(re.sub(r"\s+", "", plain))


def _is_generating(page):
    """Gemini가 응답 생성 중인지 확인."""
    try:
        # 생성 중지 버튼이 있으면 생성 중
        stop_sel = ', '.join([
            'button[aria-label="Stop response"]',
            'button[aria-label="응답 중지"]',
            'button[aria-label="Stop generating"]',
            '.stop-button',
            'button[data-test-id="stop-button"]',
        ])
        if page.locator(stop_sel).count() > 0:
            return True

        # 로딩 인디케이터 확인
        loading_sel = '.loading-indicator, .thinking-indicator, [data-is-loading="true"]'
        if page.locator(loading_sel).count() > 0:
            return True
    except Exception:
        pass
    return False


def _get_response_len(page):
    """현재 최신 응답의 텍스트 길이 반환."""
    try:
        return page.evaluate("""() => {
            const sels = [
                '.model-response-text',
                'message-content .markdown',
                'model-response .markdown-main-panel',
                '.response-content',
                'div.markdown',
                '[class*="response"] p',
            ];
            let longest = '';
            for (const sel of sels) {
                const els = document.querySelectorAll(sel);
                if (els.length > 0) {
                    const t = els[els.length - 1].innerText || '';
                    if (t.length > longest.length) longest = t;
                }
            }
            return longest.length;
        }""")
    except Exception:
        return 0


def _wait_for_response(page, log):
    """응답 완료까지 대기."""
    prev_len = 0
    stable_count = 0

    # 생성 시작될 때까지 최대 15초 대기
    for _ in range(15):
        page.wait_for_timeout(1000)
        if _get_response_len(page) > 50 or _is_generating(page):
            break

    for i in range(MAX_WAIT_SECS):
        page.wait_for_timeout(1000)
        cur_len = _get_response_len(page)

        if i > 0 and i % 10 == 0:
            log(f"[Gemini] {i}초 경과... ({cur_len}자 생성됨, 안정 {stable_count}초)")

        if cur_len > 0 and cur_len == prev_len:
            stable_count += 1
        else:
            stable_count = 0
        prev_len = cur_len

        # 충분한 글자수 + 15초 안정 → 완료
        if cur_len >= MIN_CHARS_FOR_DONE and stable_count >= STABLE_SECS_REQUIRED:
            log(f"[Gemini] 응답 완료 ({cur_len}자, {stable_count}초 안정)")
            return cur_len

        # 생성 완료 버튼 사라짐 + 최소 대기
        if i >= 20 and not _is_generating(page) and stable_count >= 5:
            if cur_len >= MIN_CHARS_FOR_DONE:
                log(f"[Gemini] 응답 완료 (생성 종료 확인, {cur_len}자)")
                return cur_len
            elif stable_count >= STABLE_SECS_REQUIRED:
                log(f"[Gemini] 응답 정지 확정 ({cur_len}자)")
                return cur_len

    log(f"[Gemini] 최대 대기 시간 초과 — {prev_len}자")
    return prev_len


def _extract_response(page, log):
    """DOM에서 마지막 응답 텍스트 추출."""
    page.wait_for_timeout(2000)
    response_text = ""

    for sel in RESPONSE_SEL_LIST:
        if response_text.strip():
            break
        try:
            els = page.locator(sel).all()
            if els:
                candidate = els[-1].inner_text()
                if len(candidate.strip()) > 50:
                    response_text = candidate
                    if sel != RESPONSE_SEL_LIST[0]:
                        log(f"[Gemini] 응답 셀렉터 폴백: {sel}")
        except Exception:
            pass

    if not response_text.strip():
        try:
            response_text = page.evaluate("""() => {
                const sels = [
                    '.model-response-text',
                    'message-content',
                    '[class*="response-content"]',
                    '[class*="model-response"]',
                ];
                for (const s of sels) {
                    const els = document.querySelectorAll(s);
                    if (els.length > 0) {
                        const t = els[els.length - 1].innerText;
                        if (t && t.length > 50) return t;
                    }
                }
                return '';
            }""")
        except Exception:
            pass

    if not response_text.strip():
        response_text = "[추출 실패] DOM에서 응답을 찾지 못했습니다."

    return response_text.strip()


def generate_text(prompt: str, blog_id: str = None, keyword: str = None,
                  on_log=None, extra_context: str = None):
    """gemini.google.com에 프롬프트를 보내고 응답 텍스트를 반환한다.

    claude_playwright.generate_text()와 동일한 인터페이스.
    blog_id + keyword가 주어지면 Notion에서 프롬프트를 가져와 사용.
    """
    def log(msg):
        if on_log:
            on_log(msg)

    # 볼드 처리 공통 규칙
    _BOLD_RULE = (
        "\n\n[볼드 처리 규칙]\n"
        "중요한 내용은 반드시 **볼드** 처리해줘.\n"
        "볼드 처리 대상: 핵심 키워드, 중요 수치/금액, 신청 기간 및 마감일, 자격 조건, 주의사항\n"
        "볼드 남용 금지: 한 문단에 1~2개 이내\n"
        "제목(H2/H3)은 볼드 처리 불필요"
    )

    # Gem이 설정된 blog_id면 키워드만 전송 (Gem 지침이 자동 적용됨)
    # Gem 미설정 blog_id면 기존대로 Notion에서 전체 프롬프트 가져오기
    gem_url = BLOG_GEM_URLS.get(blog_id) if blog_id else None
    if blog_id and keyword:
        if gem_url:
            prompt = f"키워드: {keyword}{_BOLD_RULE}"
            log(f"[Gemini] Gem 모드 — 키워드만 전송: '{keyword}'")
        else:
            try:
                prompt = fetch_prompt(blog_id, keyword, on_log)
                prompt = prompt + _BOLD_RULE
            except Exception as e:
                log(f"[Notion] 프롬프트 가져오기 실패: {e}")
                log("[Notion] 기본 프롬프트로 진행합니다.")

    # Gem 모드에서는 extra_context 스킵 (Gem 지침만으로 충분)
    if extra_context and not gem_url:
        prompt = f"{extra_context}\n\n---\n\n{prompt}"
        log(f"[Gemini] 팩트 컨텍스트 주입: {len(extra_context)}자")
    elif extra_context and gem_url:
        log(f"[Gemini] Gem 모드 — 팩트 컨텍스트 스킵")

    log(f"[Gemini] 프롬프트 길이: {len(prompt)}자")
    log(f"[Gemini] 프롬프트 처음 200자: {prompt[:200]}...")

    log("[Gemini] CDP 연결 중...")
    pw, browser = _connect_cdp(on_log)
    page = get_or_create_page(
        browser, url_contains="gemini.google.com", navigate_to=GEMINI_URL
    )
    if gem_url:
        log(f"[Gemini] Gem 모드: {blog_id} → {gem_url}")

    response_text = "[추출 실패] 응답 없음"

    try:
        for attempt in range(1, MAX_RETRIES + 2):
            if attempt > 1:
                log(f"[Gemini] === 재시도 {attempt - 1}/{MAX_RETRIES} ===")

            log(f"[Gemini] 페이지 준비 ({page.url})")

            # 새 대화 시작
            try:
                page.keyboard.press("Escape")
                page.wait_for_timeout(500)
            except Exception:
                pass

            page.on("dialog", lambda d: d.dismiss())

            # Gem 또는 일반 Gemini 페이지로 이동
            target_url = gem_url if gem_url else f"{GEMINI_URL}/app"
            page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(3000)

            # 입력창 찾기
            input_el = None
            used_sel = None
            for sel in INPUT_SEL_LIST:
                try:
                    el = page.locator(sel).first
                    if el.count() > 0:
                        el.wait_for(state="visible", timeout=5000)
                        input_el = el
                        used_sel = sel
                        log(f"[Gemini] 입력창 발견: {sel}")
                        break
                except Exception:
                    pass

            if not input_el:
                log("[Gemini] 입력창을 찾지 못함 — 재시도")
                page.wait_for_timeout(2000)
                continue

            # 클릭해서 포커스
            input_el.click()
            page.wait_for_timeout(500)

            # JavaScript로 텍스트 삽입 (execCommand 방식)
            page.evaluate("""(text) => {
                // Quill 에디터 처리
                const quill = document.querySelector('.ql-editor');
                if (quill) {
                    quill.focus();
                    document.execCommand('selectAll', false, null);
                    document.execCommand('insertText', false, text);
                    return;
                }
                // role=textbox 처리
                const tb = document.querySelector('div[role="textbox"][contenteditable="true"]');
                if (tb) {
                    tb.focus();
                    document.execCommand('selectAll', false, null);
                    document.execCommand('insertText', false, text);
                    return;
                }
                // textarea 처리
                const ta = document.querySelector('textarea');
                if (ta) {
                    ta.focus();
                    ta.value = text;
                    ta.dispatchEvent(new Event('input', {bubbles: true}));
                    ta.dispatchEvent(new Event('change', {bubbles: true}));
                }
            }""", prompt)
            page.wait_for_timeout(1000)

            # 입력 길이 확인
            typed_len = page.evaluate("""() => {
                const quill = document.querySelector('.ql-editor');
                if (quill) return quill.innerText.length;
                const tb = document.querySelector('div[role="textbox"][contenteditable="true"]');
                if (tb) return tb.innerText.length;
                const ta = document.querySelector('textarea');
                return ta ? ta.value.length : 0;
            }""")
            log(f"[Gemini] 입력창에 {typed_len}자 입력됨")

            if typed_len < 100:
                log("[Gemini] 프롬프트 입력 실패 — 재시도")
                page.wait_for_timeout(2000)
                continue

            # 전송
            sent = False
            try:
                btn = page.locator(SEND_BTN_SEL).first
                if btn.count() > 0:
                    btn.click(timeout=5000)
                    sent = True
                    log("[Gemini] 전송 버튼 클릭")
            except Exception as e:
                log(f"[Gemini] 전송 버튼 실패: {e}")

            if not sent:
                log("[Gemini] Enter 키로 전송")
                page.keyboard.press("Enter")

            page.wait_for_timeout(3000)

            # 응답 대기
            log("[Gemini] 응답 대기 중...")
            _wait_for_response(page, log)

            # 응답 추출
            log("[Gemini] 응답 추출 중...")
            response_text = _extract_response(page, log)

            body_chars = _count_body_chars(response_text)
            log(f"[Gemini] 추출 완료 (전체 {len(response_text)}자, 본문 {body_chars}자)")
            log(f"[Gemini] 응답 처음 200자: {response_text[:200]}")

            if body_chars >= RETRY_THRESHOLD:
                return response_text

            if attempt <= MAX_RETRIES:
                log(f"[Gemini] 본문 {body_chars}자 < {RETRY_THRESHOLD}자 — 재시도")
                page.wait_for_timeout(3000)
                continue

            log(f"[Gemini] 재시도 소진 — {body_chars}자로 진행")
            return response_text

        return response_text

    finally:
        pw.stop()
