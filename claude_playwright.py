"""claude.ai Playwright 자동화 — CDP 연결로 글 생성"""
import re
import time
import random
from playwright.sync_api import TimeoutError as PlaywrightTimeout
from browser import connect_cdp as _connect_cdp, get_or_create_page
from notion_prompt import fetch_prompt

CLAUDE_URL = "https://claude.ai"

# blog_id별 Claude Project URL (없으면 일반 /new로 이동)
BLOG_PROJECT_URLS = {
    "goodisak":  "https://claude.ai/project/019ca495-0520-7706-8188-bcd875c96b68",
    "nolja100":  "https://claude.ai/project/019b689e-1dbb-706d-93f3-6174de3a4835",
    "salim1su":  "https://claude.ai/project/019c8917-8337-74e8-989b-edf14e462901",
    "baremi542": "https://claude.ai/project/019d2882-7cfb-72e0-a40f-9669bc6408d6",
}

# 전송 버튼 (한국어/영어 + 다양한 UI 버전 대응)
SEND_BTN_SEL = ', '.join([
    'button[aria-label="메시지 보내기"]',
    'button[aria-label="Send Message"]',
    'button[aria-label="Send message"]',
    'button[data-testid="send-button"]',
    'button[type="submit"]',
])
# assistant 응답 텍스트 셀렉터 (Claude.ai UI 버전별 대응)
RESPONSE_SEL = "div.standard-markdown"
RESPONSE_SEL_FALLBACKS = [
    "div.standard-markdown",
    "[data-testid='assistant-message-content']",
    ".font-claude-message div[class*='prose']",
    "div[class*='assistant'] div[class*='prose']",
    "div[class*='message-content']",
    "div[class*='response'] p",
]

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

        # 현재 응답 길이 (여러 셀렉터 시도)
        cur_len = 0
        try:
            cur_len = page.evaluate("""(prevCount) => {
                const sels = [
                    'div.standard-markdown',
                    '[data-testid="assistant-message-content"]',
                    '[class*="assistant-message"] [class*="prose"]',
                    '[class*="message-content"]',
                    '[class*="response"] p',
                ];
                for (const sel of sels) {
                    const els = document.querySelectorAll(sel);
                    if (els.length > prevCount) {
                        const t = els[els.length - 1].innerText;
                        if (t && t.length > 0) return t.length;
                    }
                    if (els.length > 0) {
                        const t = els[els.length - 1].innerText;
                        if (t && t.length > 100) return t.length;
                    }
                }
                return 0;
            }""", prev_response_count)
        except Exception:
            pass

        # 10초마다 로그
        if i > 0 and i % 10 == 0:
            log(f"[Playwright] {i}초 경과... ({cur_len}자 생성됨, 안정 {stable_count}초)")

        # 텍스트 변화 감지 — 10자 이하는 노이즈(사용자 메시지/thinking 표시)로 간주, 안정 카운트 안 함
        effective_len = cur_len if cur_len > 10 else 0
        if effective_len > 0 and effective_len == prev_len:
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
                # 글자수가 매우 짧으면(≤50) Claude가 확인 메시지만 보낸 것일 수 있음
                # 처음 한 번만 어떤 요소에서 왔는지 로그 출력
                if cur_len <= 50 and stable_count == 5:
                    try:
                        src = page.evaluate("""(prevCount) => {
                            const sels = ['div.standard-markdown','[data-testid="assistant-message-content"]',
                                '[class*="assistant-message"] [class*="prose"]','[class*="message-content"]','[class*="response"] p'];
                            for (const sel of sels) {
                                const els = document.querySelectorAll(sel);
                                if (els.length > 0) {
                                    const t = els[els.length-1].innerText||'';
                                    if (t.length > 0) return sel + ' → ' + t.substring(0,30);
                                }
                            }
                            return 'not found';
                        }""", prev_response_count)
                        log(f"[Playwright] 6자 출처: {src}")
                    except Exception:
                        pass
                # 추가 30초 대기 후 변화 없을 때만 포기
                if cur_len <= 50 and stable_count < STABLE_SECS_REQUIRED + 30:
                    continue
                if stable_count >= STABLE_SECS_REQUIRED:
                    log(f"[Playwright] 응답 정지 확정 ({cur_len}자)")
                    return cur_len

    log(f"[Playwright] 최대 대기 시간 초과 (5분) — {prev_len}자")
    return prev_len


def _extract_response(page, prev_response_count, log):
    """DOM에서 응답 텍스트를 추출한다. HTML→마크다운 변환으로 볼드/헤딩 보존."""
    page.wait_for_timeout(2000)
    response_text = ""

    # HTML 노드를 순회해 마크다운으로 변환 (볼드/**볼드**, 헤딩 ## 보존)
    _JS_TO_MD = """(sel) => {
        function toMd(el) {
            let r = '';
            for (const n of el.childNodes) {
                if (n.nodeType === 3) {
                    r += n.textContent;
                } else if (n.nodeType === 1) {
                    const t = n.tagName.toLowerCase();
                    if (t === 'strong' || t === 'b') r += '**' + toMd(n) + '**';
                    else if (t === 'em' || t === 'i') r += '*' + toMd(n) + '*';
                    else if (t === 'h2') r += '\\n## ' + toMd(n) + '\\n';
                    else if (t === 'h3') r += '\\n### ' + toMd(n) + '\\n';
                    else if (t === 'h1') r += '\\n# ' + toMd(n) + '\\n';
                    else if (t === 'p') r += toMd(n) + '\\n\\n';
                    else if (t === 'br') r += '\\n';
                    else if (t === 'li') r += '- ' + toMd(n) + '\\n';
                    else if (t === 'ul' || t === 'ol') r += '\\n' + toMd(n);
                    else if (t === 'code') r += '`' + n.textContent + '`';
                    else if (t === 'pre') r += '\\n```\\n' + n.textContent + '\\n```\\n';
                    else r += toMd(n);
                }
            }
            return r;
        }
        const els = document.querySelectorAll(sel);
        if (!els.length) return '';
        const md = toMd(els[els.length - 1]);
        return (md && md.trim().length > 50) ? md : '';
    }"""

    for sel in RESPONSE_SEL_FALLBACKS:
        if response_text.strip():
            break
        try:
            candidate = page.evaluate(_JS_TO_MD, sel)
            if candidate and len(candidate.strip()) > 50:
                response_text = candidate
                if sel != RESPONSE_SEL:
                    log(f"[Playwright] 응답 셀렉터 폴백 사용: {sel}")
        except Exception:
            pass

    # 최후 수단: innerText (볼드 손실)
    if not response_text.strip():
        try:
            response_text = page.evaluate("""() => {
                const sels = [
                    'div.standard-markdown',
                    '[data-testid*="assistant"]',
                    '[class*="assistant-message"]',
                    '[class*="response-content"]',
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

    # 최후 수단1.5: 가장 긴 텍스트 블록 자동 탐색 (셀렉터 변경 대응)
    if not response_text.strip():
        try:
            dom_info = page.evaluate("""() => {
                // 텍스트 100자 이상인 요소 중 가장 긴 것 3개 찾기
                const all = Array.from(document.querySelectorAll('div,article,section,p'));
                const candidates = all
                    .filter(el => {
                        const t = el.innerText || '';
                        return t.length > 100 && t.includes('===');
                    })
                    .sort((a, b) => (b.innerText||'').length - (a.innerText||'').length)
                    .slice(0, 3);
                return candidates.map(el => ({
                    tag: el.tagName,
                    cls: el.className.substring(0, 80),
                    id: el.id,
                    len: (el.innerText||'').length,
                    text: (el.innerText||'').substring(0, 200),
                }));
            }""")
            if dom_info:
                log(f"[Playwright] DOM 후보 요소 {len(dom_info)}개 발견:")
                for d in dom_info:
                    log(f"  <{d['tag']} class='{d['cls']}' id='{d['id']}'> {d['len']}자")
                # 가장 긴 후보에서 텍스트 추출
                best = page.evaluate("""() => {
                    const all = Array.from(document.querySelectorAll('div,article,section'));
                    const cands = all
                        .filter(el => (el.innerText||'').includes('===제목==='))
                        .sort((a, b) => (b.innerText||'').length - (a.innerText||'').length);
                    return cands.length ? cands[0].innerText : '';
                }""")
                if best and "===제목===" in best:
                    response_text = best
                    log(f"[Playwright] DOM 자동 탐색 성공: {len(best)}자")
        except Exception as e:
            log(f"[Playwright] DOM 자동 탐색 실패: {e}")

    # 최후 수단2: 페이지 전체 텍스트에서 ===제목=== 패턴 직접 탐색
    if not response_text.strip() or "추출 실패" in response_text:
        try:
            all_text = page.evaluate("""() => {
                // 모든 텍스트 노드에서 ===제목=== 패턴 검색
                const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
                let full = '';
                let n;
                while ((n = walker.nextNode())) full += n.textContent;
                return full;
            }""")
            if all_text and "===제목===" in all_text:
                # ===제목=== ~ ===이미지끝=== 구간 추출
                m = re.search(r"===제목===(.*?)(?:===이미지끝===|$)", all_text, re.DOTALL)
                if m:
                    response_text = "===제목===" + m.group(1)
                    if "===이미지끝===" in all_text:
                        response_text += "===이미지끝==="
                    log(f"[Playwright] 최후 폴백: 페이지 텍스트에서 섹션 추출 ({len(response_text)}자)")
        except Exception as e:
            log(f"[Playwright] 최후 폴백 실패: {e}")

    # 최종 검증: ===제목=== 없으면 UI 텍스트나 garbage를 잘못 추출한 것
    if response_text.strip() and "===제목===" not in response_text:
        log(f"[Playwright] ⚠ 추출된 텍스트에 ===제목=== 없음 — 잘못된 추출로 판단, 무효화")
        log(f"[Playwright] 추출 텍스트 앞 100자: {response_text[:100]}")
        response_text = ""

    if not response_text.strip():
        response_text = "[추출 실패] DOM에서 응답을 찾지 못했습니다."

    return response_text.strip()


def repair_text(raw: str, issues: list, on_log=None) -> str:
    """검수 실패한 글을 이슈 목록 기반으로 Claude에 부분 수정 요청.

    전체 재생성 대신 기존 글 + 문제점만 전달해서 빠르게 수정.
    Returns: 수정된 raw 텍스트 (실패 시 None)
    """
    def log(msg):
        if on_log:
            on_log(msg)

    issues_str = "\n".join(f"- {i}" for i in issues)
    repair_prompt = f"""아래 블로그 글에서 검수 실패한 부분만 수정해줘.
수정 후 동일한 ===섹션=== 형식 그대로 전체 글을 다시 출력해줘.

【수정해야 할 문제점】
{issues_str}

【수정 규칙】
- 문제가 없는 부분은 절대 바꾸지 말 것
- AI 패턴(당연히/살펴보겠습니다 등)은 자연스러운 구어체로 교체
- 제목에 직장인/주부 등 대상이 있으면 제거하고 검색 의도만 남길 것
- 형식(===제목===, ===본문===, ===태그===, ===이미지===)은 그대로 유지

【원본 글】
{raw}"""

    log("[repair] 부분 수정 요청 중...")
    result = generate_text(repair_prompt, on_log=on_log)
    if result and "추출 실패" not in result and len(result) > 200:
        log("[repair] ✓ 부분 수정 완료")
        return result
    log("[repair] 부분 수정 실패")
    return None


def generate_text(prompt: str, blog_id: str = None, keyword: str = None,
                   on_log=None, extra_context: str = None):
    """claude.ai에 프롬프트를 보내고 응답 텍스트를 반환한다.

    blog_id + keyword가 주어지면 Notion에서 프롬프트를 가져와 사용.
    extra_context가 있으면 프롬프트 맨 앞에 참고 자료로 주입.
    응답 500자 미만이면 최대 2회 재시도.
    Claude 실패 시 Gemini로 자동 폴백.
    """

    def log(msg):
        if on_log:
            on_log(msg)

    # 볼드 처리 + 제목 형식 + 이미지 공통 규칙
    _BOLD_RULE = (
        "\n\n[볼드 처리 규칙]\n"
        "중요한 내용은 반드시 **볼드** 처리해줘.\n"
        "볼드 처리 대상: 핵심 키워드, 중요 수치/금액, 신청 기간 및 마감일, 자격 조건, 주의사항\n"
        "볼드 남용 금지: 한 문단에 1~2개 이내\n"
        "제목(H2/H3)은 볼드 처리 불필요\n"
        "\n[제목 규칙]\n"
        "===제목=== 안의 제목은 반드시 명사형/명사구로 작성해.\n"
        "문장형 어미(~습니다/~해요/~입니다/~세요/~합니다/~있어요) 절대 금지.\n"
        "예) X: '갤럭시 S25 배터리 설정 방법을 알아보겠습니다'\n"
        "예) O: '갤럭시 S25 배터리 설정 방법'\n"
        "\n[이미지 규칙]\n"
        "반드시 ===이미지=== 섹션에 이미지 2개를 포함해줘.\n"
        "형식:\n"
        "===이미지===\n"
        "[이미지1]\n"
        "- Gemini프롬프트: (Gemini 이미지 생성용 영어 또는 한국어 프롬프트)\n"
        "- 파일명: (영문-소문자-하이픈.webp)\n"
        "- alt: (키워드 포함 한국어 alt 텍스트)\n"
        "[이미지2]\n"
        "- Gemini프롬프트: ...\n"
        "- 파일명: ...\n"
        "- alt: ...\n"
        "===이미지끝==="
    )

    # 본문 헤딩/볼드 형식 강제 규칙 (프로젝트 모드 포함 모든 블로그에 적용)
    _FORMAT_RULE = (
        "\n\n[본문 형식 규칙 — 필수]\n"
        "본문 소제목은 반드시 ## (H2) 또는 ### (H3) 마크다운 헤딩 형식으로 작성해.\n"
        "예) ## 소제목 텍스트\n"
        "중요 키워드·수치·조건은 **볼드** 처리해. (한 문단 1~2개 이내)\n"
        "본문 길이: 공백 제외 순수 텍스트 **반드시 2000자 이상** 작성 (소제목 3개 이상, 각 소제목 아래 3~5문단).\n"
    )

    # Claude Project가 설정된 blog_id면 키워드만 전송 — 프로젝트 지침이 모든 규칙 담당
    # 팩트(공식사이트 수치)는 동적 데이터라 프로젝트에 넣을 수 없으므로 별도 주입
    # 프로젝트 미설정 blog_id면 기존대로 Notion에서 전체 프롬프트 가져오기
    if blog_id and keyword:
        if blog_id in BLOG_PROJECT_URLS:
            # 프로젝트 모드: 키워드 + 형식 규칙 (프로젝트 지침이 내용/문체 담당, 형식은 여기서 강제)
            prompt = keyword + _FORMAT_RULE
            log(f"[Playwright] 프로젝트 모드 — 키워드+형식규칙 전송: '{keyword}'")
        else:
            try:
                prompt = fetch_prompt(blog_id, keyword, on_log)
                prompt = prompt + _BOLD_RULE
            except Exception as e:
                log(f"[Notion] 프롬프트 가져오기 실패: {e}")
                log("[Notion] 기본 프롬프트로 진행합니다.")

    # 팩트 컨텍스트 주입 — 프로젝트 모드 포함 항상 주입 (할루시네이션 방지 핵심)
    # 키워드 뒤에 붙여서 프로젝트 지침이 앞에 오도록 구조 유지
    if extra_context:
        prompt = f"{prompt}\n\n[참고 자료 — 아래 수치/날짜만 사용, 임의 수치 금지]\n{extra_context}"
        log(f"[Playwright] 팩트 컨텍스트 주입: {len(extra_context)}자")

    # 프롬프트 내용 확인 로그
    log(f"[Playwright] 프롬프트 길이: {len(prompt)}자")
    log(f"[Playwright] 프롬프트 처음 200자: {prompt[:200]}...")

    log("[Playwright] CDP 연결 중...")
    pw, browser = _connect_cdp(on_log)
    page = get_or_create_page(browser, url_contains="claude.ai", navigate_to=CLAUDE_URL)

    # blog_id에 해당하는 프로젝트 URL 결정
    project_url = BLOG_PROJECT_URLS.get(blog_id) if blog_id else None
    if project_url:
        log(f"[Playwright] 프로젝트 모드: {blog_id} → {project_url}")
    else:
        log(f"[Playwright] 일반 모드: /new")

    try:
        for attempt in range(1, MAX_RETRIES + 2):
            if attempt > 1:
                log(f"[Playwright] === 재시도 {attempt - 1}/{MAX_RETRIES} ===")
                page.wait_for_timeout(5000)

            log(f"[Playwright] claude.ai 페이지 준비 ({page.url})")

            # 새 대화 시작
            try:
                page.keyboard.press("Escape")
                page.wait_for_timeout(500)
            except Exception:
                pass

            # JavaScript 다이얼로그 자동 수락 (페이지 이동 시 confirm/alert 팝업 방지)
            page.on("dialog", lambda d: d.dismiss())

            if project_url:
                # 재시도 시 또는 현재 URL이 특정 채팅이면 프로젝트 루트로 새 채팅 시작
                if attempt > 1 or "/chat/" in page.url:
                    log(f"[Playwright] 프로젝트 루트로 새 채팅 시작")
                    page.goto(project_url, wait_until="domcontentloaded", timeout=30000)
                    page.wait_for_timeout(4000)
                else:
                    page.goto(project_url, wait_until="domcontentloaded", timeout=30000)
                    page.wait_for_timeout(3000)
            else:
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

            min_len = 3 if project_url else 100
            if typed_len < min_len:
                log("[Playwright] ⚠ 프롬프트 입력 실패 — 재시도")
                page.wait_for_timeout(2000)
                continue

            # 전송
            log("[Playwright] 전송 중...")
            sent = False
            try:
                send_btn = page.locator(SEND_BTN_SEL).first
                if send_btn.count() > 0:
                    send_btn.click(timeout=5000)
                    sent = True
                    log("[Playwright] 전송 버튼 클릭")
            except Exception as e:
                log(f"[Playwright] 전송 버튼 클릭 실패: {e}")

            if not sent:
                # 폴백: Enter 키
                log("[Playwright] 폴백 — Enter 키로 전송")
                page.keyboard.press("Enter")

            page.wait_for_timeout(2000)

            prev_response_count = page.locator(RESPONSE_SEL).count()
            log(f"[Playwright] 기존 응답 블록: {prev_response_count}개")

            # 응답 대기
            log("[Playwright] 응답 대기 중...")
            final_len = _wait_for_response(page, prev_response_count, log)

            # 응답 추출
            log("[Playwright] 응답 추출 중...")
            # 현재 페이지에 있는 응답 블록 수 확인 (디버그용)
            try:
                cur_sel_counts = {}
                for _sel in RESPONSE_SEL_FALLBACKS[:3]:
                    cur_sel_counts[_sel] = page.locator(_sel).count()
                log(f"[Playwright] 셀렉터별 응답 블록 수: {cur_sel_counts}")
            except Exception:
                pass
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


def generate_text_with_fallback(prompt: str, blog_id: str = None, keyword: str = None,
                                 on_log=None, extra_context: str = None):
    """AI_PROVIDER 환경변수에 따라 Claude 또는 Gemini로 글을 생성한다.

    AI_PROVIDER=claude (기본) → Claude.ai 사용
    AI_PROVIDER=gemini        → Gemini 사용
    """
    import os
    provider = os.environ.get("AI_PROVIDER", "claude").lower()

    def log(msg):
        if on_log:
            on_log(msg)

    if provider == "gemini":
        log("[Writer] Gemini.google.com으로 글 생성...")
        import gemini_playwright as _gemini
        return _gemini.generate_text(prompt, blog_id=blog_id, keyword=keyword,
                                     on_log=on_log, extra_context=extra_context)
    else:
        log("[Writer] Claude.ai로 글 생성...")
        return generate_text(prompt, blog_id=blog_id, keyword=keyword,
                             on_log=on_log, extra_context=extra_context)
